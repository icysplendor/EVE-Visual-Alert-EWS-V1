import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QGroupBox, QGridLayout, QLineEdit, 
                             QFileDialog, QMessageBox, QWidget, QSlider, QScrollArea)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage, QIcon

BTN_STYLE = """
QPushButton {
    background-color: #333;
    border: 1px solid #555;
    color: #eee;
    border-radius: 3px;
    padding: 5px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #444;
    border-color: #00bcd4;
    color: #fff;
}
QPushButton:pressed {
    background-color: #00bcd4;
    color: #000;
}
"""

SLIDER_STYLE = """
QSlider::groove:horizontal {
    border: 1px solid #333;
    height: 6px;
    background: #111;
    margin: 2px 0;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #00bcd4;
    border: 1px solid #00bcd4;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: #008ba3;
    border-radius: 3px;
}
"""

def resource_path(relative_path):
    import sys
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# === 设置窗口 ===
class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Advanced Settings")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.resize(500, 700)
        
        icon_path = resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.setup_ui()
        self.setStyleSheet("background-color: #121212; color: #ccc;")

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #121212; border: none;")
        
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)
        
        gb_style = """
        QGroupBox { 
            border: 1px solid #444; 
            margin-top: 15px; 
            padding-top: 15px; 
            font-weight: bold; 
            color: #00bcd4; 
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 5px;
        }
        """

        def create_stepped_slider(label_text, real_min, real_max, step_size, current_real_val, callback, val_fmt):
            total_steps = int((real_max - real_min) / step_size)
            current_slider_pos = int((current_real_val - real_min) / step_size)
            current_slider_pos = max(0, min(total_steps, current_slider_pos))

            lbl = QLabel(label_text)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, total_steps)
            slider.setSingleStep(1)
            slider.setPageStep(1)
            slider.setValue(current_slider_pos)
            slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            slider.setTickInterval(1)
            slider.setStyleSheet(SLIDER_STYLE)
            
            val_lbl = QLabel(val_fmt(current_real_val))
            val_lbl.setFixedWidth(60)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val_lbl.setStyleSheet("color: #00bcd4; font-weight: bold;")
            
            def on_change(pos):
                real_val = real_min + (pos * step_size)
                real_val = round(real_val, 5)
                val_lbl.setText(val_fmt(real_val))
                callback(real_val)

            slider.valueChanged.connect(on_change)
            return lbl, slider, val_lbl

        # 1. 逻辑设置
        grp_logic = QGroupBox("Logic Configuration")
        grp_logic.setStyleSheet(gb_style)
        l_logic = QGridLayout()
        l_logic.setSpacing(10)
        
        curr_scan = self.cfg.get("scan_interval") * 1000
        l1, s1, v1 = create_stepped_slider(
            "Scan Interval:", 200, 1200, 50, curr_scan,
            lambda v: self.cfg.set("scan_interval", v / 1000.0),
            lambda v: f"{int(v)}ms"
        )
        l_logic.addWidget(l1, 0, 0)
        l_logic.addWidget(s1, 0, 1)
        l_logic.addWidget(v1, 0, 2)

        curr_jitter = self.cfg.get("jitter_delay") * 1000
        l2, s2, v2 = create_stepped_slider(
            "Anti-Jitter:", 100, 300, 10, curr_jitter,
            lambda v: self.cfg.set("jitter_delay", v / 1000.0),
            lambda v: f"{int(v)}ms"
        )
        l_logic.addWidget(l2, 1, 0)
        l_logic.addWidget(s2, 1, 1)
        l_logic.addWidget(v2, 1, 2)
        grp_logic.setLayout(l_logic)
        layout.addWidget(grp_logic)

        # 2. 阈值设置
        grp_th = QGroupBox("Global Thresholds")
        grp_th.setStyleSheet(gb_style)
        l_th = QGridLayout()
        l_th.setSpacing(10)
        
        thresholds = self.cfg.get("thresholds")
        
        def add_thresh_slider(row, key, label):
            curr_val = thresholds.get(key, 0.95)
            def update_cfg(val):
                t = self.cfg.get("thresholds")
                t[key] = val
                self.cfg.set("thresholds", t)

            l, s, v = create_stepped_slider(
                label, 0.800, 0.995, 0.005, curr_val,
                update_cfg,
                lambda val: f"{val*100.0:.1f}%"
            )
            l_th.addWidget(l, row, 0)
            l_th.addWidget(s, row, 1)
            l_th.addWidget(v, row, 2)

        add_thresh_slider(0, "local", "Local %:")
        add_thresh_slider(1, "overview", "Overview %:")
        add_thresh_slider(2, "monster", "Rats %:")
        add_thresh_slider(3, "probe", "Probe %:")
        add_thresh_slider(4, "location", "System %:")
        
        grp_th.setLayout(l_th)
        layout.addWidget(grp_th)

        # 3. Webhook
        grp_wh = QGroupBox("Webhook Configuration")
        grp_wh.setStyleSheet(gb_style)
        l_wh = QVBoxLayout()
        self.line_webhook = QLineEdit(self.cfg.get("webhook_url"))
        self.line_webhook.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.line_webhook.setStyleSheet("background-color: #080808; border: 1px solid #333; color: #00bcd4; padding: 4px;")
        self.line_webhook.textChanged.connect(lambda t: self.cfg.set("webhook_url", t))
        l_wh.addWidget(self.line_webhook)
        grp_wh.setLayout(l_wh)
        layout.addWidget(grp_wh)

        # 4. Audio
        grp_audio = QGroupBox("Audio Assets")
        grp_audio.setStyleSheet(gb_style)
        grid_audio = QGridLayout()
        grid_audio.setSpacing(10)
        
        audio_keys = ["local", "overview", "monster", "mixed", "probe", "idle"]
        for idx, key in enumerate(audio_keys):
            row = idx // 2
            col = idx % 2
            
            container = QWidget()
            h = QHBoxLayout(container)
            h.setContentsMargins(0,0,0,0)
            
            lbl_name = QLabel(key.upper())
            lbl_name.setFixedWidth(60)
            lbl_name.setStyleSheet("color: #888;")
            
            path_val = self.cfg.get("audio_paths").get(key, "")
            fname = os.path.basename(path_val) if path_val else "---"
            lbl_file = QLabel(fname)
            lbl_file.setStyleSheet("color: #00bcd4; font-size: 10px;")
            
            btn_sel = QPushButton("SELECT")
            btn_sel.setFixedSize(60, 24)
            btn_sel.setStyleSheet(BTN_STYLE)
            btn_sel.clicked.connect(lambda _, k=key, l=lbl_file: self.select_audio(k, l))
            
            h.addWidget(lbl_name)
            h.addWidget(lbl_file)
            h.addStretch()
            h.addWidget(btn_sel)
            grid_audio.addWidget(container, row, col)
            
        grp_audio.setLayout(grid_audio)
        layout.addWidget(grp_audio)
        
        btn_close = QPushButton("CLOSE SETTINGS")
        btn_close.setFixedHeight(35)
        btn_close.setStyleSheet(BTN_STYLE)
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)
        
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def select_audio(self, key, label_widget):
        fname, _ = QFileDialog.getOpenFileName(self, "Select Audio", "", "Audio (*.wav *.mp3)")
        if fname:
            cwd = os.getcwd()
            try:
                rel_path = os.path.relpath(fname, cwd)
                save_path = rel_path if not rel_path.startswith("..") else fname
            except:
                save_path = fname

            paths = self.cfg.get("audio_paths")
            paths[key] = save_path
            self.cfg.set("audio_paths", paths)
            label_widget.setText(os.path.basename(fname))

