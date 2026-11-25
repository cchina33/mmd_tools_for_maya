# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 首境界の非結合スナップ・法線補正・ウェイト整合モジュール (ar716253準拠)
頭側メッシュと体側メッシュを polyUnite で結合せず（モーフとスキンクラスタを維持したまま）、
首付近の開放境界エッジを自動抽出し、境界頂点の位置スナップ、境界周辺の法線平均化・ロック、
および体側から頭側への境界スキンウェイトコピーを実行します。
さらに首ボーンを一時回転させて継ぎ目の割れを検査する確認機能を提供します。
"""

import math
import importlib

import maya.cmds as mc
import maya.api.OpenMaya as om

from . import skin_utils
from . import align

importlib.reload(skin_utils)
importlib.reload(align)


PREVIEW_GROUP_NAME = "MMD_NeckSeam_Preview_Grp"

# 首曲げテスト用の元の回転角バックアップ
_neck_bend_backup = {}
_neck_bend_pose_index = 0
_NECK_TEST_POSES = [
    ("前屈 (+30度)", (30.0, 0.0, 0.0)),
    ("後屈 (-30度)", (-30.0, 0.0, 0.0)),
    ("側屈 (+30度)", (0.0, 0.0, 30.0)),
    ("回旋 (+35度)", (15.0, 35.0, 0.0)),
    ("大角度曲げ (+45度)", (45.0, 0.0, 20.0)),
]


def _to_long_name(node_name):
    """ノード名をフルDAGパスへ変換"""
    if not node_name or not mc.objExists(node_name):
        return None
    res = mc.ls(node_name, long=True)
    return res[0] if res else node_name


def _resolve_model_root_from_node(node_or_model):
    """メッシュまたはトランスフォームから所属するモデルルートノードを推定"""
    long_n = _to_long_name(node_or_model)
    if not long_n:
        return None
    if mc.attributeQuery("mmdModelRoot", node=long_n, exists=True):
        return long_n

    parts = [p for p in long_n.split("|") if p]
    cur = ""
    best = None
    for p in parts:
        cur = f"{cur}|{p}"
        if mc.objExists(cur):
            if mc.attributeQuery("mmdModelRoot", node=cur, exists=True):
                return cur
            if best is None and mc.nodeType(cur) == "transform":
                best = cur
    return best or long_n


def _get_neck_zone_bounds(model_root, y_tolerance=None):
    """
    モデルの「首」「頭」「上半身」ボーン位置から、首境界を探索する空間範囲を計算
    """
    root_node = _resolve_model_root_from_node(model_root)
    bone_info = align.check_standard_bones(root_node) if root_node else {"found": {}}
    found = bone_info.get("found", {})

    neck_j = found.get("首")
    head_j = found.get("頭")
    upper_j = found.get("上半身")

    neck_pos = None
    head_pos = None
    upper_pos = None

    if neck_j and mc.objExists(neck_j):
        neck_pos = align._get_world_pos(neck_j)
    if head_j and mc.objExists(head_j):
        head_pos = align._get_world_pos(head_j)
    if upper_j and mc.objExists(upper_j):
        upper_pos = align._get_world_pos(upper_j)

    if neck_pos is None and head_pos is not None:
        neck_pos = (head_pos[0], head_pos[1] - 0.8, head_pos[2])
    elif neck_pos is None and upper_pos is not None:
        neck_pos = (upper_pos[0], upper_pos[1] + 1.5, upper_pos[2])

    if neck_pos is None:
        return None

    ref_len = 1.2
    if head_pos is not None:
        d_nh = align._distance_3d(neck_pos, head_pos)
        if d_nh > 1e-3:
            ref_len = d_nh
    elif upper_pos is not None:
        d_un = align._distance_3d(upper_pos, neck_pos)
        if d_un > 1e-3:
            ref_len = d_un * 0.6

    tol_y = float(y_tolerance) if y_tolerance is not None else max(1.8, ref_len * 1.8)
    y_min = neck_pos[1] - tol_y
    y_max = neck_pos[1] + tol_y
    if upper_pos is not None:
        y_min = max(y_min, upper_pos[1] - 0.3)
    if head_pos is not None:
        y_max = min(y_max, head_pos[1] + 0.5)
    if y_max <= y_min:
        y_min = neck_pos[1] - tol_y
        y_max = neck_pos[1] + tol_y

    xz_radius = max(2.2, ref_len * 2.2)

    return {
        "neck_pos": neck_pos,
        "y_min": y_min,
        "y_max": y_max,
        "xz_radius": xz_radius,
        "ref_len": ref_len,
    }


def extract_neck_boundary_vertices(model_or_mesh, y_tolerance=None):
    """
    MItMeshEdge.onBoundary を用いて、首ボーン周辺の開放境界ループ頂点を抽出
    袖口や裾などの離れた開放エッジを除外し、首まわりの境界頂点のみを返します。
    """
    long_node = _to_long_name(model_or_mesh)
    if not long_node:
        return []

    model_root = _resolve_model_root_from_node(long_node)
    if mc.nodeType(long_node) == "mesh":
        meshes = [long_node]
    else:
        meshes = skin_utils.get_model_meshes(long_node, include_edge=False)
        if not meshes:
            shp = skin_utils._get_mesh_shape(long_node)
            if shp:
                meshes = [shp]

    if not meshes:
        return []

    bounds = _get_neck_zone_bounds(model_root, y_tolerance=y_tolerance)

    def _collect_with_scale(zone_scale):
        collected = []
        for shp in meshes:
            parents = mc.listRelatives(shp, parent=True, fullPath=True) or [shp]
            mesh_tr = parents[0]

            sel = om.MSelectionList()
            sel.add(shp)
            dag = sel.getDagPath(0)
            mfn_mesh = om.MFnMesh(dag)
            pts = mfn_mesh.getPoints(om.MSpace.kWorld)

            boundary_v_set = set()
            it_edge = om.MItMeshEdge(dag)
            while not it_edge.isDone():
                if it_edge.onBoundary():
                    boundary_v_set.add(int(it_edge.vertexId(0)))
                    boundary_v_set.add(int(it_edge.vertexId(1)))
                it_edge.next()

            for v_idx in sorted(list(boundary_v_set)):
                pt = pts[v_idx]
                px, py, pz = float(pt.x), float(pt.y), float(pt.z)

                if bounds:
                    nx, ny, nz = bounds["neck_pos"]
                    half_y = (bounds["y_max"] - bounds["y_min"]) * 0.5 * zone_scale
                    mid_y = (bounds["y_max"] + bounds["y_min"]) * 0.5
                    if py < (mid_y - half_y) or py > (mid_y + half_y):
                        continue
                    dx = px - nx
                    dz = pz - nz
                    if math.sqrt(dx * dx + dz * dz) > (bounds["xz_radius"] * zone_scale):
                        continue

                norm = mfn_mesh.getVertexNormal(v_idx, False, om.MSpace.kWorld)
                collected.append({
                    "mesh_shape": shp,
                    "mesh_transform": mesh_tr,
                    "v_idx": v_idx,
                    "component": f"{mesh_tr}.vtx[{v_idx}]",
                    "pos": (px, py, pz),
                    "normal": (float(norm.x), float(norm.y), float(norm.z)),
                })
        return collected

    result = _collect_with_scale(1.0)
    if not result:
        result = _collect_with_scale(2.2)
    return result


def find_neck_seam_pairs(head_model_or_mesh, body_model_or_mesh, distance_threshold=0.5, y_tolerance=None):
    """
    頭側の首境界頂点ごとに、体側の首境界から最も近い頂点を探索して対応ペアを構築
    """
    head_verts = extract_neck_boundary_vertices(head_model_or_mesh, y_tolerance=y_tolerance)
    body_verts = extract_neck_boundary_vertices(body_model_or_mesh, y_tolerance=y_tolerance)

    matched_pairs = []
    unmatched_head = []
    used_body_keys = set()
    many_to_one_count = 0

    for hv in head_verts:
        hx, hy, hz = hv["pos"]
        best_bv = None
        best_dist = float("inf")

        for bv in body_verts:
            bx, by, bz = bv["pos"]
            d = math.sqrt((hx - bx) ** 2 + (hy - by) ** 2 + (hz - bz) ** 2)
            if d < best_dist:
                best_dist = d
                best_bv = bv

        if best_bv is not None and best_dist <= float(distance_threshold):
            b_key = (best_bv["mesh_shape"], best_bv["v_idx"])
            if b_key in used_body_keys:
                many_to_one_count += 1
            used_body_keys.add(b_key)
            matched_pairs.append({
                "head": hv,
                "body": best_bv,
                "distance": round(float(best_dist), 5),
            })
        else:
            unmatched_entry = dict(hv)
            unmatched_entry["nearest_distance"] = round(float(best_dist), 5) if best_bv else None
            unmatched_head.append(unmatched_entry)

    is_count_mismatch = (len(head_verts) != len(body_verts))
    warnings = []
    if not head_verts or not body_verts:
        warnings.append("首周辺の開放境界エッジが見つかりませんでした。先にStep 3で不要側パーツを削除してください。")
    else:
        if is_count_mismatch:
            warnings.append(
                f"頭側の首境界頂点数({len(head_verts)})と体側の首境界頂点数({len(body_verts)})が異なります。最近傍への多対一スナップを適用します。"
            )
        if unmatched_head:
            warnings.append(
                f"距離閾値({distance_threshold})を超える未一致の境界頂点が {len(unmatched_head)} 個あります。閾値を広げるか位置合わせを微調整してください。"
            )

    max_dist = max((p["distance"] for p in matched_pairs), default=0.0)
    return {
        "head_boundary_count": len(head_verts),
        "body_boundary_count": len(body_verts),
        "matched_count": len(matched_pairs),
        "unmatched_count": len(unmatched_head),
        "matched_pairs": matched_pairs,
        "unmatched_head_verts": unmatched_head,
        "head_boundary_verts": head_verts,
        "body_boundary_verts": body_verts,
        "is_count_mismatch": is_count_mismatch,
        "is_many_to_one": (many_to_one_count > 0),
        "max_matched_distance": max_dist,
        "warnings": warnings,
    }


def clear_neck_seam_preview():
    """首境界プレビュー用のガイドライングループを削除"""
    if mc.objExists(PREVIEW_GROUP_NAME):
        try:
            mc.delete(PREVIEW_GROUP_NAME)
        except Exception:
            pass
    return True


@skin_utils.undo_chunk("MMD_PreviewNeckSeam")
def preview_neck_seam(head_model_or_mesh, body_model_or_mesh, distance_threshold=0.5):
    """
    首境界の対応ペアを探索し、対応ラインをビューポートへ表示して境界頂点を選択ハイライト
    未一致頂点がある場合は未一致頂点を優先選択し、すべて一致している場合は対応頂点を選択します。
    """
    clear_neck_seam_preview()
    pair_info = find_neck_seam_pairs(head_model_or_mesh, body_model_or_mesh, distance_threshold=distance_threshold)

    matched = pair_info["matched_pairs"]
    unmatched = pair_info["unmatched_head_verts"]

    # バッチモード以外の環境では対応ペアを結ぶガイドカーブを生成
    if matched and not mc.about(batch=True):
        try:
            grp = mc.group(empty=True, name=PREVIEW_GROUP_NAME)
            for idx, pair in enumerate(matched):
                p1 = pair["head"]["pos"]
                p2 = pair["body"]["pos"]
                if align._distance_3d(p1, p2) > 1e-4:
                    crv = mc.curve(degree=1, point=[p1, p2], name=f"neck_pair_line_{idx:03d}")
                    mc.parent(crv, grp)
        except Exception:
            pass

    if unmatched:
        sel_comps = [u["component"] for u in unmatched]
    else:
        sel_comps = [p["head"]["component"] for p in matched] + [p["body"]["component"] for p in matched]

    if sel_comps:
        try:
            mc.select(sel_comps, replace=True)
        except Exception:
            pass
    else:
        mc.select(clear=True)

    return pair_info


def _snap_head_boundary_positions(matched_pairs):
    """
    頭側の首境界頂点を体側の対応頂点座標へスナップ移動
    スキンクラスタと blendShape を壊さないよう、オブジェクト空間座標へ変換して
    中間Origシェイプおよびベースシェイプの頂点座標を直接更新します。
    """
    if not matched_pairs:
        return 0

    by_head_mesh = {}
    for pair in matched_pairs:
        hv = pair["head"]
        bv = pair["body"]
        shp = hv["mesh_shape"]
        by_head_mesh.setdefault(shp, []).append((int(hv["v_idx"]), bv["pos"]))

    snapped_count = 0
    for shp, v_target_list in by_head_mesh.items():
        parents = mc.listRelatives(shp, parent=True, fullPath=True) or [shp]
        mesh_tr = parents[0]

        sel_tr = om.MSelectionList()
        sel_tr.add(mesh_tr)
        dag_tr = sel_tr.getDagPath(0)
        inv_mat = dag_tr.inclusiveMatrixInverse()

        obj_targets = []
        for v_idx, w_pos in v_target_list:
            w_pt = om.MPoint(float(w_pos[0]), float(w_pos[1]), float(w_pos[2]), 1.0)
            o_pt = w_pt * inv_mat
            obj_targets.append((v_idx, o_pt))

        sk = skin_utils.get_skin_cluster(shp)
        history = mc.listHistory(shp, pruneDagObjects=True) or []
        bs_list = mc.ls(history, type="blendShape") or []

        if sk and mc.objExists(sk):
            try:
                mc.setAttr(f"{sk}.envelope", 0.0)
            except Exception:
                pass
        for bs in bs_list:
            try:
                mc.setAttr(f"{bs}.envelope", 0.0)
            except Exception:
                pass

        try:
            all_shapes = mc.listRelatives(mesh_tr, shapes=True, type="mesh", fullPath=True) or [shp]
            orig_shapes = [s for s in all_shapes if mc.getAttr(f"{s}.intermediateObject")]
            target_shapes = orig_shapes if orig_shapes else [shp]

            for s_node in target_shapes:
                was_intermediate = bool(mc.getAttr(f"{s_node}.intermediateObject"))
                if was_intermediate:
                    mc.setAttr(f"{s_node}.intermediateObject", False)
                try:
                    sel = om.MSelectionList()
                    sel.add(s_node)
                    dag = sel.getDagPath(0)
                    mfn_m = om.MFnMesh(dag)
                    pts = mfn_m.getPoints(om.MSpace.kObject)
                    for v_idx, o_pt in obj_targets:
                        if 0 <= v_idx < len(pts):
                            pts[v_idx] = o_pt
                    mfn_m.setPoints(pts, om.MSpace.kObject)
                    mfn_m.updateSurface()
                finally:
                    if was_intermediate:
                        mc.setAttr(f"{s_node}.intermediateObject", True)

            snapped_count += len(obj_targets)
        finally:
            for bs in bs_list:
                if mc.objExists(bs):
                    try:
                        mc.setAttr(f"{bs}.envelope", 1.0)
                    except Exception:
                        pass
            if sk and mc.objExists(sk):
                try:
                    mc.setAttr(f"{sk}.envelope", 1.0)
                    mc.dgdirty(sk)
                except Exception:
                    pass

    return snapped_count


def _copy_and_average_neck_normals(matched_pairs):
    """
    首境界の対応頂点ペア間で法線を統一して頭側・体側の双方へ設定（ar716253準拠）
    多対一スナップ時も同一の体側頂点に対応するすべての頭側頂点が同じ法線ベクトルを持つように統一し、
    メッシュ全体に polySoftEdge(angle=180) をかけずに首の継ぎ目の影を消去します。
    """
    if not matched_pairs:
        return 0

    # 体側頂点ごとに統一法線ベクトルを決定
    unified_by_body = {}
    for pair in matched_pairs:
        hv = pair["head"]
        bv = pair["body"]
        b_key = (bv["mesh_shape"], int(bv["v_idx"]))
        hn = hv["normal"]
        bn = bv["normal"]

        if b_key not in unified_by_body:
            # 頭側法線と体側法線が逆向きに近い場合は体側法線を基準にする
            dot_hb = hn[0] * bn[0] + hn[1] * bn[1] + hn[2] * bn[2]
            if dot_hb >= 0.0:
                ax, ay, az = hn[0] + bn[0], hn[1] + bn[1], hn[2] + bn[2]
            else:
                ax, ay, az = bn[0], bn[1], bn[2]
            length = math.sqrt(ax * ax + ay * ay + az * az)
            if length > 1e-6:
                unified_by_body[b_key] = om.MVector(ax / length, ay / length, az / length)
            else:
                unified_by_body[b_key] = om.MVector(0.0, 1.0, 0.0)

    head_normals_by_mesh = {}
    body_normals_by_mesh = {}

    for pair in matched_pairs:
        hv = pair["head"]
        bv = pair["body"]
        b_key = (bv["mesh_shape"], int(bv["v_idx"]))
        u_vec = unified_by_body[b_key]
        head_normals_by_mesh.setdefault(hv["mesh_shape"], {})[int(hv["v_idx"])] = u_vec
        body_normals_by_mesh.setdefault(bv["mesh_shape"], {})[int(bv["v_idx"])] = u_vec

    updated_count = 0
    for target_map in (head_normals_by_mesh, body_normals_by_mesh):
        for shp, v_norm_dict in target_map.items():
            if not v_norm_dict or not mc.objExists(shp):
                continue
            try:
                parents = mc.listRelatives(shp, parent=True, fullPath=True) or [shp]
                mesh_tr = parents[0]
                all_shapes = mc.listRelatives(mesh_tr, shapes=True, type="mesh", fullPath=True) or [shp]

                v_indices = om.MIntArray()
                v_normals = om.MVectorArray()
                for v_i in sorted(v_norm_dict.keys()):
                    v_indices.append(int(v_i))
                    v_normals.append(v_norm_dict[v_i])

                sk = skin_utils.get_skin_cluster(shp)
                history = mc.listHistory(shp, pruneDagObjects=True) or []
                bs_list = mc.ls(history, type="blendShape") or []

                if sk and mc.objExists(sk):
                    try:
                        mc.setAttr(f"{sk}.envelope", 0.0)
                    except Exception:
                        pass
                for bs in bs_list:
                    try:
                        mc.setAttr(f"{bs}.envelope", 0.0)
                    except Exception:
                        pass

                try:
                    orig_shapes = [s for s in all_shapes if mc.getAttr(f"{s}.intermediateObject")]
                    target_shapes = orig_shapes if orig_shapes else [shp]
                    for s_node in target_shapes:
                        was_intermediate = bool(mc.getAttr(f"{s_node}.intermediateObject"))
                        if was_intermediate:
                            mc.setAttr(f"{s_node}.intermediateObject", False)
                        try:
                            sel = om.MSelectionList()
                            sel.add(s_node)
                            dag = sel.getDagPath(0)
                            mfn_m = om.MFnMesh(dag)
                            mfn_m.setVertexNormals(v_normals, v_indices, om.MSpace.kObject)
                            mfn_m.updateSurface()
                            mc.dgdirty(s_node)
                        finally:
                            if was_intermediate:
                                mc.setAttr(f"{s_node}.intermediateObject", True)
                finally:
                    for bs in bs_list:
                        if mc.objExists(bs):
                            try:
                                mc.setAttr(f"{bs}.envelope", 1.0)
                                mc.dgdirty(bs)
                            except Exception:
                                pass
                    if sk and mc.objExists(sk):
                        try:
                            mc.setAttr(f"{sk}.envelope", 1.0)
                            mc.dgdirty(sk)
                        except Exception:
                            pass

                # 評価後の出力シェイプに対してもロック法線を設定
                try:
                    sel_out = om.MSelectionList()
                    sel_out.add(shp)
                    mfn_out = om.MFnMesh(sel_out.getDagPath(0))
                    mfn_out.setVertexNormals(v_normals, v_indices, om.MSpace.kObject)
                    mfn_out.updateSurface()
                except Exception:
                    pass

                updated_count += len(v_indices)
            except Exception as e_norm:
                mc.warning(f"首境界法線の設定時に警告: {e_norm}")

    return updated_count


def _copy_neck_boundary_weights(matched_pairs, head_model_root=None, body_model_root=None):
    """
    体側の首境界頂点のスキンウェイトを、ボーン名（日本語オリジナル名・英語名）基準で
    頭側の対応する首境界頂点へコピー（首を曲げた際の境界割れを防止）
    """
    if not matched_pairs:
        return 0

    # メッシュペアごとにグループ化
    pairs_by_meshes = {}
    for pair in matched_pairs:
        h_shp = pair["head"]["mesh_shape"]
        b_shp = pair["body"]["mesh_shape"]
        pairs_by_meshes.setdefault((h_shp, b_shp), []).append((int(pair["head"]["v_idx"]), int(pair["body"]["v_idx"])))

    copied_vertices = 0
    for (h_shp, b_shp), idx_pairs in pairs_by_meshes.items():
        h_root = head_model_root or _resolve_model_root_from_node(h_shp)
        b_root = body_model_root or _resolve_model_root_from_node(b_shp)

        h_wdata = skin_utils.extract_mesh_skin_weights(h_shp, model_root=h_root)
        b_wdata = skin_utils.extract_mesh_skin_weights(b_shp, model_root=b_root)
        if not h_wdata or not b_wdata:
            continue

        # 頭側インフルエンスの名前引き辞書を構築
        h_canon_to_idx = {}
        h_eng_to_idx = {}
        h_short_to_idx = {}
        for h_inf in h_wdata["influences"]:
            h_i = int(h_inf["index"])
            c_n = h_inf.get("canonical_name", "")
            e_n = (h_inf.get("english_name", "") or "").strip().lower()
            s_n = h_inf.get("short_name", "")
            if c_n:
                h_canon_to_idx.setdefault(c_n, h_i)
            if e_n:
                h_eng_to_idx.setdefault(e_n, h_i)
            if s_n:
                h_short_to_idx.setdefault(s_n, h_i)

        fallback_h_idx = (
            h_canon_to_idx.get("首")
            or h_canon_to_idx.get("頭")
            or h_canon_to_idx.get("上半身2")
            or h_canon_to_idx.get("上半身")
            or 0
        )

        # 体側インフルエンス番号 -> 頭側インフルエンス番号の対応表
        b_idx_to_h_idx = {}
        for b_inf in b_wdata["influences"]:
            b_i = int(b_inf["index"])
            c_n = b_inf.get("canonical_name", "")
            e_n = (b_inf.get("english_name", "") or "").strip().lower()
            s_n = b_inf.get("short_name", "")
            p_n = b_inf.get("parent_canonical", "")

            matched_h = None
            if c_n and c_n in h_canon_to_idx:
                matched_h = h_canon_to_idx[c_n]
            elif e_n and e_n in h_eng_to_idx:
                matched_h = h_eng_to_idx[e_n]
            elif s_n and s_n in h_short_to_idx:
                matched_h = h_short_to_idx[s_n]
            elif p_n and p_n in h_canon_to_idx:
                matched_h = h_canon_to_idx[p_n]
            else:
                matched_h = fallback_h_idx

            b_idx_to_h_idx[b_i] = matched_h

        h_sparse = h_wdata["sparse_weights"]
        b_sparse = b_wdata["sparse_weights"]

        for h_v_idx, b_v_idx in idx_pairs:
            if not (0 <= h_v_idx < len(h_sparse)) or not (0 <= b_v_idx < len(b_sparse)):
                continue
            b_pairs = b_sparse[b_v_idx]
            accum = {}
            for pair in b_pairs:
                if len(pair) >= 2:
                    b_inf_i = int(pair[0])
                    w_val = float(pair[1])
                    h_inf_i = b_idx_to_h_idx.get(b_inf_i, fallback_h_idx)
                    if w_val > 1e-6:
                        accum[h_inf_i] = accum.get(h_inf_i, 0.0) + w_val

            total_w = sum(accum.values())
            if total_w > 1e-6:
                h_sparse[h_v_idx] = [[k, round(v / total_w, 6)] for k, v in sorted(accum.items())]
                copied_vertices += 1

        skin_utils.apply_mesh_skin_weights(
            mesh_node=h_shp,
            weight_data=h_wdata,
            model_root=h_root,
            rebind=False,
        )

    return copied_vertices


@skin_utils.undo_chunk("MMD_ProcessNeckSeam")
def process_neck_seam(
    head_model_or_mesh,
    body_model_or_mesh,
    distance_threshold=0.5,
    snap_positions=True,
    smooth_normals=True,
    copy_weights=True,
):
    """
    首の継ぎ目処理を一括実行（メッシュ非結合方式）
    頭側と体側の首境界頂点を対応付け、位置スナップ・境界法線平均化・境界ウェイトコピーを行います。
    """
    clear_neck_seam_preview()
    pair_info = find_neck_seam_pairs(
        head_model_or_mesh,
        body_model_or_mesh,
        distance_threshold=distance_threshold,
    )
    matched = pair_info["matched_pairs"]
    if not matched:
        return {
            "success": False,
            "matched_count": 0,
            "unmatched_count": pair_info["unmatched_count"],
            "warnings": pair_info["warnings"],
            "message": "距離閾値内で一致する首境界の頂点ペアが見つかりませんでした。",
        }

    snapped = 0
    normals_updated = 0
    weights_copied = 0

    if snap_positions:
        snapped = _snap_head_boundary_positions(matched)

    if copy_weights:
        weights_copied = _copy_neck_boundary_weights(
            matched,
            head_model_root=_resolve_model_root_from_node(head_model_or_mesh),
            body_model_root=_resolve_model_root_from_node(body_model_or_mesh),
        )

    if smooth_normals:
        normals_updated = _copy_and_average_neck_normals(matched)

    return {
        "success": True,
        "matched_count": len(matched),
        "unmatched_count": pair_info["unmatched_count"],
        "head_boundary_count": pair_info["head_boundary_count"],
        "body_boundary_count": pair_info["body_boundary_count"],
        "is_count_mismatch": pair_info["is_count_mismatch"],
        "is_many_to_one": pair_info["is_many_to_one"],
        "snapped_count": snapped,
        "normals_updated_count": normals_updated,
        "weights_copied_count": weights_copied,
        "warnings": pair_info["warnings"],
    }


@skin_utils.undo_chunk("MMD_SmoothSingleNeckNormals")
def smooth_single_model_neck_normals(target_model_or_mesh, y_min=None, y_max=None):
    """
    単一モデルまたは指定メッシュの首境界周辺の頂点法線のみを滑らかに補正
    メッシュ全体への polySoftEdge(angle=180) は行わず、首境界に接続するエッジのみをソフト化します。
    """
    b_verts = extract_neck_boundary_vertices(target_model_or_mesh)
    if not b_verts:
        return False

    by_mesh = {}
    for bv in b_verts:
        pt = bv["pos"]
        if y_min is not None and pt[1] < float(y_min):
            continue
        if y_max is not None and pt[1] > float(y_max):
            continue
        by_mesh.setdefault(bv["mesh_transform"], []).append(int(bv["v_idx"]))

    if not by_mesh:
        return False

    for mesh_tr, v_list in by_mesh.items():
        v_comps = [f"{mesh_tr}.vtx[{v}]" for v in v_list]
        try:
            edges = mc.polyListComponentConversion(v_comps, toEdge=True) or []
            if edges:
                mc.polySoftEdge(edges, angle=180, constructionHistory=False)
        except Exception:
            pass

    return True


def measure_neck_seam_gap(matched_pairs):
    """現在の姿勢における対応ペア間の最大距離（首の隙間・割れ量）を計測"""
    if not matched_pairs:
        return 0.0

    # メッシュごとの現在ワールド頂点座標を取得
    mesh_pts_cache = {}
    for pair in matched_pairs:
        for side in ("head", "body"):
            shp = pair[side]["mesh_shape"]
            if shp not in mesh_pts_cache and mc.objExists(shp):
                sel = om.MSelectionList()
                sel.add(shp)
                dag = sel.getDagPath(0)
                mesh_pts_cache[shp] = om.MFnMesh(dag).getPoints(om.MSpace.kWorld)

    max_gap = 0.0
    for pair in matched_pairs:
        h_shp = pair["head"]["mesh_shape"]
        b_shp = pair["body"]["mesh_shape"]
        h_idx = int(pair["head"]["v_idx"])
        b_idx = int(pair["body"]["v_idx"])

        h_pts = mesh_pts_cache.get(h_shp)
        b_pts = mesh_pts_cache.get(b_shp)
        if not h_pts or not b_pts:
            continue
        if h_idx >= len(h_pts) or b_idx >= len(b_pts):
            continue

        hp = h_pts[h_idx]
        bp = b_pts[b_idx]
        gap = math.sqrt(
            (float(hp.x) - float(bp.x)) ** 2
            + (float(hp.y) - float(bp.y)) ** 2
            + (float(hp.z) - float(bp.z)) ** 2
        )
        if gap > max_gap:
            max_gap = gap

    return round(float(max_gap), 5)


@skin_utils.undo_chunk("MMD_TestNeckBend")
def test_neck_bend(head_model, body_model, rotation_xyz=None, distance_threshold=0.5):
    """
    「首を曲げて確認」機能: 両モデルの首ボーン（および上半身2）を一時的に回転させ、
    首の継ぎ目に割れが生じないか確認し、現在の最大隙間距離を返します。
    ボタンを繰り返し押すと前屈・後屈・側屈・回旋・45度曲げのテストポーズを順番に切り替えます。
    """
    global _neck_bend_pose_index

    if rotation_xyz is not None:
        pose_label = f"指定角度 {rotation_xyz}"
        rx, ry, rz = float(rotation_xyz[0]), float(rotation_xyz[1]), float(rotation_xyz[2])
    else:
        pose_label, (rx, ry, rz) = _NECK_TEST_POSES[_neck_bend_pose_index % len(_NECK_TEST_POSES)]
        _neck_bend_pose_index += 1

    # 曲げ適用前の境界ペアを初期姿勢で取得するために一旦リセット
    if _neck_bend_backup:
        reset_neck_bend()

    pair_info = find_neck_seam_pairs(head_model, body_model, distance_threshold=distance_threshold)

    for m_node in (head_model, body_model):
        long_m = _resolve_model_root_from_node(m_node)
        if not long_m:
            continue
        b_info = align.check_standard_bones(long_m)
        neck_j = b_info["found"].get("首")
        head_j = b_info["found"].get("頭")

        for j in (neck_j, head_j):
            if j and mc.objExists(j) and j not in _neck_bend_backup:
                cur_r = mc.getAttr(f"{j}.rotate")[0]
                _neck_bend_backup[j] = (float(cur_r[0]), float(cur_r[1]), float(cur_r[2]))

        if neck_j and mc.objExists(neck_j):
            mc.setAttr(f"{neck_j}.rotate", rx, ry, rz, type="double3")
        elif head_j and mc.objExists(head_j):
            mc.setAttr(f"{head_j}.rotate", rx, ry, rz, type="double3")

    max_gap = measure_neck_seam_gap(pair_info["matched_pairs"])
    return {
        "pose_label": pose_label,
        "rotation": (rx, ry, rz),
        "matched_count": pair_info["matched_count"],
        "max_seam_gap": max_gap,
    }


@skin_utils.undo_chunk("MMD_ResetNeckBend")
def reset_neck_bend():
    """「首を曲げて確認」で回転させた首・頭ボーンの角度を元の初期状態へ戻す"""
    global _neck_bend_pose_index
    for j, rot in list(_neck_bend_backup.items()):
        if mc.objExists(j):
            try:
                mc.setAttr(f"{j}.rotate", rot[0], rot[1], rot[2], type="double3")
            except Exception:
                pass
    _neck_bend_backup.clear()
    _neck_bend_pose_index = 0
    return True
