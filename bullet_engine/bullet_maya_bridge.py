# -*- coding: utf-8 -*-
"""
MMD Bullet 物理演算エンジン Maya ブリッジモジュール
本家 MMD 仕様の Bullet Physics 2.83.7 によるシミュレーションと Maya ボーンへのベイク処理を提供します。
"""

import os
import sys
import math
import maya.cmds as mc
import maya.api.OpenMaya as om

from .bullet_wrapper import BulletEngineWrapper
from ..cpp_engine.xpbd_visualizer import (
    sync_visualizer_transforms,
    mute_dynamic_constraints,
    VIS_GROUP_NAME,
    map_pmx_bones_to_maya,
    reconnect_visualizers_to_bones
)
from ..mmd_core import pmx

def quat_normalize(q):
    """四元数の正規化"""
    length = math.sqrt(q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3])
    if length > 1e-7:
        inv = 1.0 / length
        return (q[0]*inv, q[1]*inv, q[2]*inv, q[3]*inv)
    return (0.0, 0.0, 0.0, 1.0)

def quat_multiply(q1, q2):
    """四元数の積 (q1 * q2)"""
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return (
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
        w1*w2 - x1*x2 - y1*y2 - z1*z2
    )

def quat_inverse(q):
    """単位四元数の逆元"""
    return (-q[0], -q[1], -q[2], q[3])

def quat_rotate_vector(q, v):
    """四元数によるベクトルの回転"""
    qv = (v[0], v[1], v[2], 0.0)
    res = quat_multiply(quat_multiply(q, qv), quat_inverse(q))
    return (res[0], res[1], res[2])

def quat_from_euler_xyz(rx_deg, ry_deg, rz_deg):
    """XYZオイラー角（度数法）から四元数への変換"""
    e = om.MEulerRotation(math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg), om.MEulerRotation.kXYZ)
    q = e.asQuaternion()
    return (q.x, q.y, q.z, q.w)

def quat_to_euler_xyz(q):
    """四元数からXYZオイラー角（度数法）への変換"""
    mq = om.MQuaternion(q[0], q[1], q[2], q[3])
    e = mq.asEulerRotation()
    return (math.degrees(e.x), math.degrees(e.y), math.degrees(e.z))

def quat_normalize(q):
    """四元数の正規化"""
    length = math.sqrt(q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3])
    if length < 1e-8:
        return (0.0, 0.0, 0.0, 1.0)
    return (q[0] / length, q[1] / length, q[2] / length, q[3] / length)

def get_dag_path(node_name):
    """MayaノードのMDagPathを取得"""
    sel = om.MSelectionList()
    sel.add(node_name)
    return sel.getDagPath(0)

