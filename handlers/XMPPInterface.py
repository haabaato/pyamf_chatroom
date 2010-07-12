import re
import datetime
from datetime import timedelta

from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.api import xmpp
from google.appengine.ext.webapp import xmpp_handlers

### Model classes
from models.chatroom import * 

# Import constants and helper methods
from constants import *
from utils import *

WELCOME_MSG = """Welcome to Haabaato's chatroom! Type /help for more commands.
Here's the most recent messages...

"""
HELP_MSG = """To start chatting, type anything and press enter.  To send private messages to someone in the chatroom, type /msg "nickname" "your message" without the quotes.  To see the list of user nicknames, type /users.

/help - This help message.
/logout - Logs out of this chatroom
/me <message> - Sends message in the third person. 
    Ex: If your nick is haabaato, and your message is "is so cool", then the resulting text will be: "haabaato is so cool"
/msg <nickname> <message> - Sends a private message to the person specified by nickname
/nick <nickname> - Change your nickname by typing /nick newname
/topic <message> - Change the topic of the chatroom to your custom message
/users - The list of users currently logged in to this chatroom
"""
UNHANDLED_MSG = """Sorry, I didn't understand "%s". Type /help for a list of commands."""
XMPP_CHAT_MSG = "(%s) [%s]: %s\n"
XMPP_PRIV_MSG = "*PRIVATE* (%s) [%s]: %s\n"
XMPP_LOGOUT_MSG = "You logged out of the chatroom.  To log back in, type anything and press enter."
LOGOUT_MSG = "%s logged out at %s from Google Talk. Later hater!"
NICKNAME_TAKEN_MSG = "The nickname '%s' is already taken."
USER_NOTEXIST_MSG = """The user '%s' is not logged in.  Type /users to see the list of logged in users."""
USERS_MSG = "%d currently logged in users: "
USER_LIMIT = 5
USER_LIMIT_MSG = "Sorry, the maximum number of Google Talk users are logged in. Please try again later."

