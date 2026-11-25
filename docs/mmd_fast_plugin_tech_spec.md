# MMD Fast Plugin (mmd_fast.mll) 技術解説書

## 概要とアーキテクチャ

`mmd_fast_plugin` は、Maya 上での MMD（PMX / VMD）データ取り扱いを高速化するために開発された C++ ネイティブプラグインです。
従来の Python スクリプト単体による逐次処理では、大容量モデルや長時間のダンスモーション読み込み時に膨大な時間（数分〜数十分）を要していました。
本プラグインでは、負荷の高いバイナリ解析や並列計算、Maya 内部データ構造への一括転送を C++ 側で担い、名前解決や UI 制御、シェーダー構築といった柔軟性が求められる処理を Python 側で担う「ハイブリッド構成」を採用しています。

```
[PMX / VMD バイナリファイル]
       │
       ▼ (C++ 高速ファイル解析 & メモリキャッシュ)
 [ PmxBinaryCache / VmdBinaryCache ]
       │
       ├─ (C++) メッシュ一括生成 (MFnMesh::create)
       ├─ (C++) スキニングウェイト一括注入 (MFnSkinCluster::setWeights)
       ├─ (C++) ブレンドシェイプ一括登録 (inputPointsTarget / inputComponentsTarget 直結)
       ├─ (C++) ボーンキーフレームマルチスレッド並列計算 & 一括注入 (MFnAnimCurve::addKeys)
       ├─ (C++) モーフキーフレーム一括注入 (MFnAnimCurve::addKeys)
       └─ (C++) カメラキーフレームベジェ展開サンプリング & 一括注入 (MFnAnimCurve::addKeys)
       │
       ▼ (Python 協調処理)
 [ 辞書名称照合 / マテリアル・シェーダー構築 / 足IK構築 / 自動フォールバック ]
```

---

## 主な特徴

- **ハイブリッド設計による堅牢性**：
  C++ プラグインが未ロードの環境やロードに失敗した場合でも、自動的に従来の Python 処理へフォールバックして処理を継続します。
- **オンメモリキャッシュ機構**：
  同一ファイルに対する複数回のアクセス（メッシュ生成、モーフ登録、ウェイト設定）において、バイナリの再パースを抑止して即座にメモリ上の構造体を参照します。
- **マルチスレッド並列処理**：
  大量のボーンキーフレームに対するクォータニオン座標変換、オイラー角変換、最短連続角計算、MMD ベジェ補間パラメータ解析をマルチスレッドで並列処理します。
- **物理ベイク機能の統合**：
  旧来の `mmd_motion_plugin` に含まれていた高速キーフレームベイクコマンド（`mmdFastBakeBone`）を内包し、プラグインの集約を実現しています。

---

## 提供コマンド一覧

| コマンド名 | 種別 | 概要 |
| :--- | :--- | :--- |
| `mmdFastImportPmxMesh` | PMX | PMX の頂点・面・UV・法線・エッジ倍率からメッシュを一括生成 |
| `mmdFastApplyPmxBlendShapes` | PMX | PMX 頂点モーフの移動差分を BlendShape ノードへ直接一括注入 |
| `mmdFastApplyPmxSkinWeights` | PMX | PMX の頂点ウェイトを SkinCluster へネイティブ速度で一括注入 |
| `mmdFastImportVmdBone` | VMD | ボーンモーションをマルチスレッド計算し AnimCurve へ一括注入 |
| `mmdFastImportVmdMorph` | VMD | 表情モーフモーションを AnimCurve へ一括注入 |
| `mmdFastImportVmdCamera` | VMD | カメラモーションをベジェ補間式でサンプリング展開し一括注入 |
| `mmdFastBakeBone` | 物理ベイク | 物理シミュレーション結果の各軸キーフレームをジョイントへ一括書き込み |

---

## 技術仕様詳細

### PMX 高速インポート (`mmd_fast_pmx_cmd`)

- **バイナリ解析とキャッシュ (`PmxBinaryCache`)**：
  - PMX 2.0 / 2.1 規格に準拠し、頂点・面・テクスチャ・材質・ボーン・モーフの各バイナリブロックを高速に読み込みます。
  - Shift-JIS (CP932) および UTF-8 / UTF-16 文字列の相互変換を適切に処理します。
  - 解析結果は `PmxParsedModel` 構造体に保持され、同一ファイルパスでの連続呼び出し時はパース処理をスキップします。

