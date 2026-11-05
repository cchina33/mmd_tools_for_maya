# MMD Tools for Maya 技術解説ドキュメント: プラグイン構成 & MMDシェーディング再現アーキテクチャ

> [!NOTE]
> 本詳細技術仕様書は、AI によって作成・整理されたドキュメントです。内容はソースコードおよび開発記録をもとに記述していますが、実際の動作と細部が異なる場合があります。

本ドキュメントは、Maya用MMDモデル総合ツール「MMD Tools for Maya」の内部構造、各Pythonスクリプトの役割、およびMMD特有のシェーディング（Toonマップ・スフィアマップ）をMaya上で高精度に再現するための技術仕様をまとめたものです。

---

## 1. プラグインの構成と各Pythonファイルの解説

MMD Tools for Maya は、外部ライブラリ（numpyや外部バイナリパーサー）に依存せず、純粋なPython標準ライブラリ（`struct`モジュール）とMaya API 2.0（`maya.api.OpenMaya`）のみで構築された高移植性・高速動作のプラグインです。

### ファイル構成一覧

```text
mmd_tools_for_maya/
├── __init__.py                       # パッケージ初期化＆後方互換透過エクスポート
├── mmd_tools_for_maya_plugin.py      # Mayaプラグイン登録エントリポイント
├── README.md                         # プロジェクト概要・導入手順
├── LICENSE                           # MITライセンス条項
│
├── ui/                               # モダン統合UIパッケージ (PySide6 / PySide2 互換)
│   ├── __init__.py                   # UIエクスポート定義
│   ├── gui.py                        # メインウィンドウ統合エントリ (MMDToolsMainWindow, show_ui)
│   ├── gui_style.py                  # 共通ダークテーマスタイルシート (QSS)
│   ├── common.py                     # Qt互換インポート・共通ログ・ユーティリティ
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
├── converters/                       # モデル・モーション変換・インポートエンジン群
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
├── toon/                             # MMD標準共有トゥーンテクスチャ (toon01.bmp〜toon10.bmp)
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
│   ├── bin/                          # 各年度版コンパイル済みシェーダープラグイン (.mll)
│   ├── shaders/                      # DirectX 11 HLSL シェーダーコード
│   ├── src/                          # C++ ソースコード群
│   ├── scripts/                      # シェーダー自動セットアップスクリプト
│   └── CMakeLists.txt                # ビルド定義
│
├── mmd_toon_plugin/                  # Viewport 2.0 専用 OGSFX Toonシェーダー C++ プラグイン
│   ├── bin/                          # コンパイル済みシェーダープラグイン (.mll)
│   ├── shaders/                      # OGSFX トゥーンシェーダーコード
│   ├── src/                          # C++ ソースコード群
│   └── CMakeLists.txt                # ビルド定義
│
├── mmd_motion_plugin/                # 高速モーション処理 C++ プラグイン
│   ├── bin/                          # コンパイル済みモーションプラグイン (.mll)
│   ├── src/                          # 高速補間・キーフレーム処理ソース群
│   └── CMakeLists.txt                # ビルド定義
│
├── physics_bake_cs/                  # MMD物理演算リアルタイムベイクアプリ (C# / .NET 8 / WPF 3D)
│   ├── bin/Release/net8.0-windows/   # 実行可能バイナリ群
│   └── ...                           # ソースコード群
│
├── physics_bridge_cs/                # MMD物理演算シミュレーションビューア (C# / .NET 8 / WPF)
│   ├── bin/Release/net8.0-windows/   # 実行可能バイナリ群
│   └── ...                           # ソースコード群
│
├── pmx_analyzer/                     # PMXモデル詳細解析・一括保存 & ユーザー辞書対話登録パッケージ
│   ├── __init__.py                   # 解析パッケージエクスポート定義
│   ├── analyzer_core.py              # 構造解析・未登録漢字抽出
│   └── user_dict_dialog.py           # 未登録ボーン名対話型登録GUI
│
└── docs/                             # 独立技術仕様書群
```

---

### 各Pythonスクリプトの詳細解説

#### 1. `mmd_tools_for_maya_plugin.py` (プラグイン登録エントリポイント)

- **役割**: Mayaのプラグインマネージャからロードされる公式プラグインインターフェースです。
- **主要関数**:
  - `initializePlugin(mobject)`: プラグインロード時に呼ばれ、Mayaのトップメニューに「MMD Tools for Maya」メニューを登録します。
  - `uninitializePlugin(mobject)`: アンロード時に登録したメニューをクリーンアップします。
  - `show_mmd_window()`: GUIダイアログ（`gui.py`）を起動します。

#### 2. `ui/` パッケージ (モダン統合ユーザーインターフェース)

- **役割**: Maya 2025（PySide6 / Qt6）および過去バージョン（PySide2 / Qt5）の両方で動作するモダンなダークテーマUIを提供します。メインウィンドウ、10個の独立した機能別タブ、および各種専門操作ダイアログへ構造化分割され、保守性と拡張性が大幅に向上しました。
- **主な構成と各モジュールの役割**:
  - `ui/gui.py`: メインウィンドウ (`MMDToolsMainWindow` / `MmdMayaMainWindow`)、起動関数 (`show_ui`)、ホットリロード機構、タブ統合。
  - `ui/gui_style.py`: 全UIコンポーネントで統一されたダークテーマ QSS スタイルシート定義。
  - `ui/common.py`: Qt互換インポート、Mayaメインウィンドウ取得、および共通進捗ログダイアログ (`ExecutionLogDialog`)。
  - `ui/tab_*.py` (10個の独立タブ):
    - `tab_import.py`: モデルインポート（PMX/PMD/X、設定、解析連携）
    - `tab_easy_import.py`: 初心者向けワンクリック簡単インポート
    - `tab_vmd.py`: VMDモーション・カメラ・WAV音声インポート（スクロール対応）
    - `tab_material.py`: シェーダー設定・Toon切り替え・マテリアル保護
    - `tab_physics.py`: 物理演算設定・ベイク（Bullet / XPBD / 外部新3Dビューア連携）
    - `tab_export.py`: PMX / VMD / VPD エクスポート機能の一元集約
    - `tab_hik.py`: HumanIK (HIK) キャラクター定義・コントロールリグ展開
    - `tab_extra.py`: その他機能（地面影、照明操作、モデル種別判定、表情操作、VPDポーズ適用など）
    - `tab_plugin.py`: プラグインマネージャ（mll / C++ / C# バイナリ管理）
    - `tab_cleanup.py`: シーン内 MMD 要素の一括削除・初期化
  - **専門操作ダイアログ群**:
    - `ui/dialog_light_control.py`: MMD照明操作ダイアログ（地面影の向きXYZ・RGBカラーのリアルタイム調整）
    - `ui/dialog_model_classifier.py`: モデル種別判定・個別指定設定ダイアログ（キャラクター、ステージ、スカイドーム）
    - `ui/dialog_physics_model_select.py`: 物理演算対象モデル選択ダイアログ
    - `ui/morph_window.py`: 表情・モーフ操作GUI（4分割パネル、タイムスライダー追従、材質モーフ自動連動）
    - `ui/pmm_dialog.py`: PMMプロジェクト解析ダイアログ (`PmmAnalysisDialog`) およびチェックリスト形式のモデル選択インポート (`PmmModelImportSelectDialog`)
    - `ui/multi_model_dialog.py`: 複数モデル一括順次インポート (`MultiModelImportDialog`) およびベイク確認ダイアログ
    - `ui/accessory_dialog.py`: アクセサリ追従アタッチダイアログ
    - `ui/advanced_dict_dialog.py`: 高度なユーザー辞書・マテリアル保護設定GUI
    - `ui/user_dict_dialog.py`: 未登録ボーン名検出・対話型辞書登録ダイアログ
    - `ui/material_protect_dialog.py`: マテリアル保護キーワード管理GUI
    - `ui/bone_state_export_dialog.py`: ボーン状態・トランスフォーム情報エクスポートGUI
    - `ui/experimental_dialog.py`: 試験的機能ダイアログ

