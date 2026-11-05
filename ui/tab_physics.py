# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 物理演算ベイクタブおよび物理演算ベイクGUIタブ
"""

from .common import *
from .multi_model_dialog import MultiModelPhysicsBakeDialog
try:
    from .dialog_physics_model_select import PhysicsModelSelectDialog
except Exception:
    try:
        from dialog_physics_model_select import PhysicsModelSelectDialog
    except Exception:
        PhysicsModelSelectDialog = None

# ==============================================================================
# 物理演算 (XPBD) タブ
# ==============================================================================
class PhysicsTabWidget(QWidget):
    """自前C++ XPBD物理エンジンによるシミュレーションおよびベイクUI"""
    def __init__(self, parent=None):
        super(PhysicsTabWidget, self).__init__(parent)
        self.parent_window = parent
        self.setAcceptDrops(True)
        self._selected_model_nodes = None
        self.bridge = None
        self._selected_model_nodes = None
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

        # 内部互換用PMXパス保持（UI表示は行わず適用対象モデルから自動取得）


        self.le_pmx_path = QLineEdit()


        last_pmx = mc.optionVar(q="MMDToolsForMaya_LastPmxPath") if (mc and mc.optionVar(exists="MMDToolsForMaya_LastPmxPath")) else ""


        if last_pmx and os.path.exists(last_pmx):


            self.le_pmx_path.setText(last_pmx)


        self.le_pmx_path.textChanged.connect(self._on_pmx_changed)

        # 適用対象モデル指定
        model_box = QGroupBox("適用対象モデル (物理演算を行うモデルを指定)")
        model_layout = QVBoxLayout(model_box)
        h_model_btn = QHBoxLayout()
        self.btn_select_models = QPushButton("適用対象モデルの選択 (チェックリスト)...")
        self.btn_select_models.setFixedHeight(36)
        self.btn_select_models.setStyleSheet(
            "QPushButton { background-color: #2c3e50; color: #ecf0f1; font-weight: bold; font-size: 12px; border-radius: 4px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #34495e; }"
        )
        self.btn_select_models.setToolTip("シーン内のスカイドーム・ステージ・キャラクターから、物理演算を行うモデルをチェックリスト形式で指定します。")
        self.btn_select_models.clicked.connect(self._open_model_select_dialog)
        h_model_btn.addWidget(self.btn_select_models)



        self.btn_refresh_models = QPushButton("更新")
        self.btn_refresh_models.setFixedWidth(70)
        self.btn_refresh_models.setFixedHeight(36)
        self.btn_refresh_models.clicked.connect(self._refresh_target_models)
        h_model_btn.addWidget(self.btn_refresh_models)
        model_layout.addLayout(h_model_btn)

        self.lbl_selected_models_summary = QLabel("選択中: 自動検出中...")
        self.lbl_selected_models_summary.setStyleSheet("color: #2ecc71; font-weight: bold; margin-top: 2px;")
        model_layout.addWidget(self.lbl_selected_models_summary)
        layout.addWidget(model_box)

        # 物理シミュレーション設定
        param_box = QGroupBox("物理演算パラメータ (XPBD / Bullet 共通)")
        param_layout = QVBoxLayout(param_box)

        # Bullet エンジンバージョン選択 (本家MMD採用 2.75 vs 改良 2.83.7)
        h_bullet_ver = QHBoxLayout()
        h_bullet_ver.addWidget(QLabel("Bullet エンジン:"))
        self.rb_bullet_275 = QRadioButton("Bullet 2.75 (本家MMD採用・挙動再現重視)")
        self.rb_bullet_283 = QRadioButton("Bullet 2.83.7 (後発・改良バージョン・安定性重視)")

        saved_ver = "2.75"
        if mc.optionVar(exists="MMDToolsForMaya_BulletVersion"):
            saved_ver = str(mc.optionVar(q="MMDToolsForMaya_BulletVersion"))
        if "2.83" in saved_ver:
            self.rb_bullet_283.setChecked(True)
        else:
            self.rb_bullet_275.setChecked(True)

        self.rb_bullet_275.toggled.connect(self._on_bullet_version_toggled)
        self.rb_bullet_283.toggled.connect(self._on_bullet_version_toggled)

        self.bg_bullet_ver = QButtonGroup(self)
        self.bg_bullet_ver.addButton(self.rb_bullet_275)
        self.bg_bullet_ver.addButton(self.rb_bullet_283)

        h_bullet_ver.addWidget(self.rb_bullet_275)
        h_bullet_ver.addWidget(self.rb_bullet_283)
        h_bullet_ver.addStretch()
        param_layout.addLayout(h_bullet_ver)

        # 動作モード選択 (ダンスモーションモード vs 簡易モード)
        h_mode = QHBoxLayout()
        h_mode.addWidget(QLabel("物理演算モード:"))
        self.rb_mode_dance = QRadioButton("ダンスモーションモード (高精度・しなやか)")
        self.rb_mode_simple = QRadioButton("簡易モード (ベイク速さ重視)")
        self.rb_mode_dance.setChecked(True)
        self.rb_mode_dance.toggled.connect(self._on_physics_mode_toggled)

        self.bg_physics_mode = QButtonGroup(self)
        self.bg_physics_mode.addButton(self.rb_mode_dance)
        self.bg_physics_mode.addButton(self.rb_mode_simple)

        h_mode.addWidget(self.rb_mode_dance)
        h_mode.addWidget(self.rb_mode_simple)
        h_mode.addStretch()
        param_layout.addLayout(h_mode)

        # 重力設定 (MMD本家仕様: 加速度 9.80)
        h_grav = QHBoxLayout()
        h_grav.addWidget(QLabel("重力加速度 (Y):"))
        self.le_gravity = QLineEdit("-9.80")
        self.le_gravity.setFixedWidth(75)
        self.le_gravity.setToolTip(
            "MMD重力加速度 (下向き: -9.80)\n"
            "・MMD標準地球重力 (1.0G): -9.80 (通常・ダンス推奨)\n"
            "・ふんわり軽め (0.5G): -4.90 (スカートがふわっと浮き上がる)\n"
            "・重め (1.5G): -14.70 (素早く下へ落ち着かせる)\n"
            "・無重力 (0.0G): 0.0"
        )
        h_grav.addWidget(self.le_gravity)
        lbl_grav_hint = QLabel("(MMD標準 1.0G: -9.80 ／ ふんわり: -4.90 ／ 重め: -14.70)")
        lbl_grav_hint.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        h_grav.addWidget(lbl_grav_hint)
        h_grav.addStretch()
        param_layout.addLayout(h_grav)

        # サブステップ数
        h_sub = QHBoxLayout()
        h_sub.addWidget(QLabel("サブステップ数:"))
        self.le_substeps = QLineEdit("30")
        self.le_substeps.setFixedWidth(75)
        self.le_substeps.setToolTip(
            "1フレームあたりの物理計算分割数。\n"
            "・ダンスモーションモード: 30 (激しいステップやターンでも剛体・Jointが破綻せずしなやか)\n"
            "・簡易モード: 10～15 (ベイク速さ重視)\n"
            "※数値を高くするほど剛体の貫通や伸びが抑制され安定しますが、計算時間が増加します。"
        )
        h_sub.addWidget(self.le_substeps)
        lbl_sub_hint = QLabel("(ダンス推奨: 30 ／ 簡易速さ重視: 10～15)")
        lbl_sub_hint.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        h_sub.addWidget(lbl_sub_hint)
        h_sub.addStretch()
        param_layout.addLayout(h_sub)

        # スケール倍率
        h_scale = QHBoxLayout()
        h_scale.addWidget(QLabel("スケール倍率:"))
        self.le_scale = QLineEdit("8.0")
        self.le_scale.setFixedWidth(80)
        h_scale.addWidget(self.le_scale)
        h_scale.addWidget(QLabel("(インポート時と同一の倍率)"))
        h_scale.addStretch()
        param_layout.addLayout(h_scale)

        # フレーム範囲 (ラジオボタン選択 & 一段下げレイアウト)
        h_frame_mode = QHBoxLayout()
        h_frame_mode.addWidget(QLabel("シミュレーション範囲:"))
        self.rb_auto_frame = QRadioButton("タイムラインすべて")
        self.rb_auto_frame.setChecked(True)
        self.rb_custom_frame = QRadioButton("フレーム指定")
        self.rb_auto_frame.toggled.connect(self._on_frame_mode_toggled)

        self.bg_frame_mode = QButtonGroup(self)
        self.bg_frame_mode.addButton(self.rb_auto_frame)
        self.bg_frame_mode.addButton(self.rb_custom_frame)

        h_frame_mode.addWidget(self.rb_auto_frame)
        h_frame_mode.addWidget(self.rb_custom_frame)
        h_frame_mode.addStretch()
        param_layout.addLayout(h_frame_mode)

        # 一段下げたフレーム数値入力レイアウト
        h_custom_frame = QHBoxLayout()
        h_custom_frame.setContentsMargins(24, 0, 0, 0)
        h_custom_frame.addWidget(QLabel("開始フレーム:"))
        self.le_start_frame = QLineEdit()
        self.le_start_frame.setFixedWidth(70)
        self.le_start_frame.setEnabled(False)
        h_custom_frame.addWidget(self.le_start_frame)

        h_custom_frame.addWidget(QLabel("終了フレーム:"))
        self.le_end_frame = QLineEdit()
        self.le_end_frame.setFixedWidth(70)
        self.le_end_frame.setEnabled(False)
        h_custom_frame.addWidget(self.le_end_frame)
        h_custom_frame.addStretch()
        param_layout.addLayout(h_custom_frame)

        # ベイク終了後の補助ノード非表示設定
        self.cb_hide_helpers = QCheckBox("物理ベイク終了後に補助ノード (Apose_view_cnt / Apose_subetenoya / *_master / 剛体・ジョイント可視化メッシュ) を非表示にする")
        hide_default = True
        if mc.optionVar(exists="MMDToolsForMaya_HideHelpersAfterBake"):
            hide_default = bool(mc.optionVar(q="MMDToolsForMaya_HideHelpersAfterBake"))
        self.cb_hide_helpers.setChecked(hide_default)
        self.cb_hide_helpers.toggled.connect(self._on_hide_helpers_toggled)
        param_layout.addWidget(self.cb_hide_helpers)

        # 床判定（Y=0 地面衝突）
        self.cb_enable_floor = QCheckBox("床判定 (地面無限平面 Y=0) を有効化する ※ひもやスカートの床下沈み込みを防止")
        self.cb_enable_floor.setChecked(True)
        param_layout.addWidget(self.cb_enable_floor)
        layout.addWidget(param_box)
        layout.addStretch()

        # 実行ボタンエリア
        v_action = QVBoxLayout()

        # 中段: 従来の物理ベイク実行ボタン (Bullet と XPBD を横並び)
        h_bake_action = QHBoxLayout()

        self.btn_bullet_bake = QPushButton("Bullet 物理ベイク実行 (MMD本家仕様)")
        self.btn_bullet_bake.setFixedHeight(40)
        self.btn_bullet_bake.setStyleSheet("QPushButton { background-color: #2e6b9e; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3b88c7; } QPushButton:disabled { background-color: #444; color: #888; }")
        self.btn_bullet_bake.clicked.connect(self._execute_bullet_bake)
        h_bake_action.addWidget(self.btn_bullet_bake)

        self.btn_bake = QPushButton("XPBD 物理ベイク実行(ベータ版)")
        self.btn_bake.setProperty("class", "primary")
        self.btn_bake.setFixedHeight(40)
        self.btn_bake.clicked.connect(self._execute_bake)
        h_bake_action.addWidget(self.btn_bake)

        v_action.addLayout(h_bake_action)

        # 下段: ユーティリティ操作 (可視化生成、再吸着、キーフレームクリアを横並び)
        h_sub_action = QHBoxLayout()

        self.btn_create_vis = QPushButton("剛体・Joint可視化を生成")
        self.btn_create_vis.setFixedHeight(40)
        self.btn_create_vis.clicked.connect(self._execute_create_visualizers)
        h_sub_action.addWidget(self.btn_create_vis)

        self.btn_reconnect = QPushButton("剛体・Jointをモデルに再吸着")
        self.btn_reconnect.setFixedHeight(40)
        self.btn_reconnect.clicked.connect(self._execute_reconnect)
        h_sub_action.addWidget(self.btn_reconnect)

        self.btn_clear_keys = QPushButton("物理キーフレームをクリア")
        self.btn_clear_keys.setFixedHeight(40)
        self.btn_clear_keys.clicked.connect(self._execute_clear_keys)
        h_sub_action.addWidget(self.btn_clear_keys)

        v_action.addLayout(h_sub_action)
        layout.addLayout(v_action)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        self._refresh_bullet_status()

    def _check_motion_plugin_status(self):
        """mmd_motion.mll プラグインのロード状況を確認しラベルを更新"""
        loaded = False
        try:
            if hasattr(mc, "mmdFastBakeBone"):
                loaded = True
            elif hasattr(mel, "eval") and mel.eval('exists "mmdFastBakeBone"') == 1:
                loaded = True
            elif any("mmd_motion" in p.lower() for p in (mc.pluginInfo(query=True, listPlugins=True) or [])):
                loaded = True
            elif mc.pluginInfo("mmd_motion.mll", query=True, loaded=True) or mc.pluginInfo("mmd_motion", query=True, loaded=True):
                loaded = True
        except Exception:
            pass

        motion_autoload = False
        if loaded:
            try:
                motion_autoload = mc.pluginInfo("mmd_motion.mll", query=True, autoload=True) or mc.pluginInfo("mmd_motion", query=True, autoload=True)
            except Exception:
                motion_autoload = False
            if not motion_autoload:
                try:
                    mc.pluginInfo("mmd_motion.mll", edit=True, autoload=True)
                    motion_autoload = True
                except Exception:
                    try:
                        mc.pluginInfo("mmd_motion", edit=True, autoload=True)
                        motion_autoload = True
                    except Exception:
                        pass

        if loaded:
            auto_str = " (自動ロード: 有効)" if motion_autoload else ""
            self.lbl_motion_plugin_status.setText(f"<span style='color:#55ff77; font-weight:bold;'>● プラグイン読み込み済み (mmd_motion.mll{auto_str})</span>")
        else:
            self.lbl_motion_plugin_status.setText("<span style='color:#ff7777; font-weight:bold;'>○ プラグイン未読み込み (mmd_motion.mll)</span>")

    def _reload_motion_plugin(self):
        """mmd_motion.mll プラグインを強制リロード"""
        try:
            try:
                from ..bullet_engine import bullet_maya_bridge
            except Exception:
                from bullet_engine import bullet_maya_bridge
            bridge = bullet_maya_bridge.BulletMayaBridge.__new__(bullet_maya_bridge.BulletMayaBridge)
            success = bridge._ensure_motion_plugin_loaded()
            if success:
                try:
                    mc.pluginInfo("mmd_motion", edit=True, autoload=True)
                except Exception:
                    pass
                try:
                    mc.pluginInfo("mmd_motion.mll", edit=True, autoload=True)
                except Exception:
                    pass
            self._check_motion_plugin_status()
            if success:
                QMessageBox.information(self, "プラグイン", "MMDモーションプラグイン (mmd_motion.mll) が正常にロードされ、自動ロードが設定されました。")
            else:
                QMessageBox.warning(self, "プラグイン", "MMDモーションプラグイン (mmd_motion.mll) のロードに失敗しました。")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"プラグインのロード中にエラーが発生しました: {e}")

    def _is_bullet_available(self):
        """Bullet物理モジュール (bullet_engine) が存在し利用可能か判定"""
        try:
            plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            bullet_dir = os.path.join(plugin_root, "bullet_engine")
            bin_dir = os.path.join(bullet_dir, "bin")
            dll_275 = os.path.join(bin_dir, "mmd_bullet_275.dll")
            dll_283 = os.path.join(bin_dir, "mmd_bullet_283.dll")
            dll_common = os.path.join(bin_dir, "mmd_bullet.dll")
            has_dll = os.path.exists(dll_275) or os.path.exists(dll_283) or os.path.exists(dll_common)
            bridge_path = os.path.join(bullet_dir, "bullet_maya_bridge.py")
            return has_dll and os.path.exists(bridge_path)
        except Exception:
            return False

    def _refresh_bullet_status(self):
        """Bulletボタンの活性化状態を更新 (フォルダ削除時は自動無効化)"""
        available = self._is_bullet_available()
        self.btn_bullet_bake.setEnabled(available)
        if available:
            ver = "2.83.7 (改良版)" if hasattr(self, 'rb_bullet_283') and self.rb_bullet_283.isChecked() else "2.75 (本家MMD仕様)"
            self.btn_bullet_bake.setToolTip(f"Bullet Physics {ver} により、柔らかくしなやかな髪やスカートの物理をベイクします。")
        else:
            self.btn_bullet_bake.setToolTip("Bullet物理モジュール (bullet_engine) は削除または未導入です。\n下の「XPBD 物理ベイク実行」をご利用ください。")

    def _on_bullet_version_toggled(self, checked):
        """Bulletバージョン切り替え時の設定保存"""
        ver = "2.83.7" if self.rb_bullet_283.isChecked() else "2.75"
        mc.optionVar(sv=("MMDToolsForMaya_BulletVersion", ver))
        self._refresh_bullet_status()

    def _on_physics_mode_toggled(self, checked):
        """ダンスモーションモードと簡易モードの切り替え"""
        if self.rb_mode_dance.isChecked():
            self.le_substeps.setText("30")
        else:
            self.le_substeps.setText("10")

    def _get_effective_pmx_path(self):
        """適用対象モデルまたはシーン内モデルからPMXファイルパスを自動取得"""
        target_nodes = self._selected_model_nodes
        if not target_nodes:
            try:
                from ..converters import vmdpaimaya
                models = vmdpaimaya.get_available_mmd_models()
                target_nodes = [node for node, _ in models]
            except Exception:
                try:
                    from converters import vmdpaimaya
                    models = vmdpaimaya.get_available_mmd_models()
                    target_nodes = [node for node, _ in models]
                except Exception:
                    target_nodes = []

        if target_nodes:
            for node in target_nodes:
                if mc and mc.objExists(node):
                    if mc.attributeQuery('mmdModelPath', node=node, exists=True):
                        p = mc.getAttr(f"{node}.mmdModelPath")
                        if p and os.path.exists(p):
                            return p
                    meshes = mc.listRelatives(node, allDescendents=True, type="mesh") or []
                    for m in meshes:
                        if mc.attributeQuery('mmdModelPath', node=m, exists=True):
                            p = mc.getAttr(f"{m}.mmdModelPath")
                            if p and os.path.exists(p):
                                return p

        last_pmx = mc.optionVar(q="MMDToolsForMaya_LastPmxPath") if (mc and mc.optionVar(exists="MMDToolsForMaya_LastPmxPath")) else ""
        if last_pmx and os.path.exists(last_pmx):
            return last_pmx

        if hasattr(self, 'le_pmx_path'):
            p = self.le_pmx_path.text().strip()
            if p and os.path.exists(p):
                return p

        return ""

    def _open_model_select_dialog(self):
        """物理演算適用対象モデル選択ダイアログを表示"""
        if PhysicsModelSelectDialog is None:
            QMessageBox.warning(self, "エラー", "モデル選択ダイアログモジュールを読み込めませんでした。")
            return

        dlg = PhysicsModelSelectDialog(
            parent=self.parent_window or self,
            initial_selected_nodes=self._selected_model_nodes,
            default_pmx_path=self._get_effective_pmx_path()
        )
        if dlg.exec_():
            self._selected_model_nodes = dlg.get_selected_nodes()
            self._update_selected_models_summary()

    def _update_selected_models_summary(self):
        """選択されているモデルのサマリー表示を更新"""
        if not hasattr(self, 'lbl_selected_models_summary'):
            return

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

        total = len(models)
        if total == 0:
            self.lbl_selected_models_summary.setText("未検出: シーン内にMMDモデルが見つかりません")
            self.lbl_selected_models_summary.setStyleSheet("color: #e74c3c; font-weight: bold;")
            return

        if self._selected_model_nodes is None:
            self.lbl_selected_models_summary.setText(f"すべてのモデルが対象: {total} 体のモデルを検出 (自動設定)")
            self.lbl_selected_models_summary.setStyleSheet("color: #52b7ff; font-weight: bold;")
        else:
            selected_set = set(self._selected_model_nodes)
            matched = [lbl for node, lbl in models if node in selected_set]
            cnt = len(matched)
            if cnt == 0:
                self.lbl_selected_models_summary.setText(f"選択中: 0 / {total} 体 (ベイク対象なし)")
                self.lbl_selected_models_summary.setStyleSheet("color: #e67e22; font-weight: bold;")
            else:
                names_summary = ", ".join(matched[:2])
                if cnt > 2:
                    names_summary += f" 他{cnt - 2}体"
                self.lbl_selected_models_summary.setText(f"選択中: {cnt} / {total} 体 ({names_summary})")
                self.lbl_selected_models_summary.setStyleSheet("color: #2ecc71; font-weight: bold;")

    def _refresh_target_models(self):
        """シーン内の対象MMDモデル一覧および選択状態サマリーを更新"""
        self._update_selected_models_summary()
        return
        if not hasattr(self, 'cbb_target_model'):
            return
        self.cbb_target_model.clear()
        self.cbb_target_model.addItem("自動検出 (シーン内のMMDモデル)", "")
        try:
            from ..converters import vmdpaimaya
        except Exception:
            try:
                from converters import vmdpaimaya
            except Exception:
                import vmdpaimaya
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for node, label in models:
                self.cbb_target_model.addItem(label, node)
        except Exception:
            pass

    def showEvent(self, event):
        super(PhysicsTabWidget, self).showEvent(event)
        self._refresh_target_models()
        # タブ表示時に最新のモデルパスが未入力であれば自動反映
        if not self.le_pmx_path.text().strip():
            last_pmx = mc.optionVar(q="MMDToolsForMaya_LastPmxPath") if mc.optionVar(exists="MMDToolsForMaya_LastPmxPath") else ""
            if last_pmx and os.path.exists(last_pmx):
                self.le_pmx_path.setText(last_pmx)

    def _on_frame_mode_toggled(self, checked):
        is_custom = self.rb_custom_frame.isChecked()
        self.le_start_frame.setEnabled(is_custom)
        self.le_end_frame.setEnabled(is_custom)

    def _on_pmx_changed(self, text=""):
        path = self.le_pmx_path.text().strip()
        valid = path.lower().endswith('.pmx') and os.path.exists(path)
        mc.optionVar(sv=("MMDToolsForMaya_LastPmxPath", path if valid else ""))

    def _clear_pmx_file(self):
        """PMXモデルファイル入力欄をクリア"""
        self.le_pmx_path.clear()
        mc.optionVar(sv=("MMDToolsForMaya_LastPmxPath", ""))

    def _browse_pmx(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "PMXモデルファイルを選択",
            self.le_pmx_path.text(),
            "PMX Files (*.pmx);;All Files (*.*)"
        )
        if path:
            self.le_pmx_path.setText(path)
            mc.optionVar(sv=("MMDToolsForMaya_LastPmxPath", path))

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith('.pmx'):
                self.le_pmx_path.setText(path)
                mc.optionVar(sv=("MMDToolsForMaya_LastPmxPath", path))

    def _on_hide_helpers_toggled(self, checked):
        mc.optionVar(iv=("MMDToolsForMaya_HideHelpersAfterBake", int(checked)))

    def _hide_helper_nodes_if_needed(self):
        """物理ベイク終了後に補助ノード（カメラビューコントローラ、subetenoya、*_master、剛体・ジョイント可視化メッシュ等）を非表示化"""
        if not self.cb_hide_helpers.isChecked():
            return

        target_names = ["Apose_view_cnt", "Apose_subetenoya", "MMD_RigidBody_Joint_Visualizers"]
        for name in target_names:
            if mc.objExists(name):
                try:
                    mc.setAttr(f"{name}.visibility", False)
                except Exception:
                    pass

        # 剛体・ジョイント可視化グループのワイルドカード非表示
        for pat in ["*_RigidBody_Joint_Visualizers*", "*_RigidBody_Visualizers*", "*_Joint_Visualizers*"]:
            for v_node in mc.ls(pat, type=["transform", "joint"]) or []:
                try:
                    mc.setAttr(f"{v_node}.visibility", False)
                except Exception:
                    pass

        # ワイルドカード検索でマッチする補助ノード（カメラ、subetenoya、*_master）も非表示化
        # ライトやカメラ関連ノードを誤って非表示に巻き込まないよう保護
        for pattern in ["*view_cnt*", "*subetenoya*", "*_master*"]:
            matched = mc.ls(pattern, type=["transform", "joint"]) or []
            for m in matched:
                m_lower = m.lower()
                if any(ex in m_lower for ex in ["light", "camera", "aim"]):
                    continue
                try:
                    mc.setAttr(f"{m}.visibility", False)
                except Exception:
                    pass

        # ビューポートライティングを確実に復元
        restore_viewport_lighting()
    def _execute_bullet_bake(self):
        """Bullet Physics (MMD本家仕様) による物理ベイク実行"""
        if not self._is_bullet_available():
            QMessageBox.information(
                self, "案内",
                "Bullet物理モジュール (bullet_engine) は削除または未導入です。\n"
                "「XPBD 物理ベイク実行」をご利用ください。"
            )
            return

        pmx_path = self._get_effective_pmx_path()
        if not pmx_path or not os.path.exists(pmx_path):
            QMessageBox.warning(self, "エラー", "有効なPMXモデルファイルを指定してください。")
            return

        try:
            scale = float(self.le_scale.text())
            gravity = float(self.le_gravity.text())
            substeps = int(self.le_substeps.text())
        except ValueError:
            QMessageBox.warning(self, "エラー", "パラメータの数値が正しくありません。")
            return

        if self.rb_auto_frame.isChecked():
            start_frame = int(mc.playbackOptions(query=True, minTime=True))
            end_frame = int(mc.playbackOptions(query=True, maxTime=True))
        else:
            try:
                start_frame = int(self.le_start_frame.text())
                end_frame = int(self.le_end_frame.text())
                # 開始・最終フレームが入力されている場合はタイムライン範囲を指定値に更新
                mc.playbackOptions(minTime=start_frame, maxTime=end_frame, animationStartTime=start_frame, animationEndTime=end_frame)
            except ValueError:
                QMessageBox.warning(self, "エラー", "開始・終了フレーム番号を正しく入力してください。")
                return

        enable_floor = self.cb_enable_floor.isChecked()
        fps = 30.0
        physics_mode = "dance" if self.rb_mode_dance.isChecked() else "simple"
        target_mode = ""
        bullet_ver = "2.83.7" if self.rb_bullet_283.isChecked() else "2.75"

        try:
            from ..bullet_engine import bullet_maya_bridge
        except Exception:
            from bullet_engine import bullet_maya_bridge

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

        # 複数モデル順次ベイクの自動判定 (自動検出時に複数モデルが存在する場合)
        # 適用対象モデルの取得
        if self._selected_model_nodes is None:
            models_to_bake = models
        else:
            selected_set = set(self._selected_model_nodes)
            models_to_bake = [(node, label) for node, label in models if node in selected_set]

        if not models_to_bake:
            QMessageBox.warning(
                self, "警告",
                "ベイク対象のモデルが選択されていません。\n"
                "「適用対象モデルの選択 (チェックリスト)...」からベイクするモデルにチェックを入れてください。"
            )
            return

        # 複数モデル順次ベイクの判定
        if len(models_to_bake) > 1:
            log_dialog = ExecutionLogDialog(
                self.parent_window or self,
                title="Bullet 複数モデル順次物理ベイク実行ログ (追突防止・個別実行)",
                show_cancel=True
            )

            def run_multi_bullet_task():
                total = len(models_to_bake)
                log_dialog.append_log("--- Bullet 複数モデル順次物理ベイク開始 ---\n")
                log_dialog.append_log(f"使用Bulletエンジン: Bullet {bullet_ver}\n")
                log_dialog.append_log(f"対象モデル: {total} 体が選択されています。\n")
                log_dialog.append_log("剛体の追突や反発・吹き飛びを防ぐため、1体ずつ順番に独立してベイクします。\n\n")

                for idx, (m_node, m_label) in enumerate(models_to_bake, start=1):
                    if log_dialog.check_cancelled():
                        log_dialog.append_log("\n[中断] ユーザーによりベイクが中断されました。\n")
                        break

                    log_dialog.append_log("==================================================\n")
                    log_dialog.append_log(f"[{idx}/{total}] モデル物理ベイク開始: {m_label}\n")
                    log_dialog.append_log("==================================================\n")

                    # モデル固有のPMXパスを取得 (保存されている場合は優先)
                    model_pmx = pmx_path
                    if mc.attributeQuery('mmdModelPath', node=m_node, exists=True):
                        saved_path = mc.getAttr(f"{m_node}.mmdModelPath")
                        if saved_path and os.path.exists(saved_path):
                            model_pmx = saved_path

                    bridge = bullet_maya_bridge.BulletMayaBridge(pmx_path=model_pmx, scale=scale, target_model=m_node, bullet_version=bullet_ver)

                    def make_progress_cb(m_idx):
                        def _progress_cb(*args, **kwargs):
                            if len(args) >= 4:
                                cur_f, end_f, cur_step, tot_step = args[:4]
                                step_ratio = float(cur_step) / max(1.0, float(tot_step))
                                overall_p = int(((m_idx - 1) + step_ratio) / total * 100)
                                log_dialog.update_progress(
                                    overall_p,
                                    label_prefix=f"[{m_idx}/{total}]",
                                    unit=f"フレーム {cur_f} / {end_f}"
                                )
                            elif len(args) == 2:
                                p, msg = args
                                overall_p = int(((m_idx - 1) + (float(p) / 100.0)) / total * 100)
                                log_dialog.update_progress(overall_p, label_prefix=f"[{m_idx}/{total}]", unit=str(msg))
                            elif len(args) == 1:
                                p = args[0]
                                overall_p = int(((m_idx - 1) + (float(p) / 100.0)) / total * 100)
                                log_dialog.update_progress(overall_p)
                        return _progress_cb

                    bridge.bake_simulation(
                        start_frame=start_frame,
                        end_frame=end_frame,
                        sub_steps=substeps,
                        enable_floor=enable_floor,
                        gravity_y=gravity,
                        fps=fps,
                        physics_mode=physics_mode,
                        progress_callback=make_progress_cb(idx),
                        cancel_callback=log_dialog.check_cancelled
                    )
                    log_dialog.append_log(f"[{idx}/{total}] 終了: {m_label}\n\n")

                log_dialog.update_progress(100, 100)
                log_dialog.append_log("すべてのモデルの物理ベイクが終了しました\n")
                restore_viewport_lighting()

            success = log_dialog.run_task(run_multi_bullet_task)
        else:
            # 単一モデル時のPMXパスおよび対象モデルの解決
            single_pmx = pmx_path
            single_target, single_label = models_to_bake[0]


            if single_target and mc.attributeQuery('mmdModelPath', node=single_target, exists=True):
                saved_path = mc.getAttr(f"{single_target}.mmdModelPath")
                if saved_path and os.path.exists(saved_path):
                    single_pmx = saved_path

            log_dialog = ExecutionLogDialog(self.parent_window or self, title="Bullet 物理演算ベイク実行ログ (MMD本家仕様)", show_cancel=True)

            def run_bullet_task():
                log_dialog.append_log(f"使用Bulletエンジン: Bullet {bullet_ver}\n")
                log_dialog.append_log(f"対象モデル: {single_label}\n")
                bridge = bullet_maya_bridge.BulletMayaBridge(pmx_path=single_pmx, scale=scale, target_model=single_target, bullet_version=bullet_ver)
                bridge.bake_simulation(
                    start_frame=start_frame,
                    end_frame=end_frame,
                    sub_steps=substeps,
                    enable_floor=enable_floor,
                    gravity_y=gravity,
                    fps=fps,
                    physics_mode=physics_mode,
                    progress_callback=log_dialog.update_progress,
                    cancel_callback=log_dialog.check_cancelled
                )
                restore_viewport_lighting()

            success = log_dialog.run_task(run_bullet_task)
        if success:
            self._hide_helper_nodes_if_needed()
            if log_dialog.is_cancelled:
                mc.inViewMessage(
                    amg='<span style="color:#ffaa55;">MMD Tools for Maya:</span> Bullet物理ベイクがユーザーにより中断されました。',
                    pos='topCenter',
                    fade=True
                )
            else:
                mc.inViewMessage(
                    amg='<span style="color:#2ecc71;">MMD Tools for Maya:</span> Bullet物理シミュレーションのベイクが終了しました。',
                    pos='topCenter',
                    fade=True
                )

    def _execute_bake(self):
        pmx_path = self._get_effective_pmx_path()
        if not pmx_path or not os.path.exists(pmx_path):
            QMessageBox.warning(self, "エラー", "有効なPMXモデルファイルが指定されていません。")
            return

        try:
            scale = float(self.le_scale.text())
            gravity = float(self.le_gravity.text())
            substeps = int(self.le_substeps.text())
        except ValueError:
            QMessageBox.warning(self, "エラー", "パラメータの数値が正しくありません。")
            return

        if self.rb_auto_frame.isChecked():
            start_frame = int(mc.playbackOptions(query=True, minTime=True))
            end_frame = int(mc.playbackOptions(query=True, maxTime=True))
        else:
            try:
                start_frame = int(self.le_start_frame.text())
                end_frame = int(self.le_end_frame.text())
                # 開始・最終フレームが入力されている場合はタイムライン範囲を指定値に更新
                mc.playbackOptions(minTime=start_frame, maxTime=end_frame, animationStartTime=start_frame, animationEndTime=end_frame)
            except ValueError:
                QMessageBox.warning(self, "エラー", "開始・終了フレーム番号を正しく入力してください。")
                return

        fps = 30.0
        physics_mode = "dance" if self.rb_mode_dance.isChecked() else "simple"

        log_dialog = ExecutionLogDialog(self.parent_window or self, title="XPBD 物理演算ベイク実行ログ", show_cancel=True)

        def run_physics_task():
            try:
                from ..cpp_engine import xpbd_maya_bridge
            except Exception:
                from cpp_engine import xpbd_maya_bridge
            self.bridge = xpbd_maya_bridge.XpbdMayaBridge(scale=scale)
            ok = self.bridge.initialize_from_pmx(pmx_path)
            if not ok:
                raise RuntimeError("PMX剛体データの読み込みに失敗しました。")
            self.bridge.bake_simulation(
                start_frame=start_frame,
                end_frame=end_frame,
                gravity_y=gravity,
                substeps=substeps,
                fps=fps,
                physics_mode=physics_mode,
                progress_callback=log_dialog.update_progress,
                cancel_callback=log_dialog.check_cancelled
            )

        success = log_dialog.run_task(run_physics_task)
        if success:
            self._hide_helper_nodes_if_needed()
            if log_dialog.is_cancelled:
                mc.inViewMessage(
                    amg='<span style="color:#ffaa55;">MMD Tools for Maya:</span> XPBD物理ベイクがユーザーにより中断されました。',
                    pos='topCenter',
                    fade=True
                )
            else:
                mc.inViewMessage(
                    amg='<span style="color:#2ecc71;">MMD Tools for Maya:</span> XPBD物理シミュレーションのベイクが終了しました。',
                    pos='topCenter',
                    fade=True
                )

    def _execute_clear_keys(self):
        pmx_path = self._get_effective_pmx_path()
        if not pmx_path or not os.path.exists(pmx_path):
            QMessageBox.warning(self, "エラー", "有効なPMXモデルファイルを指定してください。")
            return

        try:
            try:
                from ..cpp_engine import xpbd_maya_bridge
            except Exception:
                from cpp_engine import xpbd_maya_bridge
            bridge = xpbd_maya_bridge.XpbdMayaBridge()
            if bridge.initialize_from_pmx(pmx_path):
                bridge.clear_physics_keyframes()
                mc.inViewMessage(
                    amg='<span style="color:#ffaa55;">MMD Tools for Maya:</span> 物理キーフレームをクリアしました。',
                    pos='topCenter',
                    fade=True
                )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"キーフレーム削除中にエラーが発生しました:\n{e}")

    def _execute_reconnect(self):
        try:
            try:
                from ..converters import reconnect_visualizers_to_bones
            except Exception:
                from converters import reconnect_visualizers_to_bones
            ok = reconnect_visualizers_to_bones()
            if ok:
                mc.inViewMessage(
                    amg='<span style="color:#2ecc71;">MMD Tools for Maya:</span> 剛体とJointをモデルボーンに再吸着しました。',
                    pos='topCenter',
                    fade=True
                )
            else:
                QMessageBox.information(self, "情報", "シーン内に剛体・Joint可視化ノードが存在しません。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"再吸着処理中にエラーが発生しました:\n{e}")

    def _execute_create_visualizers(self):
        pmx_path = self._get_effective_pmx_path()
        if not pmx_path or not os.path.exists(pmx_path):
            QMessageBox.warning(self, "エラー", "有効なPMXモデルファイルを指定してください。")
            return

        try:
            scale = float(self.le_scale.text())
        except ValueError:
            scale = 8.0

        try:
            try:
                from ..converters import create_rigidbody_visualizers
            except Exception:
                from converters import create_rigidbody_visualizers
            create_rigidbody_visualizers(pmx_path, scale=scale)
            mc.inViewMessage(
                amg='<span style="color:#2ecc71;">MMD Tools for Maya:</span> 剛体とJointの可視化を生成しました。',
                pos='topCenter',
                fade=True
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"可視化生成中にエラーが発生しました:\n{e}")

# ==============================================================================
# 物理演算GUI タブ（外部物理エンジン連携・キーフレームベイク）
# ==============================================================================
class PhysicsGuiTabWidget(QWidget):
    """外部物理演算エンジンとのデータ連携（モーション書き出し＆キーフレームベイク）を行うUIタブ"""
    def __init__(self, parent=None):
        super(PhysicsGuiTabWidget, self).__init__(parent)
        self.parent_window = parent
        self.setAcceptDrops(True)
        self._selected_model_nodes = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # シーン内インポート状態確認
        status_box = QGroupBox("シーン読み込み状態の確認")
        status_layout = QVBoxLayout(status_box)

        h_status_row = QHBoxLayout()
        h_status_row.setContentsMargins(6, 4, 6, 4)
        h_status_row.setSpacing(12)
        v_status_labels = QVBoxLayout()
        self.lbl_scene_pmx_status = QLabel("PMXモデル: 確認中...")
        self.lbl_scene_pmx_status.setStyleSheet("font-weight: bold;")
        self.lbl_scene_motion_status = QLabel("モーション: 確認中...")
        self.lbl_scene_motion_status.setStyleSheet("font-weight: bold;")
        v_status_labels.addWidget(self.lbl_scene_pmx_status)
        v_status_labels.addWidget(self.lbl_scene_motion_status)
        h_status_row.addLayout(v_status_labels)

        h_status_row.addStretch()
        self.btn_refresh_scene_status = QPushButton("状態を再確認")
        self.btn_refresh_scene_status.setFixedWidth(120)
        self.btn_refresh_scene_status.setFixedHeight(34)
        self.btn_refresh_scene_status.setStyleSheet("padding: 4px 8px; font-weight: bold;")
        self.btn_refresh_scene_status.clicked.connect(self._check_scene_import_status)
        h_status_row.addWidget(self.btn_refresh_scene_status)
        status_layout.addLayout(h_status_row)
        content_layout.addWidget(status_box)

        # 内部互換用PMXパス保持（UI表示は行わず適用対象モデルから自動取得）
        self.le_pmx_path = QLineEdit()
        last_pmx = mc.optionVar(q="MMDToolsForMaya_LastPmxPath") if (mc and mc.optionVar(exists="MMDToolsForMaya_LastPmxPath")) else ""
        if last_pmx and os.path.exists(last_pmx):
            self.le_pmx_path.setText(last_pmx)
        self.le_pmx_path.textChanged.connect(self._on_pmx_changed)

        # 適用対象モデル指定（シーン読み込み状態の直下に配置）
        model_box = QGroupBox("適用対象モデルの選択")
        model_layout = QVBoxLayout(model_box)

        h_model_btn = QHBoxLayout()
        self.btn_stream_select_models = QPushButton("適用対象モデルの選択 (チェックリスト)...")
        self.btn_stream_select_models.setFixedHeight(36)
        self.btn_stream_select_models.setStyleSheet(
            "QPushButton { background-color: #2c3e50; color: #ecf0f1; font-weight: bold; font-size: 12px; border-radius: 4px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #34495e; }"
        )
        self.btn_stream_select_models.setToolTip("シーン内のスカイドーム・ステージ・キャラクターから、物理演算を行うモデルをチェックリスト形式で指定します。")
        self.btn_stream_select_models.clicked.connect(self._open_stream_model_select_dialog)
        h_model_btn.addWidget(self.btn_stream_select_models)

        self.btn_stream_refresh_models = QPushButton("更新")
        self.btn_stream_refresh_models.setFixedWidth(70)
        self.btn_stream_refresh_models.setFixedHeight(36)
        self.btn_stream_refresh_models.clicked.connect(self._refresh_stream_target_models)
        h_model_btn.addWidget(self.btn_stream_refresh_models)

        self.btn_open_multi_bake = QPushButton("ベイクするモデルの確認...")
        self.btn_open_multi_bake.setFixedHeight(36)
        self.btn_open_multi_bake.clicked.connect(self._open_multi_stream_bake_dialog)
        h_model_btn.addWidget(self.btn_open_multi_bake)

        model_layout.addLayout(h_model_btn)

        self.lbl_stream_selected_models_summary = QLabel("選択中: 自動検出中...")
        self.lbl_stream_selected_models_summary.setStyleSheet("color: #2ecc71; font-weight: bold; margin-top: 2px;")
        model_layout.addWidget(self.lbl_stream_selected_models_summary)
        content_layout.addWidget(model_box)

        # VMDモーション情報（適用対象モデルの直下に配置）
        vmd_src_box = QGroupBox("VMDモーション情報")
        vmd_src_layout = QVBoxLayout(vmd_src_box)

        h_vmd_src = QHBoxLayout()
        h_vmd_src.addWidget(QLabel("VMDモーション:"))
        self.le_vmd_source_path = QLineEdit()
        self.le_vmd_source_path.setPlaceholderText("ベイク元となるVMDモーションファイルパスを指定")
        last_vmd = mc.optionVar(q="MMDToolsForMaya_LastModelVmdPath") if (mc and mc.optionVar(exists="MMDToolsForMaya_LastModelVmdPath")) else ""
        if last_vmd and os.path.exists(last_vmd):
            self.le_vmd_source_path.setText(last_vmd)
        self.le_vmd_source_path.textChanged.connect(self._on_vmd_changed)
        h_vmd_src.addWidget(self.le_vmd_source_path)

        self.btn_browse_vmd_source = QPushButton("参照...")
        self.btn_browse_vmd_source.setFixedWidth(75)
        self.btn_browse_vmd_source.clicked.connect(self._browse_source_vmd)
        h_vmd_src.addWidget(self.btn_browse_vmd_source)

        self.btn_sync_vmd_motion = QPushButton("モーションタブから取得")
        self.btn_sync_vmd_motion.clicked.connect(lambda: self._sync_vmd_from_motion_tab(silent=False))
        h_vmd_src.addWidget(self.btn_sync_vmd_motion)

        vmd_src_layout.addLayout(h_vmd_src)

        lbl_pmm_vmd_hint = QLabel("※pmmからインポートした場合は自動で設定されます。")
        lbl_pmm_vmd_hint.setStyleSheet("color: #888888; font-size: 11px; margin-top: 2px;")
        vmd_src_layout.addWidget(lbl_pmm_vmd_hint)

        content_layout.addWidget(vmd_src_box)

        # リアルタイム物理ベイク設定・実行
        stream_bake_box = QGroupBox("リアルタイム物理ベイク (高速・確実)")
        stream_bake_layout = QVBoxLayout(stream_bake_box)

        # Bullet エンジンバージョン選択 (本家MMD採用 2.75 vs 改良 2.83.7)
        h_stream_bullet_ver = QHBoxLayout()
        h_stream_bullet_ver.addWidget(QLabel("Bullet エンジン:"))
        self.rb_stream_bullet_275 = QRadioButton("Bullet 2.75 (本家MMD採用・挙動再現重視)")
        self.rb_stream_bullet_283 = QRadioButton("Bullet 2.83.7 (後発・改良バージョン・安定性重視)")

        saved_stream_ver = "2.75"
        if mc.optionVar(exists="MMDToolsForMaya_StreamBulletVersion"):
            saved_stream_ver = str(mc.optionVar(q="MMDToolsForMaya_StreamBulletVersion"))
        elif mc.optionVar(exists="MMDToolsForMaya_BulletVersion"):
            saved_stream_ver = str(mc.optionVar(q="MMDToolsForMaya_BulletVersion"))

        if "2.83" in saved_stream_ver:
            self.rb_stream_bullet_283.setChecked(True)
        else:
            self.rb_stream_bullet_275.setChecked(True)

        self.rb_stream_bullet_275.toggled.connect(self._on_stream_bullet_version_toggled)
        self.rb_stream_bullet_283.toggled.connect(self._on_stream_bullet_version_toggled)

        self.bg_stream_bullet_ver = QButtonGroup(self)
        self.bg_stream_bullet_ver.addButton(self.rb_stream_bullet_275)
        self.bg_stream_bullet_ver.addButton(self.rb_stream_bullet_283)

        h_stream_bullet_ver.addWidget(self.rb_stream_bullet_275)
        h_stream_bullet_ver.addWidget(self.rb_stream_bullet_283)
        h_stream_bullet_ver.addStretch()
        stream_bake_layout.addLayout(h_stream_bullet_ver)

        # VMDファイル出力オプション
        vmd_out_box = QGroupBox("物理ベイク済みモーションの書き出し設定")
        vmd_out_layout = QVBoxLayout(vmd_out_box)

        h_vmd_out_choice = QHBoxLayout()
        self.rb_vmd_out_enable = QRadioButton("VMDファイルを出力する")
        self.rb_vmd_out_disable = QRadioButton("VMDファイルを出力しない (Mayaへの直接ベイクのみ)")
        self.rb_vmd_out_disable.setChecked(True)
        self.rb_vmd_out_enable.toggled.connect(self._on_vmd_output_toggled)

        self.bg_vmd_output = QButtonGroup(self)
        self.bg_vmd_output.addButton(self.rb_vmd_out_enable)
        self.bg_vmd_output.addButton(self.rb_vmd_out_disable)

        h_vmd_out_choice.addWidget(self.rb_vmd_out_enable)
        h_vmd_out_choice.addWidget(self.rb_vmd_out_disable)
        h_vmd_out_choice.addStretch()
        vmd_out_layout.addLayout(h_vmd_out_choice)

        h_vmd_out_path = QHBoxLayout()
        h_vmd_out_path.addWidget(QLabel("保存先:"))
        self.le_vmd_output_path = QLineEdit()
        self.le_vmd_output_path.setPlaceholderText("出力先VMDファイルパス")
        self.le_vmd_output_path.setEnabled(False)
        h_vmd_out_path.addWidget(self.le_vmd_output_path)

        self.btn_browse_vmd_output = QPushButton("参照...")
        self.btn_browse_vmd_output.setFixedWidth(75)
        self.btn_browse_vmd_output.setEnabled(False)
        self.btn_browse_vmd_output.clicked.connect(self._browse_vmd_output)
        h_vmd_out_path.addWidget(self.btn_browse_vmd_output)
        vmd_out_layout.addLayout(h_vmd_out_path)

        stream_bake_layout.addWidget(vmd_out_box)

        # シミュレーション範囲設定 (ラジオボタン選択 & 入力欄)
        h_stream_frame_mode = QHBoxLayout()
        h_stream_frame_mode.addWidget(QLabel("シミュレーション範囲:"))
        self.rb_stream_auto_frame = QRadioButton("タイムラインすべて (自動)")
        self.rb_stream_auto_frame.setChecked(True)
        self.rb_stream_custom_frame = QRadioButton("フレーム指定")
        self.rb_stream_auto_frame.toggled.connect(self._on_stream_frame_mode_toggled)

        self.bg_stream_frame_mode = QButtonGroup(self)
        self.bg_stream_frame_mode.addButton(self.rb_stream_auto_frame)
        self.bg_stream_frame_mode.addButton(self.rb_stream_custom_frame)

        h_stream_frame_mode.addWidget(self.rb_stream_auto_frame)
        h_stream_frame_mode.addWidget(self.rb_stream_custom_frame)
        h_stream_frame_mode.addStretch()
        stream_bake_layout.addLayout(h_stream_frame_mode)

        # 一段下げたフレーム数値入力レイアウト
        h_stream_custom_frame = QHBoxLayout()
        h_stream_custom_frame.setContentsMargins(24, 0, 0, 0)
        h_stream_custom_frame.addWidget(QLabel("開始フレーム:"))
        self.le_stream_start_frame = QLineEdit()
        self.le_stream_start_frame.setFixedWidth(70)
        self.le_stream_start_frame.setEnabled(False)
        h_stream_custom_frame.addWidget(self.le_stream_start_frame)

        h_stream_custom_frame.addWidget(QLabel("終了フレーム:"))
        self.le_stream_end_frame = QLineEdit()
        self.le_stream_end_frame.setFixedWidth(70)
        self.le_stream_end_frame.setEnabled(False)
        h_stream_custom_frame.addWidget(self.le_stream_end_frame)
        h_stream_custom_frame.addStretch()
        stream_bake_layout.addLayout(h_stream_custom_frame)

        # タイムライン初期値を設定
        try:
            min_t = int(mc.playbackOptions(query=True, minTime=True))
            max_t = int(mc.playbackOptions(query=True, maxTime=True))
            self.le_stream_start_frame.setText(str(min_t))
            self.le_stream_end_frame.setText(str(max_t))
        except Exception:
            self.le_stream_start_frame.setText("0")
            self.le_stream_end_frame.setText("100")

        # 物理パラメータ設定 (上段: 先行フレーム数・安定化時間)
        h_stream_params_top = QHBoxLayout()
        h_stream_params_top.addWidget(QLabel("先行フレーム数:"))
        init_lookahead = mc.optionVar(q="MMDToolsForMaya_StreamLookahead") if mc.optionVar(exists="MMDToolsForMaya_StreamLookahead") else "16"
        self.le_stream_lookahead = QLineEdit(str(init_lookahead))
        self.le_stream_lookahead.setFixedWidth(70)
        self.le_stream_lookahead.setToolTip("ビューアが先行して物理計算を行うフレーム数です (ACK同期用)。")
        self.le_stream_lookahead.textChanged.connect(lambda val: mc.optionVar(sv=("MMDToolsForMaya_StreamLookahead", val.strip())))
        h_stream_params_top.addWidget(self.le_stream_lookahead)

        h_stream_params_top.addWidget(QLabel("安定化時間(秒):"))
        init_warmup = mc.optionVar(q="MMDToolsForMaya_StreamWarmup") if mc.optionVar(exists="MMDToolsForMaya_StreamWarmup") else "0.0"
        self.le_stream_warmup = QLineEdit(str(init_warmup))
        self.le_stream_warmup.setFixedWidth(70)
        self.le_stream_warmup.setToolTip("ベイク開始前にフレーム0の姿勢で物理演算を先行実行し、スカートや髪の垂れ下がりを落ち着かせる時間(秒)です。タイミングの一致を優先する場合は0.0秒を設定します。")
        self.le_stream_warmup.textChanged.connect(lambda val: mc.optionVar(sv=("MMDToolsForMaya_StreamWarmup", val.strip())))
        h_stream_params_top.addWidget(self.le_stream_warmup)
        h_stream_params_top.addStretch()
        stream_bake_layout.addLayout(h_stream_params_top)

        # 物理パラメータ設定 (下段: オフセット・スケール倍率・精度)
        h_stream_params_bottom = QHBoxLayout()
        h_stream_params_bottom.addWidget(QLabel("オフセット:"))
        init_offset = mc.optionVar(q="MMDToolsForMaya_StreamOffset") if mc.optionVar(exists="MMDToolsForMaya_StreamOffset") else "0"
        self.le_stream_offset = QLineEdit(str(init_offset))
        self.le_stream_offset.setFixedWidth(70)
        self.le_stream_offset.setToolTip("身体モーションや楽曲に対して物理ベイクの開始フレームを前後にずらす値です (例: -60 または 60)。")
        self.le_stream_offset.textChanged.connect(lambda val: mc.optionVar(sv=("MMDToolsForMaya_StreamOffset", val.strip())))
        h_stream_params_bottom.addWidget(self.le_stream_offset)

        h_stream_params_bottom.addWidget(QLabel("スケール倍率:"))
        init_scale = mc.optionVar(q="MMDToolsForMaya_StreamScale") if mc.optionVar(exists="MMDToolsForMaya_StreamScale") else "8.0"
        self.le_stream_scale = QLineEdit(str(init_scale))
        self.le_stream_scale.setFixedWidth(70)
        h_stream_params_bottom.addWidget(self.le_stream_scale)

        h_stream_params_bottom.addWidget(QLabel("精度 (貫通防止):"))
        self.cbb_stream_substep = QComboBox()
        self.cbb_stream_substep.addItem("高精度 (120Hz・貫通防止推奨)", 120)
        self.cbb_stream_substep.addItem("超高精度 (240Hz・激しいダンス用)", 240)
        self.cbb_stream_substep.addItem("標準 (60Hz)", 60)
        init_substep = int(mc.optionVar(q="MMDToolsForMaya_StreamSubstep")) if mc.optionVar(exists="MMDToolsForMaya_StreamSubstep") else 120
        idx = self.cbb_stream_substep.findData(init_substep)
        if idx >= 0:
            self.cbb_stream_substep.setCurrentIndex(idx)
        self.cbb_stream_substep.currentIndexChanged.connect(
            lambda _: mc.optionVar(iv=("MMDToolsForMaya_StreamSubstep", self.cbb_stream_substep.currentData() or 120))
        )
        self.cbb_stream_substep.setToolTip("物理シミュレーションの内部計算周波数を指定します。120Hz以上に設定することで足やスカートの剛体貫通を大幅に防止します。")
        h_stream_params_bottom.addWidget(self.cbb_stream_substep)
        h_stream_params_bottom.addStretch()
        stream_bake_layout.addLayout(h_stream_params_bottom)

        # ベイク終了後の補助ノード非表示設定
        self.cb_stream_hide_helpers = QCheckBox("物理ベイク終了後に補助ノード (Apose_view_cnt / Apose_subetenoya / *_master / 剛体・ジョイント可視化メッシュ) を非表示にする")
        self.cb_stream_hide_helpers.setChecked(True)
        stream_bake_layout.addWidget(self.cb_stream_hide_helpers)

        self.btn_stream_bake = QPushButton("リアルタイム物理ベイク実行")
        self.btn_stream_bake.setFixedHeight(44)
        self.btn_stream_bake.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: #fff; font-size: 13px; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3498db; }"
        )
        self.btn_stream_bake.setToolTip("新3D物理ビューアを起動し、揺れものボーン（スカート・髪等）の計算結果をリアルタイムにMayaへ同期・ベイクします。")
        self.btn_stream_bake.clicked.connect(self._run_realtime_stream_bake)
        stream_bake_layout.addWidget(self.btn_stream_bake)

        content_layout.addWidget(stream_bake_box)

        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # 対象モデル一覧および状態の初期設定
        self._refresh_stream_target_models()
        self._update_default_vmd_output_path()
        self._on_vmd_output_toggled(False)
        self._check_scene_import_status()

    def _get_default_vmd_output_dir(self):
        """プラグイン内の asset/userdata/vmd_bake_data フォルダパスを取得し、自動作成"""
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bake_dir = os.path.join(plugin_root, "asset", "userdata", "vmd_bake_data")
        try:
            os.makedirs(bake_dir, exist_ok=True)
        except Exception:
            pass
        return bake_dir

    def _update_default_vmd_output_path(self):
        """モデル名またはVMD名に基づいてデフォルトの出力先パスを設定"""
        bake_dir = self._get_default_vmd_output_dir()
        base_name = "physics_baked"
        pmx_path = self._get_effective_pmx_path()
        vmd_path = self.le_vmd_source_path.text().strip()
        if vmd_path:
            base_name = os.path.splitext(os.path.basename(vmd_path))[0] + "_physics_baked"
        elif pmx_path:
            base_name = os.path.splitext(os.path.basename(pmx_path))[0] + "_physics_baked"
        self.le_vmd_output_path.setText(os.path.join(bake_dir, f"{base_name}.vmd").replace("\\", "/"))

    def _on_pmx_changed(self, text=""):
        """PMXファイルパス変更時の連動処理"""
        self._update_default_vmd_output_path()
        self._check_scene_import_status()

    def _on_vmd_changed(self, text=""):
        """VMDファイルパス変更時の連動処理"""
        self._update_default_vmd_output_path()
        self._check_scene_import_status()

    def _on_vmd_output_toggled(self, checked):
        """VMD出力ラジオボタンの切り替え"""
        self.le_vmd_output_path.setEnabled(checked)
        self.btn_browse_vmd_output.setEnabled(checked)

    def _browse_vmd_output(self):
        """VMD保存先ファイル選択ダイアログ"""
        current_path = self.le_vmd_output_path.text().strip()
        start_dir = os.path.dirname(current_path) if current_path else self._get_default_vmd_output_dir()
        path, _ = QFileDialog.getSaveFileName(
            self, "物理ベイクVMDファイルの保存先を指定", current_path or start_dir, "VMDファイル (*.vmd);;すべてのファイル (*.*)"
        )
        if path:
            self.le_vmd_output_path.setText(path.replace("\\", "/"))

    def _check_scene_import_status(self):
        """シーン内のPMXモデルおよびモーションのインポート状態を確認"""
        # PMXモデル確認
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

        if models:
            model_names = [m[1] for m in models]
            self.lbl_scene_pmx_status.setText(f"✔ PMXモデル: インポート済み ({len(models)} 体検出: {model_names[0]})")
            self.lbl_scene_pmx_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            joints = mc.ls(type="joint") or []
            if joints:
                self.lbl_scene_pmx_status.setText(f"✔ PMXモデル: ジョイント検出済み (計 {len(joints)} 本)")
                self.lbl_scene_pmx_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
            else:
                self.lbl_scene_pmx_status.setText("✖ PMXモデル: 未インポート (「MMD → Maya」タブからインポートしてください)")
                self.lbl_scene_pmx_status.setStyleSheet("color: #e67e22; font-weight: bold;")

        # モーション確認
        anim_curves = mc.ls(type=["animCurveTA", "animCurveTL", "animCurveTT", "animCurveTU"]) or []
        if anim_curves:
            try:
                min_t = mc.playbackOptions(query=True, minTime=True)
                max_t = mc.playbackOptions(query=True, maxTime=True)
                self.lbl_scene_motion_status.setText(f"✔ モーション: インポート済み (タイムライン: {int(min_t)} ～ {int(max_t)} フレーム)")
                self.lbl_scene_motion_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
            except Exception:
                self.lbl_scene_motion_status.setText(f"✔ モーション: キーフレーム検出済み ({len(anim_curves)} カーブ)")
                self.lbl_scene_motion_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            self.lbl_scene_motion_status.setText("✖ モーション: 未インポート (「モーション(VMD)」タブからインポートしてください)")
            self.lbl_scene_motion_status.setStyleSheet("color: #e67e22; font-weight: bold;")

    def _get_effective_pmx_path(self):
        """適用対象モデルまたはシーン内モデルからPMXファイルパスを自動取得"""
        target_nodes = self._selected_model_nodes
        if not target_nodes:
            try:
                from ..converters import vmdpaimaya
                models = vmdpaimaya.get_available_mmd_models()
                target_nodes = [node for node, _ in models]
            except Exception:
                try:
                    from converters import vmdpaimaya
                    models = vmdpaimaya.get_available_mmd_models()
                    target_nodes = [node for node, _ in models]
                except Exception:
                    target_nodes = []

        if target_nodes:
            for node in target_nodes:
                if mc and mc.objExists(node):
                    if mc.attributeQuery('mmdModelPath', node=node, exists=True):
                        p = mc.getAttr(f"{node}.mmdModelPath")
                        if p and os.path.exists(p):
                            return p
                    meshes = mc.listRelatives(node, allDescendents=True, type="mesh") or []
                    for m in meshes:
                        if mc.attributeQuery('mmdModelPath', node=m, exists=True):
                            p = mc.getAttr(f"{m}.mmdModelPath")
                            if p and os.path.exists(p):
                                return p

        last_pmx = mc.optionVar(q="MMDToolsForMaya_LastPmxPath") if (mc and mc.optionVar(exists="MMDToolsForMaya_LastPmxPath")) else ""
        if last_pmx and os.path.exists(last_pmx):
            return last_pmx

        if hasattr(self, 'le_pmx_path'):
            p = self.le_pmx_path.text().strip()
            if p and os.path.exists(p):
                return p

        return ""

    def _open_stream_model_select_dialog(self):
        """リアルタイム物理ベイク用の対象モデル選択ダイアログを表示"""
        if PhysicsModelSelectDialog is None:
            QMessageBox.warning(self, "エラー", "モデル選択ダイアログモジュールを読み込めませんでした。")
            return

        dlg = PhysicsModelSelectDialog(
            parent=self.parent_window or self,
            initial_selected_nodes=self._selected_model_nodes,
            default_pmx_path=self._get_effective_pmx_path()
        )
        if dlg.exec_():
            self._selected_model_nodes = dlg.get_selected_nodes()
            self._update_stream_selected_models_summary()

    def _update_stream_selected_models_summary(self):
        """リアルタイム物理ベイク用の選択サマリーを更新"""
        if not hasattr(self, 'lbl_stream_selected_models_summary'):
            return

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

        total = len(models)
        if total == 0:
            self.lbl_stream_selected_models_summary.setText("未検出: シーン内にMMDモデルが見つかりません")
            self.lbl_stream_selected_models_summary.setStyleSheet("color: #e74c3c; font-weight: bold;")
            return

        if self._selected_model_nodes is None:
            self.lbl_stream_selected_models_summary.setText(f"すべてのモデルが対象: {total} 体のモデルを検出 (自動設定)")
            self.lbl_stream_selected_models_summary.setStyleSheet("color: #52b7ff; font-weight: bold;")
        else:
            selected_set = set(self._selected_model_nodes)
            matched = [lbl for node, lbl in models if node in selected_set]
            cnt = len(matched)
            if cnt == 0:
                self.lbl_stream_selected_models_summary.setText(f"選択中: 0 / {total} 体 (ベイク対象なし)")
                self.lbl_stream_selected_models_summary.setStyleSheet("color: #e67e22; font-weight: bold;")
            else:
                names_summary = ", ".join(matched[:2])
                if cnt > 2:
                    names_summary += f" 他{cnt - 2}体"
                excluded = total - cnt
                ex_text = f" ／ 対象外: {excluded} 体" if excluded > 0 else ""
                self.lbl_stream_selected_models_summary.setText(f"選択中: {cnt} / {total} 体 ({names_summary}){ex_text}")
                self.lbl_stream_selected_models_summary.setStyleSheet("color: #2ecc71; font-weight: bold;")

    def _open_multi_stream_bake_dialog(self):
        """複数モデル順次物理ベイクダイアログを表示"""
        if not hasattr(self, '_multi_bake_dialog') or self._multi_bake_dialog is None:
            self._multi_bake_dialog = MultiModelPhysicsBakeDialog(self)
        self._multi_bake_dialog._refresh_models_from_scene()
        self._multi_bake_dialog.show()
        self._multi_bake_dialog.raise_()
        self._multi_bake_dialog.activateWindow()

    def _refresh_stream_target_models(self):
        """リアルタイム物理ベイク用の対象MMDモデル一覧および選択サマリーを更新"""
        self._update_stream_selected_models_summary()
        return
        self.cbb_stream_target_model.clear()
        self.cbb_stream_target_model.addItem("自動検出 (シーン内のMMDモデル)", "")
        try:
            from ..converters import vmdpaimaya
        except Exception:
            try:
                from converters import vmdpaimaya
            except Exception:
                import vmdpaimaya
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for node, label in models:
                self.cbb_stream_target_model.addItem(label, node)
        except Exception:
            pass

    def _sync_pmx_from_import_tab(self, silent=False):
        """インポートタブから現在設定されているPMXパスを取得"""
        path = ""
        if self.parent_window and hasattr(self.parent_window, "tab_import"):
            path = self.parent_window.tab_import.le_file_path.text().strip()
        if not path and mc.optionVar(exists="MMDToolsForMaya_LastPmxPath"):
            path = mc.optionVar(q="MMDToolsForMaya_LastPmxPath")
        if path:
            if self.le_pmx_path.text().strip() != path:
                self.le_pmx_path.setText(path)
                self._update_default_paths(path)
                self._update_default_vmd_output_path()
            if not silent:
                mc.inViewMessage(
                    amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> PMXパスを取得しました: {os.path.basename(path)}',
                    pos='topCenter',
                    fade=True
                )
        elif not silent:
            QMessageBox.information(self, "情報", "インポートタブにPMXパスが設定されていません。")

    def _sync_vmd_from_motion_tab(self, silent=False):
        """モーションタブから現在設定されているVMDパスを取得"""
        path = ""
        if self.parent_window and hasattr(self.parent_window, "tab_vmd"):
            path = self.parent_window.tab_vmd.le_file_path.text().strip()
        if not path and mc.optionVar(exists="MMDToolsForMaya_LastModelVmdPath"):
            path = mc.optionVar(q="MMDToolsForMaya_LastModelVmdPath")
        if path:
            if self.le_vmd_source_path.text().strip() != path:
                self.le_vmd_source_path.setText(path)
                self._update_default_vmd_output_path()
            if not silent:
                mc.inViewMessage(
                    amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> VMDモーションパスを取得しました: {os.path.basename(path)}',
                    pos='topCenter',
                    fade=True
                )
        elif not silent:
            QMessageBox.information(self, "情報", "モーションタブにVMDパスが設定されていません。")

    def refresh_all_tab_info(self):
        """タブ選択時にシーン読み込み状態、PMXモデル情報、VMDモーション情報を即時更新"""
        self._check_scene_import_status()
        self._sync_pmx_from_import_tab(silent=True)
        self._sync_vmd_from_motion_tab(silent=True)
        self._refresh_stream_target_models()

    def _browse_source_vmd(self):
        """ベイク元VMDファイル選択ダイアログ"""
        path, _ = QFileDialog.getOpenFileName(
            self, "ベイク元VMDモーションファイルを選択", self.le_vmd_source_path.text(), "VMDファイル (*.vmd);;すべてのファイル (*.*)"
        )
        if path:
            self.le_vmd_source_path.setText(path.replace("\\", "/"))
            self._update_default_vmd_output_path()

    def _on_stream_frame_mode_toggled(self, checked):
        """シミュレーション範囲ラジオボタンの切り替え連動"""
        is_custom = not checked
        self.le_stream_start_frame.setEnabled(is_custom)
        self.le_stream_end_frame.setEnabled(is_custom)

    def _on_stream_bullet_version_toggled(self, checked):
        """リアルタイム物理ベイクのBulletバージョン切り替えイベント"""
        if not checked:
            return
        ver = "2.83.7" if hasattr(self, 'rb_stream_bullet_283') and self.rb_stream_bullet_283.isChecked() else "2.75"
        mc.optionVar(sv=("MMDToolsForMaya_StreamBulletVersion", ver))

    def _hide_helper_nodes_after_bake(self):
        """ベイク終了後に補助ノード群を非表示化"""
        if hasattr(self, 'cb_stream_hide_helpers') and not self.cb_stream_hide_helpers.isChecked():
            return

        # 剛体・Joint可視化ノードを非表示化
        for node in mc.ls("MMD_Physics_RigidBodies*", "MMD_Physics_Joints*", "MMD_Physics_Locators*","MMD_RigidBody_Joint_Visualizers", type=["transform", "joint"]) or []:
            try:
                mc.setAttr(f"{node}.visibility", False)
            except Exception:
                pass

        # 補助コントローラーを非表示化
        target_names = [
            "Apose_view_cnt",
            "Apose_subetenoya",
            "view_cnt",
            "subetenoya",
            "Apose_view_cnt_master",
            "Apose_subetenoya_master"
        ]
        for name in target_names:
            if mc.objExists(name):
                try:
                    mc.setAttr(f"{name}.visibility", False)
                except Exception:
                    pass

        # ワイルドカード検索でマッチする補助ノードを非表示化 (カメラ・ライト・エイムは除外保護)
        for pattern in ["*view_cnt*", "*subetenoya*", "*_master*"]:
            matched = mc.ls(pattern, type=["transform", "joint"]) or []
            for m in matched:
                m_lower = m.lower()
                if any(ex in m_lower for ex in ["light", "camera", "aim"]):
                    continue
                try:
                    mc.setAttr(f"{m}.visibility", False)
                except Exception:
                    pass

        restore_viewport_lighting()

    def _run_realtime_stream_bake(self):
        """新3D物理ビューアと同期しながらリアルタイム物理ベイクを実行"""
        pmx_path = self._get_effective_pmx_path()
        vmd_path = self.le_vmd_source_path.text().strip()

        if not pmx_path or not os.path.exists(pmx_path):
            QMessageBox.warning(self, "警告", "有効なPMXモデルファイルを指定してください。")
            return

        if not vmd_path or not os.path.exists(vmd_path):
            QMessageBox.warning(self, "警告", "有効なベイク元VMDモーションファイルを指定してください。")
            return

        # シミュレーション範囲の取得
        start_frame = None
        end_frame = None
        if not self.rb_stream_auto_frame.isChecked():
            try:
                start_frame = int(self.le_stream_start_frame.text().strip())
                end_frame = int(self.le_stream_end_frame.text().strip())
                mc.playbackOptions(minTime=start_frame, maxTime=end_frame, animationStartTime=start_frame, animationEndTime=end_frame)
            except ValueError:
                QMessageBox.warning(self, "エラー", "開始・終了フレーム番号を正しく入力してください。")
                return

        try:
            scale = float(self.le_stream_scale.text().strip())
        except ValueError:
            scale = 8.0
        mc.optionVar(sv=("MMDToolsForMaya_StreamScale", str(scale)))

        try:
            lookahead = int(self.le_stream_lookahead.text().strip())
        except ValueError:
            lookahead = 16
        mc.optionVar(sv=("MMDToolsForMaya_StreamLookahead", str(lookahead)))

        try:
            warmup = float(self.le_stream_warmup.text().strip())
        except ValueError:
            warmup = 0.0
        mc.optionVar(sv=("MMDToolsForMaya_StreamWarmup", str(warmup)))

        try:
            frame_offset = int(self.le_stream_offset.text().strip())
        except ValueError:
            frame_offset = 0
        mc.optionVar(sv=("MMDToolsForMaya_StreamOffset", str(frame_offset)))

        out_vmd = "none"
        if self.rb_vmd_out_enable.isChecked():
            out_vmd = self.le_vmd_output_path.text().strip()
            if not out_vmd:
                self._update_default_vmd_output_path()
                out_vmd = self.le_vmd_output_path.text().strip()
            out_dir = os.path.dirname(out_vmd)
            if out_dir:
                try:
                    os.makedirs(out_dir, exist_ok=True)
                except Exception:
                    pass

        target_model = None

        try:
            from ..converters import physics_stream
        except Exception:
            try:
                from converters import physics_stream
            except Exception:
                import physics_stream

        try:
            from ..converters import vmdpaimaya
        except Exception:
            try:
                from converters import vmdpaimaya
            except Exception:
                import vmdpaimaya

        substep = self.cbb_stream_substep.currentData() if hasattr(self, 'cbb_stream_substep') else 120
        bullet_ver = "2.83.7" if hasattr(self, 'rb_stream_bullet_283') and self.rb_stream_bullet_283.isChecked() else "2.75"

        models = []
        try:
            models = vmdpaimaya.get_available_mmd_models()
        except Exception:
            pass

        # 複数モデル順次ベイクの自動判定 (自動検出時に複数モデルが存在する場合)
        # 適用対象モデルの取得
        if self._selected_model_nodes is None:
            models_to_bake = models
        else:
            selected_set = set(self._selected_model_nodes)
            models_to_bake = [(node, label) for node, label in models if node in selected_set]

        if not models_to_bake:
            QMessageBox.warning(
                self, "警告",
                "ベイク対象のモデルが選択されていません。\n"
                "「適用対象モデルの選択 (チェックリスト)...」からベイクするモデルにチェックを入れてください。"
            )
            return

        # 複数モデル順次ベイクの判定
        if len(models_to_bake) > 1:
            log_dialog = ExecutionLogDialog(
                self.parent_window or self,
                title="リアルタイム複数モデル順次物理ベイク実行ログ (追突防止・個別実行)",
                show_cancel=True
            )

            def run_multi_task():
                total = len(models_to_bake)
                log_dialog.append_log("--- リアルタイム複数モデル順次物理ベイク開始 ---\n")
                log_dialog.append_log(f"対象モデル: {total} 体が選択されています。\n")
                log_dialog.append_log("剛体の追突や反発・吹き飛びを防ぐため、1体ずつ順番に独立してビューアを起動してベイクします。\n\n")

                for idx, (m_node, m_label) in enumerate(models_to_bake, start=1):
                    if log_dialog.check_cancelled():
                        log_dialog.append_log("\n[中断] ユーザーによりベイクが中断されました。\n")
                        break

                    log_dialog.append_log("==================================================\n")
                    log_dialog.append_log(f"[{idx}/{total}] モデル物理ベイク開始: {m_label}\n")
                    log_dialog.append_log("==================================================\n")

                    # モデル固有のPMXパスを取得 (保存されている場合は優先)
                    model_pmx = pmx_path
                    if mc.attributeQuery('mmdModelPath', node=m_node, exists=True):
                        saved_path = mc.getAttr(f"{m_node}.mmdModelPath")
                        if saved_path and os.path.exists(saved_path):
                            model_pmx = saved_path

                    # モデル固有のVMDパスを取得 (PMMからインポートされたモデル用VMDがあれば自動セット)
                    model_vmd = vmd_path
                    model_vmd_found = ""
                    check_nodes = [m_node]
                    rel_nodes = mc.listRelatives(m_node, allDescendents=True, type=["transform", "mesh"]) or []
                    check_nodes.extend(rel_nodes)
                    for cn in check_nodes:
                        if mc.attributeQuery('mmdVmdPath', node=cn, exists=True):
                            vp = mc.getAttr(f"{cn}.mmdVmdPath")
                            if vp and os.path.exists(vp):
                                model_vmd_found = vp
                                break
                    if not model_vmd_found:
                        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        pmm_dir = os.path.join(plugin_root, "asset", "userdata", "pmm_vmd_data")
                        m_clean = safe_node_name(m_label.split(' ')[0])
                        candidate = os.path.join(pmm_dir, f"{m_clean}_pmm_motion.vmd")
                        if os.path.exists(candidate):
                            model_vmd_found = candidate.replace("\\", "/")
                    if model_vmd_found:
                        model_vmd = model_vmd_found
                        log_dialog.append_log(f"  - 対応VMDモーションを自動セット: {os.path.basename(model_vmd)}\n")

                    # モデルごとのVMD出力パス
                    model_out_vmd = out_vmd
                    if out_vmd and str(out_vmd).lower() != "none":
                        base_vmd, vmd_ext = os.path.splitext(out_vmd)
                        safe_label = safe_node_name(m_label.split(' ')[0])
                        model_out_vmd = f"{base_vmd}_{safe_label}{vmd_ext}"

                    physics_stream.stream_bake_physics(
                        pmx_path=model_pmx,
                        vmd_path=model_vmd,
                        target_model=m_node,
                        scale=scale,
                        lookahead=lookahead,
                        warmup=warmup,
                        out_vmd=model_out_vmd,
                        frame_offset=frame_offset,
                        start_frame=start_frame,
                        end_frame=end_frame,
                        substep=substep,
                        bullet_version=bullet_ver,
                        log_dialog=log_dialog
                    )
                    log_dialog.append_log(f"[{idx}/{total}] 終了: {m_label}\n\n")

                restore_viewport_lighting()

            success = log_dialog.run_task(run_multi_task)
            if success and not log_dialog.is_cancelled:
                self._hide_helper_nodes_after_bake()
                self._check_scene_import_status()
                mc.inViewMessage(
                    amg='<span style="color:#2ecc71;">MMD Tools for Maya:</span> 複数モデルのリアルタイム物理ベイクが終了しました。',
                    pos='topCenter',
                    fade=True
                )
            return

        # 単一モデルベイク（モデル1体、または個別モデル指定時）
        single_pmx = pmx_path
        single_target, single_label = models_to_bake[0]

        if single_target and mc.attributeQuery('mmdModelPath', node=single_target, exists=True):
            saved_path = mc.getAttr(f"{single_target}.mmdModelPath")
            if saved_path and os.path.exists(saved_path):
                single_pmx = saved_path

        # 単一モデル対応VMDの自動取得 (PMM由来等)
        single_vmd = vmd_path
        single_vmd_found = ""
        check_nodes = [single_target] + (mc.listRelatives(single_target, allDescendents=True, type=["transform", "mesh"]) or [])
        for cn in check_nodes:
            if mc.attributeQuery('mmdVmdPath', node=cn, exists=True):
                vp = mc.getAttr(f"{cn}.mmdVmdPath")
                if vp and os.path.exists(vp):
                    single_vmd_found = vp
                    break
        if not single_vmd_found:
            plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            pmm_dir = os.path.join(plugin_root, "asset", "userdata", "pmm_vmd_data")
            m_clean = safe_node_name(single_label.split(' ')[0])
            candidate = os.path.join(pmm_dir, f"{m_clean}_pmm_motion.vmd")
            if os.path.exists(candidate):
                single_vmd_found = candidate.replace("\\", "/")
        if single_vmd_found:
            single_vmd = single_vmd_found

        log_dialog = ExecutionLogDialog(
            self.parent_window or self,
            title="リアルタイム物理ベイク実行ログ (新3D物理ビューア連携)",
            show_cancel=True
        )

        def run_task():
            log_dialog.append_log(f"対象モデル: {single_label}\n")
            physics_stream.stream_bake_physics(
                pmx_path=single_pmx,
                vmd_path=single_vmd,
                target_model=single_target,
                scale=scale,
                lookahead=lookahead,
                warmup=warmup,
                out_vmd=out_vmd,
                frame_offset=frame_offset,
                start_frame=start_frame,
                end_frame=end_frame,
                substep=substep,
                bullet_version=bullet_ver,
                log_dialog=log_dialog
            )
            restore_viewport_lighting()

        success = log_dialog.run_task(run_task)
        if success and not log_dialog.is_cancelled:
            self._hide_helper_nodes_after_bake()
            self._check_scene_import_status()
            mc.inViewMessage(
                amg='<span style="color:#2ecc71;">MMD Tools for Maya:</span> リアルタイム物理ベイクが終了しました。',
                pos='topCenter',
                fade=True
            )

    def _hide_helper_nodes_after_bake(self):
        """物理ベイク終了後に補助ノード（*_RigidBody_Joint_Visualizers、カメラビューコントローラ、subetenoya、*_master等）を非表示化"""
        # 剛体・ジョイント可視化グループの非表示化
        vis_patterns = [
            "*_RigidBody_Joint_Visualizers*",
            "*_RigidBody_Visualizers*",
            "*_Joint_Visualizers*",
            "MMD_RigidBody_Joint_Visualizers*",
            "MMD_RigidBody_Visualizers*",
            "MMD_Joint_Visualizers*"
        ]
        for pat in vis_patterns:
            for v_node in mc.ls(pat, type=["transform", "joint"]) or []:
                try:
                    mc.setAttr(f"{v_node}.visibility", False)
                except Exception:
                    pass

        # 補助ノード非表示チェックボックスがOFFの場合はここで終了
        if hasattr(self, 'cb_stream_hide_helpers') and not self.cb_stream_hide_helpers.isChecked():
            restore_viewport_lighting()
            return

        target_names = ["Apose_view_cnt", "Apose_subetenoya"]
        for name in target_names:
            if mc.objExists(name):
                try:
                    mc.setAttr(f"{name}.visibility", False)
                except Exception:
                    pass

        # ワイルドカード検索でマッチする補助ノード（カメラ、subetenoya、*_master）も非表示化
        for pattern in ["*view_cnt*", "*subetenoya*", "*_master*"]:
            matched = mc.ls(pattern, type=["transform", "joint"]) or []
            for m in matched:
                m_lower = m.lower()
                if any(ex in m_lower for ex in ["light", "camera", "aim"]):
                    continue
                try:
                    mc.setAttr(f"{m}.visibility", False)
                except Exception:
                    pass

        restore_viewport_lighting()

    def _update_default_paths(self, pmx_path):
        """PMXパス設定時の補助処理"""
        self._update_default_vmd_output_path()

    def _browse_pmx(self):
        """PMXファイル選択ダイアログ"""
        path, _ = QFileDialog.getOpenFileName(
            self, "PMXモデルファイルを選択", "", "PMXファイル (*.pmx);;すべてのファイル (*.*)"
        )
        if path:
            self.le_pmx_path.setText(path)
            self._update_default_paths(path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """ドラッグ侵入時のファイル拡張子確認"""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                ext = os.path.splitext(url.toLocalFile())[1].lower()
                if ext in [".pmx", ".vmd"]:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def showEvent(self, event):
        super(PhysicsGuiTabWidget, self).showEvent(event)
        self._check_scene_import_status()
        self._refresh_stream_target_models()

    def dropEvent(self, event: QDropEvent):
        """ドロップ時のファイルパス反映"""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".pmx":
                self.le_pmx_path.setText(file_path)
                self._update_default_paths(file_path)
                mc.inViewMessage(
                    amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> PMXモデルを設定しました: {os.path.basename(file_path)}',
                    pos='topCenter',
                    fade=True
                )
                event.acceptProposedAction()
                return
            elif ext == ".vmd":
                self.le_vmd_source_path.setText(file_path)
                mc.inViewMessage(
                    amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> ベイク元VMDを設定しました: {os.path.basename(file_path)}',
                    pos='topCenter',
                    fade=True
                )
                event.acceptProposedAction()
                return
        event.ignore()

    def showEvent(self, event):
        super(PhysicsGuiTabWidget, self).showEvent(event)
        self._check_scene_import_status()
        self._refresh_stream_target_models()
