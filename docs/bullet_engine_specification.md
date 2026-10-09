# Bullet Physics 物理演算エンジン技術仕様書 (MMD本家仕様)

本ドキュメントは、「MMD Tools for Maya」に搭載された MMD 本家（MikuMikuDance）互換の **Bullet Physics 2.83.7** 物理演算エンジンモジュール（`bullet_engine/`）のアーキテクチャ、ライセンス分離設計、剛体・ジョイントの完全パラメータ仕様、拘束解決モデル、および Maya との連携仕様を定めたものです。

---

## 1. 導入の目的と MMD 特有のしなやかさの再現

MMD（MikuMikuDance）は、樋口優氏により Bullet Physics Library（2.75〜2.77系）を物理コアとして採用して開発されました。
MMD のモデルデータ（剛体の反発・摩擦、ジョイントのばね定数・制限角度）は、Bullet の `btGeneric6DofSpringConstraint` および PGS (Projected Gauss-Seidel / Sequential Impulse) ソルバーの内部挙動に最適化してパラメータ調整されています。

本モジュールは、Bullet 2.8x系（2.83.7）のコアソースファイルを直接プロジェクト内に組み込み、単一DLL（`mmd_bullet.dll`）へコンパイルすることで、**MMD特有の「柔らかく綺麗なしなやかさ」を Maya 上で完全再現**します。

---

## 2. ライセンス完全分離（カプセル化）アーキテクチャ

オープンソースライセンスの明確な分離とユーザーの自由度を保証するため、以下の設計を採用しています。

- **ライセンス体系**:
  - `bullet_engine/` フォルダ配下: **zlib license** (Erwin Coumans / Bullet Physics 公式)
  - プロジェクト本体（入出力コア `mmd_core`、自作XPBDエンジン等）: **MIT License**
- **削除耐性（Zero-Dependency Fallback）**:
  - `bullet_engine/` フォルダを丸ごと削除するだけで、プロジェクト全体は自動的かつ完全に **MIT License 単一構成（自作XPBDエンジンのみ）** に戻ります。
  - GUI（`gui.py`）は起動時および表示時に `bullet_engine/bin/mmd_bullet.dll` の存在を動的に検出します。
  - フォルダやDLLが削除された場合でも、GUIの起動やモデルインポート・モーション適用等に一切エラーは発生せず、「Bullet 物理ベイク実行」ボタンのみが安全に無効化（グレーアウト）され、自作「XPBD 物理ベイク実行」で全機能が平常稼働し続けます。

---

## 3. 剛体（RigidBody）の完全パラメータ仕様 & マッピング

PMXモデルデータに定義された剛体パラメータと、Bullet Physics（`btRigidBody` / `btCollisionShape`）へのマッピング仕様です。

### 3-1. 形状パラメータ（Shape Types）
| PMX shape_type | 形状 | PMX size パラメータ | Bullet 衝突形状クラス | 備考 |
| :--- | :--- | :--- | :--- | :--- |
| `0` | 球 (Sphere) | `[radius, 0, 0]` | `btSphereShape(radius * scale)` | 半径 |
| `1` | 箱 (Box) | `[half_x, half_y, half_z]` | `btBoxShape(btVector3(half_x * scale, half_y * scale, half_z * scale))` | XYZハーフサイズ |
| `2` | カプセル (Capsule) | `[radius, height, 0]` | `btCapsuleShape(radius * scale, height * scale)` | Y軸沿いカプセル |

### 3-2. 物理プロパティ
- **質量 (`mass`)**:
  - タイプ 0 (Kinematic): 質量 `0.0f`（物理演算で動かない静的・アニメーション駆動体）。
  - タイプ 1 (Dynamic) / タイプ 2 (Aligned): PMXの `mass` 値をそのまま設定。
- **移動減衰 (`linear_damping`)**:
  - `btRigidBodyConstructionInfo::m_linearDamping` に設定（最低 `0.05` でクランプ）。
- **回転減衰 (`angular_damping`)**:
  - `btRigidBodyConstructionInfo::m_angularDamping` に設定（最低 `0.05` でクランプ）。
- **反発係数 (`restitution`)**:
  - `btRigidBody::setRestitution(restitution)` に設定（0.0 〜 1.0）。
