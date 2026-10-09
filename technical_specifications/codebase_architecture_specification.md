# コードベース構成・各モジュール仕様書

本ドキュメントは、「MMD Tools for Maya」プロジェクトを構成する全ディレクトリ、Python スクリプト、C++ エンジンソース、ヘッダー、DLL、およびリソースファイルのファイル一覧と詳細な仕様を網羅的に定めたものです。

---

## 1. プロジェクト全体ディレクトリツリー

```text
mmd_tools_for_maya/
├── mmd_tools_for_maya_plugin.py      # Mayaプラグイン公式エントリポイント
├── gui.py                            # モダン統合タブ型UI (PySide6 / PySide2)
├── gui_style.py                      # UIダークテーマスタイルシート (QSS)
├── pmxpaimaya.py                     # MMDモデル (PMX/PMD/X) Mayaインポートエンジン (Toon/セルフ影3段階/IK)
├── vmdpaimaya.py                     # MMDモーション (VMD) アニメーション適用エンジン
├── vmd_analyzer.py                   # VMDモーション構造解析・診断モジュール
├── mayapaipmx.py                     # MayaシーンからPMXへのエクスポートエンジン
├── bullet_builder.py                 # レガシー剛体構築補助モジュール
├── __init__.py                       # パッケージ初期化モジュール
├── README.md                         # プロジェクト概要・導入手順
├── plugin_technical_guide.md         # 総合技術解説ガイド
├── LICENSE                           # MITライセンス条項
│
├── mmd_core/                         # 自作MMDバイナリ/テキスト構文解析パッケージ (MIT)
│   ├── __init__.py                   # パッケージエクスポート定義
│   ├── pmx.py                        # PMX 2.0 / 2.1 パーサー & ライター
│   ├── pmd.py                        # PMD (MMD旧形式) パーサー & PMX自動変換
│   ├── x_file.py                     # DirectX (.x) テキスト/バイナリ構文解析器
│   ├── vmd.py                        # VMD モーションパーサー
│   └── vpd.py                        # VPD ポーズパーサー
│
├── bullet_engine/                    # MMD本家 Bullet 2.83.7 物理演算エンジン (zlib license)
│   ├── bin/
│   │   └── mmd_bullet.dll            # コンパイル済み Bullet 物理エンジンDLL
│   ├── include/                      # Bullet C++ ヘッダー群 (LinearMath, BulletCollision, BulletDynamics)
│   ├── src/                          # Bullet C++ ソース群 & C-API エクスポートラッパー
│   ├── build_bullet_dll.py           # MSVC / MinGW 自動検出 DLL ビルドスクリプト
│   ├── bullet_wrapper.py             # ctypes による Bullet DLL Python バインディング (ウォームアップ・リセット機能)
│   ├── bullet_maya_bridge.py         # Bullet 物理シミュレーション・Maya ベイク制御エンジン
│   ├── LICENSE                       # Bullet 公式 zlib ライセンス条項
│   └── README.md                     # Bullet エンジン概要・ビルド手順
│
├── cpp_engine/                       # C++ XPBD 物理演算エンジン (MIT)
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
│   └── khatangton.txt                # UI設定永続化ファイル (シャドウモード・各種フラグ)
│
├── toon/                             # MMD標準共有トゥーンテクスチャ
│   └── toon01.bmp 〜 toon10.bmp      # 階調陰影用標準BMPテクスチャ群
│
├── technical_specifications/         # 分離独立した専門技術仕様書群
│   ├── codebase_architecture_specification.md # 本ファイル (全体構成・各モジュール仕様)
│   ├── bullet_engine_specification.md         # MMD本家 Bullet 物理演算エンジン仕様
│   ├── model_import_specification.md          # モデルインポート・Toon＆セルフ影再現仕様
│   ├── physics_system_specification.md        # Maya物理システム仕様
│   ├── vmd_import_specification.md            # VMDインポート仕様
│   └── xpbd_engine_specification.md           # C++ XPBD物理エンジン仕様
│
└── docs/                             # プロジェクト機能アップデート・開発作業記録録
    └── ... (各機能アップデートごとの実装計画・タスクリスト・確認録)
```

---

## 2. ルート階層モジュール仕様

### 2-1. `mmd_tools_for_maya_plugin.py`

- **種別**: Python (Mayaプラグインエントリポイント)
- **役割**: Maya のプラグインマネージャから直接ロードされ、トップメニューバーに「MMD」メニューを登録。
- **主要関数**:
  - `initializePlugin(plugin_obj)`: プラグイン登録、検索パス（`sys.path`）の設定、メニュー生成。
  - `uninitializePlugin(plugin_obj)`: プラグイン解除、メニュー消去。
  - `on_open_gui()`: モジュール強制リロード対応の GUI 起動ハンドラ。
  - `on_show_about()`: バージョン・開発者・機能サマリー表示ダイアログ。

### 2-2. `gui.py`

- **種別**: Python (UIモジュール)
- **役割**: PySide6 (Maya 2025+) および PySide2 (Maya 2022-2024) 両対応のタブ型統合インターフェース。
- **主要機能 & クラス**:
  - `MmdMayaMainWindow`: メインウィンドウ。
  - `ImportTabWidget`: PMX/PMD/X インポート設定。
    - **Toonシェーディング & セルフ影ラジオボタン**: 「セルフ影なし」「モード1」「モード2」のリアルタイム選択。
    - **既存シーン設定変更**: 「既存シーンのToonシェーディング設定変更」ボタンにより、インポート済みシーンの影モードやワールド空間Toonを即座に再設定。
    - **設定永続化**: シャドウモードやメッシュ結合設定を `khatangton.txt` へ自動保存・復元。
  - `VmdImportTabWidget`: VMD モーション・カメラ・音源インポート設定。
  - `PhysicsTabWidget`: Bullet / XPBD 物理演算設定、剛体・Joint可視化生成、再吸着、物理ベイク実行（DLL自動検出による安全なフォールバック）。
  - `ExportTabWidget`: Maya シーンから PMX へのエクスポート設定。
  - `HikTabWidget`: HumanIK スケルトン定義マッピング設定。
  - `CleanupTabWidget`: シーン内アニメーション初期化・MMD要素全削除。
  - `ExecutionLogDialog`: プログレスバー付きリアルタイムログダイアログ。

