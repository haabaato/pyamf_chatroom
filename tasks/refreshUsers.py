import logging
import datetime
from datetime import timedelta
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import users
from google.appengine.ext import db

from models.chatroom import * 

from constants import *

class RefreshUsersTask(webapp.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/html'

        logging.debug("TASK: refreshUsers")
        now = datetime.datetime.now()

        logging.debug("now %s" % now)
        self.response.out.write("now %s<br />" % now)
        print("now %s" % now)
        localtime = now + timedelta(hours=UTC_OFFSET)
        logging.debug("localtime %s" % localtime)
        self.response.out.write("localtime %s<br />" % localtime)
        print("localtime %s" % localtime)

        past = now - timedelta(minutes=2)
        # Retrieve all users who haven't sent a keepalive in the past 2 minutes
        q = db.GqlQuery("SELECT * FROM CurrentUsers WHERE date < :1", past)
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

            logging.warning("deleting user " + nickname)

            msg = nickname + " logged out at " + localtime.strftime("%H:%M, %a, %b %d %Y") + ' (timed out). Later hater!'
            chatMsg = ChatMsg.createMsg(msg, "chat.getUsers")
            chatMsg.user = users.User(nickname + "@gmail.com")
            chatMsg.put()

            #self.response.out.write("user %s was deleted.<br />" % currentUser.user.nickname())
            print("user %s was deleted." % currentUser.user.nickname())
            currentUser.delete()

        #self.response.out.write("Users who didn't ping since %s were deleted.<br />" % past)
        print("Users who didn't ping since %s were deleted." % past)

def main():
    debug_enabled = True

    application_paths = [('/tasks/refreshUsers', RefreshUsersTask)]
    application = webapp.WSGIApplication(application_paths, debug=debug_enabled)

    run_wsgi_app(application)


if __name__ == '__main__':
  main()

