# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - ボーン対応表構築・ウェイト付け替え・固有ボーン移植モジュール (Step 5)
MMD標準ボーン対応辞書 (bone_name_map.json) およびユーザー辞書を参照し、
移植元モデル（例: 頭側）のボーンをマスター骨格モデル（例: 衣装側）へ統合します。
共通ボーンのウェイト付け替え、固有ボーン（髪・目・アクセサリー等）の階層移植、
同名で位置が異なる衝突ボーンへの接尾辞付与、および mmdBoneStructure / mmdModelStructure の更新を行います。
"""

import os
import json
import math
import importlib

import maya.cmds as mc

from . import skin_utils
from . import align

importlib.reload(skin_utils)
importlib.reload(align)


def _to_long_name(node_name):
    """ノード名をフルDAGパスへ変換"""
    if not node_name or not mc.objExists(node_name):
        return None
    res = mc.ls(node_name, long=True)
    return res[0] if res else node_name


def _get_bone_map_json_path():
    """bone_name_map.json のファイルパスを取得"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "asset", "bone_name_map.json"))


def load_bone_name_dictionary():
    """
    MMD標準ボーン名対応辞書 (bone_name_map.json) およびユーザー辞書を読み込み、
    別名 -> 標準日本語ボーン名の正規化辞書と、基本骨格ボーン集合を返します。
    """
    alias_to_standard = {}
    core_skeleton_set = set()

    json_path = _get_bone_map_json_path()
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for b_name in data.get("core_skeleton_bones", []) or []:
                core_skeleton_set.add(str(b_name).strip())
            std_map = data.get("standard_bones", {}) or {}
            for std_jp, aliases in std_map.items():
                std_clean = str(std_jp).strip()
                alias_to_standard[std_clean] = std_clean
                alias_to_standard[std_clean.lower()] = std_clean
                for al in aliases or []:
                    al_clean = str(al).strip()
                    if al_clean:
                        alias_to_standard[al_clean] = std_clean
                        alias_to_standard[al_clean.lower()] = std_clean
        except Exception as e:
            mc.warning(f"bone_name_map.json の読み込み中に軽微な警告: {e}")

    # 既存のユーザー辞書設定 (user_dict_manager) が存在する場合は追加マージ
    try:
        from ...asset.user_dict_manager import load_bone_dict_json
        user_bone_dict = load_bone_dict_json()
        if isinstance(user_bone_dict, dict):
            for jp_name, en_name in user_bone_dict.items():
                jp_clean = str(jp_name).strip()
                en_clean = str(en_name).strip()
                if jp_clean:
                    std_target = alias_to_standard.get(jp_clean, jp_clean)
                    alias_to_standard.setdefault(jp_clean, std_target)
                    alias_to_standard.setdefault(jp_clean.lower(), std_target)
                    if en_clean:
                        alias_to_standard.setdefault(en_clean, std_target)
                        alias_to_standard.setdefault(en_clean.lower(), std_target)
    except Exception:
        pass

    return {
        "alias_to_standard": alias_to_standard,
        "core_skeleton_set": core_skeleton_set,
    }


def normalize_mmd_bone_name(joint_node, model_root=None, dict_bundle=None):
    """
    ジョイントノードから正規化されたMMDボーン名を取得
    originalName・englishName・ノード短縮名を辞書に照合して標準日本語名へ統一します。
    """
    if dict_bundle is None:
        dict_bundle = load_bone_name_dictionary()
    alias_map = dict_bundle["alias_to_standard"]

    raw_canon = skin_utils.get_bone_canonical_name(joint_node, model_root=model_root)
    if raw_canon:
        if raw_canon in alias_map:
            return alias_map[raw_canon]
        if raw_canon.lower() in alias_map:
            return alias_map[raw_canon.lower()]

    if joint_node and mc.objExists(joint_node) and mc.attributeQuery("englishName", node=joint_node, exists=True):
        try:
            eng = mc.getAttr(f"{joint_node}.englishName")
            if eng:
                eng_clean = str(eng).strip()
                if eng_clean in alias_map:
                    return alias_map[eng_clean]
                if eng_clean.lower() in alias_map:
                    return alias_map[eng_clean.lower()]
        except Exception:
            pass

    return raw_canon