- **摩擦係数 (`friction`)**:
  - `btRigidBody::setFriction(friction)` に設定。
- **アクティベーション状態**:
  - 静止による物理スリープを防ぐため、全剛体に `DISABLE_DEACTIVATION` を設定。

### 3-3. 衝突グループ (1〜16) と 衝突マスク (16bit) の完全仕様
PMXモデルでは、最大16個の衝突グループを定義可能です。

- **グループ番号の対応**:
  - PMXエディタ上の表示: **グループ 1 〜 16**（1始まり）
  - PMXバイナリ内の内部値: **`group` = 0 〜 15**（0始まり）
  - ビット表現: `groupBit = 1 << group`（`0x0001` 〜 `0x8000`）
- **衝突マスク (`collision_mask`) の仕様**:
  - 16bit符号なし整数（`uint16_t` / `ushort`、`0x0000` 〜 `0xFFFF`）。
  - **各ビット（ビット0〜15）は「衝突を許可する相手グループ」を表すフラグそのもの**です。
    - 例: ビット $k$ が `1` $\rightarrow$ グループ $k+1$（内部値 $k$）と衝突する。
    - 例: ビット $k$ が `0` $\rightarrow$ グループ $k+1$ とは衝突しない（すり抜ける）。
  - **重要**: PMXの内部バイナリデータはすでに「衝突許可ビット」となっているため、**ビット反転（`~`）を行わずにそのまま Bullet のブロードフェーズマスクへ渡します**。
- **Bullet への登録**:
  ```cpp
  short groupBit = static_cast<short>(1 << group);
  short maskBit = static_cast<short>(collisionMask);
  world->addRigidBody(body, groupBit, maskBit);
  ```

---

## 4. ジョイント（Joint / 6DOF Spring）の完全パラメータ仕様

PMXモデルのジョイントは、すべて 6自由度スプリング拘束（`btGeneric6DofSpringConstraint`）として解決されます。

### 4-1. 相対フレーム計算
- 剛体Aおよび剛体Bのバインド時ワールドトランスフォーム $T_A, T_B$ とジョイントのワールドトランスフォーム $T_J$ から、各剛体のローカル空間におけるトランスフォームを算出：
  $$F_A = T_A^{-1} \cdot T_J$$
  $$F_B = T_B^{-1} \cdot T_J$$
- コンストレイント生成時に第5引数を `true` に設定し、接続剛体ペア同士の直接衝突判定を無効化（`disableCollisionsBetweenLinkedBodies = true`）。

### 4-2. 制限角度・移動範囲 (Limits)
- **平行移動リミット**:
  - 下限: `[posMinX * scale, posMinY * scale, -posMaxZ * scale]`
  - 上限: `[posMaxX * scale, posMaxY * scale, -posMinZ * scale]`
  - `spring->setLinearLowerLimit()` / `setLinearUpperLimit()`
- **回転オイラー角リミット (ラジアン)**:
  - 下限: `[rotMinX, rotMinY, -rotMaxZ]`
  - 上限: `[rotMaxX, rotMaxY, -rotMinZ]`
  - `spring->setAngularLowerLimit()` / `setAngularUpperLimit()`

### 4-3. スプリングばね定数 (Stiffness) & 減衰 (Damping)
- 6自由度（0, 1, 2: 平行移動 XYZ / 3, 4, 5: 回転 XYZ）それぞれについて：
  - PMXの `linear_spring` / `angular_spring` が非ゼロの場合、`spring->enableSpring(i, true)` を有効化。
  - ばね定数: `spring->setStiffness(i, spring_val)`
  - 減衰定数: `spring->setDamping(i, 1.0f)`
- **平衡点の初期化**:
  - `spring->setEquilibriumPoint()` を呼び出し、拘束生成時の相対姿勢を安定平衡点として登録。

---

## 5. Maya 座標系変換・アニメーション連携仕様

### 5-1. 座標系変換規則 (MMD $\leftrightarrow$ Maya)
MMDとMayaはいずれも右手系（Y-up）ですが、Z軸の向き規則に対応するため以下の変換を適用します。
- 位置: $(X \times \text{scale}, Y \times \text{scale}, -Z \times \text{scale})$
- 回転オイラー角: $(\text{degX}, \text{degY}, -\text{degZ})$

