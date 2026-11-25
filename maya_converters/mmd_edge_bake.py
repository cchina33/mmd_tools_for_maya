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
    """シェーディンググループの mmdMaterial から (enable, size) を返す。無ければ (False, 0.0)。"""
    shaders = cmds.listConnections(sg + ".surfaceShader", source=True, destination=False) or []
    for shd in shaders:
        if cmds.nodeType(shd) == "mmdMaterial":
            return bool(cmds.getAttr(shd + ".edgeEnable")), float(cmds.getAttr(shd + ".edgeSize"))
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
                scale = size * src[v] if enable else 0.0
                colors.append(om.MColor((scale, 1.0, 0.0, 1.0)))
                face_ids.append(f)
                vert_ids.append(v)

        fn.setFaceVertexColors(colors, face_ids, vert_ids)

        # 頂点カラー表示は出さない (表面シェーディングに影響させない)
        cmds.setAttr(shape + ".displayColors", 0)
        done.append(shape)

    print("[MMD Edge] baked {} mesh(es): {}".format(len(done), done))
    return done
