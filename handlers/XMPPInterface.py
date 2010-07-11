import re
import datetime
from datetime import timedelta

from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.ext.webapp import xmpp_handlers

### Model classes
from models.chatroom import * 

# Import constants and helper methods
from constants import *
from utils import getNickname

WELCOME_MSG = """Welcome to Haabaato's chatroom! Type /help for more commands.
Here's the most recent messages...

"""
HELP_MSG = """To start chatting, type anything and press enter.  To send private messages to someone in the chatroom, type /msg "nickname" "your message" without the quotes.  To see the list of users nicknames, type /users.

/help - This help message.
/logout - Logs out of this chatroom
/msg <nickname> <message> - Sends a private message to the person specified by nickname
/nick <nickname> - Change your nickname by typing /nick newname
/topic <message> - Change the topic of the chatroom to your custom message
/users - The list of users currently logged in to this chatroom
"""
UNHANDLED_MSG = """Sorry, I didn't understand "%s". Type /help for a list of commands."""

XMPP_CHAT_MSG = "%s, %s: %s\n"


#class XMPPHandler(webapp.RequestHandler):
class XMPPHandler(xmpp_handlers.CommandHandler):
    def post(self):
        super(XMPPHandler, self).post()

        currentUser = CurrentUsers.all().filter("xmpp = ", db.IM("xmpp", message.sender)).get()

        if currentUser is None:
            logging.debug("adding new user in xmpp handler")
            # Add to list of current users
            currentUser = CurrentUsers()
            currentUser.xmpp = db.IM("xmpp", message.sender)
            email = re.sub(r'(.*)\/.*', r'\1', message.sender)
            currentUser.user = users.User(email)
            try:
                currentUser.put()
            except CapabilityDisabledError:
                logging.warn("datastore maintenance")
                message.reply(MAINTENANCE_MSG)
                return 

            # Create new login message
            localtime = datetime.datetime.now() + timedelta(hours=UTC_OFFSET)
            msg = getNickname(currentUser.user) + " logged in at " + localtime.strftime("%H:%M on %a, %b %d %Y") + " from Google Talk. Irasshaimase biatch!"
            chatMsg = ChatMsg.createXmppMsg(message.sender, msg, "chat.getUsers", isAnon=True)

            # Send recent chats to the XMPP user
            recentChats = ChatMsg.all().order("-date").fetch(20)
            recentChats.reverse()

            reply = WELCOME_MSG + "\n"
            #chats = [to_dict(chat) for chat in recentChats]
            for chat in recentChats:
                reply += XMPPHandler.parseChatMsg(chat)
            message.reply(reply)

    def text_message(self, message=None):
        logging.debug("<-------------- XMPPHandler --------------->")
        message = xmpp.Message(self.request.POST)
        logging.debug("sender: %s, to: %s, body: %s" % (message.sender, message.to, message.body))
        currentUser = CurrentUsers.all().filter("xmpp = ", db.IM("xmpp", message.sender)).get()
#        if currentUser is None:
#            logging.debug("adding new user in xmpp handler")
#            # Add to list of current users
#            currentUser = CurrentUsers()
#            currentUser.xmpp = db.IM("xmpp", message.sender)
#            email = re.sub(r'(.*)\/.*', r'\1', message.sender)
#            currentUser.user = users.User(email)
#            try:
#                currentUser.put()
#            except CapabilityDisabledError:
#                logging.warn("datastore maintenance")
#                message.reply(MAINTENANCE_MSG)
#                return 
#
#            # Create new login message
#            localtime = datetime.datetime.now() + timedelta(hours=UTC_OFFSET)
#            msg = getNickname(currentUser.user) + " logged in at " + localtime.strftime("%H:%M on %a, %b %d %Y") + " from Google Talk. Irasshaimase biatch!"
#            chatMsg = ChatMsg.createXmppMsg(message.sender, msg, "chat.getUsers", isAnon=True)
#
#            # Send recent chats to the XMPP user
#            recentChats = ChatMsg.all().order("-date").fetch(20)
#            recentChats.reverse()
#
#            reply = WELCOME_MSG + "\n"
#            #chats = [to_dict(chat) for chat in recentChats]
#            for chat in recentChats:
#                reply += XMPPHandler.parseChatMsg(chat)
#            message.reply(reply)

        # Replace URLs with html code
        msg = re.sub(HTML_REGEX,
                     r'<a href="\1" target="_BLANK"><font color="#0000ff">\1</font></a>',
                     message.body)
        ChatMsg.createXmppMsg(message.sender, msg)

    def unhandled_command(self, message=None):
        # Show unnknown cmd text
        message.reply(UNHANDLED_MSG % message.command)

    def help_command(self, message=None):
        # Show help text
        message.reply(HELP_MSG)


    @staticmethod
    def parseChatMsg(chat):
        date = re.sub(r'(.*)\.\d+', r'\1', str(chat.date))
        user = getNickname(chat.user)
        msg = re.sub(r'<.*?>', r'', chat.msg)
        return XMPP_MSG % (date, user, msg)


