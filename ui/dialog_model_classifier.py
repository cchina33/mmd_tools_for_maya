# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - モデル種別判定・個別指定設定ダイアログ
スカイドーム・大型ステージのキーワード編集および特定モデルファイル（.pmx / .pmd / .x）の個別指定・保存GUIを提供します。
"""

import os
from .common import *

try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
        QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
        QHeaderView, QComboBox, QTabWidget, QWidget, QMessageBox,
        QFileDialog, QGroupBox, QAbstractItemView
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
except ImportError:
    from PySide2.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
        QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
        QHeaderView, QComboBox, QTabWidget, QWidget, QMessageBox,
        QFileDialog, QGroupBox, QAbstractItemView
    )
    from PySide2.QtCore import Qt
    from PySide2.QtGui import QColor

try:
    from ..asset.model_classifier_manager import ModelClassifierManager
except Exception:
    from asset.model_classifier_manager import ModelClassifierManager

try:
    from ..maya_maya_converters import pmxpaimaya
except Exception:
    from maya_converters import pmxpaimaya


class ModelClassifierDialog(QDialog):
    """
    スカイドーム・ステージのキーワード編集およびモデルファイル個別指定を管理するダイアログです。
    """
    def __init__(self, parent=None):
        super(ModelClassifierDialog, self).__init__(parent)
        self.setWindowTitle("モデル種別判定・個別指定設定")
        self.resize(720, 540)
        self.manager = ModelClassifierManager.get_instance()

        self._init_ui()
        self._load_data_to_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 説明ヘッダー
        header_label = QLabel(
            "スカイドーム（天球・空）および大型ステージの識別キーワードの編集、\n"
            "ならびに特定モデルファイル（.pmx / .pmd / .x）に対する種別の明示的な個別指定を行います。"
        )
        header_label.setStyleSheet("color: #ecf0f1; font-size: 12px; margin-bottom: 4px;")
        main_layout.addWidget(header_label)

        # タブウィジェット
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #34495e; background: #2c3e50; }
            QTabBar::tab { background: #34495e; color: #bdc3c7; padding: 8px 16px; margin-right: 2px; }
            QTabBar::tab:selected { background: #2980b9; color: #ffffff; font-weight: bold; }
        """)

        # タブの生成
        self._create_keywords_tab()
        self._create_files_tab()

        main_layout.addWidget(self.tab_widget)

        # 下部ボタングループ
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_save_apply = QPushButton("設定を保存して現在のシーンへ適用")
        self.btn_save_apply.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2ecc71; }
            QPushButton:pressed { background-color: #219d54; }
        """)
        self.btn_save_apply.clicked.connect(self._on_save_and_apply)
        btn_layout.addWidget(self.btn_save_apply)

        btn_layout.addStretch()

        self.btn_close = QPushButton("閉じる")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #7f8c8d;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #95a5a6; }
        """)
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)

        main_layout.addLayout(btn_layout)

    def _create_keywords_tab(self):
        """キーワード設定タブの作成"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        cols_layout = QHBoxLayout()
        cols_layout.setSpacing(12)

        # 左側: スカイドーム用キーワード
        gb_dome = QGroupBox("スカイドーム判定キーワード")
        gb_dome.setStyleSheet("QGroupBox { font-weight: bold; color: #ecf0f1; }")
        v_dome = QVBoxLayout(gb_dome)
        v_dome.setContentsMargins(8, 14, 8, 8)

        lbl_dome = QLabel("天球・青空・背景空単体モデルとして認識するキーワード:")
        lbl_dome.setStyleSheet("color: #bdc3c7; font-size: 11px;")
        v_dome.addWidget(lbl_dome)

        self.list_dome_keywords = QListWidget()
        self.list_dome_keywords.setStyleSheet("background: #1e272e; color: #ecf0f1; border: 1px solid #34495e;")
        v_dome.addWidget(self.list_dome_keywords)

        h_add_dome = QHBoxLayout()
        self.edit_dome_keyword = QLineEdit()
        self.edit_dome_keyword.setPlaceholderText("キーワードを入力...")
        self.edit_dome_keyword.setStyleSheet("background: #2f3640; color: #ecf0f1; padding: 4px; border: 1px solid #34495e;")
        self.edit_dome_keyword.returnPressed.connect(self._on_add_dome_keyword)
        h_add_dome.addWidget(self.edit_dome_keyword)

        btn_add_dome = QPushButton("追加")
        btn_add_dome.setStyleSheet("background-color: #2980b9; color: white; padding: 4px 10px;")
        btn_add_dome.clicked.connect(self._on_add_dome_keyword)
        h_add_dome.addWidget(btn_add_dome)
        v_dome.addLayout(h_add_dome)

        btn_del_dome = QPushButton("選択項目を削除")
        btn_del_dome.setStyleSheet("background-color: #c0392b; color: white; padding: 4px 8px;")
        btn_del_dome.clicked.connect(lambda: self._on_delete_list_item(self.list_dome_keywords))
        v_dome.addWidget(btn_del_dome)

        cols_layout.addWidget(gb_dome)

        # 右側: 大型ステージ用キーワード
        gb_stage = QGroupBox("大型ステージ判定キーワード")
        gb_stage.setStyleSheet("QGroupBox { font-weight: bold; color: #ecf0f1; }")
        v_stage = QVBoxLayout(gb_stage)
        v_stage.setContentsMargins(8, 14, 8, 8)

        lbl_stage = QLabel("床・建造物・ステージとして認識するキーワード:")
        lbl_stage.setStyleSheet("color: #bdc3c7; font-size: 11px;")
        v_stage.addWidget(lbl_stage)

        self.list_stage_keywords = QListWidget()
        self.list_stage_keywords.setStyleSheet("background: #1e272e; color: #ecf0f1; border: 1px solid #34495e;")
        v_stage.addWidget(self.list_stage_keywords)

        h_add_stage = QHBoxLayout()
        self.edit_stage_keyword = QLineEdit()
        self.edit_stage_keyword.setPlaceholderText("キーワードを入力...")
        self.edit_stage_keyword.setStyleSheet("background: #2f3640; color: #ecf0f1; padding: 4px; border: 1px solid #34495e;")
        self.edit_stage_keyword.returnPressed.connect(self._on_add_stage_keyword)
        h_add_stage.addWidget(self.edit_stage_keyword)

        btn_add_stage = QPushButton("追加")
        btn_add_stage.setStyleSheet("background-color: #2980b9; color: white; padding: 4px 10px;")
        btn_add_stage.clicked.connect(self._on_add_stage_keyword)
        h_add_stage.addWidget(btn_add_stage)
        v_stage.addLayout(h_add_stage)

        btn_del_stage = QPushButton("選択項目を削除")
        btn_del_stage.setStyleSheet("background-color: #c0392b; color: white; padding: 4px 8px;")
        btn_del_stage.clicked.connect(lambda: self._on_delete_list_item(self.list_stage_keywords))
        v_stage.addWidget(btn_del_stage)

        cols_layout.addWidget(gb_stage)

        layout.addLayout(cols_layout)

        # デフォルト復帰ボタン
        h_bottom = QHBoxLayout()
        h_bottom.addStretch()
        btn_reset_kw = QPushButton("キーワードを初期デフォルトに戻す")
        btn_reset_kw.setStyleSheet("background-color: #d35400; color: white; padding: 4px 12px;")
        btn_reset_kw.clicked.connect(self._on_reset_keywords)
        h_bottom.addWidget(btn_reset_kw)
        layout.addLayout(h_bottom)

        self.tab_widget.addTab(tab, "判定キーワード設定")

    def _create_files_tab(self):
        """モデルファイル個別指定タブの作成"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        desc_label = QLabel(
            "特定のモデルファイル（.pmx / .pmd / .x）に対して種別を明示的に指定します（キーワード判定より最優先されます）。\n"
            "※キャラクターモデルは自動判定されるため個別指定への登録は不要です。ここではステージやスカイドームのみを登録してください。"
        )
        desc_label.setStyleSheet("color: #bdc3c7; font-size: 11px;")
        layout.addWidget(desc_label)

        # 操作バー
        bar_layout = QHBoxLayout()
        btn_add_file = QPushButton("ファイルを選択して追加...")
        btn_add_file.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold; padding: 6px 12px;")
        btn_add_file.clicked.connect(self._on_browse_and_add_files)
        bar_layout.addWidget(btn_add_file)

        btn_del_file = QPushButton("選択項目を削除")
        btn_del_file.setStyleSheet("background-color: #c0392b; color: white; padding: 6px 12px;")
        btn_del_file.clicked.connect(self._on_delete_file_row)
        bar_layout.addWidget(btn_del_file)

        bar_layout.addStretch()
        layout.addLayout(bar_layout)

        # テーブルウィジェット
        self.table_files = QTableWidget()
        self.table_files.setColumnCount(3)
        self.table_files.setHorizontalHeaderLabels(["ファイル名", "指定種別", "ファイルパス"])
        self.table_files.setStyleSheet("""
            QTableWidget {
                background: #1e272e;
                color: #ecf0f1;
                border: 1px solid #34495e;
                gridline-color: #2f3640;
            }
            QHeaderView::section {
                background: #2f3640;
                color: #ecf0f1;
                font-weight: bold;
                border: 1px solid #34495e;
                padding: 4px;
            }
        """)
        self.table_files.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table_files.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table_files.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_files.setColumnWidth(0, 180)
        self.table_files.setColumnWidth(1, 150)
        layout.addWidget(self.table_files)

        self.tab_widget.addTab(tab, "モデルファイル個別指定")

    def _load_data_to_ui(self):
        """マネージャーからデータをUIに反映"""
        # キーワードの読み込み
        self.list_dome_keywords.clear()
        for kw in self.manager.skydome_keywords:
            self.list_dome_keywords.addItem(kw)

        self.list_stage_keywords.clear()
        for kw in self.manager.stage_keywords:
            self.list_stage_keywords.addItem(kw)

        # 個別指定ファイルの読み込み
        self.table_files.setRowCount(0)
        for path_key, kind in sorted(self.manager.file_overrides.items()):
            self._add_file_row(path_key, kind)

    def _add_file_row(self, file_path, kind="stage"):
        """テーブルに行を追加"""
        row = self.table_files.rowCount()
        self.table_files.insertRow(row)

        file_name = os.path.basename(file_path)

        # ファイル名アイテム
        name_item = QTableWidgetItem(file_name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        self.table_files.setItem(row, 0, name_item)

        # 種別コンボボックス（ステージまたはスカイドームのみ）
        cb_kind = QComboBox()
        cb_kind.setStyleSheet("background: #2f3640; color: #ecf0f1; padding: 2px;")
        cb_kind.addItem("大型ステージ (床・背景)", "stage")
        cb_kind.addItem("スカイドーム (空・天球)", "skydome")

        # 該当項目の選択
        idx = cb_kind.findData(kind)
        if idx >= 0:
            cb_kind.setCurrentIndex(idx)
        self.table_files.setCellWidget(row, 1, cb_kind)

        # ファイルパスアイテム
        path_item = QTableWidgetItem(file_path)
        path_item.setFlags(path_item.flags() & ~Qt.ItemIsEditable)
        self.table_files.setItem(row, 2, path_item)

    def _on_add_dome_keyword(self):
        kw = self.edit_dome_keyword.text().strip()
        if not kw:
            return
        # 重複チェック
        items = [self.list_dome_keywords.item(i).text() for i in range(self.list_dome_keywords.count())]
        if kw not in items:
            self.list_dome_keywords.addItem(kw)
        self.edit_dome_keyword.clear()

    def _on_add_stage_keyword(self):
        kw = self.edit_stage_keyword.text().strip()
        if not kw:
            return
        items = [self.list_stage_keywords.item(i).text() for i in range(self.list_stage_keywords.count())]
        if kw not in items:
            self.list_stage_keywords.addItem(kw)
        self.edit_stage_keyword.clear()

    def _on_delete_list_item(self, list_widget):
        selected = list_widget.selectedItems()
        for item in selected:
            row = list_widget.row(item)
            list_widget.takeItem(row)

    def _on_reset_keywords(self):
        res = QMessageBox.question(
            self,
            "初期値復帰の確認",
            "スカイドームおよび大型ステージの判定キーワードを初期デフォルト値に戻しますか？\n（モデルファイルの個別指定は保持されます）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if res == QMessageBox.Yes:
            self.manager.reset_to_defaults()
            self._load_data_to_ui()

    def _on_browse_and_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "指定するモデルファイルを選択",
            "",
            "MMDモデルファイル (*.pmx *.pmd *.x);;すべてのファイル (*.*)"
        )
        if not files:
            return

        # 登録済みパスの取得
        existing_paths = set()
        for r in range(self.table_files.rowCount()):
            p_item = self.table_files.item(r, 2)
            if p_item:
                existing_paths.add(p_item.text())

        for fp in files:
            norm_fp = os.path.normpath(fp).replace("\\", "/")
            if norm_fp not in existing_paths:
                # デフォルト種別の推測（名前に skydome 等があればスカイドーム、それ以外はステージ）
                f_lower = os.path.basename(norm_fp).lower()
                def_kind = "skydome" if any(k in f_lower for k in ["skydome", "dome", "ドーム", "天球", "sky", "空"]) else "stage"
                self._add_file_row(norm_fp, def_kind)
                existing_paths.add(norm_fp)

    def _on_delete_file_row(self):
        selected_rows = sorted(set(idx.row() for idx in self.table_files.selectedIndexes()), reverse=True)
        if not selected_rows:
            QMessageBox.information(self, "案内", "削除対象の行を選択してください。")
            return
        for r in selected_rows:
            self.table_files.removeRow(r)

    def _on_save_and_apply(self):
        """設定を保存し、シーン内のシャドウおよび地面影プレーンへ即時反映"""
        # キーワードの回収
        dome_kws = [self.list_dome_keywords.item(i).text().strip() for i in range(self.list_dome_keywords.count())]
        stage_kws = [self.list_stage_keywords.item(i).text().strip() for i in range(self.list_stage_keywords.count())]

        self.manager.skydome_keywords = [k for k in dome_kws if k]
        self.manager.stage_keywords = [k for k in stage_kws if k]

        # 個別指定ファイルの回収
        new_overrides = {}
        for r in range(self.table_files.rowCount()):
            p_item = self.table_files.item(r, 2)
            cb_widget = self.table_files.cellWidget(r, 1)
            if p_item and cb_widget:
                fp = p_item.text().strip()
                kind = cb_widget.currentData()
                if fp and kind:
                    norm_path = os.path.normpath(fp).replace("\\", "/")
                    new_overrides[norm_path] = kind

        self.manager.file_overrides = new_overrides

        # JSONファイルへの書き込み保存
        success = self.manager.save_settings()
        if not success:
            QMessageBox.critical(self, "エラー", "設定ファイルの保存に失敗しました。")
            return

        # 現在のMayaシーンへ設定を即時再適用
        try:
            pmxpaimaya.optimize_model_meshes_for_mmd_lighting(auto_stage_detect=True)
            msg = "設定を保存し、現在のシーンのモデル判定とシャドウ設定を更新しました。"
        except Exception as e:
            msg = f"設定を保存しました（シーン更新時に軽微なエラー: {e}）。"

        QMessageBox.information(self, "設定完了", msg)
        self.accept()


def show_model_classifier_dialog(parent=None):
    """ダイアログを表示するヘルパー関数"""
    dlg = ModelClassifierDialog(parent=parent)
    return dlg.exec_()
