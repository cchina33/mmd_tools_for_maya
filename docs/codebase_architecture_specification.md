# コードベース構成・各モジュール仕様書

> [!NOTE]
> 本詳細技術仕様書は、AI によって作成・整理されたドキュメントです。内容はソースコードおよび開発記録をもとに記述していますが、実際の動作と細部が異なる場合があります。

本ドキュメントは、「MMD Tools for Maya」プロジェクトを構成する各ディレクトリ、Python スクリプト、C++ 物理/シェーダープラグイン、C# 外部物理ビューア、および各モジュールの責務と仕様を詳細に解説する仕様書です。

```text
mmd_tools_for_maya/
├── mmd_tools_for_maya_plugin.py      # Mayaプラグイン公式エントリポイント (MMDメニュー & 上級者メニュー)
├── __init__.py                       # パッケージ初期化＆後方互換透過エクスポート
├── README.md                         # プロジェクト概要・導入手順
├── LICENSE                           # MITライセンス条項
│
├── ui/                               # 統合UIパッケージ (PySide6 / PySide2 互換)
│   ├── __init__.py                   # UIエクスポート定義
│   ├── gui.py                        # メインウィンドウ統合エントリ (MMDToolsMainWindow, show_ui)
│   ├── gui_style.py                  # 共通ダークテーマスタイルシート (QSS)
│   ├── common.py                     # Qt互換インポート・共通ログ・ユーティリティ (ExecutionLogDialog)
│   ├── tab_import.py                 # モデルインポートタブ (PMX/PMD/X・設定・解析連携)
│   ├── tab_easy_import.py            # 簡単インポートタブ (ワンクリックシンプル導入)
│   ├── tab_vmd.py                    # VMDモーションインポートタブ (ボーン・モーフ・カメラ・音声)
│   ├── tab_material.py               # シェーダー設定タブ (Toon/Sphere・マテリアル保護)
│   ├── tab_physics.py                # 物理演算タブ (Bullet/XPBD/外部ビューア連携)
│   ├── tab_export.py                 # エクスポートタブ (PMX/VMD/VPD一元集約)
│   ├── tab_hik.py                    # HumanIK管理タブ (キャラクター定義・リグ展開)
│   ├── tab_extra.py                  # その他機能タブ (地面影・照明操作・モデル判定・VPD)
│   ├── tab_plugin.py                 # プラグイン管理タブ (mll/C++/C#バイナリ管理)
│   ├── tab_cleanup.py                # MMD削除・クリーンアップタブ (要素別一括消去)
│   ├── dialog_edge_control.py        # MMDエッジ太さリアルタイム操作GUIダイアログ
│   ├── dialog_light_control.py       # MMD照明操作ダイアログ (影向きXYZ・RGBカラー)
│   ├── dialog_model_classifier.py    # モデル種別判定・個別指定設定ダイアログ
│   ├── dialog_physics_model_select.py# 物理演算対象モデル選択ダイアログ
│   ├── morph_window.py               # 表情・モーフ操作GUI (4分割パネル・材質モーフ連動)
│   ├── pmm_dialog.py                 # PMMプロジェクト解析・モデル選択インポート
│   ├── multi_model_dialog.py         # 複数モデル一括順次インポートダイアログ
│   ├── accessory_dialog.py           # アクセサリ追従アタッチダイアログ
│   ├── advanced_dict_dialog.py       # 高度なユーザー辞書・マテリアル保護設定GUI
│   ├── user_dict_dialog.py           # 未登録ボーン名検出・対話型辞書登録ダイアログ
│   ├── material_protect_dialog.py    # マテリアル保護キーワード管理GUI
│   ├── bone_state_export_dialog.py   # ボーン状態・トランスフォーム情報エクスポートGUI
│   └── experimental_dialog.py        # 試験的機能ダイアログ
│
├── ui_editor/                        # MMD Model Editor 独立設定画面パッケージ (PySide6 / PySide2 互換)
│   ├── __init__.py                   # パッケージエクスポート定義
│   ├── editor_window.py              # MMD Model Editor メインウィンドウ基底 (MmdModelEditorWindow, show_model_editor)
│   ├── tab_info_editor.py            # 情報管理タブ (モデル名・英名・コメント・要素統計サマリー)
│   ├── tab_vertex_editor.py          # 頂点管理タブ (座標・法線・UV・ウェイト配分・ページング表示)
│   ├── tab_face_editor.py            # 面管理タブ (面インデックス・構成頂点・所属材質別フィルタ)
│   ├── tab_material_editor.py        # 材質管理タブ (一覧表示・色/輪郭線/テクスチャ/フラグ編集・シーン同期)
│   ├── tab_bone_editor.py            # ボーン管理タブ (一覧表示・属性確認・未生成時の後付け作成・バインド)
│   ├── tab_morph_editor.py           # モーフ管理タブ (モーフ一覧・カテゴリ絞り込み・リアルタイムウェイト操作)
│   ├── tab_rigidbody_editor.py       # 剛体管理タブ (剛体一覧・衝突グループ・形状サイズ・物理特性編集)
│   ├── tab_joint_editor.py           # Joint管理タブ (剛体間拘束一覧・接続・移動/回転制限・ばね定数編集)
│   ├── tab_modification_editor.py    # 改造・お着替えタブ (開発中・既定非表示フラグ制御)
│   ├── dialog_terms_confirm.py       # 改造前のモデル利用規約確認ダイアログ
│   ├── dialog_material_filter.py     # 材質別マスキング表示・パーツ削除ダイアログ
│   └── dialog_bone_physics_filter.py # ボーン・剛体絞り込み・削除ダイアログ (キャラ別/両方表示対応)
│
├── ui_other_importer/                # その他モデルインポーターUIパッケージ (VRM等・試験的機能)
│   ├── __init__.py                   # パッケージエクスポート定義
│   ├── importer_window.py            # その他モデルインポーター統合ウィンドウ (OtherModelImporterWindow)
│   ├── tab_vrm_importer.py           # VRMモデル専用インポートタブ (メタデータ・サムネイル表示・設定)
│   └── tab_cleanup.py                # 外部モデルおよび関連ノード一括消去タブ
│
├── other_converters/                 # 外部モデルフォーマット解析・構築パッケージ (VRM等)
│   ├── __init__.py                   # コンバータエクスポート定義
│   └── vrm_importer.py               # VRM (glTF 2.0 GLB: 0.x / 1.0) 解析・Maya構築エンジン
│
├── maya_converters/                  # Maya ↔ MMD 相互変換・解析エンジンパッケージ
│   ├── __init__.py                   # コンバータエクスポート定義
│   ├── pmxpaimaya.py                 # MMDモデルインポートエンジン (メッシュ/マテリアル/IK/地面影)
│   ├── vmdpaimaya.py                 # MMDモーション(VMD)アニメーション適用エンジン
│   ├── mayapaipmx.py                 # MayaシーンからPMXへのエクスポートエンジン
│   ├── pmd2pmx.py                    # PMDからPMXへの自動変換エンジン (剛体・ジョイント対応)
│   ├── physics_stream.py             # 外部C#物理ビューア連携・リアルタイムストリーミング＆ベイク
│   ├── vmd_analyzer.py               # VMDモーション構造解析・診断モジュール
│   ├── bullet_builder.py             # 剛体構築補助モジュール
│   ├── edge_mesh_builder.py          # 反転法線押し出し (Inverted Hull) エッジメッシュ生成エンジン
│   ├── mmd_edge_bake.py              # 材質エッジ倍率の頂点カラー (mmd_edge_scale) 焼き込みモジュール
│   ├── mesh_mask_utils.py            # 材質別マスキング表示・頂点再マッピングパーツ削除・不要モーフ掃除
│   ├── model_modifier.py             # モデル改造・汎用パーツ移植統合ファサード
│   └── dressup/                      # モデル改造・汎用パーツ移植コアサブパッケージ
│       ├── __init__.py               # サブパッケージエクスポート定義
│       ├── skin_utils.py             # APIスキンウェイト取得/復元・シーンキャッシュ・Undo・ボーン表示切替
│       ├── align.py                  # 基準ボーン選択式位置合わせ・スケール推定・バインドポーズ再設定
│       ├── part_split.py             # ウェイト基準パーツ分類補助モジュール
│       ├── neck_seam.py              # 非結合方式の首境界スナップ・法線平均化・ウェイト整合
│       ├── bone_merge.py             # 標準/ユーザー辞書によるボーン統合・固有ボーン移植
│       ├── physics_merge.py          # 剛体・Joint番号振り直し・制約再接続・衝突グループ解析
│       └── validate.py               # 書き出し前6項目診断・PMX BDEF4上限正規化
│
├── mmd_parser/                       # 自作MMDバイナリ/テキスト構文解析パッケージ (MIT)
│   ├── __init__.py                   # パッケージエクスポート定義
│   ├── pmx.py                        # PMX 2.0 / 2.1 パーサー & ライター (推奨標準フォーマット)
│   ├── vmd.py                        # VMD モーションパーサー
│   ├── vpd.py                        # VPD ポーズパーサー
│   ├── pmm.py                        # PMM (Polygon Movie Maker) プロジェクト解析
│   ├── pmd.py                        # PMD (旧形式) パーサー & PMX自動変換
│   └── x_file.py                     # DirectX (.x) 構文解析器
│
├── asset/                            # 辞書データ・設定管理補助モジュール
│   ├── __init__.py                   # アセット初期化
│   ├── model_classifier_manager.py   # モデル種別判定・個別指定設定マネージャ
│   ├── user_dict_manager.py          # ユーザー辞書・マテリアル保護設定管理モジュール
│   ├── bone_dict.py                  # 標準ボーン日英相互変換モジュール (ユーザー辞書連動)
│   ├── jaka.py                       # 日本語/中国語ノード名のローマ字変換 & 正常化
│   ├── hik.py                        # HumanIK (HIK) ボーン定義マッピング
│   └── dictionary/                   # 辞書・標準設定ファイル管理ディレクトリ (階層分離)
│       ├── default/                  # 開発者提供の標準辞書・設定群
│       │   ├── bone_dict.json        # MMD標準・準標準ボーン（厳選78本）定義JSON
│       │   ├── default_model_dictionary.json # 抽出・解析および移行統合されたモデル拡張ボーン/モーフ辞書（ボーン7,125件、モーフ1,275件）
│       │   ├── hik_dict.json         # HIKボーンマッピング定義JSON
│       │   ├── jaka_dict.json        # ローマ字変換定義JSON
│       │   ├── model_classifier_settings.json # モデル種別自動判別キーワード既定設定
│       │   ├── morph_dict.json       # 標準モーフ辞書JSON
│       │   └── user_dictionary.json  # 標準設定永続化ファイル
│       └── user/                     # ユーザー追加・編集用カスタム辞書・設定格納ディレクトリ (.gitignore除外)
│
├── toon/                             # MMD標準トゥーンテクスチャ
│   └── toon01.bmp ～ toon10.bmp      # 各階調用標準BMPテクスチャ群
│
├── physics/                          # 物理演算統合パッケージ
│   ├── __init__.py                   # 物理モジュール統合エントリ
│   │
│   ├── bullet_engine/                # MMD本家 Bullet 2.83.7 物理演算エンジン (zlib license)
│   │   ├── __init__.py               # Bullet エンジンパッケージ初期化
│   │   ├── bin/
│   │   │   └── mmd_bullet.dll        # コンパイル済み Bullet 物理エンジンDLL
│   │   ├── include/                  # Bullet C++ ヘッダー群
│   │   ├── src/                      # Bullet C++ ソース群 & C-API エクスポートラッパー
│   │   ├── build_bullet_dll.py       # MSVC / MinGW 自動検出 DLL ビルドスクリプト
│   │   ├── bullet_wrapper.py         # ctypes による Bullet DLL Python バインディング
│   │   ├── bullet_maya_bridge.py     # Bullet 物理シミュレーション・Maya ベイク制御エンジン
│   │   ├── LICENSE                   # Bullet 公式 zlib ライセンス条項
│   │   └── README.md                 # Bullet エンジン概要・ビルド手順
│   │
│   ├── cpp_engine/                   # C++ XPBD 物理演算エンジン (MIT)
│   │   ├── bin/
│   │   │   └── mmd_xpbd.dll          # コンパイル済みXPBD物理エンジンDLL
│   │   ├── include/
│   │   │   └── xpbd_engine.h         # XPBDエンジンヘッダー
│   │   ├── src/
│   │   │   └── xpbd_engine.cpp       # XPBDエンジン実装
│   │   ├── build_dll.py              # MSVC / MinGW 自動検出DLLビルドスクリプト
│   │   ├── xpbd_wrapper.py           # ctypes による C++ DLL Pythonバインディング
│   │   ├── xpbd_visualizer.py        # Maya上のメッシュ・Jointロケーター追従・再吸着
│   │   ├── xpbd_maya_bridge.py       # シミュレーションベイク制御エンジン
│   │   └── test_xpbd.py              # XPBDエンジンスタンドアロン単体テスト
│   │
│   ├── physics_bake_cs/              # MMD物理演算リアルタイムベイクアプリ (CPU) (C# / .NET 8 / WPF 3D)
│   │   ├── bin/Release/net8.0-windows/ # 実行可能バイナリ群 (PhysicsSimulationBakeViewer_275.exe 等)
│   │   ├── App.xaml / App.xaml.cs    # アプリケーションエントリ
│   │   ├── ViewerWindow.xaml / .cs   # 物理シミュレーション同期描画ウィンドウ
│   │   ├── PoseEvaluator.cs          # ボーンポーズ・物理挙動リアルタイム評価
│   │   └── PhysicsSimulationBakeViewer.csproj # プロジェクト定義
│   │
│   ├── physics_bake_gpu_cs/          # MMD物理演算リアルタイムベイクアプリ (ハードウェアベイク(GPU)) (C# / .NET 8 / C++ / CUDA)
│   │   ├── bin/Release/net8.0-windows/ # 実行可能バイナリ群 (PhysicsSimulationBakeViewerGpu.exe)
│   │   ├── CudaPhysicsNative.cs      # C++ / CUDA ネイティブ DLL との P/Invoke 相互運用
│   │   ├── native_cuda/              # NVIDIA GPU 汎用対応 C++ / CUDA ネイティブ DLL (mmd_physics_cuda.dll)
│   │   │   └── build_cuda.py         # CUDA ネイティブ DLL ビルドスクリプト
│   │   └── PhysicsSimulationBakeViewerGpu.csproj # プロジェクト定義
│   │
│   └── physics_bridge_cs/            # MMD物理演算シミュレーションビューア (C# / .NET 8 / WPF)
│       ├── bin/Release/net8.0-windows/ # 実行可能バイナリ群 (MmdPhysicsBridge.exe)
│       ├── MainWindow.xaml / .cs     # ビューア操作・描画画面
│       ├── PhysicsSimulationEngine.cs # BulletSharp 物理シミュレーションコア
│       ├── PmxLoader.cs / VmdLoader.cs # 高速 PMX / VMD 読み込みモジュール
│       └── MmdPhysicsBridge.csproj   # プロジェクト定義
│
├── plugins/                          # C++ プラグイン統合パッケージ
│   ├── __init__.py                   # プラグインパッケージ初期化エントリ
│   │
│   ├── mmd_material_plugin/          # MMD専用シェーダー C++ プラグイン (Viewport 2.0 対応)
│   │   ├── bin/
│   │   │   ├── 2025/mmd_material.mll # Maya 2025 用コンパイル済みシェーダープラグイン
│   │   │   ├── 2026/mmd_material.mll # Maya 2026 用コンパイル済みシェーダープラグイン
│   │   │   └── mmd_material.mll      # 標準リンク用シェーダープラグイン
│   │   ├── shaders/
│   │   │   └── mmd_material.fx       # Viewport 2.0 (DirectX 11) HLSL シェーダー
│   │   ├── src/                      # シェーダーノードおよび描画オーバーライド実装
│   │   ├── scripts/
│   │   │   ├── mmd_material_setup.py # シェーダーネットワーク自動構築・アサインスクリプト
│   │   │   └── mmd_edge_bake.py      # 頂点カラーエッジ倍率ベイクスクリプト (ステージ除外対応)
│   │   ├── CMakeLists.txt            # ビルド定義
│   │   └── README.md                 # シェーダープラグインビルド・運用手順
│   │
│   ├── mmd_fast_plugin/              # 高速インポート＆モーション・ベイク統合 C++ プラグイン
│   │   ├── bin/
│   │   │   ├── 2025/mmd_fast.mll     # Maya 2025 用コンパイル済み高速化プラグイン
│   │   │   └── mmd_fast.mll          # 標準リンク用高速化プラグイン
│   │   ├── src/                      # PMX/VMD 高速パーサー・キーフレーム並列注入ソース群
│   │   ├── include/                  # C++ ヘッダー群
│   │   └── CMakeLists.txt            # ビルド定義
│   │
│   └── mmd_motion_plugin/            # 旧高速モーション処理 C++ プラグイン (mmd_fast_pluginに統合済み)
│       └── bin/                      # 【旧プラグイン本体 (mmd_motion.mll)】
│
├── pmx_analyzer/                     # PMXモデル詳細解析・一括保存 & ユーザー辞書対話登録パッケージ
│   ├── __init__.py                   # 解析パッケージエクスポート定義
│   ├── analyzer_core.py              # 材質・ボーン・モーフ・剛体・Joint一括シリアライズ保存 & 未登録漢字抽出
│   └── user_dict_dialog.py           # 未登録ボーン名検出・ローマ字入力登録GUI
│
└── docs/                             # 独立技術仕様書群
    ├── codebase_architecture_specification.md # 本ファイル (構造の概要・各モジュール仕様)
    ├── plugin_technical_guide.md              # プラグイン総合技術解説ガイド
    ├── technical_overview_guide.md            # インポートから物理ベイクまでの総合図解ガイド
    ├── model_import_specification.md          # モデルインポート総合技術仕様書 (ポータル)
    ├── pmx_model_import_specification.md      # PMXモデル (2.0/2.1) インポート技術仕様書
    ├── pmd_model_import_specification.md      # PMDモデル (旧形式) インポート・自動変換技術仕様書
    ├── x_model_import_specification.md        # DirectX .x ファイルインポート技術仕様書
    ├── vrm_model_import_specification.md      # VRMモデル (0.x/1.0) 解析・構築技術仕様書
    ├── pmx-pmd-x_specification.md             # MMDモデル共通シーン構築技術仕様書 (連携フロー図解)
    ├── vmd_import_specification.md            # VMDインポート仕様書
    ├── mmd_material_plugin_specification.md   # Viewport 2.0 対応 C++ シェーダープラグイン仕様書
    ├── mmd_fast_plugin_tech_spec.md           # 高速インポート＆モーション・ベイク C++ プラグイン仕様書
    ├── pmx_analyzer_specification.md          # PMXモデル詳細解析 & ユーザー辞書対話登録仕様書
    ├── bullet_engine_specification.md         # MMD本家 Bullet 物理演算エンジン仕様書
    ├── physics_system_specification.md        # Maya物理システム連携仕様書
    ├── realtime_physics_bake_specification.md # リアルタイム物理ベイク技術仕様書
    ├── xpbd_engine_specification.md           # C++ XPBDエンジン仕様書
    ├── pmm_specification.md                   # PMMプロジェクトファイル解析仕様書
    └── ta_math_coordinate_systems_guide.md    # TA向け3D数学・座標系マスターガイド
```

