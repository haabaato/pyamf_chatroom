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
from google.appengine.api import mail
from google.appengine.api import xmpp
from google.appengine.runtime.apiproxy_errors import CapabilityDisabledError


from django.utils import simplejson

### Model classes
from models.chatroom import * 

# Import constants and helper methods
from constants import *
from utils import getNickname

HTML_REGEX = r'(https?:\/\/[0-9A-Za-z_,.:;&=+*%$#!?@()~\'\/-]+)'
XMPP_MSG = "%s, %s: %s\n"
MAINTENANCE_MSG = "Sorry, Google's database is currently undergoing maintenance."
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

    #stats = memcache.get_stats()
    #logging.debug("Cache hits: " + str(stats['hits']))
    #logging.debug("Cache misses: " + str(stats['misses']))

    return chats

def loadPrivateMessages(latestMsgID = 0):
    logging.debug("<--------------- loadPrivateMessages -------------->")

    chats = []
    user = users.get_current_user()
    if user is None:
        return
    logging.info("latestMsgID = " + str(latestMsgID)  + " for user:" + user.nickname())
    memcachekey = "recentPrivChats" + user.nickname()
    HISTORYSIZE = 1000
    if latestMsgID == 0:
        # User has just logged in, so send them all the chats
        recentPrivChats = memcache.get(memcachekey)
        # Query db for most recent messages and store in memcache
        if recentPrivChats is None:
            allPrivMsgs = PrivMsg.all().order("id").fetch(HISTORYSIZE)
            recentPrivChats = []
            if len(allPrivMsgs) != 0:
                # Remove messages that aren't from or to this user
                for chat in allPrivMsgs:
                    if chat.sender == user or chat.target == user:
                        recentPrivChats.append(chat)

                memcache.add(memcachekey, recentPrivChats, 60*60) 
        # Check that recentPrivChats is not empty
        if len(recentPrivChats):
            latestMsgID = recentPrivChats[-1].id
            allPrivMsgs = PrivMsg.all().order("id").filter("id > ", latestMsgID).fetch(HISTORYSIZE)
        else:
            allPrivMsgs = PrivMsg.all().order("id").fetch(HISTORYSIZE)
        # Remove messages that aren't from or to this user
        for chat in allPrivMsgs:
            if chat.sender == user or chat.target == user:
                recentPrivChats.append(chat)

        chats = recentPrivChats
    else:
        # Only return the most recent chats
        allPrivMsgs = PrivMsg.all().order("id").filter("id > ", latestMsgID).fetch(HISTORYSIZE)
        # Remove messages that aren't from or to this user
        for chat in allPrivMsgs:
            if chat.sender == user or chat.target == user:
                chats.append(chat)

    # Add the db id to each object
    #for chat in chats:
    #    chat.id = chat.key().id()

    # Convert each object into a JSON-serializable object
    chats = [to_dict(chat) for chat in chats]

    #logging.info("# privates: " + str(len(chats)))
    return chats


def saveMessage(msg, latestChatID, latestPrivMsgID):
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

    # Send this message to all XMPP clients
    xmppUsers = CurrentUsers.all().filter("xmpp != ", None).fetch(1000)
    logging.info("xmppUsers = " + str(len(xmppUsers)))
    if len(xmppUsers) > 0:
        xmppUsers = [xmppUser.user.email() for xmppUser in xmppUsers]
        #chat = to_dict(chat)
        xmpp.send_message(xmppUsers, XMPPHandler.parseChatMsg(chat)) #XMPP_MSG % (chat['date'], chat['user'], chat['msg']))

    return loadMessages(latestChatID, latestPrivMsgID)

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
        try:
            userPrefs.put()
        except CapabilityDisabledError:
            logging.warn("datastore maintenance")
            return MAINTENANCE_MSG

    # Create a new message
    if prefs.nickname:
       msg = getNickname() + ' has changed nickname to: "' + prefs.nickname + '"'
       ChatMsg.createMsg(msg, "chat.getUsers", isAnon=True)

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
    if result is not None:
        return result

    return loadMessages(latestChatID, latestPrivMsgID)

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
            if currentUser.user and currentUser.user.nickname() == userName:
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
    PrivMsg.createMsg(findUser(userName), message)
    
