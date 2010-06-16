import logging
import datetime
from datetime import timedelta
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import users
from google.appengine.ext import db

class DbPurgeTask(webapp.RequestHandler):
    def get(self):
        now = datetime.datetime.now()
        pastDay = now - timedelta(2)
        q = db.GqlQuery("SELECT * FROM ChatMsg WHERE date < :1", pastDay)
        results = q.fetch(1000)
        db.delete(results)
        self.response.out.write("Deleted all messages before " + pastDay.ctime())

def main():
    debug_enabled = True

    application_paths = [('/tasks/purge', DbPurgeTask)]
    application = webapp.WSGIApplication(application_paths, debug=debug_enabled)

    run_wsgi_app(application)


if __name__ == '__main__':
  main()

