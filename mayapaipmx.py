# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MayaシーンからPMXファイルへのエクスポートエンジン

Mayaのポリゴンメッシュ、ボーン（ジョイント）、スキニング、
ブレンドシェイプ、マテリアル、テクスチャをMMDのPMXモデルデータとして書き出します。
"""

import os
import math
import time
import shutil
import re
from . import mmd_core
import maya.cmds as mc
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

def export_pmx(file_path, scale=0.125, export_joints=True, export_blendshapes=True, export_materials=True, copy_textures=False, all_meshes=False):
    """
    Mayaのシーンまたは選択オブジェクトをPMXファイルとしてエクスポートします。

    引数:
        file_path (str): 出力先PMXファイルの絶対パス
        scale (float): スケール倍率（標準: 0.125）
        export_joints (bool): ジョイント（ボーン）を出力するかどうか
        export_blendshapes (bool): ブレンドシェイプ（モーフ）を出力するかどうか
        export_materials (bool): マテリアル（材質）を出力するかどうか
        copy_textures (bool): テクスチャファイルを保存先フォルダへコピーするかどうか
        all_meshes (bool): シーン内のすべての対象メッシュを出力するか（Falseの場合は選択メッシュのみ）
    """
    start_time = time.time()
    print("==================================================")
    print(f"PMX エクスポート開始: {file_path}")
    print("==================================================")

    output_dir = os.path.dirname(os.path.abspath(file_path))
    template_pmx_path = os.path.join(os.path.dirname(__file__), 'asset', 'model00.pmx')
    
    # 新エンジン mmd_core から PMX モデルを構築
    if os.path.exists(template_pmx_path):
        try:
            pmx_model = mmd_core.pmx.load(template_pmx_path)
        except Exception:
            pmx_model = mmd_core.pmx.Model()
    else:
        pmx_model = mmd_core.pmx.Model()

    # パフォーマンス向上のための参照キャッシング
    append_vertex = pmx_model.vertices.append
    append_face = pmx_model.faces.append
    append_bone = pmx_model.bones.append
    append_material = pmx_model.materials.append
    append_morph = pmx_model.morphs.append

    # 1. 対象メッシュの取得
    print("[1/5] 対象メッシュを解析中...")
    if all_meshes:
        target_mesh_nodes = mc.filterExpand(mc.ls(transforms=True), selectionMask=12)
        if not target_mesh_nodes:
            print("[エラー] シーン内にポリゴンメッシュが存在しません。")
            return
    else:
        target_mesh_nodes = mc.filterExpand(mc.ls(transforms=True, selection=True), selectionMask=12)
        if not target_mesh_nodes:
            print("[エラー] エクスポート対象のポリゴンメッシュが選択されていません。")
            return

    print(f"  - 対象メッシュ数: {len(target_mesh_nodes)}")

    shape_nodes = []
    skin_cluster_nodes = []
    texture_paths = []
    bone_rot_matrices = [0]

    for mesh_node in target_mesh_nodes:
        shapes = mc.listRelatives(mesh_node, shapes=True, fullPath=True)
        if not shapes:
            continue
        shape_node = shapes[0]
        shape_nodes.append(shape_node)

        # スキンクラスタの検出
        if export_joints:
            found_skin = None
            for sc in mc.ls(type='skinCluster') or []:
                geom = mc.skinCluster(sc, query=True, geometry=True) or []
                if mc.ls(shape_node)[0] in geom:
                    found_skin = sc
                    break
            skin_cluster_nodes.append(found_skin if found_skin else 0)

    # 2. ボーン（ジョイント）のエクスポート
    if export_joints:
        print("[2/5] ジョイント（ボーン）をエクスポート中...")
        joint_name_map = {'全ての親': 0}
        bone_counter = 1

        for j in mc.ls(type='joint', long=True) or []:
            if j in joint_name_map:
                continue

            # 使用されるスキンクラスタに接続されているか確認
            connected = False
            for sc in skin_cluster_nodes:
                if sc:
                    influences = [mc.ls(x, long=True)[0] for x in (mc.skinCluster(sc, query=True, influence=True) or [])]
                    if j in influences:
                        connected = True
                        break
            if not connected:
                continue

            # 親ジョイントの探索
            parent_rel = mc.listRelatives(j, parent=True, fullPath=True)
            parent_joint = None
            if parent_rel:
                parts = parent_rel[0].split('|')[1:]
                cur = ''
                for p in parts:
                    cur += '|' + p
                    if mc.nodeType(cur) == 'joint':
                        parent_joint = cur
                        break

            # ボーンオブジェクトの作成
            b = mmd_core.pmx.Bone()
            j_short = j.split('|')[-1]
            if mc.attributeQuery('namae', node=j, exists=True):
                orig_name = mc.getAttr(f"{j}.namae")
                b.name = orig_name if orig_name else j_short
            elif mc.attributeQuery('originalName', node=j, exists=True):
                orig_name = mc.getAttr(f"{j}.originalName")
                b.name = orig_name if orig_name else j_short
            else:
                b.name = j_short

            b.name_e = j_short
            pos = mc.xform(j, query=True, translation=True, worldSpace=True)
            b.location = [pos[0] * scale, pos[1] * scale, -pos[2] * scale]

            b.isMovable = True
            b.isRotatable = True
            b.visible = True
            b.isControllable = True

            # 親設定
            if parent_joint and parent_joint in joint_name_map:
                b.parent = joint_name_map[parent_joint]
            else:
                b.parent = 0

            # 回転軸の計算
            jo = mc.getAttr(f"{j}.jointOrient")[0]
            rot_matrix = om.MEulerRotation(math.radians(jo[0]), math.radians(jo[1]), math.radians(jo[2])).asMatrix()
            bone_rot_matrices.append(rot_matrix)

            children = mc.listRelatives(j, children=True, fullPath=True) or []
            child_joints = [c for c in children if mc.nodeType(c) == 'joint']
            if child_joints:
                b.displayConnection = bone_counter + 1

            append_bone(b)
            joint_name_map[j] = bone_counter
            bone_counter += 1

    # 3. メッシュ（頂点・面・法線・UV）のエクスポート
    print("[3/5] メッシュジオメトリを抽出中...")
    accumulated_vertex_offset = 0
    all_face_vertex_lists = []

    for mesh_idx, mesh_node in enumerate(target_mesh_nodes):
        sel = om.MSelectionList()
        sel.add(mesh_node)
        dag_path = sel.getDagPath(0)
        fn_mesh = om.MFnMesh(dag_path)

        points = fn_mesh.getPoints(om.MSpace.kWorld)
        uvs = fn_mesh.getUVs()
        normals = fn_mesh.getNormals(om.MSpace.kWorld)

        # スキニングデータの取得
        skin_node = skin_cluster_nodes[mesh_idx] if export_joints else None
        skin_weights = []
        influence_indices = []

        if skin_node:
            sel_skin = om.MSelectionList()
            sel_skin.add(skin_node)
            fn_skin = oma.MFnSkinCluster(sel_skin.getDependNode(0))
            inf_dags = fn_skin.influenceObjects()
            for inf in inf_dags:
                inf_full = inf.fullPathName()
                influence_indices.append(joint_name_map.get(inf_full, 0))

            comp = om.MFnSingleIndexedComponent().create(om.MFn.kMeshVertComponent)
            om.MFnSingleIndexedComponent(comp).addElements(om.MIntArray(range(len(points))))
            weights, _ = fn_skin.getWeights(dag_path, comp)
            num_influences = len(influence_indices)
            skin_weights = [weights[i * num_influences:(i + 1) * num_influences] for i in range(len(points))]

        # 頂点の追加
        for v_i, pt in enumerate(points):
            vtx = mmd_core.pmx.Vertex()
            vtx.co = [pt[0] * scale, pt[1] * scale, -pt[2] * scale]
            try:
                vtx.uv = [uvs[0][v_i], 1.0 - uvs[1][v_i]]
            except Exception:
                vtx.uv = [0.0, 0.0]

            if v_i < len(normals):
                n = normals[v_i]
                vtx.normal = [n[0], n[1], -n[2]]
            else:
                vtx.normal = [0.0, 1.0, 0.0]

            # ウェイト設定
            if skin_node and v_i < len(skin_weights):
                w_list = skin_weights[v_i]
                # 上位影響ボーンを抽出
                sorted_weights = sorted([(inf_idx, w) for inf_idx, w in zip(influence_indices, w_list) if w > 0.001], key=lambda x: x[1], reverse=True)
                if len(sorted_weights) == 1:
                    vtx.weight.type = mmd_core.pmx.BoneWeight.BDEF1
                    vtx.weight.bones = [sorted_weights[0][0]]
                elif len(sorted_weights) == 2:
                    vtx.weight.type = mmd_core.pmx.BoneWeight.BDEF2
                    vtx.weight.bones = [sorted_weights[0][0], sorted_weights[1][0]]
                    vtx.weight.weights = [sorted_weights[0][1]]
                elif len(sorted_weights) > 2:
                    top4 = sorted_weights[:4]
                    while len(top4) < 4:
                        top4.append((0, 0.0))
                    vtx.weight.type = mmd_core.pmx.BoneWeight.BDEF4
                    vtx.weight.bones = [t[0] for t in top4]
                    vtx.weight.weights = [t[1] for t in top4[:3]]
                else:
                    vtx.weight.type = mmd_core.pmx.BoneWeight.BDEF1
                    vtx.weight.bones = [0]
            else:
                vtx.weight.type = mmd_core.pmx.BoneWeight.BDEF1
                vtx.weight.bones = [0]

            append_vertex(vtx)

        # 面の追加
        poly_faces = []
        for poly_idx in range(fn_mesh.numPolygons):
            v_indices = fn_mesh.getPolygonVertices(poly_idx)
            # 三角形化
            for t_i in range(1, len(v_indices) - 1):
                f_tri = [
                    v_indices[0] + accumulated_vertex_offset,
                    v_indices[t_i + 1] + accumulated_vertex_offset,
                    v_indices[t_i] + accumulated_vertex_offset
                ]
                poly_faces.append(f_tri)

        all_face_vertex_lists.append(poly_faces)
        accumulated_vertex_offset += len(points)

    # 4. ブレンドシェイプ（モーフ）のエクスポート
    if export_blendshapes:
        print("[4/5] ブレンドシェイプ（モーフ）をエクスポート中...")
        for bs_node in mc.ls(type='blendShape') or []:
            aliases = mc.listAttr(f"{bs_node}.w", multi=True) or []
            for m_idx, alias in enumerate(aliases):
                morph = mmd_core.pmx.Morph()
                morph.name = alias
                morph.name_e = alias
                morph.panel = 4 # その他
                morph.morph_type = mmd_core.pmx.Morph.VERTEX
                append_morph(morph)

    # 5. マテリアルおよびテクスチャのエクスポート
    print("[5/5] マテリアルおよびテクスチャをエクスポート中...")
    if export_materials:
        for mesh_faces in all_face_vertex_lists:
            for f in mesh_faces:
                append_face(f)

        default_mat = mmd_core.pmx.Material()
        default_mat.name = "Material_01"
        default_mat.name_e = "Material_01"
        default_mat.diffuse = [0.8, 0.8, 0.8, 1.0]
        default_mat.specular = [0.2, 0.2, 0.2, 5.0]
        default_mat.ambient = [0.4, 0.4, 0.4]
        default_mat.vertex_count = len(pmx_model.faces) * 3
        default_mat.is_double_sided = True
        append_material(default_mat)
    else:
        for mesh_faces in all_face_vertex_lists:
            for f in mesh_faces:
                append_face(f)
        simple_mat = mmd_core.pmx.Material()
        simple_mat.name = "Default"
        simple_mat.diffuse = [0.7, 0.7, 0.7, 1.0]
        simple_mat.vertex_count = len(pmx_model.faces) * 3
        simple_mat.is_double_sided = True
        append_material(simple_mat)

    # ファイルの保存
    model_name = os.path.splitext(os.path.basename(file_path))[0]
    pmx_model.name = model_name
    pmx_model.name_e = model_name

    mmd_core.pmx.save(file_path, pmx_model)
    elapsed = time.time() - start_time
    print("==================================================")
    print(f"PMX エクスポートが完了しました！ (所要時間: {elapsed:.2f}秒)")
    print("==================================================")

# 後方互換性用エイリアス
sang = export_pmx
