# -*- coding: utf-8 -*-
"""
 logger util module
"""
from datetime import datetime
import logging
import pprint
import sys
from time import sleep
from typing import Optional, Union

from colorama import Fore, init

from .model import SlackFile, SlackMessage

# init colors for Powershell
init()


class SlackLoggerLayer(object):
  """
   one stack element to group delete operations
  """

  def __init__(self, name: str, parent: Union['SlackLogger', 'SlackLoggerLayer']):
    self.deleted = 0
    self.errors = 0
    self.name = name
    self._parent = parent

  def __str__(self):
    return u'{n}: deleted: {d}, errors: {e}'.format(n=self.name, d=self.deleted, e=self.errors)

  def __call__(self, error):
    if error:
      self.errors += 1
    else:
      self.deleted += 1

  def __enter__(self):
    return self

  def __exit__(self, *args):
    self._parent.pop()
    return self._parent


class SlackLogger(object):
  """
  helper logging class
  """

  def __init__(self, to_file=False, sleep_for: float = 0):
    self.sleep_for = sleep_for
    self._log = logging.getLogger('slack-cleaner')
    for handler in list(self._log.handlers):
      self._log.removeHandler(handler)
    self._pp = pprint.PrettyPrinter(indent=2)
    self._layers = [SlackLoggerLayer('overall', self)]

    if to_file:
      ts = datetime.now().strftime('%Y%m%d-%H%M%S')
      file_log_handler = logging.FileHandler('slack-cleaner.' + ts + '.log')
      file_log_handler.setLevel(logging.DEBUG)
      self._log.addHandler(file_log_handler)

    self._log.setLevel(logging.DEBUG)
    # And always display on console
    out = logging.StreamHandler()
    out.setLevel(logging.INFO)
    self._log.addHandler(out)
    # wrap regular log methods
    self.debug = self._log.debug
    self.info = self._log.info
    self.warning = self._log.warning
    self.error = self._log.error
    self.critical = self._log.critical
    self.log = self._log.log

  def deleted(self, file_or_msg: Union[SlackFile, SlackMessage], error: Optional[Exception] = None):
    """
    log a deleted file or message with optional error
    """
    for layer in self._layers:
      layer(error)

    if error:
      sys.stdout.write(Fore.RED + 'x' + Fore.RESET)
      sys.stdout.flush()
      self.warning(u'cannot delete entry: %s: %s', file_or_msg, error)
    else:
      sys.stdout.write('.')
      sys.stdout.flush()
      self.debug(u'deleted entry: %s', file_or_msg)

    if self.sleep_for > 0:
      sleep(self.sleep_for)

  def group(self, name: str) -> SlackLoggerLayer:
    """
    push another log group
    """
    layer = SlackLoggerLayer(name, self)
    self.info(u'start deleting: %s', name)
    self._layers.append(layer)
    return layer

  def pop(self) -> SlackLoggerLayer:
    """
    pops last log group
    """
    layer = self._layers[-1]
    del self._layers[-1]
    self.info(u'stop deleting: %s', layer)
    return layer

  def __str__(self):
    return str(self._layers[0])

  def summary(self):
    """
    logs ones summary
    """
    self.info('summary %s', self)
