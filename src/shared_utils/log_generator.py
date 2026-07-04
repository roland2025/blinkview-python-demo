# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Roland Uuesoo

import random
import threading
import time


class LogGenerator(threading.Thread):
    """
    Separate worker thread responsible for background log generation.
    Configured dynamically via thread-safe control methods.
    """

    def __init__(self, base_logger):
        super().__init__(daemon=True)
        self.logger = base_logger.getChild("generator")

        # State variables configuration
        self.enabled = False
        self.interval = 1.0
        self.batch_size = 1  # Changed from msgs_remaining to batch_size

        self.rng_mode = True  # Track if RNG random walk is enabled
        self.value = 0  # Starting value for the RNG mode

        # Thread safety guard for state updates
        self._lock = threading.Lock()
        self._running = True
        self.counter = 0

    def update_configuration(self, enabled=None, interval=None, batch_size=None):
        """Thread-safe entry point to reconfigure the generator."""
        with self._lock:
            if enabled is not None:
                self.enabled = enabled
                self.logger.getChild("enabled").info(str(enabled))
            if interval is not None:
                self.interval = float(interval / 1000)
                self.logger.getChild("interval").info(str(interval))
            if batch_size is not None:
                self.batch_size = int(batch_size)
                self.logger.getChild("batch_size").info(str(batch_size))

    def run(self):
        # Anchor so the very first run fires instantly
        monotonic = time.monotonic
        last_log_time = monotonic() - self.interval
        randint = random.randint

        log_data = self.logger.getChild("data").debug

        log_rng = self.logger.getChild("rng").debug

        while self._running:
            with self._lock:
                is_active = self.enabled
                current_interval = self.interval
                current_batch = self.batch_size
                is_rng = self.rng_mode

            now = monotonic()

            if is_active:
                # Dynamically calculate next target based on the CURRENT interval
                next_log_time = last_log_time + current_interval

                # Is it time to fire?
                if now >= next_log_time:
                    if is_rng:
                        # Move up or down by a random amount (e.g., -10 to 10)
                        step = randint(-10, 10)
                        # Clamp the value strictly between -100 and 100
                        self.value = max(-100, min(100, self.value + step))
                        log_rng(str(self.value))

                    counter = self.counter
                    for i in range(current_batch):
                        log_data(f"Simulated message #{counter}.")
                        # print(f"message {self.counter}")
                        counter += 1

                    self.counter = counter

                    # Update anchor. Using `now` instead of `next_log_time` prevents
                    # a rapid-fire catch-up loop if the thread was starved/paused.
                    last_log_time = now = monotonic()
                    next_log_time = last_log_time + current_interval

                # Calculate exact wait time
                if next_log_time > now:
                    time.sleep(next_log_time - now)

            else:
                # Idle state: Wait indefinitely until re-enabled or stopped

                time.sleep(0.1)

                # Reset the anchor so it fires instantly when turned back on
                last_log_time = monotonic() - self.interval

    def stop(self):
        self._running = False
        self.join(3)
