#!/usr/bin/env python3
"""
Electronic Nose GUI - v7 Professional Dashboard Theme
- Clean, professional dashboard design
- Optimized layout and spacing
- Enhanced visual hierarchy
- FIXED: Edge Impulse upload with JSON format (Status 422 fix)
"""

import sys
import time
import os
import csv
import json
import socket
import requests
from datetime import datetime
from collections import deque
from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtWidgets import QMessageBox, QProgressDialog
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QFont, QLinearGradient, QColor, QPalette
import pyqtgraph as pg

# ===== EDGE IMPULSE CONFIGURATION =====
EI_API_URL = "https://ingestion.edgeimpulse.com"
EI_API_KEY = "ei_4ab099b49f2becd6bb6ce8b3ab59de6c83b6ee70a451aaca"
EI_PROJECT_ID = "821850"

# ===== BACKEND CONFIGURATION =====
TCP_DATA_HOST = "127.0.0.1"
TCP_DATA_PORT = 8083
TCP_CMD_HOST = "127.0.0.1"
TCP_CMD_PORT = 8082

# ===== PROFESSIONAL COLOR SCHEME =====
COLORS = {
    # Background colors
    "bg_primary": "#f8fafc",
    "bg_secondary": "#ffffff",
    "bg_sidebar": "#1e293b",
    "bg_card": "#ffffff",
    
    # Primary colors
    "primary": "#3b82f6",
    "primary_dark": "#1d4ed8",
    "primary_light": "#dbeafe",
    
    # Status colors
    "success": "#10b981",
    "success_light": "#ecfdf5",
    "danger": "#ef4444",
    "danger_light": "#fef2f2",
    "warning": "#f59e0b",
    "warning_light": "#fffbeb",
    "info": "#06b6d4",
    "info_light": "#ecfeff",
    
    # Text colors
    "text_primary": "#1e293b",
    "text_secondary": "#64748b",
    "text_light": "#94a3b8",
    "text_white": "#ffffff",
    
    # Border and accents
    "border": "#e2e8f0",
    "border_light": "#f1f5f9",
    "shadow": "rgba(0, 0, 0, 0.08)",
}

# ===== SENSOR COLORS (Professional palette) =====
SENSOR_COLORS = {
    "co_m": "#ef4444",      # Red
    "eth_m": "#10b981",     # Green
    "voc_m": "#8b5cf6",     # Violet
    "no2": "#f59e0b",       # Amber
    "c2h50h_gm": "#06b6d4", # Cyan
    "voc_gm": "#f97316",    # Orange
    "co_gm": "#3b82f6",     # Blue
}

# ===== TCP RECEIVER THREAD =====
class TCPReceiver(QObject):
    data_received = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    
    def run(self):
        try:
            self.status_changed.emit(f"📡 Connecting to Rust: {TCP_DATA_HOST}:{TCP_DATA_PORT}...")
            
            while True:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.connect((TCP_DATA_HOST, TCP_DATA_PORT))
                    self.status_changed.emit(f"🟢 Connected to Rust: {TCP_DATA_HOST}:{TCP_DATA_PORT}")
                    
                    with sock.makefile('r') as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("SENSOR:"):
                                self.data_received.emit(line)
                except ConnectionRefusedError:
                    self.status_changed.emit(f"⚠️ Cannot connect to Rust. Make sure backend is running on {TCP_DATA_HOST}:{TCP_DATA_PORT}")
                    time.sleep(2)
                except Exception as e:
                    self.status_changed.emit(f"⚠️ Connection error: {e}")
                    time.sleep(2)
        except Exception as e:
            self.status_changed.emit(f"❌ TCP Error: {e}")

