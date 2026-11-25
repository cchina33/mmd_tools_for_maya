# -*- coding: utf-8 -*-
"""
MMD照明操作GUIモジュール (dialog_light_control.py)

MMD (MikuMikuDance) 本家の照明操作パネル（赤・緑・青、X・Y・Z、初期化、登録）を忠実に再現します。
モーフ操作ウィンドウと統一されたモダンダークテーマ（#2b2b2b）を採用し、
Mayaビューポート内のディレクショナルライトの角度・カラー、および地面影プレーンの影の向き・長さを
リアルタイムにインタラクティブ操作可能です。
"""

import math
import os

try:
    from PySide6.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QSlider, QDoubleSpinBox, QSpinBox,
        QFrame, QMessageBox
    )
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QFont
except ImportError:
    from PySide2.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QSlider, QDoubleSpinBox, QSpinBox,
        QFrame, QMessageBox
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
    from ..maya_maya_converters import pmxpaimaya
except Exception:
    try:
        from maya_converters import pmxpaimaya
    except Exception:
        pmxpaimaya = None


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


def calculate_euler_from_mmd_light_vector(lx, ly, lz):
    """
    MMDの光線進行方向ベクトル (lx, ly, lz) から、
    Mayaのディレクショナルライト（XYZ回転順序、初期向き -Z）のオイラー回転角 (rx, ry, rz) を算出します。
    """
    length = math.sqrt(lx * lx + ly * ly + lz * lz)
    if length < 1e-6:
        # ベクトル長がゼロに近い場合の保護フォールバック（真下）
        return -90.0, 0.0, 0.0

    nx = lx / length
    ny = ly / length
    nz = lz / length

    # 水平方向の投影長
    horiz_len = math.sqrt(nx * nx + nz * nz)

    # X軸回転（仰角・俯角）: nyが負のとき下向き照光となりrxが負角
    rx = math.degrees(math.atan2(ny, horiz_len))

    # Y軸回転（方位角）: nxと-nzから算出
    ry = math.degrees(math.atan2(nx, -nz))
    rz = 0.0

    return rx, ry, rz


def calculate_mmd_light_vector_from_euler(rx_deg, ry_deg):
    """
    Mayaのディレクショナルライトのオイラー角からMMD光線方向ベクトルを逆算します。
    MMD本家ではY=-1.00を基準とした比率ベクトル（初期値: +0.50, -1.00, -0.50）を扱うため、
    Y成分が0でない場合はY=-1.00基準にスケール換算して返します。
    """
    rx_rad = math.radians(rx_deg)
    ry_rad = math.radians(ry_deg)

    ny = math.sin(rx_rad)
    cos_x = math.cos(rx_rad)

    nx = math.sin(ry_rad) * cos_x
    nz = -math.cos(ry_rad) * cos_x

    # MMD本家基準（Y=-1.00）へのスケール換算
    if abs(ny) > 1e-4:
        scale = abs(1.0 / ny)
        if ny < 0.0:
            nx *= scale
            ny = -1.00
            nz *= scale
        else:
            nx *= scale
            ny = 1.00
            nz *= scale

    return nx, ny, nz


# モーフ操作ウィンドウと統一されたモダンダークテーマスタイルシート
LIGHT_CONTROL_STYLE = """
QDialog#MmdLightControlDialog {
    background-color: #2b2b2b;
    color: #e8e8e8;
    font-family: 'Segoe UI', 'Meiryo UI', 'Yu Gothic UI', sans-serif;
    font-size: 13px;
}

QFrame.light-panel {
    background-color: #242424;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    padding: 8px;
}

QLabel.channel-label {
    color: #e8e8e8;
    font-size: 13px;
    font-weight: bold;
    min-width: 24px;
}

/* スライダーのスタイル */
QSlider::groove:horizontal {
    border: 1px solid #3c3c3c;
    height: 6px;
    background: #1a1a1a;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #52b7ff;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6ec5ff, stop:1 #2d8ac7);
    border: 1px solid #1a1a1a;
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background: #8cd4ff;
    border: 1px solid #ffffff;
}

/* 数値入力ボックス */
QSpinBox, QDoubleSpinBox {
    background-color: #1e1e1e;
    color: #ffffff;
    border: 1px solid #484848;
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 12px;
    font-weight: bold;
    min-width: 60px;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #52b7ff;
}

/* 操作ボタン */
QPushButton.btn-reset {
    background-color: #3a3a3a;
    color: #e0e0e0;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: bold;
}

QPushButton.btn-reset:hover {
    background-color: #4a4a4a;
    border: 1px solid #777777;
    color: #ffffff;
}

QPushButton.btn-register {
    background-color: #0078d4;
    color: #ffffff;
    border: 1px solid #106ebe;
    border-radius: 4px;
    padding: 6px 20px;
    font-size: 13px;
    font-weight: bold;
}

QPushButton.btn-register:hover {
    background-color: #1084d8;
    border: 1px solid #52b7ff;
}

QPushButton.btn-register:pressed {
    background-color: #005a9e;
}
"""


