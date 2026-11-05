# コードベース構成・各モジュール仕様書

> [!NOTE]
> 本詳細技術仕様書は、AI によって作成・整理されたドキュメントです。内容はソースコードおよび開発記録をもとに記述していますが、実際の動作と細部が異なる場合があります。

本ドキュメントは、「MMD Tools for Maya」プロジェクトを構成する全ディレクトリ、Python スクリプト、C++ 物理/シェーダープラグイン、C# 外部物理ビューア、および各モジュールの責務と仕様を詳細に解説する仕様書です。

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
├── converters/                       # Maya ↔ MMD 相互変換・解析エンジンパッケージ
│   ├── __init__.py                   # コンバータエクスポート定義
│   ├── pmxpaimaya.py                 # MMDモデルインポートエンジン (メッシュ/マテリアル/IK/地面影)
│   ├── vmdpaimaya.py                 # MMDモーション(VMD)アニメーション適用エンジン
│   ├── mayapaipmx.py                 # MayaシーンからPMXへのエクスポートエンジン
│   ├── pmd2pmx.py                    # PMDからPMXへの自動変換エンジン (剛体・ジョイント対応)
│   ├── physics_stream.py             # 外部C#物理ビューア連携・リアルタイムストリーミング＆ベイク
│   ├── vmd_analyzer.py               # VMDモーション構造解析・診断モジュール
│   └── bullet_builder.py             # 剛体構築補助モジュール
│
├── mmd_core/                         # 自作MMDバイナリ/テキスト構文解析パッケージ (MIT)
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
│   ├── user_dictionary.json          # ユーザー設定永続化ファイル (保護キーワード・カスタム辞書)
│   ├── bone_dict.py                  # 標準ボーン日英相互変換モジュール (ユーザー辞書連動)
│   ├── bone_dict.json                # 標準ボーン定義JSON
│   ├── jaka.py                       # 日本語/中国語ノード名のローマ字変換 & 健全化
│   ├── jaka_dict.json                # ローマ字変換定義JSON
│   ├── hik.py                        # HumanIK (HIK) ボーン定義マッピング
│   └── hik_dict.json                 # HIKボーンマッピング定義JSON
│
├── toon/                             # MMD標準トゥーンテクスチャ
│   └── toon01.bmp ～ toon10.bmp      # 各階調用標準BMPテクスチャ群
│
├── bullet_engine/                    # MMD本家 Bullet 2.83.7 物理演算エンジン (zlib license)
│   ├── bin/
│   │   └── mmd_bullet.dll            # コンパイル済み Bullet 物理エンジンDLL
│   ├── include/                      # Bullet C++ ヘッダー群
│   ├── src/                          # Bullet C++ ソース群 & C-API エクスポートラッパー
│   ├── build_bullet_dll.py           # MSVC / MinGW 自動検出 DLL ビルドスクリプト
│   ├── bullet_wrapper.py             # ctypes による Bullet DLL Python バインディング
│   ├── bullet_maya_bridge.py         # Bullet 物理シミュレーション・Maya ベイク制御エンジン
│   ├── LICENSE                       # Bullet 公式 zlib ライセンス条項
│   └── README.md                     # Bullet エンジン概要・ビルド手順
│
├── cpp_engine/                       # C++ XPBD 物理演算エンジン (MIT)
│   ├── bin/
│   │   └── mmd_xpbd.dll              # コンパイル済みXPBD物理エンジンDLL
│   ├── include/
│   │   └── xpbd_engine.h             # XPBDエンジンヘッダー
│   ├── src/
│   │   └── xpbd_engine.cpp           # XPBDエンジン実装
│   ├── build_dll.py                  # MSVC / MinGW 自動検出DLLビルドスクリプト
│   ├── xpbd_wrapper.py               # ctypes による C++ DLL Pythonバインディング
│   ├── xpbd_visualizer.py            # Maya上のメッシュ・Jointロケーター追従・再吸着
│   ├── xpbd_maya_bridge.py           # シミュレーションベイク制御エンジン
│   └── test_xpbd.py                  # XPBDエンジンスタンドアロン単体テスト
│
├── mmd_material_plugin/              # MMD専用シェーダー C++ プラグイン (Viewport 2.0 対応)
│   ├── bin/
│   │   ├── 2025/mmd_material.mll     # Maya 2025 用コンパイル済みシェーダープラグイン
│   │   ├── 2026/mmd_material.mll     # Maya 2026 用コンパイル済みシェーダープラグイン
│   │   └── mmd_material.mll          # 標準リンク用シェーダープラグイン
│   ├── shaders/
│   │   └── mmd_material.fx           # Viewport 2.0 (DirectX 11) HLSL シェーダー
│   ├── src/                          # シェーダーノードおよび描画オーバーライド実装
│   ├── scripts/
│   │   └── mmd_material_setup.py     # シェーダーネットワーク自動構築・アサインスクリプト
│   ├── CMakeLists.txt                # ビルド定義
│   └── README.md                     # シェーダープラグインビルド・運用手順
│
├── mmd_toon_plugin/                  # Viewport 2.0 専用 OGSFX Toonシェーダー C++ プラグイン
│   ├── bin/
│   │   ├── 2025/mmd_toon_shader.mll  # Maya 2025 用コンパイル済みプラグイン
│   │   └── mmd_toon_shader.mll       # 標準リンク用シェーダープラグイン
│   ├── shaders/
│   │   └── mmd_toon.ogsfx            # Viewport 2.0 OGSFX トゥーンシェーダーコード
│   ├── src/                          # シェーダーノードおよび描画オーバーライド実装
│   ├── include/                      # C++ ヘッダー群
│   └── CMakeLists.txt                # ビルド定義
│
├── mmd_motion_plugin/                # 高速モーション処理 C++ プラグイン
│   ├── bin/
│   │   ├── 2025/mmd_motion.mll       # Maya 2025 用コンパイル済みモーションプラグイン
│   │   └── 2026/mmd_motion.mll       # Maya 2026 用コンパイル済みモーションプラグイン
│   ├── src/                          # 高速補間・キーフレーム処理ソース群
│   └── CMakeLists.txt                # ビルド定義
│
├── physics_bake_cs/                  # MMD物理演算リアルタイムベイクアプリ (C# / .NET 8 / WPF 3D)
│   ├── bin/Release/net8.0-windows/   # 実行可能バイナリ群
│   ├── App.xaml / App.xaml.cs        # アプリケーションエントリ
│   ├── ViewerWindow.xaml / .cs       # 物理シミュレーション同期描画ウィンドウ
│   ├── PoseEvaluator.cs              # ボーンポーズ・物理挙動リアルタイム評価
│   └── PhysicsSimulationBakeViewer.csproj # プロジェクト定義
│
├── physics_bridge_cs/                # MMD物理演算シミュレーションビューア (C# / .NET 8 / WPF)
│   ├── bin/Release/net8.0-windows/   # 実行可能バイナリ群
│   ├── MainWindow.xaml / .cs         # ビューア操作・描画画面
│   ├── PhysicsSimulationEngine.cs    # BulletSharp 物理シミュレーションコア
│   ├── PmxLoader.cs / VmdLoader.cs   # 高速 PMX / VMD 読み込みモジュール
│   └── MmdPhysicsBridge.csproj       # プロジェクト定義
│
├── pmx_analyzer/                     # PMXモデル詳細解析・一括保存 & ユーザー辞書対話登録パッケージ
│   ├── __init__.py                   # 解析パッケージエクスポート定義
│   ├── analyzer_core.py              # 材質・ボーン・モーフ・剛体・Joint一括シリアライズ保存 & 未登録漢字抽出
│   └── user_dict_dialog.py           # 未登録ボーン名検出・ローマ字入力登録GUI
│
└── docs/                             # 独立技術仕様書群
    ├── codebase_architecture_specification.md # 本ファイル (全体の構造・各モジュール仕様)
    ├── plugin_technical_guide.md              # プラグイン総合技術解説ガイド
    ├── technical_overview_guide.md            # インポートから物理ベイクまでの総合図解ガイド
    ├── model_import_specification.md          # モデルインポート総合技術仕様書 (ポータル)
    ├── pmx_model_import_specification.md      # PMXモデル (2.0/2.1) インポート技術仕様書
    ├── pmd_model_import_specification.md      # PMDモデル (旧形式) インポート・自動変換技術仕様書
    ├── x_model_import_specification.md        # DirectX .x ファイルインポート技術仕様書
    ├── pmx-pmd-x_specification.md             # MMDモデル共通シーン構築技術仕様書 (連携フロー図解)
    ├── vmd_import_specification.md            # VMDインポート仕様書
    ├── mmd_material_plugin_specification.md   # Viewport 2.0 対応 C++ シェーダープラグイン仕様書
    ├── pmx_analyzer_specification.md          # PMXモデル詳細解析 & ユーザー辞書対話登録仕様書
    ├── bullet_engine_specification.md         # MMD本家 Bullet 物理演算エンジン仕様書
    ├── physics_system_specification.md        # Maya物理システム連携仕様書
    ├── realtime_physics_bake_specification.md # リアルタイム物理ベイク技術仕様書
    ├── xpbd_engine_specification.md           # C++ XPBDエンジン仕様書
    └── pmm_specification.md                   # PMMプロジェクトファイル解析仕様書