---

## 2. ルート階層モジュール仕様

### 2-1. `mmd_tools_for_maya_plugin.py`

- **種別**: Python (Mayaプラグイン公式エントリポイント)
- **役割**: Maya のプラグインマネージャからロードされ、メインメニューバーに「MMD」メニューを登録。
- **主要関数**:
  - `initializePlugin(plugin_obj)`: プラグイン登録、検索パス（`sys.path`）への内部パッケージ登録、メニュー生成。
  - `uninitializePlugin(plugin_obj)`: プラグイン解除、登録メニューの破棄。
  - `on_open_gui()`: モジュールリロード対応 GUI 起動ハンドラ。既存ウィンドウを検索して確実に破棄した上で単一ウィンドウを表示する多重起動防止機構を内包。
  - `on_open_advanced_dict()`: ユーザー辞書・マテリアル保護設定 GUI 起動ハンドラ。
  - `on_show_about()`: バージョン・開発者・機能サマリー表示ダイアログ。

### 2-2. `__init__.py`

- **種別**: Python (パッケージ初期化モジュール)
- **役割**: `mmd_tools_for_maya` を単一の Python パッケージとして成立させるエントリポイント。
- **機能**:
  - サブパッケージ群（`ui`, `maya_converters`, `mmd_parser`, `pmx_analyzer`, `physics`, `plugins`, `asset`）の確実なインポートとパス解決（旧パスへの後方互換透過エクスポートを含む）。
  - 外部スクリプトからの `from mmd_tools_for_maya import pmxpaimaya, vmdpaimaya` 等の後方互換アクセスを保証。

