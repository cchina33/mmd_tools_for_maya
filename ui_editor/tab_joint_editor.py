# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MMD Model Editor Joint管理タブモジュール
MMDモデルのJoint（剛体間拘束・コンストレイント）の一覧表示および接続・制限・ばね定数の編集を提供します。
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
        QSplitter, QScrollArea, QGroupBox, QDoubleSpinBox,
        QFrame, QMessageBox
    )
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QSplitter, QScrollArea, QGroupBox, QDoubleSpinBox,
        QFrame, QMessageBox
    )


class JointEditorTabWidget(QWidget):
    """
    MMD Model Editor Joint管理タブウィジェット
    剛体間拘束の一覧表示および制限角度・移動範囲・ばねパラメータの確認・編集を行います。
    """

    def __init__(self, parent=None):
        super(JointEditorTabWidget, self).__init__(parent)
        self.current_model = None
        self.joint_data_list = []
        self.selected_joint_index = -1
        self._block_signals = False

        self._init_ui()

    def _init_ui(self):
        """ユーザーインターフェースの初期化"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 水平スプリッター (左: Joint一覧、右: 詳細属性)
        self.splitter = QSplitter(Qt.Horizontal)

        # -------------------------------------------------------------
        # 左ペイン: Joint一覧テーブル・検索
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
        self.le_search.setPlaceholderText("Joint名 / 剛体名で検索...")
        self.le_search.textChanged.connect(self._filter_joint_list)
        btn_clear = QPushButton("クリア")
        btn_clear.setFixedWidth(50)
        btn_clear.clicked.connect(lambda: self.le_search.clear())

        search_layout.addWidget(lbl_search)
        search_layout.addWidget(self.le_search)
        search_layout.addWidget(btn_clear)
        left_layout.addLayout(search_layout)

        # テーブル
        self.table_joints = QTableWidget()
        self.table_joints.setColumnCount(4)
        self.table_joints.setHorizontalHeaderLabels(["No", "Joint名 (日本語)", "接続剛体A", "接続剛体B"])
        self.table_joints.horizontalHeader().setStretchLastSection(True)
        self.table_joints.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_joints.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_joints.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_joints.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_joints.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_joints.setSelectionMode(QTableWidget.SingleSelection)
        self.table_joints.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_joints.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333333;")
        self.table_joints.itemSelectionChanged.connect(self._on_table_selection_changed)
        left_layout.addWidget(self.table_joints)

        btn_refresh = QPushButton("リスト再取得")
        btn_refresh.clicked.connect(self._reload_joint_list)
        left_layout.addWidget(btn_refresh)

        # -------------------------------------------------------------
        # 右ペイン: Joint詳細パラメータ編集パネル
        # -------------------------------------------------------------
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)

        # 基本情報グループ
        grp_base = QGroupBox("Joint基本情報")
        base_layout = QVBoxLayout(grp_base)
        base_layout.setSpacing(6)

        lbl_ja = QLabel("Joint名 (日本語):")
        lbl_ja.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.le_joint_name_ja = QLineEdit()
        self.le_joint_name_ja.editingFinished.connect(self._on_parameter_changed)
        base_layout.addWidget(lbl_ja)
        base_layout.addWidget(self.le_joint_name_ja)

        lbl_en = QLabel("Joint名 (英語):")
        lbl_en.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.le_joint_name_en = QLineEdit()
        self.le_joint_name_en.editingFinished.connect(self._on_parameter_changed)
        base_layout.addWidget(lbl_en)
        base_layout.addWidget(self.le_joint_name_en)

        h_conn = QHBoxLayout()
        self.lbl_rb_a = QLabel("剛体A: (未接続)")
        self.lbl_rb_a.setStyleSheet("color: #52b7ff; font-weight: bold;")
        self.lbl_rb_b = QLabel("剛体B: (未接続)")
        self.lbl_rb_b.setStyleSheet("color: #ffaa55; font-weight: bold;")
        h_conn.addWidget(self.lbl_rb_a)
        h_conn.addWidget(self.lbl_rb_b)
        base_layout.addLayout(h_conn)

        right_layout.addWidget(grp_base)

        # 移動制限グループ
        grp_pos_limit = QGroupBox("移動制限 (Position Limits)")
        pos_layout = QVBoxLayout(grp_pos_limit)
        pos_layout.setSpacing(4)

        row_pos_min = QHBoxLayout()
        row_pos_min.addWidget(QLabel("下限 (Min):"))
        self.spin_pos_min_x = self._create_spin()
        self.spin_pos_min_y = self._create_spin()
        self.spin_pos_min_z = self._create_spin()
        row_pos_min.addWidget(self.spin_pos_min_x)
        row_pos_min.addWidget(self.spin_pos_min_y)
        row_pos_min.addWidget(self.spin_pos_min_z)
        pos_layout.addLayout(row_pos_min)

        row_pos_max = QHBoxLayout()
        row_pos_max.addWidget(QLabel("上限 (Max):"))
        self.spin_pos_max_x = self._create_spin()
        self.spin_pos_max_y = self._create_spin()
        self.spin_pos_max_z = self._create_spin()
        row_pos_max.addWidget(self.spin_pos_max_x)
        row_pos_max.addWidget(self.spin_pos_max_y)
        row_pos_max.addWidget(self.spin_pos_max_z)
        pos_layout.addLayout(row_pos_max)

        right_layout.addWidget(grp_pos_limit)

        # 回転制限グループ
        grp_rot_limit = QGroupBox("回転制限 (Rotation Limits [deg])")
        rot_layout = QVBoxLayout(grp_rot_limit)
        rot_layout.setSpacing(4)

        row_rot_min = QHBoxLayout()
        row_rot_min.addWidget(QLabel("下限 (Min):"))
        self.spin_rot_min_x = self._create_spin(-360.0, 360.0)
        self.spin_rot_min_y = self._create_spin(-360.0, 360.0)
        self.spin_rot_min_z = self._create_spin(-360.0, 360.0)
        row_rot_min.addWidget(self.spin_rot_min_x)
        row_rot_min.addWidget(self.spin_rot_min_y)
        row_rot_min.addWidget(self.spin_rot_min_z)
        rot_layout.addLayout(row_rot_min)

        row_rot_max = QHBoxLayout()
        row_rot_max.addWidget(QLabel("上限 (Max):"))
        self.spin_rot_max_x = self._create_spin(-360.0, 360.0)
        self.spin_rot_max_y = self._create_spin(-360.0, 360.0)
        self.spin_rot_max_z = self._create_spin(-360.0, 360.0)
        row_rot_max.addWidget(self.spin_rot_max_x)
        row_rot_max.addWidget(self.spin_rot_max_y)
        row_rot_max.addWidget(self.spin_rot_max_z)
        rot_layout.addLayout(row_rot_max)

        right_layout.addWidget(grp_rot_limit)

        # ばね定数グループ
        grp_spring = QGroupBox("ばね定数 (Spring Constants)")
        spring_layout = QVBoxLayout(grp_spring)
        spring_layout.setSpacing(4)

        row_sp_pos = QHBoxLayout()
        row_sp_pos.addWidget(QLabel("移動ばね:"))
        self.spin_sp_pos_x = self._create_spin(0.0, 100000.0)
        self.spin_sp_pos_y = self._create_spin(0.0, 100000.0)
        self.spin_sp_pos_z = self._create_spin(0.0, 100000.0)
        row_sp_pos.addWidget(self.spin_sp_pos_x)
        row_sp_pos.addWidget(self.spin_sp_pos_y)
        row_sp_pos.addWidget(self.spin_sp_pos_z)
        spring_layout.addLayout(row_sp_pos)

        row_sp_rot = QHBoxLayout()
        row_sp_rot.addWidget(QLabel("回転ばね:"))
        self.spin_sp_rot_x = self._create_spin(0.0, 100000.0)
        self.spin_sp_rot_y = self._create_spin(0.0, 100000.0)
        self.spin_sp_rot_z = self._create_spin(0.0, 100000.0)
        row_sp_rot.addWidget(self.spin_sp_rot_x)
        row_sp_rot.addWidget(self.spin_sp_rot_y)
        row_sp_rot.addWidget(self.spin_sp_rot_z)
        spring_layout.addLayout(row_sp_rot)

        right_layout.addWidget(grp_spring)

        right_layout.addStretch()
        right_scroll.setWidget(right_widget)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_scroll)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 5)

        main_layout.addWidget(self.splitter)

    def _create_spin(self, min_val=-10000.0, max_val=10000.0):
        """スピンボックス生成ヘルパー"""
        sb = QDoubleSpinBox()
        sb.setRange(min_val, max_val)
        sb.setDecimals(3)
        sb.valueChanged.connect(self._on_parameter_changed)
        return sb

    def set_target_model(self, model_node):
        """対象モデルを受け取り、Joint一覧を構築"""
        self.current_model = model_node
        try:
            self._reload_joint_list()
        except Exception as e:
            print(f"[Jointタブ 警告] Joint一覧の読み込み中に軽微な例外を捕捉: {e}")

    def _reload_joint_list(self):
        """PMXデータからJoint情報を抽出"""
        import json
        self.joint_data_list = []
        self.selected_joint_index = -1

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

        pmx_joints = []
        rigid_names = []
        if pmx_path:
            try:
                try:
                    from .. import mmd_parser
                except Exception:
                    import mmd_parser
                pmx_model = mmd_parser.pmx.load(pmx_path)
                pmx_joints = getattr(pmx_model, 'joints', [])
                rigid_names = [rb.name for rb in getattr(pmx_model, 'rigid_bodies', [])]
            except Exception:
                pmx_joints = []

        if pmx_joints:
            for j_idx, jt in enumerate(pmx_joints):
                ra_idx = getattr(jt, 'rigid_body_a', -1)
                rb_idx = getattr(jt, 'rigid_body_b', -1)
                ra_name = rigid_names[ra_idx] if 0 <= ra_idx < len(rigid_names) else "(なし)"
                rb_name = rigid_names[rb_idx] if 0 <= rb_idx < len(rigid_names) else "(なし)"

                p_min = getattr(jt, 'linear_limit_min', getattr(jt, 'position_min', [0.0, 0.0, 0.0]))
                p_max = getattr(jt, 'linear_limit_max', getattr(jt, 'position_max', [0.0, 0.0, 0.0]))
                r_min = getattr(jt, 'angular_limit_min', getattr(jt, 'rotation_min', [0.0, 0.0, 0.0]))
                r_max = getattr(jt, 'angular_limit_max', getattr(jt, 'rotation_max', [0.0, 0.0, 0.0]))
                s_pos = getattr(jt, 'linear_spring', getattr(jt, 'spring_position', [0.0, 0.0, 0.0]))
                s_rot = getattr(jt, 'angular_spring', getattr(jt, 'spring_rotation', [0.0, 0.0, 0.0]))

                self.joint_data_list.append({
                    "index": j_idx,
                    "name_ja": jt.name,
                    "name_en": getattr(jt, 'name_e', '') or '',
                    "rigid_a": ra_name,
                    "rigid_b": rb_name,
                    "pos_min": p_min,
                    "pos_max": p_max,
                    "rot_min": r_min,
                    "rot_max": r_max,
                    "spring_pos": s_pos,
                    "spring_rot": s_rot,
                })
        else:
            # PMXファイル未検出時、ノード構造メタデータからの復元探索
            st_data = None
            for n in nodes_to_search:
                if n and mc.objExists(n) and mc.attributeQuery("mmdModelStructure", node=n, exists=True):
                    try:
                        raw_json = mc.getAttr(f"{n}.mmdModelStructure")
                        st_data = json.loads(raw_json)
                        if st_data and st_data.get("joints"):
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
                jt_list = st_data.get("joints", [])
                rb_list = st_data.get("rigid_bodies", [])
                rb_names = [rb.get("name", "") for rb in rb_list] if isinstance(rb_list, list) else []

                for j_idx, jt in enumerate(jt_list):
                    ra_idx = jt.get("rigid_body_a", -1)
                    rb_idx = jt.get("rigid_body_b", -1)
                    ra_name = rb_names[ra_idx] if 0 <= ra_idx < len(rb_names) else "(なし)"
                    rb_name = rb_names[rb_idx] if 0 <= rb_idx < len(rb_names) else "(なし)"

                    p_min = jt.get("linear_limit_min", jt.get("position_min", [0.0, 0.0, 0.0]))
                    p_max = jt.get("linear_limit_max", jt.get("position_max", [0.0, 0.0, 0.0]))
                    r_min = jt.get("angular_limit_min", jt.get("rotation_min", [0.0, 0.0, 0.0]))
                    r_max = jt.get("angular_limit_max", jt.get("rotation_max", [0.0, 0.0, 0.0]))
                    s_pos = jt.get("linear_spring", jt.get("spring_position", [0.0, 0.0, 0.0]))
                    s_rot = jt.get("angular_spring", jt.get("spring_rotation", [0.0, 0.0, 0.0]))

                    self.joint_data_list.append({
                        "index": j_idx,
                        "name_ja": jt.get("name", f"Joint_{j_idx}"),
                        "name_en": jt.get("name_e", ""),
                        "rigid_a": ra_name,
                        "rigid_b": rb_name,
                        "pos_min": p_min,
                        "pos_max": p_max,
                        "rot_min": r_min,
                        "rot_max": r_max,
                        "spring_pos": s_pos,
                        "spring_rot": s_rot,
                    })

        # それでも見つからない場合、シーン内のJointノードから探索
        if not self.joint_data_list:
            joint_transforms = [tr for tr in mc.ls(type="transform") or [] if any(k in tr.lower() for k in ["joint", "constraint", "mmd_jt"])]
            for j_idx, tr in enumerate(joint_transforms):
                self.joint_data_list.append({
                    "index": j_idx,
                    "name_ja": tr.split("|")[-1],
                    "name_en": "",
                    "rigid_a": "(シーンノード)",
                    "rigid_b": "(シーンノード)",
                    "pos_min": [0.0, 0.0, 0.0],
                    "pos_max": [0.0, 0.0, 0.0],
                    "rot_min": [0.0, 0.0, 0.0],
                    "rot_max": [0.0, 0.0, 0.0],
                    "spring_pos": [0.0, 0.0, 0.0],
                    "spring_rot": [0.0, 0.0, 0.0],
                })

        self._populate_table()

        for j_idx, jt in enumerate(pmx_joints):
            ra_idx = getattr(jt, 'rigid_body_a', -1)
            rb_idx = getattr(jt, 'rigid_body_b', -1)
            ra_name = rigid_names[ra_idx] if 0 <= ra_idx < len(rigid_names) else "(なし)"
            rb_name = rigid_names[rb_idx] if 0 <= rb_idx < len(rigid_names) else "(なし)"

            p_min = getattr(jt, 'position_min', [0.0, 0.0, 0.0])
            p_max = getattr(jt, 'position_max', [0.0, 0.0, 0.0])
            r_min = getattr(jt, 'rotation_min', [0.0, 0.0, 0.0])
            r_max = getattr(jt, 'rotation_max', [0.0, 0.0, 0.0])
            s_pos = getattr(jt, 'spring_position', [0.0, 0.0, 0.0])
            s_rot = getattr(jt, 'spring_rotation', [0.0, 0.0, 0.0])

            self.joint_data_list.append({
                "index": j_idx,
                "name_ja": jt.name,
                "name_en": getattr(jt, 'name_e', '') or '',
                "rigid_a": ra_name,
                "rigid_b": rb_name,
                "pos_min": p_min,
                "pos_max": p_max,
                "rot_min": r_min,
                "rot_max": r_max,
                "spring_pos": s_pos,
                "spring_rot": s_rot,
            })

        self._populate_table()

    def _populate_table(self):
        """Joint一覧テーブルの行を生成"""
        self.table_joints.blockSignals(True)
        self.table_joints.setRowCount(0)

        filter_text = self.le_search.text().strip().lower()

        visible_rows = 0
        for data in self.joint_data_list:
            if filter_text:
                combined = f"{data['name_ja']} {data['name_en']} {data['rigid_a']} {data['rigid_b']}".lower()
                if filter_text not in combined:
                    continue

            row = self.table_joints.rowCount()
            self.table_joints.insertRow(row)

            item_no = QTableWidgetItem(f"{data['index']}")
            item_no.setTextAlignment(Qt.AlignCenter)
            item_no.setData(Qt.UserRole, data["index"])

            item_ja = QTableWidgetItem(data["name_ja"])
            item_ra = QTableWidgetItem(data["rigid_a"])
            item_rb = QTableWidgetItem(data["rigid_b"])

            self.table_joints.setItem(row, 0, item_no)
            self.table_joints.setItem(row, 1, item_ja)
            self.table_joints.setItem(row, 2, item_ra)
            self.table_joints.setItem(row, 3, item_rb)
            visible_rows += 1

        self.table_joints.blockSignals(False)

        if visible_rows > 0:
            self.table_joints.selectRow(0)
        else:
            self._clear_detail_panel()

    def _on_table_selection_changed(self):
        """行選択変更時ハンドラ"""
        selected_rows = self.table_joints.selectionModel().selectedRows()
        if not selected_rows:
            self._clear_detail_panel()
            return

        row = selected_rows[0].row()
        item_no = self.table_joints.item(row, 0)
        if not item_no:
            return

        orig_idx = item_no.data(Qt.UserRole)
        for data in self.joint_data_list:
            if data["index"] == orig_idx:
                self.selected_joint_index = orig_idx
                self._load_joint_to_ui(data)
                break

    def _load_joint_to_ui(self, data):
        """右ペイン詳細パネルへの読み込み"""
        self._block_signals = True
        self.le_joint_name_ja.setText(data["name_ja"])
        self.le_joint_name_en.setText(data["name_en"])
        self.lbl_rb_a.setText(f"剛体A: {data['rigid_a']}")
        self.lbl_rb_b.setText(f"剛体B: {data['rigid_b']}")

        p_min = data["pos_min"]
        p_max = data["pos_max"]
        self.spin_pos_min_x.setValue(p_min[0])
        self.spin_pos_min_y.setValue(p_min[1])
        self.spin_pos_min_z.setValue(p_min[2])
        self.spin_pos_max_x.setValue(p_max[0])
        self.spin_pos_max_y.setValue(p_max[1])
        self.spin_pos_max_z.setValue(p_max[2])

        r_min = data["rot_min"]
        r_max = data["rot_max"]
        self.spin_rot_min_x.setValue(r_min[0])
        self.spin_rot_min_y.setValue(r_min[1])
        self.spin_rot_min_z.setValue(r_min[2])
        self.spin_rot_max_x.setValue(r_max[0])
        self.spin_rot_max_y.setValue(r_max[1])
        self.spin_rot_max_z.setValue(r_max[2])

        sp_p = data["spring_pos"]
        sp_r = data["spring_rot"]
        self.spin_sp_pos_x.setValue(sp_p[0])
        self.spin_sp_pos_y.setValue(sp_p[1])
        self.spin_sp_pos_z.setValue(sp_p[2])
        self.spin_sp_rot_x.setValue(sp_r[0])
        self.spin_sp_rot_y.setValue(sp_r[1])
        self.spin_sp_rot_z.setValue(sp_r[2])
        self._block_signals = False

    def _clear_detail_panel(self):
        """詳細パネルのクリア"""
        self.le_joint_name_ja.clear()
        self.le_joint_name_en.clear()
        self.lbl_rb_a.setText("剛体A: (未接続)")
        self.lbl_rb_b.setText("剛体B: (未接続)")

    def _on_parameter_changed(self, *args):
        """パラメータ変更ハンドラ"""
        if self._block_signals or self.selected_joint_index < 0:
            return

        data = None
        for d in self.joint_data_list:
            if d["index"] == self.selected_joint_index:
                data = d
                break
        if not data:
            return

        data["name_ja"] = self.le_joint_name_ja.text().strip()
        data["name_en"] = self.le_joint_name_en.text().strip()

        data["pos_min"] = [self.spin_pos_min_x.value(), self.spin_pos_min_y.value(), self.spin_pos_min_z.value()]
        data["pos_max"] = [self.spin_pos_max_x.value(), self.spin_pos_max_y.value(), self.spin_pos_max_z.value()]
        data["rot_min"] = [self.spin_rot_min_x.value(), self.spin_rot_min_y.value(), self.spin_rot_min_z.value()]
        data["rot_max"] = [self.spin_rot_max_x.value(), self.spin_rot_max_y.value(), self.spin_rot_max_z.value()]
        data["spring_pos"] = [self.spin_sp_pos_x.value(), self.spin_sp_pos_y.value(), self.spin_sp_pos_z.value()]
        data["spring_rot"] = [self.spin_sp_rot_x.value(), self.spin_sp_rot_y.value(), self.spin_sp_rot_z.value()]

        # テーブル更新
        for r in range(self.table_joints.rowCount()):
            item_no = self.table_joints.item(r, 0)
            if item_no and item_no.data(Qt.UserRole) == self.selected_joint_index:
                self.table_joints.item(r, 1).setText(data["name_ja"])
                break

    def _filter_joint_list(self):
        """絞り込み"""
        self._populate_table()

