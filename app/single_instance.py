"""每个用户只运行一个 ImageFlow，重复启动通过本机连接唤起窗口。"""
from __future__ import annotations

import hashlib
import time
import sys
from pathlib import Path

from app.qt.QtCore import QObject, QLockFile, QStandardPaths, Signal
from app.qt.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activation_requested = Signal()

    def __init__(self, directory: Path | None = None):
        super().__init__()
        directory = directory or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        directory.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(str(directory.resolve()).casefold().encode("utf-8")).hexdigest()[:24]
        self.name = "ImageFlow-" + key
        self.lock = QLockFile(str(directory / "instance.lock"))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._activate)
        self._primary = False

    def start_or_activate(self) -> bool:
        """返回 True 才创建主窗口；锁也保护同时启动和残留 socket 清理。"""
        deadline = time.monotonic() + 5
        while True:
            if self.lock.tryLock(0):
                QLocalServer.removeServer(self.name)
                if not self.server.listen(self.name):
                    self.lock.unlock()
                    raise RuntimeError("无法启动本机窗口唤醒服务：" + self.server.errorString())
                self._primary = True
                return True
            socket = QLocalSocket()
            if sys.platform == "win32":
                # 由刚被用户启动的进程授权后台窗口前置，避免 Windows 只闪烁任务栏。
                import ctypes
                info = self.lock.getLockInfo()
                pid = info[1] if len(info) == 4 else info[0]
                if isinstance(pid, int) and pid > 0:
                    ctypes.windll.user32.AllowSetForegroundWindow(pid)
            socket.connectToServer(self.name)
            if socket.waitForConnected(200):
                socket.disconnectFromServer()
                return False
            if time.monotonic() >= deadline:
                raise RuntimeError("ImageFlow 已在运行，但暂时无法唤起。请稍后重试，或从托盘图标打开。")
            time.sleep(0.05)

    def _activate(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.close()
            socket.deleteLater()
            self.activation_requested.emit()

    def close(self) -> None:
        if self._primary:
            self.server.close()
            self.lock.unlock()
            self._primary = False
