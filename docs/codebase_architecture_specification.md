# コードベース構成・各モジュール仕様書

本ドキュメントは、「MMD Tools for Maya」プロジェクトを構成する全ディレクトリ、Python スクリプト、C++ 物理エンジン、および各モジュールの責務と仕様を詳細に解説する仕様書です。

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
│   ├── gui.py                        # モダン統合タブ型UI (多重起動防止・閉じて再表示)
│   ├── gui_style.py                  # UIダークテーマスタイルシート (QSS)
│   └── advanced_dict_dialog.py       # 高度なユーザー辞書・マテリアル保護設定GUI (左右分割・上級者向け)
│
├── converters/                       # Maya ↔ MMD 相互変換・解析エンジンパッケージ
│   ├── __init__.py                   # コンバータエクスポート定義
│   ├── pmxpaimaya.py                 # MMDモデル (PMX/PMD/X) Mayaインポートエンジン (Toon/セルフ影3段階/IK)
│   ├── vmdpaimaya.py                 # MMDモーション (VMD) アニメーション適用エンジン
│   ├── vmd_analyzer.py               # VMDモーション構造解析・診断モジュール
│   ├── mayapaipmx.py                 # MayaシーンからPMXへのエクスポートエンジン
│   └── bullet_builder.py             # レガシー剛体構築補助モジュール
│
├── pmx_analyzer/                     # PMXモデル詳細解析・一括保存 & ユーザー辞書対話登録パッケージ
│   ├── __init__.py                   # 解析パッケージエクスポート定義
│   ├── analyzer_core.py              # 材質・ボーン・モーフ・剛体・Joint一括シリアライズ保存 & 未登録漢字抽出
│   └── user_dict_dialog.py           # 未登録ボーン名検出・ローマ字入力登録GUI & 再チェック (サイドチェック)
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
│   │   └── xpbd_engine.cpp           # XPBDエンジン実装 (剛体・拘束・衝突)
│   ├── build_dll.py                  # MSVC / MinGW 自動検出DLLビルドスクリプト
│   ├── xpbd_wrapper.py               # ctypes による C++ DLL Pythonバインディング
│   ├── xpbd_visualizer.py            # Maya上のメッシュ・Jointロケーター追従・再吸着
│   ├── xpbd_maya_bridge.py           # シミュレーションベイク制御エンジン
│   └── test_xpbd.py                  # XPBDエンジンスタンドアロン単体テスト
│
├── asset/                            # ユーティリティデータ・補助モジュール
│   ├── user_dict_manager.py          # ユーザー辞書・マテリアル保護設定管理モジュール
│   ├── user_dictionary.json          # ユーザー設定永続化ファイル (保護キーワード・カスタム辞書)
│   ├── bone_dict.py                  # 標準ボーン日英相互変換モジュール (ユーザー辞書連動)
│   ├── jaka.py                       # 日本語/中国語ノード名のローマ字変換 & 健全化 (ユーザー辞書連動・動的リロード)
│   ├── hik.py                        # HumanIK (HIK) ボーン定義マッピング (Tポーズ展開・膝プレベンド・つま先対応)
│   ├── last_imported_structure.json  # 前回インポート時の専用ボーン構造キャッシュ
│   ├── khatangton1.txt               # インポートUI設定永続化ファイル (モデルパス・各種フラグ)
│   └── khatangton2.txt               # エクスポートUI設定永続化ファイル
│
├── toon/                             # MMD標準トゥーンテクスチャ
│   └── toon01.bmp ～ toon10.bmp      # 各階調用標準BMPテクスチャ群
│
├── docs/                               # 独立技術仕様書群
│   ├── codebase_architecture_specification.md # 本ファイル (全体の構造・各モジュール仕様)
│   ├── pmx_analyzer_specification.md          # PMXモデル詳細解析・一括保存 & ユーザー辞書対話登録仕様
│   ├── bullet_engine_specification.md         # MMD本家 Bullet 物理演算エンジン仕様
│   ├── model_import_specification.md          # モデルインポート・Toon・セルフ影・質感仕様
│   ├── physics_system_specification.md        # Maya物理システム連携仕様
│   ├── vmd_import_specification.md            # VMDインポート仕様
│   └── xpbd_engine_specification.md           # C++ XPBDエンジン仕様
│
└── docs/                             # プロジェクト機能アップデート・開発記録文書
    └── ... (各機能アップデートごとの計画・タスクリスト・確認書)
