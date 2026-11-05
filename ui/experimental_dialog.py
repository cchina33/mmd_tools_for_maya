# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 試験的機能ダイアログ
"""

from .common import *

# ==============================================================================
# 試験的機能 ダイアログ
# ==============================================================================
class ExperimentalFeaturesDialog(QDialog):
    """動作確認が不十分な機能や開発中の機能をまとめた試験的機能ウィンドウ"""
    def __init__(self, parent=None):
        super(ExperimentalFeaturesDialog, self).__init__(parent)
        self.parent_tab = parent
        self.setWindowTitle("試験的機能")
        self.resize(820, 780)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self._init_ui()
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_file = os.path.join(plugin_root, 'asset', 'khatangton1.txt')
        self._refresh_vpd_models()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 小画面対応スクロールエリア
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(14)
        layout.setContentsMargins(10, 10, 10, 10)

        # 注意文表示ボックス
        notice_box = QGroupBox("試験的機能に関するご注意")
        notice_box.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; color: #ffaa00; border: 1px solid #7a581e; margin-top: 6px; padding: 12px; border-radius: 4px; background-color: #262016; }")
        notice_layout = QVBoxLayout(notice_box)
        notice_layout.setSpacing(6)
        lbl_notice_title = QLabel("【注意・未確認の試験的機能】")
        lbl_notice_title.setStyleSheet("color: #ffaa00; font-size: 15px; font-weight: bold;")
        notice_layout.addWidget(lbl_notice_title)

        lbl_notice = QLabel(
            "本ウィンドウに掲載されている機能は、開発中または正しく動作するか確認できていない試験的機能です。\n"
            "予期せぬ動作、エラー、フリーズなどが発生する可能性がありますのでご注意ください。"
        )
        lbl_notice.setWordWrap(True)
        lbl_notice.setStyleSheet("color: #ffd180; font-size: 13px; line-height: 1.4; font-weight: normal;")
        notice_layout.addWidget(lbl_notice)
        layout.addWidget(notice_box)

        # 《モデル操作グループ》
        oper_box = QGroupBox("モデル操作")
        oper_layout = QVBoxLayout(oper_box)
        oper_layout.setSpacing(10)

        # Maya → MMD (エクスポート) ボタン
        self.btn_open_export = QPushButton("Maya → MMD (エクスポート)")
        self.btn_open_export.setFixedHeight(42)
        self.btn_open_export.setToolTip("PMXモデル・VMDモーション・VPDポーズのエクスポート機能を別ウィンドウで表示します。")
        self.btn_open_export.setStyleSheet("QPushButton { background-color: #2e6b52; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3b8767; }")
        self.btn_open_export.clicked.connect(self._open_export_window)
        oper_layout.addWidget(self.btn_open_export)

        # HumanIK管理ボタン
        self.btn_hik_ui = QPushButton("HumanIK管理")
        self.btn_hik_ui.setFixedHeight(42)
        self.btn_hik_ui.setToolTip("HumanIK管理パネルを別ウィンドウで開き、キャラクター定義の作成やボーンマッピングを行います。")
        self.btn_hik_ui.setStyleSheet("QPushButton { background-color: #2e607a; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3b7696; }")
        self.btn_hik_ui.clicked.connect(self._open_hik_window)
        oper_layout.addWidget(self.btn_hik_ui)

        # アクセサリ追従アタッチボタン
        self.btn_accessory_attach = QPushButton("アクセサリ追従アタッチ (右手/左手/頭/腰) (試験的機能)")
        self.btn_accessory_attach.setFixedHeight(42)
        self.btn_accessory_attach.setToolTip("小物（.x / .pmx / 任意メッシュ）をMMDモデルのボーンへ追従アタッチ・デタッチするパネルを開きます。")
        self.btn_accessory_attach.setStyleSheet("QPushButton { background-color: #7b4a2e; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #965a38; }")
        self.btn_accessory_attach.clicked.connect(self._open_accessory_attach_window)
        oper_layout.addWidget(self.btn_accessory_attach)

        # VPDポーズデータ適用サブグループ
        pose_box = QGroupBox("MMD ポーズデータ (.vpd) 適用")
        pose_layout = QVBoxLayout(pose_box)
        pose_layout.setSpacing(8)

        h_pose_opt = QHBoxLayout()
        lbl_target_m = QLabel("対象モデル:")
        lbl_target_m.setStyleSheet("font-size: 13px;")
        h_pose_opt.addWidget(lbl_target_m)

        self.cbb_vpd_target_model = QComboBox()
        self.cbb_vpd_target_model.setFixedHeight(34)
        self.cbb_vpd_target_model.setStyleSheet("QComboBox { font-size: 13px; }")
        h_pose_opt.addWidget(self.cbb_vpd_target_model, 1)

        self.btn_vpd_refresh_model = QPushButton("更新")
        self.btn_vpd_refresh_model.setFixedWidth(75)
        self.btn_vpd_refresh_model.setFixedHeight(34)
        self.btn_vpd_refresh_model.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 13px; font-weight: bold; }")
        self.btn_vpd_refresh_model.clicked.connect(self._refresh_vpd_models)
        h_pose_opt.addWidget(self.btn_vpd_refresh_model)

        lbl_scale = QLabel("スケール:")
        lbl_scale.setStyleSheet("font-size: 13px;")
        h_pose_opt.addWidget(lbl_scale)

        self.le_vpd_scale = QLineEdit("8.0")
        self.le_vpd_scale.setFixedWidth(60)
        self.le_vpd_scale.setFixedHeight(34)
        self.le_vpd_scale.setStyleSheet("QLineEdit { font-size: 13px; padding: 2px 4px; }")
        h_pose_opt.addWidget(self.le_vpd_scale)
        pose_layout.addLayout(h_pose_opt)

        self.btn_import_vpd = QPushButton("VPDポーズを適用 (インポート)")
        self.btn_import_vpd.setFixedHeight(38)
        self.btn_import_vpd.setStyleSheet("QPushButton { background-color: #2b5b84; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3872a4; }")
        self.btn_import_vpd.setToolTip("MMDのポーズデータ (.vpd) を読み込み、現在フレームのモデルへ適用します。")
        self.btn_import_vpd.clicked.connect(self._on_import_vpd)
        pose_layout.addWidget(self.btn_import_vpd)

        self.cb_vpd_keyframe = QCheckBox("ポーズ適用時にカレントフレームへキーフレームを登録する")
        self.cb_vpd_keyframe.setChecked(True)
        pose_layout.addWidget(self.cb_vpd_keyframe)

        lbl_vpd_info = QLabel("※MMD標準のポーズファイル (.vpd) を読み込み、シーン内のモデルにポーズを反映します。")
        lbl_vpd_info.setStyleSheet("color: #999; font-size: 12px;")
        pose_layout.addWidget(lbl_vpd_info)

        oper_layout.addWidget(pose_box)
        layout.addWidget(oper_box)

        # 《モデル解析グループ》
        analysis_box = QGroupBox("モデル解析")
        analysis_layout = QVBoxLayout(analysis_box)
        analysis_layout.setSpacing(10)

        lbl_radio_guide = QLabel("実行する解析・エクスポート機能を選択してください:")
        lbl_radio_guide.setStyleSheet("color: #bbb; font-size: 12px;")
        analysis_layout.addWidget(lbl_radio_guide)

        # ラジオボタンによる機能統合
        self.rb_analyze_pmx = QRadioButton("PMXモデルチェック・データ一括保存 (材質/ボーン/モーフ/剛体/Joint)")
        self.rb_analyze_pmx.setStyleSheet("QRadioButton { font-size: 13px; color: #e0e0e0; font-weight: bold; }")
        self.rb_analyze_pmx.setChecked(True)
        self.rb_analyze_pmx.toggled.connect(self._on_analysis_option_changed)
        analysis_layout.addWidget(self.rb_analyze_pmx)

        self.rb_export_bones = QRadioButton("ボーン状態JSONエクスポート (指定フレーム範囲)")
        self.rb_export_bones.setStyleSheet("QRadioButton { font-size: 13px; color: #e0e0e0; font-weight: bold; }")
        analysis_layout.addWidget(self.rb_export_bones)

        # 統合実行ボタン
        self.btn_execute_analysis = QPushButton("PMXモデルチェック・データ一括保存を実行")
        self.btn_execute_analysis.setFixedHeight(42)
        self.btn_execute_analysis.setToolTip("インポートタブで指定されたPMXの構成要素（材質・ボーン・モーフ・剛体・Joint）をJSONに一括保存し、未登録漢字のユーザー辞書登録を行います。")
        self.btn_execute_analysis.setStyleSheet("QPushButton { background-color: #2b5b84; color: #fff; font-weight: bold; font-size: 13px; border-radius: 4px; } QPushButton:hover { background-color: #3872a4; }")
        self.btn_execute_analysis.clicked.connect(self._on_execute_analysis_clicked)
        analysis_layout.addWidget(self.btn_execute_analysis)

        # 互換性参照用
        self.btn_analyze_model = self.btn_execute_analysis
        self.btn_export_bone_states = self.btn_execute_analysis

        layout.addWidget(analysis_box)

        # 《エッジメッシュ生成グループ (反転法線押し出し別メッシュ)》
        edge_box = QGroupBox("エッジメッシュ生成 (反転法線押し出し別メッシュ)")
        edge_layout = QVBoxLayout(edge_box)
        edge_layout.setSpacing(10)

        # インポート時生成チェックボックス
        self.cb_create_edge_mesh = QCheckBox("インポート時にエッジ（輪郭線）メッシュを作成する (別メッシュ生成)")
        self.cb_create_edge_mesh.setChecked(self._load_edge_mesh_setting())
        self.cb_create_edge_mesh.setToolTip("旧方式の反転法線押し出し別メッシュを生成します。Maya Viewport 2.0 では C++ シェーダー単体でのエッジ描画が標準のため通常はOFFを推奨します。Arnold等で実体ポリゴンが必要な場合のみ有効にしてください。")
        self.cb_create_edge_mesh.toggled.connect(self._on_edge_mesh_toggled)
        edge_layout.addWidget(self.cb_create_edge_mesh)

        # 手動生成・解除ボタン
        h_edge_actions = QHBoxLayout()
        self.btn_apply_edge = QPushButton("選択モデルにエッジメッシュを生成・適用")
        self.btn_apply_edge.setFixedHeight(36)
        self.btn_apply_edge.setToolTip("選択されているモデルメッシュ（未選択時はシーン内のMMDモデル）に対し、反転法線押し出し方式のエッジメッシュを即座に生成します。")
        self.btn_apply_edge.clicked.connect(self._apply_edge_mesh_clicked)
        h_edge_actions.addWidget(self.btn_apply_edge)

        self.btn_remove_edge = QPushButton("選択モデルのエッジメッシュを解除")
        self.btn_remove_edge.setFixedHeight(36)
        self.btn_remove_edge.setToolTip("選択されているモデル（未選択時はシーン内のMMDモデル）のエッジメッシュを解除・削除します。")
        self.btn_remove_edge.clicked.connect(self._remove_edge_mesh_clicked)
        h_edge_actions.addWidget(self.btn_remove_edge)

        edge_layout.addLayout(h_edge_actions)

        lbl_edge_note = QLabel("※Maya Viewport 2.0 では C++ シェーダーによる輪郭線描画が有効なため、通常は生成不要です。Arnold等の外部レンダラーで実体ポリゴンが必要な場合のみご利用ください。")
        lbl_edge_note.setWordWrap(True)
        lbl_edge_note.setStyleSheet("color: #999; font-size: 11px;")
        edge_layout.addWidget(lbl_edge_note)

        layout.addWidget(edge_box)

        # 《外部ツールグループ》
        viewer_box = QGroupBox("外部ツール (3D物理ビューア)")
        viewer_layout = QVBoxLayout(viewer_box)
        viewer_layout.setSpacing(8)

        # MMD Physics Brige - 3D物理ビューア起動ボタン (試験的機能)
        self.btn_launch_viewer = QPushButton("MMD Physics Brige - 3D物理ビューア(試験的機能)")
        self.btn_launch_viewer.setFixedHeight(42)
        self.btn_launch_viewer.setToolTip("physics_bridge_cs フォルダー内の MMD Physics Brige を単体起動します。Norton CyberCapture等の誤検知を回避する正規ホスト起動に対応しています。")
        self.btn_launch_viewer.setStyleSheet("QPushButton { background-color: #5c3b7a; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #734a99; }")
        self.btn_launch_viewer.clicked.connect(self._launch_standalone_viewer)
        viewer_layout.addWidget(self.btn_launch_viewer)

        lbl_viewer_info = QLabel("※.NET 8公式ホスト経由で起動し、Norton等のセキュリティソフトによる誤検知を抑制します。")
        lbl_viewer_info.setStyleSheet("color: #999; font-size: 12px;")
        viewer_layout.addWidget(lbl_viewer_info)

        layout.addWidget(viewer_box)
        layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # ウィンドウ下部ボタン
        h_bottom = QHBoxLayout()
        h_bottom.addStretch()
        btn_close = QPushButton("閉じる")
        btn_close.setFixedWidth(100)
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.close)
        h_bottom.addWidget(btn_close)
        main_layout.addLayout(h_bottom)

    def _get_target_pmx_path(self):
        """対象PMXパスを取得"""
        if self.parent_tab and hasattr(self.parent_tab, "_get_target_pmx_path"):
            return self.parent_tab._get_target_pmx_path()
        return ""

    def _sync_pmx_path(self):
        """対象PMXパスを同期"""
        if self.parent_tab and hasattr(self.parent_tab, "_sync_pmx_path"):
            return self.parent_tab._sync_pmx_path()
        return ""

    def _on_analysis_option_changed(self):
        """解析ラジオボタンの選択変更時にボタン表示とスタイルを連動更新"""
        if self.rb_analyze_pmx.isChecked():
            self.btn_execute_analysis.setText("PMXモデルチェック・データ一括保存を実行")
            self.btn_execute_analysis.setToolTip("インポートタブで指定されたPMXの構成要素（材質・ボーン・モーフ・剛体・Joint）をJSONに一括保存し、未登録漢字のユーザー辞書登録を行います。")
            self.btn_execute_analysis.setStyleSheet("QPushButton { background-color: #2b5b84; color: #fff; font-weight: bold; font-size: 13px; border-radius: 4px; } QPushButton:hover { background-color: #3872a4; }")
        else:
            self.btn_execute_analysis.setText("ボーン状態JSONエクスポートダイアログを開く")
            self.btn_execute_analysis.setToolTip("指定したフレーム範囲のすべてのボーンの移動・回転状態（ローカルおよびワールド）をJSONファイルとして書き出します。")
            self.btn_execute_analysis.setStyleSheet("QPushButton { background-color: #2e6b52; color: #fff; font-weight: bold; font-size: 13px; border-radius: 4px; } QPushButton:hover { background-color: #3b8767; }")

    def _on_execute_analysis_clicked(self):
        """選択中の解析・エクスポート機能を実行"""
        if self.rb_analyze_pmx.isChecked():
            self._analyze_and_save_structure()
        else:
            self._open_bone_state_export_window()

    def _analyze_and_save_structure(self):
        """PMXモデル詳細チェック・データ一括保存を実行"""
        if self.parent_tab and hasattr(self.parent_tab, "_analyze_and_save_structure"):
            self.parent_tab._analyze_and_save_structure()

    def _open_morph_window(self):
        """表情操作ウィンドウを開く"""
        if self.parent_tab and hasattr(self.parent_tab, "_open_morph_window"):
            self.parent_tab._open_morph_window()

    def _open_export_window(self):
        """Maya → MMD エクスポートウィンドウを開く"""
        if self.parent_tab and hasattr(self.parent_tab, "_open_export_window"):
            self.parent_tab._open_export_window()

    def _open_hik_window(self):
        """HumanIK管理ウィンドウを開く"""
        if self.parent_tab and hasattr(self.parent_tab, "_open_hik_window"):
            self.parent_tab._open_hik_window()

    def _launch_standalone_viewer(self):
        """3D物理ビューアを単体起動"""
        if self.parent_tab and hasattr(self.parent_tab, "_launch_standalone_viewer"):
            self.parent_tab._launch_standalone_viewer()

    def _open_bone_state_export_window(self):
        """ボーン状態JSONエクスポートダイアログを開く"""
        if self.parent_tab and hasattr(self.parent_tab, "_open_bone_state_export_window"):
            self.parent_tab._open_bone_state_export_window()

    def _open_accessory_attach_window(self):
        """アクセサリアタッチダイアログを開く"""
        if self.parent_tab and hasattr(self.parent_tab, "_open_accessory_attach_window"):
            self.parent_tab._open_accessory_attach_window()

    def _refresh_vpd_models(self):
        """VPDポーズ適用対象のMMDモデル一覧を更新"""
        self.cbb_vpd_target_model.clear()
        try:
            from ..converters import vmdpaimaya
        except Exception:
            from converters import vmdpaimaya
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for node_name, label in models:
                self.cbb_vpd_target_model.addItem(label, node_name)
        except Exception:
            pass

    def _on_import_vpd(self):
        """VPDポーズファイルを読み込んでモデルに適用"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "VPDポーズファイルを選択",
            "",
            "VPD Pose Data (*.vpd);;All Files (*.*)"
        )
        if not path:
            return

        target_model = self.cbb_vpd_target_model.currentData()
        try:
            scale = float(self.le_vpd_scale.text())
        except ValueError:
            scale = 8.0

        set_key = self.cb_vpd_keyframe.isChecked()

        try:
            from ..converters import vmdpaimaya
        except Exception:
            from converters import vmdpaimaya

        try:
            res = vmdpaimaya.import_vpd(path, target_model_node=target_model, scale=scale, set_keyframe=set_key)
            QMessageBox.information(
                self,
                "VPDインポート完了",
                f"VPDポーズを適用しました。\n"
                f"・ボーン: {res['bones_applied']} 本\n"
                f"・モーフ: {res['morphs_applied']} 個\n"
                f"・モデル: {res.get('model_name', '')}"
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"VPDポーズの適用中にエラーが発生しました:\n{e}")

    def _load_edge_mesh_setting(self):
        """設定ファイルからエッジメッシュ生成設定を読み込み (デフォルト: False)"""
        try:
            if hasattr(self, 'config_file') and os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line_str = line.strip()
                        if line_str.startswith("エッジメッシュ"):
                            val = line_str.split('=')[-1].strip()
                            return bool(int(val))
        except Exception:
            pass
        return False

    def _on_edge_mesh_toggled(self, checked):
        """エッジメッシュ生成チェック切り替え時に設定ファイルおよびインポートタブへ即時同期"""
        try:
            if hasattr(self, 'config_file') and os.path.exists(self.config_file):
                lines = []
                found = False
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip().startswith("エッジメッシュ"):
                            lines.append(f"エッジメッシュ = {int(checked)}\n")
                            found = True
                        else:
                            lines.append(line)
                if not found:
                    lines.append(f"エッジメッシュ = {int(checked)}\n")
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
        except Exception:
            pass

        # 親ウィンドウのインポートタブ側の保持値を同期
        try:
            main_win = getattr(self, 'parent_tab', None)
            if hasattr(main_win, 'parent_window'):
                main_win = main_win.parent_window
            if hasattr(main_win, 'tab_import'):
                main_win.tab_import._create_edge_mesh_setting = bool(checked)
        except Exception:
            pass

    def _apply_edge_mesh_clicked(self):
        """選択されているモデルまたはシーン内のMMDモデルにエッジメッシュを生成・適用"""
        try:
            try:
                from ..converters import edge_mesh_builder
            except Exception:
                from converters import edge_mesh_builder

            try:
                scale = float(self.le_vpd_scale.text())
            except Exception:
                scale = 8.0

            res = edge_mesh_builder.apply_edge_mesh_to_current_scene(scale=scale)
            if res:
                mesh_names = ", ".join(res)
                if mc:
                    mc.inViewMessage(amg=f'<span style="color:#2ecc71;">MMD Tools:</span> エッジメッシュを生成しました: {mesh_names}', pos='topCenter', fade=True)
                QMessageBox.information(
                    self,
                    "エッジメッシュ生成成功",
                    f"反転法線押し出し方式のエッジメッシュを生成しました。\n\n"
                    f"生成されたメッシュ: {mesh_names}\n\n"
                    f"肌・髪・服のエッジが別ジオメトリとして表示されます。"
                )
            else:
                QMessageBox.warning(
                    self,
                    "対象未検出",
                    "エッジメッシュの生成対象となるMMDモデルが見つかりませんでした。\n"
                    "ビューポートまたはアウトライナでモデルメッシュを選択して再度実行してください。"
                )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"エッジメッシュ生成中にエラーが発生しました:\n{e}")

    def _remove_edge_mesh_clicked(self):
        """選択されているモデルまたはシーン内のMMDモデルのエッジメッシュを解除・削除"""
        try:
            try:
                from ..converters import edge_mesh_builder
            except Exception:
                from converters import edge_mesh_builder

            removed = edge_mesh_builder.remove_edge_mesh_from_scene()
            if removed:
                mesh_names = ", ".join(removed)
                if mc:
                    mc.inViewMessage(amg=f'<span style="color:#e67e22;">MMD Tools:</span> エッジメッシュを解除しました: {mesh_names}', pos='topCenter', fade=True)
                QMessageBox.information(
                    self,
                    "エッジメッシュ解除終了",
                    f"エッジメッシュを正常に解除・削除しました。\n\n"
                    f"対象メッシュ: {mesh_names}"
                )
            else:
                QMessageBox.information(
                    self,
                    "解除対象なし",
                    "解除すべきエッジメッシュは見つかりませんでした。"
                )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"エッジメッシュ解除中にエラーが発生しました:\n{e}")
