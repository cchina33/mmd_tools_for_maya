# MMDオリジナルマテリアルプラグイン (mmd_material) 技術仕様書

## 概要

`mmd_material_plugin` は、Autodesk Maya の **Viewport 2.0**（DirectX 11 / OpenGL）環境下において、MikuMikuDance (MMD) 本家のシェーディングモデルおよび質感表現をリアルタイムに再現するための C++ ネイティブプラグイン（`mmd_material.mll`）です。

現代の物理ベースレンダリング（PBR / StandardSurface 等）とは異なり、MMD 特有の「Phong/Blinn-Phong反射モデル」「スフィアテクスチャ合成（乗算/加算）」「Toonセル調陰影」「モデル輪郭線（エッジ）」を忠実に再現します。

---

## アーキテクチャ構成

プラグインは、Maya の Dependency Graph (DG) ノードと Viewport 2.0 レンダリングパイプラインを統合する以下の C++ クラス群で構成されています。

```
mmd_material_plugin/
├── CMakeLists.txt              # CMake ビルド定義 (Maya 2025 Devkit 対応)
├── build.bat / build.ps1       # ビルド自動化スクリプト
├── include/
│   ├── mmd_material_node.h     # MPxNode 派生: mmdMaterial ノード定義
│   └── mmd_shader_override.h   # MPxSurfaceShadingNodeOverride 派生: Viewport 2.0 描画定義
├── src/
│   ├── plugin_main.cpp         # プラグイン登録 (initializePlugin / uninitializePlugin)
│   ├── mmd_material_node.cpp   # アトリビュート定義 & DG コンピュート
│   └── mmd_shader_override.cpp # Viewport 2.0 シェーダーオーバーライド実装
├── shaders/
│   └── mmd_material.fx         # DirectX 11 HLSL ピクセルシェーダー
├── scripts/
│   └── mmd_material_setup.py   # Python 連携用ヘルパー
└── bin/
    └── mmd_material.mll        # コンパイル済みプラグインバイナリ
```

### 主要コンポーネント

- **`MMDMaterialNode` (`MPxNode`)**:
  - ノードタイプ名: `mmdMaterial`
  - ノードID: `0x0013B200`（ユーザー領域ID）
  - 分類 (Classification): `drawdb/shader/surface/mmdMaterial:shader/surface:rendernode/MmdMat/Material`
  - ハイパーシェード上で標準サーフェスシェーダーとして認識され、シェーディンググループ（`shadingEngine`）の `surfaceShader` アトリビュートへ直接接続可能です。
  - **Hypershade ノード作成分類**:
    `rendernode/MmdMat/Material` を指定することで、Pencil+ 4 等の商用プラグインと同様に Hypershade のノード作成 (Create) パネルに独自セクション `MmdMat` > `Material` が自動生成され、ユーザーが手動で一覧から `mmdMaterial` を作成・配線できます。

- **`MMDShaderOverride` (`MHWRender::MPxSurfaceShadingNodeOverride`)**:
  - Viewport 2.0 のシェーディングパイプラインとノードアトリビュートを直結するオーバーライドクラス。
  - 対応描画 API: DirectX 11, OpenGL, OpenGL Core Profile。
  - Maya 内部のシェーディングフラグメント（`mayaPhongSurface`）を活用し、テクスチャサンプリングや光沢計算をGPUハードウェア上で高速実行します。

---

## ノードアトリビュート仕様

`mmdMaterial` ノードが保持するアトリビュート一覧です。MMDのPMXマテリアル仕様と1対1で対応しています。

