# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Roland Uuesoo

import json
import logging
import socket
import struct
import sys
import threading

from shared_utils.log_generator import LogGenerator


class BackendServer:
    def __init__(self, logger, host="127.0.0.1", port=65432):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False

        # Initialize Main App Logger Instance
        # Redirecting logs downstream to the default logging sink loop (127.0.0.1:5140)
        self.logger = logger or logging.getLogger("server")

        # Derive Static Component Sub-Loggers
        self.link_logger = self.logger.getChild("link")
        self.keys_base_logger = self.logger.getChild("keys")

        # Local cache for dynamic child loggers to prevent global lock contention
        self._logger_cache = {}
        self._cache_lock = threading.Lock()

        self.generator = LogGenerator(self.logger)
        self.generator.start()

    def _get_dynamic_logger(self, event_type):
        """Retrieves a logger from the local cache or creates it if it doesn't exist."""
        # Fast path: Optimistically try to fetch from cache
        try:
            return self._logger_cache[event_type]
        except KeyError:
            pass  # Logger hasn't been created yet, proceed to slow path

        # Slow path: Acquire lock to safely create and cache the new logger
        with self._cache_lock:
            # Double-check inside the lock to ensure another thread didn't create it
            try:
                return self._logger_cache[event_type]
            except KeyError:
                # Create, cache, and return the new child logger
                logger = self.keys_base_logger.getChild(str(event_type))
                self._logger_cache[event_type] = logger
                return logger

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            self.link_logger.info("Backend network socket operational on %s:%s", self.host, self.port)
        except Exception as e:
            self.logger.critical("Failed to bind backend service port: %s", e)
            sys.exit(1)

        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
                self.link_logger.info("New connection handshake accepted from edge node: %s", addr)
                threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True).start()
            except Exception:
                break

    def _handle_client(self, sock):
        # Pre-compile the struct format outside the loop
        header_struct = struct.Struct("!I")

        log_recv = self.link_logger.getChild("recv").debug
        log_send = self.link_logger.getChild("send").debug

        with sock:
            while self.running:
                try:
                    # Read length prefix
                    header = sock.recv(4)
                    if not header or len(header) < 4:
                        break

                    # Unpack length
                    data_len = header_struct.unpack(header)[0]

                    # Read payload
                    data = bytearray()
                    while len(data) < data_len:
                        packet = sock.recv(data_len - len(data))
                        if not packet:
                            break
                        data.extend(packet)

                    if len(data) < data_len:
                        break

                    log_recv("%s", data)

                    # Decode only for reading the event details
                    event = json.loads(data.decode())

                    # Route logging
                    event_type = event.get("key", "unknown")
                    event_value = event.get("value", "")

                    # --- INTERCEPT GENERATOR CONFIGURATION KEYS ---
                    gen_enabled = bool(event_value) if event_type == "generator_enabled" else None
                    gen_interval = int(event_value) if event_type == "generator_interval" else None
                    gen_msgs = int(event_value) if event_type == "generator_msgs" else None

                    if gen_enabled is not None or gen_interval is not None or gen_msgs is not None:
                        # self.link_logger.info(f"Reconfiguring LogGenerator thread metrics dynamically: {event}")
                        self.generator.update_configuration(
                            enabled=gen_enabled, interval=gen_interval, batch_size=gen_msgs
                        )

                    key_logger = self._get_dynamic_logger(event_type)
                    key_logger.info("%s", event_value)

                    # Echo event back out over stream frame
                    # OPTIMIZED: Send the exact original bytes and header

                    log_send("%s", data)
                    sock.sendall(header + data)

                except Exception as e:
                    self.link_logger.error("Error handling streaming frames from remote: %s", e)
                    break