#### 3. `pmxpaimaya.py` (モデルインポートエンジン)

- **役割**: パースされたモデルデータから、Mayaのポリゴンメッシュ、マテリアル、スケルトン（ジョイント階層）、足IKハンドル（`ikHandle`）、スキニング（SkinCluster）、モーフ（BlendShape）、ライティングを自動構築するコアエンジンです。
- **主要処理**:
  - `create_mesh()`: `MFnMesh.create`（Maya API 2.0）を用いて数十万頂点のポリゴンメッシュを一括高速生成。
  - `setup_mmd_ik()`: 左右の足（足 → ひざ → 足首）およびつま先に Maya の IKハンドル（`ikRPsolver` / `ikSCsolver`）を自動構築し、足IKボーンに連動させる処理。
  - `create_mmd_lighting()`: MMD標準の平行光源および環境光を自動生成。
  - `import_pmx()`: 全体フローの統括、ボーン構造・モーフ構造メタデータの永続化保存（`mmdBoneStructure`）。

#### 4. `vmdpaimaya.py` (モーションインポートエンジン)

- **役割**: VMDバイナリデータを解析し、Mayaのタイムライン（30fps同期）およびターゲットモデルのボーン・モーフ・カメラに対してキーフレームを自動適用するアニメーションエンジンです。
- **主要処理**:
  - `resolve_model_structure()`: モデルノードのメタデータやキャッシュから日本語ボーン構造マップを復元。
  - `_resolve_full_joint_path()`: フルDAGパス解決による名前重複衝突の防止。
  - `apply_bone_motion()`: クォータニオンからオイラー角への変換、初期位置オフセット加算、足IK自動構築連動、全ボーンへのキーフレーム設定。
  - `apply_morph_motion()`: BlendShapeターゲット属性へのウェイトキーフレーム設定。
  - `apply_camera_motion()`: Mayaカメラへの移動・回転・画角（FOV）キーフレーム設定。
  - `delete_mmd_scene_elements()`: MMDモデル、ジョイント、IK、ライト、カメラ、および未使用マテリアルの全削除。

#### 5. `vmd_analyzer.py` (VMDモーション構造診断モジュール)

- **役割**: VMDバイナリを高速解析し、標準ボーン、準標準ボーン（グルーブ、腰、足D、足IK親など）、IKボーン（全角/半角）、表情モーフ、カメラのキーフレーム構成を診断してサマリーを出力するモジュールです。

#### 6. `mayapaipmx.py` (エクスポートエンジン)

- **役割**: Maya上で編集されたモデルメッシュ、ボーン、スキニングウェイト、マテリアル情報を収集し、MMD標準のPMX形式ファイルとして書き出すエンジンです。

#### 7. `mmd_core/` パッケージ (自作データパーサー群)

- **`pmm.py`**:
  - MikuMikuDance のプロジェクトファイル (`.pmm`) 解析エンジン。解像度・カメラ視野角などのメタデータ抽出、複数モデル境界追従リシンク機構、実体ファイル照合、タイムライン走査によるモーション/ポーズ判定、および旧データ自動判定を提供。
- **`pmx.py`**:
  - PMX 2.0 / 2.1 仕様に基づくバイナリ解析器。頂点（BDEF1/BDEF2/BDEF4/SDEF/QDEF）、面、テクスチャパス（UTF-8/UTF-16）、マテリアル、ボーン、モーフ（頂点/UV/ボーン/材質）、剛体、ジョイントの読み書きをサポート。
- **`pmd.py`**:
  - MMD旧形式（PMD）のバイナリパーサー。Shift_JISデコード（多重文字コードフォールバック）に対応し、ボーン直後のIKセクション（ターゲット、チェーン、可動域制限）を解析。さらにPMD拡張セクションに記録された英語情報、Toonリスト、剛体（RigidBody）、ジョイント（Joint）のバイナリ抽出に対応。`converters/pmd2pmx.py` と連携し、同一フォルダへの最新 PMX 2.0 形式への自動変換・保存を提供。マテリアル解析時にToonインデックスおよびスフィアモード（乗算/加算）を保持。
- **`x_file.py`**:
  - DirectX 3Dメッシュ形式（`.x`）のトークンストリーム字句解析器。テンプレートブロック（`template Mesh { ... }`）の自動スキップ、入れ子構造の中括弧解析、頂点座標・面インデックス・法線・UV・マテリアル・テクスチャファイル名の抽出を実装。
- **`vmd.py` / `vpd.py`**:
  - カメラ・ボーン・モーフのアニメーションキーフレーム（VMD）およびポーズ設定（VPD）のデータ解析器。

#### 8. `asset/` モジュール (補助ライブラリ)

- **`jaka.py`**:
  - MMDモデル特有の日本語（漢字・ひらがな・カタカナ）や中国語（簡体字・繁体字）のボーン名・マテリアル名を、Maya内部で安全に扱える英数字（ヘボン式ローマ字 / ピンイン）に変換し、不正文字によるノード作成失敗を防止。
- **`hik.py`**:
  - MMDのボーン階層（センター、下半身、上半身、首、頭、肩、腕、手、足、つま先等）をMayaのHumanIK標準スケルトン定義に対応付けるマッピングテーブル。

---

## 2. MMDシェーディングの理論とDirectX仕様

### MMDのToonシェーディングとは

MMD（MikuMikuDance）のセル調アニメ陰影（Toon）は、通常のテクスチャマッピングとは根本的に異なる仕組みで動作しています。

```text
【一般的なカラーテクスチャ】
メッシュのUV展開座標 (U, V) ──> テクスチャ画像 ──> サーフェス表面の色

【MMDのToonテクスチャ】
ライト方向ベクトル L と 法線 N の内積 (N・L: 光の当たり具合) ──> Toon画像のV座標 ──> 影の色
```

