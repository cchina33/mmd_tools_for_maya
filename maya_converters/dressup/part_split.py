# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - ウェイト基準の頭・体自動パーツ分けモジュール
「首」および「頭」ボーンの階層とスキンウェイト比率を用いて、
各ポリゴン面を「頭パーツ（頭部・顔・髪・頭飾り）」と「体パーツ（首下・胴体・衣装・四肢）」へ自動分類し、
ビューポートでのハイライト選択プレビューおよび頂点番号付け替え付きの安全な不要側削除を提供します。
"""

import importlib
import maya.cmds as mc
import maya.api.OpenMaya as om

from . import skin_utils
from . import align
importlib.reload(skin_utils)
importlib.reload(align)

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


_HEAD_BONE_KEYWORDS = (
    "頭", "顔", "目", "瞳", "眉", "まつ毛", "睫毛", "口", "舌", "歯", "牙",
    "耳", "髪", "前髪", "後髪", "横髪", "もみあげ", "アホ毛", "ツインテ", "ポニテ",
    "帽", "眼鏡", "メガネ", "ヘッド", "head", "face", "eye", "brow", "lip",
    "mouth", "tongue", "teeth", "ear", "hair", "hat",
)

_BODY_BONE_KEYWORDS = (
    "上半身", "下半身", "胸", "肩", "腕", "ひじ", "肘", "手", "指",
    "親指", "人指", "中指", "薬指", "小指", "足", "ひざ", "膝", "つま先",
    "スカート", "袖", "マント", "腰", "センター", "グルーブ", "全ての親",
    "upper", "lower", "breast", "bust", "shoulder", "arm", "elbow", "wrist",
    "hand", "thumb", "index", "middle", "ring", "pinky", "leg", "knee", "ankle",
    "toe", "skirt", "center", "groove", "mother",
)


def _to_long_name(node_name):
    """ノード名をフルDAGパスへ変換"""
    if not node_name or not mc.objExists(node_name):
        return None
    res = mc.ls(node_name, long=True)
    return res[0] if res else node_name


def get_head_bone_set(model_root, include_neck=False):
    """
    指定モデルの「頭グループ」に属するジョイント集合（フルDAGパス）を取得
    「頭」ボーンとその全子孫、「首」ボーン配下の子孫、および頭部キーワードを持つボーンを収集します。
    """
    long_root = _to_long_name(model_root)
    if not long_root:
        return set(), None

    bone_info = align.check_standard_bones(long_root)
    found = bone_info["found"]
    all_joints = bone_info["all_joints"]

    head_joint = found.get("頭")
    neck_joint = found.get("首")

    head_bones = set()

    if head_joint and mc.objExists(head_joint):
        head_bones.add(head_joint)
        desc = mc.listRelatives(head_joint, allDescendents=True, type="joint", fullPath=True) or []
        head_bones.update(desc)

    if neck_joint and mc.objExists(neck_joint):
        if include_neck:
            head_bones.add(neck_joint)
        neck_desc = mc.listRelatives(neck_joint, allDescendents=True, type="joint", fullPath=True) or []
        head_bones.update(neck_desc)

    # 上半身2等に直接親子付けされた髪・帽子ボーンを名前および高さから補完
    head_y = None
    if head_joint and mc.objExists(head_joint):
        head_y = float(mc.xform(head_joint, query=True, worldSpace=True, translation=True)[1])
    elif neck_joint and mc.objExists(neck_joint):
        head_y = float(mc.xform(neck_joint, query=True, worldSpace=True, translation=True)[1])

    for j in all_joints:
        if j in head_bones or j == neck_joint:
            continue
        canon = skin_utils.get_bone_canonical_name(j, model_root=long_root)
        canon_low = canon.lower()

        if any(bk in canon_low for bk in _BODY_BONE_KEYWORDS):
            continue

        if any(hk in canon_low for hk in _HEAD_BONE_KEYWORDS):
            head_bones.add(j)
            desc = mc.listRelatives(j, allDescendents=True, type="joint", fullPath=True) or []
            head_bones.update(desc)
            continue

        if head_y is not None:
            try:
                jy = float(mc.xform(j, query=True, worldSpace=True, translation=True)[1])
                if jy >= head_y + 0.2:
                    head_bones.add(j)
            except Exception:
                pass

    return head_bones, neck_joint


def classify_head_body_faces(model_root, threshold=0.5, include_neck=False):
    """
    各ポリゴン面の頂点ウェイトにおける「頭グループ」比率を計算し、
    閾値（既定 0.5 = 50%）以上を「頭パーツ面」、未満を「体パーツ面」に分類
    """
    long_root = _to_long_name(model_root)
    if not long_root:
        return None

    meshes = skin_utils.get_model_meshes(long_root, include_edge=False)
    if not meshes:
        return None

    head_bone_set, neck_joint = get_head_bone_set(long_root, include_neck=include_neck)

    neck_y = 15.0
    if neck_joint and mc.objExists(neck_joint):
        try:
            neck_y = float(mc.xform(neck_joint, query=True, worldSpace=True, translation=True)[1])
        except Exception:
            pass

    mesh_head_faces = {}
    mesh_body_faces = {}
    head_face_ranges = []
    body_face_ranges = []
    total_head_count = 0
    total_body_count = 0

    for shp in meshes:
        parents = mc.listRelatives(shp, parent=True, fullPath=True) or [shp]
        mesh_tr = parents[0]

        sel = om.MSelectionList()
        sel.add(shp)
        dag = sel.getDagPath(0)
        mfn_mesh = om.MFnMesh(dag)
        num_verts = mfn_mesh.numVertices
        num_faces = mfn_mesh.numPolygons

        w_data = skin_utils.extract_mesh_skin_weights(shp, model_root=long_root)
        vtx_head_ratio = [0.0] * num_verts

        if w_data and head_bone_set:
            infs = w_data.get("influences", [])
            inf_head_factor = {}
            for info in infs:
                idx = int(info["index"])
                inf_long = info.get("long_name", "")
                if inf_long in head_bone_set:
                    inf_head_factor[idx] = 1.0
                else:
                    inf_head_factor[idx] = 0.0

            sparse = w_data.get("sparse_weights", [])
            for v_i in range(min(num_verts, len(sparse))):
                h_sum = 0.0
                t_sum = 0.0
                for pair in sparse[v_i]:
                    if len(pair) >= 2:
                        inf_i = int(pair[0])
                        w_val = float(pair[1])
                        t_sum += w_val
                        h_sum += w_val * inf_head_factor.get(inf_i, 0.0)
                if t_sum > 1e-6:
                    vtx_head_ratio[v_i] = h_sum / t_sum
        else:
            # スキンクラスタが存在しない場合は首の高さ座標でフォールバック判定
            pts = mfn_mesh.getPoints(om.MSpace.kWorld)
            for v_i in range(num_verts):
                vtx_head_ratio[v_i] = 1.0 if float(pts[v_i].y) >= neck_y else 0.0

        h_faces = []
        b_faces = []
        for f_i in range(num_faces):
            f_verts = mfn_mesh.getPolygonVertices(f_i)
            if not f_verts:
                b_faces.append(f_i)
                continue
            avg_ratio = sum(vtx_head_ratio[int(v)] for v in f_verts) / float(len(f_verts))
            if avg_ratio >= float(threshold):
                h_faces.append(f_i)
            else:
                b_faces.append(f_i)

        if h_faces:
            mesh_head_faces[shp] = h_faces
            head_face_ranges.extend(mesh_mask_utils._format_component_ranges(mesh_tr, "f", h_faces))
        if b_faces:
            mesh_body_faces[shp] = b_faces
            body_face_ranges.extend(mesh_mask_utils._format_component_ranges(mesh_tr, "f", b_faces))

        total_head_count += len(h_faces)
        total_body_count += len(b_faces)

    return {
        "model_root": long_root,
        "threshold": float(threshold),
        "include_neck": bool(include_neck),
        "head_face_count": total_head_count,
        "body_face_count": total_body_count,
        "total_face_count": total_head_count + total_body_count,
        "mesh_head_faces": mesh_head_faces,
        "mesh_body_faces": mesh_body_faces,
        "head_face_ranges": head_face_ranges,
        "body_face_ranges": body_face_ranges,
    }


def preview_part_split(model_root, keep_part="head", threshold=0.5, include_neck=False):
    """
    頭・体の自動パーツ分けを実行し、削除対象となる側のポリゴン面をビューポートで選択ハイライト表示
    keep_part="head"（素体・頭モデル用）では「体パーツ面」を選択し、
    keep_part="body"（衣装・体モデル用）では「頭パーツ面」を選択します。
    """
    cls_res = classify_head_body_faces(model_root, threshold=threshold, include_neck=include_neck)
    if not cls_res:
        return None

    if keep_part == "head":
        delete_ranges = cls_res["body_face_ranges"]
        delete_mesh_map = cls_res["mesh_body_faces"]
        delete_count = cls_res["body_face_count"]
        keep_count = cls_res["head_face_count"]
    else:
        delete_ranges = cls_res["head_face_ranges"]
        delete_mesh_map = cls_res["mesh_head_faces"]
        delete_count = cls_res["head_face_count"]
        keep_count = cls_res["body_face_count"]

    if delete_ranges:
        try:
            mc.select(delete_ranges, replace=True)
        except Exception:
            pass
    else:
        mc.select(clear=True)

    return {
        "model_root": cls_res["model_root"],
        "keep_part": keep_part,
        "threshold": float(threshold),
        "include_neck": bool(include_neck),
        "head_face_count": cls_res["head_face_count"],
        "body_face_count": cls_res["body_face_count"],
        "delete_face_count": delete_count,
        "keep_face_count": keep_count,
        "delete_mesh_faces": delete_mesh_map,
        "delete_face_ranges": delete_ranges,
    }


@skin_utils.undo_chunk("MMD_CommitPartSplitDeletion")
def commit_part_split_deletion(
    model_root,
    keep_part="head",
    threshold=0.5,
    include_neck=False,
    delete_unused_morphs=True,
    cleanup_unused_bones=False,
):
    """
    自動分類された不要側パーツ（頭モデルなら体側、体モデルなら頭側）を確定削除
    P2 の頂点番号付け替え付き削除エンジン（delete_materials_and_remap）を使用し、
    残る側のスキンウェイトと表情モーフを崩さずに削除します。
    """
    preview = preview_part_split(
        model_root=model_root,
        keep_part=keep_part,
        threshold=threshold,
        include_neck=include_neck,
    )
    if not preview:
        return {"success": False, "message": "対象モデルのポリゴン面を分類できませんでした。"}

    if preview["delete_face_count"] <= 0:
        return {"success": False, "message": "指定された閾値では削除対象となるポリゴン面がありません。"}
    if preview["keep_face_count"] <= 0:
        return {"success": False, "message": "残るポリゴン面が0になるため削除を中止しました。閾値を確認してください。"}

    part_label = "頭以外の体パーツ" if keep_part == "head" else "頭・髪パーツ"
    synthetic_target = [{
        "sg": None,
        "shader": None,
        "name_ja": part_label,
        "name_en": keep_part,
        "face_count": preview["delete_face_count"],
        "faces": preview["delete_face_ranges"],
        "mesh_face_indices": preview["delete_mesh_faces"],
    }]

    del_res = mesh_mask_utils.delete_materials_and_remap(
        model_root=preview["model_root"],
        target_material_datas=synthetic_target,
        delete_unused_morphs=delete_unused_morphs,
        cleanup_unused_shaders=False,
    )
    if not del_res.get("success"):
        return del_res

    cleaned_bones = 0
    cleaned_physics = 0
    if cleanup_unused_bones:
        try:
            from .. import model_modifier
            cleaned_bones, cleaned_physics = model_modifier.cleanup_unused_bones_and_physics(preview["model_root"])
        except Exception:
            pass

    mc.select(clear=True)
    del_res["cleaned_bones"] = cleaned_bones
    del_res["cleaned_physics"] = cleaned_physics
    del_res["keep_part"] = keep_part
    return del_res
