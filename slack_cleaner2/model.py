# -*- coding: utf-8 -*-
"""
 model module for abstracting channels, messages, and files
"""
from typing import Any, Callable, cast, Dict, Generic, Iterator, Iterable, List, Optional, Sequence, TypeVar, Union
import time
from os import path
from enum import Enum
from logging import Logger
from time import sleep
import requests
from requests import Response
from requests.sessions import Session
from slacker import Slacker, Error

from .logger import SlackLogger


JSONDict = Dict[str, Any]
TimeIsh = Union[None, int, str, float]


class SlackUser:
    """
  internal model of a slack user
  """

    id: str
    """
  user id
  """

    name: str
    """
  user name
  """

    real_name: str
    """
  user real name
  """

    display_name: str
    """
  user display name
  """

    email: str
    """
  user email address
  """

    is_bot = False
    """
  is it a bot user
  """

    is_app_user = False
    """
  is it an app user
  """

    bot = False
    """
  is it a bot or app user
  """

    json: JSONDict
    """
  the underlying slack response as json
  """

    def __init__(self, entry: JSONDict, slack: "SlackCleaner"):
        """
    :param entry: json dict entry as returned by slack api
    :type entry: dict
    :param slack: slack cleaner instance
    :type slack: SlackCleaner
    """
        self.id = entry["id"]
        self._slack = slack
        self.name = entry["name"]
        self.real_name = entry["profile"].get("real_name")
        self.display_name = entry["profile"]["display_name"]
        self.email = entry["profile"].get("email")
        self.json = entry
        self.is_bot = entry["is_bot"]
        self.is_app_user = entry["is_app_user"]
        self.bot = self.is_bot or self.is_app_user

    def __str__(self):
        return "{s.name} ({s.id}) {s.real_name}".format(s=self)

    def __repr__(self):
        return self.__str__()

    def files(self, after: TimeIsh = None, before: TimeIsh = None, types: Optional[str] = None) -> Iterator["SlackFile"]:
        """
    list all files of this user

    :param after: limit to entries after the given timestamp
    :type after: int,str,time
    :param before: limit to entries before the given timestamp
    :type before: int,str,time
    :param types: see slack api, one or multiple of all,spaces,snippets,images,gdocs,zips,pdfs
    :type types: str
    :return: generator of SlackFile objects
    :rtype: SlackFile
    """
        return SlackFile.list(self._slack, user=self.id, after=after, before=before, types=types)

    def msgs(self, after: TimeIsh = None, before: TimeIsh = None, with_replies=False) -> Iterator["SlackMessage"]:
        """
    list all messages of this user

    :param after: limit to entries after the given timestamp
    :type after: int,str,time
    :param before: limit to entries before the given timestamp
    :type before: int,str,time
    :type with_replies: boolean
    :return: generator of SlackMessage objects
    :return: generator of SlackMessage objects
    :rtype: SlackMessage
    """
        for msg in self._slack.msgs((c for c in self._slack.conversations if self in c.members), after=after, before=before, with_replies=with_replies):
            if msg.user == self:
                yield msg


class SlackChannelType(Enum):
    """
    enum class for defining the channel type
    """

    PUBLIC = 1
    PRIVATE = 2
    MPIM = 3
    IM = 4


