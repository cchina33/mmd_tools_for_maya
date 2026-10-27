# コードベース構成・各モジュール仕様書

> [!NOTE]
> 本詳細技術仕様書は、AI によって作成・整理されたドキュメントです。内容はソースコードおよび開発記録をもとに記述していますが、実際の動作と細部が異なる場合があります。

本ドキュメントは、「MMD Tools for Maya」プロジェクトを構成する全ディレクトリ、Python スクリプト、C++ 物理/シェーダープラグイン、C# 外部物理ビューア、および各モジュールの責務と仕様を詳細に解説する仕様書です。

```text
mmd_tools_for_maya/
├── mmd_tools_for_maya_plugin.py      # Mayaプラグイン公式エントリポイント (MMDメニュー & 上級者メニュー)
├── __init__.py                       # パッケージ初期化＆後方互換透過エクスポート
├── README.md                         # プロジェクト概要・導入手順
├── plugin_technical_guide.md         # 総合技術解説ガイド
├── LICENSE                           # MITライセンス条項
│
├── ui/                               # 統合UIパッケージ (PySide6 / PySide2)
│   ├── __init__.py                   # UIエクスポート定義
│   ├── gui.py                        # モダン統合タブ型UI (多重起動防止・リアルタイムベイク連携)
│   ├── gui_style.py                  # UIダークテーマスタイルシート (QSS)
│   ├── morph_window.py               # 表情・モーフ操作GUI (4分割パネル・材質モーフ自動連携)
│   ├── advanced_dict_dialog.py       # 高度なユーザー辞書・マテリアル保護設定GUI (左右分割・上級者向け)
│   ├── bone_state_export_dialog.py   # ボーン状態・トランスフォーム情報エクスポートGUI
│   ├── material_protect_dialog.py    # マテリアル保護キーワード管理GUI
│   └── user_dict_dialog.py           # 未登録ボーン名検出・対話型辞書登録ダイアログ
│
├── converters/                       # Maya ↔ MMD 相互変換・解析エンジンパッケージ
│   ├── __init__.py                   # コンバータエクスポート定義
│   ├── pmxpaimaya.py                 # MMDモデル (PMX推奨、非推奨: PMD/X) インポートエンジン (材質モーフ/透過遮光/IK)
│   ├── pmd2pmx.py                    # PMDからPMXへの自動変換エンジン (剛体・ジョイント対応)
│   ├── vmdpaimaya.py                 # MMDモーション (VMD) アニメーション適用エンジン
│   ├── physics_stream.py             # 外部C#物理ビューア連携・リアルタイムストリーミング＆ベイク
│   ├── vmd_analyzer.py               # VMDモーション構造解析・診断モジュール
│   ├── mayapaipmx.py                 # MayaシーンからPMXへのエクスポートエンジン
│   └── bullet_builder.py             # 剛体構築補助モジュール
│
├── pmx_analyzer/                     # PMXモデル詳細解析・一括保存 & ユーザー辞書対話登録パッケージ
│   ├── __init__.py                   # 解析パッケージエクスポート定義
│   ├── analyzer_core.py              # 材質・ボーン・モーフ・剛体・Joint一括シリアライズ保存 & 未登録漢字抽出
│   └── user_dict_dialog.py           # 未登録ボーン名検出・ローマ字入力登録GUI & 再チェック (サイドチェック)
│
├── mmd_material_plugin/              # MMD専用シェーダー C++ プラグイン (Viewport 2.0 対応)
│   ├── bin/
│   │   ├── 2025/mmd_material.mll     # Maya 2025 用コンパイル済みシェーダープラグイン
│   │   ├── 2026/mmd_material.mll     # Maya 2026 用コンパイル済みシェーダープラグイン
│   │   └── mmd_material.mll          # 標準リンク用シェーダープラグイン
│   ├── shaders/
│   │   └── mmd_material.fx           # Viewport 2.0 (DirectX 11) HLSL シェーダー
│   ├── src/
│   │   ├── mmd_material_node.cpp     # MPxNode 派生シェーダーノード実装
│   │   ├── mmd_material_override.cpp # MPxShaderOverride 描画オーバーライド実装
│   │   └── ...
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
│   ├── bin/Release/net8.0-windows/   # 実行可能バイナリ群 (PhysicsSimulationBakeViewer.exe, BulletSharp.dll, etc.)
│   ├── App.xaml / App.xaml.cs        # アプリケーションエントリ
│   ├── ViewerWindow.xaml / .cs       # 物理シミュレーション同期描画ウィンドウ
│   ├── PoseEvaluator.cs              # ボーンポーズ・物理挙動リアルタイム評価
│   └── PhysicsSimulationBakeViewer.csproj # プロジェクト定義
│
├── physics_bridge_cs/                # MMD物理演算シミュレーションビューア (C# / .NET 8 / WPF)
│   ├── bin/Release/net8.0-windows/   # 実行可能バイナリ群 (MmdPhysicsBridge.exe, BulletSharp.dll, etc.)
│   ├── MainWindow.xaml / .cs         # ビューア操作・描画画面
│   ├── PhysicsSimulationEngine.cs    # BulletSharp 物理シミュレーションコア
│   ├── PmxLoader.cs / VmdLoader.cs   # 高速 PMX / VMD 読み込みモジュール
│   └── MmdPhysicsBridge.csproj       # プロジェクト定義
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
├── mmd_core/                         # 自作MMDバイナリ/テキスト構文解析パッケージ (MIT)
│   ├── __init__.py                   # パッケージエクスポート定義
│   ├── pmx.py                        # PMX 2.0 / 2.1 パーサー & ライター (推奨標準フォーマット)
│   ├── pmd.py                        # PMD (旧形式) パーサー & PMX自動変換 (非推奨)
│   ├── x_file.py                     # DirectX (.x) 構文解析器 (非推奨)
│   ├── vmd.py                        # VMD モーションパーサー
│   └── vpd.py                        # VPD ポーズパーサー
│
├── asset/                            # 辞書データ・補助モジュール
│   ├── user_dict_manager.py          # ユーザー辞書・マテリアル保護設定管理モジュール
│   ├── user_dictionary.json          # ユーザー設定永続化ファイル (保護キーワード・カスタム辞書)
│   ├── bone_dict.py                  # 標準ボーン日英相互変換モジュール (ユーザー辞書連動)
│   ├── bone_dict.json                # 標準ボーン定義JSON
│   ├── jaka.py                       # 日本語/中国語ノード名のローマ字変換 & 健全化
│   ├── jaka_dict.json                # ローマ字変換定義JSON
│   ├── hik.py                        # HumanIK (HIK) ボーン定義マッピング
│   ├── hik_dict.json                 # HIKボーンマッピング定義JSON
│   ├── last_imported_structure.json  # 前回インポート時の専用ボーン構造キャッシュ
│   ├── khatangton1.txt               # インポートUI設定永続化ファイル
│   └── khatangton2.txt               # エクスポートUI設定永続化ファイル
│
├── toon/                             # MMD標準トゥーンテクスチャ
│   └── toon01.bmp ～ toon10.bmp      # 各階調用標準BMPテクスチャ群
│
└── docs/                             # 独立技術仕様書群
    ├── codebase_architecture_specification.md # 本ファイル (全体の構造・各モジュール仕様)
    ├── mmd_material_plugin_specification.md   # Viewport 2.0 対応 C++ シェーダープラグイン仕様
    ├── pmx_analyzer_specification.md          # PMXモデル詳細解析・一括保存 & ユーザー辞書対話登録仕様
    ├── bullet_engine_specification.md         # MMD本家 Bullet 物理演算エンジン仕様
    ├── model_import_specification.md          # モデルインポート・材質モーフ・Toon・質感仕様
    ├── physics_system_specification.md        # Maya物理システム連携仕様
    ├── vmd_import_specification.md            # VMDインポート仕様
    ├── xpbd_engine_specification.md           # C++ XPBDエンジン仕様
    ├── realtime_physics_bake_specification.md # リアルタイム物理ベイク技術仕様 (bullet_engine ✕ physics_bake_cs)
    ├── technical_overview_guide.md            # インポートから物理ベイクまでの仕組み解説 (総合図解ガイド)
    └── plugin_technical_guide.md             # プラグイン総合技術解説ガイド
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

PySide6 / PySide2 デュアル対応のモダン UI を提供します。

### 3-1. `ui/gui.py`

- **主要クラス**: `MmdMayaMainWindow` (メインウィンドウ)
- **主要タブ**:
  - `ImportTabWidget`: モデルインポート（PMX推奨、PMD/.x非推奨、PMD自動変換機能内包）、PMX詳細解析・一括保存 (JSON)、未登録ボーン辞書登録連携、Toon/影設定。
  - `VmdImportTabWidget`: VMD モーション・カメラ・WAV 音声インポート（QScrollArea によるスクロール対応）。
  - `ExportTabWidget`: エクスポート関連機能を一元集約した統合タブ（QScrollArea 対応・縦長解消）。
    - モデルデータ (.pmx) エクスポート（試験的機能）
    - モーションデータ (.vmd) エクスポート（試験的機能）
    - ポーズデータ (.vpd) エクスポート（試験的機能）
  - `ExtraTabWidget`: PMXモデル解析・辞書照合、表情操作ウィンドウ起動、HumanIK管理、スタンドアロン物理ビューア起動、アクセサリ追従アタッチ、および VPD ポーズデータ (.vpd) 適用（キーフレーム自動登録対応）ユーティリティ。
  - `HumanIKTabWidget`: HIK キャラクター定義・Tポーズ自動展開、コントロールリグ生成、二重IK競合解除。
  - `PhysicsTabWidget`: Maya内部 Bullet / XPBD 物理演算設定、剛体・Joint可視化生成、再吸着、追突防止複数モデル順次ベイク対応。
  - `PhysicsGuiTabWidget`: 外部新3D物理ビューア（`PhysicsSimulationBakeViewer.exe`）連携、リアルタイム同期ベイク、追突防止複数モデル順次ベイク対応。
  - `CleanupTabWidget`: シーン内 MMD 要素（モデル、ボーン、カメラ、ライト、地面影、および未使用マテリアル）の一括削除（対象モデル選択と全削除ボタンのみのシンプル設計）。
- **補助ダイアログ**:
  - `ExecutionLogDialog`: リアルタイム進捗ログダイアログ（中断・コピー機能付き）。
  - `MultiModelPhysicsBakeDialog`: ベイクするモデルの確認ダイアログ（単体・複数問わず現在ベイク対象として設定されているモデル一覧の確認）。

### 3-2. `ui/morph_window.py`

- **主要クラス**: `MorphWindow` (表情・モーフ操作GUI)
- **役割**:
  - 「目」「まゆ」「リップ」「その他」の4分割パネル構成でスライダー操作・キーフレーム登録を提供。
  - **動的バインド & タイムスライダー追従**: アクティブなモデルへ自動バインドし、タイムライン移動に合わせてモーフウェイト値をリアルタイムにUIへ同期。
  - **材質モーフ連携**: 頂点モーフだけでなく、頬染め・目発光・帽子off・ドロワoff等の材質モーフアトリビュートを自動操作。加算・乗算オフセット演算に基づき、受光・輪郭線（エッジ）の連動フェードを制御。
  - **自作表情プリセット機能（試験的機能）**: 複数の表情スライダーを調整したカスタム表情をプリセットとして保存・一覧から瞬時に呼び出し可能。
  - **アクセサリ追従アタッチ機能（試験的機能）**: メガネ・髪飾り・武器等の小道具メッシュを、頭や手などの指定ボーンへ自動追従させるコンストレイント構築。

### 3-3. `ui/advanced_dict_dialog.py`

- **主要クラス**: `AdvancedDictDialog`
- **役割**: マテリアル保護キーワードおよびカスタムボーン日英辞書の上級者向け直接編集ダイアログ。

### 3-4. `ui/material_protect_dialog.py`

- **主要クラス**: `MaterialProtectDialog`
- **役割**: 顔や肌など、アニメ調特有のスペキュラ抑止・Toon保護対象となるマテリアルキーワードを視覚的に追加・削除・編集するダイアログ。

### 3-5. `ui/bone_state_export_dialog.py`

- **主要クラス**: `BoneStateExportDialog`
- **役割**: 現在のモデルのボーン姿勢・トランスフォーム情報を抽出・保存するユーティリティGUI。

### 3-6. `ui/user_dict_dialog.py`

- **主要クラス**: `UserDictRegisterDialog`
- **役割**: インポート時に未登録の漢字ボーン名が検出された際、ローマ字入力欄を並べて即座に辞書へ登録する対話型ダイアログ。

### 3-7. `ui/gui_style.py`

- **役割**: ダークテーマ QSS スタイルシート定義。

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

## 8. `mmd_motion_plugin/` パッケージ仕様 (高速モーション C++ プラグイン)

大規模モーションデータのインポートおよび補間曲線計算をネイティブ C++ で高速化する拡張モジュールです。

- **`bin/2025/mmd_motion.mll` / `bin/2026/mmd_motion.mll`**: 各年度版 Maya 専用コンパイル済みプラグイン。
- **特徴**: 大量フレームの補間カーブ展開において Python 実行オーバーヘッドを削減し、安定したフレーム生成を実現。

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

## 13. `asset/` モジュール・データ仕様 (辞書・ユーティリティ)

- **`user_dict_manager.py`**: ユーザー辞書・マテリアル保護設定管理。
- **`user_dictionary.json`**: ユーザー設定永続化ファイル（保護キーワード、カスタム辞書）。
- **`bone_dict.py` / `bone_dict.json`**: 標準ボーン日英相互変換モジュールおよび定義データ。
- **`jaka.py` / `jaka_dict.json`**: 日本語/中国語ノード名のローマ字変換 & 健全化。
- **`hik.py` / `hik_dict.json`**: HumanIK (HIK) ボーン定義マッピング（Tポーズ展開、膝の優先角度 `preferredAngle` & プレベンド設定、つま先ボーン対応）。
- **`last_imported_structure.json`**: 前回インポート時の専用ボーン構造キャッシュ。
- **`khatangton1.txt` / `khatangton2.txt`**: UI設定永続化ファイル。

---

## 14. `toon/` ディレクトリ仕様

MMD 標準のトゥーン階調テクスチャ（`toon01.bmp` 〜 `toon10.bmp`）を格納。モデルインポート時に参照・適用されます。

---

## 15. `docs/` & `ai-task-docs/`

- **`docs/`**: 各サブシステムの公式設計仕様書群。
  - `codebase_architecture_specification.md` (全体構造仕様書 - 本ドキュメント)
  - `mmd_material_plugin_specification.md` (Viewport 2.0 C++ シェーダー仕様書)
  - `pmx_analyzer_specification.md` (PMXモデル詳細解析 & ユーザー辞書仕様書)
  - `bullet_engine_specification.md` (Bullet物理仕様書)
  - `model_import_specification.md` (モデルインポート・質感・材質モーフ仕様書)
  - `physics_system_specification.md` (Maya物理システム仕様書)
  - `vmd_import_specification.md` (VMDインポート仕様書)
  - `xpbd_engine_specification.md` (XPBD物理仕様書)
  - `realtime_physics_bake_specification.md` (リアルタイム物理ベイク技術仕様書: bullet_engine ✕ physics_bake_cs)
  - `technical_overview_guide.md` (インポートから物理ベイクまでの仕組み解説: 総合図解仕様書)
  - `plugin_technical_guide.md` (プラグイン総合技術解説ガイド)
- **`ai-task-docs/`**: AIペアプログラミングによる機能アップデートごとの計画・タスクリスト・確認書を格納（Git除外）。