def _compute_joint_active_weights(model_root):
    """モデル配下の各ジョイントについて、影響を与えている頂点数を集計"""
    long_root = _to_long_name(model_root)
    if not long_root:
        return {}

    joints = skin_utils.get_model_joints(long_root)
    counts = {j: 0 for j in joints}
    meshes = skin_utils.get_model_meshes(long_root, include_edge=False)

    for shp in meshes:
        w_data = skin_utils.extract_mesh_skin_weights(shp, model_root=long_root)
        if not w_data:
            continue
        idx_to_long = {int(inf["index"]): inf.get("long_name") for inf in w_data.get("influences", [])}
        for v_pairs in w_data.get("sparse_weights", []):
            for pair in v_pairs:
                if len(pair) >= 2 and float(pair[1]) > 1e-4:
                    j_long = idx_to_long.get(int(pair[0]))
                    if j_long in counts:
                        counts[j_long] += 1

    return counts


def _has_attached_physics(joint_node, model_root):
    """ジョイントに追従する剛体ビジュアライザが存在するか確認"""
    if not joint_node or not mc.objExists(joint_node):
        return False
    conns = mc.listConnections(joint_node, type="parentConstraint", source=False, destination=True) or []
    for c in conns:
        if mc.attributeQuery("isMmdPhysicsConstraint", node=c, exists=True) or mc.attributeQuery("isMmdJointConstraint", node=c, exists=True):
            return True
    return False