---

## 3. `ui/` パッケージ仕様 (統合インターフェース群)

PySide6（Maya 2025+）および PySide2（過去バージョン）デュアル対応のモダン UI パッケージです。
メインウィンドウ（`gui.py`）、共通スタイル（`gui_style.py`）、共通基盤（`common.py`）、10個の機能別タブモジュール（`tab_*.py`）、および専門操作ダイアログ群によって階層的に構成されています。

### 3-1. `ui/gui.py` (メインウィンドウ統合エントリ)

- **主要クラス**: `MMDToolsMainWindow`（後方互換エイリアス: `MmdMayaMainWindow`）
- **役割**:
  - メインウィンドウの骨格構築、各タブモジュールの遅延・確実なロードとタブコンテナへの登録。
  - 多重起動防止機構およびモジュールリロード機構の内包。
  - Maya メインメニューバーとの連動および `show_ui()` 起動関数の提供。

### 3-2. 独立タブモジュール群 (`ui/tab_*.py`)

メインウィンドウを構成する10個の独立したタブモジュールです：

- **`tab_import.py` (`ImportTabWidget`)**:
  - モデルインポート（PMX/PMD/X）、Toon/エッジ/影設定、PMX構造詳細解析・一括保存（JSON）、未登録ボーン辞書登録連携。
- **`tab_easy_import.py` (`EasyImportTabWidget`)**:
  - 初心者向けのワンクリック簡単インポート（標準設定での自動読み込みと推奨最適化の同時適用）。
- **`tab_vmd.py` (`VmdTabWidget` / `VmdImportTabWidget`)**:
  - VMD モーション・カメラ・WAV 音声インポート（QScrollArea スクロール対応、音源同期再生）。
- **`tab_material.py` (`MaterialTabWidget`)**:
  - シェーダー設定、Toonテクスチャ切り替え、透過遮光設定、マテリアル保護キーワード管理。
- **`tab_physics.py` (`PhysicsTabWidget` / `PhysicsStreamBakeTabWidget`)**:
  - Maya内部 Bullet / XPBD 物理演算設定、剛体・Joint可視化生成、再吸着、外部新3D物理ビューア（`PhysicsSimulationBakeViewer.exe`）連携。モデル選択行の更新ボタンを右側へ配置。
