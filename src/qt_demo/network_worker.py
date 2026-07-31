# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Roland Uuesoo

import json
import logging
import struct
import threading

from qtpy.QtCore import QObject, QTimer, Signal, Slot
from qtpy.QtNetwork import QTcpSocket


class NetworkWorker(QObject):
    """Handles all network I/O, auto-reconnect logic, and remote log updates."""

    connected = Signal()
    disconnected = Signal()
    event_received = Signal(dict)

    def __init__(self, host="127.0.0.1", port=65500, link_logger=None, remote_base_logger=None):
        super().__init__()
        self.host = host
        self.port = port
        self.socket = None
        self.header_struct = struct.Struct("!I")

        self.link_logger = link_logger or logging.getLogger("ui.link")
        self.remote_base_logger = remote_base_logger or logging.getLogger("ui.keys.remote")

        self.link_send_logger = self.link_logger.getChild("send")
        self.link_recv_logger = self.link_logger.getChild("recv")

        self._remote_cache = {}
        self._cache_lock = threading.Lock()
        self.reconnect_timer = None
        self.reconnect_interval_ms = 3000

    def _get_remote_logger(self, event_type):
        try:
            return self._remote_cache[event_type]
        except KeyError:
            pass

        with self._cache_lock:
            try:
                return self._remote_cache[event_type]
            except KeyError:
                logger = self.remote_base_logger.getChild(str(event_type))
                self._remote_cache[event_type] = logger
                return logger

    @Slot()
    def start_connection(self):
        self.socket = QTcpSocket(self)
        self.socket.readyRead.connect(self.on_ready_read)
        self.socket.connected.connect(self._on_connected)
        self.socket.disconnected.connect(self._on_disconnected)
        self.socket.errorOccurred.connect(self._on_error)

        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setInterval(self.reconnect_interval_ms)
        self.reconnect_timer.timeout.connect(self._connect_to_host)
        self._connect_to_host()

    def _connect_to_host(self):
        if self.socket.state() == QTcpSocket.UnconnectedState:
            self.link_logger.info("Attempting connection to %s:%s...", self.host, self.port)
            self.socket.connectToHost(self.host, self.port)

    @Slot()
    def _on_connected(self):
        self.reconnect_timer.stop()
        self.connected.emit()

    @Slot()
    def _on_disconnected(self):
        self.disconnected.emit()
        if not self.reconnect_timer.isActive():
            self.reconnect_timer.start()

    @Slot(int)
    def _on_error(self, _):
        if self.socket.state() == QTcpSocket.UnconnectedState:
            if not self.reconnect_timer.isActive():
                self.reconnect_timer.start()

    @Slot(dict)
    def send_json_event(self, payload: dict):
        if self.socket and self.socket.state() == QTcpSocket.ConnectedState:
            try:
                json_dumped = json.dumps(payload)
                json_bytes = json_dumped.encode()
                self.link_send_logger.debug("%s", json_bytes)
                header = self.header_struct.pack(len(json_bytes))
                self.socket.write(header + json_bytes)
            except Exception as e:
                self.link_logger.error("Serialization/Write error: %s", e)
        else:
            self.link_logger.error("Cannot send event: Socket is not connected.")

    @Slot()
    def on_ready_read(self):
        while self.socket.bytesAvailable() >= 4:
            header = self.socket.peek(4)
            if len(header) < 4:
                return

            data_len = self.header_struct.unpack(bytes(header))[0]
            if self.socket.bytesAvailable() < (4 + data_len):
                return

            self.socket.read(4)
            data_bytes = bytes(self.socket.read(data_len))

            self.link_recv_logger.debug("%s", data_bytes)

            try:
                decoded = data_bytes.decode()
                event = json.loads(decoded)
                ev_type = event.get("key", "unknown")
                val = event.get("value", "")
                remote_logger = self._get_remote_logger(ev_type)
                remote_logger.info("%s", val)

                self.event_received.emit(event)
            except Exception as e:
                self.link_logger.error("Deserialization error:  %s", e)

    @Slot()
    def stop(self):
        if self.reconnect_timer:
            self.reconnect_timer.stop()
        if self.socket:
            self.socket.disconnectFromHost()
            self.socket.close()
