# -*- coding: utf-8 -*-
"""
 model module for abstracting channels, messages, and files
"""
from typing import Any, Callable, cast, Dict, Generic, Iterator, Iterable, List, Optional, Sequence, TypeVar, Union
from abc import ABC, abstractmethod
import time
from os import path
from enum import Enum
from logging import Logger
from time import sleep
from functools import cached_property
from datetime import datetime
import requests
from requests import Response
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

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
        return f"{self.name} ({self.id}) {self.real_name}"

    def __repr__(self):
        return str(self)

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
        :rtype: SlackMessage
        """
        for msg in self._slack.msgs((c for c in self._slack.conversations if self in c.members), after=after, before=before, with_replies=with_replies):
            if msg.user == self:
                yield msg

    def reactions(self) -> Iterator[Dict]:
        """
        list alls reactions of this user
        """
        return self._slack.safe_paginated_api(lambda kw: self._slack.client.reactions_list(user=self.id, **kw), "items", [], "reactions.list")


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

    json: JSONDict
    """
    the underlying slack response as json
    """

    type: SlackChannelType
    """
    the channel type
    """

    def __init__(self, entry: JSONDict, channel_type: SlackChannelType, slack: "SlackCleaner"):
        """
        :param entry: json dict entry as returned by slack api
        :type entry: dict
        :param channel_type: the channel type
        :type channel_type: SlackChannelType
        :param slack: slack cleaner instance
        :type slack: SlackCleaner
        """

        self.id = entry["id"]
        self.type = channel_type
        self._slack = slack
        self.json = entry

    @property
    def name(self) -> str:
        """
        channel name
        """
        return self.json.get("name", self.id)

    @cached_property
    def members(self) -> List[SlackUser]:
        """
        list of members
        """
        if self.is_archived:
            self._slack.log.debug("cannot fetch members of archived channel %s", self.name)
            return []
        raw_members = self._slack.safe_paginated_api(lambda kw: self._slack.client.conversations_members(channel=self.id, **kw), "members")
        return [self._slack.users.resolve_user(user) for user in raw_members]

    @property
    def is_archived(self) -> bool:
        """
        whether this channel is archived
        """
        return self.json.get("is_archived", False)

    def __str__(self):
        return self.name

    def __repr__(self):
        return str(self)

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
        after_time = _parse_time(after, self._slack.log)
        before_time = _parse_time(before, self._slack.log)
        self._slack.log.debug("list msgs of %s (after=%s, before=%s)", self, after_time, before_time)

        messages = self._slack.safe_paginated_api(
            lambda kw: self._slack.client.conversations_history(channel=self.id, latest=before_time, oldest=after_time, **kw), "messages", [self._scope()], "conversations.history"
        )

        for msg in reversed(list(messages)) if asc else messages:
            # Delete user messages
            if msg["type"] == "message":
                s_msg = SlackMessage(msg, self, self._slack)
                yield s_msg

                if with_replies and s_msg.has_replies:
                    yield from self.replies_to(s_msg, after=after_time, before=before_time, asc=asc)

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
        after_time = _parse_time(after, self._slack.log)
        before_time = _parse_time(before, self._slack.log)
        self._slack.log.debug("list replies of %s (after=%s, before=%s)", base_msg, after_time, before_time)

        messages = self._slack.safe_paginated_api(
            lambda kw: self._slack.client.conversations_replies(channel=self.id, ts=ts, latest=before_time, oldest=after_time, **kw), "messages", [self._scope()], "conversations.replies"
        )

        for msg in reversed(list(messages)) if asc else messages:
            # Delete user messages
            if msg["type"] == "message":
                s_msg = SlackMessage(msg, self, self._slack)
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

    def __init__(self, entry: JSONDict, slack: "SlackCleaner"):
        """
        :param entry: json dict entry as returned by slack api
        :type entry: dict
        :param slack: slack cleaner instance
        :type slack: SlackCleaner
        """

        super().__init__(entry, SlackChannelType.IM, slack)

    @property
    def name(self) -> str:
        """
        IM channel user name
        """
        return self.user.name

    @cached_property
    def user(self) -> SlackUser:
        """
        user talking to
        """
        return self._slack.users.resolve_user(self.json["user"])

    @cached_property
    def members(self) -> List[SlackUser]:
        """
        list of members
        """
        return [self.user]


class SlackMessage:
    """
    internal model of a slack message
    """

    ts: float
    """
    message timestamp
    """
    dt: datetime
    """
    message timestamp as datetime
    """
    thread_ts: Optional[float]
    """
    message timestamp for its thread
    """
    thread_dt: Optional[datetime]
    """
    message timestamp for its thread as datetime
    """

    text: str
    """
    message text
    """

    user_id: Optional[str]
    """
    user id writing the message
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

    channel: SlackChannel
    """
    channel this message is part of
    """

    def __init__(self, entry: JSONDict, channel: SlackChannel, slack: "SlackCleaner"):
        """
        :param entry: json dict entry as returned by slack api
        :type entry: dict
        :param channel: channels this message is written in
        :type channel: SlackChannel
        :param slack: slack cleaner instance
        :type slack: SlackCleaner
        """
        self.ts = float(entry["ts"])
        self.dt = datetime.fromtimestamp(self.ts)
        self.text = entry["text"]
        self.channel = channel
        self._slack = slack
        self.json = entry
        self.user_id = entry["user"] if "user" in entry else None
        self.bot = entry.get("subtype") == "bot_message" or "bot_id" in entry
        self.pinned_to = entry.get("pinned_to", False)
        self.has_replies = entry.get("reply_count", 0) > 0
        self.thread_ts = float(entry.get("thread_ts", entry["ts"]))
        self.thread_dt = datetime.fromtimestamp(self.thread_ts)
        self.files = [SlackFile(f, slack) for f in entry.get("files", []) if f.get("mode", "tombstone") != "tombstone"]
        self.is_tombstone = entry.get("subtype", None) == "tombstone"

    @cached_property
    def user(self) -> Optional[SlackUser]:
        """
        user sending the message
        """
        return self._slack.users.resolve_user(self.user_id) if self.user_id else None

    @property
    def is_thread_parent(self) -> bool:
        """
        flag whether this message is the parent of a thread
        """
        return self.thread_ts is not None

    def _delete_rated(self, as_user=True):
        # Do until being rate limited
        return self._slack.call_rate_limited(lambda: self._slack.client.chat_delete(channel=self.channel.id, ts=self.json["ts"], as_user=as_user))

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
                self._delete_rated(as_user)
                self._slack.post_delete(self)
            else:
                self._slack.log.debug("Cannot delete tombstone message - but its replies and files")

            if files and self.files:
                for slack_file in self.files:
                    error = slack_file.delete()
                    if error:
                        return error
            if replies and self.has_replies:
                for reply in self.replies():
                    error = reply.delete(as_user=as_user, files=files)
                    if error:
                        return error
            return None
        except SlackApiError as error:
            self._slack.post_delete(self, error)
            return error

    def replies(self) -> Iterator["SlackMessage"]:
        """
        list all replies of this message

        :return: generator of SlackMessage objects
        :rtype: SlackMessage
        """
        return self.channel.replies_to(self)

    def reactions(self) -> List["SlackMessageReaction"]:
        """
        list all reactions of this message

        :return: generator of SlackMessageReaction objects
        :rtype: SlackMessageReaction
        """
        self._slack.log.debug("list reactions of %s", self)

        message = self._slack.safe_api(
            lambda: self._slack.client.reactions_get(
                channel=self.channel.id,
                ts=self.ts,
                full=True,
            ),
            "message",
            {},
            ["reactions:read"],
            "reactions.get",
        )

        def parse_reaction(reaction: JSONDict) -> "SlackMessageReaction":
            return SlackMessageReaction(reaction, self, self._slack)

        return [parse_reaction(r) for r in message.get("reactions", [])]

    def __str__(self):
        user_name = "bot" if self.bot else self.user
        text = self.text[0:20] if len(self.text) > 20 else self.text
        return f"{self.channel.name}:{self.dt.isoformat()} ({user_name}): {text}"

    def __repr__(self):
        return str(self)


