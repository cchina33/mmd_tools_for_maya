# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MMD Model Editor モデル改造・お着替えタブモジュール
素体モデル（頭部・キャラクター側）と衣装モデル（ボディ・衣装側）を選択し、
利用規約の事前確認、位置合わせ、不要メッシュ整理、首境界結合・法線補正、
スキンウェイト一時保存・綺麗再バインド、ボーン・物理統合を実行します。
"""

import os
import sys
import maya.cmds as mc
import maya.api.OpenMaya as om

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QGroupBox, QComboBox, QDoubleSpinBox,
        QCheckBox, QScrollArea, QFrame, QMessageBox, QProgressBar, QSlider,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
    )
    PYSIDE_VER = 6
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt, Signal
    from PySide2.QtWidgets import (
        QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QGroupBox, QComboBox, QDoubleSpinBox,
        QCheckBox, QScrollArea, QFrame, QMessageBox, QProgressBar, QSlider,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
    )
    PYSIDE_VER = 2

from .dialog_terms_confirm import ModelTermsConfirmDialog
from .dialog_material_filter import MaterialFilterDialog
from .dialog_bone_physics_filter import BonePhysicsFilterDialog

try:
    from ..maya_converters import model_modifier
except Exception:
    try:
        from maya_converters import model_modifier
    except Exception:
        import model_modifier


def _create_button_style(bg_normal, bg_hover, text_color="#ffffff", border_color=None, border_hover=None, font_size=12, padding="3px 8px"):
    """
    ボタンのパディングとフォントサイズを適正化し、文字の縦潰れや見切れを防止するQSSスタイルを生成
    無効状態（disabled）の時も背景と同化せず文字がはっきりと読めるコントラストを保証します。
    """
    b_col = border_color or bg_hover
    bh_col = border_hover or "#52b7ff"
    return (
        f"QPushButton {{ background-color: {bg_normal}; color: {text_color}; border: 1px solid {b_col}; border-radius: 4px; padding: {padding}; font-size: {font_size}px; font-weight: bold; }}"
        f"QPushButton:hover {{ background-color: {bg_hover}; border: 1px solid {bh_col}; }}"
        f"QPushButton:pressed {{ background-color: #1a1a1a; }}"
        f"QPushButton:disabled {{ background-color: #272727; color: #8e8e8e; border: 1px solid #3c3c3c; padding: {padding}; font-size: {font_size}px; font-weight: normal; }}"
    )


class BoneMergeMapDialog(QDialog):
    """
    ボーン統合対応表の確認・手動編集ダイアログ (Step 5)
    左に移植元ボーン、中央に統合方式、右にマスター骨格側の割り当て先ボーンを表示し、
    自動推定結果を一覧で確認・変更した上でボーン統合を実行できます。
    """

    _ACTION_LABELS = [
        ("merge_to_master", "共通: マスター側ボーンへウェイト付替"),
        ("transplant_unique", "固有: マスター骨格へ親子付け移植"),
        ("transplant_renamed", "衝突回避: 接尾辞付きで固有移植"),
        ("skip_unused", "未使用: 移植スキップ (ウェイト0)"),
    ]

    def __init__(self, merge_plan, parent=None):
        super(BoneMergeMapDialog, self).__init__(parent)
        self.setWindowTitle("ボーン統合対応表の確認・編集 (Step 5)")
        self.resize(860, 580)
        self.setMinimumSize(680, 440)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        self.merge_plan = merge_plan or {}
        self.items = self.merge_plan.get("items", [])
        self.master_bones = self.merge_plan.get("master_bones", [])
        self.is_confirmed = False
        self._row_widgets = []

        self._init_ui()
        self._populate_table()

    def _init_ui(self):
        """ダイアログレイアウトの初期化"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        src_m = self.merge_plan.get("source_model", "").split("|")[-1]
        mst_m = self.merge_plan.get("master_model", "").split("|")[-1]
        sum_info = self.merge_plan.get("summary", {})

        lbl_info = QLabel(
            f"移植元『{src_m}』 → マスター骨格『{mst_m}』\n"
            f"自動推定: 共通ウェイト付替 {sum_info.get('merge_count', 0)} 本 / "
            f"固有ボーン移植 {sum_info.get('transplant_unique_count', 0)} 本 / "
            f"名前衝突リネーム {sum_info.get('transplant_renamed_count', 0)} 本 / "
            f"未使用スキップ {sum_info.get('skip_unused_count', 0)} 本"
        )
        lbl_info.setStyleSheet("color: #d8f0ff; font-weight: bold; font-size: 12px;")
        layout.addWidget(lbl_info)

        h_filter = QHBoxLayout()
        h_filter.addWidget(QLabel("ボーン名検索:"))
        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText("ボーン名で絞り込み...")
        self.le_search.textChanged.connect(self._on_filter_changed)
        h_filter.addWidget(self.le_search, 1)

        self.chk_hide_unused = QCheckBox("未使用スキップ(ウェイト0)を隠す")
        self.chk_hide_unused.setChecked(True)
        self.chk_hide_unused.toggled.connect(self._on_filter_changed)
        h_filter.addWidget(self.chk_hide_unused)
        layout.addLayout(h_filter)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "No", "移植元ボーン名", "ウェイト頂点数", "統合方式",
            "割り当て先 / 移植親ボーン (マスター側)", "移植後のボーン名"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #1f1f1f; border: 1px solid #444; gridline-color: #333; }"
            "QHeaderView::section { background-color: #2e2e2e; color: #bbb; padding: 4px; border: 1px solid #3c3c3c; font-weight: bold; }"
        )
        layout.addWidget(self.table, 1)

        h_btns = QHBoxLayout()
        h_btns.addStretch()

        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setFixedWidth(100)
        btn_cancel.setFixedHeight(34)
        btn_cancel.setStyleSheet(_create_button_style("#383838", "#484848", "#dddddd", border_color="#555555", font_size=12))
        btn_cancel.clicked.connect(self.reject)
        h_btns.addWidget(btn_cancel)

        btn_ok = QPushButton("この対応表でボーン統合を実行")
        btn_ok.setFixedWidth(220)
        btn_ok.setFixedHeight(34)
        btn_ok.setStyleSheet(_create_button_style("#185d8f", "#2176b5", "#ffffff", border_color="#2b94e3", font_size=12))
        btn_ok.clicked.connect(self._on_confirm)
        h_btns.addWidget(btn_ok)
        layout.addLayout(h_btns)

    def _populate_table(self):
        """対応表データをテーブルへ投入"""
        self.table.setRowCount(0)
        self._row_widgets = []

        for row_idx, item in enumerate(self.items):
            self.table.insertRow(row_idx)

            it_no = QTableWidgetItem(str(row_idx + 1))
            it_no.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 0, it_no)

            src_label = f"{item['source_name_jp']} ({item['source_short_name']})"
            it_src = QTableWidgetItem(src_label)
            self.table.setItem(row_idx, 1, it_src)

            it_w = QTableWidgetItem(str(item.get("weight_count", 0)))
            it_w.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 2, it_w)

            cbb_act = QComboBox()
            for act_key, act_label in self._ACTION_LABELS:
                cbb_act.addItem(act_label, act_key)
            act_idx = cbb_act.findData(item.get("action", "merge_to_master"))
            if act_idx >= 0:
                cbb_act.setCurrentIndex(act_idx)
            self.table.setCellWidget(row_idx, 3, cbb_act)

            cbb_target = QComboBox()
            cbb_target.addItem("(なし / サブツリー内部)", None)
            for mb in self.master_bones:
                m_label = f"{mb['canonical_name']} ({mb['short_name']})"
                cbb_target.addItem(m_label, mb["node"])

            cur_target = item.get("target_master_bone") or item.get("target_parent_bone")
            if cur_target:
                t_idx = cbb_target.findData(cur_target)
                if t_idx >= 0:
                    cbb_target.setCurrentIndex(t_idx)
            self.table.setCellWidget(row_idx, 4, cbb_target)

            le_name = QLineEdit(item.get("new_bone_name") or item.get("source_name_jp", ""))
            self.table.setCellWidget(row_idx, 5, le_name)

            self._row_widgets.append((item, cbb_act, cbb_target, le_name))

        self._on_filter_changed()

    def _on_filter_changed(self):
        """検索キーワードおよび未使用非表示フィルタの反映"""
        query = self.le_search.text().strip().lower()
        hide_unused = self.chk_hide_unused.isChecked()

        for row_idx, (item, cbb_act, _, _) in enumerate(self._row_widgets):
            act_val = cbb_act.currentData()
            if hide_unused and act_val == "skip_unused":
                self.table.setRowHidden(row_idx, True)
                continue
            if query:
                text_src = f"{item.get('source_name_jp', '')} {item.get('source_short_name', '')}".lower()
                if query not in text_src:
                    self.table.setRowHidden(row_idx, True)
                    continue
            self.table.setRowHidden(row_idx, False)

    def _on_confirm(self):
        """UI上で編集された内容を merge_plan に書き戻して確定"""
        for item, cbb_act, cbb_target, le_name in self._row_widgets:
            new_act = cbb_act.currentData()
            new_target = cbb_target.currentData()
            new_bname = le_name.text().strip() or item.get("source_name_jp", "")

            item["action"] = new_act
            item["new_bone_name"] = new_bname
            if new_act == "merge_to_master":
                item["target_master_bone"] = new_target
            elif new_act in ("transplant_unique", "transplant_renamed"):
                if new_target:
                    item["target_parent_bone"] = new_target
                    item["target_master_bone"] = new_target
                    item["is_subtree_root"] = True

        self.is_confirmed = True
        self.accept()