### 「V Coord（V座標）」に接続する

1. **UV座標軸の定義**:
   - 3Dグラフィックスにおけるテクスチャ座標（UV）では、**U軸が横方向（水平）**、**V軸が縦方向（垂直）** を表します。
2. **Toonテクスチャ画像（toon01.bmp〜toon10.bmp）の構造**:
   - Toon画像を開くと、画像の上から下に向かって明暗のグラデーションが描かれています。
   - **上部（V = 1.0）**: 明部色（白など。光が十分に当たっている面）
   - **下部（V = 0.0）**: 暗部色（グレーや茶色など。光が当たっていない影の面）
   - **横方向（U軸）**: 横方向には色の変化が一切ありません（単色・均一）。
3. **DirectXシェーダーでの計算ロジック**:
   MMD標準のシェーダープログラム（HLSL）では、以下のように記述されています：
   ```hlsl
   // 法線とライト方向の内積から受光量（0.0〜1.0）を計算
   float lightIntensity = saturate(dot(Normal, LightDir));
   // Uは中央固定(0.5)、Vに受光量を指定してサンプリング
   float2 toonUV = float2(0.5, lightIntensity);
   float4 toonColor = tex2D(ToonSampler, toonUV);
   ```
   このように、**「光の当たり具合を縦軸（V）のスライド値として使う」** ため、Mayaでも受光輝度を `vCoord` に接続する必要があります。

---

## 3. Mayaにおけるシェーダー再現アーキテクチャ

MMD Tools for Maya では、Mayaのリアルタイムビューポート（Viewport 2.0）で確実に動作する標準ユーティリティノードを組み合わせて、このシェーディングネットワークを再現しています。

### ノード接続構成図

```text
[シーンカメラ / サーフェス]
        │
        ▼
   samplerInfo ──(normalCamera)──> [ input1 ]
                                              vectorProduct ──(outputX: -1.0〜1.0)──> [ valueX ]
   [ライト到来方向ベクトル]  ───(input2)──> (Dot Product: 内積)                            setRange ──(outValueX: 0.0〜1.0)──> [ vCoord ]
                                                                                   (0.0〜1.0に正規化)                         Toon file ノード
                                                                                                                           (uCoord = 0.5 固定)
                                                                                                                                   │
                                                                                                                              (outColor)
                                                                                                                                   ▼
[メインテクスチャ] ──> [ input1 ]                                                                                           [ input2 ]
                      multiplyDivide (スフィア乗算) ──(output)──> [ input1 ]                                                        │
[スフィアテクスチャ] ─> [ input2 ]                                        multiplyDivide (Toon乗算) <──────────────────────────────┘
                                                                                 │
                                                                             (output)
                                                                                 │
                                                                                 ▼
                                                                StandardSurface.baseColor / Blinn.color
```

### 各ノードの役割

1. **`samplerInfo` (サーフェス情報ノード)**:
   - カメラ空間における面の向き（法線ベクトル: `normalCamera`）をリアルタイムに出力します。
2. **`vectorProduct` (ベクトル演算ノード)**:
   - 演算モードを `Dot Product (内積)`、`normalizeOutput = True` に設定。
   - `input1`（面の法線）と `input2`（ライトの到来方向 `[0.35, 0.75, 0.55]`）の内積を計算します。
   - 面が光を向いているときは正（最大 `1.0`）、背を向けているときは負（最小 `-1.0`）を出力します。
3. **`setRange` (数値範囲変換ノード)**:
   - 内積の出力範囲（`-0.2 〜 0.8`）を、Toon画像のV座標（`0.0 〜 1.0`）へとマッピングします。
   - これにより、MMD特有の「一定以上の角度になると急激に影が落ちる」アニメ調のセル境界が形成されます。
4. **Toon `file` ノード**:
   - メッシュのポリゴンUV（`place2dTexture`）から切り離し、`uCoord` を `0.5` 固定、`vCoord` に `setRange.outValueX` を接続します。
   - これにより、**ポリゴンのUV展開形状に起因する汚れや帯の焼き付きが防止**されます。
5. **`multiplyDivide` (カラー乗算ノード)**:
   - メインカラー（基本テクスチャ × スフィアマップ）に Toon ファイルノードの `outColor` を乗算（Multiply）します。
   - 光が当たっている面は Toon の白（1.0, 1.0, 1.0）が掛かるため本来のテクスチャが美しく発色し、影の面には Toon の暗部色が乗算されてセル影が落ちます。

---

## 4. スフィアマップ（MatCap）の再現技術

MMDモデルのマテリアルには、金属光沢やハイライトを表現する「スフィアマップ（`.sph` / `.spa`）」が含まれます。

- **乗算スフィア (`.sph` / モード 1)**:
  - 基本テクスチャの色と乗算され、陰影や質感を加えます。
- **加算スフィア (`.spa` / モード 2)**:
  - 基本テクスチャに加算され、強いハイライトや発光感を加えます（Mayaでは `incandescence` または StandardSurface の `emissionColor` に接続）。

### MatCap UV 変換ネットワーク

スフィアマップは、カメラから見た法線方向（-1.0 〜 1.0）をUV座標（0.0 〜 1.0）に変換してテクスチャを参照します：

```python
# カメラ空間法線 (-1.0 〜 1.0) を UV (0.0 〜 1.0) に変換
mc.connectAttr(f"{sampler_node}.normalCameraX", f"{matcap_range_node}.valueX")
mc.connectAttr(f"{sampler_node}.normalCameraY", f"{matcap_range_node}.valueY")
mc.connectAttr(f"{matcap_range_node}.outValueX", f"{sphere_file_node}.uCoord")
mc.connectAttr(f"{matcap_range_node}.outValueY", f"{sphere_file_node}.vCoord")
```

これにより、カメラのアングルを回転させても常に法線に応じた滑らかな光沢が追従します。

---

## 5. 発色最適化とライティング環境

### ビュー変換「Un-tone-mapped (sRGB)」の重要性

Maya 2022以降のカラーマネジメント（ACEScg / OCIO）では、デフォルトのビュー変換がシネマティック用トーンマッパー（ACES 1.0 SDR-video や AgX）に設定されていることが多く、MMDモデルの明るく鮮やかなセルアニメ調テクスチャが沈み、黒ずんで表示される問題が発生します。

MMD Tools for Maya では、インポート時に以下のAPIを実行し、トーンカーブによる減衰を行わない表示に自動設定します：

```python
mc.colorManagementPrefs(edit=True, viewTransformName='Un-tone-mapped (sRGB)')
```

これにより、MMDの元テクスチャが持っている鮮やかな発色がそのままビューポートに再現されます。

### MMD標準ライティング・影システム

MMD特有の陰影と接地感をMaya上で再現するため、専用のライティング・セルフシャドウ機構を構築します。