#class XMPPHandler(webapp.RequestHandler):
class XMPPHandler(xmpp_handlers.CommandHandler):
    def post(self):
        logging.debug("<-------------- XMPPHandler --------------->")
        message = xmpp.Message(self.request.POST)
        logging.debug("text_message sender: %s, to: %s, body: %s" % (message.sender, message.to, message.body))
        currentUser = CurrentUsers.all().filter("xmpp = ", db.IM("xmpp", message.sender)).get()

        if currentUser is None:
            logging.debug("adding new user in xmpp handler")

            # Prevent too many users from logging in
            xmppUsers = CurrentUsers.all().filter("xmpp != ", None).fetch(USER_LIMIT)
            if len(xmppUsers) == USER_LIMIT:
                message.reply(USER_LIMIT_MSG)
                return
            # Add to list of current users

            email = re.sub(r'(.*)\/.*', r'\1', message.sender)
            # See if this user already exists. If does exist, write to the xmpp property only
            currentUser = CurrentUsers.all().filter("user = ", users.User(email)).get()
            if currentUser is None:
                currentUser = CurrentUsers()
                currentUser.user = users.User(email)

            try:
                currentUser.xmpp = db.IM("xmpp", message.sender)
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
            for chat in recentChats:
                reply += XMPPHandler.parseChatMsg(chat)
            message.reply(reply)
        else:
            logging.debug("already added")
            currentUser.date = datetime.datetime.now()
            try:
                currentUser.put()
            except CapabilityDisabledError:
                logging.warn("datastore maintenance")
                message.reply(MAINTENANCE_MSG)
                return 

        # Call super's method last so commands are executed afer the current user has been created
        super(XMPPHandler, self).post()


    def text_message(self, message=None):
        currentUser = CurrentUsers.all().filter("xmpp = ", db.IM("xmpp", message.sender)).get()

        # Replace URLs with html code
        msg = re.sub(HTML_REGEX,
                     r'<a href="\1" target="_BLANK"><font color="#0000ff">\1</font></a>',
                     message.body)
        ChatMsg.createXmppMsg(message.sender, msg)


    def unhandled_command(self, message=None):
        # Show unnknown cmd text
        message.reply(UNHANDLED_MSG % message.command)

    def me_command(self, message=None):
        currentUser = CurrentUsers.all().filter("xmpp = ", db.IM("xmpp", message.sender)).get()
        cmd, msg = message.body.split(' ', 1)
        msg = "<i>" + getNickname(currentUser.user) + " " + msg + "</i>"   
        ChatMsg.createXmppMsg(message.sender, msg)

        pass


    def help_command(self, message=None):
        # Show help text
        message.reply(HELP_MSG)

    def nick_command(self, message=None):
        # Change user's nickname 
        logging.debug("nick_command")
        email = re.sub(r'(.*)\/.*', r'\1', message.sender)
        sender = users.User(email)
        #currentUser = CurrentUsers.all().filter("xmpp = ", db.IM("xmpp", message.sender)).get()
        currentUser = CurrentUsers.all().filter("user = ", sender).get()
        # Replace restricted chars
        spaceIdx = message.body.find(' ')
        nickname = re.sub(':', '', message.body[spaceIdx + 1:])
        # Check if name is taken
        userPrefs = UserPrefs.all().filter("nickname = ", nickname).fetch(1000)
        logging.debug(userPrefs)
        if len(userPrefs) > 0:
            message.reply(NICKNAME_TAKEN_MSG % nickname) 
            return

        msg = NICK_MSG % (getNickname(currentUser.user), nickname)
        ChatMsg.createMsg(msg, "chat.getUsers", isAnon=True)

        userPrefs = UserPrefs.all().filter("user = ", currentUser).get()
        if userPrefs is None:
            userPrefs = UserPrefs()
            userPrefs.user = users.User(sender)
        userPrefs.nickname = nickname

        try:
            userPrefs.put()
        except CapabilityDisabledError:
            logging.warn("datastore maintenance")
            return MAINTENANCE_MSG

        message.reply(msg)

    def logout_command(self, message=None):
        logging.debug("logout_command")
        currentUser = CurrentUsers.all().filter("xmpp = ", db.IM("xmpp", message.sender)).get()
        localtime = datetime.datetime.now() + timedelta(hours=UTC_OFFSET)
        msg = LOGOUT_MSG % (getNickname(currentUser.user), localtime.strftime("%H:%M, %a %b, %d, %Y"))
        # Create logout message
        ChatMsg.createMsg(msg, "chat.getUsers", isAnon=True)
        message.reply(XMPP_LOGOUT_MSG)
        currentUser.delete()

    def msg_command(self, message=None):
        logging.debug("msg_command")
        cmd, userName, msg = message.body.split(' ', 2)
        #spaceIdx = message.body.find(' ')
        #secondSpaceIdx = message.body[spaceIdx + 1].find(' ')
        #userName = message.body[spaceIdx + 1 : secondSpaceIdx]
        user = findUser(userName)
        logging.debug("userName = %s, message= %s" % (userName, msg))
        if user is None:
            message.reply(USER_NOTEXIST_MSG % userName)
            return
        #msg = message.body[secondSpaceIdx + 1:]
        PrivMsg.createXmppMsg(message.sender, user, msg)


    def topic_command(self, message=None):
        pass

    def users_command(self, message=None):
        currentUsers = CurrentUsers.all().fetch(1000)
        numUsers = len(currentUsers)
        reply = USERS_MSG % numUsers
        for i in range(0, numUsers):
            currentUser = currentUsers[i]
            if i == numUsers - 1:
                reply += "%s" % getNickname(currentUser.user)
            else:    
                reply += "%s, " % getNickname(currentUser.user)
        message.reply(reply)
        

    # Input: chat - A ChatMsg object
    @staticmethod
    def parseChatMsg(chat):
        #date = re.sub(r'(.*)\.\d+', r'\1', str(chat.date))
        date = chat.date.strftime("%H:%M")
        user = getNickname(chat.user)
        # Remove HTML tags from the message
        msg = re.sub(r'<.*?>', r'', chat.msg)
        # Emphasize messages to user
#        idx = msg.find(':')
#        if idx != -1:
#            userName = msg[0:idx - 1]
#            user = findUser(userName)
#            if :
#                msg.replace(userName, "*%s*" % userName, 1)
        return XMPP_CHAT_MSG % (date, user, msg)

    # Input: chat - A PrivMsg object
    @staticmethod
    def parsePrivMsg(chat):
        date = chat.date.strftime("%H:%M")
        sender = getNickname(chat.sender)
        #target = getNickname(chat.target)
        # Remove HTML tags from the message
        msg = re.sub(r'<.*?>', r'', chat.msg)
        return XMPP_PRIV_MSG % (date, sender, msg)
