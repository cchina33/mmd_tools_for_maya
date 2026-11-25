# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MMD Model Editor メインウィンドウモジュール
MMDモデルの材質・モデル属性を編集するための独立ウィンドウ（タブ形式）を提供します。
"""

import sys
import os
import maya.cmds as mc
import maya.api.OpenMaya as om

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QComboBox, QPushButton, QTabWidget, QFrame, QProgressBar
    )
    PYSIDE_VER = 6
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QComboBox, QPushButton, QTabWidget, QFrame, QProgressBar
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

from .tab_info_editor import InfoEditorTabWidget
from .tab_vertex_editor import VertexEditorTabWidget
from .tab_face_editor import FaceEditorTabWidget
from .tab_material_editor import MaterialEditorTabWidget
from .tab_bone_editor import BoneEditorTabWidget
from .tab_morph_editor import MorphEditorTabWidget
from .tab_rigidbody_editor import RigidBodyEditorTabWidget
from .tab_joint_editor import JointEditorTabWidget
try:
    from .tab_modification_editor import ModificationEditorTabWidget
except Exception:
    ModificationEditorTabWidget = None

# 開発中タブ「改造・お着替え (Modification)」の表示制御フラグ（既定: 非表示）
# 開発時に表示する場合は True に変更するか、
# show_model_editor(show_modification_tab=True) または
# mc.optionVar(iv=("mmdToolsShowModificationTab", 1)) を設定してください。
SHOW_MODIFICATION_TAB = False
OPTIONVAR_SHOW_MODIFICATION_TAB = "mmdToolsShowModificationTab"

_model_editor_instance = None


def is_modification_tab_enabled(override=None):
    """改造・お着替えタブを表示するかどうかを設定フラグおよびoptionVarから判定"""
    if override is not None:
        return bool(override)
    try:
        if mc.optionVar(exists=OPTIONVAR_SHOW_MODIFICATION_TAB):
            return bool(mc.optionVar(query=OPTIONVAR_SHOW_MODIFICATION_TAB))
    except Exception:
        pass
    return bool(SHOW_MODIFICATION_TAB)


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


class MmdModelEditorWindow(QDialog):
    """
    MMD Model Editor 独立ウィンドウ
    タブ形式で材質やモデル属性の管理・編集機能を提供します。
    """

    def __init__(self, parent=None, show_modification_tab=None):
        if parent is None:
            parent = get_maya_main_window()
        super(MmdModelEditorWindow, self).__init__(parent)

        self._show_modification_tab = is_modification_tab_enabled(show_modification_tab)
        self.tab_modification = None

        self.setWindowTitle("MMD Model Editor")
        self.setObjectName("MmdModelEditorWindow")
        self.resize(1180, 800)
        self.setMinimumSize(880, 560)

        # Maya子ウィンドウとして設定
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        if MODERN_STYLE:
            self.setStyleSheet(MODERN_STYLE)

        self._init_ui()
        self._refresh_model_list()

    def _init_ui(self):
        """ウィンドウレイアウトの初期化"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 上部ヘッダー（対象モデル選択）
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #242424; border-radius: 6px; padding: 4px;")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(8)

        lbl_model = QLabel("対象MMDモデル:")
        lbl_model.setStyleSheet("font-weight: bold; color: #52b7ff; font-size: 14px;")
        header_layout.addWidget(lbl_model)

        self.cbb_target_model = QComboBox()
        self.cbb_target_model.setMinimumWidth(280)
        self.cbb_target_model.currentIndexChanged.connect(self._on_model_selection_changed)
        header_layout.addWidget(self.cbb_target_model)

        self.btn_refresh_models = QPushButton("モデル再検出")
        self.btn_refresh_models.setFixedWidth(110)
        self.btn_refresh_models.setToolTip("シーン内のMMDモデルを再検出してコンボボックスを更新します。")
        self.btn_refresh_models.clicked.connect(self._refresh_model_list)
        header_layout.addWidget(self.btn_refresh_models)

        self.btn_reload_ui = QPushButton("エディタ再読込")
        self.btn_reload_ui.setFixedWidth(110)
        self.btn_reload_ui.setStyleSheet(
            "QPushButton { background-color: #2b553b; color: #aaffaa; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3b754b; border: 1px solid #77ff77; }"
        )
        self.btn_reload_ui.setToolTip("スクリプトファイルを再読み込み（ホットリロード）して最新状態を即座に反映します。")
        self.btn_reload_ui.clicked.connect(self._reload_editor_and_reopen)
        header_layout.addWidget(self.btn_reload_ui)

        header_layout.addStretch()
        main_layout.addWidget(header_frame)

        # メインタブコンテナ (PMXエディタ準拠配列)
        self.tabs = QTabWidget()

        # 情報 (Info) タブ
        self.tab_info = InfoEditorTabWidget(self)
        self.tabs.addTab(self.tab_info, "情報 (Info)")

        # 頂点 (Vertex) タブ
        self.tab_vertex = VertexEditorTabWidget(self)
        self.tabs.addTab(self.tab_vertex, "頂点 (Vertex)")

        # 面 (Face) タブ
        self.tab_face = FaceEditorTabWidget(self)
        self.tabs.addTab(self.tab_face, "面 (Face)")

        # 材質 (Material) タブ
        self.tab_material = MaterialEditorTabWidget(self)
        self.tabs.addTab(self.tab_material, "材質 (Material)")

        # ボーン (Bone) タブ
        self.tab_bone = BoneEditorTabWidget(self)
        self.tabs.addTab(self.tab_bone, "ボーン (Bone)")

        # モーフ (Morph) タブ
        self.tab_morph = MorphEditorTabWidget(self)
        self.tabs.addTab(self.tab_morph, "モーフ (Morph)")

        # 剛体 (RigidBody) タブ
        self.tab_rigidbody = RigidBodyEditorTabWidget(self)
        self.tabs.addTab(self.tab_rigidbody, "剛体 (RigidBody)")

        # Joint タブ
        self.tab_joint = JointEditorTabWidget(self)
        self.tabs.addTab(self.tab_joint, "Joint")

        # 改造・お着替え (Modification) タブ（開発中のため設定フラグ有効時のみ表示）
        self.tab_modification = None
        if self._show_modification_tab and ModificationEditorTabWidget is not None:
            self.tab_modification = ModificationEditorTabWidget(self)
            self.tabs.addTab(self.tab_modification, "改造・お着替え (Modification)")

        main_layout.addWidget(self.tabs)

        # フッター部
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(4, 2, 4, 2)
        lbl_hint = QLabel("※MMD Model Editor (β1.0) です。変更はMayaシーンへ同期されます。")
        lbl_hint.setStyleSheet("color: #888; font-size: 12px;")
        footer_layout.addWidget(lbl_hint)
        footer_layout.addStretch()

        lbl_ver = QLabel("MMD Tools for Maya | Model Editor")
        lbl_ver.setStyleSheet("color: #666; font-size: 12px;")
        footer_layout.addWidget(lbl_ver)
        main_layout.addLayout(footer_layout)

    def _refresh_model_list(self):
        """シーン内のMMDモデルルートノードのみを正確に検出"""
        self.cbb_target_model.blockSignals(True)
        self.cbb_target_model.clear()

        # シーン内総括選択肢
        self.cbb_target_model.addItem("シーン内の自動検索（特定モデル指定なし）", None)

        found_models = []

        # 除外すべき非モデルノード種別
        excluded_types = {
            "shadingEngine", "material", "lambert", "blinn", "phong",
            "standardSurface", "mmdMaterial", "mmdToonShader", "file",
            "place2dTexture", "camera", "directionalLight", "ambientLight", "joint"
        }

        # 優先判定: mmdModelRoot または mmdModelPath を持つノード
        candidate_nodes = []
        transforms = mc.ls(type="transform") or []
        for tr in transforms:
            n_type = mc.nodeType(tr)
            if n_type in excluded_types:
                continue

            # ジョイントやカメラ、ライトのTransformか確認
            shapes = mc.listRelatives(tr, shapes=True, fullPath=True) or []
            shape_types = {mc.nodeType(s) for s in shapes}
            if shape_types and shape_types.issubset({"camera", "directionalLight", "ambientLight", "pointLight"}):
                continue

            # mmdModelRoot / mmdModelPath / mmdSourceFilePath の存在確認
            is_root = False
            if mc.attributeQuery("mmdModelRoot", node=tr, exists=True):
                is_root = True
            elif mc.attributeQuery("mmdModelPath", node=tr, exists=True):
                is_root = True
            elif mc.attributeQuery("mmdSourceFilePath", node=tr, exists=True):
                is_root = True
            elif any(k in tr.lower() for k in ["pmx", "pmd", "mmd_model"]):
                # 最上位トランスフォーム（親なし）かつメッシュ子孫を持つ
                parent = mc.listRelatives(tr, parent=True)
                if not parent:
                    desc_meshes = mc.listRelatives(tr, allDescendents=True, type="mesh") or []
                    if desc_meshes:
                        is_root = True

            if is_root:
                candidate_nodes.append(tr)

        # 重複除外して登録
        seen = set()
        for node in candidate_nodes:
            if node in seen:
                continue
            seen.add(node)

            # 表示ラベルの決定
            label_name = node
            if mc.attributeQuery("originalName", node=node, exists=True):
                orig = mc.getAttr(f"{node}.originalName")
                if orig:
                    label_name = f"{orig} ({node})"
            found_models.append((label_name, node))

        for label, node_name in found_models:
            self.cbb_target_model.addItem(label, node_name)

        self.cbb_target_model.blockSignals(False)

        # 検出モデルが存在する場合は最初のMMDモデルを選択、なければシーン選択肢
        if len(found_models) > 0:
            self.cbb_target_model.setCurrentIndex(1)
        else:
            self._on_model_selection_changed(self.cbb_target_model.currentIndex())

    def _on_model_selection_changed(self, index):
        """対象モデル変更時のハンドラ"""
        target_node = self.cbb_target_model.itemData(index)
        for tab_attr in [
            "tab_info", "tab_vertex", "tab_face", "tab_material",
            "tab_bone", "tab_morph", "tab_rigidbody", "tab_joint",
            "tab_modification"
        ]:
            tab_obj = getattr(self, tab_attr, None)
            if tab_obj and hasattr(tab_obj, "set_target_model"):
                try:
                    tab_obj.set_target_model(target_node)
                except Exception as e:
                    print(f"[MMD Model Editor 警告] タブ '{tab_attr}' の更新処理で軽微な例外を捕捉: {e}")


    def _reload_editor_and_reopen(self):
        """エディタ関連モジュールを再読み込みし、ウィンドウを再構築"""
        saved_idx = self.cbb_target_model.currentIndex()
        reload_editor_modules()
        new_win = show_model_editor()
        if new_win and saved_idx >= 0 and saved_idx < new_win.cbb_target_model.count():
            new_win.cbb_target_model.setCurrentIndex(saved_idx)


