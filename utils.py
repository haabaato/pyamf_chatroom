from google.appengine.ext import db
from google.appengine.api import users
### Model classes
from models.chatroom import * 

# Helper method that retrieves current user's nickname
# Input: currentUser - User object
def getNickname(currentUser=None):
    if currentUser is None:
        currentUser = users.get_current_user()

    email = currentUser.email()
    nickname = memcache.get(email)
    if nickname:
        return nickname
    # Get user's preferences
    prefs = UserPrefs.all().filter("user = ", currentUser).get()

    # Set user's nickname
    if prefs and prefs.nickname:
        nickname = prefs.nickname
    elif currentUser:
        nickname = currentUser.nickname()
    else:
        nickname = "Unknown"
    # Store the user's nickname in memcache with email as key
    memcache.add(email, nickname, 60*60*24)

    return nickname

# Helper method that retrieves User object given nickname
# Input: userName - string
def findUser(userName):
    userPrefs = UserPrefs.all().filter("nickname = ", userName).get()
    if userPrefs:
        return userPrefs.user
    else:
        # Otherwise userName is the default email
        currentUsers = CurrentUsers.all().fetch(1000)
        for currentUser in currentUsers:
            if currentUser.user and currentUser.user.nickname() == userName:
                return currentUser.user

    # If User object is not found, return nothing
    return None 

