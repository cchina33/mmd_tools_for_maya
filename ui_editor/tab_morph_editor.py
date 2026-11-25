# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MMD Model Editor モーフ管理タブモジュール
MMDモデルのモーフ（表情・材質・ボーン・グループ）の一覧表示、カテゴリ絞り込み、およびウェイト調整を提供します。
"""

import os
import sys
import maya.cmds as mc

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QSplitter, QScrollArea, QGroupBox, QComboBox, QSlider,
        QDoubleSpinBox, QFrame, QMessageBox
    )
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt, Signal
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QSplitter, QScrollArea, QGroupBox, QComboBox, QSlider,
        QDoubleSpinBox, QFrame, QMessageBox
    )

# モーフパネル表示名対応表
PANEL_NAMES = {
    0: "システム",
    1: "眉 (Eyebrow)",
    2: "目 (Eye)",
    3: "口 (Lip)",
    4: "その他 (Other)",
}

# モーフ種別表示名対応表
TYPE_NAMES = {
    0: "グループ (Group)",
    1: "頂点 (Vertex)",
    2: "ボーン (Bone)",
    3: "UV",
    4: "追加UV1",
    5: "追加UV2",
    6: "追加UV3",
    7: "追加UV4",
    8: "材質 (Material)",
    9: "フリップ (Flip)",
    10: "インパルス (Impulse)",
}


class MorphEditorTabWidget(QWidget):
    """
    MMD Model Editor モーフ管理タブウィジェット
    モデルのモーフ一覧を表示し、スライダによるウェイト調整とMayaシーン即時連動を行います。
    """

    def __init__(self, parent=None):
        super(MorphEditorTabWidget, self).__init__(parent)
        self.current_model = None
        self.morph_data_list = []
        self.selected_morph_index = -1
        self._block_signals = False
        self.blendshape_node = None

        self._init_ui()

    def _init_ui(self):
        """ユーザーインターフェースの初期化"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 水平スプリッター (左: モーフ一覧テーブル、右: 詳細属性・ウェイトスライダ)
        self.splitter = QSplitter(Qt.Horizontal)

        # -------------------------------------------------------------
        # 左ペイン: モーフ一覧テーブル・絞り込み
        # -------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(6)

        # 絞り込みバー
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(4)

        lbl_cat = QLabel("分類:")
        lbl_cat.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.cbb_panel_filter = QComboBox()
        self.cbb_panel_filter.addItems(["すべての分類", "眉", "目", "口", "その他", "システム"])
        self.cbb_panel_filter.currentIndexChanged.connect(self._filter_morph_list)

        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText("モーフ名で検索...")
        self.le_search.textChanged.connect(self._filter_morph_list)

        btn_clear = QPushButton("クリア")
        btn_clear.setFixedWidth(50)
        btn_clear.clicked.connect(self._clear_filters)

        filter_layout.addWidget(lbl_cat)
        filter_layout.addWidget(self.cbb_panel_filter)
        filter_layout.addWidget(self.le_search)
        filter_layout.addWidget(btn_clear)
        left_layout.addLayout(filter_layout)

        # モーフ一覧テーブル
        self.table_morphs = QTableWidget()
        self.table_morphs.setColumnCount(5)
        self.table_morphs.setHorizontalHeaderLabels(["No", "モーフ名 (日本語)", "英語名", "分類", "種別"])
        self.table_morphs.horizontalHeader().setStretchLastSection(True)
        self.table_morphs.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_morphs.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_morphs.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_morphs.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_morphs.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_morphs.setSelectionMode(QTableWidget.SingleSelection)
        self.table_morphs.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_morphs.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333333;")
        self.table_morphs.itemSelectionChanged.connect(self._on_table_selection_changed)
        left_layout.addWidget(self.table_morphs)

        # 下部ボタン群
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        btn_reset_current = QPushButton("選択ウェイトを0にリセット")
        btn_reset_current.clicked.connect(self._reset_current_weight)
        btn_layout.addWidget(btn_reset_current)

        btn_reset_all = QPushButton("すべてのモーフをリセット")
        btn_reset_all.clicked.connect(self._reset_all_weights)
        btn_layout.addWidget(btn_reset_all)

        btn_refresh = QPushButton("リスト再取得")
        btn_refresh.setFixedWidth(90)
        btn_refresh.clicked.connect(self._reload_morph_list)
        btn_layout.addWidget(btn_refresh)

        left_layout.addLayout(btn_layout)

        # -------------------------------------------------------------
        # 右ペイン: モーフ詳細情報およびリアルタイムウェイト操作
        # -------------------------------------------------------------
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)

        # 基本情報グループ
        grp_info = QGroupBox("モーフ基本情報")
        info_layout = QVBoxLayout(grp_info)
        info_layout.setSpacing(6)

        lbl_ja = QLabel("モーフ名 (日本語):")
        lbl_ja.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.le_morph_name_ja = QLineEdit()
        self.le_morph_name_ja.setReadOnly(True)
        info_layout.addWidget(lbl_ja)
        info_layout.addWidget(self.le_morph_name_ja)

        lbl_en = QLabel("モーフ名 (英語):")
        lbl_en.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.le_morph_name_en = QLineEdit()
        self.le_morph_name_en.setReadOnly(True)
        info_layout.addWidget(lbl_en)
        info_layout.addWidget(self.le_morph_name_en)

        self.lbl_panel_type = QLabel("分類: -  |  種別: -")
        self.lbl_panel_type.setStyleSheet("color: #52b7ff; font-weight: bold;")
        info_layout.addWidget(self.lbl_panel_type)

        self.lbl_target_attr = QLabel("Maya属性: (未接続)")
        self.lbl_target_attr.setStyleSheet("color: #888888; font-size: 11px;")
        info_layout.addWidget(self.lbl_target_attr)

        right_layout.addWidget(grp_info)

        # ウェイト操作グループ
        grp_weight = QGroupBox("ウェイト操作 (Weight Slider)")
        weight_layout = QVBoxLayout(grp_weight)
        weight_layout.setSpacing(8)

        slider_row = QHBoxLayout()
        self.slider_weight = QSlider(Qt.Horizontal)
        self.slider_weight.setRange(0, 1000)
        self.slider_weight.setValue(0)
        self.slider_weight.valueChanged.connect(self._on_slider_value_changed)

        self.spin_weight = QDoubleSpinBox()
        self.spin_weight.setRange(0.0, 1.0)
        self.spin_weight.setSingleStep(0.05)
        self.spin_weight.setDecimals(3)
        self.spin_weight.setValue(0.0)
        self.spin_weight.valueChanged.connect(self._on_spin_value_changed)

        slider_row.addWidget(self.slider_weight)
        slider_row.addWidget(self.spin_weight)
        weight_layout.addLayout(slider_row)

        # プリセット値ボタン
        preset_row = QHBoxLayout()
        for p_val in [0.0, 0.25, 0.5, 0.75, 1.0]:
            btn_p = QPushButton(f"{p_val:.2f}")
            btn_p.setFixedHeight(24)
            btn_p.clicked.connect(lambda checked=False, v=p_val: self._set_preset_weight(v))
            preset_row.addWidget(btn_p)
        weight_layout.addLayout(preset_row)

        right_layout.addWidget(grp_weight)

        right_layout.addStretch()
        right_scroll.setWidget(right_widget)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_scroll)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 5)

        main_layout.addWidget(self.splitter)

    def set_target_model(self, model_node):
        """対象モデルを受け取り、モーフ一覧を構築"""
        self.current_model = model_node
        try:
            self._reload_morph_list()
        except Exception as e:
            print(f"[モーフタブ 警告] モーフ一覧の読み込み中に軽微な例外を捕捉: {e}")

    def _reload_morph_list(self):
        """モデル配下のブレンドシェイプおよびPMXデータからモーフ情報を抽出"""
        self.morph_data_list = []
        self.selected_morph_index = -1
        self.blendshape_node = None

        model_node = self.current_model
        if not model_node or not mc.objExists(model_node):
            # シーン内からMMDモデル候補を自動探索
            candidates = []
            for tr in mc.ls(type="transform") or []:
                if (mc.attributeQuery("mmdModelRoot", node=tr, exists=True) or
                    mc.attributeQuery("mmdSourceFilePath", node=tr, exists=True) or
                    mc.attributeQuery("mmdModelPath", node=tr, exists=True)):
                    candidates.append(tr)
                elif any(k in tr.lower() for k in ["pmx", "pmd", "mmd_model"]):
                    candidates.append(tr)
            if not candidates:
                for m in mc.ls(type="mesh") or []:
                    p = mc.listRelatives(m, parent=True)
                    if p and p[0] not in candidates:
                        candidates.append(p[0])
            if candidates:
                model_node = candidates[0]

        mesh_node = model_node
        if model_node and mc.objExists(model_node):
            if mc.nodeType(model_node) != "mesh":
                child_meshes = mc.listRelatives(model_node, shapes=True, type="mesh") or []
                if child_meshes:
                    mesh_node = child_meshes[0]
                else:
                    desc_meshes = mc.listRelatives(model_node, allDescendents=True, type="mesh") or []
                    if desc_meshes:
                        mesh_node = desc_meshes[0]

        # ブレンドシェイプノードの探索
        if mesh_node and mc.objExists(mesh_node):
            bs_nodes = mc.listConnections(mesh_node, type="blendShape") or []
            if bs_nodes:
                self.blendshape_node = bs_nodes[0]

        if not self.blendshape_node and model_node and mc.objExists(model_node):
            bs_nodes = mc.listRelatives(model_node, allDescendents=True, type="blendShape") or []
            if bs_nodes:
                self.blendshape_node = bs_nodes[0]

        if not self.blendshape_node:
            # シーン内のブレンドシェイプノードから探索
            all_bs = mc.ls(type="blendShape") or []
            if all_bs:
                self.blendshape_node = all_bs[0]

        # PMXファイル探索 (モデル、親、子孫ノード)
        pmx_path = None
        nodes_to_search = []
        if model_node and mc.objExists(model_node):
            nodes_to_search.extend([model_node, mesh_node])
            nodes_to_search.extend(mc.listRelatives(model_node, parent=True) or [])
            nodes_to_search.extend(mc.listRelatives(model_node, allDescendents=True) or [])

        for n in nodes_to_search:
            if not n or not mc.objExists(n):
                continue
            for attr_name in ["mmdSourceFilePath", "mmdModelPath", "mmdFilePath"]:
                if mc.attributeQuery(attr_name, node=n, exists=True):
                    p = mc.getAttr(f"{n}.{attr_name}")
                    if p and os.path.isfile(p):
                        pmx_path = p
                        break
            if pmx_path:
                break

        pmx_morphs = []
        if pmx_path:
            try:
                try:
                    from .. import mmd_parser
                except Exception:
                    import mmd_parser
                pmx_model = mmd_parser.pmx.load(pmx_path)
                pmx_morphs = getattr(pmx_model, 'morphs', [])
            except Exception:
                pmx_morphs = []

        if pmx_morphs:
            for m_idx, morph in enumerate(pmx_morphs):
                name_ja = morph.name
                name_en = getattr(morph, 'name_e', '') or ''
                p_cat = getattr(morph, 'panel', 4)
                m_type = getattr(morph, 'morph_type', getattr(morph, 'type', 1))

                # Mayaアトリビュートの解決
                maya_attr = None
                cur_val = 0.0
                if self.blendshape_node and mc.objExists(self.blendshape_node):
                    if mc.attributeQuery(name_ja, node=self.blendshape_node, exists=True):
                        maya_attr = f"{self.blendshape_node}.{name_ja}"
                    else:
                        # エイリアス属性から探索
                        aliases = mc.aliasAttr(self.blendshape_node, query=True) or []
                        for a_i in range(0, len(aliases), 2):
                            if aliases[a_i] == name_ja:
                                maya_attr = f"{self.blendshape_node}.{aliases[a_i+1]}"
                                break

                    if maya_attr and mc.objExists(maya_attr):
                        try:
                            cur_val = float(mc.getAttr(maya_attr))
                        except Exception:
                            pass

                self.morph_data_list.append({
                    "index": m_idx,
                    "name_ja": name_ja,
                    "name_en": name_en,
                    "panel": p_cat,
                    "panel_str": PANEL_NAMES.get(p_cat, f"パネル{p_cat}"),
                    "type": m_type,
                    "type_str": TYPE_NAMES.get(m_type, f"種別{m_type}"),
                    "maya_attr": maya_attr,
                    "weight": cur_val,
                })
        else:
            # PMXファイル未検出時、ノード構造メタデータからの復元探索
            meta_morphs = []
            for n in nodes_to_search:
                if n and mc.objExists(n):
                    if mc.attributeQuery("mmdModelStructure", node=n, exists=True):
                        try:
                            import json
                            raw_st = mc.getAttr(f"{n}.mmdModelStructure")
                            parsed_st = json.loads(raw_st)
                            meta_morphs = parsed_st.get("morphs", [])
                            if meta_morphs:
                                break
                        except Exception:
                            pass

            if meta_morphs:
                for m_idx, morph_dict in enumerate(meta_morphs):
                    name_ja = morph_dict.get("name", f"モーフ_{m_idx}")
                    name_en = morph_dict.get("name_e", "")
                    p_cat = morph_dict.get("panel", 4)
                    m_type = morph_dict.get("type", 1)

                    maya_attr = None
                    cur_val = 0.0
                    if self.blendshape_node and mc.objExists(self.blendshape_node):
                        if mc.attributeQuery(name_ja, node=self.blendshape_node, exists=True):
                            maya_attr = f"{self.blendshape_node}.{name_ja}"
                        else:
                            aliases = mc.aliasAttr(self.blendshape_node, query=True) or []
                            for a_i in range(0, len(aliases), 2):
                                if aliases[a_i] == name_ja:
                                    maya_attr = f"{self.blendshape_node}.{aliases[a_i+1]}"
                                    break
                        if maya_attr and mc.objExists(maya_attr):
                            try:
                                cur_val = float(mc.getAttr(maya_attr))
                            except Exception:
                                pass

                    self.morph_data_list.append({
                        "index": m_idx,
                        "name_ja": name_ja,
                        "name_en": name_en,
                        "panel": p_cat,
                        "panel_str": PANEL_NAMES.get(p_cat, f"パネル{p_cat}"),
                        "type": m_type,
                        "type_str": TYPE_NAMES.get(m_type, f"種別{m_type}"),
                        "maya_attr": maya_attr,
                        "weight": cur_val,
                    })
            elif self.blendshape_node and mc.objExists(self.blendshape_node):
                # blendShapeターゲットからの抽出
                targets = mc.blendShape(self.blendshape_node, query=True, target=True) or []
                aliases = mc.aliasAttr(self.blendshape_node, query=True) or []
                alias_map = {}
                for a_i in range(0, len(aliases), 2):
                    alias_map[aliases[a_i+1]] = aliases[a_i]

                for t_idx, target_name in enumerate(targets):
                    display_name = alias_map.get(target_name, target_name)
                    maya_attr = f"{self.blendshape_node}.{target_name}"
                    cur_val = 0.0
                    try:
                        cur_val = float(mc.getAttr(maya_attr))
                    except Exception:
                        pass

                    self.morph_data_list.append({
                        "index": t_idx,
                        "name_ja": display_name,
                        "name_en": target_name if display_name != target_name else "",
                        "panel": 4,
                        "panel_str": "その他 (Other)",
                        "type": 1,
                        "type_str": "頂点 (Vertex)",
                        "maya_attr": maya_attr,
                        "weight": cur_val,
                    })

        self._populate_table()

    def _populate_table(self):
        """モーフ一覧テーブルの行を生成"""
        self.table_morphs.blockSignals(True)
        self.table_morphs.setRowCount(0)

        filter_panel = self.cbb_panel_filter.currentText()
        filter_text = self.le_search.text().strip().lower()

        visible_rows = 0
        for data in self.morph_data_list:
            # 分類フィルタ
            if filter_panel == "眉" and data["panel"] != 1:
                continue
            elif filter_panel == "目" and data["panel"] != 2:
                continue
            elif filter_panel == "口" and data["panel"] != 3:
                continue
            elif filter_panel == "その他" and data["panel"] != 4:
                continue
            elif filter_panel == "システム" and data["panel"] != 0:
                continue

            # テキスト検索
            if filter_text:
                combined = f"{data['name_ja']} {data['name_en']}".lower()
                if filter_text not in combined:
                    continue

            row = self.table_morphs.rowCount()
            self.table_morphs.insertRow(row)

            item_no = QTableWidgetItem(f"{data['index']}")
            item_no.setTextAlignment(Qt.AlignCenter)
            item_no.setData(Qt.UserRole, data["index"])

            item_ja = QTableWidgetItem(data["name_ja"])
            item_en = QTableWidgetItem(data["name_en"])
            item_panel = QTableWidgetItem(data["panel_str"])
            item_type = QTableWidgetItem(data["type_str"])

            self.table_morphs.setItem(row, 0, item_no)
            self.table_morphs.setItem(row, 1, item_ja)
            self.table_morphs.setItem(row, 2, item_en)
            self.table_morphs.setItem(row, 3, item_panel)
            self.table_morphs.setItem(row, 4, item_type)
            visible_rows += 1

        self.table_morphs.blockSignals(False)

        if visible_rows > 0:
            self.table_morphs.selectRow(0)
        else:
            self._clear_detail_panel()

    def _on_table_selection_changed(self):
        """テーブルの行選択変更時ハンドラ"""
        selected_rows = self.table_morphs.selectionModel().selectedRows()
        if not selected_rows:
            self._clear_detail_panel()
            return

        row = selected_rows[0].row()
        item_no = self.table_morphs.item(row, 0)
        if not item_no:
            return

        orig_idx = item_no.data(Qt.UserRole)
        for data in self.morph_data_list:
            if data["index"] == orig_idx:
                self.selected_morph_index = orig_idx
                self._load_morph_to_ui(data)
                break

    def _load_morph_to_ui(self, data):
        """右ペイン詳細パネルへのモーフデータ読み込み"""
        self._block_signals = True
        self.le_morph_name_ja.setText(data["name_ja"])
        self.le_morph_name_en.setText(data["name_en"])
        self.lbl_panel_type.setText(f"分類: {data['panel_str']}  |  種別: {data['type_str']}")

        attr_text = f"Maya属性: {data['maya_attr']}" if data["maya_attr"] else "Maya属性: (未接続/PMX定義のみ)"
        self.lbl_target_attr.setText(attr_text)

        w = data["weight"]
        self.slider_weight.setValue(int(w * 1000.0))
        self.spin_weight.setValue(w)
        self._block_signals = False

    def _clear_detail_panel(self):
        """詳細パネルの初期化クリア"""
        self.le_morph_name_ja.clear()
        self.le_morph_name_en.clear()
        self.lbl_panel_type.setText("分類: -  |  種別: -")
        self.lbl_target_attr.setText("Maya属性: (未接続)")
        self.slider_weight.setValue(0)
        self.spin_weight.setValue(0.0)

    def _on_slider_value_changed(self, int_val):
        """スライダ値変更ハンドラ"""
        if self._block_signals:
            return
        w = float(int_val) / 1000.0
        self._block_signals = True
        self.spin_weight.setValue(w)
        self._block_signals = False
        self._apply_weight_to_scene(w)

    def _on_spin_value_changed(self, float_val):
        """スピンボックス値変更ハンドラ"""
        if self._block_signals:
            return
        self._block_signals = True
        self.slider_weight.setValue(int(float_val * 1000.0))
        self._block_signals = False
        self._apply_weight_to_scene(float_val)

    def _set_preset_weight(self, preset_val):
        """プリセット値の適用"""
        self.spin_weight.setValue(preset_val)

    def _apply_weight_to_scene(self, weight):
        """Mayaシーン上のblendShapeアトリビュートへウェイトを書き込み"""
        if self.selected_morph_index < 0:
            return

        for data in self.morph_data_list:
            if data["index"] == self.selected_morph_index:
                data["weight"] = weight
                maya_attr = data["maya_attr"]
                if maya_attr and mc.objExists(maya_attr):
                    try:
                        mc.setAttr(maya_attr, weight)
                    except Exception as e:
                        mc.warning(f"モーフウェイトの反映に失敗しました ({maya_attr}): {e}")
                break

    def _reset_current_weight(self):
        """現在選択モーフのウェイトを0にリセット"""
        self.spin_weight.setValue(0.0)

    def _reset_all_weights(self):
        """すべてのモーフのウェイトを一括リセット"""
        for data in self.morph_data_list:
            data["weight"] = 0.0
            maya_attr = data["maya_attr"]
            if maya_attr and mc.objExists(maya_attr):
                try:
                    mc.setAttr(maya_attr, 0.0)
                except Exception:
                    pass
        self.spin_weight.setValue(0.0)

    def _filter_morph_list(self):
        """フィルター条件変更時のテーブル再描画"""
        self._populate_table()

    def _clear_filters(self):
        """検索フィルターのクリア"""
        self.cbb_panel_filter.setCurrentIndex(0)
        self.le_search.clear()

