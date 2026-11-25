# -*- coding: utf-8 -*-
"""
mmdMaterial の材質ごとの edgeEnable / edgeSize を、頂点カラーセット
"mmd_edge_scale" へ焼き込む (面頂点単位)。

エンコード (mmd_edge_shader_code.h と一致):
    R = 倍率 (edgeEnable ? edgeSize * PMX頂点エッジ倍率 : 0)
    G = 1.0  (焼き込み済みマーカー)
    B = 0, A = 1

PMX 由来の元の頂点エッジ倍率は "mmd_edge_scale_src" に退避し、再実行しても二重に掛からない。
使い方:
    import mmd_edge_bake
    mmd_edge_bake.bake_edge_scale()          # 選択中のメッシュ (無ければ mmdMaterial の付いた各メッシュ)
材質の edgeEnable / edgeSize を変えたら再実行する。
"""

import maya.cmds as cmds
import maya.api.OpenMaya as om

SET_NAME = "mmd_edge_scale"
SRC_NAME = "mmd_edge_scale_src"


def _edge_params_of_sg(sg):
    """シェーディンググループの mmdMaterial から (has_mmd, effective_size) を返す。無ければ (False, 0.0)。"""
    shaders = cmds.listConnections(sg + ".surfaceShader", source=True, destination=False) or []
    for shd in shaders:
        if cmds.nodeType(shd) in ("mmdMaterial", "mmdToonShader"):
            enable = bool(cmds.getAttr(shd + ".edgeEnable"))
            size = float(cmds.getAttr(shd + ".edgeSize"))
            diff_alpha = float(cmds.getAttr(shd + ".diffuseAlpha")) if cmds.attributeQuery("diffuseAlpha", node=shd, exists=True) else 1.0
            trans_val = cmds.getAttr(shd + ".transparency")[0] if cmds.attributeQuery("transparency", node=shd, exists=True) else (0.0, 0.0, 0.0)
            trans_avg = (float(trans_val[0]) + float(trans_val[1]) + float(trans_val[2])) / 3.0
            opacity = max(0.0, min(diff_alpha, 1.0 - trans_avg))
            eff_size = (size * opacity) if (enable and size > 0.001 and opacity > 0.05) else 0.0
            return True, eff_size
    return False, 0.0


def _mesh_shapes(targets):
    shapes = []
    for t in targets:
        if cmds.nodeType(t) == "mesh":
            shapes.append(t)
        else:
            shapes += cmds.listRelatives(t, allDescendents=True, type="mesh",
                                         noIntermediate=True, fullPath=True) or []
    return list(dict.fromkeys(shapes))


def _read_source_scale(fn, num_vertices):
    """PMX 由来の頂点エッジ倍率 (頂点ごと) を返す。無ければすべて 1.0。"""
    names = list(fn.getColorSetNames())

    if SRC_NAME in names:
        cols = fn.getVertexColors(SRC_NAME)
        return [max(0.0, c.r) for c in cols]

    if SET_NAME in names:
        cols = fn.getVertexColors(SET_NAME)
        baked = len(cols) > 0 and cols[0].g > 0.5
        if not baked:
            # 未焼き込みの元データを退避
            fn.createColorSet(SRC_NAME, False, om.MFnMesh.kRGBA)
            fn.setCurrentColorSetName(SRC_NAME)
            idx = om.MIntArray(range(len(cols)))
            fn.setVertexColors(cols, idx)
            return [max(0.0, c.r) for c in cols]

    return [1.0] * num_vertices


def _is_skydome_or_stage_mesh(mesh_shape):
    """メッシュがスカイドームまたはステージであるかを判定します"""
    try:
        try:
            from asset.model_classifier_manager import ModelClassifierManager
        except Exception:
            from ..asset.model_classifier_manager import ModelClassifierManager
        mgr = ModelClassifierManager.get_instance()
        if mgr.is_skydome_mesh(mesh_shape) or mgr.is_stage_mesh(mesh_shape):
            return True
    except Exception:
        pass

    # ノードアトリビュート mmdModelType の確認
    try:
        if cmds.attributeQuery('mmdModelType', node=mesh_shape, exists=True):
            m_type = cmds.getAttr(f"{mesh_shape}.mmdModelType")
            if m_type in ('skydome', 'stage'):
                return True
        parent_tr = cmds.listRelatives(mesh_shape, parent=True)
        if parent_tr and cmds.attributeQuery('mmdModelType', node=parent_tr[0], exists=True):
            m_type = cmds.getAttr(f"{parent_tr[0]}.mmdModelType")
            if m_type in ('skydome', 'stage'):
                return True
    except Exception:
        pass
    return False


def bake_edge_scale(targets=None):
    if not targets:
        targets = cmds.ls(selection=True, long=True) or []
    if targets:
        shapes = _mesh_shapes(targets)
    else:
        shapes = _mesh_shapes(cmds.ls(type="mesh", long=True) or [])

    done = []
    for shape in shapes:
        sel = om.MSelectionList()
        sel.add(shape)
        dag = sel.getDagPath(0)
        fn = om.MFnMesh(dag)

        inst = dag.instanceNumber() if dag.isInstanced() else 0
        sg_objs, face_sg = fn.getConnectedShaders(inst)
        sg_params = []
        for o in sg_objs:
            sg_params.append(_edge_params_of_sg(om.MFnDependencyNode(o).name()))
        if not any(p[0] for p in sg_params):
            continue  # mmdMaterial (edgeEnable) が無いメッシュは対象外

        # スカイドームまたはステージモデルの場合はエッジ描画を対象外（倍率0.0）に設定
        is_bg_stage = _is_skydome_or_stage_mesh(shape)
        if is_bg_stage:
            sg_params = [(True, 0.0) for _ in sg_params]

        src = _read_source_scale(fn, fn.numVertices)

        if SET_NAME not in fn.getColorSetNames():
            fn.createColorSet(SET_NAME, False, om.MFnMesh.kRGBA)  # clamped=False: 1.0 超えを許可
        fn.setCurrentColorSetName(SET_NAME)

        colors = om.MColorArray()
        face_ids = om.MIntArray()
        vert_ids = om.MIntArray()
        for f in range(fn.numPolygons):
            sg_idx = face_sg[f]
            enable, size = sg_params[sg_idx] if 0 <= sg_idx < len(sg_params) else (False, 0.0)
            for v in fn.getPolygonVertices(f):
                scale = size * src[v] if (enable and size > 0.001) else 0.0
                alpha_flag = 1.0 if scale > 0.001 else 0.0
                colors.append(om.MColor((scale, 1.0, 0.0, alpha_flag)))
                face_ids.append(f)
                vert_ids.append(v)

        fn.setFaceVertexColors(colors, face_ids, vert_ids)

        # 頂点カラー表示は出さない (表面シェーディングに影響させない)
        cmds.setAttr(shape + ".displayColors", 0)
        done.append(shape)

    print("[MMD Edge] baked {} mesh(es): {}".format(len(done), done))
    return done