class SlackChannel:
    """
  internal model of a slack channel, group, mpim, im
  """

    id: str
    """
  channel id
  """

    name: str
    """
  channel name
  """

    members: List[SlackUser] = []
    """
  list of members
  """

    api: Any
    """
  Slacker sub api
  """

    json: JSONDict
    """
  the underlying slack response as json
  """

    type: SlackChannelType
    """
  the channel type
  """

    def __init__(self, entry: JSONDict, members: List[SlackUser], channel_type: SlackChannelType, api: Any, slack: "SlackCleaner"):
        """
    :param entry: json dict entry as returned by slack api
    :type entry: dict
    :param members: list of members
    :type members: [SlackUser]
    :param channel_type: the channel type
    :type channel_type: SlackChannelType
    :param api: Slacker sub api
    :param slack: slack cleaner instance
    :type slack: SlackCleaner
    """

        self.id = entry["id"]
        self.name = entry.get("name", self.id)
        self.members = members
        self.type = channel_type
        self.api = api
        self._slack = slack
        self.json = entry

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()

    def _scope(self):
        if self.type == SlackChannelType.PRIVATE:
            return "groups:history"
        if self.type == SlackChannelType.MPIM:
            return "mpim:history"
        if self.type == SlackChannelType.IM:
            return "im:history"
        return "channels:history"

    def msgs(self, after: TimeIsh = None, before: TimeIsh = None, asc=False, with_replies=False) -> Iterator["SlackMessage"]:
        """
        retrieve all messages as a generator

        :param after: limit to entries after the given timestamp
        :type after: int,str,time
        :param before: limit to entries before the given timestamp
        :type before: int,str,time
        :param asc: returning a batch of messages in ascending order
        :type asc: boolean
        :param with_replies: also iterate over all replies / threads
        :type with_replies: boolean
        :return: generator of SlackMessage objects
        :rtype: SlackMessage
        """
        after = _parse_time(after)
        before = _parse_time(before)
        self._slack.log.debug("list msgs of %s (after=%s, before=%s)", self, after, before)

        messages = self._slack.safe_paginated_api(lambda kw: self.api.history(self.id, latest=before, oldest=after, **kw), "messages", [self._scope()], "conversations.history")

        for msg in reversed(list(messages)) if asc else messages:
            # Delete user messages
            if msg["type"] == "message":
                user = _find_user(self._slack, msg)
                s_msg = SlackMessage(msg, user, self, self._slack)
                yield s_msg

                if with_replies and s_msg.has_replies:
                    yield from self.replies_to(s_msg, after=after, before=before, asc=asc)

    def replies_to(self, base_msg: "SlackMessage", after: TimeIsh = None, before: TimeIsh = None, asc=False) -> Iterator["SlackMessage"]:
        """
        returns the replies to a given SlackMessage instance

        :param base_msg: message instance to find replies to
        :type base_msg: SlackMessage
        :param after: limit to entries after the given timestamp
        :type after: int,str,time
        :param before: limit to entries before the given timestamp
        :type before: int,str,time
        :param asc: returning a batch of messages in ascending order
        :type asc: boolean
        :return: generator of SlackMessage replies
        :rtype: SlackMessage
        """
        ts = base_msg.json.get("thread_ts", base_msg.json["ts"])
        after = _parse_time(after)
        before = _parse_time(before)
        self._slack.log.debug("list msgs of %s (after=%s, before=%s)", self, after, before)

        messages = self._slack.safe_paginated_api(lambda kw: self.api.replies(self.id, ts, latest=before, oldest=after, **kw), "messages", [self._scope()], "conversations.replies")

        for msg in reversed(list(messages)) if asc else messages:
            # Delete user messages
            if msg["type"] == "message":
                user = _find_user(self._slack, msg)
                s_msg = SlackMessage(msg, user, self, self._slack)
                if base_msg.ts != s_msg.ts:  # don't yield itself
                    yield s_msg

    def files(self, after: TimeIsh = None, before: TimeIsh = None, types: Optional[str] = None) -> Iterator["SlackFile"]:
        """
    list all files of this channel

    :param after: limit to entries after the given timestamp
    :type after: int,str,time
    :param before: limit to entries before the given timestamp
    :type before: int,str,time
    :param types: see slack api, one or multiple of all,spaces,snippets,images,gdocs,zips,pdfs
    :type types: str
    :return: generator of SlackFile objects
    :rtype: SlackFile
    """
        return SlackFile.list(self._slack, channel=self.id, after=after, before=before, types=types)


class SlackDirectMessage(SlackChannel):
    """
  internal model of a slack direct message channel
  """

    user: SlackUser
    """
  user talking to
  """

    def __init__(self, entry: JSONDict, user: SlackUser, api: Any, slack: "SlackCleaner"):
        """
    :param entry: json dict entry as returned by slack api
    :type entry: dict
    :param user: user talking to
    :type user: SlackUser
    :param api: Slacker sub api
    :param slack: slack cleaner instance
    :type slack: SlackCleaner
    """

        super(SlackDirectMessage, self).__init__(entry, [user], SlackChannelType.IM, api, slack)
        self.name = user.name
        self.user = user


