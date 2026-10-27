# -*- coding: utf-8 -*-
"""
MMD 剛体・ジョイント デバッグ可視化モジュール
PMX剛体（球・箱・カプセル）およびJoint（6DOFスプリング関節）をMayaビューポート上に
ワイヤーフレーム表示し、アニメーション追従および物理シミュレーションをリアルタイムに目視確認できるようにします。
"""

import os
import json
import math
import maya.cmds as mc
import maya.api.OpenMaya as om
from ..mmd_core import pmx
from ..asset.jaka import safe_node_name
from ..asset.bone_dict import get_english_bone_name, get_japanese_bone_name

ROOT_VIS_GROUP_NAME = "MMD_RigidBody_Joint_Visualizers"
RB_VIS_GROUP_NAME = "MMD_RigidBody_Visualizers"
JOINT_VIS_GROUP_NAME = "MMD_Joint_Visualizers"
VIS_GROUP_NAME = ROOT_VIS_GROUP_NAME

def quat_from_euler_xyz(rx_deg, ry_deg, rz_deg):
    """XYZオイラー角から四元数を算出"""
    e = om.MEulerRotation(math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg), om.MEulerRotation.kXYZ)
    q = e.asQuaternion()
    return (q.x, q.y, q.z, q.w)

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

def quat_to_euler_xyz(q):
    """四元数からXYZオイラー角を算出"""
    mq = om.MQuaternion(q[0], q[1], q[2], q[3])
    e = mq.asEulerRotation()
    return (math.degrees(e.x), math.degrees(e.y), math.degrees(e.z))

def create_capsule_visualizer(radius, height, name):
    """PMXViewと同等の円柱＋両端半球を持つカプセルワイヤーフレームメッシュを生成"""
    r = max(0.01, float(radius))
    h = max(0.01, float(height))
    half_h = h * 0.5
    try:
        cyl = mc.polyCylinder(radius=r, height=h, subdivisionsX=12, subdivisionsY=1, subdivisionsCaps=0, constructionHistory=False)[0]
        sph_top = mc.polySphere(radius=r, subdivisionsX=12, subdivisionsY=8, constructionHistory=False)[0]
        mc.xform(sph_top, translation=(0.0, half_h, 0.0))
        sph_bottom = mc.polySphere(radius=r, subdivisionsX=12, subdivisionsY=8, constructionHistory=False)[0]
        mc.xform(sph_bottom, translation=(0.0, -half_h, 0.0))
        capsule = mc.polyUnite(cyl, sph_top, sph_bottom, constructionHistory=False, name=name)[0]
        return capsule
    except Exception:
        return mc.polyCylinder(radius=r, height=h, subdivisionsX=12, subdivisionsY=1, name=name, constructionHistory=False)[0]

def remove_visualizers():
    """既存の剛体・ジョイント可視化ノードを削除"""
    for grp in [ROOT_VIS_GROUP_NAME, RB_VIS_GROUP_NAME, "MMD_RigidBody_Visualizers"]:
        if mc.objExists(grp):
            try:
                mc.delete(grp)
                print(f"[Visualizer] 既存の可視化グループ '{grp}' を削除しました。")
            except Exception:
                pass

def mute_dynamic_constraints(mute=True):
    """
    XPBD物理シミュレーションベイク時に、Dynamic剛体(緑・黄)およびJointの追従コンストレイントを
    一時無効化（または復元）して物理ソルバーの計算結果と競合しないように制御します。
    mute=True: コンストレイントをPassThrough（無効）に設定
    mute=False: 通常の追従状態に戻す
    """
    if not mc.objExists(ROOT_VIS_GROUP_NAME) and not mc.objExists(RB_VIS_GROUP_NAME):
        return

    constraints = mc.ls(type="parentConstraint") or []
    target_state = 1 if mute else 0 # 1: PassThrough, 0: Normal

    count = 0
    for c in constraints:
        if mc.attributeQuery("isMmdPhysicsConstraint", node=c, exists=True):
            rb_mode = mc.getAttr(f"{c}.rbMode") if mc.attributeQuery("rbMode", node=c, exists=True) else 0
            if rb_mode != 0: # Dynamic または Aligned
                mc.setAttr(f"{c}.nodeState", target_state)
                count += 1
        elif mc.attributeQuery("isMmdJointConstraint", node=c, exists=True):
            mc.setAttr(f"{c}.nodeState", target_state)
            count += 1

    action_str = "一時無効化" if mute else "復元"
    print(f"[Visualizer] 剛体・Joint追従コンストレイント {count} 個を{action_str}しました。")

