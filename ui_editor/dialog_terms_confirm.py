# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 利用規約確認・同意ダイアログモジュール
モデルデータの利用規約（改造・お着替えの可否、パーツ流用、再配布等の禁止事項）を確認し、
ユーザーの明示的な同意を得るための安全ダイアログを提供します。
"""

import os
import sys
import glob
import maya.cmds as mc

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QCheckBox, QPushButton, QTextEdit, QTabWidget, QGroupBox,
        QFrame, QMessageBox
    )
    PYSIDE_VER = 6
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import (
        QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QCheckBox, QPushButton, QTextEdit, QTabWidget, QGroupBox,
        QFrame, QMessageBox
    )
    PYSIDE_VER = 2


def _extract_model_terms_text(model_node):
    """
    指定されたMMDモデルノードからコメントや外部規約テキストを収集
    ノードのアトリビュートや同一フォルダ内のReadmeテキストを走査します。
    """
    result = {
        "model_name": "",
        "comment_ja": "",
        "comment_en": "",
        "external_files": {}
    }
    if not model_node or not mc.objExists(model_node):
        return result

    # モデル名の取得
    for attr in ["mmdModelNameJa", "mmdModelName", "modelName"]:
        if mc.attributeQuery(attr, node=model_node, exists=True):
            val = mc.getAttr(f"{model_node}.{attr}")
            if val:
                result["model_name"] = str(val)
                break
    if not result["model_name"]:
        result["model_name"] = model_node

    # 日本語コメント・規約の取得
    for attr in ["mmdModelCommentJa", "mmdModelComment", "modelComment"]:
        if mc.attributeQuery(attr, node=model_node, exists=True):
            val = mc.getAttr(f"{model_node}.{attr}")
            if val:
                result["comment_ja"] = str(val)
                break

    # 英語コメント・規約の取得
    for attr in ["mmdModelCommentEn", "modelCommentEn"]:
        if mc.attributeQuery(attr, node=model_node, exists=True):
            val = mc.getAttr(f"{model_node}.{attr}")
            if val:
                result["comment_en"] = str(val)
                break

    # モデル元ファイルパスの探索と同一階層のテキストファイル検出
    model_path = ""
    for attr in ["mmdModelPath", "modelPath", "filePath"]:
        if mc.attributeQuery(attr, node=model_node, exists=True):
            val = mc.getAttr(f"{model_node}.{attr}")
            if val and os.path.exists(str(val)):
                model_path = str(val)
                break

    if model_path:
        base_dir = os.path.dirname(model_path)
        search_patterns = [
            os.path.join(base_dir, "*.txt"),
            os.path.join(base_dir, "*.md")
        ]
        found_files = []
        for pat in search_patterns:
            found_files.extend(glob.glob(pat))

        for fpath in found_files:
            fname = os.path.basename(fpath)
            # テキストファイルの内容を安全に読み込み
            encodings = ["utf-8", "cp932", "shift_jis", "euc_jp"]
            content = ""
            for enc in encodings:
                try:
                    with open(fpath, "r", encoding=enc) as f:
                        content = f.read()
                    break
                except Exception:
                    continue
            if content:
                result["external_files"][fname] = content

    return result


class ModelTermsConfirmDialog(QDialog):
    """
    モデル利用規約確認ダイアログ
    素体モデルおよび衣装モデルの規約を表示し、明示的なチェック同意を求めます。
    """

    def __init__(self, base_model=None, outfit_model=None, parent=None):
        super(ModelTermsConfirmDialog, self).__init__(parent)
        self.setWindowTitle("MMDモデル利用規約・改造許可の確認")
        self.resize(760, 620)
        self.setMinimumSize(640, 480)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        self.base_model = base_model
        self.outfit_model = outfit_model
        self.is_agreed = False

        self._init_ui()
        self._load_terms_data()

    def _init_ui(self):
        """ダイアログのユーザーインターフェース初期化"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # 警告・案内ヘッダー
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #3b2a1a; border: 1px solid #c97a2e; border-radius: 6px; padding: 6px;")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(4)

        lbl_title = QLabel("モデル改造・お着替えに関する利用規約確認")
        lbl_title.setStyleSheet("font-weight: bold; color: #ffb86c; font-size: 14px;")
        header_layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "MMDモデルの改造・パーツ付け替え・お着替えを行う前に、各モデラー様の利用規約を遵守する必要があります。\n"
            "各モデルの説明文および同梱テキストをご確認の上、規約で許可されている範囲内でのみ作業を進めてください。"
        )
        lbl_desc.setStyleSheet("color: #dddddd; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        header_layout.addWidget(lbl_desc)

        layout.addWidget(header_frame)

        # モデル規約タブコンテナ（素体側・衣装側）
        self.tabs_terms = QTabWidget()
        layout.addWidget(self.tabs_terms, 1)

        # 素体側タブ
        self.widget_base = QWidget()
        self.layout_base = QVBoxLayout(self.widget_base)
        self.lbl_base_name = QLabel("素体モデル: 未選択")
        self.lbl_base_name.setStyleSheet("font-weight: bold; color: #52b7ff;")
        self.layout_base.addWidget(self.lbl_base_name)
        self.te_base_terms = QTextEdit()
        self.te_base_terms.setReadOnly(True)
        self.te_base_terms.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0; font-family: monospace;")
        self.layout_base.addWidget(self.te_base_terms)
        self.tabs_terms.addTab(self.widget_base, "素体モデル規約 (頭部・キャラクター側)")

        # 衣装側タブ
        self.widget_outfit = QWidget()
        self.layout_outfit = QVBoxLayout(self.widget_outfit)
        self.lbl_outfit_name = QLabel("衣装モデル: 未選択")
        self.lbl_outfit_name.setStyleSheet("font-weight: bold; color: #ff99cc;")
        self.layout_outfit.addWidget(self.lbl_outfit_name)
        self.te_outfit_terms = QTextEdit()
        self.te_outfit_terms.setReadOnly(True)
        self.te_outfit_terms.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0; font-family: monospace;")
        self.layout_outfit.addWidget(self.te_outfit_terms)
        self.tabs_terms.addTab(self.widget_outfit, "衣装モデル規約 (ボディ・衣装側)")

        # 同意確認チェックボックスグループ
        grp_confirm = QGroupBox("規約確認および同意事項")
        grp_confirm.setStyleSheet("QGroupBox { font-weight: bold; color: #aaffaa; }")
        confirm_layout = QVBoxLayout(grp_confirm)
        confirm_layout.setSpacing(6)

        self.cb_base_agreed = QCheckBox("素体モデルの利用規約を確認し、パーツ付け替えや改造が許可されていることを確認しました")
        self.cb_base_agreed.stateChanged.connect(self._check_agreements)
        confirm_layout.addWidget(self.cb_base_agreed)

        self.cb_outfit_agreed = QCheckBox("衣装モデルの利用規約を確認し、他モデルへのお着替えやパーツ流用が許可されていることを確認しました")
        self.cb_outfit_agreed.stateChanged.connect(self._check_agreements)
        confirm_layout.addWidget(self.cb_outfit_agreed)

        self.cb_general_agreed = QCheckBox("再配布の禁止、R-18・公序良俗に反する使用の禁止など、各モデラー様の禁止事項を遵守します")
        self.cb_general_agreed.stateChanged.connect(self._check_agreements)
        confirm_layout.addWidget(self.cb_general_agreed)

        layout.addWidget(grp_confirm)

        # アクションボタン
        h_btn_layout = QHBoxLayout()
        h_btn_layout.setSpacing(10)

        self.btn_agree = QPushButton("利用規約に同意して改造・お着替えを進める")
        self.btn_agree.setFixedHeight(36)
        self.btn_agree.setEnabled(False)
        self.btn_agree.setStyleSheet(
            "QPushButton:enabled { background-color: #2b6e3f; color: #ffffff; font-weight: bold; font-size: 13px; border-radius: 4px; }"
            "QPushButton:enabled:hover { background-color: #388d52; border: 1px solid #77ff77; }"
            "QPushButton:disabled { background-color: #333333; color: #777777; }"
        )
        self.btn_agree.clicked.connect(self._on_agree_clicked)
        h_btn_layout.addWidget(self.btn_agree, 3)

        self.btn_cancel = QPushButton("キャンセル")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.clicked.connect(self.reject)
        h_btn_layout.addWidget(self.btn_cancel, 1)

        layout.addLayout(h_btn_layout)

    def _load_terms_data(self):
        """モデルから規約テキストを読み込んで表示"""
        # 素体側データのロード
        base_data = _extract_model_terms_text(self.base_model)
        self.lbl_base_name.setText(f"素体モデル: {base_data['model_name']}")
        base_text = self._format_terms_display(base_data)
        self.te_base_terms.setPlainText(base_text)

        # 衣装側データのロード
        outfit_data = _extract_model_terms_text(self.outfit_model)
        self.lbl_outfit_name.setText(f"衣装モデル: {outfit_data['model_name']}")
        outfit_text = self._format_terms_display(outfit_data)
        self.te_outfit_terms.setPlainText(outfit_text)

    def _format_terms_display(self, data):
        """抽出したメタデータを整形テキストとして結合"""
        lines = []
        lines.append(f"【モデル名称】: {data['model_name']}")
        lines.append("-" * 50)

        if data["comment_ja"]:
            lines.append("【PMXコメント (日本語)】")
            lines.append(data["comment_ja"])
            lines.append("-" * 50)

        if data["comment_en"]:
            lines.append("【PMXコメント (英語)】")
            lines.append(data["comment_en"])
            lines.append("-" * 50)

        if data["external_files"]:
            lines.append("【同梱ドキュメント (Readme / 規約テキスト)】")
            for fname, content in data["external_files"].items():
                lines.append(f"\n--- [ファイル: {fname}] ---")
                lines.append(content)
                lines.append("-" * 50)

        if not data["comment_ja"] and not data["comment_en"] and not data["external_files"]:
            lines.append("※モデルファイル内に規約コメントは見つかりませんでした。")
            lines.append("※配布元の配布ページや付属ドキュメントを別途ご確認ください。")

        return "\n".join(lines)

    def _check_agreements(self):
        """すべての同意チェックボックスが有効化されているか判定"""
        all_checked = (
            self.cb_base_agreed.isChecked() and
            self.cb_outfit_agreed.isChecked() and
            self.cb_general_agreed.isChecked()
        )
        self.btn_agree.setEnabled(all_checked)

    def _on_agree_clicked(self):
        """同意実行時の確定処理"""
        self.is_agreed = True
        self.setResult(QDialog.Accepted)
        self.accept()