- **`tab_export.py` (`ExportTabWidget`)**:
  - エクスポート機能を一元集約（PMXモデル出力、VMDモーション出力、VPDポーズ出力）。
- **`tab_hik.py` (`HikTabWidget`)**:
  - HumanIK (HIK) キャラクター定義・Tポーズ自動展開、コントロールリグ生成、二重IK競合解除。
- **`tab_extra.py` (`ExtraTabWidget`)**:
  - その他機能（地面影トグル、MMD照明操作GUI起動、モデル種別判定ダイアログ起動、表情操作ウィンドウ起動、VPDポーズデータ適用など）。
- **`tab_plugin.py` (`PluginTabWidget`)**:
  - 各種プラグイン（C++シェーダー、高速モーション、Bullet DLL、XPBD DLL、C#物理ビューア）のロード状態確認と一括管理。
- **`tab_cleanup.py` (`CleanupTabWidget`)**:
  - シーン内 MMD 要素（モデル、ボーン、カメラ、ライト、地面影、および未使用マテリアル）の一括削除。

### 3-3. 独立ダイアログモジュール群

各専門操作を受け持つ独立したダイアログです：

- **`dialog_edge_control.py` (`MmdEdgeControlDialog`, `show_mmd_edge_control_dialog`)**:
  - シーン内の MMD モデル（単一メッシュ構成）の輪郭線（エッジ）太さをスライダーや数値入力でリアルタイムに一括調整する操作パネル。
- **`dialog_light_control.py` (`LightControlDialog`)**:
  - MMD本家の照明操作パネルを忠実に再現したGUI。地面影の落ちる向き（XYZ: 0.50, -1.00, -0.50）および光の色（RGB）をスライダーでリアルタイム操作。
- **`dialog_model_classifier.py` (`ModelClassifierDialog`)**:
  - モデル種別（キャラクター、ステージ、スカイドーム）の判定・個別指定設定GUI。地面影やライティングの最適挙動をモデル単位で個別制御。
- **`dialog_physics_model_select.py` (`PhysicsModelSelectDialog`)**:
  - シーン内に複数モデルが存在する際の物理演算・ベイク対象選択ダイアログ。
- **`morph_window.py` (`MorphWindow`)**:
  - 表情・モーフ操作GUI（「目」「まゆ」「リップ」「その他」4分割パネル、タイムスライダー追従、材質モーフ自動連携）。
- **`pmm_dialog.py` (`PmmAnalysisDialog` / `PmmModelImportSelectDialog`)**:
  - PMM プロジェクト解析およびチェックリスト形式のモデル選択インポート。
- **`multi_model_dialog.py` (`MultiModelImportDialog`)**:
  - 複数モデルの一括順次インポートおよび自動配置ダイアログ。
- **`accessory_dialog.py` (`AccessoryDialog`)**:
  - メガネ・武器等の小道具メッシュを指定ボーンへ追従させるアクセサリ追従アタッチ。
- **`advanced_dict_dialog.py` (`AdvancedDictDialog`)**:
  - マテリアル保護キーワードおよびカスタムボーン日英辞書の上級者向け直接編集GUI。
- **`user_dict_dialog.py` (`UserDictRegisterDialog`)**:
  - インポート時に未登録の漢字ボーン名が検出された際の対話型辞書登録ダイアログ。
- **`material_protect_dialog.py` (`MaterialProtectDialog`)**:
  - Toon保護・スペキュラ抑止対象マテリアルキーワード管理ダイアログ。
- **`bone_state_export_dialog.py` (`BoneStateExportDialog`)**:
  - モデルのボーン姿勢・トランスフォーム情報抽出・保存ダイアログ。
- **`experimental_dialog.py` (`ExperimentalDialog`)**:
  - 実験的・先進的機能の検証用ダイアログ。

### 3-4. 基盤・スタイルモジュール

- **`ui/common.py`**:
  - Qt互換インポート、Mayaメインウィンドウハンドル取得、リアルタイム進捗ログダイアログ（`ExecutionLogDialog`、フレーム情報上部への現在適用中ボーン名表示に対応）。
- **`ui/gui_style.py`**:
  - 各タブおよび各ダイアログで統一されたダークテーマ QSS スタイルシート定義。

### 3-5. `ui_editor/` パッケージ仕様 (MMD Model Editor 独立設定画面)

MMDモデルの材質・モデル属性管理に特化した独立ウィンドウを提供するモジュール群です：
- **`ui_editor/editor_window.py` (`MmdModelEditorWindow`, `show_model_editor`)**:
  - Mayaメインウィンドウを親とした独立ダイアログ基底。多重起動抑止機構、シーン内MMDモデルルート自動検出ヘッダー、PMXエディタ準拠配列の拡張タブコンテナ（`QTabWidget`）を搭載。後方互換用エイリアス（`PmxEditorWindow`, `show_pmx_editor`）も提供。
- **`ui_editor/tab_info_editor.py` (`InfoEditorTabWidget`)**:
  - 情報管理タブ本体。モデル名（日本語/英語）、コメント（日本語/英語）、PMXバージョン、構成要素統計サマリーの表示およびシーン属性への反映。
- **`ui_editor/tab_vertex_editor.py` (`VertexEditorTabWidget`)**:
  - 頂点管理タブ本体。頂点座標 (XYZ)、法線、UV、ウェイト変形方式（BDEF/SDEF/QDEF）および影響ボーン一覧のページング表示（1ページ200件）、ビューポート頂点選択連動。
- **`ui_editor/tab_face_editor.py` (`FaceEditorTabWidget`)**:
  - 面管理タブ本体。面インデックス、構成頂点番号、所属材質のページング表示、材質別ドロップダウンフィルタ、ビューポート面選択連動。
- **`ui_editor/tab_material_editor.py` (`MaterialEditorTabWidget`)**:
  - 材質管理タブ本体。
  - 左ペイン: 材質一覧テーブル（No、日本語名、英語名、ノード名、色プレビュー）、インクリメンタル絞り込み、ビューポート面・メッシュ選択連動、選択から材質特定機能。
  - 右ペイン: 拡散色・アルファ・反射・環境色・描画フラグ（両面/影/エッジ）・輪郭線色/サイズ・テクスチャ/スフィア/Toon編集、Mayaシーンノードとの双方向即時同期機能。
- **`ui_editor/tab_bone_editor.py` (`BoneEditorTabWidget`)**:
  - ボーン管理タブ本体。
  - 左ペイン: ボーン一覧テーブル（No、日本語名、英語名、ノード名、親ボーン名、表示状態）、インクリメンタル絞り込み、ビューポート選択連携、表示/非表示切替機能。ボーン未生成時には案内バナーと目立つ「ボーン作成を実行」ボタンを表示。
  - 右ペイン: ボーン名編集、初期位置（`mmdInitialTranslate`）、現在位置・回転スピンボックス、半径、表示スタイル（`drawStyle`）、姿勢リセット機能、親子関係表示。
- **`ui_editor/tab_morph_editor.py` (`MorphEditorTabWidget`)**:
  - モーフ管理タブ本体。モーフ一覧（眉・目・口・その他）、パネル分類フィルタ、検索機能、スライダによるウェイトリアルタイム操作およびMaya `blendShape` との即時同期。
- **`ui_editor/tab_rigidbody_editor.py` (`RigidBodyEditorTabWidget`)**:
  - 剛体管理タブ本体。剛体一覧、衝突グループ、形状（球・箱・カプセル）サイズ、位置/回転、質量・減衰・摩擦、剛体タイプ（ボーン追従・物理演算・位置合わせ）の確認・編集。
