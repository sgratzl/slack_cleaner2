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
  # delete messages, its files, and all its replies (thread)
  msg.delete(replies=True, files=True)

# delete all general messages and also iterate over all replies
for msg in s.c.general.msgs(with_replies=True):
  msg.delete()
```


## Token

The slack cleaner needs you to give Slack's API permission to let it run the
operations it needs. You grant these by registering it as an app in the
workspace you want to use it in.

You can grant these permissions to the app by:

1. going to [Your Apps](https://api.slack.com/apps)
1. select 'Create New App', fill out an App Name (eg 'Slack Cleaner') and
   select the Slack workspace you want to use it in
1. select 'OAuth & Permissions' in the sidebar
1. scroll down to **User Token Scope** and select all scopes you need according to list below
1. select 'Save changes'
1. select 'Install App to Workspace'
1. review the permissions and press 'Authorize'
1. copy the 'OAuth Access Token' shown, and use as the first argument to `SlackCleaner`

The token should start with **xoxp** and not like bot tokens with **xoxb**.

Beyond granting permissions, if you wish to use this library to delete
messages or files posted by others, you will need to be an [Owner or
Admin](https://get.slack.help/hc/en-us/articles/218124397-Change-a-member-s-role) of the workspace.


### User Token Scopes by Use Case

#### General channel and user detection

- `users:read`
- `channels:read`
- `groups:read`
- `im:read`
- `mpim:read`

#### Deleting messages from public channels

- `users:read`
- `channels:read`
- `channels:history`
- `chat:write`

#### Deleting messages from private channels

- `users:read`
- `groups:read`
- `groups:history`
- `chat:write`

#### Deleting messages from 1:1 IMs

**Note**: You can only delete your own messages, not the ones of others. This is due to a restriction in the Slack API and there is nothing one can do about it.

- `im:read`
- `im:history`
- `users:read`
- `chat:write`

#### Deleting messages from multi-person IMs

- `mpim:read`
- `mpim:history`
- `users:read`
- `chat:write`

#### Deleting files

- `files:read`
- `users:read`
- `files:write`

### All User Token scopes

![user token scopes](https://user-images.githubusercontent.com/4129778/81291893-f20b9580-906a-11ea-80a8-f19f3e6878e9.png)

## Docker

There is no direct docker file available, however since it is a python module one can easily create one: 

```
FROM python:3.7-alpine

LABEL maintainer="Samuel Gratzl <sam@sgratzl.com>"

VOLUME "/backup"
WORKDIR /backup

RUN pip --no-cache-dir install slack-cleaner2

CMD ["python", "-"]
```

An Docker image named `slack_cleaner2` with this Dockerfile would be used like

```sh
cat myscript.py | docker run -i slack_cleaner2
```

The `myscript.py` file is a python script using the slack_cleaner2 module.

## Credits

**To all the people who can only afford a free plan. :cry:**


## Development

### Release

```bash
bumpversion patch
git commit -am 'release vX.X.X'
git tag vX.X.X
invoke release
git push 
git push --tags
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
