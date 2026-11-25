# MMD専用マテリアル統合プラグイン (mmd_material.mll) 技術仕様書

> [!NOTE]
> 本詳細技術仕様書は、AI によって作成・整理されたドキュメントです。内容はソースコードおよび開発記録をもとに記述していますが、実際の動作と細部が異なる場合があります。

## 概要

MMD Tools for Maya は、Autodesk Maya の **Viewport 2.0**（DirectX 11 / OpenGL Core Profile）環境下において、MikuMikuDance (MMD) 本家の質感表現やセル調シェーディングを忠実に再現するため、専用の C++ ネイティブプラグイン（`mmd_material.mll`）を提供しています。

以前は個別のプラグインパッケージとして存在していた `mmd_material_plugin`（`mmdMaterial` 基盤）と `mmd_toon_plugin`（`mmdToonShader` セル調シェーダー）は、描画パイプラインの緊密な連携と運用の効率化のため、単一のプラグインバイナリ（`mmd_material.mll`）へと統合されました。

単一のプラグインバイナリ（`mmd_material.mll`）内に、以下の主要コンポーネントが集約・統合されています：

- **MMD統合マテリアルシステム (`mmdToonShader` / `mmdMaterial`)**:
  本家 MMD 解析に基づく受光モデル・白飛び防止クランプ・セルフシャドウ統合補間を提供する推奨セルシェーダーノード `mmdToonShader` と、Maya フラグメントグラフ（`mayaPhongSurface`）連携およびスウォッチ互換を提供する `mmdMaterial` を一体として提供します。
- **MMD Viewport Renderer (`MMDRenderOverride`)**:
  エッジ描画パス（`MMDEdgeScenePass`）による同一メッシュ方式の輪郭線描画、単一パス統合描画（`kRenderShadedItems`）、Object Sorting 透過合成、白背景表示を統合した独自レンダーオーバーライドです。
- **MMD Renderer オフスクリーン描画 (`mmdRender` コマンド)**:
  Render View ウィンドウおよびバッチ出力に対応し、頂点カラー（`COLOR0`）と Depth Peeling を正規評価する `ogsRender` 統合オフスクリーン描画機能です。

---

## アーキテクチャ構成

システムは、Maya の Dependency Graph (DG) ノード、Viewport 2.0 レンダーオーバーライド、およびシェーディングパイプラインを統合する以下のディレクトリ構成となっています。

```text
mmd_tools_for_maya/
└── mmd_material_plugin/              # MMD統合マテリアル & レンダーオーバーライド
    ├── CMakeLists.txt                # CMake ビルド定義 (Maya 2025 Devkit 対応)
    ├── build.bat / build.ps1         # ビルドスクリプト
    ├── include/
    │   ├── mmd_material_node.h       # MPxNode 派生: mmdMaterial ノード定義
    │   ├── mmd_shader_override.h     # MPxSurfaceShadingNodeOverride 派生
    │   ├── mmd_toon_node.h           # MPxNode 派生: mmdToonShader ノード定義
    │   ├── mmd_toon_override.h       # MPxSurfaceShadingNodeOverride 派生
    │   ├── mmd_render_override.h     # MRenderOverride 派生: MMDレンダーオーバーライド
    │   ├── mmd_edge_scene_pass.h     # MSceneRender 派生: 同一メッシュエッジ描画パス
    │   ├── mmd_edge_shader_code.h    # HLSL / OGSFX エッジシェーダーコード
    │   └── mmd_render_cmd.h          # MPxCommand 派生: mmdRender コマンド
    ├── src/
    │   ├── plugin_main.cpp           # プラグイン初期化・ノード一括登録
    │   ├── mmd_material_node.cpp     # mmdMaterial 定義 & DG コンピュート
    │   ├── mmd_shader_override.cpp   # Viewport 2.0 サーフェスフラグメント連携
    │   ├── mmd_toon_node.cpp         # mmdToonShader 定義 & DG コンピュート
    │   ├── mmd_toon_override.cpp     # OGSFX 組み込みシェーダーオーバーライド
    │   ├── mmd_render_override.cpp   # マルチパスレンダーオーバーライド実装
    │   ├── mmd_edge_scene_pass.cpp   # エッジ描画パス・ターゲット制御実装
    │   └── mmd_render_cmd.cpp        # オフスクリーンレンダリング実行実装
    ├── shaders/
    │   └── mmd_toon.ogsfx            # Viewport 2.0 OGSFX トゥーンシェーダー
    ├── scripts/
    │   ├── mmd_material_setup.py     # Python 連携用ヘルパー
    │   ├── mmd_material_hypershade.mel # Hypershade 統合コールバック
    │   └── mmd_edge_bake.py          # 材質エッジ設定頂点カラー焼き込みスクリプト
    └── bin/
        └── mmd_material.mll          # コンパイル済み統合プラグインバイナリ
```

