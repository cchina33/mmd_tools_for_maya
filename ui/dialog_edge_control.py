# -*- coding: utf-8 -*-
"""
MMDエッジ太さ操作GUIモジュール (dialog_edge_control.py)

シーン内の MMD モデル（単一メッシュ構成）の輪郭線（エッジ）の太さを、
スライダーや数値入力によりリアルタイムに一括調整するための操作パネルを提供します。
"""

import os
import sys

try:
    from PySide6.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QSlider, QDoubleSpinBox, QCheckBox,
        QComboBox, QGroupBox, QFrame, QMessageBox, QApplication
    )
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QFont
except ImportError:
    from PySide2.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QSlider, QDoubleSpinBox, QCheckBox,
        QComboBox, QGroupBox, QFrame, QMessageBox, QApplication
    )
    from PySide2.QtCore import Qt, Signal
    from PySide2.QtGui import QFont

try:
    import maya.cmds as mc
    import maya.OpenMayaUI as omui
except ImportError:
    mc = None
    omui = None

try:
    from ..maya_maya_converters import vmdpaimaya
except Exception:
    try:
        from maya_converters import vmdpaimaya
    except Exception:
        vmdpaimaya = None


def get_maya_main_window():
    """MayaのメインウィンドウをPySideウィジェットとして取得します"""
    if not omui:
        return None
    ptr = omui.MQtUtil.mainWindow()
    if not ptr:
        return None
    try:
        from shiboken6 import wrapInstance
        return wrapInstance(int(ptr), QWidget)
    except ImportError:
        try:
            from shiboken2 import wrapInstance
            return wrapInstance(int(ptr), QWidget)
        except ImportError:
            return None