- **`ui_editor/tab_joint_editor.py` (`JointEditorTabWidget`)**:
  - Joint管理タブ本体。剛体間拘束一覧、接続剛体ペア、移動制限（下限〜上限）、回転制限（下限〜上限）、ばね定数（移動・回転）の確認・編集。
- **`ui_editor/tab_modification_editor.py` (`ModificationEditorTabWidget`)**:
  - 改造・お着替え・汎用パーツ移植タブ（開発中のため `editor_window.py` の `SHOW_MODIFICATION_TAB` フラグで既定非表示制御）。キャラ別・両方のボーン表示切替、基準ボーン選択位置合わせ、削除ウィンドウ連携、ボーン統合対応表ダイアログ、物理統合プラン確認ダイアログ、書き出し前6項目診断ダイアログを統合。
- **`ui_editor/dialog_terms_confirm.py` (`ModelTermsConfirmDialog`)**:
  - モデル改造・パーツ移植前に各モデルの利用規約・同梱ドキュメントを確認し、同意ロック解除を行うダイアログ。
- **`ui_editor/dialog_material_filter.py` (`MaterialFilterDialog`, `PartDeleteConfirmDialog`)**:
  - PMXエディタ風の材質別マスキング表示（表示チェック列・全表示/全非表示/反転/選択のみ/検索結果のみ/マスク解除）、選択材質・非表示材質のパーツ削除および不要モーフ同時削除確認ダイアログ。
- **`ui_editor/dialog_bone_physics_filter.py` (`BonePhysicsFilterDialog`)**:
  - キャラ単体および両方モデル同時のボーン・剛体・Joint一覧表示、ビューポートのキャラ別/両方ボーン表示切替、未使用・孤立絞り込みフィルタおよび安全削除ダイアログ。

### 3-6. `ui_other_importer/` パッケージ仕様 (その他モデルインポーターUI)

VRM モデル等の MMD 以外の 3D フォーマットを Maya へインポートするための独立ウィンドウパッケージです（試験的機能・ベータ版）：

- **`ui_other_importer/__init__.py`**:
  - `OtherModelImporterWindow`, `show_other_model_importer`, `TabVrmImporterWidget`, `TabCleanupWidget` のパッケージエクスポート定義。
- **`ui_other_importer/importer_window.py` (`OtherModelImporterWindow`, `OtherModelImporterSplashDialog`, `show_other_model_importer`)**:
  - VRM インポートタブおよびクリーンアップタブを統合する独立ダイアログ。起動中スプラッシュ表示、多重起動防止、およびホットリロード（`reload_importer_modules`）を提供。
- **`ui_other_importer/tab_vrm_importer.py` (`TabVrmImporterWidget`, `VrmDropAreaLineEdit`)**:
  - `.vrm` ファイルのドラッグ＆ドロップ対応入力欄、VRM 0.x / 1.0 メタデータおよびサムネイル画像の即時プレビュー、マテリアル種別（`mmdToonShader` / `standardSurface` / `lambert`）・Z軸反転・スケール倍率設定・実行ログ表示を提供。
- **`ui_other_importer/tab_cleanup.py` (`TabCleanupWidget`)**:
  - インポート済みの VRM モデル（`vrmSourcePath` 属性保持ノード・`*_root` グループ）を自動検出し、メッシュ・ボーン・スキンクラスター・関連マテリアル/SG・テクスチャ・未使用ノード・照明・地面影を一括削除。

---

## 4. `maya_converters/` パッケージ仕様 (変換・解析エンジン群)

### 4-1. `maya_converters/pmxpaimaya.py`

- **主要関数**: `import_pmx`, `build_bones_and_skin_for_model`, `setup_mmd_ik`, `create_mmd_lighting`, `fix_toon_shading_in_scene`, `disable_stage_and_skydome_edges_and_bones`
- **特徴**:
  - **PMX 2.0 / 2.1 推奨サポート**。旧形式 PMD および DirectX .x は非推奨。
  - **ボーン後付け作成・バインド機能 (`build_bones_and_skin_for_model`)**: インポート時にボーン生成のチェックを外した（ボーンが存在しない）モデルに対し、PMXファイルパスを自動探索して再解析し、ジョイント階層生成、親子結合、付与親エクスプレッション生成、初期位置記録、メッシュへのスキニングウェイト適用（C++高速注入およびPythonフォールバック）、足IKシステム構築を一括実行。
  - SDEF デュアルクォータニオン近似スキニング、PMX 剛体・Joint コライダー生成。
  - **スカイドーム・ステージモデルのエッジ無効化 & ボーン非表示化**: `ModelClassifierManager` と連動し、スカイドームやステージモデルを自動検知。マテリアルのエッジ属性無効化（`edgeEnable = False`, `edgeSize = 0.0`）および頂点カラーセット（`mmd_edge_scale`）のゼロ設定により、巨大ポリゴンの裏面押し出しによるエッジ白浮き・突き抜けを阻止。各ジョイントの描画スタイル（`drawStyle = 2`）およびルートの可視性を非表示に切り替え。既存シーン向けの一括適用関数（`disable_stage_and_skydome_edges_and_bones`）も提供。
  - **モーフ高速直接書き込み (Sparse Target Delta Direct Write)**: メッシュ複製ループを廃止し、OpenMaya 2.0 API により `blendShape` ノードの `inputTargetItem[6000]` スパース配列へ直接オフセット座標とインデックス配列を書き込み、数百個の表情モーフを数秒台で生成。
  - **mmdToonShader 材質モーフ二重透過・受光制御**: Viewport 2.0 OGSFX シェーダー（`mmdToonShader`）に対応し、`transparency` と `diffuseAlpha` への二重透過配線、および非表示時受光遮断（`diffuse = 0.0`）による黒浮き・落ち影浮き防止を自動構築。
  - **透過メッシュ遮光設定**: チーク・涙・顔斜線等の透過ポリゴン板に対し、ディレクショナルライト受光遮断（`diffuse = 0.0`）とシャドウ最適化を適用。

### 4-2. `maya_converters/vmdpaimaya.py`

- **主要関数**: `import_vmd`, `apply_bone_motion`, `apply_morph_motion`, `apply_camera_motion`, `apply_vpd_pose`, `delete_mmd_scene_elements`
- **特徴**:
  - VMD ベジェ補間曲線の精密計算、IK ベイク、カメラ・照明・音声連動。ボーンモーション適用時に現在処理中のボーン名を進捗ダイアログへリアルタイム通知し、フレーム進行の視認性を向上。
  - VPD ポーズデータ読み込み・適用（キーフレーム自動登録対応）。
  - MMD シーン一括削除時の地面影グループ（`mmd_ground_shadow_grp`）およびライト・カメラ・リグの一括クリーンアップ。

### 4-3. `maya_converters/physics_stream.py`

- **主要関数**: `stream_physics_to_maya`, `bake_external_simulation`
- **役割**: MMD物理演算リアルタイムベイクアプリ（`physics/physics_bake_cs` / `PhysicsSimulationBakeViewer.exe`）との通信パイプライン。シミュレーション結果をリアルタイムに受け取り、Maya シーン上のボーンへキーフレームを直接書き込み。

### 4-4. `maya_converters/vmd_analyzer.py`

- **主要クラス**: `VmdAnalyzer` (ボーン・モーフ・カメラキーフレーム統計解析)。

### 4-5. `maya_converters/mayapaipmx.py`

- **主要関数**: `export_pmx` (Maya メッシュ・ジョイントから PMX への出力)。

### 4-6. `maya_converters/bullet_builder.py`

- **役割**: 剛体構築補助モジュール。

### 4-7. `maya_converters/pmd2pmx.py`

- **主要関数**: `convert_pmd_to_pmx` (PMD から PMX へのファイル変換・保存)。
- **特徴**:
  - 旧形式 PMD モデルを解析し、同一フォルダ内に最新の PMX 2.0 形式バイナリを出力。
  - 頂点、面、材質、ボーン、IK、モーフに加え、PMD 拡張セクションに記録された剛体およびジョイント情報も抽出して引き継ぎ。
  - インポート時の自動プロンプトおよびスタンドアロンボタンから実行可能。

