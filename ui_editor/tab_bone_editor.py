# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MMD Model Editor ボーン管理タブモジュール
MMDモデルのボーン（ジョイント）一覧表示、属性確認、およびボーン後付け作成機能を提供します。
"""

import os
import sys
import maya.cmds as mc
import maya.mel as mel

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QSplitter, QScrollArea, QGroupBox, QCheckBox, QDoubleSpinBox,
        QComboBox, QTextEdit, QFileDialog, QFrame, QAbstractItemView,
        QMessageBox
    )
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt, Signal
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QSplitter, QScrollArea, QGroupBox, QCheckBox, QDoubleSpinBox,
        QComboBox, QTextEdit, QFileDialog, QFrame, QAbstractItemView,
        QMessageBox
    )


class BoneEditorTabWidget(QWidget):
    """
    MMD Model Editor ボーン管理タブウィジェット
    シーン内のボーン階層を一覧表示し、属性確認および未生成時のボーン作成を行います。
    """

    def __init__(self, parent=None):
        super(BoneEditorTabWidget, self).__init__(parent)
        self.current_model = None
        self.bone_data_list = []
        self.selected_bone_index = -1
        self._block_signals = False

        self._init_ui()

    def _init_ui(self):
        """ユーザーインターフェースの初期化"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 水平スプリッター (左: ボーン一覧、右: 詳細属性)
        self.splitter = QSplitter(Qt.Horizontal)

        # -------------------------------------------------------------
        # 左ペイン: ボーン一覧テーブル・検索・作成ボタン
        # -------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(6)

        # 検索フィルターバー
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)
        search_label = QLabel("絞り込み:")
        search_label.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText("ボーン名 / ノード名で検索...")
        self.le_search.textChanged.connect(self._filter_bone_list)
        btn_clear_search = QPushButton("クリア")
        btn_clear_search.setFixedWidth(54)
        btn_clear_search.clicked.connect(lambda: self.le_search.clear())

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.le_search)
        search_layout.addWidget(btn_clear_search)
        left_layout.addLayout(search_layout)

        # ボーン未生成時バナーフレーム（初期非表示）
        self.frame_no_bones = QFrame()
        self.frame_no_bones.setStyleSheet("background-color: #2e281e; border: 1px solid #775522; border-radius: 6px; padding: 8px;")
        no_bones_layout = QVBoxLayout(self.frame_no_bones)
        no_bones_layout.setSpacing(6)

        lbl_no_bones_msg = QLabel("※対象モデルにボーン（ジョイント）が存在しません。\n「ボーン作成」ボタンを押すと、PMXデータからボーン階層を構築してメッシュへバインドします。")
        lbl_no_bones_msg.setStyleSheet("color: #ffcc66; font-size: 13px; font-weight: bold;")
        lbl_no_bones_msg.setWordWrap(True)
        no_bones_layout.addWidget(lbl_no_bones_msg)

        self.btn_create_bones_banner = QPushButton("ボーン作成を実行")
        self.btn_create_bones_banner.setFixedHeight(34)
        self.btn_create_bones_banner.setStyleSheet(
            "QPushButton { background-color: #1e6fa8; color: #ffffff; font-weight: bold; border-radius: 4px; font-size: 14px; }"
            "QPushButton:hover { background-color: #288bc9; border: 1px solid #6ac5fe; }"
        )
        self.btn_create_bones_banner.clicked.connect(self._execute_build_bones)
        no_bones_layout.addWidget(self.btn_create_bones_banner)
        left_layout.addWidget(self.frame_no_bones)
        self.frame_no_bones.setVisible(False)

        # ボーンテーブル
        self.table_bones = QTableWidget()
        self.table_bones.setColumnCount(5)
        self.table_bones.setHorizontalHeaderLabels(["No", "ボーン名 (日本語)", "英語名", "親ボーン", "表示"])
        self.table_bones.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_bones.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_bones.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_bones.verticalHeader().setVisible(False)
        self.table_bones.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_bones.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_bones.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_bones.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_bones.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_bones.setStyleSheet(
            "QTableWidget { background-color: #222; border: 1px solid #444; border-radius: 4px; gridline-color: #333; }"
            "QTableWidget::item:selected { background-color: #2c5d88; color: #ffffff; }"
            "QHeaderView::section { background-color: #2e2e2e; color: #bbb; padding: 4px; border: 1px solid #3c3c3c; font-weight: bold; }"
        )
        self.table_bones.itemSelectionChanged.connect(self._on_table_selection_changed)
        left_layout.addWidget(self.table_bones)

        # 操作ツールバー
        btn_grid = QVBoxLayout()
        btn_grid.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(4)
        self.btn_select_joint = QPushButton("選択ボーンを選択")
        self.btn_select_joint.setToolTip("選択中のボーンをビューポート上でハイライト選択します。")
        self.btn_select_joint.clicked.connect(self._select_viewport_joint)
        self.btn_find_from_vp = QPushButton("選択からボーン特定")
        self.btn_find_from_vp.setToolTip("現在ビューポートで選択中のジョイントをテーブル上で特定します。")
        self.btn_find_from_vp.clicked.connect(self._find_bone_from_viewport)
        row1.addWidget(self.btn_select_joint)
        row1.addWidget(self.btn_find_from_vp)

        row2 = QHBoxLayout()
        row2.setSpacing(4)
        self.btn_toggle_drawstyle = QPushButton("表示 / 非表示 切替")
        self.btn_toggle_drawstyle.setToolTip("選択中ボーンの表示スタイル（drawStyle）を切り替えます。")
        self.btn_toggle_drawstyle.clicked.connect(self._toggle_bone_drawstyle)

        self.btn_create_bones = QPushButton("ボーン作成 / 再構築")
        self.btn_create_bones.setStyleSheet("background-color: #2f6f9f; color: #ffffff; font-weight: bold;")
        self.btn_create_bones.setToolTip("PMXファイルからボーン階層を生成し、メッシュへのスキニングを設定します。")
        self.btn_create_bones.clicked.connect(self._execute_build_bones)

        self.btn_refresh = QPushButton("リスト再取得")
        self.btn_refresh.setToolTip("シーン内のジョイント情報を再読込してテーブルを更新します。")
        self.btn_refresh.clicked.connect(self.refresh_bones)

        row2.addWidget(self.btn_toggle_drawstyle)
        row2.addWidget(self.btn_create_bones)
        row2.addWidget(self.btn_refresh)

        btn_grid.addLayout(row1)
        btn_grid.addLayout(row2)
        left_layout.addLayout(btn_grid)

        self.splitter.addWidget(left_widget)

        # -------------------------------------------------------------
        # 右ペイン: ボーン属性詳細パネル
        # -------------------------------------------------------------
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(10)

        # 基本情報グループ
        grp_basic = QGroupBox("ボーン基本情報")
        grp_basic_layout = QVBoxLayout(grp_basic)
        grp_basic_layout.setSpacing(6)

        h_name_ja = QHBoxLayout()
        h_name_ja.addWidget(QLabel("ボーン名 (日本語):"))
        self.le_bone_name_ja = QLineEdit()
        self.le_bone_name_ja.editingFinished.connect(self._on_parameter_changed)
        h_name_ja.addWidget(self.le_bone_name_ja)
        grp_basic_layout.addLayout(h_name_ja)

        h_name_en = QHBoxLayout()
        h_name_en.addWidget(QLabel("ボーン名 (英語):"))
        self.le_bone_name_en = QLineEdit()
        self.le_bone_name_en.editingFinished.connect(self._on_parameter_changed)
        h_name_en.addWidget(self.le_bone_name_en)
        grp_basic_layout.addLayout(h_name_en)

        h_node_name = QHBoxLayout()
        h_node_name.addWidget(QLabel("ジョイントノード:"))
        self.le_joint_node = QLineEdit()
        self.le_joint_node.setReadOnly(True)
        self.le_joint_node.setStyleSheet("background-color: #1a1a1a; color: #88c;")
        h_node_name.addWidget(self.le_joint_node)
        grp_basic_layout.addLayout(h_node_name)

        right_layout.addWidget(grp_basic)

        # トランスフォーム情報グループ
        grp_transform = QGroupBox("トランスフォーム情報")
        grp_trans_layout = QVBoxLayout(grp_transform)
        grp_trans_layout.setSpacing(6)

        # 初期基準位置 (mmdInitialTranslate)
        h_init_pos = QHBoxLayout()
        h_init_pos.addWidget(QLabel("初期位置 (XYZ):"))
        self.lbl_init_pos = QLabel("0.000, 0.000, 0.000")
        self.lbl_init_pos.setStyleSheet("color: #77dd77; font-family: monospace;")
        h_init_pos.addWidget(self.lbl_init_pos)
        h_init_pos.addStretch()
        grp_trans_layout.addLayout(h_init_pos)

        # 現在位置 (Translate)
        h_trans = QHBoxLayout()
        h_trans.addWidget(QLabel("現在位置 (T):"))
        self.spin_tx = self._create_double_spin(-9999.0, 9999.0, 0.1, 3)
        self.spin_ty = self._create_double_spin(-9999.0, 9999.0, 0.1, 3)
        self.spin_tz = self._create_double_spin(-9999.0, 9999.0, 0.1, 3)
        h_trans.addWidget(QLabel("X:"))
        h_trans.addWidget(self.spin_tx)
        h_trans.addWidget(QLabel("Y:"))
        h_trans.addWidget(self.spin_ty)
        h_trans.addWidget(QLabel("Z:"))
        h_trans.addWidget(self.spin_tz)
        grp_trans_layout.addLayout(h_trans)

        # 現在回転 (Rotate)
        h_rot = QHBoxLayout()
        h_rot.addWidget(QLabel("現在回転 (R):"))
        self.spin_rx = self._create_double_spin(-360.0, 360.0, 1.0, 2)
        self.spin_ry = self._create_double_spin(-360.0, 360.0, 1.0, 2)
        self.spin_rz = self._create_double_spin(-360.0, 360.0, 1.0, 2)
        h_rot.addWidget(QLabel("X:"))
        h_rot.addWidget(self.spin_rx)
        h_rot.addWidget(QLabel("Y:"))
        h_rot.addWidget(self.spin_ry)
        h_rot.addWidget(QLabel("Z:"))
        h_rot.addWidget(self.spin_rz)
        grp_trans_layout.addLayout(h_rot)

        # 半径と表示スタイル
        h_draw = QHBoxLayout()
        h_draw.addWidget(QLabel("ジョイント半径:"))
        self.spin_radius = self._create_double_spin(0.01, 100.0, 0.1, 2)
        h_draw.addWidget(self.spin_radius)

        h_draw.addWidget(QLabel("表示スタイル:"))
        self.cbb_draw_style = QComboBox()
        self.cbb_draw_style.addItems(["0: 通常表示 (Bone)", "1: 接続線のみ", "2: 非表示 (None)"])
        self.cbb_draw_style.currentIndexChanged.connect(self._on_parameter_changed)
        h_draw.addWidget(self.cbb_draw_style)
        grp_trans_layout.addLayout(h_draw)

        # 姿勢リセットボタン
        btn_reset_pose = QPushButton("選択ボーンの姿勢を初期位置にリセット")
        btn_reset_pose.clicked.connect(self._reset_selected_bone_pose)
        grp_trans_layout.addWidget(btn_reset_pose)

        right_layout.addWidget(grp_transform)

        # 親子関係グループ
        grp_hierarchy = QGroupBox("ボーン階層関係")
        grp_hier_layout = QVBoxLayout(grp_hierarchy)
        grp_hier_layout.setSpacing(6)

        h_parent = QHBoxLayout()
        h_parent.addWidget(QLabel("親ボーン:"))
        self.lbl_parent_bone = QLabel("なし (ルートボーン)")
        self.lbl_parent_bone.setStyleSheet("color: #77ddff; font-weight: bold;")
        h_parent.addWidget(self.lbl_parent_bone)
        h_parent.addStretch()
        grp_hier_layout.addLayout(h_parent)

        h_children = QVBoxLayout()
        h_children.addWidget(QLabel("子ボーン一覧:"))
        self.te_child_bones = QTextEdit()
        self.te_child_bones.setReadOnly(True)
        self.te_child_bones.setFixedHeight(80)
        self.te_child_bones.setStyleSheet("background-color: #1a1a1a; color: #bbb;")
        h_children.addWidget(self.te_child_bones)
        grp_hier_layout.addLayout(h_children)

        right_layout.addWidget(grp_hierarchy)

        right_layout.addStretch()
        right_scroll.setWidget(right_widget)
        self.splitter.addWidget(right_scroll)

        self.splitter.setSizes([480, 620])
        main_layout.addWidget(self.splitter)

    def _create_double_spin(self, min_val, max_val, step, decimals):
        """汎用数値スピンボックスを生成"""
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setFixedWidth(70)
        spin.valueChanged.connect(self._on_parameter_changed)
        return spin

    # -------------------------------------------------------------
    # シーン情報の取得とテーブル構築
    # -------------------------------------------------------------
    def set_target_model(self, model_name):
        """対象とするMMDモデルルートを指定"""
        self.current_model = model_name
        try:
            self.refresh_bones()
        except Exception as e:
            print(f"[ボーンタブ 警告] ボーン情報の読み込み中に軽微な例外を捕捉: {e}")

    def refresh_bones(self):
        """Mayaシーンからボーン情報を収集してテーブルを構築"""
        self.bone_data_list = []
        self.table_bones.setRowCount(0)
        self.selected_bone_index = -1

        joints = []
        if self.current_model and mc.objExists(self.current_model):
            model_short = self.current_model.split("|")[-1].split(":")[-1]
            found_set = set()

            # 探索: モデル自身および子孫ジョイント
            desc_joints = mc.listRelatives(self.current_model, allDescendents=True, type="joint", fullPath=True) or []
            if mc.nodeType(self.current_model) == "joint":
                desc_joints.append(self.current_model)
            for j in desc_joints:
                found_set.add(j)

            # 探索: スキンクラスタからのインフルエンスジョイント探索
            target_meshes = []
            if mc.nodeType(self.current_model) == "mesh":
                target_meshes.append(self.current_model)
            else:
                m_children = mc.listRelatives(self.current_model, shapes=True, type="mesh", fullPath=True) or []
                target_meshes.extend(m_children)
                m_desc = mc.listRelatives(self.current_model, allDescendents=True, type="mesh", fullPath=True) or []
                target_meshes.extend(m_desc)

            for m in target_meshes:
                s_clusters = mc.listConnections(m, type="skinCluster") or []
                for sc in set(s_clusters):
                    infs = mc.skinCluster(sc, query=True, influence=True) or []
                    for inf in infs:
                        long_j = mc.ls(inf, long=True)
                        if long_j:
                            found_set.add(long_j[0])
                            sub_desc = mc.listRelatives(long_j[0], allDescendents=True, type="joint", fullPath=True) or []
                            for sj in sub_desc:
                                found_set.add(sj)

            # 探索: プレフィックス一致ノードおよびその配下の子孫ジョイントを再帰取得
            all_scene_joints = mc.ls(type="joint", long=True) or []
            prefix_matched_roots = []
            for j in all_scene_joints:
                j_short = j.split("|")[-1]
                if j_short.startswith(f"{model_short}_"):
                    prefix_matched_roots.append(j)
                    found_set.add(j)

            for r_j in prefix_matched_roots:
                sub_desc = mc.listRelatives(r_j, allDescendents=True, type="joint", fullPath=True) or []
                for sj in sub_desc:
                    found_set.add(sj)

            # 探索: モデルメタデータ（mmdModelStructure）に記録されたボーン名との照合
            meta_bone_order = {}
            for check_n in [self.current_model] + target_meshes:
                if mc.objExists(check_n) and mc.attributeQuery("mmdModelStructure", node=check_n, exists=True):
                    try:
                        import json
                        meta_data = json.loads(mc.getAttr(f"{check_n}.mmdModelStructure"))
                        b_list = meta_data.get("bones", [])
                        for b_i, b in enumerate(b_list):
                            if isinstance(b, dict):
                                b_name = b.get("name")
                                if b_name:
                                    meta_bone_order[b_name] = b_i
                        if meta_bone_order:
                            break
                    except Exception:
                        pass

            if not meta_bone_order:
                # キャッシュJSONからの照合探索
                try:
                    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    cache_path = os.path.join(plugin_root, 'asset', 'last_imported_structure.json')
                    if os.path.isfile(cache_path):
                        with open(cache_path, 'r', encoding='utf-8') as f:
                            c_data = json.load(f)
                            for b_i, b in enumerate(c_data.get("bones", [])):
                                if isinstance(b, dict) and b.get("name"):
                                    meta_bone_order[b["name"]] = b_i
                except Exception:
                    pass

            if meta_bone_order:
                for j in all_scene_joints:
                    orig_n = mc.getAttr(f"{j}.originalName") if mc.attributeQuery("originalName", node=j, exists=True) else ""
                    short_n = j.split("|")[-1]
                    if orig_n in meta_bone_order or short_n in meta_bone_order:
                        found_set.add(j)
                        sub_j = mc.listRelatives(j, allDescendents=True, type="joint", fullPath=True) or []
                        for sj in sub_j:
                            found_set.add(sj)

            # ボーン順序の整理: メタデータのPMX定義順、なければ階層深さと名前でソート
            def get_sort_key(j_path):
                orig_n = mc.getAttr(f"{j_path}.originalName") if mc.attributeQuery("originalName", node=j_path, exists=True) else ""
                short_n = j_path.split("|")[-1]
                idx = meta_bone_order.get(orig_n, meta_bone_order.get(short_n, 999999))
                return (idx, j_path.count("|"), short_n)

            joints = sorted(list(found_set), key=get_sort_key)
        else:
            # モデル指定なしの場合はシーン内のジョイントを階層順に収集
            all_joints = mc.ls(type="joint", long=True) or []
            joints = sorted(all_joints, key=lambda x: (x.count("|"), x.split("|")[-1]))

        # ボーンが存在しない場合のバナー表示制御
        if not joints:
            self.frame_no_bones.setVisible(True)
        else:
            self.frame_no_bones.setVisible(False)

        # 情報抽出
        for idx, j_node in enumerate(joints):
            data = self._gather_joint_info(idx, j_node)
            self.bone_data_list.append(data)

        self._populate_table()

    def _gather_joint_info(self, index, j_node):
        """ジョイントノードから属性情報を抽出"""
        j_short = j_node.split("|")[-1]

        # 日本語名
        name_ja = ""
        if mc.attributeQuery("originalName", node=j_node, exists=True):
            name_ja = mc.getAttr(f"{j_node}.originalName") or ""
        if not name_ja:
            name_ja = j_short

        # 英語名
        name_en = ""
        if mc.attributeQuery("englishName", node=j_node, exists=True):
            name_en = mc.getAttr(f"{j_node}.englishName") or ""

        # 親ジョイント
        parents = mc.listRelatives(j_node, parent=True, type="joint") or []
        parent_name = parents[0].split("|")[-1] if parents else "なし (ルート)"

        # 子ジョイント
        children = mc.listRelatives(j_node, children=True, type="joint") or []
        child_names = [c.split("|")[-1] for c in children]

        # 表示状態
        draw_style = 0
        if mc.attributeQuery("drawStyle", node=j_node, exists=True):
            draw_style = int(mc.getAttr(f"{j_node}.drawStyle"))

        # トランスフォーム
        cur_t = mc.getAttr(f"{j_node}.translate")[0] if mc.objExists(j_node) else (0.0, 0.0, 0.0)
        cur_r = mc.getAttr(f"{j_node}.rotate")[0] if mc.objExists(j_node) else (0.0, 0.0, 0.0)
        radius = float(mc.getAttr(f"{j_node}.radius")) if mc.attributeQuery("radius", node=j_node, exists=True) else 1.0

        # 初期位置
        init_t = cur_t
        if mc.attributeQuery("mmdInitialTranslate", node=j_node, exists=True):
            init_t = mc.getAttr(f"{j_node}.mmdInitialTranslate")[0]

        return {
            "index": index,
            "node": j_node,
            "short_name": j_short,
            "name_ja": name_ja,
            "name_en": name_en,
            "parent_name": parent_name,
            "child_names": child_names,
            "draw_style": draw_style,
            "cur_t": cur_t,
            "cur_r": cur_r,
            "init_t": init_t,
            "radius": radius,
        }

    def _populate_table(self):
        """抽出したデータからテーブルアイテムを生成"""
        self.table_bones.blockSignals(True)
        self.table_bones.setRowCount(len(self.bone_data_list))

        for row, data in enumerate(self.bone_data_list):
            item_no = QTableWidgetItem(f"{data['index']}")
            item_no.setTextAlignment(Qt.AlignCenter)

            item_ja = QTableWidgetItem(data["name_ja"])
            item_en = QTableWidgetItem(data["name_en"])
            item_parent = QTableWidgetItem(data["parent_name"])

            style_str = "非表示" if data["draw_style"] == 2 else "表示"
            item_style = QTableWidgetItem(style_str)
            item_style.setTextAlignment(Qt.AlignCenter)
            if data["draw_style"] == 2:
                item_style.setForeground(QtGui.QBrush(QtGui.QColor("#888888")))
            else:
                item_style.setForeground(QtGui.QBrush(QtGui.QColor("#77dd77")))

            self.table_bones.setItem(row, 0, item_no)
            self.table_bones.setItem(row, 1, item_ja)
            self.table_bones.setItem(row, 2, item_en)
            self.table_bones.setItem(row, 3, item_parent)
            self.table_bones.setItem(row, 4, item_style)

        self.table_bones.blockSignals(False)

        if self.bone_data_list:
            self.table_bones.selectRow(0)

    def _filter_bone_list(self, text):
        """テーブルのインクリメンタル絞り込み"""
        pattern = text.lower().strip()
        for row in range(self.table_bones.rowCount()):
            match = False
            for col in [1, 2, 3]:
                item = self.table_bones.item(row, col)
                if item and pattern in item.text().lower():
                    match = True
                    break
            self.table_bones.setRowHidden(row, not match)

    # -------------------------------------------------------------
    # 選択イベントと右ペインへの展開
    # -------------------------------------------------------------
    def _on_table_selection_changed(self):
        """テーブル行選択時の詳細パネル更新"""
        selected_rows = self.table_bones.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        if 0 <= row < len(self.bone_data_list):
            self.selected_bone_index = row
            self._load_parameters_to_ui(self.bone_data_list[row])

    def _load_parameters_to_ui(self, data):
        """データを右ペインのウィジェットへ反映"""
        self._block_signals = True

        self.le_bone_name_ja.setText(data["name_ja"])
        self.le_bone_name_en.setText(data["name_en"])
        self.le_joint_node.setText(data["short_name"])

        it = data["init_t"]
        self.lbl_init_pos.setText(f"{it[0]:.3f}, {it[1]:.3f}, {it[2]:.3f}")

        ct = data["cur_t"]
        self.spin_tx.setValue(ct[0])
        self.spin_ty.setValue(ct[1])
        self.spin_tz.setValue(ct[2])

        cr = data["cur_r"]
        self.spin_rx.setValue(cr[0])
        self.spin_ry.setValue(cr[1])
        self.spin_rz.setValue(cr[2])

        self.spin_radius.setValue(data["radius"])

        # 表示スタイル
        ds = min(2, max(0, data["draw_style"]))
        self.cbb_draw_style.setCurrentIndex(ds)

        self.lbl_parent_bone.setText(data["parent_name"])
        self.te_child_bones.setPlainText("\n".join(data["child_names"]) if data["child_names"] else "なし (末端)")

        self._block_signals = False

    def _on_parameter_changed(self, *args):
        """UIパラメータ変更時のハンドラ"""
        if self._block_signals or self.selected_bone_index < 0:
            return

        data = self.bone_data_list[self.selected_bone_index]
        j_node = data["node"]
        if not mc.objExists(j_node):
            return

        data["name_ja"] = self.le_bone_name_ja.text().strip()
        data["name_en"] = self.le_bone_name_en.text().strip()
        data["draw_style"] = self.cbb_draw_style.currentIndex()
        data["radius"] = self.spin_radius.value()

        # Mayaシーンへ即時反映
        try:
            if not mc.attributeQuery("originalName", node=j_node, exists=True):
                mc.addAttr(j_node, longName="originalName", niceName="元の名称", dataType="string")
            mc.setAttr(f"{j_node}.originalName", data["name_ja"], typ="string")

            if not mc.attributeQuery("englishName", node=j_node, exists=True):
                mc.addAttr(j_node, longName="englishName", niceName="英語名称", dataType="string")
            mc.setAttr(f"{j_node}.englishName", data["name_en"], typ="string")

            if mc.attributeQuery("drawStyle", node=j_node, exists=True):
                mc.setAttr(f"{j_node}.drawStyle", data["draw_style"])

            if mc.attributeQuery("radius", node=j_node, exists=True):
                mc.setAttr(f"{j_node}.radius", data["radius"])

            # トランスフォーム変更の反映
            mc.setAttr(f"{j_node}.translate", self.spin_tx.value(), self.spin_ty.value(), self.spin_tz.value(), type="double3")
            mc.setAttr(f"{j_node}.rotate", self.spin_rx.value(), self.spin_ry.value(), self.spin_rz.value(), type="double3")

            # テーブル行更新
            row = self.selected_bone_index
            item_ja = self.table_bones.item(row, 1)
            if item_ja:
                item_ja.setText(data["name_ja"])
            item_en = self.table_bones.item(row, 2)
            if item_en:
                item_en.setText(data["name_en"])

            style_str = "非表示" if data["draw_style"] == 2 else "表示"
            item_style = self.table_bones.item(row, 4)
            if item_style:
                item_style.setText(style_str)
                if data["draw_style"] == 2:
                    item_style.setForeground(QtGui.QBrush(QtGui.QColor("#888888")))
                else:
                    item_style.setForeground(QtGui.QBrush(QtGui.QColor("#77dd77")))
        except Exception as e:
            mc.warning(f"ボーンパラメータ反映中に警告が発生しました: {e}")

    def _reset_selected_bone_pose(self):
        """選択中ボーンの姿勢を初期位置にリセット"""
        if self.selected_bone_index < 0:
            return
        data = self.bone_data_list[self.selected_bone_index]
        j_node = data["node"]
        if not mc.objExists(j_node):
            return

        it = data["init_t"]
        try:
            mc.setAttr(f"{j_node}.translate", it[0], it[1], it[2], type="double3")
            mc.setAttr(f"{j_node}.rotate", 0.0, 0.0, 0.0, type="double3")
            self._load_parameters_to_ui(data)
        except Exception as e:
            mc.warning(f"姿勢リセットに失敗しました: {e}")

    def _toggle_bone_drawstyle(self):
        """選択中ボーンの表示状態（drawStyle）をトグル切替"""
        if self.selected_bone_index < 0:
            return
        data = self.bone_data_list[self.selected_bone_index]
        new_style = 0 if data["draw_style"] == 2 else 2
        self.cbb_draw_style.setCurrentIndex(new_style)

    def _select_viewport_joint(self):
        """ビューポート上でジョイントを選択"""
        if self.selected_bone_index < 0:
            return
        j_node = self.bone_data_list[self.selected_bone_index]["node"]
        if mc.objExists(j_node):
            mc.select(j_node, replace=True)

    def _find_bone_from_viewport(self):
        """ビューポート選択ジョイントをテーブルで特定"""
        sel = mc.ls(selection=True, type="joint") or []
        if not sel:
            mc.warning("ビューポート上でジョイントノードを選択してください。")
            return

        target_joint = sel[0]
        target_short = target_joint.split("|")[-1]

        for row, data in enumerate(self.bone_data_list):
            if data["node"] == target_joint or data["short_name"] == target_short:
                self.table_bones.selectRow(row)
                return

        mc.warning("選択されたジョイントは現在のモデルリストに含まれていません。")

    # -------------------------------------------------------------
    # ボーン作成処理の呼び出し
    # -------------------------------------------------------------
    def _execute_build_bones(self):
        """PMXファイルからボーン階層を生成してメッシュにスキニング"""
        target_model = self.current_model
        if not target_model or not mc.objExists(target_model):
            QMessageBox.warning(self, "エラー", "上部のコンボボックスで対象MMDモデルを選択してください。")
            return

        # PMXファイルパスの探索
        pmx_path = ""
        if mc.attributeQuery("mmdModelPath", node=target_model, exists=True):
            pmx_path = mc.getAttr(f"{target_model}.mmdModelPath") or ""

        if not pmx_path or not os.path.isfile(pmx_path):
            path, _ = QFileDialog.getOpenFileName(
                self, "ボーン作成用 PMXファイルを選択", "", "PMXモデル (*.pmx);;すべてのファイル (*.*)"
            )
            if not path:
                return
            pmx_path = path

        try:
            try:
                from ..maya_converters import pmxpaimaya
            except Exception:
                from maya_converters import pmxpaimaya

            if not hasattr(pmxpaimaya, "build_bones_and_skin_for_model"):
                QMessageBox.critical(self, "エラー", "pmxpaimaya モジュールに build_bones_and_skin_for_model 関数が見つかりません。")
                return

            res = pmxpaimaya.build_bones_and_skin_for_model(target_model, file_path=pmx_path)
            if res:
                joints_created, roots, skin = res
                QMessageBox.information(
                    self, "作成終了",
                    f"ボーン作成が正常に終了しました。\n生成ジョイント数: {len(joints_created)}\nスキンクラスタ: {skin}"
                )
                self.refresh_bones()
            else:
                QMessageBox.critical(self, "エラー", "ボーン作成処理に失敗しました。スクリプトエディタのログをご確認ください。")
        except Exception as e:
            import traceback
            err = traceback.format_exc()
            QMessageBox.critical(self, "例外エラー", f"ボーン作成中に例外が発生しました:\n{err}")
