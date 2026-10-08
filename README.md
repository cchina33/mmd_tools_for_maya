# MMD Tools for Maya (v1.0.0 Beta)

Autodesk Maya 上で MMD（PMX / PMD / DirectX .x）形式のモデルやアクセサリのインポート・エクスポート、VMDモーション・カメラ・音声のインポート、HumanIKリグ定義、および物理演算ベイクを行うための Maya 統合拡張プラグインです。

> **[NOTE] ベータ版について**  
> 本バージョン（**v1.0.0 Beta**）は、機能実装を完了し実運用検証を行っているベータ版です。モデルのインポート、モーション適用、物理演算ベイク等の一連のワークフローが動作確認されています。フィードバックや不具合報告は大歓迎です。

- **制作者 (Author)**: Hina33
- **ライセンス**: MIT License（※一部モジュールに個別ライセンスあり。詳細は後述の「ライセンスについて」を参照）

---

## 主な特徴

- **完全オリジナル入出力エンジン (`mmd_core`) 搭載**:
  - 外部ライブラリ（`blender_mmd_tools` 等）に依存せず、純粋な Python 標準ライブラリのみでゼロから構築された高速・堅牢なパーサー＆ライター。
  - **PMX 2.0 / 2.1**: 頂点、BDEF/SDEF/QDEFウェイト、面、材質、テクスチャ、ボーン、モーフ、剛体、ジョイントの入出力に対応。
  - **PMD (MMD旧形式)**: ボーン、IK（インバースキネマティクス）、モーフ、面巻き順の反転補正に対応。
  - **DirectX .x**: フリーフォーマット字句解析（トークナイザー）により、改行・コメント・多様な区切り文字を含むメッシュやアクセサリを安定パース。
- **デュアル物理演算エンジン（本家 Bullet ＆ 自作 XPBD）**:
  - **Bullet 物理ベイク (MMD本家仕様)**: Bullet Physics 2.83.7 コアを直接 C++ 単一 DLL（`mmd_bullet.dll`）に組み込み、本家 MikuMikuDance 特有の「柔らかく綺麗なしなやかさ」を Maya 上で完全再現。
  - **XPBD 物理ベイク (自作C++エンジン)**: 拡張位置ベース物理（XPBD）による高剛性・低ジッターな高速シミュレーション。
  - **物理キーフレーム管理**: ワンクリックでのモデル再吸着や物理キーフレームの完全クリアに対応。
- **VMD モーション / カメラ / 音声インポート**:
  - 高精度な 4次ベジェ補間曲線ソルバー（MMD $\leftrightarrow$ Maya 座標系・回転オーダー変換完全対応）。
  - IK / ボーン追従の動的フレーム同期。カメラ・照明・WAV音声の一括インポート対応。
- **HumanIK キャラクタ定義 & コントロールリグ自動生成**:
  - PMXボーン構造を自動解析し、Maya 標準の HumanIK キャラクタ定義とリグをワンクリックで構築。
- **大容量・中国語モデル対応 & 安全なノード名変換**:
  - 簡体字・未知文字・特殊記号を含むモデルでも、名前の衝突や Maya の命名制限エラーを自動回避するセーフノードネーミング機構を搭載。
- **Maya 2025 最適化モダン UI**:
  - PySide6 / PySide2 両対応。単一の統合タブウィンドウで直感的な操作感を提供。

---

## 動作要件

- **Autodesk Maya**: 2022 / 2023 / 2024 / 2025 以降 (Python 3 環境)
  - **Maya 2025 動作確認済み**
- **OS**: Windows (x64)

---

## インストール手順

### プラグインマネージャーから直接ロード（推奨）

1. 本リポジトリの `mmd_tools_for_maya` フォルダを、Maya のプラグインフォルダに配置します：
   - 例: `C:\Users\<ユーザー名>\Documents\maya\2025\plug-ins\mmd_tools_for_maya`
2. 同フォルダ直下の `mmd_tools_for_maya_plugin.py` を以下の位置に配置します：
   - 例: `C:\Users\<ユーザー名>\Documents\maya\2025\plug-ins\mmd_tools_for_maya_plugin.py`