# === 单个监控组控件 (布局优化) ===
class GroupWidget(QGroupBox):
    def __init__(self, group_data, index, parent_win):
        super().__init__()
        self.group_data = group_data
        self.index = index
        self.parent_win = parent_win
        
        self.setStyleSheet("""
            QGroupBox { 
                border: 1px solid #444; 
                border-radius: 0px; 
                margin-top: 12px; 
                font-weight: bold; 
                color: #00bcd4; 
                background-color: #1a1a1a;
            }
        """)
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # 1. 顶部栏
        top_bar = QHBoxLayout()
        lbl_title = QLabel(f"CLIENT {self.index + 1}")
        lbl_title.setStyleSheet("font-weight: bold; color: #00bcd4; font-size: 12px;")
        top_bar.addWidget(lbl_title)
        
        self.lbl_location = QLabel("[ Unknown ]")
        self.lbl_location.setStyleSheet("color: #888; font-size: 11px; margin-left: 10px;")
        top_bar.addWidget(self.lbl_location)
        
        top_bar.addStretch()
        
        self.btn_remove = QPushButton("✖")
        self.btn_remove.setFixedSize(24, 24)
        self.btn_remove.setToolTip("Remove Group")
        self.btn_remove.setStyleSheet("""
            QPushButton { background: transparent; border: none; color: #666; font-size: 14px; }
            QPushButton:hover { color: #ff5555; background: #2a0000; }
        """)
        self.btn_remove.clicked.connect(self.request_remove)
        
        if self.index == 0:
            self.btn_remove.setVisible(False)
            
        top_bar.addWidget(self.btn_remove)
        main_layout.addLayout(top_bar)

        # 2. 按钮区域 (布局优化)
        btn_grid = QGridLayout()
        btn_grid.setSpacing(5) # 稍微紧凑一点

        self.btn_local = QPushButton()
        self.btn_overview = QPushButton()
        self.btn_monster = QPushButton()
        self.btn_probe = QPushButton()
        self.btn_location = QPushButton()
        
        # === 布局核心修改 ===
        # Local: 独占第1行，且高度稍大，强调重要性
        self.btn_local.setFixedHeight(35) 
        self.btn_local.setStyleSheet(BTN_STYLE + "QPushButton { font-size: 12px; border-color: #00bcd4; }")
        btn_grid.addWidget(self.btn_local, 0, 0, 1, 2) # 跨两列
        
        # 其他按钮：普通高度，并排
        for btn in [self.btn_overview, self.btn_monster, self.btn_probe, self.btn_location]:
            btn.setStyleSheet(BTN_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)

        # Overview / Rats 在第2行
        btn_grid.addWidget(self.btn_overview, 1, 0)
        btn_grid.addWidget(self.btn_monster, 1, 1)
        
        # Probe / Location 在第3行
        btn_grid.addWidget(self.btn_probe, 2, 0)
        btn_grid.addWidget(self.btn_location, 2, 1)
        
        main_layout.addLayout(btn_grid)

        self.btn_local.clicked.connect(lambda: self.parent_win.start_region_selection(self.index, "local"))
        self.btn_overview.clicked.connect(lambda: self.parent_win.start_region_selection(self.index, "overview"))
        self.btn_monster.clicked.connect(lambda: self.parent_win.start_region_selection(self.index, "monster"))
        self.btn_probe.clicked.connect(lambda: self.parent_win.start_region_selection(self.index, "probe"))
        self.btn_location.clicked.connect(lambda: self.parent_win.start_region_selection(self.index, "location"))

        self.update_texts()

    def update_texts(self):
        _ = self.parent_win.i18n.get
        self.btn_local.setText(_("btn_local"))
        self.btn_overview.setText(_("btn_overview"))
        self.btn_monster.setText(_("btn_npc"))
        self.btn_probe.setText(_("btn_probe"))
        self.btn_location.setText(_("btn_location"))

    def update_location_display(self, system_name):
        self.lbl_location.setText(f"[ {system_name} ]")
        if system_name == "Unknown":
            self.lbl_location.setStyleSheet("color: #888; font-size: 11px; margin-left: 10px;")
        else:
            self.lbl_location.setStyleSheet("color: #00ff00; font-weight: bold; font-size: 11px; margin-left: 10px;")

    def request_remove(self):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle('CONFIRM REMOVAL')
        msg_box.setText(f"Are you sure you want to remove Client {self.index + 1}?")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        msg_box.setStyleSheet("background-color: #121212; color: #ccc; QPushButton { background: #333; color: #eee; border: 1px solid #555; padding: 5px; min-width: 60px; }")
        
        reply = msg_box.exec()
        if reply == QMessageBox.StandardButton.Yes:
            self.parent_win.remove_group(self.index)

