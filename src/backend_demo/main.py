# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Roland Uuesoo

import logging
import time

from backend_demo.server import BackendServer
from shared_utils.tcp_logger import setup_tcp_logger


def main():
    logger = setup_tcp_logger(host="127.0.0.1", port=5143, log_level="DEBUG", logger_name="server")

    backend = BackendServer(logger)
    backend.start()

    print("Backend server running with hierarchical TCP Logging active.")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\nShutting down backend...")
        logging.shutdown()


if __name__ == "__main__":
    main()
