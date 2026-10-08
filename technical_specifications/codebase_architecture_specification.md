# コードベース構成・各モジュール仕様書

本ドキュメントは、「MMD Tools for Maya」プロジェクトを構成する全ディレクトリ、Python スクリプト、C++ エンジンソース、ヘッダー、DLL、およびリソースファイルのファイル一覧と詳細な仕様を網羅的に定めたものです。

---

## 1. プロジェクト全体ディレクトリツリー

```text
mmd_tools_for_maya/
├── mmd_tools_for_maya_plugin.py      # Mayaプラグイン公式エントリポイント
├── mmdpaimaya_plugin.py              # 旧プラグイン互換性維持ラッパー
├── gui.py                            # モダン統合タブ型UI (PySide6 / PySide2)
├── gui_style.py                      # UIダークテーマスタイルシート (QSS)
├── pmxpaimaya.py                     # MMDモデル (PMX/PMD/X) Mayaインポートエンジン
├── vmdpaimaya.py                     # MMDモーション (VMD) アニメーション適用エンジン
├── vmd_analyzer.py                   # VMDモーション構造解析・診断モジュール
├── mayapaipmx.py                     # MayaシーンからPMXへのエクスポートエンジン
├── bullet_builder.py                 # レガシー剛体構築補助モジュール
├── __init__.py                       # パッケージ初期化モジュール
├── README.md                         # プロジェクト概要・導入手順
├── plugin_technical_guide.md         # 総合技術解説ガイド
├── LICENSE                           # MITライセンス条項
│
├── mmd_core/                         # 自作MMDバイナリ/テキスト構文解析パッケージ
│   ├── __init__.py                   # パッケージエクスポート定義
│   ├── pmx.py                        # PMX 2.0 / 2.1 パーサー & ライター
│   ├── pmd.py                        # PMD (MMD旧形式) パーサー & PMX自動変換
│   ├── x_file.py                     # DirectX (.x) テキスト/バイナリ構文解析器
│   ├── vmd.py                        # VMD モーションパーサー
│   └── vpd.py                        # VPD ポーズパーサー
│
├── cpp_engine/                       # C++ XPBD 物理演算エンジン
│   ├── bin/
│   │   └── mmd_xpbd.dll              # コンパイル済みXPBD物理エンジンDLL
│   ├── include/
│   │   └── xpbd_engine.h             # XPBDエンジンヘッダー (クラス・構造体定義)
│   ├── src/
│   │   └── xpbd_engine.cpp           # XPBDエンジン実装 (拘束解決・コリジョン)
│   ├── build_dll.py                  # MSVC / MinGW 自動検出DLLビルドスクリプト
│   ├── xpbd_wrapper.py               # ctypes による C++ DLL Pythonバインディング
│   ├── xpbd_visualizer.py            # Maya剛体メッシュ・Jointロケーター可視化・再吸着
│   ├── xpbd_maya_bridge.py           # 物理シミュレーションベイク制御エンジン
│   └── test_xpbd.py                  # XPBDエンジンスタンドアロン単体テスト
│
├── asset/                            # ユーティリティデータ・補助モジュール
│   ├── bone_dict.py                  # 標準ボーン日英相互変換辞書モジュール
│   ├── jaka.py                       # 日本語/中国語ノード名のローマ字変換 & 安全化
│   ├── hik.py                        # HumanIK (HIK) ボーン定義マッピング
│   ├── last_imported_structure.json  # 前回インポート時の日英ボーン構造キャッシュ
│   └── khatangton.txt                # UI設定永続化ファイル
│
├── toon/                             # MMD標準共有トゥーンテクスチャ
│   └── toon01.bmp 〜 toon10.bmp      # 階調陰影用標準BMPテクスチャ群
│
└── docs/                             # プロジェクト技術ドキュメント
    ├── technical_specifications/     # 分離独立した専門技術仕様書群 (本フォルダ)
    │   ├── model_import_specification.md      # モデルインポート仕様
    │   ├── vmd_import_specification.md        # VMDインポート仕様
    │   ├── physics_system_specification.md    # Maya物理システム仕様
    │   ├── xpbd_engine_specification.md       # C++ XPBDエンジン仕様
    │   └── codebase_architecture_specification.md # 本ファイル
    └── ... (各機能アップデートごとの実装計画・タスクリスト・確認録)
```

---

## 2. ルート階層モジュール仕様

### 2-1. `mmd_tools_for_maya_plugin.py`

- **種別**: Python (Mayaプラグインエントリポイント)
- **役割**: Maya のプラグインマネージャから直接ロードされ、トップメニューバーに「MMD」メニューを登録。
- **主要関数**:
  - `initializePlugin(plugin_obj)`: プラグイン登録、検索パス（`sys.path`）の設定、メニュー生成。
  - `uninitializePlugin(plugin_obj)`: プラグイン登録解除、メニュー消去。
  - `on_open_gui()`: モジュール強制リロード対応の GUI 起動ハンドラ。
  - `on_show_about()`: バージョン・開発者・機能サマリー表示ダイアログ。

### 2-2. `gui.py`

