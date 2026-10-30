"""Event-loop waits missing from the Qt5 Python QTest bindings."""
from app.qt.QtCore import QEventLoop, QTimer
from app.qt.QtTest import QTest


if not hasattr(QTest, "qWait"):
    def _wait(milliseconds):
        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    QTest.qWait = staticmethod(_wait)