def messageOfTheDay(userName, message):
    pass

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
    ChatMsg.createMsg(msg, callback, isAnon=True)

slashCommands = {
    'kick' : kickUser,
    'me' : emote,
    'motd' : messageOfTheDay,
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
        if userPrefs.lastEmailRequest is None:
            userPrefs.lastEmailRequest = now
            userPrefs.put()
        logging.debug(str(past) + " " + str(userPrefs.lastEmailRequest))
        if userPrefs.lastEmailRequest > past:
            return "Sorry, you can only request an email once every 30 minutes."
    else:
        userPrefs = UserPrefs()
        userPrefs.user = users.get_current_user()

    # Update user preferences to log latest email request
    userPrefs.lastEmailRequest = now
    userPrefs.put()

    email = currentUser.email() 

    subject = "Chat logs for %s" % datetime.datetime.now()

    # Load all chat messages and private messages
    [chats, privates] = loadMessages(0, 0)

    body = "------------------------------ Chat Messages ------------------------------\n\n"
    
    for chat in chats:
        body += "%s %s: %s\n" % (chat['date'], chat['user'], chat['msg'])
    
    body += "\n\n------------------------------ Private Messages ------------------------------\n\n"

    for priv in privates:
        body += "%s %s -> %s: %s\n" % (priv['date'], priv['sender'], priv['target'], priv['msg'])

    mail.send_mail(email, email, subject, body)
    logging.debug(body)

class XMPPHandler(webapp.RequestHandler):
    def post(self):
        logging.debug("<-------------- XMPPHandler --------------->")
        message = xmpp.Message(self.request.POST)
        logging.debug("sender: %s, to: %s, body: %s" % (message.sender, message.to, message.body))
        currentUser = CurrentUsers.all().filter("xmpp = ", db.IM("xmpp", message.sender)).get()
        if currentUser is None:
            logging.debug("adding new user in xmpp handler")
            # Add to list of current users
            currentUser = CurrentUsers()
            currentUser.xmpp = db.IM("xmpp", message.sender)
            email = re.sub(r'(.*)\/.*', r'\1', message.sender)
            currentUser.user = users.User(email)
            try:
                currentUser.put()
            except CapabilityDisabledError:
                logging.warn("datastore maintenance")
                message.reply(MAINTENANCE_MSG)
                return 

            # Create new login message
            localtime = datetime.datetime.now() + timedelta(hours=UTC_OFFSET)
            msg = getNickname(currentUser.user) + " logged in at " + localtime.strftime("%H:%M on %a, %b %d %Y") + " from Google Talk. Irasshaimase biatch!"
            chatMsg = ChatMsg.createXmppMsg(message.sender, msg, "chat.getUsers", isAnon=True)

            # Send recent chats to the XMPP user
            recentChats = ChatMsg.all().order("-date").fetch(20)
            recentChats.reverse()

            reply = "\n"
            #chats = [to_dict(chat) for chat in recentChats]
            for chat in recentChats:
                reply += XMPPHandler.parseChatMsg(chat)
            message.reply(reply)

        # Replace URLs with html code
        msg = re.sub(HTML_REGEX,
                     r'<a href="\1" target="_BLANK"><font color="#0000ff">\1</font></a>',
                     message.body)
        ChatMsg.createXmppMsg(message.sender, msg)

    @staticmethod
    def parseChatMsg(chat):
        date = re.sub(r'(.*)\.\d+', r'\1', str(chat.date))
        user = getNickname(chat.user)
        msg = re.sub(r'<.*?>', r'', chat.msg)
        return XMPP_MSG % (date, user, msg)