def build_bone_merge_plan(
    source_model,
    master_model,
    collision_distance=1.5,
    rename_suffix="_part",
):
    """
    移植元モデル (source_model) の全ボーンを走査し、マスター骨格モデル (master_model) への
    ボーン統合計画（対応表リスト）を自動生成します。
    頭・羽・帽子・尻尾・アクセサリーなど、あらゆるパーツの固有ボーン移植に対応します。

    各エントリの action:
    - "merge_to_master": 共通ボーン（マスター側の対応ボーンへウェイトを付け替え）
    - "transplant_unique": 固有ボーン（マスター骨格の親ボーン配下へ階層ごと移植）
    - "transplant_renamed": 名前衝突ボーン（同名だが位置が離れているため接尾辞を付けて移植）
    - "skip_unused": ウェイト0かつ子孫にも有効ボーンがない未使用ボーン（移植スキップ）
    """
    src_root = _to_long_name(source_model)
    mst_root = _to_long_name(master_model)
    if not src_root or not mst_root:
        return None

    dict_bundle = load_bone_name_dictionary()
    core_set = dict_bundle["core_skeleton_set"]

    src_joints = skin_utils.get_model_joints(src_root)
    mst_joints = skin_utils.get_model_joints(mst_root)
    if not src_joints or not mst_joints:
        return None

    # マスター側ボーンの名前引き辞書を構築
    mst_by_norm = {}
    mst_by_raw = {}
    mst_info_list = []
    for mj in mst_joints:
        norm_n = normalize_mmd_bone_name(mj, model_root=mst_root, dict_bundle=dict_bundle)
        raw_n = skin_utils.get_bone_canonical_name(mj, model_root=mst_root)
        short_n = mj.split("|")[-1]
        if norm_n:
            mst_by_norm.setdefault(norm_n, mj)
        if raw_n:
            mst_by_raw.setdefault(raw_n, mj)
        mst_by_raw.setdefault(short_n, mj)
        mst_info_list.append({
            "node": mj,
            "short_name": short_n,
            "canonical_name": raw_n or short_n,
            "normalized_name": norm_n or raw_n or short_n,
        })

    # 親不明時のフォールバック候補となるマスター側の主要骨格ボーン一覧
    major_anchor_keys = ["頭", "首", "上半身2", "上半身", "下半身", "腰", "センター", "左腕", "右腕", "全ての親"]
    major_mst_anchors = []
    for k in major_anchor_keys:
        mj = mst_by_norm.get(k)
        if mj:
            try:
                major_mst_anchors.append((mj, align._get_world_pos(mj)))
            except Exception:
                pass
    default_root_parent = (
        mst_by_norm.get("上半身2")
        or mst_by_norm.get("上半身")
        or mst_by_norm.get("センター")
        or mst_by_norm.get("全ての親")
        or mst_joints[0]
    )

    weight_counts = _compute_joint_active_weights(src_root)

    # 残存メッシュにウェイトを持つボーン、およびその祖先チェーンを有効ボーンとして収集
    weighted_joints = set()
    active_joint_set = set()
    for sj in src_joints:
        if weight_counts.get(sj, 0) > 0:
            weighted_joints.add(sj)
            active_joint_set.add(sj)
            cur_p = mc.listRelatives(sj, parent=True, type="joint", fullPath=True) or []
            while cur_p:
                p_node = cur_p[0]
                if p_node in active_joint_set:
                    break
                active_joint_set.add(p_node)
                cur_p = mc.listRelatives(p_node, parent=True, type="joint", fullPath=True) or []

    # 有効な固有ボーン（非コア骨格でウェイトを持つボーン）配下の物理先端ボーンも含める
    src_joint_set = set(src_joints)
    for wj in list(weighted_joints):
        w_norm = normalize_mmd_bone_name(wj, model_root=src_root, dict_bundle=dict_bundle)
        if w_norm in core_set:
            continue
        desc_j = mc.listRelatives(wj, allDescendents=True, type="joint", fullPath=True) or []
        for dj in desc_j:
            if dj in src_joint_set and _has_attached_physics(dj, src_root):
                active_joint_set.add(dj)
                cur_p = mc.listRelatives(dj, parent=True, type="joint", fullPath=True) or []
                while cur_p and cur_p[0] not in active_joint_set:
                    active_joint_set.add(cur_p[0])
                    cur_p = mc.listRelatives(cur_p[0], parent=True, type="joint", fullPath=True) or []

    # 第1パス: 各ボーンのアクション（共通 / 固有 / 衝突 / スキップ）を決定
    prelim_entries = {}
    for idx, sj in enumerate(src_joints):
        raw_n = skin_utils.get_bone_canonical_name(sj, model_root=src_root)
        norm_n = normalize_mmd_bone_name(sj, model_root=src_root, dict_bundle=dict_bundle)
        w_cnt = weight_counts.get(sj, 0)
        parent_rel = mc.listRelatives(sj, parent=True, type="joint", fullPath=True) or []
        src_parent = parent_rel[0] if parent_rel else None

        matched_mst = mst_by_norm.get(norm_n) or mst_by_raw.get(raw_n)
        pos_src = align._get_world_pos(sj)

        action = "skip_unused"
        target_mst_bone = None
        new_name = raw_n
        dist_to_mst = None

        if sj not in active_joint_set and w_cnt == 0:
            action = "skip_unused"
            target_mst_bone = matched_mst
        elif matched_mst:
            pos_mst = align._get_world_pos(matched_mst)
            dist_to_mst = round(align._distance_3d(pos_src, pos_mst), 4)
            if norm_n in core_set or dist_to_mst <= float(collision_distance):
                action = "merge_to_master"
                target_mst_bone = matched_mst
            else:
                # 同名だが位置が大きく異なる固有ボーン（名前衝突）
                action = "transplant_renamed"
                new_name = f"{raw_n}{rename_suffix}"
        else:
            action = "transplant_unique"

        prelim_entries[sj] = {
            "index": idx,
            "source_node": sj,
            "source_short_name": sj.split("|")[-1],
            "source_name_jp": raw_n,
            "normalized_name": norm_n,
            "source_parent": src_parent,
            "weight_count": w_cnt,
            "action": action,
            "target_master_bone": target_mst_bone,
            "target_parent_bone": None,
            "is_subtree_root": False,
            "new_bone_name": new_name,
            "distance_to_master": dist_to_mst,
            "world_pos": pos_src,
        }

    # 第2パス: 移植される固有ボーン（transplant_unique / transplant_renamed）の移植先親ボーンを解決
    plan_items = []
    for sj in src_joints:
        entry = prelim_entries[sj]
        act = entry["action"]

        if act in ("transplant_unique", "transplant_renamed"):
            src_p = entry["source_parent"]
            if src_p and src_p in prelim_entries and prelim_entries[src_p]["action"] in ("transplant_unique", "transplant_renamed"):
                # 親ボーン自体も一緒に移植されるため、親子関係をそのまま維持
                entry["is_subtree_root"] = False
                entry["target_parent_bone"] = src_p
            else:
                # この固有ボーンツリーの最上位ルート: 親を辿って対応するマスター側ボーンを探す
                entry["is_subtree_root"] = True
                resolved_mst_parent = None
                cur_anc = src_p
                while cur_anc and cur_anc in prelim_entries:
                    anc_entry = prelim_entries[cur_anc]
                    if anc_entry["target_master_bone"]:
                        resolved_mst_parent = anc_entry["target_master_bone"]
                        break
                    anc_norm = anc_entry["normalized_name"]
                    if anc_norm and anc_norm in mst_by_norm:
                        resolved_mst_parent = mst_by_norm[anc_norm]
                        break
                    cur_anc = anc_entry["source_parent"]

                if not resolved_mst_parent:
                    if major_mst_anchors:
                        best_mj = default_root_parent
                        best_d = 1e18
                        w_pos = entry["world_pos"]
                        for cand_mj, cand_pos in major_mst_anchors:
                            d = align._distance_3d(w_pos, cand_pos)
                            if d < best_d:
                                best_d = d
                                best_mj = cand_mj
                        resolved_mst_parent = best_mj
                    else:
                        resolved_mst_parent = default_root_parent

                entry["target_parent_bone"] = resolved_mst_parent
                entry["target_master_bone"] = resolved_mst_parent

        plan_items.append(entry)

    summary = {
        "merge_count": sum(1 for x in plan_items if x["action"] == "merge_to_master"),
        "transplant_unique_count": sum(1 for x in plan_items if x["action"] == "transplant_unique"),
        "transplant_renamed_count": sum(1 for x in plan_items if x["action"] == "transplant_renamed"),
        "skip_unused_count": sum(1 for x in plan_items if x["action"] == "skip_unused"),
    }

    return {
        "source_model": src_root,
        "master_model": mst_root,
        "items": plan_items,
        "master_bones": mst_info_list,
        "summary": summary,
    }


