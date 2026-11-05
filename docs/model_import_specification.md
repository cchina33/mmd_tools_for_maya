# MMDモデル (PMX / PMD / DirectX .x) インポート総合技術仕様書

> [!NOTE]
> 本詳細技術仕様書は、AI によって作成・整理されたドキュメントです。内容はソースコードおよび開発記録をもとに記述していますが、実際の動作と細部が異なる場合があります。

本ドキュメントは、「MMD Tools for Maya」における MMD モデルインポート機能の総合ポータルです。
各ファイル形式（PMX, PMD, DirectX .x）に応じた詳細な解析仕様および共通の Maya シーン構築アーキテクチャは、以下の各専門仕様書に分割・記載されています。目的に応じて各ドキュメントをご参照ください。

---

## 専門技術仕様書一覧

### 1. [pmx_model_import_specification.md](pmx_model_import_specification.md) (PMX 2.0 / 2.1 専用仕様)
現代の MMD 標準形式である PMX モデルの専用仕様書です。
- PMX バイナリフォーマット解析仕様（グローバル設定、頂点、面、材質、ボーン、モーフ、剛体、Joint）
- 堅牢化バイナリパーサー仕様（多重文字コード自動フォールバック、終端安全保護、頂点ウェイト・インデックス自動修復、不正モーフ除外）
- スキニング方式（BDEF1, BDEF2, BDEF4, SDEF, QDEF）の対応詳細
- モーフ高速直接書き込み仕様（Sparse Target Delta Direct Write）
- `mmdToonShader` 材質モーフ二重透過・受光遮断仕様

### 2. [pmd_model_import_specification.md](pmd_model_import_specification.md) (PMD 専用仕様)
MMD の旧標準形式である PMD モデルの専用仕様書です。
- PMD 旧規格バイナリ構造解析仕様（Shift_JIS、IKセクション、Toon、スフィア）
- 拡張セクション（剛体・Joint）の解析と保持仕様
- `converters/pmd2pmx.py` による PMD → PMX 2.0 自動変換エンジンと対話型変換プロンプト仕様

### 3. [x_model_import_specification.md](x_model_import_specification.md) (DirectX .x 専用仕様)
アクセサリやステージで使用される DirectX 形式の専用仕様書です。
- テキスト・バイナリ形式対応字句解析器（Tokenizer）仕様
- メッシュ、法線、テクスチャUV、マテリアルリスト抽出仕様
- アクセサリ追従アタッチ（`ui/accessory_dialog.py`）との連携

### 4. [pmx-pmd-x_specification.md](pmx-pmd-x_specification.md) (3形式共通シーン構築仕様)
3形式共通の Maya シーン構築パイプラインおよびアーキテクチャの解説書です。
- **`mmd_core`（構文解析層）と `converters`（シーン構築層）の連携フロー図解（Mermaid）**
- 各 Python モジュールの呼び出し順序と生成ノードの役割一覧
- 高速メッシュ生成アーキテクチャ（`MFnMesh.create`）
- スケルトン生成と安全名変換（`asset/jaka.py`）
- 足IKリグ自動構築（`setup_mmd_ik`）
- ワールド空間Toon・スフィア・二重透過シェーディングアーキテクチャ
- 本家MMDセルフシャドウ・地面影落ちアーキテクチャ
- ビュー変換設定（`Un-tone-mapped (sRGB)`）