### 4-8. `maya_converters/edge_mesh_builder.py` / `maya_converters/mmd_edge_bake.py`

- **`edge_mesh_builder.py` (`build_edge_mesh_from_pmx`)**:
  - PMX 生データから反転法線押し出し（Inverted Hull）エッジメッシュおよびエッジ専用マテリアルを構築。エッジ無効頂点の内側沈み込み処理に対応。
- **`mmd_edge_bake.py` (`bake_edge_scale`)**:
  - `mmdMaterial` の材質ごとの `edgeEnable` / `edgeSize` と PMX 頂点エッジ倍率を頂点カラーセット `mmd_edge_scale` へ焼き込み（元倍率は `mmd_edge_scale_src` へ退避して二重適用を防止）。

### 4-9. `maya_converters/mesh_mask_utils.py` / `model_modifier.py` / `dressup/` パッケージ

- **`mesh_mask_utils.py`**:
  - 材質別面リスト収集、面単位 Isolate Select マスキング表示と復元、面・孤立頂点削除に伴う旧→新頂点番号対応表の構築、`blendShape` 差分・`skinCluster` ウェイトの再マッピング、不要モーフ判定・削除、`mmdModelStructure` / `mmdMorphStructure` JSON 更新および削除前後照合チェック。
- **`model_modifier.py`**:
  - モデル改造・汎用パーツ移植処理（`dressup/` サブパッケージ）を統括するファサード。おまかせ一括統合（`perform_full_model_dressup`）やボーン・物理解析、安全削除を提供。
- **`dressup/__init__.py`**: `dressup` パッケージの公開エクスポート定義。
- **`dressup/skin_utils.py`**: `MFnSkinCluster.getWeights` / `setWeights` による一括ウェイト抽出・適用、シーン内非表示ノード JSON キャッシュ、Undo チャンクデコレーター、自動バックアップ、およびキャラ別／両方ボーン表示切替（`set_models_bone_visibility`）。
- **`dressup/align.py`**: 標準・共通基準ボーン（`上半身2`, `首`, `頭`, `上半身`, `下半身`, `センター` 等）の検出、位置・スケール推定とプレビュー、`makeIdentity` を使わない安全なバインドポーズ再設定。
- **`dressup/part_split.py`**: ウェイト比率に基づくパーツ面分類・削除補助モジュール。
- **`dressup/neck_seam.py`**: 非結合方式による首境界ループ抽出、最近傍対応ペア探索、座標スナップ・法線平均化・ウェイトコピー、首曲げ確認テスト。
- **`dressup/bone_merge.py`**: 標準ボーン辞書（`maya_converters/asset/bone_name_map.json`）およびユーザー辞書を用いたボーン統合計画、共通ボーンのウェイト付け替え、固有ボーンサブツリー移植、衝突回避リネーム、`mmdBoneStructure` / `mmdModelStructure` 更新。
- **`dressup/physics_merge.py`**: 残存パーツ有効ボーンおよび移植固有ボーンに紐づく剛体・Joint の抽出、`rbIndex` / `jointIndex` / `rbAIndex` / `rbBIndex` 連番再付番、`parentConstraint` 再接続、衝突グループ重複解析・候補提示、`mmdModelStructure` 更新。
- **`dressup/validate.py`**: 書き出し前6項目診断（未ウェイト頂点、PMX BDEF4 上限4インフルエンス、ボーン/材質名重複、孤立剛体・Joint、表情モーフ残存、首境界隙間）および4インフルエンス以下自動整理（`clamp_max_4_influences`）。

---

## 4-B. `other_converters/` パッケージ仕様 (外部モデル解析・構築エンジン)

VRM などの MMD 以外の 3D フォーマットを解析し Maya シーンへ構築するためのコンバーターパッケージです（詳細は [vrm_model_import_specification.md](vrm_model_import_specification.md) を参照）：

- **`other_converters/__init__.py`**: `parse_vrm_metadata`, `import_vrm_model`, `VRMImporter` のエクスポート定義。
- **`other_converters/vrm_importer.py` (`VRMImporter`, `parse_vrm_metadata`, `import_vrm_model`)**:
  - glTF 2.0 GLB コンテナ（VRM 0.x `VRM` 拡張および VRM 1.0 `VRMC_vrm` 拡張）のバイナリ・JSON 解析。
  - BIN チャンク全体を展開せずにメタデータ（タイトル・作者・仕様・ライセンス・構成数）および埋め込みサムネイル画像を高速抽出する `parse_vrm_metadata`。
  - 4×4 ワールド行列事前算出によるジョイント階層構築と `humanoidBone` 属性付与、テクスチャファイル書き出しと `mmdToonShader` / `standardSurface` / `lambert` 構築・透過配線、`MFnMesh.create`（Z軸反転時の三角形順序スワップ・法線・UV V反転対応）、`skinCluster` バインド、MMD標準ライティング・地面影連携を提供。

---

## 5. `pmx_analyzer/` パッケージ仕様 (モデル解析 & ユーザー辞書登録)

### 5-1. `pmx_analyzer/analyzer_core.py`

- **主要関数**:
  - `export_pmx_structure(pmx_path, output_json_path=None)`: 材質・ボーン・モーフ・剛体・Joint の各パラメータを抽出し、`<モデル名>_pmx_analysis.json` に構造化出力。
  - `find_unregistered_kanji_in_bones(pmx_path_or_model)`: モデル内のボーン名から標準辞書およびユーザー辞書に未登録の漢字文字・熟語を抽出。

### 5-2. `pmx_analyzer/user_dict_dialog.py`

- **主要クラス・関数**:
  - `UserDictRegisterDialog(QDialog)`: 未登録漢字の隣にローマ字を記入できる対話型テーブル GUI。
  - `check_and_prompt_user_dict(parent, pmx_path)`: 未登録ボーン名検出プロンプトを表示し、「はい」で GUI 起動・登録後に再チェック（サイドチェック）を実行。「いいえ」でスルー。

---

## 6. `plugins/` 統合プラグインパッケージ仕様

Maya 上でネイティブ C++ 速度による高速処理を提供する各種プラグイン（シェーダー・独自レンダラー、高速インポート＆モーション・ベイク、旧モーション互換バイナリ）を `plugins/` 配下へ統合集約したパッケージです。

### 6-1. `plugins/mmd_material_plugin/` (Viewport 2.0 C++ 統合シェーダー & レンダラー)

Autodesk Maya の Viewport 2.0 上で本家 MMD のセル調シェーディング、輪郭線（エッジ）、スフィアマップ、多層透過（Depth Peeling）、およびオフスクリーンレンダリングを忠実に再現する高速 C++ 統合プラグインです。

- **提供バイナリ**:
  - `bin/2024/mmd_material.mll`: Autodesk Maya 2024 専用バイナリ
  - `bin/2025/mmd_material.mll`: Autodesk Maya 2025 専用バイナリ
  - `bin/2026/mmd_material.mll`: Autodesk Maya 2026 専用バイナリ
  - `bin/2027/mmd_material.mll`: Autodesk Maya 2027 専用バイナリ
  - `bin/mmd_material.mll`: 既定フォールバック用バイナリ