```

---

## 2. ルート階層モジュール仕様

### 2-1. `mmd_tools_for_maya_plugin.py`

- **種別**: Python (Mayaプラグイン公式エントリポイント)
- **役割**: Maya のプラグインマネージャから直接ロードされ、トップメニューバーに「MMD」メニューを登録。
- **主要関数**:
  - `initializePlugin(plugin_obj)`: プラグイン登録、検索パス（`sys.path`）への新規フォルダ（`ui`・`converters`・`pmx_analyzer`）追加、メニュー生成。
  - `uninitializePlugin(plugin_obj)`: プラグイン解除、メニュー破棄。
  - `on_open_gui()`: モジュールリロード対応 GUI 起動ハンドラ。**既存ウィンドウを検索して安全に破棄（`close` / `deleteLater`）した上で1つだけ再表示する多重起動防止機構**を内包。
  - `on_open_advanced_dict()`: 上級者向け警告ダイアログ付きのユーザー辞書・マテリアル保護設定 GUI 起動ハンドラ。
  - `on_show_about()`: バージョン・開発者・機能サマリー表示ダイアログ。

### 2-2. `__init__.py`

- **種別**: Python (パッケージ初期化モジュール)
- **役割**: `mmd_tools_for_maya` を単一の Python パッケージとして成立させるエントリポイント。
- **機能**:
  - サブパッケージ群（`ui`, `converters`, `mmd_core`, `pmx_analyzer`, `bullet_engine`, `cpp_engine`, `asset`）の安全なインポートと `sys.path` 解決。
  - 外部スクリプトからの `from mmd_tools_for_maya import pmxpaimaya, vmdpaimaya` 等の後方互換アクセスを保証。

---

## 3. `ui/` パッケージ仕様 (統合インターフェース群)

モダンな PySide6 / PySide2 デュアル対応 UI を提供します。

### 3-1. `ui/gui.py`

- **主要クラス**: `MmdMayaMainWindow` (メインウィンドウ)
- **主要タブ**:
  - `ImportTabWidget`: モデルインポート、PMXモデル詳細解析・一括保存 (JSON)、未登録ボーン辞書登録連携、Toon/影設定。
  - `VmdImportTabWidget`: VMD モーション・カメラ・WAV 音声インポート。
  - `ExportTabWidget`: Maya シーンから PMX 形式へのエクスポート。
  - `HumanIKTabWidget`: HIK キャラクター定義・Tポーズ（腕水平化＆膝プレベンド）自動展開、コントロールリグ生成、二重IK競合解除。
  - `PhysicsTabWidget`: Bullet / XPBD 物理演算設定、剛体・Joint可視化生成、再吸着、物理ベイク実行（DLL自動検出による安全なフォールバック）。
  - `CleanupTabWidget`: シーン内 MMD 要素の一括削除・初期化。
- **補助ダイアログ**: `ExecutionLogDialog` (リアルタイム進捗ログダイアログ・コピー機能付き)。

### 3-2. `ui/advanced_dict_dialog.py`

- **主要クラス**: `AdvancedDictDialog`
- **役割**: マテリアル保護キーワードおよびカスタムボーン日英辞書の上級者向け直接編集ダイアログ。

### 3-3. `ui/gui_style.py`

- **役割**: モダンなダークテーマ QSS スタイルシート定義。

### 3-4. `ui/__init__.py`

- **役割**: `MmdMayaMainWindow`, `show_ui`, `ExecutionLogDialog` 等の UI モジュール公開 API のエクスポート。

---

## 4. `converters/` パッケージ仕様 (変換・解析エンジン群)

### 4-1. `converters/pmxpaimaya.py`

- **主要関数**: `import_pmx`, `setup_mmd_ik`, `create_mmd_lighting`, `fix_toon_shading_in_scene`。
- **特徴**:
  - SDEF デュアルクォータニオン近似スキニング、PMX 剛体・Joint コライダー生成。
  - モデル構造キャッシュ (`asset/last_imported_structure.json`) の保存。

### 4-2. `converters/vmdpaimaya.py`

- **主要関数**: `import_vmd`, `apply_bone_motion`, `apply_morph_motion`, `apply_camera_motion`, `delete_mmd_scene_elements`。

### 4-3. `converters/vmd_analyzer.py`

- **主要クラス**: `VmdAnalyzer` (ボーン・モーフ・カメラキーフレーム統計解析)。

### 4-4. `converters/mayapaipmx.py`

- **主要関数**: `export_pmx` (Maya メッシュ・ジョイントから PMX への出力)。

### 4-5. `converters/bullet_builder.py`

- **役割**: レガシー剛体構築補助モジュール。

### 4-6. `converters/__init__.py`

- **役割**: コンバータ関連の公開 API を透過エクスポート。

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

### 5-3. `pmx_analyzer/__init__.py`

- **役割**: パッケージ公開 API のエクスポート。

---

## 6. `bullet_engine/` パッケージ仕様 (MMD本家 Bullet 物理演算エンジン)

MMD 本家（MikuMikuDance）と 100% 互換の挙動を実現する Bullet 2.83.7 ベースの物理演算モジュールです。

- **`bin/mmd_bullet.dll`**: 高速な C-API エクスポート物理 DLL。
- **`bullet_wrapper.py`**: ctypes による Python バインディング。
- **`bullet_maya_bridge.py`**: シミュレーションループ制御および Maya キーフレームベイク。

---

## 7. `mmd_core/` パッケージ仕様 (バイナリパーサー群)

外部依存ゼロの純粋な Python 標準ライブラリによるバイナリ／テキスト構文解析器です。

- **`pmx.py`**: PMX 2.0 / 2.1 パーサー & ライター。
- **`pmd.py`**: PMD パーサー & PMX 構造への透過変換。
- **`x_file.py`**: DirectX .x テキスト／バイナリ構文解析器。
- **`vmd.py`**: VMD モーションパーサー。
- **`vpd.py`**: VPD ポーズパーサー。

---

## 8. `cpp_engine/` パッケージ仕様 (C++ XPBD 物理演算エンジン)

- **`bin/mmd_xpbd.dll`**: 拡張位置ベース物理（XPBD）ソルバー。
- **`xpbd_visualizer.py`**: Maya ビューポート用コライダーメッシュ生成および再吸着機構。
- **`xpbd_maya_bridge.py`**: XPBD 物理シミュレーションベイク制御。

---

## 9. `asset/` モジュール仕様 (辞書・ユーティリティ)

- **`user_dict_manager.py`**: ユーザー辞書・マテリアル保護設定管理。
- **`user_dictionary.json`**: ユーザー設定永続化ファイル（保護キーワード、カスタム辞書 `custom_name_translations`）。
- **`bone_dict.py`**: 標準ボーン日英相互変換モジュール。
- **`jaka.py`**: 日本語/中国語ノード名のローマ字変換 & 健全化（ユーザー辞書動的リロード対応）。
- **`hik.py`**: HumanIK (HIK) ボーン定義マッピング（Tポーズ展開、膝の優先角度 `preferredAngle` & プレベンド設定、つま先ボーン ID 16/17 対応）。
- **`last_imported_structure.json`**: 前回インポート時の専用ボーン構造キャッシュ（プラグイン直下の `asset/` に統一保存）。
- **`khatangton1.txt`**: インポート UI 設定永続化ファイル（モデルパス・各種フラグ）。
- **`khatangton2.txt`**: エクスポート UI 設定永続化ファイル。

---

## 10. `toon/` ディレクトリ仕様

MMD 標準のトゥーン階調テクスチャ（`toon01.bmp` 〜 `toon10.bmp`）を格納。モデルインポート時に参照・適用されます。

---

## 11. `docs/` & `ai-task-docs/`

- **`docs/`**: 各サブシステムの公式設計仕様書群。
  - `codebase_architecture_specification.md` (全体構造仕様書 - 本ドキュメント)
  - `pmx_analyzer_specification.md` (PMXモデル詳細解析 & ユーザー辞書仕様書)
  - `bullet_engine_specification.md` (Bullet物理仕様書)
  - `model_import_specification.md` (モデルインポート・質感仕様書)
  - `physics_system_specification.md` (Maya物理システム仕様書)
  - `vmd_import_specification.md` (VMDインポート仕様書)
  - `xpbd_engine_specification.md` (XPBD物理仕様書)
- **`ai-task-docs/`**: AIペアプログラミングによる機能アップデートごとの計画・タスクリスト・確認書を格納（Git除外）。
