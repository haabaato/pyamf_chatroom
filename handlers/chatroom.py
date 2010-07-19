import datetime
from datetime import timedelta

import re

import logging

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.api import memcache
#from google.appengine.ext.webapp import template
from google.appengine.ext.db import Key
from google.appengine.api.datastore import Get, Put
from google.appengine.api import mail
from google.appengine.api import xmpp
from google.appengine.runtime.apiproxy_errors import CapabilityDisabledError

#from django.utils import simplejson

### Model classes
from models.chatroom import * 
from handlers.XMPPInterface import XMPPHandler

# Import constants and helper methods
from constants import *
from utils import getNickname

HISTORYSIZE = 500

CHAT_MSG = "%s %s: %s\n"
PRIV_MSG = "%s %s -> %s: %s\n"
USER_NOTEXIST_MSG = "The user '%s' does not exist. (Maybe they changed their nickname?)"

### Chat services (PyAMF)

def echo(data):
    return data

def loadMessages(latestChatID = 0, latestPrivMsgID = 0):
    logging.debug("<--------------- loadMessages -------------->")

    chats = loadChatMessages(latestChatID)
    privates = loadPrivateMessages(latestPrivMsgID)
    return [chats, privates]

def loadChatMessages(latestMsgID = 0):
    logging.debug("<--------------- loadChatMessages -------------->")
    logging.info("latestMsgID = " + str(latestMsgID))

    # Check if commands need to be executed
    result = checkCommandQueue()
    # Return early if a command has a return value
    if result:
        logging.debug(result)
        return result

    recentChats = memcache.get("recentChats")

    # Query db for most recent messages and store in memcache
    if recentChats is None or len(recentChats) == 0:
        logging.debug("making new memcache")
        recentChats = ChatMsg.all().order("id").fetch(HISTORYSIZE)
        if len(recentChats) == 0:
            recentChats = []
        else:
            memcache.add("recentChats", recentChats, 60*60*24) 

    if latestMsgID == 0:
        logging.debug("sending memcache:%d", len(recentChats))

        if len(recentChats):
            logging.debug("updating memcache")
            # Update recentChats in memcache
            recentID = recentChats[-1].id
            chats = ChatMsg.all().order("id").filter("id > ", recentID).fetch(HISTORYSIZE)
            recentChats.extend(chats)
            memcache.replace("recentChats", recentChats, 60*60*24) 
        # User has just logged in, so send them all the chats
        chats = recentChats

    else:
        # Only return the most recent chats
        chats = ChatMsg.all().order("id").filter("id > ", latestMsgID).fetch(HISTORYSIZE)

    # Convert each object into a JSON-serializable object
    chats = [to_dict(chat) for chat in chats]

    #stats = memcache.get_stats()
    #logging.debug("Cache hits: " + str(stats['hits']))
    #logging.debug("Cache misses: " + str(stats['misses']))

    return chats

def loadPrivateMessages(latestMsgID = 0):
    logging.debug("<--------------- loadPrivateMessages -------------->")

    user = users.get_current_user()
    if user is None:
        return
    logging.info("latestMsgID = " + str(latestMsgID)  + " for user:" + user.nickname())
    memcachekey = "recentPrivChats" + user.nickname()
    chats = []

    recentPrivChats = memcache.get(memcachekey)
    # Query db for most recent messages and store in memcache
    if recentPrivChats is None:
        logging.debug("making new memcache for key:%s", memcachekey)
        allPrivMsgs = PrivMsg.all().order("id").fetch(HISTORYSIZE)
        recentPrivChats = []
        if len(allPrivMsgs) != 0:
            # Remove messages that aren't from or to this user
            for chat in allPrivMsgs:
                if chat.sender == user or chat.target == user:
                    recentPrivChats.append(chat)

            memcache.add(memcachekey, recentPrivChats, 60*60*24) 

    if latestMsgID == 0:
        # Update recentPrivChats in memcache
        # Check that recentPrivChats is not empty
        if len(recentPrivChats):
            logging.debug("updating memcache for key:%s", memcachekey)
            recentID = recentPrivChats[-1].id
            newPrivMsgs = PrivMsg.all().order("id").filter("id > ", recentID).fetch(HISTORYSIZE)
            for chat in newPrivMsgs:
                if chat.sender == user or chat.target == user:
                    recentPrivChats.append(chat)

            memcache.replace(memcachekey, recentPrivChats, 60*60*24) 
        # User has just logged in, so send them all the chats
        chats = recentPrivChats
    else:
        # Only return the most recent chats
        newPrivMsgs = PrivMsg.all().order("id").filter("id > ", latestMsgID).fetch(HISTORYSIZE)
        for chat in newPrivMsgs:
            if chat.sender == user or chat.target == user:
                chats.append(chat)

    # Convert each object into a JSON-serializable object
    chats = [to_dict(chat) for chat in chats]

    return chats


