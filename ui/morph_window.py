# -*- coding: utf-8 -*-
"""
MMD表情操作モーフGUIモジュール (morph_window.py)

MMD Tools for Maya のメインGUIと統一されたモダンダークテーマを採用。
Maya上のBlendShapeターゲットウェイトを直感的に操作・キーフレーム登録できるUIを提供します。
ウィンドウはQWidgetベースのモードレスウィンドウとし、他アプリ（ブラウザ等）の背面に適切に隠れる設計です。
"""

import os
import json
import re

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QComboBox, QSlider, QLineEdit,
        QMessageBox, QFrame, QSizePolicy, QInputDialog
    )
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QDoubleValidator, QFont
except ImportError:
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QComboBox, QSlider, QLineEdit,
        QMessageBox, QFrame, QSizePolicy, QInputDialog
    )
    from PySide2.QtCore import Qt, Signal
    from PySide2.QtGui import QDoubleValidator, QFont

try:
    import maya.cmds as mc
    import maya.OpenMayaUI as omui
except ImportError:
    mc = None
    omui = None


def get_maya_main_window():
    """MayaのメインウィンドウをPySideウィジェットとして取得"""
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


# 矢印アイコンパスの動的解決（gui_style.py と同一仕様）
_script_dir = os.path.dirname(os.path.abspath(__file__))
_image_dir = os.path.abspath(os.path.join(_script_dir, "..", "image")).replace("\\", "/")
_arrow_icon = f"{_image_dir}/arrow_down.png"
_arrow_hover_icon = f"{_image_dir}/arrow_down_hover.png"

# メインGUI（MMD Tools for Maya）と統一されたモダンダークテーマQSS
MODERN_DARK_STYLE = f"""
QWidget#MorphMainWindow {{
    background-color: #2b2b2b;
    color: #e8e8e8;
    font-family: 'Segoe UI', 'Meiryo UI', 'Yu Gothic UI', sans-serif;
    font-size: 13px;
}}

/* 各表情パネルカード */
QFrame.morph-card {{
    background-color: #242424;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
}}
QFrame.morph-card:hover {{
    border: 1px solid #52b7ff;
}}

/* カテゴリタイトル（目、リップ、まゆ、その他） */
QLabel.card-title {{
    color: #52b7ff;
    font-size: 14px;
    font-weight: bold;
}}

/* 数値入力ボックス */
QLineEdit.val-box {{
    background-color: #1e1e1e;
    color: #ffffff;
    border: 1px solid #484848;
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 13px;
    font-weight: bold;
    selection-background-color: #0078d4;
}}
QLineEdit.val-box:focus {{
    border: 1px solid #52b7ff;
    background-color: #181818;
}}

/* 「登　録」ボタン */
QPushButton.btn-register {{
    background-color: #383838;
    color: #ffffff;
    border: 1px solid #505050;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 12px;
    font-weight: bold;
}}
QPushButton.btn-register:hover {{
    background-color: #0078d4;
    border: 1px solid #52b7ff;
    color: #ffffff;
}}
QPushButton.btn-register:pressed {{
    background-color: #005a9e;
}}

/* 切替ボタン（<< / >>） */
QPushButton.btn-nav {{
    background-color: #383838;
    color: #ffffff;
    border: 1px solid #505050;
    border-radius: 4px;
    font-size: 12px;
    font-weight: bold;
}}
QPushButton.btn-nav:hover {{
    background-color: #0078d4;
    border: 1px solid #52b7ff;
    color: #ffffff;
}}
QPushButton.btn-nav:pressed {{
    background-color: #005a9e;
}}

/* コンボボックス */
QComboBox.morph-combo {{
    background-color: #2e2e2e;
    color: #ffffff;
    border: 1px solid #505050;
    border-radius: 4px;
    padding: 3px 28px 3px 8px;
    font-size: 13px;
    font-weight: 500;
}}
QComboBox.morph-combo:hover {{
    border: 1px solid #52b7ff;
    background-color: #383838;
}}
QComboBox.morph-combo:focus {{
    border: 1px solid #52b7ff;
}}
QComboBox.morph-combo::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #444444;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
    background-color: #333333;
}}
QComboBox.morph-combo::drop-down:hover {{
    background-color: #404040;
}}
QComboBox.morph-combo::down-arrow {{
    image: url('{_arrow_icon}');
    width: 12px;
    height: 12px;
}}
QComboBox.morph-combo::down-arrow:hover {{
    image: url('{_arrow_hover_icon}');
}}
QComboBox.morph-combo QAbstractItemView {{
    background-color: #242424;
    border: 1px solid #52b7ff;
    border-radius: 4px;
    color: #ffffff;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
    font-size: 13px;
    padding: 2px;
    outline: none;
}}
QComboBox.morph-combo QAbstractItemView::item {{
    min-height: 24px;
    padding: 3px 8px;
}}

/* スライダー */
QSlider::groove:horizontal {{
    height: 4px;
    background: #3c3c3c;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: #52b7ff;
    border-radius: 2px;
}}
QSlider::add-page:horizontal {{
    background: #3c3c3c;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #52b7ff;
    border: 2px solid #ffffff;
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: #7eccff;
    border: 2px solid #ffffff;
}}

/* ヘッダー更新ボタン */
QPushButton.btn-header {{
    background-color: #383838;
    color: #e0e0e0;
    border: 1px solid #505050;
    border-radius: 4px;
    font-size: 12px;
    padding: 3px 8px;
}}
QPushButton.btn-header:hover {{
    background-color: #52b7ff;
    color: #ffffff;
    border: 1px solid #7eccff;
}}

/* 自作表情プリセットカード */
QFrame.preset-card {{
    background-color: #242424;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
}}
QFrame.preset-card:hover {{
    border: 1px solid #52b7ff;
}}

/* プリセット用小型ボタン */
QPushButton.btn-preset {{
    background-color: #333333;
    color: #e0e0e0;
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    font-size: 11px;
    padding: 3px 6px;
}}
QPushButton.btn-preset:hover {{
    background-color: #444444;
    color: #ffffff;
    border-color: #52b7ff;
}}
QPushButton.btn-preset-primary {{
    background-color: #0078d4;
    color: #ffffff;
    border: 1px solid #0090ff;
    border-radius: 4px;
    font-size: 11px;
    padding: 3px 7px;
    font-weight: bold;
}}
QPushButton.btn-preset-primary:hover {{
    background-color: #1084e3;
}}
QPushButton.btn-preset-danger {{
    background-color: #422424;
    color: #ff9999;
    border: 1px solid #5e3232;
    border-radius: 4px;
    font-size: 11px;
    padding: 3px 6px;
}}
QPushButton.btn-preset-danger:hover {{
    background-color: #5e2828;
    color: #ffffff;
}}
"""