### 2-3. `pmxpaimaya.py`

- **種別**: Python (モデルインポートエンジン)
- **役割**: パース済み PMX 構造体から Maya API 2.0（`MFnMesh`）を用いた高速メッシュ生成、マテリアル構築、スケルトン階層構築、足IK構築、スキニング（SkinCluster）、モーフ（BlendShape）設定を統括。
- **Toonシェーディング & MMD照明再現機能**:
  - `create_mmd_lighting(shadow_mode=1)`: MMDデフォルト照明（RGB 154、照射角: RotateX -54.74°, RotateY 45.0°, RotateZ 0.0°）の自動生成とセルフ影制御。
    - `shadow_mode=0`: セルフ影なし（Depth Map Shadows OFF、Toon明暗は維持）。
    - `shadow_mode=1`: モード1（解像度2048、フィルタ3、バイアス0.015）。
    - `shadow_mode=2`: モード2（解像度4096、フィルタ1、バイアス0.010）。
  - **ワールド空間Toonシェーディング**: `samplerInfo.normalCamera` を `matrixEyeToWorld` によりワールド空間法線へと変換し、固定光線ベクトルとの内積を算出。カメラ回転による影のズレを完全解消。
  - **StandardSurface質感制御**: 顔・肌マテリアルにおける不要なスペキュラ反射を抑制し、MMD特有のマットなセル調質感を確保。
  - `fix_toon_shading_in_scene(shadow_mode)`: 既存シーンのToonシェーダーおよび照明をインプレースで修復・更新。

### 2-4. `vmdpaimaya.py`

- **種別**: Python (モーションインポートエンジン)
- **役割**: VMD バイナリを解析し、Maya タイムラインへ 30fps キーフレームアニメーション（クォータニオン $\rightarrow$ オイラー角、ベジェ接線）を適用。カメラおよび WAV 音源も同期配置。
- **主要関数**: `import_vmd`, `apply_bone_motion`, `apply_morph_motion`, `apply_camera_motion`, `delete_mmd_scene_elements`。

### 2-5. `mayapaipmx.py`

- **種別**: Python (エクスポートエンジン)
- **役割**: Maya シーン内の選択メッシュ、ボーン、ウェイト、マテリアル情報を収集し、PMX 2.0 バイナリとして書き出し。

---

## 3. `bullet_engine/` パッケージ仕様 (MMD本家 Bullet 物理演算エンジン)

MMD 本家（MikuMikuDance）と 100% 互換の挙動を実現する Bullet 2.83.7 ベースの物理演算モジュールです。ライセンスは zlib license で完全分離されています。

- **`bullet_wrapper.py`**:
  - `ctypes` による `mmd_bullet.dll` の Python ラッパー。
  - **剛体のボーンポーズへの強制同期リセット**: インポート時や現在フレームのボーン姿勢から剛体のワールド姿勢を逆算し、強制同期配置。
  - **めり込み解消ウォームアップ処理 (`relax_penetration`)**: 外力ゼロ・高ダンピング（0.99）下で接触反発インパルスのみを25ステップ解き、太ももとスカート等の初期めり込みを初速ゼロのまま外側へ押し出す。
  - **初速ゼロ化・拘束リセット (`reset_velocities`, `reset_constraints`)**: ベイク開始時のゴム跳ね・振動・破綻を防止し、滑らかな揺れ出しを保証。
- **`bullet_maya_bridge.py`**:
  - PMX 剛体・ジョイントパラメータを Bullet 構造体へ変換し、Maya タイムライン進行に連動してシミュレーションを実行。
  - DAG 階層深度ソート（親から子へ）および OpenMaya マトリクス逆算（`jointOrient`, `rotateAxis` の相殺）により、正確なローカル回転角をキーフレーム記録。
- **`build_bullet_dll.py`**:
  - Visual Studio (`cl.exe`) または MinGW (`g++`) を自動検出し、Bullet ソースコードから単一 DLL（`mmd_bullet.dll`）をビルド。

---

## 4. `mmd_core/` パッケージ仕様 (バイナリパーサー群)

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

## 5. `cpp_engine/` パッケージ仕様 (C++ XPBD 物理演算エンジン)

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

## 6. `asset/` モジュール仕様 (辞書・ユーティリティ)

- **`bone_dict.py`**:
  - mikudan, blender2pmxem, usausakokoko の標準ボーン対応表を網羅した日英双方向変換辞書。左右接頭辞/接尾辞（`_L`/`_R` $\leftrightarrow$ `左`/`右`）の自動解決を提供。
- **`jaka.py`**:
  - 日本語（漢字・かな）および中国語（簡体字）を安全なローマ字表記に変換し、Maya ノード命名規則エラーを防止。
- **`hik.py`**:
  - MMD ボーン構造を Maya の HumanIK キャラクター定義へマッピングする定義テーブル。
- **`last_imported_structure.json`**:
  - 最新のモデルインポート時に出力された和名・英名両対応のボーン階層・DAG パスキャッシュ。
- **`khatangton.txt`**:
  - UIの各種設定状態（セルフ影モード、Toon使用フラグ、スケール等）を永続化保存するテキスト設定ファイル。

