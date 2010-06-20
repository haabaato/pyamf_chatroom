import logging

from google.appengine.api import memcache
from google.appengine.ext import db
from google.appengine.api import users

import datetime
import time

SIMPLE_TYPES = (int, long, float, bool, dict, basestring, list)

def to_dict(model):
    """
    Converts datastore model into a JSON-serializable dictionary.
    """
    output = {}

    for key, prop in model.properties().iteritems():
        value = getattr(model, key)

        if value is None or isinstance(value, SIMPLE_TYPES):
            output[key] = value
        elif isinstance(value, datetime.datetime):
            output[key] = value
        elif isinstance(value, datetime.date):
            # Convert date/datetime to ms-since-epoch ("new Date()").
            ms = time.mktime(value.utctimetuple()) * 1000
            ms += getattr(value, 'microseconds', 0) / 1000
            output[key] = int(ms)
        elif isinstance(value, db.Model):
            output[key] = to_dict(value)
        elif isinstance(value, users.User):
            output[key] = value.nickname()
        else:
            raise ValueError('cannot encode ' + repr(prop))

    return output


class ChatMsg(db.Model):
    id = db.IntegerProperty()
    author = db.UserProperty()
    msg = db.StringProperty(multiline=True)
    date = db.DateTimeProperty(auto_now_add=True)
    callback = db.StringProperty()

    @classmethod
    def createChatMsg(self, msg, callback=None):
        chatMsg = ChatMsg()
        
        user = users.get_current_user()
        chatMsg.author = user if user else users.User("Unknown")
        chatMsg.msg = msg

        # If callback is set, Flash app will issue RPC to service named by callback
        chatMsg.callback = callback

        # Get the ID of the latest message
        latestChat = ChatMsg.all().order("-id").get()
        latestID = latestChat.id if latestChat else 0
        chatMsg.id = latestID + 1
        chatMsg.put()    

        return chatMsg

class CurrentUsers(db.Model):
    """
    Stores the logged in users. 
    """
    user = db.UserProperty()
    date = db.DateTimeProperty(auto_now_add=True)

    @classmethod
    def addUser(self):
        """
        Create a new user and puts into CurrentUsers.
        """
        newUser = CurrentUsers()
        newUser.user = users.get_current_user()
        # Check if user is already in list
        user = CurrentUsers.all().filter("user = ", users.get_current_user()).get()
        if user is None:
            newUser.put()
        else:
            logging.debug("User already exists, not adding")

    @classmethod
    def delUser(self):
        """
        Deletes current user from CurrentUsers.
        """
        user = CurrentUsers.all().filter("user = ", users.get_current_user()).get()
        logging.debug("User deleted")
        logging.debug(user)
        if user:
            db.delete(user)
         

class UserPrefs(db.Model):
    user = db.UserProperty()