---

## MMD統合マテリアルシステム仕様 (`mmdMaterial` & `mmdToonShader`)

### 統合アーキテクチャと設計思想

従来の開発段階では、サーフェスシェーダー基盤（`mmdMaterial`）とセル調シェーダー（`mmdToonShader` / `mmd_toon_shader.mll`）が別々のプラグインパッケージとして分かれていました。しかし、メッシュの輪郭線（エッジ）描画パスや材質モーフ連動、レンダーオーバーライドとの協調動作においてプラグインの二重管理や連携の複雑化が生じていました。

これらを解消するため、すべての MMD 質感制御コンポーネントを `mmd_material.mll` へ統合しました。統合されたシステムでは、2つのシェーダーノードが目的・用途に応じて緊密に連携しながら同一の描画基盤を共有します。

- **`mmdToonShader` (メイン推奨セルシェーダー)**:
  - ノードタイプ名: `mmdToonShader`（ノードID: `0x0013B280`）
  - 分類 (Classification): `rendernode/MmdToon/Material:shader/surface:drawdb/shader/surface/mmdToonShader`
  - サーフェスシェーディングオーバーライド `MMDToonOverride` を内包。組み込み OGSFX（`mmd_toon.ogsfx`）をロードし、ディフューズテクスチャ、スフィアテクスチャ、トゥーンテクスチャ、およびシャドウマップテクスチャを統合サンプリングします。
  - MMD本家解析仕様に準拠した受光モデル、白飛び防止クランプ、セルフシャドウとトゥーンの統合補間（二重影の黒濁り抑止）を GPU 上で直接評価します。モデルインポート（`pmxpaimaya.py`）時の推奨シェーダーとして設定されます。
- **`mmdMaterial` (互換サーフェスシェーダー)**:
  - ノードタイプ名: `mmdMaterial`（ノードID: `0x0013B200`）
  - 分類 (Classification): `rendernode/MmdMat/Material:shader/surface:swatch/mayaShader:drawdb/shader/surface/mmdMaterial`
  - Maya の `mayaPhongSurface` フラグメントを返すサーフェスオーバーライド `MMDShaderOverride` として動作します。
  - Maya 標準のフラグメントグラフと連携してテクスチャやライティングを適切に処理し、Hypershade 上でのスウォッチ描画互換を担保します。

### 共通アトリビュート体系と相互運用性

`mmdToonShader` と `mmdMaterial` は、MMD の材質規約に準拠した共通のパラメータアトリビュート群を備えています。インポートエンジン（`pmxpaimaya.py`）や表情・材質モーフ制御、エッジベイクスクリプト（`mmd_edge_bake.py`）は、ノード種別の差異を意識することなく同一の命名規則で制御できます。

#### ノードアトリビュート一覧

