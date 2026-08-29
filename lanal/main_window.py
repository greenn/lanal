from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from http import HTTPStatus

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .curl_presets import RequestOptions, display_command, option_summary, validate_url
from .curl_runner import CurlInfo, execute_curl, find_curl
from .database import Database, StoredRequest
from .parsers import parse_headers


class CurlWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, executable: str, url: str, options: RequestOptions) -> None:
        super().__init__()
        self.executable = executable
        self.url = url
        self.options = options

    def run(self) -> None:
        try:
            self.finished.emit(execute_curl(self.executable, self.url, self.options))
        except Exception as exc:  # worker errors are surfaced in the UI
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.settings = QSettings("Lanal", "Lanal")
        self.curl_info: CurlInfo = find_curl()
        self.current_request_id: int | None = None
        self.worker_thread: QThread | None = None
        self.worker: CurlWorker | None = None

        self.setWindowTitle(f"Lanal {__version__}")
        self.setMinimumSize(1100, 700)
        self.resize(1480, 880)
        self._build_ui()
        self._apply_style()
        self._connect_signals()
        self._restore_window_state()
        self.reload_history()
        self.update_command_preview()
        self._update_curl_status()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(22, 18, 22, 18)
        root_layout.setSpacing(14)
        self.setCentralWidget(root)

        topbar = QHBoxLayout()
        brand = QLabel(f"⌁  Lanal {__version__}")
        brand.setObjectName("brand")
        topbar.addWidget(brand)
        topbar.addStretch(1)
        root_layout.addLayout(topbar)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_history_panel())
        self.splitter.addWidget(self._build_center_panel())
        self.splitter.addWidget(self._build_inspector_panel())
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([285, 930, 230])
        root_layout.addWidget(self.splitter, 1)

        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.setStatusBar(status)
        self.curl_status_label = QLabel()
        self.run_status_label = QLabel("Ready")
        status.addWidget(self.run_status_label)
        status.addPermanentWidget(self.curl_status_label)

    def _build_history_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("historyPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)

        title_row = QHBoxLayout()
        title = QLabel("HISTORY")
        title.setObjectName("sectionTitle")
        self.new_request_button = QToolButton()
        self.new_request_button.setText("+")
        self.new_request_button.setToolTip("New request")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.new_request_button)
        layout.addLayout(title_row)

        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("Search domains or requests…")
        self.history_search.setClearButtonEnabled(True)
        layout.addWidget(self.history_search)

        self.history_tree = QTreeWidget()
        self.history_tree.setHeaderHidden(True)
        self.history_tree.setIndentation(14)
        self.history_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history_tree.setObjectName("historyTree")
        layout.addWidget(self.history_tree, 1)

        footer = QHBoxLayout()
        footer.addWidget(QLabel("Total requests"))
        footer.addStretch(1)
        self.total_requests_label = QLabel("0")
        self.total_requests_label.setObjectName("mutedStrong")
        footer.addWidget(self.total_requests_label)
        layout.addLayout(footer)
        return panel

    def _build_center_panel(self) -> QWidget:
        center = QWidget()
        center.setObjectName("centerPanel")
        layout = QVBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        request_card = QFrame()
        request_card.setObjectName("card")
        request_layout = QVBoxLayout(request_card)
        request_layout.setContentsMargins(16, 16, 16, 14)
        request_layout.setSpacing(12)

        url_row = QHBoxLayout()
        self.url_input = QLineEdit("https://novelcrow.com/")
        self.url_input.setPlaceholderText("https://example.com/")
        self.url_input.setObjectName("urlInput")
        self.run_button = QPushButton("Run  ▶")
        self.run_button.setObjectName("runButton")
        self.run_button.setMinimumWidth(105)
        url_row.addWidget(self.url_input, 1)
        url_row.addWidget(self.run_button)
        request_layout.addLayout(url_row)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.method_widget, self.method_group = self._segmented(["HEAD", "GET"], "HEAD")
        controls.addWidget(self.method_widget)

        self.verbose_check = QCheckBox("Verbose")
        self.verbose_check.setObjectName("pillCheck")
        controls.addWidget(self.verbose_check)

        self.ip_widget, self.ip_group = self._segmented(["IPv4", "IPv6"], "IPv4")
        controls.addWidget(self.ip_widget)

        self.http_widget, self.http_group = self._segmented(["HTTP/1.1", "HTTP/2"], "HTTP/2")
        controls.addWidget(self.http_widget)

        self.browser_check = QCheckBox("Browser-like")
        self.browser_check.setChecked(True)
        self.browser_check.setObjectName("pillCheck")
        controls.addWidget(self.browser_check)

        self.extra_combo = QComboBox()
        self.extra_combo.addItems(["Info", "Redirects", "Raw", "None"])
        controls.addWidget(self.extra_combo)
        controls.addStretch(1)
        request_layout.addLayout(controls)
        layout.addWidget(request_card)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_overview_tab(), "Overview")
        self.tabs.addTab(self._build_headers_tab(), "Headers")
        self.tabs.addTab(self._build_body_tab(), "Body")
        self.tabs.addTab(self._build_debug_tab(), "Debug")
        self.tabs.addTab(self._build_timing_tab(), "Timing")
        self.tabs.addTab(self._build_command_tab(), "Command")
        layout.addWidget(self.tabs, 1)
        return center

    def _build_overview_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 12, 0, 0)
        outer.setSpacing(12)

        summary = QFrame()
        summary.setObjectName("card")
        layout = QVBoxLayout(summary)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(20)

        hero = QHBoxLayout()
        self.status_badge = QLabel("403")
        self.status_badge.setObjectName("statusBadge")
        self.status_title = QLabel("Forbidden")
        self.status_title.setObjectName("statusTitle")
        hero.addWidget(self.status_badge)
        hero.addWidget(self.status_title)
        hero.addStretch(1)
        self.server_hero = QLabel("☁  cloudflare")
        self.server_hero.setObjectName("serverHero")
        hero.addWidget(self.server_hero)
        layout.addLayout(hero)

        grid = QGridLayout()
        grid.setHorizontalSpacing(30)
        grid.setVerticalSpacing(14)
        self.overview_values: dict[str, QLabel] = {}
        rows = [
            ("Final URL", "final_url"),
            ("Protocol", "protocol"),
            ("Remote IP", "remote_ip"),
            ("Remote Port", "remote_port"),
            ("Server", "server"),
            ("TLS", "tls"),
        ]
        timing_rows = [
            ("DNS Lookup", "dns"),
            ("TCP Connect", "connect"),
            ("TLS Handshake", "tls_time"),
            ("TTFB", "ttfb"),
            ("Total Time", "total"),
            ("Exit code", "exit_code"),
        ]
        for row, (label, key) in enumerate(rows):
            grid.addWidget(self._muted_label(label), row, 0)
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.overview_values[key] = value
            grid.addWidget(value, row, 1)
        for row, (label, key) in enumerate(timing_rows):
            grid.addWidget(self._muted_label(label), row, 2)
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.overview_values[key] = value
            grid.addWidget(value, row, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        layout.addLayout(grid)
        outer.addWidget(summary)

        metrics = QFrame()
        metrics.setObjectName("card")
        metric_layout = QHBoxLayout(metrics)
        metric_layout.setContentsMargins(20, 16, 20, 16)
        metric_layout.setSpacing(20)
        self.metric_labels: dict[str, QLabel] = {}
        for caption, key in [
            ("Status", "status"),
            ("Protocol", "protocol"),
            ("Server", "server"),
            ("IP", "ip"),
            ("Total Time", "time"),
        ]:
            box = QVBoxLayout()
            box.addWidget(self._muted_label(caption))
            value = QLabel("—")
            value.setObjectName("metricValue")
            self.metric_labels[key] = value
            box.addWidget(value)
            metric_layout.addLayout(box)
            if key != "time":
                metric_layout.addStretch(1)
        outer.addWidget(metrics)
        outer.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _build_headers_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        splitter = QSplitter(Qt.Vertical)

        self.headers_table = QTableWidget(0, 2)
        self.headers_table.setHorizontalHeaderLabels(["Header", "Value"])
        self.headers_table.verticalHeader().setVisible(False)
        self.headers_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.headers_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.headers_table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.headers_table)

        self.headers_raw = QPlainTextEdit()
        self.headers_raw.setReadOnly(True)
        self.headers_raw.setPlaceholderText("Raw response headers")
        splitter.addWidget(self.headers_raw)
        splitter.setSizes([330, 190])
        layout.addWidget(splitter)
        return widget

    def _build_body_tab(self) -> QWidget:
        self.body_text = QPlainTextEdit()
        self.body_text.setReadOnly(True)
        self.body_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._set_monospace(self.body_text)
        return self._padded(self.body_text)

    def _build_debug_tab(self) -> QWidget:
        self.debug_text = QPlainTextEdit()
        self.debug_text.setReadOnly(True)
        self.debug_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._set_monospace(self.debug_text)
        return self._padded(self.debug_text)

    def _build_timing_tab(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(26, 24, 26, 24)
        self.timing_values: dict[str, QLabel] = {}
        names = [
            ("DNS lookup", "dns"),
            ("TCP connect", "connect"),
            ("TLS handshake", "tls"),
            ("Time to first byte", "ttfb"),
            ("Total", "total"),
        ]
        for row, (caption, key) in enumerate(names):
            grid.addWidget(QLabel(caption), row, 0)
            value = QLabel("—")
            value.setObjectName("timingValue")
            grid.addWidget(value, row, 1)
            self.timing_values[key] = value
        grid.setColumnStretch(0, 1)
        return self._padded(card)

    def _build_command_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        self.command_text = QPlainTextEdit()
        self.command_text.setReadOnly(True)
        self.command_text.setMaximumHeight(120)
        self._set_monospace(self.command_text)
        layout.addWidget(self.command_text)
        self.command_summary = QLabel()
        self.command_summary.setWordWrap(True)
        self.command_summary.setObjectName("mutedText")
        layout.addWidget(self.command_summary)
        capture_note = QLabel(
            "Lanal executes the shown request options and adds temporary -D / -o / --write-out flags only to capture headers, body and metrics."
        )
        capture_note.setWordWrap(True)
        capture_note.setObjectName("mutedText")
        layout.addWidget(capture_note)
        buttons = QHBoxLayout()
        self.copy_command_button = QPushButton("Copy command")
        self.delete_request_button = QPushButton("Delete selected history item")
        self.delete_request_button.setObjectName("dangerButton")
        buttons.addWidget(self.copy_command_button)
        buttons.addStretch(1)
        buttons.addWidget(self.delete_request_button)
        layout.addLayout(buttons)
        layout.addStretch(1)
        return widget

    def _build_inspector_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("inspectorPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        hint_card = QFrame()
        hint_card.setObjectName("sideCard")
        hint_layout = QVBoxLayout(hint_card)
        hint_layout.setContentsMargins(16, 16, 16, 16)
        hint_layout.setSpacing(12)
        title = QLabel("HINTS")
        title.setObjectName("sectionTitle")
        hint_layout.addWidget(title)

        self.hint_status_code = QLabel("403")
        self.hint_status_code.setObjectName("hintStatus")
        self.hint_status_text = QLabel("Forbidden")
        self.hint_status_text.setObjectName("sideStrong")
        hint_layout.addWidget(self.hint_status_code)
        hint_layout.addWidget(self.hint_status_text)
        hint_layout.addSpacing(8)
        self.hint_server = QLabel("☁  cloudflare")
        self.hint_server.setObjectName("sideStrong")
        self.hint_server_type = QLabel("CDN / Security")
        self.hint_server_type.setObjectName("mutedText")
        hint_layout.addWidget(self.hint_server)
        hint_layout.addWidget(self.hint_server_type)
        layout.addWidget(hint_card)

        note_card = QFrame()
        note_card.setObjectName("sideCard")
        note_layout = QVBoxLayout(note_card)
        note_layout.setContentsMargins(16, 16, 16, 16)
        note_layout.setSpacing(10)
        note_title = QLabel("NOTE")
        note_title.setObjectName("sectionTitle")
        note_layout.addWidget(note_title)
        self.note_edit = QPlainTextEdit()
        self.note_edit.setPlaceholderText("Write your note…")
        note_layout.addWidget(self.note_edit, 1)
        self.save_note_button = QPushButton("Save note")
        note_layout.addWidget(self.save_note_button)
        layout.addWidget(note_card, 1)
        return panel

    def _segmented(self, labels: list[str], checked: str) -> tuple[QWidget, QButtonGroup]:
        widget = QFrame()
        widget.setObjectName("segmented")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        group = QButtonGroup(widget)
        group.setExclusive(True)
        for label in labels:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setChecked(label == checked)
            button.setProperty("segment", True)
            group.addButton(button)
            layout.addWidget(button)
        return widget, group

    @staticmethod
    def _muted_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("mutedText")
        return label

    @staticmethod
    def _padded(child: QWidget) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.addWidget(child)
        return widget

    @staticmethod
    def _set_monospace(widget: QWidget) -> None:
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        widget.setFont(font)

    # ---------- behavior ----------

    def _connect_signals(self) -> None:
        self.run_button.clicked.connect(self.run_request)
        self.new_request_button.clicked.connect(self.new_request)
        self.history_search.textChanged.connect(self.filter_history)
        self.history_tree.itemSelectionChanged.connect(self.history_selection_changed)
        self.url_input.textChanged.connect(self.update_command_preview)
        self.verbose_check.toggled.connect(self.update_command_preview)
        self.browser_check.toggled.connect(self.update_command_preview)
        self.extra_combo.currentTextChanged.connect(self.update_command_preview)
        self.method_group.buttonClicked.connect(self.update_command_preview)
        self.ip_group.buttonClicked.connect(self.update_command_preview)
        self.http_group.buttonClicked.connect(self.update_command_preview)
        self.copy_command_button.clicked.connect(self.copy_command)
        self.save_note_button.clicked.connect(self.save_note)
        self.delete_request_button.clicked.connect(self.delete_selected_request)

    def current_options(self) -> RequestOptions:
        return RequestOptions(
            method=self.method_group.checkedButton().text(),
            verbose=self.verbose_check.isChecked(),
            ip_version=self.ip_group.checkedButton().text(),
            http_version=self.http_group.checkedButton().text(),
            browser_like=self.browser_check.isChecked(),
            extra=self.extra_combo.currentText(),
        )

    def update_command_preview(self, *_args: object) -> None:
        executable = self.curl_info.executable or "curl.exe"
        try:
            command = display_command(executable, self.url_input.text().strip(), self.current_options())
        except ValueError:
            command = "Enter a valid http:// or https:// URL"
        self.command_text.setPlainText(command)
        self.command_summary.setText(option_summary(self.current_options()))

    def run_request(self) -> None:
        if self.worker_thread is not None:
            return
        try:
            url = validate_url(self.url_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid URL", str(exc))
            return
        if not self.curl_info.executable:
            QMessageBox.critical(self, "curl not found", "curl.exe was not found. Install curl or use Windows 10/11 with curl available in PATH.")
            return

        self.run_button.setEnabled(False)
        self.run_button.setText("Running…")
        self.run_status_label.setText("Running")

        thread = QThread(self)
        worker = CurlWorker(self.curl_info.executable, url, self.current_options())
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._request_finished)
        worker.failed.connect(self._request_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._worker_cleanup)
        self.worker_thread = thread
        self.worker = worker
        thread.start()

    def _request_finished(self, result: StoredRequest) -> None:
        request_id = self.database.add_request(result)
        result.id = request_id
        self.run_status_label.setText("Completed")
        self.reload_history(select_id=request_id)
        self.display_request(result)

    def _request_failed(self, message: str) -> None:
        self.run_status_label.setText("Failed")
        QMessageBox.critical(self, "Request failed", message)

    def _worker_cleanup(self) -> None:
        if self.worker_thread is not None:
            self.worker_thread.deleteLater()
        self.worker_thread = None
        self.worker = None
        self.run_button.setEnabled(bool(self.curl_info.executable))
        self.run_button.setText("Run  ▶")

    def reload_history(self, select_id: int | None = None) -> None:
        items = self.database.list_requests()
        grouped: dict[str, list[StoredRequest]] = defaultdict(list)
        for item in items:
            grouped[item.domain].append(item)

        self.history_tree.blockSignals(True)
        self.history_tree.clear()
        selected_tree_item: QTreeWidgetItem | None = None
        for domain, requests in grouped.items():
            parent = QTreeWidgetItem([f"◎  {domain}                                      {len(requests)}"])
            parent.setData(0, Qt.UserRole, None)
            parent.setExpanded(True)
            self.history_tree.addTopLevelItem(parent)
            for request in requests:
                time_text = self._history_time(request.started_at)
                status = str(request.status_code or "ERR")
                sample = "  sample" if request.is_sample else ""
                child = QTreeWidgetItem([f"{time_text}    {status:>3}    {request.preset_name}{sample}"])
                child.setData(0, Qt.UserRole, request.id)
                parent.addChild(child)
                if request.id == select_id:
                    selected_tree_item = child

        self.history_tree.blockSignals(False)
        self.total_requests_label.setText(str(len(items)))

        if selected_tree_item:
            self.history_tree.setCurrentItem(selected_tree_item)
        elif items:
            first_parent = self.history_tree.topLevelItem(0)
            if first_parent and first_parent.childCount():
                self.history_tree.setCurrentItem(first_parent.child(0))

    def filter_history(self, text: str) -> None:
        query = text.strip().lower()
        for index in range(self.history_tree.topLevelItemCount()):
            parent = self.history_tree.topLevelItem(index)
            parent_match = query in parent.text(0).lower()
            visible_children = 0
            for child_index in range(parent.childCount()):
                child = parent.child(child_index)
                child_visible = not query or parent_match or query in child.text(0).lower()
                child.setHidden(not child_visible)
                visible_children += int(child_visible)
            parent.setHidden(bool(query) and not parent_match and visible_children == 0)

    def history_selection_changed(self) -> None:
        items = self.history_tree.selectedItems()
        if not items:
            return
        request_id = items[0].data(0, Qt.UserRole)
        if not request_id:
            return
        item = self.database.get_request(int(request_id))
        if item:
            self.display_request(item)

    def display_request(self, item: StoredRequest) -> None:
        self.current_request_id = item.id
        self.url_input.blockSignals(True)
        self.url_input.setText(item.url)
        self.url_input.blockSignals(False)

        status_code = item.status_code
        status_text = self._status_text(status_code)
        self.status_badge.setText(str(status_code or "ERR"))
        self.status_badge.setProperty("ok", bool(status_code and 200 <= status_code < 400))
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)
        self.status_title.setText(status_text)
        self.server_hero.setText(f"☁  {item.server or '—'}")

        values = {
            "final_url": item.final_url or item.url,
            "protocol": self._protocol_text(item.http_version),
            "remote_ip": item.remote_ip or "—",
            "remote_port": item.remote_port or "—",
            "server": item.server or "—",
            "tls": "TLS negotiated" if item.timing.get("tls", 0) else "—",
            "dns": self._seconds(item.timing.get("dns")),
            "connect": self._seconds(item.timing.get("connect")),
            "tls_time": self._seconds(item.timing.get("tls")),
            "ttfb": self._seconds(item.timing.get("ttfb")),
            "total": self._seconds(item.timing.get("total")) or f"{item.duration_ms / 1000:.3f} s",
            "exit_code": str(item.exit_code),
        }
        for key, value in values.items():
            self.overview_values[key].setText(value or "—")

        self.metric_labels["status"].setText(status_text)
        self.metric_labels["protocol"].setText(values["protocol"])
        self.metric_labels["server"].setText(values["server"])
        self.metric_labels["ip"].setText(values["remote_ip"])
        self.metric_labels["time"].setText(values["total"])

        parsed = parse_headers(item.headers_raw)
        rows = [pair for block in parsed.blocks for pair in block]
        self.headers_table.setRowCount(len(rows))
        for row, (name, value) in enumerate(rows):
            self.headers_table.setItem(row, 0, QTableWidgetItem(name))
            self.headers_table.setItem(row, 1, QTableWidgetItem(value))
        self.headers_table.resizeColumnsToContents()
        self.headers_raw.setPlainText(item.headers_raw)
        self.body_text.setPlainText(item.body)

        debug_parts = []
        if item.stderr:
            debug_parts.append("STDERR / curl diagnostics\n" + item.stderr)
        if item.stdout:
            debug_parts.append("STDOUT\n" + item.stdout)
        if not debug_parts:
            debug_parts.append("No diagnostic output captured. Enable Verbose for connection details.")
        self.debug_text.setPlainText("\n\n".join(debug_parts))

        self.timing_values["dns"].setText(values["dns"])
        self.timing_values["connect"].setText(values["connect"])
        self.timing_values["tls"].setText(values["tls_time"])
        self.timing_values["ttfb"].setText(values["ttfb"])
        self.timing_values["total"].setText(values["total"])

        self.command_text.setPlainText(item.display_command)
        sample_text = " · SAMPLE DATA" if item.is_sample else ""
        self.command_summary.setText(item.preset_name + sample_text)
        self.note_edit.setPlainText(item.note)

        self.hint_status_code.setText(str(status_code or "ERR"))
        self.hint_status_text.setText(status_text)
        self.hint_server.setText(f"☁  {item.server or 'Unknown server'}")
        self.hint_server_type.setText("CDN / Security" if (item.server or "").lower() == "cloudflare" else "Response server")
        self.run_status_label.setText("Sample" if item.is_sample else "Completed")

    def new_request(self) -> None:
        self.current_request_id = None
        self.url_input.setText("https://novelcrow.com/")
        self.note_edit.clear()
        self.tabs.setCurrentIndex(0)
        self.url_input.setFocus()
        self.url_input.selectAll()

    def save_note(self) -> None:
        if not self.current_request_id:
            QMessageBox.information(self, "Note", "Run or select a stored request before saving a note.")
            return
        self.database.update_note(self.current_request_id, self.note_edit.toPlainText())
        self.run_status_label.setText("Note saved")

    def delete_selected_request(self) -> None:
        if not self.current_request_id:
            return
        response = QMessageBox.question(self, "Delete request", "Delete this stored request from local history?")
        if response != QMessageBox.Yes:
            return
        self.database.delete_request(self.current_request_id)
        self.current_request_id = None
        self.reload_history()

    def copy_command(self) -> None:
        QGuiApplication.clipboard().setText(self.command_text.toPlainText())
        self.run_status_label.setText("Command copied")

    def _update_curl_status(self) -> None:
        self.curl_status_label.setText(self.curl_info.version)
        self.run_button.setEnabled(bool(self.curl_info.executable))
        if not self.curl_info.executable:
            self.run_status_label.setText("curl.exe not found")

    # ---------- settings / helpers ----------

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.saveState())
        self.settings.setValue("last_url", self.url_input.text())
        super().closeEvent(event)

    def _restore_window_state(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitter = self.settings.value("splitter")
        if splitter:
            self.splitter.restoreState(splitter)
        last_url = self.settings.value("last_url")
        if isinstance(last_url, str) and last_url:
            self.url_input.setText(last_url)

    @staticmethod
    def _history_time(value: str) -> str:
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime("%d.%m %H:%M")
        except ValueError:
            return value[:16]

    @staticmethod
    def _status_text(code: int | None) -> str:
        if code is None:
            return "Request error"
        try:
            return HTTPStatus(code).phrase
        except ValueError:
            return f"HTTP {code}"

    @staticmethod
    def _protocol_text(value: str | None) -> str:
        if not value:
            return "—"
        if value.startswith("HTTP/"):
            return value
        return f"HTTP/{value}"

    @staticmethod
    def _seconds(value: object) -> str:
        try:
            return f"{float(value):.3f} s"
        except (TypeError, ValueError):
            return "—"

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, #root { background: #eef1f5; color: #18223a; }
            QWidget { font-family: "Segoe UI"; font-size: 13px; }
            #brand { font-size: 18px; font-weight: 650; color: #17213a; padding: 2px 8px; }
            #historyPanel, #card, #sideCard { background: #ffffff; border: 1px solid #dde3eb; border-radius: 14px; }
            #inspectorPanel { background: #e2e6eb; border: none; border-radius: 14px; }
            #sectionTitle { color: #536078; font-size: 12px; font-weight: 700; }
            #mutedText { color: #7b879a; }
            #mutedStrong { color: #5d6980; font-weight: 650; }
            QLineEdit, QComboBox, QPlainTextEdit, QTableWidget {
                background: #ffffff; border: 1px solid #d5dce6; border-radius: 9px; padding: 8px; selection-background-color: #e7efff;
            }
            #urlInput { min-height: 34px; font-size: 15px; font-weight: 600; padding-left: 13px; }
            #runButton { background: #2d73e8; color: white; border: none; border-radius: 9px; padding: 10px 18px; font-weight: 700; }
            #runButton:hover { background: #2469db; }
            #runButton:disabled { background: #a9b8d0; }
            #segmented { background: #ffffff; border: 1px solid #d7dee8; border-radius: 9px; }
            QToolButton[segment="true"] { border: none; border-radius: 6px; padding: 7px 10px; color: #4c5870; }
            QToolButton[segment="true"]:checked { background: #eaf1ff; color: #1f4f9e; font-weight: 650; }
            #pillCheck { background: #ffffff; border: 1px solid #d7dee8; border-radius: 9px; padding: 8px 10px; spacing: 7px; }
            QComboBox { min-height: 31px; padding: 2px 28px 2px 9px; }
            QTabWidget::pane { border: none; }
            QTabBar::tab { background: transparent; color: #6b778b; padding: 12px 16px; border-bottom: 2px solid transparent; }
            QTabBar::tab:selected { color: #22314c; border-bottom-color: #2d73e8; font-weight: 650; }
            #statusBadge { background: #e63232; color: white; border-radius: 9px; padding: 10px 14px; font-size: 22px; font-weight: 800; }
            #statusBadge[ok="true"] { background: #2fac63; }
            #statusTitle { font-size: 22px; font-weight: 700; }
            #serverHero { font-size: 16px; font-weight: 650; color: #26344e; }
            #metricValue { font-weight: 650; color: #34435d; }
            #timingValue { font-size: 16px; font-weight: 650; color: #26344e; }
            #historyTree { background: transparent; border: none; outline: none; }
            #historyTree::item { padding: 7px 5px; border-radius: 6px; }
            #historyTree::item:selected { background: #eaf1fd; color: #24324a; }
            #historyTree::branch { background: transparent; }
            #hintStatus { color: #e63232; font-size: 18px; font-weight: 800; }
            #sideStrong { font-weight: 700; color: #25324b; }
            QPushButton { background: #ffffff; border: 1px solid #d5dce6; border-radius: 8px; padding: 8px 12px; }
            QPushButton:hover { background: #f6f8fb; }
            #dangerButton { color: #bf3434; }
            QStatusBar { background: #f7f8fa; border-top: 1px solid #dfe4eb; color: #69758a; }
            QSplitter::handle { background: transparent; width: 6px; }
            QScrollArea { background: transparent; }
            """
        )