class SlackMessage:
    """
  internal model of a slack message
  """

    ts: float
    """
  message timestamp
  """
    thread_ts: Optional[float]
    """
  message timestamp for its thread
  """

    text: str
    """
  message text
  """

    api: Any
    """
  slacker sub api
  """

    user: Optional[SlackUser]
    """
  user sending the messsage
  """

    bot = False
    """
  is the message written by a bot
  """

    pinned_to = False
    """
  is the message pinned
  """

    json: JSONDict
    """
  the underlying slack response as json
  """

    has_replies = False
    """
  whether the message has any replies
  """
    files: List["SlackFile"] = []
    """
  files part of this message
  """
    is_tombstone = False
    """
  whether the is a tombstone message as in 'message was deleted'
  thus cannot be deleted but is thread can
  """

    def __init__(self, entry: JSONDict, user: Optional[SlackUser], channel: SlackChannel, slack: "SlackCleaner"):
        """
    :param entry: json dict entry as returned by slack api
    :type entry: dict
    :param user: user wrote this message
    :type user: SlackUser
    :param channel: channels this message is written in
    :type channel: SlackChannel
    :param slack: slack cleaner instance
    :type slack: SlackCleaner
    """
        self.ts = float(entry["ts"])
        self.text = entry["text"]
        self._channel = channel
        self._slack = slack
        self.api = slack.api.chat
        self.json = entry
        self.user = user
        self.bot = entry.get("subtype") == "bot_message" or "bot_id" in entry
        self.pinned_to = entry.get("pinned_to", False)
        self.has_replies = entry.get("reply_count", 0) > 0
        self.thread_ts = float(entry.get("thread_ts", entry["ts"]))
        self.files = [SlackFile(f, user if user else slack.resolve_user(f["user"]), slack) for f in entry.get("files", []) if f["mode"] != "tombstone"]
        self.is_tombstone = entry.get("subtype", None) == "tombstone"

    def delete(self, as_user=True, files=False, replies=False) -> Optional[Exception]:
        """
    deletes this message

    :param as_user: trigger the delete operation as the user identified by the token (default True)
    :type as_user: bool
    :param files: delete attached files, too
    :type files: bool
    :param replies: delete thread replies, too
    :type replies: bool
    :return: None if successful else error
    :rtype: Exception
    """
        try:
            # No response is a good response
            if not self.is_tombstone:
                self.api.delete(self._channel.id, self.json["ts"], as_user=as_user)
                self._slack.post_delete(self)
            else:
                self._slack.log.debug("Cannot delete tombstone message - but its replies and files")

            if files and self.files:
                for sfile in self.files:
                    error = sfile.delete()
                    if error:
                        return error
            if replies and self.has_replies:
                for reply in self.replies():
                    error = reply.delete(as_user=as_user, files=files)
                    if error:
                        return error
            return None
        except Exception as error:
            self._slack.post_delete(self, error)
            return error

    def replies(self) -> Iterator["SlackMessage"]:
        """
    list all replies of this message

    :return: generator of SlackMessage objects
    :rtype: SlackMessage
    """
        return self._channel.replies_to(self)

    def __str__(self):
        return "{c}:{t} ({u}): {s}".format(c=self._channel.name, t=self.ts, u="bot" if self.bot else self.user, s=self.text[0:20] if len(self.text) > 20 else self.text)

    def __repr__(self):
        return self.__str__()


