# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false, reportCallIssue=false
"""Main-window widget layout construction.

The layout is kept in a leaf mixin so the state, discovery, and cache
controllers can be composed around it without importing :mod:`gui`.
``WindowCoreMixin`` calls :meth:`_build_window_layout` after initializing the
controller state.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QHeaderView,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
    QToolButton,
    QTextEdit,
)

from front.filter_widgets import CheckFilterButton


class WindowLayoutMixin:
    """Build the widgets and signal wiring owned by ``MainWindow``."""

    def _build_window_layout(self):
        central = QWidget()
        self.setCentralWidget(central)
        self.setAcceptDrops(True)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # --- Top controls row -----------------------------------------------
        controls_container = QWidget()
        self.controls_container = controls_container
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        btn_row_1 = QHBoxLayout()
        btn_row_1.setSpacing(10)

        button_height = 35
        settings_btn = QPushButton("Settings")
        settings_btn.setToolTip("Settings")
        settings_btn.setFixedHeight(35)
        settings_btn.clicked.connect(self._open_settings)
        btn_row_1.addWidget(settings_btn)

        self.open_btn = QToolButton()
        self.open_btn.setObjectName("openBtn")
        self.open_btn.setText("Open ▼")
        self.open_btn.setToolTip("Open model files or scan a folder")
        self.open_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.open_btn.setMenu(self._build_open_menu())
        self.open_btn.setMinimumWidth(130)
        self.open_btn.setFixedHeight(button_height)
        btn_row_1.addWidget(self.open_btn)

        btn_row_1.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_current_operation)
        btn_row_1.addWidget(self.cancel_btn)

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self.progress_label.setWordWrap(False)
        self.progress_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.progress_label.setMinimumHeight(22)
        self.progress_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        btn_row_1.addWidget(self.progress_label, 1)

        self.analyze_btn = QPushButton("Analyze")
        self.analyze_btn.setObjectName("analyzeBtn")
        self.analyze_btn.clicked.connect(self._analyze_all)
        self.analyze_btn.setStyleSheet("font-weight: 800;")
        self.analyze_btn.setMinimumWidth(260)
        self.analyze_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )

        self.progress = QProgressBar()
        self.progress.setFixedSize(260, 28)
        self.progress.setVisible(False)

        self.action_slot = QWidget()
        self.action_slot.setFixedWidth(260)
        action_slot_layout = QVBoxLayout(self.action_slot)
        action_slot_layout.setContentsMargins(0, 0, 0, 0)
        action_slot_layout.setSpacing(0)
        action_slot_layout.addWidget(self.analyze_btn)
        action_slot_layout.addWidget(self.progress)
        btn_row_1.addWidget(self.action_slot)

        controls_layout.addLayout(btn_row_1)
        self._set_idle_status()
        self._update_analyze_slot()

        root.addWidget(controls_container)

        # --- Tab widget (Cards / Data) -------------------------------------
        self.tabs = QTabWidget()

        # Cards tab
        cards_tab = QWidget()
        cards_tab_layout = QVBoxLayout(cards_tab)
        cards_tab_layout.setContentsMargins(0, 0, 0, 0)
        cards_tab_layout.setSpacing(6)

        cards_toolbar = QHBoxLayout()
        self.cards_select_all_cb = QCheckBox("Select All")
        self.cards_select_all_cb.stateChanged.connect(self._on_cards_select_all_changed)
        cards_toolbar.addWidget(self.cards_select_all_cb)
        self.selected_count_label = QLabel("0 selected")
        self.selected_count_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        cards_toolbar.addWidget(self.selected_count_label)
        cards_toolbar.addStretch()
        cards_tab_layout.addLayout(cards_toolbar)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setContentsMargins(8, 8, 8, 8)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cards_scroll.setWidget(self.cards_container)

        self.cards_placeholder = QLabel(
            "No models analyzed yet.\nDrop files anywhere or click Open."
        )
        self.cards_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cards_placeholder.setStyleSheet(
            "color: #45475a; font-size: 14px; padding: 60px;"
        )
        self.cards_layout.insertWidget(0, self.cards_placeholder)

        cards_tab_layout.addWidget(self.cards_scroll)
        self.tabs.addTab(cards_tab, "Cards")

        # Data table tab
        data_tab = QWidget()
        data_tab_layout = QVBoxLayout(data_tab)
        data_tab_layout.setContentsMargins(0, 0, 0, 0)
        data_tab_layout.setSpacing(6)

        data_toolbar = QHBoxLayout()
        self.table_select_all_cb = QCheckBox("Select All")
        self.table_select_all_cb.stateChanged.connect(self._on_table_select_all_changed)
        data_toolbar.addWidget(self.table_select_all_cb)
        self.show_full_path_cb = QCheckBox("Show Full Path")
        self.show_full_path_cb.stateChanged.connect(self._on_show_full_path_changed)
        data_toolbar.addWidget(self.show_full_path_cb)
        self.table_selected_count_label = QLabel("0 selected")
        self.table_selected_count_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        data_toolbar.addWidget(self.table_selected_count_label)
        data_toolbar.addStretch()
        data_tab_layout.addLayout(data_toolbar)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        vertical_header = self.table.verticalHeader()
        assert vertical_header is not None
        vertical_header.setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_table_item_selection_changed)
        self.table.cellClicked.connect(self._on_table_cell_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        horizontal_header = self.table.horizontalHeader()
        assert horizontal_header is not None
        horizontal_header.sortIndicatorChanged.connect(self._on_table_sort_changed)

        self._table_columns = [
            "",
            "File",
            "Format",
            "File Size",
            "Architecture",
            "Model Type",
            "Adapter",
            "Quantization",
            "Precision",
            "UNet Precision",
            "VAE Precision",
            "Text Encoder Precision",
            "Transformer Precision",
            "Parameters",
            "Tensors",
            "LoRA Rank",
            "MoE",
            "Experts",
            "Active Experts",
            "Software",
            "Images",
            "Resolution",
            "Epochs",
            "Steps",
        ]
        self.table.setColumnCount(len(self._table_columns))
        self.table.setHorizontalHeaderLabels(self._table_columns)

        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 34)
        for i in range(1, len(self._table_columns)):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 280)  # File
        self.table.setColumnWidth(2, 70)  # Format
        self.table.setColumnWidth(3, 90)  # File Size
        self.table.setColumnWidth(4, 140)  # Architecture
        self.table.setColumnWidth(5, 100)  # Model Type
        self.table.setColumnWidth(6, 90)  # Adapter
        self.table.setColumnWidth(7, 100)  # Quantization
        self.table.setColumnWidth(8, 100)  # Precision
        self.table.setColumnWidth(9, 115)  # UNet
        self.table.setColumnWidth(10, 115)  # VAE
        self.table.setColumnWidth(11, 160)  # Text Encoder
        self.table.setColumnWidth(12, 120)  # Transformer
        self.table.setColumnWidth(13, 95)  # Parameters
        self.table.setColumnWidth(14, 70)  # Tensors
        self.table.setColumnWidth(15, 85)  # LoRA Rank
        self.table.setColumnWidth(16, 60)  # MoE
        self.table.setColumnWidth(17, 80)  # Experts
        self.table.setColumnWidth(18, 105)  # Active Experts
        self.table.setColumnWidth(19, 150)  # Software
        self.table.setColumnWidth(20, 70)  # Images
        self.table.setColumnWidth(21, 100)  # Resolution
        self.table.setColumnWidth(22, 70)  # Epochs
        self.table.setColumnWidth(23, 80)  # Steps
        self._apply_table_column_visibility()
        data_tab_layout.addWidget(self.table)
        self.tabs.addTab(data_tab, "Data")

        # The Raw tab remains a focused compatible raw-dump view.
        raw_container = QWidget()
        raw_layout = QVBoxLayout(raw_container)
        raw_layout.setContentsMargins(8, 8, 8, 8)
        raw_layout.setSpacing(6)

        # File selector for the compatible raw-dump view
        raw_top = QHBoxLayout()
        raw_top.addWidget(QLabel("Select model:"))
        self.raw_combo = QComboBox()
        self.raw_combo.setMinimumWidth(300)
        self.raw_combo.installEventFilter(self)
        self.raw_combo.currentIndexChanged.connect(self._on_raw_selection_changed)
        raw_top.addWidget(self.raw_combo, stretch=1)
        self.raw_prev_btn = QToolButton()
        self.raw_prev_btn.setText("▲")
        self.raw_prev_btn.setToolTip("Previous model")
        self.raw_prev_btn.clicked.connect(lambda: self._step_raw_selection(-1))
        raw_top.addWidget(self.raw_prev_btn)
        self.raw_next_btn = QToolButton()
        self.raw_next_btn.setText("▼")
        self.raw_next_btn.setToolTip("Next model")
        self.raw_next_btn.clicked.connect(lambda: self._step_raw_selection(1))
        raw_top.addWidget(self.raw_next_btn)
        self.raw_load_btn = QPushButton("Load Full Dump")
        self.raw_load_btn.clicked.connect(self._load_selected_raw_dump)
        raw_top.addWidget(self.raw_load_btn)
        self._update_raw_controls()
        raw_layout.addLayout(raw_top)

        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setStyleSheet(
            "QTextEdit { background-color: #11111b; color: #a6adc8; "
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; "
            "border: 1px solid #313244; border-radius: 4px; padding: 8px; }"
        )
        self.raw_text.setPlaceholderText(
            "Analyze models to see raw tensor key data here."
        )
        raw_layout.addWidget(self.raw_text)

        self.tabs.addTab(raw_container, "Raw")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._apply_default_tab()

        root.addWidget(self.tabs, stretch=1)

        bottom_actions = QHBoxLayout()
        bottom_actions.setSpacing(10)

        self.arch_filter_btn = CheckFilterButton("Architecture")
        self.arch_filter_btn.filter_changed.connect(self._on_arch_filter_changed)
        self.arch_filter_btn.setMinimumHeight(34)
        self.arch_filter_btn.setMinimumWidth(170)
        self.arch_filter_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        bottom_actions.addWidget(self.arch_filter_btn, 1)

        self.tag_filter_btn = CheckFilterButton("Tags")
        self.tag_filter_btn.filter_changed.connect(self._on_tag_filter_changed)
        self.tag_filter_btn.setMinimumHeight(34)
        self.tag_filter_btn.setMinimumWidth(150)
        self.tag_filter_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        bottom_actions.addWidget(self.tag_filter_btn, 1)

        self.format_filter_btn = CheckFilterButton("Format")
        self.format_filter_btn.filter_changed.connect(self._on_format_filter_changed)
        self.format_filter_btn.setMinimumHeight(34)
        self.format_filter_btn.setMinimumWidth(150)
        self.format_filter_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        bottom_actions.addWidget(self.format_filter_btn, 1)
        self._reset_format_filter_items()

        self.selected_action_btn = QPushButton()
        self.selected_action_btn.setEnabled(False)
        self.selected_action_btn.clicked.connect(self._run_selected_action)
        bottom_actions.addWidget(self.selected_action_btn)

        self.selected_action_menu_btn = QToolButton()
        self.selected_action_menu_btn.setText("▼")
        self.selected_action_menu_btn.setToolTip("Selected model actions")
        self.selected_action_menu_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.selected_action_menu_btn.setMenu(self._build_selected_action_menu())
        bottom_actions.addWidget(self.selected_action_menu_btn)

        self.clear_results_btn = QPushButton("Clear All")
        self.clear_results_btn.setObjectName("clearBtn")
        self.clear_results_btn.clicked.connect(self._clear_all)
        bottom_actions.addWidget(self.clear_results_btn)
        self._refresh_selected_action_button()
        root.addLayout(bottom_actions)

        self.copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self.copy_shortcut.activated.connect(self._on_copy_shortcut)