def saveMessage(msg, latestChatID):
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
    msg = re.sub(HTML_REGEX,
                 r'<a href="\1" target="_BLANK"><font color="#0000ff">\1</font></a>',
                 msg)
    chat = ChatMsg.createMsg(msg, callback)
    sendToXmpp(chat)

    #return loadMessages(latestChatID, latestPrivMsgID)
    return loadChatMessages(latestChatID)

def getUsers():
    logging.debug("<-------------- getUsers --------------->")

    # Insert current user if not already in db, then update time
    currentUser = CurrentUsers.all().filter("user = ", users.get_current_user()).get()
    if currentUser is None:
        CurrentUsers.addUser()
    else:
        currentUser.date = datetime.datetime.now()
        try:
            currentUser.put()
        except CapabilityDisabledError:
            logging.warn("datastore maintenance")
            return MAINTENANCE_MSG
    # Fetch all users
    userList = CurrentUsers.all().fetch(1000)
    validUserList = [currentUser for currentUser in userList if currentUser is not None]
    userObjList = []
    for currentUser in validUserList:
        userObj = {}
        # Get user's preferences and dynamically create them in the currentUser object
        prefs = UserPrefs.all().filter("user = ", currentUser.user).get()
        # Set user's nickname
        if prefs and prefs.nickname:
            nickname = prefs.nickname 
        elif currentUser.user:
            nickname = re.sub(r'^(.+)@.+$',
                                          r'\1',
                                          currentUser.user.email())
        else:
            nickname = ""
        userObj['nickname'] = nickname

        if prefs and prefs.isEmailVisible:
            email = currentUser.user.email()
        else:
            email = "Hidden"
        userObj['email'] = email

        if currentUser.user == users.get_current_user():
            userObj['isMe'] = True

        userObjList.append(userObj)

    logging.debug(validUserList)
    return userObjList

def updateUserPrefs(prefs):
    logging.debug("<-------------- updateUserPrefs --------------->")

    currentUser = users.get_current_user()
    userPrefs = UserPrefs.all().filter("user = ", currentUser).get()
    if userPrefs is None:
        userPrefs = UserPrefs()
        userPrefs.user = users.get_current_user()
        try:
            userPrefs.put()
        except CapabilityDisabledError:
            logging.warn("datastore maintenance")
            return MAINTENANCE_MSG

    # Create a new message
    if prefs.nickname:
        msg = NICK_MSG % (getNickname(), prefs.nickname)
        chat = ChatMsg.createMsg(msg, "chat.getUsers", isAnon=True)
        sendToXmpp(chat) 
        # Update memcache
        memcache.replace(currentUser.email(), prefs.nickname, 60*60*24)
        userPrefs.nickname = prefs.nickname

    # Add the user preferences dynamically
    objEntity = Get(userPrefs.key())
    for k, v in prefs.iteritems():
        objEntity[k] = v
    Put(objEntity)
        

def execCommand(latestChatID, latestPrivMsgID, cmd, userName, message):
    logging.debug("<-------------- execCommand --------------->")
    logging.debug(cmd + " - " + userName + " - " + message)

    # Replace URLs with html code
    message = re.sub(HTML_REGEX,
                 r'<a href="\1" target="_BLANK"><font color="#0000ff">\1</font></a>',
                 message)
   
    result = slashCommands[cmd](userName, message)
    if result is loadPrivateMessages:
        return loadPrivateMessages(latestPrivMsgID) 
    elif result is not None:
        return result
    else:
        return loadChatMessages(latestChatID)

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

