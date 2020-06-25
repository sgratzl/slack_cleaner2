# -*- coding: utf-8 -*-
"""
 logger util module
"""
from datetime import datetime
import logging
import sys
from typing import Union, Optional

from colorama import Fore, init


# init colors for Powershell
init()


class SlackLoggerLayer:
    """
    one stack element to group delete operations
    """

    def __init__(self, name: str, parent: Union["SlackLogger", "SlackLoggerLayer"]):
        self.deleted = 0
        self.errors = 0
        self.name = name
        self._parent = parent

    def __str__(self):
        return "{n}: deleted: {d}, errors: {e}".format(n=self.name, d=self.deleted, e=self.errors)

    def __call__(self, error=False):
        if error:
            self.errors += 1
        else:
            self.deleted += 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._parent.pop()
        return self._parent


def _create_default_logger(to_file=False):
    log = logging.getLogger("slack-cleaner")
    for handler in list(log.handlers):
        log.removeHandler(handler)
    if to_file:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        file_log_handler = logging.FileHandler("slack-cleaner." + ts + ".log")
        file_log_handler.setLevel(logging.DEBUG)
        log.addHandler(file_log_handler)

    log.setLevel(logging.DEBUG)
    # And always display on console
    out = logging.StreamHandler()
    out.setLevel(logging.INFO)
    log.addHandler(out)
    return log


class SlackLogger:
    """
    helper logging class
    """

    def __init__(self, to_file=False, logger: Optional[logging.Logger] = None, show_progress=True):
        self.show_progress = show_progress
        self._layers = [SlackLoggerLayer("overall", self)]
        self._log = logger if logger else _create_default_logger(to_file)

        # wrap regular log methods
        self.debug = self._log.debug
        self.info = self._log.info
        self.warning = self._log.warning
        self.error = self._log.error
        self.critical = self._log.critical
        self.log = self._log.log

    def deleted(self, error: Optional[Exception] = None):
        """
        log a deleted file or message with optional error
        """
        for layer in self._layers:
            layer(error)

        if not self.show_progress:
            return

        if error:
            sys.stdout.write(Fore.RED + "x" + Fore.RESET)
        else:
            sys.stdout.write(".")
        sys.stdout.flush()

    def group(self, name: str) -> SlackLoggerLayer:
        """
        push another log group
        """
        layer = SlackLoggerLayer(name, self)
        self.info("start deleting: %s", name)
        self._layers.append(layer)
        return layer

    def pop(self) -> SlackLoggerLayer:
        """
        pops last log group
        """
        layer = self._layers[-1]
        del self._layers[-1]
        self.info("stop deleting: %s", layer)
        return layer

    def __str__(self):
        return str(self._layers[0])

    def summary(self):
        """
        logs ones summary
        """
        self.info("summary %s", self)