def reload_editor_modules():
    """ui_editor パッケージ配下のモジュールを再読み込み（ホットリロード）"""
    import sys
    import importlib

    mod_names = [
        "tab_info_editor",
        "tab_vertex_editor",
        "tab_face_editor",
        "tab_material_editor",
        "tab_bone_editor",
        "tab_morph_editor",
        "tab_rigidbody_editor",
        "tab_joint_editor",
        "tab_modification_editor",
        "dialog_terms_confirm",
        "dialog_material_filter",
        "dialog_bone_physics_filter",
        "editor_window",
        "ui_editor",
    ]

    all_keys = list(sys.modules.keys())
    for k in all_keys:
        if any(m in k for m in mod_names) and ("ui_editor" in k or k in mod_names):
            m_obj = sys.modules.get(k)
            if m_obj:
                try:
                    importlib.reload(m_obj)
                except Exception:
                    pass


class ModelEditorSplashDialog(QDialog):
    """MMD Model Editor 起動中ローディングインジケータダイアログ"""
    def __init__(self, parent=None):
        if parent is None:
            parent = get_maya_main_window()
        super(ModelEditorSplashDialog, self).__init__(parent)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(360, 140)

        # スタイル設定（モダンダークテーマ、角丸、アクセントブルーボーダー）
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
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #52b7ff;
                border-radius: 3px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        lbl_title = QLabel("MMD Model Editor")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #52b7ff;")
        lbl_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_title)

        self.lbl_status = QLabel("エディタを起動中... しばらくお待ちください")
        self.lbl_status.setStyleSheet("font-size: 12px; color: #cccccc;")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(8)
        layout.addWidget(self.progress)

        self._center_on_parent(parent)

    def _center_on_parent(self, parent):
        """親ウィンドウまたは画面中央に配置"""
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

    def update_status(self, text):
        """進捗ステータスメッセージを更新"""
        self.lbl_status.setText(text)
        QtWidgets.QApplication.processEvents()


