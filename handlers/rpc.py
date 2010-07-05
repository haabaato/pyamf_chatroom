import logging
import datetime
from datetime import timedelta

from google.appengine.ext import webapp
from google.appengine.api import memcache
from google.appengine.ext import db
from google.appengine.api import users
from django.utils import simplejson

### Model classes
from models.chatroom import * 

from constants import *
from utils import getNickname

### RPC methods

class RPCHandler(webapp.RequestHandler):
    """ Allows the functions defined in the RPCMethods class to be RPCed."""
    def __init__(self):
        webapp.RequestHandler.__init__(self)
        self.methods = RPCMethods()

    def get(self):
        logging.debug("RPC get called")
        func = None

        action = self.request.get('action')
        if action:
            if action[0] == '_':
                self.error(403) # access denied
                return
            else:
                func = getattr(self.methods, action, None)

        if not func:
            self.error(404) # file not found
            return

        args = ()
        while True:
            key = 'arg%d' % len(args)
            val = self.request.get(key)
            if val:
                args += (simplejson.loads(val),)
            else:
                break
        result = func(*args)
        self.response.out.write(simplejson.dumps(result))
    
    def post(self):
        logging.debug("RPC post called")
        args = simplejson.loads(self.request.body)
        func, args = args[0], args[1:]

        if func[0] == '_':
            self.error(403) # access denied
            return

        func = getattr(self.methods, func, None)
        if not func:
            self.error(404) # file not found
            return

        result = func(*args)
        self.response.out.write(simplejson.dumps(result))

class RPCMethods:
    """ Defines the methods that can be RPCed.
    NOTE: Do not allow remote callers access to private/protected "_*" methods.
    """
    def sendMsg(self, *args):
        if args[0] == "logout":
            # Remove user from list of current users
            result = CurrentUsers.delUser()
            # Show logout msg if user was deleted 
            if result:
                localtime = datetime.datetime.now() + timedelta(hours=UTC_OFFSET)
                msg = getNickname() + " logged out at " + localtime.strftime("%H:%M, %a %b, %d, %Y") + '. Later hater!'
                # Create logout message
                ChatMsg.createMsg(msg, "chat.getUsers", isAnon=True)

        else:
            return args[0]
        return

    def Add(self, *args):
        # The JSON encoding may have encoded integers as strings.
        # Be sure to convert args to any mandatory type(s).
        ints = [int(arg) for arg in args]
        return sum(ints)
 