| アトリビュート名 | 内部型 | mmdToonShader | mmdMaterial | MMD対応パラメータ | 役割・機能説明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `color` | Float3 (Color) | あり | あり | Diffuse (RGB) | 基本表面色・テクスチャカラー。Maya標準の `file.outColor` と直接接続可能。 |
| `diffuseColor` | Float3 (Color) | あり | あり | Diffuse (RGB) | PMX材質固有の拡散反射色データ保持用。 |
| `diffuseAlpha` | Float | あり | あり | Alpha | PMX材質固有の不透明度（0.0〜1.0）。 |
| `transparency` | Float3 (Color) | あり | あり | 1.0 - Alpha | 透過度（黒=不透明、白=透明）。二重透過配線に対応。 |
| `diffuse` | Float | あり | あり | - | 拡散受光係数。透明化時に `0.0` へ連動して受光を遮断。 |
| `ambientColor` | Float3 (Color) | あり | あり | Ambient (RGB) | 環境光（影部分の底上げ色）。 |
| `incandescence` | Float3 (Color) | あり | あり | - | 自己発光（エミッシブ）。暗所発光や加算スフィア接続用。 |
| `specularColor` | Float3 (Color) | あり | あり | Specular (RGB) | 鏡面反射色（ハイライト色）。 |
| `specularPower` | Float | あり | あり | Specular Power | PMX固有の光沢強度データ保持用。 |
| `cosinePower` | Float | あり | あり | - | Phongハイライト係数。 |
| `sphereMode` | Enum | あり | あり | Sphere Mode | スフィアマップモード。<br>・0: 無効 (None)<br>・1: 乗算 (Multiply / .sph)<br>・2: 加算 (Additive / .spa)<br>・3: サブテクスチャ (SubTexture) |
| `toonMode` | Enum | あり | あり | Toon Mode | セル影（Toon）の描画モード。<br>・0: 無効 (Disabled)<br>・1: MMD標準 (Standard)<br>・2: 高精細 (Smooth) |
| `lightMode` | Enum | あり | - | - | MMD基準輝度換算モード。<br>・0: Mayaライト直接 (Maya Light)<br>・1: MMD基準輝度換算 (0.604換算) |
| `shadowMode` | Enum | あり | - | - | セルフシャドウ判定方式。<br>・0: 無効 (Disabled)<br>・1: MMD深度差判定 (MMD Depth)<br>・2: 4点PCFフィルタ (PCF) |
| `shadowBias` | Float | あり | - | - | シャドウアクネ防止用デプスバイアス。 |
| `edgeEnable` | Boolean | あり | あり | Edge Flag | 輪郭線（エッジ）の描画フラグ。 |
| `edgeColor` | Float4 (Color) | あり | あり | Edge Color (RGBA) | 輪郭線の描画色および不透明度。 |
| `edgeSize` | Float | あり | あり | Edge Size | 輪郭線の太さ係数。材質モーフ連動に対応。 |
| `colorTexture` | Float3 (Color) | あり | - | Texture | 基本ディフューズテクスチャ接続スロット。 |
| `sphereTexture` | Float3 (Color) | あり | - | Sphere Texture | スフィアテクスチャ接続スロット。 |
| `toonTexture` | Float3 (Color) | あり | - | Toon Texture | トゥーン階調テクスチャ接続スロット。 |
| `normalCamera` | Point (Vector) | あり | あり | - | カメラ空間法線入力。バンプマップ接続対応。 |
| `outColor` | Float3 (Color) | あり | あり | - | シェーディング結果の出力カラー。 |
| `outTransparency` | Float3 (Color) | あり | あり | - | シェーディング結果の出力透過度。 |

---

### MMD Toon Shader の受光・陰影計算モデル

本シェーダーは、`mmd_toon.ogsfx` 内で以下の数理モデルに基づいてリアルタイム計算を行います。

#### MMD基準輝度換算 (`lightMode = 1`)

Maya の標準ライトは強度が $1.0$ 以上になることが多く、MMDモデルをそのまま照らすと露出オーバー（白飛び）の原因になります。MMD本家の初期ライト設定輝度（$154 / 255 \approx 0.604$）を基準として、ライトカラーの上限を自動クランプします。

$$
L_{col} = \begin{cases}
\min(LightColor \times LightIntensity, \; 0.604) & (\text{lightMode} = 1) \\
LightColor \times LightIntensity & (\text{lightMode} = 0)
\end{cases}
$$

#### 事前受光色 ($EgColor$) の飽和クランプ

拡散光と環境光が加算された段階でカラー値を $[0, 1]$ にクランプし、明るいテクスチャでも原色情報が破壊されないようにします。

$$
EgColor = \mathrm{clamp}\left( DiffuseColor \times L_{col} + AmbientColor \times L_{col} + AmbientColor \times L_{amb}, \; 0.0, \; 1.0 \right)
$$

$$
BaseColor = EgColor \times TexColor
$$

#### トゥーン受光係数 ($compToon$)

