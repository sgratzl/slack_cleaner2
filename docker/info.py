from slack_cleaner2 import SlackCleaner
token = 'TOKEN'

s = SlackCleaner(token)
print('users', s.users)
print('public channels', s.channels)
print('private channels', s.groups)
print('instant messages', s.ims)
print('multi user direct messages', s.mpim)
