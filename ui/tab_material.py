# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - シェーダー設定タブおよび独立ダイアログ (mmdMaterial 管理)
"""

from .common import *

# ==============================================================================
# シェーダー設定タブ (mmdMaterial 管理)
# ==============================================================================
class MaterialTabWidget(QWidget):
    """MMDシェーダー (mmdMaterial) のアサイン・管理タブ"""
    def __init__(self, parent=None):
        super(MaterialTabWidget, self).__init__(parent)
        self.parent_window = parent
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # スクロールエリア（小画面でも見切れを防止）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 14, 14, 14)

        # 対象モデル・メッシュ指定グループ
        target_box = QGroupBox("アサイン対象モデル / メッシュの選択")
        target_layout = QVBoxLayout(target_box)
        target_layout.setSpacing(8)

        h_model = QHBoxLayout()
        h_model.addWidget(QLabel("対象:"))
        self.cbb_target = QComboBox()
        self.btn_refresh = QPushButton("更新")
        self.btn_refresh.setFixedWidth(80)
        self.btn_refresh.clicked.connect(self._refresh_targets)
        h_model.addWidget(self.cbb_target)
        h_model.addWidget(self.btn_refresh)
        target_layout.addLayout(h_model)

        lbl_target_info = QLabel("※「現在選択中のオブジェクト」を選ぶと、ビューポートで選択中の全メッシュが対象になります。")
        lbl_target_info.setStyleSheet("color: #999; font-size: 12px;")
        target_layout.addWidget(lbl_target_info)
        layout.addWidget(target_box)

        # ツール連携 ＆ MMDライティング（横並び統合グループ）
        tool_box = QGroupBox("ツール連携 & MMDライティング")
        tool_layout = QVBoxLayout(tool_box)
        tool_layout.setSpacing(8)

        h_tools = QHBoxLayout()
        h_tools.setSpacing(10)

        self.btn_open_hypershade = QPushButton("Hypershade を開く")
        self.btn_open_hypershade.setFixedHeight(34)
        self.btn_open_hypershade.setToolTip("Hypershade のノード作成ツリー [MmdMat] > [Material] から直接ノードを作成できます。")
        self.btn_open_hypershade.setStyleSheet(
            "QPushButton { background-color: #383838; color: #e0e0e0; border: 1px solid #555; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #484848; color: #ffffff; border-color: #777; }"
        )
        self.btn_open_hypershade.clicked.connect(self._open_hypershade)
        h_tools.addWidget(self.btn_open_hypershade)

        self.btn_create_light = QPushButton("MMD標準ライトを作成 / 最適化")
        self.btn_create_light.setFixedHeight(34)
        self.btn_create_light.setToolTip("MMD公式準拠の平行光源と環境光を作成し、白飛びを防止してビューポート描画を最適化します。")
        self.btn_create_light.setStyleSheet(
            "QPushButton { background-color: #383838; color: #e0e0e0; border: 1px solid #555; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #484848; color: #ffffff; border-color: #777; }"
        )
        self.btn_create_light.clicked.connect(self._create_mmd_lighting)
        h_tools.addWidget(self.btn_create_light)

        self.btn_create_ground_shadow = QPushButton("MMD地面影を作成 / 最適化")
        self.btn_create_ground_shadow.setFixedHeight(34)
        self.btn_create_ground_shadow.setToolTip("Y=0平面上に半透明のシャドウキャッチャー平面を配置し、MMD標準の地面影を再現します。")
        self.btn_create_ground_shadow.setStyleSheet(
            "QPushButton { background-color: #383838; color: #e0e0e0; border: 1px solid #555; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #484848; color: #ffffff; border-color: #777; }"
        )
        self.btn_create_ground_shadow.clicked.connect(self._create_mmd_ground_shadow)
        h_tools.addWidget(self.btn_create_ground_shadow)

        tool_layout.addLayout(h_tools)

        lbl_tool_info = QLabel("※Hypershadeでのノード作成や、MMD標準ライトによるビューポート発色・陰影の最適化を行えます。")
        lbl_tool_info.setStyleSheet("color: #999; font-size: 12px;")
        tool_layout.addWidget(lbl_tool_info)
        layout.addWidget(tool_box)

        # 実行ボタングループ
        act_box = QGroupBox("アサイン実行")
        act_layout = QVBoxLayout(act_box)
        act_layout.setSpacing(8)

        lbl_act_info = QLabel("※既存テクスチャ（fileノード）は自動で引き継がれ、スフィア・Toon未設定時も安全に処理されます。")
        lbl_act_info.setStyleSheet("color: #aaa; font-size: 12px;")
        act_layout.addWidget(lbl_act_info)

        self.btn_assign = QPushButton("MMDシェーダーを選択モデルにアサイン")
        self.btn_assign.setFixedHeight(46)
        self.btn_assign.setStyleSheet(
            "QPushButton { background-color: #1e4d75; color: #e6f3ff; border: 1px solid #2d6ca3; border-radius: 4px; font-weight: bold; font-size: 15px; }"
            "QPushButton:hover { background-color: #276396; color: #ffffff; border-color: #438fcf; }"
            "QPushButton:pressed { background-color: #153856; }"
        )
        self.btn_assign.clicked.connect(self._execute_assign)
        act_layout.addWidget(self.btn_assign)

        self.lbl_result = QLabel("")
        self.lbl_result.setStyleSheet("color: #52b7ff; font-size: 13px; padding: 2px;")
        act_layout.addWidget(self.lbl_result)

        layout.addWidget(act_box)
        layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        self._check_plugin_status()
        self._refresh_targets()

    def _check_plugin_status(self):
        """プラグインのロード状況を確認（互換性のためのスタブ）"""
        pass

    def _refresh_targets(self):
        """対象モデル一覧コンボボックスを更新"""
        self.cbb_target.clear()
        self.cbb_target.addItem("現在選択中のオブジェクト (メッシュ / モデル)", None)
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for m in models:
                self.cbb_target.addItem(f"モデル: {m}", m)
        except Exception:
            pass

    def _open_hypershade(self):
        """MayaのHypershadeウィンドウを開く（コールバックを適用した上で表示）"""
        if mmd_material_setup:
            try:
                mmd_material_setup.ensure_plugin_loaded()
                mmd_material_setup.setup_hypershade_callbacks()
            except Exception:
                pass

        try:
            mel.eval("HypershadeWindow;")
        except Exception as e:
            QMessageBox.warning(self, "Hypershade", f"Hypershadeを開けませんでした:\n{e}")

    def _create_mmd_lighting(self):
        """MMD標準ライティングを作成または最適化"""
        if mmd_material_setup:
            try:
                grp = mmd_material_setup.ensure_mmd_lighting()
                if grp:
                    QMessageBox.information(
                        self,
                        "ライティング",
                        "MMD標準ライティングを作成・適用しました。\n白飛び防止パラメータが適用され、ビューポートのライティングが適正化されました。"
                    )
                else:
                    QMessageBox.warning(self, "ライティング", "ライティングの作成に失敗しました。")
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"ライト作成中にエラーが発生しました:\n{e}")
        else:
            QMessageBox.warning(self, "エラー", "mmd_material_setup モジュールが見つかりません。")

    def _create_mmd_ground_shadow(self):
        """MMD標準地面影プレーンを作成または最適化"""
        try:
            from ..converters import pmxpaimaya
        except Exception:
            try:
                from converters import pmxpaimaya
            except Exception:
                import pmxpaimaya
        try:
            plane = pmxpaimaya.create_mmd_ground_shadow()
            if plane:
                QMessageBox.information(
                    self,
                    "地面影 (Ground Shadow)",
                    f"MMD標準地面影プレーン ({plane}) を作成・適用しました。\nY=0平面に半透明の落ち影が投影されます。"
                )
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"地面影プレーン作成中にエラーが発生しました:\n{e}")

    def _execute_assign(self):
        """選択モデルまたはメッシュに mmdMaterial をアサイン"""
        if not mmd_material_setup:
            QMessageBox.critical(self, "エラー", "mmd_material_setup モジュールが利用できません。")
            return

        selected_model = self.cbb_target.currentData()
        inherit_tex = True

        targets = None
        if selected_model:
            targets = [selected_model]
        else:
            targets = mc.ls(selection=True, long=True) or []
            if not targets:
                QMessageBox.warning(self, "警告", "アサイン対象のオブジェクトまたはメッシュをビューポートで選択してください。")
                return

        try:
            results = mmd_material_setup.assign_mmd_material_to_model(
                targets=targets,
                inherit_textures=inherit_tex
            )

            if results:
                count = len(results)
                msg = f"MMDシェーダーをアサインしました ({count} 個のシェーダー設定完了)。"
                self.lbl_result.setText(f"<span style='color:#55ff77;'>✓ {msg}</span>")
                mc.inViewMessage(
                    amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> {msg}',
                    pos='topCenter',
                    fade=True
                )
            else:
                msg = "アサイン対象のメッシュまたはシェーダーが見つかりませんでした。"
                self.lbl_result.setText(f"<span style='color:#ffaa55;'>! {msg}</span>")
                QMessageBox.information(self, "情報", msg)

        except Exception as e:
            err_msg = f"シェーダーアサイン中にエラーが発生しました:\n{e}"
            self.lbl_result.setText(f"<span style='color:#ff7777;'>✕ エラー</span>")
            QMessageBox.critical(self, "エラー", err_msg)

# ==============================================================================
# MMDシェーダー 独立ダイアログ
# ==============================================================================
class MaterialDialog(QDialog):
    """MMDシェーダー (mmdMaterial) を別ウィンドウで表示するダイアログ"""
    def __init__(self, parent=None):
        super(MaterialDialog, self).__init__(parent)
        self.setWindowTitle("MMDシェーダー")
        self.resize(840, 760)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        self.material_widget = MaterialTabWidget(self)
        main_layout.addWidget(self.material_widget)

        # 下部ボタングループ
        h_bottom = QHBoxLayout()
        h_bottom.addStretch()
        btn_close = QPushButton("閉じる")
        btn_close.setFixedWidth(100)
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.close)
        h_bottom.addWidget(btn_close)
        main_layout.addLayout(h_bottom)
