# -*- coding: utf-8 -*-
"""
高度なユーザー辞書・マテリアル保護設定ダイアログ (上級者向け)
PySide6 (Maya 2025+) および PySide2 (Maya 2022-2024) 両対応。
マテリアル保護キーワード、Toon除外キーワードを左右（日本語 / 英語）に分けて表示・編集します。
"""

import sys
import os

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    PYSIDE_VER = 6
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
        PYSIDE_VER = 2
    except ImportError:
        raise ImportError("PySide6 または PySide2 が見つかりません。")

import maya.cmds as mc
try:
    from ..asset.user_dict_manager import (
        load_user_settings, save_user_settings, get_default_settings
    )
except Exception:
    from asset.user_dict_manager import (
        load_user_settings, save_user_settings, get_default_settings
    )

# ダイアログシングルトン参照
_advanced_dict_dialog_instance = None

class AdvancedDictDialog(QtWidgets.QDialog):
    """高度なユーザー辞書・マテリアル設定ダイアログ"""

    def __init__(self, parent=None):
        super(AdvancedDictDialog, self).__init__(parent)
        self.setWindowTitle("高度なユーザー辞書・マテリアル設定 (上級者向け)")
        self.resize(760, 600)
        self.setMinimumSize(620, 480)

        # ウィンドウフラグ設定 (Mayaメインウィンドウの子として前面表示)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)

        self._init_ui()
        self._load_data_to_ui()

    def _init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 警告バナー
        warning_box = QtWidgets.QFrame()
        warning_box.setStyleSheet(
            "background-color: #2b1f14; border: 1px solid #c27d00; border-radius: 4px; padding: 6px;"
        )
        warning_layout = QtWidgets.QHBoxLayout(warning_box)
        warning_layout.setContentsMargins(8, 4, 8, 4)
        warning_label = QtWidgets.QLabel(
            "【上級者向け機能】 ここでの変更はモデルインポート時のマテリアル構築および名称変換に直接反映されます。"
        )
        warning_label.setStyleSheet("color: #ffaa00; font-weight: bold;")
        warning_label.setWordWrap(True)
        warning_layout.addWidget(warning_label)
        main_layout.addWidget(warning_box)

        # タブウィジェット
        self.tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # タブ1: マテリアル保護＆Toon除外設定 (左右で日本語/英語を分離)
        self.tab_mat = QtWidgets.QWidget()
        self._setup_material_tab()
        self.tab_widget.addTab(self.tab_mat, "マテリアル保護・Toon除外")

        # タブ2: ボーン日英変換辞書
        self.tab_bone = QtWidgets.QWidget()
        self._setup_bone_tab()
        self.tab_widget.addTab(self.tab_bone, "ボーン日英辞書")

        # タブ3: ノード名カスタム置換
        self.tab_name = QtWidgets.QWidget()
        self._setup_name_tab()
        self.tab_widget.addTab(self.tab_name, "名称変換ルール")

        # 下部ボタングループ
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_reset_default = QtWidgets.QPushButton("初期デフォルトに戻す")
        self.btn_reset_default.setStyleSheet(
            "background-color: #4a2828; color: #ffaaaa; border: 1px solid #773333; padding: 6px 14px; border-radius: 4px;"
        )
        self.btn_reset_default.clicked.connect(self._on_reset_default)
        btn_layout.addWidget(self.btn_reset_default)

        btn_layout.addStretch()

        self.btn_save = QtWidgets.QPushButton("保存して適用")
        self.btn_save.setStyleSheet(
            "background-color: #1e5631; color: #ffffff; font-weight: bold; border: 1px solid #2e7d32; padding: 6px 20px; border-radius: 4px;"
        )
        self.btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(self.btn_save)

        self.btn_close = QtWidgets.QPushButton("閉じる")
        self.btn_close.setStyleSheet(
            "background-color: #333333; color: #dddddd; border: 1px solid #555555; padding: 6px 14px; border-radius: 4px;"
        )
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_close)

        main_layout.addLayout(btn_layout)

    def _setup_material_tab(self):
        """マテリアル設定タブ: 日本語と英語を左右に分けて表示"""
        layout = QtWidgets.QVBoxLayout(self.tab_mat)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # 1. 顔・肌・表情保護キーワードグループ (左右2列)
        grp_skin = QtWidgets.QGroupBox("顔・肌・表情マテリアル判定キーワード (テカリ・スペキュラ除去対象)")
        grp_skin_layout = QtWidgets.QHBoxLayout(grp_skin)
        grp_skin_layout.setSpacing(12)

        # 左側: 日本語キーワード
        box_skin_ja = QtWidgets.QVBoxLayout()
        lbl_skin_ja = QtWidgets.QLabel("日本語キーワード (和名)")
        lbl_skin_ja.setStyleSheet("font-weight: bold; color: #64b5f6;")
        self.list_skin_ja = QtWidgets.QListWidget()
        skin_ja_input_layout = QtWidgets.QHBoxLayout()
        self.txt_skin_ja = QtWidgets.QLineEdit()
        self.txt_skin_ja.setPlaceholderText("追加 (例: ほほ, 唇)")
        self.btn_skin_ja_add = QtWidgets.QPushButton("追加")
        self.btn_skin_ja_add.clicked.connect(lambda: self._add_to_list(self.list_skin_ja, self.txt_skin_ja))
        self.btn_skin_ja_del = QtWidgets.QPushButton("削除")
        self.btn_skin_ja_del.clicked.connect(lambda: self._remove_from_list(self.list_skin_ja))
        skin_ja_input_layout.addWidget(self.txt_skin_ja)
        skin_ja_input_layout.addWidget(self.btn_skin_ja_add)
        skin_ja_input_layout.addWidget(self.btn_skin_ja_del)

        box_skin_ja.addWidget(lbl_skin_ja)
        box_skin_ja.addWidget(self.list_skin_ja)
        box_skin_ja.addLayout(skin_ja_input_layout)
        grp_skin_layout.addLayout(box_skin_ja)

        # 右側: 英語キーワード
        box_skin_en = QtWidgets.QVBoxLayout()
        lbl_skin_en = QtWidgets.QLabel("英語キーワード (English)")
        lbl_skin_en.setStyleSheet("font-weight: bold; color: #81c784;")
        self.list_skin_en = QtWidgets.QListWidget()
        skin_en_input_layout = QtWidgets.QHBoxLayout()
        self.txt_skin_en = QtWidgets.QLineEdit()
        self.txt_skin_en.setPlaceholderText("追加 (例: cheek, lip)")
        self.btn_skin_en_add = QtWidgets.QPushButton("追加")
        self.btn_skin_en_add.clicked.connect(lambda: self._add_to_list(self.list_skin_en, self.txt_skin_en))
        self.btn_skin_en_del = QtWidgets.QPushButton("削除")
        self.btn_skin_en_del.clicked.connect(lambda: self._remove_from_list(self.list_skin_en))
        skin_en_input_layout.addWidget(self.txt_skin_en)
        skin_en_input_layout.addWidget(self.btn_skin_en_add)
        skin_en_input_layout.addWidget(self.btn_skin_en_del)

        box_skin_en.addWidget(lbl_skin_en)
        box_skin_en.addWidget(self.list_skin_en)
        box_skin_en.addLayout(skin_en_input_layout)
        grp_skin_layout.addLayout(box_skin_en)

        layout.addWidget(grp_skin)

        # 2. Toon乗算除外キーワードグループ (左右2列)
        grp_toon = QtWidgets.QGroupBox("Toon乗算除外キーワード (瞳ハイライト等、明るさを常に維持する材質)")
        grp_toon_layout = QtWidgets.QHBoxLayout(grp_toon)
        grp_toon_layout.setSpacing(12)

        # 左側: 日本語キーワード
        box_toon_ja = QtWidgets.QVBoxLayout()
        lbl_toon_ja = QtWidgets.QLabel("日本語キーワード (和名)")
        lbl_toon_ja.setStyleSheet("font-weight: bold; color: #64b5f6;")
        self.list_toon_ja = QtWidgets.QListWidget()
        toon_ja_input_layout = QtWidgets.QHBoxLayout()
        self.txt_toon_ja = QtWidgets.QLineEdit()
        self.txt_toon_ja.setPlaceholderText("追加 (例: ハイライト, 白目)")
        self.btn_toon_ja_add = QtWidgets.QPushButton("追加")
        self.btn_toon_ja_add.clicked.connect(lambda: self._add_to_list(self.list_toon_ja, self.txt_toon_ja))
        self.btn_toon_ja_del = QtWidgets.QPushButton("削除")
        self.btn_toon_ja_del.clicked.connect(lambda: self._remove_from_list(self.list_toon_ja))
        toon_ja_input_layout.addWidget(self.txt_toon_ja)
        toon_ja_input_layout.addWidget(self.btn_toon_ja_add)
        toon_ja_input_layout.addWidget(self.btn_toon_ja_del)

        box_toon_ja.addWidget(lbl_toon_ja)
        box_toon_ja.addWidget(self.list_toon_ja)
        box_toon_ja.addLayout(toon_ja_input_layout)
        grp_toon_layout.addLayout(box_toon_ja)

        # 右側: 英語キーワード
        box_toon_en = QtWidgets.QVBoxLayout()
        lbl_toon_en = QtWidgets.QLabel("英語キーワード (English)")
        lbl_toon_en.setStyleSheet("font-weight: bold; color: #81c784;")
        self.list_toon_en = QtWidgets.QListWidget()
        toon_en_input_layout = QtWidgets.QHBoxLayout()
        self.txt_toon_en = QtWidgets.QLineEdit()
        self.txt_toon_en.setPlaceholderText("追加 (例: highlight, eyewhite)")
        self.btn_toon_en_add = QtWidgets.QPushButton("追加")
        self.btn_toon_en_add.clicked.connect(lambda: self._add_to_list(self.list_toon_en, self.txt_toon_en))
        self.btn_toon_en_del = QtWidgets.QPushButton("削除")
        self.btn_toon_en_del.clicked.connect(lambda: self._remove_from_list(self.list_toon_en))
        toon_en_input_layout.addWidget(self.txt_toon_en)
        toon_en_input_layout.addWidget(self.btn_toon_en_add)
        toon_en_input_layout.addWidget(self.btn_toon_en_del)

        box_toon_en.addWidget(lbl_toon_en)
        box_toon_en.addWidget(self.list_toon_en)
        box_toon_en.addLayout(toon_en_input_layout)
        grp_toon_layout.addLayout(box_toon_en)

        layout.addWidget(grp_toon)

    def _setup_bone_tab(self):
        layout = QtWidgets.QVBoxLayout(self.tab_bone)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        lbl_info = QtWidgets.QLabel("モデル特有の特殊なボーン名を標準英語ボーン名に対応付けるカスタムマッピングです。")
        lbl_info.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(lbl_info)

        self.table_bone = QtWidgets.QTableWidget(0, 2)
        self.table_bone.setHorizontalHeaderLabels(["日本語ボーン名 (和名)", "英語ボーン名 (英名)"])
        self.table_bone.horizontalHeader().setStretchLastSection(True)
        self.table_bone.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table_bone)

        tbl_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_bone_add_row = QtWidgets.QPushButton("行を追加")
        self.btn_bone_add_row.clicked.connect(lambda: self._add_table_row(self.table_bone))
        self.btn_bone_del_row = QtWidgets.QPushButton("選択行を削除")
        self.btn_bone_del_row.clicked.connect(lambda: self._remove_table_row(self.table_bone))

        tbl_btn_layout.addWidget(self.btn_bone_add_row)
        tbl_btn_layout.addWidget(self.btn_bone_del_row)
        tbl_btn_layout.addStretch()
        layout.addLayout(tbl_btn_layout)

    def _setup_name_tab(self):
        layout = QtWidgets.QVBoxLayout(self.tab_name)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        lbl_info = QtWidgets.QLabel("Mayaノード名生成時（jaka.py）に特定の漢字・単語を任意の英字文字列へ置換するカスタムルールです。")
        lbl_info.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(lbl_info)

        self.table_name = QtWidgets.QTableWidget(0, 2)
        self.table_name.setHorizontalHeaderLabels(["変換前文字列 (漢字/中国語/記号)", "変換後ローマ字/英字"])
        self.table_name.horizontalHeader().setStretchLastSection(True)
        self.table_name.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table_name)

        tbl_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_name_add_row = QtWidgets.QPushButton("行を追加")
        self.btn_name_add_row.clicked.connect(lambda: self._add_table_row(self.table_name))
        self.btn_name_del_row = QtWidgets.QPushButton("選択行を削除")
        self.btn_name_del_row.clicked.connect(lambda: self._remove_table_row(self.table_name))

        tbl_btn_layout.addWidget(self.btn_name_add_row)
        tbl_btn_layout.addWidget(self.btn_name_del_row)
        tbl_btn_layout.addStretch()
        layout.addLayout(tbl_btn_layout)

    def _add_to_list(self, list_widget, line_edit):
        text = line_edit.text().strip()
        if text:
            items = [list_widget.item(i).text() for i in range(list_widget.count())]
            if text not in items:
                list_widget.addItem(text)
            line_edit.clear()

    def _remove_from_list(self, list_widget):
        for item in list_widget.selectedItems():
            list_widget.takeItem(list_widget.row(item))

    def _add_table_row(self, table_widget, col1_text="", col2_text=""):
        row = table_widget.rowCount()
        table_widget.insertRow(row)
        table_widget.setItem(row, 0, QtWidgets.QTableWidgetItem(col1_text))
        table_widget.setItem(row, 1, QtWidgets.QTableWidgetItem(col2_text))

    def _remove_table_row(self, table_widget):
        rows = sorted(set(idx.row() for idx in table_widget.selectedIndexes()), reverse=True)
        for r in rows:
            table_widget.removeRow(r)

    def _load_data_to_ui(self, settings=None):
        if settings is None:
            settings = load_user_settings()

        # マテリアル保護キーワード (日本語 / 英語)
        self.list_skin_ja.clear()
        for kw in settings.get("face_skin_keywords_ja", []):
            self.list_skin_ja.addItem(kw)

        self.list_skin_en.clear()
        for kw in settings.get("face_skin_keywords_en", []):
            self.list_skin_en.addItem(kw)

        # Toon除外キーワード (日本語 / 英語)
        self.list_toon_ja.clear()
        for kw in settings.get("toon_bypass_keywords_ja", []):
            self.list_toon_ja.addItem(kw)

        self.list_toon_en.clear()
        for kw in settings.get("toon_bypass_keywords_en", []):
            self.list_toon_en.addItem(kw)

        # ボーン辞書テーブル
        self.table_bone.setRowCount(0)
        for k, v in settings.get("custom_bone_dict", {}).items():
            self._add_table_row(self.table_bone, str(k), str(v))

        # 名称変換テーブル
        self.table_name.setRowCount(0)
        for k, v in settings.get("custom_name_translations", {}).items():
            self._add_table_row(self.table_name, str(k), str(v))

    def _collect_data_from_ui(self):
        skin_ja = [self.list_skin_ja.item(i).text().strip() for i in range(self.list_skin_ja.count()) if self.list_skin_ja.item(i).text().strip()]
        skin_en = [self.list_skin_en.item(i).text().strip() for i in range(self.list_skin_en.count()) if self.list_skin_en.item(i).text().strip()]

        toon_ja = [self.list_toon_ja.item(i).text().strip() for i in range(self.list_toon_ja.count()) if self.list_toon_ja.item(i).text().strip()]
        toon_en = [self.list_toon_en.item(i).text().strip() for i in range(self.list_toon_en.count()) if self.list_toon_en.item(i).text().strip()]

        bone_dict = {}
        for r in range(self.table_bone.rowCount()):
            k_item = self.table_bone.item(r, 0)
            v_item = self.table_bone.item(r, 1)
            k = k_item.text().strip() if k_item else ""
            v = v_item.text().strip() if v_item else ""
            if k and v:
                bone_dict[k] = v

        name_trans = {}
        for r in range(self.table_name.rowCount()):
            k_item = self.table_name.item(r, 0)
            v_item = self.table_name.item(r, 1)
            k = k_item.text().strip() if k_item else ""
            v = v_item.text().strip() if v_item else ""
            if k and v:
                name_trans[k] = v

        return {
            "face_skin_keywords_ja": skin_ja,
            "face_skin_keywords_en": skin_en,
            "toon_bypass_keywords_ja": toon_ja,
            "toon_bypass_keywords_en": toon_en,
            "custom_bone_dict": bone_dict,
            "custom_name_translations": name_trans
        }

    def _on_save(self):
        data = self._collect_data_from_ui()
        success = save_user_settings(data)
        if success:
            QtWidgets.QMessageBox.information(self, "保存完了", "ユーザー辞書およびマテリアル設定を正常に保存しました。\n次回インポートおよびシーン修復時に即座に反映されます。")
        else:
            QtWidgets.QMessageBox.critical(self, "保存失敗", "設定の保存中にエラーが発生しました。")

    def _on_reset_default(self):
        ret = QtWidgets.QMessageBox.question(
            self,
            "初期化の確認",
            "すべてのマテリアル保護キーワード、Toon除外設定、ボーン辞書を安全な初期デフォルト値に戻しますか？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if ret == QtWidgets.QMessageBox.Yes:
            defaults = get_default_settings()
            self._load_data_to_ui(defaults)
            save_user_settings(defaults)
            QtWidgets.QMessageBox.information(self, "初期化完了", "設定を初期デフォルト値に戻しました。")

def show_advanced_dict_dialog():
    """
    上級者向け警告ダイアログを表示し、承認された場合のみ設定ダイアログを開きます。
    """
    global _advanced_dict_dialog_instance

    # 上級者向け確認ダイアログ
    confirm = QtWidgets.QMessageBox.warning(
        None,
        "上級者向け機能の警告",
        "【警告: 上級者専用設定】\n\n"
        "この設定は内部辞書、シェーダーマッピング、および名称変換ルールを変更します。\n"
        "誤った設定を行うと、モデルのインポートやToonシェーディング描画が意図通りに行われなくなる可能性があります。\n\n"
        "設定ダイアログを開きますか？",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.No
    )

    if confirm != QtWidgets.QMessageBox.Yes:
        return

    # ダイアログ生成・表示
    try:
        from maya import OpenMayaUI as omui
        if PYSIDE_VER == 6:
            from shiboken6 import wrapInstance
        else:
            from shiboken2 import wrapInstance
        ptr = omui.MQtUtil.mainWindow()
        parent = wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None
    except Exception:
        parent = None

    # 既存のダイアログがあれば閉じて破棄
    if _advanced_dict_dialog_instance is not None:
        try:
            _advanced_dict_dialog_instance.close()
            _advanced_dict_dialog_instance.deleteLater()
        except Exception:
            pass
        _advanced_dict_dialog_instance = None

    _advanced_dict_dialog_instance = AdvancedDictDialog(parent)
    _advanced_dict_dialog_instance.show()
    _advanced_dict_dialog_instance.raise_()
    _advanced_dict_dialog_instance.activateWindow()
