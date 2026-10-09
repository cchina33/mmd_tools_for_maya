# Bullet Physics Engine for MMD Tools for Maya

MMD（MikuMikuDance）本家で採用されている **Bullet Physics 2.7x〜2.8x系（2.83.7）** の物理演算コア（LinearMath, BulletCollision, BulletDynamics）を直接組み込んだ専用物理エンジンモジュールです。

MMDモデルの剛体反発・摩擦係数およびジョイントの6自由度ばね拘束（`btGeneric6DofSpringConstraint`）に準拠し、MMD特有の「柔らかくしなやかな髪やスカートの揺れ」を忠実に再現します。

---

## ライセンス・分離独立アーキテクチャについて

- **Bullet Physics ライセンス**: [zlib license](LICENSE) (Erwin Coumans)
- **分離独立の保証**:
  - 本 `bullet_engine` ディレクトリは、プロジェクトの他モジュール（MIT License）からカプセル化・分離されています。
  - **この `bullet_engine` フォルダを丸ごと削除するだけで、プロジェクト全体は自動的に 100% 純粋な MIT License（自作XPBDエンジンのみ）として動作・運用可能です。**
  - Bullet が存在しない場合、GUI側は自動的にそれを検出し、「Bullet 物理ベイク」ボタンを安全に非活性化（無効化）します。エラーやクラッシュは一切発生せず、自作XPBDエンジンで全ての機能が動作し続けます。

---

## 構成ファイル一覧

- `bin/mmd_bullet.dll`: C++最適化ビルド済み単一DLL (Windows 64-bit)
- `src/`: Bullet 2.83.7 コアソースコードおよび MMD C-API (`mmd_bullet_bridge.cpp`)
- `include/mmd_bullet_bridge.h`: C言語互換エクスポート関数ヘッダー
- `build_bullet_dll.py`: Visual Studio (MSVC) による自動コンパイルスクリプト
- `bullet_wrapper.py`: Python `ctypes` バインディング
- `bullet_maya_bridge.py`: Maya アニメーションベイク実行エンジン
- `LICENSE`: Bullet Physics (zlib license) 条項
