import logging
import datetime
from datetime import timedelta
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import users
from google.appengine.ext import db

from models.chatroom import * 

#import constants
from constants import *

class RefreshUsersTask(webapp.RequestHandler):
    def get(self):
        now = datetime.datetime.now()
        past = now - timedelta(minutes=2)
        # Retrieve all users who haven't sent a keepalive in the past 2 minutes
        q = db.GqlQuery("SELECT * FROM CurrentUsers WHERE date < :1", past)
        results = q.fetch(1000)
        # Delete the timedout users
        #db.delete(results)
        for user in results:
            localtime = datetime.datetime.now() + timedelta(hours=UTC_OFFSET)
            msg = users.get_current_user().nickname() + " logged out at " + localtime.strftime("%H:%M, %a %b, %d, %Y") + ' (timed out). Later hater!'
            user.delete()

        self.response.headers['Content-Type'] = 'text/html'

        self.response.out.write("Users who didn't ping since %s were deleted." % past)

def main():
    debug_enabled = True

    application_paths = [('/tasks/refreshUsers', RefreshUsersTask)]
    application = webapp.WSGIApplication(application_paths, debug=debug_enabled)

    run_wsgi_app(application)


if __name__ == '__main__':
  main()