class PhysicsMergePlanDialog(QDialog):
    """
    物理統合プランおよび衝突グループ候補の確認・調整ダイアログ (Step 6)
    移植される剛体・Jointの一覧と、衝突グループ番号（グループ1〜16）の重複状況および空きグループ候補を表示し、
    グループ割り当てを確認・調整した上で物理統合を実行できます。
    """

    def __init__(self, physics_plan, parent=None):
        super(PhysicsMergePlanDialog, self).__init__(parent)
        self.setWindowTitle("物理統合プラン & 衝突グループ候補の確認 (Step 6)")
        self.resize(840, 560)
        self.setMinimumSize(660, 440)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        self.physics_plan = physics_plan or {}
        self.collision_analysis = self.physics_plan.get("collision_analysis", {})
        self.group_remap = dict(self.collision_analysis.get("default_remap", {}))
        self.is_confirmed = False
        self._group_combos = []

        self._init_ui()
        self._populate_tables()

    def _init_ui(self):
        """ダイアログレイアウトの初期化"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        src_m = self.physics_plan.get("source_model", "").split("|")[-1]
        mst_m = self.physics_plan.get("master_model", "").split("|")[-1]
        rbs = self.physics_plan.get("transplanted_rbs", [])
        jts = self.physics_plan.get("transplanted_joints", [])
        mst_rb_cnt = self.physics_plan.get("master_existing_rb_count", 0)
        mst_jt_cnt = self.physics_plan.get("master_existing_joint_count", 0)

        lbl_head = QLabel(
            f"移植元『{src_m}』 → マスター『{mst_m}』\n"
            f"・移植対象の剛体: {len(rbs)} 個 (番号振り直し: {mst_rb_cnt} 〜 {mst_rb_cnt + max(0, len(rbs) - 1)})\n"
            f"・移植対象のJoint: {len(jts)} 個 (番号振り直し: {mst_jt_cnt} 〜 {mst_jt_cnt + max(0, len(jts) - 1)})"
        )
        lbl_head.setStyleSheet("color: #d8f0ff; font-weight: bold; font-size: 12px;")
        layout.addWidget(lbl_head)

        # 衝突グループ候補テーブル
        grp_col = QGroupBox("衝突グループ重複チェック & グループ番号割り当て候補")
        grp_col.setStyleSheet("QGroupBox { font-weight: bold; color: #ffcc66; }")
        col_layout = QVBoxLayout(grp_col)

        h_col_tools = QHBoxLayout()
        unused_g = [str(g + 1) for g in self.collision_analysis.get("unused_master_groups", [])]
        lbl_unused = QLabel(f"マスター側の空き衝突グループ: {', '.join(unused_g) if unused_g else 'なし'}")
        lbl_unused.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        h_col_tools.addWidget(lbl_unused)
        h_col_tools.addStretch()

        btn_apply_suggested = QPushButton("重複グループを空きグループ候補へ一括設定")
        btn_apply_suggested.setFixedHeight(28)
        btn_apply_suggested.setStyleSheet(_create_button_style("#3d4f2f", "#4f663d", "#ddffbb", border_color="#65824e", font_size=11))
        btn_apply_suggested.clicked.connect(self._on_apply_suggested_groups)
        h_col_tools.addWidget(btn_apply_suggested)
        col_layout.addLayout(h_col_tools)

        self.table_groups = QTableWidget()
        self.table_groups.setColumnCount(5)
        self.table_groups.setHorizontalHeaderLabels([
            "移植元グループ", "移植剛体数", "マスター側同グループ剛体数", "空きグループ候補", "統合後の割り当てグループ"
        ])
        self.table_groups.setMaximumHeight(160)
        self.table_groups.verticalHeader().setVisible(False)
        self.table_groups.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_groups.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_groups.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_groups.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_groups.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table_groups.setStyleSheet(
            "QTableWidget { background-color: #1f1f1f; border: 1px solid #444; gridline-color: #333; }"
            "QHeaderView::section { background-color: #2e2e2e; color: #bbb; padding: 4px; border: 1px solid #3c3c3c; font-weight: bold; }"
        )
        col_layout.addWidget(self.table_groups)
        layout.addWidget(grp_col)

        # 移植剛体プレビューテーブル
        grp_rbs = QGroupBox("移植される剛体一覧 (番号振り直し & 追従先ボーン)")
        grp_rbs.setStyleSheet("QGroupBox { font-weight: bold; color: #52c5ff; }")
        rbs_layout = QVBoxLayout(grp_rbs)

        self.table_rbs = QTableWidget()
        self.table_rbs.setColumnCount(5)
        self.table_rbs.setHorizontalHeaderLabels(["旧rbIndex -> 新rbIndex", "剛体名", "物理モード", "旧グループ", "統合後の追従先ボーン"])
        self.table_rbs.verticalHeader().setVisible(False)
        self.table_rbs.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_rbs.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_rbs.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_rbs.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_rbs.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_rbs.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table_rbs.setStyleSheet(
            "QTableWidget { background-color: #1f1f1f; border: 1px solid #444; gridline-color: #333; }"
            "QHeaderView::section { background-color: #2e2e2e; color: #bbb; padding: 4px; border: 1px solid #3c3c3c; font-weight: bold; }"
        )
        rbs_layout.addWidget(self.table_rbs)
        layout.addWidget(grp_rbs, 1)

        h_btns = QHBoxLayout()
        h_btns.addStretch()

        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setFixedWidth(100)
        btn_cancel.setFixedHeight(34)
        btn_cancel.setStyleSheet(_create_button_style("#383838", "#484848", "#dddddd", border_color="#555555", font_size=12))
        btn_cancel.clicked.connect(self.reject)
        h_btns.addWidget(btn_cancel)

        btn_ok = QPushButton("この設定で物理統合を実行")
        btn_ok.setFixedWidth(210)
        btn_ok.setFixedHeight(34)
        btn_ok.setStyleSheet(_create_button_style("#185d8f", "#2176b5", "#ffffff", border_color="#2b94e3", font_size=12))
        btn_ok.clicked.connect(self._on_confirm)
        h_btns.addWidget(btn_ok)
        layout.addLayout(h_btns)

    def _populate_tables(self):
        """衝突グループ候補および剛体一覧テーブルを構築"""
        suggestions = self.collision_analysis.get("suggestions", [])
        self.table_groups.setRowCount(0)
        self._group_combos = []

        for row_idx, sug in enumerate(suggestions):
            self.table_groups.insertRow(row_idx)
            src_g = int(sug["source_group"])
            alt_g = int(sug["suggested_unused_group"])

            it_src = QTableWidgetItem(f"グループ {src_g + 1} (内部値 {src_g})")
            it_src.setTextAlignment(Qt.AlignCenter)
            self.table_groups.setItem(row_idx, 0, it_src)

            it_scnt = QTableWidgetItem(f"{sug['source_rb_count']} 個")
            it_scnt.setTextAlignment(Qt.AlignCenter)
            self.table_groups.setItem(row_idx, 1, it_scnt)

            mst_cnt = sug["master_rb_count_in_same_group"]
            it_mcnt = QTableWidgetItem(f"{mst_cnt} 個 {'(重複あり)' if mst_cnt > 0 else '(空き)'}")
            it_mcnt.setTextAlignment(Qt.AlignCenter)
            self.table_groups.setItem(row_idx, 2, it_mcnt)

            it_alt = QTableWidgetItem(f"グループ {alt_g + 1}" if alt_g != src_g else "変更不要")
            it_alt.setTextAlignment(Qt.AlignCenter)
            self.table_groups.setItem(row_idx, 3, it_alt)

            cbb_g = QComboBox()
            for g_i in range(16):
                label = f"グループ {g_i + 1} (内部値 {g_i})"
                if g_i == src_g:
                    label += " [元の設定]"
                elif g_i == alt_g:
                    label += " [空き候補]"
                cbb_g.addItem(label, g_i)
            cbb_g.setCurrentIndex(src_g)
            self.table_groups.setCellWidget(row_idx, 4, cbb_g)
            self._group_combos.append((src_g, alt_g, cbb_g))

        rbs = self.physics_plan.get("transplanted_rbs", [])
        base_idx = self.physics_plan.get("master_existing_rb_count", 0)
        mode_names = {0: "0: ボーン追従", 1: "1: 物理演算", 2: "2: 物理+ボーン位置合わせ"}

        self.table_rbs.setRowCount(0)
        for offset, rb in enumerate(rbs):
            self.table_rbs.insertRow(offset)
            old_i = rb["index"]
            new_i = base_idx + offset

            it_idx = QTableWidgetItem(f"{old_i}  ->  {new_i}")
            it_idx.setTextAlignment(Qt.AlignCenter)
            self.table_rbs.setItem(offset, 0, it_idx)

            self.table_rbs.setItem(offset, 1, QTableWidgetItem(rb.get("name_jp", "")))
            self.table_rbs.setItem(offset, 2, QTableWidgetItem(mode_names.get(rb.get("physics_mode", 0), "")))

            it_grp = QTableWidgetItem(f"グループ {int(rb.get('group', 0)) + 1}")
            it_grp.setTextAlignment(Qt.AlignCenter)
            self.table_rbs.setItem(offset, 3, it_grp)

            t_bone = rb.get("resolved_master_bone") or rb.get("target_bone") or ""
            self.table_rbs.setItem(offset, 4, QTableWidgetItem(t_bone.split("|")[-1]))

    def _on_apply_suggested_groups(self):
        """重複している衝突グループを空きグループ候補へ一括切り替え"""
        for _, alt_g, cbb in self._group_combos:
            idx = cbb.findData(alt_g)
            if idx >= 0:
                cbb.setCurrentIndex(idx)

    def _on_confirm(self):
        """選択された衝突グループ対応表を保存して確定"""
        self.group_remap = {}
        for src_g, _, cbb in self._group_combos:
            self.group_remap[src_g] = int(cbb.currentData())
        self.is_confirmed = True
        self.accept()


class ValidationReportDialog(QDialog):
    """
    書き出し前6項目最終チェックの結果表示・該当箇所選択ダイアログ (Step 7)
    未ウェイト頂点・インフルエンス上限(BDEF4)・名前重複・物理整合性・モーフ残存・首境界隙間を表示し、
    問題箇所のビューポート選択やインフルエンス4以下への自動整理を行えます。
    """

    def __init__(self, report, head_model=None, body_model=None, master_model=None, seam_threshold=0.5, check_neck_seam=True, parent=None):
        super(ValidationReportDialog, self).__init__(parent)
        self.setWindowTitle("書き出し前最終チェック結果 (Step 7 - 6項目診断)")
        self.resize(820, 460)
        self.setMinimumSize(640, 380)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        self.report = report or {}
        self.head_model = head_model
        self.body_model = body_model
        self.master_model = master_model
        self.seam_threshold = seam_threshold
        self.check_neck_seam = check_neck_seam

        self._init_ui()
        self._populate_report(self.report)

    def _init_ui(self):
        """ダイアログレイアウトの初期化"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        self.lbl_summary = QLabel()
        self.lbl_summary.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(self.lbl_summary)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["チェック項目", "判定", "診断内容", "該当箇所"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #1f1f1f; border: 1px solid #444; gridline-color: #333; }"
            "QHeaderView::section { background-color: #2e2e2e; color: #bbb; padding: 4px; border: 1px solid #3c3c3c; font-weight: bold; }"
        )
        layout.addWidget(self.table, 1)

        h_btns = QHBoxLayout()

        self.btn_clamp_bdef4 = QPushButton("インフルエンス4以下へ自動整理 (BDEF4)")
        self.btn_clamp_bdef4.setFixedHeight(32)
        self.btn_clamp_bdef4.setStyleSheet(
            _create_button_style("#3d4f2f", "#4f663d", "#ddffbb", border_color="#65824e", font_size=11)
        )
        self.btn_clamp_bdef4.clicked.connect(self._on_clamp_bdef4)
        h_btns.addWidget(self.btn_clamp_bdef4)

        self.btn_rerun = QPushButton("再診断")
        self.btn_rerun.setFixedWidth(90)
        self.btn_rerun.setFixedHeight(32)
        self.btn_rerun.setStyleSheet(
            _create_button_style("#264b6e", "#33618d", "#ffffff", border_color="#3d72a4", font_size=12)
        )
        self.btn_rerun.clicked.connect(self._on_rerun_validation)
        h_btns.addWidget(self.btn_rerun)

        h_btns.addStretch()

        btn_close = QPushButton("閉じる")
        btn_close.setFixedWidth(96)
        btn_close.setFixedHeight(32)
        btn_close.setStyleSheet(
            _create_button_style("#383838", "#484848", "#dddddd", border_color="#555555", font_size=12)
        )
        btn_close.clicked.connect(self.accept)
        h_btns.addWidget(btn_close)
        layout.addLayout(h_btns)

    def _populate_report(self, report):
        """診断レポートをテーブルへ反映"""
        self.report = report or {}
        overall = self.report.get("overall_status", "ok")
        ok_c = self.report.get("ok_count", 0)
        warn_c = self.report.get("warning_count", 0)
        err_c = self.report.get("error_count", 0)

        if overall == "error":
            self.lbl_summary.setText(f"総合判定: 要修正 (エラー: {err_c} 件 / 注意: {warn_c} 件 / OK: {ok_c} 件)")
            self.lbl_summary.setStyleSheet("color: #ff6666; font-size: 13px; font-weight: bold;")
        elif overall == "warning":
            self.lbl_summary.setText(f"総合判定: 注意あり (エラー: 0 件 / 注意: {warn_c} 件 / OK: {ok_c} 件)")
            self.lbl_summary.setStyleSheet("color: #ffcc66; font-size: 13px; font-weight: bold;")
        else:
            self.lbl_summary.setText(f"総合判定: 問題なし (全 {ok_c} 項目クリア - PMX書き出し可能です)")
            self.lbl_summary.setStyleSheet("color: #77ff77; font-size: 13px; font-weight: bold;")

        checks = self.report.get("checks", [])
        self.table.setRowCount(0)
        status_map = {
            "ok": ("OK", "#77ff77"),
            "warning": ("注意", "#ffcc66"),
            "error": ("エラー", "#ff6666"),
        }

        has_over4 = False
        for row_idx, chk in enumerate(checks):
            self.table.insertRow(row_idx)
            self.table.setRowHeight(row_idx, 34)

            if chk.get("id") == "max_4_influences" and chk.get("count", 0) > 0:
                has_over4 = True

            self.table.setItem(row_idx, 0, QTableWidgetItem(chk.get("title", "")))

            st_text, st_color = status_map.get(chk.get("status", "ok"), ("OK", "#77ff77"))
            it_st = QTableWidgetItem(st_text)
            it_st.setTextAlignment(Qt.AlignCenter)
            it_st.setForeground(QtGui.QColor(st_color))
            self.table.setItem(row_idx, 1, it_st)

            self.table.setItem(row_idx, 2, QTableWidgetItem(chk.get("detail", "")))

            targets = chk.get("select_targets", [])
            if targets:
                btn_sel = QPushButton("選択")
                btn_sel.setFixedWidth(68)
                btn_sel.setFixedHeight(26)
                btn_sel.setStyleSheet(
                    _create_button_style("#384a5e", "#4b637d", "#ffffff", border_color="#5d7999", font_size=11, padding="2px 6px")
                )
                btn_sel.clicked.connect(lambda checked=False, t=list(targets): self._select_targets(t))
                self.table.setCellWidget(row_idx, 3, btn_sel)
            else:
                it_none = QTableWidgetItem("-")
                it_none.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, 3, it_none)

        self.btn_clamp_bdef4.setEnabled(has_over4 and bool(self.head_model or self.body_model))

    def _select_targets(self, targets):
        """該当頂点またはノードをビューポート上で選択"""
        valid = [t for t in targets if mc.objExists(t)]
        if valid:
            mc.select(valid, replace=True)
            mc.inViewMessage(amg=f"<hl>該当箇所 ({len(valid)} 件) をビューポートで選択しました</hl>", pos="topCenter", fade=True)
        else:
            QMessageBox.information(self, "案内", "選択可能な対象ノードが見つかりませんでした。")

    def _on_clamp_bdef4(self):
        """対象モデルの1頂点あたりインフルエンス数を4以下へ自動正規化し再診断"""
        fixed = 0
        with model_modifier.undo_chunk("MMD_UI_ClampBDEF4"):
            for m in (self.head_model, self.body_model):
                if m and mc.objExists(m):
                    fixed += model_modifier.clamp_max_4_influences(m)
        mc.inViewMessage(amg=f"<hl>{fixed} 頂点のインフルエンスを4ボーン以下へ整理しました</hl>", pos="topCenter", fade=True)
        self._on_rerun_validation()

    def _on_rerun_validation(self):
        """現在のシーン状態に対して6項目診断を再実行"""
        new_report = model_modifier.validate_dressup_models(
            head_model=self.head_model,
            body_model=self.body_model,
            master_model=self.master_model,
            seam_threshold=self.seam_threshold,
            check_neck_seam=self.check_neck_seam,
        )
        self._populate_report(new_report)


