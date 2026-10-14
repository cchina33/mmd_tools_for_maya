# -*- coding: utf-8 -*-
"""
ユーザー辞書・対応表設定ダイアログ (ユーザー登録辞書 / ボーン日英辞書 / HumanIK辞書 / 日本語ローマ字辞書)
PySide6 (Maya 2025+) および PySide2 (Maya 2022-2024) 両対応。
user_dictionary.json、bone_dict.json、hik_dict.json、jaka_dict.json の対応表を一覧表示・追加・編集・保存します。
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
        load_bone_dict_json, save_bone_dict_json,
        load_hik_dict_json, save_hik_dict_json,
        load_jaka_dict_json, save_jaka_dict_json,
        load_user_settings, save_user_settings, get_default_settings
    )
except Exception:
    from asset.user_dict_manager import (
        load_bone_dict_json, save_bone_dict_json,
        load_hik_dict_json, save_hik_dict_json,
        load_jaka_dict_json, save_jaka_dict_json,
        load_user_settings, save_user_settings, get_default_settings
    )

_user_dict_dialog_instance = None

class UserDictDialog(QtWidgets.QDialog):
    """ユーザー辞書・対応表設定ダイアログ"""

    def __init__(self, parent=None):
        super(UserDictDialog, self).__init__(parent)
        self.setWindowTitle("ユーザー辞書・対応表設定 (ユーザー登録 / ボーン / HumanIK / 名称変換)")
        self.resize(880, 720)
        self.setMinimumSize(700, 540)

        # ウィンドウフラグ設定
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)

        self._init_ui()
        self._load_data_to_ui()

    def _init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 説明バナー
        info_box = QtWidgets.QFrame()
        info_box.setStyleSheet(
            "background-color: #1e262f; border: 1px solid #324759; border-radius: 6px; padding: 10px;"
        )
        info_layout = QtWidgets.QVBoxLayout(info_box)
        info_layout.setSpacing(6)

        lbl_title = QtWidgets.QLabel("【対応表JSONカスタマイズ】")
        lbl_title.setStyleSheet("color: #70b5f5; font-weight: bold; font-size: 13px;")
        info_layout.addWidget(lbl_title)

        lbl_desc = QtWidgets.QLabel(
            "ユーザー登録辞書（user_dictionary.json）、MMD標準ボーンの日英対応表、HumanIKキャラクタライズ定義、および漢字のローマ字変換ルールを編集・追加できます。\n"
            "各対応表はJSONファイルとして保存され、次回インポートや解析時に即座に反映されます。"
        )
        lbl_desc.setStyleSheet("color: #cfd8dc; font-size: 12px; line-height: 140%;")
        lbl_desc.setWordWrap(True)
        info_layout.addWidget(lbl_desc)

        main_layout.addWidget(info_box)

        # タブウィジェット
        self.tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # タブ: ユーザー登録辞書 (user_dictionary.json)
        self.tab_user_dict = QtWidgets.QWidget()
        self._setup_user_dict_tab()
        self.tab_widget.addTab(self.tab_user_dict, "ユーザー登録辞書 (user_dictionary)")

        # タブ: ボーン日英辞書 (bone_dict.json)
        self.tab_bone = QtWidgets.QWidget()
        self._setup_bone_tab()
        self.tab_widget.addTab(self.tab_bone, "標準ボーン日英辞書 (bone_dict)")

        # タブ: HumanIK ジョイント対応辞書 (hik_dict.json)
        self.tab_hik = QtWidgets.QWidget()
        self._setup_hik_tab()
        self.tab_widget.addTab(self.tab_hik, "HumanIK 対応辞書 (hik_dict)")

        # タブ: 日本語ローマ字変換辞書 (jaka_dict.json)
        self.tab_jaka = QtWidgets.QWidget()
        self._setup_jaka_tab()
        self.tab_widget.addTab(self.tab_jaka, "標準名称変換ルール (jaka_dict)")

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

    def _setup_user_dict_tab(self):
        """ユーザー登録辞書タブのUI構築 (custom_bone_dict & custom_name_translations)"""
        layout = QtWidgets.QVBoxLayout(self.tab_user_dict)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 上段: カスタムボーン辞書
        grp_user_bone = QtWidgets.QGroupBox("カスタム登録ボーン辞書 (ユーザー定義のボーン和名: 英名ペア)")
        grp_user_bone.setStyleSheet("QGroupBox { font-weight: bold; color: #64b5f6; }")
        layout_user_bone = QtWidgets.QVBoxLayout(grp_user_bone)
        layout_user_bone.setSpacing(6)

        self.table_user_bone = QtWidgets.QTableWidget(0, 2)
        self.table_user_bone.setHorizontalHeaderLabels(["カスタム日本語ボーン名", "カスタム英語ボーン名"])
        self.table_user_bone.horizontalHeader().setStretchLastSection(True)
        self.table_user_bone.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_user_bone.setAlternatingRowColors(True)
        layout_user_bone.addWidget(self.table_user_bone)

        tbl_bone_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_user_bone_add = QtWidgets.QPushButton("行を追加")
        self.btn_user_bone_add.clicked.connect(lambda: self._add_table_row(self.table_user_bone, "", ""))
        self.btn_user_bone_del = QtWidgets.QPushButton("選択行を削除")
        self.btn_user_bone_del.clicked.connect(lambda: self._remove_table_row(self.table_user_bone))
        tbl_bone_btn_layout.addWidget(self.btn_user_bone_add)
        tbl_bone_btn_layout.addWidget(self.btn_user_bone_del)
        tbl_bone_btn_layout.addStretch()
        layout_user_bone.addLayout(tbl_bone_btn_layout)
        layout.addWidget(grp_user_bone)

        # 中段: カスタムモーフ辞書
        grp_user_morph = QtWidgets.QGroupBox("カスタム登録モーフ辞書 (ユーザー定義のモーフ和名: 英名ペア)")
        grp_user_morph.setStyleSheet("QGroupBox { font-weight: bold; color: #ffb74d; }")
        layout_user_morph = QtWidgets.QVBoxLayout(grp_user_morph)
        layout_user_morph.setSpacing(6)

        self.table_user_morph = QtWidgets.QTableWidget(0, 2)
        self.table_user_morph.setHorizontalHeaderLabels(["カスタム日本語モーフ名", "カスタム英語モーフ名"])
        self.table_user_morph.horizontalHeader().setStretchLastSection(True)
        self.table_user_morph.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_user_morph.setAlternatingRowColors(True)
        layout_user_morph.addWidget(self.table_user_morph)

        tbl_morph_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_user_morph_add = QtWidgets.QPushButton("行を追加")
        self.btn_user_morph_add.clicked.connect(lambda: self._add_table_row(self.table_user_morph, "", ""))
        self.btn_user_morph_del = QtWidgets.QPushButton("選択行を削除")
        self.btn_user_morph_del.clicked.connect(lambda: self._remove_table_row(self.table_user_morph))
        tbl_morph_btn_layout.addWidget(self.btn_user_morph_add)
        tbl_morph_btn_layout.addWidget(self.btn_user_morph_del)
        tbl_morph_btn_layout.addStretch()
        layout_user_morph.addLayout(tbl_morph_btn_layout)
        layout.addWidget(grp_user_morph)

        # 下段: カスタム名称変換ルール
        grp_user_name = QtWidgets.QGroupBox("カスタム名称変換ルール (未登録漢字・特定記号のローマ字置換ルール)")
        grp_user_name.setStyleSheet("QGroupBox { font-weight: bold; color: #81c784; }")
        layout_user_name = QtWidgets.QVBoxLayout(grp_user_name)
        layout_user_name.setSpacing(6)

        self.table_user_name = QtWidgets.QTableWidget(0, 2)
        self.table_user_name.setHorizontalHeaderLabels(["変換前文字列 (漢字/中国語/記号)", "変換後ローマ字/英字"])
        self.table_user_name.horizontalHeader().setStretchLastSection(True)
        self.table_user_name.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_user_name.setAlternatingRowColors(True)
        layout_user_name.addWidget(self.table_user_name)

        tbl_name_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_user_name_add = QtWidgets.QPushButton("行を追加")
        self.btn_user_name_add.clicked.connect(lambda: self._add_table_row(self.table_user_name, "", ""))
        self.btn_user_name_del = QtWidgets.QPushButton("選択行を削除")
        self.btn_user_name_del.clicked.connect(lambda: self._remove_table_row(self.table_user_name))
        tbl_name_btn_layout.addWidget(self.btn_user_name_add)
        tbl_name_btn_layout.addWidget(self.btn_user_name_del)
        tbl_name_btn_layout.addStretch()
        layout_user_name.addLayout(tbl_name_btn_layout)
        layout.addWidget(grp_user_name)

    def _setup_bone_tab(self):
        """標準ボーン日英辞書タブのUI構築"""
        layout = QtWidgets.QVBoxLayout(self.tab_bone)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        lbl_info = QtWidgets.QLabel(
            "MMDボーンの日本語名（和名）と標準英語名（英名）の対応表です。標準ボーンから特殊ボーンまで自由に確認・追加・編集できます。"
        )
        lbl_info.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        layout.addWidget(lbl_info)

        self.table_bone = QtWidgets.QTableWidget(0, 2)
        self.table_bone.setHorizontalHeaderLabels(["日本語ボーン名 (和名)", "英語ボーン名 (英名)"])
        self.table_bone.horizontalHeader().setStretchLastSection(True)
        self.table_bone.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_bone.setAlternatingRowColors(True)
        layout.addWidget(self.table_bone)

        tbl_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_bone_add_row = QtWidgets.QPushButton("行を追加")
        self.btn_bone_add_row.clicked.connect(lambda: self._add_table_row(self.table_bone, "", ""))
        self.btn_bone_del_row = QtWidgets.QPushButton("選択行を削除")
        self.btn_bone_del_row.clicked.connect(lambda: self._remove_table_row(self.table_bone))

        tbl_btn_layout.addWidget(self.btn_bone_add_row)
        tbl_btn_layout.addWidget(self.btn_bone_del_row)
        tbl_btn_layout.addStretch()
        layout.addLayout(tbl_btn_layout)

    def _setup_hik_tab(self):
        """HumanIK対応辞書タブのUI構築"""
        layout = QtWidgets.QVBoxLayout(self.tab_hik)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        lbl_info = QtWidgets.QLabel(
            "HumanIKキャラクタライズに使用するジョイントID、日本語ボーン名、およびマッチング用正規表現パターンです。"
        )
        lbl_info.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        layout.addWidget(lbl_info)

        self.table_hik = QtWidgets.QTableWidget(0, 3)
        self.table_hik.setHorizontalHeaderLabels(["HumanIK ID (数値)", "日本語ボーン名", "正規表現パターン"])
        self.table_hik.horizontalHeader().setStretchLastSection(True)
        self.table_hik.setColumnWidth(0, 120)
        self.table_hik.setColumnWidth(1, 200)
        self.table_hik.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_hik.setAlternatingRowColors(True)
        layout.addWidget(self.table_hik)

        tbl_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_hik_add_row = QtWidgets.QPushButton("行を追加")
        self.btn_hik_add_row.clicked.connect(lambda: self._add_hik_table_row(self.table_hik, "", "", ""))
        self.btn_hik_del_row = QtWidgets.QPushButton("選択行を削除")
        self.btn_hik_del_row.clicked.connect(lambda: self._remove_table_row(self.table_hik))

        tbl_btn_layout.addWidget(self.btn_hik_add_row)
        tbl_btn_layout.addWidget(self.btn_hik_del_row)
        tbl_btn_layout.addStretch()
        layout.addLayout(tbl_btn_layout)

    def _setup_jaka_tab(self):
        """標準日本語ローマ字変換辞書タブのUI構築"""
        layout = QtWidgets.QVBoxLayout(self.tab_jaka)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        lbl_info = QtWidgets.QLabel(
            "Mayaノード名生成時（jaka.py）に特定の漢字・単語を任意の英字文字列へ置換する変換ルールです。"
        )
        lbl_info.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        layout.addWidget(lbl_info)

        self.table_jaka = QtWidgets.QTableWidget(0, 2)
        self.table_jaka.setHorizontalHeaderLabels(["変換前文字列 (漢字/中国語/記号)", "変換後ローマ字/英字"])
        self.table_jaka.horizontalHeader().setStretchLastSection(True)
        self.table_jaka.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_jaka.setAlternatingRowColors(True)
        layout.addWidget(self.table_jaka)

        tbl_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_jaka_add_row = QtWidgets.QPushButton("行を追加")
        self.btn_jaka_add_row.clicked.connect(lambda: self._add_table_row(self.table_jaka, "", ""))
        self.btn_jaka_del_row = QtWidgets.QPushButton("選択行を削除")
        self.btn_jaka_del_row.clicked.connect(lambda: self._remove_table_row(self.table_jaka))

        tbl_btn_layout.addWidget(self.btn_jaka_add_row)
        tbl_btn_layout.addWidget(self.btn_jaka_del_row)
        tbl_btn_layout.addStretch()
        layout.addLayout(tbl_btn_layout)

    def _add_table_row(self, table_widget, col1_text="", col2_text=""):
        row = table_widget.rowCount()
        table_widget.insertRow(row)
        table_widget.setItem(row, 0, QtWidgets.QTableWidgetItem(str(col1_text)))
        table_widget.setItem(row, 1, QtWidgets.QTableWidgetItem(str(col2_text)))

    def _add_hik_table_row(self, table_widget, col0_text="", col1_text="", col2_text=""):
        row = table_widget.rowCount()
        table_widget.insertRow(row)
        table_widget.setItem(row, 0, QtWidgets.QTableWidgetItem(str(col0_text)))
        table_widget.setItem(row, 1, QtWidgets.QTableWidgetItem(str(col1_text)))
        table_widget.setItem(row, 2, QtWidgets.QTableWidgetItem(str(col2_text)))

    def _remove_table_row(self, table_widget):
        rows = sorted(set(idx.row() for idx in table_widget.selectedIndexes()), reverse=True)
        for r in rows:
            table_widget.removeRow(r)

    def _load_data_to_ui(self):
        # ユーザー登録辞書 (user_dictionary.json)
        user_settings = load_user_settings()
        self.table_user_bone.setRowCount(0)
        for k, v in sorted(user_settings.get("custom_bone_dict", {}).items()):
            self._add_table_row(self.table_user_bone, str(k), str(v))

        self.table_user_morph.setRowCount(0)
        for k, v in sorted(user_settings.get("custom_morph_dict", {}).items()):
            self._add_table_row(self.table_user_morph, str(k), str(v))

        self.table_user_name.setRowCount(0)
        for k, v in sorted(user_settings.get("custom_name_translations", {}).items()):
            self._add_table_row(self.table_user_name, str(k), str(v))

        # 標準ボーン日英辞書 (bone_dict.json)
        bone_data = load_bone_dict_json()
        self.table_bone.setRowCount(0)
        for k, v in sorted(bone_data.items()):
            self._add_table_row(self.table_bone, str(k), str(v))

        # HumanIK 対応辞書 (hik_dict.json)
        hik_data = load_hik_dict_json()
        self.table_hik.setRowCount(0)
        for k in sorted(hik_data.keys()):
            v = hik_data[k]
            label = v[0] if len(v) > 0 else ""
            pattern = v[1] if len(v) > 1 else ""
            self._add_hik_table_row(self.table_hik, str(k), label, pattern)

        # 標準日本語ローマ字辞書 (jaka_dict.json)
        jaka_data = load_jaka_dict_json()
        self.table_jaka.setRowCount(0)
        for k, v in sorted(jaka_data.items()):
            self._add_table_row(self.table_jaka, str(k), str(v))

    def _on_save(self):
        # ユーザー登録辞書収集 (user_dictionary.json)
        user_bone_dict = {}
        for r in range(self.table_user_bone.rowCount()):
            k_item = self.table_user_bone.item(r, 0)
            v_item = self.table_user_bone.item(r, 1)
            k = k_item.text().strip() if k_item else ""
            v = v_item.text().strip() if v_item else ""
            if k and v:
                user_bone_dict[k] = v

        user_morph_dict = {}
        for r in range(self.table_user_morph.rowCount()):
            k_item = self.table_user_morph.item(r, 0)
            v_item = self.table_user_morph.item(r, 1)
            k = k_item.text().strip() if k_item else ""
            v = v_item.text().strip() if v_item else ""
            if k and v:
                user_morph_dict[k] = v

        user_name_trans = {}
        for r in range(self.table_user_name.rowCount()):
            k_item = self.table_user_name.item(r, 0)
            v_item = self.table_user_name.item(r, 1)
            k = k_item.text().strip() if k_item else ""
            v = v_item.text().strip() if v_item else ""
            if k and v:
                user_name_trans[k] = v

        user_settings = load_user_settings()
        user_settings["custom_bone_dict"] = user_bone_dict
        user_settings["custom_morph_dict"] = user_morph_dict
        user_settings["custom_name_translations"] = user_name_trans
        ok0 = save_user_settings(user_settings)

        # 標準ボーン日英辞書収集 (bone_dict.json)
        bone_dict = {}
        for r in range(self.table_bone.rowCount()):
            k_item = self.table_bone.item(r, 0)
            v_item = self.table_bone.item(r, 1)
            k = k_item.text().strip() if k_item else ""
            v = v_item.text().strip() if v_item else ""
            if k and v:
                bone_dict[k] = v

        # HumanIK 対応辞書収集 (hik_dict.json)
        hik_dict = {}
        for r in range(self.table_hik.rowCount()):
            id_item = self.table_hik.item(r, 0)
            lbl_item = self.table_hik.item(r, 1)
            pat_item = self.table_hik.item(r, 2)
            raw_id = id_item.text().strip() if id_item else ""
            lbl = lbl_item.text().strip() if lbl_item else ""
            pat = pat_item.text().strip() if pat_item else ""
            if raw_id and lbl:
                try:
                    item_id = int(raw_id)
                    hik_dict[item_id] = [lbl, pat]
                except ValueError:
                    pass

        # 標準日本語ローマ字辞書収集 (jaka_dict.json)
        jaka_dict = {}
        for r in range(self.table_jaka.rowCount()):
            k_item = self.table_jaka.item(r, 0)
            v_item = self.table_jaka.item(r, 1)
            k = k_item.text().strip() if k_item else ""
            v = v_item.text().strip() if v_item else ""
            if k and v:
                jaka_dict[k] = v

        ok1 = save_bone_dict_json(bone_dict)
        ok2 = save_hik_dict_json(hik_dict)
        ok3 = save_jaka_dict_json(jaka_dict)

        if ok0 and ok1 and ok2 and ok3:
            QtWidgets.QMessageBox.information(
                self, "保存完了",
                "ユーザー登録辞書 (user_dictionary.json)、ボーン日英辞書、HumanIK対応表、および名称変換辞書を保存しました。\n次回インポートおよびキャラクタライズ時に即座に反映されます。"
            )
        else:
            QtWidgets.QMessageBox.critical(self, "保存失敗", "一部の辞書ファイルの保存中にエラーが発生しました。")

    def _on_reset_default(self):
        ret = QtWidgets.QMessageBox.question(
            self,
            "初期化の確認",
            "ユーザー登録辞書、ボーン日英辞書、HumanIK対応表、名称変換辞書を初期デフォルト値に戻しますか？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if ret == QtWidgets.QMessageBox.Yes:
            # デフォルト値の再読込
            try:
                from ..asset import bone_dict, hik, jaka
            except Exception:
                from asset import bone_dict, hik, jaka

            save_bone_dict_json(bone_dict.BASE_BONE_MAP_JA_TO_EN)
            save_hik_dict_json(hik.dic_hik)
            save_jaka_dict_json(jaka.MMD_KANJI_DICT)

            defaults = get_default_settings()
            current = load_user_settings()
            current["custom_bone_dict"] = defaults.get("custom_bone_dict", {})
            current["custom_morph_dict"] = defaults.get("custom_morph_dict", {})
            current["custom_name_translations"] = defaults.get("custom_name_translations", {})
            save_user_settings(current)

            self._load_data_to_ui()
            QtWidgets.QMessageBox.information(self, "初期化完了", "すべての対応表を初期デフォルト値に戻しました。")


def show_user_dict_dialog():
    """ユーザー辞書・対応表設定ダイアログを表示します"""
    global _user_dict_dialog_instance

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

    if _user_dict_dialog_instance is not None:
        try:
            _user_dict_dialog_instance.close()
            _user_dict_dialog_instance.deleteLater()
        except Exception:
            pass
        _user_dict_dialog_instance = None

    _user_dict_dialog_instance = UserDictDialog(parent)
    _user_dict_dialog_instance.show()
    _user_dict_dialog_instance.raise_()
    _user_dict_dialog_instance.activateWindow()
