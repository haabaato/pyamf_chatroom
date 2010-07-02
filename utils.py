from google.appengine.ext import db
from google.appengine.api import users
### Model classes
from models.chatroom import * 

# Helper method that retrieves current user's nickname
def getNickname():
    currentUser = users.get_current_user()

    # Get user's preferences
    prefs = UserPrefs.all().filter("user = ", currentUser).get()
    # Set user's nickname
    if prefs and prefs.nickname:
        nickname = prefs.nickname
    elif currentUser:
        nickname = currentUser.nickname()
    else:
        nickname = "Unknown"

    return nickname

