# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - インポートタブ (MMD → Maya)
"""

from .common import *
from .multi_model_dialog import MultiModelImportDialog
from .pmm_dialog import PmmAnalysisDialog, PmmModelImportSelectDialog

try:
    from ..mmd_core import pmx, pmd, vmd, pmm
    from ..converters import pmxpaimaya, vmdpaimaya, pmd2pmx
except Exception:
    try:
        from mmd_core import pmx, pmd, vmd, pmm
        from converters import pmxpaimaya, vmdpaimaya, pmd2pmx
    except Exception:
        import mmd_core.pmx as pmx
        import mmd_core.pmd as pmd
        import mmd_core.vmd as vmd
        import mmd_core.pmm as pmm
        import converters.pmxpaimaya as pmxpaimaya
        import converters.vmdpaimaya as vmdpaimaya
        import converters.pmd2pmx as pmd2pmx


# ==============================================================================
# インポートタブ (MMD → Maya)
# ==============================================================================
class ImportTabWidget(QWidget):
    """MMDモデルをMayaへインポートするためのUIタブ"""
    def __init__(self, parent=None):
        super(ImportTabWidget, self).__init__(parent)
        self.parent_window = parent
        try:
            self.setAcceptDrops(True)
        except Exception:
            pass
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_file = os.path.join(plugin_root, 'asset', 'khatangton1.txt')
        
        self._init_ui()
        self._load_settings()

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

        # ファイル選択ゾーン (ドラッグ＆ドロップ対応)
        file_box = QGroupBox("モデルファイル (.pmx / .pmd / .x)")
        file_layout = QVBoxLayout(file_box)
        
        h_file_input = QHBoxLayout()
        self.le_file_path = QLineEdit()
        self.le_file_path.setPlaceholderText("ファイルパスを入力、またはここにファイルをドラッグ＆ドロップ")
        self.le_file_path.textChanged.connect(self._on_file_changed)
        h_file_input.addWidget(self.le_file_path)

        self.btn_browse = QPushButton("参照...")
        self.btn_browse.setFixedWidth(75)
        self.btn_browse.clicked.connect(self._browse_file)
        h_file_input.addWidget(self.btn_browse)

        self.btn_clear_file = QPushButton("クリア")
        self.btn_clear_file.setFixedWidth(65)
        self.btn_clear_file.clicked.connect(self._clear_file)
        h_file_input.addWidget(self.btn_clear_file)
        file_layout.addLayout(h_file_input)

        # 複数モデル一括インポートボタン (試験的機能)
        self.btn_multi_import = QPushButton("複数のモデルをインポートする (試験的機能)...")
        self.btn_multi_import.setStyleSheet("font-weight: bold; padding: 6px;")
        self.btn_multi_import.clicked.connect(self._open_multi_model_import_window)
        file_layout.addWidget(self.btn_multi_import)

        # pmmから読み込めるボタン (試験的機能)
        self.btn_pmm_import = QPushButton("pmmから読み込む (試験的機能)...")
        self.btn_pmm_import.setStyleSheet("font-weight: bold; padding: 6px;")
        self.btn_pmm_import.clicked.connect(self._open_pmm_analysis_window)
        file_layout.addWidget(self.btn_pmm_import)

        layout.addWidget(file_box)

        # スケール設定

        scale_box = QGroupBox("インポート設定")
        scale_layout = QVBoxLayout(scale_box)

        h_scale = QHBoxLayout()
        h_scale.addWidget(QLabel("スケール倍率:"))
        self.le_scale = QLineEdit("8.0")
        self.le_scale.setFixedWidth(80)
        self.le_scale.textEdited.connect(self._validate_scale)
        h_scale.addWidget(self.le_scale)
        h_scale.addWidget(QLabel("(標準: 8.0)"))
        h_scale.addStretch()
        scale_layout.addLayout(h_scale)

        # チェックオプション
        self.cb_split_poly = QCheckBox("材質ごとにメッシュ（ポリゴン）を分割する")
        self.cb_create_bones = QCheckBox("スケルトン（ジョイント）を作成する")
        self.cb_create_bones.setChecked(True)
        self.cb_create_physics = QCheckBox("剛体・Jointコライダーを生成")
        self.cb_create_physics.setChecked(True)
        self.cb_create_bs = QCheckBox("ブレンドシェイプ（モーフ）を作成する")
        self.cb_create_bs.setChecked(True)
        self.cb_check_morph_bone = QCheckBox("モーフ・ボーン名チェックを実行する (辞書照合)")
        self.cb_check_morph_bone.setChecked(True)
        self.cb_check_morph_bone.setToolTip("モデルインポート時にモーフ名およびボーン名を走査し、ユーザー辞書への未登録漢字や未知名称のチェック・照合を行います。")

        scale_layout.addWidget(self.cb_split_poly)
        scale_layout.addWidget(self.cb_create_bones)
        scale_layout.addWidget(self.cb_create_physics)
        scale_layout.addWidget(self.cb_create_bs)
        scale_layout.addWidget(self.cb_check_morph_bone)

        self.cb_split_poly.toggled.connect(self._on_split_toggled)

        # マテリアルタイプ
        h_mat = QHBoxLayout()
        h_mat.addWidget(QLabel("マテリアル種別:"))
        self.cbb_material = QComboBox()
        self.cbb_material.addItem("マテリアルなし", 0)
        self.cbb_material.addItem("Blinn", 1)
        self.cbb_material.addItem("Phong", 2)
        self.cbb_material.addItem("Lambert", 3)
        self.cbb_material.addItem("StandardSurface (Maya 2022+)", 4)
        self.cbb_material.addItem("MMD Toon Shader (推奨)", 6)
        self.cbb_material.setCurrentIndex(self.cbb_material.count() - 1)
        h_mat.addWidget(self.cbb_material)
        h_mat.addStretch()
        scale_layout.addLayout(h_mat)

        layout.addWidget(scale_box)

        # ライティング＆シェーディング設定
        light_box = QGroupBox("ライティング＆シェーディング設定")
        light_layout = QVBoxLayout(light_box)
        self.cb_create_light = QCheckBox("MMD標準ライトを作成する (Directional & Ambient)")
        self.cb_create_light.setChecked(True)
        self.cb_create_light.setToolTip("MMDと同等の平行光源と環境光を作成し、モデルの黒化を防ぎます。シーン内にすでにライトがある場合は自動的にスキップされます。")
        light_layout.addWidget(self.cb_create_light)

        self.cb_untone_mapped = QCheckBox("ビュー変換を Un-tone-mapped (sRGB) に設定する")
        self.cb_untone_mapped.setChecked(True)
        self.cb_untone_mapped.setToolTip("トーンマッピングによる色の暗化・沈みを防ぎ、MMD本来の明るく鮮やかな発色にします。")
        light_layout.addWidget(self.cb_untone_mapped)

        self.cb_prevent_motion_darkening = QCheckBox("モーション再生時の暗化を防止する（ブレなし最適化）")
        self.cb_prevent_motion_darkening.setChecked(True)
        self.cb_prevent_motion_darkening.setToolTip("モーション再生時にビューポートのHDRポストプロセスを最適化し、アニメーション再生時でもモデルが暗く沈むのを防止します。シャッター開度を最小(0.01)に抑えるため、ボケやブレは発生しません。")
        light_layout.addWidget(self.cb_prevent_motion_darkening)

        self.cb_enable_toon = QCheckBox("Toonシェーディング（セル影）を適用する")
        self.cb_enable_toon.setChecked(True)
        self.cb_enable_toon.setToolTip("光の当たり具合に応じたセルアニメ調の影（Toon）を適用します。OFFにするとメッシュ本来の綺麗なテクスチャを維持します。")
        light_layout.addWidget(self.cb_enable_toon)

        h_ground_shadow = QHBoxLayout()
        self.cb_create_ground_shadow = QCheckBox("MMD標準地面影 (Ground Shadow) を作成する")
        self.cb_create_ground_shadow.setChecked(True)
        self.cb_create_ground_shadow.setToolTip("MMD同等の地面（Y=0平面）に落ちる半透明シャドウプレーンを作成し、足元の浮きを防ぎます。")
        h_ground_shadow.addWidget(self.cb_create_ground_shadow)

        self.btn_classifier_settings = QPushButton("モデル種別判定・個別指定設定...")
        self.btn_classifier_settings.setFixedHeight(36)
        self.btn_classifier_settings.setStyleSheet(
            "QPushButton { padding: 4px 14px; font-size: 12px; font-weight: bold; background-color: #2c3e50; color: #ecf0f1; border-radius: 4px; }"
            "QPushButton:hover { background-color: #34495e; }"
        )
        self.btn_classifier_settings.clicked.connect(self._open_classifier_settings)
        h_ground_shadow.addWidget(self.btn_classifier_settings)
        h_ground_shadow.addStretch()
        light_layout.addLayout(h_ground_shadow)

        # セルフ影モードラジオボタン
        self.shadow_btn_group = QButtonGroup(self)
        h_shadow = QHBoxLayout()
        h_shadow.setContentsMargins(20, 0, 0, 0)
        h_shadow.setSpacing(14)

        self.rb_shadow_none = QRadioButton("セルフ影なし")
        self.rb_shadow_none.setToolTip("前髪などの落とし影を生成せず、Toonの階調表現のみを適用します。")
        self.rb_shadow_mode1 = QRadioButton("モード1 (標準セルフ影)")
        self.rb_shadow_mode1.setToolTip("MMDのモード1相当。適度に柔らかな標準セルフシャドウを生成します。")
        self.rb_shadow_mode2 = QRadioButton("モード2 (高精細セルフ影)")
        self.rb_shadow_mode2.setToolTip("MMDのモード2相当。高解像度かつシャープな落とし影を生成します。")

        self.shadow_btn_group.addButton(self.rb_shadow_none, 0)
        self.shadow_btn_group.addButton(self.rb_shadow_mode1, 1)
        self.shadow_btn_group.addButton(self.rb_shadow_mode2, 2)
        self.rb_shadow_mode1.setChecked(True)

        h_shadow.addWidget(self.rb_shadow_none)
        h_shadow.addWidget(self.rb_shadow_mode1)
        h_shadow.addWidget(self.rb_shadow_mode2)
        h_shadow.addStretch()
        light_layout.addLayout(h_shadow)

        self.cb_enable_toon.toggled.connect(self._on_toon_toggled)

        # 既存シーンのToonシェーディング修復
        h_toon_fix = QHBoxLayout()
        self.btn_fix_toon = QPushButton("Toonシェーディング設定を変更")
        self.btn_fix_toon.setToolTip("現在開いているシーンのToonシェーダーのしきい値を調整し、現在選択中の影モードを適用します。")
        self.btn_fix_toon.clicked.connect(self._fix_toon_shading)
        h_toon_fix.addWidget(self.btn_fix_toon)
        h_toon_fix.addStretch()

        # MMD Viewport Renderer 切り替え設定
        h_renderer = QHBoxLayout()
        self.cb_switch_mmd_renderer = QCheckBox("インポート時に MMD Viewport Renderer に切り替える")
        self.cb_switch_mmd_renderer.setChecked(True)
        self.cb_switch_mmd_renderer.setToolTip("インポート終了後、ビューポートを MMD Viewport Renderer に自動切り替えし、美しい外周エッジ輪郭線と白背景を表示します。")
        h_renderer.addWidget(self.cb_switch_mmd_renderer)

        self.btn_toggle_renderer = QPushButton("Viewport 2.0 / MMD 切替")
        self.btn_toggle_renderer.setFixedHeight(36)
        self.btn_toggle_renderer.setStyleSheet(
            "QPushButton { padding: 4px 14px; font-size: 12px; font-weight: bold; background-color: #2c3e50; color: #ecf0f1; border-radius: 4px; }"
            "QPushButton:hover { background-color: #34495e; }"
        )
        self.btn_toggle_renderer.setToolTip("Viewport 2.0 と MMD Viewport Renderer を交互に切り替えます。")
        self.btn_toggle_renderer.clicked.connect(self._on_toggle_renderer_clicked)
        h_renderer.addWidget(self.btn_toggle_renderer)
        h_renderer.addStretch()
        light_layout.addLayout(h_renderer)



        light_layout.addLayout(h_toon_fix)

        layout.addWidget(light_box)

        layout.addStretch()

        # 実行アクション
        h_action = QHBoxLayout()
        self.cb_close_on_finish = QCheckBox("完了後にウィンドウを閉じる")
        h_action.addWidget(self.cb_close_on_finish)
        h_action.addStretch()

        self.btn_execute = QPushButton("モデルをインポート")
        self.btn_execute.setProperty("class", "primary")
        self.btn_execute.setFixedHeight(46)
        self.btn_execute.setMinimumWidth(180)
        self.btn_execute.clicked.connect(self._execute_import)
        h_action.addWidget(self.btn_execute)

        layout.addLayout(h_action)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

    def _load_settings(self):
        """前回のインポート設定を復元"""
        try:
            if os.path.exists(self.config_file):
                settings = {}
                ordered_lines = []
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line_str = line.strip()
                        if not line_str:
                            continue
                        if '=' in line_str:
                            k, v = line_str.split('=', 1)
                            settings[k.strip()] = v.strip()
                        ordered_lines.append(line_str)

                # キー照合、またはフォールバックとして順序照合
                file_path = settings.get("ファイルの名前", ordered_lines[0].split('=')[-1].strip() if len(ordered_lines) > 0 else "")
                scale = settings.get("尺度", ordered_lines[1].split('=')[-1].strip() if len(ordered_lines) > 1 else "8.0")
                split = int(settings.get("ポリゴンの分割", ordered_lines[2].split('=')[-1].strip() if len(ordered_lines) > 2 else 0))
                bs = int(settings.get("ブレンドシェープ", ordered_lines[3].split('=')[-1].strip() if len(ordered_lines) > 3 else 1))
                bones = int(settings.get("ジョイント", ordered_lines[4].split('=')[-1].strip() if len(ordered_lines) > 4 else 1))
                mat = int(settings.get("材質", ordered_lines[5].split('=')[-1].strip() if len(ordered_lines) > 5 else 6))
                close = int(settings.get("閉じる", ordered_lines[6].split('=')[-1].strip() if len(ordered_lines) > 6 else 0))
                light = int(settings.get("ライト", ordered_lines[7].split('=')[-1].strip() if len(ordered_lines) > 7 else 1))
                untone = int(settings.get("アントーンマップ", ordered_lines[8].split('=')[-1].strip() if len(ordered_lines) > 8 else 1))
                toon = int(settings.get("トゥーン", 1))
                physics = int(settings.get("剛体物理", 1))
                shadow_mode = int(settings.get("シャドウモード", 1))
                check_mb = int(settings.get("モーフボーンチェック", 1))
                prevent_darkening = int(settings.get("モーション暗化防止", 1))
                switch_renderer = int(settings.get("MMDレンダラー切替", settings.get("エッジメッシュ", 1)))

                self.le_file_path.setText(file_path)
                self.le_scale.setText(scale)
                self.cb_split_poly.setChecked(bool(split))
                self.cb_create_bs.setChecked(bool(bs))
                self.cb_create_bones.setChecked(bool(bones))
                self.cb_create_physics.setChecked(bool(physics))
                self.cb_switch_mmd_renderer.setChecked(bool(switch_renderer))
                self.cb_check_morph_bone.setChecked(bool(check_mb))
                idx = self.cbb_material.findData(mat)
                if idx >= 0:
                    self.cbb_material.setCurrentIndex(idx)
                elif mat in (5, 6):
                    # 過去の保存値（5: 旧MMD, 6: 新Toon）の場合は推奨シェーダーを選択
                    idx = self.cbb_material.findData(6)
                    if idx >= 0:
                        self.cbb_material.setCurrentIndex(idx)
                elif 0 <= mat < self.cbb_material.count():
                    self.cbb_material.setCurrentIndex(mat)
                self.cb_close_on_finish.setChecked(bool(close))
                self.cb_create_light.setChecked(bool(light))
                self.cb_untone_mapped.setChecked(bool(untone))
                self.cb_prevent_motion_darkening.setChecked(bool(prevent_darkening))
                self.cb_enable_toon.setChecked(bool(toon))
                if shadow_mode == 0:
                    self.rb_shadow_none.setChecked(True)
                elif shadow_mode == 2:
                    self.rb_shadow_mode2.setChecked(True)
                else:
                    self.rb_shadow_mode1.setChecked(True)
                self._on_toon_toggled(bool(toon))
                return
        except Exception:
            pass

        # デフォルト値
        self.le_scale.setText("8.0") # インポート時 スケールサイズ
        self.cb_create_bones.setChecked(True)
        self.cb_create_physics.setChecked(True)
        self.cb_create_bs.setChecked(True)
        self.cb_switch_mmd_renderer.setChecked(True)
        self.cb_check_morph_bone.setChecked(True)
        idx = self.cbb_material.findData(6)
        if idx >= 0:
            self.cbb_material.setCurrentIndex(idx)
        else:
            self.cbb_material.setCurrentIndex(self.cbb_material.count() - 1)
        self.cb_close_on_finish.setChecked(False)
        self.cb_create_light.setChecked(True)
        self.cb_untone_mapped.setChecked(True)
        self.cb_prevent_motion_darkening.setChecked(True)
        self.cb_enable_toon.setChecked(True)
        self.rb_shadow_mode1.setChecked(True)
        self._on_toon_toggled(True)

    def _save_settings(self):
        """現在の設定を保存"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(f"ファイルの名前 = {self.le_file_path.text()}\n")
                f.write(f"尺度 = {self.le_scale.text()}\n")
                f.write(f"ポリゴンの分割 = {int(self.cb_split_poly.isChecked())}\n")
                f.write(f"ブレンドシェープ = {int(self.cb_create_bs.isChecked())}\n")
                f.write(f"ジョイント = {int(self.cb_create_bones.isChecked())}\n")
                mat_id = self.cbb_material.currentData()
                f.write(f"材質 = {mat_id if mat_id is not None else 6}\n")
                f.write(f"閉じる = {int(self.cb_close_on_finish.isChecked())}\n")
                f.write(f"ライト = {int(self.cb_create_light.isChecked())}\n")
                f.write(f"アントーンマップ = {int(self.cb_untone_mapped.isChecked())}\n")
                f.write(f"モーション暗化防止 = {int(self.cb_prevent_motion_darkening.isChecked())}\n")
                f.write(f"トゥーン = {int(self.cb_enable_toon.isChecked())}\n")
                f.write(f"剛体物理 = {int(self.cb_create_physics.isChecked())}\n")
                f.write(f"MMDレンダラー切替 = {int(self.cb_switch_mmd_renderer.isChecked())}\n")
                f.write(f"シャドウモード = {self.get_shadow_mode()}\n")
                f.write(f"モーフボーンチェック = {int(self.cb_check_morph_bone.isChecked())}\n")
        except Exception:
            pass

    def _on_file_changed(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext == '.pmm' and os.path.exists(path):
            self.btn_execute.setEnabled(False)
            self._open_pmm_analysis_window()
            if hasattr(self, '_pmm_analysis_dialog') and self._pmm_analysis_dialog:
                self._pmm_analysis_dialog.le_pmm_path.setText(path)
                self._pmm_analysis_dialog._analyze_pmm_file(path)
            return

        valid = ext in ['.pmx', '.pmd', '.x'] and os.path.exists(path)
        self.btn_execute.setEnabled(valid)
        self._on_split_toggled()
        self._save_settings()

    def _clear_file(self):
        """モデルファイル入力欄をクリア"""
        self.le_file_path.clear()
        self._save_settings()

    def _on_split_toggled(self, checked=None):
        """材質分割チェック変更時の制限事項確認ダイアログおよび連動制御"""
        split = self.cb_split_poly.isChecked()

        # ユーザーが「材質ごとにメッシュを分割」にチェックを入れた場合の確認
        if split:
            dialog_msg = (
                "【材質分割インポートの制限事項】\n\n"
                "材質ごとにメッシュ（ポリゴン）を分割してインポートする場合、"
                "MMDモデルの構造上の理由により以下の制限が発生します：\n\n"
                "・スケルトン（ジョイント）は作成されません\n"
                "・剛体およびJointは作成されません\n"
                "・ブレンドシェイプ（モーフ）は作成されません\n"
                "・モーション（VMD）を適用・再生することはできなくなります\n\n"
                "材質ごとにメッシュを分割してインポートしますか？"
            )
            res = QMessageBox.warning(
                self,
                "材質分割インポートの確認",
                dialog_msg,
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel
            )

            if res != QMessageBox.Ok:
                # キャンセルされた場合はチェックをOFFに戻す
                self.cb_split_poly.blockSignals(True)
                self.cb_split_poly.setChecked(False)
                self.cb_split_poly.blockSignals(False)
                split = False

        ext = os.path.splitext(self.le_file_path.text())[1].lower()
        can_rig = (ext != '.x') and not split

        self.cb_create_bones.setEnabled(can_rig)
        self.cb_create_bs.setEnabled(can_rig)
        self.cb_create_physics.setEnabled(can_rig)

        if split:
            # 分割時は作成されない項目をOFFにする
            self.cb_create_bones.setChecked(False)
            self.cb_create_bs.setChecked(False)
            self.cb_create_physics.setChecked(False)
        else:
            # 分割解除時は標準の有効状態に戻す
            if can_rig:
                self.cb_create_bones.setChecked(True)
                self.cb_create_bs.setChecked(True)
                self.cb_create_physics.setChecked(True)
                self.cb_switch_mmd_renderer.setChecked(True)

    def _browse_file(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "MMDモデルファイルを選択",
            self.le_file_path.text(),
            "MMD Models (*.pmx *.pmd *.x);;PMX (*.pmx);;PMD (*.pmd);;DirectX (*.x)"
        )
        if path:
            self.le_file_path.setText(path)
            self._save_settings()

    def _open_multi_model_import_window(self):
        """複数モデル順次インポート用のダイアログを表示"""
        if not hasattr(self, '_multi_import_dialog') or self._multi_import_dialog is None:
            self._multi_import_dialog = MultiModelImportDialog(self)
        self._multi_import_dialog.show()
        self._multi_import_dialog.raise_()
        self._multi_import_dialog.activateWindow()

    def _open_pmm_analysis_window(self):
        """PMM 解析ダイアログを表示"""
        if not hasattr(self, '_pmm_analysis_dialog') or self._pmm_analysis_dialog is None:
            self._pmm_analysis_dialog = PmmAnalysisDialog(self)
        self._pmm_analysis_dialog.show()
        self._pmm_analysis_dialog.raise_()
        self._pmm_analysis_dialog.activateWindow()

    def _validate_scale(self, text):
        try:
            float(text)
        except ValueError:
            self.le_scale.setText("1.0")

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.le_file_path.setText(path)

    def _on_toon_toggled(self, checked):
        """ToonチェックボックスのON/OFFに応じて影モードのラジオボタンを有効/無効化"""
        self.rb_shadow_none.setEnabled(checked)
        self.rb_shadow_mode1.setEnabled(checked)
        self.rb_shadow_mode2.setEnabled(checked)

    def get_shadow_mode(self):
        """選択されているセルフ影モード (0: なし, 1: モード1, 2: モード2)"""
        return max(self.shadow_btn_group.checkedId(), 0)

    def _fix_toon_shading(self):
        """現在のMayaシーン内のToonシェーダーおよびセルフ影モードを修復・最適化"""
        try:
            shadow_mode = self.get_shadow_mode() if self.cb_enable_toon.isChecked() else 0
            fixed_count = pmxpaimaya.fix_toon_shading_in_scene(shadow_mode=shadow_mode)
            mode_names = ["セルフ影なし", "モード1 (標準セルフ影)", "モード2 (高精細セルフ影)"]
            mc.inViewMessage(amg=f'<span style="color:#2ecc71;">MMD Tools for Maya:</span> Toon設定完了（{mode_names[shadow_mode]}）。', pos='topCenter', fade=True)
            QMessageBox.information(
                self,
                "Toon設定完了",
                f"{fixed_count} 個の要素を設定しました。\n"
                f"影設定: {mode_names[shadow_mode]}\n"
            )
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"Toonシェーディング設定中にエラーが発生しました:\n{e}")

    def _on_toggle_renderer_clicked(self):
        """Viewport 2.0 と MMD Viewport Renderer を交互に切り替え"""
        is_now_mmd = toggle_viewport_renderer_override()
        mode_name = "MMD Viewport Renderer" if is_now_mmd else "Viewport 2.0"
        if mc:
            mc.inViewMessage(amg=f'<span style="color:#52b7ff;">レンダラー切替:</span> {mode_name} を適用しました。', pos='topCenter', fade=True)

    def _analyze_and_save_structure(self):
        """選択中モデルの材質、ボーン、モーフ、剛体、Jointを一括保存し、未登録ボーン辞書チェックを実行"""
        file_path = self.le_file_path.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "エラー", "有効なPMXモデルファイルを指定してください。")
            return

        if not file_path.lower().endswith('.pmx'):
            QMessageBox.information(self, "案内", "詳細解析および辞書照合はPMXモデル形式 (.pmx) のみ対応しています。")
            return

        try:
            # ユーザー辞書の未登録ボーン名チェック & 登録GUI
            if check_and_prompt_user_dict:
                check_and_prompt_user_dict(self.parent_window or self, file_path)

            # モデル構造の一括保存 (JSON)
            if export_pmx_structure:
                saved_path, data = export_pmx_structure(file_path)
                QMessageBox.information(
                    self,
                    "PMXモデル解析完了",
                    f"モデル構造の一括保存が完了しました！\n\n"
                    f"保存先:\n{saved_path}\n\n"
                    f"・材質: {len(data['materials'])} 件\n"
                    f"・ボーン: {len(data['bones'])} 件\n"
                    f"・モーフ: {len(data['morphs'])} 件\n"
                    f"・剛体: {len(data['rigid_bodies'])} 件\n"
                    f"・Joint: {len(data['joints'])} 件"
                )
        except Exception as e:
            QMessageBox.warning(self, "解析エラー", f"PMXモデルの解析中にエラーが発生しました:\n{e}")

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

    def _execute_import(self):
        file_path = self.le_file_path.text().strip()
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "エラー", "指定されたモデルファイルが存在しません。")
            return

        # 旧形式 PMD の検知と PMX 変換プロンプト
        if file_path.lower().endswith('.pmd'):
            reply = QMessageBox.question(
                self,
                "PMD形式の検出 (非推奨形式)",
                "旧形式の PMD モデルファイルが選択されています。\n"
                "現在、PMD形式は非推奨となっております。\n\n"
                "推奨される PMX 形式へ変換してインポートしますか？\n"
                "（「はい」をクリックすると変換が始まり、元の PMD と同一フォルダに変換した PMX が保存され、その PMX をインポートします）",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Cancel:
                print("[MMD Tools for Maya] インポートがキャンセルされました。")
                return
            elif reply == QMessageBox.Yes:
                print(f"[PMD変換] PMDからPMXへの自動変換を開始します: {os.path.basename(file_path)}")
                try:
                    try:
                        from ..converters.pmd2pmx import convert_pmd_to_pmx
                    except Exception:
                        from converters.pmd2pmx import convert_pmd_to_pmx

                    converted_pmx_path = convert_pmd_to_pmx(file_path)
                    print(f"[PMD変換] 変換が完了しました: {converted_pmx_path}")
                    # ファイルパス入力欄を更新し、以後のインポート対象を生成された PMX に切り替え
                    self.le_file_path.setText(converted_pmx_path)
                    file_path = converted_pmx_path
                    self._save_settings()
                except Exception as e:
                    QMessageBox.critical(self, "PMD変換エラー", f"PMXへの変換中にエラーが発生しました:\n{e}\n\n従来のPMDとしてインポートを試みます。")
                    print(f"[PMD変換エラー] {e}")

        check_morph_bone = self.cb_check_morph_bone.isChecked()
        try:
            scale = float(self.le_scale.text())
        except ValueError:
            scale = 1.0

        split_poly = self.cb_split_poly.isChecked()
        create_bs = not split_poly and self.cb_create_bs.isChecked()
        create_bones = not split_poly and self.cb_create_bones.isChecked()
        create_edge_mesh = False
        mat_id = self.cbb_material.currentData()
        material_type = mat_id if mat_id is not None else 6
        create_light = self.cb_create_light.isChecked()
        create_ground_shadow = self.cb_create_ground_shadow.isChecked()
        set_untone_mapped = self.cb_untone_mapped.isChecked()
        prevent_motion_darkening = self.cb_prevent_motion_darkening.isChecked()
        enable_toon = self.cb_enable_toon.isChecked()
        shadow_mode = self.get_shadow_mode() if enable_toon else 0

        create_physics = self.cb_create_physics.isChecked()

        # インポート開始直後に実行ログダイアログを生成・起動
        log_dialog = ExecutionLogDialog(self.parent_window or self, title="モデルインポート実行ログ")

        def full_import_task():
            total_start_time = time.time()

            # [PMXチェック] モーフ・ボーン名チェック & ユーザー辞書照合、構成要素データ保存
            if file_path.lower().endswith('.pmx'):
                print("==================================================")
                print(f"[PMXチェック] モデルファイル: {os.path.basename(file_path)}")
                if check_morph_bone:
                    print("  - モーフ・ボーン名チェック（辞書照合）: 実行中...")
                    if check_and_prompt_user_dict:
                        try:
                            check_and_prompt_user_dict(log_dialog, file_path)
                            print("  - モーフ・ボーン名チェック: 完了")
                        except Exception as e:
                            print(f"  - モーフ・ボーン名チェック: 完了 (警告: {e})")
                    else:
                        print("  - モーフ・ボーン名チェック: スキップ (モジュールなし)")
                else:
                    print("  - モーフ・ボーン名チェック: スキップ (設定OFF)")

                # 材質・ボーン・モーフ・剛体・Joint の一括保存
                if export_pmx_structure:
                    print("  - モデル構成要素（材質/ボーン/モーフ/剛体/Joint）データ保存: 実行中...")
                    try:
                        export_pmx_structure(file_path)
                        print("  - モデル構成要素データ保存: 完了")
                    except Exception as e:
                        print(f"  - モデル構成要素データ保存: 完了 (警告: {e})")
                print("==================================================")

            import importlib
            importlib.reload(pmxpaimaya)
            import_func = getattr(pmxpaimaya, 'import_pmx', pmxpaimaya.sang)
            res = import_func(
                file_path, scale, split_poly, create_bs, create_bones, material_type, create_light, set_untone_mapped, enable_toon, shadow_mode=shadow_mode, create_ground_shadow=create_ground_shadow, show_completion_message=False, prevent_motion_darkening=prevent_motion_darkening, create_physics=create_physics, create_edge_mesh=create_edge_mesh
            )

            # すべてのインポート工程（メッシュ・ボーン・剛体・Joint等）の終了直後に総括完了メッセージを表示
            total_elapsed = time.time() - total_start_time
            print("==================================================")
            print(f"モデルインポートが完了しました！ (所要時間: {total_elapsed:.2f}秒)")
            print("==================================================")
            return res

        # ログウィンドウを直ちに起動して全タスクを実行
        success = log_dialog.run_task(full_import_task)

        if success:
            # 物理演算タブおよびoptionVarへモデルパスを自動反映
            if file_path.lower().endswith('.pmx'):
                mc.optionVar(sv=("MMDToolsForMaya_LastPmxPath", file_path))
                if self.parent_window and hasattr(self.parent_window, 'tab_physics'):
                    try:
                        self.parent_window.tab_physics.le_pmx_path.setText(file_path)
                    except Exception:
                        pass

            if self.cb_switch_mmd_renderer.isChecked():
                set_viewport_renderer_override("mmdRenderOverride")
            mc.inViewMessage(amg='<span style="color:#52b7ff;">MMD Tools for Maya:</span> インポートが完了しました。', pos='topCenter', fade=True)
            self._save_settings()

            if self.cb_close_on_finish.isChecked() and self.parent_window:
                self.parent_window.close()

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
