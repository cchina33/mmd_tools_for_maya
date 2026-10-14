# -*- coding: utf-8 -*-
"""
未登録モーフ名・ボーン名・漢字のユーザー辞書登録ダイアログ (user_dict_dialog.py)

PMXモデルインポート時に辞書に存在しないモーフ名やボーン名（未登録漢字）を検出し、
「登録のないモーフ名（またはボーン名）があります。ユーザー辞書に記録しますか？」と確認した上で、
英字・ローマ字を入力して辞書登録・再チェックを行うPySideダイアログを提供します。
"""

import os
import re

try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
        QMessageBox, QFrame, QApplication, QTabWidget, QWidget
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
except ImportError:
    from PySide2.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
        QMessageBox, QFrame, QApplication, QTabWidget, QWidget
    )
    from PySide2.QtCore import Qt
    from PySide2.QtGui import QFont

try:
    from .analyzer_core import find_unregistered_kanji_in_bones, find_unregistered_morphs
    from ..asset import jaka, user_dict_manager
except Exception:
    from pmx_analyzer.analyzer_core import find_unregistered_kanji_in_bones, find_unregistered_morphs
    from asset import jaka, user_dict_manager

# モダンダークスタイル
DIALOG_STYLE = """
QDialog {
    background-color: #2b2b2b;
    color: #e0e0e0;
}
QLabel {
    color: #e0e0e0;
}
QTabWidget::pane {
    border: 1px solid #444;
    background-color: #2b2b2b;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #1e1e1e;
    color: #aaaaaa;
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background-color: #2b2b2b;
    color: #52b7ff;
    border-top: 2px solid #52b7ff;
}
QTableWidget {
    background-color: #1e1e1e;
    color: #f0f0f0;
    gridline-color: #3d3d3d;
    border: 1px solid #444;
    border-radius: 4px;
    font-size: 13px;
}
QTableWidget::item {
    padding: 6px;
}
QHeaderView::section {
    background-color: #333333;
    color: #52b7ff;
    padding: 6px;
    font-weight: bold;
    border: 1px solid #444;
}
QLineEdit {
    background-color: #2d2d2d;
    color: #ffffff;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 4px 8px;
    font-size: 13px;
}
QLineEdit:focus {
    border: 1px solid #52b7ff;
}
QPushButton {
    background-color: #3d3d3d;
    color: #ffffff;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #4a4a4a;
}
QPushButton#btn_save {
    background-color: #2e6b9e;
    border: 1px solid #3b88c7;
}
QPushButton#btn_save:hover {
    background-color: #3b88c7;
}
"""

# パネル種別ラベル変換マップ
PANEL_NAME_MAP = {
    1: "まゆ (眉)",
    2: "目 (瞳)",
    3: "口 (リップ)",
    4: "その他"
}