法線ベクトル $N$ とライト到来逆ベクトル $-L$ の内積（Lambert）に対し、MMD特有の急峻な傾き（係数 $3.0$）を与えてセル影の境界を明瞭化します。

$$
N \cdot L = \max(N \cdot (-L), \; 0.0)
$$

$$
compToon = \mathrm{clamp}( (N \cdot L) \times 3.0, \; 0.0, \; 1.0 )
$$

#### セルフシャドウ判定 ($compShadow$)

シャドウマップからサンプリングした深度値 $Depth_{map}$ と、現在の描画点深度 $Depth_{cur}$ の差分をもとに、MMD本家準拠の急峻なステップ関数で遮蔽率を計算します。

$$
diff = \max(Depth_{cur} - Depth_{map} - ShadowBias, \; 0.0)
$$

$$
compShadow = 1.0 - \mathrm{clamp}( diff \times 1500.0 - 0.3, \; 0.0, \; 1.0 )
$$

#### トゥーンとセルフシャドウの最小値統合補間

従来のシェーダーで発生していた「二重影による黒濁り」を防ぐため、トゥーン係数とシャドウ係数の **最小値（$\min$）** を統合補間係数 $comp$ として採用します。これにより、セルフシャドウが落ちた領域でもトゥーン最暗色より暗く落ち込むことがなくなります。

$$
comp = \begin{cases}
\min(compToon, \; compShadow) & (\text{toonMode} = 1) \\
compShadow & (\text{toonMode} = 0)
\end{cases}
$$

#### トゥーン陰影カラーの合成

影領域では、基本色が Toon テクスチャ最暗色（サンプリング座標 $v=0.05$）へ滑らかに置き換わります。

$$
BlendedColor = BaseColor \times \left( comp + ToonDark \times (1.0 - comp) \right)
$$

#### ハイライトおよびスフィアの重畳

ハイライトは影領域（$comp = 0$）では自然に消滅し、スフィアマップはモードに応じて乗算（Mode 1）または加算（Mode 2）されます。

$$
Specular = SpecularColor \times (N \cdot H)^{SpecularPower} \times comp
$$

$$
FinalRGB = BlendedColor + Specular + SphereEffect
$$

---

## Viewport 2.0 連携とテクスチャ処理設計

### 日本語ファイルパスおよびマルチバイト対応

テクスチャの読み込みとデコードは Maya 標準の `file` ノードに委譲する設計を採用しています。

- Maya 標準の画像キャッシュ機構（OpenImageIO / Maya Texture Cache）を経由して GPU へ安定転送。
- 日本語や中国語、マルチバイト空白文字を含むフォルダパスでも文字化けやファイル脱落が発生せず、安定した描画を実現しています。

### スフィアマッピングの計算モデル

MMD 特有の光沢・金属表現であるスフィアマップ（`.sph` / `.spa`）は、視線空間法線ベクトル $N_{view} = (N_x, N_y, N_z)$ からサンプリング UV を動的に計算します。

$$
u = 0.5 + 0.5 \times N_x
$$

$$
v = 0.5 - 0.5 \times N_y
$$

- **乗算スフィア (`.sph` / Mode 1)**: 基本色に乗算し、衣服のシワや陰影を表現。
- **加算スフィア (`.spa` / Mode 2)**: 基本色に加算し、髪の天使の輪や金属光沢を表現。

### MMD標準地面影（シャドウキャッチャー平面）仕様

モデル直下に専用の地面影メッシュ（`mmd_ground_shadow_grp` / `mmd_ground_shadow_mesh`）を自動生成します。

- **片面描画（Single Sided）とバックフェイスカリング**:
  地面影メッシュの `doubleSided` をオフにし、上面視点のみ影を描画。
- **煽り構図（下からの見上げ）透過対応**:
  カメラが地面の下からモデルを見上げるローアングル時、影平面が手前を遮蔽しないよう裏面カリングによって透過させます。

---

## Hypershade 統合コールバック仕様 (`mmd_material_hypershade.mel`)

Maya の Hypershade において、`mmdMaterial` および `mmdToonShader` を独自ノードとして管理するための MEL コールバック群です。

### 提供されるコールバック関数