class ModificationEditorTabWidget(QWidget):
    """
    MMD Model Editor 改造・お着替えタブウィジェット
    直感的なステップ進行形式でモデルの改造やパーツ付け替えを支援します。
    """

    def __init__(self, parent=None):
        super(ModificationEditorTabWidget, self).__init__(parent)
        self.parent_window = parent
        self.agreed_pairs = set()
        self.is_terms_agreed = False
        self.material_filter_dialog = None
        self.step_completed = {i: False for i in range(1, 8)}
        self.step_badges = {}
        self._bone_vis_mode = "both"

        self._init_ui()
        self._refresh_model_combos()

    def _init_ui(self):
        """ユーザーインターフェースレイアウトの構築"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 上部ウィザード進捗バー (Step 1〜7)
        wizard_frame = QFrame()
        wizard_frame.setStyleSheet("background-color: #20242a; border: 1px solid #3c4652; border-radius: 5px;")
        wizard_layout = QVBoxLayout(wizard_frame)
        wizard_layout.setContentsMargins(8, 6, 8, 6)
        wizard_layout.setSpacing(4)

        h_badges = QHBoxLayout()
        h_badges.setSpacing(4)
        step_titles = [
            (1, "Step1:規約"),
            (2, "Step2:位置"),
            (3, "Step3:分割"),
            (4, "Step4:首"),
            (5, "Step5:ボーン"),
            (6, "Step6:物理"),
            (7, "Step7:診断"),
        ]
        for s_num, s_text in step_titles:
            lbl_b = QLabel(s_text)
            lbl_b.setAlignment(Qt.AlignCenter)
            lbl_b.setStyleSheet(
                "background-color: #2c3038; color: #9aa5b1; border: 1px solid #444b54; "
                "border-radius: 3px; padding: 2px 4px; font-size: 10px; font-weight: bold;"
            )
            h_badges.addWidget(lbl_b, 1)
            self.step_badges[s_num] = lbl_b
        wizard_layout.addLayout(h_badges)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 7)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setFormat("お着替え進行度: %v / 7 ステップ完了")
        self.progress_bar.setStyleSheet(
            "QProgressBar { background-color: #191c20; color: #d8e6f3; border: 1px solid #3b444f; border-radius: 3px; text-align: center; font-size: 10px; }"
            "QProgressBar::chunk { background-color: #24784d; border-radius: 2px; }"
        )
        wizard_layout.addWidget(self.progress_bar)
        main_layout.addWidget(wizard_frame)

        # ビューポートのボーン表示切替バー（キャラ単体 / 両方同時 / 非表示）
        bone_vis_frame = QFrame()
        bone_vis_frame.setStyleSheet("background-color: #22262d; border: 1px solid #3a4450; border-radius: 5px;")
        h_bvis = QHBoxLayout(bone_vis_frame)
        h_bvis.setContentsMargins(8, 4, 8, 4)
        h_bvis.setSpacing(5)

        lbl_bvis = QLabel("ボーン表示:")
        lbl_bvis.setStyleSheet("color: #88ddff; font-weight: bold; font-size: 11px;")
        h_bvis.addWidget(lbl_bvis)

        self.btn_bone_vis_both = QPushButton("両方表示")
        self.btn_bone_vis_both.setFixedHeight(26)
        self.btn_bone_vis_both.setStyleSheet(
            _create_button_style("#1f5e3b", "#297a4d", "#ffffff", border_color="#369e63", font_size=11, padding="2px 6px")
        )
        self.btn_bone_vis_both.clicked.connect(lambda: self._on_set_bone_visibility("both"))
        h_bvis.addWidget(self.btn_bone_vis_both)

        self.btn_bone_vis_a = QPushButton("移植元(A)のみ")
        self.btn_bone_vis_a.setFixedHeight(26)
        self.btn_bone_vis_a.setStyleSheet(
            _create_button_style("#1e5670", "#286e8f", "#d8f4ff", border_color="#368bb4", font_size=11, padding="2px 6px")
        )
        self.btn_bone_vis_a.clicked.connect(lambda: self._on_set_bone_visibility("model_a"))
        h_bvis.addWidget(self.btn_bone_vis_a)

        self.btn_bone_vis_b = QPushButton("ベース(B)のみ")
        self.btn_bone_vis_b.setFixedHeight(26)
        self.btn_bone_vis_b.setStyleSheet(
            _create_button_style("#6e471b", "#8c5a22", "#ffe8cc", border_color="#aa6e29", font_size=11, padding="2px 6px")
        )
        self.btn_bone_vis_b.clicked.connect(lambda: self._on_set_bone_visibility("model_b"))
        h_bvis.addWidget(self.btn_bone_vis_b)

        self.btn_bone_vis_none = QPushButton("非表示")
        self.btn_bone_vis_none.setFixedHeight(26)
        self.btn_bone_vis_none.setStyleSheet(
            _create_button_style("#3a3a3a", "#4e4e4e", "#dddddd", border_color="#5c5c5c", font_size=11, padding="2px 6px")
        )
        self.btn_bone_vis_none.clicked.connect(lambda: self._on_set_bone_visibility("none"))
        h_bvis.addWidget(self.btn_bone_vis_none)

        self.chk_bone_colorize = QCheckBox("色分け")
        self.chk_bone_colorize.setChecked(True)
        self.chk_bone_colorize.setStyleSheet("color: #cccccc; font-size: 11px;")
        self.chk_bone_colorize.toggled.connect(lambda: self._on_set_bone_visibility(self._bone_vis_mode))
        h_bvis.addWidget(self.chk_bone_colorize)
        h_bvis.addStretch()
        main_layout.addWidget(bone_vis_frame)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        # -------------------------------------------------------------
        # Step 1: モデル選択および利用規約確認セクション
        # -------------------------------------------------------------
        grp_step1 = QGroupBox("【Step 1: モデル選択 & 利用規約確認】")
        grp_step1.setStyleSheet("QGroupBox { font-weight: bold; color: #52b7ff; }")
        layout_step1 = QVBoxLayout(grp_step1)
        layout_step1.setSpacing(8)

        # 移植元モデル選択（付けたいパーツ側）
        h_base = QHBoxLayout()
        h_base.addWidget(QLabel("移植元モデル (付けたいパーツ側: 頭・羽・帽子・小物等):"))
        self.cbb_base_model = QComboBox()
        self.cbb_base_model.currentIndexChanged.connect(self._on_model_selection_changed)
        h_base.addWidget(self.cbb_base_model, 1)
        layout_step1.addLayout(h_base)

        # ベースモデル選択（本体・衣装側）
        h_outfit = QHBoxLayout()
        h_outfit.addWidget(QLabel("ベースモデル (本体・衣装側):"))
        self.cbb_outfit_model = QComboBox()
        self.cbb_outfit_model.currentIndexChanged.connect(self._on_model_selection_changed)
        h_outfit.addWidget(self.cbb_outfit_model, 1)
        layout_step1.addLayout(h_outfit)

        # マスター骨格（残すスケルトン）選択
        h_master = QHBoxLayout()
        h_master.addWidget(QLabel("マスター骨格 (残す骨組み):"))
        self.cbb_master_skeleton = QComboBox()
        self.cbb_master_skeleton.addItem("ベースモデル (本体・衣装側) をマスター骨格にする [推奨]", "outfit")
        self.cbb_master_skeleton.addItem("移植元モデル (パーツ側) をマスター骨格にする", "base")
        h_master.addWidget(self.cbb_master_skeleton, 1)
        layout_step1.addLayout(h_master)

        # モデル再検出ボタンおよび標準ボーン充足チェック表示
        h_tools = QHBoxLayout()
        self.btn_refresh_models = QPushButton("シーン内モデル一覧を再取得")
        self.btn_refresh_models.setFixedHeight(32)
        self.btn_refresh_models.setStyleSheet(
            _create_button_style("#383838", "#484848", "#e0e0e0", border_color="#555555", font_size=12, padding="3px 8px")
        )
        self.btn_refresh_models.clicked.connect(self._refresh_model_combos)
        h_tools.addWidget(self.btn_refresh_models)
        layout_step1.addLayout(h_tools)

        self.lbl_bone_check = QLabel("標準ボーン診断: モデルを選択してください")
        self.lbl_bone_check.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        layout_step1.addWidget(self.lbl_bone_check)

        # 利用規約確認ボタンおよび状態インジケーター
        h_terms = QHBoxLayout()
        self.btn_check_terms = QPushButton("各モデルの利用規約を確認・同意する")
        self.btn_check_terms.setFixedHeight(34)
        self.btn_check_terms.setStyleSheet(
            _create_button_style("#7a4f15", "#9e651b", "#ffffff", border_color="#aa6d1d", border_hover="#ffaa44", font_size=13, padding="4px 10px")
        )
        self.btn_check_terms.clicked.connect(self._open_terms_dialog)
        h_terms.addWidget(self.btn_check_terms, 2)

        self.lbl_terms_status = QLabel("【未確認 - 操作ロック中】")
        self.lbl_terms_status.setStyleSheet("color: #ff6666; font-weight: bold; font-size: 12px;")
        h_terms.addWidget(self.lbl_terms_status, 1)

        self.btn_toggle_lock = QPushButton("ロック切替")
        self.btn_toggle_lock.setFixedWidth(95)
        self.btn_toggle_lock.setFixedHeight(34)
        self.btn_toggle_lock.setStyleSheet(
            _create_button_style("#424242", "#555555", "#dddddd", border_color="#5c5c5c", font_size=12, padding="3px 6px")
        )
        self.btn_toggle_lock.setToolTip("同意状態の手動切替（確認済みロック解除）")
        self.btn_toggle_lock.clicked.connect(self._toggle_lock_state)
        h_terms.addWidget(self.btn_toggle_lock)
        layout_step1.addLayout(h_terms)

        layout.addWidget(grp_step1)

        # -------------------------------------------------------------
        # Step 2: 位置合わせおよびスケール調整セクション (基準ボーン選択対応)
        # -------------------------------------------------------------
        self.grp_step2 = QGroupBox("【Step 2: 位置合わせ & スケール調整 (首・上半身2・頭など基準ボーン選択)】")
        self.grp_step2.setStyleSheet("QGroupBox { font-weight: bold; color: #aaffaa; }")
        layout_step2 = QVBoxLayout(self.grp_step2)
        layout_step2.setSpacing(6)

        h_align_mode = QHBoxLayout()
        h_align_mode.addWidget(QLabel("移動・調整対象:"))
        self.cbb_align_target = QComboBox()
        self.cbb_align_target.addItem("移植元モデル (パーツ側) をベースモデルへ合わせる [推奨]", "base_to_outfit")
        self.cbb_align_target.addItem("ベースモデル (本体側) を移植元モデルへ合わせる", "outfit_to_base")
        h_align_mode.addWidget(self.cbb_align_target, 1)
        layout_step2.addLayout(h_align_mode)

        h_anchor = QHBoxLayout()
        h_anchor.addWidget(QLabel("位置合わせ基準ボーン:"))
        self.cbb_anchor_bone = QComboBox()
        self.cbb_anchor_bone.addItem("上半身2 (羽・背中小物・上着向け)", "上半身2")
        self.cbb_anchor_bone.addItem("首 (頭の挿げ替え向け)", "首")
        self.cbb_anchor_bone.addItem("頭 (帽子・髪飾り向け)", "頭")
        self.cbb_anchor_bone.addItem("上半身 (マント・衣装向け)", "上半身")
        self.cbb_anchor_bone.addItem("下半身 (尻尾・スカート向け)", "下半身")
        self.cbb_anchor_bone.addItem("センター (全身位置合わせ)", "センター")
        h_anchor.addWidget(self.cbb_anchor_bone, 1)

        self.chk_auto_scale = QCheckBox("スケールも自動推定する")
        self.chk_auto_scale.setChecked(True)
        self.chk_auto_scale.setToolTip("オフにするとスケールは1.0のまま維持し、基準ボーンの位置だけを重ねます（羽や帽子の移植に便利）。")
        self.chk_auto_scale.setStyleSheet("color: #cccccc; font-size: 11px;")
        h_anchor.addWidget(self.chk_auto_scale)
        layout_step2.addLayout(h_anchor)

        h_auto_align = QHBoxLayout()
        self.btn_auto_estimate_align = QPushButton("基準ボーンで位置・スケール推定 & プレビュー")
        self.btn_auto_estimate_align.setFixedHeight(34)
        self.btn_auto_estimate_align.setStyleSheet(
            _create_button_style("#1f5e3b", "#297a4d", "#ffffff", border_color="#369e63", border_hover="#66ffaa", font_size=12, padding="4px 10px")
        )
        self.btn_auto_estimate_align.clicked.connect(self._on_auto_estimate_alignment)
        h_auto_align.addWidget(self.btn_auto_estimate_align, 2)

        self.btn_preview_align = QPushButton("数値でプレビュー")
        self.btn_preview_align.setFixedHeight(34)
        self.btn_preview_align.setStyleSheet(
            _create_button_style("#2d4f63", "#3a6680", "#d8f0ff", border_color="#4a80a0", font_size=12, padding="4px 8px")
        )
        self.btn_preview_align.clicked.connect(self._on_preview_alignment)
        h_auto_align.addWidget(self.btn_preview_align, 1)

        self.btn_reset_align_preview = QPushButton("元に戻す")
        self.btn_reset_align_preview.setFixedHeight(34)
        self.btn_reset_align_preview.setStyleSheet(
            _create_button_style("#4a3a2a", "#634d38", "#ffddbb", border_color="#7c6046", font_size=12, padding="4px 8px")
        )
        self.btn_reset_align_preview.clicked.connect(self._on_reset_alignment_preview)
        h_auto_align.addWidget(self.btn_reset_align_preview, 1)
        layout_step2.addLayout(h_auto_align)

        h_scale = QHBoxLayout()
        h_scale.addWidget(QLabel("微調整 - スケール倍率:"))
        self.spn_scale = QDoubleSpinBox()
        self.spn_scale.setDecimals(4)
        self.spn_scale.setRange(0.1, 5.0)
        self.spn_scale.setSingleStep(0.01)
        self.spn_scale.setValue(1.0)
        h_scale.addWidget(self.spn_scale)

        h_scale.addWidget(QLabel("左右オフセット (X):"))
        self.spn_offset_x = QDoubleSpinBox()
        self.spn_offset_x.setDecimals(3)
        self.spn_offset_x.setRange(-200.0, 200.0)
        self.spn_offset_x.setSingleStep(0.05)
        self.spn_offset_x.setValue(0.0)
        h_scale.addWidget(self.spn_offset_x)
        layout_step2.addLayout(h_scale)

        h_offset = QHBoxLayout()
        h_offset.addWidget(QLabel("高さオフセット (Y):"))
        self.spn_offset_y = QDoubleSpinBox()
        self.spn_offset_y.setDecimals(3)
        self.spn_offset_y.setRange(-200.0, 200.0)
        self.spn_offset_y.setSingleStep(0.05)
        self.spn_offset_y.setValue(0.0)
        h_offset.addWidget(self.spn_offset_y)

        h_offset.addWidget(QLabel("前後オフセット (Z):"))
        self.spn_offset_z = QDoubleSpinBox()
        self.spn_offset_z.setDecimals(3)
        self.spn_offset_z.setRange(-200.0, 200.0)
        self.spn_offset_z.setSingleStep(0.05)
        self.spn_offset_z.setValue(0.0)
        h_offset.addWidget(self.spn_offset_z)
        layout_step2.addLayout(h_offset)

        self.btn_apply_transform = QPushButton("位置・スケールを確定 (バインドポーズ再設定)")
        self.btn_apply_transform.setFixedHeight(34)
        self.btn_apply_transform.setStyleSheet(
            _create_button_style("#264b6e", "#33618d", "#ffffff", border_color="#3d72a4", font_size=12, padding="4px 8px")
        )
        self.btn_apply_transform.clicked.connect(self._on_apply_transform)
        layout_step2.addWidget(self.btn_apply_transform)

        layout.addWidget(self.grp_step2)

        # -------------------------------------------------------------
        # Step 3: 削除ウィンドウ（絞り込み機能）によるパーツ切り出し・不要要素整理
        # -------------------------------------------------------------
        self.grp_step3 = QGroupBox("【Step 3: パーツ絞り込み表示 & 削除ウィンドウ (頭・羽・帽子・衣装パーツ対応)】")
        self.grp_step3.setStyleSheet("QGroupBox { font-weight: bold; color: #ffaa55; }")
        layout_step3 = QVBoxLayout(self.grp_step3)
        layout_step3.setSpacing(8)

        lbl_step3_guide = QLabel(
            "絞り込み表示（マスキング）で残したいパーツ（頭・羽・帽子・リボン・服など）を確認しながら、不要な材質やボーンを削除します。"
        )
        lbl_step3_guide.setWordWrap(True)
        lbl_step3_guide.setStyleSheet("color: #cccccc; font-size: 11px;")
        layout_step3.addWidget(lbl_step3_guide)

        # 材質別マスキング・削除ダイアログ起動ボタン
        self.btn_open_mat_filter = QPushButton("材質別マスキング表示・パーツ削除ウィンドウを開く (絞り込み削除)...")
        self.btn_open_mat_filter.setFixedHeight(36)
        self.btn_open_mat_filter.setStyleSheet(
            _create_button_style("#1e5670", "#286e8f", "#ffffff", border_color="#368bb4", border_hover="#52c5ff", font_size=13, padding="4px 12px")
        )
        self.btn_open_mat_filter.setToolTip("材質一覧の表示チェック（絞り込み表示）を使って、頭・羽・帽子・服など残したいパーツ以外を安全に削除します。")
        self.btn_open_mat_filter.clicked.connect(self._open_material_filter_dialog)
        layout_step3.addWidget(self.btn_open_mat_filter)

        # ボーン・剛体絞り込み削除ダイアログ起動ボタン（キャラ別 / 両方表示対応）
        self.btn_open_bone_phys_filter = QPushButton("ボーン・剛体（物理）絞り込み・削除ウィンドウを開く (キャラ別 / 両方表示)...")
        self.btn_open_bone_phys_filter.setFixedHeight(36)
        self.btn_open_bone_phys_filter.setStyleSheet(
            _create_button_style("#4c3b6e", "#624c8e", "#ffffff", border_color="#7b5eb3", border_hover="#b89cff", font_size=13, padding="4px 12px")
        )
        self.btn_open_bone_phys_filter.setToolTip("キャラ単体または両方同時のボーン・剛体一覧を絞り込み表示し、不要なボーン・剛体を安全に削除します。")
        self.btn_open_bone_phys_filter.clicked.connect(self._open_bone_physics_dialog)
        layout_step3.addWidget(self.btn_open_bone_phys_filter)

        # 手動補助ボタン
        lbl_step3_hint = QLabel("ビューポート上で直接選択したポリゴン面の削除や単独表示切り替えも行えます。")
        lbl_step3_hint.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        layout_step3.addWidget(lbl_step3_hint)

        h_mesh_actions = QHBoxLayout()
        self.btn_delete_faces = QPushButton("選択したポリゴン面を削除")
        self.btn_delete_faces.setFixedHeight(32)
        self.btn_delete_faces.setStyleSheet(
            _create_button_style("#6e2b2b", "#8b3737", "#ffffff", border_color="#9e3e3e", border_hover="#ff6b6b", font_size=12, padding="3px 8px")
        )
        self.btn_delete_faces.clicked.connect(self._on_delete_selected_faces)
        h_mesh_actions.addWidget(self.btn_delete_faces)

        self.btn_toggle_isolate = QPushButton("選択オブジェクトの単独表示切替 (Isolate)")
        self.btn_toggle_isolate.setFixedHeight(32)
        self.btn_toggle_isolate.setStyleSheet(
            _create_button_style("#383838", "#4a4a4a", "#ffffff", border_color="#555555", border_hover="#52b7ff", font_size=12, padding="3px 8px")
        )
        self.btn_toggle_isolate.clicked.connect(self._on_toggle_isolate)
        h_mesh_actions.addWidget(self.btn_toggle_isolate)
        layout_step3.addLayout(h_mesh_actions)

        layout.addWidget(self.grp_step3)

        # -------------------------------------------------------------
        # Step 4: 首の継ぎ目処理セクション (頭挿げ替え時のみ・羽や小物はスキップ可)
        # -------------------------------------------------------------
        self.grp_step4 = QGroupBox("【Step 4: 首の継ぎ目処理 (頭挿げ替え時のみ / 羽・帽子・小物はスキップ可)】")
        self.grp_step4.setStyleSheet("QGroupBox { font-weight: bold; color: #55ffff; }")
        layout_step4 = QVBoxLayout(self.grp_step4)
        layout_step4.setSpacing(6)

        lbl_step4_hint = QLabel(
            "頭と体を繋ぐ場合のみ実行します（メッシュ非結合のまま境界の位置・法線・ウェイトを一致）。羽・帽子・小物等の移植時はスキップしてStep 5へ進んでください。"
        )
        lbl_step4_hint.setWordWrap(True)
        lbl_step4_hint.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        layout_step4.addWidget(lbl_step4_hint)

        h_merge = QHBoxLayout()
        h_merge.addWidget(QLabel("首境界の対応距離閾値:"))
        self.spn_merge_dist = QDoubleSpinBox()
        self.spn_merge_dist.setRange(0.001, 10.0)
        self.spn_merge_dist.setSingleStep(0.05)
        self.spn_merge_dist.setValue(0.50)
        h_merge.addWidget(self.spn_merge_dist)

        self.btn_preview_neck_seam = QPushButton("首境界の対応ペアを検出 & プレビュー")
        self.btn_preview_neck_seam.setFixedHeight(32)
        self.btn_preview_neck_seam.setStyleSheet(
            _create_button_style("#264b6e", "#33618d", "#ffffff", border_color="#3d72a4", font_size=12, padding="3px 8px")
        )
        self.btn_preview_neck_seam.clicked.connect(self._on_preview_neck_seam)
        h_merge.addWidget(self.btn_preview_neck_seam, 1)
        layout_step4.addLayout(h_merge)

        h_neck_opts = QHBoxLayout()
        self.chk_neck_snap = QCheckBox("境界位置スナップ")
        self.chk_neck_snap.setChecked(True)
        self.chk_neck_snap.setStyleSheet("color: #cccccc; font-size: 11px;")
        h_neck_opts.addWidget(self.chk_neck_snap)

        self.chk_neck_normals = QCheckBox("境界法線コピー (影消去)")
        self.chk_neck_normals.setChecked(True)
        self.chk_neck_normals.setStyleSheet("color: #cccccc; font-size: 11px;")
        h_neck_opts.addWidget(self.chk_neck_normals)

        self.chk_neck_weights = QCheckBox("境界ウェイトコピー (割れ防止)")
        self.chk_neck_weights.setChecked(True)
        self.chk_neck_weights.setStyleSheet("color: #cccccc; font-size: 11px;")
        h_neck_opts.addWidget(self.chk_neck_weights)
        layout_step4.addLayout(h_neck_opts)

        self.btn_merge_neck = QPushButton("首の継ぎ目を一括処理 (スナップ・法線・ウェイト)")
        self.btn_merge_neck.setFixedHeight(34)
        self.btn_merge_neck.setStyleSheet(
            _create_button_style("#205050", "#2b6b6b", "#ffffff", border_color="#3b8888", border_hover="#55ffff", font_size=12, padding="4px 10px")
        )
        self.btn_merge_neck.clicked.connect(self._on_merge_neck_vertices)
        layout_step4.addWidget(self.btn_merge_neck)

        h_neck_test = QHBoxLayout()
        self.btn_smooth_normals = QPushButton("首境界の法線のみ再補正")
        self.btn_smooth_normals.setFixedHeight(32)
        self.btn_smooth_normals.setStyleSheet(
            _create_button_style("#1b4d5a", "#246475", "#ffffff", border_color="#318196", border_hover="#52d2f2", font_size=11, padding="3px 8px")
        )
        self.btn_smooth_normals.setToolTip("首境界周辺の頂点法線のみを滑らかに補正します。")
        self.btn_smooth_normals.clicked.connect(self._on_smooth_neck_normals)
        h_neck_test.addWidget(self.btn_smooth_normals, 1)

        self.btn_test_neck_bend = QPushButton("首を曲げて確認 (±30〜45度)")
        self.btn_test_neck_bend.setFixedHeight(32)
        self.btn_test_neck_bend.setStyleSheet(
            _create_button_style("#4a3b6e", "#604d8f", "#ffffff", border_color="#7860b3", border_hover="#b89cff", font_size=11, padding="3px 8px")
        )
        self.btn_test_neck_bend.setToolTip("首ボーンを一時的に回転させ、継ぎ目の割れがないか確認します。")
        self.btn_test_neck_bend.clicked.connect(self._on_test_neck_bend)
        h_neck_test.addWidget(self.btn_test_neck_bend, 1)

        self.btn_reset_neck_bend = QPushButton("首の角度を戻す")
        self.btn_reset_neck_bend.setFixedHeight(32)
        self.btn_reset_neck_bend.setStyleSheet(
            _create_button_style("#4a3a2a", "#634d38", "#ffddbb", border_color="#7c6046", font_size=11, padding="3px 8px")
        )
        self.btn_reset_neck_bend.clicked.connect(self._on_reset_neck_bend)
        h_neck_test.addWidget(self.btn_reset_neck_bend)
        layout_step4.addLayout(h_neck_test)

        layout.addWidget(self.grp_step4)

        # -------------------------------------------------------------
        # スキンウェイト管理セクション (一時保存 & 綺麗再バインド)
        # -------------------------------------------------------------
        self.grp_weights = QGroupBox("【スキンウェイト管理 (一時保存 & 綺麗再バインド)】")
        self.grp_weights.setStyleSheet("QGroupBox { font-weight: bold; color: #ffcc55; }")
        layout_weights = QVBoxLayout(self.grp_weights)
        layout_weights.setSpacing(6)

        lbl_weight_hint = QLabel(
            "改造前に現在のウェイトを保存し、加工後（首結合や不要面削除後）に素体ボーンへ綺麗に再バインドスキンします。"
        )
        lbl_weight_hint.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        layout_weights.addWidget(lbl_weight_hint)

        h_w_btns = QHBoxLayout()
        self.btn_cache_weights = QPushButton("現在のスキンウェイトを一時保存 (Cache)")
        self.btn_cache_weights.setFixedHeight(34)
        self.btn_cache_weights.setStyleSheet(
            _create_button_style("#4d4d24", "#63632e", "#ffffbb", border_color="#7a7a38", border_hover="#ffff55", font_size=12, padding="4px 10px")
        )
        self.btn_cache_weights.clicked.connect(self._on_cache_skin_weights)
        h_w_btns.addWidget(self.btn_cache_weights)

        self.btn_rebind_weights = QPushButton("素体ボーンへ綺麗に再バインド (Transfer)")
        self.btn_rebind_weights.setFixedHeight(34)
        self.btn_rebind_weights.setStyleSheet(
            _create_button_style("#224d4d", "#2d6363", "#aaffff", border_color="#3a7c7c", border_hover="#55ffff", font_size=12, padding="4px 10px")
        )
        self.btn_rebind_weights.clicked.connect(self._on_rebind_skin_weights)
        h_w_btns.addWidget(self.btn_rebind_weights)

        self.btn_clear_weights = QPushButton("破棄")
        self.btn_clear_weights.setFixedWidth(64)
        self.btn_clear_weights.setFixedHeight(34)
        self.btn_clear_weights.setStyleSheet(
            _create_button_style("#3e2b2b", "#573a3a", "#ffcccc", border_color="#6e4848", border_hover="#ff7777", font_size=12, padding="4px 6px")
        )
        self.btn_clear_weights.setToolTip("シーン内に保存されているウェイトキャッシュを破棄します。")
        self.btn_clear_weights.clicked.connect(self._on_clear_skin_weights)
        h_w_btns.addWidget(self.btn_clear_weights)
        layout_weights.addLayout(h_w_btns)

        self.lbl_weight_status = QLabel("【ウェイトキャッシュ: 未保存】")
        self.lbl_weight_status.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        layout_weights.addWidget(self.lbl_weight_status)

        layout.addWidget(self.grp_weights)

        # -------------------------------------------------------------
        # Step 5: ボーン統合セクション (名前対応表でウェイト付け替え & 固有ボーン移植)
        # -------------------------------------------------------------
        self.grp_step5 = QGroupBox("【Step 5: ボーン統合 (名前対応表でウェイト付替 & 固有ボーン移植)】")
        self.grp_step5.setStyleSheet("QGroupBox { font-weight: bold; color: #dd88ff; }")
        layout_step5 = QVBoxLayout(self.grp_step5)
        layout_step5.setSpacing(8)

        h_bone_merge = QHBoxLayout()
        self.btn_open_bone_merge_map = QPushButton("ボーン対応表を確認・編集して統合...")
        self.btn_open_bone_merge_map.setFixedHeight(34)
        self.btn_open_bone_merge_map.setStyleSheet(
            _create_button_style("#3d355e", "#50467a", "#ffffff", border_color="#65589c", border_hover="#b89cff", font_size=12, padding="4px 10px")
        )
        self.btn_open_bone_merge_map.setToolTip("標準ボーン辞書とユーザー辞書による自動対応表を確認・手動修正し、ボーン統合を実行します。")
        self.btn_open_bone_merge_map.clicked.connect(self._open_bone_merge_map_dialog)
        h_bone_merge.addWidget(self.btn_open_bone_merge_map, 1)

        self.btn_auto_bone_merge = QPushButton("ボーン統合を自動推定で即実行")
        self.btn_auto_bone_merge.setFixedHeight(34)
        self.btn_auto_bone_merge.setStyleSheet(
            _create_button_style("#264b6e", "#33618d", "#ffffff", border_color="#3d72a4", border_hover="#6bc1ff", font_size=12, padding="4px 10px")
        )
        self.btn_auto_bone_merge.clicked.connect(self._on_auto_execute_bone_merge)
        h_bone_merge.addWidget(self.btn_auto_bone_merge, 1)
        layout_step5.addLayout(h_bone_merge)
        layout.addWidget(self.grp_step5)

        # -------------------------------------------------------------
        # Step 6: 物理統合セクション (剛体・Joint番号振り直し & 衝突グループ確認)
        # -------------------------------------------------------------
        self.grp_step6 = QGroupBox("【Step 6: 物理統合 (剛体・Joint番号振り直し & 衝突グループ確認)】")
        self.grp_step6.setStyleSheet("QGroupBox { font-weight: bold; color: #88ddff; }")
        layout_step6 = QVBoxLayout(self.grp_step6)
        layout_step6.setSpacing(8)

        h_phys_merge = QHBoxLayout()
        self.btn_open_physics_plan = QPushButton("物理統合プラン & 衝突グループ候補を確認して統合...")
        self.btn_open_physics_plan.setFixedHeight(34)
        self.btn_open_physics_plan.setStyleSheet(
            _create_button_style("#1e5670", "#286e8f", "#ffffff", border_color="#368bb4", border_hover="#52c5ff", font_size=12, padding="4px 10px")
        )
        self.btn_open_physics_plan.setToolTip("移植される剛体・Jointの番号振り直しと衝突グループ番号の重複・空き候補を確認し、物理統合を実行します。")
        self.btn_open_physics_plan.clicked.connect(self._open_physics_merge_plan_dialog)
        h_phys_merge.addWidget(self.btn_open_physics_plan, 1)

        self.btn_auto_physics_merge = QPushButton("物理統合を自動設定で即実行")
        self.btn_auto_physics_merge.setFixedHeight(34)
        self.btn_auto_physics_merge.setStyleSheet(
            _create_button_style("#264b6e", "#33618d", "#ffffff", border_color="#3d72a4", border_hover="#6bc1ff", font_size=12, padding="4px 10px")
        )
        self.btn_auto_physics_merge.clicked.connect(self._on_auto_execute_physics_merge)
        h_phys_merge.addWidget(self.btn_auto_physics_merge, 1)
        layout_step6.addLayout(h_phys_merge)
        layout.addWidget(self.grp_step6)

        # -------------------------------------------------------------
        # Step 7: 書き出し前最終チェック & おまかせ一括実行セクション
        # -------------------------------------------------------------
        self.grp_step7 = QGroupBox("【Step 7: 書き出し前最終チェック & おまかせ一括実行】")
        self.grp_step7.setStyleSheet("QGroupBox { font-weight: bold; color: #88ffaa; }")
        layout_step7 = QVBoxLayout(self.grp_step7)
        layout_step7.setSpacing(8)

        self.btn_run_validation = QPushButton("書き出し前最終チェックを実行 (6項目診断)")
        self.btn_run_validation.setFixedHeight(36)
        self.btn_run_validation.setStyleSheet(
            _create_button_style("#1f5e3b", "#297a4d", "#ffffff", border_color="#369e63", border_hover="#66ffaa", font_size=13, padding="4px 12px")
        )
        self.btn_run_validation.setToolTip(
            "未ウェイト頂点・インフルエンス上限(BDEF4)・名前重複・孤立剛体/Joint・表情モーフ残存・首境界の隙間を一括診断します。"
        )
        self.btn_run_validation.clicked.connect(self._on_run_validation)
        layout_step7.addWidget(self.btn_run_validation)

        h_name = QHBoxLayout()
        h_name.addWidget(QLabel("生成モデル名称:"))
        self.le_output_name = QLineEdit("Customized_MMD_Model")
        h_name.addWidget(self.le_output_name)
        layout_step7.addLayout(h_name)

        self.chk_auto_backup = QCheckBox("実行前にシーンを自動バックアップ保存する (シーン名_dressup_backup_日時.mb)")
        self.chk_auto_backup.setChecked(True)
        self.chk_auto_backup.setStyleSheet("color: #cccccc; font-size: 11px;")
        layout_step7.addWidget(self.chk_auto_backup)

        self.chk_clamp_bdef4 = QCheckBox("一括実行時にインフルエンス4以下 (PMX BDEF4上限) へ自動整理する")
        self.chk_clamp_bdef4.setChecked(True)
        self.chk_clamp_bdef4.setStyleSheet("color: #cccccc; font-size: 11px;")
        layout_step7.addWidget(self.chk_clamp_bdef4)

        self.chk_full_merge_neck = QCheckBox("一括実行・最終診断に首の継ぎ目処理・隙間チェックを含める (頭挿げ替え時のみオン)")
        self.chk_full_merge_neck.setChecked(False)
        self.chk_full_merge_neck.setToolTip("頭挿げ替えの場合はオンにします。羽・帽子・小物等の移植時はオフのままで問題ありません。")
        self.chk_full_merge_neck.setStyleSheet("color: #cccccc; font-size: 11px;")
        layout_step7.addWidget(self.chk_full_merge_neck)

        self.btn_execute_dressup = QPushButton("おまかせ一括統合を実行 (位置合わせ・ボーン・物理・診断)")
        self.btn_execute_dressup.setFixedHeight(40)
        self.btn_execute_dressup.setStyleSheet(
            _create_button_style("#185d8f", "#2176b5", "#ffffff", border_color="#2b94e3", border_hover="#6bc1ff", font_size=14, padding="6px 14px")
        )
        self.btn_execute_dressup.clicked.connect(self._on_execute_full_dressup)
        layout_step7.addWidget(self.btn_execute_dressup)

        layout.addWidget(self.grp_step7)

        layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        # 初期状態の操作ロック設定およびキャッシュ状態更新
        self._update_lock_state()
        self._refresh_weight_cache_status()

    def _refresh_model_combos(self):
        """シーン内のMMDモデルルートノードを再探索してコンボボックスに設定"""
        self.cbb_base_model.blockSignals(True)
        self.cbb_outfit_model.blockSignals(True)

        self.cbb_base_model.clear()
        self.cbb_outfit_model.clear()

        # シーン内のMMDモデルルートノードを探索
        models = []
        for tr in mc.ls(type="transform") or []:
            for attr in ["mmdModelRoot", "mmdModelPath", "modelPath"]:
                if mc.attributeQuery(attr, node=tr, exists=True):
                    models.append(tr)
                    break

        if not models:
            for tr in mc.ls(assemblies=True) or []:
                if mc.listRelatives(tr, type=["mesh", "joint"]):
                    models.append(tr)

        self.cbb_base_model.addItem("（素体モデルを選択...）", None)
        self.cbb_outfit_model.addItem("（衣装モデルを選択...）", None)

        for m in sorted(list(set(models))):
            self.cbb_base_model.addItem(m, m)
            self.cbb_outfit_model.addItem(m, m)

        if len(models) >= 2:
            self.cbb_base_model.setCurrentIndex(1)
            self.cbb_outfit_model.setCurrentIndex(2)

        self.cbb_base_model.blockSignals(False)
        self.cbb_outfit_model.blockSignals(False)

        self._on_model_selection_changed()

    def _on_model_selection_changed(self):
        """モデル選択が変更された際の処理"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()
        pair_key = (base_model, outfit_model)

        if pair_key in self.agreed_pairs and base_model and outfit_model:
            self.is_terms_agreed = True
        else:
            self.is_terms_agreed = False

        self._update_lock_state()
        self._update_bone_check_label()
        self._update_bone_visibility_buttons()
        self._refresh_anchor_bone_combo()

    def _update_bone_visibility_buttons(self):
        """選択中モデル名をボーン表示切替ボタンのラベルへ反映"""
        if not hasattr(self, "btn_bone_vis_a"):
            return
        base_m = self.cbb_base_model.currentData()
        outfit_m = self.cbb_outfit_model.currentData()
        name_a = base_m.split("|")[-1] if base_m else "移植元(A)"
        name_b = outfit_m.split("|")[-1] if outfit_m else "ベース(B)"
        self.btn_bone_vis_a.setText(f"{name_a} のみ")
        self.btn_bone_vis_b.setText(f"{name_b} のみ")

    def _on_set_bone_visibility(self, mode):
        """ビューポート上のキャラ別 / 両方ボーン表示を切り替え"""
        self._bone_vis_mode = mode
        base_m = self.cbb_base_model.currentData()
        outfit_m = self.cbb_outfit_model.currentData()
        colorize = self.chk_bone_colorize.isChecked() if hasattr(self, "chk_bone_colorize") else False
        res = model_modifier.set_models_bone_visibility(base_m, outfit_m, mode=mode, colorize=colorize)
        mode_labels = {
            "both": "両方のキャラのボーンを表示",
            "model_a": f"{base_m.split('|')[-1] if base_m else '移植元(A)'} のボーンのみ表示",
            "model_b": f"{outfit_m.split('|')[-1] if outfit_m else 'ベース(B)'} のボーンのみ表示",
            "none": "ボーンを非表示",
        }
        mc.inViewMessage(
            amg=f"<hl>{mode_labels.get(mode, mode)} (表示: {res['visible_count']} 本)</hl>",
            pos="topCenter",
            fade=True,
        )

    def _refresh_anchor_bone_combo(self):
        """両モデルの共通ボーン一覧からStep 2の位置合わせ基準ボーン候補を更新"""
        if not hasattr(self, "cbb_anchor_bone"):
            return
        prev_val = self.cbb_anchor_bone.currentData()
        base_m = self.cbb_base_model.currentData()
        outfit_m = self.cbb_outfit_model.currentData()

        hint_map = {
            "上半身2": "上半身2 (羽・背中小物・上着向け)",
            "首": "首 (頭の挿げ替え向け)",
            "頭": "頭 (帽子・髪飾り向け)",
            "上半身": "上半身 (マント・衣装向け)",
            "下半身": "下半身 (尻尾・スカート向け)",
            "腰": "腰 (腰小物・ベルト向け)",
            "センター": "センター (全身位置合わせ)",
            "左腕": "左腕 (左腕パーツ向け)",
            "右腕": "右腕 (右腕パーツ向け)",
            "全ての親": "全ての親 (原点基準)",
        }

        common = []
        if base_m and outfit_m and base_m != outfit_m:
            common = model_modifier.get_common_anchor_bones(base_m, outfit_m)

        if not common:
            common = ["上半身2", "首", "頭", "上半身", "下半身", "センター"]

        self.cbb_anchor_bone.blockSignals(True)
        self.cbb_anchor_bone.clear()
        for b_name in common:
            self.cbb_anchor_bone.addItem(hint_map.get(b_name, b_name), b_name)

        restore_idx = self.cbb_anchor_bone.findData(prev_val) if prev_val else -1
        if restore_idx >= 0:
            self.cbb_anchor_bone.setCurrentIndex(restore_idx)
        else:
            def_idx = self.cbb_anchor_bone.findData("上半身2")
            if def_idx >= 0:
                self.cbb_anchor_bone.setCurrentIndex(def_idx)
        self.cbb_anchor_bone.blockSignals(False)

    def _update_bone_check_label(self):
        """選択された2モデルの標準ボーン（頭・首・上半身・センター）の充足状態をラベルに表示"""
        if not hasattr(self, "lbl_bone_check"):
            return
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()
        if not base_model and not outfit_model:
            self.lbl_bone_check.setText("標準ボーン診断: モデルを選択してください")
            self.lbl_bone_check.setStyleSheet("color: #aaaaaa; font-size: 11px;")
            return

        msgs = []
        all_ok = True
        for label, m_node in [("素体", base_model), ("衣装", outfit_model)]:
            if not m_node:
                continue
            info = model_modifier.check_standard_bones(m_node)
            if info["is_ready"] and not info["missing"]:
                msgs.append(f"{label}: 標準ボーン検出OK")
            elif info["is_ready"]:
                msgs.append(f"{label}: 位置合わせ可能 (未検出: {','.join(info['missing'])})")
            else:
                all_ok = False
                msgs.append(f"{label}: 首/頭ボーン未検出 ({','.join(info['missing'])})")

        self.lbl_bone_check.setText(" / ".join(msgs))
        if all_ok:
            self.lbl_bone_check.setStyleSheet("color: #88ee88; font-size: 11px;")
        else:
            self.lbl_bone_check.setStyleSheet("color: #ffaa55; font-size: 11px;")

    def _open_terms_dialog(self):
        """利用規約確認ダイアログを起動"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()

        if not base_model or not outfit_model:
            QMessageBox.warning(self, "モデル未選択", "素体モデルと衣装モデルの両方を指定してください。")
            return
        if base_model == outfit_model:
            QMessageBox.warning(self, "同一モデルの選択", "素体モデルと衣装モデルには異なるモデルを選択してください。")
            return

        dlg = ModelTermsConfirmDialog(base_model, outfit_model, parent=self)
        dlg.exec_()

        # 同意フラグが立っていれば確実にアンロック
        if dlg.is_agreed:
            pair_key = (base_model, outfit_model)
            self.agreed_pairs.add(pair_key)
            self.is_terms_agreed = True
            self._update_lock_state()
            QMessageBox.information(self, "規約確認完了", "利用規約の確認と同意が完了しました。各種編集機能が利用可能です。")

    def _toggle_lock_state(self):
        """同意状態の手動トグル切り替え"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()
        self.is_terms_agreed = not self.is_terms_agreed
        if self.is_terms_agreed and base_model and outfit_model:
            self.agreed_pairs.add((base_model, outfit_model))
        self._update_lock_state()

    def _mark_step_done(self, step_num, done=True):
        """上部ウィザード進捗バーのステップ完了状態を更新"""
        if step_num not in self.step_completed:
            return
        self.step_completed[step_num] = bool(done)
        badge = self.step_badges.get(step_num)
        if badge:
            if done:
                badge.setStyleSheet(
                    "background-color: #1f5c3a; color: #ccffdd; border: 1px solid #35a064; "
                    "border-radius: 3px; padding: 2px 4px; font-size: 10px; font-weight: bold;"
                )
            else:
                badge.setStyleSheet(
                    "background-color: #2c3038; color: #9aa5b1; border: 1px solid #444b54; "
                    "border-radius: 3px; padding: 2px 4px; font-size: 10px; font-weight: bold;"
                )
        if hasattr(self, "progress_bar"):
            done_cnt = sum(1 for v in self.step_completed.values() if v)
            self.progress_bar.setValue(done_cnt)

    def _update_lock_state(self):
        """規約確認状態に応じてStep 2以降のウィジェットを有効/無効化"""
        if self.is_terms_agreed:
            self.lbl_terms_status.setText("【規約確認・同意済み】")
            self.lbl_terms_status.setStyleSheet("color: #77ff77; font-weight: bold;")
            self.grp_step2.setEnabled(True)
            self.grp_step3.setEnabled(True)
            self.grp_step4.setEnabled(True)
            self.grp_weights.setEnabled(True)
            self.grp_step5.setEnabled(True)
            if hasattr(self, "grp_step6"):
                self.grp_step6.setEnabled(True)
            if hasattr(self, "grp_step7"):
                self.grp_step7.setEnabled(True)
            self._mark_step_done(1, True)
        else:
            self.lbl_terms_status.setText("【未確認 - 操作ロック中】")
            self.lbl_terms_status.setStyleSheet("color: #ff5555; font-weight: bold;")
            self.grp_step2.setEnabled(False)
            self.grp_step3.setEnabled(False)
            self.grp_step4.setEnabled(False)
            self.grp_weights.setEnabled(False)
            self.grp_step5.setEnabled(False)
            if hasattr(self, "grp_step6"):
                self.grp_step6.setEnabled(False)
            if hasattr(self, "grp_step7"):
                self.grp_step7.setEnabled(False)
            self._mark_step_done(1, False)

    def _open_material_filter_dialog(self):
        """材質別絞り込み・削除ダイアログを開く"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()

        target_models = []
        if base_model:
            target_models.append(base_model)
        if outfit_model and outfit_model not in target_models:
            target_models.append(outfit_model)

        if not target_models:
            QMessageBox.warning(self, "案内", "モデルが選択されていません。")
            return

        self.material_filter_dialog = MaterialFilterDialog(
            target_models=target_models,
            current_model=base_model if base_model else target_models[0],
            parent=self
        )
        self._mark_step_done(3, True)
        self.material_filter_dialog.show()
        self.material_filter_dialog.raise_()
        self.material_filter_dialog.activateWindow()

    def _open_bone_physics_dialog(self):
        """ボーン・剛体絞り込み・削除ダイアログを開く（2体選択時は両方表示モードで起動）"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()

        target_models = []
        if base_model:
            target_models.append(base_model)
        if outfit_model and outfit_model not in target_models:
            target_models.append(outfit_model)

        if not target_models:
            QMessageBox.warning(self, "案内", "モデルが選択されていません。")
            return

        default_view = BonePhysicsFilterDialog.ALL_MODELS_KEY if len(target_models) >= 2 else target_models[0]
        self.bone_phys_dialog = BonePhysicsFilterDialog(
            target_models=target_models,
            current_model=default_view,
            parent=self
        )
        self._mark_step_done(3, True)
        self.bone_phys_dialog.show()
        self.bone_phys_dialog.raise_()
        self.bone_phys_dialog.activateWindow()

    def _refresh_weight_cache_status(self):
        """シーン内のウェイトキャッシュ保存状態を確認してラベルへ反映"""
        if model_modifier.has_cached_weights(cache_tag="mod_cache"):
            self.lbl_weight_status.setText("【ウェイトキャッシュ: シーン内データを保存済み】")
            self.lbl_weight_status.setStyleSheet("color: #77ff77; font-weight: bold; font-size: 11px;")
        else:
            self.lbl_weight_status.setText("【ウェイトキャッシュ: 未保存】")
            self.lbl_weight_status.setStyleSheet("color: #aaaaaa; font-size: 11px;")

    def _on_auto_cleanup_bones_physics(self):
        """未使用ボーンおよび孤立剛体の一括クリーンアップ"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()
        target = outfit_model if outfit_model else base_model
        if not target:
            QMessageBox.warning(self, "案内", "対象モデルが選択されていません。")
            return

        reply = QMessageBox.question(
            self,
            "クリーンアップ確認",
            f"モデル『{target}』内の未使用ボーン（ウェイト0）および孤立剛体・Jointを一括自動削除しますか？\n"
            f"※子ボーンは親へ安全に再接続されます。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        with model_modifier.undo_chunk("MMD_UI_AutoCleanup"):
            del_b, del_p = model_modifier.cleanup_unused_bones_and_physics(target)
        QMessageBox.information(
            self,
            "クリーンアップ完了",
            f"クリーンアップが完了しました！\n"
            f"・削除された未使用ボーン: {del_b} 個\n"
            f"・削除された孤立剛体/Joint: {del_p} 個"
        )

    def _on_cache_skin_weights(self):
        """スキンウェイトの一時保存"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()
        if not outfit_model and not base_model:
            QMessageBox.warning(self, "警告", "モデルを選択してください。")
            return

        target = outfit_model if outfit_model else base_model
        with model_modifier.undo_chunk("MMD_UI_CacheSkinWeights"):
            success = model_modifier.cache_model_skin_weights(target, cache_tag="mod_cache")
        if success:
            self.lbl_weight_status.setText(f"【ウェイトキャッシュ: 『{target}』を保存済み】")
            self.lbl_weight_status.setStyleSheet("color: #77ff77; font-weight: bold; font-size: 11px;")
            mc.inViewMessage(amg="<hl>スキンウェイトをシーン内へ保存しました</hl>", pos="topCenter", fade=True)
        else:
            QMessageBox.warning(self, "警告", "スキンクラスタを持つメッシュが見つかりませんでした。")

    def _on_clear_skin_weights(self):
        """保存されているウェイトキャッシュの破棄"""
        with model_modifier.undo_chunk("MMD_UI_ClearSkinWeights"):
            model_modifier.clear_cached_weights(cache_tag="mod_cache")
        self._refresh_weight_cache_status()
        mc.inViewMessage(amg="<hl>保存されていたウェイトキャッシュを破棄しました</hl>", pos="topCenter", fade=True)

    def _on_rebind_skin_weights(self):
        """素体ボーンへ綺麗に再バインドスキン"""
        base_model = self.cbb_base_model.currentData()
        if not base_model:
            QMessageBox.warning(self, "警告", "素体モデルを選択してください。")
            return

        if not model_modifier.has_cached_weights(cache_tag="mod_cache"):
            QMessageBox.warning(self, "警告", "保存されたウェイトキャッシュがありません。先に一時保存を実行してください。")
            return

        sel = mc.ls(selection=True)
        target_meshes = []
        if sel:
            for s in sel:
                target_meshes.extend(model_modifier.find_model_mesh_nodes(s) or [s])
        else:
            outfit_model = self.cbb_outfit_model.currentData()
            target_root = outfit_model if outfit_model else base_model
            target_meshes = model_modifier.find_model_mesh_nodes(target_root)

        if not target_meshes:
            QMessageBox.warning(self, "警告", "再バインド対象のメッシュを選択するかモデルを指定してください。")
            return

        count = 0
        with model_modifier.undo_chunk("MMD_UI_RebindSkinWeights"):
            for m in target_meshes:
                if model_modifier.rebind_and_transfer_skin_weights(m, base_model, cache_tag="mod_cache"):
                    count += 1

        if count > 0:
            mc.inViewMessage(amg=f"<hl>{count}個のメッシュへ綺麗にウェイトを再バインドしました</hl>", pos="topCenter", fade=True)
            QMessageBox.information(self, "再バインド完了", f"{count}個のメッシュに対して素体ボーンへの綺麗再バインドスキンが完了しました！")
        else:
            QMessageBox.warning(self, "警告", "ウェイト転送に失敗しました。")

    def _get_align_moving_and_reference(self):
        """位置合わせの移動側モデルと参照側モデルを取得"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()
        mode = self.cbb_align_target.currentData() if hasattr(self, "cbb_align_target") else "base_to_outfit"
        if mode == "outfit_to_base":
            return outfit_model, base_model
        return base_model, outfit_model

    def _on_auto_estimate_alignment(self):
        """選択された基準ボーンからスケール倍率と移動量を自動推定しプレビューを適用"""
        moving, reference = self._get_align_moving_and_reference()
        if not moving or not reference:
            QMessageBox.warning(self, "案内", "移植元モデルとベースモデルの両方を選択してください。")
            return

        anchor_bone = self.cbb_anchor_bone.currentData() if hasattr(self, "cbb_anchor_bone") else "上半身2"
        auto_scale = self.chk_auto_scale.isChecked() if hasattr(self, "chk_auto_scale") else True

        with model_modifier.undo_chunk("MMD_UI_AutoEstimateAlign"):
            est = model_modifier.estimate_alignment_transform(
                moving_model=moving,
                reference_model=reference,
                anchor_bone=anchor_bone,
                auto_scale=auto_scale,
            )
            if not est:
                QMessageBox.warning(self, "警告", f"基準ボーン『{anchor_bone}』が両モデルで検出できなかったため推定できませんでした。")
                return

            sc = est["scale_factor"]
            ox = est["offset_x"]
            oy = est["offset_y"]
            oz = est["offset_z"]

            self.spn_scale.setValue(sc)
            if hasattr(self, "spn_offset_x"):
                self.spn_offset_x.setValue(ox)
            self.spn_offset_y.setValue(oy)
            self.spn_offset_z.setValue(oz)

            model_modifier.preview_alignment_transform(moving, sc, ox, oy, oz)

        mc.inViewMessage(
            amg=f"<hl>位置合わせプレビュー (基準: {est.get('anchor_bone', anchor_bone)}): 倍率={sc:.3f}, 移動=({ox:.2f}, {oy:.2f}, {oz:.2f})</hl>",
            pos="topCenter",
            fade=True,
        )

    def _on_preview_alignment(self):
        """現在入力されている微調整数値で位置合わせプレビューを更新"""
        moving, _ = self._get_align_moving_and_reference()
        if not moving or not mc.objExists(moving):
            return
        sc = self.spn_scale.value()
        ox = self.spn_offset_x.value() if hasattr(self, "spn_offset_x") else 0.0
        oy = self.spn_offset_y.value()
        oz = self.spn_offset_z.value()
        with model_modifier.undo_chunk("MMD_UI_PreviewAlign"):
            model_modifier.preview_alignment_transform(moving, sc, ox, oy, oz)
        mc.inViewMessage(amg="<hl>微調整値で位置合わせプレビューを更新しました</hl>", pos="topCenter", fade=True)

    def _on_reset_alignment_preview(self):
        """プレビュー中の位置合わせを初期状態へ戻す"""
        with model_modifier.undo_chunk("MMD_UI_ResetAlignPreview"):
            model_modifier.reset_alignment_preview()
        self.spn_scale.setValue(1.0)
        if hasattr(self, "spn_offset_x"):
            self.spn_offset_x.setValue(0.0)
        self.spn_offset_y.setValue(0.0)
        self.spn_offset_z.setValue(0.0)
        mc.inViewMessage(amg="<hl>位置合わせプレビューを初期状態へ戻しました</hl>", pos="topCenter", fade=True)

    def _on_apply_transform(self):
        """位置およびスケールを確定し、バインドポーズを安全に再設定"""
        moving, _ = self._get_align_moving_and_reference()
        if not moving or not mc.objExists(moving):
            return
        scale_val = self.spn_scale.value()
        off_x = self.spn_offset_x.value() if hasattr(self, "spn_offset_x") else 0.0
        off_y = self.spn_offset_y.value()
        off_z = self.spn_offset_z.value()

        with model_modifier.undo_chunk("MMD_UI_ApplyTransform"):
            model_modifier.commit_alignment_transform(moving, scale_val, off_x, off_y, off_z)
        self.spn_scale.setValue(1.0)
        if hasattr(self, "spn_offset_x"):
            self.spn_offset_x.setValue(0.0)
        self.spn_offset_y.setValue(0.0)
        self.spn_offset_z.setValue(0.0)
        self._mark_step_done(2, True)
        mc.inViewMessage(
            amg=f"<hl>『{moving}』の位置・スケールを確定しバインドポーズを更新しました</hl>",
            pos="topCenter",
            fade=True,
        )

    def _on_delete_selected_faces(self):
        """選択されているメッシュコンポーネントを削除"""
        sel = mc.ls(selection=True)
        if not sel:
            QMessageBox.information(self, "案内", "削除したいポリゴン面を選択してください。")
            return
        with model_modifier.undo_chunk("MMD_UI_DeleteSelectedFaces"):
            model_modifier.delete_selected_mesh_components(sel)
        mc.inViewMessage(amg="<hl>選択コンポーネントを削除しました</hl>", pos="topCenter", fade=True)

    def _on_toggle_isolate(self):
        """選択オブジェクトのビューポート単独表示切替"""
        current_panel = mc.getPanel(withFocus=True)
        if current_panel and mc.getPanel(typeOf=current_panel) == "modelPanel":
            state = mc.isolateSelect(current_panel, query=True, state=True)
            mc.isolateSelect(current_panel, state=(not state))

    def _on_preview_neck_seam(self):
        """首境界の対応頂点ペアを検出してプレビュー表示"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()
        if not base_model or not outfit_model:
            QMessageBox.warning(self, "案内", "素体モデルと衣装モデルの両方を選択してください。")
            return

        threshold = self.spn_merge_dist.value()
        with model_modifier.undo_chunk("MMD_UI_PreviewNeckSeam"):
            info = model_modifier.preview_neck_seam(base_model, outfit_model, distance_threshold=threshold)

        msg = (
            f"首境界プレビュー: 頭側境界={info['head_boundary_count']}頂点 / "
            f"体側境界={info['body_boundary_count']}頂点 / "
            f"対応ペア={info['matched_count']}組 (未一致={info['unmatched_count']})"
        )
        mc.inViewMessage(amg=f"<hl>{msg}</hl>", pos="topCenter", fade=True)
        if info.get("warnings"):
            QMessageBox.information(self, "首境界の検出結果", msg + "\n\n" + "\n".join(info["warnings"]))

    def _on_merge_neck_vertices(self):
        """首の継ぎ目処理（非結合スナップ・法線コピー・ウェイトコピー）を一括実行"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()
        if not base_model or not outfit_model:
            QMessageBox.warning(self, "警告", "素体モデルと衣装モデルの両方を選択してください。")
            return

        threshold = self.spn_merge_dist.value()
        do_snap = self.chk_neck_snap.isChecked() if hasattr(self, "chk_neck_snap") else True
        do_norm = self.chk_neck_normals.isChecked() if hasattr(self, "chk_neck_normals") else True
        do_wgt = self.chk_neck_weights.isChecked() if hasattr(self, "chk_neck_weights") else True

        with model_modifier.undo_chunk("MMD_UI_ProcessNeckSeam"):
            res = model_modifier.process_neck_seam(
                head_model_or_mesh=base_model,
                body_model_or_mesh=outfit_model,
                distance_threshold=threshold,
                snap_positions=do_snap,
                smooth_normals=do_norm,
                copy_weights=do_wgt,
            )

        if not res.get("success"):
            warn_txt = "\n".join(res.get("warnings", []))
            QMessageBox.warning(
                self,
                "首継ぎ目処理",
                f"{res.get('message', '一致する境界ペアが見つかりませんでした。')}\n\n{warn_txt}",
            )
            return

        self._mark_step_done(4, True)
        summary = (
            f"首の継ぎ目処理が完了しました！（メッシュ非結合・モーフ保持）\n\n"
            f"・対応ペア数: {res['matched_count']} 組 (未一致: {res['unmatched_count']} 頂点)\n"
            f"・位置スナップ頂点数: {res['snapped_count']} 頂点\n"
            f"・法線平均化頂点数: {res['normals_updated_count']} 頂点\n"
            f"・ウェイトコピー頂点数: {res['weights_copied_count']} 頂点"
        )
        if res.get("warnings"):
            summary += "\n\n【補足】\n" + "\n".join(res["warnings"])
        QMessageBox.information(self, "首の継ぎ目処理完了", summary)

    def _on_smooth_neck_normals(self):
        """首境界まわりの法線平均化処理を実行"""
        sel = mc.ls(selection=True)
        target = sel[0] if sel else None
        if not target:
            base_model = self.cbb_base_model.currentData()
            outfit_model = self.cbb_outfit_model.currentData()
            if base_model and outfit_model:
                threshold = self.spn_merge_dist.value()
                with model_modifier.undo_chunk("MMD_UI_SmoothNeckNormalsPair"):
                    res = model_modifier.process_neck_seam(
                        head_model_or_mesh=base_model,
                        body_model_or_mesh=outfit_model,
                        distance_threshold=threshold,
                        snap_positions=False,
                        smooth_normals=True,
                        copy_weights=False,
                    )
                if res.get("success"):
                    mc.inViewMessage(amg="<hl>首境界の法線を滑らかに補正しました (影消去)</hl>", pos="topCenter", fade=True)
                    return
            target = base_model

        if not target:
            QMessageBox.warning(self, "警告", "法線を補正するモデルまたはメッシュを選択してください。")
            return

        with model_modifier.undo_chunk("MMD_UI_SmoothNeckNormals"):
            success = model_modifier.smooth_neck_normals(target)
        if success:
            mc.inViewMessage(amg="<hl>首境界まわりの法線を滑らかに補正しました (影消去)</hl>", pos="topCenter", fade=True)
        else:
            mc.warning("首境界頂点が見つからなかったため法線補正をスキップしました。")

    def _on_test_neck_bend(self):
        """首ボーンを一時的に曲げて継ぎ目の割れを確認"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()
        if not base_model or not outfit_model:
            QMessageBox.warning(self, "案内", "素体モデルと衣装モデルの両方を選択してください。")
            return

        threshold = self.spn_merge_dist.value()
        with model_modifier.undo_chunk("MMD_UI_TestNeckBend"):
            res = model_modifier.test_neck_bend(base_model, outfit_model, distance_threshold=threshold)
        mc.inViewMessage(
            amg=f"<hl>首曲げテスト [{res['pose_label']}]: 対応ペア最大隙間={res['max_seam_gap']:.4f}</hl>",
            pos="topCenter",
            fade=True,
        )

    def _on_reset_neck_bend(self):
        """首曲げテストの角度を初期状態へ戻す"""
        with model_modifier.undo_chunk("MMD_UI_ResetNeckBend"):
            model_modifier.reset_neck_bend()
        mc.inViewMessage(amg="<hl>首の回転角度を初期姿勢へ戻しました</hl>", pos="topCenter", fade=True)

    def _get_source_and_master_models(self):
        """マスター骨格設定に基づき、(移植元モデル, マスター骨格モデル, 接尾辞) を取得"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()
        master_mode = self.cbb_master_skeleton.currentData() if hasattr(self, "cbb_master_skeleton") else "outfit"
        if master_mode == "base":
            return outfit_model, base_model, "_outfit"
        return base_model, outfit_model, "_part"

    def _open_bone_merge_map_dialog(self):
        """ボーン統合対応表の確認・編集ダイアログを起動し、確定時にボーン統合を実行"""
        src_model, mst_model, suffix = self._get_source_and_master_models()
        if not src_model or not mst_model:
            QMessageBox.warning(self, "案内", "素体モデルと衣装モデルの両方を選択してください。")
            return

        plan = model_modifier.build_bone_merge_plan(
            source_model=src_model,
            master_model=mst_model,
            rename_suffix=suffix,
        )
        if not plan:
            QMessageBox.warning(self, "警告", "ボーン構造を解析できませんでした。")
            return

        dlg = BoneMergeMapDialog(merge_plan=plan, parent=self)
        dlg.exec_()
        if not dlg.is_confirmed:
            return

        with model_modifier.undo_chunk("MMD_UI_ExecuteBoneMergeWithMap"):
            res = model_modifier.execute_bone_merge(
                source_model=src_model,
                master_model=mst_model,
                merge_plan=dlg.merge_plan,
                rename_suffix=suffix,
                cleanup_unused_source_bones=False,
            )

        if res.get("success"):
            self._mark_step_done(5, True)
            QMessageBox.information(
                self,
                "ボーン統合完了",
                f"対応表に基づくボーン統合が完了しました！\n\n"
                f"・共通ボーンのウェイト付替: {res['merged_common_bones']} 本\n"
                f"・固有ボーンの移植: {res['transplanted_bones']} 本 (サブツリー: {res['transplanted_subtrees']} 組)\n"
                f"・衝突回避リネーム: {res['renamed_collision_bones']} 本\n"
                f"・再バインド完了メッシュ: {res['rebound_meshes']} 個",
            )
        else:
            QMessageBox.warning(self, "ボーン統合中断", res.get("message", "処理を中断しました。"))

    def _on_auto_execute_bone_merge(self):
        """自動推定されたボーン対応表を用いてボーン統合を即実行"""
        src_model, mst_model, suffix = self._get_source_and_master_models()
        if not src_model or not mst_model:
            QMessageBox.warning(self, "案内", "素体モデルと衣装モデルの両方を選択してください。")
            return

        reply = QMessageBox.question(
            self,
            "ボーン統合の自動実行確認",
            f"移植元『{src_model}』のボーンとウェイトを、\n"
            f"マスター骨格『{mst_model}』へ自動統合しますか？\n\n"
            f"・共通ボーンはマスター骨格側へウェイトを付け替えます。\n"
            f"・固有ボーン（髪・目・アクセサリー等）はマスター骨格へ親子付け移植します。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        with model_modifier.undo_chunk("MMD_UI_AutoExecuteBoneMerge"):
            res = model_modifier.execute_bone_merge(
                source_model=src_model,
                master_model=mst_model,
                rename_suffix=suffix,
                cleanup_unused_source_bones=False,
            )

        if res.get("success"):
            self._mark_step_done(5, True)
            QMessageBox.information(
                self,
                "ボーン統合完了",
                f"ボーン統合が完了しました！\n\n"
                f"・共通ボーンのウェイト付替: {res['merged_common_bones']} 本\n"
                f"・固有ボーンの移植: {res['transplanted_bones']} 本 (サブツリー: {res['transplanted_subtrees']} 組)\n"
                f"・衝突回避リネーム: {res['renamed_collision_bones']} 本\n"
                f"・再バインド完了メッシュ: {res['rebound_meshes']} 個",
            )
        else:
            QMessageBox.warning(self, "ボーン統合中断", res.get("message", "処理を中断しました。"))

    def _open_physics_merge_plan_dialog(self):
        """物理統合プランおよび衝突グループ候補の確認ダイアログを起動し、確定時に物理統合を実行"""
        src_model, mst_model, _ = self._get_source_and_master_models()
        if not src_model or not mst_model:
            QMessageBox.warning(self, "案内", "素体モデルと衣装モデルの両方を選択してください。")
            return

        plan = model_modifier.build_physics_merge_plan(source_model=src_model, master_model=mst_model)
        if not plan:
            QMessageBox.warning(self, "警告", "物理データ（剛体・Joint）を解析できませんでした。")
            return

        dlg = PhysicsMergePlanDialog(physics_plan=plan, parent=self)
        dlg.exec_()
        if not dlg.is_confirmed:
            return

        with model_modifier.undo_chunk("MMD_UI_ExecutePhysicsMergeWithPlan"):
            res = model_modifier.execute_physics_merge(
                source_model=src_model,
                master_model=mst_model,
                physics_plan=plan,
                group_remap=dlg.group_remap,
            )

        if res.get("success"):
            self._mark_step_done(6, True)
            QMessageBox.information(
                self,
                "物理統合完了",
                f"物理統合が完了しました！\n\n"
                f"・移植された剛体: {res['transplanted_rb_count']} 個 (合計: {res.get('total_master_rbs', 0)} 個)\n"
                f"・移植されたJoint: {res['transplanted_joint_count']} 個 (合計: {res.get('total_master_joints', 0)} 個)",
            )
        else:
            QMessageBox.warning(self, "物理統合中断", res.get("message", "処理を中断しました。"))

    def _on_auto_execute_physics_merge(self):
        """自動設定で物理統合（剛体・Joint番号振り直しと追従先再接続）を即実行"""
        src_model, mst_model, _ = self._get_source_and_master_models()
        if not src_model or not mst_model:
            QMessageBox.warning(self, "案内", "素体モデルと衣装モデルの両方を選択してください。")
            return

        with model_modifier.undo_chunk("MMD_UI_AutoExecutePhysicsMerge"):
            res = model_modifier.execute_physics_merge(
                source_model=src_model,
                master_model=mst_model,
            )

        if res.get("success"):
            self._mark_step_done(6, True)
            QMessageBox.information(
                self,
                "物理統合完了",
                f"物理統合が完了しました！\n\n"
                f"・移植された剛体: {res['transplanted_rb_count']} 個 (合計: {res.get('total_master_rbs', 0)} 個)\n"
                f"・移植されたJoint: {res['transplanted_joint_count']} 個 (合計: {res.get('total_master_joints', 0)} 個)",
            )
        else:
            QMessageBox.warning(self, "物理統合中断", res.get("message", "処理を中断しました。"))

    def _on_run_validation(self):
        """Step 7: 書き出し前6項目最終チェックを実行し結果ダイアログを表示"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()
        _, mst_model, _ = self._get_source_and_master_models()

        if not base_model and not outfit_model:
            QMessageBox.warning(self, "案内", "診断対象のモデルを選択してください。")
            return

        threshold = self.spn_merge_dist.value() if hasattr(self, "spn_merge_dist") else 0.5
        do_neck_chk = self.chk_full_merge_neck.isChecked() if hasattr(self, "chk_full_merge_neck") else False
        report = model_modifier.validate_dressup_models(
            head_model=base_model,
            body_model=outfit_model,
            master_model=mst_model,
            seam_threshold=max(float(threshold), 0.5),
            check_neck_seam=do_neck_chk,
        )

        if report.get("error_count", 0) == 0:
            self._mark_step_done(7, True)

        dlg = ValidationReportDialog(
            report=report,
            head_model=base_model,
            body_model=outfit_model,
            master_model=mst_model,
            seam_threshold=max(float(threshold), 0.5),
            check_neck_seam=do_neck_chk,
            parent=self,
        )
        dlg.exec_()

    def _on_execute_full_dressup(self):
        """モデル改造・汎用パーツ移植のおまかせ一括統合を実行"""
        base_model = self.cbb_base_model.currentData()
        outfit_model = self.cbb_outfit_model.currentData()
        new_name = self.le_output_name.text().strip() or "Customized_MMD_Model"

        if not base_model or not outfit_model:
            QMessageBox.warning(self, "警告", "移植元モデルとベースモデルの両方を選択してください。")
            return
        if base_model == outfit_model:
            QMessageBox.warning(self, "警告", "移植元モデルとベースモデルには異なるモデルを選択してください。")
            return

        master_mode = self.cbb_master_skeleton.currentData() if hasattr(self, "cbb_master_skeleton") else "outfit"
        master_label = outfit_model if master_mode == "outfit" else base_model
        anchor_bone = self.cbb_anchor_bone.currentData() if hasattr(self, "cbb_anchor_bone") else "上半身2"
        auto_scale = self.chk_auto_scale.isChecked() if hasattr(self, "chk_auto_scale") else True
        do_merge_neck = self.chk_full_merge_neck.isChecked() if hasattr(self, "chk_full_merge_neck") else False

        reply = QMessageBox.question(
            self,
            "おまかせ一括統合の確認",
            f"移植元『{base_model}』とベース『{outfit_model}』を統合します。\n"
            f"※不要パーツは事前に Step 3 の削除ウィンドウ（絞り込み機能）で削除しておいてください。\n\n"
            f"・位置合わせ基準ボーン: 『{anchor_bone}』 (スケール自動推定: {'オン' if auto_scale else 'オフ'})\n"
            f"・首の継ぎ目処理: {'実行する' if do_merge_neck else 'スキップ (羽・帽子・小物等)'}\n"
            f"・マスター骨格: 『{master_label}』\n"
            f"・出力グループ名: 『{new_name}』\n"
            f"※Undo 1回で元に戻せます。よろしいですか？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            scale_val = self.spn_scale.value()
            off_x = self.spn_offset_x.value() if hasattr(self, "spn_offset_x") else 0.0
            off_y = self.spn_offset_y.value()
            off_z = self.spn_offset_z.value()
            threshold = self.spn_merge_dist.value()
            do_backup = self.chk_auto_backup.isChecked() if hasattr(self, "chk_auto_backup") else True
            do_clamp = self.chk_clamp_bdef4.isChecked() if hasattr(self, "chk_clamp_bdef4") else True

            with model_modifier.undo_chunk("MMD_UI_ExecuteFullDressup"):
                result_node = model_modifier.perform_full_model_dressup(
                    base_model=base_model,
                    outfit_model=outfit_model,
                    scale_factor=scale_val,
                    offset_x=off_x,
                    offset_y=off_y,
                    offset_z=off_z,
                    merge_neck=do_merge_neck,
                    distance_threshold=threshold,
                    smooth_normals=True,
                    new_model_name=new_name,
                    auto_backup=do_backup,
                    master_skeleton=master_mode,
                    auto_align=True,
                    anchor_bone=anchor_bone,
                    auto_scale=auto_scale,
                    clamp_bdef4=do_clamp,
                )

            for s_num in range(2, 8):
                self._mark_step_done(s_num, True)

            full_rep = model_modifier.get_last_dressup_report() or {}
            val_rep = full_rep.get("validation") or {}

            QMessageBox.information(
                self,
                "おまかせ一括統合完了",
                f"統合モデル『{result_node}』の生成が完了しました！\n\n"
                f"・書き出し前診断: OK {val_rep.get('ok_count', 0)} 件 / 注意 {val_rep.get('warning_count', 0)} 件 / エラー {val_rep.get('error_count', 0)} 件\n"
                f"※両メッシュを選択状態にしています。このままPMXエクスポートを実行できます。"
            )
            if val_rep:
                dlg = ValidationReportDialog(
                    report=val_rep,
                    head_model=full_rep.get("head_mesh"),
                    body_model=full_rep.get("body_mesh"),
                    master_model=full_rep.get("body_mesh") if master_mode == "outfit" else full_rep.get("head_mesh"),
                    seam_threshold=max(float(threshold), 0.5),
                    check_neck_seam=do_merge_neck,
                    parent=self,
                )
                dlg.exec_()

            self._refresh_model_combos()
        except Exception as e:
            import traceback
            err = traceback.format_exc()
            QMessageBox.critical(self, "統合エラー", f"改造処理中に例外が発生しました:\n{err}")

    def set_target_model(self, model_node):
        """外部から対象モデルが切り替えられた場合のハンドラ"""
        if model_node:
            idx = self.cbb_base_model.findData(model_node)
            if idx >= 0:
                self.cbb_base_model.setCurrentIndex(idx)
