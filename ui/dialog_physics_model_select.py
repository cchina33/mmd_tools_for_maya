# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 物理演算適用対象モデル選択ダイアログ
シーン内のMMDモデル（キャラクター・大型ステージ・スカイドーム）を検出し、
物理演算（ベイク）を行うモデルをチェックリスト形式で指定・管理するUIを提供します。
"""

import os
try:
    import maya.cmds as mc
except ImportError:
    mc = None

try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
        QWidget, QMessageBox, QFrame
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont
except ImportError:
    from PySide2.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
        QWidget, QMessageBox, QFrame
    )
    from PySide2.QtCore import Qt
    from PySide2.QtGui import QColor, QFont

try:
    from ..asset.model_classifier_manager import ModelClassifierManager
except Exception:
    try:
        from asset.model_classifier_manager import ModelClassifierManager
    except Exception:
        ModelClassifierManager = None

try:
    from ..converters import vmdpaimaya
except Exception:
    try:
        from converters import vmdpaimaya
    except Exception:
        vmdpaimaya = None


class PhysicsModelSelectDialog(QDialog):
    """
    物理演算（ベイク）の適用対象モデルを選択・管理するダイアログです。
    """
    def __init__(self, parent=None, initial_selected_nodes=None, default_pmx_path=""):
        super(PhysicsModelSelectDialog, self).__init__(parent)
        self.setWindowTitle("物理演算 適用対象モデルの選択")
        self.resize(780, 480)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        self.initial_selected_nodes = initial_selected_nodes
        self.default_pmx_path = default_pmx_path or ""
        self.selected_nodes = []
        self.model_records = []

        self._init_ui()
        self.refresh_models()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 説明ヘッダー
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: #2b2b2b; border-radius: 4px; padding: 6px;")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(8, 8, 8, 8)
        info_layout.setSpacing(4)

        lbl_title = QLabel("物理演算（ベイク）を行うモデルにチェックを入れてください。")
        lbl_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #ecf0f1;")
        info_layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "スカイドームや大型ステージなど、物理演算が不要なモデルのチェックを外すことで、\n"
            "計算負荷を低減し、剛体の意図しない反発や吹き飛びを防ぐことができます。"
        )
        lbl_desc.setStyleSheet("color: #bdc3c7; font-size: 11px;")
        info_layout.addWidget(lbl_desc)
        main_layout.addWidget(info_frame)

        # 一括選択操作ボタン群
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_select_all = QPushButton("すべて選択")
        self.btn_select_all.setFixedHeight(30)
        self.btn_select_all.clicked.connect(self._select_all)
        btn_bar.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("すべて解除")
        self.btn_deselect_all.setFixedHeight(30)
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        btn_bar.addWidget(self.btn_deselect_all)

        self.btn_select_characters = QPushButton("キャラクターのみ選択")
        self.btn_select_characters.setFixedHeight(30)
        self.btn_select_characters.setToolTip("スカイドームやステージを除外し、キャラクターモデルのみにチェックを入れます。")
        self.btn_select_characters.clicked.connect(self._select_characters_only)
        btn_bar.addWidget(self.btn_select_characters)

        self.btn_exclude_backgrounds = QPushButton("スカイドーム・ステージを除外")
        self.btn_exclude_backgrounds.setFixedHeight(30)
        self.btn_exclude_backgrounds.setToolTip("スカイドームと大型ステージのチェックを外します。")
        self.btn_exclude_backgrounds.clicked.connect(self._exclude_backgrounds)
        btn_bar.addWidget(self.btn_exclude_backgrounds)

        btn_bar.addStretch()
        main_layout.addLayout(btn_bar)

        # モデルテーブル
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["対象", "モデル表示名", "モデル種別", "Mayaノード名", "PMXファイルパス"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._on_table_item_changed)
        main_layout.addWidget(self.table)

        # 状態サマリー表示
        self.lbl_status = QLabel("検出中...")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #52b7ff; padding: 2px;")
        main_layout.addWidget(self.lbl_status)

        # 下部ボタングループ
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        self.btn_refresh = QPushButton("シーンから再検出")
        self.btn_refresh.setFixedHeight(34)
        self.btn_refresh.setFixedWidth(130)
        self.btn_refresh.clicked.connect(self.refresh_models)
        bottom_bar.addWidget(self.btn_refresh)

        bottom_bar.addStretch()

        self.btn_ok = QPushButton("決定")
        self.btn_ok.setFixedHeight(34)
        self.btn_ok.setFixedWidth(110)
        self.btn_ok.setStyleSheet("background-color: #2980b9; color: #fff; font-weight: bold;")
        self.btn_ok.clicked.connect(self._on_accept)
        bottom_bar.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("キャンセル")
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.setFixedWidth(100)
        self.btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_cancel)

        main_layout.addLayout(bottom_bar)

    def refresh_models(self):
        """シーン内のMMDモデルを検出してテーブルを更新"""
        models = []
        if vmdpaimaya and hasattr(vmdpaimaya, 'get_available_mmd_models'):
            try:
                models = vmdpaimaya.get_available_mmd_models()
            except Exception:
                pass

        classifier = None
        if ModelClassifierManager:
            try:
                classifier = ModelClassifierManager.get_instance()
            except Exception:
                pass

        self.model_records = []
        for node, label in models:
            # モデル固有のPMXパスを取得
            pmx_path = self.default_pmx_path
            if mc and mc.objExists(node) and mc.attributeQuery('mmdModelPath', node=node, exists=True):
                saved_path = mc.getAttr(f"{node}.mmdModelPath")
                if saved_path and os.path.exists(saved_path):
                    pmx_path = saved_path

            # モデル種別判定
            kind = "character"
            if mc and mc.objExists(node) and mc.attributeQuery('mmdModelType', node=node, exists=True):
                attr_type = str(mc.getAttr(f"{node}.mmdModelType") or "").lower()
                if attr_type in ["skydome", "stage", "character"]:
                    kind = attr_type
            elif classifier:
                try:
                    if classifier.is_skydome_mesh(node, file_path=pmx_path):
                        kind = "skydome"
                    elif classifier.is_stage_mesh(node, file_path=pmx_path):
                        kind = "stage"
                    else:
                        kind = "character"
                except Exception:
                    kind = "character"

            # 表示名の整理
            display_name = label
            if "(" in label and label.endswith(")"):
                inner = label[label.find("(") + 1:-1].strip()
                if inner:
                    display_name = inner

            # 初期チェック状態の決定
            if self.initial_selected_nodes is not None:
                is_checked = node in self.initial_selected_nodes
            else:
                # 初期設定: スカイドームは除外、それ以外は選択
                is_checked = (kind != "skydome")

            self.model_records.append({
                'node': node,
                'name': display_name,
                'full_label': label,
                'type': kind,
                'pmx_path': pmx_path,
                'is_checked': is_checked
            })

        self._populate_table()
        self._update_status_summary()

    def _populate_table(self):
        """テーブルの行データを設定"""
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.model_records))

        for row, rec in enumerate(self.model_records):
            # 対象チェックボックス
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk_item.setCheckState(Qt.Checked if rec['is_checked'] else Qt.Unchecked)
            chk_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, chk_item)

            # モデル表示名
            name_item = QTableWidgetItem(rec['name'])
            self.table.setItem(row, 1, name_item)

            # モデル種別
            type_label = "キャラクター"
            type_color = "#2ecc71"
            if rec['type'] == "skydome":
                type_label = "スカイドーム"
                type_color = "#e67e22"
            elif rec['type'] == "stage":
                type_label = "大型ステージ"
                type_color = "#3498db"

            type_item = QTableWidgetItem(type_label)
            type_item.setTextAlignment(Qt.AlignCenter)
            type_item.setForeground(QColor(type_color))
            self.table.setItem(row, 2, type_item)

            # Mayaノード名
            node_item = QTableWidgetItem(rec['node'])
            self.table.setItem(row, 3, node_item)

            # PMXファイルパス
            pmx_item = QTableWidgetItem(rec['pmx_path'] or "(未設定 / 共通設定参照)")
            self.table.setItem(row, 4, pmx_item)

        self.table.blockSignals(False)

    def _on_table_item_changed(self, item):
        """テーブルのチェック状態が変化した際の処理"""
        if item.column() == 0:
            row = item.row()
            if 0 <= row < len(self.model_records):
                self.model_records[row]['is_checked'] = (item.checkState() == Qt.Checked)
                self._update_status_summary()

    def _select_all(self):
        """全モデルにチェックを付与"""
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)
            if row < len(self.model_records):
                self.model_records[row]['is_checked'] = True
        self.table.blockSignals(False)
        self._update_status_summary()

    def _deselect_all(self):
        """全モデルのチェックを解除"""
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
            if row < len(self.model_records):
                self.model_records[row]['is_checked'] = False
        self.table.blockSignals(False)
        self._update_status_summary()

    def _select_characters_only(self):
        """キャラクターモデルのみにチェックを付与"""
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            if row < len(self.model_records):
                is_char = (self.model_records[row]['type'] == 'character')
                self.model_records[row]['is_checked'] = is_char
                item = self.table.item(row, 0)
                if item:
                    item.setCheckState(Qt.Checked if is_char else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_status_summary()

    def _exclude_backgrounds(self):
        """スカイドームおよび大型ステージのチェックを解除"""
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            if row < len(self.model_records):
                is_bg = self.model_records[row]['type'] in ['skydome', 'stage']
                if is_bg:
                    self.model_records[row]['is_checked'] = False
                    item = self.table.item(row, 0)
                    if item:
                        item.setCheckState(Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_status_summary()

    def _update_status_summary(self):
        """現在の選択状況サマリーを更新"""
        total = len(self.model_records)
        selected = sum(1 for r in self.model_records if r['is_checked'])
        char_count = sum(1 for r in self.model_records if r['is_checked'] and r['type'] == 'character')
        stage_count = sum(1 for r in self.model_records if r['is_checked'] and r['type'] == 'stage')
        dome_count = sum(1 for r in self.model_records if r['is_checked'] and r['type'] == 'skydome')

        if total == 0:
            self.lbl_status.setText("シーン内にMMDモデルが見つかりません。")
            self.lbl_status.setStyleSheet("color: #e74c3c; font-weight: bold;")
        else:
            details = []
            if char_count > 0:
                details.append(f"キャラ: {char_count}")
            if stage_count > 0:
                details.append(f"ステージ: {stage_count}")
            if dome_count > 0:
                details.append(f"ドーム: {dome_count}")
            detail_str = f" ({', '.join(details)})" if details else ""
            self.lbl_status.setText(f"選択中: {selected} / {total} 体{detail_str}")
            self.lbl_status.setStyleSheet("color: #2ecc71; font-weight: bold;" if selected > 0 else "color: #e67e22; font-weight: bold;")

    def _on_accept(self):
        """確定処理"""
        self.selected_nodes = [r['node'] for r in self.model_records if r['is_checked']]
        self.accept()

    def get_selected_nodes(self):
        """チェックされたモデルのノード名リストを取得"""
        return list(self.selected_nodes)

    def get_selected_model_records(self):
        """チェックされたモデルの詳細情報レコードを取得"""
        return [r for r in self.model_records if r['is_checked']]

