#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import datetime
#import json
import os

import logging
my_logger = logging.getLogger('mylogger')

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext.webapp import template

import pyamf
from pyamf.remoting.gateway.google import WebAppGateway

class ChatMsg(db.Model):
    author = db.UserProperty()
    msg = db.StringProperty(multiline=True)
    date = db.DateTimeProperty(auto_now_add=True)

class ChatMsgFlash(object):
    """
    Models information associated with a simple chat message object.
    """
    # we need a default constructor (e.g. a paren-paren constructor)
    def __init__(self, author=None, date=None, msg=None):
        """
        Create an instance of a chat message object.
        """
        self.author = author
        self.date = date
        self.msg = msg

class MainPage(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()

        if user is None:
            self.redirect(users.create_login_url(self.request.uri))

        self.response.headers['Content-Type'] = 'text/html'
        chatMsg = ChatMsg()

        chatMsg.author = user

        chatMsg.msg = chatMsg.author.nickname() + " logged in at " + datetime.datetime.now().ctime()
        chatMsg.put()

        template_values = {
            }

        path = os.path.join(os.path.dirname(__file__), 'chat.html')
        self.response.out.write(template.render(path, template_values))

def echo(data):
    return data

### Chat services

UTC_OFFSET = 9

def loadMessages():
    chats = db.GqlQuery("SELECT * FROM ChatMsg ORDER BY date ASC LIMIT 10")
    
    my_logger.debug("<--GQL here-->")
    result = []
    for chat in chats:
        author = chat.author.nickname() if chat.author else "Unknown"
        hour = chat.date.hour + UTC_OFFSET
        day =  chat.date.day + int(hour / 24)
        msgTime = str(hour) + chat.date.strftime(":%M %m/") + str(day)
        #my_logger.debug("date=" + msgTime + " author=" + author)
        chatMsgFlash = ChatMsgFlash(author, msgTime, chat.msg)
        result.append(chatMsgFlash) 

    return result

def saveMessage(msg):
    chatMsg = ChatMsg()

    if users.get_current_user():
        chatMsg.author = users.get_current_user()
    else:
        chatMsg.author = users.User("Unknown@sshole.com")

    chatMsg.msg = msg
    chatMsg.put()
    #chats = db.GqlQuery("SELECT * FROM ChatMsg ORDER BY date DESC LIMIT 10")
    
    return loadMessages()

class Greeting(db.Model):
    author = db.UserProperty()
    content = db.StringProperty(multiline=True)
    date = db.DateTimeProperty(auto_now_add=True)

class HelloWorld(webapp.RequestHandler):
    def get(self):
        greetings_query = Greeting.all().order('-date')
        greetings = greetings_query.fetch(10)

        if users.get_current_user():
            url = users.create_logout_url(self.request.uri)
            url_linktext = 'Logout'
        else:
            url = users.create_login_url(self.request.uri)
            url_linktext = 'Login'

        template_values = {
            'greetings': greetings,
            'url': url,
            'url_linktext': url_linktext,
            }

        path = os.path.join(os.path.dirname(__file__), 'index.html')
        self.response.out.write(template.render(path, template_values))

class Guestbook(webapp.RequestHandler):
    def post(self):
        greeting = Greeting()

        if users.get_current_user():
            greeting.author = users.get_current_user()

        greeting.content = self.request.get('content')
        greeting.put()
        self.response.out.write("uh")
        self.redirect('/helloworld')



def main():
    debug_enabled = True
    LOG_FILENAME = 'logging_example.out'
    logging.basicConfig(filename=LOG_FILENAME, filemode="w", level=logging.DEBUG)
    #my_logger.setLevel(logging.DEBUG)

    services = {
        'myservice.echo': echo,
        'chat.loadMessages': loadMessages,
        'chat.saveMessage': saveMessage,
    }

    pyamf.DEFAULT_ENCODING = pyamf.AMF3
    gateway = WebAppGateway(services, logger=logging, debug=debug_enabled)

    application_paths = [('/', gateway), ('/chat', MainPage), ('/helloworld', HelloWorld), ('/sign/', Guestbook)]
    application = webapp.WSGIApplication(application_paths, debug=debug_enabled)

    run_wsgi_app(application)


if __name__ == '__main__':
  main()

