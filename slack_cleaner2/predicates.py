# -*- coding: utf-8 -*-
"""
 set of helper predicates to filter messages, channels, and users
 multiple predicates can be combined using & and |
"""
import re
from typing import Optional, Iterable, List, Any, Callable

from .model import SlackUser


PreciateFun = Callable[[Any], bool]


class AndPredicate:
  """
   common and predicate
  """

  def __init__(self, children: Optional[List[PreciateFun]] = None):
    self.children = children or []

  def __call__(self, obj: Any) -> bool:
    if not self.children:
      return True
    return all(f(obj) for f in self.children)

  def __and__(self, other: PreciateFun) -> 'Predicate':
    if isinstance(other, AndPredicate):
      self.children = self.children + other.children
      return self
    self.children.append(other)
    return self

  def __or__(self, other: PreciateFun) -> 'Predicate':
    return OrPredicate([self, other])


def and_(predicates: List[PreciateFun]) -> 'Predicate':
  """
  combines multiple predicates using a logical and

  :param predicates: the predicates to combine
  :type predicates: [Predicate]
  :return: a new predicate
  :rtype: AndPredicate
  """
  return AndPredicate(predicates)


class OrPredicate:
  """
   common or predicate
  """

  def __init__(self, children: Optional[List[PreciateFun]] = None):
    self.children = children or []

  def __call__(self, obj: Any) -> bool:
    if not self.children:
      return False
    return any(f(obj) for f in self.children)

  def __or__(self, other: PreciateFun) -> 'Predicate':
    if isinstance(other, OrPredicate):
      self.children = self.children + other.children
      return self
    self.children.append(other)
    return self

  def __and__(self, other: PreciateFun) -> 'Predicate':
    return AndPredicate([self, other])


class Predicate:
  """
  helper predicate wrapper for having operator support
  """

  def __init__(self, fun: PreciateFun):
    """
    :param fun: function to evaluate
    """
    self.fun = fun

  def __call__(self, obj: Any) -> bool:
    return self.fun(obj)

  def __and__(self, other: PreciateFun) -> 'Predicate':
    return AndPredicate([self.fun, other])

  def __or__(self, other: PreciateFun) -> 'Predicate':
    return OrPredicate([self.fun, other])


def or_(predicates: List[PreciateFun]) -> Predicate:
  """
  combines multiple predicates using a logical or

  :param predicates: the predicates to combine
  :type predicates: [Predicate]
  :return: a new predicate
  :rtype: OrPredicate
  """
  return OrPredicate(predicates)


def is_not_pinned() -> Predicate:
  """
  predicate for filtering messages or files that are not pinned
  """
  return Predicate(lambda msg_or_file: not msg_or_file.pinned_to)


def is_bot() -> Predicate:
  """
  predicate for filtering messages or files created by a bot
  """
  return Predicate(lambda msg_or_user: msg_or_user.bot)


def match(pattern: str, attr: str = 'name') -> Predicate:
  """
  predicate for filtering channels which names match the given regex

  :param pattern: regex pattern to match
  :type pattern: str
  :param attr: attribute to check of the object
  :type attr: str
  :return: Predicate
  :rtype: Predicate
  """
  regex = re.compile('^' + pattern + '$', re.I)

  return Predicate(lambda channel: regex.search(getattr(channel, attr)) is not None)


def is_name(channel_name: str) -> Predicate:
  """
  predicate for filtering channels with the given name

  :param name: string to match
  :type name: str
  :return: Predicate
  :rtype: Predicate
  """
  return Predicate(lambda channel: channel.name == channel_name)


def match_text(pattern: str) -> Predicate:
  """
  predicate for filtering messages which text matches the given regex

  :param pattern: regex to match
  :type pattern: str
  :return: Predicate
  :rtype: Predicate
  """
  return match(pattern, 'text')


def match_user(pattern: str) -> Predicate:
  """
  predicate for filtering users which match the given regex (any of id, name, display_name, email, real_name)

  :param pattern: regex to match
  :type pattern: str
  :return: Predicate
  :rtype: Predicate
  """
  regex = re.compile('^' + pattern + '$', re.I)
  return Predicate(lambda user: any(
    regex.search(u or '') for u in [user.id, user.name, user.display_name, user.email, user.real_name]))


def is_member(user: SlackUser) -> Predicate:
  """
  predicate for filtering channels in which the given user is a member of

  :param user: the user to check
  :type user: SlackUser
  :return: Predicate
  :rtype: Predicate
  """
  return Predicate(lambda channel: user in channel.members)


def by_user(user: SlackUser) -> Predicate:
  """
  predicate for filtering messages or files written by the given user

  :param users: the users to check
  :type user: [SlackUser]
  :return: Predicate
  :rtype: Predicate
  """
  return Predicate(lambda msg_or_file: msg_or_file.user == user)


def by_users(users: Iterable[SlackUser]) -> Predicate:
  """
  predicate for filtering messages or files written by one of the given users

  :param users: the users to check
  :type user: [SlackUser]
  :return: Predicate
  :rtype: Predicate
  """
  users = set(users)
  return Predicate(lambda msg_or_file: msg_or_file.user in users)