class UserDictRegisterDialog(QDialog):
    """未登録モーフ名・ボーン名（漢字）に英名・ローマ字を記入して登録するダイアログ"""
    def __init__(self, parent=None, pmx_path=None, initial_tab=0):
        super(UserDictRegisterDialog, self).__init__(parent)
        self.pmx_path = pmx_path
        self.setWindowTitle("ユーザー辞書 モーフ名・ボーン名登録")
        self.resize(760, 520)
        self.setMinimumSize(600, 400)
        self.setStyleSheet(DIALOG_STYLE)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.input_fields_morphs = {} # モーフ名 -> QLineEdit
        self.input_fields_bones = {}  # 漢字 -> QLineEdit

        self._init_ui()
        self._refresh_tables()
        if initial_tab in [0, 1]:
            self.tabs.setCurrentIndex(initial_tab)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 説明ヘッダー
        title_lbl = QLabel("モーフ名・ボーン名 ユーザー辞書登録")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color: #52b7ff;")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(
            "モデル内に標準辞書およびユーザー辞書へ未登録のモーフ名またはボーン名（漢字）が検出されました。\n"
            "各項目の入力欄に英語名またはローマ字（半角英数）を入力し、「辞書に登録して再チェック」をクリックしてください。"
        )
        desc_lbl.setStyleSheet("color: #cccccc; line-height: 1.4;")
        layout.addWidget(desc_lbl)

        # タブ切り替えウィジェット
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # タブ: モーフ名登録
        self.tab_morph = QWidget()
        layout_morph = QVBoxLayout(self.tab_morph)
        layout_morph.setContentsMargins(8, 8, 8, 8)
        self.table_morph = QTableWidget()
        self.table_morph.setColumnCount(4)
        self.table_morph.setHorizontalHeaderLabels(["未登録モーフ名", "英語名 / ローマ字入力", "パネル種別", "未登録漢字"])
        hdr_m = self.table_morph.horizontalHeader()
        hdr_m.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr_m.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr_m.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr_m.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_morph.verticalHeader().setVisible(False)
        layout_morph.addWidget(self.table_morph)
        self.tabs.addTab(self.tab_morph, "モーフ名 登録")

        # タブ: ボーン名・漢字登録
        self.tab_bone = QWidget()
        layout_bone = QVBoxLayout(self.tab_bone)
        layout_bone.setContentsMargins(8, 8, 8, 8)
        self.table_bone = QTableWidget()
        self.table_bone.setColumnCount(3)
        self.table_bone.setHorizontalHeaderLabels(["未登録漢字", "ローマ字入力 (英数字)", "検出されたボーン名"])
        hdr_b = self.table_bone.horizontalHeader()
        hdr_b.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr_b.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr_b.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_bone.verticalHeader().setVisible(False)
        layout_bone.addWidget(self.table_bone)
        self.tabs.addTab(self.tab_bone, "ボーン名・漢字 登録")

        # ステータス表示ラベル
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #2ecc71; font-weight: bold;")
        layout.addWidget(self.status_lbl)

        # 下部ボタングループ
        h_btn = QHBoxLayout()
        h_btn.addStretch()

        self.btn_cancel = QPushButton("スキップ（閉じる）")
        self.btn_cancel.clicked.connect(self.reject)
        h_btn.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("辞書に登録して再チェック")
        self.btn_save.setObjectName("btn_save")
        self.btn_save.clicked.connect(self._save_and_recheck)
        h_btn.addWidget(self.btn_save)

        layout.addLayout(h_btn)

    def _refresh_tables(self):
        """未登録モーフおよびボーン漢字を再走査して各テーブルを更新します"""
        self.input_fields_morphs.clear()
        self.input_fields_bones.clear()
        self.table_morph.setRowCount(0)
        self.table_bone.setRowCount(0)

        unregistered_morphs = find_unregistered_morphs(self.pmx_path)
        unregistered_bones = find_unregistered_kanji_in_bones(self.pmx_path)

        # モーフテーブルの構築
        self.table_morph.setRowCount(len(unregistered_morphs))
        for row, item in enumerate(unregistered_morphs):
            m_name = item["name"]
            suggested = item.get("suggested_en", "")
            panel_id = item.get("panel", 0)
            panel_text = PANEL_NAME_MAP.get(panel_id, "その他")
            kanji_str = "、".join(item.get("unregistered_kanji", [])) or "なし"

            # モーフ名セル
            item_name = QTableWidgetItem(f"  {m_name}  ")
            item_name.setTextAlignment(Qt.AlignCenter)
            item_name.setFlags(Qt.ItemIsEnabled)
            font = QFont()
            font.setPointSize(12)
            font.setBold(True)
            item_name.setFont(font)
            self.table_morph.setItem(row, 0, item_name)

            # 英語名・ローマ字入力セル
            le = QLineEdit()
            le.setText(suggested)
            le.setPlaceholderText(f"例: {suggested or '英名を入力'}")
            self.table_morph.setCellWidget(row, 1, le)
            self.input_fields_morphs[m_name] = le

            # パネル種別セル
            item_panel = QTableWidgetItem(panel_text)
            item_panel.setTextAlignment(Qt.AlignCenter)
            item_panel.setFlags(Qt.ItemIsEnabled)
            self.table_morph.setItem(row, 2, item_panel)

            # 未登録漢字セル
            item_k = QTableWidgetItem(kanji_str)
            item_k.setTextAlignment(Qt.AlignCenter)
            item_k.setFlags(Qt.ItemIsEnabled)
            self.table_morph.setItem(row, 3, item_k)

        # ボーンテーブルの構築
        self.table_bone.setRowCount(len(unregistered_bones))
        for row, item in enumerate(unregistered_bones):
            kanji = item["kanji"]
            bone_list_str = ", ".join(item["bones"][:4])
            if len(item["bones"]) > 4:
                bone_list_str += f" 他 (計{len(item['bones'])}本)"

            # 漢字セル
            item_kanji = QTableWidgetItem(f"  {kanji}  ")
            item_kanji.setTextAlignment(Qt.AlignCenter)
            item_kanji.setFlags(Qt.ItemIsEnabled)
            font = QFont()
            font.setPointSize(13)
            font.setBold(True)
            item_kanji.setFont(font)
            self.table_bone.setItem(row, 0, item_kanji)

            # ローマ字入力セル
            le = QLineEdit()
            le.setPlaceholderText(f"例: {kanji} の読み（半角英字）")
            self.table_bone.setCellWidget(row, 1, le)
            self.input_fields_bones[kanji] = le

            # 出現ボーン名セル
            item_bones = QTableWidgetItem(bone_list_str)
            item_bones.setToolTip("\n".join(item["bones"]))
            item_bones.setFlags(Qt.ItemIsEnabled)
            self.table_bone.setItem(row, 2, item_bones)

        # タブのバッジ表記
        self.tabs.setTabText(0, f"モーフ名 登録 ({len(unregistered_morphs)})")
        self.tabs.setTabText(1, f"ボーン名・漢字 登録 ({len(unregistered_bones)})")

        if not unregistered_morphs and not unregistered_bones:
            self.status_lbl.setText("すべてのモーフ名およびボーン名が正常に辞書登録されています！")
            self.btn_save.setEnabled(False)
        else:
            msg_parts = []
            if unregistered_morphs:
                msg_parts.append(f"未登録モーフ名: {len(unregistered_morphs)} 件")
            if unregistered_bones:
                msg_parts.append(f"未登録漢字(ボーン): {len(unregistered_bones)} 件")
            self.status_lbl.setText(" / ".join(msg_parts))
            self.btn_save.setEnabled(True)

    def _save_and_recheck(self):
        """入力されたモーフ名および漢字ローマ字をユーザー辞書に保存し、再チェックを実行します"""
        new_morphs = {}
        for m_name, le in self.input_fields_morphs.items():
            text = le.text().strip()
            clean_val = re.sub(r'[^a-zA-Z0-9_]', '_', text)
            clean_val = re.sub(r'_+', '_', clean_val).strip('_')
            if clean_val:
                new_morphs[m_name] = clean_val

        new_bones = {}
        for kanji, le in self.input_fields_bones.items():
            text = le.text().strip()
            clean_val = re.sub(r'[^a-zA-Z0-9_]', '', text).lower()
            if clean_val:
                new_bones[kanji] = clean_val

        if not new_morphs and not new_bones:
            QMessageBox.warning(self, "入力確認", "少なくとも1つのモーフ名または漢字に英名・ローマ字を入力してください。")
            return

        # ユーザー辞書ファイルに保存
        settings = user_dict_manager.load_user_settings()
        custom_morph = settings.setdefault("custom_morph_dict", {})
        custom_trans = settings.setdefault("custom_name_translations", {})

        if new_morphs:
            custom_morph.update(new_morphs)
            custom_trans.update(new_morphs)

        if new_bones:
            custom_trans.update(new_bones)

        user_dict_manager.save_user_settings(settings)

        # メモリ上の jaka.py 辞書にも即時マージ
        if new_morphs:
            jaka.MMD_KANJI_DICT.update(new_morphs)
        if new_bones:
            jaka.MMD_KANJI_DICT.update(new_bones)

        total_saved = len(new_morphs) + len(new_bones)
        print(f"[ユーザー辞書] {total_saved} 件（モーフ: {len(new_morphs)}件, 漢字: {len(new_bones)}件）を辞書登録しました")

        # 再チェックの実行
        rem_morphs = find_unregistered_morphs(self.pmx_path)
        rem_bones = find_unregistered_kanji_in_bones(self.pmx_path)

        if not rem_morphs and not rem_bones:
            QMessageBox.information(
                self, "登録完了",
                f"{total_saved} 件の名称・漢字を辞書に登録しました。\n\n"
                "すべてのモーフ名およびボーン名が正常に解決されました！"
            )
            self.accept()
        else:
            QMessageBox.information(
                self, "再チェック結果",
                f"{total_saved} 件を辞書に登録しました。\n\n"
                f"残りの未登録（モーフ: {len(rem_morphs)}件, ボーン: {len(rem_bones)}件）があります。続けて入力してください。"
            )
            self._refresh_tables()