- **主要モジュール**:
  - `src/mmd_material_node.cpp`: Maya の `MPxNode` を拡張したカスタムシェーダーノード `mmdMaterial`。
  - `src/mmd_toon_node.cpp`: Viewport 2.0 高精度セルシェーダーノード `mmdToonShader`。
  - `src/mmd_render_override.cpp`: 白背景・単一パス統合描画・Depth Peeling を統括する独自レンダーオーバーライド `MMDRenderOverride`（MMD Viewport Renderer）。
  - `src/mmd_edge_scene_pass.cpp`: 同一メッシュ Inverted Hull 方式のエッジ描画パス。材質モーフ変化を毎フレーム監視して頂点カラー `mmd_edge_scale` を動的同期。
  - `src/mmd_render_cmd.cpp`: Render View ウィンドウおよびバッチ出力に対応したオフスクリーンレンダリングコマンド `mmdRender`（MMD Renderer）。`ogsRender` パイプラインを介して頂点カラーと Depth Peeling を正規評価。
  - `scripts/mmd_material_setup.py`: インポートされたモデルのマテリアルを `mmdMaterial` に自動置換・アサインする Python スクリプト。
  - `scripts/mmd_edge_bake.py`: 材質のエッジ設定を頂点カラーセット `mmd_edge_scale` へ焼き込むスクリプト。

### 6-2. `plugins/mmd_fast_plugin/` (C++ 高速インポート＆モーション・ベイク統合プラグイン)

Maya 上での PMX / VMD バイナリの高速展開、メッシュ・ウェイト一括生成、マルチスレッド並列キーフレーム計算、および物理ベイクを担う C++ ネイティブプラグイン（`mmd_fast.mll`）です。旧来の `mmd_motion_plugin` を内包・統合しています。

- **提供バイナリ**:
  - `bin/2025/mmd_fast.mll`: Autodesk Maya 2025 専用バイナリ
  - `bin/mmd_fast.mll`: 既定フォールバック用バイナリ
- **提供 C++ コマンド**:
  - `mmdFastImportPmxMesh`: PMX の頂点・面・UV・法線・エッジ倍率からメッシュを一括生成。
  - `mmdFastApplyPmxBlendShapes`: PMX 頂点モーフの移動差分を BlendShape ノードへ直接一括注入。
  - `mmdFastApplyPmxSkinWeights`: PMX の頂点ウェイトを SkinCluster へネイティブ速度で一括注入。
  - `mmdFastImportVmdBone`: ボーンモーションをマルチスレッド計算し AnimCurve へ一括注入。
  - `mmdFastImportVmdMorph`: 表情モーフモーションを AnimCurve へ一括注入。
  - `mmdFastImportVmdCamera`: カメラモーションをベジェ補間式でサンプリング展開し一括注入。
  - `mmdFastBakeBone`: 物理シミュレーション結果のボーン Transform を配列経由でネイティブ一括注入。

### 6-3. `plugins/mmd_motion_plugin/` (旧高速モーション処理 C++ プラグイン)

過去のバージョンで使用されていたモーション処理プラグインです。機能は現在 `plugins/mmd_fast_plugin/` に統合されていますが、互換性維持および旧バイナリ保持のために保管されています。

### 6-4. トゥーンシェーダー等の統合経緯 (旧 `mmd_toon_plugin/` 統合)

従来の開発段階で独立していた `mmd_toon_plugin`（`mmd_toon_shader.mll`）は、レンダーオーバーライドおよびエッジ描画パスとの連携効率化のため、`mmd_material_plugin/`（`mmd_material.mll`）へ統合されました。サーフェスシェーダー基盤とセル調シェーダーが単一バイナリとして一元管理されています。

---

## 7. `physics/` 統合物理演算パッケージ仕様

MMD Tools for Maya の物理演算に関わる各種モジュール（Bullet C++ エンジン、自作 XPBD エンジン、C# スタンドアロンベイク・ビューア群、ハードウェアベイク(GPU)）を `physics/` 配下へ統合集約したパッケージです。

### 7-1. `physics/bullet_engine/` (MMD本家 Bullet 物理演算エンジン)

MMD 本家（MikuMikuDance）に準拠した剛体シミュレーションを提供する Bullet 2.83.7 / 2.75 ベースの物理演算モジュールです。

- **`__init__.py`**: Bullet エンジンパッケージ初期化。
- **`bin/`**: C-API エクスポート物理 DLL（`mmd_bullet_275.dll` / `mmd_bullet_283.dll` / `mmd_bullet.dll`）。
- **`bullet_wrapper.py`**: ctypes による Python バインディング。
- **`bullet_maya_bridge.py`**: シミュレーションループ制御、`target_model` によるモデル階層限定ジョイント探索、および追突防止複数モデル順次ベイク制御。

### 7-2. `physics/cpp_engine/` (C++ XPBD 物理演算エンジン)

位置ベース物理（XPBD）による高剛性・高安定なソルバーモジュールです。

- **`bin/mmd_xpbd.dll`**: 拡張位置ベース物理（XPBD）ソルバー DLL。
- **`xpbd_visualizer.py`**: Maya ビューポート用コライダーメッシュ生成および再吸着機構。
- **`xpbd_maya_bridge.py`**: XPBD 物理シミュレーションベイク制御。

### 7-3. `physics/physics_bake_cs/` (MMD物理演算リアルタイムベイクアプリ - CPU)

- **実行ファイル**: `bin/Release/net8.0-windows/PhysicsSimulationBakeViewer_275.exe` / `PhysicsSimulationBakeViewer.exe`
- **主要技術**: WPF 3D, BulletSharp, .NET 8
- **責務**:
  - Maya と標準入出力（JSON Lines）を通じて高速にプロセス間通信を実行。
  - Maya 本体のビューポート負荷に左右されず、滑らかにしなやかな剛体挙動を評価しながらキーフレームを Maya のボーンへ直接同期ベイク。
  - **自動カメラ配置・注視点・動的追尾機構**:
    - モデル正面（Z正方向、180度）へ正対する初期カメラアングルを自動設定。
    - モデル身の丈の約52%（みぞおち付近）を注視目標（LookAt）とし、距離を身の丈の2.35倍へ拡大した引き構図により頭から足先まで収容を確立。
    - 移動アニメーション時にモデルのルート座標変位へカメラを動的同期させ、常に被写体を画角中央に維持。
  - **剛体貫通防止強化アーキテクチャ**:
    - 剛体それぞれにおける連続衝突検出 (CCD) の有効化による高速移動体のすり抜け防止。
    - Kinematic剛体のフレーム間移動量から線速度（Linear Velocity）を算出して反発インパルスを Dynamic 剛体へ正確に伝達。
    - ソルバー反復回数25回および Split Impulse（位置補正分離）による安定した押し戻し挙動。
    - 120Hz / 240Hz サブステップ対応による激しいモーション下での貫通抑制。

### 7-4. `physics/physics_bake_gpu_cs/` (ハードウェアベイク(GPU) アプリ)