class MmdLightControlDialog(QDialog):
    """
    MMD本家と同等のライティングおよび地面影操作を提供するダイアログウィンドウです。
    """
    _instance = None

    @classmethod
    def get_instance(cls, parent=None):
        """シングルトンインスタンスを取得または生成します"""
        if cls._instance is None:
            if parent is None:
                parent = get_maya_main_window()
            cls._instance = cls(parent=parent)
        return cls._instance

    def __init__(self, parent=None):
        super(MmdLightControlDialog, self).__init__(parent)
        self.setObjectName("MmdLightControlDialog")
        self.setWindowTitle("照明操作")
        self.setFixedWidth(280)
        self.setStyleSheet(LIGHT_CONTROL_STYLE)

        # 内部イベント同期フラグ
        self._updating = False

        self._init_ui()
        self._load_current_scene_lighting()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # パネル枠
        panel_frame = QFrame()
        panel_frame.setObjectName("MainPanel")
        panel_frame.setProperty("class", "light-panel")
        panel_layout = QVBoxLayout(panel_frame)
        panel_layout.setContentsMargins(8, 8, 8, 8)
        panel_layout.setSpacing(8)

        # --- カラー（赤・緑・青）セクション ---
        self.spin_r = QSpinBox()
        self.spin_r.setRange(0, 255)
        self.spin_r.setValue(154)
        self.slider_r = QSlider(Qt.Horizontal)
        self.slider_r.setRange(0, 255)
        self.slider_r.setValue(154)

        self.spin_g = QSpinBox()
        self.spin_g.setRange(0, 255)
        self.spin_g.setValue(154)
        self.slider_g = QSlider(Qt.Horizontal)
        self.slider_g.setRange(0, 255)
        self.slider_g.setValue(154)

        self.spin_b = QSpinBox()
        self.spin_b.setRange(0, 255)
        self.spin_b.setValue(154)
        self.slider_b = QSlider(Qt.Horizontal)
        self.slider_b.setRange(0, 255)
        self.slider_b.setValue(154)

        # --- 方向（X・Y・Z）セクション ---
        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-1.00, 1.00)
        self.spin_x.setSingleStep(0.01)
        self.spin_x.setDecimals(2)
        self.spin_x.setValue(0.50)
        self.slider_x = QSlider(Qt.Horizontal)
        self.slider_x.setRange(-100, 100)
        self.slider_x.setValue(50)

        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-1.00, 1.00)
        self.spin_y.setSingleStep(0.01)
        self.spin_y.setDecimals(2)
        self.spin_y.setValue(-1.00)
        self.slider_y = QSlider(Qt.Horizontal)
        self.slider_y.setRange(-100, 100)
        self.slider_y.setValue(-100)

        self.spin_z = QDoubleSpinBox()
        self.spin_z.setRange(-1.00, 1.00)
        self.spin_z.setSingleStep(0.01)
        self.spin_z.setDecimals(2)
        self.spin_z.setValue(-0.50)
        self.slider_z = QSlider(Qt.Horizontal)
        self.slider_z.setRange(-100, 100)
        self.slider_z.setValue(-50)

        # グリッド配置
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        rows = [
            ("赤", self.slider_r, self.spin_r),
            ("緑", self.slider_g, self.spin_g),
            ("青", self.slider_b, self.spin_b),
            ("Ｘ", self.slider_x, self.spin_x),
            ("Ｙ", self.slider_y, self.spin_y),
            ("Ｚ", self.slider_z, self.spin_z),
        ]

        for row_idx, (label_text, slider_widget, spin_widget) in enumerate(rows):
            lbl = QLabel(label_text)
            lbl.setProperty("class", "channel-label")
            grid.addWidget(lbl, row_idx, 0)
            grid.addWidget(slider_widget, row_idx, 1)
            grid.addWidget(spin_widget, row_idx, 2)

        panel_layout.addLayout(grid)
        main_layout.addWidget(panel_frame)

        # 下部ボタングループ
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_reset = QPushButton("初期化")
        self.btn_reset.setProperty("class", "btn-reset")
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        btn_layout.addWidget(self.btn_reset)

        self.btn_register = QPushButton("登　録")
        self.btn_register.setProperty("class", "btn-register")
        self.btn_register.clicked.connect(self._on_register_clicked)
        btn_layout.addWidget(self.btn_register)

        main_layout.addLayout(btn_layout)

        # シグナルスロット接続
        self._connect_signals()

    def _connect_signals(self):
        """スライダーとスピンボックスの双方向同期およびライト更新イベントを接続"""
        # 赤
        self.slider_r.valueChanged.connect(lambda v: self._sync_spin_from_slider(self.spin_r, v))
        self.spin_r.valueChanged.connect(lambda v: self._sync_slider_from_spin(self.slider_r, v))

        # 緑
        self.slider_g.valueChanged.connect(lambda v: self._sync_spin_from_slider(self.spin_g, v))
        self.spin_g.valueChanged.connect(lambda v: self._sync_slider_from_spin(self.slider_g, v))

        # 青
        self.slider_b.valueChanged.connect(lambda v: self._sync_spin_from_slider(self.spin_b, v))
        self.spin_b.valueChanged.connect(lambda v: self._sync_slider_from_spin(self.slider_b, v))

        # X
        self.slider_x.valueChanged.connect(lambda v: self._sync_double_spin_from_slider(self.spin_x, v))
        self.spin_x.valueChanged.connect(lambda v: self._sync_slider_from_double_spin(self.slider_x, v))

        # Y
        self.slider_y.valueChanged.connect(lambda v: self._sync_double_spin_from_slider(self.spin_y, v))
        self.spin_y.valueChanged.connect(lambda v: self._sync_slider_from_double_spin(self.slider_y, v))

        # Z
        self.slider_z.valueChanged.connect(lambda v: self._sync_double_spin_from_slider(self.spin_z, v))
        self.spin_z.valueChanged.connect(lambda v: self._sync_slider_from_double_spin(self.slider_z, v))

    def _sync_spin_from_slider(self, spin_widget, val):
        if self._updating:
            return
        self._updating = True
        spin_widget.setValue(val)
        self._updating = False
        self._apply_lighting_to_scene()

    def _sync_slider_from_spin(self, slider_widget, val):
        if self._updating:
            return
        self._updating = True
        slider_widget.setValue(val)
        self._updating = False
        self._apply_lighting_to_scene()

    def _sync_double_spin_from_slider(self, spin_widget, val):
        if self._updating:
            return
        self._updating = True
        spin_widget.setValue(val / 100.0)
        self._updating = False
        self._apply_lighting_to_scene()

    def _sync_slider_from_double_spin(self, slider_widget, val):
        if self._updating:
            return
        self._updating = True
        slider_widget.setValue(int(round(val * 100.0)))
        self._updating = False
        self._apply_lighting_to_scene()

    def _get_target_directional_light(self):
        """シーン内のMMDディレクショナルライトを取得します（未作成時は自動作成）"""
        if not mc:
            return None, None

        dir_shapes = mc.ls("mmd_directional_light*Shape*", type="directionalLight") or []
        if not dir_shapes:
            # 一般のディレクショナルライトを検索
            all_dir_shapes = mc.ls(type="directionalLight") or []
            if all_dir_shapes:
                dir_shapes = all_dir_shapes

        if not dir_shapes:
            # ライトが存在しない場合は自動作成
            if pmxpaimaya and hasattr(pmxpaimaya, "create_mmd_lighting"):
                pmxpaimaya.create_mmd_lighting(shadow_mode=1)
                dir_shapes = mc.ls("mmd_directional_light*Shape*", type="directionalLight") or []

        if not dir_shapes:
            return None, None

        shape = dir_shapes[0]
        parents = mc.listRelatives(shape, parent=True, fullPath=True) or [shape]
        transform = parents[0]
        return transform, shape

    def _load_current_scene_lighting(self):
        """現在のシーンのライト設定を読み込んでUIへ反映します"""
        if not mc:
            return

        transform, shape = self._get_target_directional_light()
        if not transform or not shape:
            return

        self._updating = True
        try:
            # カラーの取得 (0.0〜1.0 -> 0〜255)
            color_vals = mc.getAttr(f"{shape}.color")[0]
            r = int(round(color_vals[0] * 255.0))
            g = int(round(color_vals[1] * 255.0))
            b = int(round(color_vals[2] * 255.0))

            self.slider_r.setValue(r)
            self.spin_r.setValue(r)
            self.slider_g.setValue(g)
            self.spin_g.setValue(g)
            self.slider_b.setValue(b)
            self.spin_b.setValue(b)

            # 回転角の取得
            rx = mc.getAttr(f"{transform}.rotateX")
            ry = mc.getAttr(f"{transform}.rotateY")

            # MMD照明カスタム属性が存在する場合は優先取得
            has_custom_attr = (
                mc.attributeQuery("mmdLightX", node=transform, exists=True) and
                mc.attributeQuery("mmdLightY", node=transform, exists=True) and
                mc.attributeQuery("mmdLightZ", node=transform, exists=True)
            )
            if has_custom_attr:
                nx = mc.getAttr(f"{transform}.mmdLightX")
                ny = mc.getAttr(f"{transform}.mmdLightY")
                nz = mc.getAttr(f"{transform}.mmdLightZ")
            else:
                # オイラー角からの逆算（Y=-1.00基準スケール換算）
                nx, ny, nz = calculate_mmd_light_vector_from_euler(rx, ry)

            self.spin_x.setValue(round(nx, 2))
            self.slider_x.setValue(int(round(nx * 100.0)))
            self.spin_y.setValue(round(ny, 2))
            self.slider_y.setValue(int(round(ny * 100.0)))
            self.spin_z.setValue(round(nz, 2))
            self.slider_z.setValue(int(round(nz * 100.0)))
        except Exception:
            pass
        finally:
            self._updating = False

    def _apply_lighting_to_scene(self):
        """UIの現在の設定値をMayaシーンのライトへリアルタイム反映します"""
        if not mc:
            return

        transform, shape = self._get_target_directional_light()
        if not transform or not shape:
            return

        # カラーの反映
        cr = self.spin_r.value() / 255.0
        cg = self.spin_g.value() / 255.0
        cb = self.spin_b.value() / 255.0

        # 方向ベクトルの算出
        lx = self.spin_x.value()
        ly = self.spin_y.value()
        lz = self.spin_z.value()

        rx, ry, rz = calculate_euler_from_mmd_light_vector(lx, ly, lz)

        try:
            mc.setAttr(f"{shape}.color", cr, cg, cb, typ='double3')
            mc.setAttr(f"{transform}.rotate", rx, ry, rz, typ='double3')

            # MMD照明カスタム属性の同期
            if mc.attributeQuery("mmdLightX", node=transform, exists=True):
                mc.setAttr(f"{transform}.mmdLightX", lx)
            if mc.attributeQuery("mmdLightY", node=transform, exists=True):
                mc.setAttr(f"{transform}.mmdLightY", ly)
            if mc.attributeQuery("mmdLightZ", node=transform, exists=True):
                mc.setAttr(f"{transform}.mmdLightZ", lz)

            # ビューポートのリフレッシュ
            mc.refresh(force=True)
        except Exception:
            pass

    def _on_reset_clicked(self):
        """初期化ボタン: MMD標準の初期状態にリセットします"""
        self._updating = True
        # MMD標準初期値: RGB 154, XYZ (+0.50, -1.00, -0.50)
        self.slider_r.setValue(154)
        self.spin_r.setValue(154)
        self.slider_g.setValue(154)
        self.spin_g.setValue(154)
        self.slider_b.setValue(154)
        self.spin_b.setValue(154)

        self.spin_x.setValue(0.50)
        self.slider_x.setValue(50)
        self.spin_y.setValue(-1.00)
        self.slider_y.setValue(-100)
        self.spin_z.setValue(-0.50)
        self.slider_z.setValue(-50)

        self._updating = False
        self._apply_lighting_to_scene()

    def _on_register_clicked(self):
        """登録ボタン: 現在のタイムラインフレームにキーフレームを設定します"""
        if not mc:
            return

        transform, shape = self._get_target_directional_light()
        if not transform or not shape:
            QMessageBox.warning(self, "登録エラー", "操作対象のディレクショナルライトが見つかりません。")
            return

        current_frame = mc.currentTime(query=True)

        try:
            # 回転のキーフレーム設定
            mc.setKeyframe(transform, attribute="rotateX")
            mc.setKeyframe(transform, attribute="rotateY")
            mc.setKeyframe(transform, attribute="rotateZ")

            # カラーのキーフレーム設定
            mc.setKeyframe(shape, attribute="colorR")
            mc.setKeyframe(shape, attribute="colorG")
            mc.setKeyframe(shape, attribute="colorB")

            print(f"[MMD照明操作] フレーム {int(current_frame)} に照明キーフレームを登録しました。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"キーフレームの登録中にエラーが発生しました: {e}")

    def closeEvent(self, event):
        """ウィンドウ終了時のインスタンス解放"""
        MmdLightControlDialog._instance = None
        event.accept()


def show_mmd_light_control_dialog(parent=None):
    """ダイアログを表示するエントリポイント"""
    dlg = MmdLightControlDialog.get_instance(parent=parent)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg

