#Example on How You can create a complex Slack bot using this - 

from slack_cleaner2 import *
import time

while True:
    try:
        s = SlackCleaner('your-token-here')

        channelvars = ['channel1','channel2','channel3','channel4']
        channelvar_lazy =  ['channel3','channel4']
        userlevel1=['user1','dexter','user2','user3','user4']     
        
        break
    except Exception as e:
        print("Oops!", e.__class__, "occurred.")
        print("Restarting in 30 seconds...")
        time.sleep(30)


x=0
while True:
    try:
        for channelvar in channelvars:
            for msg in s.c[channelvar].msgs(after="20210530"):
              if not msg.bot:
              
                # It will delete all links that does not have github.com in it. But it will not delete if the user dexter posts it.
                if ((msg.user.name != 'dexter') and ("github.com/" not in str(msg.json["text"])) and (str(msg.json["user"]) != "USLACKBOT")):
                
                    #Different configuration for Different Channel Type
                    if((channelvar in channelvar_lazy) and (x%200 == 0) and ('thread_ts' not in msg.json)):                     
                      msg.delete()
                    if(channelvar not in channelvar_lazy):              
                      msg.delete()
        time.sleep(15)
    except Exception as e:
        print("Oops!", e.__class__, "occurred.")
        print("Restarting in 30 seconds...")
        time.sleep(30)

    x=x+1
