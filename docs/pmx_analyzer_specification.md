# PMX モデル解析・一括保存およびユーザー辞書登録仕様書

## 1. 概要
`pmx_analyzer` パッケージは、Maya に読み込まれた PMX モデルの内部データ構造（材質、ボーン、モーフ、剛体、Joint）を完全抽出し、JSON 形式で一括保存する解析機能、ならびに `jaka.py` に未登録のボーン名・漢字を検出してユーザーが GUI 上でローマ字を記入して即時登録・再チェックできる対話型辞書管理機能を提供します。

---

## 2. モジュール構成

```
pmx_analyzer/
├── __init__.py               # 公開 API のエクスポート
├── analyzer_core.py          # モデル構成要素の抽出・一括シリアライズ保存 & 未登録漢字抽出
└── user_dict_dialog.py       # 未登録ボーン名検出プロンプト & ローマ字入力登録 GUI & 再チェック
```

---

## 3. モデル構成要素の一括保存仕様 (`export_pmx_structure`)

PMX モデルファイル（`.pmx`）から以下の 5 大要素のパラメータを漏れなく抽出し、`<モデル名>_pmx_analysis.json` に構造化出力します。

### 出力 JSON スキーマ
1. **`model_info`**:
   - `name`, `name_e`: モデル和名・英名
   - `comment`, `comment_e`: モデルコメント
   - `vertex_count`, `face_count`, `texture_count`: 頂点数・面数・テクスチャ数
   - `file_path`: ソースファイル絶対パス
2. **`materials`**:
   - `index`, `name`, `name_e`
   - `diffuse`, `specular`, `ambient`, `edge_color`, `edge_size`
   - `texture`, `sphere_texture`, `sphere_texture_mode`
   - `toon_texture`, `is_shared_toon_texture`, `is_double_sided`, `vertex_count`
3. **`bones`**:
   - `index`, `name`, `name_e`, `location` (X, Y, Z)
   - `parent_index`, `transform_level`
   - `is_ik`, `visible`, `rotatable`, `translatable`
   - `has_additional_rotate`, `has_additional_location`, `additional_transform`
   - `ik_target`, `ik_loop`, `ik_limit_radian`, `ik_links` (リンク先ボーン、角度制限 min/max)
4. **`morphs`**:
   - `index`, `name`, `name_e`, `panel`, `type_index`, `offset_count`
5. **`rigid_bodies`**:
   - `index`, `name`, `name_e`, `bone_index`
   - `collision_group`, `collision_mask`
   - `shape_type` (球 / 箱 / カプセル), `shape_size`
   - `position`, `rotation`, `mass`, `linear_damping`, `angular_damping`, `restitution`, `friction`
   - `physics_mode` (ボーン追従 / 物理演算 / 物理+位置合わせ)
6. **`joints`**:
   - `index`, `name`, `name_e`, `joint_type`
   - `rigid_body_a`, `rigid_body_b`, `position`, `rotation`
   - `linear_limit_min`, `linear_limit_max`, `angular_limit_min`, `angular_limit_max`
   - `linear_spring`, `angular_spring`

---

## 4. 未登録漢字・ボーン名の検出アルゴリズム (`find_unregistered_kanji_in_bones`)

1. **辞書統合セットの構築**:
   - `jaka.py` の標準漢字辞書 (`MMD_KANJI_DICT`) と、ユーザー辞書 (`asset/user_dictionary.json` 内の `custom_name_translations`) の全登録語句を結合。
   - 語句の長さ（文字数）降順でソート（最長一致優先）。
2. **登録済み語句の除去**:
   - モデル内の各ボーン名を NFKC 正規化。
   - 登録済み語句に一致する部分をスペースに置換して除去。
3. **未登録漢字の抽出**:
   - CJK 統合漢字パターン（`[\u4e00-\u9fff\u3400-\u4dbf]`）を用いて、残存した漢字文字を抽出。
   - 漢字文字ごとに出現ボーン名の一覧を対応付けてリスト化。

---

## 5. ユーザー辞書登録 GUI および再チェック（サイドチェック）仕様

### 5-1. 確認プロンプト (`check_and_prompt_user_dict`)
- モデル内に未登録の漢字・ボーン名が検出された場合、以下の確認ダイアログを表示：
  > **「登録のないボーン名があります。ユーザー辞書に記録しますか？」**
- **「はい」**: 登録 GUI（`UserDictRegisterDialog`）を表示。
- **「いいえ」**: スルーして処理を継続。

### 5-2. 登録 GUI (`UserDictRegisterDialog`)
- **テーブルレイアウト**:
  - **列 1 (未登録漢字)**: 検出された漢字文字（太字・中央揃え・読み取り専用）。
  - **列 2 (ローマ字入力)**: 半角英数字のローマ字入力欄 (`QLineEdit`)。
  - **列 3 (検出されたボーン名)**: その漢字が含まれるボーン名の例。
- **保存および再チェック動作**:
  1. 「辞書に登録して再チェック」をクリック。
  2. 入力されたローマ字を `asset/user_dictionary.json` に永続化保存。
  3. メモリ上の `jaka.MMD_KANJI_DICT` に即時マージ。
  4. 自動的に未登録漢字の再スキャン（サイドチェック）を実行。
     - **未登録が 0 件になった場合**: 完了メッセージを表示して自動クローズ。
     - **未登録が残っている場合**: テーブルを更新して残りの漢字を表示し、追加登録を案内。