class MmdEdgeControlDialog(QDialog):
    """MMDモデルのエッジ太さをリアルタイムに一括調整するダイアログ"""

    def __init__(self, parent=None):
        if parent is None:
            parent = get_maya_main_window()
        super(MmdEdgeControlDialog, self).__init__(parent)

        self.setWindowTitle("MMD エッジ太さ操作")
        self.resize(460, 320)
        self.setMinimumSize(420, 280)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        # マテリアル初期値の保持用キャッシュ辞書
        self._base_edge_sizes = {}
        self._is_updating_ui = False

        self._init_ui()
        self._refresh_models()

    def _init_ui(self):
        # ウィンドウスタイルシート設定
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #444444;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 12px;
                background-color: #333333;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: #52b7ff;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
            }
            QComboBox {
                background-color: #222222;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QDoubleSpinBox {
                background-color: #222222;
                color: #52b7ff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
                font-weight: bold;
                font-size: 13px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #222222;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #2980b9;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #52b7ff;
                border: 1px solid #ffffff;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
            QCheckBox {
                color: #ffffff;
                font-size: 12px;
            }
            QPushButton {
                background-color: #383838;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #484848;
                border-color: #777777;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(14, 14, 14, 14)

        # 対象モデル選択グループ
        target_box = QGroupBox("調整対象モデル")
        target_layout = QHBoxLayout(target_box)
        target_layout.setSpacing(8)

        self.cbb_target = QComboBox()
        self.cbb_target.currentIndexChanged.connect(self._on_target_changed)
        target_layout.addWidget(self.cbb_target, stretch=1)

        self.btn_refresh = QPushButton("更新")
        self.btn_refresh.setFixedWidth(65)
        self.btn_refresh.clicked.connect(self._refresh_models)
        target_layout.addWidget(self.btn_refresh)

        main_layout.addWidget(target_box)

        # エッジ太さ調整グループ
        edge_box = QGroupBox("エッジ（輪郭線）太さ調整")
        edge_layout = QVBoxLayout(edge_box)
        edge_layout.setSpacing(10)

        # エッジ表示ON/OFFチェックボックス
        self.cb_edge_enable = QCheckBox("エッジ輪郭線を表示する (edgeEnable)")
        self.cb_edge_enable.setChecked(True)
        self.cb_edge_enable.toggled.connect(self._on_edge_enable_toggled)
        edge_layout.addWidget(self.cb_edge_enable)

        # スライダーとスピンボックスのレイアウト
        h_slider_layout = QHBoxLayout()
        h_slider_layout.setSpacing(10)

        lbl_scale = QLabel("太さ倍率:")
        lbl_scale.setFixedWidth(65)
        h_slider_layout.addWidget(lbl_scale)

        # スライダー (0〜500 -> 0.00〜5.00倍)
        self.slider_width = QSlider(Qt.Horizontal)
        self.slider_width.setRange(0, 500)
        self.slider_width.setValue(100)
        self.slider_width.valueChanged.connect(self._on_slider_changed)
        h_slider_layout.addWidget(self.slider_width, stretch=1)

        # スピンボックス (0.00〜10.00倍)
        self.sp_width = QDoubleSpinBox()
        self.sp_width.setRange(0.0, 10.0)
        self.sp_width.setSingleStep(0.05)
        self.sp_width.setValue(1.0)
        self.sp_width.setFixedWidth(80)
        self.sp_width.valueChanged.connect(self._on_spin_changed)
        h_slider_layout.addWidget(self.sp_width)

        edge_layout.addLayout(h_slider_layout)

        # 補助説明ラベル
        self.lbl_status = QLabel("※スライダーを動かすとビューポート上の輪郭線がリアルタイムに変化します。")
        self.lbl_status.setStyleSheet("color: #999999; font-size: 11px;")
        edge_layout.addWidget(self.lbl_status)

        main_layout.addWidget(edge_box)

        # ボタンエリア
        h_btn_layout = QHBoxLayout()
        h_btn_layout.setSpacing(8)

        self.btn_reset = QPushButton("初期値（1.0倍）に戻す")
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background-color: #2c3e50;
                color: #ffffff;
                border: 1px solid #34495e;
            }
            QPushButton:hover {
                background-color: #34495e;
            }
        """)
        self.btn_reset.clicked.connect(self._reset_to_default)
        h_btn_layout.addWidget(self.btn_reset)

        h_btn_layout.addStretch()

        self.btn_close = QPushButton("閉じる")
        self.btn_close.setFixedWidth(90)
        self.btn_close.clicked.connect(self.close)
        h_btn_layout.addWidget(self.btn_close)

        main_layout.addLayout(h_btn_layout)

    def _refresh_models(self):
        """シーン内のMMDモデル一覧を取得してコンボボックスを更新"""
        self.cbb_target.blockSignals(True)
        self.cbb_target.clear()

        self.cbb_target.addItem("シーン内のMMDモデル（モデル選択）", "__ALL_MMD__")

        if vmdpaimaya:
            try:
                models = vmdpaimaya.get_available_mmd_models()
                for item in models:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        node_name, label = item[0], item[1]
                    else:
                        node_name = str(item)
                        label = node_name
                    self.cbb_target.addItem(f"モデル: {label}", node_name)
            except Exception:
                pass

        # 選択中オブジェクト項目
        self.cbb_target.addItem("現在選択中のオブジェクト / メッシュ", "__SELECTION__")

        self.cbb_target.blockSignals(False)
        self._on_target_changed(0)

    def _get_target_shaders(self):
        """現在選択されている対象に応じたマテリアルシェーダーの一覧を取得"""
        if not mc:
            return []

        target_data = self.cbb_target.currentData()
        shaders = set()

        if target_data == "__ALL_MMD__":
            # シーン内のMMD専用シェーダーノードを網羅的に収集
            for node_type in ["mmdMaterial", "mmdToonShader"]:
                found = mc.ls(type=node_type) or []
                shaders.update(found)
        elif target_data == "__SELECTION__":
            sel = mc.ls(selection=True) or []
            if sel:
                # 選択オブジェクト配下のメッシュを収集
                shapes = mc.listRelatives(sel, shapes=True, path=True) or []
                meshes = [s for s in shapes if mc.nodeType(s) == 'mesh']
                for item in sel:
                    if mc.nodeType(item) == 'mesh':
                        meshes.append(item)
                # メッシュに接続された ShadingEngine を探索
                for m in meshes:
                    sgs = mc.listConnections(m, type='shadingEngine') or []
                    for sg in sgs:
                        shds = mc.listConnections(f"{sg}.surfaceShader") or []
                        for shd in shds:
                            if mc.attributeQuery("edgeSize", node=shd, exists=True):
                                shaders.add(shd)
        else:
            # 特定モデルノード配下のメッシュを探索
            model_node = str(target_data)
            if mc.objExists(model_node):
                shapes = mc.listRelatives(model_node, allDescendents=True, shapes=True, path=True) or []
                meshes = [s for s in shapes if mc.nodeType(s) == 'mesh']
                for m in meshes:
                    sgs = mc.listConnections(m, type='shadingEngine') or []
                    for sg in sgs:
                        shds = mc.listConnections(f"{sg}.surfaceShader") or []
                        for shd in shds:
                            if mc.attributeQuery("edgeSize", node=shd, exists=True):
                                shaders.add(shd)

        # 万一検出ゼロの場合、シーン内のエッジ属性所持ノードをフォールバック収集
        if not shaders:
            for node_type in ["mmdMaterial", "mmdToonShader"]:
                found = mc.ls(type=node_type) or []
                shaders.update(found)

        return sorted(list(shaders))

    def _on_target_changed(self, index):
        """対象モデル切り替え時にマテリアル初期値をキャッシュ"""
        shaders = self._get_target_shaders()
        self._base_edge_sizes.clear()

        if mc:
            for shd in shaders:
                if mc.attributeQuery("edgeSize", node=shd, exists=True):
                    try:
                        cur_size = mc.getAttr(f"{shd}.edgeSize")
                        self._base_edge_sizes[shd] = float(cur_size)
                    except Exception:
                        self._base_edge_sizes[shd] = 1.0

        count = len(self._base_edge_sizes)
        self.lbl_status.setText(f"検出マテリアル数: {count} 件（スライダー操作で即座に反映されます）")

    def _on_slider_changed(self, value):
        """スライダー値変更時にスピンボックスへ同期しエッジ太さを適用"""
        if self._is_updating_ui:
            return
        multiplier = value / 100.0
        self._is_updating_ui = True
        self.sp_width.setValue(multiplier)
        self._is_updating_ui = False
        self._apply_edge_scale(multiplier)

    def _on_spin_changed(self, value):
        """スピンボックス値変更時にスライダーへ同期しエッジ太さを適用"""
        if self._is_updating_ui:
            return
        slider_val = int(round(value * 100))
        self._is_updating_ui = True
        self.slider_width.setValue(min(max(slider_val, 0), 500))
        self._is_updating_ui = False
        self._apply_edge_scale(value)

    def _apply_edge_scale(self, multiplier):
        """対象シェーダーの edgeSize を一括乗算更新しビューポートを即座に再描画"""
        if not mc or not self._base_edge_sizes:
            return

        for shd, base_size in self._base_edge_sizes.items():
            if mc.objExists(shd) and mc.attributeQuery("edgeSize", node=shd, exists=True):
                try:
                    new_size = max(0.0, base_size * multiplier)
                    mc.setAttr(f"{shd}.edgeSize", new_size)
                except Exception:
                    pass

        try:
            mc.refresh()
        except Exception:
            pass

    def _on_edge_enable_toggled(self, checked):
        """エッジ表示/非表示（edgeEnable）の一括切り替え"""
        if not mc:
            return

        shaders = self._get_target_shaders()
        for shd in shaders:
            if mc.objExists(shd) and mc.attributeQuery("edgeEnable", node=shd, exists=True):
                try:
                    mc.setAttr(f"{shd}.edgeEnable", checked)
                except Exception:
                    pass

        try:
            mc.refresh()
        except Exception:
            pass

    def _reset_to_default(self):
        """標準の太さ倍率（1.0倍）へ復元"""
        self._is_updating_ui = True
        self.slider_width.setValue(100)
        self.sp_width.setValue(1.0)
        self.cb_edge_enable.setChecked(True)
        self._is_updating_ui = False

        self._apply_edge_scale(1.0)
        self._on_edge_enable_toggled(True)


# ダイアログシングルトン参照保持用
_edge_control_dialog_instance = None


def show_mmd_edge_control_dialog(parent=None):
    """MMDエッジ太さ操作ダイアログを起動または前面表示します"""
    global _edge_control_dialog_instance
    if _edge_control_dialog_instance is not None:
        try:
            _edge_control_dialog_instance.close()
            _edge_control_dialog_instance.deleteLater()
        except Exception:
            pass
        _edge_control_dialog_instance = None

    _edge_control_dialog_instance = MmdEdgeControlDialog(parent=parent)
    _edge_control_dialog_instance.show()
    return _edge_control_dialog_instance