# ===== PARSE SENSOR DATA =====
def parse_sensor_data(line: str) -> dict:
    if not line.startswith("SENSOR:"):
        return None
    
    try:
        data_str = line[7:]
        parts = data_str.split(',')
        
        if len(parts) < 9:
            return None
        
        def parse_f(s):
            try:
                return float(s.strip())
            except:
                return 0.0
        
        def parse_i(s):
            try:
                return int(s.strip())
            except:
                return 0
        
        data = {
            "no2": parse_f(parts[0]),
            "eth_gm": parse_f(parts[1]),
            "voc_gm": parse_f(parts[2]),
            "co_gm": parse_f(parts[3]),
            "co_m": parse_f(parts[4]),
            "eth_m": parse_f(parts[5]),
            "voc_m": parse_f(parts[6]),
            "state": parse_i(parts[7]),
            "level": parse_i(parts[8]),
            "timestamp": int(time.time() * 1000),
        }
        
        data["c2h50h_gm"] = data["eth_gm"]
        return data
    except:
        return None

# ===== EDGE IMPULSE UPLOADER WORKER (FIXED - MULTIPART CSV UPLOAD) =====
class EdgeImpulseUploader(QObject):
    upload_progress = pyqtSignal(str)
    upload_finished = pyqtSignal(bool, str)
    
    def upload_csv(self, csv_file: str, label: str, sample_name: str):
        """
        Upload CSV ke Edge Impulse via Ingestion API (multipart/form-data)
        FIXED: 404 Error - Gunakan ingestion.edgeimpulse.com + label sebagai query param
        """
        try:
            self.upload_progress.emit(f"📖 Reading CSV: {os.path.basename(csv_file)}")
            
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
            if not rows:
                self.upload_finished.emit(False, "❌ CSV file is empty!")
                return
            
            self.upload_progress.emit(f"🔄 Preparing upload ({len(rows)} samples)...")
            
            # FIXED: URL base + endpoint benar (tanpa double path)
            upload_url = f"{EI_API_URL}/api/training/files"
            
            headers = {
                "x-api-key": EI_API_KEY,
                "x-label": label,
                # Content-Type diatur otomatis oleh requests saat pakai 'files'
            }
            
            # Siapkan file untuk multipart
            file_name = f"{sample_name}.csv"
            with open(csv_file, 'rb') as f:
                files = {
                    "data": (file_name, f, "text/csv")
                }
                
                self.upload_progress.emit(f"📤 Uploading to Edge Impulse...")
                
                print(f"\n🔧 Upload Details (FIXED):")
                print(f"   URL: {upload_url}")
                print(f"   Label: {label}")
                print(f"   File: {file_name}")
                print(f"   Samples: {len(rows)}")
                print(f"   Content-Type: multipart/form-data")
                print(f"   Headers: {headers}\n")
                
                response = requests.post(
                    upload_url,
                    headers=headers,
                    files=files,
                    timeout=60  # Naikkan timeout untuk file besar
                )
            
            print(f"   Status Code: {response.status_code}")
            print(f"   Response: {response.text[:300]}\n")
            
            if response.status_code in (200, 201):
                # Parse response (biasanya JSON dengan 'success': true)
                try:
                    resp_json = response.json()
                    if resp_json.get("success", False):
                        self.upload_progress.emit("✅ Upload successful!")
                        message = f"✅ Successfully uploaded to Edge Impulse!\n\n"
                        message += f"📊 Samples: {len(rows)}\n"
                        message += f"🏷️  Label: {label}\n"
                        message += f"📁 Sample Name: {sample_name}\n"
                        message += f"📋 Format: CSV (Status {response.status_code})\n"
                        message += f"\n📍 View in Edge Impulse:\n"
                        message += f"https://studio.edgeimpulse.com/studio/{EI_PROJECT_ID}/data-acquisition"
                        self.upload_finished.emit(True, message)
                        return
                    else:
                        error_msg = resp_json.get("message", "Upload failed internally")
                except:
                    error_msg = "Response not JSON, but status OK"
                
                self.upload_finished.emit(False, f"❌ API success but error: {error_msg}")
            else:
                error_msg = response.text
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", error_msg)
                except:
                    pass
                
                self.upload_finished.emit(False, f"❌ Upload failed (Status {response.status_code}):\n{error_msg}")
        
        except FileNotFoundError:
            self.upload_finished.emit(False, f"❌ File not found: {csv_file}")
        except requests.exceptions.Timeout:
            self.upload_finished.emit(False, "❌ Upload timeout - Edge Impulse server lambat")
        except requests.exceptions.ConnectionError:
            self.upload_finished.emit(False, "❌ Cannot connect - check internet & API key")
        except Exception as e:
            self.upload_finished.emit(False, f"❌ Error: {str(e)}")