```

---

## 2. ルート階層モジュール仕様

### 2-1. `mmd_tools_for_maya_plugin.py`

- **種別**: Python (Mayaプラグイン公式エントリポイント)
- **役割**: Maya のプラグインマネージャからロードされ、メインメニューバーに「MMD」メニューを登録。
- **主要関数**:
  - `initializePlugin(plugin_obj)`: プラグイン登録、検索パス（`sys.path`）への内部パッケージ登録、メニュー生成。
  - `uninitializePlugin(plugin_obj)`: プラグイン解除、登録メニューの破棄。
  - `on_open_gui()`: モジュールリロード対応 GUI 起動ハンドラ。既存ウィンドウを検索して安全に破棄した上で単一ウィンドウを表示する多重起動防止機構を内包。
  - `on_open_advanced_dict()`: ユーザー辞書・マテリアル保護設定 GUI 起動ハンドラ。
  - `on_show_about()`: バージョン・開発者・機能サマリー表示ダイアログ。

### 2-2. `__init__.py`

- **種別**: Python (パッケージ初期化モジュール)
- **役割**: `mmd_tools_for_maya` を単一の Python パッケージとして成立させるエントリポイント。
- **機能**:
  - サブパッケージ群（`ui`, `converters`, `mmd_core`, `pmx_analyzer`, `bullet_engine`, `cpp_engine`, `asset`）の安全なインポートとパス解決。
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
- **`tab_physics.py` (`PhysicsTabWidget`)**:
  - Maya内部 Bullet / XPBD 物理演算設定、剛体・Joint可視化生成、再吸着、外部新3D物理ビューア（`PhysicsSimulationBakeViewer.exe`）連携。
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
  - Qt互換インポート、Mayaメインウィンドウハンドル取得、リアルタイム進捗ログダイアログ（`ExecutionLogDialog`）。
- **`ui/gui_style.py`**:
  - 全タブおよび各ダイアログで統一されたダークテーマ QSS スタイルシート定義。

---

## 4. `converters/` パッケージ仕様 (変換・解析エンジン群)

### 4-1. `converters/pmxpaimaya.py`

- **主要関数**: `import_pmx`, `setup_mmd_ik`, `create_mmd_lighting`, `fix_toon_shading_in_scene`
- **特徴**:
  - **PMX 2.0 / 2.1 推奨サポート**。旧形式 PMD および DirectX .x は非推奨。
  - SDEF デュアルクォータニオン近似スキニング、PMX 剛体・Joint コライダー生成。
  - **モーフ高速直接書き込み (Sparse Target Delta Direct Write)**: メッシュ複製ループを廃止し、OpenMaya 2.0 API により `blendShape` ノードの `inputTargetItem[6000]` スパース配列へ直接オフセット座標とインデックス配列を書き込み、数百個の表情モーフを数秒台で生成。
  - **mmdToonShader 材質モーフ二重透過・受光制御**: Viewport 2.0 OGSFX シェーダー（`mmdToonShader`）に対応し、`transparency` と `diffuseAlpha` への二重透過配線、および非表示時受光遮断（`diffuse = 0.0`）による黒浮き・落ち影浮き防止を自動構築。
  - **透過メッシュ遮光設定**: チーク・涙・顔斜線等の透過ポリゴン板に対し、ディレクショナルライト受光遮断（`diffuse = 0.0`）とシャドウ最適化を適用。

### 4-2. `converters/vmdpaimaya.py`

- **主要関数**: `import_vmd`, `apply_bone_motion`, `apply_morph_motion`, `apply_camera_motion`, `apply_vpd_pose`, `delete_mmd_scene_elements`
- **特徴**:
  - VMD ベジェ補間曲線の精密計算、IK ベイク、カメラ・照明・音声連動。
  - VPD ポーズデータ読み込み・適用（キーフレーム自動登録対応）。
  - MMD シーン全削除時の地面影グループ（`mmd_ground_shadow_grp`）およびライト・カメラ・リグの一括クリーンアップ。

### 4-3. `converters/physics_stream.py`

- **主要関数**: `stream_physics_to_maya`, `bake_external_simulation`
- **役割**: MMD物理演算リアルタイムベイクアプリ（`physics_bake_cs` / `PhysicsSimulationBakeViewer.exe`）との通信パイプライン。シミュレーション結果をリアルタイムに受け取り、Maya シーン上のボーンへキーフレームを直接書き込み。

### 4-4. `converters/vmd_analyzer.py`

- **主要クラス**: `VmdAnalyzer` (ボーン・モーフ・カメラキーフレーム統計解析)。

### 4-5. `converters/mayapaipmx.py`

- **主要関数**: `export_pmx` (Maya メッシュ・ジョイントから PMX への出力)。

### 4-6. `converters/bullet_builder.py`

- **役割**: 剛体構築補助モジュール。

### 4-7. `converters/pmd2pmx.py`

- **主要関数**: `convert_pmd_to_pmx` (PMD から PMX へのファイル変換・保存)。
- **特徴**:
  - 旧形式 PMD モデルを解析し、同一フォルダ内に最新の PMX 2.0 形式バイナリを出力。
  - 頂点、面、材質、ボーン、IK、モーフに加え、PMD 拡張セクションに記録された剛体およびジョイント情報も抽出して引き継ぎ。
  - インポート時の自動プロンプトおよびスタンドアロンボタンから実行可能。

---

## 5. `pmx_analyzer/` パッケージ仕様 (モデル解析 & ユーザー辞書登録)

### 5-1. `pmx_analyzer/analyzer_core.py`

- **主要関数**:
  - `export_pmx_structure(pmx_path, output_json_path=None)`: 材質・ボーン・モーフ・剛体・Joint の全パラメータを抽出し、`<モデル名>_pmx_analysis.json` に構造化出力。
  - `find_unregistered_kanji_in_bones(pmx_path_or_model)`: モデル内のボーン名から標準辞書およびユーザー辞書に未登録の漢字文字・熟語を抽出。

### 5-2. `pmx_analyzer/user_dict_dialog.py`

- **主要クラス・関数**:
  - `UserDictRegisterDialog(QDialog)`: 未登録漢字の隣にローマ字を記入できる対話型テーブル GUI。
  - `check_and_prompt_user_dict(parent, pmx_path)`: 未登録ボーン名検出プロンプトを表示し、「はい」で GUI 起動・登録後に再チェック（サイドチェック）を実行。「いいえ」でスルー。

---

## 6. `mmd_material_plugin/` パッケージ仕様 (Viewport 2.0 C++ シェーダー)

Autodesk Maya の Viewport 2.0 上で本家 MMD のセル調シェーディング、輪郭線（エッジ）、スフィアマップ、二重構造透過を忠実に再現する高速 C++ プラグインです。

- **`bin/2025/mmd_material.mll` / `bin/2026/mmd_material.mll`**: 各年度版 Maya 専用コンパイル済みプラグイン。
- **`shaders/mmd_material.fx`**: DirectX 11 (HLSL) シェーダーコード。Toon 階調テクスチャ乗算、スフィア動的反射、二重透過加算ブレンドを実装。
- **`src/mmd_material_node.cpp`**: Maya の `MPxNode` を拡張したカスタムシェーダーノード `mmdMaterial`。
- **`src/mmd_material_override.cpp`**: `MPxShaderOverride` によるリアルタイム描画制御。
- **`scripts/mmd_material_setup.py`**: インポートされたモデルのマテリアルを `mmdMaterial` に自動置換・アサインする Python スクリプト。

---

## 7. `mmd_toon_plugin/` パッケージ仕様 (Viewport 2.0 OGSFX Toonシェーダー)

Maya の Viewport 2.0 ネイティブ OGSFX（OpenGL / DirectX クロスプラットフォーム）エフェクト規格に対応したアニメ調トゥーンシェーダープラグインです。

- **`bin/2025/mmd_toon_shader.mll`**: Maya 2025 用コンパイル済みプラグイン。
- **`shaders/mmd_toon.ogsfx`**: Viewport 2.0 OGSFX シェーダーコード。
- **特徴**:
  - シェーダー内部での直接アルファ（`diffuseAlpha`）および逆転透過（`transparencyR/G/B`）に対応。
  - ディレクショナルライト受光とアンビエント光のバランスを調整し、白飛びや黒沈みを抑えたセル調陰影描画を提供。

---

## 8. `mmd_motion_plugin/` パッケージ仕様 (ボーンベイク高速化 C++ プラグイン)

物理演算シミュレーション結果など、大量フレームのボーンアニメーション姿勢（平行移動・回転）を Maya の `animCurve` ノードへネイティブ C++ 速度で一括注入する高速化プラグインです。

- **提供バイナリ**:
  - `bin/2024/mmd_motion.mll`: Autodesk Maya 2024 専用バイナリ
  - `bin/2025/mmd_motion.mll`: Autodesk Maya 2025 専用バイナリ
  - `bin/2026/mmd_motion.mll`: Autodesk Maya 2026 専用バイナリ
  - `bin/2027/mmd_motion.mll`: Autodesk Maya 2027 専用バイナリ
  - `bin/mmd_motion.mll`: 既定フォールバック用バイナリ
- **提供 C++ コマンド**: `mmdFastBakeBone`
  - シグネチャ: `mmdFastBakeBone(boneName, frames, tx, ty, tz, rx, ry, rz)`
  - `MFnAnimCurve::addKeys` を用いて、平行移動（`kAnimCurveTL`）および回転（`kAnimCurveTA`）のキーフレームを配列経由で直接注入。
  - Python レイヤーによる繰り返し呼び出しや `cmds.setKeyframe` と比較して数十倍から数百倍の高速書き込みを達成。
- **主要な連携先**:
  - `bullet_engine/bullet_maya_bridge.py`: Bullet 物理演算シミュレーション結果のジョイントベイク処理（`apply_bake_buffer`）。
- **機能分担と責務の明確化**:
  - `mmd_motion.mll` はボーンの Transform アニメーションベイクに特化しています。
  - 通常の VMD ファイル読み込み（キャラクターダンス、表情モーフ、カメラワーク、音源）は Python コアモジュール `converters/vmdpaimaya.py` が担当し、各種モデルやカメラに対して柔軟かつ独立した処理を提供します。

---

## 9. `physics_bake_cs/` & `physics_bridge_cs/` サブシステム仕様

Maya 本体の描画負荷から物理シミュレーションを分離し、独立プロセスでリアルタイム可視化やキーフレーム生成を行う C# (.NET 8) スタンドアロンシステム群です。

### 9-1. `physics_bake_cs/` (MMD物理演算リアルタイムベイクアプリ)

- **実行ファイル**: `bin/Release/net8.0-windows/PhysicsSimulationBakeViewer.exe`
- **主要技術**: WPF 3D, BulletSharp, .NET 8
- **責務**:
  - Maya と標準入出力（JSON Lines）を通じて高速にプロセス間通信を実行。
  - Maya 本体のビューポート負荷に左右されず、滑らかにしなやかな剛体挙動を評価しながらキーフレームを Maya のボーンへ直接同期ベイク。
  - **自動カメラ配置・注視点・動的追尾機構**:
    - モデル正面（Z正方向、180度）へ正対する初期カメラアングルを自動設定。
    - モデル全高の約52%（みぞおち付近）を注視目標（LookAt）とし、距離を全高の2.35倍へ拡大した引き構図により全身収容を確立。
    - 移動アニメーション時にモデルのルート座標変位へカメラを動的同期させ、常に被写体を画角中央に維持。
  - **剛体貫通防止強化アーキテクチャ**:
    - 全剛体における連続衝突検出 (CCD) の有効化による高速移動体のすり抜け防止。
    - Kinematic剛体のフレーム間移動量から線速度（Linear Velocity）を算出して反発インパルスを Dynamic 剛体へ正確に伝達。
    - ソルバー反復回数25回および Split Impulse（位置補正分離）による安定した押し戻し挙動。
    - 120Hz / 240Hz サブステップ対応による激しいモーション下での貫通抑制。

### 9-2. `physics_bridge_cs/` (MMD物理演算シミュレーションビューア)

- **実行ファイル**: `bin/Release/net8.0-windows/MmdPhysicsBridge.exe`
- **主要技術**: C# / BulletSharp / .NET 8 / WPF
- **責務**:
  - PMX 剛体・ジョイントデータと VMD モーションを高速読み込み。
  - BulletSharp による物理シミュレーション挙動を独立した 3D 画面上でリアルタイムにプレビュー・動作検証できるシミュレーションビューア。

---

## 10. `bullet_engine/` パッケージ仕様 (MMD本家 Bullet 物理演算エンジン)

MMD 本家（MikuMikuDance）に準拠した剛体シミュレーションを提供する Bullet 2.83.7 ベースの物理演算モジュールです。

- **`bin/mmd_bullet.dll`**: C-API エクスポート物理 DLL。
- **`bullet_wrapper.py`**: ctypes による Python バインディング。
- **`bullet_maya_bridge.py`**: シミュレーションループ制御、`target_model` によるモデル階層限定ジョイント探索、および追突防止複数モデル順次ベイク制御。

---

## 11. `cpp_engine/` パッケージ仕様 (C++ XPBD 物理演算エンジン)

位置ベース物理（XPBD）による高剛性・高安定なソルバーモジュールです。

- **`bin/mmd_xpbd.dll`**: 拡張位置ベース物理（XPBD）ソルバー DLL。
- **`xpbd_visualizer.py`**: Maya ビューポート用コライダーメッシュ生成および再吸着機構。
- **`xpbd_maya_bridge.py`**: XPBD 物理シミュレーションベイク制御。

---

## 12. `mmd_core/` パッケージ仕様 (バイナリパーサー群)

外部依存ゼロの純粋な Python 標準ライブラリによる構文解析器です。

- **`pmx.py`**: PMX 2.0 / 2.1 パーサー & ライター（標準推奨フォーマット）。
- **`pmd.py`**: PMD パーサー & PMX 構造への変換エンジン。剛体のボーン相対位置をPMXワールド座標系へ自動展開し、アルファ異常値の自動補正機能を搭載（非推奨形式のPMX自動移行対応）。
- **`x_file.py`**: DirectX .x テキスト／バイナリ構文解析器（非推奨）。
- **`vmd.py`**: VMD モーションパーサー。
- **`vpd.py`**: VPD ポーズパーサー。

---

## 13. `asset/` モジュール・データ仕様 (辞書・設定管理)

- **`model_classifier_manager.py`**:
  - モデル種別（キャラクター、ステージ、スカイドーム）の判定・個別指定設定を管理するマネージャ。
  - メタデータ属性（`mmdModelType`）および設定ファイルへの永続化を行い、地面影やライティングの最適挙動を支援。
- **`user_dict_manager.py`**: ユーザー辞書・マテリアル保護設定管理モジュール。
- **`user_dictionary.json`**: ユーザー設定永続化ファイル（保護キーワード、カスタム辞書）。
- **`bone_dict.py` / `bone_dict.json`**: 標準ボーン日英相互変換モジュールおよび定義データ。
- **`jaka.py` / `jaka_dict.json`**: 日本語/中国語ノード名のローマ字変換 & 健全化。
- **`hik.py` / `hik_dict.json`**: HumanIK (HIK) ボーン定義マッピング（Tポーズ展開、膝の優先角度 `preferredAngle` & プレベンド設定、つま先ボーン対応）。

---

## 14. `toon/` ディレクトリ仕様

MMD 標準のトゥーン階調テクスチャ（`toon01.bmp` 〜 `toon10.bmp`）を格納。モデルインポート時に参照・適用されます。

---

## 15. `docs/` ディレクトリ仕様

各サブシステムの公式設計仕様書群です：

- `codebase_architecture_specification.md` (全体構造仕様書 - 本ドキュメント)
- `plugin_technical_guide.md` (プラグイン総合技術解説ガイド)
- `technical_overview_guide.md` (インポートから物理ベイクまでの総合図解仕様書)
- `model_import_specification.md` (モデルインポート総合技術仕様書 - ポータル)
- `pmx_model_import_specification.md` (PMXモデル 2.0/2.1 インポート技術仕様書)
- `pmd_model_import_specification.md` (PMDモデル 旧形式インポート・自動変換技術仕様書)
- `x_model_import_specification.md` (DirectX .x ファイルインポート技術仕様書)
- `pmx-pmd-x_specification.md` (MMDモデル共通シーン構築技術仕様書 - 連携フロー図解)
- `vmd_import_specification.md` (VMDインポート仕様書)
- `mmd_material_plugin_specification.md` (Viewport 2.0 C++ シェーダー仕様書)
- `pmx_analyzer_specification.md` (PMXモデル詳細解析 & ユーザー辞書仕様書)
- `bullet_engine_specification.md` (Bullet物理仕様書)
- `physics_system_specification.md` (Maya物理システム仕様書)
- `realtime_physics_bake_specification.md` (リアルタイム物理ベイク技術仕様書)
- `xpbd_engine_specification.md` (XPBD物理仕様書)
- `pmm_specification.md` (PMMプロジェクト解析・インポート仕様書)