# 後方互換クラス名エイリアス
PmxEditorWindow = MmdModelEditorWindow


def show_model_editor(show_modification_tab=None):
    """MMD Model Editor ウィンドウを表示（多重起動防止・起動中ローディング表示対応）"""
    global _model_editor_instance

    # 起動中ローディングダイアログを表示
    splash = None
    try:
        splash = ModelEditorSplashDialog()
        splash.show()
        QtWidgets.QApplication.processEvents()
    except Exception:
        splash = None

    try:
        if splash:
            splash.update_status("エディタモジュールを構成中...")

        if _model_editor_instance is not None:
            try:
                _model_editor_instance.close()
                _model_editor_instance.deleteLater()
            except Exception:
                pass
            _model_editor_instance = None

        if splash:
            splash.update_status("コンポーネントおよびモデル情報を読み込み中...")

        _model_editor_instance = MmdModelEditorWindow(show_modification_tab=show_modification_tab)
        _model_editor_instance.show()
        _model_editor_instance.raise_()
        _model_editor_instance.activateWindow()
        QtWidgets.QApplication.processEvents()
        return _model_editor_instance
    finally:
        # ウィンドウが表示されたら起動中表示を消去
        if splash:
            try:
                splash.close()
                splash.deleteLater()
            except Exception:
                pass


# 後方互換関数名エイリアス
show_pmx_editor = show_model_editor
