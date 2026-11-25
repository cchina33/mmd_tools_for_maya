# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MMD Model Editor 剛体管理タブモジュール
MMDモデルの剛体（物理コライダー）の一覧表示、衝突グループ、形状、および物理パラメータの確認・編集を提供します。
"""

import os
import sys
import maya.cmds as mc

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QSplitter, QScrollArea, QGroupBox, QComboBox, QDoubleSpinBox,
        QSpinBox, QFrame, QMessageBox
    )
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QSplitter, QScrollArea, QGroupBox, QComboBox, QDoubleSpinBox,
        QSpinBox, QFrame, QMessageBox
    )

SHAPE_NAMES = {
    0: "球 (Sphere)",
    1: "箱 (Box)",
    2: "カプセル (Capsule)",
}

MODE_NAMES = {
    0: "ボーン追従 (Kinematic)",
    1: "物理演算 (Dynamic)",
    2: "物理+ボーン位置合わせ",
}


class RigidBodyEditorTabWidget(QWidget):
    """
    MMD Model Editor 剛体管理タブウィジェット
    剛体コライダーの一覧表示および形状・質量・衝突グループの属性編集を行います。
    """

    def __init__(self, parent=None):
        super(RigidBodyEditorTabWidget, self).__init__(parent)
        self.current_model = None
        self.rigid_data_list = []
        self.selected_rigid_index = -1
        self._block_signals = False

        self._init_ui()

    def _init_ui(self):
        """ユーザーインターフェースの初期化"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 水平スプリッター (左: 剛体一覧、右: 詳細属性)
        self.splitter = QSplitter(Qt.Horizontal)

        # -------------------------------------------------------------
        # 左ペイン: 剛体一覧テーブル・検索
        # -------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(6)

        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)
        lbl_search = QLabel("絞り込み:")
        lbl_search.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText("剛体名 / ボーン名で検索...")
        self.le_search.textChanged.connect(self._filter_rigid_list)
        btn_clear = QPushButton("クリア")
        btn_clear.setFixedWidth(50)
        btn_clear.clicked.connect(lambda: self.le_search.clear())

        search_layout.addWidget(lbl_search)
        search_layout.addWidget(self.le_search)
        search_layout.addWidget(btn_clear)
        left_layout.addLayout(search_layout)

        # テーブル
        self.table_rigids = QTableWidget()
        self.table_rigids.setColumnCount(6)
        self.table_rigids.setHorizontalHeaderLabels(["No", "剛体名 (日本語)", "関連ボーン", "グループ", "形状", "剛体タイプ"])
        self.table_rigids.horizontalHeader().setStretchLastSection(True)
        self.table_rigids.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_rigids.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_rigids.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_rigids.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_rigids.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_rigids.setSelectionMode(QTableWidget.SingleSelection)
        self.table_rigids.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_rigids.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333333;")
        self.table_rigids.itemSelectionChanged.connect(self._on_table_selection_changed)
        left_layout.addWidget(self.table_rigids)

        # 下部ボタン群
        btn_layout = QHBoxLayout()
        btn_refresh = QPushButton("リスト再取得")
        btn_refresh.clicked.connect(self._reload_rigid_list)
        btn_layout.addWidget(btn_refresh)
        left_layout.addLayout(btn_layout)

        # -------------------------------------------------------------
        # 右ペイン: 剛体詳細パラメータ編集パネル
        # -------------------------------------------------------------
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)

        # 基本情報グループ
        grp_base = QGroupBox("剛体基本情報")
        base_layout = QVBoxLayout(grp_base)
        base_layout.setSpacing(6)

        lbl_ja = QLabel("剛体名 (日本語):")
        lbl_ja.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.le_rigid_name_ja = QLineEdit()
        self.le_rigid_name_ja.editingFinished.connect(self._on_parameter_changed)
        base_layout.addWidget(lbl_ja)
        base_layout.addWidget(self.le_rigid_name_ja)

        lbl_en = QLabel("剛体名 (英語):")
        lbl_en.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.le_rigid_name_en = QLineEdit()
        self.le_rigid_name_en.editingFinished.connect(self._on_parameter_changed)
        base_layout.addWidget(lbl_en)
        base_layout.addWidget(self.le_rigid_name_en)

        lbl_bone = QLabel("関連ボーン:")
        lbl_bone.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.lbl_bone_name = QLabel("(未設定)")
        self.lbl_bone_name.setStyleSheet("color: #52b7ff; font-weight: bold;")
        base_layout.addWidget(lbl_bone)
        base_layout.addWidget(self.lbl_bone_name)

        right_layout.addWidget(grp_base)

        # 形状・グループグループ
        grp_shape = QGroupBox("形状・衝突グループ")
        shape_layout = QVBoxLayout(grp_shape)
        shape_layout.setSpacing(6)

        h_shape = QHBoxLayout()
        lbl_shape_t = QLabel("形状種別:")
        self.cbb_shape_type = QComboBox()
        self.cbb_shape_type.addItems(["球 (Sphere)", "箱 (Box)", "カプセル (Capsule)"])
        self.cbb_shape_type.currentIndexChanged.connect(self._on_parameter_changed)
        h_shape.addWidget(lbl_shape_t)
        h_shape.addWidget(self.cbb_shape_type)
        shape_layout.addLayout(h_shape)

        h_size = QHBoxLayout()
        lbl_size_r = QLabel("半径 / 幅:")
        self.spin_size_r = QDoubleSpinBox()
        self.spin_size_r.setRange(0.01, 1000.0)
        self.spin_size_r.setDecimals(3)
        self.spin_size_r.valueChanged.connect(self._on_parameter_changed)

        lbl_size_h = QLabel("高さ:")
        self.spin_size_h = QDoubleSpinBox()
        self.spin_size_h.setRange(0.01, 1000.0)
        self.spin_size_h.setDecimals(3)
        self.spin_size_h.valueChanged.connect(self._on_parameter_changed)

        lbl_size_d = QLabel("奥行き:")
        self.spin_size_d = QDoubleSpinBox()
        self.spin_size_d.setRange(0.01, 1000.0)
        self.spin_size_d.setDecimals(3)
        self.spin_size_d.valueChanged.connect(self._on_parameter_changed)

        h_size.addWidget(lbl_size_r)
        h_size.addWidget(self.spin_size_r)
        h_size.addWidget(lbl_size_h)
        h_size.addWidget(self.spin_size_h)
        h_size.addWidget(lbl_size_d)
        h_size.addWidget(self.spin_size_d)
        shape_layout.addLayout(h_size)

        h_group = QHBoxLayout()
        lbl_grp_idx = QLabel("衝突グループ (0〜15):")
        self.spin_group = QSpinBox()
        self.spin_group.setRange(0, 15)
        self.spin_group.valueChanged.connect(self._on_parameter_changed)

        lbl_mode_idx = QLabel("剛体タイプ:")
        self.cbb_mode = QComboBox()
        self.cbb_mode.addItems(["ボーン追従 (Kinematic)", "物理演算 (Dynamic)", "物理+ボーン位置合わせ"])
        self.cbb_mode.currentIndexChanged.connect(self._on_parameter_changed)

        h_group.addWidget(lbl_grp_idx)
        h_group.addWidget(self.spin_group)
        h_group.addWidget(lbl_mode_idx)
        h_group.addWidget(self.cbb_mode)
        shape_layout.addLayout(h_group)

        right_layout.addWidget(grp_shape)

        # 物理パラメータグループ
        grp_physics = QGroupBox("物理特性パラメータ")
        physics_layout = QVBoxLayout(grp_physics)
        physics_layout.setSpacing(6)

        row_phys1 = QHBoxLayout()
        lbl_mass = QLabel("質量:")
        self.spin_mass = QDoubleSpinBox()
        self.spin_mass.setRange(0.0, 10000.0)
        self.spin_mass.setDecimals(3)
        self.spin_mass.valueChanged.connect(self._on_parameter_changed)

        lbl_repulsion = QLabel("反発力:")
        self.spin_repulsion = QDoubleSpinBox()
        self.spin_repulsion.setRange(0.0, 10.0)
        self.spin_repulsion.setDecimals(3)
        self.spin_repulsion.valueChanged.connect(self._on_parameter_changed)

        lbl_friction = QLabel("摩擦力:")
        self.spin_friction = QDoubleSpinBox()
        self.spin_friction.setRange(0.0, 10.0)
        self.spin_friction.setDecimals(3)
        self.spin_friction.valueChanged.connect(self._on_parameter_changed)

        row_phys1.addWidget(lbl_mass)
        row_phys1.addWidget(self.spin_mass)
        row_phys1.addWidget(lbl_repulsion)
        row_phys1.addWidget(self.spin_repulsion)
        row_phys1.addWidget(lbl_friction)
        row_phys1.addWidget(self.spin_friction)
        physics_layout.addLayout(row_phys1)

        row_phys2 = QHBoxLayout()
        lbl_damp_pos = QLabel("移動減衰:")
        self.spin_damp_pos = QDoubleSpinBox()
        self.spin_damp_pos.setRange(0.0, 10.0)
        self.spin_damp_pos.setDecimals(3)
        self.spin_damp_pos.valueChanged.connect(self._on_parameter_changed)

        lbl_damp_rot = QLabel("回転減衰:")
        self.spin_damp_rot = QDoubleSpinBox()
        self.spin_damp_rot.setRange(0.0, 10.0)
        self.spin_damp_rot.setDecimals(3)
        self.spin_damp_rot.valueChanged.connect(self._on_parameter_changed)

        row_phys2.addWidget(lbl_damp_pos)
        row_phys2.addWidget(self.spin_damp_pos)
        row_phys2.addWidget(lbl_damp_rot)
        row_phys2.addWidget(self.spin_damp_rot)
        physics_layout.addLayout(row_phys2)

        right_layout.addWidget(grp_physics)

        right_layout.addStretch()
        right_scroll.setWidget(right_widget)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_scroll)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 5)

        main_layout.addWidget(self.splitter)

    def set_target_model(self, model_node):
        """対象モデルを受け取り、剛体一覧を構築"""
        self.current_model = model_node
        try:
            self._reload_rigid_list()
        except Exception as e:
            print(f"[剛体タブ 警告] 剛体一覧の読み込み中に軽微な例外を捕捉: {e}")

    def _reload_rigid_list(self):
        """PMXデータおよびシーン内剛体ノードから剛体情報を抽出"""
        import json
        self.rigid_data_list = []
        self.selected_rigid_index = -1

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

        # PMXファイルパスの探索 (モデル、親、子孫ノード)
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

        pmx_rigids = []
        bone_names = []
        if pmx_path:
            try:
                try:
                    from .. import mmd_parser
                except Exception:
                    import mmd_parser
                pmx_model = mmd_parser.pmx.load(pmx_path)
                pmx_rigids = getattr(pmx_model, 'rigid_bodies', [])
                bone_names = [b.name for b in getattr(pmx_model, 'bones', [])]
            except Exception:
                pmx_rigids = []

        if pmx_rigids:
            for r_idx, rb in enumerate(pmx_rigids):
                b_idx = getattr(rb, 'bone_index', getattr(rb, 'bone', -1))
                b_name = bone_names[b_idx] if 0 <= b_idx < len(bone_names) else "(なし)"
                shape_val = getattr(rb, 'shape_type', getattr(rb, 'shape', 0))
                mode_val = getattr(rb, 'physics_mode', getattr(rb, 'mode', 0))
                sz = getattr(rb, 'size', [1.0, 1.0, 1.0])
                grp_val = getattr(rb, 'group', getattr(rb, 'collision_group', 0))

                self.rigid_data_list.append({
                    "index": r_idx,
                    "name_ja": rb.name,
                    "name_en": getattr(rb, 'name_e', '') or '',
                    "bone_name": b_name,
                    "bone_index": b_idx,
                    "group": grp_val,
                    "shape": shape_val,
                    "shape_str": SHAPE_NAMES.get(shape_val, f"形状{shape_val}"),
                    "mode": mode_val,
                    "mode_str": MODE_NAMES.get(mode_val, f"モード{mode_val}"),
                    "size_r": sz[0] if len(sz) > 0 else 1.0,
                    "size_h": sz[1] if len(sz) > 1 else 1.0,
                    "size_d": sz[2] if len(sz) > 2 else 1.0,
                    "mass": getattr(rb, 'mass', 1.0),
                    "repulsion": getattr(rb, 'restitution', getattr(rb, 'repulsion', 0.0)),
                    "friction": getattr(rb, 'friction', 0.5),
                    "damp_pos": getattr(rb, 'linear_damping', getattr(rb, 'damping_position', 0.0)),
                    "damp_rot": getattr(rb, 'angular_damping', getattr(rb, 'damping_rotation', 0.0)),
                })
        else:
            # PMXファイル未検出時、ノード構造メタデータからの復元探索
            st_data = None
            for n in nodes_to_search:
                if n and mc.objExists(n) and mc.attributeQuery("mmdModelStructure", node=n, exists=True):
                    try:
                        raw_json = mc.getAttr(f"{n}.mmdModelStructure")
                        st_data = json.loads(raw_json)
                        if st_data and st_data.get("rigid_bodies"):
                            break
                    except Exception:
                        pass

            if not st_data:
                # キャッシュJSONからのフォールバック探索
                try:
                    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    cache_path = os.path.join(plugin_root, 'asset', 'last_imported_structure.json')
                    if os.path.isfile(cache_path):
                        with open(cache_path, 'r', encoding='utf-8') as f:
                            st_data = json.load(f)
                except Exception:
                    pass

            if st_data:
                rb_list = st_data.get("rigid_bodies", [])
                b_list = st_data.get("bones", [])
                b_names = [b.get("name", "") for b in b_list] if isinstance(b_list, list) else []

                for r_idx, rb in enumerate(rb_list):
                    b_idx = rb.get("bone_index", rb.get("bone", -1))
                    b_name = b_names[b_idx] if 0 <= b_idx < len(b_names) else "(なし)"
                    shape_val = rb.get("shape_type", rb.get("shape", 0))
                    mode_val = rb.get("physics_mode", rb.get("mode", 0))
                    sz = rb.get("size", [1.0, 1.0, 1.0])
                    grp_val = rb.get("group", rb.get("collision_group", 0))

                    self.rigid_data_list.append({
                        "index": r_idx,
                        "name_ja": rb.get("name", f"剛体_{r_idx}"),
                        "name_en": rb.get("name_e", ""),
                        "bone_name": b_name,
                        "bone_index": b_idx,
                        "group": grp_val,
                        "shape": shape_val,
                        "shape_str": SHAPE_NAMES.get(shape_val, f"形状{shape_val}"),
                        "mode": mode_val,
                        "mode_str": MODE_NAMES.get(mode_val, f"モード{mode_val}"),
                        "size_r": sz[0] if len(sz) > 0 else 1.0,
                        "size_h": sz[1] if len(sz) > 1 else 1.0,
                        "size_d": sz[2] if len(sz) > 2 else 1.0,
                        "mass": rb.get("mass", 1.0),
                        "repulsion": rb.get("restitution", rb.get("repulsion", 0.0)),
                        "friction": rb.get("friction", 0.5),
                        "damp_pos": rb.get("linear_damping", rb.get("damping_position", 0.0)),
                        "damp_rot": rb.get("angular_damping", rb.get("damping_rotation", 0.0)),
                    })

        # それでも見つからない場合、シーン内の剛体Transformノードから探索
        if not self.rigid_data_list:
            rigid_transforms = [tr for tr in mc.ls(type="transform") or [] if any(k in tr.lower() for k in ["rigid", "rigidbody", "mmd_rb"])]
            for r_idx, tr in enumerate(rigid_transforms):
                self.rigid_data_list.append({
                    "index": r_idx,
                    "name_ja": tr.split("|")[-1],
                    "name_en": "",
                    "bone_name": "(シーンノード)",
                    "bone_index": -1,
                    "group": 0,
                    "shape": 0,
                    "shape_str": "球 (Sphere)",
                    "mode": 0,
                    "mode_str": "ボーン追従 (Kinematic)",
                    "size_r": 1.0,
                    "size_h": 1.0,
                    "size_d": 1.0,
                    "mass": 1.0,
                    "repulsion": 0.0,
                    "friction": 0.5,
                    "damp_pos": 0.0,
                    "damp_rot": 0.0,
                })

        self._populate_table()

    def _populate_table(self):
        """剛体一覧テーブルの行を生成"""
        self.table_rigids.blockSignals(True)
        self.table_rigids.setRowCount(0)

        filter_text = self.le_search.text().strip().lower()

        visible_rows = 0
        for data in self.rigid_data_list:
            if filter_text:
                combined = f"{data['name_ja']} {data['name_en']} {data['bone_name']}".lower()
                if filter_text not in combined:
                    continue

            row = self.table_rigids.rowCount()
            self.table_rigids.insertRow(row)

            item_no = QTableWidgetItem(f"{data['index']}")
            item_no.setTextAlignment(Qt.AlignCenter)
            item_no.setData(Qt.UserRole, data["index"])

            item_ja = QTableWidgetItem(data["name_ja"])
            item_bone = QTableWidgetItem(data["bone_name"])
            item_grp = QTableWidgetItem(f"G{data['group']}")
            item_grp.setTextAlignment(Qt.AlignCenter)
            item_shape = QTableWidgetItem(data["shape_str"])
            item_mode = QTableWidgetItem(data["mode_str"])

            self.table_rigids.setItem(row, 0, item_no)
            self.table_rigids.setItem(row, 1, item_ja)
            self.table_rigids.setItem(row, 2, item_bone)
            self.table_rigids.setItem(row, 3, item_grp)
            self.table_rigids.setItem(row, 4, item_shape)
            self.table_rigids.setItem(row, 5, item_mode)
            visible_rows += 1

        self.table_rigids.blockSignals(False)

        if visible_rows > 0:
            self.table_rigids.selectRow(0)
        else:
            self._clear_detail_panel()

    def _on_table_selection_changed(self):
        """行選択変更時ハンドラ"""
        selected_rows = self.table_rigids.selectionModel().selectedRows()
        if not selected_rows:
            self._clear_detail_panel()
            return

        row = selected_rows[0].row()
        item_no = self.table_rigids.item(row, 0)
        if not item_no:
            return

        orig_idx = item_no.data(Qt.UserRole)
        for data in self.rigid_data_list:
            if data["index"] == orig_idx:
                self.selected_rigid_index = orig_idx
                self._load_rigid_to_ui(data)
                break

    def _load_rigid_to_ui(self, data):
        """右ペイン詳細パネルへの読み込み"""
        self._block_signals = True
        self.le_rigid_name_ja.setText(data["name_ja"])
        self.le_rigid_name_en.setText(data["name_en"])
        self.lbl_bone_name.setText(data["bone_name"])

        self.cbb_shape_type.setCurrentIndex(min(2, max(0, data["shape"])))
        self.spin_size_r.setValue(data["size_r"])
        self.spin_size_h.setValue(data["size_h"])
        self.spin_size_d.setValue(data["size_d"])

        self.spin_group.setValue(data["group"])
        self.cbb_mode.setCurrentIndex(min(2, max(0, data["mode"])))

        self.spin_mass.setValue(data["mass"])
        self.spin_repulsion.setValue(data["repulsion"])
        self.spin_friction.setValue(data["friction"])
        self.spin_damp_pos.setValue(data["damp_pos"])
        self.spin_damp_rot.setValue(data["damp_rot"])
        self._block_signals = False

    def _clear_detail_panel(self):
        """詳細パネルのクリア"""
        self.le_rigid_name_ja.clear()
        self.le_rigid_name_en.clear()
        self.lbl_bone_name.setText("(未設定)")

    def _on_parameter_changed(self, *args):
        """UIパラメータ変更ハンドラ"""
        if self._block_signals or self.selected_rigid_index < 0:
            return

        data = None
        for d in self.rigid_data_list:
            if d["index"] == self.selected_rigid_index:
                data = d
                break
        if not data:
            return

        data["name_ja"] = self.le_rigid_name_ja.text().strip()
        data["name_en"] = self.le_rigid_name_en.text().strip()
        data["shape"] = self.cbb_shape_type.currentIndex()
        data["shape_str"] = SHAPE_NAMES.get(data["shape"], f"形状{data['shape']}")
        data["size_r"] = self.spin_size_r.value()
        data["size_h"] = self.spin_size_h.value()
        data["size_d"] = self.spin_size_d.value()
        data["group"] = self.spin_group.value()
        data["mode"] = self.cbb_mode.currentIndex()
        data["mode_str"] = MODE_NAMES.get(data["mode"], f"モード{data['mode']}")
        data["mass"] = self.spin_mass.value()
        data["repulsion"] = self.spin_repulsion.value()
        data["friction"] = self.spin_friction.value()
        data["damp_pos"] = self.spin_damp_pos.value()
        data["damp_rot"] = self.spin_damp_rot.value()

        # テーブル更新
        for r in range(self.table_rigids.rowCount()):
            item_no = self.table_rigids.item(r, 0)
            if item_no and item_no.data(Qt.UserRole) == self.selected_rigid_index:
                self.table_rigids.item(r, 1).setText(data["name_ja"])
                self.table_rigids.item(r, 3).setText(f"G{data['group']}")
                self.table_rigids.item(r, 4).setText(data["shape_str"])
                self.table_rigids.item(r, 5).setText(data["mode_str"])
                break

    def _filter_rigid_list(self):
        """絞り込み"""
        self._populate_table()