- **`renderNodeClassification` フック**:
  - `mmdMaterial_RenderNodeClassificationCallback()`: `"rendernode/MmdMat"` を返却。
  - `mmdToonShader_RenderNodeClassificationCallback()`: `"rendernode/MmdToon"` を返却。
  - これにより、Maya 標準の Surface カテゴリ（`shader/surface`）から両ノードが自動除外され、混同を防ぎます。
- **`hyperShadePanelBuildCreateSubMenu` フック**:
  - `mmdMaterial_HyperShadePanelBuildCreateSubMenuCallback()`: `"rendernode/MmdMat"` サブメニューを生成。
  - `mmdToonShader_HyperShadePanelBuildCreateSubMenuCallback()`: `"rendernode/MmdToon"` サブメニューを生成。
- **`hyperShadePanelPluginChange` / `createRenderNodePluginChange` フック**:
  - 分類文字列が `"rendernode/MmdMat"` または `"rendernode/MmdToon"` で始まる場合に `1` を返し、プラグインのロード・アンロード時に Hypershade を自動再構築。
- **`buildRenderNodeTreeListerContent` フック**:
  - `mmdMaterial_BuildRenderNodeTreeListerContentCallback()`:
    Hypershade のノード作成ツリー（TreeLister）に以下の独自セクションを動的構築。
    - `MmdMat/Material` (`rendernode/MmdMat/Material`) -> `mmdMaterial`
    - `MmdToon/Material` (`rendernode/MmdToon/Material`) -> `mmdToonShader`
- **一括登録・解除**:
  - `mmdMaterial_RegisterCallbacks()`: 上記コールバック群を一括登録。
  - `mmdMaterial_UnregisterCallbacks()`: 上記コールバック群を一括解除。

---

## Python セットアップモジュール仕様 (`mmd_material_setup.py` / `mmd_edge_bake.py`)

- **`mmd_material_setup.ensure_plugin_loaded()`**:
  プラグインバイナリ（`mmd_material.mll`）のロード確認・自動ロードおよび Hypershade コールバックの有効化。
- **`mmd_material_setup.setup_hypershade_callbacks()`**:
  `mmd_material_hypershade.mel` を `source` し、`mmdMaterial_RegisterCallbacks()` を実行。
- **`mmd_material_setup.assign_mmd_material_to_model(targets, inherit_textures=True)`**:
  選択されたモデルまたはメッシュに `mmdMaterial` を一括アサインし、テクスチャ接続・透過設定・ビュー変換（Un-tone-mapped）・透過アルゴリズム（Object Sorting）を自動構成。
- **`mmd_edge_bake.bake_edge_scale(mesh_list=None)`**:
  モデル内の各材質（`mmdMaterial`）に設定された `edgeEnable` および `edgeSize` を頂点カラーセット `mmd_edge_scale` へ焼き込み。材質ごとのエッジ除外設定（目、眉、口、チーク等）や線幅スケールをメッシュ頂点へ反映させ、エッジ描画パス（`MMDEdgeScenePass`）と連動。

---

## ビルド環境およびコンパイル仕様

### ビルド要件

- **Autodesk Maya**: 2025 (DevkitBase 2025)
- **コンパイラ**: Visual Studio 2022 (MSVC v143, C++17)
- **ビルドツール**: CMake 3.20 以上

### ビルド実行手順

- **環境変数の準備**:
  Maya Devkit の配置パスを `DEVKIT_LOCATION` として設定。
