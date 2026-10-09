# -*- coding: utf-8 -*-
"""
MMD Bullet 物理演算エンジン ctypes ラッパーモジュール
外部依存ライブラリなしで mmd_bullet.dll を読み込み、本家MMD仕様のBullet物理シミュレーションを制御します。
"""

import os
import sys
import ctypes

class BulletEngineWrapper:
    """
    MMD Bullet物理エンジンの ctypes インターフェースラッパークラス
    """
    def __init__(self, dll_path=None):
        if dll_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            dll_path = os.path.join(current_dir, "bin", "mmd_bullet.dll")

        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"Bullet DLLが見つかりません: {dll_path}")

        self._dll = ctypes.CDLL(dll_path)
        self._setup_function_signatures()

        self._engine = self._dll.bullet_create()
        if not self._engine:
            raise RuntimeError("Bulletエンジンのインスタンス生成に失敗しました。")

    def _setup_function_signatures(self):
        c_void_p = ctypes.c_void_p
        c_float = ctypes.c_float
        c_int = ctypes.c_int
        c_uint16 = ctypes.c_uint16
        c_float_p = ctypes.POINTER(ctypes.c_float)

        self._dll.bullet_create.restype = c_void_p
        self._dll.bullet_create.argtypes = []

        self._dll.bullet_destroy.restype = None
        self._dll.bullet_destroy.argtypes = [c_void_p]

        self._dll.bullet_reset.restype = None
        self._dll.bullet_reset.argtypes = [c_void_p]

        self._dll.bullet_clear.restype = None
        self._dll.bullet_clear.argtypes = [c_void_p]

        self._dll.bullet_set_gravity.restype = None
        self._dll.bullet_set_gravity.argtypes = [c_void_p, c_float, c_float, c_float]

        self._dll.bullet_add_rigidbody.restype = c_int
        self._dll.bullet_add_rigidbody.argtypes = [
            c_void_p, c_int, c_int, c_int,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float,
            c_float, c_float,
            c_float, c_float,
            c_uint16, c_uint16
        ]

        self._dll.bullet_set_rigidbody_transform.restype = None
        self._dll.bullet_set_rigidbody_transform.argtypes = [
            c_void_p, c_int,
            c_float, c_float, c_float,
            c_float, c_float, c_float
        ]

        self._dll.bullet_set_target_transform.restype = None
        self._dll.bullet_set_target_transform.argtypes = [
            c_void_p, c_int,
            c_float, c_float, c_float,
            c_float, c_float, c_float
        ]

        self._dll.bullet_get_rigidbody_transform.restype = None
        self._dll.bullet_get_rigidbody_transform.argtypes = [
            c_void_p, c_int,
            c_float_p, c_float_p, c_float_p,
            c_float_p, c_float_p, c_float_p, c_float_p
        ]

        self._dll.bullet_add_joint.restype = c_int
        self._dll.bullet_add_joint.argtypes = [
            c_void_p, c_int, c_int,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float,
            c_float, c_float, c_float
        ]

        self._dll.bullet_step_simulation.restype = None
        self._dll.bullet_step_simulation.argtypes = [
            c_void_p, c_float, c_int, c_float
        ]

        self._dll.bullet_reset_velocities.restype = None
        self._dll.bullet_reset_velocities.argtypes = [c_void_p]

        self._dll.bullet_reset_constraints.restype = None
        self._dll.bullet_reset_constraints.argtypes = [c_void_p]

        self._dll.bullet_relax_penetration.restype = None
        self._dll.bullet_relax_penetration.argtypes = [c_void_p, c_int, c_float]

    def __del__(self):
        if hasattr(self, '_engine') and self._engine and hasattr(self, '_dll'):
            try:
                self._dll.bullet_destroy(self._engine)
            except Exception:
                pass
            self._engine = None

    def reset(self):
        self._dll.bullet_reset(self._engine)

    def clear(self):
        self._dll.bullet_clear(self._engine)

    def set_gravity(self, gx, gy, gz):
        self._dll.bullet_set_gravity(self._engine, float(gx), float(gy), float(gz))

    def add_rigidbody(self, bone_idx, shape_type, physics_mode,
                       size, pos, rot_euler, mass,
                       linear_damping=0.0, angular_damping=0.0,
                       restitution=0.0, friction=0.5,
                       group=0, collision_mask=0xFFFF):
        return self._dll.bullet_add_rigidbody(
            self._engine,
            int(bone_idx), int(shape_type), int(physics_mode),
            float(size[0]), float(size[1]), float(size[2]),
            float(pos[0]), float(pos[1]), float(pos[2]),
            float(rot_euler[0]), float(rot_euler[1]), float(rot_euler[2]),
            float(mass),
            float(linear_damping), float(angular_damping),
            float(restitution), float(friction),
            int(group), int(collision_mask)
        )

    def set_rigidbody_transform(self, rb_idx, pos, rot_euler):
        self._dll.bullet_set_rigidbody_transform(
            self._engine, int(rb_idx),
            float(pos[0]), float(pos[1]), float(pos[2]),
            float(rot_euler[0]), float(rot_euler[1]), float(rot_euler[2])
        )

    def set_target_transform(self, rb_idx, pos, rot_euler):
        self._dll.bullet_set_target_transform(
            self._engine, int(rb_idx),
            float(pos[0]), float(pos[1]), float(pos[2]),
            float(rot_euler[0]), float(rot_euler[1]), float(rot_euler[2])
        )

    def get_rigidbody_transform(self, rb_idx):
        px = ctypes.c_float()
        py = ctypes.c_float()
        pz = ctypes.c_float()
        rx = ctypes.c_float()
        ry = ctypes.c_float()
        rz = ctypes.c_float()
        rw = ctypes.c_float()

        self._dll.bullet_get_rigidbody_transform(
            self._engine, int(rb_idx),
            ctypes.byref(px), ctypes.byref(py), ctypes.byref(pz),
            ctypes.byref(rx), ctypes.byref(ry), ctypes.byref(rz), ctypes.byref(rw)
        )
        return (px.value, py.value, pz.value), (rx.value, ry.value, rz.value, rw.value)

    def add_joint(self, rb_a_idx, rb_b_idx, pos, rot_euler,
                  pos_min, pos_max, rot_min, rot_max,
                  spring_pos, spring_rot):
        return self._dll.bullet_add_joint(
            self._engine, int(rb_a_idx), int(rb_b_idx),
            float(pos[0]), float(pos[1]), float(pos[2]),
            float(rot_euler[0]), float(rot_euler[1]), float(rot_euler[2]),
            float(pos_min[0]), float(pos_min[1]), float(pos_min[2]),
            float(pos_max[0]), float(pos_max[1]), float(pos_max[2]),
            float(rot_min[0]), float(rot_min[1]), float(rot_min[2]),
            float(rot_max[0]), float(rot_max[1]), float(rot_max[2]),
            float(spring_pos[0]), float(spring_pos[1]), float(spring_pos[2]),
            float(spring_rot[0]), float(spring_rot[1]), float(spring_rot[2])
        )

    def step_simulation(self, dt=1.0/30.0, max_sub_steps=10, fixed_time_step=1.0/180.0):
        self._dll.bullet_step_simulation(
            self._engine, float(dt), int(max_sub_steps), float(fixed_time_step)
        )

    def reset_velocities(self):
        """全剛体の線形速度・角速度および蓄積された力をゼロクリア"""
        self._dll.bullet_reset_velocities(self._engine)

    def reset_constraints(self):
        """全ジョイントの平衡点・内部バッファをリセット"""
        self._dll.bullet_reset_constraints(self._engine)

    def relax_penetration(self, steps=25, damping=0.99):
        """
        初期姿勢でのめり込み解消ウォームアップ (Pre-roll Relaxation)
        外力なし・高ダンピング下で接触反発のみを解き、初速0のまま太もも外側へ自然に押し出す
        """
        self._dll.bullet_relax_penetration(self._engine, int(steps), float(damping))

