# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - プラグイン管理タブ
"""

from .common import *

# ==============================================================================
# プラグイン管理タブ (各種プラグインの状態確認・再読み込み)
# ==============================================================================
class PluginTabWidget(QWidget):
    """MMD Tools for Maya で使用する各種 C++ / 物理演算 / シェーダープラグインの管理タブ"""
    def __init__(self, parent=None):
        super(PluginTabWidget, self).__init__(parent)
        self.parent_window = parent
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 14, 14, 14)

        # 高速インポート＆モーション統合プラグイン
        motion_box = QGroupBox("C++ 高速インポート＆モーション統合プラグイン (mmd_fast.mll)")
        motion_layout = QVBoxLayout(motion_box)
        motion_layout.setSpacing(8)

        h_motion = QHBoxLayout()
        self.lbl_motion_status = QLabel()
        self.lbl_motion_status.setWordWrap(True)
        self.lbl_motion_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.btn_reload_motion = QPushButton("プラグイン再読み込み")
        self.btn_reload_motion.setFixedWidth(160)
        self.btn_reload_motion.clicked.connect(self._reload_motion_plugin)
        h_motion.addWidget(self.lbl_motion_status, 1)
        h_motion.addWidget(self.btn_reload_motion, 0, Qt.AlignTop)
        motion_layout.addLayout(h_motion)

        lbl_motion_info = QLabel(
            "・PMX メッシュ一括生成・スキニングウェイト一括適用・ブレンドシェイプ高速登録\n"
            "・VMD ボーン（並列ベジェ計算）・モーフ・カメラキーフレーム一括注入および物理ベイク (mmdFastBakeBone) を統合した C++ プラグインです。"
        )
        lbl_motion_info.setWordWrap(True)
        lbl_motion_info.setStyleSheet("color: #999; font-size: 12px;")
        motion_layout.addWidget(lbl_motion_info)
        layout.addWidget(motion_box)

        # 物理演算プラグイン (Bullet / XPBD)
        physics_box = QGroupBox("物理演算プラグイン (Bullet / XPBD)")
        physics_layout = QVBoxLayout(physics_box)
        physics_layout.setSpacing(8)

        self.lbl_bullet_status = QLabel()
        self.lbl_bullet_status.setWordWrap(True)
        physics_layout.addWidget(self.lbl_bullet_status)

        self.lbl_xpbd_status = QLabel()
        self.lbl_xpbd_status.setWordWrap(True)
        physics_layout.addWidget(self.lbl_xpbd_status)

        self.lbl_viewer_status = QLabel()
        self.lbl_viewer_status.setWordWrap(True)
        physics_layout.addWidget(self.lbl_viewer_status)

        h_phys_action = QHBoxLayout()
        h_phys_action.addStretch()
        self.btn_reload_physics = QPushButton("物理プラグイン再読み込み")
        self.btn_reload_physics.setFixedWidth(180)
        self.btn_reload_physics.clicked.connect(self._reload_physics_plugins)
        h_phys_action.addWidget(self.btn_reload_physics)
        physics_layout.addLayout(h_phys_action)

        lbl_phys_info = QLabel(
            "・Bullet Physics (mmd_bullet.dll): 本家MMD準拠の剛体シミュレーション機能です。\n"
            "・XPBD Physics (mmd_xpbd.dll): 位置ベース物理による高速かつ安定したソルバー機能です。\n"
            "・物理演算ベイクプレビューア (PhysicsSimulationBakeViewer.exe): WPF3Dによるリアルタイム物理シミュレーションで柔らかくしなやかな剛体挙動とMayaへの同期ベイク機能です。"
        )
        lbl_phys_info.setWordWrap(True)
        lbl_phys_info.setStyleSheet("color: #999; font-size: 12px; line-height: 1.4;")
        physics_layout.addWidget(lbl_phys_info)
        layout.addWidget(physics_box)

        # MMD統合マテリアル & 独自レンダラープラグイン
        mat_box = QGroupBox("MMD統合マテリアル & 独自レンダラープラグイン (mmd_material.mll)")
        mat_layout = QVBoxLayout(mat_box)
        mat_layout.setSpacing(8)

        h_mat = QHBoxLayout()
        self.lbl_mat_status = QLabel()
        self.lbl_mat_status.setWordWrap(True)
        self.lbl_mat_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.btn_reload_mat = QPushButton("プラグイン再読み込み")
        self.btn_reload_mat.setFixedWidth(160)
        self.btn_reload_mat.clicked.connect(self._reload_material_plugin)
        h_mat.addWidget(self.lbl_mat_status, 1)
        h_mat.addWidget(self.btn_reload_mat, 0, Qt.AlignTop)
        mat_layout.addLayout(h_mat)

        lbl_mat_info = QLabel(
            "・mmdMaterial / mmdToonShader: Viewport 2.0上でMMD本家準拠のToon陰影・セルフシャドウ・スフィアマップをリアルタイム描画します。\n"
            "・MMD Viewport Renderer: エッジ描画パス (MMDEdgeScenePass) による同一メッシュ方式の輪郭線描画、Object Sorting透過合成、白背景表示を統合した独自レンダラーです。\n"
            "・MMD Renderer: Render Viewおよびバッチレンダリングに対応したオフスクリーン描画機能 (mmdRender) を提供します。"
        )
        lbl_mat_info.setWordWrap(True)
        lbl_mat_info.setStyleSheet("color: #999; font-size: 12px; line-height: 1.4;")
        mat_layout.addWidget(lbl_mat_info)
        layout.addWidget(mat_box)

        # プラグイン一括再読み込み
        all_box = QGroupBox("プラグイン一括管理")
        all_layout = QVBoxLayout(all_box)
        all_layout.setSpacing(8)
        self.btn_reload_all = QPushButton("各プラグインを一括再読み込み")
        self.btn_reload_all.setFixedHeight(38)
        self.btn_reload_all.setStyleSheet(
            "QPushButton { background-color: #2b4c6f; color: #ffffff; border-radius: 4px; font-weight: bold; font-size: 13px; }"
            "QPushButton:hover { background-color: #38618d; }"
        )
        self.btn_reload_all.clicked.connect(self._reload_all_plugins)
        all_layout.addWidget(self.btn_reload_all)

        self.btn_enable_autoload_all = QPushButton("各プラグインの自動ロードを設定 (Auto Load ON)")
        self.btn_enable_autoload_all.setFixedHeight(34)
        self.btn_enable_autoload_all.setStyleSheet(
            "QPushButton { background-color: #2d5a3f; color: #ffffff; border-radius: 4px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background-color: #3b7552; }"
        )
        self.btn_enable_autoload_all.clicked.connect(self._enable_all_autoload)
        all_layout.addWidget(self.btn_enable_autoload_all)
        layout.addWidget(all_box)

        layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        self.refresh_all_status()

    def refresh_all_status(self):
        """各プラグインの状態表示を最新化"""
        self._check_motion_status()
        self._check_physics_status()
        self._check_material_status()

    def _check_motion_status(self):
        loaded = False
        try:
            if hasattr(mc, "mmdFastImportPmxMesh") and hasattr(mc, "mmdFastBakeBone"):
                loaded = True
            elif any("mmd_fast" in p.lower() for p in (mc.pluginInfo(query=True, listPlugins=True) or [])):
                loaded = True
            elif mc.pluginInfo("mmd_fast.mll", query=True, loaded=True) or mc.pluginInfo("mmd_fast", query=True, loaded=True):
                loaded = True
        except Exception:
            pass

        motion_autoload = False
        if loaded:
            try:
                motion_autoload = mc.pluginInfo("mmd_fast.mll", query=True, autoload=True) or mc.pluginInfo("mmd_fast", query=True, autoload=True)
            except Exception:
                motion_autoload = False
            if not motion_autoload:
                try:
                    mc.pluginInfo("mmd_fast.mll", edit=True, autoload=True)
                    motion_autoload = True
                except Exception:
                    try:
                        mc.pluginInfo("mmd_fast", edit=True, autoload=True)
                        motion_autoload = True
                    except Exception:
                        pass

        if loaded:
            auto_str = " (自動ロード: 有効)" if motion_autoload else ""
            self.lbl_motion_status.setText(f"<span style='color:#55ff77; font-weight:bold;'>● プラグイン読み込み済み (mmd_fast.mll{auto_str})</span>")
        else:
            self.lbl_motion_status.setText("<span style='color:#ff7777; font-weight:bold;'>○ プラグイン未読み込み (mmd_fast.mll)</span>")

    def _check_physics_status(self):
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Bullet 物理エンジン
        bullet_labels = {
            "mmd_bullet_275.dll": "2.75",
            "mmd_bullet_283.dll": "2.83",
            "mmd_bullet.dll": "標準",
        }
        bullet_found = []
        for b_name in ["mmd_bullet_275.dll", "mmd_bullet_283.dll", "mmd_bullet.dll"]:
            candidates = [
                os.path.join(plugin_root, "physics", "bullet_engine", "bin", b_name),
                os.path.join(plugin_root, "bullet_engine", "bin", b_name),
            ]
            for p in candidates:
                if os.path.exists(p) and b_name not in bullet_found:
                    bullet_found.append(b_name)

        if bullet_found:
            short_names = " / ".join(bullet_labels.get(n, n) for n in bullet_found)
            self.lbl_bullet_status.setText(f"<span style='color:#55ff77; font-weight:bold;'>● Bullet 物理エンジン: 利用可能 ({short_names})</span>")
            self.lbl_bullet_status.setToolTip("検出されたファイル:\n" + "\n".join(bullet_found))
        else:
            self.lbl_bullet_status.setText("<span style='color:#ffaa55; font-weight:bold;'>△ Bullet 物理エンジン: 未検出</span>")
            self.lbl_bullet_status.setToolTip("対象ファイル:\nmmd_bullet_275.dll\nmmd_bullet_283.dll\nmmd_bullet.dll")

        # XPBD 物理エンジン
        xpbd_ok = False
        try:
            candidates = [
                os.path.join(plugin_root, "physics", "cpp_engine", "bin", "mmd_xpbd.dll"),
                os.path.join(plugin_root, "cpp_engine", "bin", "mmd_xpbd.dll"),
            ]
            xpbd_ok = any(os.path.exists(p) for p in candidates)
        except Exception:
            pass

        if xpbd_ok:
            self.lbl_xpbd_status.setText("<span style='color:#55ff77; font-weight:bold;'>● XPBD 物理エンジン: 利用可能 (mmd_xpbd.dll)</span>")
            self.lbl_xpbd_status.setToolTip("検出されたファイル:\nmmd_xpbd.dll")
        else:
            self.lbl_xpbd_status.setText("<span style='color:#ffaa55; font-weight:bold;'>△ XPBD 物理エンジン: 未検出 (mmd_xpbd.dll)</span>")
            self.lbl_xpbd_status.setToolTip("対象ファイル:\nmmd_xpbd.dll")

        # 新3D物理ベイクビューア (PhysicsSimulationBakeViewer.exe)
        viewer_labels = {
            "PhysicsSimulationBakeViewer_275.exe": "2.75",
            "PhysicsSimulationBakeViewer_283.exe": "2.83",
            "PhysicsSimulationBakeViewer.exe": "標準",
            "PhysicsSimulationBakeViewerGpu.exe": "GPU",
        }
        viewer_found = []
        for v_name in ["PhysicsSimulationBakeViewer_275.exe", "PhysicsSimulationBakeViewer_283.exe", "PhysicsSimulationBakeViewer.exe", "PhysicsSimulationBakeViewerGpu.exe"]:
            for cfg in ["Release", "Debug"]:
                candidates = [
                    os.path.join(plugin_root, "physics", "physics_bake_cs", "bin", cfg, "net8.0-windows", v_name),
                    os.path.join(plugin_root, "physics", "physics_bake_gpu_cs", "bin", cfg, "net8.0-windows", v_name),
                    os.path.join(plugin_root, "physics_bake_cs", "bin", cfg, "net8.0-windows", v_name),
                    os.path.join(plugin_root, "physics_bake_gpu_cs", "bin", cfg, "net8.0-windows", v_name),
                ]
                for v_path in candidates:
                    if os.path.exists(v_path) and v_name not in viewer_found:
                        viewer_found.append(v_name)

        if not viewer_found:
            try:
                from ..maya_converters import physics_stream
                v_exe = physics_stream.get_viewer_executable_path()
                if os.path.exists(v_exe):
                    viewer_found.append(os.path.basename(v_exe))
            except Exception:
                try:
                    from maya_converters import physics_stream
                    v_exe = physics_stream.get_viewer_executable_path()
                    if os.path.exists(v_exe):
                        viewer_found.append(os.path.basename(v_exe))
                except Exception:
                    pass

        if viewer_found:
            short_viewers = " / ".join(viewer_labels.get(n, os.path.splitext(n)[0]) for n in viewer_found)
            self.lbl_viewer_status.setText(f"<span style='color:#55ff77; font-weight:bold;'>● 物理演算ベイクビューア: 利用可能 ({short_viewers})</span>")
            self.lbl_viewer_status.setToolTip("実行環境: .NET 8 WPF\n検出されたファイル:\n" + "\n".join(viewer_found))
        else:
            self.lbl_viewer_status.setText("<span style='color:#ffaa55; font-weight:bold;'>△ 物理演算ベイクビューア: 未検出 (physics_bake_cs をビルドしてください)</span>")
            self.lbl_viewer_status.setToolTip(
                "対象ファイル (.NET 8 WPF):\n"
                "PhysicsSimulationBakeViewer_275.exe\n"
                "PhysicsSimulationBakeViewer_283.exe\n"
                "PhysicsSimulationBakeViewer.exe\n"
                "PhysicsSimulationBakeViewerGpu.exe"
            )

    def _check_material_status(self):
        """MMD統合プラグイン (mmd_material.mll) および内包機能のロード状態を判定"""
        mll_loaded = False
        try:
            if mc.pluginInfo("mmd_material.mll", query=True, loaded=True) or mc.pluginInfo("mmd_material", query=True, loaded=True):
                mll_loaded = True
            elif any("mmd_material" in p.lower() for p in (mc.pluginInfo(query=True, listPlugins=True) or [])):
                mll_loaded = True
            elif "mmdToonShader" in (mc.allNodeTypes() or []) or "mmdMaterial" in (mc.allNodeTypes() or []):
                mll_loaded = True
        except Exception:
            pass

        mll_autoload = False
        if mll_loaded:
            try:
                mll_autoload = mc.pluginInfo("mmd_material.mll", query=True, autoload=True) or mc.pluginInfo("mmd_material", query=True, autoload=True)
            except Exception:
                mll_autoload = False
            if not mll_autoload:
                try:
                    mc.pluginInfo("mmd_material.mll", edit=True, autoload=True)
                    mll_autoload = True
                except Exception:
                    try:
                        mc.pluginInfo("mmd_material", edit=True, autoload=True)
                        mll_autoload = True
                    except Exception:
                        pass

        # 内包機能の認識状況をチェック
        all_nodes = set(mc.allNodeTypes() or [])
        has_mat_node = "mmdMaterial" in all_nodes
        has_toon_node = "mmdToonShader" in all_nodes

        has_renderer = False
        try:
            if mel.eval('renderer -exists "mmdRenderer";') == 1:
                has_renderer = True
        except Exception:
            pass

        status_parts = []
        if mll_loaded:
            auto_str = " (自動ロード: 有効)" if mll_autoload else " (自動ロード: 無効)"
            status_parts.append(f"<span style='color:#55ff77; font-weight:bold;'>● プラグイン読み込み済み (mmd_material.mll{auto_str})</span>")

            # 内包コンポーネントの内訳表示
            components = []
            components.append(f"mmdMaterial ({'有効' if has_mat_node else '未検出'})")
            components.append(f"mmdToonShader ({'有効' if has_toon_node else '未検出'})")
            components.append(f"MMD Renderer ({'登録済み' if has_renderer else '未登録'})")
            comp_str = " / ".join(components)
            status_parts.append(f"<span style='color:#bbb; font-size:12px;'>　内包機能: {comp_str}</span>")
        else:
            status_parts.append("<span style='color:#ff7777; font-weight:bold;'>○ プラグイン未読み込み (mmd_material.mll)</span>")
            status_parts.append("<span style='color:#888; font-size:12px;'>　※Toonシェーダー・マテリアル・独自レンダラーを含む統合プラグインです</span>")

        self.lbl_mat_status.setText("<br>".join(status_parts))

    def _reload_motion_plugin(self):
        """高速インポート＆モーション統合プラグイン (mmd_fast.mll) を安全に再読み込み"""
        # 旧 mmd_motion が残っている場合はアンロード & 自動ロード解除
        for old_p in ["mmd_motion", "mmd_motion.mll"]:
            try:
                if mc.pluginInfo(old_p, query=True, loaded=True):
                    mc.pluginInfo(old_p, edit=True, autoload=False)
                    mc.unloadPlugin(old_p, force=True)
            except Exception:
                pass

        # 既存の mmd_fast をアンロード
        for fp in ["mmd_fast", "mmd_fast.mll"]:
            try:
                if mc.pluginInfo(fp, query=True, loaded=True):
                    mc.unloadPlugin(fp, force=True)
            except Exception:
                pass

        # プラグインパスを特定して新規ロード
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        maya_ver = "2025"
        try:
            ver_str = str(mc.about(version=True))
            m = re.search(r"20\d{2}", ver_str)
            if m:
                maya_ver = m.group(0)
        except Exception:
            pass

        candidates = [
            os.path.join(plugin_root, "plugins", "mmd_fast_plugin", "bin", maya_ver, "mmd_fast.mll"),
            os.path.join(plugin_root, "plugins", "mmd_fast_plugin", "bin", "mmd_fast.mll"),
            os.path.join(plugin_root, "plugins", "mmd_fast_plugin", "bin", "2025", "mmd_fast.mll"),
            os.path.join(plugin_root, "mmd_fast_plugin", "bin", maya_ver, "mmd_fast.mll"),
            os.path.join(plugin_root, "mmd_fast_plugin", "bin", "mmd_fast.mll"),
            os.path.join(plugin_root, "mmd_fast_plugin", "bin", "2025", "mmd_fast.mll"),
        ]

        load_err = None
        success = False
        for mll_path in candidates:
            if os.path.exists(mll_path):
                try:
                    mc.loadPlugin(mll_path)
                    if hasattr(mc, "mmdFastImportPmxMesh"):
                        try:
                            mc.pluginInfo(mll_path, edit=True, autoload=True)
                            mc.pluginInfo("mmd_fast", edit=True, autoload=True)
                            mc.pluginInfo("mmd_fast.mll", edit=True, autoload=True)
                        except Exception:
                            pass
                        success = True
                        break
                except Exception as e:
                    load_err = e

        self._check_motion_status()
        if success:
            QMessageBox.information(self, "プラグイン", "MMD高速化プラグイン (mmd_fast.mll) が正常に再読み込みされ、自動ロードが設定されました。")
        else:
            err_msg = f": {load_err}" if load_err else ""
            QMessageBox.warning(self, "プラグイン", f"MMD高速化プラグイン (mmd_fast.mll) の再読み込みに失敗しました{err_msg}。")

    def _reload_physics_plugins(self):
        self._check_physics_status()
        QMessageBox.information(self, "物理プラグイン", "物理演算ライブラリ (Bullet / XPBD) の状態を更新しました。")

    def _ensure_toon_shader_loaded(self):
        """後方互換用: 統合プラグイン (mmd_material.mll) のロードを保証"""
        if mmd_material_setup:
            try:
                return mmd_material_setup.ensure_plugin_loaded()
            except Exception:
                pass
        return False

    def _reload_material_plugin(self):
        success = False
        if mmd_material_setup:
            try:
                success = mmd_material_setup.ensure_plugin_loaded()
                if success:
                    try:
                        mc.pluginInfo("mmd_material", edit=True, autoload=True)
                    except Exception:
                        pass
                    try:
                        mc.pluginInfo("mmd_material.mll", edit=True, autoload=True)
                    except Exception:
                        pass
            except Exception:
                pass

        self._check_material_status()

        if success:
            QMessageBox.information(
                self,
                "プラグイン",
                "MMD統合プラグイン (mmd_material.mll) が正常にロードされ、自動ロードが設定されました。\n(mmdMaterial / mmdToonShader / MMD Renderer を一括有効化)"
            )
        else:
            QMessageBox.warning(self, "プラグイン", "MMD統合プラグイン (mmd_material.mll) のロードに失敗しました。")

    def _enable_all_autoload(self):
        """各MMDプラグインの自動ロードフラグを設定"""
        target_plugins = [
            "mmd_material", "mmd_material.mll",
            "mmd_fast", "mmd_fast.mll",
        ]
        count = 0
        for p in target_plugins:
            try:
                if mc.pluginInfo(p, query=True, loaded=True):
                    mc.pluginInfo(p, edit=True, autoload=True)
                    count += 1
            except Exception:
                pass
        self.refresh_all_status()
        QMessageBox.information(
            self,
            "自動ロード設定",
            "ロード済みの各プラグインに対して自動ロード (Auto Load) 設定を有効化しました。"
        )

    def _reload_all_plugins(self):
        # 高速インポート＆モーション統合プラグイン
        try:
            from ..physics.bullet_engine import bullet_maya_bridge
        except Exception:
            try:
                from ..bullet_engine import bullet_maya_bridge
            except Exception:
                try:
                    from bullet_engine import bullet_maya_bridge
                except Exception:
                    bullet_maya_bridge = None
        if bullet_maya_bridge:
            bridge = bullet_maya_bridge.BulletMayaBridge.__new__(bullet_maya_bridge.BulletMayaBridge)
            bridge._ensure_motion_plugin_loaded()
            try:
                mc.pluginInfo("mmd_fast", edit=True, autoload=True)
            except Exception:
                pass
            try:
                mc.pluginInfo("mmd_fast.mll", edit=True, autoload=True)
            except Exception:
                pass

        # MMD統合マテリアル & 独自レンダラープラグイン
        if mmd_material_setup:
            try:
                mmd_material_setup.ensure_plugin_loaded()
                try:
                    mc.pluginInfo("mmd_material", edit=True, autoload=True)
                except Exception:
                    pass
                try:
                    mc.pluginInfo("mmd_material.mll", edit=True, autoload=True)
                except Exception:
                    pass
            except Exception:
                pass

        self.refresh_all_status()
        QMessageBox.information(self, "プラグイン一括再読み込み", "各プラグインの再読み込みおよび自動ロード設定を終了しました。")
