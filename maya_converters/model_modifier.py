# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - モデル改造・お着替え統合処理モジュール
2つのMMDモデル（素体側・衣装側）を合成し、パーツ付け替えやお着替えを自動化・支援します。
首まわりの境界結合と法線調整（ar716253準拠）およびボーン・物理・モーフの統合（ar1344471準拠）を提供します。
"""

import json
import math
import importlib
import maya.cmds as mc
import maya.api.OpenMaya as om

try:
    from .dressup import skin_utils, align, part_split, neck_seam, bone_merge, physics_merge, validate
    importlib.reload(skin_utils)
    importlib.reload(align)
    importlib.reload(part_split)
    importlib.reload(neck_seam)
    importlib.reload(bone_merge)
    importlib.reload(physics_merge)
    importlib.reload(validate)
except Exception:
    try:
        from maya_converters.dressup import skin_utils, align, part_split, neck_seam, bone_merge, physics_merge, validate
        importlib.reload(skin_utils)
        importlib.reload(align)
        importlib.reload(part_split)
        importlib.reload(neck_seam)
        importlib.reload(bone_merge)
        importlib.reload(physics_merge)
        importlib.reload(validate)
    except Exception:
        from dressup import skin_utils, align, part_split, neck_seam, bone_merge, physics_merge, validate
        importlib.reload(skin_utils)
        importlib.reload(align)
        importlib.reload(part_split)
        importlib.reload(neck_seam)
        importlib.reload(bone_merge)
        importlib.reload(physics_merge)
        importlib.reload(validate)

undo_chunk = skin_utils.undo_chunk
create_scene_backup = skin_utils.create_scene_backup
set_models_bone_visibility = skin_utils.set_models_bone_visibility
check_standard_bones = align.check_standard_bones
get_common_anchor_bones = align.get_common_anchor_bones
estimate_alignment_transform = align.estimate_alignment_transform
preview_alignment_transform = align.preview_alignment_transform
reset_alignment_preview = align.reset_alignment_preview
commit_alignment_transform = align.commit_alignment_transform
classify_head_body_faces = part_split.classify_head_body_faces
preview_part_split = part_split.preview_part_split
commit_part_split_deletion = part_split.commit_part_split_deletion
extract_neck_boundary_vertices = neck_seam.extract_neck_boundary_vertices
find_neck_seam_pairs = neck_seam.find_neck_seam_pairs
preview_neck_seam = neck_seam.preview_neck_seam
clear_neck_seam_preview = neck_seam.clear_neck_seam_preview
process_neck_seam = neck_seam.process_neck_seam
test_neck_bend = neck_seam.test_neck_bend
reset_neck_bend = neck_seam.reset_neck_bend
load_bone_name_dictionary = bone_merge.load_bone_name_dictionary
normalize_mmd_bone_name = bone_merge.normalize_mmd_bone_name
build_bone_merge_plan = bone_merge.build_bone_merge_plan
execute_bone_merge = bone_merge.execute_bone_merge
collect_model_physics_data = physics_merge.collect_model_physics_data
analyze_collision_groups = physics_merge.analyze_collision_groups
build_physics_merge_plan = physics_merge.build_physics_merge_plan
execute_physics_merge = physics_merge.execute_physics_merge
validate_dressup_models = validate.validate_dressup_models
clamp_max_4_influences = validate.clamp_max_4_influences

_last_dressup_report = None


def get_last_dressup_report():
    """直近の一括実行で生成されたStep 7診断レポートを取得"""
    return _last_dressup_report


def find_model_mesh_nodes(model_root):
    """指定されたモデル階層下のポリゴンメッシュノードを検出（中間オブジェクト・エッジ・剛体を除外）"""
    return skin_utils.get_model_meshes(model_root)


def find_model_joint_nodes(model_root):
    """指定されたモデルに関連するジョイント（ボーン）ノードを辞書形式（名称: フルパス）で取得"""
    if not model_root or not mc.objExists(model_root):
        return {}
    joints = skin_utils.get_model_joints(model_root)
    bone_map = {}
    for j in joints:
        short_name = j.split("|")[-1]
        bone_map[short_name] = j
        canon_name = skin_utils.get_bone_canonical_name(j, model_root=model_root)
        if canon_name:
            bone_map.setdefault(canon_name, j)
    return bone_map


def get_skin_cluster(mesh_node):
    """メッシュに接続されているスキンクラスタノードを取得"""
    return skin_utils.get_skin_cluster(mesh_node)


@undo_chunk("MMD_AlignAndScaleModel")
def align_and_scale_model(target_model, scale_factor=1.0, offset_y=0.0, offset_z=0.0, offset_x=0.0):
    """
    モデルのプロポーション調整（スケールおよび位置オフセットの適用）
    メッシュに makeIdentity を使わず、スケルトンとバインドポーズを安全に再設定します。
    """
    return align.commit_alignment_transform(
        moving_model=target_model,
        scale_factor=scale_factor,
        offset_x=offset_x,
        offset_y=offset_y,
        offset_z=offset_z,
    )


@undo_chunk("MMD_FreezeModelTransforms")
def freeze_model_transforms(model_root):
    """
    モデルトランスフォームの確定処理
    スキンクラスタを持つモデルでは makeIdentity によるバインド破損を避け、バインドポーズ更新で保護します。
    """
    if not model_root or not mc.objExists(model_root):
        return False
    meshes = find_model_mesh_nodes(model_root)
    if any(get_skin_cluster(m) for m in meshes):
        return True
    try:
        mc.makeIdentity(model_root, apply=True, translate=True, rotate=True, scale=True, normal=False)
        return True
    except Exception as e:
        mc.warning(f"トランスフォーム初期化時に軽微な警告: {e}")
        return False


@undo_chunk("MMD_DeleteMeshComponents")
def delete_selected_mesh_components(components):
    """
    選択または指定されたメッシュコンポーネント（フェース等）を削除
    突き抜け防止用や不要部位の除去に使用します。
    """
    if not components:
        return False
    valid_items = [c for c in components if mc.objExists(c)]
    if not valid_items:
        return False
    try:
        mc.delete(valid_items)
        return True
    except Exception as e:
        mc.warning(f"コンポーネント削除時に例外を捕捉: {e}")
        return False


@undo_chunk("MMD_MergeNeckBorder")
def merge_neck_border_vertices(mesh_a, mesh_b, distance_threshold=0.35):
    """
    素体首と衣装首の境界頂点を非結合方式でスナップ・法線平均化・ウェイト整合（ar716253準拠）
    polyUnite によるメッシュ結合を行わず、モーフ（blendShape）とスキンクラスタを維持したまま継ぎ目を消去します。
    """
    if not mesh_a or not mc.objExists(mesh_a) or not mesh_b or not mc.objExists(mesh_b):
        return 0

    res = neck_seam.process_neck_seam(
        head_model_or_mesh=mesh_a,
        body_model_or_mesh=mesh_b,
        distance_threshold=distance_threshold,
        snap_positions=True,
        smooth_normals=True,
        copy_weights=True,
    )
    return int(res.get("matched_count", 0)) if isinstance(res, dict) else 0


@undo_chunk("MMD_SmoothNeckNormals")
def smooth_neck_normals(target_mesh, y_min=None, y_max=None):
    """
    首境界まわりの法線平均化処理（ar716253準拠）
    メッシュ全体への polySoftEdge(angle=180) は行わず、首境界周辺の頂点法線のみを滑らかに補正します。
    """
    if not target_mesh or not mc.objExists(target_mesh):
        return False
    return neck_seam.smooth_single_model_neck_normals(target_mesh, y_min=y_min, y_max=y_max)


@undo_chunk("MMD_TransferAndBindSkeleton")
def transfer_and_bind_skeleton(base_model, outfit_model, master_skeleton="outfit", merge_plan=None):
    """
    ボーン名対応辞書に基づいて2モデルのスケルトンを統合し、移植元メッシュのウェイトを付け替え（ar1344471準拠）
    master_skeleton="outfit"（推奨既定）では衣装モデルをマスター骨格として頭側（素体）の固有ボーンを移植し、
    master_skeleton="base" では素体モデルをマスター骨格として衣装側の固有ボーンを移植します。
    """
    if master_skeleton == "base":
        src_m, mst_m, suffix = outfit_model, base_model, "_outfit"
    else:
        src_m, mst_m, suffix = base_model, outfit_model, "_part"

    res = bone_merge.execute_bone_merge(
        source_model=src_m,
        master_model=mst_m,
        merge_plan=merge_plan,
        rename_suffix=suffix,
        cleanup_unused_source_bones=False,
    )
    return bool(res.get("success", False)) if isinstance(res, dict) else False


@undo_chunk("MMD_IntegrateRigidbodyAndJoints")
def integrate_rigidbody_and_joints(
    base_model,
    outfit_model,
    master_skeleton="outfit",
    physics_plan=None,
    group_remap=None,
):
    """
    剛体・Joint（物理演算アセット）をマスター骨格モデル側へ統合（Step 6）
    rbIndex / jointIndex / rbAIndex / rbBIndex の振り直し、parentConstraint の追従先再接続、
    衝突グループ調整および mmdModelStructure JSON の更新を行います。
    """
    if not base_model or not outfit_model:
        return False

    if master_skeleton == "base":
        src_m, mst_m = outfit_model, base_model
    else:
        src_m, mst_m = base_model, outfit_model

    res = physics_merge.execute_physics_merge(
        source_model=src_m,
        master_model=mst_m,
        physics_plan=physics_plan,
        group_remap=group_remap,
    )
    return bool(res.get("success", False)) if isinstance(res, dict) else False


@undo_chunk("MMD_CacheModelSkinWeights")
def cache_model_skin_weights(model_root, cache_tag="default"):
    """
    指定モデル配下の全メッシュのスキンウェイト情報を抽出し、
    シーン内の非表示ノード属性へJSON形式で永続化保存します。
    """
    return skin_utils.save_model_weights_to_scene(model_root, cache_tag=cache_tag)


def has_cached_weights(cache_tag="default"):
    """指定タグのウェイトキャッシュがシーン内に存在するか確認"""
    return skin_utils.has_scene_weight_cache(cache_tag=cache_tag)


def list_cached_weights():
    """シーン内に保存されているウェイトキャッシュのタグ一覧を取得"""
    return skin_utils.list_scene_weight_caches()


@undo_chunk("MMD_ClearCachedWeights")
def clear_cached_weights(cache_tag="default"):
    """保存されているウェイトキャッシュを安全に破棄・クリーンアップ"""
    return skin_utils.clear_scene_weight_cache(cache_tag=cache_tag)


@undo_chunk("MMD_RebindAndTransferSkinWeights")
def rebind_and_transfer_skin_weights(target_mesh, skeleton_root, cache_tag="default", vertex_map=None):
    """
    シーン内の保存キャッシュから対象メッシュへスキンウェイトを復元・再バインド
    メッシュごとに対応する保存データを特定し、ボーン名対応付けおよび
    頂点番号の対応表または空間近接点により高精度にウェイトを適用します。
    """
    return skin_utils.rebind_mesh_from_scene_cache(
        target_mesh=target_mesh,
        skeleton_root=skeleton_root,
        cache_tag=cache_tag,
        vertex_map=vertex_map,
        rebind=True,
    )


def _copy_string_attr(src_node, dst_node, attr_name):
    """ソースノードの文字列属性をターゲットノードへ複製"""
    if not src_node or not dst_node or not mc.objExists(src_node) or not mc.objExists(dst_node):
        return False
    if not mc.attributeQuery(attr_name, node=src_node, exists=True):
        return False
    val = mc.getAttr(f"{src_node}.{attr_name}") or ""
    if not mc.attributeQuery(attr_name, node=dst_node, exists=True):
        mc.addAttr(dst_node, longName=attr_name, dataType="string")
    mc.setAttr(f"{dst_node}.{attr_name}", str(val), type="string")
    return True


def _merge_structure_metadata(head_model, body_model, master_model, final_group):
    """統合後の最終グループへ mmdModelRoot および構造JSON属性を引き継ぐ"""
    if not mc.attributeQuery("mmdModelRoot", node=final_group, exists=True):
        mc.addAttr(final_group, longName="mmdModelRoot", attributeType="bool", defaultValue=True)
    mc.setAttr(f"{final_group}.mmdModelRoot", True)

    _copy_string_attr(master_model, final_group, "mmdBoneStructure")
    _copy_string_attr(master_model, final_group, "mmdModelPath")

    # モーフ構造は頭部（素体）側を優先して引き継ぐ
    if head_model and mc.attributeQuery("mmdMorphStructure", node=head_model, exists=True):
        _copy_string_attr(head_model, final_group, "mmdMorphStructure")
    else:
        _copy_string_attr(master_model, final_group, "mmdMorphStructure")

    # mmdModelStructure JSON を統合（ボーン・物理はマスター側、モーフは頭部＋体側を統合）
    if mc.attributeQuery("mmdModelStructure", node=master_model, exists=True):
        raw_mst = mc.getAttr(f"{master_model}.mmdModelStructure") or ""
        try:
            mst_data = json.loads(raw_mst) if raw_mst else {}
        except Exception:
            mst_data = {}

        if head_model and head_model != master_model and mc.attributeQuery("mmdModelStructure", node=head_model, exists=True):
            try:
                head_data = json.loads(mc.getAttr(f"{head_model}.mmdModelStructure") or "{}")
                head_morphs = head_data.get("morphs", [])
                if head_morphs:
                    merged_morphs = []
                    seen_names = set()
                    for m_entry in head_morphs + list(mst_data.get("morphs", [])):
                        nm = m_entry.get("name", "")
                        if nm and nm in seen_names:
                            continue
                        if nm:
                            seen_names.add(nm)
                        new_entry = dict(m_entry)
                        new_entry["index"] = len(merged_morphs)
                        merged_morphs.append(new_entry)
                    mst_data["morphs"] = merged_morphs
                    if isinstance(mst_data.get("name_lookup"), dict):
                        mst_data["name_lookup"]["morphs"] = {
                            m["name"]: m["index"] for m in merged_morphs if m.get("name")
                        }
            except Exception:
                pass

        if not mc.attributeQuery("mmdModelStructure", node=final_group, exists=True):
            mc.addAttr(final_group, longName="mmdModelStructure", dataType="string")
        mc.setAttr(f"{final_group}.mmdModelStructure", json.dumps(mst_data, ensure_ascii=False), type="string")


@undo_chunk("MMD_PerformFullModelDressup")
def perform_full_model_dressup(
    base_model,
    outfit_model,
    scale_factor=1.0,
    offset_y=0.0,
    offset_z=0.0,
    merge_neck=False,
    distance_threshold=0.5,
    smooth_normals=True,
    new_model_name="Customized_MMD_Model",
    auto_backup=True,
    master_skeleton="outfit",
    auto_align=True,
    anchor_bone="上半身2",
    auto_scale=True,
    offset_x=0.0,
    clamp_bdef4=False,
    rename_suffix=None,
):
    """
    お着替え・汎用パーツ移植の一括統合メインルーチン
    削除ウィンドウ（絞り込み機能）で必要なパーツ（頭・羽・帽子・小物・衣装等）を残した状態に対し、
    自動バックアップ -> 基準ボーン位置合わせ -> （任意）首継ぎ目処理 -> ボーン統合 -> 物理統合 -> 6項目診断を実行します。
    """
    global _last_dressup_report

    if not base_model or not mc.objExists(base_model):
        raise ValueError("移植元モデルが正しく指定されていません。")
    if not outfit_model or not mc.objExists(outfit_model):
        raise ValueError("ベースモデルが正しく指定されていません。")

    if auto_backup:
        create_scene_backup(enabled=True)

    if master_skeleton == "base":
        src_m, mst_m, default_suffix = outfit_model, base_model, "_outfit"
    else:
        src_m, mst_m, default_suffix = base_model, outfit_model, "_part"
    suffix = rename_suffix if rename_suffix else default_suffix

    # Step 2: 基準ボーン位置合わせおよびスケール確定
    has_manual_xform = (
        abs(float(scale_factor) - 1.0) > 1e-4
        or abs(float(offset_x)) > 1e-4
        or abs(float(offset_y)) > 1e-4
        or abs(float(offset_z)) > 1e-4
    )
    if has_manual_xform:
        align.commit_alignment_transform(
            moving_model=src_m,
            scale_factor=scale_factor,
            offset_x=offset_x,
            offset_y=offset_y,
            offset_z=offset_z,
        )
    elif auto_align:
        est = align.estimate_alignment_transform(
            moving_model=src_m,
            reference_model=mst_m,
            anchor_bone=anchor_bone,
            auto_scale=auto_scale,
        )
        if est:
            align.commit_alignment_transform(
                moving_model=src_m,
                scale_factor=est["scale_factor"],
                offset_x=est["offset_x"],
                offset_y=est["offset_y"],
                offset_z=est["offset_z"],
            )

    # Step 4: 首の継ぎ目処理（頭挿げ替え等、接合が必要なパーツで有効化された場合のみ実行）
    neck_res = None
    if merge_neck:
        neck_res = neck_seam.process_neck_seam(
            head_model_or_mesh=base_model,
            body_model_or_mesh=outfit_model,
            distance_threshold=distance_threshold,
            snap_positions=True,
            smooth_normals=smooth_normals,
            copy_weights=True,
        )

    # Step 5: ボーン統合（共通ボーンのウェイト付替および固有ボーン移植）
    bone_res = bone_merge.execute_bone_merge(
        source_model=src_m,
        master_model=mst_m,
        rename_suffix=suffix,
        cleanup_unused_source_bones=True,
    )

    # Step 6: 物理統合（剛体・Joint番号振り直しと追従先ボーン再接続）
    phys_res = physics_merge.execute_physics_merge(
        source_model=src_m,
        master_model=mst_m,
    )

    # PMXのBDEF4上限への自動整理（オプション）
    if clamp_bdef4:
        validate.clamp_max_4_influences(base_model)
        validate.clamp_max_4_influences(outfit_model)

    # Step 7: 書き出し前6項目診断を実行
    val_report = validate.validate_dressup_models(
        head_model=base_model,
        body_model=outfit_model,
        master_model=mst_m,
        seam_threshold=max(float(distance_threshold), 0.5),
        check_neck_seam=bool(merge_neck),
    )

    # 非結合のまま両メッシュを出力グループ配下へ整理（polyUnite は使用しない）
    final_group = mc.group(empty=True, name=new_model_name)
    _merge_structure_metadata(base_model, outfit_model, mst_m, final_group)

    parented_meshes = []
    for m_node in (base_model, outfit_model):
        if m_node and mc.objExists(m_node):
            try:
                p_res = mc.parent(m_node, final_group)
                if p_res:
                    parented_meshes.append(p_res[0])
            except Exception as e:
                mc.warning(f"最終グループへの格納時に軽微な警告 ({m_node}): {e}")

    if parented_meshes:
        try:
            mc.select(parented_meshes, replace=True)
        except Exception:
            pass

    _last_dressup_report = {
        "final_group": final_group,
        "head_mesh": parented_meshes[0] if len(parented_meshes) > 0 else base_model,
        "body_mesh": parented_meshes[1] if len(parented_meshes) > 1 else outfit_model,
        "neck_result": neck_res,
        "bone_result": bone_res,
        "physics_result": phys_res,
        "validation": val_report,
    }
    return final_group


def get_model_bones_analysis(model_root):
    """
    指定モデル配下の全ジョイントを走査し、ウェイト頂点数および剛体連動数を解析
    メッシュ削除後に不要となった未使用ボーン（ウェイト0）の特定に活用します。
    """
    if not model_root or not mc.objExists(model_root):
        return []

    joints = skin_utils.get_model_joints(model_root)
    if not joints:
        prefix = model_root.split("|")[-1]
        all_j = mc.ls(type="joint", long=True) or []
        joints = [j for j in all_j if j.split("|")[-1].startswith(f"{prefix}_") or prefix in j]

    # スキンクラスタごとのインフルエンスウェイトを一括集計
    meshes = find_model_mesh_nodes(model_root)
    joint_weight_counts = {j: 0 for j in joints}

    for m in meshes:
        w_data = skin_utils.extract_mesh_skin_weights(m, model_root=model_root)
        if not w_data:
            continue
        infs = w_data.get("influences", [])
        idx_to_long = {int(info["index"]): info.get("long_name") for info in infs}
        for v_pairs in w_data.get("sparse_weights", []):
            for pair in v_pairs:
                if len(pair) >= 2 and float(pair[1]) > 0.001:
                    inf_long = idx_to_long.get(int(pair[0]))
                    if inf_long in joint_weight_counts:
                        joint_weight_counts[inf_long] += 1

    # 剛体の追従先ボーンを集計（ビジュアライザグループおよび parentConstraint を含む）
    bone_rigid_counts = {j: 0 for j in joints}
    phys_data = physics_merge.collect_model_physics_data(model_root)
    for rb in phys_data.get("rigid_bodies", []):
        t_bone = rb.get("target_bone")
        if t_bone and t_bone in bone_rigid_counts:
            bone_rigid_counts[t_bone] += 1

    results = []
    for idx, j in enumerate(joints):
        short_name = j.split("|")[-1]
        name_ja = mc.getAttr(f"{j}.originalName") if mc.attributeQuery("originalName", node=j, exists=True) else short_name
        name_en = mc.getAttr(f"{j}.englishName") if mc.attributeQuery("englishName", node=j, exists=True) else ""

        parent_j = mc.listRelatives(j, parent=True, type="joint")
        parent_name = parent_j[0].split("|")[-1] if parent_j else "(ルート)"

        w_count = joint_weight_counts.get(j, 0)
        r_count = bone_rigid_counts.get(j, 0)

        results.append({
            "index": idx,
            "node": j,
            "short_name": short_name,
            "name_ja": name_ja,
            "name_en": name_en,
            "parent_name": parent_name,
            "weight_count": w_count,
            "is_unused": (w_count == 0),
            "rigid_count": r_count
        })

    return results


def get_model_physics_analysis(model_root):
    """
    指定モデル配下の剛体（RigidBody）およびJoint（関節設定）ノードを解析
    `{モデル}_RigidBody_Joint_Visualizers` グループおよび `rbIndex` / `jointIndex` に対応し、
    追従先ボーンが存在しない孤立物理アセットを特定します。
    """
    if not model_root or not mc.objExists(model_root):
        return []

    phys_data = physics_merge.collect_model_physics_data(model_root)
    physics_items = []
    valid_rb_indices = set()

    for rb in phys_data.get("rigid_bodies", []):
        node = rb.get("node")
        if not node or not mc.objExists(node):
            continue
        t_bone = rb.get("target_bone")
        is_orphaned = not (t_bone and mc.objExists(t_bone))
        if not is_orphaned:
            valid_rb_indices.add(int(rb["index"]))
        physics_items.append({
            "index": len(physics_items),
            "node": node,
            "type": "剛体",
            "name_ja": rb.get("name_jp") or node.split("|")[-1],
            "target_bone": (t_bone.split("|")[-1] if t_bone else "(未接続)"),
            "is_orphaned": is_orphaned,
        })

    for jt in phys_data.get("joints", []):
        node = jt.get("node")
        if not node or not mc.objExists(node):
            continue
        ra = int(jt.get("rb_a_index", -1))
        rb = int(jt.get("rb_b_index", -1))
        t_bone = jt.get("target_bone")
        is_orphaned = (ra not in valid_rb_indices) or (rb not in valid_rb_indices) or (t_bone and not mc.objExists(t_bone))
        physics_items.append({
            "index": len(physics_items),
            "node": node,
            "type": "Joint",
            "name_ja": jt.get("name_jp") or node.split("|")[-1],
            "target_bone": (t_bone.split("|")[-1] if t_bone else f"剛体[{ra}]-[{rb}]"),
            "is_orphaned": is_orphaned,
        })

    return physics_items


def delete_bones_safely(joint_nodes, delete_connected_physics=True):
    """
    指定されたジョイントを安全に削除
    子ボーンが存在する場合は親を祖父へ再接続して階層の分断を防ぎます。
    """
    if not joint_nodes:
        return 0

    valid_joints = [j for j in joint_nodes if mc.objExists(j)]
    if not valid_joints:
        return 0

    deleted_count = 0
    mc.undoInfo(openChunk=True, chunkName="MMD_DeleteBonesSafely")
    try:
        for j in valid_joints:
            if not mc.objExists(j):
                continue

            # 連動する剛体・Jointビジュアライザを parentConstraint 接続から高速特定して削除
            if delete_connected_physics:
                p_conns = set(mc.listConnections(j, type="parentConstraint", source=False, destination=True) or [])
                for c_node in p_conns:
                    if not mc.objExists(c_node):
                        continue
                    is_phys_c = (
                        mc.attributeQuery("isMmdPhysicsConstraint", node=c_node, exists=True)
                        or mc.attributeQuery("isMmdJointConstraint", node=c_node, exists=True)
                    )
                    parents_tr = mc.listRelatives(c_node, parent=True, type="transform", fullPath=True) or []
                    if parents_tr:
                        v_tr = parents_tr[0]
                        if is_phys_c or mc.attributeQuery("rbIndex", node=v_tr, exists=True) or mc.attributeQuery("jointIndex", node=v_tr, exists=True):
                            try:
                                mc.delete(v_tr)
                            except Exception:
                                pass

            # 子ジョイントを親へ再接続
            parent_j = mc.listRelatives(j, parent=True, type="joint")
            children_j = mc.listRelatives(j, children=True, type="joint") or []
            for child in children_j:
                try:
                    if parent_j:
                        mc.parent(child, parent_j[0])
                    else:
                        mc.parent(child, world=True)
                except Exception:
                    pass

            try:
                mc.delete(j)
                deleted_count += 1
            except Exception:
                pass
    finally:
        mc.undoInfo(closeChunk=True)

    return deleted_count


def delete_physics_nodes(physics_nodes):
    """指定された剛体・Jointノードを削除"""
    if not physics_nodes:
        return 0
    valid_items = [p for p in physics_nodes if mc.objExists(p)]
    if not valid_items:
        return 0

    mc.undoInfo(openChunk=True, chunkName="MMD_DeletePhysicsNodes")
    try:
        mc.delete(valid_items)
        return len(valid_items)
    finally:
        mc.undoInfo(closeChunk=True)


@undo_chunk("MMD_CleanupUnusedBonesAndPhysics")
def cleanup_unused_bones_and_physics(model_root):
    """
    指定モデル配下の未使用ボーン（ウェイト0）および孤立剛体・Jointを一括自動クリーンアップ
    """
    if not model_root or not mc.objExists(model_root):
        return 0, 0

    bone_data = get_model_bones_analysis(model_root)
    unused_bones = [b["node"] for b in bone_data if b["is_unused"]]

    deleted_bones = delete_bones_safely(unused_bones, delete_connected_physics=True)

    phys_data = get_model_physics_analysis(model_root)
    orphaned_phys = [p["node"] for p in phys_data if p["is_orphaned"]]
    deleted_phys = delete_physics_nodes(orphaned_phys)

    return deleted_bones, deleted_phys

