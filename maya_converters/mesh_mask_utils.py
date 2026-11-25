# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 材質マスキング表示・頂点番号付け替え付きパーツ削除モジュール
PMXエディタの絞り込み表示（マスキング）と同様に、材質単位での表示・非表示切り替え、
選択材質または非表示材質のポリゴン面・孤立頂点削除、スキンウェイトおよびモーフ差分の
頂点番号付け替え（リマップ）、不要モーフの自動判定・削除、構造JSON更新を提供します。
"""

import re
import json
import math
import importlib

import maya.cmds as mc
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

try:
    from .dressup import skin_utils
    importlib.reload(skin_utils)
except Exception:
    try:
        from maya_converters.dressup import skin_utils
        importlib.reload(skin_utils)
    except Exception:
        from dressup import skin_utils
        importlib.reload(skin_utils)


# モデルごとのマスキング状態および元の表示状態を保持する辞書
_active_mask_states = {}

_FACE_INDEX_RE = re.compile(r"\.f\[(\d+)(?::(\d+))?\]")


def _to_long_name(node_name):
    """ノード名をフルDAGパスへ変換"""
    if not node_name or not mc.objExists(node_name):
        return None
    res = mc.ls(node_name, long=True)
    return res[0] if res else node_name


def _format_component_ranges(node_name, comp_type, indices):
    """
    整数インデックス集合を連続区間形式（例: node.f[0:99]）のリストへ圧縮変換
    大量の面や頂点を高速にMayaコマンドへ渡すために使用します。
    """
    sorted_idx = sorted(set(int(i) for i in indices if i is not None and int(i) >= 0))
    if not sorted_idx:
        return []

    ranges = []
    start = sorted_idx[0]
    prev = start
    for idx in sorted_idx[1:]:
        if idx == prev + 1:
            prev = idx
        else:
            if start == prev:
                ranges.append(f"{node_name}.{comp_type}[{start}]")
            else:
                ranges.append(f"{node_name}.{comp_type}[{start}:{prev}]")
            start = idx
            prev = idx

    if start == prev:
        ranges.append(f"{node_name}.{comp_type}[{start}]")
    else:
        ranges.append(f"{node_name}.{comp_type}[{start}:{prev}]")
    return ranges


def _parse_face_components_by_mesh(face_components, valid_meshes):
    """
    展開済みまたは区間形式のフェース文字列リストからメッシュシェイプごとの面番号集合を抽出
    """
    transform_to_shape = {}
    shape_set = set(valid_meshes)
    for shp in valid_meshes:
        parents = mc.listRelatives(shp, parent=True, fullPath=True) or []
        if parents:
            transform_to_shape[parents[0]] = shp
            transform_to_shape[parents[0].split("|")[-1]] = shp
        transform_to_shape[shp] = shp
        transform_to_shape[shp.split("|")[-1]] = shp

    mesh_faces = {shp: set() for shp in valid_meshes}
    for comp in face_components:
        if ".f[" not in comp:
            continue
        node_part = comp.split(".f[")[0]
        long_n = _to_long_name(node_part)
        shp = transform_to_shape.get(long_n) or transform_to_shape.get(node_part)
        if not shp or shp not in shape_set:
            continue
        m = _FACE_INDEX_RE.search(comp)
        if not m:
            continue
        start_i = int(m.group(1))
        end_i = int(m.group(2)) if m.group(2) is not None else start_i
        mesh_faces[shp].update(range(start_i, end_i + 1))

    return mesh_faces


def get_model_materials_data(model_root, preserve_visibility_from=None):
    """
    指定されたモデル階層下の全ポリゴンメッシュから材質情報を収集
    各材質に紐づくシェーダー、日本語名、英語名、割り当てフェース、メッシュ別面番号、
    および現在のマスキング表示フラグを返します。
    """
    long_root = _to_long_name(model_root)
    if not long_root:
        return []

    valid_meshes = skin_utils.get_model_meshes(long_root, include_edge=False)
    if not valid_meshes:
        return []

    valid_mesh_set = set(valid_meshes)
    prev_vis_map = {}
    if preserve_visibility_from:
        for item in preserve_visibility_from:
            sg_key = item.get("sg")
            if sg_key:
                prev_vis_map[sg_key] = bool(item.get("visible", True))
    elif long_root in _active_mask_states:
        hidden_sgs = _active_mask_states[long_root].get("hidden_sgs", set())
        for sg_k in hidden_sgs:
            prev_vis_map[sg_k] = False

    sg_set = set()
    for m in valid_meshes:
        sgs = mc.listConnections(m, type="shadingEngine") or []
        for sg in sgs:
            if sg != "initialShadingGroup":
                sg_set.add(sg)
        if not sgs:
            sgs_all = mc.listConnections(m, type="shadingEngine") or []
            sg_set.update(sgs_all)

    raw_entries = []
    for sg in sorted(list(sg_set)):
        shaders = mc.listConnections(f"{sg}.surfaceShader") or []
        shd = shaders[0] if shaders else sg

        name_ja = ""
        if mc.attributeQuery("originalName", node=shd, exists=True):
            try:
                name_ja = mc.getAttr(f"{shd}.originalName") or ""
            except Exception:
                name_ja = ""
        if not name_ja:
            name_ja = shd.split("|")[-1].split(":")[-1]

        name_en = ""
        if mc.attributeQuery("englishName", node=shd, exists=True):
            try:
                name_en = mc.getAttr(f"{shd}.englishName") or ""
            except Exception:
                name_en = ""

        members = mc.sets(sg, query=True) or []
        model_members = []
        for mem in members:
            node_part = mem.split(".")[0]
            if not mc.objExists(node_part):
                continue
            long_n = _to_long_name(node_part)
            if not long_n:
                continue

            is_model_mesh = False
            if long_n in valid_mesh_set:
                is_model_mesh = True
            else:
                shapes = mc.listRelatives(long_n, shapes=True, fullPath=True) or []
                for shp in shapes:
                    if shp in valid_mesh_set:
                        is_model_mesh = True
                        break

            if is_model_mesh:
                model_members.append(mem)

        assigned_faces = []
        if model_members:
            try:
                conv = mc.polyListComponentConversion(model_members, toFace=True) or []
                if conv:
                    assigned_faces = mc.filterExpand(conv, sm=34) or []
            except Exception:
                assigned_faces = []

        mesh_face_map = _parse_face_components_by_mesh(assigned_faces, valid_meshes)
        total_face_count = sum(len(f_set) for f_set in mesh_face_map.values())
        if total_face_count == 0 and assigned_faces:
            total_face_count = len(assigned_faces)

        min_face_idx = float("inf")
        for f_set in mesh_face_map.values():
            if f_set:
                min_face_idx = min(min_face_idx, min(f_set))

        compact_faces = []
        for shp, f_set in mesh_face_map.items():
            if f_set:
                parents = mc.listRelatives(shp, parent=True, fullPath=True) or [shp]
                compact_faces.extend(_format_component_ranges(parents[0], "f", f_set))
        if not compact_faces and assigned_faces:
            compact_faces = assigned_faces

        raw_entries.append({
            "sg": sg,
            "shader": shd,
            "name_ja": str(name_ja),
            "name_en": str(name_en),
            "face_count": total_face_count,
            "members": model_members,
            "faces": compact_faces,
            "mesh_face_indices": {k: sorted(list(v)) for k, v in mesh_face_map.items() if v},
            "min_face_idx": min_face_idx,
            "visible": prev_vis_map.get(sg, True),
        })

    # PMX本来の材質順（最小フェース番号順）でソート
    raw_entries.sort(key=lambda x: (x["min_face_idx"], x["sg"]))

    materials_data = []
    for idx, entry in enumerate(raw_entries):
        entry["index"] = idx
        materials_data.append(entry)

    return materials_data


def _find_edge_meshes(model_root):
    """モデルに付随する輪郭線用エッジメッシュを探索"""
    long_root = _to_long_name(model_root)
    if not long_root:
        return []
    root_short = long_root.split("|")[-1]
    edge_nodes = []
    candidate = f"{root_short}_Edge"
    if mc.objExists(candidate):
        edge_nodes.append(_to_long_name(candidate))
    for shp in skin_utils.get_model_meshes(long_root, include_edge=True):
        parents = mc.listRelatives(shp, parent=True, fullPath=True) or []
        p_tr = parents[0] if parents else shp
        if p_tr.split("|")[-1].endswith("_Edge") and p_tr not in edge_nodes:
            edge_nodes.append(p_tr)
    return [e for e in edge_nodes if e and mc.objExists(e)]


def _get_model_panels():
    """シーン内の3Dビューポートパネル一覧を取得"""
    try:
        if mc.about(batch=True):
            return []
        return mc.getPanel(type="modelPanel") or []
    except Exception:
        return []


def is_mask_active(model_root):
    """指定モデルに対してマスキング表示が適用中か判定"""
    long_root = _to_long_name(model_root)
    if not long_root or long_root not in _active_mask_states:
        return False
    return bool(_active_mask_states[long_root].get("is_masked", False))


def apply_material_mask(model_root, materials_data):
    """
    チェックされた材質のポリゴン面のみをビューポートに表示（マスキング表示）
    単一メッシュモデルは面単位の Isolate Select を用い、
    材質分割モデルはサブメッシュの visibility 切り替えを併用します。
    データは一切削除せず、見た目のみを切り替えます。
    """
    long_root = _to_long_name(model_root)
    if not long_root or not materials_data:
        return False

    valid_meshes = skin_utils.get_model_meshes(long_root, include_edge=False)
    if not valid_meshes:
        return False

    # 初回マスク適用時に元の表示状態を記録
    if long_root not in _active_mask_states:
        mesh_vis_backup = {}
        for shp in valid_meshes:
            parents = mc.listRelatives(shp, parent=True, fullPath=True) or [shp]
            tr = parents[0]
            try:
                mesh_vis_backup[tr] = bool(mc.getAttr(f"{tr}.visibility"))
            except Exception:
                mesh_vis_backup[tr] = True

        edge_vis_backup = {}
        for e_node in _find_edge_meshes(long_root):
            try:
                edge_vis_backup[e_node] = bool(mc.getAttr(f"{e_node}.visibility"))
            except Exception:
                edge_vis_backup[e_node] = True

        _active_mask_states[long_root] = {
            "is_masked": False,
            "hidden_sgs": set(),
            "visible_sgs": set(),
            "mesh_vis_backup": mesh_vis_backup,
            "edge_vis_backup": edge_vis_backup,
        }

    state = _active_mask_states[long_root]
    visible_entries = [d for d in materials_data if d.get("visible", True) and d.get("face_count", 0) > 0]
    hidden_entries = [d for d in materials_data if not d.get("visible", True) and d.get("face_count", 0) > 0]
    active_entries = [d for d in materials_data if d.get("face_count", 0) > 0]

    state["visible_sgs"] = set(d["sg"] for d in visible_entries if d.get("sg"))
    state["hidden_sgs"] = set(d["sg"] for d in hidden_entries if d.get("sg"))

    # 全材質が表示状態の場合はマスク解除と同じ状態に戻す
    if len(visible_entries) == len(active_entries) and len(hidden_entries) == 0:
        restore_material_mask(long_root)
        return True

    state["is_masked"] = True

    # マスク中は輪郭線エッジメッシュを一時的に非表示にして視認性を確保
    for e_node in _find_edge_meshes(long_root):
        try:
            mc.setAttr(f"{e_node}.visibility", False)
        except Exception:
            pass

    # 材質分割モデル（複数サブメッシュ）の場合はサブメッシュ単位の visibility も制御
    if len(valid_meshes) > 1:
        visible_meshes = set()
        for d in visible_entries:
            for shp in d.get("mesh_face_indices", {}).keys():
                visible_meshes.add(shp)
        for shp in valid_meshes:
            parents = mc.listRelatives(shp, parent=True, fullPath=True) or [shp]
            tr = parents[0]
            try:
                mc.setAttr(f"{tr}.visibility", shp in visible_meshes)
            except Exception:
                pass
    else:
        shp = valid_meshes[0]
        parents = mc.listRelatives(shp, parent=True, fullPath=True) or [shp]
        tr = parents[0]
        try:
            mc.setAttr(f"{tr}.visibility", len(visible_entries) > 0)
        except Exception:
            pass

    # 3Dビューポートパネルに対して面単位の Isolate Select を適用
    panels = _get_model_panels()
    if panels:
        visible_faces = []
        for d in visible_entries:
            visible_faces.extend(d.get("faces", []))

        prev_sel = mc.ls(selection=True) or []
        try:
            for panel in panels:
                try:
                    mc.isolateSelect(panel, state=False)
                except Exception:
                    pass

            if visible_faces:
                mc.select(visible_faces, replace=True)
                for panel in panels:
                    try:
                        mc.isolateSelect(panel, state=True)
                        mc.isolateSelect(panel, addSelected=True)
                    except Exception:
                        pass
            else:
                mc.select(clear=True)
                for panel in panels:
                    try:
                        mc.isolateSelect(panel, state=True)
                    except Exception:
                        pass
        finally:
            try:
                if prev_sel:
                    valid_prev = [x for x in prev_sel if mc.objExists(x)]
                    if valid_prev:
                        mc.select(valid_prev, replace=True)
                    else:
                        mc.select(clear=True)
                else:
                    mc.select(clear=True)
            except Exception:
                pass

    return True


def restore_material_mask(model_root=None):
    """
    マスキング表示を解除し、モデルおよびビューポートをマスク前の表示状態へ復元
    model_root に None を渡した場合は全モデルのマスクを解除します。
    """
    target_roots = []
    if model_root is None:
        target_roots = list(_active_mask_states.keys())
    else:
        long_root = _to_long_name(model_root)
        if long_root and long_root in _active_mask_states:
            target_roots = [long_root]
        elif model_root in _active_mask_states:
            target_roots = [model_root]

    panels = _get_model_panels()
    for panel in panels:
        try:
            if mc.isolateSelect(panel, query=True, state=True):
                mc.isolateSelect(panel, state=False)
        except Exception:
            pass

    for r_key in target_roots:
        state = _active_mask_states.pop(r_key, None)
        if not state:
            continue
        for tr, vis in state.get("mesh_vis_backup", {}).items():
            if mc.objExists(tr):
                try:
                    mc.setAttr(f"{tr}.visibility", bool(vis))
                except Exception:
                    pass
        for e_node, vis in state.get("edge_vis_backup", {}).items():
            if mc.objExists(e_node):
                try:
                    mc.setAttr(f"{e_node}.visibility", bool(vis))
                except Exception:
                    pass

    return True


def _find_model_blendshape(mesh_shape, model_root=None):
    """メッシュまたはモデルルートに接続されている blendShape ノードを取得"""
    history = mc.listHistory(mesh_shape, pruneDagObjects=True) or []
    bs_nodes = mc.ls(history, type="blendShape")
    if bs_nodes:
        return bs_nodes[0]

    if model_root and mc.objExists(model_root):
        if mc.attributeQuery("mmdModelStructure", node=model_root, exists=True):
            try:
                raw = mc.getAttr(f"{model_root}.mmdModelStructure")
                if raw:
                    struct = json.loads(raw)
                    bs_name = struct.get("maya", {}).get("blendshape_node")
                    if bs_name and mc.objExists(bs_name):
                        return bs_name
            except Exception:
                pass
    return None


def extract_blendshape_targets(mesh_shape, model_root=None):
    """
    blendShape ノードの inputPointsTarget / inputComponentsTarget を OpenMaya API で読み取り
    各ターゲットの番号、エイリアス名、現在のウェイト値、頂点差分リスト、
    およびアニメーションキー接続の有無を返します。
    """
    bs_node = _find_model_blendshape(mesh_shape, model_root=model_root)
    if not bs_node or not mc.objExists(bs_node):
        return None

    # エイリアス辞書 (logical_index -> alias_name) を構築
    alias_pairs = mc.aliasAttr(bs_node, query=True) or []
    idx_to_alias = {}
    for i in range(0, len(alias_pairs) - 1, 2):
        alias_name = alias_pairs[i]
        plug_name = alias_pairs[i + 1]
        m = re.search(r"weight\[(\d+)\]|w\[(\d+)\]", plug_name)
        if m:
            w_idx = int(m.group(1) or m.group(2))
            idx_to_alias[w_idx] = alias_name

    sel = om.MSelectionList()
    sel.add(bs_node)
    bs_mobj = sel.getDependNode(0)
    fn_bs = om.MFnDependencyNode(bs_mobj)

    plug_input_target = fn_bs.findPlug("inputTarget", False)
    plug_it_0 = plug_input_target.elementByLogicalIndex(0)
    plug_target_group = plug_it_0.child(0)

    logical_indices = list(plug_target_group.getExistingArrayAttributeIndices())
    weight_plug = fn_bs.findPlug("weight", False)
    for w_i in weight_plug.getExistingArrayAttributeIndices():
        if w_i not in logical_indices:
            logical_indices.append(w_i)
    logical_indices.sort()

    targets = []
    for t_idx in logical_indices:
        alias_name = idx_to_alias.get(t_idx, f"target_{t_idx:03d}")
        cur_weight = 0.0
        try:
            cur_weight = float(mc.getAttr(f"{bs_node}.weight[{t_idx}]"))
        except Exception:
            cur_weight = 0.0

        has_key = False
        try:
            conns = mc.listConnections(f"{bs_node}.weight[{t_idx}]", source=True, destination=False) or []
            if any(mc.nodeType(c).startswith("animCurve") for c in conns):
                has_key = True
        except Exception:
            has_key = False

        deltas = {}
        try:
            plug_grp = plug_target_group.elementByLogicalIndex(t_idx)
            plug_item = plug_grp.child(0).elementByLogicalIndex(6000)

            plug_pts = None
            plug_comps = None
            for c_i in range(plug_item.numChildren()):
                ch = plug_item.child(c_i)
                ch_long = ch.partialName(useLongNames=True)
                if "inputPointsTarget" in ch_long or ch_long == "ipt":
                    plug_pts = ch
                elif "inputComponentsTarget" in ch_long or ch_long == "ict":
                    plug_comps = ch

            if plug_pts and plug_comps:
                pts_obj = plug_pts.asMObject()
                if not pts_obj.isNull():
                    pts_arr = om.MFnPointArrayData(pts_obj).array()
                    ict_attr = f"{bs_node}.inputTarget[0].inputTargetGroup[{t_idx}].inputTargetItem[6000].inputComponentsTarget"
                    raw_comps = mc.getAttr(ict_attr) or []
                    vtx_indices = []
                    for c_str in raw_comps:
                        if "[" not in c_str:
                            continue
                        inner = c_str.split("[")[-1].rstrip("]")
                        if ":" in inner:
                            s_i, e_i = inner.split(":", 1)
                            vtx_indices.extend(range(int(s_i), int(e_i) + 1))
                        elif inner.isdigit():
                            vtx_indices.append(int(inner))

                    pair_len = min(len(pts_arr), len(vtx_indices))
                    for k in range(pair_len):
                        pt = pts_arr[k]
                        dx, dy, dz = float(pt.x), float(pt.y), float(pt.z)
                        if abs(dx) > 1e-7 or abs(dy) > 1e-7 or abs(dz) > 1e-7:
                            deltas[vtx_indices[k]] = (dx, dy, dz)
        except Exception as e_bs_read:
            mc.warning(f"blendShapeターゲット[{t_idx}]読み取り警告: {e_bs_read}")

        targets.append({
            "target_index": int(t_idx),
            "alias_name": alias_name,
            "weight": cur_weight,
            "has_keyframe": has_key,
            "deltas": deltas,
        })

    return {
        "blendshape_node": bs_node,
        "targets": targets,
    }


def _analyze_material_morphs_usage(model_root, all_shaders, deleted_shaders):
    """
    モデルルート上の材質モーフ属性（matmorph_*）が削除対象シェーダーのみに影響するか解析
    """
    long_root = _to_long_name(model_root)
    if not long_root:
        return [], []

    user_attrs = mc.listAttr(long_root, userDefined=True) or []
    matmorph_attrs = [a for a in user_attrs if a.startswith("matmorph_")]
    if not matmorph_attrs:
        return [], []

    all_shader_set = set(all_shaders)
    deleted_shader_set = set(deleted_shaders)

    unused_mat_morphs = []
    kept_mat_morphs = []

    for attr in matmorph_attrs:
        plug = f"{long_root}.{attr}"
        nice_name = attr
        try:
            nn = mc.attributeQuery(attr, node=long_root, niceName=True)
            if nn:
                nice_name = nn
        except Exception:
            pass

        has_key = False
        try:
            conns = mc.listConnections(plug, source=True, destination=False) or []
            if any(mc.nodeType(c).startswith("animCurve") for c in conns):
                has_key = True
        except Exception:
            has_key = False

        direct_dests = mc.listConnections(plug, source=False, destination=True) or []
        future_nodes = (mc.listHistory(direct_dests, future=True) or []) if direct_dests else []
        affected_shaders = [n for n in future_nodes if n in all_shader_set]

        info = {
            "attr_name": attr,
            "name_jp": nice_name,
            "has_keyframe": has_key,
            "affected_shaders": affected_shaders,
        }

        if affected_shaders and all(s in deleted_shader_set for s in affected_shaders):
            unused_mat_morphs.append(info)
        else:
            kept_mat_morphs.append(info)

    return unused_mat_morphs, kept_mat_morphs


def analyze_deletion_impact(model_root, target_material_datas):
    """
    削除前の事前プレビュー解析
    消える材質名、削除されるポリゴン面数、削除される孤立頂点数、
    不要になる頂点モーフ・材質モーフ一覧、アニメーションキー付きモーフ、
    および要確認のグループモーフ一覧を計算して返します。
    """
    long_root = _to_long_name(model_root)
    if not long_root or not target_material_datas:
        return None

    all_materials = get_model_materials_data(long_root)
    target_sgs = set(d["sg"] for d in target_material_datas if d.get("sg"))
    all_shaders = [d["shader"] for d in all_materials if d.get("shader")]
    deleted_shaders = [d["shader"] for d in all_materials if d.get("sg") in target_sgs and d.get("shader")]

    valid_meshes = skin_utils.get_model_meshes(long_root, include_edge=False)
    total_faces_before = 0
    total_verts_before = 0
    deleted_faces_count = 0
    deleted_verts_count = 0

    unused_vertex_morphs = []
    keyed_morph_names = []

    for shp in valid_meshes:
        sel = om.MSelectionList()
        sel.add(shp)
        dag = sel.getDagPath(0)
        mfn_mesh = om.MFnMesh(dag)
        num_f = mfn_mesh.numPolygons
        num_v = mfn_mesh.numVertices
        total_faces_before += num_f
        total_verts_before += num_v

        del_f_set = set()
        for d in target_material_datas:
            f_list = d.get("mesh_face_indices", {}).get(shp, [])
            del_f_set.update(f_list)

        deleted_faces_count += len(del_f_set)
        kept_v_set = set()
        for f_idx in range(num_f):
            if f_idx not in del_f_set:
                kept_v_set.update(int(v) for v in mfn_mesh.getPolygonVertices(f_idx))

        del_v_set = set(range(num_v)) - kept_v_set
        deleted_verts_count += len(del_v_set)

        bs_data = extract_blendshape_targets(shp, model_root=long_root)
        if bs_data:
            for t_info in bs_data["targets"]:
                deltas = t_info["deltas"]
                if not deltas:
                    continue
                rem_count = sum(1 for v_i in deltas.keys() if v_i in kept_v_set)
                if rem_count == 0:
                    unused_vertex_morphs.append({
                        "target_index": t_info["target_index"],
                        "alias_name": t_info["alias_name"],
                        "has_keyframe": t_info["has_keyframe"],
                        "original_delta_count": len(deltas),
                    })
                    if t_info["has_keyframe"]:
                        keyed_morph_names.append(t_info["alias_name"])

    unused_mat_morphs, _ = _analyze_material_morphs_usage(long_root, all_shaders, deleted_shaders)
    for mm in unused_mat_morphs:
        if mm["has_keyframe"]:
            keyed_morph_names.append(mm["name_jp"])

    # mmdModelStructure から頂点モーフの日本語名を補完し、要確認のグループモーフを抽出
    alias_to_jp = {}
    review_group_morphs = []
    if mc.attributeQuery("mmdModelStructure", node=long_root, exists=True):
        try:
            raw = mc.getAttr(f"{long_root}.mmdModelStructure")
            if raw:
                struct = json.loads(raw)
                for m_entry in struct.get("morphs", []) or []:
                    m_target = m_entry.get("maya_target")
                    m_jp = m_entry.get("name_jp") or m_target or ""
                    m_type = m_entry.get("morph_type", 1)
                    if m_target:
                        alias_to_jp[m_target] = m_jp
                    if m_type == 0:
                        review_group_morphs.append({
                            "index": m_entry.get("index", 0),
                            "name_jp": m_jp,
                            "name_en": m_entry.get("name_en", ""),
                            "morph_type": m_type,
                        })
        except Exception:
            pass

    for vm in unused_vertex_morphs:
        vm["name_jp"] = alias_to_jp.get(vm["alias_name"], vm["alias_name"])

    return {
        "model_root": long_root,
        "material_names": [d["name_ja"] for d in target_material_datas],
        "target_sgs": list(target_sgs),
        "total_faces_before": total_faces_before,
        "total_verts_before": total_verts_before,
        "deleted_faces_count": deleted_faces_count,
        "deleted_verts_count": deleted_verts_count,
        "remaining_faces_count": total_faces_before - deleted_faces_count,
        "remaining_verts_count": total_verts_before - deleted_verts_count,
        "unused_vertex_morphs": unused_vertex_morphs,
        "unused_material_morphs": unused_mat_morphs,
        "review_group_morphs": review_group_morphs,
        "keyed_morph_names": keyed_morph_names,
    }


def _rebuild_blendshape_with_remap(
    mesh_transform,
    bs_data,
    old_to_new_map,
    new_num_verts,
    delete_unused_morphs=True,
):
    """
    新しい頂点番号で blendShape ノードを再構築し、頂点モーフ差分を書き戻し
    動かす頂点がすべて削除された頂点モーフは delete_unused_morphs=True 時に除外します。
    """
    if not bs_data or not bs_data.get("targets"):
        return None, [], {}

    old_bs_name = bs_data.get("blendshape_node") or f"bs_{mesh_transform.split('|')[-1]}"
    short_bs_name = old_bs_name.split("|")[-1]
    if mc.objExists(short_bs_name):
        try:
            mc.delete(short_bs_name)
        except Exception:
            pass

    kept_targets = []
    removed_aliases = []

    for t_info in bs_data["targets"]:
        old_deltas = t_info.get("deltas", {})
        remapped_deltas = {}
        for old_v, d_vec in old_deltas.items():
            new_v = old_to_new_map.get(int(old_v))
            if new_v is not None and 0 <= new_v < new_num_verts:
                remapped_deltas[int(new_v)] = d_vec

        if not remapped_deltas:
            if delete_unused_morphs:
                removed_aliases.append(t_info["alias_name"])
                continue

        kept_targets.append({
            "alias_name": t_info["alias_name"],
            "weight": t_info["weight"],
            "deltas": remapped_deltas,
        })

    if not kept_targets:
        return None, removed_aliases, {}

    new_bs = mc.blendShape(mesh_transform, name=short_bs_name, frontOfChain=True)[0]
    sel = om.MSelectionList()
    sel.add(new_bs)
    bs_mobj = sel.getDependNode(0)
    fn_bs = om.MFnDependencyNode(bs_mobj)

    plug_it_0 = fn_bs.findPlug("inputTarget", False).elementByLogicalIndex(0)
    plug_target_group = plug_it_0.child(0)

    written_counts = {}
    for new_idx, t_entry in enumerate(kept_targets):
        alias_name = t_entry["alias_name"]
        remapped_deltas = t_entry["deltas"]

        plug_grp = plug_target_group.elementByLogicalIndex(new_idx)
        plug_item = plug_grp.child(0).elementByLogicalIndex(6000)

        plug_pts = None
        plug_comps = None
        for c_i in range(plug_item.numChildren()):
            ch = plug_item.child(c_i)
            ch_long = ch.partialName(useLongNames=True)
            if "inputPointsTarget" in ch_long or ch_long == "ipt":
                plug_pts = ch
            elif "inputComponentsTarget" in ch_long or ch_long == "ict":
                plug_comps = ch

        if not plug_pts or not plug_comps:
            continue

        pts_array = om.MPointArray()
        fn_comp = om.MFnSingleIndexedComponent()
        comp_obj = fn_comp.create(om.MFn.kMeshVertComponent)

        if remapped_deltas:
            for v_i in sorted(remapped_deltas.keys()):
                dx, dy, dz = remapped_deltas[v_i]
                pts_array.append(om.MPoint(dx, dy, dz, 1.0))
                fn_comp.addElement(int(v_i))
        else:
            pts_array.append(om.MPoint(0.0, 0.0, 0.0, 1.0))
            fn_comp.addElement(0)

        fn_pts = om.MFnPointArrayData()
        plug_pts.setMObject(fn_pts.create(pts_array))

        fn_comp_data = om.MFnComponentListData()
        data_comp = fn_comp_data.create()
        fn_comp_data.add(comp_obj)
        plug_comps.setMObject(data_comp)

        mc.setAttr(f"{new_bs}.weight[{new_idx}]", float(t_entry["weight"]))
        try:
            mc.aliasAttr(alias_name, f"{new_bs}.w[{new_idx}]")
        except Exception:
            pass

        written_counts[alias_name] = len(remapped_deltas)

    return new_bs, removed_aliases, written_counts


def _update_model_structure_morphs(model_root, removed_targets, removed_group_names=None, new_bs_node=None):
    """
    mmdModelStructure および mmdMorphStructure から削除されたモーフを除外し、
    モーフ一覧の index と name_lookup を振り直し
    """
    long_root = _to_long_name(model_root)
    if not long_root:
        return

    removed_set = set(str(x) for x in (removed_targets or []) if x)
    removed_group_set = set(str(x) for x in (removed_group_names or []) if x)
    if not removed_set and not removed_group_set and not new_bs_node:
        return

    if mc.attributeQuery("mmdMorphStructure", node=long_root, exists=True):
        try:
            raw_map = mc.getAttr(f"{long_root}.mmdMorphStructure")
            if raw_map:
                m_map = json.loads(raw_map)
                if isinstance(m_map, dict):
                    new_map = {
                        k: v for k, v in m_map.items()
                        if v not in removed_set and k not in removed_set and k not in removed_group_set
                    }
                    mc.setAttr(f"{long_root}.mmdMorphStructure", json.dumps(new_map, ensure_ascii=False), type="string")
        except Exception:
            pass

    if mc.attributeQuery("mmdModelStructure", node=long_root, exists=True):
        try:
            raw_struct = mc.getAttr(f"{long_root}.mmdModelStructure")
            if raw_struct:
                struct = json.loads(raw_struct)
                old_morphs = struct.get("morphs", []) or []
                new_morphs = []
                new_lookup = {}

                for entry in old_morphs:
                    m_target = entry.get("maya_target") or ""
                    m_jp = entry.get("name_jp") or ""
                    m_en = entry.get("name_en") or ""
                    if m_target in removed_set or m_jp in removed_set or m_jp in removed_group_set:
                        continue

                    new_idx = len(new_morphs)
                    updated_entry = dict(entry)
                    updated_entry["index"] = new_idx
                    if new_bs_node and updated_entry.get("morph_type") == 1:
                        updated_entry["maya_node"] = new_bs_node
                    new_morphs.append(updated_entry)

                    if m_jp:
                        new_lookup[m_jp] = new_idx
                    if m_en:
                        new_lookup[m_en] = new_idx

                struct["morphs"] = new_morphs
                if "name_lookup" not in struct or not isinstance(struct["name_lookup"], dict):
                    struct["name_lookup"] = {}
                struct["name_lookup"]["morphs"] = new_lookup

                if new_bs_node and "maya" in struct and isinstance(struct["maya"], dict):
                    struct["maya"]["blendshape_node"] = new_bs_node

                legacy = struct.get("legacy_compatibility", {})
                if isinstance(legacy, dict) and isinstance(legacy.get("morphs"), dict):
                    legacy["morphs"] = {
                        k: v for k, v in legacy["morphs"].items()
                        if v not in removed_set and k not in removed_set and k not in removed_group_set
                    }

                mc.setAttr(f"{long_root}.mmdModelStructure", json.dumps(struct, ensure_ascii=False), type="string")
        except Exception:
            pass


@skin_utils.undo_chunk("MMD_DeleteMaterialsWithRemap")
def delete_materials_and_remap(
    model_root,
    target_material_datas,
    delete_unused_morphs=True,
    remove_group_morph_names=None,
    cleanup_unused_shaders=False,
):
    """
    指定された材質のパーツ（ポリゴン面および孤立頂点）を削除し、
    残った頂点の「旧番号 → 新番号」対応表を作成してスキンウェイトとモーフ差分を書き戻し。
    削除前後の照合チェック（頂点位置・ウェイト合計・モーフ差分件数）を実行し、
    不整合が検出された場合は例外を送出して安全に中断します。
    """
    long_root = _to_long_name(model_root)
    if not long_root or not target_material_datas:
        return {"success": False, "message": "削除対象のモデルまたは材質が指定されていません。"}

    # マスキング表示中であれば一旦マスクを解除してから削除を実行
    was_masked = is_mask_active(long_root)
    if was_masked:
        restore_material_mask(long_root)

    all_materials = get_model_materials_data(long_root)
    target_sgs = set(d["sg"] for d in target_material_datas if d.get("sg"))
    all_shaders = [d["shader"] for d in all_materials if d.get("shader")]
    deleted_shaders = [d["shader"] for d in all_materials if d.get("sg") in target_sgs and d.get("shader")]

    valid_meshes = skin_utils.get_model_meshes(long_root, include_edge=False)
    if not valid_meshes:
        return {"success": False, "message": "対象メッシュが見つかりませんでした。"}

    # 全ポリゴン削除の防止チェック
    impact = analyze_deletion_impact(long_root, target_material_datas)
    if not impact or impact["deleted_faces_count"] <= 0:
        return {"success": False, "message": "削除対象のポリゴン面が見つかりませんでした。"}
    if impact["remaining_faces_count"] <= 0:
        return {"success": False, "message": "すべてのポリゴン面を削除することはできません。少なくとも1つの材質を残してください。"}

    total_deleted_faces = 0
    total_deleted_verts = 0
    removed_morph_targets = []
    removed_morph_labels = []
    latest_bs_node = None

    for shp in valid_meshes:
        del_f_list = []
        for d in target_material_datas:
            del_f_list.extend(d.get("mesh_face_indices", {}).get(shp, []))
        del_f_set = set(int(x) for x in del_f_list)
        if not del_f_set:
            continue

        parents = mc.listRelatives(shp, parent=True, fullPath=True) or [shp]
        mesh_tr = parents[0]

        sel = om.MSelectionList()
        sel.add(shp)
        dag = sel.getDagPath(0)
        mfn_mesh = om.MFnMesh(dag)
        old_num_faces = mfn_mesh.numPolygons
        old_num_verts = mfn_mesh.numVertices

        # サブメッシュ全体の面がすべて削除対象の場合（材質分割インポートモデル）
        if len(del_f_set) >= old_num_faces and len(valid_meshes) > 1:
            mc.delete(mesh_tr)
            total_deleted_faces += old_num_faces
            total_deleted_verts += old_num_verts
            continue

        # 削除前: モーフとスキンのエンベロープを一時的に0にして基準形状（バインドポーズ）でデータを抽出
        bs_node = _find_model_blendshape(shp, model_root=long_root)
        skin_node = skin_utils.get_skin_cluster(shp)

        bs_data = extract_blendshape_targets(shp, model_root=long_root) if bs_node else None
        if bs_node and mc.objExists(bs_node):
            try:
                mc.setAttr(f"{bs_node}.envelope", 0.0)
            except Exception:
                pass

        weight_data = skin_utils.extract_mesh_skin_weights(shp, model_root=long_root) if skin_node else None
        if skin_node and mc.objExists(skin_node):
            try:
                mc.setAttr(f"{skin_node}.envelope", 0.0)
            except Exception:
                pass

        # 基準形状での頂点座標および各ポリゴンの構成頂点番号を記録
        sel_base = om.MSelectionList()
        sel_base.add(shp)
        dag_base = sel_base.getDagPath(0)
        mfn_base = om.MFnMesh(dag_base)

        old_obj_points = mfn_base.getPoints(om.MSpace.kObject)
        old_coords = [
            (float(old_obj_points[i].x), float(old_obj_points[i].y), float(old_obj_points[i].z))
            for i in range(old_num_verts)
        ]
        old_face_verts = [
            [int(v) for v in mfn_base.getPolygonVertices(f_i)]
            for f_i in range(old_num_faces)
        ]

        kept_face_indices = [f_i for f_i in range(old_num_faces) if f_i not in del_f_set]
        kept_vert_set = set()
        for f_i in kept_face_indices:
            kept_vert_set.update(old_face_verts[f_i])

        # デフォーマヒストリを一旦整理してクリーンなベースメッシュにする
        if skin_node and mc.objExists(skin_node):
            try:
                mc.skinCluster(shp, edit=True, unbind=True)
            except Exception:
                pass
        if bs_node and mc.objExists(bs_node):
            try:
                mc.delete(bs_node)
            except Exception:
                pass
        mc.delete(mesh_tr, constructionHistory=True)

        # 対象ポリゴン面を削除
        face_ranges = _format_component_ranges(mesh_tr, "f", del_f_set)
        if face_ranges:
            mc.delete(face_ranges)

        # 面削除によって接続面が0になった孤立頂点を検出して削除
        shp_after_face = skin_utils._get_mesh_shape(mesh_tr)
        sel_af = om.MSelectionList()
        sel_af.add(shp_after_face)
        dag_af = sel_af.getDagPath(0)
        it_vtx = om.MItMeshVertex(dag_af)
        isolated_vtx_indices = []
        while not it_vtx.isDone():
            if it_vtx.numConnectedFaces() == 0:
                isolated_vtx_indices.append(int(it_vtx.index()))
            it_vtx.next()

        if isolated_vtx_indices:
            vtx_ranges = _format_component_ranges(mesh_tr, "vtx", isolated_vtx_indices)
            if vtx_ranges:
                mc.delete(vtx_ranges)

        mc.delete(mesh_tr, constructionHistory=True)

        # エッジメッシュが同数フェースで存在する場合は対応する面と孤立頂点も同期削除
        for e_node in _find_edge_meshes(long_root):
            try:
                e_shp = skin_utils._get_mesh_shape(e_node)
                if e_shp and mc.polyEvaluate(e_shp, face=True) == old_num_faces:
                    e_f_ranges = _format_component_ranges(e_node, "f", del_f_set)
                    if e_f_ranges:
                        mc.delete(e_f_ranges)
            except Exception:
                pass

        # 削除後メッシュから「旧頂点番号 <-> 新頂点番号」対応表を構築
        new_shp = skin_utils._get_mesh_shape(mesh_tr)
        sel_new = om.MSelectionList()
        sel_new.add(new_shp)
        dag_new = sel_new.getDagPath(0)
        mfn_new = om.MFnMesh(dag_new)
        new_num_faces = mfn_new.numPolygons
        new_num_verts = mfn_new.numVertices

        old_to_new = {}
        new_to_old = [-1] * new_num_verts

        if new_num_faces == len(kept_face_indices):
            for new_f_i, old_f_i in enumerate(kept_face_indices):
                old_corners = old_face_verts[old_f_i]
                new_corners = [int(v) for v in mfn_new.getPolygonVertices(new_f_i)]
                if len(old_corners) == len(new_corners):
                    for old_v, new_v in zip(old_corners, new_corners):
                        old_to_new[old_v] = new_v
                        if 0 <= new_v < new_num_verts:
                            new_to_old[new_v] = old_v

        # 未対応頂点が残っている場合は昇順保持リストで補完
        sorted_kept_old = sorted(list(kept_vert_set))
        if len(sorted_kept_old) == new_num_verts:
            for new_v in range(new_num_verts):
                if new_to_old[new_v] < 0:
                    old_v = sorted_kept_old[new_v]
                    new_to_old[new_v] = old_v
                    old_to_new[old_v] = new_v

        # 照合チェック: 削除前後の頂点座標の一致を確認
        new_obj_points = mfn_new.getPoints(om.MSpace.kObject)
        max_pos_diff = 0.0
        for new_v in range(new_num_verts):
            old_v = new_to_old[new_v]
            if old_v < 0 or old_v >= old_num_verts:
                raise RuntimeError(f"頂点番号の対応表に未解決の頂点が含まれています (new_v={new_v})。")
            ox, oy, oz = old_coords[old_v]
            np = new_obj_points[new_v]
            diff = max(abs(float(np.x) - ox), abs(float(np.y) - oy), abs(float(np.z) - oz))
            if diff > max_pos_diff:
                max_pos_diff = diff

        if max_pos_diff > 1e-2:
            raise RuntimeError(f"削除前後の頂点座標照合で許容値を超えるズレを検出しました (最大誤差={max_pos_diff:.5f})。")

        # 新しい番号でモーフ差分を書き戻し（スキンクラスタより前段に配置）
        if bs_data:
            new_bs, removed_aliases, written_counts = _rebuild_blendshape_with_remap(
                mesh_transform=mesh_tr,
                bs_data=bs_data,
                old_to_new_map=old_to_new,
                new_num_verts=new_num_verts,
                delete_unused_morphs=delete_unused_morphs,
            )
            latest_bs_node = new_bs
            removed_morph_targets.extend(removed_aliases)

            # モーフ差分件数の照合チェック
            for t_info in bs_data["targets"]:
                alias_n = t_info["alias_name"]
                if alias_n in removed_aliases:
                    continue
                expected_cnt = sum(1 for ov in t_info["deltas"].keys() if ov in old_to_new)
                actual_cnt = written_counts.get(alias_n, 0)
                if expected_cnt != actual_cnt:
                    raise RuntimeError(
                        f"モーフ『{alias_n}』の差分件数照合が一致しません (期待値={expected_cnt}, 実際={actual_cnt})。"
                    )

        # 新しい番号でスキンウェイトを書き戻し
        if weight_data:
            ok_skin = skin_utils.apply_mesh_skin_weights(
                mesh_node=new_shp,
                weight_data=weight_data,
                model_root=long_root,
                vertex_map=new_to_old,
                rebind=True,
            )
            if not ok_skin:
                raise RuntimeError("削除後メッシュへのスキンウェイト書き戻しに失敗しました。")

            # ウェイト合計の照合チェック
            verify_w = skin_utils.extract_mesh_skin_weights(new_shp, model_root=long_root)
            if not verify_w or verify_w["vertex_count"] != new_num_verts:
                raise RuntimeError("書き戻し後のスキンクラスタ頂点数照合に失敗しました。")
            for v_idx, v_pairs in enumerate(verify_w["sparse_weights"]):
                w_sum = sum(float(p[1]) for p in v_pairs)
                if abs(w_sum - 1.0) > 1e-2:
                    raise RuntimeError(f"頂点[{v_idx}]のウェイト合計が不整合です (合計={w_sum:.4f})。")

        total_deleted_faces += (old_num_faces - new_num_faces)
        total_deleted_verts += (old_num_verts - new_num_verts)

    # 不要になった材質モーフ属性の削除
    unused_mat_morphs, _ = _analyze_material_morphs_usage(long_root, all_shaders, deleted_shaders)
    if delete_unused_morphs and unused_mat_morphs:
        for mm in unused_mat_morphs:
            attr_n = mm["attr_name"]
            plug = f"{long_root}.{attr_n}"
            if mc.attributeQuery(attr_n, node=long_root, exists=True):
                try:
                    mc.deleteAttr(plug)
                    removed_morph_targets.append(attr_n)
                    removed_morph_labels.append(mm["name_jp"])
                except Exception:
                    pass

    # 構造JSON（mmdModelStructure / mmdMorphStructure）の更新
    _update_model_structure_morphs(
        model_root=long_root,
        removed_targets=removed_morph_targets,
        removed_group_names=remove_group_morph_names,
        new_bs_node=latest_bs_node,
    )

    # 割り当て面が0になったシェーディングエンジンおよび未使用シェーダーの任意掃除
    if cleanup_unused_shaders:
        for sg in target_sgs:
            if not sg or not mc.objExists(sg) or sg == "initialShadingGroup":
                continue
            rem_members = mc.sets(sg, query=True) or []
            if not rem_members:
                shaders = mc.listConnections(f"{sg}.surfaceShader") or []
                try:
                    mc.delete(sg)
                except Exception:
                    pass
                for shd in shaders:
                    if shd and mc.objExists(shd):
                        sgs_conn = mc.listConnections(shd, type="shadingEngine") or []
                        if not sgs_conn:
                            try:
                                mc.delete(shd)
                            except Exception:
                                pass

    return {
        "success": True,
        "deleted_faces": total_deleted_faces,
        "deleted_vertices": total_deleted_verts,
        "removed_morph_count": len(removed_morph_targets) + len(remove_group_morph_names or []),
        "removed_morph_targets": removed_morph_targets,
        "removed_morph_labels": removed_morph_labels,
    }