class SlackFile:
    """
  internal representation of a slack file
  """

    id: str
    """
  file id
  """

    name: str
    """
  file name
  """

    title: str
    """
  file title
  """

    api: Any
    """
  slacker sub api
  """

    user: SlackUser
    """
  user created this file
  """

    pinned_to = False
    """
  is the file pinned
  """

    mimetype: Optional[str]
    """
  the file mime type
  """

    size: int
    """
  the file size
  """

    is_public = False
    """
  is the file public
  """

    json: JSONDict
    """
  the underlying slack response as json
  """

    def __init__(self, entry: JSONDict, user: SlackUser, slack: "SlackCleaner"):
        """
    :param entry: json dict entry as returned by slack api
    :type entry: dict
    :param user: user created this file
    :param slack: slack cleaner instance
    :type slack: SlackCleaner
    """
        self.id = entry["id"]
        self.name = entry["name"]
        self.title = entry["title"]
        self.user = user
        self.pinned_to = entry.get("pinned_to", False)
        self.mimetype = entry.get("mimetype")
        self.size = entry["size"]
        self.is_public = entry["is_public"]

        self.json = entry
        self._slack = slack
        self.api = slack.api.files

    @staticmethod
    def list(
        slack: "SlackCleaner", user: Union[str, SlackUser, None] = None, after: TimeIsh = None, before: TimeIsh = None, types: Optional[str] = None, channel: Union[str, SlackChannel, None] = None
    ) -> Iterator["SlackFile"]:
        """
    list all given files

    :param user: user id to limit search
    :type user: str,SlackUser
    :param after: limit to entries after the given timestamp
    :type after: int,str,time
    :param before: limit to entries before the given timestamp
    :type before: int,str,time
    :param channel: channel to limit search
    :type channel: str,SlackChannel
    :param types: see slack api, one or multiple of all,spaces,snippets,images,gdocs,zips,pdfs
    :type types: str
    :return: generator of SlackFile objects
    :rtype: SlackFile
    """

        after = _parse_time(after)
        before = _parse_time(before)
        if isinstance(user, SlackUser):
            user = user.id
        if isinstance(channel, SlackChannel):
            channel = channel.id

        api = slack.api.files
        slack.log.debug("list all files(user=%s, after=%s, before=%s, types=%s, channel=%s", user, after, before, types, channel)

        files = slack.safe_paginated_api(lambda kw: api.list(user=user, ts_from=after, ts_to=before, types=types, channel=channel, **kw), "files", ["files:read"], "files.list")

        for sfile in files:
            yield SlackFile(sfile, slack.resolve_user(sfile["user"]), slack)

    def __str__(self) -> str:
        return self.name

    def __repr__(self):
        return self.__str__()

    def delete(self) -> Optional[Exception]:
        """
    delete the file itself

    :return:  None if successful else exception
    :rtype: Exception
    """
        try:
            # No response is a good response so no error
            self.api.delete(self.id)
            self._slack.post_delete(self)
            return None
        except Exception as error:
            self._slack.post_delete(self, error)
            return error

    def download_response(self, **kwargs) -> Response:
        """
    downloads this file using python requests module

    :return: python requests Response object
    :rtype: Response
    """
        headers = {"Authorization": "Bearer " + self._slack.token}
        return requests.get(self.json["url_private_download"], headers=headers, **kwargs)

    def download_json(self) -> JSONDict:
        """
    downloads this file and returns the JSON content

    :return: json content
    :rtype: dict,list
    """
        res = self.download_response()
        return res.json()

    def download_content(self) -> bytes:
        """
    downloads this file and returns the raw content

    :return: the content
    :rtype: bytes[]
    """
        res = self.download_response()
        return res.content

    def download_stream(self, chunk_size=1024) -> Iterator[bytes]:
        """
    downloads this file and returns a content stream

    :return: bytes[] chunk stream
    :rtype: *bytes[]
    """
        res = self.download_response(stream=True)
        return res.iter_content(chunk_size=chunk_size)

    def download_to(self, directory: str = ".") -> str:
        """
    downloads this file to the given directory

    :return: the stored file path
    :rtype: str
    """
        file_name = path.join(directory, self.name)
        return self.download(file_name)

    def download(self, file_name: Optional[str] = None) -> str:
        """
    downloads this file to the given file name

    :return: the stored file name
    :rtype: str
    """
        with open(file_name or self.name, "wb") as out:
            for chunk in self.download_stream():
                out.write(chunk)
        return file_name or self.name


def _parse_time(time_str: TimeIsh) -> Optional[float]:
    if time_str is None:
        return None
    if isinstance(time_str, (int, float)):
        return int(time_str)
    try:
        if len(time_str) == 8:
            return time.mktime(time.strptime(time_str, "%Y%m%d"))
        return time.mktime(time.strptime(time_str, "%Y%m%d%H%M"))
    except ValueError:
        return None


