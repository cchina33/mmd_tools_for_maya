# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MMD Model Editor 面管理タブモジュール
MMDモデルの面（ポリゴン三角形インデックス・構成頂点・所属材質）の一覧表示および材質別絞り込みを提供します。
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
        QSplitter, QScrollArea, QGroupBox, QComboBox, QSpinBox,
        QFrame, QMessageBox
    )
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QSplitter, QScrollArea, QGroupBox, QComboBox, QSpinBox,
        QFrame, QMessageBox
    )


class FaceEditorTabWidget(QWidget):
    """
    MMD Model Editor 面管理タブウィジェット
    ポリゴン面の一覧表示、所属材質フィルタリング、およびビューポート選択連動を行います。
    """

    def __init__(self, parent=None):
        super(FaceEditorTabWidget, self).__init__(parent)
        self.current_model = None
        self.current_mesh = None
        self.faces_cache = []
        self.material_names = []
        self.filtered_faces = []
        self.current_page = 0
        self.page_size = 200
        self.selected_face_index = -1
        self._block_signals = False

        self._init_ui()

    def _init_ui(self):
        """ユーザーインターフェースの初期化"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 水平スプリッター (左: 面一覧テーブル、右: 詳細属性)
        self.splitter = QSplitter(Qt.Horizontal)

        # -------------------------------------------------------------
        # 左ペイン: 面一覧テーブル・材質フィルタ・ページャー
        # -------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(6)

        # 材質フィルター & ページバー
        top_filter_layout = QHBoxLayout()
        top_filter_layout.setSpacing(4)

        lbl_mat = QLabel("材質:")
        lbl_mat.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.cbb_material_filter = QComboBox()
        self.cbb_material_filter.addItem("すべての材質")
        self.cbb_material_filter.currentIndexChanged.connect(self._on_material_filter_changed)

        top_filter_layout.addWidget(lbl_mat)
        top_filter_layout.addWidget(self.cbb_material_filter)
        left_layout.addLayout(top_filter_layout)

        pager_layout = QHBoxLayout()
        pager_layout.setSpacing(4)

        self.btn_prev_page = QPushButton("前へ")
        self.btn_prev_page.setFixedWidth(50)
        self.btn_prev_page.clicked.connect(self._prev_page)

        self.lbl_page_info = QLabel("0 / 0 (計 0 面)")
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

        # 面テーブル
        self.table_faces = QTableWidget()
        self.table_faces.setColumnCount(5)
        self.table_faces.setHorizontalHeaderLabels(["No", "頂点0", "頂点1", "頂点2", "所属材質"])
        self.table_faces.horizontalHeader().setStretchLastSection(True)
        self.table_faces.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_faces.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_faces.setSelectionMode(QTableWidget.SingleSelection)
        self.table_faces.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_faces.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333333;")
        self.table_faces.itemSelectionChanged.connect(self._on_table_selection_changed)
        left_layout.addWidget(self.table_faces)

        # 下部操作バー
        bot_layout = QHBoxLayout()
        btn_sel_viewport = QPushButton("ビューポートで面を選択")
        btn_sel_viewport.clicked.connect(self._select_face_in_viewport)
        btn_refresh = QPushButton("リスト再取得")
        btn_refresh.setFixedWidth(90)
        btn_refresh.clicked.connect(self._reload_face_data)

        bot_layout.addWidget(btn_sel_viewport)
        bot_layout.addWidget(btn_refresh)
        left_layout.addLayout(bot_layout)

        # -------------------------------------------------------------
        # 右ペイン: 面詳細情報
        # -------------------------------------------------------------
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)

        # 面基本情報グループ
        grp_face = QGroupBox("面情報")
        face_layout = QVBoxLayout(grp_face)
        self.lbl_face_no = QLabel("面インデックス: -")
        self.lbl_face_no.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px;")
        self.lbl_face_mat = QLabel("所属材質: -")
        self.lbl_face_mat.setStyleSheet("color: #52b7ff; font-weight: bold;")
        face_layout.addWidget(self.lbl_face_no)
        face_layout.addWidget(self.lbl_face_mat)
        right_layout.addWidget(grp_face)

        # 構成頂点グループ
        grp_verts = QGroupBox("構成頂点インデックス")
        verts_layout = QVBoxLayout(grp_verts)
        self.lbl_v0 = QLabel("頂点 0: -")
        self.lbl_v1 = QLabel("頂点 1: -")
        self.lbl_v2 = QLabel("頂点 2: -")
        self.lbl_v0.setStyleSheet("color: #cccccc;")
        self.lbl_v1.setStyleSheet("color: #cccccc;")
        self.lbl_v2.setStyleSheet("color: #cccccc;")
        verts_layout.addWidget(self.lbl_v0)
        verts_layout.addWidget(self.lbl_v1)
        verts_layout.addWidget(self.lbl_v2)
        right_layout.addWidget(grp_verts)

        right_layout.addStretch()
        right_scroll.setWidget(right_widget)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_scroll)
        self.splitter.setStretchFactor(0, 6)
        self.splitter.setStretchFactor(1, 4)

        main_layout.addWidget(self.splitter)

    def set_target_model(self, model_node):
        """対象モデルを受け取り、面データを読み込み"""
        self.current_model = model_node
        try:
            self._reload_face_data()
        except Exception as e:
            print(f"[面タブ 警告] 面データの読み込み中に軽微な例外を捕捉: {e}")

    def _reload_face_data(self):
        """PMXファイルおよびMayaメッシュから面データを収集"""
        self.faces_cache = []
        self.material_names = []
        self.filtered_faces = []
        self.current_page = 0
        self.selected_face_index = -1
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

        pmx_faces = []
        pmx_materials = []
        if pmx_path:
            try:
                try:
                    from .. import mmd_parser
                except Exception:
                    import mmd_parser
                pmx_model = mmd_parser.pmx.load(pmx_path)
                pmx_faces = getattr(pmx_model, 'faces', [])
                pmx_materials = getattr(pmx_model, 'materials', [])
            except Exception:
                pmx_faces = []

        if pmx_faces:
            # 材質名一覧の作成
            self.material_names = [m.name for m in pmx_materials]

            # 面ごとの所属材質判定
            mat_for_face = []
            for mat in pmx_materials:
                v_cnt = getattr(mat, 'vertex_count', 0)
                f_cnt = v_cnt // 3
                mat_for_face.extend([mat.name] * f_cnt)

            for f_idx, face in enumerate(pmx_faces):
                mat_name = mat_for_face[f_idx] if f_idx < len(mat_for_face) else "(不明)"
                v0 = face[0] if len(face) > 0 else 0
                v1 = face[1] if len(face) > 1 else 0
                v2 = face[2] if len(face) > 2 else 0

                self.faces_cache.append({
                    "index": f_idx,
                    "v0": v0,
                    "v1": v1,
                    "v2": v2,
                    "material": mat_name,
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

                    num_polys = fn_mesh.numPolygons
                    # シェーダーと材質マッピング
                    shaders, face_indices = fn_mesh.getConnectedShaders(0)
                    shd_names = []
                    for s in shaders:
                        conns = mc.listConnections(f"{om.MFnDependencyNode(s).name}.surfaceShader") or []
                        shd_names.append(conns[0] if conns else om.MFnDependencyNode(s).name)
                    self.material_names = list(set(shd_names)) if shd_names else ["標準マテリアル"]

                    for p_idx in range(num_polys):
                        v_list = fn_mesh.getPolygonVertices(p_idx)
                        v0 = v_list[0] if len(v_list) > 0 else 0
                        v1 = v_list[1] if len(v_list) > 1 else 0
                        v2 = v_list[2] if len(v_list) > 2 else 0

                        mat_name = "標準マテリアル"
                        if face_indices and p_idx < len(face_indices):
                            s_idx = face_indices[p_idx]
                            if 0 <= s_idx < len(shd_names):
                                mat_name = shd_names[s_idx]

                        self.faces_cache.append({
                            "index": p_idx,
                            "v0": v0,
                            "v1": v1,
                            "v2": v2,
                            "material": mat_name,
                        })
            except Exception as e_face_api:
                print(f"[面抽出警告] メッシュからの面抽出に失敗: {e_face_api}")

        # 材質コンボボックスの更新
        self._block_signals = True
        self.cbb_material_filter.clear()
        self.cbb_material_filter.addItem("すべての材質")
        for m_name in self.material_names:
            self.cbb_material_filter.addItem(m_name)
        self._block_signals = False

        self._apply_filter()

    def _on_material_filter_changed(self):
        """材質フィルター変更時"""
        if self._block_signals:
            return
        self.current_page = 0
        self._apply_filter()

    def _apply_filter(self):
        """選択材質によるフィルタリング適用"""
        sel_mat = self.cbb_material_filter.currentText()
        if sel_mat == "すべての材質" or not sel_mat:
            self.filtered_faces = self.faces_cache
        else:
            self.filtered_faces = [f for f in self.faces_cache if f["material"] == sel_mat]

        self._update_table_page()

    def _update_table_page(self):
        """ページ描画"""
        total_faces = len(self.filtered_faces)
        total_pages = max(1, (total_faces + self.page_size - 1) // self.page_size)

        self.current_page = max(0, min(self.current_page, total_pages - 1))
        self.lbl_page_info.setText(f"ページ {self.current_page + 1} / {total_pages} (計 {total_faces:,} 面)")

        self._block_signals = True
        self.spin_page_jump.setRange(1, total_pages)
        self.spin_page_jump.setValue(self.current_page + 1)
        self._block_signals = False

        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, total_faces)
        page_items = self.filtered_faces[start_idx:end_idx]

        self.table_faces.blockSignals(True)
        self.table_faces.setRowCount(len(page_items))

        for row, data in enumerate(page_items):
            item_no = QTableWidgetItem(f"{data['index']}")
            item_no.setTextAlignment(Qt.AlignCenter)
            item_no.setData(Qt.UserRole, data["index"])

            item_v0 = QTableWidgetItem(f"{data['v0']}")
            item_v1 = QTableWidgetItem(f"{data['v1']}")
            item_v2 = QTableWidgetItem(f"{data['v2']}")
            item_v0.setTextAlignment(Qt.AlignCenter)
            item_v1.setTextAlignment(Qt.AlignCenter)
            item_v2.setTextAlignment(Qt.AlignCenter)

            item_mat = QTableWidgetItem(data["material"])

            self.table_faces.setItem(row, 0, item_no)
            self.table_faces.setItem(row, 1, item_v0)
            self.table_faces.setItem(row, 2, item_v1)
            self.table_faces.setItem(row, 3, item_v2)
            self.table_faces.setItem(row, 4, item_mat)

        self.table_faces.blockSignals(False)

        if len(page_items) > 0:
            self.table_faces.selectRow(0)
        else:
            self._clear_detail_panel()

    def _on_table_selection_changed(self):
        """行選択変更時ハンドラ"""
        selected_rows = self.table_faces.selectionModel().selectedRows()
        if not selected_rows:
            self._clear_detail_panel()
            return

        row = selected_rows[0].row()
        item_no = self.table_faces.item(row, 0)
        if not item_no:
            return

        orig_idx = item_no.data(Qt.UserRole)
        for data in self.faces_cache:
            if data["index"] == orig_idx:
                self.selected_face_index = orig_idx
                self._load_face_to_ui(data)
                break

    def _load_face_to_ui(self, data):
        """右ペイン詳細パネルへの読み込み"""
        self.lbl_face_no.setText(f"面インデックス: {data['index']}")
        self.lbl_face_mat.setText(f"所属材質: {data['material']}")
        self.lbl_v0.setText(f"頂点 0: index {data['v0']}")
        self.lbl_v1.setText(f"頂点 1: index {data['v1']}")
        self.lbl_v2.setText(f"頂点 2: index {data['v2']}")

    def _clear_detail_panel(self):
        """詳細パネルのクリア"""
        self.lbl_face_no.setText("面インデックス: -")
        self.lbl_face_mat.setText("所属材質: -")
        self.lbl_v0.setText("頂点 0: -")
        self.lbl_v1.setText("頂点 1: -")
        self.lbl_v2.setText("頂点 2: -")

    def _select_face_in_viewport(self):
        """選択面をMayaビューポート上で選択"""
        if self.selected_face_index < 0 or not self.current_mesh:
            return
        face_comp = f"{self.current_mesh}.f[{self.selected_face_index}]"
        if mc.objExists(face_comp):
            mc.select(face_comp, replace=True)

    def _prev_page(self):
        """前のページへ"""
        if self.current_page > 0:
            self.current_page -= 1
            self._update_table_page()

    def _next_page(self):
        """次のページへ"""
        total_pages = max(1, (len(self.filtered_faces) + self.page_size - 1) // self.page_size)
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