class MorphPanelUnit(QFrame):
    """
    1つの表情カテゴリ（まゆ、目、リップ、その他）を操作するカードパネル
    """
    weightChanged = Signal(str, float)
    registerKeyRequested = Signal(str, float)

    def __init__(self, title, panel_id, parent=None):
        super().__init__(parent)
        self.setProperty("class", "morph-card")
        self.title = title
        self.panel_id = panel_id
        self.morph_items = []  # [(display_name, target_attr, bs_node)]
        self._is_updating = False

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # 最上段：タイトル、数値ボックス、登録ボタン
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.lbl_title = QLabel(self.title)
        self.lbl_title.setProperty("class", "card-title")
        self.lbl_title.setFixedWidth(52)

        self.le_val = QLineEdit("0.000")
        self.le_val.setProperty("class", "val-box")
        self.le_val.setFixedWidth(60)
        self.le_val.setFixedHeight(26)
        self.le_val.setAlignment(Qt.AlignCenter)
        validator = QDoubleValidator(0.0, 1.0, 3, self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.le_val.setValidator(validator)
        self.le_val.editingFinished.connect(self._on_text_value_committed)

        self.btn_register = QPushButton("登　録")
        self.btn_register.setProperty("class", "btn-register")
        self.btn_register.setFixedWidth(60)
        self.btn_register.setFixedHeight(26)
        self.btn_register.setToolTip("現在のフレームにこの表情のウェイト値をキーフレーム登録します")
        self.btn_register.clicked.connect(self._on_register_clicked)

        top_row.addWidget(self.lbl_title)
        top_row.addWidget(self.le_val)
        top_row.addWidget(self.btn_register)
        top_row.addStretch()
        layout.addLayout(top_row)

        # 中段：<< ボタン、コンボボックス、>> ボタン
        mid_row = QHBoxLayout()
        mid_row.setSpacing(4)

        self.btn_prev = QPushButton("<<")
        self.btn_prev.setProperty("class", "btn-nav")
        self.btn_prev.setFixedSize(30, 26)
        self.btn_prev.setToolTip("前のモーフへ切り替え")
        self.btn_prev.clicked.connect(self._on_prev_morph)

        self.cmb_morph = QComboBox()
        self.cmb_morph.setProperty("class", "morph-combo")
        self.cmb_morph.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cmb_morph.setFixedHeight(26)
        self.cmb_morph.currentIndexChanged.connect(self._on_morph_selection_changed)

        self.btn_next = QPushButton(">>")
        self.btn_next.setProperty("class", "btn-nav")
        self.btn_next.setFixedSize(30, 26)
        self.btn_next.setToolTip("次のモーフへ切り替え")
        self.btn_next.clicked.connect(self._on_next_morph)

        mid_row.addWidget(self.btn_prev)
        mid_row.addWidget(self.cmb_morph)
        mid_row.addWidget(self.btn_next)
        layout.addLayout(mid_row)

        # 最下段：スライダーおよび目盛り線
        slider_layout = QVBoxLayout()
        slider_layout.setSpacing(2)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setValue(0)
        self.slider.valueChanged.connect(self._on_slider_value_changed)
        slider_layout.addWidget(self.slider)

        # 目盛り表示（0.0, 0.5, 1.0）
        ticks_row = QHBoxLayout()
        ticks_row.setContentsMargins(6, 0, 6, 0)
        lbl_tick_left = QLabel("0.0")
        lbl_tick_left.setStyleSheet("color: #777777; font-size: 9px;")
        lbl_tick_mid = QLabel("0.5")
        lbl_tick_mid.setStyleSheet("color: #777777; font-size: 9px;")
        lbl_tick_right = QLabel("1.0")
        lbl_tick_right.setStyleSheet("color: #777777; font-size: 9px;")

        ticks_row.addWidget(lbl_tick_left, 0, Qt.AlignLeft)
        ticks_row.addWidget(lbl_tick_mid, 0, Qt.AlignCenter)
        ticks_row.addWidget(lbl_tick_right, 0, Qt.AlignRight)
        slider_layout.addLayout(ticks_row)

        layout.addLayout(slider_layout)

    def set_morphs(self, morph_list):
        """
        モーフ一覧を登録
        morph_list: [(display_name, target_attr, bs_node), ...]
        """
        self._is_updating = True
        self.morph_items = morph_list
        self.cmb_morph.clear()
        for item in self.morph_items:
            self.cmb_morph.addItem(item[0])

        self._is_updating = False
        if self.morph_items:
            self._update_current_morph_value()
        else:
            self.le_val.setText("0.000")
            self.slider.setValue(0)

    def _on_morph_selection_changed(self, index):
        if self._is_updating or index < 0:
            return
        self._update_current_morph_value()

    def _update_current_morph_value(self):
        """Mayaシーンから現在選択されているモーフのウェイト値を取得して反映"""
        idx = self.cmb_morph.currentIndex()
        if idx < 0 or idx >= len(self.morph_items):
            return

        item = self.morph_items[idx]
        target_attr = item[1]
        bs_node = item[2]

        current_val = 0.0
        if mc and bs_node and target_attr:
            full_attr = f"{bs_node}.{target_attr}"
            if mc.objExists(full_attr):
                try:
                    current_val = float(mc.getAttr(full_attr))
                except Exception:
                    current_val = 0.0

        self._is_updating = True
        slider_val = int(round(current_val * 1000.0))
        self.slider.setValue(max(0, min(1000, slider_val)))
        self.le_val.setText(f"{current_val:.3f}")
        self._is_updating = False

    def _on_slider_value_changed(self, value):
        if self._is_updating:
            return

        float_val = value / 1000.0
        self._is_updating = True
        self.le_val.setText(f"{float_val:.3f}")
        self._is_updating = False

        self._apply_weight_to_maya(float_val)

    def _on_text_value_committed(self):
        if self._is_updating:
            return

        try:
            val = float(self.le_val.text().strip())
        except ValueError:
            val = 0.0

        val = max(0.0, min(1.0, val))
        self._is_updating = True
        self.slider.setValue(int(round(val * 1000.0)))
        self.le_val.setText(f"{val:.3f}")
        self._is_updating = False

        self._apply_weight_to_maya(val)

    def _apply_weight_to_maya(self, val):
        idx = self.cmb_morph.currentIndex()
        if idx < 0 or idx >= len(self.morph_items):
            return

        item = self.morph_items[idx]
        target_attr = item[1]
        bs_node = item[2]

        if mc and bs_node and target_attr:
            full_attr = f"{bs_node}.{target_attr}"
            if mc.objExists(full_attr):
                try:
                    mc.setAttr(full_attr, val)
                except Exception as e:
                    print(f"[表情操作] ウェイト反映エラー ({full_attr}): {e}")

        self.weightChanged.emit(target_attr, val)

    def _on_prev_morph(self):
        count = self.cmb_morph.count()
        if count <= 1:
            return
        cur = self.cmb_morph.currentIndex()
        nxt = (cur - 1) % count
        self.cmb_morph.setCurrentIndex(nxt)

    def _on_next_morph(self):
        count = self.cmb_morph.count()
        if count <= 1:
            return
        cur = self.cmb_morph.currentIndex()
        nxt = (cur + 1) % count
        self.cmb_morph.setCurrentIndex(nxt)

    def _on_register_clicked(self):
        """カレントフレームにキーフレームを打つ"""
        idx = self.cmb_morph.currentIndex()
        if idx < 0 or idx >= len(self.morph_items):
            return

        item = self.morph_items[idx]
        target_attr = item[1]
        bs_node = item[2]

        try:
            val = float(self.le_val.text().strip())
        except ValueError:
            val = 0.0

        if mc and bs_node and target_attr:
            full_attr = f"{bs_node}.{target_attr}"
            if mc.objExists(full_attr):
                try:
                    mc.setKeyframe(full_attr, value=val)
                    print(f"[表情操作] キーフレーム登録完了: {full_attr} = {val:.3f}")
                except Exception as e:
                    print(f"[表情操作] キーフレーム登録エラー ({full_attr}): {e}")

        self.registerKeyRequested.emit(target_attr, val)

    def get_current_morph_info(self):
        """現在選択中のモーフ情報 (表示名, アトリビュート名, ノード名, 現在ウェイト値) を取得"""
        idx = self.cmb_morph.currentIndex()
        if idx < 0 or idx >= len(self.morph_items):
            return None
        item = self.morph_items[idx]
        name, target_attr, bs_node = item[0], item[1], item[2]
        try:
            val = float(self.le_val.text().strip())
        except ValueError:
            val = 0.0
        return name, target_attr, bs_node, val

    def select_and_set_morph(self, target_attr, val):
        """特定のアトリビュート名を持つモーフを選択してウェイト値を設定"""
        for i, item in enumerate(self.morph_items):
            if item[1] == target_attr:
                self.cmb_morph.setCurrentIndex(i)
                val = max(0.0, min(1.0, float(val)))
                self._is_updating = True
                self.slider.setValue(int(round(val * 1000.0)))
                self.le_val.setText(f"{val:.3f}")
                self._is_updating = False
                self._apply_weight_to_maya(val)
                return True
        return False


class MMDMorphWindow(QWidget):
    """
    MMD Tools for Maya 統一ダークデザイン「表情操作」メインウィンドウ
    左上: 目 (panel: 2)
    右上: リップ (panel: 3)
    左下: まゆ (panel: 1)
    右下: その他 (panel: 4)
    """

    def __init__(self, parent=None):
        maya_parent = get_maya_main_window()
        super().__init__(maya_parent)

        self.setObjectName("MorphMainWindow")
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle("表情操作 (モーフ)")
        self.setStyleSheet(MODERN_DARK_STYLE)
        self.setFixedWidth(520)
        self.setFixedHeight(345)

        self._script_job_id = None
        self._is_refreshing = False
        self.current_model = None
        self._current_scene_targets = {}

        self._build_ui()
        self._setup_script_job()
        self.refresh_morph_data()

    def closeEvent(self, event):
        """ウィンドウ終了時にscriptJobを解除してリソースを解放"""
        self._cleanup_script_job()
        super().closeEvent(event)

    def _setup_script_job(self):
        """タイムスライダー変更時に各パネルのスライダー値を自動更新するイベントハンドラを登録"""
        if mc:
            try:
                self._cleanup_script_job()
                self._script_job_id = mc.scriptJob(event=["timeChanged", self._on_time_changed], protected=False)
            except Exception as e:
                print(f"[表情操作] scriptJobの登録をスキップしました: {e}")

    def _cleanup_script_job(self):
        """登録済みscriptJobを安全に解除"""
        if mc and self._script_job_id is not None:
            try:
                if mc.scriptJob(exists=self._script_job_id):
                    mc.scriptJob(kill=self._script_job_id, force=True)
            except Exception:
                pass
            self._script_job_id = None

    def _on_time_changed(self):
        """タイムスライダー移動時に各モーフカードの現在値を同期"""
        if self._is_refreshing:
            return
        for unit in [self.unit_brow, self.unit_eye, self.unit_lip, self.unit_other]:
            unit._update_current_morph_value()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 12)
        main_layout.setSpacing(6)

        # ヘッダーバー（タイトル・対象モデル選択・更新ボタン）
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        lbl_header = QLabel("表情操作 (モーフ)")
        lbl_header.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")

        header_row.addWidget(lbl_header)
        header_row.addStretch()

        lbl_model = QLabel("モデル:")
        lbl_model.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        header_row.addWidget(lbl_model)

        self.cmb_model = QComboBox()
        self.cmb_model.setProperty("class", "morph-combo")
        self.cmb_model.setFixedWidth(140)
        self.cmb_model.setFixedHeight(24)
        self.cmb_model.setToolTip("表情を操作する対象のモデルを選択します")
        self.cmb_model.currentIndexChanged.connect(self._on_model_changed)
        header_row.addWidget(self.cmb_model)

        self.btn_refresh = QPushButton("更新")
        self.btn_refresh.setProperty("class", "btn-header")
        self.btn_refresh.setFixedSize(46, 24)
        self.btn_refresh.setToolTip("シーン内のモーフ情報および解析データを再読み込みします")
        self.btn_refresh.clicked.connect(self.refresh_morph_data)
        header_row.addWidget(self.btn_refresh)

        main_layout.addLayout(header_row)

        # 4分割グリッドレイアウト（各表情カテゴリカード）
        # 左上: 目 (2), 右上: リップ (3), 左下: まゆ (1), 右下: その他 (4)
        grid = QGridLayout()
        grid.setSpacing(6)

        # 左上: 目
        self.unit_eye = MorphPanelUnit("目", panel_id=2, parent=self)
        grid.addWidget(self.unit_eye, 0, 0)

        # 右上: リップ
        self.unit_lip = MorphPanelUnit("リップ", panel_id=3, parent=self)
        grid.addWidget(self.unit_lip, 0, 1)

        # 左下: まゆ
        self.unit_brow = MorphPanelUnit("まゆ", panel_id=1, parent=self)
        grid.addWidget(self.unit_brow, 1, 0)

        # 右下: その他
        self.unit_other = MorphPanelUnit("その他", panel_id=4, parent=self)
        grid.addWidget(self.unit_other, 1, 1)

        main_layout.addLayout(grid)

        # 自作表情プリセットバー
        preset_frame = QFrame()
        preset_frame.setProperty("class", "preset-card")
        preset_layout = QHBoxLayout(preset_frame)
        preset_layout.setContentsMargins(8, 4, 8, 4)
        preset_layout.setSpacing(6)

        lbl_preset = QLabel("自作表情 (試験的機能):")
        lbl_preset.setStyleSheet("color: #52b7ff; font-weight: bold; font-size: 12px;")
        preset_layout.addWidget(lbl_preset)

        self.cmb_presets = QComboBox()
        self.cmb_presets.setProperty("class", "morph-combo")
        self.cmb_presets.setFixedWidth(130)
        self.cmb_presets.setFixedHeight(22)
        self.cmb_presets.setToolTip("登録済みの自作表情プリセットを選択します")
        preset_layout.addWidget(self.cmb_presets)

        self.btn_apply_preset = QPushButton("適用")
        self.btn_apply_preset.setProperty("class", "btn-preset-primary")
        self.btn_apply_preset.setFixedHeight(22)
        self.btn_apply_preset.setToolTip("選択中の自作表情プリセットをモデルに適用します")
        self.btn_apply_preset.clicked.connect(self._on_apply_preset)
        preset_layout.addWidget(self.btn_apply_preset)

        self.btn_key_preset = QPushButton("キー登録")
        self.btn_key_preset.setProperty("class", "btn-preset")
        self.btn_key_preset.setFixedHeight(22)
        self.btn_key_preset.setToolTip("カレントフレームに選択中の表情キーフレームを登録します")
        self.btn_key_preset.clicked.connect(self._on_key_preset)
        preset_layout.addWidget(self.btn_key_preset)

        self.btn_save_preset = QPushButton("新規登録")
        self.btn_save_preset.setProperty("class", "btn-preset")
        self.btn_save_preset.setFixedHeight(22)
        self.btn_save_preset.setToolTip("現在の表情の組み合わせを新規プリセットとして保存します")
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        preset_layout.addWidget(self.btn_save_preset)

        self.btn_delete_preset = QPushButton("削除")
        self.btn_delete_preset.setProperty("class", "btn-preset-danger")
        self.btn_delete_preset.setFixedHeight(22)
        self.btn_delete_preset.setToolTip("選択中の自作表情プリセットを削除します")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)
        preset_layout.addWidget(self.btn_delete_preset)

        self.btn_reset_all = QPushButton("リセット")
        self.btn_reset_all.setProperty("class", "btn-preset")
        self.btn_reset_all.setFixedHeight(22)
        self.btn_reset_all.setToolTip("すべての表情モーフを 0.0 に戻します")
        self.btn_reset_all.clicked.connect(self._on_reset_all_morphs)
        preset_layout.addWidget(self.btn_reset_all)

        main_layout.addWidget(preset_frame)

    def _on_model_changed(self, index):
        """対象モデル切り替え時の処理"""
        if self._is_refreshing:
            return
        model_name = self.cmb_model.currentText()
        if model_name:
            self.current_model = model_name
            self._load_morphs_for_current_model()
            self._update_presets_combo()

    def _get_scene_models(self):
        """シーン内の対象MMDモデル一覧を取得"""
        if not mc:
            return []

        try:
            from ..converters import vmdpaimaya
        except Exception:
            try:
                from converters import vmdpaimaya
            except Exception:
                import vmdpaimaya

        try:
            models = vmdpaimaya.get_available_mmd_models()
            if models:
                return [m[0] for m in models]
        except Exception:
            pass

        roots = mc.ls('*.mmdModelRoot', objectsOnly=True) or []
        if not roots:
            all_transforms = mc.ls(transforms=True) or []
            roots = [n for n in all_transforms if any(a.startswith("matmorph_") for a in (mc.listAttr(n, userDefined=True) or []))]
        if not roots:
            bs_nodes = mc.ls(type="blendShape") or []
            found = set()
            for bs in bs_nodes:
                geoms = mc.blendShape(bs, query=True, geometry=True) or []
                for g in geoms:
                    parents = mc.listRelatives(g, parent=True, fullPath=False) or []
                    if parents:
                        found.add(parents[0])
            roots = list(found)
        return sorted(list(set(roots)))

    def refresh_morph_data(self):
        """モデル一覧の再取得およびモーフ情報のバインド更新"""
        if not mc:
            return

        self._is_refreshing = True
        try:
            models = self._get_scene_models()

            # 現在選択中のオブジェクトから対象モデルを推測
            selected_objs = mc.ls(selection=True) or []
            preferred_model = None
            if selected_objs:
                for obj in selected_objs:
                    for m in models:
                        if obj == m or obj.startswith(f"{m}|"):
                            preferred_model = m
                            break
                    if preferred_model:
                        break

            self.cmb_model.clear()
            if models:
                self.cmb_model.addItems(models)
                target_idx = 0
                if preferred_model and preferred_model in models:
                    target_idx = models.index(preferred_model)
                elif self.current_model and self.current_model in models:
                    target_idx = models.index(self.current_model)
                self.cmb_model.setCurrentIndex(target_idx)
                self.current_model = self.cmb_model.currentText()
            else:
                self.cmb_model.addItem("モデルなし")
                self.current_model = None
        finally:
            self._is_refreshing = False

        self._load_morphs_for_current_model()
        self._update_presets_combo()

    def _load_morphs_for_current_model(self):
        """選択中モデルに属するBlendShapeおよび材質モーフを抽出し各パネルへバインド"""
        if not mc:
            return

        scene_targets = {}
        model_nodes = [self.current_model] if self.current_model and mc.objExists(self.current_model) else []

        # 選択中モデル配下のBlendShapeを探索
        target_bs_nodes = []
        if self.current_model and mc.objExists(self.current_model):
            relatives = mc.listRelatives(self.current_model, allDescendents=True, type="mesh") or []
            for r in relatives:
                history = mc.listHistory(r, pdo=True) or []
                for h in history:
                    if mc.nodeType(h) == "blendShape" and h not in target_bs_nodes:
                        target_bs_nodes.append(h)
        if not target_bs_nodes:
            target_bs_nodes = mc.ls(type="blendShape") or []

        for bs in target_bs_nodes:
            try:
                aliases = mc.listAttr(f"{bs}.w", multi=True) or []
                for alias in aliases:
                    scene_targets[alias] = bs
            except Exception:
                pass
            try:
                targets = mc.blendShape(bs, query=True, target=True) or []
                for tgt in targets:
                    scene_targets[tgt] = bs
            except Exception:
                pass

        # モデルノード上のカスタム材質モーフアトリビュートを探索
        for m_node in model_nodes:
            user_attrs = mc.listAttr(m_node, userDefined=True) or []
            for u_attr in user_attrs:
                if u_attr.startswith("matmorph_"):
                    scene_targets[u_attr] = m_node

        self._current_scene_targets = scene_targets

        # 解析JSONデータの探索
        json_morphs, structure_morph_map = self._load_pmx_data()

        # パネルごとにモーフを分類
        panels = {1: [], 2: [], 3: [], 4: []}
        registered_attrs = set()
        registered_names = set()

        if json_morphs:
            for m in json_morphs:
                name = m.get("name", "")
                if not name or name in registered_names:
                    continue
                p_id = m.get("panel", 4)
                # PMXデータに設定されているパネル（1:まゆ, 2:目, 3:リップ, 4:その他）を最優先として尊重
                if p_id not in [1, 2, 3, 4]:
                    p_id = self._guess_panel_id_by_name(name)
                target_attr, matched_node = self._resolve_target_attr(name, structure_morph_map, scene_targets, model_nodes)
                if target_attr and target_attr not in registered_attrs:
                    panels[p_id].append((name, target_attr, matched_node))
                    registered_attrs.add(target_attr)
                    registered_names.add(name)

        for attr, tgt_node in scene_targets.items():
            if attr in registered_attrs:
                continue
            disp_name = attr
            if mc.objExists(tgt_node) and mc.attributeQuery(attr, node=tgt_node, exists=True):
                try:
                    nice = mc.attributeQuery(attr, node=tgt_node, niceName=True)
                    if nice and not nice.startswith("matmorph_"):
                        disp_name = nice
                except Exception:
                    pass
            for jp_name, t_name in structure_morph_map.items():
                if t_name == attr:
                    disp_name = jp_name
                    break

            if disp_name in registered_names:
                continue

            p_id = self._guess_panel_id_by_name(disp_name)
            panels[p_id].append((disp_name, attr, tgt_node))
            registered_attrs.add(attr)
            registered_names.add(disp_name)

        self.unit_brow.set_morphs(panels[1])
        self.unit_eye.set_morphs(panels[2])
        self.unit_lip.set_morphs(panels[3])
        self.unit_other.set_morphs(panels[4])

    def _resolve_target_attr(self, morph_name, structure_morph_map, scene_targets, model_nodes=None):
        """モーフ名からMayaのターゲットアトリビュートを特定"""
        # 構造マップに明示されている場合
        if morph_name in structure_morph_map:
            t_attr = structure_morph_map[morph_name]
            if t_attr in scene_targets:
                return t_attr, scene_targets[t_attr]
            if model_nodes:
                for mn in model_nodes:
                    if mc.objExists(mn) and mc.attributeQuery(t_attr, node=mn, exists=True):
                        return t_attr, mn

        # 直接一致
        if morph_name in scene_targets:
            return morph_name, scene_targets[morph_name]

        # モデルノードのniceName属性と一致するか確認
        if model_nodes:
            for mn in model_nodes:
                if not mc.objExists(mn):
                    continue
                user_attrs = mc.listAttr(mn, userDefined=True) or []
                for u_attr in user_attrs:
                    if u_attr.startswith("matmorph_"):
                        try:
                            nice = mc.attributeQuery(u_attr, node=mn, niceName=True)
                            if nice == morph_name:
                                return u_attr, mn
                        except Exception:
                            pass

        # クリーン名や材質モーフ接頭辞による照合
        clean_name = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', '_', morph_name)
        for attr, tgt_node in scene_targets.items():
            if attr == clean_name:
                return attr, tgt_node
            if attr == f"matmorph_{clean_name}" or attr.endswith(f"_{clean_name}"):
                return attr, tgt_node
            if f"_{clean_name}_" in attr:
                return attr, tgt_node

        if model_nodes:
            for mn in model_nodes:
                if not mc.objExists(mn):
                    continue
                mat_attr = f"matmorph_{clean_name}"
                if mc.attributeQuery(mat_attr, node=mn, exists=True):
                    return mat_attr, mn

        return None, None

    def _load_pmx_data(self):
        """モデル属性、解析JSONおよび last_imported_structure.json からモーフ情報を取得"""
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        structure_morph_map = {}
        json_morphs = []

        # カレントモデルの属性から取得
        if mc and self.current_model and mc.objExists(self.current_model):
            # 新スキーマ mmdModelStructure を優先探索
            if mc.attributeQuery('mmdModelStructure', node=self.current_model, exists=True):
                try:
                    raw_model = mc.getAttr(f"{self.current_model}.mmdModelStructure")
                    if raw_model:
                        model_data = json.loads(raw_model)
                        raw_morphs = model_data.get('morphs', [])
                        if isinstance(raw_morphs, list):
                            for m in raw_morphs:
                                if isinstance(m, dict):
                                    name_jp = m.get('name_jp') or m.get('name', '')
                                    target = m.get('maya_target')
                                    if name_jp and target:
                                        structure_morph_map[name_jp] = target
                                    if m.get('name_en') and target:
                                        structure_morph_map[m['name_en']] = target
                                    json_morphs.append({
                                        'name': name_jp,
                                        'name_en': m.get('name_en', ''),
                                        'panel': m.get('panel', 4),
                                        'target': target
                                    })
                except Exception:
                    pass

            if mc.attributeQuery('mmdMorphStructure', node=self.current_model, exists=True):
                try:
                    raw = mc.getAttr(f"{self.current_model}.mmdMorphStructure")
                    if raw:
                        structure_morph_map.update(json.loads(raw))
                except Exception:
                    pass

        # last_imported_structure.json からマップおよびモーフ定義を取得
        cache_path = os.path.join(plugin_root, 'asset', 'last_imported_structure.json')
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cdata = json.load(f)
                    raw_m = cdata.get('morphs')
                    if isinstance(raw_m, list):
                        for m in raw_m:
                            if isinstance(m, dict):
                                name_jp = m.get('name_jp') or m.get('name', '')
                                target = m.get('maya_target')
                                if name_jp and target:
                                    structure_morph_map[name_jp] = target
                                if m.get('name_en') and target:
                                    structure_morph_map[m['name_en']] = target
                                if not json_morphs:
                                    json_morphs.append({
                                        'name': name_jp,
                                        'name_en': m.get('name_en', ''),
                                        'panel': m.get('panel', 4),
                                        'target': target
                                    })
                    elif isinstance(raw_m, dict):
                        structure_morph_map.update(raw_m)
                    if not structure_morph_map and isinstance(cdata.get('legacy_compatibility', {}).get('morphs'), dict):
                        structure_morph_map.update(cdata['legacy_compatibility']['morphs'])
            except Exception:
                pass

        # User_pmx_data からカレントモデル名に一致する解析JSONを最優先探索
        if not json_morphs:
            user_pmx_dir = os.path.join(plugin_root, "asset", "User_pmx_data")
            candidate_files = []
            model_name_lower = self.current_model.lower() if self.current_model else ""

            if os.path.exists(user_pmx_dir):
                for fname in os.listdir(user_pmx_dir):
                    if fname.endswith(".json"):
                        full_path = os.path.join(user_pmx_dir, fname)
                        score = os.path.getmtime(full_path)
                        if model_name_lower and model_name_lower in fname.lower():
                            score += 1000000000.0
                        candidate_files.append((score, full_path))

            if not candidate_files:
                tes_dir = os.path.join(plugin_root, "tes_model")
                if os.path.exists(tes_dir):
                    for root, _, files in os.walk(tes_dir):
                        for fname in files:
                            if fname.endswith("_pmx_analysis.json"):
                                full_path = os.path.join(root, fname)
                                score = os.path.getmtime(full_path)
                                if model_name_lower and model_name_lower in fname.lower():
                                    score += 1000000000.0
                                candidate_files.append((score, full_path))

            if candidate_files:
                candidate_files.sort(key=lambda x: x[0], reverse=True)
                latest_json = candidate_files[0][1]
                try:
                    with open(latest_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        raw_list = data.get("morphs", [])
                        for m in raw_list:
                            if isinstance(m, dict):
                                json_morphs.append({
                                    'name': m.get('name_jp') or m.get('name', ''),
                                    'panel': m.get('panel', 4)
                                })
                except Exception:
                    pass

        return json_morphs, structure_morph_map

    def _guess_panel_id_by_name(self, name):
        """名称から推定してパネルID（1:まゆ, 2:目, 3:リップ, 4:その他）を決定"""
        n = name.lower()
        # 特殊な代表モーフの優先判定
        if "真面目" in n or "まじめ" in n:
            return 1
        if any(k in n for k in ["怒り目", "悪い目", "じと目", "なごみ目", "哀目"]):
            return 2
        # パーツ非表示・消去系モーフは無条件でその他（パネル4）へ分類
        if any(k in n for k in ["off", "消し", "非表示", "なし", "外し", "消去"]):
            return 4
        # 口・リップ (パネル3) を含む複合語の優先判定
        if any(k in n for k in ["笑い口", "開き口", "閉じ口", "広口", "狭口", "口", "リップ", "lip", "mouth"]):
            return 3
        # 目 (パネル2)
        eye_keywords = [
            "目", "瞳", "eye", "アイ", "blink", "まばたき", "ウィンク", "笑い",
            "じと目", "なごみ", "悪い目", "怒り目", "哀目", "涙", "発光", "ハイライト",
            "黒目", "白目", "瞳小", "瞳大", "恐ろしい目", "光なし"
        ]
        if any(k in n for k in eye_keywords):
            return 2
        # まゆ (パネル1)
        brow_keywords = ["まゆ", "眉", "brow", "にこり", "困る", "怒り", "眉頭", "眉尻"]
        if any(k in n for k in brow_keywords):
            return 1
        # リップ (口) その他のキーワード (パネル3)
        lip_keywords = [
            "あ", "い", "う", "え", "お", "ω", "▲", "口角", "歯", "tooth", "teeth", "舌", "tongue", "牙", "fang"
        ]
        if any(k in n for k in lip_keywords):
            return 3
        # その他 (パネル4)
        return 4

    def _get_presets_file_path(self):
        """自作表情プリセット保存用JSONファイルパスを取得"""
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(plugin_root, 'asset', 'custom_facial_presets.json')

    def _load_presets(self):
        """モデル属性またはJSONファイルから自作表情プリセットを読み込み"""
        presets = {}
        # モデルノードの属性から読み込み
        if mc and self.current_model and mc.objExists(self.current_model):
            if mc.attributeQuery('mmdCustomFacialPresets', node=self.current_model, exists=True):
                try:
                    raw = mc.getAttr(f"{self.current_model}.mmdCustomFacialPresets")
                    if raw:
                        presets = json.loads(raw)
                except Exception:
                    pass

        # なければ共有JSONファイルから読み込み
        if not presets:
            fpath = self._get_presets_file_path()
            if os.path.isfile(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        presets = json.load(f)
                except Exception:
                    pass
        return presets

    def _save_presets(self, presets):
        """モデル属性および共有JSONファイルへ自作表情プリセットを保存"""
        raw_json = json.dumps(presets, ensure_ascii=False, indent=2)
        # モデルノードへ保存
        if mc and self.current_model and mc.objExists(self.current_model):
            try:
                if not mc.attributeQuery('mmdCustomFacialPresets', node=self.current_model, exists=True):
                    mc.addAttr(self.current_model, longName='mmdCustomFacialPresets', dataType='string')
                mc.setAttr(f"{self.current_model}.mmdCustomFacialPresets", raw_json, type='string')
            except Exception as e:
                print(f"[表情操作] モデル属性へのプリセット保存警告: {e}")

        # 共有JSONファイルへ保存
        try:
            fpath = self._get_presets_file_path()
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(raw_json)
        except Exception as e:
            print(f"[表情操作] プリセットファイル保存警告: {e}")

    def _update_presets_combo(self):
        """自作表情コンボボックスのリストを最新化"""
        presets = self._load_presets()
        self.cmb_presets.clear()
        if presets:
            names = sorted(list(presets.keys()))
            self.cmb_presets.addItems(names)
        else:
            self.cmb_presets.addItem("プリセットなし")

    def _on_apply_preset(self):
        """選択中の自作表情プリセットをシーンとUIへ一括適用"""
        preset_name = self.cmb_presets.currentText()
        presets = self._load_presets()
        if preset_name not in presets:
            return

        morph_weights = presets[preset_name]
        applied_count = 0

        # まず現在のモデルの全モーフをリセット
        self._on_reset_all_morphs()

        # プリセット内の各モーフ値を適用
        for attr, val in morph_weights.items():
            if attr in self._current_scene_targets:
                node = self._current_scene_targets[attr]
                full_attr = f"{node}.{attr}"
                if mc and mc.objExists(full_attr):
                    try:
                        mc.setAttr(full_attr, float(val))
                        applied_count += 1
                    except Exception:
                        pass

            # 4分割カードにも反映
            for unit in [self.unit_brow, self.unit_eye, self.unit_lip, self.unit_other]:
                unit.select_and_set_morph(attr, val)

        print(f"[表情操作] 自作表情「{preset_name}」を適用しました (適用モーフ数: {applied_count})")

    def _on_key_preset(self):
        """選択中プリセットのモーフにカレントフレームでキーフレームを打刻"""
        preset_name = self.cmb_presets.currentText()
        presets = self._load_presets()
        if preset_name not in presets:
            return

        morph_weights = presets[preset_name]
        keyed_count = 0
        for attr, val in morph_weights.items():
            if attr in self._current_scene_targets:
                node = self._current_scene_targets[attr]
                full_attr = f"{node}.{attr}"
                if mc and mc.objExists(full_attr):
                    try:
                        mc.setKeyframe(full_attr, value=float(val))
                        keyed_count += 1
                    except Exception:
                        pass
        print(f"[表情操作] 自作表情「{preset_name}」のキーフレームを一括登録しました ({keyed_count}件)")

    def _on_save_preset(self):
        """現在の表情の組み合わせを新規プリセットとして登録"""
        if not mc:
            return

        active_morphs = {}
        for attr, node in self._current_scene_targets.items():
            full_attr = f"{node}.{attr}"
            if mc.objExists(full_attr):
                try:
                    val = float(mc.getAttr(full_attr))
                    if abs(val) > 0.0005:
                        active_morphs[attr] = round(val, 3)
                except Exception:
                    pass

        if not active_morphs:
            QMessageBox.information(
                self,
                "自作表情の登録",
                "現在ウェイト値が設定されている表情モーフがありません。\nスライダーで表情を調整してから登録してください。"
            )
            return

        name, ok = QInputDialog.getText(
            self,
            "自作表情の新規登録",
            f"プリセット名を入力してください:\n(対象モーフ数: {len(active_morphs)})"
        )
        if not ok or not name.strip():
            return

        preset_name = name.strip()
        presets = self._load_presets()
        presets[preset_name] = active_morphs
        self._save_presets(presets)
        self._update_presets_combo()

        idx = self.cmb_presets.findText(preset_name)
        if idx >= 0:
            self.cmb_presets.setCurrentIndex(idx)

        QMessageBox.information(
            self,
            "登録完了",
            f"自作表情プリセット「{preset_name}」を登録しました。\n(登録モーフ: {', '.join(list(active_morphs.keys())[:5])}... 計{len(active_morphs)}個)"
        )

    def _on_delete_preset(self):
        """選択中プリセットを削除"""
        preset_name = self.cmb_presets.currentText()
        presets = self._load_presets()
        if preset_name not in presets:
            return

        ret = QMessageBox.question(
            self,
            "自作表情の削除",
            f"プリセット「{preset_name}」を削除してもよろしいですか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ret == QMessageBox.Yes:
            del presets[preset_name]
            self._save_presets(presets)
            self._update_presets_combo()

    def _on_reset_all_morphs(self):
        """すべての表情モーフを 0.0 にリセット"""
        if not mc:
            return
        for attr, node in self._current_scene_targets.items():
            full_attr = f"{node}.{attr}"
            if mc.objExists(full_attr):
                try:
                    mc.setAttr(full_attr, 0.0)
                except Exception:
                    pass
        for unit in [self.unit_brow, self.unit_eye, self.unit_lip, self.unit_other]:
            unit._update_current_morph_value()
        print("[表情操作] 全表情モーフのウェイト値を 0.0 に初期化しました。")


_global_morph_window = None

def show_morph_window(parent=None):
    """表情操作GUIを表示（既存ウィンドウがあれば前面にフォーカス、事前検証付き）"""
    global _global_morph_window

    # Mayaシーン内のボーン・ブレンドシェイプの存在確認
    if mc:
        joints = mc.ls(type="joint") or []
        bs_nodes = mc.ls(type="blendShape") or []
        has_targets = False
        if bs_nodes:
            for bs in bs_nodes:
                try:
                    aliases = mc.listAttr(f"{bs}.w", multi=True) or []
                    targets = mc.blendShape(bs, query=True, target=True) or []
                    if aliases or targets:
                        has_targets = True
                        break
                except Exception:
                    pass

        has_matmorphs = False
        all_transforms = mc.ls(transforms=True) or []
        for tr in all_transforms:
            if any(a.startswith("matmorph_") for a in (mc.listAttr(tr, userDefined=True) or [])):
                has_matmorphs = True
                break

        has_any_morphs = has_targets or has_matmorphs
        if not joints or (not bs_nodes and not has_matmorphs) or not has_any_morphs:
            missing_items = []
            if not joints:
                missing_items.append("・ボーン (Joint)")
            if not has_any_morphs:
                missing_items.append("・ブレンドシェイプ / モーフ (blendShape / 材質モーフ)")

            missing_str = "\n".join(missing_items)
            msg_parent = parent or get_maya_main_window()
            QMessageBox.warning(
                msg_parent,
                "表情操作の準備ができていません",
                f"モデル（ボーン・モーフ・ブレンドシェイプ）がインポートされていないか、必要な要素が不足しています。\n\n"
                f"不足している要素:\n{missing_str}\n\n"
                f"[MMD → Maya (インポート)] タブからモデルをインポートし直してください。\n"
                f"（※インポート設定で「ボーン生成」「ブレンドシェイプ生成」にチェックが入っていることをご確認ください）"
            )
            return None

    if _global_morph_window is not None:
        try:
            _global_morph_window.refresh_morph_data()
            _global_morph_window.show()
            _global_morph_window.raise_()
            _global_morph_window.activateWindow()
            return _global_morph_window
        except Exception:
            _global_morph_window = None

    _global_morph_window = MMDMorphWindow(parent=parent)
    _global_morph_window.show()
    return _global_morph_window
