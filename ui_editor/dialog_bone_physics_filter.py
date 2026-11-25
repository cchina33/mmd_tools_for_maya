# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - ボーン・剛体整理・削除ダイアログモジュール
不要な材質を削除した後のモデルに対し、不要ボーンや未使用ボーン（ウェイト0）、
および孤立した剛体・Jointの検索・自動検出・安全な削除機能を提供します。
"""

import sys
import maya.cmds as mc

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QAbstractItemView, QMessageBox, QFrame, QComboBox, QTabWidget,
        QCheckBox
    )
    PYSIDE_VER = 6
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QAbstractItemView, QMessageBox, QFrame, QComboBox, QTabWidget,
        QCheckBox
    )
    PYSIDE_VER = 2

try:
    from ..maya_converters import model_modifier
except Exception:
    try:
        from maya_converters import model_modifier
    except Exception:
        import model_modifier


def _btn_style(bg_normal, bg_hover, text_color="#ffffff", border_color=None, font_size=12, padding="3px 8px"):
    """ボタンスタイル生成（文字潰れ防止とコントラスト確保）"""
    b_col = border_color or bg_hover
    return (
        f"QPushButton {{ background-color: {bg_normal}; color: {text_color}; border: 1px solid {b_col}; border-radius: 4px; padding: {padding}; font-size: {font_size}px; font-weight: bold; }}"
        f"QPushButton:hover {{ background-color: {bg_hover}; border: 1px solid #52b7ff; }}"
        f"QPushButton:pressed {{ background-color: #1a1a1a; }}"
        f"QPushButton:disabled {{ background-color: #272727; color: #8e8e8e; border: 1px solid #3c3c3c; padding: {padding}; font-size: {font_size}px; font-weight: normal; }}"
    )


class BonePhysicsFilterDialog(QDialog):
    """
    ボーンおよび剛体・Jointの絞り込み表示・削除ダイアログ
    キャラクター単体表示および2体同時表示（両方表示）、ビューポートのボーン表示切替に対応します。
    """

    ALL_MODELS_KEY = "__ALL__"

    def __init__(self, target_models=None, current_model=None, parent=None):
        super(BonePhysicsFilterDialog, self).__init__(parent)
        self.setWindowTitle("ボーン・剛体（物理）絞り込み・削除ウィンドウ")
        self.resize(880, 620)
        self.setMinimumSize(680, 460)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        self.target_models = target_models or []
        self.current_model = current_model if current_model else (
            self.ALL_MODELS_KEY if len(self.target_models) >= 2 else (self.target_models[0] if self.target_models else None)
        )
        self.bones_data = []
        self.physics_data = []
        self._last_vis_mode = "both"

        self._init_ui()
        self._populate_model_combo()

    def _init_ui(self):
        """ユーザーインターフェースレイアウトの構築"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # 対象モデル選択バー（単体または両方表示）
        h_model = QHBoxLayout()
        lbl_target = QLabel("一覧表示対象:")
        lbl_target.setStyleSheet("font-weight: bold; color: #52b7ff; font-size: 13px;")
        h_model.addWidget(lbl_target)
        self.cbb_model = QComboBox()
        self.cbb_model.currentIndexChanged.connect(self._on_model_changed)
        h_model.addWidget(self.cbb_model, 1)

        self.btn_refresh = QPushButton("更新")
        self.btn_refresh.setFixedWidth(70)
        self.btn_refresh.setFixedHeight(30)
        self.btn_refresh.setStyleSheet(_btn_style("#383838", "#484848", "#e0e0e0", border_color="#555555", font_size=12))
        self.btn_refresh.clicked.connect(self._reload_all_data)
        h_model.addWidget(self.btn_refresh)
        layout.addLayout(h_model)

        # ビューポート上のボーン表示切替バー（キャラ別 / 両方 / 非表示）
        vis_frame = QFrame()
        vis_frame.setStyleSheet("background-color: #23272e; border: 1px solid #3c4552; border-radius: 5px;")
        h_vis = QHBoxLayout(vis_frame)
        h_vis.setContentsMargins(8, 5, 8, 5)
        h_vis.setSpacing(6)

        lbl_vis = QLabel("ビューポートのボーン表示:")
        lbl_vis.setStyleSheet("color: #88ddff; font-weight: bold; font-size: 12px;")
        h_vis.addWidget(lbl_vis)

        model_a_label = self.target_models[0].split("|")[-1] if len(self.target_models) >= 1 else "モデルA"
        model_b_label = self.target_models[1].split("|")[-1] if len(self.target_models) >= 2 else "モデルB"

        self.btn_vis_both = QPushButton("両方表示")
        self.btn_vis_both.setFixedHeight(28)
        self.btn_vis_both.setStyleSheet(_btn_style("#1f5e3b", "#297a4d", "#ffffff", border_color="#369e63", font_size=11))
        self.btn_vis_both.clicked.connect(lambda: self._apply_viewport_bone_visibility("both"))
        h_vis.addWidget(self.btn_vis_both)

        self.btn_vis_a = QPushButton(f"{model_a_label} のみ")
        self.btn_vis_a.setFixedHeight(28)
        self.btn_vis_a.setStyleSheet(_btn_style("#1e5670", "#286e8f", "#d8f4ff", border_color="#368bb4", font_size=11))
        self.btn_vis_a.clicked.connect(lambda: self._apply_viewport_bone_visibility("model_a"))
        h_vis.addWidget(self.btn_vis_a)

        self.btn_vis_b = QPushButton(f"{model_b_label} のみ")
        self.btn_vis_b.setFixedHeight(28)
        self.btn_vis_b.setStyleSheet(_btn_style("#6e471b", "#8c5a22", "#ffe8cc", border_color="#aa6e29", font_size=11))
        self.btn_vis_b.setEnabled(len(self.target_models) >= 2)
        self.btn_vis_b.clicked.connect(lambda: self._apply_viewport_bone_visibility("model_b"))
        h_vis.addWidget(self.btn_vis_b)

        self.btn_vis_none = QPushButton("非表示")
        self.btn_vis_none.setFixedHeight(28)
        self.btn_vis_none.setStyleSheet(_btn_style("#3a3a3a", "#4e4e4e", "#dddddd", border_color="#5c5c5c", font_size=11))
        self.btn_vis_none.clicked.connect(lambda: self._apply_viewport_bone_visibility("none"))
        h_vis.addWidget(self.btn_vis_none)

        self.chk_colorize_bones = QCheckBox("キャラ別色分け")
        self.chk_colorize_bones.setChecked(True)
        self.chk_colorize_bones.setStyleSheet("color: #cccccc; font-size: 11px;")
        self.chk_colorize_bones.toggled.connect(lambda: self._apply_viewport_bone_visibility(self._last_vis_mode))
        h_vis.addWidget(self.chk_colorize_bones)
        h_vis.addStretch()
        layout.addWidget(vis_frame)

        # メインタブコンテナ（ボーン / 剛体・Joint）
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # ボーン絞り込み・削除タブ
        self.tab_bone = QWidget()
        layout_bone = QVBoxLayout(self.tab_bone)
        layout_bone.setSpacing(8)
        layout_bone.setContentsMargins(8, 8, 8, 8)

        # ボーン検索・絞り込みバー
        h_bsearch = QHBoxLayout()
        h_bsearch.addWidget(QLabel("ボーン絞り込み:"))
        self.le_bone_search = QLineEdit()
        self.le_bone_search.setPlaceholderText("ボーン名（頭、首、羽、帽子、リボン、腕、指など）やモデル名で絞り込み...")
        self.le_bone_search.textChanged.connect(self._filter_bone_items)
        h_bsearch.addWidget(self.le_bone_search, 1)

        self.chk_only_unused_bones = QCheckBox("未使用 (ウェイト0) のみ表示")
        self.chk_only_unused_bones.setChecked(False)
        self.chk_only_unused_bones.setStyleSheet("color: #ffaaaa; font-size: 11px;")
        self.chk_only_unused_bones.toggled.connect(self._filter_bone_items)
        h_bsearch.addWidget(self.chk_only_unused_bones)

        btn_bclear = QPushButton("クリア")
        btn_bclear.setFixedWidth(60)
        btn_bclear.setFixedHeight(28)
        btn_bclear.setStyleSheet(_btn_style("#383838", "#484848", "#dddddd", font_size=11))
        btn_bclear.clicked.connect(self._clear_bone_filter)
        h_bsearch.addWidget(btn_bclear)
        layout_bone.addLayout(h_bsearch)

        # ボーン一覧テーブル
        self.table_bones = QTableWidget()
        self.table_bones.setColumnCount(7)
        self.table_bones.setHorizontalHeaderLabels(["No", "所属モデル", "ボーン名 (日本語)", "英語名", "親ボーン", "ウェイト頂点数", "連動剛体"])
        self.table_bones.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_bones.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_bones.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_bones.verticalHeader().setVisible(False)
        self.table_bones.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_bones.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_bones.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_bones.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_bones.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_bones.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table_bones.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table_bones.setStyleSheet(
            "QTableWidget { background-color: #202020; border: 1px solid #444; border-radius: 4px; gridline-color: #333; }"
            "QTableWidget::item:selected { background-color: #2c5d88; color: #ffffff; }"
            "QHeaderView::section { background-color: #2e2e2e; color: #bbb; padding: 4px; border: 1px solid #3c3c3c; font-weight: bold; }"
        )
        self.table_bones.itemSelectionChanged.connect(self._on_bone_selection_changed)
        layout_bone.addWidget(self.table_bones, 1)

        # ボーンアクションフレーム
        bone_action_frame = QFrame()
        bone_action_frame.setStyleSheet("background-color: #262626; border-radius: 6px; padding: 4px;")
        layout_baction = QHBoxLayout(bone_action_frame)
        layout_baction.setContentsMargins(6, 6, 6, 6)
        layout_baction.setSpacing(8)

        self.cb_delete_bone_physics = QCheckBox("関連剛体・Jointも同時削除")
        self.cb_delete_bone_physics.setChecked(True)
        self.cb_delete_bone_physics.setStyleSheet("color: #aaffaa; font-weight: bold; font-size: 12px;")
        layout_baction.addWidget(self.cb_delete_bone_physics)
        layout_baction.addStretch()

        self.btn_delete_selected_bones = QPushButton("選択ボーンを安全に削除")
        self.btn_delete_selected_bones.setFixedHeight(34)
        self.btn_delete_selected_bones.setStyleSheet(_btn_style("#7a2b2b", "#9c3737", "#ffffff", border_color="#b84242", font_size=12))
        self.btn_delete_selected_bones.clicked.connect(self._delete_selected_bones)
        layout_baction.addWidget(self.btn_delete_selected_bones)

        layout_bone.addWidget(bone_action_frame)
        self.tabs.addTab(self.tab_bone, "ボーン絞り込み・削除")

        # 剛体・Joint絞り込み・削除タブ
        self.tab_physics = QWidget()
        layout_phys = QVBoxLayout(self.tab_physics)
        layout_phys.setSpacing(8)
        layout_phys.setContentsMargins(8, 8, 8, 8)

        # 剛体検索・絞り込みバー
        h_psearch = QHBoxLayout()
        h_psearch.addWidget(QLabel("剛体/Joint絞り込み:"))
        self.le_phys_search = QLineEdit()
        self.le_phys_search.setPlaceholderText("剛体名・追従先ボーン名（羽、髪、スカート等）・モデル名で絞り込み...")
        self.le_phys_search.textChanged.connect(self._filter_phys_items)
        h_psearch.addWidget(self.le_phys_search, 1)

        self.chk_only_orphaned_phys = QCheckBox("孤立 (ボーン未接続) のみ表示")
        self.chk_only_orphaned_phys.setChecked(False)
        self.chk_only_orphaned_phys.setStyleSheet("color: #ffcc88; font-size: 11px;")
        self.chk_only_orphaned_phys.toggled.connect(self._filter_phys_items)
        h_psearch.addWidget(self.chk_only_orphaned_phys)

        btn_pclear = QPushButton("クリア")
        btn_pclear.setFixedWidth(60)
        btn_pclear.setFixedHeight(28)
        btn_pclear.setStyleSheet(_btn_style("#383838", "#484848", "#dddddd", font_size=11))
        btn_pclear.clicked.connect(self._clear_phys_filter)
        h_psearch.addWidget(btn_pclear)
        layout_phys.addLayout(h_psearch)

        # 剛体・Joint一覧テーブル
        self.table_phys = QTableWidget()
        self.table_phys.setColumnCount(6)
        self.table_phys.setHorizontalHeaderLabels(["No", "所属モデル", "種別", "剛体/Joint名", "追従先ボーン", "接続状態"])
        self.table_phys.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_phys.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_phys.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_phys.verticalHeader().setVisible(False)
        self.table_phys.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_phys.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_phys.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_phys.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_phys.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_phys.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table_phys.setStyleSheet(
            "QTableWidget { background-color: #202020; border: 1px solid #444; border-radius: 4px; gridline-color: #333; }"
            "QTableWidget::item:selected { background-color: #2c5d88; color: #ffffff; }"
            "QHeaderView::section { background-color: #2e2e2e; color: #bbb; padding: 4px; border: 1px solid #3c3c3c; font-weight: bold; }"
        )
        self.table_phys.itemSelectionChanged.connect(self._on_phys_selection_changed)
        layout_phys.addWidget(self.table_phys, 1)

        # 剛体アクションフレーム
        phys_action_frame = QFrame()
        phys_action_frame.setStyleSheet("background-color: #262626; border-radius: 6px; padding: 4px;")
        layout_paction = QHBoxLayout(phys_action_frame)
        layout_paction.setContentsMargins(6, 6, 6, 6)
        layout_paction.setSpacing(8)
        layout_paction.addStretch()

        self.btn_delete_selected_phys = QPushButton("選択した剛体・Jointを削除")
        self.btn_delete_selected_phys.setFixedHeight(34)
        self.btn_delete_selected_phys.setStyleSheet(_btn_style("#7a2b2b", "#9c3737", "#ffffff", border_color="#b84242", font_size=12))
        self.btn_delete_selected_phys.clicked.connect(self._delete_selected_phys)
        layout_paction.addWidget(self.btn_delete_selected_phys)

        layout_phys.addWidget(phys_action_frame)
        self.tabs.addTab(self.tab_physics, "剛体・Joint絞り込み・削除")

        # 下部バー
        h_bottom = QHBoxLayout()
        lbl_hint = QLabel("※行を選択するとMayaビューポート上で該当ボーン・剛体がハイライト選択されます。")
        lbl_hint.setStyleSheet("color: #888888; font-size: 11px;")
        h_bottom.addWidget(lbl_hint)
        h_bottom.addStretch()

        btn_close = QPushButton("閉じる")
        btn_close.setFixedWidth(85)
        btn_close.setFixedHeight(30)
        btn_close.setStyleSheet(_btn_style("#383838", "#484848", "#dddddd", font_size=12))
        btn_close.clicked.connect(self.close)
        h_bottom.addWidget(btn_close)
        layout.addLayout(h_bottom)

    def _populate_model_combo(self):
        """モデルコンボボックスの設定（2体以上ある場合は両方表示モードを先頭に追加）"""
        self.cbb_model.blockSignals(True)
        self.cbb_model.clear()

        if len(self.target_models) >= 2:
            self.cbb_model.addItem("両方のモデルを表示 (全キャラのボーン・物理を一括表示)", self.ALL_MODELS_KEY)

        for m in self.target_models:
            self.cbb_model.addItem(m, m)

        if self.current_model == self.ALL_MODELS_KEY and len(self.target_models) >= 2:
            self.cbb_model.setCurrentIndex(0)
        elif self.current_model and self.current_model in self.target_models:
            idx = self.cbb_model.findData(self.current_model)
            if idx >= 0:
                self.cbb_model.setCurrentIndex(idx)

        self.cbb_model.blockSignals(False)
        self._reload_all_data()

    def _on_model_changed(self):
        """選択モデル切り替え時のハンドラ"""
        self.current_model = self.cbb_model.currentData()
        self._reload_all_data()

    def _apply_viewport_bone_visibility(self, mode):
        """ビューポート上のキャラ別 / 両方ボーン表示を切り替え"""
        self._last_vis_mode = mode
        model_a = self.target_models[0] if len(self.target_models) >= 1 else None
        model_b = self.target_models[1] if len(self.target_models) >= 2 else None
        colorize = self.chk_colorize_bones.isChecked() if hasattr(self, "chk_colorize_bones") else False
        res = model_modifier.set_models_bone_visibility(model_a, model_b, mode=mode, colorize=colorize)
        mode_labels = {
            "both": "両方のキャラのボーンを表示",
            "model_a": f"{model_a.split('|')[-1] if model_a else 'モデルA'} のボーンのみ表示",
            "model_b": f"{model_b.split('|')[-1] if model_b else 'モデルB'} のボーンのみ表示",
            "none": "ボーンを非表示",
        }
        mc.inViewMessage(
            amg=f"<hl>{mode_labels.get(mode, mode)} (表示: {res['visible_count']} 本)</hl>",
            pos="topCenter",
            fade=True,
        )

    def _reload_all_data(self):
        """選択対象（単体または両方）のボーンおよび剛体データを再収集"""
        if self.current_model == self.ALL_MODELS_KEY:
            models_to_load = [m for m in self.target_models if m and mc.objExists(m)]
        elif self.current_model and mc.objExists(self.current_model):
            models_to_load = [self.current_model]
        else:
            models_to_load = []

        self.bones_data = []
        self.physics_data = []
        seen_bone_nodes = set()
        seen_phys_nodes = set()

        for m in models_to_load:
            m_short = m.split("|")[-1]
            for b in model_modifier.get_model_bones_analysis(m):
                b_node = b.get("node")
                if b_node in seen_bone_nodes:
                    continue
                seen_bone_nodes.add(b_node)
                b_copy = dict(b)
                b_copy["model_name"] = m_short
                self.bones_data.append(b_copy)

            for p in model_modifier.get_model_physics_analysis(m):
                p_node = p.get("node")
                if p_node in seen_phys_nodes:
                    continue
                seen_phys_nodes.add(p_node)
                p_copy = dict(p)
                p_copy["model_name"] = m_short
                self.physics_data.append(p_copy)

        self._populate_bone_table()
        self._populate_phys_table()

    def _populate_bone_table(self):
        """ボーンテーブルへのデータ投入"""
        self.table_bones.blockSignals(True)
        self.table_bones.setRowCount(0)

        first_model = self.target_models[0].split("|")[-1] if self.target_models else ""
        for row_idx, b in enumerate(self.bones_data):
            self.table_bones.insertRow(row_idx)

            item_no = QTableWidgetItem(str(row_idx + 1))
            item_no.setTextAlignment(Qt.AlignCenter)
            item_no.setData(Qt.UserRole, b)

            m_name = b.get("model_name", "")
            item_model = QTableWidgetItem(m_name)
            item_model.setTextAlignment(Qt.AlignCenter)
            if m_name == first_model:
                item_model.setForeground(QtGui.QColor("#77ddff"))
            else:
                item_model.setForeground(QtGui.QColor("#ffcc77"))

            item_ja = QTableWidgetItem(b["name_ja"])
            item_en = QTableWidgetItem(b["name_en"])
            item_parent = QTableWidgetItem(b["parent_name"])

            w_text = f"{b['weight_count']} 頂点"
            if b["is_unused"]:
                w_text = "0 (未使用)"
            item_weight = QTableWidgetItem(w_text)
            item_weight.setTextAlignment(Qt.AlignCenter)
            if b["is_unused"]:
                item_weight.setForeground(QtGui.QColor("#ff7777"))

            r_text = f"{b['rigid_count']} 個" if b["rigid_count"] > 0 else "-"
            item_rigid = QTableWidgetItem(r_text)
            item_rigid.setTextAlignment(Qt.AlignCenter)

            self.table_bones.setItem(row_idx, 0, item_no)
            self.table_bones.setItem(row_idx, 1, item_model)
            self.table_bones.setItem(row_idx, 2, item_ja)
            self.table_bones.setItem(row_idx, 3, item_en)
            self.table_bones.setItem(row_idx, 4, item_parent)
            self.table_bones.setItem(row_idx, 5, item_weight)
            self.table_bones.setItem(row_idx, 6, item_rigid)

        self.table_bones.blockSignals(False)
        self._filter_bone_items()

    def _populate_phys_table(self):
        """剛体テーブルへのデータ投入"""
        self.table_phys.blockSignals(True)
        self.table_phys.setRowCount(0)

        first_model = self.target_models[0].split("|")[-1] if self.target_models else ""
        for row_idx, p in enumerate(self.physics_data):
            self.table_phys.insertRow(row_idx)

            item_no = QTableWidgetItem(str(row_idx + 1))
            item_no.setTextAlignment(Qt.AlignCenter)
            item_no.setData(Qt.UserRole, p)

            m_name = p.get("model_name", "")
            item_model = QTableWidgetItem(m_name)
            item_model.setTextAlignment(Qt.AlignCenter)
            if m_name == first_model:
                item_model.setForeground(QtGui.QColor("#77ddff"))
            else:
                item_model.setForeground(QtGui.QColor("#ffcc77"))

            item_type = QTableWidgetItem(p["type"])
            item_type.setTextAlignment(Qt.AlignCenter)

            item_name = QTableWidgetItem(p["name_ja"])
            item_target = QTableWidgetItem(p["target_bone"])

            status_text = "孤立 (ボーン未接続)" if p["is_orphaned"] else "正常接続"
            item_status = QTableWidgetItem(status_text)
            item_status.setTextAlignment(Qt.AlignCenter)
            if p["is_orphaned"]:
                item_status.setForeground(QtGui.QColor("#ffaa44"))

            self.table_phys.setItem(row_idx, 0, item_no)
            self.table_phys.setItem(row_idx, 1, item_model)
            self.table_phys.setItem(row_idx, 2, item_type)
            self.table_phys.setItem(row_idx, 3, item_name)
            self.table_phys.setItem(row_idx, 4, item_target)
            self.table_phys.setItem(row_idx, 5, item_status)

        self.table_phys.blockSignals(False)
        self._filter_phys_items()

    def _clear_bone_filter(self):
        """ボーン絞り込み条件を初期化"""
        self.le_bone_search.clear()
        self.chk_only_unused_bones.setChecked(False)

    def _clear_phys_filter(self):
        """剛体絞り込み条件を初期化"""
        self.le_phys_search.clear()
        self.chk_only_orphaned_phys.setChecked(False)

    def _filter_bone_items(self):
        """ボーンテーブルの絞り込みフィルタ（検索キーワードおよび未使用フィルタ）"""
        query = self.le_bone_search.text().strip().lower()
        only_unused = self.chk_only_unused_bones.isChecked()
        for row in range(self.table_bones.rowCount()):
            item_no = self.table_bones.item(row, 0)
            data = item_no.data(Qt.UserRole) if item_no else {}
            if only_unused and not data.get("is_unused", False):
                self.table_bones.setRowHidden(row, True)
                continue
            if not query:
                self.table_bones.setRowHidden(row, False)
                continue
            match = False
            for col in [1, 2, 3, 4]:
                item = self.table_bones.item(row, col)
                if item and query in item.text().lower():
                    match = True
                    break
            self.table_bones.setRowHidden(row, not match)

    def _filter_phys_items(self):
        """剛体テーブルの絞り込みフィルタ（検索キーワードおよび孤立フィルタ）"""
        query = self.le_phys_search.text().strip().lower()
        only_orphaned = self.chk_only_orphaned_phys.isChecked()
        for row in range(self.table_phys.rowCount()):
            item_no = self.table_phys.item(row, 0)
            data = item_no.data(Qt.UserRole) if item_no else {}
            if only_orphaned and not data.get("is_orphaned", False):
                self.table_phys.setRowHidden(row, True)
                continue
            if not query:
                self.table_phys.setRowHidden(row, False)
                continue
            match = False
            for col in [1, 2, 3, 4]:
                item = self.table_phys.item(row, col)
                if item and query in item.text().lower():
                    match = True
                    break
            self.table_phys.setRowHidden(row, not match)

    def _on_bone_selection_changed(self):
        """ボーンテーブル選択時にMaya上で該当ジョイントを選択"""
        selected_nodes = []
        for item in self.table_bones.selectedItems():
            row = item.row()
            item_no = self.table_bones.item(row, 0)
            if item_no:
                data = item_no.data(Qt.UserRole)
                if data and "node" in data:
                    selected_nodes.append(data["node"])

        valid_nodes = [n for n in set(selected_nodes) if mc.objExists(n)]
        if valid_nodes:
            mc.select(valid_nodes, replace=True)

    def _on_phys_selection_changed(self):
        """剛体テーブル選択時にMaya上で該当ノードを選択"""
        selected_nodes = []
        for item in self.table_phys.selectedItems():
            row = item.row()
            item_no = self.table_phys.item(row, 0)
            if item_no:
                data = item_no.data(Qt.UserRole)
                if data and "node" in data:
                    selected_nodes.append(data["node"])

        valid_nodes = [n for n in set(selected_nodes) if mc.objExists(n)]
        if valid_nodes:
            mc.select(valid_nodes, replace=True)

    def _delete_selected_bones(self):
        """選択されたボーンを削除"""
        selected_rows = set(item.row() for item in self.table_bones.selectedItems())
        if not selected_rows:
            QMessageBox.information(self, "案内", "削除したいボーンを選択してください。")
            return

        target_nodes = []
        target_names = []
        for r in sorted(list(selected_rows)):
            item_no = self.table_bones.item(r, 0)
            if item_no:
                data = item_no.data(Qt.UserRole)
                if data and "node" in data:
                    target_nodes.append(data["node"])
                    target_names.append(data["name_ja"])

        del_physics = self.cb_delete_bone_physics.isChecked()
        phys_hint = "\n※連動する剛体・Jointも一緒にクリーンアップされます。" if del_physics else ""

        reply = QMessageBox.question(
            self,
            "ボーン削除確認",
            f"選択された以下のボーン（計 {len(target_nodes)} 個）を削除しますか？\n"
            f"【対象】: {', '.join(target_names[:6])}{' 等...' if len(target_names) > 6 else ''}{phys_hint}\n\n"
            f"※子ボーンは親ボーンへ安全に再接続されます。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        deleted_count = model_modifier.delete_bones_safely(target_nodes, delete_connected_physics=del_physics)
        mc.inViewMessage(amg=f"<hl>{deleted_count}個のボーンを安全に削除しました</hl>", pos="topCenter", fade=True)
        self._reload_all_data()

    def _delete_selected_phys(self):
        """選択された剛体・Jointを削除"""
        selected_rows = set(item.row() for item in self.table_phys.selectedItems())
        if not selected_rows:
            QMessageBox.information(self, "案内", "削除したい剛体・Jointを選択してください。")
            return

        target_nodes = []
        target_names = []
        for r in sorted(list(selected_rows)):
            item_no = self.table_phys.item(r, 0)
            if item_no:
                data = item_no.data(Qt.UserRole)
                if data and "node" in data:
                    target_nodes.append(data["node"])
                    target_names.append(data["name_ja"])

        reply = QMessageBox.question(
            self,
            "剛体・Joint削除確認",
            f"選択された以下の物理アセット（計 {len(target_nodes)} 個）を削除しますか？\n"
            f"【対象】: {', '.join(target_names[:6])}{' 等...' if len(target_names) > 6 else ''}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        deleted_count = model_modifier.delete_physics_nodes(target_nodes)
        mc.inViewMessage(amg=f"<hl>{deleted_count}個の剛体/Jointを削除しました</hl>", pos="topCenter", fade=True)
        self._reload_all_data()

