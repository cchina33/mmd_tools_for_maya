# -*- coding: utf-8 -*-
"""
Maya 標準 Bullet Physics 自動リグ構築モジュール
PMXモデルの剛体・ジョイントデータをMaya標準のBullet物理エンジン
(bulletRigidBodyShape, bulletRigidBodyConstraint, bulletSolverShape) に自動変換・接続し、
Mayaのタイムライン再生（インタラクティブ）による物理シミュレーションを実現します。
"""

import math
import maya.cmds as mc
import maya.mel as mel
import maya.api.OpenMaya as om
from .mmd_core import pmx

BULLET_ROOT_GROUP = "MMD_Bullet_Physics_Rig"

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

def is_bullet_available():
    """MayaのBullet物理プラグインがロード可能か検証"""
    if not mc.pluginInfo("bullet", query=True, loaded=True):
        try:
            mc.loadPlugin("bullet", quiet=True)
        except Exception as e:
            print(f"[Bullet] プラグイン 'bullet' のロードに失敗しました: {e}")
            return False
    return True

def remove_bullet_rig():
    """既存のBullet物理リグをクリーンアップ"""
    if mc.objExists(BULLET_ROOT_GROUP):
        mc.delete(BULLET_ROOT_GROUP)
        print(f"[Bullet] 既存の物理リグ '{BULLET_ROOT_GROUP}' を削除しました。")

