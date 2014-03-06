# -*- coding: utf-8 -*-

from PyQt5.QtCore import QObject, pyqtSlot

from collections import deque
import threading, os, sys

from multiprocessing.connection import Listener, Client

import constants

class FrontendAction(object):
    def __init__(self):
        super().__init__()

class CreateTasksAction(FrontendAction):
    tasks = None # tasks to add in the same batch

    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks

    def __repr__(self):
        return "{} [{}]".format(self.__class__.__name__, self.tasks)

class CreateTask(object):
    NORMAL = 0
    LOCAL_TORRENT = 1

    url = None
    kind = None
    def __init__(self, url = None, kind = None):
        self.url = url

        if kind is None:
            kind = self.NORMAL
        self.kind = kind

    def __repr__(self):
        return "{} <{}>".format(self.__class__.__name__, self.url)

class FrontendActionsQueue(QObject):
    _queue = None
    _listener = None
    frontendpy = None

    def __init__(self, parent = None):
        super().__init__(parent)
        self._queue = deque()
        self.frontendpy = parent

        self._listener = threading.Thread(target = self.listenerThread, daemon = True,
                                          name = "frontend communication listener")
        self._listener.start()

        tasks = sys.argv[1:]
        if tasks:
            self.createTasksAction(tasks)

    def listenerThread(self):
        # clean if previous run crashes
        try:
            os.remove(constants.FRONTEND_SOCKET[0])
        except FileNotFoundError:
            pass

        with Listener(*constants.FRONTEND_SOCKET) as listener:
            while True:
                with listener.accept() as conn:
                    payload = conn.recv()
                    self.createTasksAction(payload)

    def queueAction(self, action):
        self._queue.append(action)
        self.frontendpy.consumeAction("action newly queued")

    def dequeueAction(self):
        return self._queue.popleft()

    @pyqtSlot()
    @pyqtSlot(list)
    def createTasksAction(self, taskUrls = None):
        if taskUrls:
            alltasks = list(map(self._createTask, taskUrls))
            tasks = list(filter(lambda task: task.kind == CreateTask.NORMAL, alltasks))
            tasks_localtorrent = list(filter(lambda task: task.kind == CreateTask.LOCAL_TORRENT,
                                             alltasks))
        else:
            # else
            tasks = [self._createTask()]
            tasks_localtorrent = []

        if tasks:
            self.queueAction(CreateTasksAction(tasks))
        for task_bt in tasks_localtorrent: # because only 1 bt-task can be added once.
            self.queueAction(CreateTasksAction([task_bt]))

    def _createTask(self, taskUrl = None):
        from urllib import parse

        if taskUrl is None:
            return CreateTask()

        parsed = parse.urlparse(taskUrl)
        if parsed.scheme in ("thunder", "flashget", "qqdl"):
            import misc
            url = misc.decodePrivateLink(taskUrl)
            return CreateTask(url)

        elif parsed.scheme == "":
            if parsed.path.endswith(".torrent"):
                return CreateTask(taskUrl, kind = CreateTask.LOCAL_TORRENT)

        elif parsed.scheme in ("http", "https", "ftp", "magnet", "ed2k"):
            return CreateTask(taskUrl)

class FrontendCommunicationClient(object):
    def __init__(self, payload):
        with Client(*constants.FRONTEND_SOCKET) as conn:
            conn.send(payload)