# ===== CUSTOM STATS CARD WIDGET =====
class StatsCard(QtWidgets.QFrame):
    def __init__(self, title, value, subtitle, color, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['bg_card']};
                border-radius: 12px;
                border: 1px solid {COLORS['border']};
            }}
        """)
        self.setFixedHeight(120)
        
        # Subtle shadow effect
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 15))
        self.setGraphicsEffect(shadow)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(20, 16, 20, 16)
        
        # Title
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        """)
        layout.addWidget(title_label)
        
        # Value
        self.value_label = QtWidgets.QLabel(value)
        self.value_label.setStyleSheet(f"""
            color: {color};
            font-size: 28px;
            font-weight: 700;
        """)
        layout.addWidget(self.value_label)
        
        # Subtitle
        subtitle_label = QtWidgets.QLabel(subtitle)
        subtitle_label.setStyleSheet(f"""
            color: {COLORS['text_light']};
            font-size: 11px;
            font-weight: 500;
        """)
        layout.addWidget(subtitle_label)
    
    def update_value(self, value):
        self.value_label.setText(value)

# ===== MAIN WINDOW =====
class MainWindow(QtWidgets.QMainWindow):
    data_signal = pyqtSignal(dict)
    status_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Electronic Nose System - Kelompok 5 SPS")
        self.resize(1800, 1000)
        
        # Set clean background
        self.setStyleSheet(f"background: {COLORS['bg_primary']};")
        
        self.buffers = {
            "co_m": [], "eth_m": [], "voc_m": [], "no2": [],
            "c2h50h_gm": [], "voc_gm": [], "co_gm": []
        }
        self.maxlen = 200
        self.csv_rows = []
        self.sample_count = 0

        # Main container
        main_container = QtWidgets.QWidget()
        self.setCentralWidget(main_container)
        
        main_layout = QtWidgets.QHBoxLayout(main_container)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Sidebar
        sidebar = self.create_sidebar()
        main_layout.addWidget(sidebar)
        
        # Main content area
        content_container = QtWidgets.QWidget()
        content_container.setStyleSheet(f"background: {COLORS['bg_primary']};")
        content_layout = QtWidgets.QVBoxLayout(content_container)
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = self.create_header()
        content_layout.addWidget(header)
        
        # Stats cards
        stats_section = self.create_stats_section()
        content_layout.addWidget(stats_section)
        
        # Charts area
        charts_container = QtWidgets.QWidget()
        charts_layout = QtWidgets.QVBoxLayout(charts_container)
        charts_layout.setContentsMargins(24, 0, 24, 24)
        charts_layout.setSpacing(0)
        
        # Tabs for different views
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet(self.get_tab_stylesheet())
        self.tabs.addTab(self.create_grid_charts(), "Grid View")
        self.tabs.addTab(self.create_combined_chart(), "Combined View")
        
        charts_layout.addWidget(self.tabs)
        content_layout.addWidget(charts_container, 1)
        
        main_layout.addWidget(content_container, 1)

        # Signals
        self.data_signal.connect(self.on_data_update)
        self.status_signal.connect(self.on_status_update)

        # TCP Receiver
        self.receiver = TCPReceiver()
        self.receiver_thread = QThread()
        self.receiver.moveToThread(self.receiver_thread)
        self.receiver_thread.started.connect(self.receiver.run)
        self.receiver.data_received.connect(self.handle_sensor_data)
        self.receiver.status_changed.connect(self.status_signal.emit)
        self.receiver_thread.start()

        # Update timer
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(80)

    def create_sidebar(self):
        """Create professional sidebar"""
        sidebar = QtWidgets.QWidget()
        sidebar.setFixedWidth(280)
        sidebar.setStyleSheet(f"""
            QWidget {{
                background: {COLORS['bg_sidebar']};
                color: {COLORS['text_white']};
            }}
        """)
        
        layout = QtWidgets.QVBoxLayout(sidebar)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Logo section
        logo_container = QtWidgets.QWidget()
        logo_container.setFixedHeight(120)
        logo_container.setStyleSheet(f"background: {COLORS['primary_dark']};")
        logo_layout = QtWidgets.QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(20, 20, 20, 20)
        
        logo_title = QtWidgets.QLabel("E-Nose System")
        logo_title.setStyleSheet(f"""
            font-size: 18px;
            font-weight: 700;
            color: white;
        """)
        logo_layout.addWidget(logo_title)
        
        logo_subtitle = QtWidgets.QLabel("Kelompok 5 SPS")
        logo_subtitle.setStyleSheet(f"""
            font-size: 12px;
            color: rgba(255, 255, 255, 0.8);
            font-weight: 500;
        """)
        logo_layout.addWidget(logo_subtitle)
        
        layout.addWidget(logo_container)
        
        # Control panel in sidebar
        control_panel = self.create_control_panel()
        layout.addWidget(control_panel)
        
        return sidebar

    def create_header(self):
        """Create clean header"""
        header = QtWidgets.QWidget()
        header.setFixedHeight(70)
        header.setStyleSheet(f"""
            QWidget {{
                background: {COLORS['bg_secondary']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        
        layout = QtWidgets.QHBoxLayout(header)
        layout.setContentsMargins(24, 0, 24, 0)
        
        # Page title
        title = QtWidgets.QLabel("Real-time Sensor Monitoring")
        title.setStyleSheet(f"""
            font-size: 20px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """)
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Status indicator
        self.status_label = QtWidgets.QLabel("Initializing...")
        self.status_label.setStyleSheet(f"""
            font-size: 12px;
            font-weight: 500;
            color: {COLORS['text_secondary']};
            padding: 8px 16px;
            background: {COLORS['bg_primary']};
            border-radius: 6px;
        """)
        layout.addWidget(self.status_label)
        
        return header

    def create_stats_section(self):
        """Create compact stats section"""
        container = QtWidgets.QWidget()
        container.setFixedHeight(120)
        container.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        
        layout = QtWidgets.QHBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 16, 24, 16)
        
        # Stats cards
        self.samples_card = StatsCard(
            "Total Samples",
            "0",
            "Data points collected",
            COLORS['primary']
        )
        layout.addWidget(self.samples_card)
        
        self.status_card = StatsCard(
            "Connection Status",
            "●",
            "Connecting...",
            COLORS['warning']
        )
        layout.addWidget(self.status_card)
        
        self.motor_card = StatsCard(
            "Motor State",
            "IDLE",
            "Current operation",
            COLORS['info']
        )
        layout.addWidget(self.motor_card)
        
        self.save_card = StatsCard(
            "Save Status",
            "⏳",
            "Waiting for data",
            COLORS['text_light']
        )
        layout.addWidget(self.save_card)
        
        return container

    def create_control_panel(self):
        """Create control panel for sidebar"""
        container = QtWidgets.QWidget()
        container.setStyleSheet(f"background: transparent;")
        
        layout = QtWidgets.QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QtWidgets.QLabel("CONTROL PANEL")
        title.setStyleSheet(f"""
            color: rgba(255, 255, 255, 0.7);
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
        """)
        layout.addWidget(title)
        
        # Sample Name
        sample_label = QtWidgets.QLabel("Sample Name")
        sample_label.setStyleSheet(f"""
            color: rgba(255, 255, 255, 0.9);
            font-size: 12px;
            font-weight: 500;
        """)
        layout.addWidget(sample_label)
        
        self.sample_name = self.create_sidebar_input("e.g., contohSample_001")
        layout.addWidget(self.sample_name)
        
        # EI Label
        ei_label_text = QtWidgets.QLabel("Edge Impulse Label")
        ei_label_text.setStyleSheet(f"""
            color: rgba(255, 255, 255, 0.9);
            font-size: 12px;
            font-weight: 500;
        """)
        layout.addWidget(ei_label_text)
        
        self.ei_label = self.create_sidebar_input("e.g., contohLabel")
        layout.addWidget(self.ei_label)
        
        layout.addSpacing(10)
        
        # Buttons
        self.btn_start = self.create_sidebar_button(
            "▶ Start Sampling",
            COLORS['success']
        )
        self.btn_start.clicked.connect(self.start_sampling)
        layout.addWidget(self.btn_start)
        
        self.btn_stop = self.create_sidebar_button(
            "⏹ Stop Sampling",
            COLORS['danger']
        )
        self.btn_stop.clicked.connect(self.stop_sampling)
        layout.addWidget(self.btn_stop)
        
        self.btn_save = self.create_sidebar_button(
            "💾 Save & Upload",
            COLORS['primary']
        )
        self.btn_save.clicked.connect(self.save_all_and_upload)
        layout.addWidget(self.btn_save)
        
        self.btn_clear = self.create_sidebar_button(
            "🗑 Clear Data",
            COLORS['warning']
        )
        self.btn_clear.clicked.connect(self.clear_data)
        layout.addWidget(self.btn_clear)
        
        layout.addStretch()
        
        return container

    def create_sidebar_input(self, placeholder):
        """Create input field for sidebar"""
        input_field = QtWidgets.QLineEdit()
        input_field.setPlaceholderText(placeholder)
        input_field.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                padding: 10px 12px;
                font-size: 12px;
                color: white;
                font-weight: 500;
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['primary']};
                background: rgba(255, 255, 255, 0.15);
            }}
            QLineEdit::placeholder {{
                color: rgba(255, 255, 255, 0.5);
            }}
        """)
        input_field.setMinimumHeight(38)
        return input_field

    def create_sidebar_button(self, text, color):
        """Create button for sidebar"""
        btn = QtWidgets.QPushButton(text)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {color};
                opacity: 0.9;
            }}
            QPushButton:pressed {{
                background: {color};
                opacity: 0.8;
            }}
        """)
        btn.setMinimumHeight(42)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def get_tab_stylesheet(self):
        return f"""
            QTabWidget::pane {{
                border: none;
                background: transparent;
            }}
            
            QTabBar::tab {{
                background: {COLORS['bg_secondary']};
                color: {COLORS['text_secondary']};
                padding: 12px 24px;
                margin-right: 4px;
                font-weight: 500;
                font-size: 13px;
                border: none;
                border-radius: 6px 6px 0px 0px;
            }}
            
            QTabBar::tab:selected {{
                background: {COLORS['bg_card']};
                color: {COLORS['primary']};
                font-weight: 600;
            }}
            
            QTabBar::tab:hover:!selected {{
                background: {COLORS['bg_primary']};
                color: {COLORS['text_primary']};
            }}
        """

    def create_grid_charts(self):
        """Create grid layout for individual sensor charts"""
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: {COLORS['border_light']};
                width: 10px;
                border-radius: 5px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['text_light']};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {COLORS['text_secondary']};
            }}
        """)
        
        content = QtWidgets.QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QtWidgets.QGridLayout(content)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 8, 0)

        # Create sensor charts in grid
        sensors = [
            ("co_m", "CO (MICS)", SENSOR_COLORS["co_m"]),
            ("eth_m", "Ethanol (MICS)", SENSOR_COLORS["eth_m"]),
            ("voc_m", "VOC (MICS)", SENSOR_COLORS["voc_m"]),
            ("no2", "NO₂ (GM)", SENSOR_COLORS["no2"]),
            ("c2h50h_gm", "C₂H₅OH (GM)", SENSOR_COLORS["c2h50h_gm"]),
            ("voc_gm", "VOC (GM)", SENSOR_COLORS["voc_gm"]),
            ("co_gm", "CO (GM)", SENSOR_COLORS["co_gm"])
        ]
        
        row, col = 0, 0
        for key, title, color in sensors:
            chart_widget = self.create_sensor_chart(key, title, color)
            chart_widget.setMinimumHeight(240)
            layout.addWidget(chart_widget, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1
        
        # Add stretch to push content up
        layout.setRowStretch(row + 1, 1)
        
        scroll_area.setWidget(content)
        return scroll_area

    def create_sensor_chart(self, key, title, color):
        """Create individual sensor chart with professional styling"""
        container = QtWidgets.QWidget()
        container.setStyleSheet(f"""
            background: {COLORS['bg_card']};
            border-radius: 8px;
            border: 1px solid {COLORS['border']};
        """)
        
        # Subtle shadow
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 10))
        container.setGraphicsEffect(shadow)
        
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Title
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 14px;
            font-weight: 600;
        """)
        layout.addWidget(title_label)
        
        # Chart
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', COLORS['text_primary'])
        
        plot = pg.PlotWidget()
        plot.setBackground('w')
        plot.showGrid(x=True, y=True, alpha=0.2)
        
        # Clear axis labels
        plot.setLabel('left', 'Value', color=COLORS['text_secondary'], size='10pt')
        plot.setLabel('bottom', 'Samples', color=COLORS['text_secondary'], size='10pt')
        
        plot.setMinimumHeight(180)
        
        # Style axes
        axis_pen = pg.mkPen(color=COLORS['border'], width=1)
        plot.getPlotItem().getAxis('left').setPen(axis_pen)
        plot.getPlotItem().getAxis('bottom').setPen(axis_pen)
        
        # Create curve
        curve = plot.plot(
            pen=pg.mkPen(color, width=2.5)
        )
        
        if not hasattr(self, 'sensor_curves'):
            self.sensor_curves = {}
        self.sensor_curves[key] = curve
        
        layout.addWidget(plot)
        return container

    def create_combined_chart(self):
        """Create combined chart view"""
        container = QtWidgets.QWidget()
        container.setStyleSheet(f"""
            background: {COLORS['bg_card']};
            border-radius: 8px;
            border: 1px solid {COLORS['border']};
        """)
        
        # Subtle shadow
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 10))
        container.setGraphicsEffect(shadow)
        
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QtWidgets.QLabel("Combined Sensor Signals")
        title.setStyleSheet(f"""
            font-size: 16px;
            font-weight: 600;
            color: {COLORS['text_primary']};
        """)
        layout.addWidget(title)
        
        # Chart
        pg.setConfigOption('background', 'w')
        
        self.combined_plot = pg.PlotWidget()
        self.combined_plot.setBackground('w')
        self.combined_plot.showGrid(x=True, y=True, alpha=0.2)
        
        # Clear axis labels
        self.combined_plot.setLabel('left', 'Value', color=COLORS['text_secondary'], size='11pt')
        self.combined_plot.setLabel('bottom', 'Samples', color=COLORS['text_secondary'], size='11pt')
        
        self.combined_plot.setMinimumHeight(400)
        
        # Style axes
        axis_pen = pg.mkPen(color=COLORS['border'], width=1)
        self.combined_plot.getPlotItem().getAxis('left').setPen(axis_pen)
        self.combined_plot.getPlotItem().getAxis('bottom').setPen(axis_pen)
        
        # Legend
        legend = self.combined_plot.addLegend(offset=(10, 10))
        
        # Sensor names
        names = {
            "co_m": "CO (MICS)",
            "eth_m": "Ethanol (MICS)",
            "voc_m": "VOC (MICS)",
            "no2": "NO₂",
            "c2h50h_gm": "C₂H₅OH (GM)",
            "voc_gm": "VOC (GM)",
            "co_gm": "CO (GM)"
        }
        
        self.combined_curves = {}
        for key in self.buffers.keys():
            self.combined_curves[key] = self.combined_plot.plot(
                pen=pg.mkPen(SENSOR_COLORS[key], width=2),
                name=names[key]
            )
        
        layout.addWidget(self.combined_plot)
        return container

    def handle_sensor_data(self, line):
        """Handle incoming sensor data"""
        data = parse_sensor_data(line)
        if data:
            self.data_signal.emit(data)

    def on_status_update(self, message):
        """Update status display"""
        self.status_label.setText(message)
        
        if "Connected" in message:
            self.status_label.setStyleSheet(f"""
                font-size: 12px;
                font-weight: 500;
                color: {COLORS['success']};
                padding: 8px 16px;
                background: {COLORS['success_light']};
                border-radius: 6px;
                border: 1px solid {COLORS['success']}20;
            """)
            self.status_card.update_value("●")
        elif "Connecting" in message or "Cannot connect" in message:
            self.status_label.setStyleSheet(f"""
                font-size: 12px;
                font-weight: 500;
                color: {COLORS['warning']};
                padding: 8px 16px;
                background: {COLORS['warning_light']};
                border-radius: 6px;
                border: 1px solid {COLORS['warning']}20;
            """)

    def on_data_update(self, data):
        """Update data buffers and UI"""
        now = data.get("timestamp", int(time.time()*1000))
        row = {
            "timestamp": now,
            "co_m": data.get("co_m"),
            "eth_m": data.get("eth_m"),
            "voc_m": data.get("voc_m"),
            "no2": data.get("no2"),
            "c2h50h_gm": data.get("c2h50h_gm"),
            "voc_gm": data.get("voc_gm"),
            "co_gm": data.get("co_gm"),
        }
        self.csv_rows.append(row)
        self.sample_count += 1
        
        # Update stats card
        self.samples_card.update_value(str(self.sample_count))

        # Update buffers
        for key in self.buffers:
            val = data.get(key, 0.0)
            try:
                val_num = float(val) if val is not None else 0.0
            except:
                val_num = 0.0
            self.buffers[key].append(val_num)
            if len(self.buffers[key]) > self.maxlen:
                self.buffers[key].pop(0)

    def update_plot(self):
        """Update all plots"""
        if hasattr(self, 'sensor_curves'):
            for key, curve in self.sensor_curves.items():
                y = self.buffers[key]
                if y:
                    x = list(range(len(y)))
                    curve.setData(x, y)
        
        if hasattr(self, 'combined_curves'):
            for key, curve in self.combined_curves.items():
                y = self.buffers[key]
                if y:
                    x = list(range(len(y)))
                    curve.setData(x, y)

    def send_command(self, cmd):
        """Send command to backend"""
        try:
            with socket.socket() as s:
                s.connect((TCP_CMD_HOST, TCP_CMD_PORT))
                s.sendall(f"{cmd}\n".encode())
            return True
        except Exception as e:
            print(f"Command error: {e}")
            return False

    def start_sampling(self):
        """Start sampling"""
        if self.send_command("START_SAMPLING"):
            self.csv_rows.clear()
            self.sample_count = 0
            self.samples_card.update_value("0")
            for k in self.buffers:
                self.buffers[k].clear()
            self.status_label.setText("Sampling active...")
            self.status_label.setStyleSheet(f"""
                font-size: 12px;
                font-weight: 500;
                color: {COLORS['success']};
                padding: 8px 16px;
                background: {COLORS['success_light']};
                border-radius: 6px;
                border: 1px solid {COLORS['success']}20;
            """)
            self.save_card.update_value("⏳")
        else:
            QMessageBox.warning(self, "Error", f"❌ Failed to send command!\nMake sure Rust is running on {TCP_CMD_HOST}:{TCP_CMD_PORT}")

    def stop_sampling(self):
        """Stop sampling"""
        if self.send_command("STOP_SAMPLING"):
            self.status_label.setText("Sampling stopped")
            self.status_label.setStyleSheet(f"""
                font-size: 12px;
                font-weight: 500;
                color: {COLORS['info']};
                padding: 8px 16px;
                background: {COLORS['info_light']};
                border-radius: 6px;
                border: 1px solid {COLORS['info']}20;
            """)
            self.save_card.update_value("✓")
        else:
            QMessageBox.warning(self, "Error", "❌ Failed to send command!")

    def clear_data(self):
        """Clear all data"""
        reply = QMessageBox.question(
            self, 'Clear Data',
            '🗑️ Delete all data?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.csv_rows.clear()
            self.sample_count = 0
            self.samples_card.update_value("0")
            for k in self.buffers:
                self.buffers[k].clear()
            self.save_card.update_value("⏳")

    def save_all_and_upload(self):
        """Save to CSV + JSON + Upload to Edge Impulse"""
        
        if not self.csv_rows:
            QMessageBox.warning(self, "Warning", "⚠️ No data to save!")
            return
        
        ei_label = self.ei_label.text().strip()
        if not ei_label:
            QMessageBox.warning(self, "Missing Label", "❌ Please enter Edge Impulse label")
            return
        
        sample_name = self.sample_name.text().strip() or "Unknown"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("data", exist_ok=True)
        
        csv_path = f"data/{sample_name}_{ts}.csv"
        json_path = f"data/{sample_name}_{ts}.json"
        
        try:
            # Save CSV
            self.save_card.update_value("💾")
            QtCore.QCoreApplication.processEvents()
            
            with open(csv_path, "w", newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.csv_rows[0].keys())
                writer.writeheader()
                writer.writerows(self.csv_rows)
            
            # Save JSON
            json_data = {
                "sample_name": sample_name,
                "ei_label": ei_label,
                "timestamp": ts,
                "total_samples": len(self.csv_rows),
                "data": self.csv_rows
            }
            
            with open(json_path, "w") as f:
                json.dump(json_data, f, indent=2)
            
            # Show progress dialog
            progress = QProgressDialog("Uploading to Edge Impulse...", None, 0, 0, self)
            progress.setWindowTitle("Upload")
            progress.setCancelButton(None)
            progress.show()
            QtCore.QCoreApplication.processEvents()
            
            self.save_card.update_value("📤")
            
            # Create uploader worker
            uploader = EdgeImpulseUploader()
            uploader_thread = QThread()
            uploader.moveToThread(uploader_thread)
            
            def on_progress(msg):
                progress.setLabelText(msg)
                QtCore.QCoreApplication.processEvents()
            
            def on_finished(success, message):
                progress.close()
                uploader_thread.quit()
                uploader_thread.wait()
                
                if success:
                    self.save_card.update_value("✓")
                    msg = f"✅ All files saved and uploaded!\n\n"
                    msg += f"📁 CSV: {csv_path}\n"
                    msg += f"📁 JSON: {json_path}\n\n"
                    msg += message
                    QMessageBox.information(self, "Success", msg)
                    self.clear_data()
                    self.sample_name.clear()
                    self.ei_label.clear()
                else:
                    self.save_card.update_value("✗")
                    msg = f"Files saved locally but upload failed:\n\n"
                    msg += f"📁 CSV: {csv_path}\n"
                    msg += f"📁 JSON: {json_path}\n\n"
                    msg += message
                    QMessageBox.critical(self, "Upload Failed", msg)
            
            uploader.upload_progress.connect(on_progress)
            uploader.upload_finished.connect(on_finished)
            
            uploader_thread.started.connect(
                lambda: uploader.upload_csv(csv_path, ei_label, sample_name)
            )
            uploader_thread.start()
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"❌ {str(e)}")
            self.save_card.update_value("✗")

    def closeEvent(self, event):
        """Clean up on close"""
        self.receiver_thread.quit()
        self.receiver_thread.wait()
        self.timer.stop()
        event.accept()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setFont(QtGui.QFont("Segoe UI", 10))
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())