| アトリビュート名 | 内部型 | デフォルト値 | MMD対応パラメータ | 役割・機能説明 |
| :--- | :--- | :--- | :--- | :--- |
| `color` | Float3 (Color) | (0.8, 0.8, 0.8) | Diffuse (RGB) | 基本表面色。Maya標準の `file.outColor` と直接接続可能。 |
| `transparency` | Float3 (Color) | (0.0, 0.0, 0.0) | 1.0 - Alpha | 透過度。Maya標準仕様に準拠（黒=不透明、白=完全透明）。 |
| `diffuse` | Float | 0.8 | - | 拡散反射係数。 |
| `diffuseColor` | Float3 (Color) | (0.8, 0.8, 0.8) | Diffuse (RGB) | PMX固有の拡散反射色データ保持用。 |
| `diffuseAlpha` | Float | 1.0 | Alpha | PMX固有の不透明度（0.0〜1.0）。 |
| `specularColor` | Float3 (Color) | (0.0, 0.0, 0.0) | Specular (RGB) | 鏡面反射色（ハイライト色）。 |
| `cosinePower` | Float | 5.0 | Specular Power | ハイライトの鋭さ（Blinn-Phong係数）。 |
| `specularPower` | Float | 5.0 | Specular Power | PMX固有の光沢強度データ保持用。 |
| `ambientColor` | Float3 (Color) | (0.4, 0.4, 0.4) | Ambient (RGB) | 環境光（影部分の底上げ色）。 |
| `incandescence` | Float3 (Color) | (0.0, 0.0, 0.0) | - | 自己発光（エミッシブ）。暗所での自発光表現用。 |
| `normalCamera` | Float3 (Vector) | (0.0, 0.0, 1.0) | - | カメラ空間法線。バンプマップや法線テクスチャ接続用。 |
| `sphereMode` | Enum | 0 (None) | Sphere Mode | スフィアマップの適用方法。<br>・0: 無効 (None)<br>・1: 乗算 (Multiply / .sph)<br>・2: 加算 (Additive / .spa)<br>・3: サブテクスチャ (SubTexture) |
| `toonMode` | Enum | 1 (MMD Standard) | Toon Mode | セル影（Toon）の描画モード。<br>・0: 無効 (None)<br>・1: MMD標準セル影 (Standard)<br>・2: 高精細セル影 (Smooth) |
| `edgeEnable` | Boolean | True | Edge Flag | 輪郭線（エッジ）の描画フラグ。 |
| `edgeColor` | Float4 (Color) | (0.0, 0.0, 0.0, 1.0) | Edge Color (RGBA)| 輪郭線の描画色および不透明度。 |
| `edgeSize` | Float | 1.0 | Edge Size | 輪郭線の太さ係数。 |
| `outColor` | Float3 (Color) | - | - | シェーディング結果の出力カラー。 |
| `outTransparency` | Float3 (Color) | - | - | シェーディング結果の出力透過度。 |

---

## Viewport 2.0 連携とテクスチャ処理設計

### 日本語ファイルパスおよび文字化けの完全防止

過去のカスタムシェーダープラグインでは、C++ 内部で独自にテクスチャファイルを読み込む構造に起因して、日本語パス（例: `古明地こいし/tex/...`）を含むモデルでテクスチャが白色にフォールバックする問題が発生していました。

本プラグインでは、テクスチャのロードとデコードを **Maya 標準の `file` ノード** に完全に委譲するアーキテクチャを採用しています。

- Maya 標準のテクスチャキャッシュ機構（OIIO / Maya Texture Cache）を経由してGPUへテクスチャが転送されます。
- 日本語・中国語・マルチバイト文字を含むフォルダパスでも文字化けやファイル脱落が一切発生せず、極めて高速かつ堅牢な描画を実現しています。

### スフィアマッピングの計算モデル

MMD特有の金属・光沢・ハイライト表現であるスフィアマップは、ビュー空間における法線ベクトル $N = (N_x, N_y, N_z)$ からサンプリング UV 座標を動的に算出して合成します。

$$
u = 0.5 + 0.5 \times N_x
$$
$$
v = 0.5 - 0.5 \times N_y
$$

- **乗算スフィア (`.sph` / Mode 1)**: 基本テクスチャカラーに対してスフィアテクスチャ色を乗算（服の陰影や環境遮蔽表現）。
- **加算スフィア (`.spa` / Mode 2)**: 基本テクスチャカラーに対してスフィアテクスチャ色を加算（髪の天使の輪や金属の反射ハイライト）。

---

## Python / MEL ヘルパースクリプト

プラグインのロード、Mayaノードネットワークの自動結線、Hypershadeツリーの独自カテゴリ構築、および既存モデルへのアサインを行うスクリプト群です。

### `mmd_material_hypershade.mel` (Hypershade 連携スクリプト)

Maya の Hypershade ノード作成パネルに独自カテゴリ `MmdMat` > `Material` を追加し、Maya 標準の Surface カテゴリから除外するためのコールバック管理スクリプトです。

- **`renderNodeClassification` コールバック**:
  `rendernode/MmdMat` を Maya に通知し、Maya 標準の Surface リストから `mmdMaterial` を自動除外。
- **`buildRenderNodeTreeListerContent` コールバック**:
  Hypershade のツリー生成時に `addToRenderNodeTreeLister` を実行し、`MmdMat/Material` セクションを動的構築。
