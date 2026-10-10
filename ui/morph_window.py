# -*- coding: utf-8 -*-
"""
MMD表情操作モーフGUIモジュール (morph_window.py)

MMD Tools for Maya のメインGUIと完全統一されたモダンダークテーマを採用。
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
        QMessageBox, QFrame, QSizePolicy
    )
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QDoubleValidator, QFont
except ImportError:
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QComboBox, QSlider, QLineEdit,
        QMessageBox, QFrame, QSizePolicy
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

# メインGUI（MMD Tools for Maya）と完全統一されたモダンダークテーマQSS
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
        # 最前面（WindowStaysOnTopHint）は設定せず、Mayaを親とする標準ウィンドウフラグ
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle("表情操作 (モーフ)")
        self.setStyleSheet(MODERN_DARK_STYLE)
        self.setFixedWidth(500)
        self.setFixedHeight(256)

        self._build_ui()
        self.refresh_morph_data()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 12)
        main_layout.setSpacing(8)

        # ヘッダーバー（タイトル・更新ボタン）
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        lbl_header = QLabel("表情操作 (モーフ)")
        lbl_header.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")

        self.btn_refresh = QPushButton("更新")
        self.btn_refresh.setProperty("class", "btn-header")
        self.btn_refresh.setFixedSize(48, 24)
        self.btn_refresh.setToolTip("シーン内のモーフ情報および解析データを再読み込みします")
        self.btn_refresh.clicked.connect(self.refresh_morph_data)

        header_row.addWidget(lbl_header)
        header_row.addStretch()
        header_row.addWidget(self.btn_refresh)
        main_layout.addLayout(header_row)

        # 4分割グリッドレイアウト
        # 左上: 目 (2), 右上: リップ (3), 左下: まゆ (1), 右下: その他 (4)
        grid = QGridLayout()
        grid.setSpacing(8)

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

    def refresh_morph_data(self):
        """シーン内のBlendShapeノードと解析JSONから各パネルへモーフを割り当て"""
        if not mc:
            return

        # BlendShapeノードと全ターゲットアトリビュートを探索
        bs_nodes = mc.ls(type="blendShape") or []
        scene_targets = {}  # {attr_name: bs_node}
        for bs in bs_nodes:
            # エイリアス一覧
            try:
                aliases = mc.listAttr(f"{bs}.w", multi=True) or []
                for alias in aliases:
                    scene_targets[alias] = bs
            except Exception:
                pass
            # ターゲット名一覧
            try:
                targets = mc.blendShape(bs, query=True, target=True) or []
                for tgt in targets:
                    scene_targets[tgt] = bs
            except Exception:
                pass

        # 解析JSONデータの探索 (asset/User_pmx_data 配下を最優先)
        json_morphs, structure_morph_map = self._load_pmx_data()

        # パネルごとにモーフを分類
        panels = {
            1: [],  # まゆ
            2: [],  # 目
            3: [],  # リップ
            4: []   # その他
        }

        registered_attrs = set()

        # JSONのモーフ一覧から順次照合
        if json_morphs:
            for m in json_morphs:
                name = m.get("name", "")
                p_id = m.get("panel", 4)
                if p_id not in panels:
                    p_id = 4

                # structure_morph_map またはシーン内ターゲットから探索
                target_attr, matched_bs = self._resolve_target_attr(name, structure_morph_map, scene_targets)
                if target_attr and target_attr not in registered_attrs:
                    panels[p_id].append((name, target_attr, matched_bs))
                    registered_attrs.add(target_attr)

        # シーン内BlendShapeターゲットのフォールバック割り当て（未登録の全ターゲットを網羅）
        for attr, bs in scene_targets.items():
            if attr in registered_attrs:
                continue

            # 表示用モーフ名を特定
            disp_name = attr
            # 構造マップから逆引き
            for jp_name, t_name in structure_morph_map.items():
                if t_name == attr:
                    disp_name = jp_name
                    break

            p_id = self._guess_panel_id_by_name(disp_name)
            panels[p_id].append((disp_name, attr, bs))
            registered_attrs.add(attr)

        # 各パネルユニットへ適用
        self.unit_brow.set_morphs(panels[1])
        self.unit_eye.set_morphs(panels[2])
        self.unit_lip.set_morphs(panels[3])
        self.unit_other.set_morphs(panels[4])

    def _resolve_target_attr(self, morph_name, structure_morph_map, scene_targets):
        """モーフ名からMayaのターゲットアトリビュートを特定"""
        # 構造マップに明示されている場合
        if morph_name in structure_morph_map:
            t_attr = structure_morph_map[morph_name]
            if t_attr in scene_targets:
                return t_attr, scene_targets[t_attr]

        # 直接一致
        if morph_name in scene_targets:
            return morph_name, scene_targets[morph_name]

        # クリーン名や部分一致による照合
        clean_name = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', '_', morph_name)
        for attr, bs in scene_targets.items():
            if attr == clean_name:
                return attr, bs
            if attr.endswith(f"_{morph_name}") or attr.endswith(f"_{clean_name}"):
                return attr, bs
            if f"_{clean_name}_" in attr:
                return attr, bs

        return None, None

    def _load_pmx_data(self):
        """解析JSONおよび last_imported_structure.json からモーフ情報を取得"""
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        structure_morph_map = {}

        # last_imported_structure.json からマップを取得
        cache_path = os.path.join(plugin_root, 'asset', 'last_imported_structure.json')
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cdata = json.load(f)
                    structure_morph_map = cdata.get('morphs', {})
            except Exception:
                pass

        # モデルノードのメタデータも確認
        if mc:
            roots = mc.ls('*.mmdModelRoot', objectsOnly=True) or []
            if roots:
                last_root = roots[-1]
                if mc.attributeQuery('mmdMorphStructure', node=last_root, exists=True):
                    try:
                        raw = mc.getAttr(f"{last_root}.mmdMorphStructure")
                        if raw:
                            structure_morph_map.update(json.loads(raw))
                    except Exception:
                        pass

        # User_pmx_data から最新の解析JSONを読み込み
        user_pmx_dir = os.path.join(plugin_root, "asset", "User_pmx_data")
        candidate_files = []
        if os.path.exists(user_pmx_dir):
            for fname in os.listdir(user_pmx_dir):
                if fname.endswith(".json"):
                    full_path = os.path.join(user_pmx_dir, fname)
                    candidate_files.append((os.path.getmtime(full_path), full_path))

        # 旧保存先 (tes_model 配下) もフォールバック探索
        if not candidate_files:
            tes_dir = os.path.join(plugin_root, "tes_model")
            if os.path.exists(tes_dir):
                for root, _, files in os.walk(tes_dir):
                    for fname in files:
                        if fname.endswith("_pmx_analysis.json"):
                            full_path = os.path.join(root, fname)
                            candidate_files.append((os.path.getmtime(full_path), full_path))

        json_morphs = []
        if candidate_files:
            candidate_files.sort(key=lambda x: x[0], reverse=True)
            latest_json = candidate_files[0][1]
            try:
                with open(latest_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    json_morphs = data.get("morphs", [])
            except Exception:
                pass

        return json_morphs, structure_morph_map

    def _guess_panel_id_by_name(self, name):
        """名称から推定してパネルID（1:まゆ, 2:目, 3:リップ, 4:その他）を決定"""
        n = name.lower()
        if any(k in n for k in ["まゆ", "眉", "brow"]):
            return 1
        if any(k in n for k in ["目", "瞳", "eye", "blink", "まばたき", "ウィンク", "笑い", "じと目", "なごみ", "悪い目", "怒り目", "哀目"]):
            return 2
        if any(k in n for k in ["口", "リップ", "lip", "mouth", "あ", "い", "う", "え", "お", "ω", "▲", "口角"]):
            return 3
        return 4


_global_morph_window = None

def show_morph_window(parent=None):
    """表情操作GUIを表示（既存ウィンドウがあれば前面にフォーカス）"""
    global _global_morph_window
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
