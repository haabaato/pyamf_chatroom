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

from django.utils import simplejson

import pyamf
from pyamf.remoting.gateway.google import WebAppGateway

import sys
# Force sys.path to have our own directory first, so we can import from it.
APP_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, APP_ROOT_DIR)
sys.path.insert(1, os.path.join(APP_ROOT_DIR, 'utils/external'))
sys.path.insert(2, os.path.join(APP_ROOT_DIR, 'utils/external/firepython'))
sys.path.insert(2, os.path.join(APP_ROOT_DIR, 'utils/external/simplejson'))
from firepython.middleware import FirePythonWSGI


#import constants
from constants import *

### For Japanese support
# -*- coding: utf-8 -*- 


### Model classes
from models.chatroom import * 
### Handlers
from handlers import rpc

### Request handlers

class MainPage(webapp.RequestHandler):
    def get(self):
        logging.debug("<--------------- MainPage get -------------->")
        user = users.get_current_user()

        if user is None:
            self.redirect(users.create_login_url(self.request.uri))
        else:
            self.response.headers['Content-Type'] = 'text/html'

            # Add to list of users
            result = CurrentUsers.addUser()
            # If user isn't one of the current users, show login msg
            if result:
                currentUser = users.get_current_user()
                localtime = datetime.datetime.now() + timedelta(hours=UTC_OFFSET)
                msg = currentUser.nickname() + " logged in at " + localtime.strftime("%H:%M on %a, %b, %d, %Y") + ". Irasshaimase biatch!" + localtime.strftime("%c")
                # Create new login message
                chatMsg = ChatMsg.createChatMsg(msg, "chat.getUsers")

            template_values = {
                }

            path = os.path.join(os.path.dirname(__file__), 'chat.html')
            self.response.out.write(template.render(path, template_values))


class LoginPage(webapp.RequestHandler):
    def get(self):
        if users.get_current_user():
            url = users.create_logout_url(self.request.uri)
            url_linktext = 'Logout'
        else:
            url = users.create_login_url(self.request.uri)
            url_linktext = 'Login'
        
        self.response.out.write("<a href=" + url + ">" + url_linktext + "</a>")

### Chat services (PyAMF)

def echo(data):
    return data


def loadMessages(latestMsgID = 0):
    logging.debug("<--------------- loadMessages -------------->")

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

    chats = [to_dict(chat) for chat in chats]

    stats = memcache.get_stats()
    logging.debug("Cache hits: " + str(stats['hits']))
    logging.debug("Cache misses: " + str(stats['misses']))

    return chats

def saveMessage(msg, latestMsgID):
    logging.debug("<--------------- saveMessages -------------->")

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
    #latestChat = ChatMsg.createChatMsg(msg, callback)
    ChatMsg.createChatMsg(msg, callback)
    # Subtract 1 so this new message is retrieved as well
    #latestID = latestChat.id - 1 if latestChat.id else 0

    return loadMessages(latestMsgID)

def getUsers():
    logging.debug("<-------------- getUsers --------------->")

#    timeFrame = datetime.datetime.now() - timedelta(hours=2)
#    # Get all current logged in users
#    userList = CurrentUsers.all().fetch(1000)
#    recentChats = ChatMsg.all().order("-date").filter("date > ", timeFrame).fetch(200)
#    # See if each current user has commented in most recent messages
#    if recentChats:
#        # Delete users who haven't responded typed in over an hour
#        for currentUser in userList:
#            userChats = [chat for chat in recentChats if chat.user == currentUser.user]
#            if len(userChats) == 0:
#                logging.debug("user deleted b/c not in recentchats=%s", currentUser.user.nickname())
#                db.delete(user)
#                userList.remove(user)
#            elif userChats[0].date > timeFrame:
#                continue
#            else:
#                logging.debug("user deleted b/c inactive=%s", currentUser.user.nickname())
#                db.delete(user)
#                userList.remove(user)

    # Insert current user if not already in db, then update time
    #currentUser = CurrentUsers.get_or_insert(Key(encoded=users.get_current_user().email()))
    currentUser = CurrentUsers.all().filter("user = ", users.get_current_user()).get()
    if currentUser is None:
        CurrentUsers.addUser()
    else:
        currentUser.date = datetime.datetime.now()
        currentUser.put()
    # Fetch all users
    userList = CurrentUsers.all().fetch(1000)

    return [currentUser.user.nickname() for currentUser in userList if currentUser is not None]

def main():
    debug_enabled = True
    LOG_FILENAME = 'logging_example.out'
    logging.basicConfig(filename=LOG_FILENAME, filemode="w", level=logging.DEBUG)

    services = {
        'myservice.echo': echo,
        'chat.loadMessages': loadMessages,
        'chat.saveMessage': saveMessage,
        'chat.getUsers': getUsers
    }

    pyamf.DEFAULT_ENCODING = pyamf.AMF3
    gateway = WebAppGateway(services, logger=logging, debug=debug_enabled)

    application_paths = [
        ('/', gateway), 
        ('/chat', MainPage),
        ('/login', LoginPage),
        ('/rpc', rpc.RPCHandler)
        ]
    application = webapp.WSGIApplication(application_paths, debug=debug_enabled)

    #run_wsgi_app(application)
    run_wsgi_app(FirePythonWSGI(application))


if __name__ == '__main__':
  main()