- **メッシュの一括生成 (`mmdFastImportPmxMesh`)**：
  - 座標系変換：MMD（左手系・Y-up）から Maya（右手系・Y-up）への変換として `(X * scale, Y * scale, -Z * scale)` を適用します。
  - 面の巻き順（ワインディング）：Z 軸の反転に伴い、面の表裏（法線方向）を正しく維持するため頂点接続インデックスを `(i0, i2, i1)` の順序で反転登録します。
  - UV 座標変換：V 軸反転 `(U, 1.0 - V)` を適用します。
  - 法線変換：Z 軸反転 `(NX, NY, -NZ)` を適用します。
  - 重複頂点インデックスを含む縮退三角形を検知して除外します。
  - 各材質の描画フラグおよびアルファ値に基づき、頂点エッジの有効性を判定してカラーセット `mmd_edge_scale` へ格納します。
  - `MFnMesh::create` を用いて単一 API 呼び出しでポリゴンメッシュ、UV、法線、頂点カラーセットを生成します。

- **ブレンドシェイプの一括注入 (`mmdFastApplyPmxBlendShapes`)**：
  - 各頂点モーフの差分ベクトル配列と対象頂点インデックスを疎（Sparse）構造のまま構築します。
  - Maya の `blendShape` ノードにおける内部プラグ `inputTarget[0].inputTargetGroup[index].inputTargetItem[6000]` を直接探索します。
  - `MFnPointArrayData` および `MFnComponentListData` を通じて差分座標とコンポーネント情報をプラグへ直接設定します。
  - これにより、中間メッシュの複製やコマンド経由の頂点移動を一切行わずに数十〜百数十種類のモーフターゲットを瞬時に登録します。

- **スキニングウェイトの一括適用 (`mmdFastApplyPmxSkinWeights`)**：
  - BDEF1、BDEF2、BDEF4、SDEF、QDEF の各頂点ブレンド比率を解析します。
  - 頂点ごとのウェイト合計値が 0 や非数値（NaN）となる破損データに対しては、第 1 ボーンへの自動補正を行います。
  - ウェイト値の合計が 1.0 になるよう正規化を実施します。
  - `num_vertices * num_influences` のフラットな `MDoubleArray` を C++ メモリ上で構築し、`MFnSkinCluster::setWeights` により一括設定します。

---

### VMD 高速モーションインポート (`mmd_fast_vmd_cmd`)

- **バイナリ解析と整列 (`VmdBinaryCache`)**：
  - VMD ヘッダー（30 バイト）、ボーンレコード（111 バイト/個）、モーフレコード（23 バイト/個）、カメラレコード（61 バイト/個）をメモリバッファから高速パースします。
  - ボーン名・モーフ名の Shift-JIS 固定長バイト列を UTF-8 に変換してトラックごとに分類します。
  - 同一フレームに複数のキーが存在する場合は、MMD 本家の仕様に合わせて後勝ちで重複を統合します。

- **マルチスレッド並列評価 (`evaluateBoneTrackRange`)**：
  - 各ボーンのキーフレーム処理は独立して実行可能なため、CPU コア数に応じて均等に分割したワーカースレッド（`std::thread`）で並行実行します。
  - クォータニオン回転変換：MMD 左手系から Maya 右手系への変換として `(-qx, -qy, qz, qw)` を適用します。
  - ジョイント特性の相殺：各ジョイント固有の `jointOrient` および `rotateAxis` を数学的に相殺するローカル回転を算出します。
    $$\text{LocalRot} = \text{inv}(\text{jointOrient}) \times Q_{\text{maya}} \times \text{inv}(\text{rotateAxis})$$
  - オイラー角変換と最短連続角維持：指定された `rotateOrder` に基づきオイラー角へ変換し、前フレームの角度との差分が最小となる最短連続角（`closestSolution`）を選択して 180 度反転（フリップ現象）を防止します。
  - MMD ベジェ接線の算出：各キーフレーム区間のベジェパラメータ $(X_1, Y_1, X_2, Y_2)$ から出接線・入接線の角度（度数）と重み（ウェイト）を計算します。

- **アニメーションカーブへの一括注入**：
  - メインスレッドにおいて、計算済みの時間配列（`MTimeArray`）および値配列（`MDoubleArray`）を `MFnAnimCurve::addKeys` により高速注入します。
  - 回転アトリビュートには `kAnimCurveTA`、移動アトリビュートには `kAnimCurveTL`、表情モーフには `kAnimCurveTU` を使用します。
  - 重み付き接線（Weighted Tangents）を有効化し、`MFnAnimCurve::setTangent` を用いて MMD 特有の加減速曲線を忠実に再現します。

