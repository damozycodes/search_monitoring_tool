from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSpinBox,
                               QTextEdit, QProgressBar, QMessageBox, QGroupBox,
                               QSplitter, QTabWidget, QFrame, QCheckBox)
from PySide6.QtCore import Qt, QTimer, QDateTime, QThread
from PySide6.QtGui import QFont, QTextCursor
import qdarktheme

from core.search_manager import SearchManager
from core.config import Config


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.search_manager = SearchManager()
        self.status_timer = QTimer()
        self.continuous_timer = QTimer()
        self.completed_searches = 0
        self.failed_searches = 0
        self.is_continuous_mode = False
        self.init_ui()
        self.connect_signals()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Google Search Automation - Mass Search Tool")
        self.setGeometry(100, 100, 1400, 900)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel - Controls
        left_panel = self.create_control_panel()
        left_panel.setMaximumWidth(450)
        
        # Right panel - Logs and status
        right_panel = self.create_status_panel()
        
        # Splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([450, 950])
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.statusBar().showMessage("Ready to start searches")
        
        # Setup status update timer
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)  # Update every second
        
        # Setup continuous mode timer
        self.continuous_timer.timeout.connect(self.continuous_mode_cycle)
        
    def create_control_panel(self):
        """Create the left control panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Title
        title = QLabel("Google Search Automation")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Search configuration group
        config_group = QGroupBox("Search Configuration")
        config_layout = QVBoxLayout(config_group)
        
        # Keyword input
        keyword_layout = QHBoxLayout()
        keyword_layout.addWidget(QLabel("Keyword:"))
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("Enter keyword to search...")
        keyword_layout.addWidget(self.keyword_input)
        config_layout.addLayout(keyword_layout)
        
        # Concurrency and max searches
        concurrency_layout = QHBoxLayout()
        concurrency_layout.addWidget(QLabel("Concurrency:"))
        self.concurrency_spinbox = QSpinBox()
        self.concurrency_spinbox.setRange(1, Config.MAX_BROWSERS)
        self.concurrency_spinbox.setValue(Config.CONCURRENT_BROWSERS)
        concurrency_layout.addWidget(self.concurrency_spinbox)

        concurrency_layout.addWidget(QLabel("Max Searches:"))
        self.max_searches_spinbox = QSpinBox()
        self.max_searches_spinbox.setRange(1, 100000)
        self.max_searches_spinbox.setValue(1000)
        self.max_searches_spinbox.setSuffix(" searches")
        concurrency_layout.addWidget(self.max_searches_spinbox)
        config_layout.addLayout(concurrency_layout)
        
        # Info label
        info_label = QLabel("Concurrency = Number of simultaneous browsers\nMax Searches = Total searches to perform before continuous mode interval")
        info_label.setFont(QFont("Arial", 8))
        info_label.setStyleSheet("color: #888;")
        config_layout.addWidget(info_label)
        
        # Proxy status
        proxy_status_layout = QHBoxLayout()
        proxy_status_layout.addWidget(QLabel("Integrated Proxies:"))
        self.proxy_status_label = QLabel(f"{len(Config.HARDCODED_PROXIES)} available")
        proxy_status_layout.addWidget(self.proxy_status_label)
        proxy_status_layout.addStretch()
        config_layout.addLayout(proxy_status_layout)
        
        # Debug mode checkbox
        debug_layout = QHBoxLayout()
        self.debug_checkbox = QCheckBox("Debug Mode (Show Browser)")
        self.debug_checkbox.setChecked(not Config.HEADLESS)
        debug_layout.addWidget(self.debug_checkbox)
        config_layout.addLayout(debug_layout)
        
        # CAPTCHA settings
        captcha_layout = QHBoxLayout()
        self.captcha_checkbox = QCheckBox("Enable CAPTCHA Solving")
        self.captcha_checkbox.setChecked(Config.CAPTCHA_SOLVE_ENABLED)
        captcha_layout.addWidget(self.captcha_checkbox)

        self.captcha_retry_spinbox = QSpinBox()
        self.captcha_retry_spinbox.setRange(1, 10)
        self.captcha_retry_spinbox.setValue(Config.CAPTCHA_MAX_RETRIES)
        self.captcha_retry_spinbox.setPrefix("Max Retries: ")
        captcha_layout.addWidget(self.captcha_retry_spinbox)
        config_layout.addLayout(captcha_layout)
        
        # Audio CAPTCHA settings
        audio_captcha_layout = QHBoxLayout()
        self.audio_captcha_checkbox = QCheckBox("Enable Audio CAPTCHA Solving")
        self.audio_captcha_checkbox.setChecked(Config.AUDIO_CAPTCHA_ENABLED)
        audio_captcha_layout.addWidget(self.audio_captcha_checkbox)
        config_layout.addLayout(audio_captcha_layout)
        
        # Control buttons
        button_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Searches")
        self.stop_btn = QPushButton("Stop Searches")
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        config_layout.addLayout(button_layout)
        
        layout.addWidget(config_group)
        
        # Statistics group
        # Statistics group
        stats_group = QGroupBox("Search Statistics")
        stats_layout = QVBoxLayout(stats_group)

        # Stats labels
        self.completed_label = QLabel("Completed: 0")
        self.successful_label = QLabel("Successful: 0")
        self.failed_label = QLabel("Failed: 0")
        self.target_found_label = QLabel("Target Found: 0")
        self.active_label = QLabel("Active: 0")
        self.success_rate_label = QLabel("Success Rate: 0%")
        self.target_rate_label = QLabel("Target Found Rate: 0%")
        self.cycle_label = QLabel("Cycle: 0")
        self.remaining_label = QLabel("Remaining: 0")

        stats_layout.addWidget(self.completed_label)
        stats_layout.addWidget(self.successful_label)
        stats_layout.addWidget(self.failed_label)
        stats_layout.addWidget(self.target_found_label)
        stats_layout.addWidget(self.active_label)
        stats_layout.addWidget(self.success_rate_label)
        stats_layout.addWidget(self.target_rate_label)
        stats_layout.addWidget(self.cycle_label)
        stats_layout.addWidget(self.remaining_label)

        layout.addWidget(stats_group)
        
        layout.addStretch()
        
        return panel
        
    def create_status_panel(self):
        """Create the right status and log panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Create tab widget
        tab_widget = QTabWidget()
        
        # Log tab
        log_tab = self.create_log_tab()
        tab_widget.addTab(log_tab, "Logs")
        
        # Continuous Mode tab
        continuous_tab = self.create_continuous_tab()
        tab_widget.addTab(continuous_tab, "Continuous Mode")
        
        layout.addWidget(tab_widget)
        
        return panel

    def create_log_tab(self):
        """Create the logs tab"""
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        
        log_label = QLabel("Search Logs")
        log_label.setFont(QFont("Arial", 12, QFont.Bold))
        log_layout.addWidget(log_label)
        
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Courier", 9))
        log_layout.addWidget(self.log_display)
        
        # Modern progress bar with style
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid grey;
                border-radius: 5px;
                text-align: center;
                background-color: #2b2b2b;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        log_layout.addWidget(self.progress_bar)
        
        return log_tab

    def create_continuous_tab(self):
        """Create the Continuous Mode tab"""
        continuous_tab = QWidget()
        layout = QVBoxLayout(continuous_tab)
        
        # Continuous Mode settings group
        continuous_group = QGroupBox("Continuous Mode Settings")
        continuous_layout = QVBoxLayout(continuous_group)
        
        # Enable continuous mode
        enable_layout = QHBoxLayout()
        self.continuous_checkbox = QCheckBox("Enable Continuous Mode")
        self.continuous_checkbox.setChecked(False)
        enable_layout.addWidget(self.continuous_checkbox)
        continuous_layout.addLayout(enable_layout)
        
        # Rescan interval
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("Rescan Interval:"))
        self.rescan_interval = QSpinBox()
        self.rescan_interval.setRange(1, 1440)  # Up to 24 hours
        self.rescan_interval.setValue(Config.DEFAULT_RESCAN_INTERVAL)
        self.rescan_interval.setSuffix(" minutes")
        interval_layout.addWidget(self.rescan_interval)
        interval_layout.addStretch()
        continuous_layout.addLayout(interval_layout)
        
        # Manual control
        manual_layout = QHBoxLayout()
        self.manual_cycle_btn = QPushButton("Manual Cycle Now")
        self.manual_cycle_btn.clicked.connect(self.manual_continuous_cycle)
        manual_layout.addWidget(self.manual_cycle_btn)
        continuous_layout.addLayout(manual_layout)
        
        layout.addWidget(continuous_group)
        
        # Continuous Mode status
        status_group = QGroupBox("Continuous Mode Status")
        status_layout = QVBoxLayout(status_group)
        
        self.continuous_status_label = QLabel("Status: Inactive")
        self.next_cycle_label = QLabel("Next Cycle: N/A")
        self.continuous_cycles_label = QLabel("Completed Cycles: 0")
        
        status_layout.addWidget(self.continuous_status_label)
        status_layout.addWidget(self.next_cycle_label)
        status_layout.addWidget(self.continuous_cycles_label)
        
        layout.addWidget(status_group)
        layout.addStretch()
        
        return continuous_tab
        
    def connect_signals(self):
        """Connect signals and slots"""
        # Button connections
        self.start_btn.clicked.connect(self.start_searches)
        self.stop_btn.clicked.connect(self.stop_searches)
        
        # Continuous mode checkbox
        self.continuous_checkbox.stateChanged.connect(self.on_continuous_mode_changed)
        
        # CAPTCHA checkbox
        self.captcha_checkbox.stateChanged.connect(self.on_captcha_mode_changed)
        
        # Audio CAPTCHA checkbox
        self.audio_captcha_checkbox.stateChanged.connect(self.on_audio_captcha_mode_changed)
        
        # Debug mode checkbox
        self.debug_checkbox.stateChanged.connect(self.on_debug_mode_changed)
        
        # Search manager signals
        self.search_manager.signals.stats_updated.connect(self.on_stats_updated)
        self.search_manager.signals.search_started.connect(self.on_search_started)
        self.search_manager.signals.search_completed.connect(self.on_search_completed)
        self.search_manager.signals.search_failed.connect(self.on_search_failed)
        self.search_manager.signals.log_message.connect(self.on_log_message)
        self.search_manager.signals.all_searches_completed.connect(self.on_all_searches_completed)
        
        # Update status
        self.update_status()

    def manual_continuous_cycle(self):
        """Manually trigger a continuous mode cycle"""
        if self.is_continuous_mode:
            self.log_message("Manual continuous mode cycle triggered")
            self.continuous_mode_cycle()

    def on_debug_mode_changed(self, state):
        """Handle debug mode checkbox change"""
        Config.HEADLESS = (state != Qt.Checked)
        Config.save_settings()
        self.search_manager.debug_mode = (state == Qt.Checked)
        if state == Qt.Checked:
            self.log_message("Debug mode enabled - browsers will be visible")
        else:
            self.log_message("Debug mode disabled - browsers will run in headless mode")

    def on_captcha_mode_changed(self, state):
        """Handle CAPTCHA mode checkbox change"""
        Config.CAPTCHA_SOLVE_ENABLED = (state == Qt.Checked)
        Config.save_settings()
        if Config.CAPTCHA_SOLVE_ENABLED:
            self.log_message("CAPTCHA solving enabled")
        else:
            self.log_message("CAPTCHA solving disabled")

    def on_audio_captcha_mode_changed(self, state):
        """Handle audio CAPTCHA mode checkbox change"""
        Config.AUDIO_CAPTCHA_ENABLED = (state == Qt.Checked)
        Config.save_settings()
        if Config.AUDIO_CAPTCHA_ENABLED:
            self.log_message("Audio CAPTCHA solving enabled")
        else:
            self.log_message("Audio CAPTCHA solving disabled")

    def on_continuous_mode_changed(self, state):
        """Handle continuous mode checkbox change"""
        self.is_continuous_mode = (state == Qt.Checked)
        if self.is_continuous_mode:
            # Start the continuous timer
            interval_minutes = self.rescan_interval.value()
            self.continuous_timer.start(interval_minutes * 60 * 1000)  # Convert to milliseconds
            self.continuous_status_label.setText("Status: Active")
            next_cycle = QDateTime.currentDateTime().addSecs(interval_minutes * 60)
            self.next_cycle_label.setText(f"Next Cycle: {next_cycle.toString('hh:mm:ss')}")
            self.log_message(f"Continuous mode enabled - will rescan every {interval_minutes} minutes")
        else:
            self.continuous_timer.stop()
            self.continuous_status_label.setText("Status: Inactive")
            self.next_cycle_label.setText("Next Cycle: N/A")
            self.log_message("Continuous mode disabled - timer stopped")

    def on_all_searches_completed(self):
        """Handle when all searches are completed"""
        self.log_message(f"Completed {self.search_manager.completed_searches} searches. Waiting for continuous mode interval...")
        if self.is_continuous_mode:
            # Update cycle counter
            self.search_manager.cycle_count += 1
            self.continuous_cycles_label.setText(f"Completed Cycles: {self.search_manager.cycle_count}")
            
            # Reset counters for next cycle
            self.search_manager.completed_searches = 0
            self.search_manager.failed_searches = 0
            self.search_manager.successful_searches = 0
            self.update_stats()

    def continuous_mode_cycle(self):
        """Execute one cycle of continuous mode: stop and restart searches"""
        if not self.is_continuous_mode:
            return
            
        self.log_message("=== CONTINUOUS MODE CYCLE STARTED ===")
        
        # Stop current searches
        self.search_manager.stop_searches()
        self.log_message("Stopped current searches for refresh")
        
        # Update cycle counter
        self.search_manager.cycle_count += 1
        self.continuous_cycles_label.setText(f"Completed Cycles: {self.search_manager.cycle_count}")
        
        # Small delay before restarting
        QTimer.singleShot(2000, self.restart_searches_continuous)

    def start_searches(self):
        """Start the mass search operation"""
        keyword = self.keyword_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "Input Error", "Please enter a keyword to search.")
            return
            
        concurrency = self.concurrency_spinbox.value()
        max_searches = self.max_searches_spinbox.value()
        
        # Save concurrency setting
        Config.CONCURRENT_BROWSERS = concurrency
        Config.save_settings()
        
        # Update CAPTCHA settings
        Config.CAPTCHA_SOLVE_ENABLED = self.captcha_checkbox.isChecked()
        Config.CAPTCHA_MAX_RETRIES = self.captcha_retry_spinbox.value()
        Config.AUDIO_CAPTCHA_ENABLED = self.audio_captcha_checkbox.isChecked()
        Config.save_settings()
        
        # Update debug mode
        self.search_manager.debug_mode = self.debug_checkbox.isChecked()
        
        # Update UI
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, max_searches)
        self.progress_bar.setValue(0)
        
        # Start searches
        self.search_manager.start_searches(keyword, concurrency, max_searches)
        self.log_message(f"Started searches for keyword: '{keyword}'")
        self.log_message(f"Concurrency: {concurrency}, Max Searches: {max_searches}")
        self.log_message(f"Using {len(Config.HARDCODED_PROXIES)} integrated proxies")
        self.log_message(f"CAPTCHA solving: {'Enabled' if Config.CAPTCHA_SOLVE_ENABLED else 'Disabled'}")
        self.log_message(f"Audio CAPTCHA solving: {'Enabled' if Config.AUDIO_CAPTCHA_ENABLED else 'Disabled'}")
        
        # Start continuous timer if enabled
        if self.continuous_checkbox.isChecked():
            interval_minutes = self.rescan_interval.value()
            self.continuous_timer.start(interval_minutes * 60 * 1000)
            self.log_message(f"Continuous mode active - next rescan in {interval_minutes} minutes")
        
    def stop_searches(self):
        """Stop all search operations"""
        self.search_manager.stop_searches()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.continuous_timer.stop()
        if self.is_continuous_mode:
            self.continuous_status_label.setText("Status: Paused")
        self.log_message("Search sessions stopped")
        
    def on_search_started(self, browser_id: int, proxy: str):
        """Handle search started signal"""
        self.log_message(f"Browser {browser_id}: Started")
        
    def on_search_completed(self, browser_id: int, status: str):
        """Handle search completed signal"""
        self.progress_bar.setValue(self.search_manager.completed_searches)
        self.update_stats()
        
    def on_search_failed(self, browser_id: int, error: str):
        """Handle search failed signal"""
        self.progress_bar.setValue(self.search_manager.completed_searches)
        self.log_message(f"Browser {browser_id}: FAILED - {error}")
        self.update_stats()
        
    def on_log_message(self, message: str):
        """Handle log message from search manager"""
        self.log_message(message)
        
    def log_message(self, message: str):
        """Add a timestamped message to the log display"""
        timestamp = QDateTime.currentDateTime().toString("hh:mm:ss")
        self.log_display.append(f"[{timestamp}] {message}")
        
        # Auto-scroll to bottom
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_display.setTextCursor(cursor)
        
    def update_stats(self):
        """Update statistics display"""
        stats = self.search_manager.get_status()
        
        self.completed_label.setText(f"Completed: {stats['completed_searches']}")
        self.successful_label.setText(f"Successful: {stats['successful_searches']}")
        self.failed_label.setText(f"Failed: {stats['failed_searches']}")
        self.target_found_label.setText(f"Target Found: {stats['target_found_searches']}")
        self.active_label.setText(f"Active: {stats['active_browsers']}/{stats['max_active_browsers']}")
        self.success_rate_label.setText(f"Success Rate: {stats['success_rate']:.1f}%")
        self.target_rate_label.setText(f"Target Found Rate: {stats['target_found_rate']:.1f}%")
        self.cycle_label.setText(f"Cycle: {stats['cycle_count']}")
        self.remaining_label.setText(f"Remaining: {stats['remaining_searches']}")
        
    def update_status(self):
        """Update status bar and UI elements"""
        status = self.search_manager.get_status()
        
        if status["is_running"]:
            self.statusBar().showMessage(
                f"Searching: {status['current_keyword']} | "
                f"Active: {status['active_browsers']}/{status['max_active_browsers']} | "
                f"Completed: {status['completed_searches']}/{status['max_searches']} | "
                f"Cycle: {status['cycle_count']}"
            )
        else:
            self.statusBar().showMessage("Ready")
            
    def on_stats_updated(self, stats: dict):
        """Handle stats update from search manager"""
        self.update_stats()

    def restart_searches_continuous(self):
        """Restart searches after refresh in continuous mode"""
        if self.is_continuous_mode and not self.search_manager.is_running:
            keyword = self.keyword_input.text().strip()
            concurrency = self.concurrency_spinbox.value()
            max_searches = self.max_searches_spinbox.value()
            
            if keyword:
                self.log_message("Continuous mode: Restarting searches...")
                self.search_manager.start_searches(keyword, concurrency, max_searches)
                # Update next cycle time
                if self.is_continuous_mode:
                    interval_minutes = self.rescan_interval.value()
                    next_cycle = QDateTime.currentDateTime().addSecs(interval_minutes * 60)
                    self.next_cycle_label.setText(f"Next Cycle: {next_cycle.toString('hh:mm:ss')}")