# === 调试窗口 ===
class DebugWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LIVE VIEW")
        
        icon_path = resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.setStyleSheet("background-color: #121212; color: #ccc;")
        self.resize(750, 500)
        
        self.current_group_idx = 0
        self.group_buttons = []
        self.image_labels = {}
        
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        
        self.tab_layout = QHBoxLayout()
        self.main_layout.addLayout(self.tab_layout)
        
        self.img_layout = QHBoxLayout()
        self.img_layout.setSpacing(10)
        
        for key in ["Local", "Overview", "Rats", "Probe", "Location"]:
            vbox = QVBoxLayout()
            lbl_title = QLabel(key.upper())
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_title.setFixedHeight(20)
            lbl_title.setStyleSheet("color: #00bcd4; font-weight: bold;")
            
            lbl_img = QLabel()
            lbl_img.setFixedSize(120, 500) 
            lbl_img.setStyleSheet("border: 1px solid #333; background: #000;")
            lbl_img.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            
            vbox.addWidget(lbl_title)
            vbox.addWidget(lbl_img)
            self.img_layout.addLayout(vbox)
            self.image_labels[key] = lbl_img
            
        self.main_layout.addLayout(self.img_layout)

    def refresh_tabs(self, num_groups):
        while self.tab_layout.count():
            item = self.tab_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        self.group_buttons = []
        for i in range(num_groups):
            btn = QPushButton(f"CLIENT {i+1}")
            btn.setCheckable(True)
            btn.setFixedSize(80, 30) 
            btn.clicked.connect(lambda _, idx=i: self.switch_group(idx))
            btn.setStyleSheet("""
                QPushButton { background: #222; border: 1px solid #444; color: #888; border-bottom: none; }
                QPushButton:checked { background: #00bcd4; color: #000; border: 1px solid #00bcd4; font-weight: bold; }
                QPushButton:hover { color: #fff; }
            """)
            self.tab_layout.addWidget(btn)
            self.group_buttons.append(btn)
            
        self.tab_layout.addStretch()
        
        if self.current_group_idx >= num_groups:
            self.current_group_idx = 0
        if self.group_buttons:
            self.switch_group(self.current_group_idx)

    def switch_group(self, idx):
        self.current_group_idx = idx
        for i, btn in enumerate(self.group_buttons):
            btn.setChecked(i == idx)

    def update_images(self, all_groups_images):
        mapping = {
            "Local": "local",
            "Overview": "overview",
            "Rats": "monster",
            "Probe": "probe",
            "Location": "location"
        }
        for ui_key, data_key in mapping.items():
            img = all_groups_images.get((self.current_group_idx, data_key))
            self.set_pixmap(self.image_labels[ui_key], img)

    def set_pixmap(self, label, np_img):
        if np_img is None: 
            label.clear()
            label.setText("NO SIGNAL")
            return
        h, w, ch = np_img.shape
        bytes_per_line = ch * w
        qimg = QImage(np_img.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
        label.setPixmap(QPixmap.fromImage(qimg).scaled(label.width(), label.height(), Qt.AspectRatioMode.KeepAspectRatio))
