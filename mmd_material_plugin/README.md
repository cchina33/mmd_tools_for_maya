# MMDオリジナルマテリアル プラグイン (.mll)

Maya Viewport 2.0 (DirectX 11) 上で、MikuMikuDance (MMD) 本家のシェーディングモデルを忠実再現するカスタムマテリアルプラグインです。

---

## 概要と特徴

現代のPBR（物理ベースレンダリング）とは異なり、MMDの「固定機能パイプライン風のPhong/Blinn-Phong反射モデル」「スフィアマップ」「Toonグラデーション」を忠実にエミュレートします。

- **シェーディングモデル**:
  - **Toon計算**: 光源ベクトルと法線の内積 $N \cdot L$ から $v = 0.5 - 0.5 \times (N \cdot L)$ をサンプリング座標としてToonテクスチャをサンプリング。
  - **基本陰影**: $(\text{Diffuse} \times \text{Texture} \times \text{LightColor}) \times C_{\text{toon}} + \text{Ambient}$
  - **スフィアマップ**: ビュー空間法線から反射座標 $(u, v)$ を算出し、乗算（`.sph`）または加算（`.spa`）で合成。
  - **スペキュラ**: Blinn-Phongハイライトの加算。
- **アーキテクチャ**:
  - `MPxNode`: Maya ハイパーシェード上で操作可能な `mmdMaterial` ノード。
  - `MPxShaderOverride`: Viewport 2.0 (DirectX 11) によるリアルタイムハードウェアシェーディング。
  - `mmd_material.fx`: DirectX 11 HLSL ピクセルシェーダー。

---

## フォルダ構成

```text
mmd_material_plugin/
├── CMakeLists.txt              # CMakeビルド定義 (Maya 2025 Devkit対応)
├── build.ps1                   # PowerShellビルドスクリプト
├── build.bat                   # コマンドプロンプト用ビルドスクリプト
├── include/                    # C++ ヘッダー
│   ├── mmd_material_node.h     # MPxNode 定義
│   └── mmd_shader_override.h   # Viewport 2.0 MPxShaderOverride 定義
├── src/                        # C++ 実装
│   ├── plugin_main.cpp         # initializePlugin / uninitializePlugin
│   ├── mmd_material_node.cpp   # アトリビュート定義とコンピュート
│   └── mmd_shader_override.cpp # シェーダーオーバーライド実装
├── shaders/                    # HLSL シェーダー
│   └── mmd_material.fx         # DirectX 11 HLSL シェーダー
├── scripts/                    # Python ヘルパー
│   └── mmd_material_setup.py   # マテリアルノード生成・結線スクリプト
└── bin/                        # 出力バイナリ
    └── mmd_material.mll        # コンパイル済みMayaプラグイン
```

---

## ビルド手順

### 動作要件

- Maya 2025
- Maya Developer Toolkit
- Visual Studio 2022 (MSVC v143, C++デスクトップ開発)
- CMake 3.13 以上

### ビルドの実行

PowerShellから以下を実行します：

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

ビルドが成功すると、`bin/mmd_material.mll` が生成されます。

---

## Mayaでの利用方法

Mayaのスクリプトエディタ（Python）から以下のように利用できます：

```python
import sys
# scriptsフォルダへのパスを追加
sys.path.append(r"c:\Users\<ユーザー名>\Documents\maya\2025\plug-ins\mmd_tools_for_maya\mmd_material_plugin\scripts")

import mmd_material_setup

# MMDマテリアルの作成
mat, sg = mmd_material_setup.create_mmd_material(
    name="miku_hair",
    diffuse=(0.8, 0.9, 1.0),
    alpha=1.0,
    specular=(0.3, 0.3, 0.3),
    power=10.0,
    ambient=(0.4, 0.4, 0.4),
    color_tex_path=r"C:\path\to\texture.png",
    sphere_tex_path=r"C:\path\to\hair.spa",
    sphere_mode=2, # 加算スフィア
    toon_tex_path=r"C:\path\to\toon02.bmp",
    toon_mode=1
)
```

---

## レンダリング対応と動作環境 (Rendering Support)

### Viewport 2.0 リアルタイムレンダリング
- **DirectX 11 環境**:
  - `mmd_material.fx`（HLSL）により、サーフェス描画（パス1）と法線反転押し出し（Inverted Hull方式）による輪郭線エッジ描画（パス2）を2パスで実行。
  - MMD特有のスフィアマップ合成（乗算/加算）やToonサンプリング、Blinn-Phongハイライトをリアルタイムに評価。
- **OpenGL Core Profile 環境**:
  - Viewport 2.0 が OpenGL Core Profile モードで動作している場合、DirectX 11 専用シェーダーのマルチパスエッジ機能は非アクティブとなります。
  - この場合、プラグイン付属のエッジメッシュ生成エンジン（`converters/edge_mesh_builder.py`）により、ポリゴンジオメトリとして反転法線エッジメッシュを自動生成することで、OpenGL Core Profile 環境下でもMMD本家と同等の輪郭線を美しく描画します。

### 高品質プレイブラスト・連番画像レンダリング
ビューポート画面をそのまま高品質にレンダリング・書き出し（プレイブラストまたはハードウェアレンダリング）するための推奨設定：
- **アンチエイリアシング**:
  - マルチサンプルAA (MSAA 8x): ジャギーのない滑らかな輪郭線を生成。
  - ポストプロセスAA: スクリーンスペースでの輪郭補正。
- **透過アルゴリズム**:
  - 深度ピーリング (Depth Peeling): 重なり合う半透明メッシュ（髪、羽、フリル、レース等）の前後関係を正確にソート。
- **モーション暗化防止**:
  - シャッター開度（Shutter Open Fraction）を微小値（0.01）に設定することで、HDRポストパスでのブレや画面の暗化を抑止。

### 外部レンダラー（Arnold等）およびソフトウェアレンダリング
- **DGコンピュート評価**:
  - `mmdMaterial` は Maya の依存グラフ（DG）ノードとして動作し、`compute()` メソッド内で基本テクスチャカラー・拡散光・不透明度を標準アトリビュート（`outColor`, `outTransparency`）へ出力します。
  - これにより、Hypershade のスウォッチ生成や、Arnold などの外部オフラインレンダラーによるシーン評価時にもマテリアルのベースカラーと透過度が適切に反映されます。
- **エッジメッシュのマルチレンダラー出力**:
  - ジオメトリ方式で生成されたエッジメッシュ（`*_Edge`）は、ポリゴンメッシュ上に単色の `surfaceShader` がアサインされた構造となっています。
  - レンダラーの種別（Arnold、Maya Software、Viewport 2.0、Playblast）を問わず、どんなレンダリングエンジンでもセルアニメ調のエッジ輪郭線が均一にレンダリングされます。
  - 影を落とさず（`castsShadows = 0`）、影を受けない（`receiveShadows = 0`）設定が施されているため、パストレーシング環境でも不要な落ち影のノイズを生じさせません。