def _update_master_bone_structure_json(master_root, newly_transplanted_joints):
    """
    マスター側モデルルートの mmdBoneStructure および mmdModelStructure に
    移植された固有ボーンを追記してインデックスを振り直し
    """
    long_mst = _to_long_name(master_root)
    if not long_mst:
        return

    all_mst_joints = skin_utils.get_model_joints(long_mst)
    for tj in newly_transplanted_joints:
        tj_long = _to_long_name(tj)
        if tj_long and tj_long not in all_mst_joints:
            all_mst_joints.append(tj_long)

    # mmdBoneStructure (名前 -> フルパス辞書) の更新
    bone_map = {}
    if mc.attributeQuery("mmdBoneStructure", node=long_mst, exists=True):
        try:
            raw_b = mc.getAttr(f"{long_mst}.mmdBoneStructure")
            if raw_b:
                loaded_b = json.loads(raw_b)
                if isinstance(loaded_b, dict):
                    bone_map.update(loaded_b)
        except Exception:
            pass

    for j in all_mst_joints:
        if not mc.objExists(j):
            continue
        j_long = _to_long_name(j)
        canon_n = skin_utils.get_bone_canonical_name(j_long, model_root=long_mst)
        if canon_n:
            bone_map[canon_n] = j_long
        if mc.attributeQuery("englishName", node=j_long, exists=True):
            try:
                eng_n = mc.getAttr(f"{j_long}.englishName")
                if eng_n:
                    bone_map[str(eng_n)] = j_long
            except Exception:
                pass

    if mc.attributeQuery("mmdBoneStructure", node=long_mst, exists=True):
        try:
            mc.setAttr(f"{long_mst}.mmdBoneStructure", json.dumps(bone_map, ensure_ascii=False), type="string")
        except Exception:
            pass

    # mmdModelStructure の bones リストと name_lookup["bones"] を更新
    if mc.attributeQuery("mmdModelStructure", node=long_mst, exists=True):
        try:
            raw_struct = mc.getAttr(f"{long_mst}.mmdModelStructure")
            if raw_struct:
                struct = json.loads(raw_struct)
                old_bones = struct.get("bones", []) or []
                existing_nodes = set()
                node_to_index = {}
                new_bones = []

                for b_entry in old_bones:
                    m_node = b_entry.get("maya_node")
                    m_long = _to_long_name(m_node) if (m_node and mc.objExists(m_node)) else m_node
                    b_idx = len(new_bones)
                    updated_b = dict(b_entry)
                    updated_b["index"] = b_idx
                    if m_long:
                        updated_b["maya_node"] = m_long
                        existing_nodes.add(m_long)
                        node_to_index[m_long] = b_idx
                    new_bones.append(updated_b)

                for tj in newly_transplanted_joints:
                    tj_long = _to_long_name(tj)
                    if not tj_long or tj_long in existing_nodes:
                        continue
                    b_idx = len(new_bones)
                    existing_nodes.add(tj_long)
                    node_to_index[tj_long] = b_idx

                    name_jp = skin_utils.get_bone_canonical_name(tj_long, model_root=long_mst)
                    name_en = ""
                    if mc.attributeQuery("englishName", node=tj_long, exists=True):
                        try:
                            name_en = mc.getAttr(f"{tj_long}.englishName") or ""
                        except Exception:
                            name_en = ""

                    parent_rel = mc.listRelatives(tj_long, parent=True, type="joint", fullPath=True) or []
                    p_idx = node_to_index.get(parent_rel[0], -1) if parent_rel else -1

                    uuid_list = mc.ls(tj_long, uuid=True) or []
                    maya_uuid = uuid_list[0] if uuid_list else ""

                    new_bones.append({
                        "index": b_idx,
                        "name_jp": name_jp,
                        "name_en": str(name_en),
                        "parent_index": p_idx,
                        "maya_node": tj_long,
                        "maya_uuid": maya_uuid,
                        "is_ik": False,
                    })

                bone_lookup = {}
                for b_entry in new_bones:
                    if b_entry.get("name_jp"):
                        bone_lookup[b_entry["name_jp"]] = b_entry["index"]
                    if b_entry.get("name_en"):
                        bone_lookup[b_entry["name_en"]] = b_entry["index"]

                struct["bones"] = new_bones
                if "name_lookup" not in struct or not isinstance(struct["name_lookup"], dict):
                    struct["name_lookup"] = {}
                struct["name_lookup"]["bones"] = bone_lookup

                if "legacy_compatibility" in struct and isinstance(struct["legacy_compatibility"], dict):
                    struct["legacy_compatibility"]["bones"] = bone_map

                mc.setAttr(f"{long_mst}.mmdModelStructure", json.dumps(struct, ensure_ascii=False), type="string")
        except Exception:
            pass


