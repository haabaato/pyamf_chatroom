import logging

from google.appengine.api import memcache
from google.appengine.ext import db
from google.appengine.api import users

from google.appengine.ext.db import Key

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
    user = db.UserProperty()
    msg = db.StringProperty(multiline=True)
    date = db.DateTimeProperty(auto_now_add=True)
    callback = db.StringProperty()

    @classmethod
    def createMsg(self, msg, callback=None):
        chatMsg = ChatMsg()
        
        user = users.get_current_user()
        chatMsg.user = user if user else users.User("Unknown")
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
    loginCount = db.IntegerProperty(default=1)

    @classmethod
    def addUser(self):
        """
        Create a new user and puts into CurrentUsers.
        Returns true if user was added, false if not.
        """
        currentUser = users.get_current_user()
        newUser = CurrentUsers()
        #newUser = CurrentUsers( key=Key(encoded=currentUser.email()) )
        newUser.user = currentUser
        # Check if user is already in list
        user = CurrentUsers.all().filter("user = ", users.get_current_user()).get()
        if user is None:
            newUser.put()
            wasAdded = True
        else:
            logging.debug("User already exists, not adding")
            user.loginCount += 1
            user.put()
            wasAdded = False

        return wasAdded

    @classmethod
    def delUser(self):
        """
        Deletes current user from CurrentUsers.
        Returns true if user was deleted, false if not.
        """
        user = CurrentUsers.all().filter("user = ", users.get_current_user()).get()
        logging.debug("<------delUser = %s----->", user)
        if user:
            if user.loginCount == 1:
                logging.debug("deleting user=%s", user.user.nickname())
                db.delete(user)
                wasDeleted = True
            else:
                logging.debug("decrementing login count for user=%s", user.user.nickname())
                user.loginCount -= 1
                user.put()
                wasDeleted = False

            return wasDeleted

class UserPrefs(db.Model):
    user = db.UserProperty()
    nickname = db.StringProperty()
    isEmailVisible = db.BooleanProperty(default=True)
    loginMsg = db.StringProperty()
    logoutMsg = db.StringProperty()

class CommandQueue(db.Model):
    sender = db.UserProperty()
    target = db.UserProperty()
    cmd = db.StringProperty() 
    msg = db.StringProperty()

class PrivMsg(db.Model):
    id = db.IntegerProperty()
    date = db.DateTimeProperty(auto_now_add=True)
    sender = db.UserProperty()
    target = db.UserProperty()
    msg = db.StringProperty(multiline=True)

    @classmethod
    def createMsg(self, target, msg):
        privMsg = PrivMsg()
        
        user = users.get_current_user()
        privMsg.sender = user if user else users.User("Unknown")
        privMsg.target = target
        privMsg.msg = msg

        # Get the ID of the latest message
        #latestChat = ChatMsg.all().order("-id").get()
        #latestID = latestChat.id if latestChat else 0
        #chatMsg.id = latestID + 1

        privMsg.put()    

        return privMsg

