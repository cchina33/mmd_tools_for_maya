# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 複数モデル順次インポートおよびベイク確認ダイアログ
"""

from .common import *

# ==============================================================================
# 複数モデルインポート 実行ログダイアログ (別ウィンドウ)
# ==============================================================================
class MultiModelLogDialog(QDialog):
    """複数モデルインポート用の独立した実行ログウィンドウ"""
    def __init__(self, parent=None):
        super(MultiModelLogDialog, self).__init__(parent)
        self.setWindowTitle("複数モデルインポート - 実行ログ")
        self.resize(720, 500)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ログテキスト表示エリア
        self.te_log = QTextEdit()
        self.te_log.setReadOnly(True)
        self.te_log.setStyleSheet(
            "QTextEdit { background-color: #1a1a1a; color: #ddd; font-family: Consolas, monospace; font-size: 12px; }"
        )
        layout.addWidget(self.te_log)

        # ボタングループ
        h_btn = QHBoxLayout()
        self.btn_copy = QPushButton("ログをコピー")
        self.btn_copy.setFixedHeight(32)
        self.btn_copy.setFixedWidth(110)
        self.btn_copy.clicked.connect(self._copy_log)
        h_btn.addWidget(self.btn_copy)

        self.btn_clear = QPushButton("ログをクリア")
        self.btn_clear.setFixedHeight(32)
        self.btn_clear.setFixedWidth(110)
        self.btn_clear.clicked.connect(self.clear_log)
        h_btn.addWidget(self.btn_clear)

        h_btn.addStretch()

        self.btn_close = QPushButton("閉じる")
        self.btn_close.setFixedHeight(32)
        self.btn_close.setFixedWidth(100)
        self.btn_close.clicked.connect(self.close)
        h_btn.addWidget(self.btn_close)

        layout.addLayout(h_btn)

    def append_log(self, text):
        """ログを追加して末尾へ自動スクロール"""
        cursor = self.te_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.te_log.setTextCursor(cursor)
        self.te_log.ensureCursorVisible()
        QApplication.processEvents()

    def clear_log(self):
        """ログをクリア"""
        self.te_log.clear()

    def _copy_log(self):
        """ログをクリップボードにコピー"""
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.te_log.toPlainText())
            mc.inViewMessage(amg='<span style="color:#52b7ff;">MMD Tools for Maya:</span> 実行ログをクリップボードにコピーしました。', pos='topCenter', fade=True)


# ==============================================================================
# ドラッグ＆ドロップ対応 モデル一覧テーブル
# ==============================================================================
class MultiModelDropTableWidget(QTableWidget):
    """外部エクスプローラー等からのドラッグ＆ドロップを受け付けるモデル一覧テーブル"""
    def __init__(self, dialog=None, parent=None):
        super(MultiModelDropTableWidget, self).__init__(parent)
        self.dialog = dialog
        self.setAcceptDrops(True)
        if self.viewport():
            self.viewport().setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            files = []
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if p:
                    files.append(p)
            if files and self.dialog and hasattr(self.dialog, 'add_model_files'):
                event.acceptProposedAction()
                self.dialog.add_model_files(files)
                return
        event.ignore()


# ==============================================================================
# 複数モデルインポート ダイアログ (試験的機能)
# ==============================================================================
class MultiModelImportDialog(QDialog):
    """複数の MMD モデル (.pmx / .pmd) を順次インポートし、アンカーへ自動配置するダイアログ"""
    def __init__(self, parent=None):
        super(MultiModelImportDialog, self).__init__(parent)
        self.parent_tab = parent
        self.setWindowTitle("複数のモデルをインポート (試験的機能)")
        self.resize(920, 520)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.setAcceptDrops(True)

        # 独立した実行ログウィンドウを保持
        self.log_dialog = MultiModelLogDialog(parent=self)

        # モデル登録アイテム一覧: [ {'path': str, 'name': str, 'anchor': str, 'status': str} ]
        self.model_items = []
        self._is_importing = False
        self._cancel_requested = False

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ヘッダー説明
        desc_box = QGroupBox("複数モデルの順次インポートについて")
        desc_box.setStyleSheet("QGroupBox { font-weight: bold; color: #ffaa00; border: 1px solid #7a581e; padding: 10px; border-radius: 4px; background-color: #262016; }")
        desc_layout = QVBoxLayout(desc_box)
        lbl_desc = QLabel(
            "複数の PMX / PMD モデルを追加し、事前作成されたアンカーロケーターの位置へ自動配置します。\n"
            "※モデルの構築・剛体生成・グループ化は原点（中心）で安定保護に行われ、終了後にアンカーへ移動して次のモデルの読み込みを開始します。\n"
            "※モデルファイル（.pmx / .pmd）やモデル格納フォルダを一覧表へ直接ドラッグ＆ドロップして追加することも可能です。"
        )
        lbl_desc.setStyleSheet("color: #ffd180; font-size: 12px; font-weight: normal;")
        lbl_desc.setWordWrap(True)
        desc_layout.addWidget(lbl_desc)
        main_layout.addWidget(desc_box)

        # モデル一覧テーブル
        table_box = QGroupBox("インポート対象モデル一覧 (ドラッグ＆ドロップ対応)")
        table_layout = QVBoxLayout(table_box)
        table_layout.setSpacing(8)

        self.table = MultiModelDropTableWidget(dialog=self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["No.", "モデル名", "アンカー (ロケーター)", "状態", "ファイルパス"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(2, 180)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(200)
        table_layout.addWidget(self.table)

        # リスト操作ボタン
        h_table_btn = QHBoxLayout()
        self.btn_add = QPushButton("モデルを追加...")
        self.btn_add.setFixedHeight(34)
        self.btn_add.setStyleSheet("QPushButton { background-color: #2b5b84; color: #fff; font-weight: bold; border-radius: 4px; padding: 0 14px; } QPushButton:hover { background-color: #3872a4; }")
        self.btn_add.setToolTip("PMX または PMD ファイルを選択して一覧へ追加します（複数選択可、ドラッグ＆ドロップ可、.x ファイルは不可）。自動的にアンカーロケーターを作成します。")
        self.btn_add.clicked.connect(self._on_add_models)
        h_table_btn.addWidget(self.btn_add)

        self.btn_remove = QPushButton("選択項目を削除")
        self.btn_remove.setFixedHeight(34)
        self.btn_remove.setToolTip("選択中のモデルを一覧から削除します。")
        self.btn_remove.clicked.connect(self._on_remove_selected)
        h_table_btn.addWidget(self.btn_remove)

        self.btn_clear = QPushButton("一覧をクリア")
        self.btn_clear.setFixedHeight(34)
        self.btn_clear.clicked.connect(self._on_clear_all)
        h_table_btn.addWidget(self.btn_clear)

        h_table_btn.addSpacing(16)

        self.btn_assign_anchor = QPushButton("選択オブジェクトをアンカーに設定")
        self.btn_assign_anchor.setFixedHeight(34)
        self.btn_assign_anchor.setToolTip("現在Mayaビューポートで選択しているノード（ロケーター等）を選択行のアンカーとして再設定します。")
        self.btn_assign_anchor.clicked.connect(self._on_assign_anchor_from_selection)
        h_table_btn.addWidget(self.btn_assign_anchor)

        self.btn_focus_anchor = QPushButton("アンカーを選択・表示")
        self.btn_focus_anchor.setFixedHeight(34)
        self.btn_focus_anchor.setToolTip("選択行のアンカーロケーターをMaya上で選択し、カメラをフォーカスします。")
        self.btn_focus_anchor.clicked.connect(self._on_focus_anchor)
        h_table_btn.addWidget(self.btn_focus_anchor)

        self.btn_recreate_anchor = QPushButton("アンカーの再設置")
        self.btn_recreate_anchor.setFixedHeight(34)
        self.btn_recreate_anchor.setToolTip("選択行（またはすべてのモデル）のアンカーロケーターを再生成・再配置し、インポート済みモデルの場合は位置の再設定と追従接続・剛体吸着を行います。")
        self.btn_recreate_anchor.clicked.connect(self._on_recreate_anchor)
        h_table_btn.addWidget(self.btn_recreate_anchor)

        h_table_btn.addStretch()
        table_layout.addLayout(h_table_btn)
        main_layout.addWidget(table_box)

        # インポート共通オプション
        opt_box = QGroupBox("インポート共通設定")
        opt_layout = QHBoxLayout(opt_box)
        opt_layout.setSpacing(14)

        opt_layout.addWidget(QLabel("スケール:"))
        self.le_scale = QLineEdit("8.0")
        self.le_scale.setFixedWidth(50)
        opt_layout.addWidget(self.le_scale)

        opt_layout.addWidget(QLabel("マテリアル:"))
        self.cbb_material = QComboBox()
        self.cbb_material.addItem("マテリアルなし", 0)
        self.cbb_material.addItem("Blinn", 1)
        self.cbb_material.addItem("Phong", 2)
        self.cbb_material.addItem("Lambert", 3)
        self.cbb_material.addItem("StandardSurface (Maya 2022+)", 4)
        self.cbb_material.addItem("MMD Toon Shader (推奨)", 6)
        self.cbb_material.setCurrentIndex(self.cbb_material.count() - 1)
        opt_layout.addWidget(self.cbb_material)

        self.cb_bones = QCheckBox("スケルトン生成")
        self.cb_bones.setChecked(True)
        opt_layout.addWidget(self.cb_bones)

        self.cb_physics = QCheckBox("剛体・Joint生成")
        self.cb_physics.setChecked(True)
        opt_layout.addWidget(self.cb_physics)

        self.cb_bs = QCheckBox("ブレンドシェイプ生成")
        self.cb_bs.setChecked(True)
        opt_layout.addWidget(self.cb_bs)

        self.cb_check_mb = QCheckBox("モーフ・ボーン検査")
        self.cb_check_mb.setChecked(True)
        opt_layout.addWidget(self.cb_check_mb)

        opt_layout.addStretch()
        main_layout.addWidget(opt_box)

        # 進捗バーと状態ラベル
        prog_layout = QHBoxLayout()
        self.lbl_progress = QLabel("待機中: モデルを追加して「順次インポートを開始」をクリックしてください")
        self.lbl_progress.setStyleSheet("color: #ccc; font-size: 13px;")
        prog_layout.addWidget(self.lbl_progress)
        prog_layout.addStretch()
        main_layout.addLayout(prog_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # 実行ボタンエリア
        h_exec = QHBoxLayout()

        self.btn_show_log = QPushButton("実行ログを表示...")
        self.btn_show_log.setFixedHeight(44)
        self.btn_show_log.setFixedWidth(150)
        self.btn_show_log.setStyleSheet("QPushButton { background-color: #3e3e3e; color: #fff; font-size: 13px; border-radius: 4px; } QPushButton:hover { background-color: #4e4e4e; }")
        self.btn_show_log.setToolTip("独立した実行ログウィンドウを開きます。")
        self.btn_show_log.clicked.connect(self.show_log_dialog)
        h_exec.addWidget(self.btn_show_log)

        h_exec.addStretch()

        self.btn_start = QPushButton("順次インポートを開始")
        self.btn_start.setFixedHeight(44)
        self.btn_start.setMinimumWidth(200)
        self.btn_start.setStyleSheet("QPushButton { background-color: #2b7a4b; color: #fff; font-size: 14px; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #38965d; }")
        self.btn_start.clicked.connect(self._start_sequential_import)
        h_exec.addWidget(self.btn_start)

        self.btn_close = QPushButton("閉じる")
        self.btn_close.setFixedHeight(44)
        self.btn_close.setFixedWidth(100)
        self.btn_close.clicked.connect(self.close)
        h_exec.addWidget(self.btn_close)

        main_layout.addLayout(h_exec)

    def dragEnterEvent(self, event):
        """ダイアログすべてでのドラッグ受付"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """ダイアログ余白等へのドロップ受付"""
        if event.mimeData().hasUrls():
            files = []
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if p:
                    files.append(p)
            if files:
                event.acceptProposedAction()
                self.add_model_files(files)
                return
        event.ignore()

    def show_log_dialog(self):
        """実行ログウィンドウを前面に表示"""
        if self.log_dialog:
            self.log_dialog.show()
            self.log_dialog.raise_()
            self.log_dialog.activateWindow()

    def append_log(self, text):
        """実行ログウィンドウへテキストを書き込み"""
        if self.log_dialog:
            self.log_dialog.append_log(text)

    def closeEvent(self, event):
        """親ダイアログが閉じられたらログウィンドウも閉じる"""
        if self.log_dialog:
            self.log_dialog.close()
        event.accept()

    def _refresh_table(self):
        """テーブルの行表示を更新"""
        self.table.setRowCount(len(self.model_items))
        for row, item in enumerate(self.model_items):
            item_no = QTableWidgetItem(str(row + 1))
            item_no.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_no)

            item_name = QTableWidgetItem(item['name'])
            self.table.setItem(row, 1, item_name)

            item_anchor = QTableWidgetItem(item['anchor'])
            self.table.setItem(row, 2, item_anchor)

            item_status = QTableWidgetItem(item['status'])
            item_status.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, item_status)

            item_path = QTableWidgetItem(item['path'])
            self.table.setItem(row, 4, item_path)

    def add_model_files(self, file_paths):
        """モデルファイル一覧（またはフォルダ）を受け取り、一覧およびアンカーを追加"""
        if not file_paths:
            return

        # フォルダが渡された場合は内部のモデルファイルを探索
        collected_files = []
        for fp in file_paths:
            if os.path.isdir(fp):
                for root_dir, _, filenames in os.walk(fp):
                    for fn in filenames:
                        ext = os.path.splitext(fn)[1].lower()
                        if ext in ['.pmx', '.pmd']:
                            collected_files.append(os.path.join(root_dir, fn))
            else:
                collected_files.append(fp)

        if not collected_files:
            self.append_log("[案内] 追加可能な MMD モデルファイル (.pmx / .pmd) が見つかりませんでした。\n")
            self.show_log_dialog()
            return

        # 登録済みパスのセット（重複防止用）
        existing_paths = {item['path'].replace('\\', '/').lower() for item in self.model_items}

        added_count = 0
        for f in collected_files:
            norm_f = f.replace('\\', '/').lower()
            ext = os.path.splitext(f)[1].lower()
            base_name = os.path.splitext(os.path.basename(f))[0]

            if not os.path.exists(f):
                self.append_log(f"[スキップ] 指定されたファイルが存在しません: {os.path.basename(f)}\n")
                continue

            if ext not in ['.pmx', '.pmd']:
                self.append_log(f"[スキップ] 非対応のファイル形式です (.x ファイルは複数インポート非対応): {os.path.basename(f)}\n")
                continue

            if norm_f in existing_paths:
                self.append_log(f"[スキップ] 既に一覧に追加されています: {os.path.basename(f)}\n")
                continue

            safe_name = safe_node_name(base_name)

            # アンカーロケーターを自動生成
            loc_base = f"anchor_{safe_name}"
            loc_name = loc_base
            idx = 1
            while mc.objExists(loc_name):
                loc_name = f"{loc_base}_{idx}"
                idx += 1

            try:
                # 複数配置時に重ならないようオフセット配置
                offset_x = len(self.model_items) * 20.0
                loc_node = mc.spaceLocator(name=loc_name)[0]
                mc.setAttr(f"{loc_node}.translateX", offset_x)
                mc.setAttr(f"{loc_node}.localScaleX", 5.0)
                mc.setAttr(f"{loc_node}.localScaleY", 5.0)
                mc.setAttr(f"{loc_node}.localScaleZ", 5.0)
            except Exception as e:
                loc_node = loc_name
                self.append_log(f"[警告] ロケーター生成エラー: {e}\n")

            self.model_items.append({
                'path': f,
                'name': base_name,
                'anchor': loc_node,
                'status': "待機中"
            })
            existing_paths.add(norm_f)
            added_count += 1
            self.append_log(f"[追加] モデル: {base_name} (アンカー: {loc_node}, X={offset_x})\n")

        self._refresh_table()
        if added_count > 0:
            self.append_log(f">> {added_count} 体のモデルを追加しました。ビューポート上でアンカーロケーターを希望の位置・向きへ移動できます。\n")
            self.lbl_progress.setText(f"登録終了: 現在 {len(self.model_items)} 体のモデルが登録されています")
            self.show_log_dialog()

    def _on_add_models(self):
        """モデル選択ダイアログを表示してアンカーロケーターを自動生成"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "MMDモデルファイルを選択 (複数可)",
            "",
            "MMD Models (*.pmx *.pmd);;PMX (*.pmx);;PMD (*.pmd)"
        )
        if files:
            self.add_model_files(files)

    def _on_remove_selected(self):
        """選択行のモデルをリストから削除"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self.model_items):
            QMessageBox.information(self, "案内", "削除する行を選択してください。")
            return

        item = self.model_items.pop(row)
        # アンカーロケーターが残っていればクリーンアップ
        if item.get('anchor') and mc.objExists(item['anchor']):
            try:
                mc.delete(item['anchor'])
            except Exception:
                pass

        self._refresh_table()
        self.append_log(f"[削除] モデル '{item['name']}' をリストから除外しました。\n")

    def _on_clear_all(self):
        """すべてのモデル登録をクリア"""
        if not self.model_items:
            return
        res = QMessageBox.question(self, "確認", "登録中のすべてのモデルをリストからクリアしますか？", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            for item in self.model_items:
                if item.get('anchor') and mc.objExists(item['anchor']):
                    try:
                        mc.delete(item['anchor'])
                    except Exception:
                        pass
            self.model_items.clear()
            self._refresh_table()
            self.append_log("[クリア] モデル登録をすべてクリアしました。\n")

    def _on_assign_anchor_from_selection(self):
        """シーン内で選択中のオブジェクトを選択行のアンカーとして再設定"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self.model_items):
            QMessageBox.information(self, "案内", "アンカーを設定する対象行をテーブルで選択してください。")
            return

        sel = mc.ls(selection=True) or []
        if not sel:
            QMessageBox.warning(self, "未選択", "Mayaビューポートでアンカーに指定するオブジェクト（ロケーター等）を選択してください。")
            return

        target_node = sel[0]
        self.model_items[row]['anchor'] = target_node
        self._refresh_table()
        self.append_log(f"[アンカー変更] モデル '{self.model_items[row]['name']}' のアンカーを '{target_node}' に設定しました。\n")

    def _on_focus_anchor(self):
        """選択行のアンカーロケーターをMaya上で選択・フォーカス"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self.model_items):
            return
        anchor = self.model_items[row]['anchor']
        if anchor and mc.objExists(anchor):
            mc.select(anchor)
            try:
                mc.viewFit()
            except Exception:
                pass

    def _on_recreate_anchor(self):
        """選択行（未選択時はすべてのモデル）のアンカーロケーターを再生成・再配置し、インポート済みモデルを再接続"""
        if not self.model_items:
            QMessageBox.information(self, "案内", "インポート対象のモデルが一覧に登録されていません。")
            return

        current_row = self.table.currentRow()
        if 0 <= current_row < len(self.model_items):
            target_indices = [current_row]
        else:
            target_indices = list(range(len(self.model_items)))

        recreated_count = 0
        reconnected_count = 0

        for row_idx in target_indices:
            item = self.model_items[row_idx]
            model_name = item.get('name', 'model')
            safe_name = safe_node_name(model_name)
            anchor_name = item.get('anchor')

            # アンカーロケーターの存在確認と再作成
            loc_exists = anchor_name and mc.objExists(anchor_name)
            if not loc_exists:
                loc_base = f"anchor_{safe_name}"
                loc_name = loc_base
                idx = 1
                while mc.objExists(loc_name):
                    loc_name = f"{loc_base}_{idx}"
                    idx += 1
                try:
                    offset_x = row_idx * 20.0
                    anchor_name = mc.spaceLocator(name=loc_name)[0]
                    mc.setAttr(f"{anchor_name}.translateX", offset_x)
                    mc.setAttr(f"{anchor_name}.localScaleX", 5.0)
                    mc.setAttr(f"{anchor_name}.localScaleY", 5.0)
                    mc.setAttr(f"{anchor_name}.localScaleZ", 5.0)
                    item['anchor'] = anchor_name
                    recreated_count += 1
                    self.append_log(f"[アンカー再作成] モデル '{model_name}' のアンカーロケーター '{anchor_name}' を新規生成しました (X={offset_x})\n")
                except Exception as e:
                    self.append_log(f"[警告] アンカー生成エラー: {e}\n")
                    continue
            else:
                self.append_log(f"[アンカー確認] モデル '{model_name}' の既存アンカー '{anchor_name}' を再設置対象とします\n")

            # インポート済みモデルグループの特定
            model_group = item.get('group')
            if not (model_group and mc.objExists(model_group)):
                candidates = [f"{safe_name}_grp"] + [f"{safe_name}_{k}_grp" for k in range(1, 10)]
                for cand in candidates:
                    if mc.objExists(cand):
                        model_group = cand
                        item['group'] = cand
                        break

            # モデルグループが存在する場合は再配置および追従コンストレイント再接続
            if model_group and mc.objExists(model_group) and mc.objExists(anchor_name):
                # 既存のアンカー追従コンストレイントを整理
                constraints = mc.listRelatives(model_group, type='parentConstraint') or []
                for c in constraints:
                    try:
                        mc.delete(c)
                    except Exception:
                        pass

                # アンカーロケーターの位置・回転を取得してモデルを移動
                anc_pos = mc.xform(anchor_name, query=True, worldSpace=True, translation=True)
                anc_rot = mc.xform(anchor_name, query=True, worldSpace=True, rotation=True)
                mc.xform(model_group, worldSpace=True, translation=anc_pos, rotation=anc_rot)

                # 新しい追従コンストレイントを設定
                try:
                    c_anc = mc.parentConstraint(anchor_name, model_group, maintainOffset=True)
                    if c_anc:
                        mc.addAttr(c_anc[0], longName="isMmdAnchorConstraint", attributeType="bool", defaultValue=True)
                    reconnected_count += 1
                    self.append_log(f"[追従再接続] モデルグループ '{model_group}' をアンカー '{anchor_name}' へ再配置・接続しました\n")
                except Exception as e_anc:
                    self.append_log(f"[警告] アンカー追従接続エラー: {e_anc}\n")

                # 剛体およびJointビジュアライザのボーン再吸着
                try:
                    from ..converters.pmxpaimaya import reconnect_visualizers_to_bones
                except Exception:
                    try:
                        from converters.pmxpaimaya import reconnect_visualizers_to_bones
                    except Exception:
                        reconnect_visualizers_to_bones = None

                if reconnect_visualizers_to_bones:
                    try:
                        reconnect_visualizers_to_bones()
                        self.append_log(f"[物理再吸着] モデル '{model_name}' の剛体・Jointビジュアライザを再吸着しました\n")
                    except Exception as e_phy:
                        self.append_log(f"[警告] 物理再吸着エラー: {e_phy}\n")

        self._refresh_table()

        # 画面表示とビューポート更新
        try:
            mc.refresh()
        except Exception:
            pass

        msg = f"アンカーの再設置が終了しました。(再生成: {recreated_count} 件, モデル再接続: {reconnected_count} 件)"
        self.append_log(f"\n>> {msg}\n")
        mc.inViewMessage(amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> {msg}', pos='topCenter', fade=True)

    def _start_sequential_import(self):
        """登録されたモデルを原点で安定してインポートし、グループ化後にアンカーへ移動して順次進行"""
        if not self.model_items:
            QMessageBox.warning(self, "未登録", "インポート対象のモデルが追加されていません。")
            return

        if self._is_importing:
            return

        self._is_importing = True
        self.btn_start.setEnabled(False)
        self.btn_add.setEnabled(False)
        self.btn_remove.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.progress_bar.setValue(0)

        total_count = len(self.model_items)
        success_count = 0

        # パラメータ取得
        try:
            scale = float(self.le_scale.text())
        except ValueError:
            scale = 8.0

        mat_id = self.cbb_material.currentData()
        material_type = mat_id if mat_id is not None else 6
        create_bones = self.cb_bones.isChecked()
        create_physics = self.cb_physics.isChecked()
        create_bs = self.cb_bs.isChecked()
        check_morph_bone = self.cb_check_mb.isChecked()

        self.show_log_dialog()
        self.append_log("\n==================================================\n")
        self.append_log(f">>> 複数モデルの順次インポートを開始します (計 {total_count} 体)\n")
        self.append_log("==================================================\n")

        for idx, item in enumerate(self.model_items):
            file_path = item['path']
            model_name = item['name']
            anchor_name = item['anchor']

            self.lbl_progress.setText(f"インポート中 ({idx + 1}/{total_count}): {model_name}")
            item['status'] = "インポート中..."
            self._refresh_table()
            self.append_log(f"\n[{idx + 1}/{total_count}] モデルの読み込み開始: {model_name}\n")
            self.append_log(f"  - ファイル: {file_path}\n")

            # PMD形式の自動PMX変換
            if file_path.lower().endswith('.pmd'):
                try:
                    try:
                        from ..converters.pmd2pmx import convert_pmd_to_pmx
                    except Exception:
                        from converters.pmd2pmx import convert_pmd_to_pmx
                    self.append_log("  - PMD形式を検出: PMXへ自動変換中...\n")
                    file_path = convert_pmd_to_pmx(file_path)
                    self.append_log(f"  - PMX変換終了: {os.path.basename(file_path)}\n")
                except Exception as e:
                    self.append_log(f"  [警告] PMD変換エラー: {e}\n")

            # 原点でインポートする前のトップレベルノードを記録
            before_assemblies = set(mc.ls(assemblies=True) or [])

            try:
                # ユーザー辞書チェック
                if file_path.lower().endswith('.pmx') and check_morph_bone and check_and_prompt_user_dict:
                    try:
                        check_and_prompt_user_dict(self, file_path)
                    except Exception as e:
                        self.append_log(f"  [警告] モーフボーン検査エラー: {e}\n")

                # 原点での安定したインポート実行
                import importlib
                importlib.reload(pmxpaimaya)
                import_func = getattr(pmxpaimaya, 'import_pmx', pmxpaimaya.sang)

                # 初回のみライト生成、2体目以降はスキップ
                create_light = (idx == 0)
                ret = import_func(
                    file_path, scale, False, create_bs,
                    create_bones, material_type,
                    create_light, True,
                    True, shadow_mode=1, create_ground_shadow=create_light,
                    show_completion_message=False, prevent_motion_darkening=True,
                    create_physics=create_physics
                )
                self.append_log("  - 原点でのメッシュ・スケルトンおよび剛体・Joint構築終了\n")

                # メッシュの二重トランスフォーム防止
                mesh_node = ret[0] if ret else None
                if mesh_node and mc.objExists(mesh_node):
                    mc.setAttr(f"{mesh_node}.inheritsTransform", False)

                # インポート後のトップレベルノード差分を検出
                after_assemblies = set(mc.ls(assemblies=True) or [])
                new_nodes = [
                    n for n in (after_assemblies - before_assemblies)
                    if not n.startswith("mmd_lighting") and not n.startswith("mmd_ground_shadow")
                ]

                # すべての生成ノードを1つのグループにまとめる
                safe_name = safe_node_name(model_name)
                grp_name = f"{safe_name}_grp"
                g_idx = 1
                while mc.objExists(grp_name):
                    grp_name = f"{safe_name}_{g_idx}_grp"
                    g_idx += 1

                if new_nodes:
                    model_group = mc.group(new_nodes, name=grp_name)
                    # 識別用カスタムアトリビュートを付与 (親グループとして識別)
                    if not mc.attributeQuery('isMmdGroup', node=model_group, exists=True):
                        mc.addAttr(model_group, longName='isMmdGroup', attributeType='bool', defaultValue=True)
                    self.append_log(f"  - 生成ノードを統合グループ '{model_group}' にまとめました\n")
                else:
                    model_group = None

                # アンカーロケーターが存在する場合、その位置・回転へ移動して追従接続
                if model_group and anchor_name and mc.objExists(anchor_name):
                    anc_pos = mc.xform(anchor_name, query=True, worldSpace=True, translation=True)
                    anc_rot = mc.xform(anchor_name, query=True, worldSpace=True, rotation=True)
                    mc.xform(model_group, worldSpace=True, translation=anc_pos, rotation=anc_rot)

                    # アンカーロケーター移動にモデル各部（メッシュ・ボーン・剛体・Joint）が連動するようコンストレイント設定
                    try:
                        c_anc = mc.parentConstraint(anchor_name, model_group, maintainOffset=True)
                        if c_anc:
                            mc.addAttr(c_anc[0], longName="isMmdAnchorConstraint", attributeType="bool", defaultValue=True)
                    except Exception as e_anc:
                        self.append_log(f"  [警告] アンカー追従接続スキップ: {e_anc}\n")

                    self.append_log(f"  - アンカー '{anchor_name}' の位置へモデルを配置・追従接続しました: {anc_pos}\n")
                else:
                    self.append_log("  - アンカー未指定または不在のため、原点に配置を維持しました\n")

                # 次のモデル読み込み前にビューポートを描画更新し、原点スペースを解放
                try:
                    mc.refresh()
                except Exception:
                    pass

                item['group'] = model_group
                item['status'] = "終了"
                success_count += 1
                self.append_log(f"  -> モデル '{model_name}' の読み込み・配置が終了しました。\n")
            except Exception as e:
                item['status'] = "エラー"
                err_trace = traceback.format_exc()
                self.append_log(f"  [エラー] モデル '{model_name}' のインポートに失敗しました:\n{err_trace}\n")

            self.progress_bar.setValue(int(((idx + 1) / total_count) * 100))
            self._refresh_table()
            QApplication.processEvents()

        self._is_importing = False
        self.btn_start.setEnabled(True)
        self.btn_add.setEnabled(True)
        self.btn_remove.setEnabled(True)
        self.btn_clear.setEnabled(True)
        self.lbl_progress.setText(f"終了: {success_count}/{total_count} 体のインポートが終了しました")

        self.append_log("\n==================================================\n")
        self.append_log(f">>> すべてのモデルの順次インポート処理が終了しました ({success_count}/{total_count} 体成功)\n")
        self.append_log("==================================================\n")

        QMessageBox.information(
            self,
            "インポート終了",
            f"複数モデルの順次インポートが終了しました。\n\n"
            f"・成功: {success_count} 体\n"
            f"・合計: {total_count} 体"
        )


# ==============================================================================
# ==============================================================================
# ベイクするモデルの確認ダイアログ (単体・複数共通)
# ==============================================================================
class MultiModelPhysicsBakeDialog(QDialog):
    """
    現在ベイク対象として設定されているMMDモデル一覧（単体・複数問わず）を確認するダイアログ
    """
    def __init__(self, parent=None):
        super(MultiModelPhysicsBakeDialog, self).__init__(parent)
        self.parent_tab = parent
        self.setWindowTitle("ベイクするモデルの確認")
        self.resize(760, 400)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.model_items = []
        self._init_ui()
        self._refresh_models_from_scene()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 説明ヘッダー
        lbl_info = QLabel(
            "<b>ベイク対象モデル一覧の確認</b><br>"
            "現在ベイク対象として設定されているMMDモデル一覧です。<br>"
            "物理ベイクはメイン画面の「リアルタイム物理ベイク実行」ボタンから行います。<br>"
            "複数モデルが存在する場合は、剛体の追突や反発を防ぐため1体ずつ順次ベイクされます。"
        )
        lbl_info.setStyleSheet("color: #cccccc; padding: 8px; background-color: #2b2b2b; border-radius: 4px; line-height: 140%;")
        main_layout.addWidget(lbl_info)

        # モデルテーブル
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["No", "モデル表示名", "Mayaノード名", "PMXモデルパス", "ベイク対象"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        main_layout.addWidget(self.table)

        # 状態表示ラベル
        self.lbl_status = QLabel("検出中...")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #52b7ff; padding: 2px;")
        main_layout.addWidget(self.lbl_status)

        # 下部ボタングループ
        h_bottom = QHBoxLayout()
        self.btn_refresh_scene = QPushButton("シーンから再取得")
        self.btn_refresh_scene.setFixedHeight(34)
        self.btn_refresh_scene.setFixedWidth(130)
        self.btn_refresh_scene.clicked.connect(self._refresh_models_from_scene)
        h_bottom.addWidget(self.btn_refresh_scene)

        h_bottom.addStretch()

        self.btn_close = QPushButton("閉じる")
        self.btn_close.setFixedWidth(100)
        self.btn_close.setFixedHeight(34)
        self.btn_close.clicked.connect(self.close)
        h_bottom.addWidget(self.btn_close)

        main_layout.addLayout(h_bottom)

    def _refresh_models_from_scene(self):
        """シーン内のMMDモデル一覧およびベイク対象状態を取得し、テーブルを更新"""
        try:
            from ..converters import vmdpaimaya
        except Exception:
            try:
                from converters import vmdpaimaya
            except Exception:
                import vmdpaimaya

        models = []
        try:
            models = vmdpaimaya.get_available_mmd_models()
        except Exception:
            pass

        default_pmx = ""
        if self.parent_tab and hasattr(self.parent_tab, 'le_pmx_path'):
            default_pmx = self.parent_tab.le_pmx_path.text().strip()

        # 親タブの適用対象モデルチェックリストを取得
        selected_nodes = None
        if self.parent_tab and hasattr(self.parent_tab, '_selected_model_nodes'):
            selected_nodes = self.parent_tab._selected_model_nodes

        self.model_items = []
        is_all_default = (selected_nodes is None)
        selected_set = set(selected_nodes) if selected_nodes is not None else None

        for node, label in models:
            # モデルノードに保存されたPMXパスがあれば優先取得
            pmx_path = default_pmx
            if mc.attributeQuery('mmdModelPath', node=node, exists=True):
                saved_path = mc.getAttr(f"{node}.mmdModelPath")
                if saved_path and os.path.exists(saved_path):
                    pmx_path = saved_path

            # ベイク対象／対象外の判定 (チェックリストの状態を反映)
            if is_all_default:
                target_status = "対象"
                is_target = True
            else:
                if selected_set and node in selected_set:
                    target_status = "対象"
                    is_target = True
                else:
                    target_status = "対象外"
                    is_target = False

            # 表示名から純粋なモデル名を抽出
            display_name = label
            if "(" in label and label.endswith(")"):
                inner = label[label.find("(") + 1:-1].strip()
                if inner:
                    display_name = inner

            self.model_items.append({
                'node': node,
                'name': display_name,
                'full_label': label,
                'pmx_path': pmx_path,
                'status': target_status,
                'is_target': is_target
            })

        self._update_table_view()

        total_count = len(self.model_items)
        active_count = sum(1 for m in self.model_items if m['is_target'])
        excluded_count = total_count - active_count

        if total_count == 0:
            self.lbl_status.setText("未検出: シーン内にMMDモデルが見つかりません")
            self.lbl_status.setStyleSheet("color: #e74c3c; font-weight: bold;")
        elif active_count == 0:
            self.lbl_status.setText(f"ベイク対象なし: すべてのモデル ({total_count} 体) が対象外に設定されています")
            self.lbl_status.setStyleSheet("color: #e67e22; font-weight: bold;")
        elif excluded_count > 0:
            self.lbl_status.setText(f"ベイク対象: {active_count} 体 ／ 対象外: {excluded_count} 体 (計 {total_count} 体中)")
            self.lbl_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            self.lbl_status.setText(f"すべてのモデルがベイク対象: {active_count} 体")
            self.lbl_status.setStyleSheet("color: #52b7ff; font-weight: bold;")

    def _update_table_view(self):
        """テーブルの行表示を更新"""
        self.table.setRowCount(len(self.model_items))
        for row, item in enumerate(self.model_items):
            item_no = QTableWidgetItem(str(row + 1))
            item_no.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_no)

            item_name = QTableWidgetItem(item['name'])
            self.table.setItem(row, 1, item_name)

            item_node = QTableWidgetItem(item['node'])
            self.table.setItem(row, 2, item_node)

            item_pmx = QTableWidgetItem(item['pmx_path'] or "(未設定 / メイン設定参照)")
            self.table.setItem(row, 3, item_pmx)

            item_status = QTableWidgetItem(item['status'])
            item_status.setTextAlignment(Qt.AlignCenter)
            if item['is_target']:
                item_status.setForeground(QColor("#2ecc71"))
            else:
                item_status.setForeground(QColor("#888888"))
            self.table.setItem(row, 4, item_status)