@skin_utils.undo_chunk("MMD_ExecuteBoneMerge")
def execute_bone_merge(
    source_model,
    master_model,
    merge_plan=None,
    collision_distance=1.5,
    rename_suffix="_head",
    cleanup_unused_source_bones=True,
):
    """
    ボーン統合プランに基づいて以下を実行:
    - 移植元メッシュの全頂点スキンウェイトを事前抽出
    - 名前衝突した固有ボーンへ接尾辞を付与してリネーム
    - 固有ボーン（サブツリールート）をマスター骨格の対応する親ボーン下へペアレント移植
    - 移植元メッシュのスキンクラスタをマスター骨格＋移植固有ボーンへ付け替え（ウェイト維持）
    - マスター側モデルの mmdBoneStructure / mmdModelStructure を更新
    """
    src_root = _to_long_name(source_model)
    mst_root = _to_long_name(master_model)
    if not src_root or not mst_root:
        return {"success": False, "message": "移植元モデルまたはマスター骨格モデルが正しく指定されていません。"}

    if merge_plan is None:
        merge_plan = build_bone_merge_plan(
            source_model=src_root,
            master_model=mst_root,
            collision_distance=collision_distance,
            rename_suffix=rename_suffix,
        )
    if not merge_plan or not merge_plan.get("items"):
        return {"success": False, "message": "ボーン統合計画を作成できませんでした。"}

    plan_items = merge_plan["items"]

    # 移植元メッシュのスキンウェイトを事前抽出
    src_meshes = skin_utils.get_model_meshes(src_root, include_edge=False)
    mesh_weight_backups = {}
    for shp in src_meshes:
        w_data = skin_utils.extract_mesh_skin_weights(shp, model_root=src_root)
        if w_data:
            mesh_weight_backups[shp] = w_data

    # 移植元メッシュのスキンクラスタを一旦解除してジョイント階層変更時の変形ズレを防止
    for shp in mesh_weight_backups.keys():
        sk = skin_utils.get_skin_cluster(shp)
        if sk and mc.objExists(sk):
            try:
                mc.skinCluster(shp, edit=True, unbind=True)
            except Exception:
                pass

    # UUIDを使って階層変更・リネーム後もジョイントを追跡できるように記録
    src_node_to_uuid = {}
    for item in plan_items:
        s_node = item["source_node"]
        if s_node and mc.objExists(s_node):
            u_list = mc.ls(s_node, uuid=True) or []
            if u_list:
                src_node_to_uuid[s_node] = u_list[0]

    def _resolve_current_path(orig_node):
        u_id = src_node_to_uuid.get(orig_node)
        if u_id:
            found = mc.ls(u_id, long=True) or []
            if found:
                return found[0]
        return _to_long_name(orig_node)

    # 名前衝突ボーンのリネーム
    renamed_count = 0
    for item in plan_items:
        if item["action"] == "transplant_renamed":
            cur_j = _resolve_current_path(item["source_node"])
            if not cur_j or not mc.objExists(cur_j):
                continue
            new_jp = item.get("new_bone_name") or f"{item['source_name_jp']}{rename_suffix}"
            if mc.attributeQuery("originalName", node=cur_j, exists=True):
                try:
                    mc.setAttr(f"{cur_j}.originalName", new_jp, type="string")
                except Exception:
                    pass
            cur_short = cur_j.split("|")[-1]
            if not cur_short.endswith(rename_suffix):
                try:
                    mc.rename(cur_j, f"{cur_short}{rename_suffix}")
                    renamed_count += 1
                except Exception:
                    pass

    # 固有ボーン（サブツリールート）をマスター骨格の親ボーンへペアレント移植
    transplanted_roots = 0
    for item in plan_items:
        if item["action"] in ("transplant_unique", "transplant_renamed") and item.get("is_subtree_root"):
            cur_j = _resolve_current_path(item["source_node"])
            target_parent = _to_long_name(item.get("target_parent_bone") or item.get("target_master_bone"))
            if cur_j and mc.objExists(cur_j) and target_parent and mc.objExists(target_parent):
                try:
                    mc.parent(cur_j, target_parent)
                    transplanted_roots += 1
                except Exception:
                    pass

    # 旧ジョイントフルパス -> 統合後の最終ジョイントフルパスの対応表を構築
    old_to_final_joint = {}
    transplanted_joints_final = []
    merged_common_count = 0

    mst_joints = skin_utils.get_model_joints(mst_root)
    fallback_mst_joint = mst_joints[0] if mst_joints else None

    for item in plan_items:
        orig_s = item["source_node"]
        act = item["action"]

        if act == "merge_to_master":
            t_mst = _to_long_name(item.get("target_master_bone"))
            if t_mst:
                old_to_final_joint[orig_s] = t_mst
                merged_common_count += 1
        elif act in ("transplant_unique", "transplant_renamed"):
            final_j = _resolve_current_path(orig_s)
            if final_j and mc.objExists(final_j):
                old_to_final_joint[orig_s] = final_j
                transplanted_joints_final.append(final_j)
        else:
            t_mst = _to_long_name(item.get("target_master_bone")) or fallback_mst_joint
            if t_mst:
                old_to_final_joint[orig_s] = t_mst

    # 統合後のマスター骨格全ジョイント一覧
    unified_joints = list(skin_utils.get_model_joints(mst_root))
    for tj in transplanted_joints_final:
        if tj not in unified_joints and mc.objExists(tj):
            unified_joints.append(tj)

    # 移植元メッシュのウェイトデータのインフルエンスを最終ジョイントへ差し替えて再バインド
    rebound_meshes = 0
    for shp, w_data in mesh_weight_backups.items():
        if not mc.objExists(shp):
            continue
        remapped_infs = []
        for inf in w_data.get("influences", []):
            old_long = inf.get("long_name")
            final_j = old_to_final_joint.get(old_long) or _resolve_current_path(old_long) or fallback_mst_joint
            if not final_j or not mc.objExists(final_j):
                final_j = fallback_mst_joint
            final_short = final_j.split("|")[-1]
            final_canon = skin_utils.get_bone_canonical_name(final_j, model_root=mst_root)

            new_inf = dict(inf)
            new_inf["long_name"] = final_j
            new_inf["short_name"] = final_short
            new_inf["canonical_name"] = final_canon
            remapped_infs.append(new_inf)

        updated_wdata = dict(w_data)
        updated_wdata["influences"] = remapped_infs

        ok = skin_utils.apply_mesh_skin_weights(
            mesh_node=shp,
            weight_data=updated_wdata,
            target_joints=unified_joints,
            model_root=mst_root,
            rebind=True,
        )
        if ok:
            rebound_meshes += 1

    # 移植されなかった残りの移植元ボーンを任意でクリーンアップ削除
    cleaned_source_bones = 0
    if cleanup_unused_source_bones:
        unused_roots = []
        for item in plan_items:
            if item["action"] in ("merge_to_master", "skip_unused"):
                cur_j = _resolve_current_path(item["source_node"])
                if cur_j and mc.objExists(cur_j):
                    parent_j = mc.listRelatives(cur_j, parent=True, type="joint", fullPath=True) or []
                    if not parent_j:
                        unused_roots.append(cur_j)
        for ur in unused_roots:
            if mc.objExists(ur):
                try:
                    mc.delete(ur)
                    cleaned_source_bones += 1
                except Exception:
                    pass

    # マスター側の構造JSONを更新
    _update_master_bone_structure_json(mst_root, transplanted_joints_final)

    return {
        "success": True,
        "source_model": src_root,
        "master_model": mst_root,
        "merged_common_bones": merged_common_count,
        "transplanted_bones": len(transplanted_joints_final),
        "transplanted_subtrees": transplanted_roots,
        "renamed_collision_bones": renamed_count,
        "rebound_meshes": rebound_meshes,
        "cleaned_source_roots": cleaned_source_bones,
        "old_to_final_joint_map": old_to_final_joint,
    }