- **カメラのベジェサンプリング展開 (`mmdFastImportVmdCamera`)**：
  - MMD のカメラモーションは補間曲線が区間ごとに独立して定義されており、Maya 標準のスプライン補間では軌道に乖離が生じます。
  - 本プラグインではキーフレーム間を 2 次元ベジェ曲線の反復計算（二分法 32 回）により高精度にサンプリング展開します。
  - 注視点ロケータ（移動・回転）、カメラトランスフォーム（距離）、カメラシェイプ（画角からの焦点距離換算）へ一括注入します。

---

### 物理ベイク統合 (`mmd_fast_baker_cmd`)

- 旧 `mmd_motion_plugin` の `mmdFastBakeBone` コマンドを内部実装として移植しました。
- Bullet や XPBD などの物理シミュレーションによってフレームごとに算出されたジョイントのワールド姿勢配列を受け取り、Maya の `AnimCurve` へネイティブ速度で一括書き込みを行います。

---

## ディレクトリ構成

```
mmd_tools_for_maya/
├── mmd_fast_plugin/
│   ├── CMakeLists.txt            # CMake ビルド定義ファイル
│   ├── include/
│   │   ├── mmd_fast_baker_cmd.h  # 物理ベイクコマンド定義
│   │   ├── mmd_fast_pmx_cmd.h    # PMX 高速処理コマンド群定義
│   │   ├── mmd_fast_vmd_cmd.h    # VMD 高速処理コマンド群定義
│   │   ├── pmx_binary_parser.h   # PMX バイナリパーサー・キャッシュ定義
│   │   └── vmd_binary_parser.h   # VMD バイナリパーサー・キャッシュ定義
│   ├── src/
│   │   ├── plugin_main.cpp       # プラグインエントリーポイント (コマンド登録・解除)
│   │   ├── mmd_fast_baker_cmd.cpp
│   │   ├── mmd_fast_pmx_cmd.cpp
│   │   ├── mmd_fast_vmd_cmd.cpp
│   │   ├── pmx_binary_parser.cpp
│   │   └── vmd_binary_parser.cpp
│   └── bin/
│       ├── mmd_fast.mll          # 標準配置バイナリ (Maya 2025 版)
│       ├── 2024/mmd_fast.mll     # Maya 2024 用バイナリ
│       ├── 2025/mmd_fast.mll     # Maya 2025 用バイナリ
│       ├── 2026/mmd_fast.mll     # Maya 2026 用バイナリ
│       └── 2027/mmd_fast.mll     # Maya 2027 用バイナリ
├── converters/
│   ├── pmxpaimaya.py             # PMX インポート Python 側連携 (C++ 呼び出し & フォールバック)
│   └── vmdpaimaya.py             # VMD インポート Python 側連携 (C++ 呼び出し & フォールバック)
└── ui/
    └── tab_plugin.py             # プラグイン管理 UI (状態監視 & リロード)
```

---

## ビルド方法

### 前提環境
- Microsoft Visual Studio 2022 (MSVC v143 以降)
- CMake 3.13 以上
- Autodesk Maya Devkit (2024, 2025, 2026, 2027)

### ビルド手順の例 (PowerShell)

```powershell
# Maya 2025 向けビルド例
$devkit = "C:/Autodesk_devkit/devkitBase_2025"
$srcDir = "C:/Users/.../Documents/maya/plug-ins/mmd_tools_for_maya/mmd_fast_plugin"
$buildDir = "$srcDir/build_2025"

cmake -S $srcDir -B $buildDir -DDEVKIT_LOCATION="$devkit"
cmake --build $buildDir --config Release

# 生成された mmd_fast.mll を bin ディレクトリへ配置
Copy-Item "$buildDir/Release/mmd_fast.mll" "$srcDir/bin/2025/mmd_fast.mll"
```

---

## 性能検証データ

| 処理項目 | テストデータ規模 | Python 処理時間 | C++ (mmd_fast.mll) 処理時間 | 高速化倍率 |
| :--- | :--- | :--- | :--- | :--- |
| PMX モデルインポート | 21,809 頂点 / 35,237 面 / 274 ボーン / 120 モーフ | 約 14.5 秒 | **約 2.5 秒** | **約 5.8 倍** |
| VMD ボーン・モーフ | 7,660 フレーム / 71 ボーン / 31,144 キー | 約 28.0 秒 | **約 1.9 秒** | **約 14.7 倍** |
| VMD カメラ展開 | 125 キー (7,671 フレーム・61,368 キー展開) | 約 3.2 秒 | **約 0.04 秒 (37 ms)** | **約 80.0 倍** |