- **実行ファイル**: `bin/Release/net8.0-windows/PhysicsSimulationBakeViewerGpu.exe`
- **ビルドスクリプト**: `native_cuda/build_cuda.py`（CUDA ネイティブ DLL `mmd_physics_cuda.dll` ビルド用）
- **主要技術**: C# / .NET 8 / WPF 3D / C++ / CUDA 12.9 (NVIDIA GPU 汎用最適化 / NVRTC JIT コンパイル)
- **責務**:
  - MMD 本家準拠の Bullet 物理仕様を厳格に尊重しながら、NVIDIA GPU（GeForce RTX 20/30/40シリーズ、GTX 10/16シリーズ、Quadro、RTX Aシリーズ等）の並列計算パワーを引き出すハードウェアベイク(GPU)プロジェクト。
  - C++ / CUDA ネイティブ DLL（`mmd_physics_cuda.dll`）と C# アプリケーションの P/Invoke 相互運用により、ハードウェア動的診断および GPU 加速計算を実現。
  - **NVRTC (NVIDIA Runtime Compilation) 実行時 JIT 汎用アーキテクチャ**:
    - ホスト側 C++（MSVC `cl.exe`）と CUDA Driver API（`cuda.lib`）および NVRTC（`nvrtc.lib`）を直接リンク。
    - 接続されている GPU の Compute Capability（Pascal / Volta / Turing / Ampere / Ada Lovelace / 最新世代）を動的に取得し、そのデバイスに最適な `--gpu-architecture=compute_XX` を動的生成して JIT 最適化コンパイルを実行。
    - 剛体のオイラー・ベルレ運動積分、地面（Floor）衝突反発判定、および 6DoF スプリング拘束の反復並列充足ソルバーを GPU 上で高速実行。
  - **メッシュ頂点スキニングの CUDA 並列化 (ハードウェアベイク(GPU) 適所アクセラレーション)**:
    - MMD 本家の Bullet 物理挙動（剛体追従・6DoFスプリング拘束）を忠実に尊重しつつ、3D ビューアの最大負荷である頂点変形処理（Linear Blend Skinning）を NVIDIA GPU の CUDA コアへオフロード。
    - モデル読み込み時に頂点初期データを VRAM へ一括転送し、毎フレームのボーン行列（数KB）のみを転送して並列計算を実行。
    - CPU 負荷を大幅に削減し、高フレームレートでの滑らかなリアルタイムプレビュー・ベイクを実現。
  - **Maya GUI との直接連携**:
    - 「物理演算ベイクGUI」タブ（`ui/tab_physics.py`）に「ハードウェアベイク(GPU)」トグルオプションを新設。
    - `maya_converters/physics_stream.py` の `use_gpu` パラメータと連動し、ワンクリックで GPU 版ビューアを選択・起動してハードウェアベイク(GPU)が可能。
  - 3D ビューア GUI 上で GPU デバイス名およびリアルタイム動作ステータス（`[CUDA 頂点スキニング有効]`）を目視確認可能。非対応環境時は自動で CPU (BulletSharp) へフォールバックする防御的設計を適用。

### 7-5. `physics/physics_bridge_cs/` (MMD物理演算シミュレーションビューア)

- **実行ファイル**: `bin/Release/net8.0-windows/MmdPhysicsBridge.exe`
- **主要技術**: C# / BulletSharp / .NET 8 / WPF
- **責務**:
  - PMX 剛体・ジョイントデータと VMD モーションを高速読み込み。
  - BulletSharp による物理シミュレーション挙動を独立した 3D 画面上でリアルタイムにプレビュー・動作検証できるシミュレーションビューア。

---

## 8. `mmd_parser/` パッケージ仕様 (バイナリパーサー群)

外部依存ゼロの純粋な Python 標準ライブラリによる構文解析器です。

- **`pmx.py`**: PMX 2.0 / 2.1 パーサー & ライター（標準推奨フォーマット）。
- **`pmd.py`**: PMD パーサー & PMX 構造への変換エンジン。剛体のボーン相対位置をPMXワールド座標系へ自動展開し、アルファ異常値の自動補正機能を搭載（非推奨形式のPMX自動移行対応）。
- **`x_file.py`**: DirectX .x テキスト／バイナリ構文解析器（非推奨）。
- **`vmd.py`**: VMD モーションパーサー。
- **`vpd.py`**: VPD ポーズパーサー。
- **`pmm.py`**: PMM（Polygon Movie Maker）プロジェクトファイル解析パーサー。

---

## 9. `asset/` モジュール・データ仕様 (辞書・設定管理)

- **`model_classifier_manager.py`**:
  - モデル種別（キャラクター、ステージ、スカイドーム）の判定・個別指定設定を管理するマネージャ。
  - `asset/dictionary/user/model_classifier_settings.json`（ユーザー個別設定）を最優先とし、未存在時は `asset/dictionary/default/model_classifier_settings.json`（既定キーワード）を参照する二階層読み込みに対応し、メタデータ属性（`mmdModelType`）への反映および地面影やライティングの最適挙動を支援。
- **`user_dict_manager.py`**:
  - ユーザー辞書・マテリアル保護設定管理モジュール。
  - `dictionary/user/`（ユーザー独自設定）を最優先とし、未定義の場合は `dictionary/default/`（開発者配布標準）を参照する二階層検索ロジックを提供。
- **`dictionary/default/`**:
  - **`bone_dict.json`**: MMD標準ボーンおよび広く使われる準標準ボーン（腕捩・手捩・足D・足先EX等）を厳選した78本の日英相互変換定義データ。
  - **`default_model_dictionary.json`**: PMXモデル群（東方キャラ、その他キャラクター、幻塔、NTE、スカイドーム・ステージモデル計172ファイル）から抽出・解析された、モデル拡張ボーン・中国語対応ボーン・特殊記号・表情モーフのローマ字辞書データ（ボーン7,125件、モーフ1,275件）。従来の標準辞書から移行した余剰項目（衣装・髪・装飾等）も包含。
  - **`jaka_dict.json`**: 日本語/中国語ノード名のローマ字変換定義JSON。
  - **`hik_dict.json`**: HumanIK (HIK) ボーン定義マッピングJSON。
  - **`model_classifier_settings.json`**: モデル種別の自動判別キーワード（スカイドーム・ステージ）既定定義JSON。
  - **`morph_dict.json`**: 標準モーフ定義JSON。
  - **`user_dictionary.json`**: 標準設定ファイル（保護キーワード、カスタム辞書）。
- **`dictionary/user/`**:
  - ユーザーが個別に追加・編集した辞書ファイル群を格納するディレクトリ。バージョン更新時にも上書きされずに保持されます。
- **`bone_dict.py`**: 標準ボーン日英相互変換モジュール（`default_model_dictionary.json` とも連動）。
- **`jaka.py`**: 日本語/中国語ノード名のローマ字変換 & 正常化モジュール。
- **`hik.py`**: HumanIK (HIK) ボーン定義マッピング（Tポーズ展開、膝の優先角度 `preferredAngle` & プレベンド設定、つま先ボーン対応）。

---

## 10. `toon/` ディレクトリ仕様

MMD 標準のトゥーン階調テクスチャ（`toon01.bmp` 〜 `toon10.bmp`）を格納。モデルインポート時に参照・適用されます。

---

## 11. `docs/` ディレクトリ仕様

各サブシステムの公式設計仕様書群です：

- `codebase_architecture_specification.md` (構造仕様書 - 本ドキュメント)
- `plugin_technical_guide.md` (プラグイン総合技術解説ガイド)
- `technical_overview_guide.md` (インポートから物理ベイクまでの総合図解仕様書)
- `model_import_specification.md` (モデルインポート総合技術仕様書 - ポータル)
- `pmx_model_import_specification.md` (PMXモデル 2.0/2.1 インポート技術仕様書)
- `pmd_model_import_specification.md` (PMDモデル 旧形式インポート・自動変換技術仕様書)
- `x_model_import_specification.md` (DirectX .x ファイルインポート技術仕様書)
- `vrm_model_import_specification.md` (VRMモデル 0.x/1.0 解析・構築技術仕様書)
- `pmx-pmd-x_specification.md` (MMDモデル共通シーン構築技術仕様書 - 連携フロー図解)
- `vmd_import_specification.md` (VMDインポート仕様書)
- `mmd_material_plugin_specification.md` (Viewport 2.0 C++ シェーダー仕様書)
- `mmd_fast_plugin_tech_spec.md` (高速インポート＆モーション・ベイク C++ プラグイン仕様書)
- `pmx_analyzer_specification.md` (PMXモデル詳細解析 & ユーザー辞書仕様書)
- `bullet_engine_specification.md` (Bullet物理仕様書)
- `physics_system_specification.md` (Maya物理システム仕様書)
- `realtime_physics_bake_specification.md` (リアルタイム物理ベイク技術仕様書)
- `xpbd_engine_specification.md` (XPBD物理仕様書)
- `pmm_specification.md` (PMMプロジェクト解析・インポート仕様書)
- `ta_math_coordinate_systems_guide.md` (TA向け3D数学・座標系マスターガイド)