- **`hyperShadePanelBuildCreateSubMenu` コールバック**:
  Hypershade の Create メニュー内に `MmdMat` サブメニューを生成。

### `mmd_material_setup.py` (Python セットアップモジュール)

- **`ensure_plugin_loaded()`**:
  プラグイン `bin/mmd_material.mll` がロード済みか確認し、未ロードの場合は自動ロードを実行。同時に `setup_hypershade_callbacks()` を呼び出して Hypershade 連携を有効化。
- **`setup_hypershade_callbacks()`**:
  `mmd_material_hypershade.mel` を読み込み（`source`）、Hypershade 構築コールバックを登録。
- **`create_mmd_material(...)`**:
  `mmdMaterial` ノードと専用の `shadingEngine` を生成。
- **`assign_mmd_material_to_model(targets, inherit_textures=True)`**:
  - 指定されたモデルノードまたはビューポートで選択中のメッシュに対し、`mmdMaterial` を自動生成してアサイン。
  - **テクスチャ引き継ぎ**:
    - 既存シェーダーの `color` や `baseColor` に接続されている `file` ノード（`place2dTexture` を含む）を自動検出し、新シェーダーの `color` へ再接続。
    - **透過テクスチャ引き継ぎと白黒反転防止**:
      既存シェーダーの `opacityR` や `transparency` に接続されている透過テクスチャを自動検出。StandardSurface 等の不透明度（`outAlpha`: 1=不透明）を `mmdMaterial` の透過度（`transparency`: 0=不透明）に繋ぐ際の反転を防ぐため、同一 file ノードの `outTransparency` へ自動読み替え、または `reverse` ノードを介して接続。
  - **受光色・環境光・明度の最適化**:
    - `diffuseColor` を MMD標準の `(1.0, 1.0, 1.0)`、`ambientColor` を MMD本来の `(0.5, 0.5, 0.5)`、`diffuse` 係数を `1.0` に確実に初期化し、直接インポート時と寸分違わぬ明るく鮮やかな発色を再現。
  - **ビュー変換および深度ピーリング連動**:
    - アサイン完了時にカラーマネジメントのビュー変換を `Un-tone-mapped (sRGB)` に自動設定。
    - Viewport 2.0 の透過アルゴリズムを Depth Peeling（`transparencyAlgorithm = 3`）に設定し、多層透過ポリゴンの描画順破綻を防止。
  - **スフィア・Toon 安全フォールバック**:
    スフィアマップや Toon テクスチャが存在しないモデルでも、例外エラーで停止することなくデフォルト値で安全に完了。

---

## GUI「MMDシェーダー」タブ仕様

MMD Tools for Maya メインウィンドウの「MMDシェーダー」タブから、モデル単位のシェーダー置換・管理を行えます。

- **プラグイン状態モニタリング**:
  `mmd_material.mll` の読み込み状態をリアルタイム表示し、未ロード時の「プラグイン再読み込み」ボタンを提供。
- **対象モデル / メッシュ選択**:
  シーン内の MMD モデル一覧または現在ビューポートで選択中のオブジェクトから対象を即座に選択可能。
- **引き継ぎオプション**:
  「既存テクスチャ (file ノード) を自動で引き継ぐ」「スフィア・Toon が存在しない場合は安全にフォールバック」をチェックボックスで切り替え可能。
- **Hypershade 直接連携**:
  「Hypershade を開く」ボタンにより、ワンクリックで Hypershade ウィンドウを呼び出し可能。
- **アサイン実行ボタン**:
  「MMDシェーダーを選択モデルにアサイン」ボタンにより、ワンクリックでモデル内の全マテリアルを `mmdMaterial` に安全置換。

---

## ビルド環境およびコンパイル仕様

### ビルド要件

- **Autodesk Maya**: 2025 (DevkitBase 2025)
- **コンパイラ**: Visual Studio 2022 (MSVC v143, C++17)
- **ビルドツール**: CMake 3.20 以上

### ビルド実行手順

- **環境変数の準備**:
  Maya Devkit の配置パスを `DEVKIT_LOCATION` として設定（未設定の場合はビルドスクリプトが自動補完）。
- **ビルドスクリプトの実行**:
  PowerShell またはコマンドプロンプトから以下のスクリプトを実行：
  ```cmd
  .\build.bat
  ```
  または
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\build.ps1
  ```
- **成果物の配置**:
  コンパイルが完了すると、`bin/mmd_material.mll` が生成されます。