#### MMD標準ライト（Directional & Ambient）
- **平行光源 (`directionalLight`)**:
  - メインの太陽光・キーライト（光の色: RGB 各154、強度 `1.0`）。
  - デフォルトの向きは MMD 本家の標準値（XYZ: `0.50, -1.00, -0.50`）に初期化され、右手奥から手前左下へ向かう自然な影を形成します。
- **環境光 (`ambientLight`)**:
  - 強度 `0.55`、アンビエントシェード `0.25`（暗部が黒潰れせず、Toon陰影が鮮明に見えるよう光を補正）。

#### 本家MMDセルフシャドウ方式による地面影落ちアーキテクチャ
MMD本家のセルフシャドウ・地面影描画を再現するため、専用のシャドウキャッチャー構造と属性制御を採用しています。

- **地面影受けプレーン (`mmd_ground_shadow_plane`)**:
  - `create_mmd_ground_shadow()` により、グループノード `mmd_ground_shadow_grp` 配下に自動生成。
  - Z-fighting（床面との重なりによるチラつき）を抑止するため、垂直位置は微小オフセット $Y = 0.05$ に配置。
- **シャドウキャッチャーシェーダー (`mmd_ground_shadow_shd`)**:
  - 黒ベース（RGB: 0, 0, 0）のマテリアルに、影の受光量に応じた透明度（Transparency）制御を適用。
  - プレーン自体の面色は見えず、落ちてくる影のみを自然な濃度（標準0.5）で描画。
- **影の送受信属性制御**:
  - キャラクターメッシュおよびステージメッシュ: `receiveShadows = True`（自身の影や他オブジェクトからの影を綺麗に受ける）。
  - 地面影プレーン自身: `castsShadows = False`（影プレーン自身が影を落とすことによる無駄な自己遮蔽やデプスマップ解像度低下を防止）。
- **ステージモデル検出による自動切り替え機構 (`setup_mmd_ground_shadow_mode`)**:
  - シーン内にステージモデル（またはスカイドーム）がインポートされた場合、地面影プレーンは自動的に非表示（`visibility = 0`）に切り替わります。これにより、キャラクターの影はステージモデルの床面メッシュ自体へ直接落ちるようになります。
  - キャラクターのみのシーンでは、地面影プレーンが自動で表示（`visibility = 1`）され、Y=0の床面に自然な接地影が形成されます。

#### MMD照明操作GUI (`dialog_light_control.py`)
MMD本家の「照明操作」パネルの操作感を再現した専用ダイアログです：
- **カラー調整**: 赤・緑・青（各0〜255）のスライダーにより、平行光源の光色をリアルタイムに変更。
- **影の向き調整**:
  - X, Y, Z スライダーにより、影が伸びる方向（光の到来角度）を自由に調整。
  - 初期化ボタンを押すことで、MMD本家推奨の基本値（X: 0.50, Y: -1.00, Z: -0.50）へ即座に復帰。
- **登録ボタン**: 現在の照明角度と色をシーン内へ確定登録。

#### モデル種別判定マネージャ (`asset/model_classifier_manager.py`)
シーン内の各PMXモデルが「キャラクター」「ステージ」「スカイドーム」のいずれであるかを自動判定・管理します：
- ボーン構造、剛体数、バウンディングボックスの大きさ、および特定キーワードから種別を自動推定。
- 「その他機能」タブの「モデル種別判定・個別指定設定」ダイアログ（`dialog_model_classifier.py`）から、ユーザーが手動でモデル種別を個別設定・変更可能。
- 設定内容はモデルノードのメタデータ（`mmdModelType`）および設定ファイルに永続化され、地面影プレーンの表示切り替えやライティング適正化に活用されます。

---

## 6. MMDモーション（VMD）インポート & アニメーション適用アーキテクチャ

MMD Tools for Maya は、MMDモーションデータ（`.vmd`）をMayaシーン上のMMDモデルへ高精度にインポートし、タイムライン同期、クォータニオン回転、ブレンドシェイプモーフ、および足IK（逆運動学）を連動させる専用エンジン（`vmdpaimaya.py`）を搭載しています。

### VMDバイナリフォーマットの解析仕様 (`mmd_core/vmd.py`)

VMDファイルは針金P様およびFantom様の解析仕様を参考にしています。

- **ヘッダーブロック (50バイト)**:
  - 識別シグネチャ: `Vocaloid Motion Data 0002`（30バイト、固定ASCII）
  - モデル名: モーション製作者が使用したモデル名（20バイト、Shift_JIS）
- **ボーンフレームレコード (各111バイト)**:
  - ボーン名（15バイト、Shift_JIS、NULL終端）
  - フレーム番号（4バイト unsigned int）
  - 移動量（`float x, y, z`、各4バイト）
  - 回転クォータニオン（`float x, y, z, w`、各4バイト）
  - 補間曲線パラメータ（64バイト: X軸, Y軸, Z軸, 回転の4要素に関するベジェ曲線制御点）
- **モーフ（表情）フレームレコード (各23バイト)**:
  - モーフ名（15バイト、Shift_JIS）
  - フレーム番号（4バイト unsigned int）
  - ウェイト値（4バイト float: `0.0 〜 1.0`）
- **カメラフレームレコード (各61バイト)**:
  - フレーム番号（4バイト unsigned int）
  - 距離（4バイト float）
  - 目標位置（`float x, y, z`）
  - 回転オイラー角（`float rx, ry, rz`、ラジアン）
  - 補間曲線パラメータ（24バイト）
  - 視野角 FOV（4バイト unsigned int、度数法）
  - パースペクティブフラグ（1バイト: 0=オン, 1=オフ）
- **照明およびモデル表示/IK切り替えレコード**:
  - 照明の向き・色（28バイト）およびIK有効無効スイッチの解析。

---

### MMD左手系からMaya右手系への座標・回転変換

MMDはDirectX準拠の**左手座標系**（Z軸奥向き）、MayaはOpenGL準拠の**右手座標系**（Z軸手前向き）を採用しています。この差異を整合させるため、以下の幾何学的変換を施します。

#### 位置（Translate）の変換

MMDの移動量ベクトル $(p_x, p_y, p_z)$ に対して、Mayaの座標空間ではZ軸を反転し、モデルのインポートスケール倍率（標準: 8.0）を乗算します。また、Mayaジョイントの初期位置 $(t_{0x}, t_{0y}, t_{0z})$ に対する相対移動として加算します：

- $T_x = t_{0x} + p_x \times \text{scale}$
- $T_y = t_{0y} + p_y \times \text{scale}$
- $T_z = t_{0z} - p_z \times \text{scale}$

#### クォータニオン回転（Rotate）の変換

MMDの回転クォータニオン $(q_x, q_y, q_z, q_w)$ は左手系基準です。右手系への反転のため、$X$ および $Y$ 成分の符号を反転させたクォータニオン $Q_{\text{maya}}$ を構築し、オイラー角へと展開します：

