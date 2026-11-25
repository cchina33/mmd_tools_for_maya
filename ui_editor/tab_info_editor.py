# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MMD Model Editor モデル情報タブモジュール
モデル名、英語名、コメント、PMXバージョン、構成要素統計の表示および編集機能を提供します。
"""

import os
import sys
import json
import maya.cmds as mc

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QSplitter, QScrollArea, QGroupBox, QTextEdit, QFrame,
        QMessageBox
    )
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QSplitter, QScrollArea, QGroupBox, QTextEdit, QFrame,
        QMessageBox
    )


class InfoEditorTabWidget(QWidget):
    """
    MMD Model Editor モデル情報管理タブウィジェット
    モデルの基本メタデータおよび各構成要素の統計サマリーを表示・編集します。
    """

    def __init__(self, parent=None):
        super(InfoEditorTabWidget, self).__init__(parent)
        self.current_model = None
        self.pmx_model_data = None
        self._block_signals = False

        self._init_ui()

    def _init_ui(self):
        """ユーザーインターフェースの初期化"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 水平スプリッター (左: 基本情報サマリー、右: メタデータ編集)
        self.splitter = QSplitter(Qt.Horizontal)

        # -------------------------------------------------------------
        # 左ペイン: モデル基本情報・統計サマリー
        # -------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(8)

        # 基本メタデータ表示カード
        grp_summary = QGroupBox("モデル基本情報")
        summary_layout = QVBoxLayout(grp_summary)
        summary_layout.setSpacing(6)

        self.lbl_model_name_disp = QLabel("モデル名: 未読込")
        self.lbl_model_name_disp.setStyleSheet("font-weight: bold; color: #52b7ff; font-size: 13px;")
        summary_layout.addWidget(self.lbl_model_name_disp)

        self.lbl_model_name_e_disp = QLabel("英語名: 未読込")
        self.lbl_model_name_e_disp.setStyleSheet("color: #cccccc;")
        summary_layout.addWidget(self.lbl_model_name_e_disp)

        self.lbl_file_path_disp = QLabel("PMXパス: 未設定")
        self.lbl_file_path_disp.setStyleSheet("color: #888888; font-size: 11px;")
        self.lbl_file_path_disp.setWordWrap(True)
        summary_layout.addWidget(self.lbl_file_path_disp)

        self.lbl_version_disp = QLabel("形式バージョン: -")
        self.lbl_version_disp.setStyleSheet("color: #ffaa55;")
        summary_layout.addWidget(self.lbl_version_disp)

        left_layout.addWidget(grp_summary)

        # 各構成要素の統計テーブル
        grp_stats = QGroupBox("構成要素の統計サマリー")
        stats_layout = QVBoxLayout(grp_stats)
        stats_layout.setSpacing(4)

        self.table_stats = QTableWidget()
        self.table_stats.setColumnCount(2)
        self.table_stats.setHorizontalHeaderLabels(["要素種別", "数量"])
        self.table_stats.horizontalHeader().setStretchLastSection(True)
        self.table_stats.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_stats.verticalHeader().setVisible(False)
        self.table_stats.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_stats.setSelectionMode(QTableWidget.NoSelection)
        self.table_stats.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333333;")
        stats_layout.addWidget(self.table_stats)

        btn_refresh_info = QPushButton("情報再取得")
        btn_refresh_info.setFixedHeight(28)
        btn_refresh_info.clicked.connect(self._reload_model_info)
        stats_layout.addWidget(btn_refresh_info)

        left_layout.addWidget(grp_stats)

        # -------------------------------------------------------------
        # 右ペイン: モデル名・コメント編集パネル
        # -------------------------------------------------------------
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)

        # モデル名称編集グループ
        grp_names = QGroupBox("名称設定")
        names_layout = QVBoxLayout(grp_names)
        names_layout.setSpacing(6)

        lbl_name_ja = QLabel("モデル名 (日本語):")
        lbl_name_ja.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.le_model_name_ja = QLineEdit()
        self.le_model_name_ja.setPlaceholderText("モデルの日本語名を入力...")
        names_layout.addWidget(lbl_name_ja)
        names_layout.addWidget(self.le_model_name_ja)

        lbl_name_en = QLabel("モデル名 (英語):")
        lbl_name_en.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.le_model_name_en = QLineEdit()
        self.le_model_name_en.setPlaceholderText("モデルの英語名を入力...")
        names_layout.addWidget(lbl_name_en)
        names_layout.addWidget(self.le_model_name_en)

        right_layout.addWidget(grp_names)

        # コメント編集グループ
        grp_comments = QGroupBox("コメント・説明文")
        comments_layout = QVBoxLayout(grp_comments)
        comments_layout.setSpacing(6)

        lbl_comment_ja = QLabel("コメント (日本語):")
        lbl_comment_ja.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.te_comment_ja = QTextEdit()
        self.te_comment_ja.setPlaceholderText("モデルの説明文や利用規約 (日本語)...")
        self.te_comment_ja.setMinimumHeight(140)
        comments_layout.addWidget(lbl_comment_ja)
        comments_layout.addWidget(self.te_comment_ja)

        lbl_comment_en = QLabel("コメント (英語):")
        lbl_comment_en.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.te_comment_en = QTextEdit()
        self.te_comment_en.setPlaceholderText("Model comments / terms of use (English)...")
        self.te_comment_en.setMinimumHeight(120)
        comments_layout.addWidget(lbl_comment_en)
        comments_layout.addWidget(self.te_comment_en)

        right_layout.addWidget(grp_comments)

        # 反映操作ボタン
        self.btn_apply_info = QPushButton("シーンモデルへ反映")
        self.btn_apply_info.setFixedHeight(34)
        self.btn_apply_info.setStyleSheet(
            "QPushButton { background-color: #1e6fa8; color: #ffffff; font-weight: bold; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #288bc9; border: 1px solid #6ac5fe; }"
        )
        self.btn_apply_info.clicked.connect(self._apply_info_to_scene)
        right_layout.addWidget(self.btn_apply_info)

        right_layout.addStretch()
        right_scroll.setWidget(right_widget)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_scroll)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 6)

        main_layout.addWidget(self.splitter)

    def set_target_model(self, model_node):
        """対象モデルノードを受け取り、モデル情報を読み込んでUIを初期化"""
        self.current_model = model_node
        try:
            self._reload_model_info()
        except Exception as e:
            print(f"[情報タブ 警告] モデル情報の読み込み中に軽微な例外を捕捉: {e}")

    def _reload_model_info(self):
        """モデルノードからメタデータおよび構成要素数を再抽出"""
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
            self._clear_ui()
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

        name_ja = ""
        name_en = ""
        comment_ja = ""
        comment_en = ""
        ver_str = "PMX 2.0"

        # PMXファイルからの解析試行
        pmx_model = None
        if pmx_path and os.path.isfile(pmx_path):
            try:
                try:
                    from .. import mmd_parser
                except Exception:
                    import mmd_parser
                pmx_model = mmd_parser.pmx.load(pmx_path)
                self.pmx_model_data = pmx_model
                name_ja = getattr(pmx_model, 'name', '') or ''
                name_en = getattr(pmx_model, 'name_e', '') or ''
                comment_ja = getattr(pmx_model, 'comment', '') or ''
                comment_en = getattr(pmx_model, 'comment_e', '') or ''
                ver_val = getattr(pmx_model, 'version', 2.0)
                ver_str = f"PMX {ver_val:.1f}"
            except Exception:
                pmx_model = None

        # シーンアトリビュートからのフォールバック取得
        if not name_ja and mc.attributeQuery("originalName", node=model_node, exists=True):
            name_ja = mc.getAttr(f"{model_node}.originalName") or ""
        if not name_ja:
            name_ja = model_node.split('|')[-1].split(':')[-1]

        if not name_en and mc.attributeQuery("englishName", node=model_node, exists=True):
            name_en = mc.getAttr(f"{model_node}.englishName") or ""

        # UI表示更新
        self.lbl_model_name_disp.setText(f"モデル名: {name_ja}")
        self.lbl_model_name_e_disp.setText(f"英語名: {name_en if name_en else '(未設定)'}")
        self.lbl_file_path_disp.setText(f"PMXパス: {pmx_path if pmx_path else '(シーン直結)'}")
        self.lbl_version_disp.setText(f"形式バージョン: {ver_str}")

        self._block_signals = True
        self.le_model_name_ja.setText(name_ja)
        self.le_model_name_en.setText(name_en)
        self.te_comment_ja.setPlainText(comment_ja)
        self.te_comment_en.setPlainText(comment_en)
        self._block_signals = False

        # 統計要素数の収集
        num_vtx = 0
        num_faces = 0
        num_materials = 0
        num_bones = 0
        num_morphs = 0
        num_rigids = 0
        num_joints = 0

        if pmx_model:
            num_vtx = len(getattr(pmx_model, 'vertices', []))
            num_faces = len(getattr(pmx_model, 'faces', []))
            num_materials = len(getattr(pmx_model, 'materials', []))
            num_bones = len(getattr(pmx_model, 'bones', []))
            num_morphs = len(getattr(pmx_model, 'morphs', []))
            num_rigids = len(getattr(pmx_model, 'rigid_bodies', []))
            num_joints = len(getattr(pmx_model, 'joints', []))
        else:
            # Mayaメッシュから要素数を推定
            if mc.objExists(mesh_node) and mc.nodeType(mesh_node) == "mesh":
                num_vtx = mc.polyEvaluate(mesh_node, vertex=True) or 0
                num_faces = mc.polyEvaluate(mesh_node, face=True) or 0

            # シーン内シェーディンググループから材質数を算出
            shading_grps = mc.listConnections(mesh_node, type="shadingEngine") or []
            num_materials = len(set(shading_grps))

            # ジョイント数
            desc_joints = mc.listRelatives(model_node, allDescendents=True, type="joint") or []
            num_bones = len(desc_joints)

            # ブレンドシェイプモーフ数
            bs_nodes = mc.listConnections(mesh_node, type="blendShape") or []
            if bs_nodes:
                weights = mc.blendShape(bs_nodes[0], query=True, target=True) or []
                num_morphs = len(weights)

        stats_items = [
            ("頂点 (Vertex)", f"{num_vtx:,} 頂点"),
            ("面 (Face)", f"{num_faces:,} 面"),
            ("材質 (Material)", f"{num_materials} 材質"),
            ("ボーン (Bone)", f"{num_bones} ジョイント"),
            ("モーフ (Morph)", f"{num_morphs} モーフ"),
            ("剛体 (RigidBody)", f"{num_rigids} 剛体"),
            ("Joint (Constraint)", f"{num_joints} Joint"),
        ]

        self.table_stats.setRowCount(len(stats_items))
        for row, (k, v) in enumerate(stats_items):
            item_k = QTableWidgetItem(k)
            item_v = QTableWidgetItem(v)
            item_v.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table_stats.setItem(row, 0, item_k)
            self.table_stats.setItem(row, 1, item_v)

    def _clear_ui(self):
        """未選択時のクリア表示"""
        self.lbl_model_name_disp.setText("モデル名: 未選択")
        self.lbl_model_name_e_disp.setText("英語名: 未選択")
        self.lbl_file_path_disp.setText("PMXパス: 未設定")
        self.lbl_version_disp.setText("形式バージョン: -")
        self.le_model_name_ja.clear()
        self.le_model_name_en.clear()
        self.te_comment_ja.clear()
        self.te_comment_en.clear()
        self.table_stats.setRowCount(0)

    def _apply_info_to_scene(self):
        """編集したモデル情報をMayaシーンノード属性へ反映"""
        if not self.current_model or not mc.objExists(self.current_model):
            QMessageBox.warning(self, "エラー", "対象モデルが選択されていないか、シーン内に存在しません。")
            return

        name_ja = self.le_model_name_ja.text().strip()
        name_en = self.le_model_name_en.text().strip()
        comment_ja = self.te_comment_ja.toPlainText()
        comment_en = self.te_comment_en.toPlainText()

        try:
            # 日本語名
            if not mc.attributeQuery("originalName", node=self.current_model, exists=True):
                mc.addAttr(self.current_model, longName="originalName", dataType="string")
            mc.setAttr(f"{self.current_model}.originalName", name_ja, typ="string")

            # 英語名
            if not mc.attributeQuery("englishName", node=self.current_model, exists=True):
                mc.addAttr(self.current_model, longName="englishName", dataType="string")
            mc.setAttr(f"{self.current_model}.englishName", name_en, typ="string")

            # コメント日本語
            if not mc.attributeQuery("mmdModelComment", node=self.current_model, exists=True):
                mc.addAttr(self.current_model, longName="mmdModelComment", dataType="string")
            mc.setAttr(f"{self.current_model}.mmdModelComment", comment_ja, typ="string")

            # コメント英語
            if not mc.attributeQuery("mmdModelCommentE", node=self.current_model, exists=True):
                mc.addAttr(self.current_model, longName="mmdModelCommentE", dataType="string")
            mc.setAttr(f"{self.current_model}.mmdModelCommentE", comment_en, typ="string")

            self.lbl_model_name_disp.setText(f"モデル名: {name_ja}")
            self.lbl_model_name_e_disp.setText(f"英語名: {name_en if name_en else '(未設定)'}")

            QMessageBox.information(self, "反映終了", "モデル情報をMayaシーンへ正常に反映しました。")
        except Exception as e:
            QMessageBox.critical(self, "反映エラー", f"シーン属性への反映中にエラーが発生しました:\n{e}")

