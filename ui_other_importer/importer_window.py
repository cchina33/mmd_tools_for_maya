# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - その他モデルインポーター メインウィンドウモジュール
VRMやglTF等の各種モデル形式をMayaへインポートするための統合タブウィンドウを提供します。
"""

import os
import sys
import maya.cmds as mc

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QTabWidget, QFrame, QProgressBar
    )
    PYSIDE_VER = 6
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QTabWidget, QFrame, QProgressBar
    )
    PYSIDE_VER = 2

# スタイルシートの読み込み
try:
    from ..ui.gui_style import MODERN_STYLE
except Exception:
    try:
        from ui.gui_style import MODERN_STYLE
    except Exception:
        MODERN_STYLE = ""

# VRMタブウィジェットの読み込み（相対・絶対・単体モジュール多段フォールバック）
try:
    from .tab_vrm_importer import TabVrmImporterWidget
except Exception:
    try:
        from ui_other_importer.tab_vrm_importer import TabVrmImporterWidget
    except Exception:
        try:
            from mmd_tools_for_maya.ui_other_importer.tab_vrm_importer import TabVrmImporterWidget
        except Exception:
            from tab_vrm_importer import TabVrmImporterWidget

VrmImporterTabWidget = TabVrmImporterWidget

# クリーンアップタブウィジェットの読み込み
try:
    from .tab_cleanup import TabCleanupWidget
except Exception:
    try:
        from ui_other_importer.tab_cleanup import TabCleanupWidget
    except Exception:
        try:
            from mmd_tools_for_maya.ui_other_importer.tab_cleanup import TabCleanupWidget
        except Exception:
            from tab_cleanup import TabCleanupWidget

_other_importer_instance = None


def get_maya_main_window():
    """Mayaのメインウィンドウポインタを取得してQWidgetとしてラップ"""
    try:
        from maya import OpenMayaUI as omui
        if PYSIDE_VER == 6:
            from shiboken6 import wrapInstance
        else:
            from shiboken2 import wrapInstance
        ptr = omui.MQtUtil.mainWindow()
        if ptr:
            return wrapInstance(int(ptr), QtWidgets.QWidget)
    except Exception:
        pass
    return None


class OtherModelImporterSplashDialog(QDialog):
    """インポーターウィンドウ起動中ローディングインジケータ"""
    def __init__(self, parent=None):
        if parent is None:
            parent = get_maya_main_window()
        super(OtherModelImporterSplashDialog, self).__init__(parent)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(360, 130)

        self.setStyleSheet("""
            QDialog {
                background-color: #242424;
                border: 2px solid #52b7ff;
                border-radius: 8px;
            }
            QLabel {
                color: #ffffff;
                font-family: 'Segoe UI', 'Meiryo', sans-serif;
            }
            QProgressBar {
                background-color: #1a1a1a;
                border: 1px solid #444444;
                border-radius: 4px;
                height: 8px;
            }
            QProgressBar::chunk {
                background-color: #52b7ff;
                border-radius: 3px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        lbl_title = QLabel("その他モデルインポーター")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #52b7ff;")
        lbl_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_title)

        self.lbl_status = QLabel("インポーターを起動中... しばらくお待ちください")
        self.lbl_status.setStyleSheet("font-size: 12px; color: #cccccc;")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(8)
        layout.addWidget(self.progress)

        self._center_on_parent(parent)

    def _center_on_parent(self, parent):
        """画面または親中央へ配置"""
        try:
            if parent:
                geo = parent.geometry()
                self.move(
                    geo.x() + (geo.width() - self.width()) // 2,
                    geo.y() + (geo.height() - self.height()) // 2
                )
            else:
                try:
                    from PySide6.QtGui import QGuiApplication
                    screen = QGuiApplication.primaryScreen().geometry()
                except ImportError:
                    from PySide2.QtGui import QGuiApplication
                    screen = QGuiApplication.primaryScreen().geometry()
                self.move(
                    (screen.width() - self.width()) // 2,
                    (screen.height() - self.height()) // 2
                )
        except Exception:
            pass