- $Q_{\text{maya}} = (-q_x, -q_y, q_z, q_w)$
- $E = Q_{\text{maya}}.\text{asEulerRotation}()$
- $R_x = \text{degrees}(E_x), \quad R_y = \text{degrees}(E_y), \quad R_z = \text{degrees}(E_z)$

---

### ボーン構造メタデータによる強制適用アーキテクチャ

MMD Tools for Maya では以下のアーキテクチャにより、**モデル名に依存せず、現在シーン内にあるモデルへ適用**します：

- **モデルインポート時のメタデータ埋め込み (`pmxpaimaya.py`)**:
  - モデルインポート時に、日本語ボーン名と対応するMayaノードのフルDAGパスの辞書テーブルを作成。
  - モデルのルートメッシュノードに `mmdBoneStructure`（JSON文字列属性）として埋め込み、さらに `asset/last_imported_structure.json` にキャッシュ保存。
  - 対応関係の例:
    - `"右腕"` → `"|ModelRoot|...|shoulderP_R|migi_kata|migi_ude"`
    - `"左足ＩＫ"` → `"|ModelRoot|...|leg_IKP_L|hidari_ashi_ik"`
    - `"下半身"` → `"|ModelRoot|...|waist|kahanshin"`
- **名前の自動逆引き解決 (`vmdpaimaya.py`)**:
  - Maya内部でノード名がローマ字化（`migi_ude`）されていても、日本語名（「右腕」）をキーとして一意のノードパスを直接取得。
  - モデル選択コンボボックスで指定されたターゲットモデル、またはシーン内で検出されたMMDモデルに対してキーフレームを適用。

---

### 同名ノード名前衝突回避と堅牢な例外保護

シーン内に過去のモデルや同名のノードが存在する場合、ショートネーム（`migi_ude` など）でキーフレームを指定すると Maya API が `More than one object matches name` エラーを発生させます。また、従来の処理では1つのボーンでエラーが起きるとループ全体が強制中断される問題がありました。

MMD Tools for Maya では以下の2重保護を実装しています：

- **フルDAGパス（ロングネーム）特定**:
  - `_resolve_full_joint_path()` により、指定されたモデルの階層ツリー下にあるノードをパイプ区切りフルパス（`|Root|Parent|Child`）で特定し、シーン内の別モデルと同名であっても競合しない安全性を確立。
- **ボーン・キー単位の個別例外保護**:
  - キーフレーム設定ループを個別 `try-except` で保護。万が一未知の特殊ボーンで例外が発生しても、体・腕・足・頭・指などの全ボーン処理が途中で停止せず、最後まで確実にキーフレームを完遂します。

---

### 足IK（インバースキネマティクス）自動構築と下半身アニメーション連動

#### MMDの足モーション構造

MMDのダンスや歩行アニメーションでは、太ももやひざのFKボーン（「左足」「左ひざ」）には回転キーが打たれず、**「左足ＩＫ」「右足ＩＫ」「つま先ＩＫ」の移動・回転**にキーが打たれます。MMDエンジンはこのIKターゲットの位置に合わせてひざの角度をリアルタイムに逆運動学計算します。

従来のMaya環境ではIKソルバーが存在しなかったため、「足ＩＫ」ジョイントが動いても足のメッシュが直立不動のまま固まる現象が発生していました。

#### Maya IKハンドルの自動構築 (`setup_mmd_ik`)

MMD Tools for Maya は、モデルインポート時およびモーション適用時に、以下のIKシステムを自動で構築します：

- **脚部IK (足 → ひざ → 足首)**:
  - `startJoint` を「足」、`endEffector` を「足首」として、回転面ソルバー（`ikRPsolver`）による `ikHandle` を生成。
  - 生成した `ikHandle` を「足ＩＫ」ジョイントに追従（`pointConstraint`）。
  - 足首の向きを「足ＩＫ」ジョイントの回転に連動（`orientConstraint`）。
- **つま先IK (足首 → つま先)**:
  - `startJoint` を「足首」、`endEffector` を「つま先」として、単一チェーンソルバー（`ikSCsolver`）による `ikHandle` を生成。
  - 生成した `ikHandle` を「つま先ＩＫ」ジョイントに追従（`pointConstraint`）。
- **非表示管理**:
  - IKハンドルはジョイントの運動を制御する補助ノードであるため、自動的に非表示（`visibility=False`）に設定され、ビューポートの視覚的ノイズを排除。
- **既存モデルへの即時適応**:
  - VMDインポートの実行時に、対象モデルにIKハンドルが存在しない場合はその場で自動構築を実行。モデルを再インポートすることなく、即座に自然なひざの屈伸・ステップ運動が再現されます。

---

### MMDカメラ再現アーキテクチャ (2階層オービットリグ)

MMDのカメラは、固定位置に配置された通常のカメラとは異なり、**「注視点（Target: XYZ）」を中心として「公転回転（RX, RY, RZ）」し、そこから「距離（Distance: 通常負値）」離れた位置から被写体を捉える**というオービット構造を採用しています。

MMD Tools for Maya では、この構造をMaya上で再現するため、以下の2階層カメラリグを自動生成します：

```text
MMD_Camera_Aim (注視点ロケータ: Transform)
  │  ・移動 (Translate XYZ): MMD注視点座標 (x * scale, y * scale, -z * scale)
  │  ・回転 (Rotate XYZ): MMDカメラ回転角 (RX, -RY, -RZ: 度数法)
  │
  └── MMD_Camera (カメラ本体: Camera Transform / CameraShape)
        ・移動 (Translate Z): 注視点からの距離オフセット (-Distance * scale)
        ・移動 (Translate XY): 0.0 固定
        ・回転 (Rotate XYZ): 0.0 固定
        ・焦点距離 (focalLength): MMDの視野角 (FOV) からミリ単位で正確に換算
```

#### 視野角（FOV）から焦点距離（focalLength）への換算理論

MMDのカメラキーフレームには視野角 $\text{FOV}$（度数法）が記録されています。Mayaのカメラシェイプではミリ単位の焦点距離 `focalLength` で制御されるため、以下の光学計算式を用いて毎フレームの焦点距離をキーフレーム設定します：

- $\text{fovRad} = \text{radians}(\text{FOV})$
- $\text{focalLength} = \frac{\text{verticalFilmAperture} \times 25.4}{2.0 \times \tan\left(\frac{\text{fovRad}}{2.0}\right)}$
- これにより、注視点を中心としたカメラワークの回転・ドリーイン/アウト・ズームが同期します。

---

### アニメーション削除（初期ポーズ復元）機能

MMD Tools for Maya では、インポートしたアニメーションを破棄して初期ポーズ（Aポーズ／Tポーズ）へ即座に戻す `clear_model_animation()` を実装しています：

- **ボーンキーフレームの全消去**:
  - 対象モデルの全ジョイントに対して `mc.cutKey()` を実行し、キーフレームアニメーションを消去。
  - ジョイントの回転（Rotate）を `[0.0, 0.0, 0.0]` にリセット。
