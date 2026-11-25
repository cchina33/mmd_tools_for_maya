# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - PMM プロジェクト解析およびモデルインポート選択ダイアログ
"""

from .common import *

try:
    from ..mmd_parser import pmx, pmd, vmd, pmm
    from ..maya_maya_converters import pmxpaimaya, vmdpaimaya, pmd2pmx
except Exception:
    try:
        from mmd_parser import pmx, pmd, vmd, pmm
        from maya_converters import pmxpaimaya, vmdpaimaya, pmd2pmx
    except Exception:
        import mmd_parser.pmx as pmx
        import mmd_parser.pmd as pmd
        import mmd_parser.vmd as vmd
        import mmd_parser.pmm as pmm
        import maya_converters.pmxpaimaya as pmxpaimaya
        import maya_converters.vmdpaimaya as vmdpaimaya
        import maya_converters.pmd2pmx as pmd2pmx

# ==============================================================================
# PMM (Polygon Movie Maker) プロジェクト解析ダイアログ (試験的機能)
# ==============================================================================
class PmmDropArea(QFrame):
    """PMM ファイル専用のドラッグ＆ドロップ受け入れフレーム"""
    def __init__(self, on_file_dropped=None, parent=None):
        super(PmmDropArea, self).__init__(parent)
        self.on_file_dropped = on_file_dropped
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Sunken)
        self.setStyleSheet("""
            QFrame {
                border: 2px dashed #4a6984;
                border-radius: 6px;
                background-color: #1e252d;
                padding: 10px;
            }
            QFrame:hover {
                border-color: #3498db;
                background-color: #232d38;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.label = QLabel("ここに .pmm ファイルをドラッグ＆ドロップ")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #7f9bb8; font-size: 12px; font-weight: bold;")
        layout.addWidget(self.label)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                filepath = url.toLocalFile()
                if filepath.lower().endswith('.pmm'):
                    event.acceptProposedAction()
                    self.setStyleSheet("""
                        QFrame {
                            border: 2px dashed #2ecc71;
                            border-radius: 6px;
                            background-color: #1f3326;
                            padding: 10px;
                        }
                    """)
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("""
            QFrame {
                border: 2px dashed #4a6984;
                border-radius: 6px;
                background-color: #1e252d;
                padding: 10px;
            }
        """)

    def dropEvent(self, event):
        self.setStyleSheet("""
            QFrame {
                border: 2px dashed #4a6984;
                border-radius: 6px;
                background-color: #1e252d;
                padding: 10px;
            }
        """)
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith('.pmm'):
                if self.on_file_dropped:
                    self.on_file_dropped(filepath)
                event.acceptProposedAction()
                return
        event.ignore()


class PmmModelImportSelectDialog(QDialog):
    """PMM プロジェクト内で検出されたモデルを選択し Maya へインポートするダイアログ"""

    def __init__(self, parent=None, model_items=None, project=None):
        super(PmmModelImportSelectDialog, self).__init__(parent)
        self.parent_dialog = parent
        self.project = project
        self.setWindowTitle("PMM インポート選択")
        self.resize(920, 540)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        self.model_items = model_items or []
        self.audio_item = getattr(self.project, 'audio', None) if self.project else None
        self._init_ui()
        self._populate_table()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 説明ヘッダー
        desc_box = QGroupBox("インポート対象モデル・アセットの選択")
        desc_box.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #5dade2; border: 1px solid #2471a3; "
            "padding: 8px; border-radius: 4px; background-color: #15222e; }"
        )
        desc_layout = QVBoxLayout(desc_box)
        lbl_desc = QLabel(
            "PMM プロジェクト内で検出されたモデルおよびBGM音声の一覧です。Maya へインポートしたい項目にチェックを入れてください。\n"
            "※「解決ファイルパス」列のセルをダブルクリックして、手動でファイル（PMX / PMD / WAV）を指定し直すことができます。\n"
            "※PMD 形式のモデルは既存の変換機能により PMX へ自動変換されてからインポートされます。"
        )
        lbl_desc.setStyleSheet("color: #aed6f1; font-size: 11px; font-weight: normal;")
        lbl_desc.setWordWrap(True)
        desc_layout.addWidget(lbl_desc)
        main_layout.addWidget(desc_box)

        # 一括選択操作バー
        h_sel = QHBoxLayout()
        self.btn_select_all = QPushButton("すべて選択")
        self.btn_select_all.clicked.connect(self._select_all)
        h_sel.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("すべて解除")
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        h_sel.addWidget(self.btn_deselect_all)

        self.btn_select_existing = QPushButton("実在モデルのみ選択")
        self.btn_select_existing.clicked.connect(self._select_existing_only)
        h_sel.addWidget(self.btn_select_existing)

        h_sel.addStretch()
        self.lbl_selected_count = QLabel("選択数: 0")
        self.lbl_selected_count.setStyleSheet("color: #2ecc71; font-weight: bold;")
        h_sel.addWidget(self.lbl_selected_count)
        main_layout.addLayout(h_sel)

        # モデルアセット一覧テーブル
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "選択", "スロット", "モデル名", "形式", "ファイル状態", "モデル照合", "モーション判定", "解決ファイルパス"
        ])
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 130)
        try:
            self.table.horizontalHeader().setStretchLastSection(True)
        except Exception:
            pass
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.cellDoubleClicked.connect(self._on_table_cell_double_clicked)
        main_layout.addWidget(self.table)

        # インポートオプション
        opt_box = QGroupBox("インポート設定")
        opt_layout = QVBoxLayout(opt_box)
        opt_layout.setSpacing(6)

        h_opt1 = QHBoxLayout()
        h_opt1.addWidget(QLabel("スケール倍率:"))
        self.spn_scale = QDoubleSpinBox()
        self.spn_scale.setRange(0.001, 1000.0)
        self.spn_scale.setDecimals(3)
        self.spn_scale.setValue(8.0)
        self.spn_scale.setSingleStep(0.1)
        self.spn_scale.setFixedWidth(80)
        h_opt1.addWidget(self.spn_scale)

        h_opt1.addSpacing(16)
        h_opt1.addWidget(QLabel("マテリアル形式:"))
        self.combo_mat = QComboBox()
        self.combo_mat.addItem("Blinn", 1)
        self.combo_mat.addItem("Phong", 2)
        self.combo_mat.addItem("Lambert", 3)
        self.combo_mat.addItem("StandardSurface", 4)
        self.combo_mat.addItem("MMD Toon Shader (推奨)", 6)
        self.combo_mat.setCurrentIndex(self.combo_mat.count() - 1)
        h_opt1.addWidget(self.combo_mat)

        h_opt1.addStretch()
        opt_layout.addLayout(h_opt1)

        h_opt2 = QHBoxLayout()
        self.cb_physics = QCheckBox("剛体・Joint（物理演算）を作成")
        self.cb_physics.setChecked(True)
        h_opt2.addWidget(self.cb_physics)

        self.cb_morph = QCheckBox("モーフ（ブレンドシェイプ）を作成")
        self.cb_morph.setChecked(True)
        h_opt2.addWidget(self.cb_morph)

        self.cb_bones = QCheckBox("ボーン（スケルトン）を作成")
        self.cb_bones.setChecked(True)
        h_opt2.addWidget(self.cb_bones)
        h_opt2.addStretch()
        opt_layout.addLayout(h_opt2)

        h_opt3 = QHBoxLayout()
        self.cb_group = QCheckBox("モデルごとにグループ化 ({モデル名}_grp)")
        self.cb_group.setChecked(True)
        h_opt3.addWidget(self.cb_group)

        self.cb_inherits = QCheckBox("二重トランスフォーム防止")
        self.cb_inherits.setChecked(True)
        self.cb_inherits.setToolTip("グループ化時にメッシュの inheritsTransform を無効化し、トランスフォームの二重適用を防ぎます。")
        h_opt3.addWidget(self.cb_inherits)

        self.cb_light = QCheckBox("MMD照明を作成 (先頭モデルのみ)")
        self.cb_light.setChecked(True)
        h_opt3.addWidget(self.cb_light)
        h_opt3.addStretch()
        opt_layout.addLayout(h_opt3)

        h_opt4 = QHBoxLayout()
        self.cb_motion = QCheckBox("モデルモーションを書き込む")
        self.cb_motion.setChecked(True)
        h_opt4.addWidget(self.cb_motion)

        self.cb_camera = QCheckBox("カメラモーションを書き込む")
        self.cb_camera.setChecked(True)
        h_opt4.addWidget(self.cb_camera)

        self.cb_audio = QCheckBox("BGM音声 (.wav) を読み込む")
        has_audio = bool(self.audio_item and (self.audio_item.resolved_path or self.audio_item.raw_path))
        self.cb_audio.setChecked(self.audio_item.exists if (self.audio_item and has_audio) else True)
        self.cb_audio.stateChanged.connect(self._on_cb_audio_changed)
        h_opt4.addWidget(self.cb_audio)
        h_opt4.addStretch()
        opt_layout.addLayout(h_opt4)

        main_layout.addWidget(opt_box)

        # アクションボタン
        h_btns = QHBoxLayout()
        self.btn_run_import = QPushButton("選択したモデルをインポート")
        self.btn_run_import.setStyleSheet(
            "QPushButton { background-color: #1e8449; color: #fff; font-weight: bold; padding: 8px 16px; border-radius: 4px; font-size: 12px; } "
            "QPushButton:hover { background-color: #27ae60; } "
            "QPushButton:disabled { background-color: #566573; color: #a6acaf; }"
        )
        self.btn_run_import.clicked.connect(self._run_import)
        h_btns.addWidget(self.btn_run_import)

        self.btn_close = QPushButton("閉じる")
        self.btn_close.clicked.connect(self.close)
        h_btns.addWidget(self.btn_close)

        main_layout.addLayout(h_btns)

    def _populate_table(self):
        self.table.blockSignals(True)
        has_audio = bool(self.audio_item)
        total_rows = len(self.model_items) + (1 if has_audio else 0)
        self.table.setRowCount(total_rows)

        for row, item in enumerate(self.model_items):
            target_path = item.resolved_path or item.raw_path or ""
            ext = os.path.splitext(target_path)[1].upper()
            ext_label = ext.replace(".", "") if ext else "不明"

            # 実在かつ旧データでない場合は初期チェックON
            is_valid = item.exists and not getattr(item, "is_old_data", False)

            # チェックボックスアイテム
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk_item.setCheckState(Qt.Checked if is_valid else Qt.Unchecked)
            chk_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, chk_item)

            # スロット番号
            slot_num = getattr(item, 'slot', row)
            slot_item = QTableWidgetItem(str(slot_num + 1))
            slot_item.setTextAlignment(Qt.AlignCenter)
            slot_item.setData(Qt.UserRole, item)
            self.table.setItem(row, 1, slot_item)

            # モデル名
            name_text = getattr(item, 'name', '') or getattr(item, 'source_name', '') or f"モデル_{row + 1}"
            name_item = QTableWidgetItem(name_text)
            self.table.setItem(row, 2, name_item)

            # 形式
            ext_item = QTableWidgetItem(ext_label)
            ext_item.setTextAlignment(Qt.AlignCenter)
            if ext_label == "PMD":
                ext_item.setForeground(QColor("#f39c12"))
            elif ext_label == "PMX":
                ext_item.setForeground(QColor("#3498db"))
            self.table.setItem(row, 3, ext_item)

            # ファイル状態
            if item.exists:
                st_item = QTableWidgetItem("存在")
                st_item.setForeground(QColor("#2ecc71"))
            else:
                st_item = QTableWidgetItem("見つかりません")
                st_item.setForeground(QColor("#e74c3c"))
            st_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, st_item)

            # モデル照合
            match_str = item.match_status or "-"
            match_item = QTableWidgetItem(match_str)
            match_item.setTextAlignment(Qt.AlignCenter)
            if match_str == "一致":
                match_item.setForeground(QColor("#2ecc71"))
            elif match_str == "部分一致":
                match_item.setForeground(QColor("#f39c12"))
            elif match_str == "不一致":
                match_item.setForeground(QColor("#e67e22"))
            self.table.setItem(row, 5, match_item)

            # モーション判定
            mot_str = item.motion_type or "なし"
            mot_item = QTableWidgetItem(mot_str)
            mot_item.setTextAlignment(Qt.AlignCenter)
            if "モーション" in mot_str:
                mot_item.setForeground(QColor("#3498db"))
            elif "ポーズ" in mot_str:
                mot_item.setForeground(QColor("#9b59b6"))
            self.table.setItem(row, 6, mot_item)

            # 解決ファイルパス
            path_item = QTableWidgetItem(item.resolved_path or item.raw_path or "-")
            path_item.setToolTip(item.resolved_path or item.raw_path or "ダブルクリックしてファイルを選択")
            self.table.setItem(row, 7, path_item)

        # BGMアイテムの行を追加（存在する場合）
        if has_audio:
            audio_row = len(self.model_items)
            audio_path = self.audio_item.resolved_path or self.audio_item.raw_path or ""
            audio_ext = os.path.splitext(audio_path)[1].upper().replace(".", "") or "WAV"
            audio_name = getattr(self.audio_item, 'name', '') or os.path.basename(audio_path) or "BGM音声"

            # チェックボックス
            chk_audio = QTableWidgetItem()
            chk_audio.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            audio_checked = bool(self.audio_item.exists and self.cb_audio.isChecked())
            chk_audio.setCheckState(Qt.Checked if audio_checked else Qt.Unchecked)
            chk_audio.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(audio_row, 0, chk_audio)

            # スロット（BGMと表記）
            slot_audio = QTableWidgetItem("BGM")
            slot_audio.setTextAlignment(Qt.AlignCenter)
            slot_audio.setForeground(QColor("#9b59b6"))
            slot_audio.setData(Qt.UserRole, self.audio_item)
            self.table.setItem(audio_row, 1, slot_audio)

            # 名称
            name_audio = QTableWidgetItem(f"[BGM] {audio_name}")
            name_audio.setForeground(QColor("#e8daef"))
            self.table.setItem(audio_row, 2, name_audio)

            # 形式
            ext_audio = QTableWidgetItem(audio_ext)
            ext_audio.setTextAlignment(Qt.AlignCenter)
            ext_audio.setForeground(QColor("#9b59b6"))
            self.table.setItem(audio_row, 3, ext_audio)

            # ファイル状態
            if self.audio_item.exists:
                st_audio = QTableWidgetItem("存在")
                st_audio.setForeground(QColor("#2ecc71"))
            else:
                st_audio = QTableWidgetItem("見つかりません")
                st_audio.setForeground(QColor("#e74c3c"))
            st_audio.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(audio_row, 4, st_audio)

            # モデル照合
            match_audio = QTableWidgetItem("-")
            match_audio.setTextAlignment(Qt.AlignCenter)
            match_audio.setForeground(QColor("#7f8c8d"))
            self.table.setItem(audio_row, 5, match_audio)

            # モーション判定
            mot_audio = QTableWidgetItem("BGM音声")
            mot_audio.setTextAlignment(Qt.AlignCenter)
            mot_audio.setForeground(QColor("#9b59b6"))
            self.table.setItem(audio_row, 6, mot_audio)

            # 解決ファイルパス
            path_audio = QTableWidgetItem(audio_path or "-")
            path_audio.setToolTip(audio_path or "ダブルクリックして音声ファイルを選択")
            self.table.setItem(audio_row, 7, path_audio)

        self.table.blockSignals(False)
        self._update_selected_count()

    def _on_item_changed(self, item):
        if item.column() == 0:
            row = item.row()
            slot_item = self.table.item(row, 1)
            if slot_item:
                item_data = slot_item.data(Qt.UserRole)
                if getattr(item_data, 'kind', '') == 'Audio':
                    self.cb_audio.blockSignals(True)
                    self.cb_audio.setChecked(item.checkState() == Qt.Checked)
                    self.cb_audio.blockSignals(False)
            self._update_selected_count()

    def _on_cb_audio_changed(self, state):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            slot_item = self.table.item(row, 1)
            if slot_item:
                item_data = slot_item.data(Qt.UserRole)
                if getattr(item_data, 'kind', '') == 'Audio':
                    chk_item = self.table.item(row, 0)
                    if chk_item:
                        is_checked = (state == Qt.Checked.value if hasattr(Qt.Checked, 'value') else state == Qt.Checked)
                        chk_item.setCheckState(Qt.Checked if is_checked else Qt.Unchecked)
                    break
        self.table.blockSignals(False)
        self._update_selected_count()

    def _select_all(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)
        self.table.blockSignals(False)
        self.cb_audio.blockSignals(True)
        self.cb_audio.setChecked(True)
        self.cb_audio.blockSignals(False)
        self._update_selected_count()

    def _deselect_all(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
        self.table.blockSignals(False)
        self.cb_audio.blockSignals(True)
        self.cb_audio.setChecked(False)
        self.cb_audio.blockSignals(False)
        self._update_selected_count()

    def _select_existing_only(self):
        self.table.blockSignals(True)
        audio_checked = False
        for row in range(self.table.rowCount()):
            slot_item = self.table.item(row, 1)
            chk_item = self.table.item(row, 0)
            if slot_item and chk_item:
                target_item = slot_item.data(Qt.UserRole)
                if getattr(target_item, 'kind', '') == 'Audio':
                    is_valid = bool(target_item and target_item.exists)
                    chk_item.setCheckState(Qt.Checked if is_valid else Qt.Unchecked)
                    audio_checked = is_valid
                else:
                    is_valid = bool(target_item and target_item.exists and not getattr(target_item, "is_old_data", False))
                    chk_item.setCheckState(Qt.Checked if is_valid else Qt.Unchecked)
        self.table.blockSignals(False)
        self.cb_audio.blockSignals(True)
        self.cb_audio.setChecked(audio_checked)
        self.cb_audio.blockSignals(False)
        self._update_selected_count()

    def _on_table_cell_double_clicked(self, row, column):
        """解決ファイルパス列のセルをダブルクリックした際にファイル選択ダイアログを表示"""
        if column == 7:
            self._change_file_for_row(row)

    def _change_file_for_row(self, row):
        """指定行のアセットファイル（PMX / PMD / WAV）をユーザー指定のファイルに変更"""
        slot_item = self.table.item(row, 1)
        if not slot_item:
            return
        item_data = slot_item.data(Qt.UserRole)
        if not item_data:
            return

        is_audio = getattr(item_data, 'kind', '') == 'Audio'

        current_path = getattr(item_data, 'resolved_path', '') or getattr(item_data, 'raw_path', '') or ""
        pmm_ref_path = getattr(self.project, 'pmm_path', '') or getattr(self.parent_dialog, 'pmm_path', '') or ""
        init_dir = ""
        if current_path and os.path.exists(os.path.dirname(current_path)):
            init_dir = os.path.dirname(current_path)
        elif pmm_ref_path and os.path.exists(os.path.dirname(pmm_ref_path)):
            init_dir = os.path.dirname(pmm_ref_path)

        if is_audio:
            dialog_title = "BGM音声ファイル (.wav) を選択"
            file_filter = "WAV音声ファイル (*.wav);;すべてのファイル (*.*)"
        else:
            model_name = getattr(item_data, 'name', '') or getattr(item_data, 'source_name', '') or f"モデル_{row + 1}"
            dialog_title = f"モデルファイル (PMX / PMD) を選択: {model_name}"
            file_filter = "MMDモデル (*.pmx *.pmd);;PMXモデル (*.pmx);;PMDモデル (*.pmd);;すべてのファイル (*.*)"

        chosen_file, _ = QFileDialog.getOpenFileName(self, dialog_title, init_dir, file_filter)
        if not chosen_file:
            return

        chosen_file = os.path.normpath(chosen_file).replace("\\", "/")
        file_exists = os.path.exists(chosen_file)

        item_data.resolved_path = chosen_file
        item_data.exists = file_exists

        self.table.blockSignals(True)

        if is_audio:
            ext_str = os.path.splitext(chosen_file)[1].upper().replace(".", "") or "WAV"
            ext_item = self.table.item(row, 3)
            if ext_item:
                ext_item.setText(ext_str)

            st_item = self.table.item(row, 4)
            if st_item:
                if file_exists:
                    st_item.setText("存在")
                    st_item.setForeground(QColor("#2ecc71"))
                else:
                    st_item.setText("見つかりません")
                    st_item.setForeground(QColor("#e74c3c"))

            path_item = self.table.item(row, 7)
            if path_item:
                path_item.setText(chosen_file)
                path_item.setToolTip(chosen_file)

            if file_exists:
                chk_item = self.table.item(row, 0)
                if chk_item:
                    chk_item.setCheckState(Qt.Checked)
                self.cb_audio.blockSignals(True)
                self.cb_audio.setChecked(True)
                self.cb_audio.blockSignals(False)

            print(f">> BGM音声パスを設定しました: {chosen_file}")
        else:
            try:
                if hasattr(pmm, '_verify_model_item'):
                    pmm._verify_model_item(item_data, chosen_file)
            except Exception as e:
                print(f"  [警告] モデル照合中に例外: {e}")

            ext_str = os.path.splitext(chosen_file)[1].upper().replace(".", "") or "不明"
            ext_item = self.table.item(row, 3)
            if ext_item:
                ext_item.setText(ext_str)
                if ext_str == "PMD":
                    ext_item.setForeground(QColor("#f39c12"))
                elif ext_str == "PMX":
                    ext_item.setForeground(QColor("#3498db"))
                else:
                    ext_item.setForeground(QColor("#ecf0f1"))

            st_item = self.table.item(row, 4)
            if st_item:
                if file_exists:
                    st_item.setText("存在")
                    st_item.setForeground(QColor("#2ecc71"))
                else:
                    st_item.setText("見つかりません")
                    st_item.setForeground(QColor("#e74c3c"))

            match_str = getattr(item_data, 'match_status', '-') or "-"
            match_item = self.table.item(row, 5)
            if match_item:
                match_item.setText(match_str)
                if match_str == "一致":
                    match_item.setForeground(QColor("#2ecc71"))
                elif match_str == "部分一致":
                    match_item.setForeground(QColor("#f39c12"))
                elif match_str == "不一致":
                    match_item.setForeground(QColor("#e67e22"))
                else:
                    match_item.setForeground(QColor("#7f8c8d"))
                match_detail = getattr(item_data, 'match_detail', '')
                if match_detail:
                    match_item.setToolTip(match_detail)

            path_item = self.table.item(row, 7)
            if path_item:
                path_item.setText(chosen_file)
                path_item.setToolTip(chosen_file)

            if file_exists:
                chk_item = self.table.item(row, 0)
                if chk_item:
                    chk_item.setCheckState(Qt.Checked)

            model_name = getattr(item_data, 'name', '') or getattr(item_data, 'source_name', '') or f"モデル_{row + 1}"
            print(f">> モデルパスを設定しました [{model_name}]: {chosen_file} (照合: {match_str})")

        self.table.blockSignals(False)
        self._update_selected_count()

    def _update_selected_count(self):
        count = 0
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                count += 1
        self.lbl_selected_count.setText(f"選択数: {count} / {self.table.rowCount()}")
        self.btn_run_import.setEnabled(count > 0)

    def _run_import(self):
        targets = []
        import_audio = False
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            if chk and chk.checkState() == Qt.Checked:
                slot_item = self.table.item(row, 1)
                if slot_item:
                    item_data = slot_item.data(Qt.UserRole)
                    if getattr(item_data, 'kind', '') == 'Audio':
                        import_audio = True
                    elif item_data:
                        targets.append(item_data)

        if not targets and not import_audio:
            QMessageBox.warning(self, "案内", "インポート対象（モデルまたはBGM）が選択されていません。")
            return

        if targets:
            confirm_msg = f"選択された {len(targets)} 体のモデル"
            if import_audio:
                confirm_msg += " および BGM音声"
            confirm_msg += " を Maya へインポートします。\n続行しますか？"
        else:
            confirm_msg = "選択された BGM音声を Maya へ読み込みます。\n続行しますか？"

        res = QMessageBox.question(
            self,
            "インポートの確認",
            confirm_msg,
            QMessageBox.Yes | QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return

        scale = self.spn_scale.value()
        mat_type = self.combo_mat.currentData()
        create_physics = self.cb_physics.isChecked()
        create_morph = self.cb_morph.isChecked()
        create_bones = self.cb_bones.isChecked()
        group_models = self.cb_group.isChecked()
        prevent_double = self.cb_inherits.isChecked()
        create_light_opt = self.cb_light.isChecked()
        apply_motion_opt = self.cb_motion.isChecked()
        apply_camera_opt = self.cb_camera.isChecked()
        apply_audio_opt = self.cb_audio.isChecked() or import_audio

        # インポート開始直後に実行ログダイアログ（tab_importと同等）を生成・起動
        log_dialog = ExecutionLogDialog(self, title="PMMインポート実行ログ")

        def import_task():
            total_start_time = time.time()

            # タイムスライダーを0フレームにリセット
            if mc:
                try:
                    mc.currentTime(0)
                except Exception:
                    pass

            success_count = 0
            total_targets = len(targets)
            extra_steps = (1 if apply_camera_opt else 0) + (1 if apply_audio_opt else 0) + 1
            total_steps = max(1, total_targets + extra_steps)
            current_step = 0

            if targets:
                print("==================================================")
                print(f"PMM 一括インポート開始 (対象: {total_targets} 体)")
                print("==================================================")

            for idx, model_item in enumerate(targets):
                current_step += 1
                log_dialog.update_progress(current_step, total_steps, label_prefix="PMMインポート", unit="ステップ")

                file_path = model_item.resolved_path or model_item.raw_path
                model_name = getattr(model_item, 'name', '') or getattr(model_item, 'source_name', '') or f"Model_{idx + 1}"

                print(f"\n[{idx + 1}/{total_targets}] モデルインポート: {model_name}")

                if not file_path or not os.path.exists(file_path):
                    print(f"  [スキップ] ファイルが未設定または見つからないためスルーしました: {model_name} ({file_path or '未設定'})")
                    continue

                # PMD形式の自動PMX変換
                if file_path.lower().endswith(".pmd"):
                    try:
                        print("  - PMD形式を検出: PMXへ自動変換中...")
                        file_path = pmd2pmx.convert_pmd_to_pmx(file_path)
                        print(f"  - PMX変換終了: {os.path.basename(file_path)}")
                    except Exception as e:
                        print(f"  [警告] PMD変換エラー: {e}")
                        continue

                # 原点でインポートする前のトップレベルノードを記録
                before_assemblies = set(mc.ls(assemblies=True) or []) if mc else set()

                try:
                    # ユーザー辞書チェック（存在する場合）
                    if file_path.lower().endswith(".pmx") and check_and_prompt_user_dict:
                        try:
                            check_and_prompt_user_dict(log_dialog, file_path)
                        except Exception as e:
                            print(f"  [情報] 辞書確認: {e}")

                    create_light = create_light_opt and (idx == 0)
                    ret = pmxpaimaya.import_pmx(
                        file_path,
                        scale=scale,
                        split_by_material=False,
                        create_blendshapes=create_morph,
                        create_joints=create_bones,
                        material_type=mat_type,
                        create_light=create_light,
                        set_untone_mapped=True,
                        enable_toon=True,
                        shadow_mode=1,
                        create_ground_shadow=create_light,
                        show_completion_message=False,
                        prevent_motion_darkening=True,
                        create_physics=create_physics
                    )
                    print("  - Mayaへの読み込み終了")

                    # メッシュの二重トランスフォーム防止
                    if prevent_double and mc and ret:
                        mesh_node = ret[0]
                        if mesh_node and mc.objExists(mesh_node):
                            mc.setAttr(f"{mesh_node}.inheritsTransform", False)
                            print(f"  - 二重トランスフォーム防止設定 ({mesh_node})")

                    # 生成ノードのグループ化
                    if group_models and mc:
                        after_assemblies = set(mc.ls(assemblies=True) or [])
                        new_nodes = [
                            n for n in (after_assemblies - before_assemblies)
                            if not n.startswith("mmd_lighting") and not n.startswith("mmd_ground_shadow")
                        ]
                        if new_nodes:
                            safe_name = safe_node_name(model_name)
                            grp_name = f"{safe_name}_grp"
                            g_idx = 1
                            while mc.objExists(grp_name):
                                grp_name = f"{safe_name}_{g_idx}_grp"
                                g_idx += 1
                            model_group = mc.group(new_nodes, name=grp_name)
                            if not mc.attributeQuery("isMmdGroup", node=model_group, exists=True):
                                mc.addAttr(model_group, longName="isMmdGroup", attributeType="bool", defaultValue=True)
                            print(f"  - グループ '{model_group}' にまとめました")

                    # PMMモーションデータをVMDファイルとして自動変換・保存しインポート欄にセット
                    if getattr(model_item, 'motion', None):
                        mot = model_item.motion
                        has_keys = bool(getattr(mot, 'bone_frames', None)) or bool(getattr(mot, 'morph_frames', None))
                        if has_keys:
                            try:
                                plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                                pmm_vmd_dir = os.path.join(plugin_root, "asset", "userdata", "pmm_vmd_data")
                                os.makedirs(pmm_vmd_dir, exist_ok=True)
                                safe_name = safe_node_name(model_name)
                                pmm_vmd_file = os.path.join(pmm_vmd_dir, f"{safe_name}_pmm_motion.vmd").replace("\\", "/")
                                vmd.save(pmm_vmd_file, mot)
                                print(f"  - PMMモーションをVMDとして保存終了: {pmm_vmd_file}")

                                # 生成されたモデルノードにモデル専用VMDパスを記録
                                if mc:
                                    mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", pmm_vmd_file))
                                    target_node = ret[0] if (isinstance(ret, (list, tuple)) and len(ret) > 0) else ret
                                    for attach_node in [target_node, model_group]:
                                        if attach_node and mc.objExists(attach_node):
                                            if not mc.attributeQuery("mmdVmdPath", node=attach_node, exists=True):
                                                mc.addAttr(attach_node, longName="mmdVmdPath", dataType="string")
                                            mc.setAttr(f"{attach_node}.mmdVmdPath", pmm_vmd_file, type="string")

                                parent_win = self.parent()
                                if parent_win:
                                    # 物理ベイクGUIタブのVMD入力欄へセット
                                    if hasattr(parent_win, 'physics_gui_tab') and hasattr(parent_win.physics_gui_tab, 'le_vmd_source_path'):
                                        parent_win.physics_gui_tab.le_vmd_source_path.setText(pmm_vmd_file)
                                    # VMDインポートタブの入力欄へセット
                                    if hasattr(parent_win, 'vmd_tab') and hasattr(parent_win.vmd_tab, 'le_vmd_path'):
                                        parent_win.vmd_tab.le_vmd_path.setText(pmm_vmd_file)
                            except Exception as ex_vmd:
                                print(f"  [警告] PMMモーションのVMD保存に失敗しました: {ex_vmd}")

                    # PMMモーションデータの書き込み（ボーン・モーフ・IK・足膝ポールベクター）
                    if apply_motion_opt and getattr(model_item, 'motion', None) and ret:
                        mot = model_item.motion
                        has_bone_keys = bool(mot.bone_frames)
                        has_morph_keys = bool(mot.morph_frames)

                        if has_bone_keys or has_morph_keys:
                            if mc:
                                try:
                                    mc.currentTime(0)
                                except Exception:
                                    pass

                            print(f"  - PMMモーション適用中: ボーン {len(mot.bone_frames)} 系統 / モーフ {len(mot.morph_frames)} 系統")
                            try:
                                target_node = ret[0] if (isinstance(ret, (list, tuple)) and len(ret) > 0) else ret
                                resolved_model, joint_map, morph_map = vmdpaimaya.resolve_model_structure(target_node)

                                # ボーンアニメーションの適用
                                if has_bone_keys and joint_map:
                                    b_cnt, b_keys = vmdpaimaya.apply_bone_motion(mot, joint_map, scale, resolved_model)
                                    print(f"    * ボーンキー設定: {b_cnt} 本 ({b_keys} キー)")

                                    # 足IK制御フレームの適用
                                    vmdpaimaya.apply_ik_motion(mot, resolved_model)

                                    # 膝の曲がり方向と外開きポールベクターの自動追従設定
                                    vmdpaimaya.apply_leg_knee_orientation(mot, joint_map, resolved_model, scale)

                                # モーフ（ブレンドシェイプ）アニメーションの適用
                                if has_morph_keys and morph_map:
                                    m_cnt, m_keys = vmdpaimaya.apply_morph_motion(mot, morph_map, resolved_model)
                                    print(f"    * 表情モーフ設定: {m_cnt} 種 ({m_keys} キー)")

                            except Exception as mot_err:
                                print(f"    [警告] モーション書き込み中に例外: {mot_err}")

                    success_count += 1
                except Exception as e:
                    print(f"  [エラー] インポート中に例外が発生しました: {e}\n{traceback.format_exc()}")

            # 各モデル終了後、カメラモーションが存在する場合の書き込み
            cam_motion = getattr(self.project, 'camera_motion', None) if self.project else None
            if apply_camera_opt and cam_motion and cam_motion.camera_frames:
                current_step += 1
                log_dialog.update_progress(current_step, total_steps, label_prefix="カメラ構築", unit="ステップ")

                if mc:
                    try:
                        mc.currentTime(0)
                    except Exception:
                        pass

                print(f"\n>> カメラモーション適用中: {len(cam_motion.camera_frames)} キーフレーム")
                try:
                    cam_locator = vmdpaimaya.apply_camera_motion(cam_motion, scale=scale)
                    if cam_locator:
                        print(f"  - MMDカメラ構築終了: {cam_locator}")
                except Exception as cam_err:
                    print(f"  [警告] カメラモーション書き込み中に例外: {cam_err}")

            # BGM音声 (.wav) の読み込み・タイムライン接続
            audio_item = getattr(self.project, 'audio', None) if self.project else None
            if apply_audio_opt and audio_item:
                current_step += 1
                log_dialog.update_progress(current_step, total_steps, label_prefix="BGM読み込み", unit="ステップ")

                wav_path = audio_item.resolved_path or audio_item.raw_path
                if wav_path and os.path.exists(wav_path):
                    print(f"\n>> BGM音声ファイル読み込み中: {os.path.basename(wav_path)}")
                    try:
                        audio_node = vmdpaimaya.import_audio(wav_path)
                        if audio_node:
                            print(f"  - 音声ノード作成終了: {audio_node}")
                    except Exception as a_err:
                        print(f"  [警告] 音声ファイル読み込み中に例外: {a_err}")
                elif wav_path:
                    print(f"  [スキップ] BGM音声ファイルが見つからないためスルーしました: {wav_path}")
                else:
                    print("  [スキップ] BGM音声ファイルが未設定のためスルーしました。")

            # タイムライン再生範囲の更新
            max_timeline_frame = 0
            if self.project and getattr(self.project, 'last_registered_frame', 0) > 0:
                max_timeline_frame = self.project.last_registered_frame
            elif targets:
                max_timeline_frame = max([getattr(t, 'max_frame', 0) for t in targets], default=0)

            if max_timeline_frame > 0 and mc:
                try:
                    mc.currentUnit(time='ntsc')
                    mc.playbackOptions(minTime=0, maxTime=max_timeline_frame, animationStartTime=0, animationEndTime=max_timeline_frame)
                    mc.currentTime(0)
                    print(f">> タイムライン範囲設定: 0 - {max_timeline_frame} フレーム (30fps)")
                except Exception:
                    pass

            # ビューポートライティングの復元
            try:
                vmdpaimaya.restore_viewport_lighting(prevent_motion_darkening=True)
            except Exception:
                pass

            # ステージ影モードの最適化（ステージモデル検出時は地面影プレーンを自動非表示）
            try:
                pmxpaimaya.optimize_model_meshes_for_mmd_lighting(auto_stage_detect=True)
                pmxpaimaya.set_ground_shadow_mode(stage_mode=None)
            except Exception:
                pass

            current_step = total_steps
            log_dialog.update_progress(current_step, total_steps, label_prefix="終了", unit="ステップ")

            total_elapsed = time.time() - total_start_time
            print("==================================================")
            print(f"PMM インポートが終了しました！ (成功: {success_count} / {len(targets)} 体, 所要時間: {total_elapsed:.2f}秒)")
            print("==================================================")
            return True

        # ログウィンドウを直ちに起動して各タスクを実行
        success = log_dialog.run_task(import_task)
        if success and mc:
            mc.inViewMessage(amg='<span style="color:#52b7ff;">MMD Tools for Maya:</span> PMMインポートが終了しました。', pos='topCenter', fade=True)


class PmmAnalysisDialog(QDialog):
    """PMM プロジェクト解析および参照ファイル一覧表示ダイアログ（2カラム構成）"""
    def __init__(self, parent=None):
        super(PmmAnalysisDialog, self).__init__(parent)
        self.parent_tab = parent
        self.setWindowTitle("pmmから読み込む (試験的機能) - プロジェクト解析")
        self.resize(1200, 700)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.setAcceptDrops(True)

        self.current_project = None
        self._all_items = []

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ヘッダー説明ボックス
        desc_box = QGroupBox("PMM プロジェクト解析について")
        desc_box.setStyleSheet("QGroupBox { font-weight: bold; color: #5dade2; border: 1px solid #2471a3; padding: 10px; border-radius: 4px; background-color: #15222e; }")
        desc_layout = QVBoxLayout(desc_box)
        lbl_desc = QLabel(
            "MikuMikuDance のプロジェクトファイル (.pmm) を解析し、画面解像度・カメラ視野角などの設定や、\n"
            "プロジェクト内で参照されているモデル (.pmx / .pmd)、アクセサリ (.x)、音声 (.wav) などの外部ファイルパスを検出・検証します。"
        )
        lbl_desc.setStyleSheet("color: #aed6f1; font-size: 12px; font-weight: normal;")
        lbl_desc.setWordWrap(True)
        desc_layout.addWidget(lbl_desc)
        main_layout.addWidget(desc_box)

        # 左右 2カラム スプリッター
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #2c3e50; width: 4px; }")

        # -------------------------------------------------------------
        # 左カラム: ファイル選択・基本情報・ログ
        # -------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(8)

        # ファイル選択グループ
        file_box = QGroupBox("PMM ファイル選択")
        file_layout = QVBoxLayout(file_box)
        file_layout.setSpacing(6)

        h_path = QHBoxLayout()
        self.le_path = QLineEdit()
        self.le_path.setPlaceholderText(".pmm ファイルを選択またはドロップしてください...")
        self.le_path.returnPressed.connect(self._on_path_entered)
        h_path.addWidget(self.le_path)

        self.btn_browse = QPushButton("参照...")
        self.btn_browse.setFixedWidth(75)
        self.btn_browse.clicked.connect(self._on_browse)
        h_path.addWidget(self.btn_browse)
        file_layout.addLayout(h_path)

        # ドロップゾーン
        self.drop_area = PmmDropArea(on_file_dropped=self._analyze_file, parent=self)
        file_layout.addWidget(self.drop_area)

        # 再解析ボタン
        self.btn_reanalyze = QPushButton("再解析を実行")
        self.btn_reanalyze.setStyleSheet("QPushButton { background-color: #2e4053; color: #fff; padding: 6px; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #34495e; }")
        self.btn_reanalyze.clicked.connect(self._on_reanalyze)
        file_layout.addWidget(self.btn_reanalyze)

        left_layout.addWidget(file_box)

        # プロジェクト基本情報グループ
        info_box = QGroupBox("プロジェクト基本情報")
        info_layout = QVBoxLayout(info_box)
        info_layout.setSpacing(4)

        self.lbl_version = QLabel("バージョン: -")
        self.lbl_resolution = QLabel("出力解像度: -")
        self.lbl_fov = QLabel("カメラ視野角: -")
        self.lbl_camera = QLabel("カメラ情報: -")
        self.lbl_counts = QLabel("検出アセット: モデル 0 / アクセサリ 0 / 音声 0")

        for lbl in [self.lbl_version, self.lbl_resolution, self.lbl_fov, self.lbl_camera, self.lbl_counts]:
            lbl.setStyleSheet("color: #d5dbdb; font-size: 11px;")
            info_layout.addWidget(lbl)

        left_layout.addWidget(info_box)

        # 解析ロググループ
        log_box = QGroupBox("解析ログ")
        log_layout = QVBoxLayout(log_box)
        log_layout.setSpacing(6)

        self.te_log = QTextEdit()
        self.te_log.setReadOnly(True)
        self.te_log.setStyleSheet("QTextEdit { background-color: #11181f; color: #a3c9e2; font-family: Consolas, monospace; font-size: 11px; border: 1px solid #283747; }")
        log_layout.addWidget(self.te_log)

        h_log_btn = QHBoxLayout()
        self.btn_copy_log = QPushButton("ログをコピー")
        self.btn_copy_log.clicked.connect(self._copy_log)
        h_log_btn.addWidget(self.btn_copy_log)

        self.btn_clear_log = QPushButton("ログをクリア")
        self.btn_clear_log.clicked.connect(self.te_log.clear)
        h_log_btn.addWidget(self.btn_clear_log)
        log_layout.addLayout(h_log_btn)

        left_layout.addWidget(log_box)
        splitter.addWidget(left_widget)

        # -------------------------------------------------------------
        # 右カラム: 参照ファイル一覧テーブル
        # -------------------------------------------------------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(8)

        table_box = QGroupBox("参照ファイル一覧")
        table_layout = QVBoxLayout(table_box)
        table_layout.setSpacing(6)

        # 上部フィルタ＆ステータスバー
        h_filter = QHBoxLayout()
        h_filter.addWidget(QLabel("種別フィルタ:"))
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["すべて表示", "モデル (.pmx / .pmd)", "アクセサリ (.x)", "音声・メディア"])
        self.combo_filter.currentIndexChanged.connect(self._update_table)
        h_filter.addWidget(self.combo_filter)

        h_filter.addSpacing(14)
        self.cb_show_missing = QCheckBox("ファイルが存在しない")
        self.cb_show_missing.setToolTip("ファイルが存在しないアイテム（旧データ・未検出パスなど）の表示・非表示を切り替えます")
        self.cb_show_missing.setChecked(True)
        self.cb_show_missing.stateChanged.connect(self._update_table)
        h_filter.addWidget(self.cb_show_missing)

        h_filter.addStretch()
        self.lbl_stats = QLabel("アイテム数: 0")
        self.lbl_stats.setStyleSheet("color: #f39c12; font-weight: bold;")
        h_filter.addWidget(self.lbl_stats)
        table_layout.addLayout(h_filter)

        # テーブル
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "No.", "種別", "名称", "ファイル状態", "モデル照合", "モーション判定", "最大フレーム", "解決ファイルパス"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(5, 130)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemDoubleClicked.connect(self._on_table_double_clicked)
        table_layout.addWidget(self.table)

        # テーブル操作バー
        h_table_actions = QHBoxLayout()
        lbl_hint = QLabel("※右クリックでパスのコピー、ダブルクリックで配置場所を開きます。")
        lbl_hint.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        h_table_actions.addWidget(lbl_hint)
        h_table_actions.addStretch()

        self.btn_copy_resolved = QPushButton("解決パスをコピー")
        self.btn_copy_resolved.clicked.connect(self._copy_selected_resolved_path)
        h_table_actions.addWidget(self.btn_copy_resolved)

        self.btn_open_folder = QPushButton("エクスプローラーで開く")
        self.btn_open_folder.clicked.connect(self._open_selected_in_explorer)
        h_table_actions.addWidget(self.btn_open_folder)

        self.btn_import_models = QPushButton("インポート設定...")
        self.btn_import_models.setStyleSheet("QPushButton { background-color: #1e8449; color: #fff; font-weight: bold; padding: 5px 12px; border-radius: 4px; } QPushButton:hover { background-color: #27ae60; } QPushButton:disabled { background-color: #566573; color: #a6acaf; }")
        self.btn_import_models.setEnabled(False)
        self.btn_import_models.clicked.connect(self._open_model_import_dialog)
        h_table_actions.addWidget(self.btn_import_models)
        table_layout.addLayout(h_table_actions)

        right_layout.addWidget(table_box)
        splitter.addWidget(right_widget)

        # スプリッターの初期幅比率設定
        splitter.setSizes([420, 760])
        main_layout.addWidget(splitter)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                filepath = url.toLocalFile()
                if filepath.lower().endswith('.pmm'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith('.pmm'):
                self._analyze_file(filepath)
                event.acceptProposedAction()
                return
        event.ignore()

    def _on_browse(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "PMM ファイルを選択",
            "",
            "MMD プロジェクトファイル (*.pmm);;すべてのファイル (*.*)"
        )
        if filepath:
            self._analyze_file(filepath)

    def _on_path_entered(self):
        path = self.le_path.text().strip().strip('"').strip("'")
        if path:
            self._analyze_file(path)

    def _on_reanalyze(self):
        path = self.le_path.text().strip().strip('"').strip("'")
        if path:
            self._analyze_file(path)

    def _analyze_file(self, filepath):
        norm_path = os.path.abspath(filepath)
        self.le_path.setText(norm_path)
        self.te_log.clear()

        if pmm is None:
            self.te_log.append("エラー: pmm 解析モジュールがロードできませんでした。")
            return

        try:
            project = pmm.parse_pmm(norm_path)
            self.current_project = project
            self._all_items = project.all_items()

            for line in project.logs:
                self.te_log.append(line)

            # 基本情報
            ver_text = project.version or "不明"
            sig_text = f"{project.signature} ({ver_text})" if project.signature else ver_text
            self.lbl_version.setText(f"バージョン: {sig_text}")

            if project.render_width and project.render_height:
                self.lbl_resolution.setText(f"出力解像度: {project.render_width} x {project.render_height}")
            else:
                self.lbl_resolution.setText("出力解像度: 未記録")

            if project.camera_fov:
                self.lbl_fov.setText(f"カメラ視野角: {project.camera_fov:.1f} 度")
            else:
                self.lbl_fov.setText("カメラ視野角: 未記録")

            if hasattr(project, 'camera_info') and project.camera_info:
                self.lbl_camera.setText(f"カメラ情報: {project.camera_info.motion_type}")
            else:
                self.lbl_camera.setText("カメラ情報: -")

            model_c = len(project.models)
            acc_c = len(project.accessories)
            audio_c = 1 if (project.audio and project.audio.raw_path) else 0
            self.lbl_counts.setText(f"検出アセット: モデル {model_c} / アクセサリ {acc_c} / 音声 {audio_c}")

            self._update_table()

            # モデルが存在する場合はインポートボタンを有効化
            has_models = bool(self.current_project and self.current_project.models)
            if hasattr(self, 'btn_import_models'):
                self.btn_import_models.setEnabled(has_models)

        except Exception as e:
            self.te_log.append(f"解析中に例外が発生しました: {e}\n{traceback.format_exc()}")

    def _update_table(self):
        self.table.setRowCount(0)
        if not self._all_items:
            self.lbl_stats.setText("アイテム数: 0")
            return

        filter_text = self.combo_filter.currentText()
        show_missing = hasattr(self, 'cb_show_missing') and self.cb_show_missing.isChecked()
        filtered = []
        for item in self._all_items:
            # ファイルが存在しないアイテムの非表示フィルタ（チェックOFF時は未検出アイテムを除外）
            if not show_missing and (not item.exists or getattr(item, 'is_old_data', False)):
                continue

            if filter_text == "モデル (.pmx / .pmd)" and item.kind != "Model":
                continue
            elif filter_text == "アクセサリ (.x)" and item.kind != "Accessory":
                continue
            elif filter_text == "音声・メディア" and item.kind in ["Model", "Accessory"]:
                continue
            filtered.append(item)

        self.table.setRowCount(len(filtered))
        exist_count = sum(1 for it in self._all_items if it.exists)
        total_count = len(self._all_items)
        missing_count = total_count - exist_count
        old_data_count = sum(1 for it in self._all_items if getattr(it, 'is_old_data', False))

        stats_text = f"表示中: {len(filtered)} 件 / 合計: {total_count} 件 (存在: {exist_count} 件, 未検出: {missing_count} 件"
        if old_data_count > 0:
            stats_text += f", 旧データ: {old_data_count} 件)"
        else:
            stats_text += ")"
        self.lbl_stats.setText(stats_text)

        kind_map = {
            "Model": "モデル",
            "Accessory": "アクセサリ",
            "Audio": "音声",
            "Background (AVI)": "背景動画",
            "Background (Image)": "背景画像"
        }

        for row, item in enumerate(filtered):
            # No.
            item_no = QTableWidgetItem(str(row + 1))
            item_no.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_no)

            # 種別
            kind_str = kind_map.get(item.kind, item.kind)
            item_kind = QTableWidgetItem(kind_str)
            item_kind.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, item_kind)

            # 名称
            item_name = QTableWidgetItem(item.name)
            self.table.setItem(row, 2, item_name)

            # ファイル状態
            is_old = getattr(item, 'is_old_data', False)
            if item.exists:
                status_str = "存在"
            elif is_old:
                status_str = "見つかりません (旧データ)"
            else:
                status_str = "見つかりません"

            item_status = QTableWidgetItem(status_str)
            item_status.setTextAlignment(Qt.AlignCenter)
            fnt = item_status.font()
            fnt.setBold(True)
            item_status.setFont(fnt)
            if item.exists:
                item_status.setForeground(QColor("#2ecc71"))
            elif is_old:
                item_status.setForeground(QColor("#95a5a6"))
                item_status.setToolTip("重複した過去の残骸データです")
            else:
                item_status.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 3, item_status)

            # モデル照合 (PMX/PMD との突合)
            if item.kind == "Model":
                match_str = item.match_status or "未照合"
                item_match = QTableWidgetItem(match_str)
                item_match.setTextAlignment(Qt.AlignCenter)
                mfnt = item_match.font()
                mfnt.setBold(True)
                item_match.setFont(mfnt)
                if match_str == "一致":
                    item_match.setForeground(QColor("#2ecc71"))
                elif match_str == "部分一致":
                    item_match.setForeground(QColor("#f39c12"))
                elif match_str == "不一致":
                    item_match.setForeground(QColor("#e67e22"))
                elif match_str == "モデル未検出":
                    item_match.setForeground(QColor("#e74c3c"))
                else:
                    item_match.setForeground(QColor("#95a5a6"))
                if item.match_detail:
                    item_match.setToolTip(item.match_detail)
            else:
                item_match = QTableWidgetItem("-")
                item_match.setTextAlignment(Qt.AlignCenter)
                item_match.setForeground(QColor("#7f8c8d"))
            self.table.setItem(row, 4, item_match)

            # モーション判定
            if item.kind == "Model":
                motion_str = item.motion_type or "なし"
                item_motion = QTableWidgetItem(motion_str)
                item_motion.setTextAlignment(Qt.AlignCenter)
                if "モーション" in motion_str:
                    item_motion.setForeground(QColor("#3498db"))
                elif "ポーズ" in motion_str:
                    item_motion.setForeground(QColor("#9b59b6"))
                else:
                    item_motion.setForeground(QColor("#7f8c8d"))
            else:
                item_motion = QTableWidgetItem("-")
                item_motion.setTextAlignment(Qt.AlignCenter)
                item_motion.setForeground(QColor("#7f8c8d"))
            self.table.setItem(row, 5, item_motion)

            # 最大フレーム
            if item.kind == "Model":
                frame_str = f"{item.max_frame:,} F" if item.max_frame > 0 else ("0 F" if item.has_motion else "-")
                item_frame = QTableWidgetItem(frame_str)
                item_frame.setTextAlignment(Qt.AlignCenter)
            else:
                item_frame = QTableWidgetItem("-")
                item_frame.setTextAlignment(Qt.AlignCenter)
                item_frame.setForeground(QColor("#7f8c8d"))
            self.table.setItem(row, 6, item_frame)

            # 解決ファイルパス
            item_res = QTableWidgetItem(item.resolved_path or item.raw_path or "-")
            if item.raw_path:
                item_res.setToolTip(f"PMM記録パス: {item.raw_path}")
            self.table.setItem(row, 7, item_res)

            # オブジェクト紐付け
            item_no.setData(Qt.UserRole, item)

    def _get_selected_item(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item_no = self.table.item(row, 0)
        if not item_no:
            return None
        return item_no.data(Qt.UserRole)

    def _show_context_menu(self, pos):
        item = self._get_selected_item()
        if not item:
            return

        menu = QMenu(self)
        action_copy_res = menu.addAction("解決ファイルパスをコピー")
        action_copy_raw = menu.addAction("PMM記録パスをコピー")
        menu.addSeparator()
        action_open_exp = menu.addAction("ファイルの場所をエクスプローラーで開く")
        if not item.exists or not item.resolved_path:
            action_open_exp.setEnabled(False)

        action_import_sel = None
        if item.kind == "Model":
            menu.addSeparator()
            action_import_sel = menu.addAction("選択モデルをインポート...")

        action = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if action == action_copy_res and item.resolved_path:
            QApplication.clipboard().setText(item.resolved_path)
        elif action == action_copy_raw and item.raw_path:
            QApplication.clipboard().setText(item.raw_path)
        elif action == action_open_exp and item.exists and item.resolved_path:
            self._open_in_explorer(item.resolved_path)
        elif action_import_sel and action == action_import_sel:
            self._open_model_import_dialog()

    def _on_table_double_clicked(self, table_item):
        item = self._get_selected_item()
        if item and item.exists and item.resolved_path:
            self._open_in_explorer(item.resolved_path)

    def _copy_selected_resolved_path(self):
        item = self._get_selected_item()
        if item and item.resolved_path:
            QApplication.clipboard().setText(item.resolved_path)

    def _open_selected_in_explorer(self):
        item = self._get_selected_item()
        if item and item.exists and item.resolved_path:
            self._open_in_explorer(item.resolved_path)

    def _open_in_explorer(self, filepath):
        if not filepath or not os.path.exists(filepath):
            return
        try:
            import subprocess
            norm = os.path.abspath(filepath)
            subprocess.run(f'explorer /select,"{norm}"', shell=True)
        except Exception:
            pass

    def _copy_log(self):
        text = self.te_log.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    def _open_model_import_dialog(self):
        if not self.current_project or not self.current_project.models:
            QMessageBox.information(self, "案内", "プロジェクト内にモデルが検出されていません。")
            return
        dialog = PmmModelImportSelectDialog(self, self.current_project.models, project=self.current_project)
        dialog.exec_()
