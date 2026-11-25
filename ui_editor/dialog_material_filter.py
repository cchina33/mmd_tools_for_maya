# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 材質別マスキング表示・パーツ削除ダイアログモジュール
PMXエディタの絞り込み表示（マスキング）と同様に、材質ごとの表示チェック切り替え、
一括表示操作（全表示・全非表示・反転・選択のみ・検索結果のみ・マスク解除）、
選択材質または非表示材質のパーツ削除（頂点番号付け替えによるウェイト・モーフ保持）、
および不要になったモーフの同時削除機能を提供します。
"""

import importlib
import maya.cmds as mc

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QAbstractItemView, QMessageBox, QFrame, QComboBox, QCheckBox,
        QListWidget, QListWidgetItem, QGroupBox, QTextEdit
    )
    PYSIDE_VER = 6
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QAbstractItemView, QMessageBox, QFrame, QComboBox, QCheckBox,
        QListWidget, QListWidgetItem, QGroupBox, QTextEdit
    )
    PYSIDE_VER = 2

try:
    from ..maya_converters import mesh_mask_utils
    importlib.reload(mesh_mask_utils)
except Exception:
    try:
        from maya_converters import mesh_mask_utils
        importlib.reload(mesh_mask_utils)
    except Exception:
        import mesh_mask_utils
        importlib.reload(mesh_mask_utils)


def _btn_style(bg_normal, bg_hover, text_color="#ffffff", border_color=None, font_size=12, padding="3px 8px"):
    """ボタンスタイル生成（文字潰れ防止とコントラスト確保）"""
    b_col = border_color or bg_hover
    return (
        f"QPushButton {{ background-color: {bg_normal}; color: {text_color}; border: 1px solid {b_col}; border-radius: 4px; padding: {padding}; font-size: {font_size}px; font-weight: bold; }}"
        f"QPushButton:hover {{ background-color: {bg_hover}; border: 1px solid #52b7ff; }}"
        f"QPushButton:pressed {{ background-color: #1a1a1a; }}"
        f"QPushButton:disabled {{ background-color: #272727; color: #8e8e8e; border: 1px solid #3c3c3c; padding: {padding}; font-size: {font_size}px; font-weight: normal; }}"
    )


def get_model_materials_data(model_root, preserve_visibility_from=None):
    """指定モデル階層下の全ポリゴンメッシュから材質情報を収集"""
    return mesh_mask_utils.get_model_materials_data(model_root, preserve_visibility_from=preserve_visibility_from)


class PartDeleteConfirmDialog(QDialog):
    """
    パーツ削除実行前の詳細確認ダイアログ
    削除される材質・面数・頂点数・不要モーフ一覧・キー付きモーフ警告を表示し、
    要確認のグループモーフを任意で選択して同時削除できるようにします。
    """

    def __init__(self, impact_data, delete_unused_morphs=True, mode_label="選択材質", parent=None):
        super(PartDeleteConfirmDialog, self).__init__(parent)
        self.setWindowTitle(f"{mode_label}のパーツ削除確認")
        self.resize(560, 480)
        self.setMinimumSize(480, 380)

        self.impact = impact_data or {}
        self.delete_unused_morphs = delete_unused_morphs
        self.mode_label = mode_label
        self.is_confirmed = False
        self.selected_group_morphs = []

        self._init_ui()

    def _init_ui(self):
        """確認ダイアログレイアウトの初期化"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        mat_names = self.impact.get("material_names", [])
        del_faces = self.impact.get("deleted_faces_count", 0)
        rem_faces = self.impact.get("remaining_faces_count", 0)
        del_verts = self.impact.get("deleted_verts_count", 0)
        rem_verts = self.impact.get("remaining_verts_count", 0)

        lbl_head = QLabel(
            f"【{self.mode_label}のパーツ削除】 以下の内容でポリゴン面および孤立頂点を削除します。\n"
            f"残る頂点の番号は自動で付け替えられ、スキンウェイトと表情モーフが維持されます。"
        )
        lbl_head.setStyleSheet("color: #e8e8e8; font-weight: bold; font-size: 12px;")
        lbl_head.setWordWrap(True)
        layout.addWidget(lbl_head)

        # 概要ボックス
        grp_summary = QGroupBox("削除対象の概要")
        grp_summary.setStyleSheet("QGroupBox { font-weight: bold; color: #52b7ff; }")
        sum_layout = QVBoxLayout(grp_summary)

        txt_summary = QTextEdit()
        txt_summary.setReadOnly(True)
        txt_summary.setMaximumHeight(140)
        txt_summary.setStyleSheet("background-color: #1c1c1c; color: #dddddd; border: 1px solid #3a3a3a; font-size: 12px;")

        unused_vm = self.impact.get("unused_vertex_morphs", [])
        unused_mm = self.impact.get("unused_material_morphs", [])
        keyed_names = self.impact.get("keyed_morph_names", [])

        lines = [
            f"・対象材質 ({len(mat_names)}件): {', '.join(mat_names)}",
            f"・削除されるポリゴン面: {del_faces:,} 面 (残り: {rem_faces:,} 面)",
            f"・削除される孤立頂点: {del_verts:,} 頂点 (残り: {rem_verts:,} 頂点)",
        ]
        if self.delete_unused_morphs:
            vm_names = [m.get("name_jp") or m.get("alias_name", "") for m in unused_vm]
            mm_names = [m.get("name_jp") or m.get("attr_name", "") for m in unused_mm]
            lines.append(
                f"・同時削除される頂点モーフ ({len(vm_names)}件): "
                + (", ".join(vm_names) if vm_names else "なし")
            )
            lines.append(
                f"・同時削除される材質モーフ ({len(mm_names)}件): "
                + (", ".join(mm_names) if mm_names else "なし")
            )
        else:
            lines.append("・不要モーフの同時削除: オフ（モーフ定義をすべて維持します）")

        txt_summary.setPlainText("\n".join(lines))
        sum_layout.addWidget(txt_summary)
        layout.addWidget(grp_summary)

        # キーフレーム付きモーフ警告
        if self.delete_unused_morphs and keyed_names:
            lbl_warn = QLabel(
                f"【注意】 削除対象モーフのうち、アニメーションキーが設定されているものがあります:\n"
                f"  {', '.join(keyed_names)}"
            )
            lbl_warn.setStyleSheet(
                "background-color: #4a2c11; color: #ffcc88; border: 1px solid #aa6622; border-radius: 4px; padding: 6px; font-weight: bold;"
            )
            lbl_warn.setWordWrap(True)
            layout.addWidget(lbl_warn)

        # 要確認モーフ（グループモーフ）の任意選択リスト
        review_groups = self.impact.get("review_group_morphs", [])
        self.list_group_morphs = None
        if self.delete_unused_morphs and review_groups:
            grp_rev = QGroupBox(f"要確認のグループモーフ ({len(review_groups)}件 - チェックした項目のみ構造データから削除)")
            grp_rev.setStyleSheet("QGroupBox { font-weight: bold; color: #ffaa55; }")
            rev_layout = QVBoxLayout(grp_rev)

            lbl_rev_hint = QLabel("グループモーフは自動削除されません。不要なものが分かる場合のみチェックを入れてください。")
            lbl_rev_hint.setStyleSheet("color: #aaaaaa; font-size: 11px;")
            rev_layout.addWidget(lbl_rev_hint)

            self.list_group_morphs = QListWidget()
            self.list_group_morphs.setMaximumHeight(120)
            self.list_group_morphs.setStyleSheet("background-color: #1c1c1c; border: 1px solid #3a3a3a;")
            for gm in review_groups:
                g_name = gm.get("name_jp") or ""
                if not g_name:
                    continue
                item = QListWidgetItem(f"[{gm.get('index', 0)}] {g_name}")
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                item.setData(Qt.UserRole, g_name)
                self.list_group_morphs.addItem(item)
            rev_layout.addWidget(self.list_group_morphs)
            layout.addWidget(grp_rev)

        layout.addStretch()

        # 下部ボタン
        h_btns = QHBoxLayout()
        h_btns.addStretch()

        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setFixedWidth(100)
        btn_cancel.setFixedHeight(32)
        btn_cancel.setStyleSheet(_btn_style("#383838", "#484848", "#dddddd", border_color="#555555", font_size=12))
        btn_cancel.clicked.connect(self.reject)
        h_btns.addWidget(btn_cancel)

        btn_ok = QPushButton("削除を実行")
        btn_ok.setFixedWidth(130)
        btn_ok.setFixedHeight(32)
        btn_ok.setStyleSheet(_btn_style("#7a2b2b", "#9c3737", "#ffffff", border_color="#b84242", font_size=12))
        btn_ok.clicked.connect(self._on_confirm)
        h_btns.addWidget(btn_ok)

        layout.addLayout(h_btns)

    def _on_confirm(self):
        """確定ボタン押下時のハンドラ"""
        self.selected_group_morphs = []
        if self.list_group_morphs:
            for i in range(self.list_group_morphs.count()):
                item = self.list_group_morphs.item(i)
                if item and item.checkState() == Qt.Checked:
                    g_name = item.data(Qt.UserRole)
                    if g_name:
                        self.selected_group_morphs.append(g_name)
        self.is_confirmed = True
        self.accept()


