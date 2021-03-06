import logging
import datetime
from datetime import timedelta
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import users
from google.appengine.ext import db

from models.chatroom import * 

class DbPurgeTask(webapp.RequestHandler):
    def get(self):
        now = datetime.datetime.now()
        pastDay = now - timedelta(2)
        q = db.GqlQuery("SELECT * FROM ChatMsg WHERE date < :1", pastDay)
        results = q.fetch(500)
        db.delete(results)
        q = db.GqlQuery("SELECT * FROM PrivMsg WHERE date < :1", pastDay)
        results = q.fetch(500)
        db.delete(results)
        # clear memcache as well
        memcache.flush_all()

        self.response.headers['Content-Type'] = 'text/html'

        self.response.out.write("Deleted all messages before %s" % pastDay)

class DbPurgeAllTask(webapp.RequestHandler):
    def get(self):
        while True:
            results = ChatMsg.all().fetch(100)
            if len(results) == 0:
                break
            db.delete(results)
        while True:
            results = PrivMsg.all().fetch(100)
            if len(results) == 0:
                break
            db.delete(results)

        # clear memcache as well
        memcache.flush_all()

        self.response.headers['Content-Type'] = 'text/html'
        self.response.out.write("Deleted all messages.")

def main():
    debug_enabled = True

    application_paths = [
        ('/tasks/purge', DbPurgeTask),
        ('/tasks/purgeall', DbPurgeAllTask)
    ]
    application = webapp.WSGIApplication(application_paths, debug=debug_enabled)

    run_wsgi_app(application)


if __name__ == '__main__':
  main()

