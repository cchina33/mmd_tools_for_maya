# -*- coding: utf-8 -*-
"""
XPBD物理エンジン単体テストスクリプト
"""
import os
import sys

# パス追加
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from xpbd_wrapper import XpbdEngineWrapper

def run_tests():
    print("=== XPBD Engine Python Wrapper Test ===")
    engine = XpbdEngineWrapper()
    print("[PASS] Engine created successfully.")

    # 重力設定
    engine.set_gravity(0.0, -9.8, 0.0)

    # 1. 自由落下テスト
    rb0 = engine.add_rigidbody(
        bone_index=0,
        shape_type=0, # Sphere
        physics_mode=1, # Dynamic
        size=(1.0, 1.0, 1.0),
        position=(0.0, 10.0, 0.0),
        mass=1.0
    )
    print(f"[PASS] Added dynamic body: idx={rb0}")

    initial_trans = engine.get_rigidbody_transform(rb0)
    print(f"Initial pos: {initial_trans[0]}")

    # 60フレーム (1秒分) シミュレーション
    for i in range(60):
        engine.step_simulation(dt=1.0/60.0, substeps=10)

    after_trans = engine.get_rigidbody_transform(rb0)
    print(f"After 1s falling pos: {after_trans[0]}")

    assert after_trans[0][1] < initial_trans[0][1], "Body should fall downwards."
    print("[PASS] Free fall test passed.")

    # 2. リセット & ジョイント拘束テスト
    engine.clear()
    assert engine.get_rigidbody_count() == 0

    # ルート剛体 (Kinematic: 静止)
    root_body = engine.add_rigidbody(
        bone_index=0,
        shape_type=0,
        physics_mode=0, # Kinematic
        position=(0.0, 10.0, 0.0),
        mass=0.0
    )

    # 子剛体 (Dynamic: 振り子)
    child_body = engine.add_rigidbody(
        bone_index=1,
        shape_type=0,
        physics_mode=1, # Dynamic
        position=(0.0, 8.0, 0.0),
        mass=1.0
    )

    # ジョイント (距離拘束)
    joint_idx = engine.add_joint(
        body_a=root_body,
        body_b=child_body,
        position=(0.0, 9.0, 0.0),
        linear_limit_min=(0.0, 0.0, 0.0),
        linear_limit_max=(0.0, 0.0, 0.0),
        angular_spring=(10.0, 10.0, 10.0)
    )
    print(f"[PASS] Added joint: idx={joint_idx}")

    # 初期位置にわずかな外乱を与える
    engine.set_rigidbody_transform(child_body, (1.0, 8.0, 0.0), (0.0, 0.0, 0.0, 1.0))

    # 120フレームシミュレーション
    for i in range(120):
        engine.step_simulation(dt=1.0/60.0, substeps=10)

    c_trans = engine.get_rigidbody_transform(child_body)
    print(f"Child body pos after pendulum simulation: {c_trans[0]}")
    # 距離が約2.0に維持されているか確認
    dist = (c_trans[0][0]**2 + (c_trans[0][1]-10.0)**2 + c_trans[0][2]**2)**0.5
    print(f"Distance to root: {dist:.3f} (expected ~2.0)")
    assert 1.8 < dist < 2.2, "Joint constraint distance maintained."
    print("[PASS] Joint constraint test passed.")

    engine.close()
    print("=== All XPBD Tests Passed Successfully! ===")

if __name__ == "__main__":
    run_tests()
