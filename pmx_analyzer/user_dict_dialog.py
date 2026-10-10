# -*- coding: utf-8 -*-
"""
未登録漢字・ボーン名辞書登録ダイアログ (user_dict_dialog.py)

jaka.py に記載のないボーン名・漢字を検出し、
「登録のないボーン名があります。ユーザー辞書に記録しますか？」と確認した上で、
漢字の隣にローマ字を記入して登録・再チェックを行うPySideダイアログを提供します。
"""

import os
import re

try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
        QMessageBox, QFrame, QApplication
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
except ImportError:
    from PySide2.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
        QMessageBox, QFrame, QApplication
    )
    from PySide2.QtCore import Qt
    from PySide2.QtGui import QFont

try:
    from .analyzer_core import find_unregistered_kanji_in_bones
    from ..asset import jaka, user_dict_manager
except Exception:
    from pmx_analyzer.analyzer_core import find_unregistered_kanji_in_bones
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

class UserDictRegisterDialog(QDialog):
    """未登録漢字の隣にローマ字を記入して登録するダイアログ"""
    def __init__(self, parent=None, pmx_path=None):
        super(UserDictRegisterDialog, self).__init__(parent)
        self.pmx_path = pmx_path
        self.setWindowTitle("ユーザー辞書 ボーン名・漢字登録")
        self.resize(680, 460)
        self.setMinimumSize(540, 360)
        self.setStyleSheet(DIALOG_STYLE)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.input_fields = {} # 漢字 -> QLineEdit
        self._init_ui()
        self._refresh_table()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 説明ヘッダー
        title_lbl = QLabel("ボーン名 ユーザー辞書登録")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color: #52b7ff;")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(
            "以下の漢字は標準辞書に登録されていません。\n"
            "各漢字の隣の入力欄にローマ字（半角英数）を入力し、「辞書に登録して再チェック」をクリックしてください。"
        )
        desc_lbl.setStyleSheet("color: #cccccc; line-height: 1.4;")
        layout.addWidget(desc_lbl)

        # テーブルウィジェット
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["未登録漢字", "ローマ字入力 (英数字)", "検出されたボーン名"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

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

    def _refresh_table(self):
        """未登録漢字を再走査してテーブルを更新します"""
        self.input_fields.clear()
        self.table.setRowCount(0)

        unregistered = find_unregistered_kanji_in_bones(self.pmx_path)
        if not unregistered:
            self.status_lbl.setText("すべてのボーン名が正常に辞書登録されています！")
            self.btn_save.setEnabled(False)
            return

        self.status_lbl.setText(f"未登録の漢字が {len(unregistered)} 件検出されました。")
        self.table.setRowCount(len(unregistered))

        for row, item in enumerate(unregistered):
            kanji = item["kanji"]
            bone_list_str = ", ".join(item["bones"][:4])
            if len(item["bones"]) > 4:
                bone_list_str += f" 他 (計{len(item['bones'])}本)"

            # 1. 漢字表示セル
            item_kanji = QTableWidgetItem(f"  {kanji}  ")
            item_kanji.setTextAlignment(Qt.AlignCenter)
            item_kanji.setFlags(Qt.ItemIsEnabled)
            font = QFont()
            font.setPointSize(13)
            font.setBold(True)
            item_kanji.setFont(font)
            self.table.setItem(row, 0, item_kanji)

            # 2. ローマ字入力用 QLineEdit
            le = QLineEdit()
            le.setPlaceholderText(f"例: {kanji} の読み（半角英字）")
            self.table.setCellWidget(row, 1, le)
            self.input_fields[kanji] = le

            # 3. 出現ボーン名セル
            item_bones = QTableWidgetItem(bone_list_str)
            item_bones.setToolTip("\n".join(item["bones"]))
            item_bones.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 2, item_bones)

        self.btn_save.setEnabled(True)

    def _save_and_recheck(self):
        """入力されたローマ字をユーザー辞書に保存し、再チェックを実行します"""
        new_entries = {}
        for kanji, le in self.input_fields.items():
            text = le.text().strip()
            # 英数字とアンダースコアのみに正規化
            clean_val = re.sub(r'[^a-zA-Z0-9_]', '', text).lower()
            if clean_val:
                new_entries[kanji] = clean_val

        if not new_entries:
            QMessageBox.warning(self, "入力確認", "少なくとも1つの漢字にローマ字を入力してください。")
            return

        # ユーザー辞書ファイルに保存
        settings = user_dict_manager.load_user_settings()
        custom_trans = settings.setdefault("custom_name_translations", {})
        custom_trans.update(new_entries)
        user_dict_manager.save_user_settings(settings)

        # メモリ上の jaka.py 辞書にも即時マージ
        jaka.MMD_KANJI_DICT.update(new_entries)

        print(f"[ユーザー辞書] {len(new_entries)} 件の漢字・ローマ字を登録しました: {new_entries}")

        # 再チェック（サイドチェック）の実行
        remaining = find_unregistered_kanji_in_bones(self.pmx_path)
        if not remaining:
            QMessageBox.information(
                self, "登録完了",
                f"{len(new_entries)} 件のボーン名・漢字を辞書に登録しました。\n\n"
                "すべてのボーン名が正常に解決されました！"
            )
            self.accept()
        else:
            QMessageBox.information(
                self, "再チェック結果",
                f"{len(new_entries)} 件を辞書に登録しました。\n\n"
                f"残りの未登録漢字が {len(remaining)} 件あります。続けて入力してください。"
            )
            self._refresh_table()

def check_and_prompt_user_dict(parent=None, pmx_path=None):
    """
    モデル内の未登録ボーン名をチェックし、存在する場合に確認ダイアログを開きます。
    
    動作:
        1. jaka.py に記載のないボーン名・漢字を走査。
        2. 未登録がある場合:
           「登録のないボーン名があります。ユーザー辞書に記録しますか？」と確認。
           - 「はい」: GUIを開き登録後、再チェックを実行。
           - 「いいえ」: スルー（何もしない）。
    """
    if not pmx_path or not os.path.exists(pmx_path):
        return True

    print("[PMXチェック] ボーン名および未登録漢字の辞書照合を開始します...")
    unregistered = find_unregistered_kanji_in_bones(pmx_path)
    if not unregistered:
        print("[PMXチェック] 全ボーン名の辞書照合が完了しました (未登録なし)")
        return True

    print(f"[PMXチェック] 辞書未登録の漢字・ボーン名が {len(unregistered)} 件検出されました。確認ダイアログを表示します。")

    # ユーザーへの確認
    kanji_sample = "、".join([item["kanji"] for item in unregistered[:5]])
    if len(unregistered) > 5:
        kanji_sample += "..."

    res = QMessageBox.question(
        parent,
        "未登録ボーン名の検出",
        f"モデル内に辞書登録のないボーン名・漢字が {len(unregistered)} 種類検出されました。\n"
        f"（検出例: {kanji_sample}）\n\n"
        "登録のないボーン名があります。ユーザー辞書に記録しますか？",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes
    )

    if res == QMessageBox.Yes:
        dlg = UserDictRegisterDialog(parent=parent, pmx_path=pmx_path)
        dlg.exec_()
        return True
    else:
        print("[PMXチェック] ユーザー辞書への登録をスキップしました。")
        return False
