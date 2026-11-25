# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - スキンウェイト保存・復元・頂点番号付け替えユーティリティ
OpenMayaAnim (MFnSkinCluster) を用いた高速なウェイト一括取得・設定、
シーン内非表示ノードへのJSON永続化、頂点削除時の番号付け替え（リマップ）、
Undoチャンク制御およびシーン自動バックアップを提供します。
"""

import os
import json
import math
import tempfile
import functools
from datetime import datetime

import maya.cmds as mc
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma


CACHE_HOLDER_NODE = "MMD_WeightCache_Holder"
CACHE_ATTR_NAME = "mmdWeightCacheStore"


class _UndoChunkContext(object):
    """
    Undoチャンクをコンテキストマネージャおよびデコレータの両方で扱うクラス
    """

    def __init__(self, chunk_name="MMD_DressUp"):
        self.chunk_name = chunk_name

    def __enter__(self):
        mc.undoInfo(openChunk=True, chunkName=self.chunk_name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        mc.undoInfo(closeChunk=True)
        return False

    def __call__(self, func):
        @functools.wraps(func)
        def _wrapper(*args, **kwargs):
            mc.undoInfo(openChunk=True, chunkName=self.chunk_name)
            try:
                return func(*args, **kwargs)
            finally:
                mc.undoInfo(closeChunk=True)
        return _wrapper


def undo_chunk(arg="MMD_DressUp"):
    """
    処理を1回のUndoで戻せるようにまとめるデコレータ兼コンテキストマネージャ
    引数なしの @undo_chunk、名前指定の @undo_chunk("Name")、with undo_chunk("Name"): に対応します。
    """
    if callable(arg):
        ctx = _UndoChunkContext(chunk_name=arg.__name__)
        return ctx(arg)
    return _UndoChunkContext(chunk_name=str(arg))


def create_scene_backup(enabled=True, backup_dir=None, prefix_override=None):
    """
    一括処理や破壊的編集の前に現在のシーンを別名で自動バックアップ保存
    ファイル名は「シーン名_dressup_backup_YYYYMMDD_HHMM.mb」形式とし、
    保存後は元のシーンファイルパス設定を維持します。
    """
    if not enabled:
        return None

    orig_scene = mc.file(query=True, sceneName=True) or ""
    if orig_scene:
        orig_dir = os.path.dirname(orig_scene)
        orig_base = os.path.splitext(os.path.basename(orig_scene))[0]
    else:
        ws_root = mc.workspace(query=True, rootDirectory=True) or ""
        scenes_dir = os.path.join(ws_root, "scenes") if ws_root else ""
        if scenes_dir and os.path.isdir(scenes_dir):
            orig_dir = scenes_dir
        elif ws_root and os.path.isdir(ws_root):
            orig_dir = ws_root
        else:
            orig_dir = tempfile.gettempdir()
        orig_base = "untitled"

    target_dir = backup_dir if (backup_dir and os.path.isdir(backup_dir)) else orig_dir
    if not target_dir:
        target_dir = tempfile.gettempdir()

    base_label = prefix_override if prefix_override else orig_base
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    backup_mb = os.path.join(target_dir, f"{base_label}_dressup_backup_{timestamp}.mb").replace("\\", "/")

    saved_path = None
    try:
        mc.file(rename=backup_mb)
        try:
            mc.file(save=True, type="mayaBinary", force=True)
            saved_path = backup_mb
        except Exception:
            backup_ma = os.path.join(target_dir, f"{base_label}_dressup_backup_{timestamp}.ma").replace("\\", "/")
            mc.file(rename=backup_ma)
            mc.file(save=True, type="mayaAscii", force=True)
            saved_path = backup_ma
    except Exception as e:
        mc.warning(f"シーンの自動バックアップ保存をスキップしました: {e}")
        saved_path = None
    finally:
        if orig_scene:
            try:
                mc.file(rename=orig_scene)
            except Exception:
                pass

    return saved_path


def _to_long_name(node_name):
    """ノード名をフルDAGパスに変換"""
    if not node_name or not mc.objExists(node_name):
        return None
    res = mc.ls(node_name, long=True)
    return res[0] if res else node_name


def _get_mesh_shape(node_name):
    """トランスフォームまたはメッシュ名から非中間メッシュシェイプのフルパスを取得"""
    long_n = _to_long_name(node_name)
    if not long_n:
        return None
    if mc.nodeType(long_n) == "mesh":
        if not mc.getAttr(f"{long_n}.intermediateObject"):
            return long_n
        return None
    shapes = mc.listRelatives(long_n, shapes=True, type="mesh", fullPath=True) or []
    for shp in shapes:
        if not mc.getAttr(f"{shp}.intermediateObject"):
            return shp
    return None


def get_skin_cluster(mesh_node):
    """
    指定メッシュ（シェイプまたはトランスフォーム）に接続されているスキンクラスタを取得
    """
    if not mesh_node or not mc.objExists(mesh_node):
        return None

    history = mc.listHistory(mesh_node, pruneDagObjects=True) or []
    skins = mc.ls(history, type="skinCluster")
    if skins:
        return skins[0]

    shp = _get_mesh_shape(mesh_node)
    if shp and shp != mesh_node:
        history = mc.listHistory(shp, pruneDagObjects=True) or []
        skins = mc.ls(history, type="skinCluster")
        if skins:
            return skins[0]

    return None


def get_model_meshes(model_root, include_edge=False):
    """
    指定モデル階層下の有効なポリゴンメッシュシェイプ一覧をフルパスで取得
    中間オブジェクト、剛体・Jointビジュアライザ、および輪郭線用エッジメッシュを除外します。
    """
    long_root = _to_long_name(model_root)
    if not long_root:
        return []

    candidates = []
    if mc.nodeType(long_root) == "mesh":
        candidates.append(long_root)
    else:
        direct_shapes = mc.listRelatives(long_root, shapes=True, type="mesh", fullPath=True) or []
        desc_shapes = mc.listRelatives(long_root, allDescendents=True, type="mesh", fullPath=True) or []
        candidates.extend(direct_shapes)
        for s in desc_shapes:
            if s not in candidates:
                candidates.append(s)

    valid_meshes = []
    seen = set()
    for m in candidates:
        if m in seen or not mc.objExists(m):
            continue
        seen.add(m)

        try:
            if mc.getAttr(f"{m}.intermediateObject"):
                continue
        except Exception:
            continue

        parents = mc.listRelatives(m, parent=True, fullPath=True) or []
        parent_tr = parents[0] if parents else m
        parent_short = parent_tr.split("|")[-1]

        # 物理ビジュアライザのメッシュを除外
        if mc.attributeQuery("rbIndex", node=parent_tr, exists=True) or mc.attributeQuery("jointIndex", node=parent_tr, exists=True):
            continue
        if "_RigidBody_" in parent_tr or "_Joint_Visualizers" in parent_tr:
            continue

        # エッジメッシュを除外（明示指定時を除く）
        if not include_edge and (parent_short.endswith("_Edge") or m.split("|")[-1].endswith("_EdgeShape")):
            continue

        valid_meshes.append(m)

    return valid_meshes


def get_bone_canonical_name(joint_node, model_root=None):
    """
    ジョイントノードからMMD標準のボーン名称（日本語オリジナル名優先）を取得
    """
    if not joint_node or not mc.objExists(joint_node):
        return ""

    if mc.attributeQuery("originalName", node=joint_node, exists=True):
        try:
            orig = mc.getAttr(f"{joint_node}.originalName")
            if orig:
                return str(orig).strip()
        except Exception:
            pass

    short_n = joint_node.split("|")[-1]
    if model_root:
        root_short = model_root.split("|")[-1]
        prefix = f"{root_short}_"
        if short_n.startswith(prefix):
            return short_n[len(prefix):]

    return short_n


def get_model_joints(model_root):
    """
    指定モデルに属する全ジョイントノードをフルパスで取得
    モデル階層下、mmdModelStructure / mmdBoneStructure 属性、スキンクラスタのインフルエンス、
    およびモデル名プレフィックス付きルートジョイントから網羅的に収集します。
    """
    long_root = _to_long_name(model_root)
    if not long_root:
        return []

    root_short = long_root.split("|")[-1]
    collected = []
    seen = set()

    def _add_joint(j_node):
        j_long = _to_long_name(j_node)
        if j_long and j_long not in seen and mc.nodeType(j_long) == "joint":
            seen.add(j_long)
            collected.append(j_long)

    def _add_joint_tree(j_root):
        j_long = _to_long_name(j_root)
        if not j_long or mc.nodeType(j_long) != "joint":
            return
        _add_joint(j_long)
        desc = mc.listRelatives(j_long, allDescendents=True, type="joint", fullPath=True) or []
        for d in reversed(desc):
            _add_joint(d)

    # モデル階層下のジョイントを探索
    if mc.nodeType(long_root) == "joint":
        _add_joint_tree(long_root)
    else:
        desc_joints = mc.listRelatives(long_root, allDescendents=True, type="joint", fullPath=True) or []
        for dj in desc_joints:
            _add_joint(dj)

    # mmdModelStructure JSON からルートジョイントおよびボーンリストを取得
    if mc.attributeQuery("mmdModelStructure", node=long_root, exists=True):
        try:
            raw_json = mc.getAttr(f"{long_root}.mmdModelStructure")
            if raw_json:
                struct = json.loads(raw_json)
                root_joints = struct.get("maya", {}).get("root_joints", []) or []
                for rj in root_joints:
                    if mc.objExists(rj):
                        _add_joint_tree(rj)
                for b_info in struct.get("bones", []) or []:
                    m_uuid = b_info.get("maya_uuid")
                    m_node = b_info.get("maya_node")
                    if m_uuid:
                        by_uuid = mc.ls(m_uuid, long=True) or []
                        if by_uuid:
                            _add_joint(by_uuid[0])
                            continue
                    if m_node and mc.objExists(m_node):
                        _add_joint(m_node)
        except Exception:
            pass

    # mmdBoneStructure JSON からジョイントを取得
    if mc.attributeQuery("mmdBoneStructure", node=long_root, exists=True):
        try:
            raw_bones = mc.getAttr(f"{long_root}.mmdBoneStructure")
            if raw_bones:
                b_map = json.loads(raw_bones)
                if isinstance(b_map, dict):
                    for j_path in b_map.values():
                        if j_path and mc.objExists(j_path):
                            _add_joint(j_path)
        except Exception:
            pass

    # メッシュに接続されたスキンクラスタのインフルエンスから収集
    meshes = get_model_meshes(long_root)
    for m in meshes:
        skin = get_skin_cluster(m)
        if skin:
            try:
                infs = mc.skinCluster(skin, query=True, influence=True) or []
                for inf in infs:
                    _add_joint(inf)
            except Exception:
                pass

    # まだ見つからない場合はモデル名プレフィックスを持つジョイントをシーンから探索
    if not collected:
        prefix = f"{root_short}_"
        for j in mc.ls(type="joint", long=True) or []:
            j_short = j.split("|")[-1]
            if j_short.startswith(prefix):
                _add_joint_tree(j)

    return collected


def extract_mesh_skin_weights(mesh_node, model_root=None):
    """
    MFnSkinCluster.getWeights を用いて指定メッシュの全頂点ウェイトとインフルエンス情報を一括取得
    """
    mesh_shape = _get_mesh_shape(mesh_node)
    if not mesh_shape:
        return None

    skin_cluster = get_skin_cluster(mesh_shape)
    if not skin_cluster:
        return None

    parents = mc.listRelatives(mesh_shape, parent=True, fullPath=True) or []
    parent_tr = parents[0] if parents else mesh_shape
    parent_short = parent_tr.split("|")[-1]

    sel = om.MSelectionList()
    sel.add(mesh_shape)
    sel.add(skin_cluster)
    dag_path = sel.getDagPath(0)
    skin_mobj = sel.getDependNode(1)

    mfn_mesh = om.MFnMesh(dag_path)
    num_verts = mfn_mesh.numVertices
    if num_verts <= 0:
        return None

    fn_skin = oma.MFnSkinCluster(skin_mobj)
    inf_dags = fn_skin.influenceObjects()
    num_infs = len(inf_dags)
    if num_infs <= 0:
        return None

    influences_info = []
    for idx in range(num_infs):
        inf_dag = inf_dags[idx]
        inf_long = inf_dag.fullPathName()
        inf_short = inf_dag.partialPathName().split("|")[-1]
        canon_name = get_bone_canonical_name(inf_long, model_root=model_root)
        eng_name = ""
        if mc.attributeQuery("englishName", node=inf_long, exists=True):
            try:
                eng_name = mc.getAttr(f"{inf_long}.englishName") or ""
            except Exception:
                eng_name = ""
        parent_j = mc.listRelatives(inf_long, parent=True, type="joint", fullPath=True) or []
        parent_canon = get_bone_canonical_name(parent_j[0], model_root=model_root) if parent_j else ""

        influences_info.append({
            "index": idx,
            "long_name": inf_long,
            "short_name": inf_short,
            "canonical_name": canon_name,
            "english_name": str(eng_name),
            "parent_canonical": parent_canon,
        })

    # 全頂点コンポーネントを作成してウェイトを一括取得
    fn_comp = om.MFnSingleIndexedComponent()
    comp_obj = fn_comp.create(om.MFn.kMeshVertComponent)
    fn_comp.setCompleteData(num_verts)

    weights_flat, _ = fn_skin.getWeights(dag_path, comp_obj)

    # 頂点ワールド座標を一括取得（トポロジ変更時の空間近接フォールバックおよび検証用）
    points = mfn_mesh.getPoints(om.MSpace.kWorld)
    positions_list = [
        [round(float(points[v].x), 5), round(float(points[v].y), 5), round(float(points[v].z), 5)]
        for v in range(num_verts)
    ]

    # ゼロ以外のウェイトのみを疎配列として格納
    sparse_weights = []
    for v_idx in range(num_verts):
        base_offset = v_idx * num_infs
        v_Pairs = []
        for inf_idx in range(num_infs):
            w_val = float(weights_flat[base_offset + inf_idx])
            if w_val > 1e-6:
                v_Pairs.append([inf_idx, round(w_val, 6)])
        sparse_weights.append(v_Pairs)

    return {
        "mesh_shape": mesh_shape,
        "mesh_transform": parent_tr,
        "mesh_short_name": parent_short,
        "skin_cluster": skin_cluster,
        "vertex_count": num_verts,
        "influences": influences_info,
        "sparse_weights": sparse_weights,
        "positions": positions_list,
    }


def remap_skin_weights(weight_data, vertex_map):
    """
    頂点番号の対応表を受け取ってウェイトデータと頂点座標を新しい頂点番号順に並べ替え
    vertex_map は以下のいずれかの形式を受け付けます:
    - dict: {旧頂点番号: 新頂点番号} （削除された頂点は含まれないか負数/None）
    - list/tuple: 新頂点番号をインデックスとし、対応する旧頂点番号を格納したリスト (new_to_old)
    """
    if not weight_data or vertex_map is None:
        return weight_data

    old_sparse = weight_data.get("sparse_weights", [])
    old_positions = weight_data.get("positions", [])
    old_count = len(old_sparse)

    new_to_old = []
    if isinstance(vertex_map, dict):
        valid_pairs = []
        for k, v in vertex_map.items():
            if v is None:
                continue
            old_i = int(k)
            new_i = int(v)
            if new_i >= 0 and 0 <= old_i < old_count:
                valid_pairs.append((new_i, old_i))
        if not valid_pairs:
            new_to_old = []
        else:
            max_new = max(p[0] for p in valid_pairs)
            temp_map = [-1] * (max_new + 1)
            for new_i, old_i in valid_pairs:
                temp_map[new_i] = old_i
            new_to_old = temp_map
    elif isinstance(vertex_map, (list, tuple)):
        new_to_old = [int(x) for x in vertex_map]
    else:
        return weight_data

    new_sparse = []
    new_positions = []
    for old_idx in new_to_old:
        if 0 <= old_idx < old_count:
            new_sparse.append([list(pair) for pair in old_sparse[old_idx]])
            if old_idx < len(old_positions):
                new_positions.append(list(old_positions[old_idx]))
            else:
                new_positions.append([0.0, 0.0, 0.0])
        else:
            new_sparse.append([])
            new_positions.append([0.0, 0.0, 0.0])

    remapped = dict(weight_data)
    remapped["vertex_count"] = len(new_sparse)
    remapped["sparse_weights"] = new_sparse
    remapped["positions"] = new_positions
    return remapped


def _build_joint_lookup(target_joints, model_root=None):
    """ターゲット側のジョイント群から名前引き辞書を構築"""
    by_long = {}
    by_short = {}
    by_canonical = {}
    by_english = {}

    for j in target_joints:
        j_long = _to_long_name(j)
        if not j_long:
            continue
        j_short = j_long.split("|")[-1]
        canon = get_bone_canonical_name(j_long, model_root=model_root)
        by_long[j_long] = j_long
        by_short.setdefault(j_short, j_long)
        if canon:
            by_canonical.setdefault(canon, j_long)
        if mc.attributeQuery("englishName", node=j_long, exists=True):
            try:
                eng = mc.getAttr(f"{j_long}.englishName")
                if eng:
                    by_english.setdefault(str(eng).strip().lower(), j_long)
            except Exception:
                pass

    return {
        "by_long": by_long,
        "by_short": by_short,
        "by_canonical": by_canonical,
        "by_english": by_english,
        "all": list(by_long.keys()),
    }


def _match_cached_influences_to_joints(cached_influences, joint_lookup):
    """
    保存されたインフルエンス一覧をターゲット側のジョイントへ対応付け
    ボーン名（日本語オリジナル名・英語名・短縮名）で一致を探し、
    見つからない場合は親ボーン名や既存ジョイントへのフォールバックを行います。
    """
    by_long = joint_lookup["by_long"]
    by_short = joint_lookup["by_short"]
    by_canonical = joint_lookup["by_canonical"]
    by_english = joint_lookup["by_english"]
    all_targets = joint_lookup["all"]

    fallback_joint = (
        by_canonical.get("センター")
        or by_canonical.get("下半身")
        or by_canonical.get("上半身")
        or by_canonical.get("全ての親")
        or (all_targets[0] if all_targets else None)
    )

    mapped_joints = {}
    for inf in cached_influences:
        idx = int(inf.get("index", len(mapped_joints)))
        canon = inf.get("canonical_name", "")
        eng = (inf.get("english_name", "") or "").strip().lower()
        short_n = inf.get("short_name", "")
        long_n = inf.get("long_name", "")
        parent_canon = inf.get("parent_canonical", "")

        matched = None
        if canon and canon in by_canonical:
            matched = by_canonical[canon]
        elif eng and eng in by_english:
            matched = by_english[eng]
        elif short_n and short_n in by_short:
            matched = by_short[short_n]
        elif short_n and short_n in by_canonical:
            matched = by_canonical[short_n]
        elif long_n and long_n in by_long:
            matched = by_long[long_n]
        elif parent_canon and parent_canon in by_canonical:
            matched = by_canonical[parent_canon]
        elif long_n and mc.objExists(long_n) and mc.nodeType(long_n) == "joint":
            matched = _to_long_name(long_n)
        elif short_n and mc.objExists(short_n) and mc.nodeType(short_n) == "joint":
            matched = _to_long_name(short_n)
        else:
            matched = fallback_joint

        if matched:
            mapped_joints[idx] = matched

    return mapped_joints


def _match_vertices_by_spatial_proximity(current_points, cached_positions):
    """
    頂点数が変化したメッシュ向けに、空間ボクセルグリッドを用いて最近傍の旧頂点インデックスを高速特定
    """
    num_cur = len(current_points)
    num_cached = len(cached_positions)
    if num_cached == 0:
        return [0] * num_cur

    cell_size = 0.5
    inv_cell = 1.0 / cell_size
    grid = {}

    for c_idx, pos in enumerate(cached_positions):
        gx = int(math.floor(pos[0] * inv_cell))
        gy = int(math.floor(pos[1] * inv_cell))
        gz = int(math.floor(pos[2] * inv_cell))
        key = (gx, gy, gz)
        if key not in grid:
            grid[key] = []
        grid[key].append(c_idx)

    new_to_old = [0] * num_cur
    for v_idx in range(num_cur):
        pt = current_points[v_idx]
        px, py, pz = float(pt.x), float(pt.y), float(pt.z)
        gx = int(math.floor(px * inv_cell))
        gy = int(math.floor(py * inv_cell))
        gz = int(math.floor(pz * inv_cell))

        candidates = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    bucket = grid.get((gx + dx, gy + dy, gz + dz))
                    if bucket:
                        candidates.extend(bucket)

        if not candidates:
            # 近傍セルが空の場合は範囲を広げて探索
            for radius in (2, 4):
                for dx in range(-radius, radius + 1):
                    for dy in range(-radius, radius + 1):
                        for dz in range(-radius, radius + 1):
                            bucket = grid.get((gx + dx, gy + dy, gz + dz))
                            if bucket:
                                candidates.extend(bucket)
                if candidates:
                    break

        search_indices = candidates if candidates else range(num_cached)
        best_idx = 0
        best_dist_sq = float("inf")
        for c_idx in search_indices:
            c_pos = cached_positions[c_idx]
            dx = px - c_pos[0]
            dy = py - c_pos[1]
            dz = pz - c_pos[2]
            d_sq = dx * dx + dy * dy + dz * dz
            if d_sq < best_dist_sq:
                best_dist_sq = d_sq
                best_idx = c_idx
                if d_sq <= 1e-10:
                    break

        new_to_old[v_idx] = best_idx

    return new_to_old


def apply_mesh_skin_weights(mesh_node, weight_data, target_joints=None, model_root=None, vertex_map=None, rebind=False):
    """
    MFnSkinCluster.setWeights を用いてウェイトデータを指定メッシュへ一括適用
    インフルエンスはボーン名で対応付けを行い、頂点番号の対応表（vertex_map）または
    空間近接点マッチングにも対応します。
    """
    mesh_shape = _get_mesh_shape(mesh_node)
    if not mesh_shape or not weight_data:
        return False

    active_data = remap_skin_weights(weight_data, vertex_map) if vertex_map is not None else weight_data
    cached_infs = active_data.get("influences", [])
    sparse_weights = active_data.get("sparse_weights", [])
    cached_positions = active_data.get("positions", [])

    if not cached_infs or not sparse_weights:
        return False

    # 対応付け対象ジョイントの決定
    if target_joints:
        available_joints = list(target_joints)
    elif model_root:
        available_joints = get_model_joints(model_root)
    else:
        available_joints = []

    if not available_joints:
        for inf in cached_infs:
            ln = inf.get("long_name")
            sn = inf.get("short_name")
            if ln and mc.objExists(ln):
                available_joints.append(ln)
            elif sn and mc.objExists(sn):
                available_joints.append(sn)

    if not available_joints:
        return False

    joint_lookup = _build_joint_lookup(available_joints, model_root=model_root)
    inf_to_joint = _match_cached_influences_to_joints(cached_infs, joint_lookup)
    if not inf_to_joint:
        return False

    # バインドに必要なジョイント集合を整理
    required_joints = []
    seen_j = set()
    for j_path in list(inf_to_joint.values()) + joint_lookup["all"]:
        if j_path and j_path not in seen_j and mc.objExists(j_path):
            seen_j.add(j_path)
            required_joints.append(j_path)

    if not required_joints:
        return False

    existing_skin = get_skin_cluster(mesh_shape)
    if existing_skin and rebind:
        try:
            mc.skinCluster(mesh_shape, edit=True, unbind=True)
            existing_skin = None
        except Exception:
            pass

    if not existing_skin:
        short_tr = mesh_shape.split("|")[-1].replace("Shape", "")
        try:
            existing_skin = mc.skinCluster(
                required_joints,
                mesh_shape,
                toSelectedBones=True,
                normalizeWeights=1,
                maximumInfluences=4,
                obeyMaxInfluences=False,
                name=f"skin_{short_tr}"
            )[0]
        except Exception as e:
            mc.warning(f"スキンクラスタの新規バインド中にエラーが発生しました: {e}")
            return False
    else:
        # 既存スキンクラスタに不足しているインフルエンスがあれば追加
        cur_infs = set(_to_long_name(x) for x in (mc.skinCluster(existing_skin, query=True, influence=True) or []))
        missing = [j for j in set(inf_to_joint.values()) if j not in cur_infs and mc.objExists(j)]
        if missing:
            for mj in missing:
                try:
                    mc.skinCluster(existing_skin, edit=True, addInfluence=mj, weight=0.0)
                except Exception:
                    pass

    # MFnSkinCluster の準備とインフルエンス番号の確定
    sel = om.MSelectionList()
    sel.add(mesh_shape)
    sel.add(existing_skin)
    dag_path = sel.getDagPath(0)
    skin_mobj = sel.getDependNode(1)

    mfn_mesh = om.MFnMesh(dag_path)
    num_cur_verts = mfn_mesh.numVertices
    if num_cur_verts <= 0:
        return False

    fn_skin = oma.MFnSkinCluster(skin_mobj)
    dest_inf_dags = fn_skin.influenceObjects()
    num_dest_infs = len(dest_inf_dags)
    if num_dest_infs <= 0:
        return False

    dest_joint_to_idx = {}
    for d_idx in range(num_dest_infs):
        d_long = dest_inf_dags[d_idx].fullPathName()
        dest_joint_to_idx[d_long] = d_idx

    cached_idx_to_dest_idx = {}
    for c_idx, target_j in inf_to_joint.items():
        if target_j in dest_joint_to_idx:
            cached_idx_to_dest_idx[c_idx] = dest_joint_to_idx[target_j]

    if not cached_idx_to_dest_idx:
        return False

    # 頂点数が一致しないかつ明示的な対応表が未指定の場合は空間近接点で対応付け
    if num_cur_verts != len(sparse_weights) and vertex_map is None and cached_positions:
        cur_points = mfn_mesh.getPoints(om.MSpace.kWorld)
        spatial_map = _match_vertices_by_spatial_proximity(cur_points, cached_positions)
        active_data = remap_skin_weights(active_data, spatial_map)
        sparse_weights = active_data.get("sparse_weights", [])

    default_dest_idx = next(iter(cached_idx_to_dest_idx.values()), 0)
    flat_weights = [0.0] * (num_cur_verts * num_dest_infs)
    num_sparse = len(sparse_weights)

    for v_idx in range(num_cur_verts):
        base_offset = v_idx * num_dest_infs
        v_pairs = sparse_weights[v_idx] if v_idx < num_sparse else []
        accum = {}
        for pair in v_pairs:
            if len(pair) < 2:
                continue
            c_inf_idx = int(pair[0])
            w_val = float(pair[1])
            d_inf_idx = cached_idx_to_dest_idx.get(c_inf_idx)
            if d_inf_idx is not None and w_val > 1e-6:
                accum[d_inf_idx] = accum.get(d_inf_idx, 0.0) + w_val

        total_w = sum(accum.values())
        if total_w <= 1e-6:
            flat_weights[base_offset + default_dest_idx] = 1.0
        else:
            inv_total = 1.0 / total_w
            for d_inf_idx, w_val in accum.items():
                flat_weights[base_offset + d_inf_idx] = w_val * inv_total

    fn_comp = om.MFnSingleIndexedComponent()
    comp_obj = fn_comp.create(om.MFn.kMeshVertComponent)
    fn_comp.setCompleteData(num_cur_verts)

    inf_indices_arr = om.MIntArray(range(num_dest_infs))
    weights_arr = om.MDoubleArray(flat_weights)

    fn_skin.setWeights(dag_path, comp_obj, inf_indices_arr, weights_arr, normalize=True)
    return True


def _ensure_cache_holder_node():
    """シーン内の非表示ウェイトキャッシュ保持ノードを取得または作成"""
    if not mc.objExists(CACHE_HOLDER_NODE):
        node = mc.group(empty=True, name=CACHE_HOLDER_NODE)
        mc.setAttr(f"{node}.visibility", False)
        if mc.attributeQuery("hiddenInOutliner", node=node, exists=True):
            try:
                mc.setAttr(f"{node}.hiddenInOutliner", True)
            except Exception:
                pass
    else:
        node = CACHE_HOLDER_NODE

    if not mc.attributeQuery(CACHE_ATTR_NAME, node=node, exists=True):
        mc.addAttr(node, longName=CACHE_ATTR_NAME, dataType="string")
        mc.setAttr(f"{node}.{CACHE_ATTR_NAME}", "{}", type="string")

    return node


def _read_all_scene_caches():
    """シーン内ノードから全キャッシュ辞書を読み込み"""
    if not mc.objExists(CACHE_HOLDER_NODE):
        return {}
    if not mc.attributeQuery(CACHE_ATTR_NAME, node=CACHE_HOLDER_NODE, exists=True):
        return {}
    try:
        raw = mc.getAttr(f"{CACHE_HOLDER_NODE}.{CACHE_ATTR_NAME}")
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_all_scene_caches(store_dict):
    """全キャッシュ辞書をシーン内ノードの文字列属性へJSON保存"""
    node = _ensure_cache_holder_node()
    serialized = json.dumps(store_dict, ensure_ascii=False)
    mc.setAttr(f"{node}.{CACHE_ATTR_NAME}", serialized, type="string")


def save_model_weights_to_scene(model_root, cache_tag="default"):
    """
    指定モデル配下の全メッシュのスキンウェイトを抽出し、シーン内非表示ノードへJSONで保存
    Mayaを再起動してもシーンファイル内にキャッシュが永続化されます。
    """
    long_root = _to_long_name(model_root)
    if not long_root:
        return False

    meshes = get_model_meshes(long_root)
    if not meshes:
        return False

    mesh_entries = []
    for m in meshes:
        w_data = extract_mesh_skin_weights(m, model_root=long_root)
        if w_data:
            mesh_entries.append(w_data)

    if not mesh_entries:
        return False

    # 旧方式のゴーストメッシュがホルダー配下に残っていれば掃除
    if mc.objExists(CACHE_HOLDER_NODE):
        old_children = mc.listRelatives(CACHE_HOLDER_NODE, children=True, fullPath=True) or []
        if old_children:
            try:
                mc.delete(old_children)
            except Exception:
                pass

    store = _read_all_scene_caches()
    store[str(cache_tag)] = {
        "model_root": long_root,
        "model_short_name": long_root.split("|")[-1],
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "meshes": mesh_entries,
    }
    _write_all_scene_caches(store)
    return True


def load_model_weights_from_scene(cache_tag="default"):
    """指定タグのウェイトキャッシュデータをシーン内ノードから読み込み"""
    store = _read_all_scene_caches()
    return store.get(str(cache_tag))


def has_scene_weight_cache(cache_tag="default"):
    """指定タグのウェイトキャッシュがシーン内に存在するか判定"""
    entry = load_model_weights_from_scene(cache_tag)
    if not entry or not isinstance(entry, dict):
        return False
    return len(entry.get("meshes", [])) > 0


def list_scene_weight_caches():
    """シーン内に保存されているウェイトキャッシュのタグ一覧を取得"""
    store = _read_all_scene_caches()
    return [tag for tag, val in store.items() if isinstance(val, dict) and val.get("meshes")]


def clear_scene_weight_cache(cache_tag=None):
    """
    保存済みウェイトキャッシュを破棄
    cache_tag に None を指定した場合は全キャッシュおよび保持ノードを削除します。
    """
    if not mc.objExists(CACHE_HOLDER_NODE):
        return True

    if cache_tag is None:
        try:
            mc.delete(CACHE_HOLDER_NODE)
        except Exception:
            pass
        return True

    store = _read_all_scene_caches()
    store.pop(str(cache_tag), None)

    if not store:
        children = mc.listRelatives(CACHE_HOLDER_NODE, children=True) or []
        if not children:
            try:
                mc.delete(CACHE_HOLDER_NODE)
                return True
            except Exception:
                pass

    _write_all_scene_caches(store)
    return True


def _select_matching_cache_entry(target_mesh_shape, cached_meshes):
    """対象メッシュに対応するキャッシュエントリを特定"""
    if not cached_meshes:
        return None
    if len(cached_meshes) == 1:
        return cached_meshes[0]

    parents = mc.listRelatives(target_mesh_shape, parent=True, fullPath=True) or []
    parent_tr = parents[0] if parents else target_mesh_shape
    parent_short = parent_tr.split("|")[-1]

    for entry in cached_meshes:
        if entry.get("mesh_shape") == target_mesh_shape or entry.get("mesh_transform") == parent_tr:
            return entry
    for entry in cached_meshes:
        if entry.get("mesh_short_name") == parent_short:
            return entry
    for entry in cached_meshes:
        c_short = entry.get("mesh_short_name", "")
        if c_short and (c_short in parent_short or parent_short in c_short):
            return entry

    return cached_meshes[0]


def rebind_mesh_from_scene_cache(target_mesh, skeleton_root, cache_tag="default", vertex_map=None, rebind=True):
    """
    シーン内に保存されたウェイトキャッシュから対象メッシュへウェイトを復元・再バインド
    """
    mesh_shape = _get_mesh_shape(target_mesh)
    if not mesh_shape:
        return False

    cache_bundle = load_model_weights_from_scene(cache_tag)
    if not cache_bundle:
        return False

    cached_meshes = cache_bundle.get("meshes", [])
    matched_entry = _select_matching_cache_entry(mesh_shape, cached_meshes)
    if not matched_entry:
        return False

    target_joints = get_model_joints(skeleton_root) if skeleton_root else []
    return apply_mesh_skin_weights(
        mesh_node=mesh_shape,
        weight_data=matched_entry,
        target_joints=target_joints,
        model_root=skeleton_root,
        vertex_map=vertex_map,
        rebind=rebind,
    )


_joint_color_backup = {}


def _apply_joint_display(joint_node, visible=True, rgb_color=None):
    """ジョイントの drawStyle および任意のオーバーライドカラーを安全に反映"""
    if not joint_node or not mc.objExists(joint_node):
        return
    try:
        mc.setAttr(f"{joint_node}.drawStyle", 0 if visible else 2)
    except Exception:
        pass

    if rgb_color is not None:
        if joint_node not in _joint_color_backup:
            try:
                _joint_color_backup[joint_node] = {
                    "overrideEnabled": bool(mc.getAttr(f"{joint_node}.overrideEnabled")),
                    "overrideRGBColors": bool(mc.getAttr(f"{joint_node}.overrideRGBColors")),
                    "overrideColorRGB": tuple(mc.getAttr(f"{joint_node}.overrideColorRGB")[0]),
                }
            except Exception:
                _joint_color_backup[joint_node] = None
        try:
            mc.setAttr(f"{joint_node}.overrideEnabled", True)
            mc.setAttr(f"{joint_node}.overrideRGBColors", True)
            mc.setAttr(f"{joint_node}.overrideColorRGB", rgb_color[0], rgb_color[1], rgb_color[2], type="double3")
        except Exception:
            pass
    elif joint_node in _joint_color_backup:
        bak = _joint_color_backup.pop(joint_node)
        if bak:
            try:
                mc.setAttr(f"{joint_node}.overrideEnabled", bak["overrideEnabled"])
                mc.setAttr(f"{joint_node}.overrideRGBColors", bak["overrideRGBColors"])
                r, g, b = bak["overrideColorRGB"]
                mc.setAttr(f"{joint_node}.overrideColorRGB", r, g, b, type="double3")
            except Exception:
                pass


def set_models_bone_visibility(model_a, model_b=None, mode="both", colorize=False):
    """
    2体のキャラクターモデルのボーン表示状態をビューポート上で切り替え
    joint.drawStyle (0: ボーン表示 / 2: 非表示) を使うため、親子階層やスキニングには影響しません。

    引数:
        model_a: モデルA（移植元モデル）のルートノード
        model_b: モデルB（ベースモデル）のルートノード
        mode: "both"（両方表示） / "model_a"（Aのみ） / "model_b"（Bのみ） / "none"（両方非表示）
        colorize: True の場合、モデルAを水色・モデルBを橙色で色分け表示
    """
    norm_mode = str(mode or "both").lower()
    if norm_mode == "all":
        norm_mode = "both"
    elif norm_mode == "only_a":
        norm_mode = "model_a"
    elif norm_mode == "only_b":
        norm_mode = "model_b"

    joints_a = set(get_model_joints(model_a)) if (model_a and mc.objExists(model_a)) else set()
    joints_b = set(get_model_joints(model_b)) if (model_b and mc.objExists(model_b)) else set()
    all_joints = joints_a | joints_b

    color_a = (0.25, 0.85, 1.0)
    color_b = (1.0, 0.65, 0.2)
    color_shared = (0.55, 1.0, 0.55)

    visible_count = 0
    hidden_count = 0

    for j in all_joints:
        in_a = j in joints_a
        in_b = j in joints_b

        if norm_mode == "both":
            vis = True
        elif norm_mode == "model_a":
            vis = in_a
        elif norm_mode == "model_b":
            vis = in_b
        else:
            vis = False

        rgb = None
        if colorize and vis:
            if in_a and in_b:
                rgb = color_shared
            elif in_a:
                rgb = color_a
            else:
                rgb = color_b

        _apply_joint_display(j, visible=vis, rgb_color=rgb)
        if vis:
            visible_count += 1
        else:
            hidden_count += 1

    return {
        "mode": norm_mode,
        "visible_count": visible_count,
        "hidden_count": hidden_count,
        "model_a_count": len(joints_a),
        "model_b_count": len(joints_b),
    }