class BulletMayaBridge:
    """
    Bullet物理シミュレーションとMayaシーンを仲介するブリッジクラス
    """
    def __init__(self, pmx_path, scale=8.0):
        self.pmx_path = pmx_path
        self.scale = scale
        self.pmx_model = pmx.load(pmx_path)

        # Bullet C++ エンジンの初期化
        self.engine = BulletEngineWrapper()

        # PMXボーンとMayaジョイントの対応付け
        all_joints = mc.ls(type="joint", long=True) or []
        self.pmx_to_maya_joints = map_pmx_bones_to_maya(self.pmx_model.bones, all_joints)

        self.kinematic_and_aligned_rb_indices = []
        self.dynamic_rb_indices = []
        self.rb_initial_trans = []
        self.last_eulers = {}

    def setup_scene_from_pmx(self):
        """PMXの剛体・ジョイント設定をBulletエンジンへ転送"""
        self.engine.clear()
        self.engine.set_gravity(0.0, -98.0 * (self.scale / 10.0), 0.0)

        self.kinematic_and_aligned_rb_indices = []
        self.dynamic_rb_indices = []
        self.rb_initial_trans = []

        self.rb_local_offsets = {}

        # 剛体登録
        for rb_idx, rb in enumerate(self.pmx_model.rigid_bodies):
            target_joint = self.pmx_to_maya_joints.get(rb.bone_index, None)
            rb_bind_p = (rb.position[0] * self.scale, rb.position[1] * self.scale, -rb.position[2] * self.scale)
            deg_x = math.degrees(rb.rotation[0])
            deg_y = math.degrees(rb.rotation[1])
            deg_z = -math.degrees(rb.rotation[2])
            rb_bind_q = quat_from_euler_xyz(deg_x, deg_y, deg_z)

            # PMXバインドデータからボーンに対する相対ローカルオフセットを算出
            b_idx = rb.bone_index
            if 0 <= b_idx < len(self.pmx_model.bones):
                bone = self.pmx_model.bones[b_idx]
                bone_loc = getattr(bone, 'location', getattr(bone, 'position', [0.0, 0.0, 0.0]))
                b_bind_p = (bone_loc[0] * self.scale, bone_loc[1] * self.scale, -bone_loc[2] * self.scale)
                local_p = (rb_bind_p[0] - b_bind_p[0], rb_bind_p[1] - b_bind_p[1], rb_bind_p[2] - b_bind_p[2])
                local_q = rb_bind_q
            else:
                local_p = (0.0, 0.0, 0.0)
                local_q = rb_bind_q
            self.rb_local_offsets[rb_idx] = (local_p, local_q)

            # 現在のボーン姿勢に基づく正確な初期ワールド姿勢計算
            init_pos = rb_bind_p
            init_quat = rb_bind_q
            if target_joint and mc.objExists(target_joint):
                try:
                    dp = get_dag_path(target_joint)
                    fn_trans = om.MFnTransform(dp)
                    curr_pos = fn_trans.translation(om.MSpace.kWorld)
                    curr_rot = fn_trans.rotation(om.MSpace.kWorld, asQuaternion=True)
                    b_pos = (curr_pos.x, curr_pos.y, curr_pos.z)
                    b_quat = (curr_rot.x, curr_rot.y, curr_rot.z, curr_rot.w)
                    world_p = quat_rotate_vector(b_quat, local_p)
                    init_pos = (b_pos[0] + world_p[0], b_pos[1] + world_p[1], b_pos[2] + world_p[2])
                    init_quat = quat_multiply(b_quat, local_q)
                except Exception:
                    pass

            self.rb_initial_trans.append((init_pos, init_quat))

            rb_size = getattr(rb, 'size', getattr(rb, 'shape_size', [1.0, 1.0, 1.0]))
            if rb.shape_type == 0:
                size = (rb_size[0] * self.scale, 0.0, 0.0)
            elif rb.shape_type == 1:
                size = (rb_size[0] * self.scale, rb_size[1] * self.scale, rb_size[2] * self.scale)
            else:
                size = (rb_size[0] * self.scale, rb_size[1] * self.scale, 0.0)

            init_euler = quat_to_euler_xyz(init_quat)
            init_euler_rad = (math.radians(init_euler[0]), math.radians(init_euler[1]), math.radians(init_euler[2]))

            self.engine.add_rigidbody(
                bone_idx=rb.bone_index,
                shape_type=rb.shape_type,
                physics_mode=rb.physics_mode,
                size=size,
                pos=init_pos,
                rot_euler=init_euler_rad,
                mass=rb.mass,
                linear_damping=max(0.05, float(rb.linear_damping)),
                angular_damping=max(0.05, float(rb.angular_damping)),
                restitution=rb.restitution,
                friction=rb.friction,
                group=rb.group,
                collision_mask=rb.collision_mask
            )

            if rb.physics_mode in [0, 2]:
                self.kinematic_and_aligned_rb_indices.append(rb_idx)
            if rb.physics_mode in [1, 2]:
                self.dynamic_rb_indices.append(rb_idx)

        # ジョイント登録
        for j in self.pmx_model.joints:
            rb_a = self.pmx_model.rigid_bodies[j.rigid_body_a]
            rb_a_bind_p = (rb_a.position[0] * self.scale, rb_a.position[1] * self.scale, -rb_a.position[2] * self.scale)
            deg_ax = math.degrees(rb_a.rotation[0])
            deg_ay = math.degrees(rb_a.rotation[1])
            deg_az = -math.degrees(rb_a.rotation[2])
            rb_a_bind_q = quat_from_euler_xyz(deg_ax, deg_ay, deg_az)

            j_bind_p = (j.position[0] * self.scale, j.position[1] * self.scale, -j.position[2] * self.scale)
            deg_jx = math.degrees(j.rotation[0])
            deg_jy = math.degrees(j.rotation[1])
            deg_jz = -math.degrees(j.rotation[2])
            j_bind_q = quat_from_euler_xyz(deg_jx, deg_jy, deg_jz)

            inv_ra_q = quat_inverse(rb_a_bind_q)
            j_diff = (j_bind_p[0] - rb_a_bind_p[0], j_bind_p[1] - rb_a_bind_p[1], j_bind_p[2] - rb_a_bind_p[2])
            j_local_p = quat_rotate_vector(inv_ra_q, j_diff)
            j_local_q = quat_multiply(inv_ra_q, j_bind_q)

            pos_a, quat_a = self.rb_initial_trans[j.rigid_body_a]
            j_world_diff = quat_rotate_vector(quat_a, j_local_p)
            current_j_pos = (pos_a[0] + j_world_diff[0], pos_a[1] + j_world_diff[1], pos_a[2] + j_world_diff[2])
            current_j_quat = quat_multiply(quat_a, j_local_q)
            current_j_euler = quat_to_euler_xyz(current_j_quat)
            current_j_rot = (math.radians(current_j_euler[0]), math.radians(current_j_euler[1]), math.radians(current_j_euler[2]))

            min_t = (j.linear_limit_min[0] * self.scale, j.linear_limit_min[1] * self.scale, -j.linear_limit_max[2] * self.scale)
            max_t = (j.linear_limit_max[0] * self.scale, j.linear_limit_max[1] * self.scale, -j.linear_limit_min[2] * self.scale)
            min_r = (j.angular_limit_min[0], j.angular_limit_min[1], -j.angular_limit_max[2])
            max_r = (j.angular_limit_max[0], j.angular_limit_max[1], -j.angular_limit_min[2])

            sp_t = (j.linear_spring[0], j.linear_spring[1], j.linear_spring[2])
            sp_r = (j.angular_spring[0], j.angular_spring[1], j.angular_spring[2])

            self.engine.add_joint(
                rb_a_idx=j.rigid_body_a,
                rb_b_idx=j.rigid_body_b,
                pos=current_j_pos,
                rot_euler=current_j_rot,
                pos_min=min_t,
                pos_max=max_t,
                rot_min=min_r,
                rot_max=max_r,
                spring_pos=sp_t,
                spring_rot=sp_r
            )

        # 動的ボーンをMayaの階層深度順（親から子へ）にソート
        def get_depth(rb_idx):
            rb = self.pmx_model.rigid_bodies[rb_idx]
            j_name = self.pmx_to_maya_joints.get(rb.bone_index, "")
            return len(j_name.split('|')) if j_name else 0

        self.dynamic_rb_indices.sort(key=get_depth)

    def bake_simulation(self, start_frame=0, end_frame=100, sub_steps=10, progress_callback=None):
        """タイムラインに沿ってBullet物理シミュレーションを実行しキーフレームを書き込み"""
        print(f"[Bullet] ベイク処理開始: {start_frame}F 〜 {end_frame}F (サブステップ: {sub_steps})")
        fps = 30.0
        dt = 1.0 / fps

        mc.currentTime(start_frame, edit=True)
        self.setup_scene_from_pmx()

        # 追従コンストレイントを一時ミュート
        mute_dynamic_constraints(mute=True)

        # 初期めり込み解消ウォームアップ (Pre-roll Relaxation)
        # 太もも等とスカートの初期貫通を接触インパルスのみで初速ゼロのまま外側へ押し出す
        print(f"[Bullet] 初期めり込み解消ウォームアップ (Pre-roll Relaxation) を実行中...")
        for rb_idx in self.kinematic_and_aligned_rb_indices:
            rb = self.pmx_model.rigid_bodies[rb_idx]
            joint_name = self.pmx_to_maya_joints.get(rb.bone_index, None)
            if not joint_name or not mc.objExists(joint_name):
                continue
            dp = get_dag_path(joint_name)
            fn_trans = om.MFnTransform(dp)
            pos = fn_trans.translation(om.MSpace.kWorld)
            rot = fn_trans.rotation(om.MSpace.kWorld, asQuaternion=True)
            b_pos = (pos.x, pos.y, pos.z)
            b_quat = (rot.x, rot.y, rot.z, rot.w)

            local_p, local_q = self.rb_local_offsets.get(rb_idx, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
            world_offset = quat_rotate_vector(b_quat, local_p)
            target_pos = (b_pos[0] + world_offset[0], b_pos[1] + world_offset[1], b_pos[2] + world_offset[2])
            target_quat = quat_multiply(b_quat, local_q)
            target_euler = quat_to_euler_xyz(target_quat)
            target_euler_rad = (math.radians(target_euler[0]), math.radians(target_euler[1]), math.radians(target_euler[2]))
            self.engine.set_target_transform(rb_idx, target_pos, target_euler_rad)

        self.engine.relax_penetration(steps=25, damping=0.99)
        self.engine.reset_velocities()
        self.engine.reset_constraints()
        print(f"[Bullet] 初期めり込み解消完了。初速ゼロの安定姿勢からベイクを開始します。")

        cached_parent_paths = {}
        for rb_idx in self.dynamic_rb_indices:
            rb = self.pmx_model.rigid_bodies[rb_idx]
            joint_name = self.pmx_to_maya_joints.get(rb.bone_index, None)
            if not joint_name or not mc.objExists(joint_name):
                continue
            parent_node = mc.listRelatives(joint_name, parent=True, fullPath=True)
            if parent_node:
                cached_parent_paths[rb_idx] = get_dag_path(parent_node[0])
            else:
                cached_parent_paths[rb_idx] = None

        self.last_eulers.clear()

        try:
            total_frames = end_frame - start_frame + 1
            for f_idx, frame in enumerate(range(int(start_frame), int(end_frame) + 1)):
                mc.currentTime(frame, edit=True)

                # Kinematic / Aligned 剛体の目標位置転送
                for rb_idx in self.kinematic_and_aligned_rb_indices:
                    rb = self.pmx_model.rigid_bodies[rb_idx]
                    joint_name = self.pmx_to_maya_joints.get(rb.bone_index, None)
                    if not joint_name or not mc.objExists(joint_name):
                        continue
                    dp = get_dag_path(joint_name)
                    fn_trans = om.MFnTransform(dp)
                    pos = fn_trans.translation(om.MSpace.kWorld)
                    rot = fn_trans.rotation(om.MSpace.kWorld, asQuaternion=True)
                    b_pos = (pos.x, pos.y, pos.z)
                    b_quat = (rot.x, rot.y, rot.z, rot.w)

                    local_p, local_q = self.rb_local_offsets.get(rb_idx, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
                    world_offset = quat_rotate_vector(b_quat, local_p)
                    target_pos = (b_pos[0] + world_offset[0], b_pos[1] + world_offset[1], b_pos[2] + world_offset[2])
                    target_quat = quat_multiply(b_quat, local_q)
                    target_euler = quat_to_euler_xyz(target_quat)
                    target_euler_rad = (math.radians(target_euler[0]), math.radians(target_euler[1]), math.radians(target_euler[2]))

                    self.engine.set_target_transform(rb_idx, target_pos, target_euler_rad)

                # Bullet物理ステップ実行
                self.engine.step_simulation(dt=dt, max_sub_steps=sub_steps, fixed_time_step=dt / float(sub_steps))

                # ジョイントへのキーフレーム書き込み
                for rb_idx in self.dynamic_rb_indices:
                    rb = self.pmx_model.rigid_bodies[rb_idx]
                    joint_name = self.pmx_to_maya_joints.get(rb.bone_index, None)
                    if not joint_name or not mc.objExists(joint_name):
                        continue

                    rb_pos, rb_rot = self.engine.get_rigidbody_transform(rb_idx)
                    # 剛体の現在ワールド回転からボーンの目標ワールド回転を算出: Q_target = Q_current * inv(Q_offset)
                    if rb_idx in self.rb_local_offsets:
                        _, local_q = self.rb_local_offsets[rb_idx]
                        target_world_quat = quat_multiply(rb_rot, quat_inverse(local_q))
                    else:
                        target_world_quat = rb_rot

                    target_world_quat = quat_normalize(target_world_quat)

                    try:
                        parent_nodes = mc.listRelatives(joint_name, parent=True, fullPath=True)
                        if parent_nodes:
                            parent_dag = get_dag_path(parent_nodes[0])
                            parent_inv_mat = parent_dag.inclusiveMatrixInverse()
                        else:
                            parent_inv_mat = om.MMatrix()

                        target_om_q = om.MQuaternion(target_world_quat[0], target_world_quat[1], target_world_quat[2], target_world_quat[3])
                        target_mat = target_om_q.asMatrix()

                        local_mat = target_mat * parent_inv_mat
                        local_trans = om.MTransformationMatrix(local_mat)
                        local_q = local_trans.rotation(asQuaternion=True)

                        jo = mc.getAttr(f"{joint_name}.jointOrient")[0]
                        jo_e = om.MEulerRotation(math.radians(jo[0]), math.radians(jo[1]), math.radians(jo[2]), om.MEulerRotation.kXYZ)
                        inv_jo_q = jo_e.asQuaternion().inverse()

                        ra = mc.getAttr(f"{joint_name}.rotateAxis")[0]
                        ra_e = om.MEulerRotation(math.radians(ra[0]), math.radians(ra[1]), math.radians(ra[2]), om.MEulerRotation.kXYZ)
                        inv_ra_q = ra_e.asQuaternion().inverse()

                        bone_rot_q = inv_jo_q * local_q * inv_ra_q
                        ro = mc.getAttr(f"{joint_name}.rotateOrder")
                        bone_euler = bone_rot_q.asEulerRotation()
                        bone_euler.reorderIt(ro)

                        if joint_name in self.last_eulers:
                            bone_euler = bone_euler.closestSolution(self.last_eulers[joint_name])
                        self.last_eulers[joint_name] = bone_euler

                        deg_x = math.degrees(bone_euler.x)
                        deg_y = math.degrees(bone_euler.y)
                        deg_z = math.degrees(bone_euler.z)

                        mc.setAttr(f"{joint_name}.rotateX", deg_x)
                        mc.setAttr(f"{joint_name}.rotateY", deg_y)
                        mc.setAttr(f"{joint_name}.rotateZ", deg_z)
                        mc.setKeyframe(joint_name, attribute=['rotateX', 'rotateY', 'rotateZ'], time=frame)

                    except Exception:
                        euler_deg = quat_to_euler_xyz(target_world_quat)
                        try:
                            mc.xform(joint_name, worldSpace=True, rotation=euler_deg)
                            mc.setKeyframe(joint_name, attribute=['rotateX', 'rotateY', 'rotateZ'], time=frame)
                        except Exception:
                            pass

                # 可視化ノードの同期
                if mc.objExists(VIS_GROUP_NAME):
                    all_trans = {}
                    for idx in range(len(self.pmx_model.rigid_bodies)):
                        pos, rot = self.engine.get_rigidbody_transform(idx)
                        all_trans[idx] = (pos, rot)
                    sync_visualizer_transforms(all_trans, frame=frame)

                if progress_callback:
                    progress_callback(int((f_idx + 1) / total_frames * 100))

        finally:
            # ベイク完了時に可視化ノードを即座にモデルボーンへ再吸着復元
            reconnect_visualizers_to_bones()
            print("[Bullet] 剛体とJointをモデルボーンに再吸着復元しました。")

        print("[Bullet] ベイク処理が正常に完了しました！")

    def clear_physics_keyframes(self):
        """
        物理対象ボーン（DynamicおよびAligned剛体に対応するMayaジョイント）に書き込まれた
        キーフレームをクリアし、可視化ノードを初期追従状態に復元します。
        """
        for rb_idx in self.dynamic_rb_indices:
            rb = self.pmx_model.rigid_bodies[rb_idx]
            joint_name = self.pmx_to_maya_joints.get(rb.bone_index, None)
            if joint_name and mc.objExists(joint_name):
                try:
                    mc.cutKey(joint_name, attribute=['translateX', 'translateY', 'translateZ', 'rotateX', 'rotateY', 'rotateZ'], clear=True)
                except Exception:
                    pass

        reconnect_visualizers_to_bones()
        print("[Bullet] 物理対象ボーンのキーフレームをクリアし、剛体・Jointを再吸着しました。")
