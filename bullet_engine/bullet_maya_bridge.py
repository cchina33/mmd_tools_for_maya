# -*- coding: utf-8 -*-
"""
MMD Bullet 物理演算エンジン Maya ブリッジモジュール
本家 MMD 仕様の Bullet Physics (2.75 / 2.83.7) によるシミュレーションと Maya ボーンへのベイク処理を提供します。
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

def restore_viewport_lighting():
    """
    ビューポートのライティング（全ライト使用: displayLights='all'）および
    テクスチャ表示（displayTextures=True）を安定化・復元します。
    """
    try:
        has_lights = bool(mc.ls(type=["directionalLight", "ambientLight", "pointLight", "spotLight"]))
        target_mode = "all" if has_lights else "default"
        panels = mc.getPanel(type="modelPanel") or []
        for p in panels:
            try:
                mc.modelEditor(p, edit=True, displayLights=target_mode, displayTextures=True)
            except Exception:
                pass
        mc.refresh(force=True)
    except Exception:
        pass

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
    def __init__(self, pmx_path, scale=8.0, target_model=None, bullet_version="2.75"):
        self.pmx_path = pmx_path
        self.scale = scale
        self.target_model = target_model
        self.bullet_version = bullet_version
        self.pmx_model = pmx.load(pmx_path)

        # Bullet C++ エンジンの初期化 (指定バージョン)
        self.engine = BulletEngineWrapper(bullet_version=bullet_version)

        # PMXボーンとMayaジョイントの対応付け (特定モデル指定時は多層探索により関連ジョイントを特定)
        model_joints = []
        if target_model and mc.objExists(target_model):
            # 対象ノード自身がジョイントの場合
            if mc.nodeType(target_model) == 'joint':
                model_joints = mc.listRelatives(target_model, allDescendents=True, type="joint", fullPath=True) or []
                model_joints.append(target_model)

            # 対象ノードがメッシュまたはトランスフォームの場合: スキンクラスターからインフルエンスジョイントを探索
            if not model_joints:
                history_skins = mc.ls(mc.listHistory(target_model) or [], type='skinCluster') or []
                for sc in history_skins:
                    influences = mc.skinCluster(sc, query=True, influence=True) or []
                    for inf in influences:
                        if inf and mc.objExists(inf) and mc.nodeType(inf) == 'joint':
                            long_p = mc.ls(inf, long=True)
                            if long_p and long_p[0] not in model_joints:
                                model_joints.append(long_p[0])

            # 親グループが存在する場合: 親グループ配下のジョイントを探索
            if not model_joints:
                parents = mc.listRelatives(target_model, parent=True, fullPath=True) or []
                for p in parents:
                    p_joints = mc.listRelatives(p, allDescendents=True, type="joint", fullPath=True) or []
                    for pj in p_joints:
                        if pj not in model_joints:
                            model_joints.append(pj)

            # メッシュ配下の子孫ジョイントの探索
            if not model_joints:
                model_joints = mc.listRelatives(target_model, allDescendents=True, type="joint", fullPath=True) or []

        # 上記でジョイントが取得できなかった場合、またはtarget_model未指定時はシーン全体のジョイントを対象化
        if not model_joints:
            model_joints = mc.ls(type="joint", long=True) or []

        self.pmx_to_maya_joints = map_pmx_bones_to_maya(self.pmx_model.bones, model_joints)
        print(f"[Bullet] ボーン紐付け完了: {len(self.pmx_to_maya_joints)} / {len(self.pmx_model.bones)} ボーン (探索対象ジョイント数: {len(model_joints)})")

        self.kinematic_and_aligned_rb_indices = []
        self.dynamic_rb_indices = []
        self.rb_initial_trans = []
        self.last_eulers = {}

    def setup_scene_from_pmx(self, gravity_y=None):
        """PMXの剛体・ジョイント設定をBulletエンジンへ転送"""
        self.engine.clear()
        if gravity_y is not None:
            gy = float(gravity_y)
            if abs(gy) < 50.0:
                # MMD本家GUIの加速度値（例: -9.80）
                grav = gy * 10.0 * (self.scale / 10.0)
            else:
                # cm/s²単位（例: -980.0）
                grav = gy * 0.1 * (self.scale / 10.0)
            self.engine.set_gravity(0.0, grav, 0.0)
        else:
            self.engine.set_gravity(0.0, -98.0 * (self.scale / 10.0), 0.0)

        self.kinematic_and_aligned_rb_indices = []
        self.dynamic_rb_indices = []
        self.rb_initial_trans = []

        self.rb_local_offsets = {}

        # 剛体登録
        for rb_idx, rb in enumerate(self.pmx_model.rigid_bodies):
            target_joint = self.pmx_to_maya_joints.get(rb.bone_index, None)
            rb_bind_p = (rb.position[0] * self.scale, rb.position[1] * self.scale, -rb.position[2] * self.scale)
            deg_x = -math.degrees(rb.rotation[0])
            deg_y = -math.degrees(rb.rotation[1])
            deg_z = math.degrees(rb.rotation[2])
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

            # 初期姿勢:
            # フレーム0におけるボーン姿勢からローカルオフセットを用いてワールド座標・回転を決定
            # (モデルが初期ポーズをとっている場合でも、剛体とJointが初期追従して初期張力爆発を防止)
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
            # 剛体Aに対するローカルオフセットから、現在の剛体Aのワールド姿勢に合わせてJointを配置
            # (剛体AとJointの相対オフセット歪みを徹底して排除し、初期張力爆発を防止)
            rb_a = self.pmx_model.rigid_bodies[j.rigid_body_a]
            rb_a_bind_p = (rb_a.position[0] * self.scale, rb_a.position[1] * self.scale, -rb_a.position[2] * self.scale)
            deg_ax = -math.degrees(rb_a.rotation[0])
            deg_ay = -math.degrees(rb_a.rotation[1])
            deg_az = math.degrees(rb_a.rotation[2])
            rb_a_bind_q = quat_from_euler_xyz(deg_ax, deg_ay, deg_az)

            j_bind_p = (j.position[0] * self.scale, j.position[1] * self.scale, -j.position[2] * self.scale)
            deg_jx = -math.degrees(j.rotation[0])
            deg_jy = -math.degrees(j.rotation[1])
            deg_jz = math.degrees(j.rotation[2])
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

            # 移動制限 (A < B で範囲、A == B でロック、A > B でフリー)
            min_tx = j.linear_limit_min[0] * self.scale
            max_tx = j.linear_limit_max[0] * self.scale
            min_ty = j.linear_limit_min[1] * self.scale
            max_ty = j.linear_limit_max[1] * self.scale
            if j.linear_limit_min[2] > j.linear_limit_max[2]:
                min_tz = 1.0
                max_tz = 0.0
            else:
                min_tz = -j.linear_limit_max[2] * self.scale
                max_tz = -j.linear_limit_min[2] * self.scale
            min_t = (min_tx, min_ty, min_tz)
            max_t = (max_tx, max_ty, max_tz)

            # 回転制限 (A < B で範囲、A == B でロック、A > B でフリー。X, Yは符号反転に伴いMinとMaxが反転)
            if j.angular_limit_min[0] > j.angular_limit_max[0]:
                min_rx = 1.0
                max_rx = -1.0
            else:
                min_rx = -j.angular_limit_max[0]
                max_rx = -j.angular_limit_min[0]

            if j.angular_limit_min[1] > j.angular_limit_max[1]:
                min_ry = 1.0
                max_ry = -1.0
            else:
                min_ry = -j.angular_limit_max[1]
                max_ry = -j.angular_limit_min[1]

            if j.angular_limit_min[2] > j.angular_limit_max[2]:
                min_rz = 1.0
                max_rz = -1.0
            else:
                min_rz = j.angular_limit_min[2]
                max_rz = j.angular_limit_max[2]
            min_r = (min_rx, min_ry, min_rz)
            max_r = (max_rx, max_ry, max_rz)

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
                spring_rot=sp_r,
                joint_type=getattr(j, 'joint_type', 0)
            )

        # 動的ボーンをMayaの階層深度順（親から子へ）にソート
        def get_depth(rb_idx):
            rb = self.pmx_model.rigid_bodies[rb_idx]
            j_name = self.pmx_to_maya_joints.get(rb.bone_index, "")
            return len(j_name.split('|')) if j_name else 0

        self.dynamic_rb_indices.sort(key=get_depth)

    def bake_simulation(self, start_frame=0, end_frame=100, sub_steps=20, progress_callback=None, cancel_callback=None, enable_floor=True, floor_height=0.0, gravity_y=None, fps=60.0, physics_mode="dance"):
        """タイムラインに沿ってBullet物理シミュレーションを実行しキーフレームを一括書き込み"""
        fps_val = float(fps) if fps else 60.0

        # モードに応じたサブステップ数の最適化
        if physics_mode == "dance":
            actual_substeps = max(int(sub_steps), 30)
            relax_steps = 3
        else:
            actual_substeps = min(int(sub_steps), 15) if int(sub_steps) > 15 else int(sub_steps)
            relax_steps = 3

        print(f"[Bullet] 超高速一括ベイク処理開始: {start_frame}F 〜 {end_frame}F (モード: {physics_mode}, FPS: {fps_val:.1f}, サブステップ: {actual_substeps})")
        dt = 1.0 / fps_val

        # ベイク開始前のビューポートライティング状態を保護・最適化
        restore_viewport_lighting()

        mc.currentTime(start_frame, edit=True)
        self.setup_scene_from_pmx(gravity_y=gravity_y)

        # 床判定 (地面無限平面 Y=0) の設定
        if enable_floor:
            self.engine.set_floor_plane(enable=True, y_height=floor_height, friction=0.5, restitution=0.0)
            print(f"[Bullet] 床判定 (地面 Y={floor_height}) を有効化しました。")
        else:
            self.engine.set_floor_plane(enable=False)

        # 追従コンストレイントを一時ミュート
        mute_dynamic_constraints(mute=True)

        # 初期めり込み解消ウォームアップ (Pre-roll Relaxation)
        print("[Bullet] 初期めり込み解消ウォームアップ (Pre-roll Relaxation) を実行中...")
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

        self.engine.relax_penetration(steps=relax_steps, damping=0.99)
        self.engine.reset_velocities()
        self.engine.reset_constraints()
        print("[Bullet] 初期めり込み解消完了。初速ゼロの安定姿勢からベイクを開始します。")

        # Dynamicボーンの静的アトリビュート（jointOrient, rotateAxis, rotateOrder等）を事前収集
        joint_static_props = {}
        for rb_idx in self.dynamic_rb_indices:
            rb = self.pmx_model.rigid_bodies[rb_idx]
            joint_name = self.pmx_to_maya_joints.get(rb.bone_index, None)
            if not joint_name or not mc.objExists(joint_name):
                continue
            jo = mc.getAttr(f"{joint_name}.jointOrient")[0]
            jo_e = om.MEulerRotation(math.radians(jo[0]), math.radians(jo[1]), math.radians(jo[2]), om.MEulerRotation.kXYZ)
            inv_jo_q = jo_e.asQuaternion().inverse()

            ra = mc.getAttr(f"{joint_name}.rotateAxis")[0]
            ra_e = om.MEulerRotation(math.radians(ra[0]), math.radians(ra[1]), math.radians(ra[2]), om.MEulerRotation.kXYZ)
            inv_ra_q = ra_e.asQuaternion().inverse()

            ro = mc.getAttr(f"{joint_name}.rotateOrder")

            parent_nodes = mc.listRelatives(joint_name, parent=True, fullPath=True)
            parent_joint = parent_nodes[0] if parent_nodes else None
            parent_dp = get_dag_path(parent_joint) if parent_joint else None

            joint_static_props[joint_name] = {
                'inv_jo_q': inv_jo_q,
                'inv_ra_q': inv_ra_q,
                'ro': ro,
                'parent_joint': parent_joint,
                'parent_dp': parent_dp
            }

        # アニメーションボーンの事前サンプリング
        # IKハンドル (ikHandle / ikRPsolver) やコンストレイントを毎フレーム確実に解決するため、
        # カレントタイムを明示的に移動してサンプリングします。
        print("[Bullet] アニメーションボーン姿勢の事前キャッシュを作成中 (IK・コンストレイント解決)...")
        kinematic_targets = {}
        parent_inv_mats = {}

        # 評価対象のノードを事前収集
        kinematic_info = {}
        for rb_idx in self.kinematic_and_aligned_rb_indices:
            rb = self.pmx_model.rigid_bodies[rb_idx]
            joint_name = self.pmx_to_maya_joints.get(rb.bone_index, None)
            if joint_name and mc.objExists(joint_name):
                dp = get_dag_path(joint_name)
                fn_trans = om.MFnTransform(dp)
                local_p, local_q = self.rb_local_offsets.get(rb_idx, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
                kinematic_info[rb_idx] = (fn_trans, local_p, local_q)

        parent_info = {}
        for joint_name, props in joint_static_props.items():
            parent_dp = props['parent_dp']
            if parent_dp:
                parent_info[joint_name] = parent_dp

        orig_time = mc.currentTime(query=True)
        try:
            mc.refresh(suspend=True)
            for f in range(int(start_frame), int(end_frame) + 1):
                mc.currentTime(f, edit=True)

                # Kinematic目標姿勢の取得 (IK解決済みの最新ワールド姿勢)
                k_data = {}
                for rb_idx, (fn_trans, local_p, local_q) in kinematic_info.items():
                    pos = fn_trans.translation(om.MSpace.kWorld)
                    rot = fn_trans.rotation(om.MSpace.kWorld, asQuaternion=True)
                    b_pos = (pos.x, pos.y, pos.z)
                    b_quat = (rot.x, rot.y, rot.z, rot.w)

                    world_offset = quat_rotate_vector(b_quat, local_p)
                    target_pos = (b_pos[0] + world_offset[0], b_pos[1] + world_offset[1], b_pos[2] + world_offset[2])
                    target_quat = quat_multiply(b_quat, local_q)
                    target_euler = quat_to_euler_xyz(target_quat)
                    target_euler_rad = (math.radians(target_euler[0]), math.radians(target_euler[1]), math.radians(target_euler[2]))
                    k_data[rb_idx] = (target_pos, target_euler_rad)
                kinematic_targets[f] = k_data

                # Kinematic親ノードの逆行列取得 (IK解決済みの最新ワールド逆行列)
                p_data = {}
                for joint_name, parent_dp in parent_info.items():
                    p_data[joint_name] = parent_dp.inclusiveMatrix().inverse()
                parent_inv_mats[f] = p_data

        finally:
            mc.currentTime(orig_time, edit=True)
            mc.refresh(suspend=False)

        print("[Bullet] 事前キャッシュ完了 (IK・コンストレイント解決済み)。")

        self.last_eulers.clear()

        # 高速ベイク用のメモリバッファを初期化
        bake_buffer = {}
        for rb_idx in self.dynamic_rb_indices:
            rb = self.pmx_model.rigid_bodies[rb_idx]
            joint_name = self.pmx_to_maya_joints.get(rb.bone_index, None)
            if joint_name and joint_name in joint_static_props:
                bake_buffer[joint_name] = {
                    'frames': [],
                    'rx': [],
                    'ry': [],
                    'rz': []
                }

        # ボーン階層の深さ順にソート (親ボーンが子ボーンよりも必ず先に評価・確定されるよう保証)
        def get_joint_hierarchy_depth(idx):
            rb_obj = self.pmx_model.rigid_bodies[idx]
            j_str = self.pmx_to_maya_joints.get(rb_obj.bone_index, "")
            return j_str.count("|") if j_str else 0

        sorted_dynamic_rb_indices = sorted(self.dynamic_rb_indices, key=get_joint_hierarchy_depth)

        try:
            total_frames = end_frame - start_frame + 1
            cancelled = False

            # タイムラインを動かさずメモリ上だけでBulletシミュレーションとオイラー角計算を実行
            for f_idx, frame in enumerate(range(int(start_frame), int(end_frame) + 1)):
                if cancel_callback and cancel_callback():
                    print(f"[Bullet] ユーザーによりベイクが中止されました (フレーム {frame})。")
                    cancelled = True
                    break

                # Kinematic剛体のマイクロステップ連続補間 (足の移動速度を持続的に物理エンジンへ伝達)
                micro_steps = 2
                sub_dt = dt / float(micro_steps)

                # 本家MMD準拠の安定した物理内部刻み (通常モード: 60Hz, ダンスモード: 120Hz)
                # 極小のfixedTimeStepによるスプリング目標速度の暴走・あらぶりを防止し、しなやかな揺れを実現
                physics_hz = 120.0 if physics_mode == "dance" else 60.0
                fixed_step = 1.0 / physics_hz
                max_sub = max(2, int(round((sub_dt / fixed_step) * 2)))

                for m in range(micro_steps):
                    alpha = (m + 1.0) / float(micro_steps)
                    for rb_idx, (cur_pos, cur_rot) in kinematic_targets.get(frame, {}).items():
                        prev_pos, _ = kinematic_targets.get(frame - 1, {}).get(rb_idx, (cur_pos, cur_rot)) if frame > start_frame else (cur_pos, cur_rot)
                        interp_pos = (
                            prev_pos[0] + (cur_pos[0] - prev_pos[0]) * alpha,
                            prev_pos[1] + (cur_pos[1] - prev_pos[1]) * alpha,
                            prev_pos[2] + (cur_pos[2] - prev_pos[2]) * alpha
                        )
                        self.engine.set_target_transform(rb_idx, interp_pos, cur_rot)
                    self.engine.step_simulation(dt=sub_dt, max_sub_steps=max_sub, fixed_time_step=fixed_step)


                # 現在フレームの物理演算適用済みボーンワールド回転行列を記録 (チェーン親子伝搬用)
                current_frame_dynamic_world_mats = {}

                # 階層順（親から子）にジョイント姿勢を算出
                for rb_idx in sorted_dynamic_rb_indices:
                    rb = self.pmx_model.rigid_bodies[rb_idx]
                    joint_name = self.pmx_to_maya_joints.get(rb.bone_index, None)
                    if joint_name not in joint_static_props or joint_name not in bake_buffer:
                        continue

                    rb_pos, rb_rot = self.engine.get_rigidbody_transform(rb_idx)
                    if rb_idx in self.rb_local_offsets:
                        _, local_q = self.rb_local_offsets[rb_idx]
                        target_world_quat = quat_multiply(rb_rot, quat_inverse(local_q))
                    else:
                        target_world_quat = rb_rot

                    target_world_quat = quat_normalize(target_world_quat)
                    target_om_q = om.MQuaternion(target_world_quat[0], target_world_quat[1], target_world_quat[2], target_world_quat[3])
                    target_mat = target_om_q.asMatrix()
                    current_frame_dynamic_world_mats[joint_name] = target_mat

                    try:
                        props = joint_static_props[joint_name]
                        parent_joint = props['parent_joint']

                        # 親がDynamicボーンの場合は最新の物理ワールド回転行列の逆行列を採用し、チェーンの累積誤差を排除
                        if parent_joint in current_frame_dynamic_world_mats:
                            parent_inv_mat = current_frame_dynamic_world_mats[parent_joint].inverse()
                        else:
                            parent_inv_mat = parent_inv_mats.get(frame, {}).get(joint_name, om.MMatrix())

                        # 親から見たボーンのローカル回転を算出 (M_local = M_target * M_parent^-1)
                        local_mat = target_mat * parent_inv_mat
                        local_trans = om.MTransformationMatrix(local_mat)
                        local_q = local_trans.rotation(asQuaternion=True)

                        inv_jo_q = props['inv_jo_q']
                        inv_ra_q = props['inv_ra_q']
                        ro = props['ro']

                        # ジョイントのオイラー回転へ変換
                        bone_rot_q = inv_jo_q * local_q * inv_ra_q
                        bone_euler = bone_rot_q.asEulerRotation()
                        bone_euler.reorderIt(ro)

                        if joint_name in self.last_eulers:
                            bone_euler = bone_euler.closestSolution(self.last_eulers[joint_name])
                        self.last_eulers[joint_name] = bone_euler

                        deg_x = math.degrees(bone_euler.x)
                        deg_y = math.degrees(bone_euler.y)
                        deg_z = math.degrees(bone_euler.z)

                        bake_buffer[joint_name]['frames'].append(float(frame))
                        bake_buffer[joint_name]['rx'].append(deg_x)
                        bake_buffer[joint_name]['ry'].append(deg_y)
                        bake_buffer[joint_name]['rz'].append(deg_z)

                    except Exception:
                        euler_deg = quat_to_euler_xyz(target_world_quat)
                        bake_buffer[joint_name]['frames'].append(float(frame))
                        bake_buffer[joint_name]['rx'].append(euler_deg[0])
                        bake_buffer[joint_name]['ry'].append(euler_deg[1])
                        bake_buffer[joint_name]['rz'].append(euler_deg[2])

                if progress_callback:
                    try:
                        progress_callback(frame, end_frame, f_idx + 1, total_frames)
                    except Exception:
                        pass

            # キーフレーム書き込みの実行
            if not cancelled:
                self.apply_bake_buffer(bake_buffer)
            else:
                print("[Bullet] ベイクが中断されたため、キーフレームの適用を安全にスキップしました。")

        finally:
            # ビューポート描画の再開と初期フレーム復元
            mc.refresh(suspend=False)
            mc.currentTime(start_frame, edit=True)
            reconnect_visualizers_to_bones()
            # ベイク完了後にビューポートのライティング状態を確実に復元
            restore_viewport_lighting()
            print("[Bullet] 剛体とJointをモデルボーンに再吸着復元しました。")

        print("[Bullet] ベイク処理が正常に完了しました！")

    def _ensure_motion_plugin_loaded(self):
        """mmd_motion.mll プラグインの自動ロードを試行"""
        if hasattr(mc, "mmdFastBakeBone"):
            return True

        if mc.pluginInfo("mmd_motion", query=True, loaded=True):
            return True

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        maya_ver = "2025"
        try:
            about_ver = mc.about(version=True)
            if "2026" in about_ver:
                maya_ver = "2026"
            elif "2025" in about_ver:
                maya_ver = "2025"
        except Exception:
            pass

        candidates = [
            os.path.join(base_dir, "mmd_motion_plugin", "bin", maya_ver, "mmd_motion.mll"),
            os.path.join(base_dir, "mmd_motion_plugin", "bin", "2025", "mmd_motion.mll"),
            os.path.join(base_dir, "mmd_motion_plugin", "build_2025", "Release", "mmd_motion.mll"),
        ]

        for path in candidates:
            if os.path.exists(path):
                try:
                    mc.loadPlugin(path)
                    if hasattr(mc, "mmdFastBakeBone"):
                        print(f"[Bullet] mmd_motion.mll を自動ロードしました: {path}")
                        try:
                            mc.pluginInfo(path, edit=True, autoload=True)
                            mc.pluginInfo("mmd_motion.mll", edit=True, autoload=True)
                            mc.pluginInfo("mmd_motion", edit=True, autoload=True)
                        except Exception:
                            pass
                        return True
                except Exception as e:
                    print(f"[Bullet] mmd_motion.mll ロード試行エラー: {e}")

        # フォールバックとして mmd_material.mll も確認
        if not hasattr(mc, "mmdFastBakeBone"):
            try:
                import mmd_material_setup
                p = mmd_material_setup.get_plugin_path()
                if p and not mc.pluginInfo("mmd_material", query=True, loaded=True):
                    mc.loadPlugin(p)
            except Exception:
                pass

        return hasattr(mc, "mmdFastBakeBone")

    def apply_bake_buffer(self, bake_buffer):
        """
        蓄積したシミュレーション姿勢データをMayaジョイントへ一括キーフレーム書き込みします。
        C++ プラグイン (mmd_motion.mll: mmdFastBakeBone)、OpenMaya 2.0 API、cmds の順にフォールバックします。
        """
        if not bake_buffer:
            print("[Bullet] ベイクバッファが空のため、キーフレーム書き込みをスキップしました。")
            return

        total_joints = len(bake_buffer)
        total_keys = sum(len(d.get('frames', [])) for d in bake_buffer.values())
        print(f"[Bullet] キーフレーム書き込み準備: {total_joints} 個のジョイント (合計 {total_keys * 3} チャンネルキー)")

        # mmd_motion.mll プラグインの確認と自動ロード
        self._ensure_motion_plugin_loaded()

        # C++ MLL コマンドによる超高速一括ベイク
        if hasattr(mc, "mmdFastBakeBone"):
            print("[Bullet] C++ mmdFastBakeBone (mmd_motion.mll) コマンドによる超高速一括ベイクを実行します。")
            empty_trans = []
            baked_count = 0
            for joint_name, data in bake_buffer.items():
                frames = data['frames']
                if not frames:
                    continue
                try:
                    mc.mmdFastBakeBone(joint_name, frames, empty_trans, empty_trans, empty_trans, data['rx'], data['ry'], data['rz'])
                    baked_count += 1
                except Exception as e:
                    print(f"[Bullet] mmdFastBakeBone 実行警告 ({joint_name}): {e}")
            print(f"[Bullet] C++ mmdFastBakeBone による書き込み完了: {baked_count} / {total_joints} ジョイント")
            return

        # フォールバック: OpenMaya 2.0 API によるバッチ書き込み
        print("[Bullet] OpenMaya 2.0 API によるバッチキーフレーム書き込みを実行します。")
        try:
            import maya.api.OpenMayaAnim as oma
            time_unit = om.MTime.uiUnit()
            baked_count = 0
            for joint_name, data in bake_buffer.items():
                frames = data['frames']
                if not frames:
                    continue
                num_keys = len(frames)
                time_array = om.MTimeArray()
                time_array.setLength(num_keys)
                for i, f in enumerate(frames):
                    time_array.set(om.MTime(f, time_unit), i)

                sl = om.MSelectionList()
                sl.add(joint_name)
                mobj = sl.getDependNode(0)
                fn_node = om.MFnDependencyNode(mobj)

                axis_map = [('rotateX', data['rx']), ('rotateY', data['ry']), ('rotateZ', data['rz'])]
                for attr_name, vals in axis_map:
                    plug = fn_node.findPlug(attr_name, True)
                    if plug.isNull:
                        continue

                    # 角度内部単位 (Radians) に変換
                    double_array = om.MDoubleArray()
                    double_array.setLength(num_keys)
                    for i, v in enumerate(vals):
                        double_array.set(math.radians(v), i)

                    anim_curve = oma.MFnAnimCurve()
                    if not anim_curve.hasCurve(plug):
                        anim_curve.create(plug, oma.MFnAnimCurve.kAnimCurveTA)
                    else:
                        anim_curve.setObject(plug)
                    anim_curve.addKeys(time_array, double_array)
                baked_count += 1
            print(f"[Bullet] OpenMaya 2.0 バッチ書き込み完了: {baked_count} / {total_joints} ジョイント")
            return
        except Exception as e:
            print(f"[Bullet] OpenMaya 2.0 バッチ書き込みフォールバック失敗: {e}")

        # 最終フォールバック: cmds.setKeyframe
        print("[Bullet] cmds.setKeyframe による順次書き込みフォールバックを実行します。")
        baked_count = 0
        for joint_name, data in bake_buffer.items():
            frames = data['frames']
            rx = data['rx']
            ry = data['ry']
            rz = data['rz']
            for i in range(len(frames)):
                f = frames[i]
                mc.setKeyframe(joint_name, attribute='rotateX', time=f, value=rx[i])
                mc.setKeyframe(joint_name, attribute='rotateY', time=f, value=ry[i])
                mc.setKeyframe(joint_name, attribute='rotateZ', time=f, value=rz[i])
            baked_count += 1
        print(f"[Bullet] cmds.setKeyframe による書き込み完了: {baked_count} / {total_joints} ジョイント")

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
