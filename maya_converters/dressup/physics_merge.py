# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 剛体・Joint（物理演算）統合・番号振り直し・衝突グループ調整モジュール (Step 6)
移植元モデル（例: 頭側）の `{モデル}_RigidBody_Joint_Visualizers` および `mmdModelStructure` から、
有効なボーンに追従する剛体とそれらをつなぐ Joint を抽出し、マスター骨格モデル（例: 衣装側）へ統合します。
`rbIndex` / `jointIndex` / `rbAIndex` / `rbBIndex` の連番振り直し、`parentConstraint` の追従先ボーン再接続、
衝突グループの重複解析・変更候補提示、および `mmdModelStructure` JSON の更新を提供します。
"""

import re
import json
import importlib

import maya.cmds as mc

from . import skin_utils
from . import align
from . import bone_merge

importlib.reload(skin_utils)
importlib.reload(align)
importlib.reload(bone_merge)


def _to_long_name(node_name):
    """ノード名をフルDAGパスへ変換"""
    if not node_name or not mc.objExists(node_name):
        return None
    res = mc.ls(node_name, long=True)
    return res[0] if res else node_name


def _get_visualizer_groups(model_root):
    """指定モデルに対応する剛体・Jointビジュアライザグループ名を取得"""
    long_root = _to_long_name(model_root)
    if not long_root:
        return None, None, None
    short_root = long_root.split("|")[-1]
    main_grp = f"{short_root}_RigidBody_Joint_Visualizers"
    rb_grp = f"{short_root}_RigidBody_Visualizers"
    joint_grp = f"{short_root}_Joint_Visualizers"
    return (
        _to_long_name(main_grp) if mc.objExists(main_grp) else None,
        _to_long_name(rb_grp) if mc.objExists(rb_grp) else None,
        _to_long_name(joint_grp) if mc.objExists(joint_grp) else None,
    )


def _ensure_visualizer_groups(model_root):
    """指定モデル用の剛体・Jointビジュアライザグループを取得または新規作成"""
    long_root = _to_long_name(model_root)
    short_root = long_root.split("|")[-1]
    main_name = f"{short_root}_RigidBody_Joint_Visualizers"
    rb_name = f"{short_root}_RigidBody_Visualizers"
    joint_name = f"{short_root}_Joint_Visualizers"

    if not mc.objExists(main_name):
        main_grp = mc.group(empty=True, name=main_name)
        mc.setAttr(f"{main_grp}.inheritsTransform", False)
    else:
        main_grp = main_name

    if not mc.objExists(rb_name):
        rb_grp = mc.group(empty=True, name=rb_name, parent=main_grp)
    else:
        rb_grp = rb_name

    if not mc.objExists(joint_name):
        joint_grp = mc.group(empty=True, name=joint_name, parent=main_grp)
    else:
        joint_grp = joint_name

    return _to_long_name(main_grp), _to_long_name(rb_grp), _to_long_name(joint_grp)


def _get_constraint_target_bone(vis_node):
    """剛体またはJointビジュアライザに設定されている parentConstraint のターゲットボーンを取得"""
    if not vis_node or not mc.objExists(vis_node):
        return None, None

    children = mc.listRelatives(vis_node, children=True, type="parentConstraint", fullPath=True) or []
    if not children:
        conns = mc.listConnections(vis_node, type="parentConstraint") or []
        children = [_to_long_name(c) for c in conns if c]

    for c_node in children:
        if not c_node or not mc.objExists(c_node):
            continue
        try:
            targets = mc.parentConstraint(c_node, query=True, targetList=True) or []
            if targets:
                return _to_long_name(targets[0]), c_node
        except Exception:
            pass
        return None, c_node

    return None, None


def collect_model_physics_data(model_root):
    """
    指定モデルの剛体・Jointビジュアライザノードおよび mmdModelStructure JSON から
    現在の物理設定データを収集
    """
    long_root = _to_long_name(model_root)
    if not long_root:
        return {"rigid_bodies": [], "joints": [], "bones": []}

    struct = {}
    if mc.attributeQuery("mmdModelStructure", node=long_root, exists=True):
        try:
            raw = mc.getAttr(f"{long_root}.mmdModelStructure")
            if raw:
                struct = json.loads(raw)
        except Exception:
            struct = {}

    struct_bones = struct.get("bones", []) or []
    struct_rbs = {int(r.get("index", i)): dict(r) for i, r in enumerate(struct.get("rigid_bodies", []) or [])}
    struct_joints = {int(j.get("index", i)): dict(j) for i, j in enumerate(struct.get("joints", []) or [])}

    bone_idx_to_node = {}
    for b_info in struct_bones:
        b_i = int(b_info.get("index", -1))
        m_uuid = b_info.get("maya_uuid")
        m_node = b_info.get("maya_node")
        resolved = None
        if m_uuid:
            by_u = mc.ls(m_uuid, long=True) or []
            if by_u:
                resolved = by_u[0]
        if not resolved and m_node and mc.objExists(m_node):
            resolved = _to_long_name(m_node)
        if b_i >= 0 and resolved:
            bone_idx_to_node[b_i] = resolved

    main_grp, rb_grp, joint_grp = _get_visualizer_groups(long_root)

    # シーン上の剛体ビジュアライザノードを収集
    rb_nodes_by_idx = {}
    search_rb_transforms = []
    if rb_grp and mc.objExists(rb_grp):
        search_rb_transforms.extend(mc.listRelatives(rb_grp, children=True, type="transform", fullPath=True) or [])
    if main_grp and mc.objExists(main_grp):
        for tr in mc.listRelatives(main_grp, allDescendents=True, type="transform", fullPath=True) or []:
            if tr not in search_rb_transforms:
                search_rb_transforms.append(tr)
    for tr in mc.listRelatives(long_root, allDescendents=True, type="transform", fullPath=True) or []:
        if tr not in search_rb_transforms:
            search_rb_transforms.append(tr)

    joint_nodes_by_idx = {}
    for tr in search_rb_transforms:
        if mc.attributeQuery("rbIndex", node=tr, exists=True):
            try:
                r_idx = int(mc.getAttr(f"{tr}.rbIndex"))
                rb_nodes_by_idx[r_idx] = tr
            except Exception:
                pass
        elif mc.attributeQuery("jointIndex", node=tr, exists=True):
            try:
                j_idx = int(mc.getAttr(f"{tr}.jointIndex"))
                joint_nodes_by_idx[j_idx] = tr
            except Exception:
                pass

    all_rb_indices = sorted(set(list(struct_rbs.keys()) + list(rb_nodes_by_idx.keys())))
    rigid_bodies = []
    for r_idx in all_rb_indices:
        vis_node = rb_nodes_by_idx.get(r_idx)
        s_data = struct_rbs.get(r_idx, {})

        rb_mode = int(s_data.get("physics_mode", 0))
        rb_group = int(s_data.get("group", 0))
        if vis_node and mc.objExists(vis_node):
            if mc.attributeQuery("rbMode", node=vis_node, exists=True):
                try:
                    rb_mode = int(mc.getAttr(f"{vis_node}.rbMode"))
                except Exception:
                    pass
            if mc.attributeQuery("rbGroup", node=vis_node, exists=True):
                try:
                    rb_group = int(mc.getAttr(f"{vis_node}.rbGroup"))
                except Exception:
                    pass

        target_bone, constraint_node = _get_constraint_target_bone(vis_node)
        b_idx = int(s_data.get("bone_index", -1))
        if not target_bone and b_idx in bone_idx_to_node:
            target_bone = bone_idx_to_node[b_idx]

        target_canon = skin_utils.get_bone_canonical_name(target_bone, model_root=long_root) if target_bone else ""
        name_jp = s_data.get("name_jp") or (vis_node.split("|")[-1] if vis_node else f"rb_{r_idx:03d}")

        rigid_bodies.append({
            "index": r_idx,
            "node": vis_node,
            "constraint_node": constraint_node,
            "name_jp": str(name_jp),
            "name_en": str(s_data.get("name_en", "")),
            "bone_index": b_idx,
            "target_bone": target_bone,
            "target_bone_canonical": target_canon,
            "physics_mode": rb_mode,
            "group": rb_group,
            "collision_mask": int(s_data.get("collision_mask", 65535)),
            "struct_data": s_data,
        })

    all_joint_indices = sorted(set(list(struct_joints.keys()) + list(joint_nodes_by_idx.keys())))
    joints = []
    for j_idx in all_joint_indices:
        vis_node = joint_nodes_by_idx.get(j_idx)
        s_data = struct_joints.get(j_idx, {})

        rb_a = int(s_data.get("rigid_body_a", -1))
        rb_b = int(s_data.get("rigid_body_b", -1))
        if vis_node and mc.objExists(vis_node):
            if mc.attributeQuery("rbAIndex", node=vis_node, exists=True):
                try:
                    rb_a = int(mc.getAttr(f"{vis_node}.rbAIndex"))
                except Exception:
                    pass
            if mc.attributeQuery("rbBIndex", node=vis_node, exists=True):
                try:
                    rb_b = int(mc.getAttr(f"{vis_node}.rbBIndex"))
                except Exception:
                    pass

        target_bone, constraint_node = _get_constraint_target_bone(vis_node)
        name_jp = s_data.get("name_jp") or (vis_node.split("|")[-1] if vis_node else f"joint_{j_idx:03d}")

        joints.append({
            "index": j_idx,
            "node": vis_node,
            "constraint_node": constraint_node,
            "name_jp": str(name_jp),
            "name_en": str(s_data.get("name_en", "")),
            "rb_a_index": rb_a,
            "rb_b_index": rb_b,
            "target_bone": target_bone,
            "struct_data": s_data,
        })

    return {
        "model_root": long_root,
        "main_group": main_grp,
        "rb_group": rb_grp,
        "joint_group": joint_grp,
        "rigid_bodies": rigid_bodies,
        "joints": joints,
        "bones": struct_bones,
    }


def analyze_collision_groups(source_rbs, master_rbs):
    """
    移植元の剛体が使用している衝突グループ番号 (0〜15) とマスター側の使用状況を照合し、
    衝突回避のためのグループ変更候補を算出
    """
    mst_group_counts = {g: 0 for g in range(16)}
    for rb in master_rbs:
        g = int(rb.get("group", 0))
        if 0 <= g < 16:
            mst_group_counts[g] += 1

    unused_mst_groups = [g for g in range(16) if mst_group_counts[g] == 0]

    src_group_counts = {}
    for rb in source_rbs:
        g = int(rb.get("group", 0))
        if 0 <= g < 16:
            src_group_counts[g] = src_group_counts.get(g, 0) + 1

    suggestions = []
    recommended_remap = {}
    unused_cursor = 0

    for src_g in sorted(src_group_counts.keys()):
        cnt = src_group_counts[src_g]
        mst_cnt = mst_group_counts.get(src_g, 0)
        if mst_cnt > 0 and unused_cursor < len(unused_mst_groups):
            alt_g = unused_mst_groups[unused_cursor]
            unused_cursor += 1
        else:
            alt_g = src_g

        # 既定では元のグループ番号を維持しつつ、重複がある場合は空きグループ候補を提示
        recommended_remap[src_g] = src_g
        suggestions.append({
            "source_group": src_g,
            "source_group_display": src_g + 1,
            "source_rb_count": cnt,
            "master_rb_count_in_same_group": mst_cnt,
            "has_overlap": (mst_cnt > 0),
            "suggested_unused_group": alt_g,
            "suggested_unused_group_display": alt_g + 1,
        })

    return {
        "master_group_counts": mst_group_counts,
        "unused_master_groups": unused_mst_groups,
        "source_group_counts": src_group_counts,
        "suggestions": suggestions,
        "default_remap": recommended_remap,
    }


def build_physics_merge_plan(source_model, master_model):
    """
    移植元モデルからマスター骨格モデルへ移植すべき剛体・Jointを自動抽出し、
    新しい番号 (rbIndex / jointIndex / rbAIndex / rbBIndex) と追従先ボーンの統合計画を構築
    """
    src_root = _to_long_name(source_model)
    mst_root = _to_long_name(master_model)
    if not src_root or not mst_root:
        return None

    src_phys = collect_model_physics_data(src_root)
    mst_phys = collect_model_physics_data(mst_root)

    dict_bundle = bone_merge.load_bone_name_dictionary()
    mst_joints = skin_utils.get_model_joints(mst_root)

    # マスター骨格側のボーン名引き辞書（Step 5で移植された固有ボーンも含む）
    mst_by_norm = {}
    mst_by_raw = {}
    mst_by_short = {}
    for mj in mst_joints:
        norm_n = bone_merge.normalize_mmd_bone_name(mj, model_root=mst_root, dict_bundle=dict_bundle)
        raw_n = skin_utils.get_bone_canonical_name(mj, model_root=mst_root)
        short_n = mj.split("|")[-1]
        if norm_n:
            mst_by_norm.setdefault(norm_n, mj)
        if raw_n:
            mst_by_raw.setdefault(raw_n, mj)
        mst_by_short.setdefault(short_n, mj)

    # 移植元モデルで現在有効なボーン（ウェイトを持つボーン、またはマスター骨格へ移植済みのボーン）を特定
    src_active_weights = bone_merge._compute_joint_active_weights(src_root)
    mst_joint_set = set(mst_joints)

    # Step 5 でマスター骨格へ移植された固有ボーン名および有効ウェイトボーン名を収集（頭固定を廃止し汎用パーツに対応）
    active_canon_names = set()
    for sj, w_cnt in src_active_weights.items():
        if w_cnt > 0:
            c_n = skin_utils.get_bone_canonical_name(sj, model_root=src_root)
            if c_n:
                active_canon_names.add(c_n)

    src_prefix = f"{src_root.split('|')[-1]}_"
    suffixes = ("_part", "_head", "_outfit")
    for mj in mst_joints:
        m_short = mj.split("|")[-1]
        has_src_tag = m_short.startswith(src_prefix) or any(m_short.endswith(sfx) for sfx in suffixes)
        if has_src_tag:
            c_n = skin_utils.get_bone_canonical_name(mj, model_root=mst_root)
            if c_n:
                active_canon_names.add(c_n)
                for sfx in suffixes:
                    if c_n.endswith(sfx):
                        active_canon_names.add(c_n[:-len(sfx)])

    src_rbs_by_idx = {rb["index"]: rb for rb in src_phys["rigid_bodies"]}
    selected_rb_indices = set()

    for rb in src_phys["rigid_bodies"]:
        t_bone = rb["target_bone"]
        t_canon = rb["target_bone_canonical"]

        is_active = False
        if t_bone and t_bone in mst_joint_set:
            is_active = True
        elif t_bone and src_active_weights.get(t_bone, 0) > 0:
            is_active = True
        elif t_canon and t_canon in active_canon_names:
            is_active = True

        if is_active:
            selected_rb_indices.add(rb["index"])

    # 移植対象の剛体に接続されている Joint を抽出（アンカー剛体がボーン追従 Kinematic の場合のみ追加）
    selected_joints = []
    initial_selected = set(selected_rb_indices)
    for jt in src_phys["joints"]:
        ra = jt["rb_a_index"]
        rb = jt["rb_b_index"]
        if ra not in src_rbs_by_idx or rb not in src_rbs_by_idx:
            continue
        if ra in initial_selected and rb in initial_selected:
            selected_joints.append(jt)
        elif rb in initial_selected and src_rbs_by_idx[ra].get("physics_mode", 0) == 0:
            selected_rb_indices.add(ra)
            selected_joints.append(jt)
        elif ra in initial_selected and src_rbs_by_idx[rb].get("physics_mode", 0) == 0:
            selected_rb_indices.add(rb)
            selected_joints.append(jt)

    selected_rbs = [src_rbs_by_idx[i] for i in sorted(list(selected_rb_indices)) if i in src_rbs_by_idx]

    # 各移植剛体のマスター骨格側での新しい追従先ボーンを解決
    fallback_mst_bone = (
        mst_by_norm.get("上半身2")
        or mst_by_norm.get("上半身")
        or mst_by_norm.get("頭")
        or mst_by_norm.get("センター")
        or (mst_joints[0] if mst_joints else None)
    )

    for rb in selected_rbs:
        t_bone = rb["target_bone"]
        t_canon = rb["target_bone_canonical"]
        t_norm = bone_merge.normalize_mmd_bone_name(t_bone, model_root=src_root, dict_bundle=dict_bundle) if t_bone else t_canon

        resolved_target = None
        if t_bone and t_bone in mst_joint_set:
            resolved_target = t_bone
        elif t_canon and f"{t_canon}_part" in mst_by_raw:
            resolved_target = mst_by_raw[f"{t_canon}_part"]
        elif t_canon and f"{t_canon}_head" in mst_by_raw:
            resolved_target = mst_by_raw[f"{t_canon}_head"]
        elif t_canon and f"{t_canon}_outfit" in mst_by_raw:
            resolved_target = mst_by_raw[f"{t_canon}_outfit"]
        elif t_canon and t_canon in mst_by_raw:
            resolved_target = mst_by_raw[t_canon]
        elif t_norm and t_norm in mst_by_norm:
            resolved_target = mst_by_norm[t_norm]
        elif t_bone and t_bone.split("|")[-1] in mst_by_short:
            resolved_target = mst_by_short[t_bone.split("|")[-1]]
        else:
            resolved_target = fallback_mst_bone

        rb["resolved_master_bone"] = resolved_target

    collision_analysis = analyze_collision_groups(selected_rbs, mst_phys["rigid_bodies"])

    return {
        "source_model": src_root,
        "master_model": mst_root,
        "master_existing_rb_count": len(mst_phys["rigid_bodies"]),
        "master_existing_joint_count": len(mst_phys["joints"]),
        "transplanted_rbs": selected_rbs,
        "transplanted_joints": selected_joints,
        "collision_analysis": collision_analysis,
    }


@skin_utils.undo_chunk("MMD_ExecutePhysicsMerge")
def execute_physics_merge(
    source_model,
    master_model,
    physics_plan=None,
    group_remap=None,
):
    """
    物理統合プランに基づいて剛体・Jointをマスター骨格モデルへ統合:
    - 移植剛体の rbIndex をマスター側剛体数＋連番に振り直し
    - 移植Jointの jointIndex / rbAIndex / rbBIndex を新しい剛体番号対応表で書き換え
    - parentConstraint の追従先をマスター骨格側の対応ボーンへ再接続
    - 衝突グループ番号の変換（指定時）を反映
    - マスター側の mmdModelStructure JSON (rigid_bodies / joints) を更新
    """
    src_root = _to_long_name(source_model)
    mst_root = _to_long_name(master_model)
    if not src_root or not mst_root:
        return {"success": False, "message": "移植元モデルまたはマスター骨格モデルが指定されていません。"}

    if physics_plan is None:
        physics_plan = build_physics_merge_plan(src_root, mst_root)
    if not physics_plan:
        return {"success": False, "message": "物理統合計画を作成できませんでした。"}

    transplanted_rbs = physics_plan.get("transplanted_rbs", [])
    transplanted_joints = physics_plan.get("transplanted_joints", [])
    if not transplanted_rbs and not transplanted_joints:
        return {
            "success": True,
            "transplanted_rb_count": 0,
            "transplanted_joint_count": 0,
            "message": "移植対象となる剛体・Jointはありませんでした。",
        }

    mst_phys = collect_model_physics_data(mst_root)
    mst_short = mst_root.split("|")[-1]
    _, mst_rb_grp, mst_joint_grp = _ensure_visualizer_groups(mst_root)

    # マスター側のボーンフルパス -> ボーンindex 辞書
    mst_bone_to_idx = {}
    for b_info in mst_phys["bones"]:
        b_node = _to_long_name(b_info.get("maya_node"))
        if b_node:
            mst_bone_to_idx[b_node] = int(b_info.get("index", 0))

    base_rb_idx = len(mst_phys["rigid_bodies"])
    base_joint_idx = len(mst_phys["joints"])

    rb_old_to_new = {}
    new_rb_target_bone = {}
    appended_rb_structs = []
    moved_rb_nodes = 0

    # 剛体の番号振り直し・グループ移動・コンストレイント再接続
    for offset, rb in enumerate(transplanted_rbs):
        old_idx = int(rb["index"])
        new_idx = base_rb_idx + offset
        rb_old_to_new[old_idx] = new_idx

        target_bone = _to_long_name(rb.get("resolved_master_bone") or rb.get("target_bone"))
        new_rb_target_bone[new_idx] = target_bone

        old_grp = int(rb.get("group", 0))
        new_grp = int(group_remap.get(old_grp, old_grp)) if isinstance(group_remap, dict) else old_grp

        vis_node = rb.get("node")
        if vis_node and mc.objExists(vis_node):
            old_c = rb.get("constraint_node")
            if old_c and mc.objExists(old_c):
                try:
                    mc.delete(old_c)
                except Exception:
                    pass

            short_vis = vis_node.split("|")[-1]
            try:
                p_res = mc.parent(vis_node, mst_rb_grp)
                if p_res:
                    vis_node = _to_long_name(p_res[0])
            except Exception:
                vis_node = _to_long_name(f"{mst_rb_grp}|{short_vis}") or _to_long_name(short_vis)

            if vis_node and mc.objExists(vis_node):
                if mc.attributeQuery("rbIndex", node=vis_node, exists=True):
                    mc.setAttr(f"{vis_node}.rbIndex", new_idx)
                if mc.attributeQuery("rbGroup", node=vis_node, exists=True):
                    mc.setAttr(f"{vis_node}.rbGroup", new_grp)

                rb_mode = int(rb.get("physics_mode", 0))
                safe_tail = re.sub(r"[^0-9A-Za-z_]", "_", rb.get("name_jp", f"rb_{new_idx}"))
                new_node_name = f"{mst_short}_rb_{new_idx:03d}_{safe_tail}"
                try:
                    vis_node = _to_long_name(mc.rename(vis_node, new_node_name))
                except Exception:
                    pass

                if target_bone and mc.objExists(target_bone):
                    try:
                        c_res = mc.parentConstraint(target_bone, vis_node, maintainOffset=True)
                        if c_res:
                            if not mc.attributeQuery("isMmdPhysicsConstraint", node=c_res[0], exists=True):
                                mc.addAttr(c_res[0], longName="isMmdPhysicsConstraint", attributeType="bool", defaultValue=True)
                            if not mc.attributeQuery("rbMode", node=c_res[0], exists=True):
                                mc.addAttr(c_res[0], longName="rbMode", attributeType="short", defaultValue=rb_mode)
                    except Exception:
                        pass
                moved_rb_nodes += 1

        s_entry = dict(rb.get("struct_data") or {})
        s_entry["index"] = new_idx
        s_entry["name_jp"] = rb.get("name_jp", f"rb_{new_idx}")
        s_entry["name_en"] = rb.get("name_en", "")
        s_entry["bone_index"] = mst_bone_to_idx.get(target_bone, int(s_entry.get("bone_index", 0)))
        s_entry["group"] = new_grp
        s_entry["physics_mode"] = int(rb.get("physics_mode", 0))
        appended_rb_structs.append(s_entry)

    # Jointの番号振り直し・rbAIndex/rbBIndex更新・コンストレイント再接続
    appended_joint_structs = []
    moved_joint_nodes = 0

    for j_offset, jt in enumerate(transplanted_joints):
        old_ra = int(jt["rb_a_index"])
        old_rb = int(jt["rb_b_index"])
        if old_ra not in rb_old_to_new or old_rb not in rb_old_to_new:
            continue

        new_j_idx = base_joint_idx + len(appended_joint_structs)
        new_ra = rb_old_to_new[old_ra]
        new_rb = rb_old_to_new[old_rb]
        anchor_bone = new_rb_target_bone.get(new_ra) or new_rb_target_bone.get(new_rb)

        vis_node = jt.get("node")
        if vis_node and mc.objExists(vis_node):
            old_c = jt.get("constraint_node")
            if old_c and mc.objExists(old_c):
                try:
                    mc.delete(old_c)
                except Exception:
                    pass

            short_vis = vis_node.split("|")[-1]
            try:
                p_res = mc.parent(vis_node, mst_joint_grp)
                if p_res:
                    vis_node = _to_long_name(p_res[0])
            except Exception:
                vis_node = _to_long_name(f"{mst_joint_grp}|{short_vis}") or _to_long_name(short_vis)

            if vis_node and mc.objExists(vis_node):
                if mc.attributeQuery("jointIndex", node=vis_node, exists=True):
                    mc.setAttr(f"{vis_node}.jointIndex", new_j_idx)
                if mc.attributeQuery("rbAIndex", node=vis_node, exists=True):
                    mc.setAttr(f"{vis_node}.rbAIndex", new_ra)
                if mc.attributeQuery("rbBIndex", node=vis_node, exists=True):
                    mc.setAttr(f"{vis_node}.rbBIndex", new_rb)

                safe_tail = re.sub(r"[^0-9A-Za-z_]", "_", jt.get("name_jp", f"joint_{new_j_idx}"))
                new_j_name = f"{mst_short}_joint_{new_j_idx:03d}_{safe_tail}"
                try:
                    vis_node = _to_long_name(mc.rename(vis_node, new_j_name))
                except Exception:
                    pass

                if anchor_bone and mc.objExists(anchor_bone):
                    try:
                        c_res = mc.parentConstraint(anchor_bone, vis_node, maintainOffset=True)
                        if c_res and not mc.attributeQuery("isMmdJointConstraint", node=c_res[0], exists=True):
                            mc.addAttr(c_res[0], longName="isMmdJointConstraint", attributeType="bool", defaultValue=True)
                    except Exception:
                        pass
                moved_joint_nodes += 1

        j_entry = dict(jt.get("struct_data") or {})
        j_entry["index"] = new_j_idx
        j_entry["name_jp"] = jt.get("name_jp", f"joint_{new_j_idx}")
        j_entry["name_en"] = jt.get("name_en", "")
        j_entry["rigid_body_a"] = new_ra
        j_entry["rigid_body_b"] = new_rb
        appended_joint_structs.append(j_entry)

    # マスター側の mmdModelStructure JSON を更新
    if mc.attributeQuery("mmdModelStructure", node=mst_root, exists=True):
        try:
            raw_struct = mc.getAttr(f"{mst_root}.mmdModelStructure")
            if raw_struct:
                struct = json.loads(raw_struct)
                cur_rbs = list(struct.get("rigid_bodies", []) or [])
                cur_joints = list(struct.get("joints", []) or [])
                cur_rbs.extend(appended_rb_structs)
                cur_joints.extend(appended_joint_structs)
                struct["rigid_bodies"] = cur_rbs
                struct["joints"] = cur_joints
                mc.setAttr(f"{mst_root}.mmdModelStructure", json.dumps(struct, ensure_ascii=False), type="string")
        except Exception:
            pass

    return {
        "success": True,
        "source_model": src_root,
        "master_model": mst_root,
        "transplanted_rb_count": len(appended_rb_structs),
        "transplanted_joint_count": len(appended_joint_structs),
        "moved_rb_visualizers": moved_rb_nodes,
        "moved_joint_visualizers": moved_joint_nodes,
        "rb_index_map": rb_old_to_new,
        "total_master_rbs": base_rb_idx + len(appended_rb_structs),
        "total_master_joints": base_joint_idx + len(appended_joint_structs),
    }