- **種別**: Python (UIモジュール)
- **役割**: PySide6 (Maya 2025+) および PySide2 (Maya 2022-2024) 両対応のタブ型統合インターフェース。
- **主要クラス**:
  - `MmdMayaMainWindow`: メインウィンドウ。
  - `ImportTabWidget`: PMX/PMD/X インポート設定（スケール、メッシュ結合、トゥーン等）。
  - `VmdImportTabWidget`: VMD モーション・カメラ・音源インポート設定。
  - `PhysicsTabWidget`: XPBD 物理演算設定、剛体・Joint可視化生成、再吸着、ベイク実行。
  - `ExportTabWidget`: Maya シーンから PMX へのエクスポート設定。
  - `HikTabWidget`: HumanIK スケルトン定義マッピング設定。
  - `CleanupTabWidget`: シーン内アニメーション初期化・MMD要素全削除。
  - `ExecutionLogDialog`: プログレスバー付きリアルタイムログダイアログ。

### 2-3. `pmxpaimaya.py`

- **種別**: Python (モデルインポートエンジン)
- **役割**: パース済み PMX 構造体から Maya API 2.0（`MFnMesh`）を用いた高速メッシュ生成、マテリアル構築、スケルトン階層構築、足IK構築、スキニング（SkinCluster）、モーフ（BlendShape）設定を統括。
- **主要関数**: `import_pmx`, `create_mesh`, `setup_mmd_ik`, `create_mmd_lighting`。

### 2-4. `vmdpaimaya.py`

- **種別**: Python (モーションインポートエンジン)
- **役割**: VMD バイナリを解析し、Maya タイムラインへ 30fps キーフレームアニメーション（クォータニオン $\rightarrow$ オイラー角、ベジェ接線）を適用。カメラおよび WAV 音源も同期配置。
- **主要関数**: `import_vmd`, `apply_bone_motion`, `apply_morph_motion`, `apply_camera_motion`, `delete_mmd_scene_elements`。

### 2-5. `mayapaipmx.py`

- **種別**: Python (エクスポートエンジン)
- **役割**: Maya シーン内の選択メッシュ、ボーン、ウェイト、マテリアル情報を収集し、PMX 2.0 バイナリとして書き出し。

---

## 3. `mmd_core/` パッケージ仕様 (バイナリパーサー群)

外部 pip パッケージに一切依存せず、Python 標準の `struct` モジュールのみで高速パースを実行。

- **`pmx.py`**:
  - PMX 2.0 / 2.1 の頂点、面、マテリアル、ボーン、モーフ、剛体、ジョイントの完全な読み書きに対応。
- **`pmd.py`**:
  - MMD 旧形式 PMD の Shift_JIS バイナリを解析し、メモリ上で PMX 互換構造体へ変換（`load2pmx`）。
- **`x_file.py`**:
  - DirectX (.x) 形式のトークナイザー字句解析器。テンプレートスキップおよびメッシュ・材質・法線・UV抽出。
- **`vmd.py`**:
  - ボーン、モーフ、カメラ、ライト、シャドウのキーフレーム解析器。
- **`vpd.py`**:
  - VPD ポーズファイルのテキスト解析器。

---

## 4. `cpp_engine/` パッケージ仕様 (C++ 物理演算エンジン)

- **`src/xpbd_engine.cpp` & `include/xpbd_engine.h`**:
  - Extended Position Based Dynamics アルゴリズムによる剛体シミュレーションコア。
  - サブステップ積分、Aligned 剛体の重力遮断および位置固定、MMD 6DOF ジョイント拘束（ハードリミット・角度復元）、球/箱/カプセルの接触判定。
- **`bin/mmd_xpbd.dll`**:
  - C++ コアを 64-bit Windows 用共有ライブラリとしてビルドしたバイナリ。
- **`build_dll.py`**:
  - Visual Studio (`cl.exe`) または MinGW (`g++`) を自動検出し、DLL をワンクリックでコンパイル・配置するスクリプト。
- **`xpbd_wrapper.py`**:
  - `ctypes` を介して `mmd_xpbd.dll` の C言語関数を Python オブジェクト指向インターフェースとしてラッピング。
- **`xpbd_visualizer.py`**:
  - Maya シーン内に剛体形状（球・箱・カプセル）メッシュおよび Joint ロケーターを自動生成。
  - ボーン追従コンストレイント設定、キーフレームクリア、モデルへの再吸着処理（`reconnect_visualizers_to_bones`）を担当。
- **`xpbd_maya_bridge.py`**:
  - Maya タイムラインを進行させながら C++ エンジンと連携し、物理結果をジョイントへキーフレーム記録するベイクエンジン。

---

## 5. `asset/` モジュール仕様 (辞書・ユーティリティ)

- **`bone_dict.py`**:
  - mikudan, blender2pmxem, usausakokoko の標準ボーン対応表を網羅した日英双方向変換辞書。左右接頭辞/接尾辞（`_L`/`_R` $\leftrightarrow$ `左`/`右`）の自動解決を提供。
- **`jaka.py`**:
  - 日本語（漢字・かな）および中国語（簡体字）を安全なローマ字表記に変換し、Maya ノード命名規則エラーを防止。
- **`hik.py`**:
  - MMD ボーン構造を Maya の HumanIK キャラクター定義へマッピングする定義テーブル。
- **`last_imported_structure.json`**:
  - 最新のモデルインポート時に出力された和名・英名両対応のボーン階層・DAG パスキャッシュ。