- **ビルドスクリプトの実行**:
  ```cmd
  .\build.bat
  ```
  または
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\build.ps1
  ```
- **成果物の配置**:
  - `mmd_material_plugin/bin/mmd_material.mll`

---

## MMDレンダーオーバーライドおよびエッジ描画パイプライン仕様

### レンダーオーバーライドパイプライン (`MMDRenderOverride`)

MMD の質感およびエッジ輪郭線を Viewport 2.0 上で破綻なく再現するため、プラグインは独自のレンダーオーバーライド `MMDRenderOverride`（UI名: `MMD Viewport Renderer`）を提供します。
本パイプラインは、以下の順序でレンダーオペレーションを逐次実行します。

- **背景クリアオペレーション (`mClearOp` / `MMDClearOperation`)**:
  - MMD 同様の白背景クリア（RGB: `1.0, 1.0, 1.0`）および深度バッファクリア（Depth: `1.0`）を実行。
- **同一メッシュエッジ描画パス (`mEdgePass` / `MMDEdgeScenePass`)**:
  - サーフェス描画の前に実行。後述の Inverted Hull（裏面押し出し）により、モデル外周のエッジ輪郭面を描画。
- **統合サーフェス描画オペレーション (`mSceneRenderOpaque` / `MMDSceneRender`)**:
  - フィルタ: `kRenderShadedItems`。不透明メッシュおよび透過メッシュを一括して描画し、エッジパスで描画された手前側ポリゴンを上書きすることで、外周の輪郭線のみを残します。
  - 不透明パスと透過パスを分割せず単一パスで描画することにより、多層透過（Depth Peeling）時の中間バッファ分離破綻や白背景抜け（白い影）を防止します。
- **ビューポートHUD描画オペレーション (`mHudOp` / `MHUDRender`)**:
  - ビューポートのカメラ情報やグリッド、HUDを表示（オフスクリーン描画時は無効化）。
- **画面出力オペレーション (`mPresentOp` / `MPresentTarget`)**:
  - バックバッファからビューポートウィンドウへ描画結果を転送（オフスクリーン描画時は無効化）。

### 同一メッシュエッジ描画パス (`MMDEdgeScenePass`) の数理と仕組み

#### 単一メッシュ方式（同一ジオメトリ描画）

従来の別メッシュ複製方式（`*_Edge`）を排除し、元メッシュ単体から表面と裏面エッジを描画する MMD 本家構造を採用しています。
シーン内に冗長なメッシュノードを生成せず、リグやスキニングの変形計算負荷を最小限に抑えます。

- **対象メッシュの動的フィルタリング**:
  `edgeEnable` が有効な `mmdMaterial` が割り当てられたメッシュのみを自動抽出し、不要な補助オブジェクト（地面プレーン等）を除外。
- **裏面描画（Inverted Hull 方式）**:
  カリングステートを前面カリング（`CullMode = FRONT` または時計回り頂点ワインディング）に設定し、法線方向へ押し出した裏面ポリゴンのみを描画。

#### 頂点カラーセット `mmd_edge_scale` によるエッジ制御と動的同期

メッシュ頂点に保持されるカラーセット `mmd_edge_scale` を参照し、頂点シェーダー内で材質ごとの細やかな線幅制御および描画除外を動的に行います。

- **R チャンネル (`edge_scale.r`)**:
  PMX 材質固有のエッジ太さ倍率（`edge_size`）。頂点押し出し量のスケーリングに使用。
- **G チャンネル (`edge_scale.g`)**:
  焼き込み状態フラグ。`1.0` で焼き込み済みと認識され、未設定頂点（`0.0`）はフォールバック値（`1.0`）へ自動復帰。
- **B チャンネル (`edge_scale.b`)**:
  予約領域（初期値 `0.0`）。
- **A チャンネル (`edge_scale.a`)**:
  描画有効フラグ。`1.0` でエッジ描画、`0.0` で非描画。
- **材質モーフ追従の動的同期 (`syncMeshEdgeColors`)**:
  表情操作や材質モーフ（ドロワoff、靴off、靴下off、帽子off等）により、リアルタイムに材質の透過度やエッジ有効フラグが変化した場合、`MMDEdgeScenePass::refreshTargets()` が毎フレーム各シェーディンググループの `edgeEnable`、`edgeSize`、`diffuseAlpha`、`transparency` を監視します。実効サイズ（$edgeSize \times opacity$）に変化が生じた場合、即座に `MFnMesh::setFaceVertexColors` および `mesh.updateSurface()` を呼び出して頂点カラーセットを動的更新します。これにより、表面が透明化した衣装パーツの裏面エッジが黒い塊（黒い影）として取り残される現象を防止します。

#### ピクセル指定の線幅計算数理

エッジ幅はワールド空間の絶対距離ではなく、画面上のピクセル単位（既定 `1.5px`）で計算されます。これにより、カメラの画角（FOV）や被写体との距離に左右されず、常に均一なセル調の輪郭線が維持されます。

$$
Offset_{px} = \frac{EdgeSize_{px}}{ScreenHeight} \times 2.0
$$

$$
V_{clip} = M_{proj} \times M_{view} \times V_{world}
$$

$$
N_{clip} = M_{proj} \times (M_{view} \times N_{world})
$$

$$
N_{proj} = \frac{(N_{clip}.x, \; N_{clip}.y)}{\sqrt{N_{clip}.x^2 + N_{clip}.y^2 + \epsilon}}
$$

$$
V_{edge} = V_{clip} + \begin{pmatrix} N_{proj}.x \times Offset_{px} \times V_{clip}.w \times \frac{Aspect}{2.0} \\ N_{proj}.y \times Offset_{px} \times V_{clip}.w \times \frac{1.0}{2.0} \\ 0 \\ 0 \end{pmatrix} \times Scale_{mat}
$$

ここで、プロジェクション行列要素に対する保護ガード（$\epsilon = 10^{-6}$）を適用し、ゼロ除算や数値不安定性による画面乱れを防止します。

#### トゲ発生および遠距離クリップ消失の防止機構

- **ピクセルシェーダー破棄（`discard`）によるトゲ防止**:
  エッジ無効頂点（$scale \le 0$）が存在する場合、頂点シェーダーで座標を固定値へ移動させると有効頂点との境界ポリゴンが画面端へ引き伸ばされて鋭利なトゲが発生します。これを防ぐため、無効頂点のアルファフラグ（`VtxColor.a`）を `0.0` としてピクセルシェーダーへ渡し、ピクセルシェーダー（`PS_Edge`）内の `discard` 命令でピクセル単位で破棄します。
- **ビュースペース深度オフセットによる遠距離消失防止**:
  クリップ空間奥方向への定数加算（`clipPos.z += 0.0008f * clipPos.w`）を行うと、Maya 既定のクリップ面設定（$nearClip = 0.1$）においてカメラ距離 $Z > 125$ で NDC 深度が $1.0$（Far Clip 境界）を超過し、エッジが消失します。このため、カメラ距離に比例するビュースペースでの深度オフセット（`viewPos.z -= px * worldPerPx * 0.5f`）に統一し、カメラ距離にかかわらず安定した輪郭線描画を維持します。
- **ラスタライザ深度バイアス**:
  ハードウェアラスタライザステートに `DepthBias = 50` および `SlopeScaledDepthBias = 1.0f` を設定。サーフェスの傾きに応じて動的に深度値を奥へシフトさせ、視線に対して浅い角度を持つ面での Z ファイティングを解消。

#### デュアルグラフィックス API 対応

DirectX 11（HLSL）および OpenGL Core Profile（OGSFX）の双方に対応したシェーダーコードを内包し、プラットフォームやグラフィックスドライバの種別を問わず同一の描画結果を提供します。

### MMD Renderer オフスクリーン描画仕様 (`MMDRenderCmd` / `mmdRender`)

Render View ウィンドウおよびバッチ出力において、MMD Viewport Renderer の描画結果をそのまま画像化するためのレンダラーコマンド `mmdRender` を提供します。

- **`batch:` 描画ソースの制限と `ogsRender` パイプライン統合**:
  Maya VP2 の `theRenderer->render("batch:cameraShape", ...)` 経由でカスタムレンダーターゲットへ直接描画する場合、メッシュの頂点カラーストリーム `COLOR0`（`mmd_edge_scale`）がシェーダーへ配信されず `(0,0,0,0)` となる内部仕様が存在します。その結果、エッジシェーダーが未ベイク状態と誤認して非表示面にも太さ 1.0 の輪郭線を描画してしまいます。
  この問題を解消するため、`mmdRender` は事前に `mmdOverride->preSyncEdgePass()` でモーフ状態を頂点カラーへ同期したうえで、頂点カラーと `Depth Peeling` をビューポートと同一品質で正規評価する `ogsRender` パイプラインを介してオフスクリーン描画を実行し、生成されたピクセルバッファを `MRenderView`（Render View）へ一括転送します。
- **多層透過（Depth Peeling）の適正動作**:
  ビューポートレンダリングと同一の描画コンテキストで `Depth Peeling (3)` を評価するため、モデル内の複雑な透過前後関係（瞳、睫毛、チーク、半透明スカート等）を乱すことなく、忠実にレンダリング結果を出力します。
