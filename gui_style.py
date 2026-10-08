# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - GUI スタイルシート定義モジュール
ダークテーマスタイル（QSS）を定義します。
"""

MODERN_STYLE = """
QWidget {
    background-color: #2b2b2b;
    color: #e8e8e8;
    font-family: 'Segoe UI', 'Meiryo UI', 'Yu Gothic UI', sans-serif;
    font-size: 15px;
}

QTabWidget::pane {
    border: 1px solid #3c3c3c;
    background-color: #2b2b2b;
    border-radius: 6px;
    padding: 8px;
}

QTabBar::tab {
    background-color: #202020;
    color: #a8a8a8;
    padding: 10px 14px;
    margin-right: 3px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    font-size: 14px;
    font-weight: bold;
}

QTabBar::tab:selected {
    background-color: #383838;
    color: #52b7ff;
    border-bottom: 2px solid #52b7ff;
}

QTabBar::tab:hover {
    background-color: #2d2d2d;
    color: #ffffff;
}

QGroupBox {
    border: 1px solid #444444;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 16px;
    font-size: 16px;
    font-weight: bold;
    color: #52b7ff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

QLineEdit {
    background-color: #1e1e1e;
    border: 1px solid #484848;
    border-radius: 4px;
    padding: 8px 10px;
    color: #ffffff;
    font-size: 15px;
    selection-background-color: #5285a6;
}

QLineEdit:focus {
    border: 1px solid #52b7ff;
}

QComboBox {
    background-color: #353535;
    border: 1px solid #484848;
    border-radius: 4px;
    padding: 7px 12px;
    color: #ffffff;
    font-size: 15px;
}

QComboBox:hover {
    border: 1px solid #52b7ff;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #2a2a2a;
    border: 1px solid #484848;
    selection-background-color: #5285a6;
    selection-color: #ffffff;
    font-size: 15px;
}

QCheckBox, QRadioButton {
    spacing: 10px;
    color: #e0e0e0;
    font-size: 15px;
}

QCheckBox:hover, QRadioButton:hover {
    color: #ffffff;
}

QPushButton {
    background-color: #3b3b3b;
    border: 1px solid #4f4f4f;
    border-radius: 4px;
    padding: 8px 16px;
    color: #ffffff;
    font-size: 15px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #4a4a4a;
    border: 1px solid #52b7ff;
}

QPushButton:pressed {
    background-color: #252525;
}

QPushButton:disabled {
    background-color: #262626;
    border: 1px solid #333333;
    color: #666666;
}

QPushButton.primary {
    background-color: #1e6fa8;
    border: 1px solid #2a8ed4;
    font-size: 16px;
    font-weight: bold;
    padding: 11px;
}

QPushButton.primary:hover {
    background-color: #258ad1;
    border: 1px solid #6ac5fe;
}

QPushButton.primary:pressed {
    background-color: #144e76;
}

QScrollArea {
    border: 1px solid #3c3c3c;
    background-color: #222222;
    border-radius: 4px;
}

QTextEdit {
    background-color: #1b1b1b;
    border: 1px solid #444444;
    border-radius: 4px;
    color: #dcdcdc;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    padding: 6px;
}

QProgressBar {
    border: 1px solid #444444;
    border-radius: 4px;
    background-color: #1e1e1e;
    text-align: center;
    color: #ffffff;
    font-size: 13px;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: #1e6fa8;
    border-radius: 3px;
}
"""
