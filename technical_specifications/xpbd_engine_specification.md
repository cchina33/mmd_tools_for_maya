# C++ XPBD 物理演算エンジン技術仕様書

本ドキュメントは、「MMD Tools for Maya」に搭載されている完全オリジナルの C++ XPBD (Extended Position Based Dynamics) 物理演算エンジン（`mmd_xpbd.dll`）の数理モデル、拘束解決アルゴリズム、剛体間コリジョン、および Python（`ctypes`）ブリッジインターフェースに至る詳細な技術仕様を定めたものです。

---

## 1. XPBD (Extended Position Based Dynamics) 数理モデル

従来の PBD (Position Based Dynamics) が時間刻み幅 $\Delta t$ やイテレーション回数に依存して剛性（Stiffness）が変動する欠点を持っていたのに対し、XPBD は連続体力学における弾性エネルギーとコンプライアンス（柔軟度 $\alpha$）を導入することで、時間刻みやサブステップ数に依存しない厳密で安定した物理挙動を実現します。

### 1-1. コンプライアンスとラグランジュ乗数の更新
拘束条件を $C(x) = 0$、剛体の逆質量を $w_i = 1 / m_i$、逆慣性テンソルを $I_i^{-1}$ とするとき、拘束補正量 $\Delta \lambda$ は以下の式で計算されます：

$$\Delta \lambda = \frac{-C(x) - \tilde{\alpha} \lambda}{\nabla C \cdot W \nabla C^T + \tilde{\alpha}}$$

ここで：
- $\tilde{\alpha} = \frac{\alpha}{\Delta t^2}$ （時間刻みスケーリングされたコンプライアンス）
- $W = \sum w_i$ （有効逆質量）
- 位置補正量: $\Delta x_i = w_i \nabla C_i^T \Delta \lambda$

### 1-2. サブステップ時間積分 (`subStep`)
各フレーム（例: 1/30秒）を複数のサブステップ（例: 10〜20分割, $\Delta t \approx 0.0016$〜$0.0033$秒）に細分化して積分を実行します。

- **予測ステップ**:
  - 線形速度の更新: $v \leftarrow v + \Delta t \cdot g$ （重力加算、ただし Aligned 剛体は除外）
  - 角速度の更新: $\omega \leftarrow \omega + \Delta t \cdot \tau_{ext}$
  - 予測位置の計算: $x^* \leftarrow x + \Delta t \cdot v$
  - 予測回転の計算: $q^* \leftarrow q + \frac{\Delta t}{2} \omega q$
- **拘束解決ステップ**:
  - ジョイント拘束（位置拘束・角度拘束）の解決（`solveJoint`）
  - 剛体間接触コリジョン拘束の解決（`solveCollisions`）
- **速度更新ステップ**:
  - $v \leftarrow (x^* - x) / \Delta t$
  - $\omega \leftarrow 2 \cdot \text{RotDiff}(q, q^*) / \Delta t$
  - 位置と回転の確定: $x \leftarrow x^*$、 $q \leftarrow q^*$

---

## 2. 剛体タイプの定義と挙動仕様

MMD の剛体タイプに応じた専用の処理フローを実装しています。

| タイプ | 名称 | 挙動仕様 | 重力加算 | 拘束解決 |
| :--- | :--- | :--- | :---: | :---: |
| **0** | **Kinematic (ボーン追従)** | アニメーションボーンのワールド位置・回転に完全固定 | なし | 相手剛体のみを押し出す（無限大質量） |
| **1** | **Dynamic (物理演算)** | 外力、ジョイントばね、コリジョン反力に従って自由に運動 | あり | 双方向の運動量・位置補正を適用 |
| **2** | **Aligned (位置合わせ追従)** | 位置は親ボーンのワールド位置に完全拘束、回転のみ物理演算 | **なし** | 位置は動かさず、回転のみ拘束解決 |

### 2-1. Aligned 剛体の重力遮断と位置固定
スカートや髪の根元に多用される Aligned 剛体（タイプ2）において、重力加速度が加算されると目標位置からの垂れ下がりやジョイントの引きちぎれが発生します。
本エンジンでは、`subStep` 内で Aligned 剛体への重力加算を完全に遮断し、線形速度をゼロに保持した上で、親ボーンの目標位置へ厳密にクランプ固定します。

---