ByKey = TypeVar("ByKey")


class ByKeyLookup(Generic[ByKey]):
    """
    helper lookup class
    """

    def __init__(self, arr: List[ByKey], keys: Callable[[ByKey], List[str]]):
        self._arr = arr
        self._lookup: Dict[str, ByKey] = {}
        self.keys = keys
        for v in arr:
            for k in keys(v):
                self._lookup[k] = v

    def get(self, key: str) -> Optional[ByKey]:
        """
        similar to dict.get method
        """
        return self[key]

    def __contains__(self, key: Union[ByKey, str]):
        return key in self._lookup or key in self._arr

    def append(self, val: ByKey):
        """
        appends the given value to this list
        """
        self._arr.append(val)
        for k in self.keys(val):
            self._lookup[k] = val

    def __getitem__(self, key: Union[str, int]) -> Optional[ByKey]:
        if isinstance(key, int):
            return self._arr[key] if 0 <= key < len(self._arr) else None
        return self._lookup.get(key, None)

    def __getattr__(self, name: str) -> Optional[ByKey]:
        return self[name]

    def __len__(self) -> int:
        return len(self._arr)

    def __iter__(self) -> Iterator[ByKey]:
        yield from self._arr

    def __str__(self) -> str:
        return str(self._arr)

    def __repr__(self):
        return repr(self._arr)


