"""Umbra entry point."""

import argparse
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("GLOG_minloglevel", "2")

from PyQt5.QtCore import QLockFile, Qt  # noqa: E402
from PyQt5.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon  # noqa: E402

from umbra import APP_ID, APP_NAME, __version__, paths  # noqa: E402
from umbra.icons import app_icon  # noqa: E402
from umbra.winutil import set_app_user_model_id  # noqa: E402

IPC_NAME = f"{APP_NAME}-{os.environ.get('USERNAME', 'user')}"
log = logging.getLogger(APP_NAME)


def setup_logging(debug: bool) -> None:
    handler = RotatingFileHandler(paths.log_dir() / "umbra.log", maxBytes=1_000_000, backupCount=3,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    handlers = [handler]
    if debug or sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, handlers=handlers)

    def excepthook(exc_type, exc, tb):
        log.critical("Unhandled exception:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))

    sys.excepthook = excepthook


def notify_running_instance() -> bool:
    """Ask an already-running instance to show its settings. True if one answered."""
    sock = QLocalSocket()
    sock.connectToServer(IPC_NAME)
    if not sock.waitForConnected(500):
        return False
    sock.write(b"show-settings")
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(prog=APP_NAME)
    parser.add_argument("--background", action="store_true", help="start silently in the tray")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    args, qt_args = parser.parse_known_args()

    setup_logging(args.debug)
    set_app_user_model_id(APP_ID)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)

    lock = QLockFile(str(paths.data_dir() / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        if not notify_running_instance():
            QMessageBox.information(None, APP_NAME, f"{APP_NAME} is already running (see the system tray).")
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "No system tray is available on this system.")
        return 1

    from umbra.app import Controller  # heavy imports (mediapipe, cv2) after the lock

    log.info("%s %s starting", APP_NAME, __version__)
    controller = Controller(app)

    QLocalServer.removeServer(IPC_NAME)
    server = QLocalServer()
    server.listen(IPC_NAME)

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.readyRead.connect(lambda: conn.readAll() and controller.open_settings())
            conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(on_connection)
    app.aboutToQuit.connect(server.close)

    controller.start(background=args.background)
    code = app.exec_()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
