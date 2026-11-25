# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 簡単インポートタブモジュール
PMXモデル、VMDモーション、WAV音声をドラッグ＆ドロップで一括設定し、
MMD Toon Shader による高品質レンダリング設定で素早くインポートします。
"""

import os
import sys
import time

from .common import *

try:
    from ..maya_maya_converters import pmxpaimaya, vmdpaimaya, vmd_analyzer
except Exception:
    try:
        from maya_converters import pmxpaimaya, vmdpaimaya, vmd_analyzer
    except Exception:
        import pmxpaimaya
        import vmdpaimaya
        import vmd_analyzer


class EasyImportAssetItem:
    """簡単インポート対象のアセット情報クラス"""
    KIND_PMX = "PMXモデル"
    KIND_VMD_MODEL = "VMD (モデルモーション)"
    KIND_VMD_CAMERA = "VMD (カメラモーション)"
    KIND_WAV = "WAV音声"
    KIND_UNKNOWN = "その他"

    def __init__(self, file_path):
        self.file_path = os.path.normpath(file_path).replace("\\", "/")
        self.file_name = os.path.basename(self.file_path)
        self.ext = os.path.splitext(self.file_path)[1].lower()
        self.kind = self.KIND_UNKNOWN
        self.detail_info = ""
        self.max_frame = 0
        self.model_name = ""
        self.bone_keys = 0
        self.morph_keys = 0
        self.camera_keys = 0
        self._analyze()

    def _analyze(self):
        """アセット種別およびVMD構造の自動判別"""
        if self.ext in ['.pmx', '.pmd']:
            self.kind = self.KIND_PMX
            self.detail_info = "MMDモデルファイル"
        elif self.ext == '.wav':
            self.kind = self.KIND_WAV
            self.detail_info = "BGM音声ファイル"
        elif self.ext == '.vmd':
            try:
                report = vmd_analyzer.analyze_vmd(self.file_path)
                self.max_frame = getattr(report, "max_frame", 0)
                self.model_name = getattr(report, "model_name", "")
                self.bone_keys = getattr(report, "total_bone_keyframes", 0)
                self.morph_keys = getattr(report, "total_morph_keyframes", 0)
                self.camera_keys = getattr(report, "camera_keyframe_count", 0)

                # カメラキーのみの場合はカメラモーションとして判定
                if self.camera_keys > 0 and self.bone_keys == 0 and self.morph_keys == 0:
                    self.kind = self.KIND_VMD_CAMERA
                    self.detail_info = f"カメラ: {self.camera_keys:,} キー (最大: {self.max_frame:,} f)"
                elif self.bone_keys > 0 or self.morph_keys > 0:
                    self.kind = self.KIND_VMD_MODEL
                    target = f"対象: {self.model_name}" if self.model_name else "対象: 汎用"
                    self.detail_info = f"{target} / ボーン: {self.bone_keys:,} キー / モーフ: {self.morph_keys:,} キー (最大: {self.max_frame:,} f)"
                    if self.camera_keys > 0:
                        self.detail_info += f" / カメラ: {self.camera_keys:,} キー"
                else:
                    self.kind = self.KIND_VMD_MODEL
                    self.detail_info = "キーフレームなし"
            except Exception as e:
                self.kind = self.KIND_VMD_MODEL
                self.detail_info = f"解析エラー: {e}"


class EasyImportDropArea(QFrame):
    """ドラッグ＆ドロップ受け入れ専用エリア"""

    def __init__(self, on_files_dropped=None, parent=None):
        super(EasyImportDropArea, self).__init__(parent)
        self.on_files_dropped = on_files_dropped
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Sunken)
        self._set_normal_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(6)

        self.label_main = QLabel("ここに PMX / VMD / WAV ファイルをドラッグ＆ドロップ")
        self.label_main.setAlignment(Qt.AlignCenter)
        self.label_main.setStyleSheet("color: #7f9bb8; font-size: 13px; font-weight: bold;")
        layout.addWidget(self.label_main)

        self.label_sub = QLabel("※複数ファイルをまとめて同時にドロップできます")
        self.label_sub.setAlignment(Qt.AlignCenter)
        self.label_sub.setStyleSheet("color: #5d6d7e; font-size: 11px;")
        layout.addWidget(self.label_sub)

    def _set_normal_style(self):
        self.setStyleSheet("""
            QFrame {
                border: 2px dashed #34495e;
                border-radius: 6px;
                background-color: #17202a;
            }
            QFrame:hover {
                border-color: #3498db;
                background-color: #1c2833;
            }
        """)

    def _set_drag_active_style(self):
        self.setStyleSheet("""
            QFrame {
                border: 2px dashed #2ecc71;
                border-radius: 6px;
                background-color: #143220;
            }
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            has_valid = False
            for url in event.mimeData().urls():
                fp = url.toLocalFile().lower()
                if fp.endswith(('.pmx', '.pmd', '.vmd', '.wav')):
                    has_valid = True
                    break
            if has_valid:
                event.acceptProposedAction()
                self._set_drag_active_style()

    def dragLeaveEvent(self, event):
        self._set_normal_style()

    def dropEvent(self, event):
        self._set_normal_style()
        files = []
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                fp = url.toLocalFile()
                if fp and os.path.exists(fp):
                    if fp.lower().endswith(('.pmx', '.pmd', '.vmd', '.wav')):
                        files.append(fp)
        if files and self.on_files_dropped:
            self.on_files_dropped(files)