def check_and_prompt_user_dict(parent=None, pmx_path=None):
    """
    モデル内の未登録モーフ名およびボーン名をチェックし、存在する場合に確認ダイアログを開きます。
    
    動作:
        1. jaka.py およびユーザー辞書に登録のないモーフ名・ボーン名を走査。
        2. 未登録がある場合:
           「登録のないモーフ名（またはボーン名）があります。ユーザー辞書に記録しますか？」と確認。
           - 「はい」: GUIを開き登録後、再チェックを実行。
           - 「いいえ」: スルー（インポート継続）。
    """
    if not pmx_path or not os.path.exists(pmx_path):
        return True

    print("[PMXチェック] モーフ名およびボーン名の辞書照合を開始します...")
    unregistered_morphs = find_unregistered_morphs(pmx_path)
    unregistered_bones = find_unregistered_kanji_in_bones(pmx_path)

    if not unregistered_morphs and not unregistered_bones:
        print("[PMXチェック] 全モーフ名および全ボーン名の辞書照合が完了しました (未登録なし)")
        return True

    m_cnt = len(unregistered_morphs)
    b_cnt = len(unregistered_bones)
    print(f"[PMXチェック] 辞書未登録が検出されました (未登録モーフ: {m_cnt}件, 未登録漢字(ボーン): {b_cnt}件)")

    # 確認ダイアログのメッセージ作成
    initial_tab = 0
    if m_cnt > 0 and b_cnt == 0:
        initial_tab = 0
        sample_str = "、".join([item["name"] for item in unregistered_morphs[:5]])
        if m_cnt > 5:
            sample_str += "..."
        dlg_title = "未登録モーフ名の検出"
        dlg_msg = (
            f"モデル内に辞書登録のないモーフ名が {m_cnt} 件検出されました。\n"
            f"（検出例: {sample_str}）\n\n"
            "登録のないモーフ名があります。ユーザー辞書に記録しますか？"
        )
    elif b_cnt > 0 and m_cnt == 0:
        initial_tab = 1
        sample_str = "、".join([item["kanji"] for item in unregistered_bones[:5]])
        if b_cnt > 5:
            sample_str += "..."
        dlg_title = "未登録ボーン名の検出"
        dlg_msg = (
            f"モデル内に辞書登録のないボーン名・漢字が {b_cnt} 種類検出されました。\n"
            f"（検出例: {sample_str}）\n\n"
            "登録のないボーン名があります。ユーザー辞書に記録しますか？"
        )
    else:
        initial_tab = 0
        m_sample = "、".join([item["name"] for item in unregistered_morphs[:3]])
        b_sample = "、".join([item["kanji"] for item in unregistered_bones[:3]])
        dlg_title = "未登録モーフ名・ボーン名の検出"
        dlg_msg = (
            f"モデル内に辞書登録のない要素が検出されました。\n"
            f"・未登録モーフ名: {m_cnt} 件（例: {m_sample}）\n"
            f"・未登録ボーン名(漢字): {b_cnt} 件（例: {b_sample}）\n\n"
            "登録のないモーフ名およびボーン名があります。ユーザー辞書に記録しますか？"
        )

    res = QMessageBox.question(
        parent,
        dlg_title,
        dlg_msg,
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes
    )

    if res == QMessageBox.Yes:
        dlg = UserDictRegisterDialog(parent=parent, pmx_path=pmx_path, initial_tab=initial_tab)
        dlg.exec_()
        return True
    else:
        print("[PMXチェック] ユーザー辞書への登録をスキップしました。")
        return False
