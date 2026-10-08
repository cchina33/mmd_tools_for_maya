# -*- coding: utf-8 -*-
"""
MMD XPBD 物理演算エンジン Maya ブリッジモジュール (スカート・揺れもの完全安定化版)
blender_mmd_tools の剛体・ボーン同期仕様に準拠し、
OpenMaya API による厳密な階層マトリクス計算とオイラー角連続性維持 (closestSolution) により、
オイラー角フリップやフィードバック自己増幅によるメッシュ破綻・爆発を完全に排除します。
"""

import os
import sys
import math
import maya.cmds as mc
import maya.api.OpenMaya as om

from .xpbd_wrapper import XpbdEngineWrapper
from .xpbd_visualizer import sync_visualizer_transforms, mute_dynamic_constraints, VIS_GROUP_NAME, map_pmx_bones_to_maya, reconnect_visualizers_to_bones
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

def get_dag_path(node_name):
    """ノード名から OpenMaya MDagPath を取得"""
    sel = om.MSelectionList()
    sel.add(node_name)
    return sel.getDagPath(0)

class XpbdMayaBridge:
    """
    MayaとXPBD物理エンジン間のデータ送受信およびベイク制御クラス
    """
    def __init__(self, scale=8.0):
        self.scale = scale
        self.engine = None
        self.pmx_model = None
        self.bone_mapping = {}      # bone_index -> maya_joint_node
        self.rb_to_bone = {}        # rb_index -> bone_index
        self.dynamic_rb_indices = []
        self.kinematic_and_aligned_rb_indices = []

        # 剛体の初期ワールド姿勢 (rb_index -> (pos, quat))
        self.rb_initial_trans = {}
        # ボーンに対する剛体の初期相対オフセット (rb_index -> (local_pos, local_quat))
        self.rb_local_offsets = {}
        # ボーンの初期ワールド姿勢 (bone_index -> (world_pos, world_quat))
        self.bone_base_world_trans = {}

        # 事前サンプリングされたアニメーション姿勢キャッシュ (frame -> {rb_idx: (world_pos, world_quat)})
        self.anim_cache = {}

    def initialize_from_pmx(self, pmx_path, model_root=None):
        """
        PMXファイルから剛体・ジョイント情報をロードし、XPBDエンジンに初期登録
        """
        if not os.path.exists(pmx_path):
            raise FileNotFoundError(f"PMXファイルが見つかりません: {pmx_path}")

        print(f"[XPBD] PMX物理データをロード中: {pmx_path}")
        self.pmx_model = pmx.load(pmx_path)

        if not self.pmx_model.rigid_bodies:
            print("[XPBD] このPMXモデルには剛体データが存在しません。")
            return False

        # XPBDエンジンの初期化
        if self.engine:
            self.engine.close()
        self.engine = XpbdEngineWrapper()
        self.engine.clear()

        # Mayaシーン内のボーンノードを厳密に対応付け
        self._map_maya_bones(model_root)

        # キャッシュのクリア
        self.rb_to_bone.clear()
        self.dynamic_rb_indices.clear()
        self.kinematic_and_aligned_rb_indices.clear()
        self.rb_initial_trans.clear()
        self.rb_local_offsets.clear()
        self.bone_base_world_trans.clear()
        self.anim_cache.clear()

        # 開始フレームに移動して初期姿勢を同期
        start_frame = int(mc.playbackOptions(query=True, minTime=True))
        mc.currentTime(start_frame, edit=True, update=True)

        for rb_idx, rb in enumerate(self.pmx_model.rigid_bodies):
            # PMXバインドポーズにおける絶対座標・回転 (MMDからMayaへの座標・スケール変換: Z反転)
            rb_bind_p = (
                rb.position[0] * self.scale,
                rb.position[1] * self.scale,
                -rb.position[2] * self.scale
            )
            deg_x = math.degrees(rb.rotation[0])
            deg_y = math.degrees(rb.rotation[1])
            deg_z = -math.degrees(rb.rotation[2])
            rb_bind_q = quat_from_euler_xyz(deg_x, deg_y, deg_z)

            size = (
                rb.size[0] * self.scale,
                rb.size[1] * self.scale,
                rb.size[2] * self.scale
            )

            self.rb_to_bone[rb_idx] = rb.bone_index

            # PMXバインドデータからボーンに対する厳密なローカルオフセットを算出
            # (アニメーション移動量によるオフセット破壊を完全防止)
            b_idx = rb.bone_index
            if 0 <= b_idx < len(self.pmx_model.bones):
                bone = self.pmx_model.bones[b_idx]
                bone_loc = getattr(bone, 'location', getattr(bone, 'position', [0.0, 0.0, 0.0]))
                b_bind_p = (
                    bone_loc[0] * self.scale,
                    bone_loc[1] * self.scale,
                    -bone_loc[2] * self.scale
                )
                local_p = (rb_bind_p[0] - b_bind_p[0], rb_bind_p[1] - b_bind_p[1], rb_bind_p[2] - b_bind_p[2])
                local_q = rb_bind_q
            else:
                local_p = (0.0, 0.0, 0.0)
                local_q = rb_bind_q

            self.rb_local_offsets[rb_idx] = (local_p, local_q)

            # 開始フレームにおけるボーンの現在ワールド姿勢から剛体の初期ワールド姿勢を算出
            if b_idx in self.bone_mapping:
                j_node = self.bone_mapping[b_idx]
                if mc.objExists(j_node):
                    try:
                        mc.getAttr(f"{j_node}.worldMatrix[0]")
                    except Exception:
                        pass
                    b_pos = mc.xform(j_node, query=True, worldSpace=True, translation=True)
                    b_rot = mc.xform(j_node, query=True, worldSpace=True, rotation=True)
                    b_quat = quat_from_euler_xyz(b_rot[0], b_rot[1], b_rot[2])

                    world_p = quat_rotate_vector(b_quat, local_p)
                    init_pos = (b_pos[0] + world_p[0], b_pos[1] + world_p[1], b_pos[2] + world_p[2])
                    init_quat = quat_multiply(b_quat, local_q)
                    self.bone_base_world_trans[b_idx] = (b_pos, b_quat)
                else:
                    init_pos = rb_bind_p
                    init_quat = rb_bind_q
            else:
                init_pos = rb_bind_p
                init_quat = rb_bind_q

            self.rb_initial_trans[rb_idx] = (init_pos, init_quat)
            init_euler_deg = quat_to_euler_xyz(init_quat)
            init_euler_rad = (math.radians(init_euler_deg[0]), math.radians(init_euler_deg[1]), math.radians(init_euler_deg[2]))

            # エンジンへ剛体追加 (開始フレームの正しい位置・姿勢で登録)
            self.engine.add_rigidbody(
                bone_index=rb.bone_index,
                shape_type=rb.shape_type,
                physics_mode=rb.physics_mode,
                size=size,
                position=init_pos,
                rotation_euler=init_euler_rad,
                mass=rb.mass,
                linear_damping=max(0.1, float(rb.linear_damping)),
                angular_damping=max(0.1, float(rb.angular_damping)),
                restitution=rb.restitution,
                friction=rb.friction,
                group=rb.group,
                collision_mask=rb.collision_mask
            )

            # 剛体分類
            # ボーン追従剛体 (Kinematic: タイプ0) および 位置合わせ剛体 (Aligned: タイプ2)
            if rb.physics_mode in [0, 2]:
                self.kinematic_and_aligned_rb_indices.append(rb_idx)

            # ベイク対象剛体 (物理演算: タイプ1, 位置合わせ: タイプ2)
            if rb.physics_mode in [1, 2]:
                self.dynamic_rb_indices.append(rb_idx)

        # ジョイントの登録 (剛体Aの開始フレーム姿勢に合わせてジョイントも正確に配置)
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
                body_a=j.rigid_body_a,
                body_b=j.rigid_body_b,
                position=current_j_pos,
                rotation_euler=current_j_rot,
                linear_limit_min=min_t,
                linear_limit_max=max_t,
                angular_limit_min=min_r,
                angular_limit_max=max_r,
                linear_spring=sp_t,
                angular_spring=sp_r
            )

        # 動的ボーンをMayaの階層深度順（親から子へ）にソート
        self._sort_dynamic_bones_by_hierarchy()

        print(f"[XPBD] 初期化完了: 剛体 {self.engine.get_rigidbody_count()} 個, ジョイント {self.engine.get_joint_count()} 個")
        return True

    def _map_maya_bones(self, model_root=None):
        """
        Mayaシーン内のジョイントを探索し、PMXボーンを高精度に紐付け
        プレフィックス剥離、ローマ字変換、スカートボーン特殊規則に対応
        """
        self.bone_mapping.clear()
        all_joints = mc.ls(type="joint", long=True) or []
        self.bone_mapping = map_pmx_bones_to_maya(self.pmx_model.bones, all_joints)
        print(f"[XPBD] ボーン紐付け完了: {len(self.bone_mapping)} / {len(self.pmx_model.bones)} ボーン")

    def _sort_dynamic_bones_by_hierarchy(self):
        """
        ベイク処理時に親ボーンから子ボーンの順序で更新できるよう、階層深度でソート
        """
        def get_depth(rb_idx):
            b_idx = self.rb_to_bone.get(rb_idx, -1)
            j_node = self.bone_mapping.get(b_idx, "")
            return len(j_node.split('|')) if j_node else 0

        self.dynamic_rb_indices.sort(key=get_depth)

    def _cache_animated_bone_transforms(self, start_frame, end_frame):
        """
        全タイムラインにわたり、身体ボーン等の初期アニメーション姿勢を事前サンプリングしてキャッシュ
        ベイク処理によるボーン姿勢変更が次フレームの剛体同期にフィードバック混入する現象を完全遮断
        """
        self.anim_cache.clear()
        print(f"[XPBD] アニメーション姿勢の事前キャッシュ開始: フレーム {start_frame} ～ {end_frame}")

        # サンプリング対象となるボーン
        target_rbs = self.kinematic_and_aligned_rb_indices

        orig_time = mc.currentTime(query=True)
        for f in range(start_frame, end_frame + 1):
            mc.currentTime(f, edit=True, update=True)
            frame_data = {}
            for rb_idx in target_rbs:
                b_idx = self.rb_to_bone.get(rb_idx, -1)
                if b_idx in self.bone_mapping:
                    j_node = self.bone_mapping[b_idx]
                    if mc.objExists(j_node):
                        # worldMatrix プラグの評価をトリガーしてIKソルバーおよび親子DAGを強制更新
                        try:
                            mc.getAttr(f"{j_node}.worldMatrix[0]")
                        except Exception:
                            pass

                        b_pos = mc.xform(j_node, query=True, worldSpace=True, translation=True)
                        b_rot = mc.xform(j_node, query=True, worldSpace=True, rotation=True)
                        b_quat = quat_from_euler_xyz(b_rot[0], b_rot[1], b_rot[2])

                        if rb_idx in self.rb_local_offsets:
                            local_p, local_q = self.rb_local_offsets[rb_idx]
                            world_p = quat_rotate_vector(b_quat, local_p)
                            final_pos = (b_pos[0] + world_p[0], b_pos[1] + world_p[1], b_pos[2] + world_p[2])
                            final_quat = quat_multiply(b_quat, local_q)
                        else:
                            final_pos = b_pos
                            final_quat = b_quat

                        frame_data[rb_idx] = (final_pos, final_quat)
            self.anim_cache[f] = frame_data

        mc.currentTime(orig_time, edit=True)
        print("[XPBD] アニメーション姿勢の事前キャッシュ完了")

    def bake_simulation(self, start_frame=None, end_frame=None, gravity_y=-980.0, substeps=10):
        """
        タイムライン上でXPBD物理シミュレーションを実行し、Mayaボーンへキーフレームをベイク
        """
        if not self.engine or self.engine.get_rigidbody_count() == 0:
            raise RuntimeError("XPBDエンジンが初期化されていません。")

        if start_frame is None:
            min_t = int(mc.playbackOptions(query=True, minTime=True))
            start_frame = min(0, min_t)
        if end_frame is None:
            end_frame = int(mc.playbackOptions(query=True, maxTime=True))

        print(f"[XPBD] 物理シミュレーション開始: フレーム {start_frame} ～ {end_frame} (Substeps: {substeps})")

        # Dynamic剛体の追従コンストレイントを無効化（物理計算と競合させないため）
        mute_dynamic_constraints(mute=True)

        # アニメーションボーンの事前キャッシュを作成（自己増幅フィードバックの完全遮断）
        self._cache_animated_bone_transforms(start_frame, end_frame)

        # 重力設定
        self.engine.set_gravity(0.0, float(gravity_y), 0.0)

        # FPS取得
        fps_map = {
            'game': 15.0, 'film': 24.0, 'pal': 25.0, 'ntsc': 30.0,
            'show': 48.0, 'palf': 50.0, 'ntscf': 60.0
        }
        time_unit = mc.currentUnit(query=True, time=True)
        fps = fps_map.get(time_unit, 30.0)
        dt = 1.0 / fps

        # 初期姿勢の同期（開始フレーム）
        mc.currentTime(start_frame, edit=True)
        self._sync_animated_bodies_from_cache(start_frame)
        self.engine.reset()

        # 各ボーンの前回オイラー角キャッシュ (ジンバルロック・180度フリップ防止用)
        prev_eulers = {}

        # 1. 開始フレーム（フレーム0）における初期姿勢のキーフレーム記録
        # ステップ実行は行わず、初期状態の美しいバインド姿勢をフレーム0に記録
        self._apply_dynamic_bodies_to_maya(start_frame, prev_eulers)
        if mc.objExists(VIS_GROUP_NAME):
            all_trans = {}
            for idx in range(self.engine.get_rigidbody_count()):
                t = self.engine.get_rigidbody_transform(idx)
                if t:
                    all_trans[idx] = t
            sync_visualizer_transforms(all_trans, frame=start_frame)

        # 2. フレーム1以降の物理シミュレーションループ (0→1フレームから自然に動き始める)
        for f in range(start_frame + 1, end_frame + 1):
            mc.currentTime(f, edit=True)

            # キャッシュからクリーンなボーン位置・回転を同期
            self._sync_animated_bodies_from_cache(f)

            # XPBDステップ実行 (前フレームからのボーン移動量を受けて自然に揺れ動く)
            self.engine.step_simulation(dt=dt, substeps=substeps)

            # Dynamic剛体の揺れを階層マトリクス計算によりMayaボーンへベイク
            self._apply_dynamic_bodies_to_maya(f, prev_eulers)

            # 可視化ノードが存在する場合、全剛体の姿勢をビューポート上にキーフレーム記録
            if mc.objExists(VIS_GROUP_NAME):
                all_trans = {}
                for idx in range(self.engine.get_rigidbody_count()):
                    t = self.engine.get_rigidbody_transform(idx)
                    if t:
                        all_trans[idx] = t
                sync_visualizer_transforms(all_trans, frame=f)

        # 3. ベイク完了後、剛体・Joint可視化ノードのキーフレームをクリアし、ボーン追従を完全復元
        reconnect_visualizers_to_bones()
        print("[XPBD] 物理シミュレーションベイクが完了しました！剛体・Jointをモデルに再吸着しました。")

    def _sync_animated_bodies_from_cache(self, frame):
        """
        事前キャッシュされたクリーンなアニメーションデータから、Kinematic/Aligned剛体の姿勢を設定
        """
        frame_data = self.anim_cache.get(frame, {})
        for rb_idx, (pos, quat) in frame_data.items():
            self.engine.set_rigidbody_transform(rb_idx, pos, quat)

    def _apply_dynamic_bodies_to_maya(self, frame, prev_eulers):
        """
        OpenMayaマトリクス演算により、剛体のワールド回転を親階層・jointOrientを考慮した
        厳密なローカルオイラー角に変換し、最短連続角(closestSolution)を維持してベイク
        """
        for rb_idx in self.dynamic_rb_indices:
            b_idx = self.rb_to_bone.get(rb_idx, -1)
            if b_idx not in self.bone_mapping:
                continue

            j_node = self.bone_mapping[b_idx]
            if not mc.objExists(j_node):
                continue

            trans = self.engine.get_rigidbody_transform(rb_idx)
            if not trans:
                continue

            _, current_quat = trans

            # 剛体の現在ワールド回転からボーンの目標ワールド回転を算出
            # Q_target = Q_current * inv(Q_offset)
            if rb_idx in self.rb_local_offsets:
                _, local_q = self.rb_local_offsets[rb_idx]
                target_world_quat = quat_multiply(current_quat, quat_inverse(local_q))
            else:
                target_world_quat = current_quat

            target_world_quat = quat_normalize(target_world_quat)

            # OpenMayaによる厳密なローカル回転計算
            try:
                j_dag = get_dag_path(j_node)

                # 親ノードのワールド逆行列を取得
                parent_nodes = mc.listRelatives(j_node, parent=True, fullPath=True)
                if parent_nodes:
                    parent_dag = get_dag_path(parent_nodes[0])
                    parent_inv_mat = parent_dag.inclusiveMatrixInverse()
                else:
                    parent_inv_mat = om.MMatrix()

                # 目標ワールド回転行列
                target_om_q = om.MQuaternion(target_world_quat[0], target_world_quat[1], target_world_quat[2], target_world_quat[3])
                target_mat = target_om_q.asMatrix()

                # 親空間におけるローカル行列
                local_mat = target_mat * parent_inv_mat
                local_trans = om.MTransformationMatrix(local_mat)
                local_q = local_trans.rotation(asQuaternion=True)

                # ジョイントの jointOrient を相殺
                jo = mc.getAttr(f"{j_node}.jointOrient")[0]
                jo_e = om.MEulerRotation(math.radians(jo[0]), math.radians(jo[1]), math.radians(jo[2]), om.MEulerRotation.kXYZ)
                inv_jo_q = jo_e.asQuaternion().inverse()

                # ジョイントの rotateAxis を相殺
                ra = mc.getAttr(f"{j_node}.rotateAxis")[0]
                ra_e = om.MEulerRotation(math.radians(ra[0]), math.radians(ra[1]), math.radians(ra[2]), om.MEulerRotation.kXYZ)
                inv_ra_q = ra_e.asQuaternion().inverse()

                # ボーン自身の純粋なローカル回転クォータニオン
                bone_rot_q = inv_jo_q * local_q * inv_ra_q

                # ジョイントの rotateOrder を適用してオイラー角へ変換
                ro = mc.getAttr(f"{j_node}.rotateOrder")
                bone_euler = bone_rot_q.asEulerRotation()
                bone_euler.reorderIt(ro)

                # 前フレームからの最短連続角度を維持 (180度フリップ・裏返りを完全防止)
                if j_node in prev_eulers:
                    bone_euler = bone_euler.closestSolution(prev_eulers[j_node])
                prev_eulers[j_node] = bone_euler

                # 角度を度数法に変換して直接属性に設定
                deg_x = math.degrees(bone_euler.x)
                deg_y = math.degrees(bone_euler.y)
                deg_z = math.degrees(bone_euler.z)

                mc.setAttr(f"{j_node}.rotateX", deg_x)
                mc.setAttr(f"{j_node}.rotateY", deg_y)
                mc.setAttr(f"{j_node}.rotateZ", deg_z)
                mc.setKeyframe(j_node, attribute=['rotateX', 'rotateY', 'rotateZ'], time=frame)

            except Exception as e:
                # 計算例外時の安全フォールバック
                euler_deg = quat_to_euler_xyz(target_world_quat)
                try:
                    mc.xform(j_node, worldSpace=True, rotation=euler_deg)
                    mc.setKeyframe(j_node, attribute=['rotateX', 'rotateY', 'rotateZ'], time=frame)
                except Exception:
                    pass

        # 可視化ノードのキーフレームもクリア
        if mc.objExists(VIS_GROUP_NAME):
            try:
                mc.cutKey(VIS_GROUP_NAME, hierarchy='below', attribute=['translateX', 'translateY', 'translateZ', 'rotateX', 'rotateY', 'rotateZ'])
            except Exception:
                pass
        # Dynamic追従コンストレイントを通常状態に復帰
        mute_dynamic_constraints(mute=False)
        print("[XPBD] 物理対象ボーンのキーフレームをクリアしました。")