### 5-2. Kinematic 剛体の追従と AABB 即時更新
- ボーンに対する剛体のバインドポーズでの相対ローカルオフセット $(P_{\text{offset}}, Q_{\text{offset}})$ を保持。
- 毎フレーム、ボーンの現在姿勢 $(P_{\text{bone}}, Q_{\text{bone}})$ に相対オフセットを乗算して剛体の目標ワールド姿勢を算出：
  $$P_{\text{target}} = P_{\text{bone}} + Q_{\text{bone}} \cdot P_{\text{offset}}$$
  $$Q_{\text{target}} = Q_{\text{bone}} \cdot Q_{\text{offset}}$$
- 目標姿勢を設定した直後に `world->updateSingleAabb(body)` を呼び出し、ブロードフェーズの衝突判定境界ボックスを即時更新（高速移動時のすり抜け・貫通を完全防止）。

### 5-3. 初期めり込み解消ウォームアップ (Pre-roll Relaxation) と ERP 調整
モーション開始フレーム（0F等）において太もも剛体とスカート剛体がめり込んでいる場合、初期フレームでの急激な反発インパルスによるゴム跳ね・振動・破綻を防止するため、以下の事前緩和機構を搭載しています。

- **ERP (Error Reduction Parameter) の抑制**:
  - `solverInfo.m_erp = 0.2f` および `solverInfo.m_erp2 = 0.2f` に設定し、拘束復元率をマイルドに抑えて跳ね返りを抑制。
- **Pre-roll Relaxation プロセス (`bullet_relax_penetration`)**:
  1. ワールド重力を一時的にゼロ $(0, 0, 0)$ に設定。
  2. 動的剛体のダンピング（空気抵抗）を一時的に極大（$0.99$）に設定。
  3. 太もも等のKinematic剛体をボーン姿勢に完全固定したまま、接触反発インパルスのみでスカート剛体が表面外側へ押し出されるシミュレーションを 25ステップ実行。
  4. 押し出し完了後、線形速度・角速度・内部力を完全にゼロクリア（`bullet_reset_velocities`）。
  5. スプリングコンストレイントの平衡点を最新の安定相対姿勢で再初期化（`bullet_reset_constraints`）。
  6. 重力とダンピングを元に戻してベイクを開始するため、初速ゼロ・無振動の滑らかな揺れ出しが保証されます。

### 5-4. OpenMaya マトリクス逆算によるキーフレーム書き込み
剛体の物理演算結果をボーンへ書き込む際、Maya特有のジョイント属性を考慮した厳密な逆算を行います。
1. **目標ワールド回転の逆算**:
   $$Q_{\text{target}} = Q_{\text{rb\_current}} \cdot Q_{\text{offset}}^{-1}$$
2. **親空間ローカル回転の算出**:
   $$M_{\text{local}} = M_{\text{target}} \cdot M_{\text{parent\_inclusive}}^{-1}$$
3. **jointOrient / rotateAxis の相殺**:
   $$Q_{\text{bone}} = Q_{\text{jointOrient}}^{-1} \cdot Q_{\text{local}} \cdot Q_{\text{rotateAxis}}^{-1}$$
4. **階層深度ソート (親から子へ)**:
   親ボーンの回転を確定させてから子ボーンの親空間行列を計算するため、動的剛体をMayaのDAG階層深度順にソートして処理。
5. **オイラー角連続性維持**:
   `closestSolution` を用いて最短連続回転角を維持し、ジンバルロックや180度反転フリップを完全防止。

---

## 6. クリーンアップと再吸着復元 (`clear_physics_keyframes`)

ベイク処理の終了時、またはユーザーによる「物理キーフレームをクリア」「剛体・Jointをモデルに再吸着」実行時：
- 動的剛体に対応する全ジョイントの移動・回転キーフレームをクリア。
- 可視化ノード（`MMD_XPBD_VISUALIZERS`）のキーフレームを削除し、モデルボーンへの追従コンストレイントを通常状態（Normal）へ完全復元。
