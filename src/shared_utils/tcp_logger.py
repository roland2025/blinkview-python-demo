# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Roland Uuesoo

import logging
import queue
import socket
import threading


class NullDelimitedTCPHandler(logging.Handler):
    """
    A non-blocking logging handler that batches logs into a bytearray, flushing them
    over a persistent TCP connection via a dedicated background thread.
    Batches are framed using a trailing null byte (0).
    """

    def __init__(self, host, port, max_bytes=0xFFFF, flush_interval=0.1, timeout=2.0, max_queue_size=100000):
        super().__init__()
        self.host = host
        self.port = port
        self.max_bytes = max_bytes
        self.flush_interval = flush_interval
        self.timeout = timeout

        self.sock = None

        # Bounded queue prevents Out-Of-Memory if the network goes down permanently.
        self.queue = queue.Queue(maxsize=max_queue_size)
        self._stop_event = threading.Event()

        # Start a single, persistent background worker
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _connect(self):
        """Establishes or restores the persistent TCP socket cleanly."""
        if self.sock is not None:
            return True

        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))
            self.sock = sock
            return True
        except Exception:
            # Clean up the socket immediately if connect fails to prevent FD exhaustion
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
            self.sock = None
            return False

    def emit(self, record):
        """Called by the application thread. Instantly hands off the log and returns."""
        try:
            # Non-blocking put. If the queue is full (network dead for a long time),
            # this raises queue.Full and we drop the log to save the application.
            self.queue.put_nowait(
                f"{record.levelname} {int(record.created * 1_000_000_000)} {record.name}: {record.getMessage() if record.args else record.msg}"
            )

        except queue.Full:
            # Optional: You could write to a local fallback file here instead of dropping
            pass
        except Exception:
            self.handleError(record)

    def _worker_loop(self):
        """
        Background thread loop optimized to minimize context switches.
        Wakes up periodically, drains the queue instantly, and sleeps.
        """
        import time

        Empty = queue.Empty
        get_nowait = self.queue.get_nowait
        _send_batch = self._send_batch
        _len = len

        current_capacity = self.max_bytes
        max_allowed_capacity = 4 * 1024 * 1024  # 4MB

        buffer = bytearray(current_capacity)
        base_mv = memoryview(buffer)
        pos = 0

        stop_is_set = self._stop_event.is_set
        while not stop_is_set():
            try:
                # Strict Heartbeat: Sleep for the entire flush interval
                time.sleep(self.flush_interval)

                # 2. DRAIN PHASE: Pull everything currently in the queue without blocking
                while True:
                    try:
                        # put_nowait paired with get_nowait means zero thread blocking here
                        msg: str = get_nowait()
                    except Empty:
                        # The queue is completely empty for this tick. Stop draining.
                        break
                    # print(record)
                    # print(msg)
                    msg_bytes = msg.encode()
                    msg_len = _len(msg_bytes)
                    required_space = msg_len + 1

                    # 3. Dynamic Expansion Check
                    if pos + required_space > current_capacity:
                        if current_capacity < max_allowed_capacity:
                            new_capacity = current_capacity
                            while pos + required_space > new_capacity and new_capacity < max_allowed_capacity:
                                new_capacity *= 2

                            new_capacity = min(new_capacity, max_allowed_capacity)

                            if new_capacity >= current_capacity:
                                # print(f"Expanding buffer from {current_capacity} to {new_capacity}")
                                base_mv.release()
                                buffer.extend(b"\x00" * (new_capacity - current_capacity))
                                current_capacity = new_capacity
                                base_mv = memoryview(buffer)

                        # If it still doesn't fit after expansion attempt, flush the current batch
                        if pos + required_space > current_capacity:
                            if pos > 0:
                                _send_batch(base_mv[:pos])
                                pos = 0

                            # Massive log edge-case
                            if required_space > max_allowed_capacity:
                                giant_buffer = bytearray(msg_bytes)
                                giant_buffer.append(0)
                                _send_batch(memoryview(giant_buffer))
                                continue

                    # copy data into buffer, updating position and length
                    base_mv[pos : pos + msg_len] = msg_bytes
                    pos += msg_len
                    base_mv[pos] = 0
                    pos += 1

                    # If we perfectly hit current capacity mid-drain, flush immediately
                    if pos == current_capacity:
                        _send_batch(base_mv[:pos])
                        pos = 0

                # 5. POST-DRAIN FLUSH: Send whatever accumulated during this interval tick
                if pos > 0:
                    _send_batch(base_mv[:pos])
                    pos = 0

            except Exception as e:
                print(f"logger worker error: {e}")
                # Keep worker thread alive through unexpected glitches
                pass

        # Final cleanup on handler shutdown
        if pos > 0:
            _send_batch(base_mv[:pos])
        base_mv.release()

    def _send_batch(self, payload):
        """Transmits the buffer over TCP. Only called by the worker thread."""
        if not payload:
            return

        if not self._connect():
            # Connection failed. We return, and the worker loop will clear the buffer
            # since it was passed by reference, effectively dropping this batch.
            return

        try:
            self.sock.sendall(payload)
        except Exception:
            # Handle socket breakages gracefully by cleaning up for a reconnect attempt
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
            self.sock = None

    def close(self):
        """Shuts down the background thread and cleans up resources cleanly."""
        # Signal the thread to stop
        self._stop_event.set()

        # Wait up to 1 second for the worker to finish its last batch
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)

        # Close the socket
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

        super().close()


def setup_tcp_logger(
    host="127.0.0.1",
    port=5140,
    log_level=logging.DEBUG,
    max_bytes=32768,
    flush_interval=0.1,
    logger_name="app",
    extra_modules=None,  # List of tuples: [("module_name", level), ...]
):
    """
    Sets up a logger configured to stream null-delimited batched byte frames over TCP.
    """
    logger = logging.getLogger(logger_name)

    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), logging.DEBUG)

    logger.setLevel(log_level)

    if logger.hasHandlers():
        logger.handlers.clear()

    network_handler = NullDelimitedTCPHandler(host, port, max_bytes=max_bytes, flush_interval=flush_interval)
    network_handler.setLevel(log_level)

    logger.addHandler(network_handler)

    # Attach the same handler instance to any extra requested modules
    if extra_modules:
        for mod_name, mod_level in extra_modules:
            extra_logger = logging.getLogger(mod_name)
            if mod_level is not None:
                # Convert string levels to logging constants if necessary
                if isinstance(mod_level, str):
                    mod_level = getattr(logging, mod_level.upper(), logging.INFO)

                extra_logger.setLevel(mod_level)
            extra_logger.addHandler(network_handler)

    return logger
