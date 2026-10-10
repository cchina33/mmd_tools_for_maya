# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - GUI スタイルシート定義モジュール
ダークテーマスタイル（QSS）を定義します。
"""

import os

# 矢印アイコンパスの動的解決
_script_dir = os.path.dirname(os.path.abspath(__file__))
_image_dir = os.path.abspath(os.path.join(_script_dir, "..", "image")).replace("\\", "/")
_arrow_icon = f"{_image_dir}/arrow_down.png"
_arrow_hover_icon = f"{_image_dir}/arrow_down_hover.png"

MODERN_STYLE = f"""
QWidget {{
    background-color: #2b2b2b;
    color: #e8e8e8;
    font-family: 'Segoe UI', 'Meiryo UI', 'Yu Gothic UI', sans-serif;
    font-size: 15px;
}}

QTabWidget::pane {{
    border: 1px solid #3c3c3c;
    background-color: #2b2b2b;
    border-radius: 6px;
    padding: 8px;
}}

QTabBar::tab {{
    background-color: #202020;
    color: #a8a8a8;
    padding: 10px 14px;
    margin-right: 3px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    font-size: 14px;
    font-weight: bold;
}}

QTabBar::tab:selected {{
    background-color: #383838;
    color: #52b7ff;
    border-bottom: 2px solid #52b7ff;
}}

QTabBar::tab:hover {{
    background-color: #2d2d2d;
    color: #ffffff;
}}

QGroupBox {{
    border: 1px solid #444444;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 16px;
    font-size: 16px;
    font-weight: bold;
    color: #52b7ff;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}}

QLineEdit {{
    background-color: #1e1e1e;
    border: 1px solid #484848;
    border-radius: 4px;
    padding: 8px 10px;
    color: #ffffff;
    font-size: 15px;
    selection-background-color: #5285a6;
}}

QLineEdit:focus {{
    border: 1px solid #52b7ff;
}}

QComboBox {{
    background-color: #2e2e2e;
    border: 1px solid #505050;
    border-radius: 4px;
    padding: 7px 32px 7px 12px;
    color: #ffffff;
    font-size: 15px;
    font-weight: 500;
    min-height: 24px;
}}

QComboBox:hover {{
    border: 1px solid #52b7ff;
    background-color: #383838;
}}

QComboBox:focus {{
    border: 1px solid #52b7ff;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid #444444;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
    background-color: #333333;
}}

QComboBox::drop-down:hover {{
    background-color: #404040;
}}

QComboBox::down-arrow {{
    image: url('{_arrow_icon}');
    width: 14px;
    height: 14px;
}}

QComboBox::down-arrow:hover {{
    image: url('{_arrow_hover_icon}');
}}

QComboBox QAbstractItemView {{
    background-color: #242424;
    border: 1px solid #52b7ff;
    border-radius: 4px;
    color: #ffffff;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
    font-size: 15px;
    padding: 2px;
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    min-height: 28px;
    padding: 4px 12px;
    border: none;
    margin: 0px;
    color: #ffffff;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: #383838;
    color: #52b7ff;
    border: none;
    margin: 0px;
    padding: 4px 12px;
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: #0078d4;
    color: #ffffff;
    border: none;
    margin: 0px;
    padding: 4px 12px;
}}

QCheckBox, QRadioButton {{
    spacing: 10px;
    color: #e0e0e0;
    font-size: 15px;
}}

QCheckBox:hover, QRadioButton:hover {{
    color: #ffffff;
}}

QPushButton {{
    background-color: #3b3b3b;
    border: 1px solid #4f4f4f;
    border-radius: 4px;
    padding: 8px 16px;
    color: #ffffff;
    font-size: 15px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: #4a4a4a;
    border: 1px solid #52b7ff;
}}

QPushButton:pressed {{
    background-color: #252525;
}}

QPushButton:disabled {{
    background-color: #262626;
    border: 1px solid #333333;
    color: #666666;
}}

QPushButton.primary {{
    background-color: #1e6fa8;
    border: 1px solid #2a8ed4;
    font-size: 16px;
    font-weight: bold;
    padding: 11px;
}}

QPushButton.primary:hover {{
    background-color: #258ad1;
    border: 1px solid #6ac5fe;
}}

QPushButton.primary:pressed {{
    background-color: #144e76;
}}

QScrollArea {{
    border: 1px solid #3c3c3c;
    background-color: #222222;
    border-radius: 4px;
}}

QTextEdit {{
    background-color: #1b1b1b;
    border: 1px solid #444444;
    border-radius: 4px;
    color: #dcdcdc;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    padding: 6px;
}}

QProgressBar {{
    border: 1px solid #444444;
    border-radius: 4px;
    background-color: #1e1e1e;
    text-align: center;
    color: #ffffff;
    font-size: 13px;
    font-weight: bold;
}}

QProgressBar::chunk {{
    background-color: #1e6fa8;
    border-radius: 3px;
}}
"""