class MaterialFilterDialog(QDialog):
    """
    材質別マスキング表示・選択・パーツ削除ダイアログ
    """

    def __init__(self, target_models=None, current_model=None, parent=None):
        super(MaterialFilterDialog, self).__init__(parent)
        self.setWindowTitle("材質別マスキング表示・パーツ削除ツール (PMXエディタ風)")
        self.resize(820, 620)
        self.setMinimumSize(640, 480)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        self.target_models = target_models or []
        self.current_model = current_model
        self.materials_data = []
        self._updating_table = False

        self._init_ui()
        self._populate_model_combo()

    def _init_ui(self):
        """ダイアログレイアウトの初期化"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # 対象モデル選択バーおよび表示状態ステータス
        h_model = QHBoxLayout()
        lbl_target = QLabel("対象モデル:")
        lbl_target.setStyleSheet("font-weight: bold; color: #52b7ff; font-size: 13px;")
        h_model.addWidget(lbl_target)
        self.cbb_model = QComboBox()
        self.cbb_model.currentIndexChanged.connect(self._on_model_changed)
        h_model.addWidget(self.cbb_model, 1)

        self.lbl_mask_status = QLabel("表示中: 0 / 0 材質")
        self.lbl_mask_status.setStyleSheet("color: #77ff77; font-weight: bold; font-size: 12px; padding: 0 8px;")
        h_model.addWidget(self.lbl_mask_status)

        self.btn_refresh = QPushButton("更新")
        self.btn_refresh.setFixedWidth(70)
        self.btn_refresh.setFixedHeight(30)
        self.btn_refresh.setStyleSheet(_btn_style("#383838", "#484848", "#e0e0e0", border_color="#555555", font_size=12))
        self.btn_refresh.clicked.connect(self._reload_materials)
        h_model.addWidget(self.btn_refresh)
        layout.addLayout(h_model)

        # マスキング一括操作ツールバー
        mask_frame = QFrame()
        mask_frame.setStyleSheet("background-color: #252525; border: 1px solid #3a3a3a; border-radius: 5px;")
        h_mask = QHBoxLayout(mask_frame)
        h_mask.setContentsMargins(8, 5, 8, 5)
        h_mask.setSpacing(6)

        lbl_mask = QLabel("絞り込み表示:")
        lbl_mask.setStyleSheet("color: #52c5ff; font-weight: bold; font-size: 12px;")
        h_mask.addWidget(lbl_mask)

        self.btn_mask_all_on = QPushButton("全表示")
        self.btn_mask_all_on.setFixedHeight(28)
        self.btn_mask_all_on.setStyleSheet(_btn_style("#264b6e", "#33618d", "#ffffff", border_color="#3d72a4", font_size=11, padding="2px 8px"))
        self.btn_mask_all_on.clicked.connect(self._on_mask_all_on)
        h_mask.addWidget(self.btn_mask_all_on)

        self.btn_mask_all_off = QPushButton("全非表示")
        self.btn_mask_all_off.setFixedHeight(28)
        self.btn_mask_all_off.setStyleSheet(_btn_style("#3a3a3a", "#4c4c4c", "#dddddd", border_color="#5a5a5a", font_size=11, padding="2px 8px"))
        self.btn_mask_all_off.clicked.connect(self._on_mask_all_off)
        h_mask.addWidget(self.btn_mask_all_off)

        self.btn_mask_invert = QPushButton("表示を反転")
        self.btn_mask_invert.setFixedHeight(28)
        self.btn_mask_invert.setStyleSheet(_btn_style("#3d355e", "#50467a", "#ffffff", border_color="#65589c", font_size=11, padding="2px 8px"))
        self.btn_mask_invert.clicked.connect(self._on_mask_invert)
        h_mask.addWidget(self.btn_mask_invert)

        self.btn_mask_only_selected = QPushButton("選択材質のみ表示")
        self.btn_mask_only_selected.setFixedHeight(28)
        self.btn_mask_only_selected.setStyleSheet(_btn_style("#1e5670", "#286e8f", "#ffffff", border_color="#368bb4", font_size=11, padding="2px 8px"))
        self.btn_mask_only_selected.clicked.connect(self._on_mask_only_selected)
        h_mask.addWidget(self.btn_mask_only_selected)

        self.btn_mask_show_filtered = QPushButton("検索結果をすべて表示")
        self.btn_mask_show_filtered.setFixedHeight(28)
        self.btn_mask_show_filtered.setStyleSheet(_btn_style("#2b4f4f", "#386666", "#aaffff", border_color="#488282", font_size=11, padding="2px 8px"))
        self.btn_mask_show_filtered.clicked.connect(self._on_mask_show_filtered)
        h_mask.addWidget(self.btn_mask_show_filtered)

        h_mask.addStretch()

        self.btn_mask_restore = QPushButton("マスク解除")
        self.btn_mask_restore.setFixedHeight(28)
        self.btn_mask_restore.setStyleSheet(_btn_style("#5c4318", "#785720", "#ffeeaa", border_color="#966d28", font_size=11, padding="2px 10px"))
        self.btn_mask_restore.setToolTip("マスキング表示を解除し、すべての材質を元の表示状態へ戻します。")
        self.btn_mask_restore.clicked.connect(self._on_mask_restore)
        h_mask.addWidget(self.btn_mask_restore)

        layout.addWidget(mask_frame)

        # 検索フィルターバー
        h_search = QHBoxLayout()
        lbl_search = QLabel("絞り込み検索:")
        lbl_search.setStyleSheet("color: #a0a0a0; font-size: 12px;")
        h_search.addWidget(lbl_search)
        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText("材質名（日本語・英語）やシェーダー名で絞り込み...")
        self.le_search.textChanged.connect(self._filter_table_items)
        h_search.addWidget(self.le_search, 1)

        btn_clear = QPushButton("クリア")
        btn_clear.setFixedWidth(65)
        btn_clear.setFixedHeight(30)
        btn_clear.setStyleSheet(_btn_style("#383838", "#484848", "#dddddd", border_color="#555555", font_size=12))
        btn_clear.clicked.connect(lambda: self.le_search.clear())
        h_search.addWidget(btn_clear)
        layout.addLayout(h_search)

        # 材質一覧テーブル（先頭に表示チェック列）
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["表示", "No", "材質名 (日本語)", "英語名", "シェーダー名", "フェース数"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #202020; border: 1px solid #444; border-radius: 4px; gridline-color: #333; }"
            "QTableWidget::item:selected { background-color: #2c5d88; color: #ffffff; }"
            "QHeaderView::section { background-color: #2e2e2e; color: #bbb; padding: 4px; border: 1px solid #3c3c3c; font-weight: bold; }"
        )
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemChanged.connect(self._on_table_item_changed)
        layout.addWidget(self.table, 1)

        # 削除オプションバー
        opt_frame = QFrame()
        opt_frame.setStyleSheet("background-color: #222222; border-radius: 4px;")
        h_opt = QHBoxLayout(opt_frame)
        h_opt.setContentsMargins(8, 4, 8, 4)
        h_opt.setSpacing(16)

        self.chk_delete_unused_morphs = QCheckBox("不要になったモーフ（頂点・材質）も一緒に削除する")
        self.chk_delete_unused_morphs.setChecked(True)
        self.chk_delete_unused_morphs.setStyleSheet("color: #e0e0e0; font-weight: bold; font-size: 12px;")
        h_opt.addWidget(self.chk_delete_unused_morphs)

        self.chk_cleanup_shaders = QCheckBox("面が0になった未使用シェーダーも掃除する")
        self.chk_cleanup_shaders.setChecked(False)
        self.chk_cleanup_shaders.setStyleSheet("color: #bbbbbb; font-size: 12px;")
        h_opt.addWidget(self.chk_cleanup_shaders)
        h_opt.addStretch()
        layout.addWidget(opt_frame)

        # アクション操作ボタンフレーム
        action_frame = QFrame()
        action_frame.setStyleSheet("background-color: #262626; border-radius: 6px; padding: 4px;")
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(6, 6, 6, 6)
        action_layout.setSpacing(10)

        self.btn_select_faces = QPushButton("選択材質のフェースをMaya上で選択")
        self.btn_select_faces.setFixedHeight(34)
        self.btn_select_faces.setStyleSheet(_btn_style("#255d82", "#3277a6", "#ffffff", border_color="#3d8ec4", font_size=12, padding="4px 10px"))
        self.btn_select_faces.clicked.connect(self._select_material_faces)
        action_layout.addWidget(self.btn_select_faces)

        self.btn_delete_faces = QPushButton("選択材質のパーツ削除")
        self.btn_delete_faces.setFixedHeight(34)
        self.btn_delete_faces.setStyleSheet(_btn_style("#7a2b2b", "#9c3737", "#ffffff", border_color="#b84242", font_size=12, padding="4px 12px"))
        self.btn_delete_faces.setToolTip("テーブルで選択している材質のポリゴン面と孤立頂点を削除し、ウェイトとモーフの頂点番号を付け替えます。")
        self.btn_delete_faces.clicked.connect(self._delete_selected_material_parts)
        action_layout.addWidget(self.btn_delete_faces)

        self.btn_delete_hidden = QPushButton("非表示材質のパーツ削除")
        self.btn_delete_hidden.setFixedHeight(34)
        self.btn_delete_hidden.setStyleSheet(_btn_style("#6b2d5c", "#8a3a77", "#ffffff", border_color="#a84791", font_size=12, padding="4px 12px"))
        self.btn_delete_hidden.setToolTip("表示チェックが外れている（非表示の）材質のポリゴン面と孤立頂点を一括削除します。")
        self.btn_delete_hidden.clicked.connect(self._delete_hidden_material_parts)
        action_layout.addWidget(self.btn_delete_hidden)

        layout.addWidget(action_frame)

        # 下部ボタンバー
        h_bottom = QHBoxLayout()
        lbl_hint = QLabel("※「表示」チェックでビューポート上の表示を絞り込みでき、ウィンドウを閉じると元の表示へ戻ります。")
        lbl_hint.setStyleSheet("color: #888888; font-size: 11px;")
        h_bottom.addWidget(lbl_hint)
        h_bottom.addStretch()

        btn_close = QPushButton("閉じる")
        btn_close.setFixedWidth(85)
        btn_close.setFixedHeight(30)
        btn_close.setStyleSheet(_btn_style("#383838", "#484848", "#dddddd", border_color="#555555", font_size=12))
        btn_close.clicked.connect(self.close)
        h_bottom.addWidget(btn_close)
        layout.addLayout(h_bottom)

    def _populate_model_combo(self):
        """モデルコンボボックスの設定"""
        self.cbb_model.blockSignals(True)
        self.cbb_model.clear()

        for m in self.target_models:
            self.cbb_model.addItem(m, m)

        if self.current_model and self.current_model in self.target_models:
            idx = self.cbb_model.findData(self.current_model)
            if idx >= 0:
                self.cbb_model.setCurrentIndex(idx)

        self.cbb_model.blockSignals(False)
        self._reload_materials()

    def _on_model_changed(self):
        """選択モデル切り替え時のハンドラ（切り替え前モデルのマスクを解除）"""
        if self.current_model:
            mesh_mask_utils.restore_material_mask(self.current_model)
        self.current_model = self.cbb_model.currentData()
        self._reload_materials()

    def _reload_materials(self):
        """現在のモデルから材質データを収集し、面数が1以上の材質でテーブルを構築"""
        raw_list = get_model_materials_data(self.current_model, preserve_visibility_from=self.materials_data)
        self.materials_data = [d for d in raw_list if d.get("face_count", 0) > 0]
        self._populate_table()
        self._update_mask_status_label()

    def _populate_table(self):
        """テーブルウィジェットへの行データ投入"""
        self._updating_table = True
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        for row_idx, data in enumerate(self.materials_data):
            self.table.insertRow(row_idx)

            item_vis = QTableWidgetItem()
            item_vis.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item_vis.setCheckState(Qt.Checked if data.get("visible", True) else Qt.Unchecked)
            item_vis.setTextAlignment(Qt.AlignCenter)

            item_no = QTableWidgetItem(str(row_idx + 1))
            item_no.setTextAlignment(Qt.AlignCenter)
            item_no.setData(Qt.UserRole, data)

            item_ja = QTableWidgetItem(data["name_ja"])
            item_en = QTableWidgetItem(data["name_en"])
            item_shd = QTableWidgetItem(data["shader"])

            count_str = str(data["face_count"]) if data["face_count"] > 0 else "-"
            item_cnt = QTableWidgetItem(count_str)
            item_cnt.setTextAlignment(Qt.AlignCenter)

            self.table.setItem(row_idx, 0, item_vis)
            self.table.setItem(row_idx, 1, item_no)
            self.table.setItem(row_idx, 2, item_ja)
            self.table.setItem(row_idx, 3, item_en)
            self.table.setItem(row_idx, 4, item_shd)
            self.table.setItem(row_idx, 5, item_cnt)

        self.table.blockSignals(False)
        self._updating_table = False
        self._filter_table_items()

    def _update_mask_status_label(self):
        """表示中材質数とマスク状態のラベルを更新"""
        total_cnt = len(self.materials_data)
        vis_cnt = sum(1 for d in self.materials_data if d.get("visible", True))
        if vis_cnt < total_cnt:
            self.lbl_mask_status.setText(f"【マスク中】 表示中: {vis_cnt} / {total_cnt} 材質")
            self.lbl_mask_status.setStyleSheet("color: #ffcc55; font-weight: bold; font-size: 12px; padding: 0 8px;")
        else:
            self.lbl_mask_status.setText(f"表示中: {vis_cnt} / {total_cnt} 材質")
            self.lbl_mask_status.setStyleSheet("color: #77ff77; font-weight: bold; font-size: 12px; padding: 0 8px;")

    def _on_table_item_changed(self, item):
        """表示チェックボックス切り替え時にマスキング表示を即時反映"""
        if self._updating_table or not item or item.column() != 0:
            return
        row = item.row()
        item_no = self.table.item(row, 1)
        if not item_no:
            return
        data = item_no.data(Qt.UserRole)
        if not data:
            return
        data["visible"] = (item.checkState() == Qt.Checked)
        self._apply_current_mask()

    def _apply_current_mask(self):
        """現在の表示フラグ構成をビューポートへ反映"""
        if self.current_model:
            mesh_mask_utils.apply_material_mask(self.current_model, self.materials_data)
        self._update_mask_status_label()

    def _set_visibility_for_predicate(self, predicate_fn):
        """条件関数に従って各行の表示チェック状態を一括更新しビューポートへ反映"""
        self._updating_table = True
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item_vis = self.table.item(row, 0)
            item_no = self.table.item(row, 1)
            if not item_vis or not item_no:
                continue
            data = item_no.data(Qt.UserRole)
            if not data:
                continue
            new_vis = bool(predicate_fn(row, data))
            data["visible"] = new_vis
            item_vis.setCheckState(Qt.Checked if new_vis else Qt.Unchecked)
        self.table.blockSignals(False)
        self._updating_table = False
        self._apply_current_mask()

    def _on_mask_all_on(self):
        """全材質を表示に設定"""
        self._set_visibility_for_predicate(lambda row, data: True)

    def _on_mask_all_off(self):
        """全材質を非表示に設定"""
        self._set_visibility_for_predicate(lambda row, data: False)

    def _on_mask_invert(self):
        """全材質の表示・非表示を反転"""
        self._set_visibility_for_predicate(lambda row, data: not data.get("visible", True))

    def _on_mask_only_selected(self):
        """現在テーブルで選択されている行の材質のみを表示"""
        selected_rows = set(item.row() for item in self.table.selectedItems())
        if not selected_rows:
            QMessageBox.information(self, "案内", "表示したい材質を行で選択してください。")
            return
        self._set_visibility_for_predicate(lambda row, data: row in selected_rows)

    def _on_mask_show_filtered(self):
        """検索欄のフィルターに一致している行の材質のみを表示"""
        self._set_visibility_for_predicate(lambda row, data: not self.table.isRowHidden(row))

    def _on_mask_restore(self):
        """マスキング表示を解除して全材質を表示状態に戻す"""
        if self.current_model:
            mesh_mask_utils.restore_material_mask(self.current_model)
        self._set_visibility_for_predicate(lambda row, data: True)

    def _filter_table_items(self):
        """検索テキストに基づくテーブル行のフィルタ表示"""
        query = self.le_search.text().strip().lower()
        for row in range(self.table.rowCount()):
            if not query:
                self.table.setRowHidden(row, False)
                continue
            match = False
            for col in [2, 3, 4]:
                item = self.table.item(row, col)
                if item and query in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)

    def _get_selected_material_datas(self):
        """現在テーブルで選択されている材質データリストを取得"""
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())

        selected_datas = []
        for r in sorted(list(selected_rows)):
            item_no = self.table.item(r, 1)
            if item_no:
                data = item_no.data(Qt.UserRole)
                if data:
                    selected_datas.append(data)
        return selected_datas

    def _get_hidden_material_datas(self):
        """現在表示チェックが外れている（非表示の）材質データリストを取得"""
        return [d for d in self.materials_data if not d.get("visible", True)]

    def _on_selection_changed(self):
        """テーブルの行選択変更時にMayaビューポートで該当フェースを連動選択"""
        if self.current_model and mesh_mask_utils.is_mask_active(self.current_model):
            return

        datas = self._get_selected_material_datas()
        all_faces = []
        for d in datas:
            all_faces.extend(d.get("faces", []))

        if all_faces:
            valid_items = [f for f in all_faces if mc.objExists(f.split(".")[0])]
            if valid_items:
                try:
                    mc.select(valid_items, replace=True)
                    return
                except Exception:
                    pass
        mc.select(clear=True)

    def _select_material_faces(self):
        """選択されている材質のフェースを改めてMaya上で選択"""
        datas = self._get_selected_material_datas()
        all_faces = []
        for d in datas:
            all_faces.extend(d.get("faces", []))
        if all_faces:
            try:
                mc.select(all_faces, replace=True)
            except Exception:
                pass

    def _execute_parts_deletion(self, target_datas, mode_label="選択材質"):
        """指定された材質リストに対して確認ダイアログを表示し、頂点番号付け替え付きパーツ削除を実行"""
        if not self.current_model:
            QMessageBox.warning(self, "案内", "対象モデルが選択されていません。")
            return
        if not target_datas:
            QMessageBox.information(self, "案内", f"削除対象となる{mode_label}がありません。")
            return
        if len(target_datas) >= len(self.materials_data):
            QMessageBox.warning(self, "警告", "すべての材質を削除することはできません。少なくとも1つの材質を残してください。")
            return

        del_morphs = self.chk_delete_unused_morphs.isChecked()
        clean_shd = self.chk_cleanup_shaders.isChecked()

        impact = mesh_mask_utils.analyze_deletion_impact(self.current_model, target_datas)
        if not impact or impact.get("deleted_faces_count", 0) <= 0:
            QMessageBox.warning(self, "警告", "削除可能なポリゴン面が見つかりませんでした。")
            return

        dlg = PartDeleteConfirmDialog(
            impact_data=impact,
            delete_unused_morphs=del_morphs,
            mode_label=mode_label,
            parent=self,
        )
        dlg.exec_()
        if not dlg.is_confirmed:
            return

        try:
            res = mesh_mask_utils.delete_materials_and_remap(
                model_root=self.current_model,
                target_material_datas=target_datas,
                delete_unused_morphs=del_morphs,
                remove_group_morph_names=dlg.selected_group_morphs,
                cleanup_unused_shaders=clean_shd,
            )
            if not res.get("success"):
                QMessageBox.warning(self, "削除中断", res.get("message", "パーツ削除を中断しました。"))
                return

            del_f = res.get("deleted_faces", 0)
            del_v = res.get("deleted_vertices", 0)
            del_m = res.get("removed_morph_count", 0)
            mc.inViewMessage(
                amg=f"<hl>{del_f}面 / {del_v}頂点 / 不要モーフ{del_m}件 を削除しました</hl>",
                pos="topCenter",
                fade=True,
            )
            self._reload_materials()
            self._apply_current_mask()
        except Exception as e:
            QMessageBox.critical(self, "削除エラー", f"パーツ削除処理中にエラーが発生したため中断しました:\n{e}")
            self._reload_materials()

    def _delete_selected_material_parts(self):
        """選択されている材質のパーツ削除"""
        datas = self._get_selected_material_datas()
        if not datas:
            QMessageBox.information(self, "案内", "削除したい材質を行で選択してください。")
            return
        self._execute_parts_deletion(datas, mode_label="選択材質")

    def _delete_material_faces(self):
        """後方互換用の選択材質パーツ削除エントリ"""
        self._delete_selected_material_parts()

    def _delete_hidden_material_parts(self):
        """非表示（表示チェックがオフ）の材質のパーツ削除"""
        datas = self._get_hidden_material_datas()
        if not datas:
            QMessageBox.information(self, "案内", "非表示になっている材質がありません。「表示」チェックを外してから実行してください。")
            return
        self._execute_parts_deletion(datas, mode_label="非表示材質")

    def closeEvent(self, event):
        """ダイアログを閉じる際にマスキング表示を解除して元の表示状態へ復元"""
        if self.current_model:
            try:
                mesh_mask_utils.restore_material_mask(self.current_model)
            except Exception:
                pass
        super(MaterialFilterDialog, self).closeEvent(event)
