# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - その他機能タブ
"""

from .common import *
from .accessory_dialog import AccessoryAttachDialog
from .experimental_dialog import ExperimentalFeaturesDialog
from .tab_material import MaterialDialog
from .tab_export import ExportDialog
from .tab_hik import show_hik_window

# ==============================================================================
# その他機能タブ
# ==============================================================================
class ExtraTabWidget(QWidget):
    """共通設定管理および試験的機能へのアクセスを提供するユーティリティタブ"""
    def __init__(self, parent=None):
        super(ExtraTabWidget, self).__init__(parent)
        self.parent_window = parent
        self._exp_dialog = None
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
        layout.setSpacing(14)
        layout.setContentsMargins(0, 0, 0, 0)

        # 共通設定・マテリアル管理グループ
        setting_box = QGroupBox("共通設定・マテリアル管理")
        setting_layout = QVBoxLayout(setting_box)
        setting_layout.setSpacing(12)

        # マテリアル保護・Toon除外設定ボタン
        self.btn_material_protect = QPushButton("マテリアル保護・Toon除外設定")
        self.btn_material_protect.setFixedHeight(42)
        self.btn_material_protect.setToolTip("顔・肌のテカリ（スペキュラ）除去、瞳ハイライトのToon除外キーワードを設定します。")
        self.btn_material_protect.setStyleSheet("QPushButton { background-color: #3b5f7a; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #4b7496; }")
        self.btn_material_protect.clicked.connect(self._open_material_protect_window)
        setting_layout.addWidget(self.btn_material_protect)

        # ユーザー辞書・対応表設定ボタン
        self.btn_user_dict = QPushButton("ユーザー辞書・対応表設定 (ボーン/HumanIK/名称)")
        self.btn_user_dict.setFixedHeight(42)
        self.btn_user_dict.setToolTip("ボーン日英辞書、HumanIK対応表、日本語ローマ字変換辞書の対応表（JSON）を設定・編集します。")
        self.btn_user_dict.setStyleSheet("QPushButton { background-color: #4d5b7a; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #5d6f96; }")
        self.btn_user_dict.clicked.connect(self._open_user_dict_window)
        setting_layout.addWidget(self.btn_user_dict)

        # モデル種別判定・個別指定設定ボタン
        self.btn_classifier = QPushButton("モデル種別判定・個別指定設定 (スカイドーム/ステージ)")
        self.btn_classifier.setFixedHeight(42)
        self.btn_classifier.setToolTip("スカイドームや大型ステージの判定キーワード設定、および特定モデルファイルの個別種別マッピング（JSON）を設定・編集します。")
        self.btn_classifier.setStyleSheet("QPushButton { background-color: #2c3e50; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #34495e; }")
        self.btn_classifier.clicked.connect(self._open_classifier_window)
        setting_layout.addWidget(self.btn_classifier)

        # MMD照明操作 (地面影 / ライト) ボタン
        self.btn_light_control = QPushButton("MMD照明操作 (地面影 / ライト)")
        self.btn_light_control.setFixedHeight(42)
        self.btn_light_control.setToolTip("MMD本家と同等の照明操作パネル（RGB、XYZ、初期化、登録）を開き、地面影やライト方向をインタラクティブに操作します。")
        self.btn_light_control.setStyleSheet("QPushButton { background-color: #1f618d; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #2980b9; }")
        self.btn_light_control.clicked.connect(self._open_light_control_window)
        setting_layout.addWidget(self.btn_light_control)

        # MMDエッジ太さ操作 (輪郭線) ボタン
        self.btn_edge_control = QPushButton("MMDエッジ太さ操作 (輪郭線)")
        self.btn_edge_control.setFixedHeight(42)
        self.btn_edge_control.setToolTip("シーン内のMMDモデルのエッジ（輪郭線）太さをスライダーでリアルタイムに一括調整します。")
        self.btn_edge_control.setStyleSheet("QPushButton { background-color: #2b546e; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #376a8c; }")
        self.btn_edge_control.clicked.connect(self._open_edge_control_window)
        setting_layout.addWidget(self.btn_edge_control)

        # PMD → PMX に変換ボタン (単独変換・保存)
        self.btn_convert_pmd = QPushButton("PMD → PMX に変換")
        self.btn_convert_pmd.setFixedHeight(42)
        self.btn_convert_pmd.setToolTip("指定した PMD ファイルを最新の PMX 形式へ変換し、同一フォルダに保存します（モデルのインポートは行いません）。")
        self.btn_convert_pmd.setStyleSheet("QPushButton { background-color: #3b6b58; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #4b876e; }")
        self.btn_convert_pmd.clicked.connect(self._on_convert_pmd_to_pmx)
        setting_layout.addWidget(self.btn_convert_pmd)

        layout.addWidget(setting_box)

        # 試験的機能グループ
        exp_box = QGroupBox("試験的機能")
        exp_layout = QVBoxLayout(exp_box)
        exp_layout.setSpacing(10)

        lbl_exp_notice = QLabel("※開発中・試験的な機能群を別ウィンドウで開きます。")
        lbl_exp_notice.setStyleSheet("color: #ffaa00; font-size: 12px;")
        exp_layout.addWidget(lbl_exp_notice)

        # 試験的機能を表示ボタン
        self.btn_open_experimental = QPushButton("試験的機能を表示")
        self.btn_open_experimental.setFixedHeight(44)
        self.btn_open_experimental.setToolTip("正しく動作するか確認できていない試験的機能群（モデル解析、HumanIK、物理ビューア、ボーンエクスポート、アクセサリアタッチ、VPDポーズ適用等）を別ウィンドウで表示します。")
        self.btn_open_experimental.setStyleSheet("QPushButton { background-color: #7b4a2e; color: #fff; font-size: 13px; font-weight: bold; border-radius: 4px; border: 1px solid #965a38; } QPushButton:hover { background-color: #965a38; }")
        self.btn_open_experimental.clicked.connect(self._open_experimental_window)
        exp_layout.addWidget(self.btn_open_experimental)

        # 表情操作 (モーフ) ボタン
        self.btn_morph_ui = QPushButton("表情操作 (モーフ)")
        self.btn_morph_ui.setFixedHeight(44)
        self.btn_morph_ui.setToolTip("表情操作パネルを開き、目・リップ・まゆ・その他のモーフを操作・登録します。")
        self.btn_morph_ui.setStyleSheet("QPushButton { background-color: #3e6852; color: #fff; font-size: 13px; font-weight: bold; border-radius: 4px; border: 1px solid #4e8267; } QPushButton:hover { background-color: #4e8267; }")
        self.btn_morph_ui.clicked.connect(self._open_morph_window)
        exp_layout.addWidget(self.btn_morph_ui)

        # MMDシェーダーボタン
        self.btn_open_material = QPushButton("MMDシェーダー")
        self.btn_open_material.setFixedHeight(44)
        self.btn_open_material.setToolTip("MMDシェーダー (mmdMaterial) のアサイン・管理機能を別ウィンドウで表示します。")
        self.btn_open_material.setStyleSheet("QPushButton { background-color: #2e607a; color: #fff; font-size: 13px; font-weight: bold; border-radius: 4px; border: 1px solid #3b7696; } QPushButton:hover { background-color: #3b7696; }")
        self.btn_open_material.clicked.connect(self._open_material_window)
        exp_layout.addWidget(self.btn_open_material)

        layout.addWidget(exp_box)
        layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

    def _open_experimental_window(self):
        """試験的機能ウィンドウを表示"""
        self._exp_dialog = ExperimentalFeaturesDialog(self) # 試験的機能を表示
        self._exp_dialog.show()

    def _open_material_window(self):
        """MMDシェーダーウィンドウを別ウィンドウで表示"""
        self._material_dialog = MaterialDialog(self)
        self._material_dialog.show()

    def _open_export_window(self):
        """Maya → MMD エクスポートウィンドウを別ウィンドウで表示"""
        self._export_dialog = ExportDialog(self)
        self._export_dialog.show()

    def _open_accessory_attach_window(self):
        """アクセサリアタッチダイアログを開く"""
        dlg = AccessoryAttachDialog(self)
        dlg.show()

    def _open_bone_state_export_window(self):
        """ボーン状態JSONエクスポートダイアログを開く"""
        try:
            from .bone_state_export_dialog import show_bone_state_export_dialog
        except Exception:
            try:
                from ui.bone_state_export_dialog import show_bone_state_export_dialog
            except Exception:
                import bone_state_export_dialog
                show_bone_state_export_dialog = bone_state_export_dialog.show_bone_state_export_dialog
        show_bone_state_export_dialog()

    def _open_material_protect_window(self):
        """マテリアル保護・Toon除外設定ダイアログを開く"""
        try:
            from .material_protect_dialog import show_material_protect_dialog
        except Exception:
            try:
                from ui.material_protect_dialog import show_material_protect_dialog
            except Exception:
                import material_protect_dialog
                show_material_protect_dialog = material_protect_dialog.show_material_protect_dialog
        show_material_protect_dialog()

    def _open_user_dict_window(self):
        """ユーザー辞書・対応表設定ダイアログを開く"""
        try:
            from .user_dict_dialog import show_user_dict_dialog
        except Exception:
            try:
                from ui.user_dict_dialog import show_user_dict_dialog
            except Exception:
                import user_dict_dialog
                show_user_dict_dialog = user_dict_dialog.show_user_dict_dialog
        show_user_dict_dialog()

    def _on_convert_pmd_to_pmx(self):
        """PMDファイルを選択して最新のPMX形式へ変換・保存（インポートは行わない）"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "変換する PMD ファイルを選択",
            "",
            "MMD Model (*.pmd);;All Files (*.*)"
        )
        if not file_path:
            return

        if not os.path.exists(file_path):
            QMessageBox.warning(self, "エラー", "指定された PMD ファイルが存在しません。")
            return

        try:
            try:
                from ..converters.pmd2pmx import convert_pmd_to_pmx
            except Exception:
                from converters.pmd2pmx import convert_pmd_to_pmx

            converted_pmx_path = convert_pmd_to_pmx(file_path)
            QMessageBox.information(
                self,
                "変換完了",
                f"PMDからPMXへの変換が正常に完了しました。\n\n保存先:\n{converted_pmx_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "PMD変換エラー", f"PMXへの変換中にエラーが発生しました:\n{e}")

    def _launch_standalone_viewer(self):

        """physics_bridge_cs フォルダー内の MMD Physics Brige を単体起動する (Norton対策・dotnet経由対応)"""
        warning_msg = (
            "【注意・試験的機能】\n\n"
            "本機能は physics_bridge_cs フォルダー内の MMD Physics Brige を起動します。\n"
            "本ツールは試験的に作成された機能であり、動作中にエラー、フリーズ、強制終了などが発生する可能性や、"
            "今後メンテナンスされない可能性があります。\n\n"
            "※Norton等のセキュリティソフトにより「Norton CyberCapture」等の確認画面が表示された場合は、"
            "「信頼して起動」を選択するか、除外リストへプラグインフォルダーを追加してください。\n\n"
            "起動を続行しますか？"
        )
        reply = QMessageBox.warning(
            self,
            "MMD Physics Brige - 3D物理ビューア(試験的機能)",
            warning_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # physics_bridge_cs フォルダー内の実行ファイルおよびDLLパスを取得
        plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bridge_candidates = [
            os.path.join(plugin_dir, "physics_bridge_cs", "bin", "Release", "net8.0-windows", "MmdPhysicsBridge.exe"),
            os.path.join(plugin_dir, "physics_bridge_cs", "bin", "Debug", "net8.0-windows", "MmdPhysicsBridge.exe"),
        ]
        exe_path = ""
        for cand in bridge_candidates:
            if os.path.isfile(cand):
                exe_path = cand
                break
        if not exe_path:
            exe_path = bridge_candidates[0]

        dll_candidates = [
            os.path.join(plugin_dir, "physics_bridge_cs", "bin", "Release", "net8.0-windows", "MmdPhysicsBridge.dll"),
            os.path.join(plugin_dir, "physics_bridge_cs", "bin", "Debug", "net8.0-windows", "MmdPhysicsBridge.dll"),
        ]
        dll_path = ""
        for cand in dll_candidates:
            if os.path.isfile(cand):
                dll_path = cand
                break
        if not dll_path:
            dll_path = dll_candidates[0]

        if not os.path.isfile(exe_path) and not os.path.isfile(dll_path):
            QMessageBox.critical(
                self,
                "エラー",
                f"physics_bridge_cs フォルダー内に MMD Physics Brige の実行ファイルが見つかりません:\n{exe_path}\n\n事前にビルドされているか確認してください。"
            )
            return

        # PMXファイルパスとVMDファイルパスの取得 (選択されていれば引数として渡す)
        pmx_path = self._get_target_pmx_path()
        vmd_path = ""
        if hasattr(self.parent_window, "tab_vmd"):
            vmd_path = self.parent_window.tab_vmd.le_file_path.text().strip()

        args = []
        if pmx_path and os.path.isfile(pmx_path):
            args.extend(["--pmx", pmx_path])
        if vmd_path and os.path.isfile(vmd_path):
            args.extend(["--vmd", vmd_path])

        # Zone.Identifier の解除 (セキュリティ警告抑止)
        for p in [exe_path, dll_path]:
            if p and os.path.exists(p) and sys.platform == 'win32':
                zone_stream = p + ":Zone.Identifier"
                try:
                    if os.path.exists(zone_stream):
                        os.remove(zone_stream)
                except Exception:
                    pass

        # Norton CyberCapture 対策: dotnet コマンド経由での起動を優先
        import shutil
        dotnet_exe = shutil.which("dotnet")
        if not dotnet_exe:
            common_paths = [
                os.path.expandvars(r"%ProgramFiles%\dotnet\dotnet.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\dotnet\dotnet.exe"),
            ]
            for cp in common_paths:
                if os.path.isfile(cp):
                    dotnet_exe = cp
                    break

        try:
            import subprocess
            if dotnet_exe and os.path.isfile(dll_path):
                cmd = [dotnet_exe, dll_path] + args
            else:
                cmd = [exe_path] + args
            subprocess.Popen(cmd)
        except Exception as e:
            QMessageBox.critical(self, "起動エラー", f"ビューアの起動に失敗しました:\n{e}")

    def _get_target_pmx_path(self):
        """インポートタブで指定されているPMXモデルのパスを取得"""
        path = ""
        if hasattr(self.parent_window, "tab_import") and hasattr(self.parent_window.tab_import, "le_file_path"):
            path = self.parent_window.tab_import.le_file_path.text().strip()
        return path

    def _sync_pmx_path(self):
        """インポートタブのモデルパスを取得"""
        return self._get_target_pmx_path()

    def _analyze_and_save_structure(self):
        """インポートタブで指定されたモデルの材質、ボーン、モーフ、剛体、Jointを一括保存し、未登録ボーン辞書チェックを実行"""
        file_path = self._sync_pmx_path()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(
                self,
                "エラー",
                "有効なPMXモデルファイルが指定されていません。\n\n"
                "[MMD → Maya (インポート)] タブでPMXモデルファイルを指定してください。"
            )
            return

        if not file_path.lower().endswith('.pmx'):
            QMessageBox.information(self, "案内", "詳細解析および辞書照合はPMXモデル形式 (.pmx) のみ対応しています。")
            return

        try:
            if check_and_prompt_user_dict:
                check_and_prompt_user_dict(self.parent_window or self, file_path)

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
        """MMD本家風の表情操作ウィンドウを開く（ボーン・モーフ・ブレンドシェイプ事前検証付き）"""
        # ボーン(Joint)存在確認
        joints = mc.ls(type="joint") if mc else []

        # BlendShapeノード存在確認
        bs_nodes = mc.ls(type="blendShape") if mc else []

        # ターゲット/モーフ存在確認
        has_targets = False
        if bs_nodes and mc:
            for bs in bs_nodes:
                try:
                    aliases = mc.listAttr(f"{bs}.w", multi=True) or []
                    targets = mc.blendShape(bs, query=True, target=True) or []
                    if aliases or targets:
                        has_targets = True
                        break
                except Exception:
                    pass

        # 必要な要素が揃っていない場合は再インポートを案内
        if not joints or not bs_nodes or not has_targets:
            missing_items = []
            if not joints:
                missing_items.append("・ボーン (Joint)")
            if not bs_nodes or not has_targets:
                missing_items.append("・ブレンドシェイプ / モーフ (blendShape)")

            missing_str = "\n".join(missing_items)
            QMessageBox.warning(
                self,
                "表情操作の準備ができていません",
                f"モデル（ボーン・モーフ・ブレンドシェイプ）がインポートされていないか、必要な要素が不足しています。\n\n"
                f"不足している要素:\n{missing_str}\n\n"
                f"[MMD → Maya (インポート)] タブからモデルをインポートし直してください。\n"
                f"（※インポート設定で「ボーン生成」「ブレンドシェイプ生成」にチェックが入っていることをご確認ください）"
            )
            return

        try:
            from .morph_window import show_morph_window
        except Exception:
            try:
                from morph_window import show_morph_window
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"表情操作モジュールの読み込みに失敗しました:\n{e}")
                return

        show_morph_window(parent=get_maya_main_window())

    def _open_hik_window(self):
        """HumanIK管理ウィンドウを別ウィンドウで開く"""
        show_hik_window(parent=get_maya_main_window())

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

    def _open_classifier_window(self):
        """モデル種別判定・個別指定設定ダイアログを開きます"""
        try:
            try:
                from .dialog_model_classifier import show_model_classifier_dialog
            except Exception:
                from ui.dialog_model_classifier import show_model_classifier_dialog
            show_model_classifier_dialog(parent=self.parent_window or self)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"設定ダイアログの起動に失敗しました: {e}")

    def _open_light_control_window(self):
        """MMD照明操作ダイアログを開きます"""
        try:
            try:
                from .dialog_light_control import show_mmd_light_control_dialog
            except Exception:
                from ui.dialog_light_control import show_mmd_light_control_dialog
            show_mmd_light_control_dialog(parent=get_maya_main_window())
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"MMD照明操作ダイアログの起動に失敗しました: {e}")

    def _open_edge_control_window(self):
        """MMDエッジ太さ操作ダイアログを開きます"""
        try:
            try:
                from .dialog_edge_control import show_mmd_edge_control_dialog
            except Exception:
                from ui.dialog_edge_control import show_mmd_edge_control_dialog
            show_mmd_edge_control_dialog(parent=get_maya_main_window())
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"MMDエッジ太さ操作ダイアログの起動に失敗しました: {e}")