- **モーフ（ブレンドシェイプ）のリセット**:
  - BlendShapeノードの全ターゲット属性からキーフレームを消去し、ウェイト値を `0.0`（無表情・初期顔）に初期化。
- **カメラリグの安全なクリーンアップ**:
  - 生成された MMDカメラリグ（`MMD_Camera_Aim` / `MMD_Camera`）をシーンから自動削除。
- **再生タイムラインの初期化**:
  - カレントタイムをフレーム `0` に戻し、即座にモデルの静止初期状態を確認可能。

---

### GUIにおけるモデル用／カメラ用ファイルの2系統独立入力

MMDの文化・配布形態として、キャラクターのダンスモーション（`.vmd`）とカメラワークモーション（`.vmd`）は別々のファイルとして配布されることが一般的です。

MMD Tools for Maya のモーションタブ（`VmdImportTabWidget`）では、この運用に対応しています：

- **キャラクタモーション (`.vmd`)**: ボーン・表情用のモーションファイルを指定。
- **カメラモーション (`.vmd`)**: カメラワーク専用のファイルを指定（省略可能）。
- **インテリジェント・ドラッグ＆ドロップ**:
  - 複数ファイルを同時にドラッグ＆ドロップした際、ファイル名（`cam`, `camera`, `カメラ` 等）を自動解析してカメラ欄とモデル欄へ自動振り分け。
- **単体カメラVMDの直接適用**:
  - モデルモーションを指定せず、カメラモーション単体のみを指定してインポートすることも可能。

---

## 7. VMDアナライザー（構造診断）、ボーンエイリアス/フォールバック、およびMMD全削除

### VMD構造解析モジュール (`vmd_analyzer.py`)

MMDモーションは制作環境や制作者によって使用されるボーン体系が大きく異なります。MMD Tools for Maya は、任意のVMDファイルを瞬時に診断・可視化するアナライザーを搭載しています：

- **ボーン種別の自動診断**:
  - **標準ボーン**: 全ての親、センター、下半身、上半身、腕、足、足IKなど
  - **準標準ボーン**: グルーブ、腰、上半身2、足D系（FK補助ボーン）、足IK親、腕捩りなど
  - **IKボーン**: 全角（`左足ＩＫ`）／半角（`左足IK`）の検出
  - **特殊ボーン**: モデル固有の拡張ボーンのリストアップ
- **表情（モーフ）・カメラ構成の把握**:
  - 表情キーフレーム総数と使用モーフ名一覧
  - カメラワークおよび照明アニメーションの有無
- **診断レポートの出力**:
  - GUIからのインポート実行時に診断サマリーを自動出力し、コンソールまたは単体スクリプト実行時にも詳細なレポートを生成。

---

### 表記揺れ正規化 & ボーンエイリアス／フォールバック理論

MMDモデルとモーションの間で生じる「足や腰が動かない」現象を解決するため、`vmdpaimaya.py` に以下の多重マッチングアルゴリズムを実装しています：

#### 全角・半角英数（NFKC）の自動正規化

VMDモーション内で全角（`左足ＩＫ`）と半角（`左足IK`）が混在していても、`unicodedata.normalize('NFKC')` を通して統一し、空白文字（スペース）を除去して照合します。

#### ボーンエイリアス（同義語）辞書

MMD特有の表記揺れ（`左足IK` ↔ `左足ＩＫ` ↔ `左足IK親`、`全ての親` ↔ `すべての親` ↔ `操作中心` 等）をテーブル化し、双方向から検索・解決します。

#### 準標準ボーンのフォールバック合成

- **グルーブ → センター**: モーションに「グルーブ」があるのにモデルに存在しない場合、自動的に「センター」ジョイントへ移動・回転を合成。
- **腰 → 下半身**: モーションに「腰」があるのにモデルに存在しない場合、自動的に「下半身」ジョイントへ回転を適用。
- **足IK親 → 足IK**: モーションに「足IK親」があるのにモデルに存在しない場合、足IKジョイントへ位置オフセットを合算。
- **足D → 足FK**: 準標準FKボーン（足D）のキーを通常FKボーンへ転送。

---

### MMDクリーンアップ機能 (CleanupTabWidget)

制作やアニメーション検証を繰り返す際、シーン内に残った古いノードやマテリアルが蓄積してシーンが重くなるのを防ぐため、専用タブ **「MMD削除 (クリーンアップ)」**（`CleanupTabWidget`）を提供しています。
UIは「**削除対象モデルの選択**」と「**全削除ボタン**」のみで構成されたシンプルな設計となっており、迷わずワンクリックでクリーンアップを実行できます：

```python
def delete_mmd_scene_elements(
    target_model_node=None,
    delete_lights=True,
    delete_cameras=True,
    delete_audio=True,
    delete_unused_nodes=True
):
    ...
```

- **直感的な2要素GUI構成**:
  - 削除対象モデルのコンボボックス（シーン内の全MMDモデルまたは個別モデルを選択可能）
  - 更新ボタン（シーン内のMMDモデルを即時再スキャン）
  - 全削除ボタン（誤操作を防ぐ確認ダイアログ付き）
- **モデル & スケルトン階層の一括削除**:
  - 対象モデル（個別またはシーン全体）のメッシュノードおよび階層下の全ジョイント、IKハンドル、コンストレイント、BlendShapeノードを特定して安全に削除。
- **地面影グループのクリーンアップ**:
  - MMD標準地面影グループ **`mmd_ground_shadow_grp`** および配下のシャドウキャッチャー平面メッシュを一括検出して削除。シーン内に孤立した影プレーンが残留するのを防ぎます。
- **物理演算ノードの一括クリーンアップ**:
  - 剛体・Joint可視化ノード（`MMD_RigidBody_Joint_Visualizers`）やBullet物理リグ（`MMD_Bullet_Physics_Rig`）を一括検出して削除。
- **MMDカメラ・オーディオ・ライトの一括消去**:
  - `MMD_Camera_Aim` / `MMD_Camera`、BGM音声ノード、および照明グループ **`mmd_lighting_grp`** を消去。
- **Maya標準「未使用ノードの削除」の自動実行**:
  - `mel.eval('MLdeleteUnused;')`（Mayaの Delete Unused Nodes）を内部実行。
  - 不要になったシェーダー（Blinn、StandardSurface）、Toonユーティリティノード（`multiplyDivide`, `samplerInfo`, `setRange`）、およびテクスチャ `file` ノードを一括クリーンアップし、シーンを常に軽量・清潔に保ちます。

---

### モーションファイルパスの永続化と引き継ぎ (`mc.optionVar`)

作業効率向上のため、キャラクタモーションおよびカメラモーションの前回選択パスは Maya の `optionVar` を利用してセッション間でも自動記憶・復元されます：

