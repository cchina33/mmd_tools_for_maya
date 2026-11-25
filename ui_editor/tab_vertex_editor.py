# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MMD Model Editor 頂点管理タブモジュール
MMDモデルの頂点（座標・法線・UV・ボーンウェイト・エッジ倍率）の一覧表示およびページング機能を提供します。
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

WEIGHT_TYPE_NAMES = {
    0: "BDEF1",
    1: "BDEF2",
    2: "BDEF4",
    3: "SDEF",
    4: "QDEF",
}


class VertexEditorTabWidget(QWidget):
    """
    MMD Model Editor 頂点管理タブウィジェット
    大容量頂点データをページング表示し、座標・法線・UV・ウェイト配分を確認します。
    """

    def __init__(self, parent=None):
        super(VertexEditorTabWidget, self).__init__(parent)
        self.current_model = None
        self.current_mesh = None
        self.vertices_cache = []
        self.bone_names = []
        self.current_page = 0
        self.page_size = 200
        self.selected_vertex_index = -1
        self._block_signals = False

        self._init_ui()

    def _init_ui(self):
        """ユーザーインターフェースの初期化"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 水平スプリッター (左: 頂点一覧テーブル・ページャー、右: 頂点属性詳細)
        self.splitter = QSplitter(Qt.Horizontal)

        # -------------------------------------------------------------
        # 左ペイン: 頂点一覧テーブル・ページ制御
        # -------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(6)

        # ページネーション・検索バー
        pager_layout = QHBoxLayout()
        pager_layout.setSpacing(4)

        self.btn_prev_page = QPushButton("前へ")
        self.btn_prev_page.setFixedWidth(50)
        self.btn_prev_page.clicked.connect(self._prev_page)

        self.lbl_page_info = QLabel("0 / 0 (計 0 頂点)")
        self.lbl_page_info.setStyleSheet("color: #52b7ff; font-weight: bold;")
        self.lbl_page_info.setAlignment(Qt.AlignCenter)

        self.btn_next_page = QPushButton("次へ")
        self.btn_next_page.setFixedWidth(50)
        self.btn_next_page.clicked.connect(self._next_page)

        lbl_jump = QLabel("移動:")
        self.spin_page_jump = QSpinBox()
        self.spin_page_jump.setRange(1, 1)
        self.spin_page_jump.valueChanged.connect(self._jump_page)

        pager_layout.addWidget(self.btn_prev_page)
        pager_layout.addWidget(self.lbl_page_info)
        pager_layout.addWidget(self.btn_next_page)
        pager_layout.addWidget(lbl_jump)
        pager_layout.addWidget(self.spin_page_jump)
        left_layout.addLayout(pager_layout)

        # テーブル
        self.table_vertices = QTableWidget()
        self.table_vertices.setColumnCount(6)
        self.table_vertices.setHorizontalHeaderLabels(["No", "X", "Y", "Z", "ウェイト種別", "エッジ倍率"])
        self.table_vertices.horizontalHeader().setStretchLastSection(True)
        self.table_vertices.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_vertices.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_vertices.setSelectionMode(QTableWidget.SingleSelection)
        self.table_vertices.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_vertices.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333333;")
        self.table_vertices.itemSelectionChanged.connect(self._on_table_selection_changed)
        left_layout.addWidget(self.table_vertices)

        # 下部操作バー
        bot_layout = QHBoxLayout()
        btn_sel_viewport = QPushButton("ビューポートで頂点を選択")
        btn_sel_viewport.clicked.connect(self._select_vertex_in_viewport)
        btn_refresh = QPushButton("リスト再取得")
        btn_refresh.setFixedWidth(90)
        btn_refresh.clicked.connect(self._reload_vertex_data)

        bot_layout.addWidget(btn_sel_viewport)
        bot_layout.addWidget(btn_refresh)
        left_layout.addLayout(bot_layout)

        # -------------------------------------------------------------
        # 右ペイン: 頂点詳細パラメータ
        # -------------------------------------------------------------
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)

        # 座標グループ
        grp_coord = QGroupBox("頂点座標 (Position XYZ)")
        coord_layout = QVBoxLayout(grp_coord)
        self.lbl_pos_val = QLabel("X: 0.000, Y: 0.000, Z: 0.000")
        self.lbl_pos_val.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px;")
        coord_layout.addWidget(self.lbl_pos_val)
        right_layout.addWidget(grp_coord)

        # 法線・UVグループ
        grp_norm_uv = QGroupBox("法線 (Normal) & テクスチャUV")
        norm_uv_layout = QVBoxLayout(grp_norm_uv)
        self.lbl_norm_val = QLabel("法線: NX: 0.000, NY: 0.000, NZ: 0.000")
        self.lbl_norm_val.setStyleSheet("color: #cccccc;")
        self.lbl_uv_val = QLabel("UV: U: 0.000, V: 0.000")
        self.lbl_uv_val.setStyleSheet("color: #52b7ff;")
        norm_uv_layout.addWidget(self.lbl_norm_val)
        norm_uv_layout.addWidget(self.lbl_uv_val)
        right_layout.addWidget(grp_norm_uv)

        # ウェイト情報グループ
        grp_weight = QGroupBox("スキニングウェイト情報")
        weight_layout = QVBoxLayout(grp_weight)
        weight_layout.setSpacing(6)

        self.lbl_weight_type = QLabel("変形方式: -")
        self.lbl_weight_type.setStyleSheet("color: #ffaa55; font-weight: bold;")
        weight_layout.addWidget(self.lbl_weight_type)

        self.table_weights = QTableWidget()
        self.table_weights.setColumnCount(3)
        self.table_weights.setHorizontalHeaderLabels(["ボーンNo", "ボーン名", "ウェイト値"])
        self.table_weights.horizontalHeader().setStretchLastSection(True)
        self.table_weights.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_weights.verticalHeader().setVisible(False)
        self.table_weights.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_weights.setFixedHeight(120)
        self.table_weights.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333333;")
        weight_layout.addWidget(self.table_weights)

        right_layout.addWidget(grp_weight)

        # エッジ倍率グループ
        grp_edge = QGroupBox("エッジ (輪郭線) 倍率")
        edge_layout = QVBoxLayout(grp_edge)
        self.lbl_edge_scale = QLabel("エッジ倍率: 1.000")
        self.lbl_edge_scale.setStyleSheet("color: #cccccc;")
        edge_layout.addWidget(self.lbl_edge_scale)
        right_layout.addWidget(grp_edge)

        right_layout.addStretch()
        right_scroll.setWidget(right_widget)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_scroll)
        self.splitter.setStretchFactor(0, 6)
        self.splitter.setStretchFactor(1, 4)

        main_layout.addWidget(self.splitter)

    def set_target_model(self, model_node):
        """対象モデルを受け取り、頂点データを読み込み"""
        self.current_model = model_node
        try:
            self._reload_vertex_data()
        except Exception as e:
            print(f"[頂点タブ 警告] 頂点データの読み込み中に軽微な例外を捕捉: {e}")

    def _reload_vertex_data(self):
        """PMXファイルおよびMayaメッシュから頂点データを収集"""
        self.vertices_cache = []
        self.bone_names = []
        self.current_page = 0
        self.selected_vertex_index = -1
        self.current_mesh = None

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

        if not model_node or not mc.objExists(model_node):
            self._update_table_page()
            return

        mesh_node = model_node
        if mc.nodeType(model_node) != "mesh":
            child_meshes = mc.listRelatives(model_node, shapes=True, type="mesh") or []
            if child_meshes:
                mesh_node = child_meshes[0]
            else:
                desc_meshes = mc.listRelatives(model_node, allDescendents=True, type="mesh") or []
                if desc_meshes:
                    mesh_node = desc_meshes[0]
        self.current_mesh = mesh_node

        # PMXファイルパスの探索 (モデル、親、子孫ノード)
        pmx_path = None
        nodes_to_search = [model_node, mesh_node]
        p_nodes = mc.listRelatives(model_node, parent=True) or []
        nodes_to_search.extend(p_nodes)
        desc_nodes = mc.listRelatives(model_node, allDescendents=True) or []
        nodes_to_search.extend(desc_nodes)

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

        pmx_vtx_list = []
        if pmx_path:
            try:
                try:
                    from .. import mmd_parser
                except Exception:
                    import mmd_parser
                pmx_model = mmd_parser.pmx.load(pmx_path)
                pmx_vtx_list = getattr(pmx_model, 'vertices', [])
                self.bone_names = [b.name for b in getattr(pmx_model, 'bones', [])]
            except Exception:
                pmx_vtx_list = []

        if pmx_vtx_list:
            for v_idx, v in enumerate(pmx_vtx_list):
                pos = getattr(v, 'co', getattr(v, 'position', [0.0, 0.0, 0.0]))
                norm = getattr(v, 'normal', [0.0, 1.0, 0.0])
                uv = getattr(v, 'uv', [0.0, 0.0])
                w_obj = getattr(v, 'weight', None)
                w_type = getattr(w_obj, 'type', 0) if w_obj else 0
                edge_scale = getattr(v, 'edge_scale', 1.0)

                # ボーンとウェイトの分解
                bones = getattr(w_obj, 'bones', []) if w_obj else []
                weights = getattr(w_obj, 'weights', []) if w_obj else []

                self.vertices_cache.append({
                    "index": v_idx,
                    "pos": pos,
                    "normal": norm,
                    "uv": uv,
                    "weight_type": w_type,
                    "weight_type_str": WEIGHT_TYPE_NAMES.get(w_type, f"タイプ{w_type}"),
                    "bones": bones,
                    "weights": weights,
                    "edge_scale": edge_scale,
                })
        elif mesh_node and mc.objExists(mesh_node):
            # PMXファイル未検出時、Mayaメッシュから直接抽出
            try:
                target_shape = mesh_node
                if mc.nodeType(mesh_node) != "mesh":
                    shapes = mc.listRelatives(mesh_node, shapes=True, type="mesh") or []
                    if shapes:
                        target_shape = shapes[0]
                    else:
                        desc_shapes = mc.listRelatives(mesh_node, allDescendents=True, type="mesh") or []
                        if desc_shapes:
                            target_shape = desc_shapes[0]

                if target_shape and mc.objExists(target_shape) and mc.nodeType(target_shape) == "mesh":
                    import maya.api.OpenMaya as om
                    sel = om.MSelectionList()
                    sel.add(target_shape)
                    dag_path = sel.getDagPath(0)
                    fn_mesh = om.MFnMesh(dag_path)

                    points = fn_mesh.getPoints(om.MSpace.kObject)
                    normals = fn_mesh.getNormals(om.MSpace.kObject)
                    u_coords, v_coords = fn_mesh.getUVs()
                    num_vtx = fn_mesh.numVertices

                    # スキンクラスタからボーン名リストの取得
                    skin_clusters = mc.listConnections(target_shape, type="skinCluster") or []
                    if skin_clusters:
                        influences = mc.skinCluster(skin_clusters[0], query=True, influence=True) or []
                        self.bone_names = [j.split("|")[-1] for j in influences]

                    for v_idx in range(num_vtx):
                        pt = points[v_idx]
                        pos = (pt.x, pt.y, pt.z)
                        norm = (normals[v_idx].x, normals[v_idx].y, normals[v_idx].z) if v_idx < len(normals) else (0.0, 1.0, 0.0)
                        uv = (u_coords[v_idx], v_coords[v_idx]) if v_idx < len(u_coords) else (0.0, 0.0)

                        self.vertices_cache.append({
                            "index": v_idx,
                            "pos": pos,
                            "normal": norm,
                            "uv": uv,
                            "weight_type": 0,
                            "weight_type_str": "Mayaメッシュ",
                            "bones": [],
                            "weights": [],
                            "edge_scale": 1.0,
                        })
            except Exception as e_api:
                # API取得例外時の簡易フォールバック
                try:
                    num_vtx = mc.polyEvaluate(mesh_node, vertex=True) or 0
                    for v_idx in range(num_vtx):
                        self.vertices_cache.append({
                            "index": v_idx,
                            "pos": (0.0, 0.0, 0.0),
                            "normal": (0.0, 1.0, 0.0),
                            "uv": (0.0, 0.0),
                            "weight_type": 0,
                            "weight_type_str": "Mayaメッシュ",
                            "bones": [],
                            "weights": [],
                            "edge_scale": 1.0,
                        })
                except Exception:
                    pass

        self._update_table_page()

    def _update_table_page(self):
        """現在のページ番号に応じた行をテーブルへ描画"""
        total_vtx = len(self.vertices_cache)
        total_pages = max(1, (total_vtx + self.page_size - 1) // self.page_size)

        self.current_page = max(0, min(self.current_page, total_pages - 1))
        self.lbl_page_info.setText(f"ページ {self.current_page + 1} / {total_pages} (計 {total_vtx:,} 頂点)")

        self._block_signals = True
        self.spin_page_jump.setRange(1, total_pages)
        self.spin_page_jump.setValue(self.current_page + 1)
        self._block_signals = False

        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, total_vtx)
        page_items = self.vertices_cache[start_idx:end_idx]

        self.table_vertices.blockSignals(True)
        self.table_vertices.setRowCount(len(page_items))

        for row, data in enumerate(page_items):
            item_no = QTableWidgetItem(f"{data['index']}")
            item_no.setTextAlignment(Qt.AlignCenter)
            item_no.setData(Qt.UserRole, data["index"])

            p = data["pos"]
            item_x = QTableWidgetItem(f"{p[0]:.3f}")
            item_y = QTableWidgetItem(f"{p[1]:.3f}")
            item_z = QTableWidgetItem(f"{p[2]:.3f}")
            item_w = QTableWidgetItem(data["weight_type_str"])
            item_e = QTableWidgetItem(f"{data['edge_scale']:.2f}")
            item_e.setTextAlignment(Qt.AlignCenter)

            self.table_vertices.setItem(row, 0, item_no)
            self.table_vertices.setItem(row, 1, item_x)
            self.table_vertices.setItem(row, 2, item_y)
            self.table_vertices.setItem(row, 3, item_z)
            self.table_vertices.setItem(row, 4, item_w)
            self.table_vertices.setItem(row, 5, item_e)

        self.table_vertices.blockSignals(False)

        if len(page_items) > 0:
            self.table_vertices.selectRow(0)
        else:
            self._clear_detail_panel()

    def _on_table_selection_changed(self):
        """行選択変更時ハンドラ"""
        selected_rows = self.table_vertices.selectionModel().selectedRows()
        if not selected_rows:
            self._clear_detail_panel()
            return

        row = selected_rows[0].row()
        item_no = self.table_vertices.item(row, 0)
        if not item_no:
            return

        orig_idx = item_no.data(Qt.UserRole)
        if 0 <= orig_idx < len(self.vertices_cache):
            self.selected_vertex_index = orig_idx
            self._load_vertex_to_ui(self.vertices_cache[orig_idx])

    def _load_vertex_to_ui(self, data):
        """右ペイン詳細パネルへの読み込み"""
        p = data["pos"]
        n = data["normal"]
        uv = data["uv"]

        self.lbl_pos_val.setText(f"X: {p[0]:.4f},  Y: {p[1]:.4f},  Z: {p[2]:.4f}")
        self.lbl_norm_val.setText(f"法線: NX: {n[0]:.4f}, NY: {n[1]:.4f}, NZ: {n[2]:.4f}")
        self.lbl_uv_val.setText(f"UV: U: {uv[0]:.4f}, V: {uv[1]:.4f}")
        self.lbl_edge_scale.setText(f"エッジ倍率: {data['edge_scale']:.3f}")
        self.lbl_weight_type.setText(f"変形方式: {data['weight_type_str']}")

        # ウェイトテーブル
        bones = data["bones"]
        weights = data["weights"]
        self.table_weights.setRowCount(len(bones))

        for row, b_idx in enumerate(bones):
            b_name = self.bone_names[b_idx] if 0 <= b_idx < len(self.bone_names) else "(不明)"
            w_val = weights[row] if row < len(weights) else 0.0
            if data["weight_type"] == 0:
                w_val = 1.0

            item_b_no = QTableWidgetItem(f"{b_idx}")
            item_b_no.setTextAlignment(Qt.AlignCenter)
            item_b_name = QTableWidgetItem(b_name)
            item_w_val = QTableWidgetItem(f"{w_val:.4f}")
            item_w_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.table_weights.setItem(row, 0, item_b_no)
            self.table_weights.setItem(row, 1, item_b_name)
            self.table_weights.setItem(row, 2, item_w_val)

    def _clear_detail_panel(self):
        """詳細パネルのクリア"""
        self.lbl_pos_val.setText("X: 0.000, Y: 0.000, Z: 0.000")
        self.lbl_norm_val.setText("法線: NX: 0.000, NY: 0.000, NZ: 0.000")
        self.lbl_uv_val.setText("UV: U: 0.000, V: 0.000")
        self.lbl_edge_scale.setText("エッジ倍率: 1.000")
        self.lbl_weight_type.setText("変形方式: -")
        self.table_weights.setRowCount(0)

    def _select_vertex_in_viewport(self):
        """選択頂点をMayaビューポート上で選択"""
        if self.selected_vertex_index < 0 or not self.current_mesh:
            return
        vtx_comp = f"{self.current_mesh}.vtx[{self.selected_vertex_index}]"
        if mc.objExists(vtx_comp):
            mc.select(vtx_comp, replace=True)

    def _prev_page(self):
        """前のページへ"""
        if self.current_page > 0:
            self.current_page -= 1
            self._update_table_page()

    def _next_page(self):
        """次のページへ"""
        total_pages = max(1, (len(self.vertices_cache) + self.page_size - 1) // self.page_size)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._update_table_page()

    def _jump_page(self, page_num):
        """指定ページへ移動"""
        if self._block_signals:
            return
        target = page_num - 1
        if target != self.current_page:
            self.current_page = target
            self._update_table_page()

