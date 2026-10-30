"""Qt bindings: Qt6 for 64-bit builds and Qt5 for 32-bit Windows."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

if sys.platform == "win32" and struct.calcsize("P") == 4:
    from PySide2 import QtCore, QtGui, QtWidgets, QtTest

    # Qt5 wheels may retain a build-machine plugin prefix. Resolve locally for
    # both source environments and PyInstaller's _internal/PySide2 directory.
    QtCore.QCoreApplication.addLibraryPath(str(Path(QtCore.__file__).parent / "plugins"))
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    # Qt6 moved these classes from QtWidgets into QtGui.
    QtGui.QAction = QtWidgets.QAction
    QtGui.QShortcut = QtWidgets.QShortcut
    QtGui.QMouseEvent.position = QtGui.QMouseEvent.localPos
    QtGui.QMouseEvent.globalPosition = QtGui.QMouseEvent.screenPos
    if not hasattr(QtGui.QWheelEvent, "position"):
        QtGui.QWheelEvent.position = QtGui.QWheelEvent.posF
    for _class in (QtWidgets.QApplication, QtWidgets.QDialog, QtWidgets.QMenu):
        if not hasattr(_class, "exec"):
            _class.exec = _class.exec_
else:
    from PySide6 import QtCore, QtGui, QtWidgets, QtTest

for _module in (QtCore, QtGui, QtWidgets, QtTest):
    sys.modules[f"{__name__}.{_module.__name__.rsplit('.', 1)[-1]}"] = _module