- **対象設定**:
  - `MMD Tools for Maya_LastModelVmdPath`: 前回指定されたキャラクタモーション（.vmd）のフルパス
  - `MMD Tools for Maya_LastCameraVmdPath`: 前回指定されたカメラモーション（.vmd）のフルパス
  - `MMD Tools for Maya_DeleteLightsOnClear`: 全削除時にライトを削除するかどうかのチェック状態 (0 / 1)
- **連携動作**:
  - ウィンドウ起動時に前回パスが存在する場合、入力欄に自動復元。
  - 「参照...」ボタン押下時、前回使用したファイルの親ディレクトリを初期フォルダとしてスムーズに展開。
  - 複数ファイルの一括ドラッグ＆ドロップ時にも自動で対応する `optionVar` を更新。

---

### GUIアーキテクチャ & レイアウト設計

- **ウィンドウサイズ**:
  - デフォルトサイズ: **980 × 820 px** (最小サイズ: 480 × 360 px)
  - 高解像度ディスプレイでもゆったりと文字が読めるよう、フォントサイズを最適化。
- **タブ構成**:
  - `プラグイン管理`: C++高速化、物理演算、シェーダープラグインのロード状態確認・自動ロード設定
  - `MMD → Maya (インポート)`: PMX / PMD / DirectX (.x) モデル読み込み
  - `モーション (VMD)`: キャラクタ＆カメラモーションの個別・一括インポート
  - `物理演算ベイク`: 物理シミュレーションおよびベイク
  - `物理演算ベイクGUI`: WPF3Dリアルタイム物理ビューア連携ベイク
  - `その他機能`: 共通設定、マテリアル保護、辞書設定、試験的機能
  - `MMD削除 (クリーンアップ)`: 対象モデル選択、各削除オプション、全削除
- **縦長レイアウトの解消と操作性向上**:
  - 設定項目が多いタブに `QScrollArea` を導入。
  - ウィンドウが縦に伸びすぎて操作しづらくなる現象を解消し、コンパクトな画面領域内でも全設定項目へ快適にアクセス可能。

---

## 8. ポーズ・モーション入出力と補助機能 (試験的機能)

### VPDポーズデータ入出力エンジン (`mmd_core/vpd.py`)

- **VPDポーズ保存**:
  - Mayaシーン上のMMDモデルの全ジョイントからトランスフォーム情報を抽出し、左手系への変換を行って `.vpd` ファイルとして保存。
- **VPDポーズ適用**:
  - 外部のVPDファイルを読み込み、現在モデルの各ボーンへ回転・移動ポーズを即座に適用。
  - ポーズ適用時にカレントフレームへキーフレームを自動設定するオプションを備え、ポーズ集からのカット作成を支援。

### VMDモーションエクスポートエンジン

- **Mayaアニメーションカーブの逆変換**:
  - Mayaシーン上のジョイント回転・移動キーフレームからアニメーションカーブ（Animation Curve）を評価。
  - 右手系から左手系への反転、およびベジェ補間曲線の制御点（P1, P2）の逆算を実行。
- **軽量化フィルター**:
  - 同一値の連続キーや微小変化キーを自動間引きし、MMD本家や他ツールで扱いやすい最適化されたVMDバイナリを出力。

### 表情モーフ操作ウィンドウ (`ui/morph_window.py`)

- **動的バインド機構**:
  - 複数モデルが存在するシーンでも、アクティブなモデルへ即座に操作対象を再バインド。
- **タイムスライダー自動追従**:
  - タイムスライダーの現在フレーム移動に合わせて、モデルのモーフウェイト値をリアルタイムにUIスライダーへ同期表示。
- **自作表情プリセット機能（試験的機能）**:
  - 目・眉・口・その他のスライダー値を組み合わせた独自の表情をプリセットとして保存・一覧からワンクリック適用。
- **アクセサリ追従アタッチ機能（試験的機能）**:
  - メガネ、帽子、武器等の小道具メッシュを、頭や手などの指定ボーンへ自動追従させるコンストレイント構築機構。

---

## 9. 剛体貫通防止強化アーキテクチャ

物理シミュレーションベイク時における剛体の突き抜け・貫通（スカートと足など）を強力に防止するため、以下の物理アーキテクチャを導入しています：

- **全剛体における連続衝突検出 (CCD: Continuous Collision Detection) の有効化**:
  - 高速で移動する足剛体や薄いスカート剛体に対して、移動軌跡のカプセルスイープ判定を適用し、フレーム間のトンネリング現象を抑制。
- **Kinematic剛体の線速度（Linear Velocity）算出と反発インパルス伝達**:
  - モーション駆動のKinematic剛体のフレーム間移動量から正確な線速度ベクトル（$\vec{v} = \frac{\Delta \vec{x}}{\Delta t}$）を算出して剛体へ付与。
  - 衝突時にDynamic剛体（スカート等）へ力強い押し出し反発インパルスを伝達し、食い込みを瞬時に押し戻す挙動を実現。
- **物理ソルバーの計算精度向上**:
  - ソルバー反復回数（Solver Iteration Count）をMMD本家推奨の25回に設定。
  - 拘束の食い込み位置補正にペナルティ法ではなく独立した位置補正（Split Impulse）を採用し、反発による吹き飛びを抑えつつ貫通を解消。
- **高密度サブステップ設定**:
  - ベイクUIに精度設定オプション（標準 120Hz、高精度 240Hz）を提供し、激しいダンスモーションでも剛体が突き抜けない安定したシミュレーションベイクを実現。

---

## 10. PMD剛体適正化および透過素材モーフ制御

### PMDからPMXへの剛体ワールド座標自動展開

- **ボーン相対位置からワールド座標への変換**:
  - PMD形式の剛体データは関連ボーン原点からの相対位置（ローカル座標）として記録されているため、PMX形式へ変換する際に関連ボーンのワールド位置を加算してワールド座標系を構築。
  - これにより、頭髪やスカート、腕部などの剛体が足元（原点）に密集する不整合を解決。
- **PMD材質アルファ異常値の自動補正**:
  - 一部PMDモデルに見られるアルファ値1.0超過（99.0等）のデータを0.0〜1.0へ自動正規化。

### 透過素材モーフ（PMX・PMD共通）の表示制御

- **基本カラーの維持**:
  - 初期アルファが0.05以下の材質に対しても、ディフューズ色（`diffuse_color`）を黒色で上書きせず材質本来の色を保持。
- **各種シェーダー（mmdMaterial等）へのアトリビュート接続網羅**:
  - `mmdMaterial`、`standardSurface`、`blinn` 等のシェーダーに対し、透過度・受光強度・基本カラー変化の連動接続を網羅。
  - `mmdMaterial` の `transparency` / `diffuseAlpha` / `diffuse` 属性にモーフ値が正常連動し、頬染めやガーンなどのモーフが正常に描画されるよう改善。
- **頂点モーフ型透過板ポリゴンの可視化保証**:
  - PMDモデルや一部PMXモデルにおいて頭部内部から板ポリゴンを手前展開させる頂点モーフに対し、材質モーフが存在しない場合は透明固定を回避して手前展開時の可視化を保証。
