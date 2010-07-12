import logging
import datetime
from datetime import timedelta
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.api import xmpp

from models.chatroom import * 

from constants import *

TIMEOUT_MSG = """%s logged out at %s (timed out). Later hater!"""
XMPP_TIMEOUT_MSG = """You have been logged out for being idle for more than 30 minutes.
To rejoin the chatroom, type anything and press enter.
"""


class RefreshUsersTask(webapp.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/html'

        logging.debug("TASK: refreshUsers")
        now = datetime.datetime.now()

        logging.debug("now %s" % now)
        self.response.out.write("now %s<br />" % now)
        logging.info("now %s" % now)
        localtime = now + timedelta(hours=UTC_OFFSET)
        logging.debug("localtime %s" % localtime)
        self.response.out.write("localtime %s<br />" % localtime)
        logging.info("localtime %s" % localtime)

        past = now - timedelta(minutes=2)
        # Retrieve all users who haven't sent a keepalive in the past 2 minutes
        #q = db.GqlQuery("SELECT * FROM CurrentUsers WHERE date < :1 AND xmpp = NULL", past)
        q = CurrentUsers.all().filter("date < ", past).filter("xmpp = ", None)
        results = q.fetch(1000)
        for currentUser in results:
            # Get user's preferences
            prefs = UserPrefs.all().filter("user = ", currentUser.user).get()
            # Set user's nickname
            if prefs and prefs.nickname:
                nickname = prefs.nickname
            elif currentUser.user:
                nickname = currentUser.user.nickname()
            else:
                nickname = "Unknown"

            logging.info("deleting user " + nickname)

            msg = TIMEOUT_MSG % (nickname, localtime.strftime("%H:%M, %a, %b %d %Y"))
            chatMsg = ChatMsg.createMsg(msg, "chat.getUsers", isAnon=True)

            currentUser.delete()

        xmppUsers = CurrentUsers.all().filter("xmpp != ", None)
        for xmppUser in xmppUsers:
            past = now - timedelta(minutes=30)
            if not xmpp.get_presence(xmppUser.user.email()):
                logging.info("deleting XMPP user " + xmppUser.user.nickname())
                xmppUser.delete()
            elif xmppUser.date < past:
                xmpp.send_message(xmppUser.xmpp, XMPP_TIMEOUT_MSG) 
                xmppUser.delete()
                msg = TIMEOUT_MSG % (nickname, localtime.strftime("%H:%M, %a, %b %d %Y"))
                chatMsg = ChatMsg.createMsg(msg, "chat.getUsers", isAnon=True)

                

        logging.info("Users who didn't ping since %s were deleted." % past)

def main():
    debug_enabled = True

    application_paths = [('/tasks/refreshUsers', RefreshUsersTask)]
    application = webapp.WSGIApplication(application_paths, debug=debug_enabled)

    run_wsgi_app(application)


if __name__ == '__main__':
  main()

