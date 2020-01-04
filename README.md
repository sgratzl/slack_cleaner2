# slack_cleaner2

[![License: MIT][mit-image]][mit-url] [![Github Actions][github-actions-image]][github-actions-url] [![PyPi][pypi-image]][pypi-url] [![Read the Docs][docs-image]][docs-url]

Bulk delete messages and files on Slack.

## Install

Install from PyPi:

```bash
pip install slack-cleaner2
```

latest version
```bash
pip install -e git+https://github.com/sgratzl/slack_cleaner2.git
```

## Usage

In contrast to the original version (https://github.com/kfei/slack-cleaner) this version is a focusing on pure python package that allows for easy scripting instead of a vast amount of different command line arguments. 

basic usage

```python
from slack_cleaner2 import *

s = SlackCleaner('SECRET TOKEN')
# list of users
s.users
# list of all kind of channels
s.conversations

# delete all messages in -bots channels
for msg in s.msgs(filter(match('.*-bots'), s.conversations)):
  msg.delete()

for msg in s.c.general.msgs():
  msg.delete()
```


## Tokens

You will need to generate a Slack legacy *user* token to use slack-cleaner. You can generate a token [here](https://api.slack.com/custom-integrations/legacy-tokens):

[https://api.slack.com/custom-integrations/legacy-tokens](https://api.slack.com/custom-integrations/legacy-tokens). 

The token should start with **xoxp** and not like bot tokens with **xoxb**.

## Permission Scopes needed

The permissions to grant depend on what you are going to use the script for.
Grant the permissions below depending on your use.

Beyond granting permissions, if you wish to use this script to delete
messages or files posted by others, you will need to be an [Owner or
Admin](https://get.slack.help/hc/en-us/articles/218124397-Change-a-member-s-role)
of the workspace.

#### General channel and user detection
- `channels:read`
- `users:read`
- `users:read.email`
- `im:read`
- `mpim:read`



#### Deleting messages from public channels

- `channels:history`
- `channels:read`
- `chat:write:user`
- `users:read`

#### Deleting messages from private channels

- `groups:history`
- `groups:read`
- `chat:write:user`
- `users:read`

#### Deleting messages from 1:1 IMs

- `im:history`
- `im:read`
- `chat:write:user`
- `users:read`

#### Deleting messages from multi-person IMs

- `mpim:history`
- `mpim:read`
- `chat:write:user`
- `users:read`

#### Deleting files

- `files:read`
- `files:write:user`
- `users:read`


## Configuring app

The cleaner needs you to give Slack's API permission to let it run the
operations it needs. You grant these by registering it as an app in the
workspace you want to use it in.

You can grant these permissions to the app by:

1. going to [Your Apps](https://api.slack.com/apps)
2. select 'Create New App', fill out an App Name (eg 'Slack Cleaner') and
   select the Slack workspace you want to use it in
3. select 'OAuth & Permissions' in the sidebar
4. scroll down to Scopes and select all scopes you need
5. select 'Save changes'
6. select 'Install App to Workspace'
7. review the permissions and press 'Authorize'
8. copy the 'OAuth Access Token' shown, and use this token as the `--token`
   argument to the script


## Credits

**To all the people who can only afford a free plan. :cry:**


## Development

### Release

```bash
python setup.py clean sdist bdist_wheel
twine upload dist/*
```

change version in `slack_cleaner2/_info.py`

[mit-image]: https://img.shields.io/badge/License-MIT-yellow.svg
[mit-url]: https://opensource.org/licenses/MIT
[github-actions-image]: https://github.com/sgratzl/slack_cleaner2/workflows/python/badge.svg
[github-actions-url]: https://github.com/sgratzl/slack_cleaner2/actions
[pypi-image]: https://pypip.in/version/slack_cleaner2/badge.svg
[pypi-url]: https://pypi.python.org/pypi/slack_cleaner2/
[docs-image]: https://readthedocs.org/projects/slack-cleaner2/badge/?version=latest
[docs-url]: https://slack-cleaner2.readthedocs.io/en/latest/?badge=latest
