import datetime
#import json
import os
import re

import logging
my_logger = logging.getLogger('mylogger')

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.ext.webapp import template

import pyamf
from pyamf.remoting.gateway.google import WebAppGateway

class ChatMsg(db.Model):
    id = db.IntegerProperty()
    author = db.UserProperty()
    msg = db.StringProperty(multiline=True)
    date = db.DateTimeProperty(auto_now_add=True)

class ChatMsgFlash(object):
    """
    Models information associated with a simple chat message object.
    """
    # we need a default constructor (e.g. a paren-paren constructor)
    def __init__(self, id=None, author=None, date=None, msg=None):
        """
        Create an instance of a chat message object.
        """
        self.id = id
        self.author = author
        self.date = date
        self.msg = msg

class MainPage(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()

        if user is None:
            self.redirect(users.create_login_url(self.request.uri))
        else:
            self.response.headers['Content-Type'] = 'text/html'
            chatMsg = ChatMsg()
            
            chatMsg.author = user
            chatMsg.msg = chatMsg.author.nickname() + " logged in at " + datetime.datetime.now().ctime()

            #def txn():
            #    # Get the ID of the latest message
            #    latestChat = ChatMsg.all().order("-id").get()
            #    chatMsg.id = latestChat.id + 1
            #    chatMsg.put()
            # Update the new chat message's ID field
            #db.run_in_transaction(txn)

            # Get the ID of the latest message
            latestChat = ChatMsg.all().order("-id").get()
            latestID = latestChat.id if latestChat else 0
            chatMsg.id = latestID + 1
            chatMsg.put()

 
            my_logger.debug(chatMsg.id)

            template_values = {
                }

            path = os.path.join(os.path.dirname(__file__), 'chat.html')
            self.response.out.write(template.render(path, template_values))
            my_logger.debug("<--------------- MainPage get -------------->")


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

UTC_OFFSET = 9

def loadMessages(latestMsgID = 0):
    my_logger.debug("<--------------- loadMessages -------------->")
    my_logger.debug(str(latestMsgID))

    HISTORYSIZE = 1000
    if latestMsgID == 0:
        # User has just logged in, so send them all the chats
        recentChats = memcache.get("recentChats")
        # Query db for most recent messages and store in memcache
        if recentChats is None:
            recentChats = ChatMsg.all().order("-date").fetch(HISTORYSIZE)
            if recentChats is None:
                chats = recentChats = []
            recentChats.reverse()
            latestMsgID = recentChats[-1].id
            memcache.add("recentChats", recentChats, 60*60) 
        # Check that recentChats is not empty
        if len(recentChats):
            newChats = ChatMsg.all().order("id").filter("id > ", latestMsgID).fetch(HISTORYSIZE)
            recentChats.extend(newChats)
            chats = recentChats
    else:
        # Only return the most recent chats
        chats = ChatMsg.all().order("id").filter("id > ", latestMsgID).fetch(HISTORYSIZE)

    result = []
    for chat in chats:
        id = chat.id
        my_logger.debug("id=" + str(id))
        author = chat.author.nickname() if chat.author else "Unknown"
        hour = (chat.date.hour + UTC_OFFSET) % 24
        day =  chat.date.day + int(hour / 24)
        msgTime = str(hour) + chat.date.strftime(":%M %m/") + str(day)
        chatMsgFlash = ChatMsgFlash(id, author, msgTime, chat.msg)
        result.append(chatMsgFlash) 

    stats = memcache.get_stats()
    my_logger.debug("Cache hits: " + str(stats['hits']))
    my_logger.debug("Cache misses: " + str(stats['misses']))

    return result

def saveMessage(msg):
    my_logger.debug("<--------------- saveMessages -------------->")

    chatMsg = ChatMsg()
    if users.get_current_user():
        chatMsg.author = users.get_current_user()
    else:
        chatMsg.author = users.User("Unknown@sshole.com")

    chatMsg.msg = re.sub(r'(https?:\/\/[0-9a-z_,.:;&=+*%$#!?@()~\'\/-]+)',
                         r'<a href="\1" target="_BLANK"><font color="#0000ff">\1</font></a>',
                         msg)

    # Get the ID of the latest message (WARNING: Concurrency issues could possibly occur here)
    latestChat = ChatMsg.all().order("-id").get()
    latestID = latestChat.id if latestChat.id else 0
    chatMsg.id = latestID + 1
    chatMsg.put()

    return loadMessages(latestID)

def main():
    debug_enabled = True
    LOG_FILENAME = 'logging_example.out'
    logging.basicConfig(filename=LOG_FILENAME, filemode="w", level=logging.DEBUG)

    services = {
        'myservice.echo': echo,
        'chat.loadMessages': loadMessages,
        'chat.saveMessage': saveMessage,
    }

    pyamf.DEFAULT_ENCODING = pyamf.AMF3
    gateway = WebAppGateway(services, logger=logging, debug=debug_enabled)

    application_paths = [
        ('/', gateway), 
        ('/chat', MainPage),
        ('/login', LoginPage)
        ]
    application = webapp.WSGIApplication(application_paths, debug=debug_enabled)

    run_wsgi_app(application)


if __name__ == '__main__':
  main()

