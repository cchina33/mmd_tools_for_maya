# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 書き出し前最終チェックモジュール (Step 7)
お着替え・改造後のモデルに対して以下の6項目を一括検証し、問題箇所のビューポート選択を支援します:
- 未ウェイト頂点（ウェイト合計が0の頂点）の有無
- 1頂点あたりのインフルエンス数が4以下か（PMXのBDEF4上限チェック＋自動正規化機能）
- ボーン名・材質名の重複チェック
- 追従先ボーンが存在しない孤立剛体・参照先不正の孤立Jointの有無
- 表情モーフ（blendShape）の残存確認
- 首境界の隙間（許容閾値以上の離れ）チェック
"""

import importlib
import maya.cmds as mc

from . import skin_utils
from . import neck_seam
from . import physics_merge

importlib.reload(skin_utils)
importlib.reload(neck_seam)
importlib.reload(physics_merge)

try:
    from .. import mesh_mask_utils
    importlib.reload(mesh_mask_utils)
except Exception:
    try:
        from maya_converters import mesh_mask_utils
        importlib.reload(mesh_mask_utils)
    except Exception:
        import mesh_mask_utils
        importlib.reload(mesh_mask_utils)


def _to_long_name(node_name):
    """ノード名をフルDAGパスへ変換"""
    if not node_name or not mc.objExists(node_name):
        return None
    res = mc.ls(node_name, long=True)
    return res[0] if res else node_name


@skin_utils.undo_chunk("MMD_ClampMax4Influences")
def clamp_max_4_influences(model_root):
    """
    PMXのBDEF4仕様に準拠するため、1頂点あたり5個以上のインフルエンスを持つ頂点を
    上位4ボーンに絞り込んでウェイトを正規化
    """
    long_root = _to_long_name(model_root)
    if not long_root:
        return 0

    meshes = skin_utils.get_model_meshes(long_root, include_edge=False)
    fixed_vertices = 0

    for shp in meshes:
        w_data = skin_utils.extract_mesh_skin_weights(shp, model_root=long_root)
        if not w_data:
            continue

        sparse = w_data.get("sparse_weights", [])
        changed = False
        for v_idx, v_pairs in enumerate(sparse):
            active = [(int(p[0]), float(p[1])) for p in v_pairs if len(p) >= 2 and float(p[1]) > 1e-5]
            if len(active) > 4:
                active.sort(key=lambda x: x[1], reverse=True)
                top4 = active[:4]
                total_w = sum(x[1] for x in top4)
                if total_w > 1e-6:
                    sparse[v_idx] = [[idx, round(w / total_w, 6)] for idx, w in top4]
                    fixed_vertices += 1
                    changed = True

        if changed:
            skin_utils.apply_mesh_skin_weights(
                mesh_node=shp,
                weight_data=w_data,
                model_root=long_root,
                rebind=False,
            )

    return fixed_vertices


def validate_dressup_models(
    head_model,
    body_model=None,
    master_model=None,
    seam_threshold=0.5,
    check_neck_seam=True,
):
    """
    改造・お着替え後のモデルに対して書き出し前の6項目を一括チェック
    各項目ごとに status ("ok" / "warning" / "error")、詳細説明、該当件数、
    およびビューポート上で該当箇所を選択するための select_targets リストを返します。
    """
    h_root = _to_long_name(head_model) if head_model else None
    b_root = _to_long_name(body_model) if body_model else None
    mst_root = _to_long_name(master_model) if master_model else (b_root or h_root)

    target_models = []
    for m in (h_root, b_root):
        if m and m not in target_models:
            target_models.append(m)

    if not target_models:
        return {
            "overall_status": "error",
            "ok_count": 0,
            "warning_count": 0,
            "error_count": 1,
            "checks": [{
                "id": "no_model",
                "title": "対象モデル確認",
                "status": "error",
                "detail": "チェック対象のモデルが選択されていません。",
                "count": 1,
                "select_targets": [],
            }],
        }

    all_meshes = []
    for m in target_models:
        for shp in skin_utils.get_model_meshes(m, include_edge=False):
            if shp not in all_meshes:
                all_meshes.append(shp)

    # 未ウェイト頂点およびインフルエンス4超過頂点の検査
    unweighted_verts = []
    over4_verts = []
    unskinned_meshes = []

    for shp in all_meshes:
        parents = mc.listRelatives(shp, parent=True, fullPath=True) or [shp]
        mesh_tr = parents[0]
        w_data = skin_utils.extract_mesh_skin_weights(shp, model_root=mst_root)
        if not w_data:
            unskinned_meshes.append(mesh_tr)
            continue

        for v_idx, v_pairs in enumerate(w_data.get("sparse_weights", [])):
            active = [p for p in v_pairs if len(p) >= 2 and float(p[1]) > 1e-4]
            w_sum = sum(float(p[1]) for p in active)
            if w_sum < 1e-4:
                unweighted_verts.append(f"{mesh_tr}.vtx[{v_idx}]")
            if len(active) > 4:
                over4_verts.append(f"{mesh_tr}.vtx[{v_idx}]")

    checks = []

    # 項目: 未ウェイト頂点チェック
    if unskinned_meshes:
        checks.append({
            "id": "unweighted_vertices",
            "title": "未ウェイト頂点・スキン接続",
            "status": "error",
            "detail": f"スキンクラスタが未設定のメッシュがあります ({len(unskinned_meshes)}個)。",
            "count": len(unskinned_meshes),
            "select_targets": unskinned_meshes,
        })
    elif unweighted_verts:
        checks.append({
            "id": "unweighted_vertices",
            "title": "未ウェイト頂点・スキン接続",
            "status": "error",
            "detail": f"ウェイトが0の頂点が {len(unweighted_verts)} 個見つかりました。",
            "count": len(unweighted_verts),
            "select_targets": unweighted_verts[:500],
        })
    else:
        checks.append({
            "id": "unweighted_vertices",
            "title": "未ウェイト頂点・スキン接続",
            "status": "ok",
            "detail": f"全 {len(all_meshes)} メッシュの全頂点に有効なウェイトが設定されています。",
            "count": 0,
            "select_targets": [],
        })

    # 項目: インフルエンス数4以下 (PMX BDEF4制限)
    if over4_verts:
        checks.append({
            "id": "max_4_influences",
            "title": "インフルエンス上限 (PMX BDEF4: 4ボーン以下)",
            "status": "warning",
            "detail": f"5ボーン以上の影響を受ける頂点が {len(over4_verts)} 個あります（上位4ボーンへ自動整理できます）。",
            "count": len(over4_verts),
            "select_targets": over4_verts[:500],
        })
    else:
        checks.append({
            "id": "max_4_influences",
            "title": "インフルエンス上限 (PMX BDEF4: 4ボーン以下)",
            "status": "ok",
            "detail": "すべての頂点が4ボーン以下の影響数に収まっています。",
            "count": 0,
            "select_targets": [],
        })

    # 項目: ボーン名・材質名の重複チェック
    mst_joints = skin_utils.get_model_joints(mst_root) if mst_root else []
    bone_name_map = {}
    dup_bone_nodes = []
    dup_bone_names = set()
    for j in mst_joints:
        c_n = skin_utils.get_bone_canonical_name(j, model_root=mst_root)
        if not c_n:
            continue
        if c_n in bone_name_map:
            dup_bone_names.add(c_n)
            dup_bone_nodes.append(j)
            if bone_name_map[c_n] not in dup_bone_nodes:
                dup_bone_nodes.append(bone_name_map[c_n])
        else:
            bone_name_map[c_n] = j

    mat_name_seen = set()
    dup_mat_names = set()
    for m in target_models:
        for m_info in mesh_mask_utils.get_model_materials_data(m):
            if m_info.get("face_count", 0) <= 0:
                continue
            mn = m_info.get("name_ja", "")
            if mn:
                if mn in mat_name_seen:
                    dup_mat_names.add(mn)
                else:
                    mat_name_seen.add(mn)

    dup_total = len(dup_bone_names) + len(dup_mat_names)
    if dup_total > 0:
        parts_msg = []
        if dup_bone_names:
            parts_msg.append(f"重複ボーン名({len(dup_bone_names)}件): {', '.join(sorted(list(dup_bone_names))[:5])}")
        if dup_mat_names:
            parts_msg.append(f"重複材質名({len(dup_mat_names)}件): {', '.join(sorted(list(dup_mat_names))[:5])}")
        checks.append({
            "id": "duplicate_names",
            "title": "ボーン名・材質名の重複",
            "status": "warning",
            "detail": " / ".join(parts_msg),
            "count": dup_total,
            "select_targets": dup_bone_nodes,
        })
    else:
        checks.append({
            "id": "duplicate_names",
            "title": "ボーン名・材質名の重複",
            "status": "ok",
            "detail": f"ボーン ({len(mst_joints)}本) および材質 ({len(mat_name_seen)}件) に名前の重複はありません。",
            "count": 0,
            "select_targets": [],
        })

    # 項目: 孤立剛体・孤立Jointのチェック
    phys_data = physics_merge.collect_model_physics_data(mst_root) if mst_root else {"rigid_bodies": [], "joints": []}
    rbs = phys_data.get("rigid_bodies", [])
    jts = phys_data.get("joints", [])
    orphaned_phys_nodes = []
    valid_rb_indices = set()

    for rb in rbs:
        t_bone = rb.get("target_bone")
        if t_bone and mc.objExists(t_bone):
            valid_rb_indices.add(int(rb["index"]))
        else:
            if rb.get("node") and mc.objExists(rb["node"]):
                orphaned_phys_nodes.append(rb["node"])

    broken_joint_count = 0
    for jt in jts:
        ra = int(jt.get("rb_a_index", -1))
        rb = int(jt.get("rb_b_index", -1))
        if ra not in valid_rb_indices or rb not in valid_rb_indices:
            broken_joint_count += 1
            if jt.get("node") and mc.objExists(jt["node"]):
                orphaned_phys_nodes.append(jt["node"])

    if orphaned_phys_nodes or broken_joint_count > 0:
        checks.append({
            "id": "orphaned_physics",
            "title": "剛体・Jointの接続整合性",
            "status": "warning",
            "detail": f"追従ボーン不明または剛体参照切れの物理ノードが {max(len(orphaned_phys_nodes), broken_joint_count)} 件あります。",
            "count": max(len(orphaned_phys_nodes), broken_joint_count),
            "select_targets": orphaned_phys_nodes,
        })
    else:
        checks.append({
            "id": "orphaned_physics",
            "title": "剛体・Jointの接続整合性",
            "status": "ok",
            "detail": f"剛体 ({len(rbs)}個) および Joint ({len(jts)}個) の接続に問題はありません。",
            "count": 0,
            "select_targets": [],
        })

    # 項目: モーフ (blendShape) 残存チェック
    found_bs_nodes = []
    total_morph_targets = 0
    for shp in all_meshes:
        bs_info = mesh_mask_utils.extract_blendshape_targets(shp, model_root=h_root or mst_root)
        if bs_info and bs_info.get("blendshape_node"):
            bn = bs_info["blendshape_node"]
            if bn not in found_bs_nodes:
                found_bs_nodes.append(bn)
                total_morph_targets += len(bs_info.get("targets", []))

    if total_morph_targets > 0:
        checks.append({
            "id": "morphs_preserved",
            "title": "表情モーフ (blendShape) の残存",
            "status": "ok",
            "detail": f"blendShape ({', '.join(found_bs_nodes)}) に {total_morph_targets} 個の表情モーフが維持されています。",
            "count": total_morph_targets,
            "select_targets": found_bs_nodes,
        })
    else:
        checks.append({
            "id": "morphs_preserved",
            "title": "表情モーフ (blendShape) の残存",
            "status": "warning",
            "detail": "blendShape（頂点モーフ）が見つかりませんでした。",
            "count": 0,
            "select_targets": [h_root] if h_root else target_models,
        })

    # 項目: 首境界の隙間チェック（羽・帽子・小物等の非接合パーツ時はスキップ可能）
    if not check_neck_seam:
        checks.append({
            "id": "neck_seam_gap",
            "title": "首境界の隙間チェック",
            "status": "ok",
            "detail": "首境界の接合チェックはオフ設定（羽・帽子・小物等の汎用パーツ移植モード）のためスキップしました。",
            "count": 0,
            "select_targets": [],
        })
    elif h_root and b_root and h_root != b_root:
        pair_info = neck_seam.find_neck_seam_pairs(h_root, b_root, distance_threshold=max(float(seam_threshold), 1.5))
        matched = pair_info.get("matched_pairs", [])
        if matched:
            cur_gap = neck_seam.measure_neck_seam_gap(matched)
            if cur_gap <= float(seam_threshold):
                checks.append({
                    "id": "neck_seam_gap",
                    "title": "首境界の隙間チェック",
                    "status": "ok",
                    "detail": f"対応ペア {len(matched)} 組の最大隙間は {cur_gap:.5f} です (許容値: {seam_threshold})。",
                    "count": 0,
                    "select_targets": [p["head"]["component"] for p in matched],
                })
            else:
                checks.append({
                    "id": "neck_seam_gap",
                    "title": "首境界の隙間チェック",
                    "status": "warning",
                    "detail": f"首境界に最大 {cur_gap:.4f} の隙間があります (許容値: {seam_threshold})。Step 4でスナップを実行してください。",
                    "count": len(matched),
                    "select_targets": [p["head"]["component"] for p in matched],
                })
        else:
            checks.append({
                "id": "neck_seam_gap",
                "title": "首境界の隙間チェック",
                "status": "warning",
                "detail": "首境界の対応ペアが検出されませんでした（未分割または距離が離れています）。",
                "count": 1,
                "select_targets": [h_root, b_root],
            })
    else:
        checks.append({
            "id": "neck_seam_gap",
            "title": "首境界の隙間チェック",
            "status": "ok",
            "detail": "単一モデルモードのため境界隙間チェックをスキップしました。",
            "count": 0,
            "select_targets": [],
        })

    ok_cnt = sum(1 for c in checks if c["status"] == "ok")
    warn_cnt = sum(1 for c in checks if c["status"] == "warning")
    err_cnt = sum(1 for c in checks if c["status"] == "error")

    if err_cnt > 0:
        overall = "error"
    elif warn_cnt > 0:
        overall = "warning"
    else:
        overall = "ok"

    return {
        "overall_status": overall,
        "ok_count": ok_cnt,
        "warning_count": warn_cnt,
        "error_count": err_cnt,
        "checks": checks,
    }
