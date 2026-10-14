# -*- coding: utf-8 -*-
"""
マテリアル保護・Toon除外設定ダイアログ
PySide6 (Maya 2025+) および PySide2 (Maya 2022-2024) 両対応。
シーン内のインポート済みモデルのPMX材質名一覧を表示し、
顔・肌のテカリ（スペキュラ）除去、および瞳ハイライト等のToon乗算除外キーワードを管理・即時反映します。
"""

import sys
import os
import re

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

try:
    from ..converters.pmxpaimaya import (
        get_scene_mmd_materials, apply_material_protection_to_scene
    )
except Exception:
    try:
        from converters.pmxpaimaya import (
            get_scene_mmd_materials, apply_material_protection_to_scene
        )
    except Exception:
        get_scene_mmd_materials = None
        apply_material_protection_to_scene = None

_material_protect_dialog_instance = None


def _is_mostly_ascii(text):
    """英数字・半角記号のみで構成されているかを判定"""
    return bool(re.match(r'^[a-zA-Z0-9_\-\s]+$', text))


class MaterialProtectDialog(QtWidgets.QDialog):
    """マテリアル保護・Toon除外設定ダイアログ"""

    def __init__(self, parent=None):
        super(MaterialProtectDialog, self).__init__(parent)
        self.setWindowTitle("マテリアル保護・Toon除外設定")
        self.resize(1040, 680)
        self.setMinimumSize(880, 560)

        # ウィンドウフラグ設定
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)

        self._init_ui()
        self._load_data_to_ui()
        self._populate_models()
        self._refresh_materials_table()

    def _init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 説明ヘッダーパネル
        info_frame = QtWidgets.QFrame()
        info_frame.setStyleSheet(
            "background-color: #1e262f; border: 1px solid #324759; border-radius: 6px; padding: 10px;"
        )
        info_layout = QtWidgets.QVBoxLayout(info_frame)
        info_layout.setSpacing(4)

        lbl_title = QtWidgets.QLabel("【マテリアル保護・Toon除外設定とモデル材質一覧】")
        lbl_title.setStyleSheet("color: #70b5f5; font-weight: bold; font-size: 13px;")
        info_layout.addWidget(lbl_title)

        lbl_desc = QtWidgets.QLabel(
            "インポートしたモデルの材質名（PMX元名称）をそのまま確認できます。\n"
            "材質を選択してキーワードに追加し「保存して適用」を押すと、シーン内モデルへ自動的にテカリ除去やToon除外が反映されます。"
        )
        lbl_desc.setStyleSheet("color: #cfd8dc; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        info_layout.addWidget(lbl_desc)
        main_layout.addWidget(info_frame)

        # 中央スプリッター (左: モデル材質一覧, 右: キーワード設定タブ)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # 左側パネル: モデル材質一覧
        panel_left = QtWidgets.QWidget()
        layout_left = QtWidgets.QVBoxLayout(panel_left)
        layout_left.setContentsMargins(0, 0, 0, 0)
        layout_left.setSpacing(8)

        grp_mat = QtWidgets.QGroupBox("インポート済みモデルの材質一覧 (PMX元名称)")
        grp_mat.setStyleSheet("QGroupBox { font-weight: bold; color: #90caf9; }")
        layout_grp_mat = QtWidgets.QVBoxLayout(grp_mat)
        layout_grp_mat.setSpacing(8)

        # モデル選択コンボボックス行
        row_model = QtWidgets.QHBoxLayout()
        lbl_model = QtWidgets.QLabel("対象モデル:")
        lbl_model.setStyleSheet("color: #b0bec5; font-size: 12px;")
        self.cmb_model = QtWidgets.QComboBox()
        self.cmb_model.currentIndexChanged.connect(self._on_model_changed)
        self.btn_refresh = QtWidgets.QPushButton("更新")
        self.btn_refresh.setFixedWidth(55)
        self.btn_refresh.setToolTip("シーン内のモデルおよび材質情報を再読み込みします。")
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)
        row_model.addWidget(lbl_model)
        row_model.addWidget(self.cmb_model)
        row_model.addWidget(self.btn_refresh)
        layout_grp_mat.addLayout(row_model)

        # 材質一覧テーブル
        self.tbl_materials = QtWidgets.QTableWidget()
        self.tbl_materials.setColumnCount(3)
        self.tbl_materials.setHorizontalHeaderLabels(["PMX材質名 (元名称)", "Mayaシェーダー", "適用状態"])
        self.tbl_materials.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tbl_materials.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tbl_materials.horizontalHeader().setStretchLastSection(True)
        self.tbl_materials.setColumnWidth(0, 160)
        self.tbl_materials.setColumnWidth(1, 140)
        self.tbl_materials.cellDoubleClicked.connect(self._on_table_double_clicked)
        self.tbl_materials.setStyleSheet(
            "QTableWidget { background-color: #23272d; alternate-background-color: #2b3038; border: 1px solid #3c4450; }"
            "QHeaderView::section { background-color: #1a1e24; color: #b0bec5; padding: 4px; border: 1px solid #333; font-weight: bold; }"
        )
        self.tbl_materials.setAlternatingRowColors(True)
        layout_grp_mat.addWidget(self.tbl_materials)

        # テーブル操作ボタン行
        btn_mat_row = QtWidgets.QHBoxLayout()
        self.btn_add_skin = QtWidgets.QPushButton("顔・肌に追加 ▶")
        self.btn_add_skin.setStyleSheet(
            "background-color: #1e4b6e; color: #ffffff; font-weight: bold; border: 1px solid #2b689a; padding: 5px 10px; border-radius: 3px;"
        )
        self.btn_add_skin.setToolTip("選択した材質のPMX元名称を「顔・肌保護キーワード」へ登録します。")
        self.btn_add_skin.clicked.connect(self._on_add_selected_to_skin)

        self.btn_add_toon = QtWidgets.QPushButton("Toon除外に追加 ▶")
        self.btn_add_toon.setStyleSheet(
            "background-color: #1e5638; color: #ffffff; font-weight: bold; border: 1px solid #2b784f; padding: 5px 10px; border-radius: 3px;"
        )
        self.btn_add_toon.setToolTip("選択した材質のPMX元名称を「Toon乗算除外キーワード」へ登録します。")
        self.btn_add_toon.clicked.connect(self._on_add_selected_to_toon)

        btn_mat_row.addWidget(self.btn_add_skin)
        btn_mat_row.addWidget(self.btn_add_toon)
        layout_grp_mat.addLayout(btn_mat_row)

        lbl_hint = QtWidgets.QLabel("※材質をダブルクリックすると現在開いているタブへ直接追加されます。")
        lbl_hint.setStyleSheet("color: #78909c; font-size: 11px;")
        layout_grp_mat.addWidget(lbl_hint)

        layout_left.addWidget(grp_mat)
        splitter.addWidget(panel_left)

        # 右側パネル: キーワード編集タブ
        panel_right = QtWidgets.QWidget()
        layout_right = QtWidgets.QVBoxLayout(panel_right)
        layout_right.setContentsMargins(0, 0, 0, 0)

        self.tab_widget = QtWidgets.QTabWidget()
        layout_right.addWidget(self.tab_widget)

        # タブ: マテリアル保護 (テカリ・スペキュラ除去)
        self.tab_protect = QtWidgets.QWidget()
        self._setup_protect_tab()
        self.tab_widget.addTab(self.tab_protect, "マテリアル保護 (テカリ除去)")

        # タブ: Toon除外 (発色維持・乗算免除)
        self.tab_toon = QtWidgets.QWidget()
        self._setup_toon_tab()
        self.tab_widget.addTab(self.tab_toon, "Toon除外 (発色維持)")

        splitter.addWidget(panel_right)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 5)

        main_layout.addWidget(splitter)

        # 下部ボタングループ
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_reset_default = QtWidgets.QPushButton("初期デフォルトに戻す")
        self.btn_reset_default.setStyleSheet(
            "background-color: #4a2828; color: #ffaaaa; border: 1px solid #773333; padding: 7px 14px; border-radius: 4px;"
        )
        self.btn_reset_default.clicked.connect(self._on_reset_default)
        btn_layout.addWidget(self.btn_reset_default)

        btn_layout.addStretch()

        self.btn_apply_only = QtWidgets.QPushButton("モデルに即時反映")
        self.btn_apply_only.setStyleSheet(
            "background-color: #2b4c68; color: #ffffff; border: 1px solid #3d6a90; padding: 7px 16px; border-radius: 4px;"
        )
        self.btn_apply_only.setToolTip("現在のキーワード入力内容でシーン内のモデルマテリアルを更新します。")
        self.btn_apply_only.clicked.connect(self._on_apply_only)
        btn_layout.addWidget(self.btn_apply_only)

        self.btn_save = QtWidgets.QPushButton("保存して適用")
        self.btn_save.setStyleSheet(
            "background-color: #1e5631; color: #ffffff; font-weight: bold; border: 1px solid #2e7d32; padding: 7px 22px; border-radius: 4px;"
        )
        self.btn_save.setToolTip("キーワード設定をJSONに保存し、シーン内モデルへ自動反映します。")
        self.btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(self.btn_save)

        self.btn_close = QtWidgets.QPushButton("閉じる")
        self.btn_close.setStyleSheet(
            "background-color: #333333; color: #dddddd; border: 1px solid #555555; padding: 7px 14px; border-radius: 4px;"
        )
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_close)

        main_layout.addLayout(btn_layout)

    def _setup_protect_tab(self):
        """マテリアル保護（テカリ・スペキュラ除去）タブの構築"""
        layout = QtWidgets.QVBoxLayout(self.tab_protect)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 機能説明パネル
        desc_box = QtWidgets.QFrame()
        desc_box.setStyleSheet(
            "background-color: #1e262f; border: 1px solid #324759; border-radius: 6px; padding: 8px;"
        )
        desc_layout = QtWidgets.QVBoxLayout(desc_box)
        desc_layout.setSpacing(4)

        lbl_title = QtWidgets.QLabel("【顔・肌マテリアルのテカリ（スペキュラ）除去】")
        lbl_title.setStyleSheet("color: #70b5f5; font-weight: bold; font-size: 12px;")
        desc_layout.addWidget(lbl_title)

        lbl_protect_exp = QtWidgets.QLabel(
            "「顔」「目」「眉」「肌」などのマテリアルにスペキュラ光沢が生じるとアニメ質感が損なわれます。\n"
            "登録されたキーワードに一致する材質はテカリ反射を抑制し、柔らかなアニメ調の質感を保護します。"
        )
        lbl_protect_exp.setStyleSheet("color: #cfd8dc; font-size: 11px;")
        lbl_protect_exp.setWordWrap(True)
        desc_layout.addWidget(lbl_protect_exp)
        layout.addWidget(desc_box)

        # キーワード編集グループ (左右2列)
        grp_skin = QtWidgets.QGroupBox("顔・肌・表情マテリアル判定キーワード一覧")
        grp_skin.setStyleSheet("QGroupBox { font-weight: bold; color: #90caf9; }")
        grp_skin_layout = QtWidgets.QHBoxLayout(grp_skin)
        grp_skin_layout.setSpacing(10)

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

    def _setup_toon_tab(self):
        """Toon除外（発色維持・乗算免除）タブの構築"""
        layout = QtWidgets.QVBoxLayout(self.tab_toon)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 機能説明パネル
        desc_box = QtWidgets.QFrame()
        desc_box.setStyleSheet(
            "background-color: #1e262f; border: 1px solid #324759; border-radius: 6px; padding: 8px;"
        )
        desc_layout = QtWidgets.QVBoxLayout(desc_box)
        desc_layout.setSpacing(4)

        lbl_title = QtWidgets.QLabel("【瞳ハイライト等のToon乗算除外】")
        lbl_title.setStyleSheet("color: #81c784; font-weight: bold; font-size: 12px;")
        desc_layout.addWidget(lbl_title)

        lbl_toon_exp = QtWidgets.QLabel(
            "「瞳のハイライト（高光）」や「白目」にセル影（Toon）が乗算されると暗く濁ってしまいます。\n"
            "登録されたキーワードに一致する材質はToon影乗算を免除し、常に澄んだ明るい輝きを維持します。"
        )
        lbl_toon_exp.setStyleSheet("color: #cfd8dc; font-size: 11px;")
        lbl_toon_exp.setWordWrap(True)
        desc_layout.addWidget(lbl_toon_exp)
        layout.addWidget(desc_box)

        # キーワード編集グループ (左右2列)
        grp_toon = QtWidgets.QGroupBox("Toon乗算除外キーワード一覧 (瞳ハイライト等)")
        grp_toon.setStyleSheet("QGroupBox { font-weight: bold; color: #a5d6a7; }")
        grp_toon_layout = QtWidgets.QHBoxLayout(grp_toon)
        grp_toon_layout.setSpacing(10)

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

    def _populate_models(self):
        """シーン内のMMDモデルを検出してコンボボックスに登録"""
        self.cmb_model.blockSignals(True)
        self.cmb_model.clear()
        self.cmb_model.addItem("シーン全体 (全材質)", None)

        try:
            try:
                from ..converters.vmdpaimaya import get_available_mmd_models
            except Exception:
                from converters.vmdpaimaya import get_available_mmd_models
            models = get_available_mmd_models()
            for node, label in models:
                self.cmb_model.addItem(label, node)
        except Exception:
            pass
        self.cmb_model.blockSignals(False)

    def _on_model_changed(self, idx):
        """モデル選択変更時に材質一覧を再取得"""
        self._refresh_materials_table()

    def _on_refresh_clicked(self):
        """更新ボタン押下時の処理"""
        self._populate_models()
        self._refresh_materials_table()

    def _get_active_keywords(self):
        """現在UI上に入力されているキーワードを取得"""
        skin_ja = [self.list_skin_ja.item(i).text().strip() for i in range(self.list_skin_ja.count()) if self.list_skin_ja.item(i).text().strip()]
        skin_en = [self.list_skin_en.item(i).text().strip() for i in range(self.list_skin_en.count()) if self.list_skin_en.item(i).text().strip()]
        toon_ja = [self.list_toon_ja.item(i).text().strip() for i in range(self.list_toon_ja.count()) if self.list_toon_ja.item(i).text().strip()]
        toon_en = [self.list_toon_en.item(i).text().strip() for i in range(self.list_toon_en.count()) if self.list_toon_en.item(i).text().strip()]
        return skin_ja + skin_en, toon_ja + toon_en

    def _refresh_materials_table(self):
        """シーン内材質情報を取得してテーブルに反映"""
        target_model = self.cmb_model.currentData()
        materials = []
        if get_scene_mmd_materials:
            try:
                materials = get_scene_mmd_materials(target_model)
            except Exception as e:
                print(f"[警告] 材質一覧の取得に失敗: {e}")

        skin_keywords, toon_keywords = self._get_active_keywords()

        self.tbl_materials.setRowCount(len(materials))
        for row, item in enumerate(materials):
            orig_name = item.get("original_name", "")
            shader = item.get("shader", "")

            # 現在のUI入力キーワードに基づいて状態を判定
            lower_orig = orig_name.lower()
            lower_shd = shader.lower()

            is_skin = any(k.lower() in lower_orig or k.lower() in lower_shd for k in skin_keywords)
            is_toon = any(k.lower() in lower_orig or k.lower() in lower_shd for k in toon_keywords)

            # アイテム作成
            it_orig = QtWidgets.QTableWidgetItem(orig_name)
            it_shd = QtWidgets.QTableWidgetItem(shader)

            if is_skin:
                status_text = "[テカリ保護]"
                status_color = QtGui.QColor("#70b5f5")
            elif is_toon:
                status_text = "[Toon除外]"
                status_color = QtGui.QColor("#81c784")
            else:
                status_text = "[通常]"
                status_color = QtGui.QColor("#90a4ae")

            it_status = QtWidgets.QTableWidgetItem(status_text)
            it_status.setForeground(status_color)

            self.tbl_materials.setItem(row, 0, it_orig)
            self.tbl_materials.setItem(row, 1, it_shd)
            self.tbl_materials.setItem(row, 2, it_status)

    def _get_selected_material_names(self):
        """テーブルで選択されている材質のPMX元名称一覧を返却"""
        selected_rows = set()
        for idx in self.tbl_materials.selectedIndexes():
            selected_rows.add(idx.row())

        names = []
        for r in sorted(list(selected_rows)):
            item = self.tbl_materials.item(r, 0)
            if item and item.text().strip():
                names.append(item.text().strip())
        return names

    def _add_keyword_smart(self, keyword, target_category="skin"):
        """文字列が日本語か英語かを判定して適切なリストに追加"""
        if not keyword:
            return False

        if target_category == "skin":
            target_list = self.list_skin_en if _is_mostly_ascii(keyword) else self.list_skin_ja
        else:
            target_list = self.list_toon_en if _is_mostly_ascii(keyword) else self.list_toon_ja

        existing = [target_list.item(i).text().strip() for i in range(target_list.count())]
        if keyword not in existing:
            target_list.addItem(keyword)
            return True
        return False

    def _on_add_selected_to_skin(self):
        """選択した材質名を顔・肌保護キーワードへ追加"""
        names = self._get_selected_material_names()
        if not names:
            QtWidgets.QMessageBox.information(self, "材質未選択", "左側のテーブルから登録したい材質を選択してください。")
            return

        added_count = 0
        for name in names:
            if self._add_keyword_smart(name, "skin"):
                added_count += 1

        self.tab_widget.setCurrentIndex(0)
        self._refresh_materials_table()
        if added_count > 0:
            QtWidgets.QMessageBox.information(
                self, "キーワード追加", f"{added_count} 個の材質名を顔・肌保護キーワードに登録しました。"
            )

    def _on_add_selected_to_toon(self):
        """選択した材質名をToon除外キーワードへ追加"""
        names = self._get_selected_material_names()
        if not names:
            QtWidgets.QMessageBox.information(self, "材質未選択", "左側のテーブルから登録したい材質を選択してください。")
            return

        added_count = 0
        for name in names:
            if self._add_keyword_smart(name, "toon"):
                added_count += 1

        self.tab_widget.setCurrentIndex(1)
        self._refresh_materials_table()
        if added_count > 0:
            QtWidgets.QMessageBox.information(
                self, "キーワード追加", f"{added_count} 個の材質名をToon除外キーワードに登録しました。"
            )

    def _on_table_double_clicked(self, row, col):
        """ダブルクリック時に現在アクティブなタブに応じて直接登録"""
        item = self.tbl_materials.item(row, 0)
        if not item or not item.text().strip():
            return

        name = item.text().strip()
        cat = "skin" if self.tab_widget.currentIndex() == 0 else "toon"
        if self._add_keyword_smart(name, cat):
            self._refresh_materials_table()

    def _add_to_list(self, list_widget, line_edit):
        text = line_edit.text().strip()
        if text:
            items = [list_widget.item(i).text() for i in range(list_widget.count())]
            if text not in items:
                list_widget.addItem(text)
            line_edit.clear()
            self._refresh_materials_table()

    def _remove_from_list(self, list_widget):
        for item in list_widget.selectedItems():
            list_widget.takeItem(list_widget.row(item))
        self._refresh_materials_table()

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

    def _collect_data_from_ui(self):
        skin_ja = [self.list_skin_ja.item(i).text().strip() for i in range(self.list_skin_ja.count()) if self.list_skin_ja.item(i).text().strip()]
        skin_en = [self.list_skin_en.item(i).text().strip() for i in range(self.list_skin_en.count()) if self.list_skin_en.item(i).text().strip()]

        toon_ja = [self.list_toon_ja.item(i).text().strip() for i in range(self.list_toon_ja.count()) if self.list_toon_ja.item(i).text().strip()]
        toon_en = [self.list_toon_en.item(i).text().strip() for i in range(self.list_toon_en.count()) if self.list_toon_en.item(i).text().strip()]

        current = load_user_settings()
        current["face_skin_keywords_ja"] = skin_ja
        current["face_skin_keywords_en"] = skin_en
        current["toon_bypass_keywords_ja"] = toon_ja
        current["toon_bypass_keywords_en"] = toon_en
        return current

    def _on_apply_only(self):
        """保存せずに現在のUI設定でシーン内モデルへ反映"""
        data = self._collect_data_from_ui()
        save_user_settings(data)

        target_model = self.cmb_model.currentData()
        res = {}
        if apply_material_protection_to_scene:
            try:
                res = apply_material_protection_to_scene(target_model)
            except Exception as e:
                print(f"[警告] モデルへの即時反映中にエラー: {e}")

        self._refresh_materials_table()
        total = res.get("total_materials", 0)
        skin = res.get("skin_protected", 0)
        toon_bp = res.get("toon_bypassed", 0)
        toon_res = res.get("toon_restored", 0)

        QtWidgets.QMessageBox.information(
            self,
            "モデル反映完了",
            f"シーン内のマテリアルへ設定を反映しました。\n\n"
            f"対象マテリアル総数: {total} 個\n"
            f"テカリ保護（スペキュラ除去）適用: {skin} 個\n"
            f"Toon除外（ハイライト保護）適用: {toon_bp} 個\n"
            f"Toon乗算復帰: {toon_res} 個"
        )

    def _on_save(self):
        """設定を保存し、シーン内モデルへ自動反映"""
        data = self._collect_data_from_ui()
        success = save_user_settings(data)
        if not success:
            QtWidgets.QMessageBox.critical(self, "保存失敗", "設定の保存中にエラーが発生しました。")
            return

        target_model = self.cmb_model.currentData()
        res = {}
        if apply_material_protection_to_scene:
            try:
                res = apply_material_protection_to_scene(target_model)
            except Exception as e:
                print(f"[警告] モデルへの自動反映中にエラー: {e}")

        self._refresh_materials_table()
        total = res.get("total_materials", 0)
        skin = res.get("skin_protected", 0)
        toon_bp = res.get("toon_bypassed", 0)

        QtWidgets.QMessageBox.information(
            self,
            "保存・適用完了",
            f"マテリアル保護・Toon除外設定を保存し、インポート済みモデルへ自動反映しました。\n\n"
            f"対象マテリアル総数: {total} 個\n"
            f"テカリ保護適用: {skin} 個\n"
            f"Toon除外適用: {toon_bp} 個\n\n"
            f"次回の新規モデルインポート時にもこの設定が自動適用されます。"
        )

    def _on_reset_default(self):
        ret = QtWidgets.QMessageBox.question(
            self,
            "初期化の確認",
            "マテリアル保護キーワードおよびToon除外設定を安全な初期デフォルト値に戻しますか？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if ret == QtWidgets.QMessageBox.Yes:
            defaults = get_default_settings()
            self._load_data_to_ui(defaults)
            current = load_user_settings()
            current["face_skin_keywords_ja"] = defaults["face_skin_keywords_ja"]
            current["face_skin_keywords_en"] = defaults["face_skin_keywords_en"]
            current["toon_bypass_keywords_ja"] = defaults["toon_bypass_keywords_ja"]
            current["toon_bypass_keywords_en"] = defaults["toon_bypass_keywords_en"]
            save_user_settings(current)
            self._refresh_materials_table()
            QtWidgets.QMessageBox.information(self, "初期化完了", "設定を初期デフォルト値に戻しました。")


def show_material_protect_dialog():
    """マテリアル保護・Toon除外設定ダイアログを表示します"""
    global _material_protect_dialog_instance

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

    if _material_protect_dialog_instance is not None:
        try:
            _material_protect_dialog_instance.close()
            _material_protect_dialog_instance.deleteLater()
        except Exception:
            pass
        _material_protect_dialog_instance = None

    _material_protect_dialog_instance = MaterialProtectDialog(parent)
    _material_protect_dialog_instance.show()
    _material_protect_dialog_instance.raise_()
    _material_protect_dialog_instance.activateWindow()
