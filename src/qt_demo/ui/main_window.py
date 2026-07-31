# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Roland Uuesoo

import logging
import os
import signal
import subprocess
import sys
import threading
import time

from qtpy.QtCore import Qt, QThread, Signal, Slot
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from qt_demo.network_worker import NetworkWorker
from shared_utils.log_generator import LogGenerator


class QtClientApp(QMainWindow):
    request_send_event = Signal(dict)
    request_update_local_gen = Signal(bool, int, int)

    def __init__(self, logger):
        super().__init__()
        self.setWindowTitle("Qt Client-Backend Synchronization & Log Controls")
        self.resize(600, 750)

        icon_pixmap = self.style().standardPixmap(QStyle.SP_ComputerIcon)

        self.setWindowIcon(QIcon(icon_pixmap))

        self.logger = logger or logging.getLogger("ui")
        self.link_logger = self.logger.getChild("link")
        self.local_base_logger = self.logger.getChild("keys.local")
        self.remote_base_logger = self.logger.getChild("keys.remote")

        self._local_cache = {}
        self._cache_lock = threading.Lock()

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # Connection Status Banner
        status_group = QGroupBox("Backend status")
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(10, 5, 10, 5)

        self.lbl_connection_status = QLabel("Disconnected")
        self.lbl_connection_status.setStyleSheet("font-weight: bold; color: red;")

        # New Toggle Button for Headless Backend
        self.btn_toggle_backend = QPushButton("Start backend")
        self.btn_toggle_backend.setCheckable(True)
        self.btn_toggle_backend.clicked.connect(self.on_toggle_backend)

        status_layout.addWidget(self.btn_toggle_backend)
        status_layout.addWidget(QLabel("TCP Server Link:"))
        status_layout.addWidget(self.lbl_connection_status)
        status_layout.addStretch()
        status_group.setSizePolicy(status_group.sizePolicy().horizontalPolicy(), QSizePolicy.Fixed)
        main_layout.addWidget(status_group)

        # Track the process instance
        self.backend_process = None

        # --- LOG GENERATOR SIMULATION PANELS ---
        generators_layout = QHBoxLayout()

        # A. Local Generator Configuration Panel
        local_gen_group = QGroupBox("Local UI Log Generator")
        local_gen_form = QFormLayout(local_gen_group)

        self.chk_local_enabled = QCheckBox("Enabled")
        self.chk_local_enabled.toggled.connect(self.update_local_generator_config)

        self.sld_local_interval = QSpinBox()
        self.sld_local_interval.setRange(1, 1000)
        self.sld_local_interval.setValue(1000)
        self.lbl_local_interval = QLabel(f"{self.sld_local_interval.value()} ms")
        self.sld_local_interval.valueChanged.connect(self.update_local_generator_config)

        self.sld_local_msgs = QSpinBox()
        self.sld_local_msgs.setRange(1, 10000)
        self.sld_local_msgs.setValue(1)
        self.lbl_local_msgs = QLabel(f"{self.sld_local_msgs.value()}")
        self.sld_local_msgs.valueChanged.connect(self.update_local_generator_config)

        local_gen_form.addRow(self.chk_local_enabled)
        local_gen_form.addRow("Interval:", self.sld_local_interval)
        local_gen_form.addRow("", self.lbl_local_interval)
        local_gen_form.addRow("Msg Count:", self.sld_local_msgs)
        local_gen_form.addRow("", self.lbl_local_msgs)
        generators_layout.addWidget(local_gen_group)

        # B. Backend Remote Generator Configuration Panel
        remote_gen_group = QGroupBox("Remote Backend Log Generator")
        remote_gen_form = QFormLayout(remote_gen_group)

        self.chk_remote_enabled = QCheckBox("Enabled")
        self.chk_remote_enabled.toggled.connect(self.on_backend_enabled_changed)

        self.sld_remote_interval = QSpinBox()
        self.sld_remote_interval.setRange(1, 1000)
        self.sld_remote_interval.setValue(1000)
        self.lbl_remote_interval = QLabel(f"{self.sld_remote_interval.value()} ms")
        self.sld_remote_interval.valueChanged.connect(self.on_backend_interval_changed)

        self.sld_remote_msgs = QSpinBox()
        self.sld_remote_msgs.setRange(1, 10000)
        self.sld_remote_msgs.setValue(1)
        self.lbl_remote_msgs = QLabel(f"{self.sld_remote_msgs.value()}")

        self.sld_remote_msgs.valueChanged.connect(self.on_backend_msgs_changed)

        remote_gen_form.addRow(self.chk_remote_enabled)
        remote_gen_form.addRow("Interval:", self.sld_remote_interval)
        remote_gen_form.addRow("", self.lbl_remote_interval)
        remote_gen_form.addRow("Msg Count:", self.sld_remote_msgs)
        remote_gen_form.addRow("", self.lbl_remote_msgs)
        generators_layout.addWidget(remote_gen_group)

        main_layout.addLayout(generators_layout)

        # --- INTERACTIVE CONTROLS ---
        input_group = QGroupBox("Interactive Controls")
        input_layout = QVBoxLayout(input_group)

        self.btn = QPushButton("Trigger Network Event")
        self.btn.clicked.connect(self.on_button_clicked)
        self.btn.pressed.connect(self.on_button_pressed)
        self.btn.released.connect(self.on_button_released)
        input_layout.addWidget(self.btn)

        self.txt_input = QLineEdit()
        self.txt_input.setPlaceholderText("Type something here...")
        self.txt_input.textChanged.connect(self.on_text_changed)
        input_layout.addWidget(self.txt_input)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(50)
        self.slider.valueChanged.connect(self.on_slider_changed)
        input_layout.addWidget(self.slider)

        self.combobox = QComboBox()

        levels = [
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
        ]

        # 3. Format them with a suffix (e.g., "INFO A", "ERROR B")
        # Using ASCII math/letter trick to pair them with A, B, C, D, E...
        items = [f"{logging.getLevelName(level)} {chr(65 + i)}" for i, level in enumerate(levels)]

        # 4. Add to your combobox
        self.combobox.addItems(items)
        self.combobox.currentTextChanged.connect(self.on_combobox_changed)
        input_layout.addWidget(self.combobox)

        self.checkbox = QCheckBox("Enable Feature Toggle")
        self.checkbox.toggled.connect(self.on_checkbox_toggled)
        input_layout.addWidget(self.checkbox)

        main_layout.addWidget(input_group)

        # --- VIEWERS LAYOUT ---
        viewers_layout = QHBoxLayout()

        local_group = QGroupBox("Local State Viewer")
        local_form = QFormLayout(local_group)
        self.lbl_local_btn = QLabel("Idle")
        self.lbl_local_txt = QLabel("")
        self.lbl_local_sld = QLabel("0")
        self.lbl_local_cmb = QLabel("Option A")
        self.lbl_local_chk = QLabel("False")

        local_form.addRow("Last Action:", self.lbl_local_btn)
        local_form.addRow("Text State:", self.lbl_local_txt)
        local_form.addRow("Slider Value:", self.lbl_local_sld)
        local_form.addRow("ComboBox:", self.lbl_local_cmb)
        local_form.addRow("CheckBox:", self.lbl_local_chk)
        viewers_layout.addWidget(local_group)

        remote_group = QGroupBox("Remote State Viewer (Echoed)")
        remote_form = QFormLayout(remote_group)
        self.lbl_remote_btn = QLabel("Idle")
        self.lbl_remote_txt = QLabel("")
        self.lbl_remote_sld = QLabel("0")
        self.lbl_remote_cmb = QLabel("Option A")
        self.lbl_remote_chk = QLabel("False")

        remote_form.addRow("Last Action:", self.lbl_remote_btn)
        remote_form.addRow("Text State:", self.lbl_remote_txt)
        remote_form.addRow("Slider Value:", self.lbl_remote_sld)
        remote_form.addRow("ComboBox:", self.lbl_remote_cmb)
        remote_form.addRow("CheckBox:", self.lbl_remote_chk)
        viewers_layout.addWidget(remote_group)

        main_layout.addLayout(viewers_layout)

        self.network_thread = QThread()
        self.worker = NetworkWorker(
            host="127.0.0.1", port=65500, link_logger=self.link_logger, remote_base_logger=self.remote_base_logger
        )
        self.worker.moveToThread(self.network_thread)

        self.local_generator = LogGenerator(self.logger)

        self.network_thread.started.connect(self.worker.start_connection)
        self.request_send_event.connect(self.worker.send_json_event)
        self.request_update_local_gen.connect(self.local_generator.update_configuration)

        self.worker.connected.connect(self.on_connected_ui)
        self.worker.disconnected.connect(self.on_disconnected_ui)
        self.worker.event_received.connect(self.update_remote_viewer)

        self.network_thread.start()
        self.local_generator.start()

        self.update_local_generator_config()

    def _get_local_logger(self, event_type):
        try:
            return self._local_cache[event_type]
        except KeyError:
            pass

        with self._cache_lock:
            try:
                return self._local_cache[event_type]
            except KeyError:
                logger = self.local_base_logger.getChild(str(event_type))
                self._local_cache[event_type] = logger
                return logger

    # --- CONTROLLER SYNC FUNCTIONS ---
    def update_local_generator_config(self):
        enabled = self.chk_local_enabled.isChecked()
        interval = self.sld_local_interval.value()
        msgs = self.sld_local_msgs.value()

        self.lbl_local_interval.setText(f"{interval} ms")
        self.lbl_local_msgs.setText(str(msgs))
        self.local_generator.update_configuration(enabled, interval, msgs)

    # --- FLAT EVENT HANDLERS MATCHING THE NEW BACKEND ---
    def on_backend_enabled_changed(self, checked):
        # Transmit as discrete key/value matching: event_type == "generator_enabled"
        # Since backend checks bool(event_value), pass it as an actual bool or string representation
        self.request_send_event.emit({"key": "generator_enabled", "value": checked, "timestamp": time.time()})

    def on_backend_interval_changed(self, value):
        self.lbl_remote_interval.setText(f"{value} ms")
        self.request_send_event.emit({"key": "generator_interval", "value": value, "timestamp": time.time()})

    def on_backend_msgs_changed(self, value):
        self.lbl_remote_msgs.setText(str(value))
        self.request_send_event.emit({"key": "generator_msgs", "value": value, "timestamp": time.time()})

    def sync_all_backend_settings(self):
        """Dispatches full initialization states sequentially matching the new backend schema."""
        self.on_backend_enabled_changed(self.chk_remote_enabled.isChecked())
        self.on_backend_interval_changed(self.sld_remote_interval.value())
        self.on_backend_msgs_changed(self.sld_remote_msgs.value())

    @Slot()
    def on_connected_ui(self):
        self.link_logger.info("Connected to backend server.")
        self.lbl_connection_status.setText("Connected")
        self.lbl_connection_status.setStyleSheet("font-weight: bold; color: green;")
        self.sync_all_backend_settings()

    @Slot()
    def on_disconnected_ui(self):
        self.link_logger.warning("Disconnected from backend server. Retrying...")
        self.lbl_connection_status.setText("Disconnected (Retrying...)")
        self.lbl_connection_status.setStyleSheet("font-weight: bold; color: orange;")

    # --- INTERACTION EVENT HANDLERS ---
    def on_button_clicked(self):
        timestamp = time.time()
        self.lbl_local_btn.setText(f"clicked ({timestamp:.2f})")
        self._get_local_logger("button").info("clicked")
        self.request_send_event.emit({"key": "button", "value": "clicked", "timestamp": timestamp})

    def on_button_pressed(self):
        timestamp = time.time()
        self.lbl_local_btn.setText(f"pressed ({timestamp:.2f})")
        self._get_local_logger("button_state").info("pressed")
        self.request_send_event.emit({"key": "button_state", "value": "pressed", "timestamp": timestamp})

    def on_button_released(self):
        timestamp = time.time()
        self.lbl_local_btn.setText(f"released ({timestamp:.2f})")
        self._get_local_logger("button_state").info("released")
        self.request_send_event.emit({"key": "button_state", "value": "released", "timestamp": timestamp})

    def on_text_changed(self, text):
        self.lbl_local_txt.setText(text)
        self._get_local_logger("text").info(f"{text}")
        self.request_send_event.emit({"key": "text", "value": text, "timestamp": time.time()})

    def on_slider_changed(self, value):
        self.lbl_local_sld.setText(str(value))

        log_level = logging.INFO
        slider = self.slider
        if slider.maximum() == value or slider.minimum() == value:
            log_level = logging.ERROR
        elif slider.maximum() - 10 < value or slider.minimum() + 10 > value:
            log_level = logging.WARNING

        self._get_local_logger("slider").log(log_level, "%s", value)
        self.request_send_event.emit({"key": "slider", "value": value, "timestamp": time.time()})

    def on_combobox_changed(self, text):
        self.lbl_local_cmb.setText(text)
        first_word = text.split()[0].upper()
        valid_levels = logging.getLevelNamesMapping()
        level_int = valid_levels.get(first_word, logging.INFO)
        self._get_local_logger("combobox").log(level_int, text)
        self.request_send_event.emit({"key": "combobox", "value": text, "timestamp": time.time()})

    def on_checkbox_toggled(self, checked):
        state_str = "True" if checked else "False"
        self.lbl_local_chk.setText(state_str)
        self._get_local_logger("checkbox").info(state_str)
        self.request_send_event.emit({"key": "checkbox", "value": checked, "timestamp": time.time()})

    @Slot(dict)
    def update_remote_viewer(self, event):
        ev_type = event.get("key", "unknown")
        val = event.get("value", "")

        if ev_type in ["button", "button_state"]:
            timestamp = event.get("timestamp", "")
            self.lbl_remote_btn.setText(f"{val} ({float(timestamp):.2f})")
        elif ev_type == "text":
            self.lbl_remote_txt.setText(str(val))
        elif ev_type == "slider":
            self.lbl_remote_sld.setText(str(val))
        elif ev_type == "combobox":
            self.lbl_remote_cmb.setText(str(val))
        elif ev_type == "checkbox":
            self.lbl_remote_chk.setText("True" if val else "False")
        # Handle showing echoes of the configuration updates in the generic status viewers if needed
        # elif ev_type == "generator_enabled":
        #     self.lbl_remote_btn.setText(f"Gen Enabled: {val}")
        # elif ev_type == "generator_interval":
        #     self.lbl_remote_txt.setText(f"Gen Int: {val}ms")

    def closeEvent(self, event):
        self.local_generator.stop()

        self.worker.stop()
        self.network_thread.quit()
        self.network_thread.wait()

        self.stop_headless_backend()

        super().closeEvent(event)

    def on_toggle_backend(self, checked):
        if checked:
            self.start_headless_backend()
        else:
            self.stop_headless_backend()

    def start_headless_backend(self):
        if self.backend_process and self.backend_process.poll() is None:
            return  # Already running

        self.link_logger.info("Starting built-in headless backend process...")

        # Create a session/process group on Linux to guarantee signal delivery
        kwargs = {}
        if sys.platform != "win32":
            kwargs["preexec_fn"] = os.setsid

        self.backend_process = subprocess.Popen(
            [sys.executable, "-m", "backend_demo.main"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs
        )
        self.btn_toggle_backend.setText("Stop backend")
        self.btn_toggle_backend.setStyleSheet("font-weight: bold; color: darkred;")

    def stop_headless_backend(self):
        if self.backend_process and self.backend_process.poll() is None:
            self.link_logger.info("Stopping built-in headless backend process...")

            try:
                if sys.platform != "win32":
                    # Replicate System Monitor/kill command behavior across the process group
                    pgid = os.getpgid(self.backend_process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                else:
                    self.backend_process.terminate()

                # Await graceful exit
                self.backend_process.wait(timeout=2)

            except subprocess.TimeoutExpired:
                self.link_logger.warning("Backend missed SIGTERM. Sending SIGKILL...")
                try:
                    if sys.platform != "win32":
                        os.killpg(os.getpgid(self.backend_process.pid), signal.SIGKILL)
                    else:
                        self.backend_process.kill()
                    self.backend_process.wait(timeout=1)
                except Exception as e:
                    self.link_logger.error("Force kill failed: %s", e)
            except Exception as e:
                self.link_logger.error("Error during backend termination: %s", e)

        self.backend_process = None
        self.btn_toggle_backend.setChecked(False)
        self.btn_toggle_backend.setText("Start backend")
        self.btn_toggle_backend.setStyleSheet("")


def main():
    import sys
    from qtpy.QtWidgets import QApplication

    # Setup basic logging to stderr so you can see logs in the PyCharm console
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    root_logger = logging.getLogger()

    # Initialize the Qt Application Context
    app = QApplication(sys.argv)

    # Instantiate and showcase the client UI window
    window = QtClientApp(logger=root_logger)
    window.show()

    # Hand over control to the Qt Event Loop
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
