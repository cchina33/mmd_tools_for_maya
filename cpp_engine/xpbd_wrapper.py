# -*- coding: utf-8 -*-
"""
MMD XPBD 物理演算エンジン ctypes ラッパーモジュール
外部依存ライブラリなしで mmd_xpbd.dll を読み込み、物理シミュレーションを制御します。
"""
import os
import sys
import ctypes

class XpbdEngineWrapper:
    """
    MMD XPBD物理エンジンのctypesインターフェースラッパークラス
    """
    def __init__(self, dll_path=None):
        if dll_path is None:
            # デフォルトのDLL格納パスを探索
            current_dir = os.path.dirname(os.path.abspath(__file__))
            dll_path = os.path.join(current_dir, "bin", "mmd_xpbd.dll")

        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"XPBD DLLが見つかりません: {dll_path}")

        # DLLロード
        self._dll = ctypes.CDLL(dll_path)
        self._setup_function_signatures()

        # エンジンインスタンス作成
        self._engine = self._dll.xpbd_create()
        if not self._engine:
            raise RuntimeError("XPBDエンジンのインスタンス生成に失敗しました。")

    def _setup_function_signatures(self):
        """
        DLL関数の引数型および戻り値型を定義
        """
        c_void_p = ctypes.c_void_p
        c_float = ctypes.c_float
        c_int = ctypes.c_int
        c_uint16 = ctypes.c_uint16
        c_float_p = ctypes.POINTER(ctypes.c_float)

        # xpbd_create
        self._dll.xpbd_create.restype = c_void_p
        self._dll.xpbd_create.argtypes = []

        # xpbd_destroy
        self._dll.xpbd_destroy.restype = None
        self._dll.xpbd_destroy.argtypes = [c_void_p]

        # xpbd_reset
        self._dll.xpbd_reset.restype = None
        self._dll.xpbd_reset.argtypes = [c_void_p]

        # xpbd_clear
        self._dll.xpbd_clear.restype = None
        self._dll.xpbd_clear.argtypes = [c_void_p]

        # xpbd_set_gravity
        self._dll.xpbd_set_gravity.restype = None
        self._dll.xpbd_set_gravity.argtypes = [c_void_p, c_float, c_float, c_float]

        # xpbd_add_rigidbody
        self._dll.xpbd_add_rigidbody.restype = c_int
        self._dll.xpbd_add_rigidbody.argtypes = [
            c_void_p,
            c_int, c_int, c_int,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float,
            c_float, c_float,
            c_float, c_float,
            c_uint16, c_uint16
        ]

        # xpbd_set_rigidbody_transform
        self._dll.xpbd_set_rigidbody_transform.restype = None
        self._dll.xpbd_set_rigidbody_transform.argtypes = [
            c_void_p, c_int,
            c_float, c_float, c_float,
            c_float, c_float, c_float, c_float
        ]

        # xpbd_add_joint
        self._dll.xpbd_add_joint.restype = c_int
        self._dll.xpbd_add_joint.argtypes = [
            c_void_p,
            c_int, c_int,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float
        ]

        # xpbd_step_simulation
        self._dll.xpbd_step_simulation.restype = None
        self._dll.xpbd_step_simulation.argtypes = [c_void_p, c_float, c_int]

        # xpbd_get_rigidbody_transform
        self._dll.xpbd_get_rigidbody_transform.restype = c_int
        self._dll.xpbd_get_rigidbody_transform.argtypes = [
            c_void_p, c_int, c_float_p, c_float_p
        ]

        # xpbd_get_rigidbody_count
        self._dll.xpbd_get_rigidbody_count.restype = c_int
        self._dll.xpbd_get_rigidbody_count.argtypes = [c_void_p]

        # xpbd_get_joint_count
        self._dll.xpbd_get_joint_count.restype = c_int
        self._dll.xpbd_get_joint_count.argtypes = [c_void_p]

        # xpbd_reset_velocities
        self._dll.xpbd_reset_velocities.restype = None
        self._dll.xpbd_reset_velocities.argtypes = [c_void_p]

        # xpbd_reset_constraints
        self._dll.xpbd_reset_constraints.restype = None
        self._dll.xpbd_reset_constraints.argtypes = [c_void_p]

        # xpbd_relax_penetration
        self._dll.xpbd_relax_penetration.restype = None
        self._dll.xpbd_relax_penetration.argtypes = [c_void_p, c_int, c_float]

    def close(self):
        """
        エンジンリソースの解放
        """
        if self._engine:
            self._dll.xpbd_destroy(self._engine)
            self._engine = None

    def __del__(self):
        self.close()

    def reset(self):
        """
        剛体とジョイントの状態を初期状態にリセット
        """
        if self._engine:
            self._dll.xpbd_reset(self._engine)

    def clear(self):
        """
        登録された剛体およびジョイントをすべてクリア
        """
        if self._engine:
            self._dll.xpbd_clear(self._engine)

    def set_gravity(self, gx, gy, gz):
        """
        重力ベクトルの設定
        """
        self._dll.xpbd_set_gravity(self._engine, float(gx), float(gy), float(gz))

    def add_rigidbody(
        self,
        bone_index=-1,
        shape_type=0,      # 0: Sphere, 1: Box, 2: Capsule
        physics_mode=0,    # 0: Kinematic, 1: Dynamic, 2: Aligned
        size=(1.0, 1.0, 1.0),
        position=(0.0, 0.0, 0.0),
        rotation_euler=(0.0, 0.0, 0.0),  # ラジアン
        mass=1.0,
        linear_damping=0.0,
        angular_damping=0.0,
        restitution=0.0,
        friction=0.5,
        group=0,
        collision_mask=0xFFFF
    ):
        """
        剛体の追加登録
        戻り値: 剛体のインデックス
        """
        idx = self._dll.xpbd_add_rigidbody(
            self._engine,
            int(bone_index),
            int(shape_type),
            int(physics_mode),
            float(size[0]), float(size[1]), float(size[2]),
            float(position[0]), float(position[1]), float(position[2]),
            float(rotation_euler[0]), float(rotation_euler[1]), float(rotation_euler[2]),
            float(mass),
            float(linear_damping), float(angular_damping),
            float(restitution), float(friction),
            int(group), int(collision_mask)
        )
        return idx

    def set_rigidbody_transform(self, index, position, quat):
        """
        Kinematic剛体などの姿勢を行列または位置・四元数で更新
        quat: (x, y, z, w)
        """
        self._dll.xpbd_set_rigidbody_transform(
            self._engine,
            int(index),
            float(position[0]), float(position[1]), float(position[2]),
            float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])
        )

    def add_joint(
        self,
        body_a,
        body_b,
        position=(0.0, 0.0, 0.0),
        rotation_euler=(0.0, 0.0, 0.0),  # ラジアン
        linear_limit_min=(0.0, 0.0, 0.0),
        linear_limit_max=(0.0, 0.0, 0.0),
        angular_limit_min=(0.0, 0.0, 0.0),
        angular_limit_max=(0.0, 0.0, 0.0),
        linear_spring=(0.0, 0.0, 0.0),
        angular_spring=(0.0, 0.0, 0.0)
    ):
        """
        6DOFスプリングジョイントの追加登録
        戻り値: ジョイントのインデックス
        """
        idx = self._dll.xpbd_add_joint(
            self._engine,
            int(body_a), int(body_b),
            float(position[0]), float(position[1]), float(position[2]),
            float(rotation_euler[0]), float(rotation_euler[1]), float(rotation_euler[2]),
            float(linear_limit_min[0]), float(linear_limit_min[1]), float(linear_limit_min[2]),
            float(linear_limit_max[0]), float(linear_limit_max[1]), float(linear_limit_max[2]),
            float(angular_limit_min[0]), float(angular_limit_min[1]), float(angular_limit_min[2]),
            float(angular_limit_max[0]), float(angular_limit_max[1]), float(angular_limit_max[2]),
            float(linear_spring[0]), float(linear_spring[1]), float(linear_spring[2]),
            float(angular_spring[0]), float(angular_spring[1]), float(angular_spring[2])
        )
        return idx

    def step_simulation(self, dt=1.0 / 60.0, substeps=10):
        """
        物理シミュレーションを1ステップ進行
        """
        self._dll.xpbd_step_simulation(self._engine, float(dt), int(substeps))

    def get_rigidbody_transform(self, index):
        """
        剛体の現在位置と回転四元数を取得
        戻り値: ((x, y, z), (qx, qy, qz, qw))
        """
        pos = (ctypes.c_float * 3)()
        quat = (ctypes.c_float * 4)()

        ok = self._dll.xpbd_get_rigidbody_transform(self._engine, int(index), pos, quat)
        if not ok:
            return None

        return (
            (pos[0], pos[1], pos[2]),
            (quat[0], quat[1], quat[2], quat[3])
        )

    def get_rigidbody_count(self):
        """
        登録された剛体数を取得
        """
        return self._dll.xpbd_get_rigidbody_count(self._engine)

    def get_joint_count(self):
        """
        登録されたジョイント数を取得
        """
        return self._dll.xpbd_get_joint_count(self._engine)

    def reset_velocities(self):
        """
        全剛体の線形速度・角速度をゼロクリアし、現在姿勢に同期
        """
        if self._engine:
            self._dll.xpbd_reset_velocities(self._engine)

    def reset_constraints(self):
        """
        全ジョイントの累積ラグランジュ乗数をリセット
        """
        if self._engine:
            self._dll.xpbd_reset_constraints(self._engine)

    def relax_penetration(self, steps=25, damping=0.99):
        """
        初期姿勢でのめり込み解消ウォームアップ (Pre-roll Relaxation)
        重力なし・高減衰下で接触反発のみを解き、初速0のまま太もも外側へ自然に押し出す
        """
        if self._engine:
            self._dll.xpbd_relax_penetration(self._engine, int(steps), float(damping))

