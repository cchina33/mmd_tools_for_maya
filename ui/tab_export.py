# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - エクスポートタブおよび独立ダイアログ (Maya → MMD)
"""

from .common import *

# ==============================================================================
# エクスポートタブ (Maya → MMD)
# ==============================================================================
class ExportTabWidget(QWidget):
    """MayaシーンからPMX、VMDモーション、VPDポーズへエクスポートするための統合UIタブ"""
    def __init__(self, parent=None):
        super(ExportTabWidget, self).__init__(parent)
        self.parent_window = parent
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_file = os.path.join(plugin_root, 'asset', 'khatangton2.txt')

        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # スクロールエリアを導入して縦長レイアウトに対応
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(14)
        layout.setContentsMargins(12, 12, 12, 12)

        # モデルデータ (.pmx) エクスポートグループ
        pmx_box = QGroupBox("モデルデータ (.pmx) エクスポート(試験機能)")
        pmx_layout = QVBoxLayout(pmx_box)
        pmx_layout.setSpacing(10)

        # 保存先 PMX ファイル
        h_pmx_file = QHBoxLayout()
        self.le_file_path = QLineEdit()
        self.le_file_path.setPlaceholderText("出力先パス (.pmx)")
        self.le_file_path.textChanged.connect(self._on_file_changed)
        h_pmx_file.addWidget(self.le_file_path)

        self.btn_browse = QPushButton("保存先...")
        self.btn_browse.setFixedWidth(95)
        self.btn_browse.clicked.connect(self._browse_save_file)
        h_pmx_file.addWidget(self.btn_browse)

        self.btn_clear_file = QPushButton("クリア")
        self.btn_clear_file.setFixedWidth(65)
        self.btn_clear_file.clicked.connect(self._clear_file)
        h_pmx_file.addWidget(self.btn_clear_file)
        pmx_layout.addLayout(h_pmx_file)

        # PMX オプション
        h_scale = QHBoxLayout()
        h_scale.addWidget(QLabel("スケール倍率:"))
        self.le_scale = QLineEdit("0.125")
        self.le_scale.setFixedWidth(80)
        self.le_scale.textEdited.connect(self._validate_scale)
        h_scale.addWidget(self.le_scale)
        h_scale.addWidget(QLabel("(インポート時が8.0の場合は 0.125 を推奨)"))
        h_scale.addStretch()
        pmx_layout.addLayout(h_scale)

        self.cb_export_bones = QCheckBox("スケルトン（ボーン）を出力")
        self.cb_export_morphs = QCheckBox("ブレンドシェイプ（モーフ）を出力")
        self.cb_export_materials = QCheckBox("マテリアル（材質）を出力")
        self.cb_copy_textures = QCheckBox("テクスチャファイルを保存先フォルダへコピー")

        pmx_layout.addWidget(self.cb_export_bones)
        pmx_layout.addWidget(self.cb_export_morphs)
        pmx_layout.addWidget(self.cb_export_materials)
        pmx_layout.addWidget(self.cb_copy_textures)

        # 出力対象メッシュ
        h_poly = QHBoxLayout()
        h_poly.addWidget(QLabel("出力対象メッシュ:"))
        self.btng_target = QButtonGroup(self)
        self.rb_all_mesh = QRadioButton("シーン内のすべての対象メッシュ")
        self.rb_selected_mesh = QRadioButton("選択中のメッシュのみ")
        self.btng_target.addButton(self.rb_all_mesh)
        self.btng_target.addButton(self.rb_selected_mesh)
        self.rb_all_mesh.setChecked(True)
        h_poly.addWidget(self.rb_all_mesh)
        h_poly.addWidget(self.rb_selected_mesh)
        h_poly.addStretch()
        pmx_layout.addLayout(h_poly)

        # PMX 実行ボタン
        self.btn_execute = QPushButton("PMX をエクスポート")
        self.btn_execute.setProperty("class", "primary")
        self.btn_execute.setFixedHeight(42)
        self.btn_execute.clicked.connect(self._execute_export)
        pmx_layout.addWidget(self.btn_execute)

        layout.addWidget(pmx_box)

        # MMD モーションデータ (.vmd) エクスポート (試験的機能) グループ
        vmd_box = QGroupBox("MMD モーションデータ (.vmd) エクスポート (試験的機能)")
        vmd_layout = QVBoxLayout(vmd_box)
        vmd_layout.setSpacing(10)

        # 適用先モデル選択
        h_vmd_model = QHBoxLayout()
        h_vmd_model.addWidget(QLabel("対象モデル:"))
        self.cbb_vmd_target_model = QComboBox()
        self.btn_refresh_vmd_models = QPushButton("更新")
        self.btn_refresh_vmd_models.setFixedWidth(75)
        self.btn_refresh_vmd_models.clicked.connect(self._refresh_models)
        h_vmd_model.addWidget(self.cbb_vmd_target_model)
        h_vmd_model.addWidget(self.btn_refresh_vmd_models)
        vmd_layout.addLayout(h_vmd_model)

        h_vmd_scale = QHBoxLayout()
        h_vmd_scale.addWidget(QLabel("スケール倍率:"))
        self.le_vmd_scale = QLineEdit("8.0")
        self.le_vmd_scale.setFixedWidth(80)
        h_vmd_scale.addWidget(self.le_vmd_scale)
        h_vmd_scale.addWidget(QLabel("(インポート時と同じ倍率を指定)"))
        h_vmd_scale.addStretch()
        vmd_layout.addLayout(h_vmd_scale)

        h_vmd_targets = QHBoxLayout()
        self.cb_vmd_exp_bones = QCheckBox("ボーンアニメーション")
        self.cb_vmd_exp_bones.setChecked(True)
        h_vmd_targets.addWidget(self.cb_vmd_exp_bones)

        self.cb_vmd_exp_morphs = QCheckBox("表情モーフアニメーション")
        self.cb_vmd_exp_morphs.setChecked(True)
        h_vmd_targets.addWidget(self.cb_vmd_exp_morphs)

        self.cb_vmd_exp_camera = QCheckBox("カメラアニメーション")
        self.cb_vmd_exp_camera.setChecked(False)
        h_vmd_targets.addWidget(self.cb_vmd_exp_camera)
        h_vmd_targets.addStretch()
        vmd_layout.addLayout(h_vmd_targets)

        h_vmd_range = QHBoxLayout()
        self.rb_vmd_exp_slider = QRadioButton("タイムスライダー範囲")
        self.rb_vmd_exp_slider.setChecked(True)
        h_vmd_range.addWidget(self.rb_vmd_exp_slider)

        self.rb_vmd_exp_custom = QRadioButton("カスタム範囲:")
        h_vmd_range.addWidget(self.rb_vmd_exp_custom)

        self.spn_vmd_start = QSpinBox()
        self.spn_vmd_start.setRange(-999999, 999999)
        self.spn_vmd_start.setValue(0)
        self.spn_vmd_start.setEnabled(False)
        h_vmd_range.addWidget(self.spn_vmd_start)

        lbl_to = QLabel("〜")
        h_vmd_range.addWidget(lbl_to)

        self.spn_vmd_end = QSpinBox()
        self.spn_vmd_end.setRange(-999999, 999999)
        self.spn_vmd_end.setValue(100)
        self.spn_vmd_end.setEnabled(False)
        h_vmd_range.addWidget(self.spn_vmd_end)

        self.rb_vmd_exp_custom.toggled.connect(self.spn_vmd_start.setEnabled)
        self.rb_vmd_exp_custom.toggled.connect(self.spn_vmd_end.setEnabled)
        h_vmd_range.addStretch()
        vmd_layout.addLayout(h_vmd_range)

        h_vmd_opts = QHBoxLayout()
        self.cb_vmd_exp_simplify = QCheckBox("静止フレームの重複キーを間引く (軽量化)")
        self.cb_vmd_exp_simplify.setChecked(True)
        h_vmd_opts.addWidget(self.cb_vmd_exp_simplify)
        h_vmd_opts.addStretch()
        vmd_layout.addLayout(h_vmd_opts)

        self.btn_export_vmd = QPushButton("アニメーションをVMD書き出し (エクスポート) (試験的機能)")
        self.btn_export_vmd.setFixedHeight(40)
        self.btn_export_vmd.setStyleSheet("QPushButton { background-color: #2b5b84; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3b7bb4; }")
        self.btn_export_vmd.setToolTip("選択中モデルのボーンおよびモーフアニメーションをMMD公式モーション (.vmd) として保存します。")
        self.btn_export_vmd.clicked.connect(self._on_export_vmd)
        vmd_layout.addWidget(self.btn_export_vmd)

        layout.addWidget(vmd_box)

        # MMD ポーズデータ (.vpd) エクスポート (試験的機能) グループ
        vpd_box = QGroupBox("MMD ポーズデータ (.vpd) エクスポート (試験的機能)")
        vpd_layout = QVBoxLayout(vpd_box)
        vpd_layout.setSpacing(10)

        h_vpd_model = QHBoxLayout()
        h_vpd_model.addWidget(QLabel("対象モデル:"))
        self.cbb_vpd_target_model = QComboBox()
        self.btn_refresh_vpd_models = QPushButton("更新")
        self.btn_refresh_vpd_models.setFixedWidth(75)
        self.btn_refresh_vpd_models.clicked.connect(self._refresh_models)
        h_vpd_model.addWidget(self.cbb_vpd_target_model)
        h_vpd_model.addWidget(self.btn_refresh_vpd_models)
        vpd_layout.addLayout(h_vpd_model)

        h_vpd_scale = QHBoxLayout()
        h_vpd_scale.addWidget(QLabel("スケール倍率:"))
        self.le_vpd_scale = QLineEdit("8.0")
        self.le_vpd_scale.setFixedWidth(80)
        h_vpd_scale.addWidget(self.le_vpd_scale)
        h_vpd_scale.addWidget(QLabel("(インポート時と同じ倍率を指定)"))
        h_vpd_scale.addStretch()
        vpd_layout.addLayout(h_vpd_scale)

        self.btn_export_vpd = QPushButton("現在のポーズをVPD保存 (エクスポート) (試験的機能)")
        self.btn_export_vpd.setFixedHeight(40)
        self.btn_export_vpd.setStyleSheet("QPushButton { background-color: #346856; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #458a72; }")
        self.btn_export_vpd.setToolTip("現在フレームのモデルのボーン姿勢および表情モーフを .vpd ファイルとして保存します。")
        self.btn_export_vpd.clicked.connect(self._on_export_vpd)
        vpd_layout.addWidget(self.btn_export_vpd)

        layout.addWidget(vpd_box)

        # 実行完了後アクション
        h_action = QHBoxLayout()
        h_action.setContentsMargins(0, 4, 0, 4)
        self.cb_close_on_finish = QCheckBox("完了後にウィンドウを閉じる")
        h_action.addWidget(self.cb_close_on_finish)
        h_action.addStretch()
        layout.addLayout(h_action)

        layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        self._refresh_models()

    def showEvent(self, event):
        super(ExportTabWidget, self).showEvent(event)
        self._refresh_models()

    def _refresh_models(self):
        """シーン内のMMDモデル一覧を取得してVMD/VPDの対象モデルコンボボックスへ設定"""
        for cbb in [getattr(self, 'cbb_vmd_target_model', None), getattr(self, 'cbb_vpd_target_model', None)]:
            if cbb is None:
                continue
            cur = cbb.currentData()
            cbb.clear()
            cbb.addItem("シーン内の全MMDモデル / 自動検出", None)
            try:
                models = vmdpaimaya.get_available_mmd_models()
                for node_name, label in models:
                    cbb.addItem(label, node_name)
            except Exception:
                pass
            if cur:
                idx = cbb.findData(cur)
                if idx >= 0:
                    cbb.setCurrentIndex(idx)

    def _load_settings(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    file_path = f.readline().split('=')[-1].strip()
                    scale = f.readline().split('=')[-1].strip()
                    bs = int(f.readline().split('=')[-1].strip())
                    bones = int(f.readline().split('=')[-1].strip())
                    mat = int(f.readline().split('=')[-1].strip())
                    copy_tex = int(f.readline().split('=')[-1].strip())
                    all_poly = int(f.readline().split('=')[-1].strip())
                    close = int(f.readline().split('=')[-1].strip())

                self.le_file_path.setText(file_path)
                self.le_scale.setText(scale)
                self.cb_export_morphs.setChecked(bool(bs))
                self.cb_export_bones.setChecked(bool(bones))
                self.cb_export_materials.setChecked(bool(mat))
                self.cb_copy_textures.setChecked(bool(copy_tex))
                if all_poly:
                    self.rb_all_mesh.setChecked(True)
                else:
                    self.rb_selected_mesh.setChecked(True)
                self.cb_close_on_finish.setChecked(bool(close))
                return
        except Exception:
            pass

        self.le_scale.setText("0.125")
        self.cb_export_bones.setChecked(True)
        self.cb_export_morphs.setChecked(True)
        self.cb_export_materials.setChecked(True)
        self.cb_copy_textures.setChecked(False)
        self.cb_close_on_finish.setChecked(False)

    def _save_settings(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(f"ファイルの名前 = {self.le_file_path.text()}\n")
                f.write(f"尺度 = {self.le_scale.text()}\n")
                f.write(f"ブレンドシェープ = {int(self.cb_export_morphs.isChecked())}\n")
                f.write(f"ジョイント = {int(self.cb_export_bones.isChecked())}\n")
                f.write(f"材質 = {int(self.cb_export_materials.isChecked())}\n")
                f.write(f"テクスチャのコピー = {int(self.cb_copy_textures.isChecked())}\n")
                f.write(f"ポリゴン全部 = {int(self.rb_all_mesh.isChecked())}\n")
                f.write(f"閉じる = {int(self.cb_close_on_finish.isChecked())}\n")
        except Exception:
            pass

    def _on_file_changed(self, path):
        valid = path.lower().endswith('.pmx')
        self.btn_execute.setEnabled(valid)
        self._save_settings()

    def _clear_file(self):
        """保存先ファイル入力欄をクリア"""
        self.le_file_path.clear()
        self._save_settings()

    def _browse_save_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "エクスポート先 PMX を指定",
            self.le_file_path.text(),
            "PMX Model (*.pmx)"
        )
        if path:
            if not path.lower().endswith('.pmx'):
                path += '.pmx'
            self.le_file_path.setText(path)
            self._save_settings()

    def _validate_scale(self, text):
        try:
            float(text)
        except ValueError:
            self.le_scale.setText("0.125")

    def _execute_export(self):
        file_path = self.le_file_path.text().strip()
        if not file_path:
            QMessageBox.warning(self, "エラー", "保存先のファイルパスを指定してください。")
            return

        try:
            scale = float(self.le_scale.text())
        except ValueError:
            scale = 0.125

        export_bones = self.cb_export_bones.isChecked()
        export_morphs = self.cb_export_morphs.isChecked()
        export_materials = self.cb_export_materials.isChecked()
        copy_textures = self.cb_copy_textures.isChecked()
        all_mesh = self.rb_all_mesh.isChecked()

        # ログウィンドウを起動して実行
        log_dialog = ExecutionLogDialog(self.parent_window or self, title="PMXエクスポート実行ログ")
        export_func = getattr(mayapaipmx, 'export_pmx', mayapaipmx.sang)
        success = log_dialog.run_task(
            export_func,
            file_path, scale, export_bones, export_morphs, export_materials, copy_textures, all_mesh
        )

        if success:
            mc.inViewMessage(amg='<span style="color:#52b7ff;">MMD Tools for Maya:</span> エクスポートが完了しました。', pos='topCenter', fade=True)
            self._save_settings()

            if self.cb_close_on_finish.isChecked() and self.parent_window:
                self.parent_window.close()

    def _on_export_vpd(self):
        """現在のポーズをVPDファイルとして保存 (試験的機能)"""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "VPDポーズの保存先を指定",
            "",
            "VPD Pose Data (*.vpd);;All Files (*.*)"
        )
        if not path:
            return

        if not path.lower().endswith('.vpd'):
            path += '.vpd'

        target_model = self.cbb_vpd_target_model.currentData()
        try:
            scale = float(self.le_vpd_scale.text())
        except ValueError:
            scale = 8.0

        try:
            from ..maya_maya_converters import vmdpaimaya
        except Exception:
            from maya_converters import vmdpaimaya

        try:
            res = vmdpaimaya.export_vpd(path, target_model_node=target_model, scale=scale)
            QMessageBox.information(
                self,
                "VPDポーズ保存",
                f"現在の姿勢をVPDポーズファイルとして保存しました。\n"
                f"・ボーン数: {res['bones_exported']} 本\n"
                f"・モーフ数: {res['morphs_exported']} 個\n"
                f"・保存先: {os.path.basename(path)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"VPDポーズの保存中にエラーが発生しました:\n{e}")

    def _on_export_vmd(self):
        """現在のシーンアニメーションをVMDファイルとして保存 (試験的機能)"""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "VMDモーションの保存先を指定",
            "",
            "VMD Motion Data (*.vmd);;All Files (*.*)"
        )
        if not path:
            return

        if not path.lower().endswith('.vmd'):
            path += '.vmd'

        target_model = self.cbb_vmd_target_model.currentData()
        try:
            scale = float(self.le_vmd_scale.text())
        except ValueError:
            scale = 8.0

        if self.rb_vmd_exp_custom.isChecked():
            start_f = self.spn_vmd_start.value()
            end_f = self.spn_vmd_end.value()
        else:
            try:
                start_f = int(mc.playbackOptions(query=True, minTime=True))
                end_f = int(mc.playbackOptions(query=True, maxTime=True))
            except Exception:
                start_f = 0
                end_f = 100

        exp_bones = self.cb_vmd_exp_bones.isChecked()
        exp_morphs = self.cb_vmd_exp_morphs.isChecked()
        exp_camera = self.cb_vmd_exp_camera.isChecked()
        simplify = self.cb_vmd_exp_simplify.isChecked()

        try:
            from ..maya_maya_converters import vmdpaimaya
        except Exception:
            from maya_converters import vmdpaimaya

        try:
            res = vmdpaimaya.export_vmd(
                path,
                target_model_node=target_model,
                start_frame=start_f,
                end_frame=end_f,
                scale=scale,
                export_bones=exp_bones,
                export_morphs=exp_morphs,
                export_camera=exp_camera,
                simplify_keys=simplify
            )
            QMessageBox.information(
                self,
                "VMD保存完了",
                f"アニメーションをVMDモーションファイルとして保存しました。\n"
                f"・ボーンキー総数: {res['total_bone_frames']:,}\n"
                f"・モーフキー総数: {res['total_morph_frames']:,}\n"
                f"・カメラキー総数: {res['total_camera_frames']:,}\n"
                f"・保存先: {os.path.basename(path)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"VMDモーションの保存中にエラーが発生しました:\n{e}")


# ==============================================================================
# Maya → MMD (エクスポート) 独立ダイアログ
# ==============================================================================
class ExportDialog(QDialog):
    """Maya → MMD エクスポートを別ウィンドウで表示するダイアログ"""
    def __init__(self, parent=None):
        super(ExportDialog, self).__init__(parent)
        self.setWindowTitle("Maya → MMD (エクスポート)")
        self.resize(840, 780)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        self.export_widget = ExportTabWidget(self)
        main_layout.addWidget(self.export_widget)

        # 下部ボタングループ
        h_bottom = QHBoxLayout()
        h_bottom.addStretch()
        btn_close = QPushButton("閉じる")
        btn_close.setFixedWidth(100)
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.close)
        h_bottom.addWidget(btn_close)
        main_layout.addLayout(h_bottom)