class SlackCleaner:
    """
    base class for cleaning up slack providing access to channels and users
    """

    log: SlackLogger
    """
    SlackLogger instance for easy logging
    """
    api: Slacker
    """
    underlying slacker instance
    """
    users: ByKeyLookup[SlackUser]
    """
    list of known users
    """
    myself: SlackUser
    """
    the calling slack user, i.e the one whose token is used
    """
    channels: List[SlackChannel] = []
    """
    list of channels
    """
    groups: List[SlackChannel] = []
    """
    list of groups aka private channels
    """
    mpim: List[SlackChannel] = []
    """
    list of multi person instant message channels
    """
    ims: List[SlackDirectMessage] = []
    """
    list of instant messages = direct messages
    """
    conversations: List[Union[SlackChannel, SlackDirectMessage]] = []
    """
    list of channel+group+mpim+ims
    """
    c: ByKeyLookup[SlackChannel]
    """
    alias of .conversations with advanced accessors
    """
    sleep_for: float
    """
    sleep for the given seconds after a file/message was deleted
    """
    page_limit: int
    """
    number of elements fetched per page
    """

    def __init__(self, token: str, sleep_for=0, log_to_file=False, slacker: Optional[Slacker] = None, session=None, logger: Optional[Logger] = None, show_progress=True, page_limit=200):
        """
        :param token: the slack token, see README.md for details
        :type token: str
        :param sleep_for: sleep for x (float) seconds between delete calls
        :type sleep_for: float
        :param log_to_file: enable logging to file
        :type log_to_file: bool
        :param slacker: optional slacker instance for better customization
        :type slacker: Slacker
        :param session: optional session instance for better customization
        :type session: Session
        :param logger: optional Logger instance to use for logging
        :type logger: Logger
        :param show_progress: show a progress upon deleting an element on the console
        :type show_progress: bool
        :param page_limit: number of elements to fetch per page
        :type page_limit: int
        """

        self.log = SlackLogger(log_to_file, logger=logger, show_progress=show_progress)
        self.sleep_for = sleep_for
        self.token = token
        self.page_limit = page_limit

        self.log.debug("start")

        if slacker:
            self.api = slacker
        else:
            slack = Slacker(token, session=session if session else Session(), rate_limit_retries=2)
            self.api = slack

        raw_users = self.safe_api(self.api.users.list, "members", [], ["users:read (bot, user)"], "users.list")
        self.users = ByKeyLookup[SlackUser]([SlackUser(m, self) for m in raw_users], lambda v: [v.name, v.id])
        self.log.debug("collected users %s", self.users)

        # determine one self
        my_id = self.safe_api(self.api.auth.test, "user_id", None, [], "auth.test")
        myself = next((u for u in self.users if u.id == my_id), None)
        if not myself:
            self.log.error("cannot determine my own user, using the first one or a dummy one")
            self.myself = self.users[0] or self._add_dummy_user("?????")
        else:
            self.myself = myself

        def _get_channel_users(channel: JSONDict):
            try:
                raw_members = self.safe_paginated_api(lambda kw: self.api.conversations.members(channel["id"], **kw), "members")
                return self._resolve_users(raw_members)
            except Error as error:
                if str(error) == "fetch_members_failed":
                    self.log.warning("failed to fetch members of channel %s due to a 'fetch_members_failed' error", channel.get("name", channel["id"]))
                    return []
                raise error

        raw_channels = self.safe_paginated_api(lambda kw: self.api.conversations.list(types="public_channel", **kw), "channels", ["channels:read"], "conversations.list (public_channel)")
        self.channels = [SlackChannel(m, _get_channel_users(m), SlackChannelType.PUBLIC, self.api.conversations, self) for m in raw_channels if m.get("is_channel") and not m.get("is_private")]
        self.log.debug("collected channels %s", self.channels)

        raw_groups = self.safe_paginated_api(lambda kw: self.api.conversations.list(types="private_channel", **kw), "channels", ["groups:read"], "conversations.list (private_channel)")
        self.groups = [
            SlackChannel(m, _get_channel_users(m), SlackChannelType.PRIVATE, self.api.conversations, self) for m in raw_groups if (m.get("is_channel") or m.get("is_group")) and m.get("is_private")
        ]
        self.log.debug("collected groups %s", self.groups)

        raw_mpim = self.safe_paginated_api(lambda kw: self.api.conversations.list(types="mpim", **kw), "channels", ["mpim:read"], "conversations.list (mpim)")
        self.mpim = [SlackChannel(m, _get_channel_users(m), SlackChannelType.MPIM, self.api.conversations, self) for m in raw_mpim if m.get("is_mpim")]
        self.log.debug("collected mpim %s", self.mpim)

        raw_ims = self.safe_paginated_api(lambda kw: self.api.conversations.list(types="im", **kw), "channels", ["im:read"], "conversations.list (im)")
        self.ims = [SlackDirectMessage(m, self.resolve_user(m["user"]), self.api.conversations, self) for m in raw_ims if m.get("is_im")]
        self.log.debug("collected ims %s", self.ims)

        # al different types with a similar interface
        self.conversations = self.channels + self.groups + self.mpim
        self.conversations.extend(self.ims)

        # pylint: disable=invalid-name
        self.c = ByKeyLookup[Union[SlackChannel, SlackDirectMessage]](self.conversations, lambda v: [v.name, v.id])
        # pylint: enable=invalid-name

    def safe_api(self, fun: Callable, attr: Union[str, Sequence[str]], default_value=None, scopes: Optional[List[str]] = None, method: Optional[str] = None) -> Any:
        """
        wrapper for handling common errors

        :param fun: function to call
        :type user_id: Callable
        :param attr: attribute name in the body to return
        :type attr: str
        :param default_value: default value in case of an error
        :param method: method hint name
        :type method: str
        :param scopes: list of scopes hint
        :type scopes: List[str]
        """
        scopes = scopes or []
        method = method or str(fun)
        try:
            res = fun()
            res = res.body
            if not res["ok"]:
                self.log.warning("%s: unknown occurred %s", method, res)
                return default_value
            if isinstance(attr, (list, tuple)):
                return tuple([res.get(a) for a in attr])
            return res.get(attr, default_value)
        except Error as error:
            if str(error) == "missing_scope" and scopes:
                self.log.warning("%s: missing scope error: %s is missing", method, f"one of '{scopes}'" if len(scopes) != 1 else scopes[0])
            else:
                self.log.error("%s: unknown error occurred: %s", method, error)
            return default_value

    def safe_paginated_api(self, fun: Callable, attr: str, scopes: Optional[List[str]] = None, method: Optional[str] = None) -> Any:
        """
        wrapper for iterating over a paginated result

        :param fun: function to call the key-word arguments given should be forwarded
        :type user_id: Callable
        :param attr: attribute name in the body to return
        :type attr: str
        :param method: method hint name
        :type method: str
        :param scopes: list of scopes hint
        :type scopes: List[str]
        """
        limit = self.page_limit
        next_cursor = None

        def list_page():
            if not next_cursor:
                # initial call
                return fun(dict(limit=limit))
            return fun(dict(cursor=next_cursor, limit=limit))

        while True:
            page, meta = self.safe_api(list_page, [attr, "response_metadata"], [[], dict()], scopes, method)
            for elem in page:
                yield elem
            if not meta or not meta.get("next_cursor"):
                break
            next_cursor = meta["next_cursor"]

    def resolve_user(self, user_id: str) -> SlackUser:
        """
        resolve a given user_id with creating a dummy user if needed

        :param user_id: user id to resolve
        :type user_id: str
        :rtype: SlackUser
        """
        if user_id not in self.users:
            self.log.error("user %s not found - generating dummy one", user_id)
            return self._add_dummy_user(user_id)
        return cast(SlackUser, self.users[user_id])

    def _add_dummy_user(self, user_id: str):
        entry = {"id": user_id, "name": user_id, "profile": {"real_name": user_id, "display_name": user_id, "email": None}, "is_bot": False, "is_app_user": False}
        user = SlackUser(entry, self)
        self.users.append(user)
        return user

    def _resolve_users(self, ids: List[str]) -> List[SlackUser]:
        return [self.resolve_user(user_id) for user_id in ids]

    def post_delete(self, file_or_msg: Union[SlackMessage, SlackFile], error: Optional[Exception] = None):
        """
        log a deleted file or message with optional error
        """
        self.log.deleted(error)

        if error:
            if str(error) == "missing_scope":
                self.log.warning("cannot delete entry: %s: missing '%s' scope", file_or_msg, "chat:write" if isinstance(file_or_msg, SlackMessage) else "files:write")
            else:
                self.log.warning("cannot delete entry: %s: %s", file_or_msg, error)
        else:
            self.log.debug("deleted entry: %s", file_or_msg)

        if self.sleep_for > 0:
            sleep(self.sleep_for)

    def files(
        self, user: Union[str, SlackUser, None] = None, after: TimeIsh = None, before: TimeIsh = None, types: Optional[str] = None, channel: Union[str, SlackChannel, None] = None
    ) -> Iterator[SlackFile]:
        """
    list all known slack files for the given parameter as a generator

    :param user: limit to given user
    :type user: str,SlackUser
    :param after: limit to entries after the given timestamp
    :type after: int,str,time
    :param before: limit to entries before the given timestamp
    :type before: int,str,time
    :param types: see slack api, one or multiple of all,spaces,snippets,images,gdocs,zips,pdfs
    :type types: str
    :param channel: limit to a certain channel
    :type channel: str,SlackChannel
    :return: generator of SlackFile objects
    :rtype: SlackFile
    """
        return SlackFile.list(self, user=user, after=after, before=before, types=types, channel=channel)

    def msgs(self, channels: Optional[Iterable[SlackChannel]] = None, after: TimeIsh = None, before: TimeIsh = None, with_replies=False) -> Iterator[SlackMessage]:
        """
    list all known slack messages for the given parameter as a generator

    :param channels: limit to given channels by default of all conversations
    :type channels: iterable of SlackChannel
    :param after: limit to entries after the given timestamp
    :type after: int,str,time
    :param before: limit to entries before the given timestamp
    :type before: int,str,time
    :type with_replies: boolean
    :return: generator of SlackMessage objects
    :return: generator of SlackMessage objects
    :rtype: SlackMessage
    """
        if not channels:
            channels = self.conversations
        for channel in channels:
            for msg in channel.msgs(after=after, before=before, with_replies=with_replies):
                yield msg


def _find_user(slack: SlackCleaner, msg: Dict[str, Any]) -> Optional[SlackUser]:
    if "user" not in msg:
        return None
    userid = msg["user"]
    return slack.resolve_user(userid)
