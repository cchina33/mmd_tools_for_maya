# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 自動位置合わせ・スケール推定・バインドポーズ更新モジュール
素体モデル（頭側）と衣装モデル（体側）の標準ボーン（首・頭・上半身・センター・全ての親）を検出し、
首ボーンを基準としたスケール倍率と移動量の自動推定、プレビュー表示、リセット、
およびメッシュに makeIdentity を使わない安全なバインドポーズ再設定を提供します。
"""

import math
import importlib

import maya.cmds as mc
import maya.api.OpenMaya as om

from . import skin_utils
importlib.reload(skin_utils)


# プレビュー適用前の状態を保持する辞書
_alignment_preview_backup = {}

# 標準ボーン検索用の別名定義
_STANDARD_BONE_ALIASES = {
    "頭": ["頭", "head"],
    "首": ["首", "neck"],
    "上半身2": ["上半身2", "upper body2", "upper_body2", "upperbody2", "upper body 2"],
    "上半身": ["上半身", "upper body", "upper_body", "upperbody"],
    "下半身": ["下半身", "lower body", "lower_body", "lowerbody"],
    "腰": ["腰", "waist"],
    "センター": ["センター", "center", "グルーブ", "groove"],
    "全ての親": ["全ての親", "mother", "root", "master"],
    "左腕": ["左腕", "left arm", "arm_l", "l_arm"],
    "右腕": ["右腕", "right arm", "arm_r", "r_arm"],
}

_RECOMMENDED_ANCHOR_ORDER = ["首", "頭", "上半身2", "上半身", "下半身", "腰", "センター", "左腕", "右腕", "全ての親"]


def _to_long_name(node_name):
    """ノード名をフルDAGパスへ変換"""
    if not node_name or not mc.objExists(node_name):
        return None
    res = mc.ls(node_name, long=True)
    return res[0] if res else node_name


def check_standard_bones(model_root):
    """
    指定モデルのMMD標準ボーン（頭・首・上半身・センター・全ての親）の有無を検査
    """
    long_root = _to_long_name(model_root)
    if not long_root:
        return {
            "found": {},
            "missing": ["頭", "首", "上半身", "センター"],
            "is_ready": False,
            "root_joints": [],
        }

    joints = skin_utils.get_model_joints(long_root)
    by_canon = {}
    by_eng = {}

    for j in joints:
        canon = skin_utils.get_bone_canonical_name(j, model_root=long_root)
        if canon:
            by_canon.setdefault(canon, j)
            by_canon.setdefault(canon.lower(), j)
        if mc.attributeQuery("englishName", node=j, exists=True):
            try:
                eng = mc.getAttr(f"{j}.englishName")
                if eng:
                    by_eng.setdefault(str(eng).strip().lower(), j)
            except Exception:
                pass

    found = {}
    for std_key, aliases in _STANDARD_BONE_ALIASES.items():
        matched = None
        for al in aliases:
            al_low = al.lower()
            if al in by_canon:
                matched = by_canon[al]
                break
            if al_low in by_canon:
                matched = by_canon[al_low]
                break
            if al_low in by_eng:
                matched = by_eng[al_low]
                break
        found[std_key] = matched

    required_keys = ["頭", "首", "上半身", "センター"]
    missing = [k for k in required_keys if not found.get(k)]

    # ルートジョイント（親がジョイントではない最上位ジョイント）を特定
    root_joints = []
    for j in joints:
        parent_j = mc.listRelatives(j, parent=True, type="joint", fullPath=True) or []
        if not parent_j:
            root_joints.append(j)

    is_ready = bool(found.get("首") and (found.get("頭") or found.get("上半身")))
    return {
        "found": found,
        "missing": missing,
        "is_ready": is_ready,
        "root_joints": root_joints,
        "all_joints": joints,
    }


def _get_world_pos(node_name):
    """ノードのワールド座標 (x, y, z) を取得"""
    pos = mc.xform(node_name, query=True, worldSpace=True, translation=True)
    return (float(pos[0]), float(pos[1]), float(pos[2]))


def _distance_3d(p1, p2):
    """2点間の3次元ユークリッド距離を計算"""
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    dz = p1[2] - p2[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _build_model_bone_lookup(model_root):
    """モデル内の全ジョイントから標準名・日本語名・英語名・短縮名の検索辞書を構築"""
    long_root = _to_long_name(model_root)
    if not long_root:
        return {}, {}
    joints = skin_utils.get_model_joints(long_root)
    by_name = {}
    by_canon = {}
    for j in joints:
        short_n = j.split("|")[-1]
        canon = skin_utils.get_bone_canonical_name(j, model_root=long_root)
        if canon:
            by_canon.setdefault(canon, j)
            by_name.setdefault(canon, j)
            by_name.setdefault(canon.lower(), j)
        by_name.setdefault(short_n, j)
        by_name.setdefault(short_n.lower(), j)
        if mc.attributeQuery("englishName", node=j, exists=True):
            try:
                eng = mc.getAttr(f"{j}.englishName")
                if eng:
                    by_name.setdefault(str(eng).strip().lower(), j)
            except Exception:
                pass
    return by_canon, by_name


def _find_bone_by_anchor_name(model_root, anchor_bone, found_std=None, by_name=None):
    """指定された基準ボーン名（日本語・英語・短縮名・標準別名）からジョイントを解決"""
    if not anchor_bone:
        return None
    if found_std and anchor_bone in found_std and found_std[anchor_bone]:
        return found_std[anchor_bone]
    if by_name is None:
        _, by_name = _build_model_bone_lookup(model_root)
    key = str(anchor_bone).strip()
    if key in by_name:
        return by_name[key]
    if key.lower() in by_name:
        return by_name[key.lower()]
    for al in _STANDARD_BONE_ALIASES.get(key, []):
        if al in by_name:
            return by_name[al]
        if al.lower() in by_name:
            return by_name[al.lower()]
    return None


def get_common_anchor_bones(moving_model, reference_model):
    """
    2つのモデルの両方に存在する基準ボーン（アンカー）候補の一覧を優先順で取得
    首・頭だけでなく、羽や背中小物向けの上半身2・上半身・下半身・腕などの共通ボーンを返します。
    """
    mov_root = _to_long_name(moving_model)
    ref_root = _to_long_name(reference_model)
    if not mov_root or not ref_root:
        return []

    mov_info = check_standard_bones(mov_root)
    ref_info = check_standard_bones(ref_root)
    mov_canon, mov_by_name = _build_model_bone_lookup(mov_root)
    ref_canon, ref_by_name = _build_model_bone_lookup(ref_root)

    common = []
    seen = set()
    for std_k in _RECOMMENDED_ANCHOR_ORDER:
        m_j = _find_bone_by_anchor_name(mov_root, std_k, mov_info["found"], mov_by_name)
        r_j = _find_bone_by_anchor_name(ref_root, std_k, ref_info["found"], ref_by_name)
        if m_j and r_j and std_k not in seen:
            common.append(std_k)
            seen.add(std_k)

    for c_name in sorted(mov_canon.keys()):
        if c_name in ref_canon and c_name not in seen:
            common.append(c_name)
            seen.add(c_name)

    return common


def estimate_alignment_transform(moving_model, reference_model, anchor_bone="首", auto_scale=True):
    """
    指定された基準ボーン（首・頭・上半身2・上半身・下半身・センター・任意ボーン等）から、
    moving_model を reference_model へ位置合わせするためのスケール倍率と移動オフセットを自動推定
    """
    mov_root = _to_long_name(moving_model)
    ref_root = _to_long_name(reference_model)
    if not mov_root or not ref_root:
        return None

    # すでにプレビュー中の場合は一旦元に戻して初期姿勢で推定
    if mov_root in _alignment_preview_backup:
        reset_alignment_preview(mov_root)

    mov_info = check_standard_bones(mov_root)
    ref_info = check_standard_bones(ref_root)
    _, mov_by_name = _build_model_bone_lookup(mov_root)
    _, ref_by_name = _build_model_bone_lookup(ref_root)

    mov_found = mov_info["found"]
    ref_found = ref_info["found"]

    resolved_anchor_name = anchor_bone
    if not anchor_bone or anchor_bone == "auto":
        candidates = ["上半身2", "上半身", "首", "頭", "センター", "全ての親"]
    else:
        candidates = [anchor_bone, "上半身2", "上半身", "首", "頭", "センター"]

    mov_anchor = None
    ref_anchor = None
    for cand in candidates:
        m_j = _find_bone_by_anchor_name(mov_root, cand, mov_found, mov_by_name)
        r_j = _find_bone_by_anchor_name(ref_root, cand, ref_found, ref_by_name)
        if m_j and r_j:
            mov_anchor = m_j
            ref_anchor = r_j
            resolved_anchor_name = cand
            break

    if not mov_anchor or not ref_anchor:
        return None

    p_mov_anchor = _get_world_pos(mov_anchor)
    p_ref_anchor = _get_world_pos(ref_anchor)

    # スケール倍率の推定（auto_scale=False の場合は1.0固定で位置のみ合わせる）
    scale_factor = 1.0
    scale_basis = "スケール固定 (1.0 - 位置合わせのみ)"

    if auto_scale:
        scale_basis = "既定値 (1.0)"
        if resolved_anchor_name in ("首", "頭"):
            ratio_pairs = [
                ("首", "頭", "首〜頭ボーン間距離比率"),
                ("上半身", "首", "上半身〜首ボーン間距離比率"),
                ("センター", "首", "センター〜首ボーン間距離比率"),
            ]
        else:
            ratio_pairs = [
                ("上半身", "首", "上半身〜首ボーン間距離比率"),
                ("センター", "首", "センター〜首ボーン間距離比率"),
                ("首", "頭", "首〜頭ボーン間距離比率"),
            ]

        matched_scale = False
        for k_a, k_b, basis_label in ratio_pairs:
            ma = mov_found.get(k_a)
            mb = mov_found.get(k_b)
            ra = ref_found.get(k_a)
            rb = ref_found.get(k_b)
            if ma and mb and ra and rb:
                d_mov = _distance_3d(_get_world_pos(ma), _get_world_pos(mb))
                d_ref = _distance_3d(_get_world_pos(ra), _get_world_pos(rb))
                if d_mov > 1e-4 and d_ref > 1e-4:
                    scale_factor = d_ref / d_mov
                    scale_basis = basis_label
                    matched_scale = True
                    break

        if not matched_scale and p_mov_anchor[1] > 1.0 and p_ref_anchor[1] > 1.0:
            scale_factor = p_ref_anchor[1] / p_mov_anchor[1]
            scale_basis = f"{resolved_anchor_name}ボーン地上高比率"

        scale_factor = max(0.1, min(5.0, float(scale_factor)))

    # 原点基準でスケールした後の基準ボーン位置から、参照側の基準ボーン位置へ重ねる移動量を計算
    scaled_x = p_mov_anchor[0] * scale_factor
    scaled_y = p_mov_anchor[1] * scale_factor
    scaled_z = p_mov_anchor[2] * scale_factor

    offset_x = p_ref_anchor[0] - scaled_x
    offset_y = p_ref_anchor[1] - scaled_y
    offset_z = p_ref_anchor[2] - scaled_z

    return {
        "moving_model": mov_root,
        "reference_model": ref_root,
        "anchor_bone": resolved_anchor_name,
        "scale_factor": round(scale_factor, 4),
        "offset_x": round(offset_x, 4),
        "offset_y": round(offset_y, 4),
        "offset_z": round(offset_z, 4),
        "scale_basis": scale_basis,
        "moving_anchor_pos": p_mov_anchor,
        "reference_anchor_pos": p_ref_anchor,
        "moving_neck_pos": p_mov_anchor,
        "reference_neck_pos": p_ref_anchor,
    }


@skin_utils.undo_chunk("MMD_PreviewAlignment")
def preview_alignment_transform(moving_model, scale_factor=1.0, offset_x=0.0, offset_y=0.0, offset_z=0.0):
    """
    指定したスケール倍率と位置オフセットをプレビュー適用
    ルートジョイントのトランスフォームを一時変更してビューポート上で位置合わせ結果を確認します。
    """
    mov_root = _to_long_name(moving_model)
    if not mov_root:
        return False

    if mov_root in _alignment_preview_backup:
        reset_alignment_preview(mov_root)

    bone_info = check_standard_bones(mov_root)
    root_joints = bone_info["root_joints"]
    all_joints = bone_info["all_joints"]

    backup_entry = {
        "root_joints": {},
        "ssc_states": {},
        "model_transform": None,
    }

    if root_joints:
        for j in all_joints:
            if mc.attributeQuery("segmentScaleCompensate", node=j, exists=True):
                try:
                    backup_entry["ssc_states"][j] = bool(mc.getAttr(f"{j}.segmentScaleCompensate"))
                    mc.setAttr(f"{j}.segmentScaleCompensate", False)
                except Exception:
                    pass

        for rj in root_joints:
            t_orig = mc.getAttr(f"{rj}.translate")[0]
            s_orig = mc.getAttr(f"{rj}.scale")[0]
            backup_entry["root_joints"][rj] = {
                "translate": (float(t_orig[0]), float(t_orig[1]), float(t_orig[2])),
                "scale": (float(s_orig[0]), float(s_orig[1]), float(s_orig[2])),
            }
            new_tx = float(t_orig[0]) * scale_factor + offset_x
            new_ty = float(t_orig[1]) * scale_factor + offset_y
            new_tz = float(t_orig[2]) * scale_factor + offset_z
            mc.setAttr(f"{rj}.scale", scale_factor, scale_factor, scale_factor, type="double3")
            mc.setAttr(f"{rj}.translate", new_tx, new_ty, new_tz, type="double3")
    else:
        t_orig = mc.getAttr(f"{mov_root}.translate")[0]
        s_orig = mc.getAttr(f"{mov_root}.scale")[0]
        backup_entry["model_transform"] = {
            "translate": (float(t_orig[0]), float(t_orig[1]), float(t_orig[2])),
            "scale": (float(s_orig[0]), float(s_orig[1]), float(s_orig[2])),
        }
        mc.setAttr(f"{mov_root}.scale", scale_factor, scale_factor, scale_factor, type="double3")
        mc.setAttr(
            f"{mov_root}.translate",
            float(t_orig[0]) + offset_x,
            float(t_orig[1]) + offset_y,
            float(t_orig[2]) + offset_z,
            type="double3",
        )

    _alignment_preview_backup[mov_root] = backup_entry
    return True


@skin_utils.undo_chunk("MMD_ResetAlignmentPreview")
def reset_alignment_preview(moving_model=None):
    """
    プレビュー適用中の位置合わせを元の初期状態へ戻す
    """
    targets = list(_alignment_preview_backup.keys()) if moving_model is None else [_to_long_name(moving_model)]
    for mov_root in targets:
        if not mov_root or mov_root not in _alignment_preview_backup:
            continue
        entry = _alignment_preview_backup.pop(mov_root)
        for rj, vals in entry.get("root_joints", {}).items():
            if mc.objExists(rj):
                tx, ty, tz = vals["translate"]
                sx, sy, sz = vals["scale"]
                try:
                    mc.setAttr(f"{rj}.translate", tx, ty, tz, type="double3")
                    mc.setAttr(f"{rj}.scale", sx, sy, sz, type="double3")
                except Exception:
                    pass
        for j, ssc_val in entry.get("ssc_states", {}).items():
            if mc.objExists(j):
                try:
                    mc.setAttr(f"{j}.segmentScaleCompensate", bool(ssc_val))
                except Exception:
                    pass
        mt = entry.get("model_transform")
        if mt and mc.objExists(mov_root):
            tx, ty, tz = mt["translate"]
            sx, sy, sz = mt["scale"]
            try:
                mc.setAttr(f"{mov_root}.translate", tx, ty, tz, type="double3")
                mc.setAttr(f"{mov_root}.scale", sx, sy, sz, type="double3")
            except Exception:
                pass
    return True


def _scale_blendshape_deltas(mesh_shape, model_root, scale_factor):
    """スケール倍率が1.0以外のとき、blendShape の頂点モーフ差分ベクトルを同倍率でスケール"""
    if abs(scale_factor - 1.0) <= 1e-5:
        return
    history = mc.listHistory(mesh_shape, pruneDagObjects=True) or []
    bs_nodes = mc.ls(history, type="blendShape")
    if not bs_nodes:
        return

    bs_node = bs_nodes[0]
    sel = om.MSelectionList()
    sel.add(bs_node)
    bs_mobj = sel.getDependNode(0)
    fn_bs = om.MFnDependencyNode(bs_mobj)

    plug_it_0 = fn_bs.findPlug("inputTarget", False).elementByLogicalIndex(0)
    plug_target_group = plug_it_0.child(0)
    for t_idx in plug_target_group.getExistingArrayAttributeIndices():
        try:
            plug_grp = plug_target_group.elementByLogicalIndex(t_idx)
            plug_item = plug_grp.child(0).elementByLogicalIndex(6000)
            plug_pts = None
            for c_i in range(plug_item.numChildren()):
                ch = plug_item.child(c_i)
                ch_long = ch.partialName(useLongNames=True)
                if "inputPointsTarget" in ch_long or ch_long == "ipt":
                    plug_pts = ch
                    break
            if plug_pts:
                pts_obj = plug_pts.asMObject()
                if not pts_obj.isNull():
                    pts_arr = om.MFnPointArrayData(pts_obj).array()
                    scaled_arr = om.MPointArray()
                    for k in range(len(pts_arr)):
                        pt = pts_arr[k]
                        scaled_arr.append(
                            om.MPoint(
                                float(pt.x) * scale_factor,
                                float(pt.y) * scale_factor,
                                float(pt.z) * scale_factor,
                                1.0,
                            )
                        )
                    plug_pts.setMObject(om.MFnPointArrayData().create(scaled_arr))
        except Exception:
            pass


@skin_utils.undo_chunk("MMD_CommitAlignmentTransform")
def commit_alignment_transform(moving_model, scale_factor=1.0, offset_x=0.0, offset_y=0.0, offset_z=0.0):
    """
    位置合わせ・スケール調整を確定
    メッシュに makeIdentity を使わず、全ジョイントのスケールを (1,1,1) に保ったままローカル座標を更新し、
    ベースメッシュ頂点・モーフ差分・スキンクラスタの bindPreMatrix および dagPose（バインドポーズ）を再設定します。
    """
    mov_root = _to_long_name(moving_model)
    if not mov_root:
        return False

    # プレビュー中の場合は一旦初期状態へ戻してから確定値を焼き込む
    if mov_root in _alignment_preview_backup:
        reset_alignment_preview(mov_root)

    if (
        abs(scale_factor - 1.0) <= 1e-6
        and abs(offset_x) <= 1e-6
        and abs(offset_y) <= 1e-6
        and abs(offset_z) <= 1e-6
    ):
        return True

    bone_info = check_standard_bones(mov_root)
    all_joints = bone_info["all_joints"]
    root_joint_set = set(bone_info["root_joints"])
    meshes = skin_utils.get_model_meshes(mov_root, include_edge=True)

    # スキンクラスタを一時的に envelope=0 に設定
    skin_nodes = []
    for shp in meshes:
        sk = skin_utils.get_skin_cluster(shp)
        if sk and sk not in skin_nodes:
            skin_nodes.append(sk)
            try:
                mc.setAttr(f"{sk}.envelope", 0.0)
            except Exception:
                pass

    try:
        # ベースメッシュ（および中間Origシェイプ）の頂点座標と blendShape 差分を更新
        for shp in meshes:
            parents = mc.listRelatives(shp, parent=True, fullPath=True) or [shp]
            p_tr = parents[0]
            all_shapes = mc.listRelatives(p_tr, shapes=True, type="mesh", fullPath=True) or [shp]

            for s_node in all_shapes:
                try:
                    sel = om.MSelectionList()
                    sel.add(s_node)
                    dag = sel.getDagPath(0)
                    mfn_m = om.MFnMesh(dag)
                    pts = mfn_m.getPoints(om.MSpace.kObject)
                    new_pts = om.MPointArray()
                    for i in range(len(pts)):
                        p = pts[i]
                        new_pts.append(
                            om.MPoint(
                                float(p.x) * scale_factor + offset_x,
                                float(p.y) * scale_factor + offset_y,
                                float(p.z) * scale_factor + offset_z,
                                1.0,
                            )
                        )
                    mfn_m.setPoints(new_pts, om.MSpace.kObject)
                except Exception:
                    pass

            _scale_blendshape_deltas(shp, mov_root, scale_factor)

        # 全ジョイントのローカル移動量をスケール・オフセット更新（スケールは 1,1,1 を維持）
        for j in all_joints:
            try:
                cur_t = mc.getAttr(f"{j}.translate")[0]
                if j in root_joint_set:
                    ntx = float(cur_t[0]) * scale_factor + offset_x
                    nty = float(cur_t[1]) * scale_factor + offset_y
                    ntz = float(cur_t[2]) * scale_factor + offset_z
                else:
                    ntx = float(cur_t[0]) * scale_factor
                    nty = float(cur_t[1]) * scale_factor
                    ntz = float(cur_t[2]) * scale_factor

                mc.setAttr(f"{j}.translate", ntx, nty, ntz, type="double3")
                mc.setAttr(f"{j}.scale", 1.0, 1.0, 1.0, type="double3")

                if mc.attributeQuery("mmdInitialTranslate", node=j, exists=True):
                    mc.setAttr(f"{j}.mmdInitialTranslate", ntx, nty, ntz, type="double3")
            except Exception:
                pass

        # 各スキンクラスタの bindPreMatrix を新しいジョイントの worldInverseMatrix で更新
        for sk in skin_nodes:
            sel_sk = om.MSelectionList()
            sel_sk.add(sk)
            fn_sk = om.MFnDependencyNode(sel_sk.getDependNode(0))
            mat_plug = fn_sk.findPlug("matrix", False)
            for log_idx in mat_plug.getExistingArrayAttributeIndices():
                conns = mc.listConnections(f"{sk}.matrix[{log_idx}]", source=True, destination=False) or []
                if conns:
                    j_node = conns[0]
                    try:
                        inv_mat = mc.getAttr(f"{j_node}.worldInverseMatrix[0]")
                        mc.setAttr(f"{sk}.bindPreMatrix[{log_idx}]", inv_mat, type="matrix")
                    except Exception:
                        pass

        # バインドポーズ (dagPose) の再設定
        if all_joints:
            bind_poses = mc.dagPose(all_joints[0], query=True, bindPose=True) or []
            for bp in bind_poses:
                try:
                    mc.dagPose(all_joints, reset=True, name=bp)
                except Exception:
                    pass
    finally:
        for sk in skin_nodes:
            if mc.objExists(sk):
                try:
                    mc.setAttr(f"{sk}.envelope", 1.0)
                except Exception:
                    pass

    return True