class ASlackReaction(ABC):
    """
    internal model of a slack message reaction
    """

    name: str
    """
    reaction name
    """

    count: int = 1
    """
    reaction count
    """

    json: JSONDict
    """
    the underlying slack response as json
    """

    _slack: "SlackCleaner"

    def __init__(self, entry: JSONDict, slack: "SlackCleaner"):
        """
        :param entry: json dict entry as returned by slack api
        :type entry: dict
        :param slack: slack cleaner instance
        :type slack: SlackCleaner
        """
        self.name = entry["name"]
        self.count = entry["count"]
        self.json = entry
        self._slack = slack

    @cached_property
    def users(self) -> List[SlackUser]:
        """
        users
        """
        return [self._slack.users.resolve_user(u) for u in self.json.get("users", [])]

    @abstractmethod
    def _context(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def _delete_impl(self):
        raise NotImplementedError()

    def _delete_rated(self):
        return self._slack.call_rate_limited(self._delete_impl)

    def delete(self) -> Optional[Exception]:
        """
        delete the reaction

        :return:  None if successful else exception
        :rtype: Exception
        """
        try:
            # No response is a good response so no error
            self._delete_rated()
            self._slack.post_delete(self)
            return None
        except SlackApiError as error:
            self._slack.post_delete(self, error)
            return error

    def __str__(self):
        return f"{self._context}:{self.name}({self.count})"

    def __repr__(self):
        return str(self)


class SlackMessageReaction(ASlackReaction):
    """
    internal model of a slack message reaction
    """

    msg: SlackMessage
    """
    slack message this reaction is of
    """

    def __init__(self, entry: JSONDict, msg: SlackMessage, slack: "SlackCleaner"):
        """
        :param entry: json dict entry as returned by slack api
        :type entry: dict
        :param msg
        :type msg: SlackMessage
        :param slack: slack cleaner instance
        :type slack: SlackCleaner
        """
        super().__init__(entry, slack)
        self.msg = msg

    def _context(self) -> str:
        return str(self.msg)

    def _delete_impl(self):
        return self._slack.call_rate_limited(lambda: self._slack.client.reactions_remove(self.name, channel=self.msg.channel.id, timestamp=self.msg.ts))


class SlackFile:
    """
    internal representation of a slack file
    """

    id: str
    """
    file id
    """

    hidden_by_limit: bool
    """
    whether file is hidden because of the limit
    """

    name: str
    """
    file name
    """

    title: str
    """
    file title
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

    def __init__(self, entry: JSONDict, slack: "SlackCleaner"):
        """
        :param entry: json dict entry as returned by slack api
        :type entry: dict
        :param slack: slack cleaner instance
        :type slack: SlackCleaner
        """
        self.id = entry["id"]
        self.hidden_by_limit = "hidden_by_limit" in entry
        self.name = entry.get("name", "Unknown")
        self.title = entry.get("title", "Unknown")
        self.pinned_to = entry.get("pinned_to", False)
        self.mimetype = entry.get("mimetype")
        self.size = entry.get("size", -1)
        self.is_public = entry.get("is_public", False)

        self.json = entry
        self._slack = slack

    @cached_property
    def user(self) -> SlackUser:
        """
        user created this file
        """
        return self._slack.users.resolve_user(self.json["user"])

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

        after = _parse_time(after, slack.log, as_int = True)
        before = _parse_time(before, slack.log, as_int = True)

        if isinstance(user, SlackUser):
            user = user.id
        if isinstance(channel, SlackChannel):
            channel = channel.id

        slack.log.debug("list all files(user=%s, after=%s, before=%s, types=%s, channel=%s", user, after, before, types, channel)

        def fetch(kwargs):
            return slack.client.files_list(user=user, ts_from=after, ts_to=before, types=types, channel=channel, show_files_hidden_by_limit=True, **kwargs)

        files = slack.safe_paging_api(fetch, "files", ["files:read"], "files.list")

        for slack_file in files:
            yield SlackFile(slack_file, slack)

    def __str__(self) -> str:
        return self.name

    def __repr__(self):
        return str(self)

    def _delete_rated(self):
        return self._slack.call_rate_limited(lambda: self._slack.client.files_delete(file=self.id))

    def delete(self) -> Optional[Exception]:
        """
        delete the file itself

        :return:  None if successful else exception
        :rtype: Exception
        """
        try:
            # No response is a good response so no error
            self._delete_rated()
            self._slack.post_delete(self)
            return None
        except SlackApiError as error:
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

    def reactions(self) -> List["SlackFileReaction"]:
        """
        list all reactions of this file

        :return: generator of SlackFileReaction objects
        :rtype: SlackFileReaction
        """
        self._slack.log.debug("list reactions of %s", self)

        wrapper = self._slack.safe_api(
            lambda: self._slack.client.reactions_get(
                file=self.id,
                full=True,
            ),
            "file",
            {},
            ["reactions:read"],
            "reactions.get",
        )

        def parse_reaction(reaction: JSONDict) -> "SlackFileReaction":
            return SlackFileReaction(reaction, self, self._slack)

        return [parse_reaction(r) for r in wrapper.get("reactions", [])]


class SlackFileReaction(ASlackReaction):
    """
    internal model of a slack message reaction
    """

    file: SlackFile
    """
    slack file this reaction is of
    """

    def __init__(self, entry: JSONDict, file: SlackFile, slack: "SlackCleaner"):
        """
        :param entry: json dict entry as returned by slack api
        :type entry: dict
        :param file
        :type file: SlackFile
        :param slack: slack cleaner instance
        :type slack: SlackCleaner
        """
        super().__init__(entry, slack)
        self.file = file

    def _context(self) -> str:
        return str(self.file)

    def _delete_impl(self):
        return self._slack.call_rate_limited(lambda: self._slack.client.reactions_remove(name=self.name, file=self.file.id))


def _parse_time(time_str: TimeIsh, log: SlackLogger, as_int: bool = False) -> Optional[str]:
    if time_str is None:
        return None
    if isinstance(time_str, (int, float)):
        return str(time_str)
    try:
        if len(time_str) == 8:
            time_d = time.strptime(time_str, "%Y%m%d")
        else:
            time_d = time.strptime(time_str, "%Y%m%d%H%M")
        sec = time.mktime(time_d)
        if as_int:
            return str(int(sec))
        return str(sec)
    except ValueError:
        log.exception("error parsing date %s", time_str)
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


class SlackChannels:
    """
    slack channels
    """

    def __init__(self, slack: "SlackCleaner"):
        self._slack = slack

    def get(self, key: str) -> Optional[SlackChannel]:
        """
        similar to dict.get method
        """
        return self[key]

    def __contains__(self, key: Union[SlackChannel, SlackDirectMessage, str]):
        return key in self._slack.channels or key in self._slack.groups or key in self._slack.mpim or cast(Union[SlackDirectMessage, str], key) in self._slack.ims

    def __getitem__(self, key: Union[str, int]) -> Optional[SlackChannel]:
        return self._slack.channels[key] or self._slack.groups[key] or self._slack.mpim[key] or self._slack.ims[key]

    def __getattr__(self, name: str) -> Optional[SlackChannel]:
        return self[name]

    def __len__(self) -> int:
        return len(self._slack.channels) + len(self._slack.groups) + len(self._slack.mpim) + len(self._slack.ims)

    def __iter__(self) -> Iterator[SlackChannel]:
        yield from self._slack.channels
        yield from self._slack.groups
        yield from self._slack.mpim
        yield from self._slack.ims

    def __str__(self) -> str:
        return str(list(self))

    def __repr__(self):
        return repr(list(self))


class SlackUsers:
    """
    helper for managing slack users
    """

    def __init__(self, slack: "SlackCleaner"):
        self._slack = slack
        self._dummy_users: List[SlackUser] = []
        self._lookup: Dict[str, SlackUser] = {}
        self._loaded = False
        self._arr: List[SlackUser] = []

    def _load(self) -> List[SlackUser]:
        if self._loaded:
            return self._arr

        self._loaded = True
        raw_users = self._slack.safe_paginated_api(lambda kw: self._slack.client.users_list(**kw), "members", ["users:read (bot, user)"], "users.list")
        self._arr = [SlackUser(m, self._slack) for m in raw_users]
        self._slack.log.debug("collected users %s", self._arr)

        for user in self._arr:
            self._lookup[user.id] = user
            self._lookup[user.name] = user
        return self._arr

    def _load_single(self, user_id: str) -> Optional[SlackUser]:
        res = self._slack.safe_api(lambda: self._slack.client.users_info(user=user_id), "user", None, ["users:read (bot, user)"], "users.info")
        if res is None:
            return None
        user = SlackUser(res, self._slack)
        self._slack.log.debug("collected single user %s", user)
        self._lookup[user.id] = user
        self._lookup[user.name] = user
        return user

    def __contains__(self, key: Union[SlackUser, str]) -> bool:
        if isinstance(key, SlackUser):
            return key._slack == self._slack

        if key in self._lookup:
            return True
        if self._loaded:
            return False
        user = self._load_single(key)
        return user is not None

    def __getitem__(self, key: Union[str, int]) -> Optional[SlackUser]:
        if isinstance(key, int):
            if key < 0 or key < len(self._dummy_users):
                return self._dummy_users[key]
            arr = self._load()
            shifted_key = key - len(self._dummy_users)
            return arr[shifted_key] if 0 <= shifted_key < len(arr) else None

        if key in self._lookup:
            return self._lookup.get(key, None)
        if self._loaded:
            return None
        return self._load_single(key)

    def get(self, key: str) -> Optional[SlackUser]:
        """
        similar to dict.get method
        """
        return self[key]

    def __getattr__(self, name: str) -> Optional[SlackUser]:
        return self[name]

    def __len__(self) -> int:
        return len(self._dummy_users) + len(self._load())

    def __iter__(self) -> Iterator[SlackUser]:
        yield from self._dummy_users
        yield from self._load()

    def __str__(self) -> str:
        return str(self._arr)

    def __repr__(self):
        return repr(self._arr)

    @cached_property
    def myself(self) -> SlackUser:
        """
        the calling slack user, i.e the one whose token is used
        """
        # determine one self
        my_id = self._slack.safe_api(self._slack.client.auth_test, "user_id", None, [], "auth.test")
        myself = self.get(my_id)
        if not myself:
            self._slack.log.error("cannot determine my own user, using the first one or a dummy one")
            return self[0] or self._add_dummy_user(my_id or "?????")
        return myself

    def resolve_user(self, user_id: str) -> SlackUser:
        """
        resolve a given user_id with creating a dummy user if needed

        :param user_id: user id to resolve
        :type user_id: str
        :rtype: SlackUser
        """
        user = self.get(user_id)
        if user is None:
            self._slack.log.error("user %s not found - generating dummy one", user_id)
            return self._add_dummy_user(user_id)
        return user

    def _add_dummy_user(self, user_id: str) -> SlackUser:
        entry = {"id": user_id, "name": user_id, "profile": {"real_name": user_id, "display_name": user_id, "email": None}, "is_bot": False, "is_app_user": False}
        user = SlackUser(entry, self._slack)
        self._dummy_users.append(user)
        self._lookup[user.id] = user
        self._lookup[user.name] = user
        return user


class SlackCleaner:
    """
    base class for cleaning up slack providing access to channels and users
    """

    log: SlackLogger
    """
    SlackLogger instance for easy logging
    """
    client: WebClient
    """
    underlying WebClient instance
    """
    sleep_for: float
    """
    sleep for the given seconds after a file/message was deleted
    """
    page_limit: int
    """
    number of elements fetched per page
    """
    users: SlackUsers
    """
    slack users
    """
    c: SlackChannels
    """
    alias of .conversations with advanced accessors
    """

    def __init__(
        self,
        token: Union[str, WebClient],
        sleep_for=0,
        log_to_file=False,
        client: Optional[WebClient] = None,
        logger: Optional[Logger] = None,
        show_progress=True,
        page_limit=200,
        team_id: Optional[str] = None,
    ):
        """
        :param token: the slack token, see README.md for details
        :type token: str
        :param sleep_for: sleep for x (float) seconds between delete calls
        :type sleep_for: float
        :param log_to_file: enable logging to file
        :type log_to_file: bool
        :param client: optional client instance for better customization
        :type client: WebClient
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
        self.token = token if isinstance(token, str) else "unknown"
        self.page_limit = page_limit

        self.log.debug("start")

        if isinstance(token, WebClient):
            self.client = token
        elif client:
            self.client = client
        else:
            client = WebClient(token=token, team_id=team_id)
            self.client = client

        self.users = SlackUsers(self)
        self.c = SlackChannels(self)  # pylint: disable=invalid-name

    @cached_property
    def channels(self) -> ByKeyLookup[SlackChannel]:
        """
        list of channels
        """
        raw_channels = self.safe_paginated_api(lambda kw: self.client.conversations_list(types="public_channel", **kw), "channels", ["channels:read"], "conversations.list (public_channel)")
        channels = [SlackChannel(m, SlackChannelType.PUBLIC, self) for m in raw_channels if m.get("is_channel") and not m.get("is_private")]
        self.log.debug("collected channels %s", channels)
        return ByKeyLookup(channels, lambda v: [v.name, v.id])

    @cached_property
    def groups(self) -> ByKeyLookup[SlackChannel]:
        """
        list of groups aka private channels
        """
        raw_groups = self.safe_paginated_api(lambda kw: self.client.conversations_list(types="private_channel", **kw), "channels", ["groups:read"], "conversations.list (private_channel)")
        groups = [SlackChannel(m, SlackChannelType.PRIVATE, self) for m in raw_groups if (m.get("is_channel") or m.get("is_group")) and m.get("is_private")]
        self.log.debug("collected groups %s", groups)
        return ByKeyLookup(groups, lambda v: [v.name, v.id])

    @cached_property
    def mpim(self) -> ByKeyLookup[SlackChannel]:
        """
        list of multi person instant message channels
        """
        raw_mpim = self.safe_paginated_api(lambda kw: self.client.conversations_list(types="mpim", **kw), "channels", ["mpim:read"], "conversations.list (mpim)")
        mpim = [SlackChannel(m, SlackChannelType.MPIM, self) for m in raw_mpim if m.get("is_mpim")]
        self.log.debug("collected mpim %s", mpim)
        return ByKeyLookup(mpim, lambda v: [v.name, v.id])

    @cached_property
    def ims(self) -> ByKeyLookup[SlackDirectMessage]:
        """
        list of instant messages = direct messages
        """
        raw_ims = self.safe_paginated_api(lambda kw: self.client.conversations_list(types="im", **kw), "channels", ["im:read"], "conversations.list (im)")
        ims = [SlackDirectMessage(m, self) for m in raw_ims if m.get("is_im")]
        self.log.debug("collected ims %s", ims)
        return ByKeyLookup(ims, lambda v: [v.name, v.id])

    @cached_property
    def conversations(self) -> List[Union[SlackChannel, SlackDirectMessage]]:
        """
        list of channel+group+mpim+ims
        """
        return list(self.c)

    @property
    def myself(self) -> SlackUser:
        """
        the calling slack user, i.e the one whose token is used
        """
        return self.users.myself

    def call_rate_limited(self, fun: Callable) -> Any:
        """
        call slack api with rate handling

        :param fun: function to call
        :type fun: Callable
        """
        # Do until being rate limited
        while True:
            try:
                return fun()
            except SlackApiError as error:
                if error.response["error"] == "ratelimited":
                    # The `Retry-After` header will tell you how long to wait before retrying
                    delay = int(error.response.headers["Retry-After"])
                    self.log.debug("Rate limited. Retrying in %s seconds", delay)
                    sleep(delay)
                    continue
                raise error

    def safe_api(self, fun: Callable, attr: Union[str, Sequence[str]], default_value=None, scopes: Optional[List[str]] = None, method: Optional[str] = None) -> Any:
        """
        wrapper for handling common errors

        :param fun: function to call
        :type fun: Callable
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
            res = self.call_rate_limited(fun)
            if not res["ok"]:
                self.log.warning("%s: unknown occurred %s", method, res)
                return default_value
            if isinstance(attr, (list, tuple)):
                return tuple(res.get(a) for a in attr)
            return res.get(attr, default_value)
        except SlackApiError as error:
            if error.response["error"] == "missing_scope" and scopes:
                self.log.warning("%s: missing scope error: %s is missing", method, f"one of '{scopes}'" if len(scopes) != 1 else scopes[0])
            elif error.response["error"] == "fetch_members_failed":
                self.log.debug("%s: fetch_members_failed: is it an archived channel?", method)
            else:
                self.log.error("%s: unknown error occurred: %s", method, error)
            return default_value

    def safe_paging_api(self, fun: Callable, attr: str, scopes: Optional[List[str]] = None, method: Optional[str] = None) -> Any:
        """
        wrapper for iterating over a paginated page result

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
        next_page = None

        def list_paging_page():
            if not next_page:
                # initial call
                return fun(dict(count=limit))
            return fun(dict(page=next_page, count=limit))

        while True:
            page, meta = self.safe_api(list_paging_page, [attr, "paging"], [[], {}], scopes, method)
            for elem in page:
                yield elem
            if not meta:
                return
            total = meta.get("total", 1)
            current = meta.get("page", 1)
            if current >= total:
                break
            next_page = current + 1

    def safe_paginated_api(self, fun: Callable, attr: str, scopes: Optional[List[str]] = None, method: Optional[str] = None) -> Any:
        """
        wrapper for iterating over a paginated cursor result

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

        def list_cursor_page():
            if not next_cursor:
                # initial call
                return fun(dict(limit=limit))
            return fun(dict(cursor=next_cursor, limit=limit))

        while True:
            page, meta = self.safe_api(list_cursor_page, [attr, "response_metadata"], [[], {}], scopes, method)
            for elem in page:
                yield elem
            if not meta or not meta.get("next_cursor"):
                break
            next_cursor = meta["next_cursor"]

    def post_delete(self, obj: Union[SlackMessage, SlackFile, ASlackReaction], error: Optional[SlackApiError] = None):
        """
        log a deleted file or message with optional error
        """
        self.log.deleted(error)

        ctx = ""
        if isinstance(obj, SlackMessage):
            ctx = "chat:write"
        elif isinstance(obj, SlackFile):
            ctx = "files:write"
        else:
            ctx = "reactions:write"

        if error:
            if error.response["error"] == "missing_scope":
                self.log.warning("cannot delete entry: %s: missing '%s' scope", obj, ctx)
            else:
                self.log.warning("cannot delete entry: %s: %s", obj, error.response["error"])
        else:
            self.log.debug("deleted entry: %s", obj)

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
