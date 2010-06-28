import datetime
from datetime import timedelta
import os
import re

import logging

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.ext.webapp import template
from google.appengine.ext.db import Key
from google.appengine.api.datastore import Get, Put

from django.utils import simplejson

### Model classes
from models.chatroom import * 

### Chat services (PyAMF)

def echo(data):
    return data

def loadMessages(latestMsgID = 0):
    logging.debug("<--------------- loadMessages -------------->")

    # Check if commands need to be executed
    result = checkCommandQueue()
    # Return early if a command has a return value
    if result:
        logging.debug(result)
        return result

    HISTORYSIZE = 1000
    if latestMsgID == 0:
        # User has just logged in, so send them all the chats
        recentChats = memcache.get("recentChats")
        # Query db for most recent messages and store in memcache
        if recentChats is None:
            recentChats = ChatMsg.all().order("-date").fetch(HISTORYSIZE)
            if len(recentChats) == 0:
                chats = recentChats = []
            else:
                recentChats.reverse()
                memcache.add("recentChats", recentChats, 60*60) 
        # Check that recentChats is not empty
        if len(recentChats):
            latestMsgID = recentChats[-1].id
            newChats = ChatMsg.all().order("id").filter("id > ", latestMsgID).fetch(HISTORYSIZE)
            recentChats.extend(newChats)
            chats = recentChats
    else:
        # Only return the most recent chats
        chats = ChatMsg.all().order("id").filter("id > ", latestMsgID).fetch(HISTORYSIZE)

    # Convert each object into a JSON-serializable object
    chats = [to_dict(chat) for chat in chats]

    stats = memcache.get_stats()
    logging.debug("Cache hits: " + str(stats['hits']))
    logging.debug("Cache misses: " + str(stats['misses']))

    return chats

def saveMessage(msg, latestMsgID):
    logging.debug("<--------------- saveMessages -------------->")

    # Check if commands need to be executed
    result = checkCommandQueue()
    # Return early if a command has a return value
    if result:
        logging.debug(result)
        return result

    # Check if user hasn't been added to CurrentUsers yet
    newUser = users.get_current_user()
    # Check if user is already in list
    user = CurrentUsers.all().filter("user = ", newUser).get()
    if user is None:
        logging.debug("adding new user in saveMessage")
        CurrentUsers.addUser()
        callback = "chat.getUsers"
    else:
        callback = None

    # Replace URLs with html code
    msg = re.sub(r'(https?:\/\/[0-9a-z_,.:;&=+*%$#!?@()~\'\/-]+)',
                 r'<a href="\1" target="_BLANK"><font color="#0000ff">\1</font></a>',
                 msg)
    ChatMsg.createChatMsg(msg, callback)

    return loadMessages(latestMsgID)

def getUsers():
    logging.debug("<-------------- getUsers --------------->")

    # Insert current user if not already in db, then update time
    currentUser = CurrentUsers.all().filter("user = ", users.get_current_user()).get()
    if currentUser is None:
        CurrentUsers.addUser()
    else:
        currentUser.date = datetime.datetime.now()
        currentUser.put()
    # Fetch all users
    userList = CurrentUsers.all().fetch(1000)
    validUserList = [currentUser for currentUser in userList if currentUser is not None]
    for currentUser in validUserList:
        # Get user's preferences and dynamically create them in the currentUser object
        prefs = UserPrefs.all().filter("user = ", currentUser.user).get()
        # Set user's nickname
        if prefs and prefs.nickname:
            currentUser.nickname = prefs.nickname 
        elif currentUser.user:
            currentUser.nickname = re.sub(r'^(.+)@.+$',
                                          r'\1',
                                          currentUser.user.email())
        else:
            currentUser.nickname = ""

        if prefs and prefs.isEmailVisible:
            currentUser.isEmailVisible = prefs.isEmailVisible 

        if currentUser.user == users.get_current_user():
            currentUser.isMe = True

    logging.debug(validUserList)
    #return [currentUser.user.nickname() for currentUser in userList if currentUser is not None]
    return validUserList

def updateUserPrefs(prefs):
    logging.debug("<-------------- updateUserPrefs --------------->")

    userPrefs = UserPrefs.all().filter("user = ", users.get_current_user()).get()
    if userPrefs is None:
        userPrefs = UserPrefs()
        userPrefs.user = users.get_current_user()
        userPrefs.put()

    # Add the user preferences dynamically
    objEntity = Get(userPrefs.key())
    for k, v in prefs.iteritems():
        objEntity[k] = v
    Put(objEntity)

               
        

def execCommand(latestMsgID, cmd, userName, message):
    logging.debug("<-------------- execCommand --------------->")
    logging.debug(cmd + ":" + userName + ":" + message)
    
    slashCommands[cmd](userName, message)

    #return loadMessages(latestMsgID)
    return

## The following methods are all helper methods for executing slash commands

def checkCommandQueue():
    # Define a response object
    class replyObj: pass
    commands = CommandQueue.all().fetch(1000)
    for command in commands:
        if command.cmd == 'kick':
            if command.target == users.get_current_user():
                obj = replyObj()
                obj.cmd = command.cmd
                chatMsg = ChatMsg()
                chatMsg.msg = "You have been kicked!" 
                if command.msg != '':
                    chatMsg.msg += ' (' + command.msg + ')'
                obj.reply = to_dict(chatMsg)
                # Remove the command from the db
                command.delete()
                return obj


    return None


def kickUser(userName, message):
    logging.debug("--kickUser--")
    logging.debug(userName + message)
    newCommand = CommandQueue()
    newCommand.sender = users.get_current_user()

    if newCommand.sender != users.User("herbert.siojo@gmail.com"):
        logging.warn("User tried to execute admin command: " + str(newCommand.sender))
        return

    

    newCommand.cmd = 'kick'
    newCommand.msg = message
    
    # First check if userName is a custom nickname
    userPrefs = UserPrefs.all().filter("nickname = ", userName).get()
    if userPrefs:
        newCommand.target = userPrefs.user
    else:
        # Otherwise userName is the default email
        currentUsers = CurrentUsers.all().fetch(1000)
        for currentUser in currentUsers:
            if currentUser.user and currentUser.user.nickname() == userName:
                newCommand.target = currentUser.user
                break

    if newCommand.target:
        newCommand.put()
 
    return 
    
slashCommands = {
    'msg' : lambda x: x * 5,
    'kick' : kickUser
}