def map_pmx_bones_to_maya(pmx_bones, all_joints=None):
    """
    PMXボーンリストとMayaシーン内のジョイントを多層照合（Multi-layer Fallback）し、
    bone_idx -> maya_joint_node のマッピング辞書を高精度に構築します。
    last_imported_structure.json、モデルプレフィックス（Apose_等）の剥離、
    日英標準ボーン辞書、ローマ字変換、スカートボーン特殊規則に対応。
    """
    if all_joints is None:
        all_joints = mc.ls(type="joint", long=True) or []

    if not all_joints or not pmx_bones:
        return {}

    bone_to_joint = {}

    # キャッシュファイル (last_imported_structure.json) の読み込み (新スキーマ2.0対応)
    cached_bones = {}
    cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'asset', 'last_imported_structure.json')
    if os.path.isfile(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cdata = json.load(f)
                raw_b = cdata.get('bones')
                if isinstance(raw_b, dict):
                    cached_bones = raw_b
                elif isinstance(raw_b, list):
                    for b in raw_b:
                        if isinstance(b, dict):
                            node = b.get('maya_node') or b.get('node')
                            if node:
                                if b.get('name_jp'):
                                    cached_bones[b['name_jp']] = node
                                if b.get('name_en'):
                                    cached_bones[b['name_en']] = node
                if not cached_bones and isinstance(cdata.get('legacy_compatibility', {}).get('bones'), dict):
                    cached_bones = cdata['legacy_compatibility']['bones']
        except Exception:
            pass

    # ジョイント情報の事前解析
    joint_info = []
    for j in all_joints:
        orig = mc.getAttr(f"{j}.originalName") if mc.attributeQuery("originalName", node=j, exists=True) else ""
        short = j.split('|')[-1]
        parts = short.split('_', 1)
        stripped = parts[1] if len(parts) > 1 else short
        joint_info.append({
            'node': j,
            'orig': orig,
            'short': short,
            'short_lower': short.lower(),
            'stripped': stripped,
            'stripped_lower': stripped.lower()
        })

    for b_idx, bone in enumerate(pmx_bones):
        b_name = bone.name
        b_name_e = getattr(bone, 'name_e', None)
        dict_en = get_english_bone_name(b_name)
        safe_name = safe_node_name(b_name, name_e=b_name_e, prefix="bone", index=b_idx)
        safe_lower = safe_name.lower()

        matched_j = None

        # 優先度-1: last_imported_structure.json からの直接照合
        if b_name in cached_bones and mc.objExists(cached_bones[b_name]):
            matched_j = cached_bones[b_name]
        elif b_name_e and b_name_e in cached_bones and mc.objExists(cached_bones[b_name_e]):
            matched_j = cached_bones[b_name_e]
        elif dict_en and dict_en in cached_bones and mc.objExists(cached_bones[dict_en]):
            matched_j = cached_bones[dict_en]

        # 優先度0: originalName による厳密一致
        if not matched_j:
            for info in joint_info:
                if info['orig'] and (info['orig'] == b_name or (b_name_e and info['orig'] == b_name_e) or (dict_en and info['orig'] == dict_en)):
                    matched_j = info['node']
                    break

        # 優先度1: short_name 厳密一致 (和名・英名・辞書英名)
        if not matched_j:
            for info in joint_info:
                if info['short'] == b_name or (b_name_e and info['short'] == b_name_e) or (dict_en and info['short'] == dict_en):
                    matched_j = info['node']
                    break

        # 優先度2: safe_node_name 一致 (プレフィックス除去またはサフィックス一致)
        if not matched_j:
            for info in joint_info:
                if info['stripped'] == safe_name or info['short'].endswith(f"_{safe_name}") or info['short'] == safe_name:
                    matched_j = info['node']
                    break

        # 優先度3: safe_node_name 小文字一致
        if not matched_j:
            for info in joint_info:
                if info['stripped_lower'] == safe_lower or info['short_lower'].endswith(f"_{safe_lower}"):
                    matched_j = info['node']
                    break

        # 優先度4: スカートボーン等 (半角カタカナ ｽｶｰﾄ_、全角 スカート_、Skirt_、q_)
        if not matched_j:
            skirt_key = None
            if b_name.startswith("ｽｶｰﾄ_") or b_name.startswith("スカート_"):
                parts = b_name.split("_")
                if len(parts) >= 3:
                    skirt_key = f"Skirt_{parts[1]}_{parts[2]}"
            elif b_name.startswith("q_"):
                skirt_key = b_name.replace("q_", "Skirt_")
            elif b_name.startswith("Skirt_"):
                skirt_key = b_name
            elif b_name_e and b_name_e.startswith("Skirt_"):
                skirt_key = b_name_e

            if skirt_key:
                for info in joint_info:
                    s_name = info['short']
                    if s_name == skirt_key or s_name.startswith(f"{skirt_key}_") or info['stripped'] == skirt_key or info['stripped'].startswith(f"{skirt_key}_"):
                        matched_j = info['node']
                        break

        if matched_j:
            bone_to_joint[b_idx] = matched_j

    return bone_to_joint

def create_rigidbody_visualizers(pmx_path, scale=8.0):
    """
    PMXファイルから剛体形状（球、箱、カプセル）およびJointのワイヤーフレームを生成
    アニメーション適用時も全剛体がボーンに正しく追従するようにバインドします。
    """
    remove_visualizers()

    # タイムライン開始フレームを0に設定し、カレント時間を0へ移動 (バインド姿勢・0フレーム初期ポーズを確実に基準化)
    try:
        mc.playbackOptions(minTime=0, animationStartTime=0)
        mc.currentTime(0)
    except Exception:
        pass

    model = pmx.load(pmx_path)
    if not model.rigid_bodies and not model.joints:
        print("[Visualizer] 剛体・ジョイントデータが存在しません。")
        return []

    # 最上位親グループと子グループ（剛体・Joint）を作成
    main_grp = mc.group(empty=True, name=ROOT_VIS_GROUP_NAME)
    rb_grp = mc.group(empty=True, name=RB_VIS_GROUP_NAME, parent=main_grp)
    joint_grp = mc.group(empty=True, name=JOINT_VIS_GROUP_NAME, parent=main_grp)

    # ボーン名からMayaジョイントへの高精度マッピング
    all_joints = mc.ls(type="joint", long=True) or []
    bone_idx_to_joint = map_pmx_bones_to_maya(model.bones, all_joints)
    print(f"[Visualizer] ボーン紐付け結果: {len(bone_idx_to_joint)} / {len(model.bones)} ボーン")

    created_nodes = {}
    rb_world_trans = {}

    # 剛体メッシュの生成とバインド
    for idx, rb in enumerate(model.rigid_bodies):
        # PMXバインドポーズにおける絶対座標・回転 (MMDからMayaへの座標系変換: Z反転)
        rb_bind_p = (
            rb.position[0] * scale,
            rb.position[1] * scale,
            -rb.position[2] * scale
        )
        deg_x = -math.degrees(rb.rotation[0])
        deg_y = -math.degrees(rb.rotation[1])
        deg_z = math.degrees(rb.rotation[2])
        rb_bind_q = quat_from_euler_xyz(deg_x, deg_y, deg_z)

        b_idx = rb.bone_index
        target_j = bone_idx_to_joint.get(b_idx)

        # PMX設計通りの整然とした初期バインド姿勢を採用
        pos = rb_bind_p
        rot = (deg_x, deg_y, deg_z)
        rb_world_trans[idx] = (pos, rb_bind_q)

        safe_name = safe_node_name(rb.name)
        node_name = f"rb_vis_{idx:03d}_{safe_name}"

        # 既存ノードとの重複を避けてRequested name警告を抑制
        if mc.objExists(node_name):
            try:
                mc.delete(node_name)
            except Exception:
                pass

        mesh_node = None
        # 形状別のワイヤーフレームジオメトリ生成 (PMXエディタ基準のサイズ・形状)
        if rb.shape_type == 0:
            # 球 (Sphere: 半径 size.x)
            r = rb.size[0] * scale
            mesh = mc.polySphere(radius=max(0.1, r), subdivisionsX=12, subdivisionsY=8, name=node_name, constructionHistory=False)[0]
            mesh_node = mesh
        elif rb.shape_type == 1:
            # 直方体 (Box: PMXのsizeは半サイズ -> 全幅 2*size)
            w = rb.size[0] * 2.0 * scale
            h = rb.size[1] * 2.0 * scale
            d = rb.size[2] * 2.0 * scale
            mesh = mc.polyCube(width=max(0.1, w), height=max(0.1, h), depth=max(0.1, d), name=node_name, constructionHistory=False)[0]
            mesh_node = mesh
        elif rb.shape_type == 2:
            # カプセル (Capsule: 半径 size.x, 高さ size.y / PMXView同等の丸みを持つ形状)
            r = rb.size[0] * scale
            h = rb.size[1] * scale
            mesh = create_capsule_visualizer(radius=r, height=h, name=node_name)
            mesh_node = mesh

        if not mesh_node:
            continue

        # 剛体用グループに格納
        mc.parent(mesh_node, rb_grp)

        # 初期姿勢の設定 (PMXエディタと寸分違わず整然と並ぶ設計姿勢)
        mc.xform(mesh_node, worldSpace=True, translation=pos)
        mc.xform(mesh_node, worldSpace=True, rotation=rot)

        # ワイヤーフレーム表示設定
        shapes = mc.listRelatives(mesh_node, shapes=True) or []
        for shape in shapes:
            mc.setAttr(f"{shape}.overrideEnabled", 1)
            mc.setAttr(f"{shape}.overrideShading", 0) # シェーディングOFF (ワイヤー表示)

            # 剛体タイプ別のカラーコード (Kinematic: 青, Dynamic: 緑, Aligned: 黄)
            if rb.physics_mode == 0:
                color_idx = 6  # 青
            elif rb.physics_mode == 1:
                color_idx = 14 # 緑
            else:
                color_idx = 17 # 黄
            mc.setAttr(f"{shape}.overrideColor", color_idx)

        # 識別用カスタムアトリビュート
        mc.addAttr(mesh_node, longName="rbIndex", attributeType="short", defaultValue=idx)
        mc.addAttr(mesh_node, longName="rbMode", attributeType="short", defaultValue=rb.physics_mode)
        mc.addAttr(mesh_node, longName="rbGroup", attributeType="short", defaultValue=rb.group)

        # 全ての剛体を対応ボーンにコンストレイントしてアニメーション追従
        if target_j and mc.objExists(target_j):
            try:
                c_res = mc.parentConstraint(target_j, mesh_node, maintainOffset=True)
                if c_res:
                    c_node = c_res[0]
                    mc.addAttr(c_node, longName="isMmdPhysicsConstraint", attributeType="bool", defaultValue=True)
                    mc.addAttr(c_node, longName="rbMode", attributeType="short", defaultValue=rb.physics_mode)
            except Exception:
                pass

        created_nodes[idx] = mesh_node

    # MMD Joint（スプリング関節）の可視化ノード生成 (PMXエディタと同仕様の四角い立方体キューブ)
    for j_idx, j in enumerate(model.joints):
        j_safe_name = safe_node_name(j.name)
        j_node_name = f"joint_vis_{j_idx:03d}_{j_safe_name}"

        if mc.objExists(j_node_name):
            try:
                mc.delete(j_node_name)
            except Exception:
                pass

        # PMXバインド空間でのJoint絶対座標・回転
        j_bind_p = (
            j.position[0] * scale,
            j.position[1] * scale,
            -j.position[2] * scale
        )
        j_deg_x = -math.degrees(j.rotation[0])
        j_deg_y = -math.degrees(j.rotation[1])
        j_deg_z = math.degrees(j.rotation[2])

        # PMXエディタと同仕様の四角い立方体 (キューブ) ワイヤーフレームを生成
        cube_size = max(0.4, 0.15 * scale)
        cube = mc.polyCube(width=cube_size, height=cube_size, depth=cube_size, name=j_node_name, constructionHistory=False)[0]

        # ジョイント用グループへ格納
        mc.parent(cube, joint_grp)

        # PMXバインド姿勢のワールド座標・回転を設定 (剛体間に整然と配置)
        mc.xform(cube, worldSpace=True, translation=j_bind_p)
        mc.xform(cube, worldSpace=True, rotation=(j_deg_x, j_deg_y, j_deg_z))

        # ワイヤーフレーム・黄色表示 (PMXエディタのJointアイコンと同等一致)
        cube_shape = mc.listRelatives(cube, shapes=True)[0]
        mc.setAttr(f"{cube_shape}.overrideEnabled", 1)
        mc.setAttr(f"{cube_shape}.overrideShading", 0) # ワイヤー表示
        mc.setAttr(f"{cube_shape}.overrideColor", 17) # 黄色 (PMXエディタ標準色)

        # 親剛体Aに対するローカルオフセット (シミュレーション変位同期用)
        j_local_p = (0.0, 0.0, 0.0)
        j_local_q = (0.0, 0.0, 0.0, 1.0)
        if 0 <= j.rigid_body_a < len(model.rigid_bodies):
            rb_a = model.rigid_bodies[j.rigid_body_a]
            rb_a_bind_p = (rb_a.position[0] * scale, rb_a.position[1] * scale, -rb_a.position[2] * scale)
            deg_ax = -math.degrees(rb_a.rotation[0])
            deg_ay = -math.degrees(rb_a.rotation[1])
            deg_az = math.degrees(rb_a.rotation[2])
            rb_a_bind_q = quat_from_euler_xyz(deg_ax, deg_ay, deg_az)

            inv_ra_q = quat_inverse(rb_a_bind_q)
            j_bind_q = quat_from_euler_xyz(j_deg_x, j_deg_y, j_deg_z)
            j_diff = (j_bind_p[0] - rb_a_bind_p[0], j_bind_p[1] - rb_a_bind_p[1], j_bind_p[2] - rb_a_bind_p[2])
            j_local_p = quat_rotate_vector(inv_ra_q, j_diff)
            j_local_q = quat_multiply(inv_ra_q, j_bind_q)

        # 識別用カスタムアトリビュート
        mc.addAttr(cube, longName="jointIndex", attributeType="short", defaultValue=j_idx)
        mc.addAttr(cube, longName="rbAIndex", attributeType="short", defaultValue=j.rigid_body_a)
        mc.addAttr(cube, longName="rbBIndex", attributeType="short", defaultValue=j.rigid_body_b)
        mc.addAttr(cube, longName="localOffsetX", attributeType="double", defaultValue=j_local_p[0])
        mc.addAttr(cube, longName="localOffsetY", attributeType="double", defaultValue=j_local_p[1])
        mc.addAttr(cube, longName="localOffsetZ", attributeType="double", defaultValue=j_local_p[2])
        mc.addAttr(cube, longName="localOffsetRotX", attributeType="double", defaultValue=j_local_q[0])
        mc.addAttr(cube, longName="localOffsetRotY", attributeType="double", defaultValue=j_local_q[1])
        mc.addAttr(cube, longName="localOffsetRotZ", attributeType="double", defaultValue=j_local_q[2])
        mc.addAttr(cube, longName="localOffsetRotW", attributeType="double", defaultValue=j_local_q[3])

        # 関連する剛体Aのボーンにコンストレイントしてアニメーション追従
        if 0 <= j.rigid_body_a < len(model.rigid_bodies):
            rb_a = model.rigid_bodies[j.rigid_body_a]
            target_j_a = bone_idx_to_joint.get(rb_a.bone_index)
            if target_j_a and mc.objExists(target_j_a):
                try:
                    c_res = mc.parentConstraint(target_j_a, cube, maintainOffset=True)
                    if c_res:
                        mc.addAttr(c_res[0], longName="isMmdJointConstraint", attributeType="bool", defaultValue=True)
                except Exception:
                    pass

    # 剛体の種別内訳をカウント
    k_count = sum(1 for rb in model.rigid_bodies if rb.physics_mode == 0)
    d_count = sum(1 for rb in model.rigid_bodies if rb.physics_mode == 1)
    a_count = sum(1 for rb in model.rigid_bodies if rb.physics_mode == 2)

    print("==================================================")
    print(f"[剛体・Joint生成] 剛体総数: {len(created_nodes)} 個")
    print(f"  - Kinematic (ボーン追従): {k_count} 個")
    print(f"  - Dynamic (物理シミュレーション): {d_count} 個")
    print(f"  - Aligned (物理+位置合わせ): {a_count} 個")
    print(f"[剛体・Joint生成] Joint (スプリング関節) 総数: {len(model.joints)} 個")
    print("==================================================")
    return created_nodes

def sync_visualizer_transforms(rb_transforms, frame=None):
    """
    シミュレーション中の剛体およびJointのワールド姿勢を可視化ノードに同期
    rb_transforms: dict (rb_idx -> (pos, quat))
    """
    if not mc.objExists(VIS_GROUP_NAME):
        return

    # 剛体メッシュの同期
    rb_target_grp = RB_VIS_GROUP_NAME if mc.objExists(RB_VIS_GROUP_NAME) else VIS_GROUP_NAME
    children = mc.listRelatives(rb_target_grp, children=True, fullPath=True) or []
    idx_to_node = {}
    for node in children:
        if mc.attributeQuery("rbIndex", node=node, exists=True):
            idx = mc.getAttr(f"{node}.rbIndex")
            idx_to_node[idx] = node

    for idx, (pos, quat) in rb_transforms.items():
        if idx in idx_to_node:
            node = idx_to_node[idx]
            rot = quat_to_euler_xyz(quat)
            mc.xform(node, worldSpace=True, translation=pos)
            mc.xform(node, worldSpace=True, rotation=rot)
            if frame is not None:
                mc.setKeyframe(node, attribute=['translateX', 'translateY', 'translateZ', 'rotateX', 'rotateY', 'rotateZ'], time=frame)

    # Jointキューブの同期 (剛体Aの現在姿勢からジョイントのワールド姿勢を算出して追従)
    joint_target_grp = JOINT_VIS_GROUP_NAME if mc.objExists(JOINT_VIS_GROUP_NAME) else f"{VIS_GROUP_NAME}|MMD_Joint_Visualizers"
    if mc.objExists(joint_target_grp):
        joint_nodes = mc.listRelatives(joint_target_grp, children=True, fullPath=True) or []
        for j_node in joint_nodes:
            if not mc.attributeQuery("rbAIndex", node=j_node, exists=True):
                continue
            rb_a_idx = mc.getAttr(f"{j_node}.rbAIndex")
            if rb_a_idx not in rb_transforms:
                continue

            pos_a, quat_a = rb_transforms[rb_a_idx]
            lx = mc.getAttr(f"{j_node}.localOffsetX")
            ly = mc.getAttr(f"{j_node}.localOffsetY")
            lz = mc.getAttr(f"{j_node}.localOffsetZ")
            local_p = (lx, ly, lz)

            lqx = mc.getAttr(f"{j_node}.localOffsetRotX")
            lqy = mc.getAttr(f"{j_node}.localOffsetRotY")
            lqz = mc.getAttr(f"{j_node}.localOffsetRotZ")
            lqw = mc.getAttr(f"{j_node}.localOffsetRotW")
            local_q = (lqx, lqy, lqz, lqw)

            world_diff = quat_rotate_vector(quat_a, local_p)
            j_pos = (pos_a[0] + world_diff[0], pos_a[1] + world_diff[1], pos_a[2] + world_diff[2])
            j_quat = quat_multiply(quat_a, local_q)
            j_rot = quat_to_euler_xyz(j_quat)

            mc.xform(j_node, worldSpace=True, translation=j_pos)
            mc.xform(j_node, worldSpace=True, rotation=j_rot)
            if frame is not None:
                mc.setKeyframe(j_node, attribute=['translateX', 'translateY', 'translateZ', 'rotateX', 'rotateY', 'rotateZ'], time=frame)

def reconnect_visualizers_to_bones():
    """
    可視化ノード（剛体・Joint）に記録されたキーフレームをすべてクリアし、
    ボーン追従コンストレイントを通常状態（Normal）に復元してモデルのボーンに吸着・追従させます。
    """
    if not mc.objExists(VIS_GROUP_NAME):
        print("[Visualizer] 可視化グループが見つかりません。")
        return False

    # キーフレームの削除
    try:
        mc.cutKey(VIS_GROUP_NAME, hierarchy='below', attribute=['translateX', 'translateY', 'translateZ', 'rotateX', 'rotateY', 'rotateZ'])
    except Exception:
        pass

    # コンストレイントの復元
    mute_dynamic_constraints(mute=False)
    print("[Visualizer] 剛体・Jointのキーフレームをクリアし、モデルボーンへの追従を復元しました。")
    return True