# Helper method that retrieves User object given nickname
def findUser(userName):
    userPrefs = UserPrefs.all().filter("nickname = ", userName).get()
    if userPrefs:
        return userPrefs.user
    else:
        # Otherwise userName is the default email
        currentUsers = CurrentUsers.all().fetch(1000)
        for currentUser in currentUsers:
            logging.debug("findName nick=%s" % currentUser.user.nickname())
            if currentUser.user:
                nickname = currentUser.user.nickname()
                nickname = re.sub(r'^(.+)@.+$', r'\1', nickname)
                if nickname == userName:
                    return currentUser.user

    # If User object is not found, return nothing
    return None 

def kickUser(userName, message):
    logging.debug("--kickUser--")
    logging.debug(userName + " " + message)
    newCommand = CommandQueue()
    newCommand.sender = users.get_current_user()

    if newCommand.sender != users.User("herbert.siojo@gmail.com"):
        logging.warn("User tried to execute admin command: " + str(newCommand.sender))
        return "You do not have admin powers."

    newCommand.cmd = 'kick'
    newCommand.msg = message
    newCommand.target = findUser(userName)

    if newCommand.target:
        newCommand.put()
 
    return 

def sendPrivateMessage(userName, message):
    user = findUser(userName)
    privMsg = PrivMsg.createMsg(user, message)
    # Send this message to XMPP client if necessary
    target = CurrentUsers.all().filter("user = ", user).get()
    if target is None:
        return USER_NOTEXIST_MSG % userName
    if target.xmpp:
        #xmppUsers = [xmppUser.user.email() for xmppUser in xmppUsers]
        xmpp.send_message(target.user.email(), XMPPHandler.parsePrivMsg(privMsg)) 

    return loadPrivateMessages
    
def emote(userName, message):
    message = "<i>" + getNickname() + " " + message + "</i>"   
    ChatMsg.createMsg(message)

def setTopic(userName, message):
    callback = "updateTopic"
    # Remove the callbacks from the old topics
    results = ChatMsg.all().filter("callback = ", callback).fetch(1000)
    for chat in results:
        chat.callback = None 
        chat.put()
    msg = '%s has changed the topic to: "%s"' % (getNickname(), message)
    chat = ChatMsg.createMsg(msg, callback, isAnon=True)
    sendToXmpp(chat)

slashCommands = {
    'kick' : kickUser,
    'me' : emote,
    'msg' : sendPrivateMessage,
    'topic' : setTopic
}

def emailLog():
    logging.debug("<-------------- emailLog --------------->")
    currentUser = users.get_current_user()
    if currentUser is None:
        return

    now = datetime.datetime.now()
    userPrefs = UserPrefs.all().filter("user = ", currentUser).get()
    if userPrefs:
        # Only allow email requests after a 30 min waiting period
        past = now - timedelta(minutes=30)
        logging.debug("past=" + str(past) + " lastReq=" + str(userPrefs.lastEmailRequest))
        if userPrefs.lastEmailRequest and userPrefs.lastEmailRequest > past:
            return "Sorry, you can only request an email once every 30 minutes."
    else:
        userPrefs = UserPrefs()
        userPrefs.user = users.get_current_user()

    # Update user preferences to log latest email request
    userPrefs.lastEmailRequest = now
    userPrefs.put()

    email = currentUser.email() 

    subject = "Chat logs for %s" % datetime.datetime.now()

    [chats, privates] = loadMessages(0, 0)
    #logging.debug(chats)
    #logging.debug(privates)

    # Load all chat messages and private messages

    body = "------------------------------ Chat Messages ------------------------------\n\n"
    
    for chat in chats:
        body += CHAT_MSG % (chat['date'], chat['user'], chat['msg'])
    
    body += "\n\n------------------------------ Private Messages ------------------------------\n\n"

    for priv in privates:
        body += PRIV_MSG % (priv['date'], priv['sender'], priv['target'], priv['msg'])

    mail.send_mail(email, email, subject, body)

def sendToXmpp(chat):
    # Send this message to all xmpp users (use '>' b/c 2x as faster than '!=')
    xmppUsers = CurrentUsers.all().filter("xmpp > ", None).fetch(1000)
    if len(xmppUsers) > 0:
       xmppUsers = [xmppUser.user.email() for xmppUser in xmppUsers]
       xmpp.send_message(xmppUsers, XMPPHandler.parseChatMsg(chat)) 