- **ポーズデータ適用UIの再配置**:
  - 「モーション (VMD)」タブの縦長解消および操作性向上のため、VPDポーズデータ適用UIを「その他機能」タブへ移動・集約。

---

## 11. UIモジュール分割リファクタリングとアーキテクチャ

### 背景と目的

初期開発において単一ファイルに集約されていた `ui/gui.py` は、機能追加に伴い **約 7,900 行 (7,899行)** にまで肥大化していました。これにより以下の課題が生じていました：

- コードの見通しや検索性の低下
- 機能修正時の影響範囲が広く、インポート漏れなどのリスクが増大
- モジュール動的解決やモデル一覧取得などの重複コードの散在

これらを解消するため、**既存の挙動・UIデザイン・外部スクリプト向けの後方互換性を維持したまま**、機能ごとに独立した15のモジュールへ分割・再設計しました（`ui/gui.py` 本体は 247 行へスリム化）。

### モジュール分割構成と設計思想

```text
ui/
├── __init__.py                  # パッケージ公開定義
├── gui_style.py                 # QSSスタイルシート定義
├── common.py                    # Qt互換インポート、Maya窓口、ExecutionLogDialog、共通ヘルパー
│
├── # --- 独立ダイアログ群 ---
├── pmm_dialog.py                # PmmDropArea, PmmModelImportSelectDialog, PmmAnalysisDialog
├── multi_model_dialog.py        # MultiModelLogDialog, MultiModelDropTableWidget, MultiModelImportDialog, MultiModelPhysicsBakeDialog
├── accessory_dialog.py          # AccessoryAttachDialog
├── experimental_dialog.py       # ExperimentalFeaturesDialog
├── morph_window.py              # 表情操作パネル
├── user_dict_dialog.py          # ユーザー辞書設定ダイアログ
├── advanced_dict_dialog.py      # 詳細辞書ダイアログ
├── material_protect_dialog.py   # マテリアル保護設定ダイアログ
├── bone_state_export_dialog.py  # ボーン状態JSONエクスポートダイアログ
│
├── # --- メインタブ・機能パネル群 ---
├── tab_plugin.py                # PluginTabWidget
├── tab_import.py                # ImportTabWidget
├── tab_vmd.py                   # VmdImportTabWidget
├── tab_physics.py               # PhysicsTabWidget, PhysicsGuiTabWidget
├── tab_extra.py                 # ExtraTabWidget
├── tab_cleanup.py               # CleanupTabWidget
├── tab_export.py                # ExportTabWidget, ExportDialog
├── tab_material.py              # MaterialTabWidget, MaterialDialog
├── tab_hik.py                   # HikTabWidget, HikWindow, show_hik_window
│
└── gui.py                       # MmdMayaMainWindow, show_ui, close_existing_ui, 後方互換再エクスポート
```

- **共通基盤の一元化 (`ui/common.py`)**:
  - `PySide6`（Maya 2025+）と `PySide2`（Maya 2024以前）の全ウィジェット・Core・Guiクラスの互換インポートを1箇所に集約。
  - `ExecutionLogDialog`（プログレスバー・推定残り時間付きログウィンドウ）や `get_maya_main_window`、`restore_viewport_lighting` などの共通リソースを提供。
  - `populate_mmd_model_combo` により、シーン内のMMDモデル一覧取得・コンボボックス反映ロジックを一元化。
- **独立ダイアログ群のモジュール化**:
  - `ui/pmm_dialog.py`: PMMプロジェクト解析ダイアログ (`PmmAnalysisDialog`)、ドロップゾーン (`PmmDropArea`)、およびモデル選択インポートダイアログ (`PmmModelImportSelectDialog`) を集約。
  - `ui/multi_model_dialog.py`: 複数モデル順次インポート (`MultiModelImportDialog`) およびベイク確認ダイアログ (`MultiModelPhysicsBakeDialog`) を集約。
  - `ui/accessory_dialog.py`: アクセサリ追従アタッチ (`AccessoryAttachDialog`)。
  - `ui/experimental_dialog.py`: 開発中・試験的機能の一覧ダイアログ (`ExperimentalFeaturesDialog`)。
- **機能タブ群の独立化 (`ui/tab_*.py`)**:
  - プラグイン管理、モデルインポート、モーション、物理演算（XPBD / Bullet）、MMD削除、エクスポート、シェーダー（mmdMaterial）、HumanIK、その他機能の各タブを個別のファイルに分離。
  - 最もコード規模の大きかった物理演算タブ（約 1,600 行）も `ui/tab_physics.py` として独立管理。
- **非循環グラフ（DAG）による依存性管理**:
  - 「`common.py` ← `独立ダイアログ群` ← `各機能タブ群` ← `gui.py`」という単方向の依存関係を確立し、モジュール間の循環参照（Circular Import）を排除。
- **後方互換性とホットリロード機構 (`ui/gui.py`)**:
  - 外部スクリプトやシェルフから `from ui.gui import MmdMayaMainWindow, show_ui, ImportTabWidget, Natanglak` のように直接参照されても正常に機能するよう、全クラスを `ui.gui` の名前空間へ再エクスポート。
  - `show_ui()` 実行時に `_reload_ui_submodules()` を呼び出し、分割された全サブモジュールを依存順序に従って `importlib.reload` し、最新のクラス定義を自動反映するホットリロード機構を導入。

### PMMプロジェクト解析とモデル選択インポート機能

`ui/pmm_dialog.py` と `mmd_core/pmm.py` の連携により、MikuMikuDance のプロジェクトファイル (`.pmm`) からモデルを抽出し、Mayaシーンへ安全にインポートするパイプラインを構築しました：

- **プロジェクト解析とアセット照合**:
  - PMMバイナリからプロジェクトメタデータ（解像度、カメラ視野角）および参照アセット（モデル、アクセサリ、音声）を抽出。
  - PC上の実体ファイルとの突合判定（一致、部分一致、不一致、未検出）や、タイムライン走査によるモーション・ポーズ判定を実施。
  - 重複する未検出アイテムを過去の残骸データ（旧データ）として自動判定し、「ファイルが存在しない」チェックボックスによる表示切り替えをサポート。
- **チェックリスト形式のインポート選択ダイアログ**:
  - 実在するモデルのみ初期状態でチェックONとし、ユーザーが必要なモデルを選択して一括インポート可能。
- **PMD自動変換連携**:
  - モデル形式が旧形式の PMD (`.pmd`) である場合、既存の `converters/pmd2pmx.py` を呼び出して自動的に PMX へ変換し、その後にMayaへインポート。
- **グループ化と二重トランスフォーム防止**:
  - インポート前後のノード差分から各モデルを `{モデル名}_grp` にグループ化し、メッシュの `inheritsTransform` を無効化して座標ずれを防止。