class EasyImportTabWidget(QWidget):
    """簡単インポート専用タブウィジェット"""

    def __init__(self, parent=None):
        super(EasyImportTabWidget, self).__init__(parent)
        self.parent_window = parent
        self.asset_items = []
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 説明ヘッダー
        desc_box = QGroupBox("簡単インポート (ドラッグ＆ドロップ一括設定)")
        desc_box.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #5dade2; border: 1px solid #2471a3; "
            "padding: 8px; border-radius: 4px; background-color: #15222e; }"
        )
        desc_layout = QVBoxLayout(desc_box)
        lbl_desc = QLabel(
            "PMXモデル、VMDモーション、WAV音声ファイルをまとめて登録し、ワンクリックでインポートします。\n"
            "VMDのモーション構造（モデル用 / カメラ用）は自動判別され、シェーダーは「MMD Toon Shader」が自動適用されます。"
        )
        lbl_desc.setStyleSheet("color: #aed6f1; font-size: 11px; font-weight: normal;")
        lbl_desc.setWordWrap(True)
        desc_layout.addWidget(lbl_desc)
        main_layout.addWidget(desc_box)

        # ドロップエリア
        self.drop_area = EasyImportDropArea(on_files_dropped=self.add_files, parent=self)
        main_layout.addWidget(self.drop_area)

        # 操作ボタンバー（参照追加、選択削除、クリア）
        h_tools = QHBoxLayout()
        self.btn_browse = QPushButton("ファイルを参照して追加...")
        self.btn_browse.setStyleSheet("padding: 5px 12px; font-size: 11px;")
        self.btn_browse.clicked.connect(self._browse_files)
        h_tools.addWidget(self.btn_browse)

        self.btn_remove_selected = QPushButton("選択項目を削除")
        self.btn_remove_selected.setStyleSheet("padding: 5px 12px; font-size: 11px;")
        self.btn_remove_selected.clicked.connect(self._remove_selected)
        h_tools.addWidget(self.btn_remove_selected)

        self.btn_clear = QPushButton("すべてクリア")
        self.btn_clear.setStyleSheet("padding: 5px 12px; font-size: 11px;")
        self.btn_clear.clicked.connect(self._clear_all)
        h_tools.addWidget(self.btn_clear)

        h_tools.addStretch()
        self.lbl_asset_summary = QLabel("登録アセット: 0 件")
        self.lbl_asset_summary.setStyleSheet("color: #5dade2; font-weight: bold;")
        h_tools.addWidget(self.lbl_asset_summary)
        main_layout.addLayout(h_tools)

        # 登録アセット一覧テーブル
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["種別", "ファイル名", "解析・判定情報", "ファイルパス"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(2, 280)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        main_layout.addWidget(self.table)

        # インポート設定（2択のみ）
        opt_box = QGroupBox("インポート設定")
        opt_layout = QVBoxLayout(opt_box)
        opt_layout.setSpacing(6)

        self.opt_group = QButtonGroup(self)

        self.rb_motion = QRadioButton("モーション用 (ボーン、剛体、ジョイントなどすべてインポート)")
        self.rb_motion.setChecked(True)
        self.rb_motion.setStyleSheet("font-weight: bold; color: #ecf0f1;")
        self.opt_group.addButton(self.rb_motion)
        opt_layout.addWidget(self.rb_motion)

        lbl_motion_hint = QLabel("  ・ボーンスケルトン、ブレンドシェイプモーフ、剛体コライダー、Jointを作成し、モーション再生や物理演算に対応させます。")
        lbl_motion_hint.setStyleSheet("color: #7f8c8d; font-size: 11px; margin-bottom: 4px;")
        opt_layout.addWidget(lbl_motion_hint)

        self.rb_preview = QRadioButton("モデル確認用 (ポリゴンメッシュのみインポート)")
        self.rb_preview.setStyleSheet("font-weight: bold; color: #ecf0f1;")
        self.opt_group.addButton(self.rb_preview)
        opt_layout.addWidget(self.rb_preview)

        lbl_preview_hint = QLabel("  ・ボーンや剛体を作成せず、ポリゴンメッシュとテクスチャのみを高速に読み込みます（形状・質感確認用）。")
        lbl_preview_hint.setStyleSheet("color: #7f8c8d; font-size: 11px; margin-bottom: 4px;")
        opt_layout.addWidget(lbl_preview_hint)

        lbl_fixed_info = QLabel("※シェーダー: MMD Toon Shader 固定 / ライティング・シェーディング: 最適化設定（すべて有効）")
        lbl_fixed_info.setStyleSheet("color: #f39c12; font-size: 11px; font-weight: bold; margin-top: 4px;")
        opt_layout.addWidget(lbl_fixed_info)

        # 影投影設定（ステージ影と地面影プレーンの制御）
        h_shadow_opt = QHBoxLayout()
        self.cb_stage_shadow = QCheckBox("ステージモデルに影を落とす (ステージ検出時は地面影板を自動非表示)")
        self.cb_stage_shadow.setChecked(True)
        self.cb_stage_shadow.setStyleSheet("color: #ecf0f1; font-size: 11px;")
        h_shadow_opt.addWidget(self.cb_stage_shadow)

        self.btn_toggle_shadow = QPushButton("地面影/ステージ影 切替")
        self.btn_toggle_shadow.setFixedHeight(36)
        self.btn_toggle_shadow.setStyleSheet(
            "QPushButton { padding: 4px 14px; font-size: 12px; font-weight: bold; background-color: #34495e; color: #ffffff; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3d566e; }"
        )
        self.btn_toggle_shadow.clicked.connect(self._toggle_shadow_mode)
        h_shadow_opt.addWidget(self.btn_toggle_shadow)

        self.btn_classifier_settings = QPushButton("モデル種別判定・個別指定設定...")
        self.btn_classifier_settings.setFixedHeight(36)
        self.btn_classifier_settings.setStyleSheet(
            "QPushButton { padding: 4px 14px; font-size: 12px; font-weight: bold; background-color: #2c3e50; color: #ecf0f1; border-radius: 4px; }"
            "QPushButton:hover { background-color: #34495e; }"
        )
        self.btn_classifier_settings.clicked.connect(self._open_classifier_settings)
        h_shadow_opt.addWidget(self.btn_classifier_settings)

        h_shadow_opt.addStretch()
        opt_layout.addLayout(h_shadow_opt)

        # レンダラー設定
        h_renderer_opt = QHBoxLayout()
        self.cb_switch_mmd_renderer = QCheckBox("インポート完了時に MMD Viewport Renderer に切り替える")
        self.cb_switch_mmd_renderer.setChecked(True)
        self.cb_switch_mmd_renderer.setStyleSheet("color: #ecf0f1; font-size: 11px;")
        self.cb_switch_mmd_renderer.setToolTip("インポート終了後、ビューポートを MMD Viewport Renderer に自動切り替えし、美しい外周エッジ輪郭線と白背景を表示します。")
        h_renderer_opt.addWidget(self.cb_switch_mmd_renderer)

        self.btn_toggle_renderer = QPushButton("Viewport 2.0 / MMD 切替")
        self.btn_toggle_renderer.setFixedHeight(36)
        self.btn_toggle_renderer.setStyleSheet(
            "QPushButton { padding: 4px 14px; font-size: 12px; font-weight: bold; background-color: #34495e; color: #ffffff; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3d566e; }"
        )
        self.btn_toggle_renderer.setToolTip("Viewport 2.0 と MMD Viewport Renderer を交互に切り替えます。")
        self.btn_toggle_renderer.clicked.connect(self._on_toggle_renderer_clicked)
        h_renderer_opt.addWidget(self.btn_toggle_renderer)
        h_renderer_opt.addStretch()
        opt_layout.addLayout(h_renderer_opt)

        main_layout.addWidget(opt_box)

        # 青色インポート実行ボタン
        self.btn_run_import = QPushButton("一括インポート実行")
        self.btn_run_import.setFixedHeight(44)
        self.btn_run_import.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: #ffffff; font-weight: bold; font-size: 14px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3498db; }"
            "QPushButton:pressed { background-color: #1f618d; }"
            "QPushButton:disabled { background-color: #566573; color: #a6acaf; }"
        )
        self.btn_run_import.clicked.connect(self._run_import)
        self.btn_run_import.setEnabled(False)
        main_layout.addWidget(self.btn_run_import)

    def _browse_files(self):
        """ファイルダイアログから複数ファイルを選択して追加"""
        file_filter = (
            "MMDアセット (*.pmx *.pmd *.vmd *.wav);;"
            "PMXモデル (*.pmx);;"
            "PMDモデル (*.pmd);;"
            "VMDモーション (*.vmd);;"
            "WAV音声 (*.wav);;"
            "すべてのファイル (*.*)"
        )
        files, _ = QFileDialog.getOpenFileNames(self, "インポートアセットの選択", "", file_filter)
        if files:
            self.add_files(files)

    def add_files(self, file_paths):
        """ファイル一覧をテーブルに追加（重複は除外）"""
        existing_paths = {item.file_path for item in self.asset_items}
        added_count = 0

        for fp in file_paths:
            norm_p = os.path.normpath(fp).replace("\\", "/")
            if norm_p not in existing_paths and os.path.exists(norm_p):
                item = EasyImportAssetItem(norm_p)
                self.asset_items.append(item)
                existing_paths.add(norm_p)
                added_count += 1

        if added_count > 0:
            self._update_table()

    def _remove_selected(self):
        """選択されている行をテーブルおよびリストから削除"""
        selected_rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not selected_rows:
            return

        for r in selected_rows:
            if 0 <= r < len(self.asset_items):
                del self.asset_items[r]

        self._update_table()

    def _clear_all(self):
        """全登録項目をクリア"""
        self.asset_items.clear()
        self._update_table()

    def _update_table(self):
        """アセット一覧テーブルの再描画"""
        self.table.setRowCount(len(self.asset_items))

        pmx_count = 0
        vmd_model_count = 0
        vmd_cam_count = 0
        wav_count = 0

        for r, item in enumerate(self.asset_items):
            # 種別セル
            kind_item = QTableWidgetItem(item.kind)
            kind_item.setTextAlignment(Qt.AlignCenter)
            if item.kind == EasyImportAssetItem.KIND_PMX:
                kind_item.setForeground(QColor("#3498db"))
                pmx_count += 1
            elif item.kind == EasyImportAssetItem.KIND_VMD_MODEL:
                kind_item.setForeground(QColor("#2ecc71"))
                vmd_model_count += 1
            elif item.kind == EasyImportAssetItem.KIND_VMD_CAMERA:
                kind_item.setForeground(QColor("#9b59b6"))
                vmd_cam_count += 1
            elif item.kind == EasyImportAssetItem.KIND_WAV:
                kind_item.setForeground(QColor("#f39c12"))
                wav_count += 1
            self.table.setItem(r, 0, kind_item)

            # ファイル名
            name_item = QTableWidgetItem(item.file_name)
            self.table.setItem(r, 1, name_item)

            # 解析情報
            detail_item = QTableWidgetItem(item.detail_info)
            detail_item.setToolTip(item.detail_info)
            self.table.setItem(r, 2, detail_item)

            # ファイルパス
            path_item = QTableWidgetItem(item.file_path)
            path_item.setToolTip(item.file_path)
            self.table.setItem(r, 3, path_item)

        total = len(self.asset_items)
        summary_text = f"登録: モデル {pmx_count}件 / モーション {vmd_model_count}件 / カメラ {vmd_cam_count}件 / 音声 {wav_count}件"
        self.lbl_asset_summary.setText(summary_text)
        self.btn_run_import.setEnabled(total > 0)

    def _run_import(self):
        """一括インポートの実行"""
        if not self.asset_items:
            QMessageBox.warning(self, "案内", "インポート対象のアセットが登録されていません。")
            return

        is_motion_mode = self.rb_motion.isChecked()

        # 分類抽出
        pmx_items = [it for it in self.asset_items if it.kind == EasyImportAssetItem.KIND_PMX]
        vmd_model_items = [it for it in self.asset_items if it.kind == EasyImportAssetItem.KIND_VMD_MODEL]
        vmd_cam_items = [it for it in self.asset_items if it.kind == EasyImportAssetItem.KIND_VMD_CAMERA]
        wav_items = [it for it in self.asset_items if it.kind == EasyImportAssetItem.KIND_WAV]

        # モデルが存在せずモーションのみ指定され、かつシーンにボーンがない場合の事前チェック
        if not pmx_items and vmd_model_items and mc:
            joints = mc.ls(type="joint") or []
            if not joints:
                QMessageBox.warning(
                    self,
                    "スケルトン未検出",
                    "シーン内にモデルのスケルトン（ボーン）が存在しません。\n\n"
                    "モデル用モーションを適用するには、モデル（PMX）も同時に登録するか、\n"
                    "あらかじめボーンを持つモデルをシーン内にインポートしてください。"
                )
                return

        # 確認ダイアログ
        mode_str = "モーション用 (ボーン・剛体等すべて)" if is_motion_mode else "モデル確認用 (ポリゴンメッシュのみ)"
        confirm_text = (
            f"以下のアセットを一括インポートします。\n\n"
            f"・インポート設定: {mode_str}\n"
            f"・シェーダー: MMD Toon Shader 固定\n"
            f"・PMXモデル: {len(pmx_items)} 件\n"
            f"・モデルモーション: {len(vmd_model_items)} 件\n"
            f"・カメラモーション: {len(vmd_cam_items)} 件\n"
            f"・BGM音声: {len(wav_items)} 件\n\n"
            f"インポートを開始しますか？"
        )
        res = QMessageBox.question(self, "簡単インポートの確認", confirm_text, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if res != QMessageBox.Yes:
            return

        log_dialog = ExecutionLogDialog(self.parent_window or self, title="簡単インポート実行ログ")

        def import_task():
            start_time = time.time()
            print("==================================================")
            print(f"簡単インポート開始 (設定: {mode_str})")
            print("==================================================")

            # タイムスライダー初期化
            if mc:
                try:
                    mc.currentTime(0)
                except Exception:
                    pass

            scale = 8.0
            last_imported_model = None
            max_registered_frame = 0

            # PMXモデルのインポート処理
            for idx, p_item in enumerate(pmx_items):
                fp = p_item.file_path
                print(f"\n[{idx + 1}/{len(pmx_items)}] モデル読み込み中: {p_item.file_name}")

                # PMD形式の自動変換対応
                if fp.lower().endswith(".pmd"):
                    try:
                        try:
                            from ..maya_maya_converters.pmd2pmx import convert_pmd_to_pmx
                        except Exception:
                            from maya_converters.pmd2pmx import convert_pmd_to_pmx
                        print("  - PMD形式を検出: PMXへ自動変換中...")
                        fp = convert_pmd_to_pmx(fp)
                        print(f"  - PMX変換完了: {os.path.basename(fp)}")
                    except Exception as e:
                        print(f"  [警告] PMD変換エラー: {e}")
                        continue

                import importlib
                importlib.reload(pmxpaimaya)
                import_func = getattr(pmxpaimaya, 'import_pmx', pmxpaimaya.sang)

                # モデル確認用ではメッシュのみ、モーション用ではボーン・剛体等すべて
                create_joints = is_motion_mode
                create_bs = is_motion_mode
                create_physics = is_motion_mode
                create_light = (idx == 0)

                ret = import_func(
                    fp,
                    scale=scale,
                    split_by_material=False,
                    create_blendshapes=create_bs,
                    create_joints=create_joints,
                    material_type=6,  # MMD Toon Shader 固定
                    create_light=create_light,
                    set_untone_mapped=True,
                    enable_toon=True,
                    shadow_mode=1,
                    create_ground_shadow=True,
                    show_completion_message=False,
                    prevent_motion_darkening=True,
                    create_physics=create_physics
                )

                if ret and isinstance(ret, tuple) and len(ret) > 0:
                    last_imported_model = ret[0]
                elif ret and isinstance(ret, str):
                    last_imported_model = ret

                # optionVarへ最後にインポートしたモデルパスを保持
                if mc:
                    try:
                        mc.optionVar(sv=("MMDToolsForMaya_LastPmxPath", fp))
                    except Exception:
                        pass

            # モーション用モード時、VMDモーションおよび音声をインポート
            if is_motion_mode and (vmd_model_items or vmd_cam_items or wav_items):
                print("\n>> モーションおよび音声データの適用中...")
                import importlib
                importlib.reload(vmdpaimaya)

                model_vmd_path = vmd_model_items[0].file_path if vmd_model_items else None
                camera_vmd_path = vmd_cam_items[0].file_path if vmd_cam_items else None
                audio_wav_path = wav_items[0].file_path if wav_items else None

                # 最大フレームの算出
                for vm in (vmd_model_items + vmd_cam_items):
                    if vm.max_frame > max_registered_frame:
                        max_registered_frame = vm.max_frame

                vmdpaimaya.import_vmd(
                    vmd_file_path=model_vmd_path,
                    camera_vmd_path=camera_vmd_path,
                    audio_wav_path=audio_wav_path,
                    scale=scale,
                    target_model_node=last_imported_model,
                    audio_volume=100,
                    progress_callback=log_dialog.update_progress,
                    prevent_motion_darkening=True
                )

                # ビューポートライティングを適正復元
                restore_viewport_lighting(prevent_motion_darkening=True)

                # モーションタブ用設定ファイルおよび optionVar への連動保存
                try:
                    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    vmd_settings_path = os.path.join(plugin_root, 'asset', 'settings', 'vmd_tab_settings.json')
                    os.makedirs(os.path.dirname(vmd_settings_path), exist_ok=True)
                    vmd_data = {}
                    if os.path.exists(vmd_settings_path):
                        try:
                            with open(vmd_settings_path, 'r', encoding='utf-8') as f:
                                vmd_data = json.load(f)
                        except Exception:
                            vmd_data = {}
                    if model_vmd_path:
                        vmd_data["model_vmd_path"] = model_vmd_path.replace("\\", "/")
                        if mc:
                            mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", model_vmd_path.replace("\\", "/")))
                    if camera_vmd_path:
                        vmd_data["camera_vmd_path"] = camera_vmd_path.replace("\\", "/")
                        if mc:
                            mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", camera_vmd_path.replace("\\", "/")))
                    if audio_wav_path:
                        vmd_data["audio_path"] = audio_wav_path.replace("\\", "/")
                        if mc:
                            mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", audio_wav_path.replace("\\", "/")))
                    with open(vmd_settings_path, 'w', encoding='utf-8') as f:
                        json.dump(vmd_data, f, indent=4, ensure_ascii=False)
                except Exception:
                    pass

                # 親ウィンドウのモーションタブ入力欄も即時更新
                if self.parent_window and hasattr(self.parent_window, "tab_vmd"):
                    try:
                        self.parent_window.tab_vmd._load_settings()
                    except Exception:
                        pass

            # タイムライン範囲の更新
            if max_registered_frame > 0 and mc:
                try:
                    mc.currentUnit(time='ntsc')
                    mc.playbackOptions(minTime=0, maxTime=max_registered_frame, animationStartTime=0, animationEndTime=max_registered_frame)
                    mc.currentTime(0)
                    print(f">> タイムライン範囲を設定しました: 0 - {max_registered_frame} フレーム (30fps)")
                except Exception:
                    pass

            # ステージ影および地面影プレーンの設定連動
            if mc and hasattr(pmxpaimaya, "set_ground_shadow_mode"):
                try:
                    # チェック時はステージ自動検出連動（検出時は非表示、未検出時は標準地面影）、未チェック時は常に標準地面影
                    stage_mode_pref = None if self.cb_stage_shadow.isChecked() else False
                    pmxpaimaya.set_ground_shadow_mode(stage_mode=stage_mode_pref)
                except Exception:
                    pass

            # MMD Viewport Renderer への自動切り替え
            if self.cb_switch_mmd_renderer.isChecked():
                set_viewport_renderer_override("mmdRenderOverride")

            elapsed = time.time() - start_time
            print("==================================================")
            print(f"簡単インポートが完了しました！ (所要時間: {elapsed:.2f}秒)")
            print("==================================================")
            return True

        success = log_dialog.run_task(import_task)
        if success and mc:
            mc.inViewMessage(amg='<span style="color:#52b7ff;">MMD Tools for Maya:</span> 簡単インポートが完了しました。', pos='topCenter', fade=True)

    def _on_toggle_renderer_clicked(self):
        """Viewport 2.0 と MMD Viewport Renderer を交互に切り替え"""
        is_now_mmd = toggle_viewport_renderer_override()
        mode_name = "MMD Viewport Renderer" if is_now_mmd else "Viewport 2.0"
        if mc:
            mc.inViewMessage(amg=f'<span style="color:#52b7ff;">レンダラー切替:</span> {mode_name} を適用しました。', pos='topCenter', fade=True)

    def _toggle_shadow_mode(self):
        """地面影プレーンとステージ影の表示切り替え"""
        if mc:
            plane_name = "mmd_ground_shadow_plane"
            # 現在プレーンが表示中なら非表示（ステージ影）へ、非表示なら表示へ反転
            if mc.objExists(plane_name):
                current_vis = bool(mc.getAttr(f"{plane_name}.visibility"))
                new_stage_mode = current_vis
            else:
                new_stage_mode = True

            if hasattr(pmxpaimaya, "set_ground_shadow_mode"):
                applied_mode = pmxpaimaya.set_ground_shadow_mode(stage_mode=new_stage_mode)
                mode_str = "ステージ影 (地面影プレーン非表示 / ステージ床受光有効)" if applied_mode else "標準地面影プレーン表示"
                try:
                    mc.inViewMessage(amg=f'<span style="color:#52b7ff;">MMD影設定:</span> {mode_str}', pos='topCenter', fade=True)
                except Exception:
                    pass
                print(f">> 影モードを切り替えました: {mode_str}")

    def _open_classifier_settings(self):
        """モデル種別判定・個別指定設定ダイアログを開きます"""
        try:
            try:
                from .dialog_model_classifier import show_model_classifier_dialog
            except Exception:
                from ui.dialog_model_classifier import show_model_classifier_dialog
            show_model_classifier_dialog(parent=self.parent_window or self)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"設定ダイアログの起動に失敗しました: {e}")