## 3. Joint（MMD 6自由度拘束）解決仕様 (`solveJoint`)

MMD の Joint は、剛体Aと剛体Bの間に位置制限（下限/上限）および回転制限（下限/上限）、ばね復元力を与える 6DOF (Six Degrees of Freedom) 拘束です。

### 3-1. 位置拘束（ハードリミット拘束）
- 剛体Aから見た剛体Bの相対位置ベクトル $p_{rel} = R_A^T (x_B - x_A)$ を算出。
- 設定された移動制限範囲 $[p_{min}, p_{max}]$ を超過した場合、限界値へ強制クランプ。
- 超過変位ベクトル $\Delta p$ を剛体Aおよび剛体Bの逆質量比に応じて分配し、位置を即座に補正。

### 3-2. 角度拘束（オイラー角クランプ & ハードリミット復元）
- 剛体Aから見た剛体Bの相対回転クォータニオン $q_{rel} = q_A^{-1} q_B$ を算出。
- $q_{rel}$ をオイラー角 $(\theta_x, \theta_y, \theta_z)$ に分解。
- 角度制限範囲 $[\theta_{min}, \theta_{max}]$ を超過した場合、限界角へクランプ。
- クランプされた目標回転クォータニオンとの差分から復元トルクおよび角変位を計算し、回転姿勢を補正。

---

## 4. 剛体間コリジョン（接触判定・押し出し）仕様

### 4-1. 衝突判定プリミティブ
- **球 vs 球 (Sphere - Sphere)**:
  - 中心間距離 $d = \|x_A - x_B\|$ を評価。
  - 貫通深度: $\delta = (r_A + r_B) - d > 0$ の場合、接触法線方向へ相互押し出し。
- **球 vs 箱 (Sphere - Box)**:
  - 球の中心を箱のローカル座標系へ変換。
  - 箱の境界ボックス（AABB）上の最近接点（Closest Point）をクランプ計算。
  - 最近接点と球中心の距離が球半径 $r$ 未満の場合に押し出し補正。
- **球 vs カプセル (Sphere - Capsule)**:
  - カプセルの線分軸に対する球中心の射影点を求め、最近接点を算出。
  - 最近接点と球中心の距離が $(r_{sphere} + r_{capsule})$ 未満の場合に押し出し補正。

### 4-2. 衝突グループ・非衝突マスクフィルタリング
MMD の衝突グループ（0〜15）および非衝突グループマスク（16ビットビット列）をビット演算で評価し、無効な組み合わせの接触判定を完全にスキップして高速化します。

---

## 5. C++ DLL / Python ブリッジインターフェース仕様

エンジンは純粋な C言語互換インターフェース（`extern "C"`）として DLL（`mmd_xpbd.dll`）からエクスポートされ、Python の標準モジュール `ctypes`（`xpbd_wrapper.py`）経由で直接呼び出されます。

### 5-1. 主要エクスポート関数
- `void init_physics()`:
  - 物理シミュレーション空間の初期化および全剛体・ジョイントバッファのクリア。
- `int add_rigidbody(const RigidBodyDesc* desc)`:
  - 剛体パラメータ（質量、形状、寸法、初期位置、初期回転、減衰、摩擦、タイプ）を登録。
- `int add_joint(const JointDesc* desc)`:
  - 剛体A、剛体B、相対位置・回転制限、ばね定数を登録。
- `void step_simulation(float dt, int sub_steps)`:
  - 時間幅 `dt` およびサブステップ数 `sub_steps` でシミュレーションを1フレーム進行。
- `void update_kinematic_transform(int index, float px, float py, float pz, float qx, float qy, float qz, float qw)`:
  - Kinematic剛体（タイプ0）およびAligned剛体（タイプ2）の最新ボーン姿勢をエンジンへ転送。
- `void get_rigidbody_transform(int index, float* out_pos, float* out_quat)`:
  - 指定剛体の最新ワールド位置（x, y, z）および回転クォータニオン（qx, qy, qz, qw）を取得。

### 5-2. ビルドおよびコンパイル仕様 (`build_dll.py`)
- Windows 環境において、Visual Studio C++ コンパイラ（`cl.exe`）または MinGW（`g++`）を自動検出し、最適化フラグ（`/O2` または `-O3`）を適用して `bin/mmd_xpbd.dll` を生成。
