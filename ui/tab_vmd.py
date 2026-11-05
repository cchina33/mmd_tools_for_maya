# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - モーションインポートタブ (VMD → Maya)
"""

from .common import *

# ==============================================================================
# モーションインポートタブ (VMD → Maya)
# ==============================================================================
class VmdImportTabWidget(QWidget):
    """MMDモーション (VMD) をMayaシーンにインポートするためのUIタブ"""
    def __init__(self, parent=None):
        super(VmdImportTabWidget, self).__init__(parent)
        self.parent_window = parent
        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        # VMDファイル選択
        file_box = QGroupBox("VMD モーションファイル指定")
        file_layout = QVBoxLayout(file_box)

        # キャラクタモーション (ボーン・表情)
        lbl_model = QLabel("キャラクタモーション (.vmd):")
        file_layout.addWidget(lbl_model)
        h_model_file = QHBoxLayout()
        self.le_file_path = QLineEdit()
        self.le_file_path.setPlaceholderText("ダンス・表情モーションファイル (.vmd)")
        self.le_file_path.textChanged.connect(self._on_file_changed)
        h_model_file.addWidget(self.le_file_path)

        self.btn_browse = QPushButton("参照...")
        self.btn_browse.setFixedWidth(75)
        self.btn_browse.clicked.connect(self._browse_file)
        h_model_file.addWidget(self.btn_browse)

        self.btn_clear_model = QPushButton("クリア")
        self.btn_clear_model.setFixedWidth(65)
        self.btn_clear_model.clicked.connect(self._clear_model_file)
        h_model_file.addWidget(self.btn_clear_model)
        file_layout.addLayout(h_model_file)

        # カメラモーション
        lbl_cam = QLabel("カメラモーション (.vmd) ※省略可能,ベータ版:")
        lbl_cam.setStyleSheet("margin-top: 6px;")
        file_layout.addWidget(lbl_cam)
        h_cam_file = QHBoxLayout()
        self.le_camera_path = QLineEdit()
        self.le_camera_path.setPlaceholderText("カメラワーク専用ファイル (.vmd)")
        self.le_camera_path.textChanged.connect(self._on_file_changed)
        h_cam_file.addWidget(self.le_camera_path)

        self.btn_browse_camera = QPushButton("参照...")
        self.btn_browse_camera.setFixedWidth(75)
        self.btn_browse_camera.clicked.connect(self._browse_camera_file)
        h_cam_file.addWidget(self.btn_browse_camera)

        self.btn_clear_camera = QPushButton("クリア")
        self.btn_clear_camera.setFixedWidth(65)
        self.btn_clear_camera.clicked.connect(self._clear_camera_file)
        h_cam_file.addWidget(self.btn_clear_camera)
        file_layout.addLayout(h_cam_file)

        # BGM / 音声ファイル (.wav)
        lbl_audio = QLabel("BGM / 音声ファイル (.wav) ※省略可能:")
        lbl_audio.setStyleSheet("margin-top: 6px;")
        file_layout.addWidget(lbl_audio)
        h_audio_file = QHBoxLayout()
        self.le_audio_path = QLineEdit()
        self.le_audio_path.setPlaceholderText("BGM音源ファイル (.wav)")
        self.le_audio_path.textChanged.connect(self._on_file_changed)
        h_audio_file.addWidget(self.le_audio_path)

        self.btn_browse_audio = QPushButton("参照...")
        self.btn_browse_audio.setFixedWidth(75)
        self.btn_browse_audio.clicked.connect(self._browse_audio_file)
        h_audio_file.addWidget(self.btn_browse_audio)

        self.btn_clear_audio = QPushButton("クリア")
        self.btn_clear_audio.setFixedWidth(65)
        self.btn_clear_audio.clicked.connect(self._clear_audio_file)
        h_audio_file.addWidget(self.btn_clear_audio)
        file_layout.addLayout(h_audio_file)

        layout.addWidget(file_box)

        # 設定

        opt_box = QGroupBox("モーション設定")
        opt_layout = QVBoxLayout(opt_box)

        # 適用先モデル選択
        h_model = QHBoxLayout()
        h_model.addWidget(QLabel("適用先モデル:"))
        self.cbb_target_model = QComboBox()
        self.btn_refresh_models = QPushButton("更新")
        self.btn_refresh_models.setFixedWidth(80)
        self.btn_refresh_models.clicked.connect(self._refresh_models)
        h_model.addWidget(self.cbb_target_model)
        h_model.addWidget(self.btn_refresh_models)
        opt_layout.addLayout(h_model)

        h_scale = QHBoxLayout()
        h_scale.addWidget(QLabel("スケール倍率:"))
        self.le_scale = QLineEdit("8.0")
        self.le_scale.setFixedWidth(80)
        h_scale.addWidget(self.le_scale)
        h_scale.addWidget(QLabel("(モデルインポート時と同じ倍率を指定)"))
        h_scale.addStretch()
        opt_layout.addLayout(h_scale)

        info_lbl = QLabel(
            "・キャラクタモーションとカメラモーションを別々に、または同時にインポートできます。\n"
            "・カメラモーション読み込み時、MMDと同等の注視点オービットカメラを自動構築します。\n"
            "・足IKシステムがモデル内に未作成の場合でも、インポート時に自動構築されて滑らかに連動します。"
        )
        info_lbl.setStyleSheet("color: #999; font-size: 12px; margin-top: 4px; line-height: 1.4;")
        opt_layout.addWidget(info_lbl)

        layout.addWidget(opt_box)
        layout.addStretch()

        self._refresh_models()

        # 実行アクション
        h_action = QHBoxLayout()
        h_action.setSpacing(12)

        self.cb_close_on_finish = QCheckBox("完了後にウィンドウを閉じる")
        h_action.addWidget(self.cb_close_on_finish)
        h_action.addStretch()

        # モーションインポート実行ボタン
        self.btn_execute = QPushButton("モーションをインポート")
        self.btn_execute.setProperty("class", "primary")
        self.btn_execute.setFixedHeight(46)
        self.btn_execute.setMinimumWidth(200)
        self.btn_execute.setEnabled(False)
        self.btn_execute.clicked.connect(self._execute_import)
        h_action.addWidget(self.btn_execute)

        layout.addLayout(h_action)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # 初期化中フラグ
        self._is_initializing = True

        # 前回パスの復元 (空白が保存されている場合は空白を維持)
        if mc.optionVar(exists="MMDToolsForMaya_LastModelVmdPath"):
            last_model_vmd = mc.optionVar(q="MMDToolsForMaya_LastModelVmdPath")
            if last_model_vmd and os.path.exists(last_model_vmd):
                self.le_file_path.setText(last_model_vmd)

        if mc.optionVar(exists="MMDToolsForMaya_LastCameraVmdPath"):
            last_cam_vmd = mc.optionVar(q="MMDToolsForMaya_LastCameraVmdPath")
            if last_cam_vmd and os.path.exists(last_cam_vmd):
                self.le_camera_path.setText(last_cam_vmd)

        if mc.optionVar(exists="MMDToolsForMaya_LastAudioPath"):
            last_audio = mc.optionVar(q="MMDToolsForMaya_LastAudioPath")
            if last_audio and os.path.exists(last_audio):
                self.le_audio_path.setText(last_audio)

        self._is_initializing = False
        self._on_file_changed()

    def _open_morph_window(self):
        """MMD本家風の表情操作ウィンドウを開く"""
        try:
            from .morph_window import show_morph_window
        except Exception:
            try:
                from morph_window import show_morph_window
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"表情操作モジュールの読み込みに失敗しました:\n{e}")
                return

        show_morph_window(parent=get_maya_main_window())

    def _refresh_models(self):
        self.cbb_target_model.clear()
        self.cbb_target_model.addItem("シーン内の全MMDモデル / 自動検出", None)
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for node_name, label in models:
                self.cbb_target_model.addItem(label, node_name)
        except Exception:
            pass

    def _on_file_changed(self, text=""):
        path1 = self.le_file_path.text().strip()
        path2 = self.le_camera_path.text().strip()
        path3 = self.le_audio_path.text().strip()
        valid1 = path1.lower().endswith('.vmd') and os.path.exists(path1)
        valid2 = path2.lower().endswith('.vmd') and os.path.exists(path2)
        valid3 = path3.lower().endswith('.wav') and os.path.exists(path3)
        self.btn_execute.setEnabled(valid1 or valid2 or valid3)

        if getattr(self, "_is_initializing", False):
            return

        if valid1:
            mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", path1))
        if valid2:
            mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", path2))
        if valid3:
            mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", path3))

    def _clear_model_file(self):
        """モデルモーション入力欄をクリア"""
        self.le_file_path.clear()
        mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", ""))

    def _clear_camera_file(self):
        """カメラモーション入力欄をクリア"""
        self.le_camera_path.clear()
        mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", ""))

    def _clear_audio_file(self):
        """BGM音声ファイル入力欄をクリア"""
        self.le_audio_path.clear()
        mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", ""))

    def _browse_file(self):

        start_dir = self.le_file_path.text().strip()
        if not start_dir or not os.path.exists(start_dir):
            if mc.optionVar(exists="MMDToolsForMaya_LastModelVmdPath"):
                cand = mc.optionVar(q="MMDToolsForMaya_LastModelVmdPath")
                if cand and os.path.exists(cand):
                    start_dir = cand
        if start_dir and os.path.isfile(start_dir):
            start_dir = os.path.dirname(start_dir)

        path, _ = QFileDialog.getOpenFileName(
            self,
            "キャラクタモーションファイルを選択",
            start_dir,
            "VMD Motion (*.vmd);;All Files (*.*)"
        )
        if path:
            self.le_file_path.setText(path)
            mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", path))

    def _browse_camera_file(self):
        start_dir = self.le_camera_path.text().strip()
        if not start_dir or not os.path.exists(start_dir):
            if mc.optionVar(exists="MMDToolsForMaya_LastCameraVmdPath"):
                cand = mc.optionVar(q="MMDToolsForMaya_LastCameraVmdPath")
                if cand and os.path.exists(cand):
                    start_dir = cand
        if start_dir and os.path.isfile(start_dir):
            start_dir = os.path.dirname(start_dir)

        path, _ = QFileDialog.getOpenFileName(
            self,
            "カメラモーションファイルを選択",
            start_dir,
            "VMD Camera (*.vmd);;All Files (*.*)"
        )
        if path:
            self.le_camera_path.setText(path)
            mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", path))

    def _browse_audio_file(self):
        start_dir = self.le_audio_path.text().strip()
        if not start_dir or not os.path.exists(start_dir):
            if mc.optionVar(exists="MMDToolsForMaya_LastAudioPath"):
                cand = mc.optionVar(q="MMDToolsForMaya_LastAudioPath")
                if cand and os.path.exists(cand):
                    start_dir = cand
            else:
                wav_dir = os.path.join(os.path.dirname(__file__), "wav")
                if os.path.exists(wav_dir):
                    start_dir = wav_dir
        if start_dir and os.path.isfile(start_dir):
            start_dir = os.path.dirname(start_dir)

        path, _ = QFileDialog.getOpenFileName(
            self,
            "BGM / 音声ファイルを選択",
            start_dir,
            "WAV Audio (*.wav);;All Files (*.*)"
        )
        if path:
            self.le_audio_path.setText(path)
            mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", path))

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        local_files = [u.toLocalFile() for u in urls]
        vmd_files = [f for f in local_files if f.lower().endswith('.vmd')]
        wav_files = [f for f in local_files if f.lower().endswith('.wav')]

        if wav_files:
            self.le_audio_path.setText(wav_files[0])
            mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", wav_files[0]))

        if len(vmd_files) >= 2:
            # 複数ファイルドロップ時のカメラ/モデル自動振り分け
            for f in vmd_files:
                base_low = os.path.basename(f).lower()
                if any(k in base_low for k in ["cam", "camera", "カメラ"]):
                    self.le_camera_path.setText(f)
                    mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", f))
                else:
                    self.le_file_path.setText(f)
                    mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", f))
        elif len(vmd_files) == 1:
            single = vmd_files[0]
            base_low = os.path.basename(single).lower()
            if any(k in base_low for k in ["cam", "camera", "カメラ"]):
                self.le_camera_path.setText(single)
                mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", single))
            else:
                self.le_file_path.setText(single)
                mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", single))

    def _execute_import(self):
        file_path = self.le_file_path.text().strip() or None
        camera_path = self.le_camera_path.text().strip() or None
        audio_path = self.le_audio_path.text().strip() or None

        if not file_path and not camera_path and not audio_path:
            QMessageBox.warning(self, "エラー", "モーションまたは音声ファイルが指定されていません。")
            return

        # キャラクタモーション指定時、シーン内にボーンが存在するか検証
        if file_path:
            joints = mc.ls(type="joint") or []
            if not joints:
                QMessageBox.warning(
                    self,
                    "スケルトン未検出エラー",
                    "シーン内にモデルのスケルトン（ボーン）が存在しません。\n\n"
                    "キャラクタモーションを適用するには、先に「MMD → Maya (インポート)」タブで\n"
                    "「スケルトン（ジョイント）を作成する」にチェックを入れてモデルをインポートしてください。"
                )
                return

        try:
            scale = float(self.le_scale.text())
        except ValueError:
            scale = 8.0

        target_model = self.cbb_target_model.currentData()

        # VMDアナライザーによる概要診断の出力
        try:
            try:
                from ..converters import vmd_analyzer
            except Exception:
                from converters import vmd_analyzer
            if file_path and os.path.exists(file_path):
                report = vmd_analyzer.analyze_vmd(file_path)
                print(report.generate_summary_text())
        except Exception:
            pass

        log_dialog = ExecutionLogDialog(self.parent_window or self, title="VMDモーションインポート実行ログ")
        import_func = vmdpaimaya.import_vmd
        # 音量調整はMaya標準機能へ委任（標準値100%を適用）
        audio_volume = 100

        if audio_path and os.path.exists(audio_path):
            mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", audio_path))
        if file_path and os.path.exists(file_path):
            mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", file_path))
        if camera_path and os.path.exists(camera_path):
            mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", camera_path))

        prevent_darkening = True
        if self.parent_window and hasattr(self.parent_window, "tab_import"):
            if hasattr(self.parent_window.tab_import, "cb_prevent_motion_darkening"):
                prevent_darkening = self.parent_window.tab_import.cb_prevent_motion_darkening.isChecked()

        success = log_dialog.run_task(
            import_func,
            file_path,
            camera_path,
            audio_path,
            scale,
            target_model,
            audio_volume,
            progress_callback=log_dialog.update_progress,
            prevent_motion_darkening=prevent_darkening
        )

        # インポート完了後のビューポートライティングを確実に復元
        restore_viewport_lighting(prevent_motion_darkening=prevent_darkening)

        if success:
            mc.inViewMessage(amg='<span style="color:#52b7ff;">MMD Tools for Maya:</span> モーション・音声インポートが完了しました。', pos='topCenter', fade=True)
            if self.cb_close_on_finish.isChecked() and self.parent_window:
                self.parent_window.close()
