# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - モダン統合 GUI メインモジュール (PySide6 / PySide2 対応)

各機能タブおよびダイアログを統合し、メインウィンドウの構築・管理と
外部スクリプト向けの互換インターフェースを提供します。
"""

from .common import *
from .multi_model_dialog import (
    MultiModelLogDialog,
    MultiModelDropTableWidget,
    MultiModelImportDialog,
    MultiModelPhysicsBakeDialog,
)
from .pmm_dialog import (
    PmmDropArea,
    PmmModelImportSelectDialog,
    PmmAnalysisDialog,
)
from .accessory_dialog import AccessoryAttachDialog
from .experimental_dialog import ExperimentalFeaturesDialog
from .dialog_model_classifier import ModelClassifierDialog, show_model_classifier_dialog
from .dialog_edge_control import MmdEdgeControlDialog, show_mmd_edge_control_dialog
from .tab_plugin import PluginTabWidget
from .tab_easy_import import EasyImportTabWidget
from .tab_import import ImportTabWidget
from .tab_export import ExportTabWidget, ExportDialog
from .tab_hik import HikTabWidget, HikWindow, show_hik_window
from .tab_vmd import VmdImportTabWidget
from .tab_physics import PhysicsTabWidget, PhysicsGuiTabWidget
from .tab_cleanup import CleanupTabWidget
from .tab_material import MaterialTabWidget, MaterialDialog
from .tab_extra import ExtraTabWidget

# グローバルウィンドウ参照保持用（ガベージコレクション防止）
_main_window_instance = None


def _reload_ui_submodules():
    """開発・更新時に分割されたUIサブモジュールを依存順序に従って最新化する"""
    from . import (
        common,
        multi_model_dialog,
        pmm_dialog,
        accessory_dialog,
        experimental_dialog,
        tab_plugin,
        tab_easy_import,
        tab_import,
        tab_export,
        tab_hik,
        tab_vmd,
        tab_physics,
        tab_cleanup,
        tab_material,
        tab_extra,
        dialog_model_classifier,
        dialog_edge_control,
    )
    submodules = [
        common,
        multi_model_dialog,
        pmm_dialog,
        accessory_dialog,
        experimental_dialog,
        tab_plugin,
        tab_easy_import,
        tab_import,
        tab_export,
        tab_hik,
        tab_vmd,
        tab_physics,
        tab_cleanup,
        tab_material,
        tab_extra,
        dialog_model_classifier,
        dialog_edge_control,
    ]
    for mod in submodules:
        try:
            importlib.reload(mod)
        except Exception:
            pass

    # リロード後の最新クラス参照をメインモジュール名前空間へ再バインド
    globals().update({
        "MultiModelLogDialog": multi_model_dialog.MultiModelLogDialog,
        "MultiModelDropTableWidget": multi_model_dialog.MultiModelDropTableWidget,
        "MultiModelImportDialog": multi_model_dialog.MultiModelImportDialog,
        "MultiModelPhysicsBakeDialog": multi_model_dialog.MultiModelPhysicsBakeDialog,
        "PmmDropArea": pmm_dialog.PmmDropArea,
        "PmmModelImportSelectDialog": pmm_dialog.PmmModelImportSelectDialog,
        "PmmAnalysisDialog": pmm_dialog.PmmAnalysisDialog,
        "AccessoryAttachDialog": accessory_dialog.AccessoryAttachDialog,
        "ExperimentalFeaturesDialog": experimental_dialog.ExperimentalFeaturesDialog,
        "PluginTabWidget": tab_plugin.PluginTabWidget,
        "EasyImportTabWidget": tab_easy_import.EasyImportTabWidget,
        "ImportTabWidget": tab_import.ImportTabWidget,
        "ExportTabWidget": tab_export.ExportTabWidget,
        "ExportDialog": tab_export.ExportDialog,
        "HikTabWidget": tab_hik.HikTabWidget,
        "HikWindow": tab_hik.HikWindow,
        "show_hik_window": tab_hik.show_hik_window,
        "VmdImportTabWidget": tab_vmd.VmdImportTabWidget,
        "PhysicsTabWidget": tab_physics.PhysicsTabWidget,
        "PhysicsGuiTabWidget": tab_physics.PhysicsGuiTabWidget,
        "CleanupTabWidget": tab_cleanup.CleanupTabWidget,
        "MaterialTabWidget": tab_material.MaterialTabWidget,
        "MaterialDialog": tab_material.MaterialDialog,
        "ExtraTabWidget": tab_extra.ExtraTabWidget,
        "ModelClassifierDialog": dialog_model_classifier.ModelClassifierDialog,
        "show_model_classifier_dialog": dialog_model_classifier.show_model_classifier_dialog,
        "MmdEdgeControlDialog": dialog_edge_control.MmdEdgeControlDialog,
        "show_mmd_edge_control_dialog": dialog_edge_control.show_mmd_edge_control_dialog,
    })


# ==============================================================================
# メインウィンドウ (タブ統合)
# ==============================================================================
class MmdMayaMainWindow(QWidget):
    """MMD Tools for Maya のメイン統合ウィンドウ"""
    def __init__(self, parent=None):
        if parent is None:
            parent = get_maya_main_window()
        super(MmdMayaMainWindow, self).__init__(parent)
        
        self.setWindowTitle("MMD Tools for Maya v1.0.5")
        self.setObjectName("MmdToolsForMayaMainWindow")

        # メインウィンドウサイズ設定 (小画面縮小時の全タブスクロールに対応)
        self.resize(980, 820)
        self.setMinimumSize(480, 360)

        # Mayaの子ウィンドウとして独立表示（他アプリより前面固定にはしない）
        self.setWindowFlags(Qt.Window)
        self.setStyleSheet(MODERN_STYLE)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # タブコンテナ
        self.tabs = QTabWidget()
        self.tab_plugin = PluginTabWidget(self)
        self.tab_easy_import = EasyImportTabWidget(self)
        self.tab_import = ImportTabWidget(self)
        self.tab_vmd = VmdImportTabWidget(self)
        self.tab_physics = PhysicsTabWidget(self)
        self.tab_physics_gui = PhysicsGuiTabWidget(self)
        self.tab_extra = ExtraTabWidget(self)
        self.tab_material = None
        self.tab_export = None
        self.tab_cleanup = CleanupTabWidget(self)

        # タブ登録 (プラグイン管理を先頭、物理演算GUIを物理演算の次へ配置)
        self.tabs.addTab(self.tab_plugin, "プラグイン管理")
        self.tabs.addTab(self.tab_easy_import, "簡単インポート")
        self.tabs.addTab(self.tab_import, "MMD → Maya (インポート)")
        self.tabs.addTab(self.tab_vmd, "モーション (VMD)")
        self.tabs.addTab(self.tab_physics, "物理演算ベイク")
        self.tabs.addTab(self.tab_physics_gui, "物理演算ベイクGUI")
        self.tabs.addTab(self.tab_extra, "その他機能")
        self.tabs.addTab(self.tab_cleanup, "MMD削除 (クリーンアップ)")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs)

        # フッタークレジット
        footer = QLabel("MMD Tools for Maya v1.0.5 | Developer: Hina33")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #777; font-size: 13px; padding: 4px;")
        main_layout.addWidget(footer)

    def _on_tab_changed(self, index):
        """タブ切り替え時にプラグイン状態を再確認およびパス同期"""
        if getattr(self, "tab_plugin", None):
            self.tab_plugin.refresh_all_status()
        if getattr(self, "tab_material", None):
            self.tab_material._check_plugin_status()
        if getattr(self, "tab_physics", None):
            self.tab_physics._refresh_bullet_status()
        if getattr(self, "tab_physics_gui", None) and self.tabs.currentWidget() == self.tab_physics_gui:
            self.tab_physics_gui.refresh_all_tab_info()
        if getattr(self, "tab_extra", None):
            self.tab_extra._sync_pmx_path()

    def showEvent(self, e):
        """ウィンドウ表示時にプラグイン状態を最新化およびパス同期"""
        super().showEvent(e)
        if getattr(self, "tab_plugin", None):
            self.tab_plugin.refresh_all_status()
        if getattr(self, "tab_material", None):
            self.tab_material._check_plugin_status()
        if getattr(self, "tab_physics", None):
            self.tab_physics._refresh_bullet_status()
        if getattr(self, "tab_physics_gui", None) and self.tabs.currentWidget() == self.tab_physics_gui:
            self.tab_physics_gui.refresh_all_tab_info()
        if getattr(self, "tab_extra", None):
            self.tab_extra._sync_pmx_path()


    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()

def close_existing_ui():
    """既に表示されているMMD Tools for Mayaウィンドウを検索してすべて閉じます"""
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        try:
            if widget.objectName() == "MmdToolsForMayaMainWindow" or widget.__class__.__name__ == "MmdMayaMainWindow":
                widget.close()
                widget.deleteLater()
        except Exception:
            pass

def show_ui():
    """UIウィンドウを表示します（既に表示されている場合は閉じてから再表示）"""
    global _main_window_instance
    try:
        _reload_ui_submodules()
    except Exception:
        pass
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # 既存ウィンドウを検索して安全に破棄（多重起動防止）
    close_existing_ui()
    _main_window_instance = None

    # プラグインの自動ロード試行
    try:
        if mmd_material_setup:
            mmd_material_setup.ensure_plugin_loaded()
    except Exception:
        pass
    try:
        try:
            from ..bullet_engine import bullet_maya_bridge
        except Exception:
            from bullet_engine import bullet_maya_bridge
        bridge = bullet_maya_bridge.BulletMayaBridge.__new__(bullet_maya_bridge.BulletMayaBridge)
        bridge._ensure_motion_plugin_loaded()
    except Exception:
        pass

    _main_window_instance = MmdMayaMainWindow()
    _main_window_instance.show()
    _main_window_instance.raise_()
    _main_window_instance.activateWindow()
    return _main_window_instance

# ==============================================================================
# 後方互換クラス & エントリポイント
# ==============================================================================
Natanglak = MmdMayaMainWindow
Natang_mmdmaya = ImportTabWidget
Natang_mayammd = ExportTabWidget
Natang_humanik = HikTabWidget