class OtherModelImporterWindow(QDialog):
    """
    その他モデルインポーター メインウィンドウ
    タブ形式でVRMや今後の各種外部フォーマットの読み込みを提供します。
    """

    def __init__(self, parent=None):
        if parent is None:
            parent = get_maya_main_window()
        super(OtherModelImporterWindow, self).__init__(parent)

        self.setWindowTitle("その他モデルインポート (VRM等)")
        self.setObjectName("OtherModelImporterWindow")
        self.resize(1020, 720)
        self.setMinimumSize(800, 540)

        self.setWindowFlags(self.windowFlags() | Qt.Window)

        if MODERN_STYLE:
            self.setStyleSheet(MODERN_STYLE)

        self._init_ui()

    def _init_ui(self):
        """ウィンドウレイアウトの初期化"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 上部ヘッダー
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #242424; border-radius: 6px; padding: 4px;")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(8)

        lbl_header = QLabel("外部モデルインポート (VRM / その他形式)")
        lbl_header.setStyleSheet("font-weight: bold; color: #52b7ff; font-size: 14px;")
        header_layout.addWidget(lbl_header)
        header_layout.addStretch()

        btn_reload = QPushButton("UI再読込")
        btn_reload.setFixedWidth(90)
        btn_reload.setStyleSheet(
            "QPushButton { background-color: #2b553b; color: #aaffaa; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3b754b; border: 1px solid #77ff77; }"
        )
        btn_reload.setToolTip("スクリプトファイルを再読み込み（ホットリロード）して最新状態を即座に反映します。")
        btn_reload.clicked.connect(self._reload_and_reopen)
        header_layout.addWidget(btn_reload)

        main_layout.addWidget(header_frame)

        # メインタブコンテナ
        self.tabs = QTabWidget()

        # VRMタブ
        self.tab_vrm = VrmImporterTabWidget(self)
        self.tabs.addTab(self.tab_vrm, "VRM モデル (.vrm)")

        # クリーンアップタブ (ユーザー指定名称のタブを追加)
        try:
            self.tab_cleanup = TabCleanupWidget(self)
            clean_title = chr(0x5B8C) + chr(0x5168) + "削除"
            self.tabs.addTab(self.tab_cleanup, clean_title)
        except Exception as e_tab:
            print(f"[警告] クリーンアップタブの追加に失敗しました: {e_tab}")

        main_layout.addWidget(self.tabs)

        # フッター部
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(4, 2, 4, 2)
        lbl_hint = QLabel("※VRMモデルのメッシュ・マテリアル・スケルトン・ブレンドシェイプをMayaへ展開します。")
        lbl_hint.setStyleSheet("color: #888; font-size: 12px;")
        footer_layout.addWidget(lbl_hint)
        footer_layout.addStretch()

        lbl_ver = QLabel("MMD Tools for Maya | Universal Importer")
        lbl_ver.setStyleSheet("color: #666; font-size: 12px;")
        footer_layout.addWidget(lbl_ver)
        main_layout.addLayout(footer_layout)

    def _reload_and_reopen(self):
        """モジュールをホットリロードしてウィンドウを再構築"""
        reload_importer_modules()
        show_other_model_importer()


def reload_importer_modules():
    """ui_other_importer および other_converters 配下のモジュールを再読み込み"""
    import importlib
    target_names = [
        "tab_vrm_importer", "tab_cleanup", "importer_window", "ui_other_importer",
        "vrm_importer", "other_converters"
    ]
    all_keys = list(sys.modules.keys())
    for k in all_keys:
        if any(m in k for m in target_names):
            m_obj = sys.modules.get(k)
            if m_obj:
                try:
                    importlib.reload(m_obj)
                except Exception:
                    pass


def show_other_model_importer():
    """その他モデルインポーター ウィンドウを表示（多重起動防止・起動中表示対応）"""
    global _other_importer_instance

    splash = None
    try:
        splash = OtherModelImporterSplashDialog()
        splash.show()
        QtWidgets.QApplication.processEvents()
    except Exception:
        splash = None

    try:
        if _other_importer_instance is not None:
            try:
                _other_importer_instance.close()
                _other_importer_instance.deleteLater()
            except Exception:
                pass
            _other_importer_instance = None

        _other_importer_instance = OtherModelImporterWindow()
        _other_importer_instance.show()
        _other_importer_instance.raise_()
        _other_importer_instance.activateWindow()
        QtWidgets.QApplication.processEvents()
        return _other_importer_instance
    finally:
        if splash:
            try:
                splash.close()
                splash.deleteLater()
            except Exception:
                pass

