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

#import json
#import simplejson as json

import sys
# Force sys.path to have our own directory first, so we can import from it.
APP_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, APP_ROOT_DIR)
sys.path.insert(1, os.path.join(APP_ROOT_DIR, 'utils/external'))
sys.path.insert(2, os.path.join(APP_ROOT_DIR, 'utils/external/firepython'))
sys.path.insert(2, os.path.join(APP_ROOT_DIR, 'utils/external/simplejson'))
from firepython.middleware import FirePythonWSGI

### For Japanese support
# -*- coding: utf-8 -*- 
## Constants
UTC_OFFSET = 9 

### Model classes
from models.chatroom import * 

# Objects of this class, based on ChatMsg model, are sent to Flash app
class ChatMsgFlash(object):
    """
    Models information associated with a simple chat message object.
    """
    # we need a default constructor (e.g. a paren-paren constructor)
    def __init__(self, id=None, author=None, date=None, msg=None, callback=None):
        """
        Create an instance of a chat message object.
        """
        self.id = id
        self.author = author
        self.date = date
        self.msg = msg
        self.callback = callback

### Request handlers

class MainPage(webapp.RequestHandler):
    def get(self):
        logging.debug("<--------------- MainPage get -------------->")
        user = users.get_current_user()

        if user is None:
            self.redirect(users.create_login_url(self.request.uri))
        else:
            self.response.headers['Content-Type'] = 'text/html'

            currentUser = users.get_current_user()
            localtime = datetime.datetime.now() + timedelta(hours=UTC_OFFSET)
            #msg = users.get_current_user().nickname() + " logged in at " + localtime.ctime() + ". Irasshaimase biatch!"
            msg = currentUser.nickname() + " logged in at " + localtime.strftime("%H:%M on %a, %b, %d, %Y") + ". Irasshaimase biatch!"
            # Create new login message
            chatMsg = ChatMsg.createChatMsg(msg, "chat.getUsers")
            # Add to list of users
            #newUser = CurrentUsers()
            #newUser.put()
            CurrentUsers.addUser()

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
    logging.debug(str(latestMsgID))

    HISTORYSIZE = 1000
    if latestMsgID == 0:
        # User has just logged in, so send them all the chats
        recentChats = memcache.get("recentChats")
        # Query db for most recent messages and store in memcache
        if recentChats is None:
            recentChats = ChatMsg.all().order("-date").fetch(HISTORYSIZE)
            logging.debug("recentChats" + str(len(recentChats)))
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

    result = []
#    for chat in chats:
#        localtime = datetime.datetime.now() + timedelta(hours=UTC_OFFSET)
#        msgTime = localtime.strftime("%H:%M %m/%d")
#        chatMsgFlash = ChatMsgFlash(chat.id, chat.author.nickname(), msgTime, chat.msg, chat.callback)
#        #result.append(chatMsgFlash) 
        #result.append(json.dumps(to_dict(chat))) 
        
    chats = [to_dict(chat) for chat in chats]

    stats = memcache.get_stats()
    logging.debug("Cache hits: " + str(stats['hits']))
    logging.debug("Cache misses: " + str(stats['misses']))

    return chats

def saveMessage(msg):
    logging.debug("<--------------- saveMessages -------------->")

    # Replace URLs with html code
    msg = re.sub(r'(https?:\/\/[0-9a-z_,.:;&=+*%$#!?@()~\'\/-]+)',
                 r'<a href="\1" target="_BLANK"><font color="#0000ff">\1</font></a>',
                 msg)
    latestChat = ChatMsg.createChatMsg(msg)
    # Subtract 1 so this new message is retrieved as well
    latestID = latestChat.id - 1 if latestChat.id else 0

    return loadMessages(latestID)

def getUsers():
    logging.debug("<-------------- getUsers --------------->")
    userList = CurrentUsers.all().fetch(1000)
    logging.debug(userList)

    return [currentUser.user.nickname() for currentUser in userList]


### RPC methods

class RPCHandler(webapp.RequestHandler):
    """ Allows the functions defined in the RPCMethods class to be RPCed."""
    def __init__(self):
        webapp.RequestHandler.__init__(self)
        self.methods = RPCMethods()

    def get(self):
        logging.debug("RPC get called")
        func = None

        action = self.request.get('action')
        if action:
            if action[0] == '_':
                self.error(403) # access denied
                return
            else:
                func = getattr(self.methods, action, None)

        if not func:
            self.error(404) # file not found
            return

        args = ()
        while True:
            key = 'arg%d' % len(args)
            val = self.request.get(key)
            if val:
                args += (simplejson.loads(val),)
            else:
                break
        result = func(*args)
        self.response.out.write(simplejson.dumps(result))
    
    def post(self):
        logging.debug("RPC post called")
        args = simplejson.loads(self.request.body)
        func, args = args[0], args[1:]

        if func[0] == '_':
            self.error(403) # access denied
            return

        func = getattr(self.methods, func, None)
        if not func:
            self.error(404) # file not found
            return

        result = func(*args)
        self.response.out.write(simplejson.dumps(result))

class RPCMethods:
    """ Defines the methods that can be RPCed.
    NOTE: Do not allow remote callers access to private/protected "_*" methods.
    """
    def sendMsg(self, *args):
        if args[0] == "logout":

            localtime = datetime.datetime.now() + timedelta(hours=UTC_OFFSET)
            msg = users.get_current_user().nickname() + " logged out at " + localtime.strftime("%H:%M, %a %b, %d, %Y") + '. Later hater!'
            # Create logout message
            ChatMsg.createChatMsg(msg, "chat.getUsers")
            # Remove user from list of current users
            CurrentUsers.delUser()

        else:
            return args[0]
        return

    def Add(self, *args):
        # The JSON encoding may have encoded integers as strings.
        # Be sure to convert args to any mandatory type(s).
        ints = [int(arg) for arg in args]
        return sum(ints)
 

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
        ('/rpc', RPCHandler)
        ]
    application = webapp.WSGIApplication(application_paths, debug=debug_enabled)

    #run_wsgi_app(application)
    run_wsgi_app(FirePythonWSGI(application))


if __name__ == '__main__':
  main()

