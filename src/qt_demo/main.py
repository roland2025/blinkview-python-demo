# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Roland Uuesoo

import logging
import signal
import sys

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QApplication

from qt_demo.ui.main_window import QtClientApp
from shared_utils.tcp_logger import setup_tcp_logger


def main():
    logger = setup_tcp_logger(port=5144, log_level="DEBUG", logger_name="ui")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = QtClientApp(logger)
    window.show()

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)

    exit_code = app.exec()
    logging.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
