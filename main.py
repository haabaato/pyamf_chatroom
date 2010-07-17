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

# Import constants and helper methods
from constants import *
from utils import getNickname

### For Japanese support
# -*- coding: utf-8 -*- 


### Model classes
from models.chatroom import * 
### Handlers
from handlers import rpc, chatroom, XMPPInterface

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

                msg = getNickname() + " logged in at " + localtime.strftime("%H:%M on %a, %b %d %Y") + ". Irasshaimase biatch!"
                # Create new login message
                chatMsg = ChatMsg.createMsg(msg, "chat.getUsers", isAnon=True)

                # Log the user's IP address
                prefs = UserPrefs.all().filter("user = ", currentUser).get()
                if prefs is None:
                    prefs = UserPrefs()
                    prefs.user = users.get_current_user()
                prefs.ipAddr = self.request.remote_addr 
                try:
                    prefs.put()
                except CapabilityDisabledError:
                    logging.warn("datastore maintenance")
                return MAINTENANCE_MSG


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

#def main():
def real_main():
    debug_enabled = True
    LOG_FILENAME = 'logging_example.out'
    logging.basicConfig(filename=LOG_FILENAME, filemode="w", level=logging.DEBUG)

    services = {
        'chat.echo': chatroom.echo,
        'chat.loadMessages': chatroom.loadMessages,
        'chat.saveMessage': chatroom.saveMessage,
        'chat.getUsers': chatroom.getUsers,
        'chat.updateUserPrefs': chatroom.updateUserPrefs,
        'chat.execCommand': chatroom.execCommand,
        'chat.loadChatMessages': chatroom.loadChatMessages,
        'chat.loadPrivateMessages': chatroom.loadPrivateMessages,
        'chat.emailLog': chatroom.emailLog,
    }

    pyamf.DEFAULT_ENCODING = pyamf.AMF3
    gateway = WebAppGateway(services, logger=logging, debug=debug_enabled)

    application_paths = [
        ('/', gateway), 
        ('/chat', MainPage),
        ('/login', LoginPage),
        ('/rpc', rpc.RPCHandler),
        ('/_ah/xmpp/message/chat/', XMPPInterface.XMPPHandler)
        ]
    application = webapp.WSGIApplication(application_paths, debug=debug_enabled)

    run_wsgi_app(application)
    #run_wsgi_app(FirePythonWSGI(application))

def profile_main():
    # This is the main function for profiling
    # We've renamed our original main() above to real_main()
    import cProfile, pstats, StringIO
    prof = cProfile.Profile()
    prof = prof.runctx("real_main()", globals(), locals())
    stream = StringIO.StringIO()
    stats = pstats.Stats(prof, stream=stream)
    stats.sort_stats("time")  # Or cumulative
    stats.print_stats(80)  # 80 = how many to print
    # The rest is optional.
    # stats.print_callees()
    # stats.print_callers()
    logging.info("Profile data:\n%s", stream.getvalue())

def main():
    real_main()
    #profile_main()

if __name__ == '__main__':
  main()

