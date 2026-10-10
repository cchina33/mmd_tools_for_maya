# MMDオリジナルマテリアル プラグイン (.mll)

Maya Viewport 2.0 (DirectX 11) 上で、MikuMikuDance (MMD) 本家のシェーディングモデルを完全再現するカスタムマテリアルプラグインです。

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