def build_bullet_rig(pmx_path, scale=8.0):
    """
    PMX剛体・ジョイントからMaya標準Bullet物理ネットワークを構築
    """
    if not is_bullet_available():
        raise RuntimeError("MayaのBullet物理プラグイン（bullet.mll）が利用できません。プラグインマネージャで有効化してください。")

    remove_bullet_rig()

    # タイムライン開始フレームを0に設定
    mc.playbackOptions(minTime=0, animationStartTime=0)
    mc.currentTime(0)

    model = pmx.load(pmx_path)
    if not model.rigid_bodies:
        raise RuntimeError("PMXモデルに剛体データが存在しません。")

    # ルートグループの作成
    root_grp = mc.group(empty=True, name=BULLET_ROOT_GROUP)

    # Bulletソルバーの取得または作成
    solvers = mc.ls(type="bulletSolverShape")
    if not solvers:
        solver_transform = mc.createNode("transform", name="MMD_BulletSolver", parent=root_grp)
        solver_shape = mc.createNode("bulletSolverShape", name="MMD_BulletSolverShape", parent=solver_transform)
        # 重力設定 (cm/s^2)
        mc.setAttr(f"{solver_shape}.gravityY", -980.0)
    else:
        solver_shape = solvers[0]

    # ボーン名からMayaジョイントへのマッピング
    all_joints = mc.ls(type="joint", long=True) or []
    name_to_joint = {}
    for j_node in all_joints:
        if mc.attributeQuery("originalName", node=j_node, exists=True):
            orig = mc.getAttr(f"{j_node}.originalName")
            if orig:
                name_to_joint[orig] = j_node
        else:
            short_name = j_node.split('|')[-1]
            name_to_joint[short_name] = j_node

    bone_idx_to_joint = {}
    for b_idx, bone in enumerate(model.bones):
        if bone.name in name_to_joint:
            bone_idx_to_joint[b_idx] = name_to_joint[bone.name]

    created_rbs = {}

    # 1. 剛体ノードの構築
    for idx, rb in enumerate(model.rigid_bodies):
        rb_bind_p = (
            rb.position[0] * scale,
            rb.position[1] * scale,
            -rb.position[2] * scale
        )
        deg_x = math.degrees(rb.rotation[0])
        deg_y = math.degrees(rb.rotation[1])
        deg_z = -math.degrees(rb.rotation[2])
        e = om.MEulerRotation(math.radians(deg_x), math.radians(deg_y), math.radians(deg_z), om.MEulerRotation.kXYZ)
        rb_bind_q = e.asQuaternion()

        b_idx = rb.bone_index
        if 0 <= b_idx < len(model.bones):
            bone = model.bones[b_idx]
            bone_loc = getattr(bone, 'location', getattr(bone, 'position', [0.0, 0.0, 0.0]))
            b_bind_p = (
                bone_loc[0] * scale,
                bone_loc[1] * scale,
                -bone_loc[2] * scale
            )
            local_p = (rb_bind_p[0] - b_bind_p[0], rb_bind_p[1] - b_bind_p[1], rb_bind_p[2] - b_bind_p[2])
            local_q = rb_bind_q
        else:
            local_p = (0.0, 0.0, 0.0)
            local_q = rb_bind_q

        target_j = bone_idx_to_joint.get(b_idx)
        if target_j and mc.objExists(target_j):
            b_pos = mc.xform(target_j, query=True, worldSpace=True, translation=True)
            b_rot = mc.xform(target_j, query=True, worldSpace=True, rotation=True)
            be = om.MEulerRotation(math.radians(b_rot[0]), math.radians(b_rot[1]), math.radians(b_rot[2]), om.MEulerRotation.kXYZ)
            bq = be.asQuaternion()
            b_quat_tuple = (bq.x, bq.y, bq.z, bq.w)

            world_p = quat_rotate_vector(b_quat_tuple, local_p)
            pos = (b_pos[0] + world_p[0], b_pos[1] + world_p[1], b_pos[2] + world_p[2])
            final_q_tuple = quat_multiply(b_quat_tuple, local_q)
            final_mq = om.MQuaternion(final_q_tuple[0], final_q_tuple[1], final_q_tuple[2], final_q_tuple[3])
            fe = final_mq.asEulerRotation()
            rot = (math.degrees(fe.x), math.degrees(fe.y), math.degrees(fe.z))
        else:
            pos = rb_bind_p
            rot = (deg_x, deg_y, deg_z)

        safe_name = rb.name.replace(" ", "_").replace("|", "_").replace(":", "_")
        mesh_name = f"bullet_rb_{idx:03d}_{safe_name}"

        # コライダー形状メッシュ生成
        if rb.shape_type == 0:
            # 球
            r = max(0.1, rb.size[0] * scale)
            mesh = mc.polySphere(radius=r, subdivisionsX=8, subdivisionsY=6, name=mesh_name)[0]
            col_shape_type = 1 # Sphere
        elif rb.shape_type == 1:
            # 箱
            w = max(0.1, rb.size[0] * 2.0 * scale)
            h = max(0.1, rb.size[1] * 2.0 * scale)
            d = max(0.1, rb.size[2] * 2.0 * scale)
            mesh = mc.polyCube(width=w, height=h, depth=d, name=mesh_name)[0]
            col_shape_type = 0 # Box
        else:
            # カプセル
            r = max(0.1, rb.size[0] * scale)
            h = max(0.1, rb.size[1] * scale)
            mesh = mc.polyCylinder(radius=r, height=h, subdivisionsX=8, subdivisionsY=1, name=mesh_name)[0]
            col_shape_type = 2 # Capsule

        mc.xform(mesh, worldSpace=True, translation=pos)
        mc.xform(mesh, worldSpace=True, rotation=rot)

        # Bullet剛体シェイプの作成
        rb_shape = mc.createNode("bulletRigidBodyShape", name=f"{mesh_name}Shape_bullet", parent=mesh)
        mc.connectAttr("time1.outTime", f"{rb_shape}.currentTime")

        # ソルバーへ接続
        try:
            solver_msg = f"{solver_shape}.message"
            mc.connectAttr(solver_msg, f"{rb_shape}.solverMsg")
        except Exception:
            pass

        # 物理プロパティの設定
        # physics_mode: 0=Kinematic, 1=Dynamic, 2=Aligned
        is_kinematic = (rb.physics_mode == 0)
        body_type = 2 if is_kinematic else 1 # 1: Dynamic, 2: Kinematic
        mc.setAttr(f"{rb_shape}.bodyType", body_type)
        mc.setAttr(f"{rb_shape}.colliderShapeType", col_shape_type)
        mc.setAttr(f"{rb_shape}.mass", float(rb.mass) if not is_kinematic else 0.0)
        mc.setAttr(f"{rb_shape}.linearDamping", max(0.1, float(rb.linear_damping)))
        mc.setAttr(f"{rb_shape}.angularDamping", max(0.1, float(rb.angular_damping)))
        mc.setAttr(f"{rb_shape}.restitution", float(rb.restitution))
        mc.setAttr(f"{rb_shape}.friction", float(rb.friction))

        # 衝突マージンを極小化 (Blenderの0.000001m仕様に準拠し、スカートの不要な浮き上がり・押し合いを排除)
        for margin_attr in ["colliderShapeMargin", "collisionMargin", "margin"]:
            if mc.attributeQuery(margin_attr, node=rb_shape, exists=True):
                try:
                    mc.setAttr(f"{rb_shape}.{margin_attr}", 0.001)
                except Exception:
                    pass

        # ワイヤーフレーム表示に設定
        mesh_shape = mc.listRelatives(mesh, shapes=True, type="mesh")[0]
        mc.setAttr(f"{mesh_shape}.overrideEnabled", 1)
        mc.setAttr(f"{mesh_shape}.overrideShading", 0)
        # 色分け: Kinematic=青(6), Dynamic=緑(14), Aligned=黄(17)
        color_idx = 6 if rb.physics_mode == 0 else (14 if rb.physics_mode == 1 else 17)
        mc.setAttr(f"{mesh_shape}.overrideColor", color_idx)

        # ボーン追従設定 (Kinematic)
        if is_kinematic and rb.bone_index in bone_idx_to_joint:
            target_j = bone_idx_to_joint[rb.bone_index]
            if mc.objExists(target_j):
                mc.parentConstraint(target_j, mesh, maintainOffset=True)

        # 物理駆動ボーン (Dynamic)
        if not is_kinematic and rb.bone_index in bone_idx_to_joint:
            target_j = bone_idx_to_joint[rb.bone_index]
            if mc.objExists(target_j):
                # 剛体の回転をボーンに連動
                try:
                    mc.orientConstraint(mesh, target_j, maintainOffset=True)
                except Exception:
                    pass

        mc.parent(mesh, root_grp)
        created_rbs[idx] = mesh

    # 2. ジョイント（コンストレイント）の構築
    for j_idx, j in enumerate(model.joints):
        rb_a_node = created_rbs.get(j.rigid_body_a)
        rb_b_node = created_rbs.get(j.rigid_body_b)
        if not rb_a_node or not rb_b_node:
            continue

        c_name = f"bullet_joint_{j_idx:03d}_{j.name.replace(' ', '_')}"
        pos = (
            j.position[0] * scale,
            j.position[1] * scale,
            -j.position[2] * scale
        )

        loc = mc.spaceLocator(name=c_name)[0]
        mc.xform(loc, worldSpace=True, translation=pos)

        c_shape = mc.createNode("bulletRigidBodyConstraint", name=f"{c_name}Shape", parent=loc)
        mc.setAttr(f"{c_shape}.constraintType", 6) # 6DOF Generic Constraint

        # ボディA、Bの接続
        rb_a_shape = mc.listRelatives(rb_a_node, shapes=True, type="bulletRigidBodyShape")[0]
        rb_b_shape = mc.listRelatives(rb_b_node, shapes=True, type="bulletRigidBodyShape")[0]

        try:
            mc.connectAttr(f"{rb_a_shape}.rigidBodyMsg", f"{c_shape}.rigidBodyAMsg")
            mc.connectAttr(f"{rb_b_shape}.rigidBodyMsg", f"{c_shape}.rigidBodyBMsg")
            mc.connectAttr(f"{solver_shape}.message", f"{c_shape}.solverMsg")
        except Exception:
            pass

        # 制限・バネ設定
        mc.setAttr(f"{c_shape}.angularConstraintMinX", math.degrees(j.angular_limit_min[0]))
        mc.setAttr(f"{c_shape}.angularConstraintMaxX", math.degrees(j.angular_limit_max[0]))
        mc.setAttr(f"{c_shape}.angularConstraintMinY", math.degrees(j.angular_limit_min[1]))
        mc.setAttr(f"{c_shape}.angularConstraintMaxY", math.degrees(j.angular_limit_max[1]))
        mc.setAttr(f"{c_shape}.angularConstraintMinZ", -math.degrees(j.angular_limit_max[2]))
        mc.setAttr(f"{c_shape}.angularConstraintMaxZ", -math.degrees(j.angular_limit_min[2]))

        mc.parent(loc, root_grp)

    print(f"[Bullet] 物理リグの構築が完了しました: 剛体 {len(created_rbs)} 個, ジョイント {len(model.joints)} 個")
    return True