3. Maya を起動し、**ウィンドウ (Windows) > 設定/プリファレンス (Settings/Preferences) > プラグイン マネージャ (Plug-in Manager)** を開きます。
4. プラグイン一覧に表示された **`mmd_tools_for_maya_plugin.py`** の **ロード (Loaded)** および **自動ロード (Auto load)** にチェックを入れます。
5. Maya メインメニューバーに **[MMD]** が追加され、**MMD to Maya (GUI)** から起動できます。

---

## 技術仕様書 (Technical Specifications)

本プラグインの内部アーキテクチャや計算モデルについては、[technical_specifications/](file:///c:/Users/Naruse/Documents/maya/2025/plug-ins/mmd_tools_for_maya/technical_specifications/) フォルダ内に詳細な技術ドキュメントを用意しています。

| ドキュメント名 | 概要・対象機能 |
| :--- | :--- |
| [bullet_engine_specification.md](file:///c:/Users/Naruse/Documents/maya/2025/plug-ins/mmd_tools_for_maya/technical_specifications/bullet_engine_specification.md) | **Bullet Physics 2.83.7 エンジン仕様**: MMD本家物理再現、単一DLL組み込み、剛体・ジョイントパラメータ定義、衝突グループ(1〜16)・16bitマスク仕様、OpenMayaマトリクス逆算 |
| [physics_system_specification.md](file:///c:/Users/Naruse/Documents/maya/2025/plug-ins/mmd_tools_for_maya/technical_specifications/physics_system_specification.md) | **Maya物理システム統合仕様**: ビューポート可視化コライダーメッシュ生成、Kinematic/Dynamic追従階層、自動再吸着・置き去り解消機構 |
| [xpbd_engine_specification.md](file:///c:/Users/Naruse/Documents/maya/2025/plug-ins/mmd_tools_for_maya/technical_specifications/xpbd_engine_specification.md) | **自作XPBD物理エンジン仕様**: 拡張位置ベース物理（XPBD）による剛体・6DOFばね拘束ソルバー、サブステップ積分、衝突判定 |
| [model_import_specification.md](file:///c:/Users/Naruse/Documents/maya/2025/plug-ins/mmd_tools_for_maya/technical_specifications/model_import_specification.md) | **モデルインポート・エクスポート仕様**: PMX 2.0/2.1、PMD、DirectX .x、SDEFスキニング、マテリアル・テクスチャ変換 |
| [vmd_import_specification.md](file:///c:/Users/Naruse/Documents/maya/2025/plug-ins/mmd_tools_for_maya/technical_specifications/vmd_import_specification.md) | **VMDモーションインポート仕様**: ベジェ補間曲線計算、IKベイク、カメラ・照明・音声インポート、オイラー角最短補正 |
| [codebase_architecture_specification.md](file:///c:/Users/Naruse/Documents/maya/2025/plug-ins/mmd_tools_for_maya/technical_specifications/codebase_architecture_specification.md) | **コードベース全体アーキテクチャ**: モジュール構造、GUI・エンジン・パーサー分離原則、例外安全設計 |

---

## ライセンスについて (License & Modular Isolation)

本プロジェクトは、オープンソースの透明性と利用者の自由度を最大限に高めるため、**フォルダ単位での完全なライセンス分離設計（カプセル化）** を採用しています。

- **プラグイン本体**: **MIT License**
  - 入出力コア（`mmd_core/`）、自作XPBD物理エンジン（`cpp_engine/`）、GUI（`gui.py`）、各種ユーティリティ等はすべて MIT ライセンスです。
- **Bullet エンジンモジュール (`bullet_engine/`)**: **zlib License**
  - Bullet Physics Library（Erwin Coumans / Bullet 公式）のソースコードを含みます。

### 削除耐性と 100% MIT ライセンスへの復元
- 商用利用やライセンスポリシー等の理由で Bullet Physics を除外したい場合、**`bullet_engine/` フォルダを丸ごと削除するだけ** で、プロジェクト全体が自動的かつ完全に **100% 純粋な MIT License 単一構成** に戻ります。
- GUI は Bullet モジュールの存在を動的に検出し、フォルダが削除されていても一切エラーを出さず、自作 XPBD 物理エンジン側で全機能が通常通り動作し続けます。

---

## クレジット

- **Author**: Hina33
- **Bullet Physics Library**: Copyright (c) 2003-2015 Erwin Coumans (zlib License)
