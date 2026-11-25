# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - 反転法線押し出し（Inverted Hull）エッジメッシュ生成エンジン

OpenGL Core Profile および DirectX 11、各種外部レンダラーを問わず、
MMD本家モデルと同等の美しい輪郭線（エッジ）を確実に描画するための
反転押し出しジオメトリおよびエッジ専用マテリアルを生成・構築します。
本家MMD（_MikuDanceStudio）およびPMX仕様書に忠実に準拠しています。
"""

import os
import sys
import math
import maya.cmds as mc
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

try:
    from ..asset.jaka import safe_node_name
except Exception:
    try:
        from asset.jaka import safe_node_name
    except Exception:
        def safe_node_name(name, *args, **kwargs):
            return name.replace(":", "_").replace("|", "_").replace(" ", "_")


# MMD本家準拠の基本押し出し基準スケール (Mayaスケール 8.0 の環境に最適化)
DEFAULT_EDGE_BASE_SCALE = 0.035


def _calc_effective_edge_offset(norm, vtx_scale, mat_size, effective_scale, is_enabled):
    """
    MMD本家準拠の頂点押し出しオフセットベクトルを計算します。
    エッジが無効な頂点は内側へ引き込み、輪郭線の露出を抑止します。
    """
    norm_len = norm.length()
    if norm_len > 1e-6:
        n = norm / norm_len
    else:
        return om.MFloatVector(0.0, 0.0, 0.0)

    if not is_enabled or vtx_scale <= 0.0 or mat_size <= 0.0:
        # 本家仕様: エッジ無効頂点は内側（法線逆方向）へ沈み込ませて隠す
        shrink_dist = -0.005 * (effective_scale / DEFAULT_EDGE_BASE_SCALE)
        return om.MFloatVector(n.x * shrink_dist, n.y * shrink_dist, n.z * shrink_dist)

    # 押し出し量 = 法線 * (基本スケール * 頂点エッジ倍率 * 材質エッジサイズ)
    dist = effective_scale * vtx_scale * mat_size
    return om.MFloatVector(n.x * dist, n.y * dist, n.z * dist)


def build_edge_mesh_from_pmx(pmx_model,
                             model_mesh_node,
                             joint_node_names=None,
                             base_thickness=DEFAULT_EDGE_BASE_SCALE,
                             scale=8.0):
    """
    PMX生データからダイレクトに反転押し出し（Inverted Hull）エッジメッシュを構築します。
    PMX仕様およびMMD本家の頂点押し出し計算式、材質描画フラグ、エッジカラー(RGBA)を反映します。

    :param pmx_model: 解析済みPMXオブジェクト
    :param model_mesh_node: Maya上の元メッシュノード名
    :param joint_node_names: スキニング対象のジョイント名リスト
    :param base_thickness: 基本エッジ押し出し係数
    :param scale: シーンのスケール倍率
    :return: 生成されたエッジメッシュのトランスフォームノード名
    """
    if not mc.objExists(model_mesh_node):
        print(f"[MMD Tools] 対象メッシュが存在しません: {model_mesh_node}")
        return None

    edge_trans_name = f"{model_mesh_node}_Edge"
    if mc.objExists(edge_trans_name):
        try:
            mc.delete(edge_trans_name)
        except Exception:
            pass

    num_vertices = len(pmx_model.vertices)
    if num_vertices == 0:
        return None

    effective_scale = base_thickness * (scale / 8.0)

    # 材質ごとのエッジ設定およびフェース走査
    # PMX仕様: flags & 0x10 がエッジ描画フラグ
    mat_edge_info = {}
    f_idx = 0
    edge_face_counts = []
    edge_face_connects = []
    edge_mat_face_mapping = {}

    # 各頂点のエッジ有効性と最大材質サイズを把握
    vtx_mat_sizes = [0.0] * num_vertices
    vtx_edge_enabled = [False] * num_vertices

    for m_idx, mat in enumerate(pmx_model.materials):
        f_count = int(mat.vertex_count / 3)
        faces_chunk = pmx_model.faces[f_idx:f_idx + f_count]
        f_idx += f_count

        # 材質描画フラグの確認
        draw_flags = getattr(mat, 'draw_flags', 0x10) if hasattr(mat, 'draw_flags') else (0x10 if getattr(mat, 'edge_flag', 1) else 0)
        has_edge_flag = bool(draw_flags & 0x10)
        is_point_mode = bool(draw_flags & 0x40)
        is_line_mode = bool(draw_flags & 0x80)

        diffuse_alpha = mat.diffuse[3] if len(mat.diffuse) > 3 else 1.0
        edge_size = getattr(mat, 'edge_size', 1.0)
        raw_edge_col = getattr(mat, 'edge_color', [0.0, 0.0, 0.0, 1.0])

        edge_r = float(raw_edge_col[0]) if len(raw_edge_col) > 0 else 0.0
        edge_g = float(raw_edge_col[1]) if len(raw_edge_col) > 1 else 0.0
        edge_b = float(raw_edge_col[2]) if len(raw_edge_col) > 2 else 0.0
        edge_a = float(raw_edge_col[3]) if len(raw_edge_col) > 3 else 1.0

        # エッジ描画が無効な材質の判定
        is_mat_edge_valid = True
        if not has_edge_flag or is_point_mode or is_line_mode:
            is_mat_edge_valid = False
        if edge_size <= 0.0 or edge_a <= 0.05 or diffuse_alpha <= 0.05:
            is_mat_edge_valid = False

        mat_name = getattr(mat, 'name', f"mat_{m_idx}")
        mat_edge_info[m_idx] = {
            'valid': is_mat_edge_valid,
            'name': mat_name,
            'size': edge_size,
            'color': (edge_r, edge_g, edge_b, edge_a)
        }

        if not is_mat_edge_valid:
            continue

        edge_mat_face_mapping[m_idx] = []

        for face in faces_chunk:
            unique_verts = list(dict.fromkeys(face))
            if len(unique_verts) < 3:
                continue

            for vi in unique_verts:
                if 0 <= vi < num_vertices:
                    vtx_mat_sizes[vi] = max(vtx_mat_sizes[vi], edge_size)
                    vtx_edge_enabled[vi] = True

            # 面の頂点順序を反転（Inverted Hull 構造の構築）
            reversed_face = list(reversed(unique_verts))
            edge_face_connects.extend(reversed_face)
            edge_face_counts.append(len(reversed_face))

            current_face_idx = len(edge_face_counts) - 1
            edge_mat_face_mapping[m_idx].append(current_face_idx)

    if not edge_face_counts:
        print("[MMD Tools] エッジ描画対象となるポリゴンフェースが存在しません。")
        return None

    # 各頂点の押し出し座標配列を算出
    offset_points = om.MFloatPointArray()
    for vi, vtx in enumerate(pmx_model.vertices):
        px = vtx.co[0] * scale
        py = vtx.co[1] * scale
        pz = -vtx.co[2] * scale

        nx = vtx.normal[0] if vtx.normal else 0.0
        ny = vtx.normal[1] if vtx.normal else 0.0
        nz = -vtx.normal[2] if vtx.normal else 0.0
        norm = om.MFloatVector(nx, ny, nz)

        e_scale = getattr(vtx, 'edge_scale', 1.0)
        m_size = vtx_mat_sizes[vi]
        is_en = vtx_edge_enabled[vi]

        offset_vec = _calc_effective_edge_offset(norm, e_scale, m_size, effective_scale, is_en)
        offset_points.append(om.MFloatPoint(px + offset_vec.x, py + offset_vec.y, pz + offset_vec.z, 1.0))

    # 新規エッジポリゴンメッシュの生成 (Maya API 2.0)
    edge_trans_fn = om.MFnTransform()
    edge_trans_obj = edge_trans_fn.create()
    edge_trans_fn.setName(edge_trans_name)
    actual_edge_trans = edge_trans_fn.name()

    edge_mesh_fn = om.MFnMesh()
    edge_face_counts_m = om.MIntArray(edge_face_counts)
    edge_face_connects_m = om.MIntArray(edge_face_connects)

    dummy_u = om.MFloatArray([0.0] * num_vertices)
    dummy_v = om.MFloatArray([0.0] * num_vertices)

    edge_mesh_obj = edge_mesh_fn.create(
        offset_points, edge_face_counts_m, edge_face_connects_m, dummy_u, dummy_v, edge_trans_obj
    )
    edge_mesh_fn.setName(f"{actual_edge_trans}Shape")
    actual_edge_shape = edge_mesh_fn.name()

    # エッジメッシュの表示属性の最適化（手前の面を確実に破棄・カリングし、奥側の輪郭面のみ描画）
    try:
        mc.setAttr(f"{actual_edge_shape}.castsShadows", 0)
        mc.setAttr(f"{actual_edge_shape}.receiveShadows", 0)
        mc.setAttr(f"{actual_edge_shape}.motionBlur", 0)
        mc.setAttr(f"{actual_edge_shape}.primaryVisibility", 1)
        mc.setAttr(f"{actual_edge_shape}.doubleSided", 0)
        mc.setAttr(f"{actual_edge_shape}.opposite", 0)
        if mc.attributeQuery('backfaceCulling', node=actual_edge_shape, exists=True):
            mc.setAttr(f"{actual_edge_shape}.backfaceCulling", 1)
        mc.polyOptions(actual_edge_shape, backCulling=True)
    except Exception:
        pass

    # 太さ微調整用カスタムアトリビュートをトランスフォームに追加
    if not mc.attributeQuery('edgeScale', node=actual_edge_trans, exists=True):
        mc.addAttr(actual_edge_trans, longName='edgeScale', niceName='エッジ太さ倍率', attributeType='float', defaultValue=1.0, keyable=True)
    if not mc.attributeQuery('mmdEdgeMesh', node=actual_edge_trans, exists=True):
        mc.addAttr(actual_edge_trans, longName='mmdEdgeMesh', attributeType='bool', defaultValue=True)

    # 材質ごとのエッジ専用マテリアル (surfaceShader) の生成およびフェース割り当て
    for m_idx, face_list in edge_mat_face_mapping.items():
        if not face_list:
            continue
        m_info = mat_edge_info.get(m_idx, {})
        mat_raw_name = m_info.get('name', f"mat_{m_idx}")
        edge_rgba = m_info.get('color', (0.0, 0.0, 0.0, 1.0))

        safe_mat = safe_node_name(mat_raw_name, prefix="mat", index=m_idx)
        edge_shd_name = f"{safe_mat}_Edge_shd"
        edge_sg_name = f"{safe_mat}_Edge_SG"

        trans_val = max(0.0, min(1.0, 1.0 - edge_rgba[3]))

        if not mc.objExists(edge_shd_name):
            edge_shd = mc.shadingNode('surfaceShader', asShader=True, name=edge_shd_name)
            mc.setAttr(f"{edge_shd}.outColor", edge_rgba[0], edge_rgba[1], edge_rgba[2], typ='double3')
            mc.setAttr(f"{edge_shd}.outTransparency", trans_val, trans_val, trans_val, typ='double3')
        else:
            edge_shd = edge_shd_name
            mc.setAttr(f"{edge_shd}.outColor", edge_rgba[0], edge_rgba[1], edge_rgba[2], typ='double3')
            mc.setAttr(f"{edge_shd}.outTransparency", trans_val, trans_val, trans_val, typ='double3')

        if not mc.objExists(edge_sg_name):
            edge_sg = mc.sets(renderable=True, noSurfaceShader=True, empty=True, name=edge_sg_name)
            mc.connectAttr(f"{edge_shd}.outColor", f"{edge_sg}.surfaceShader", force=True)
        else:
            edge_sg = edge_sg_name

        face_components = [f"{actual_edge_shape}.f[{fid}]" for fid in face_list]
        if face_components:
            try:
                mc.sets(face_components, edit=True, forceElement=edge_sg)
            except Exception as e:
                print(f"[MMD Tools] エッジフェースへのマテリアル割り当てエラー: {e}")

    # スキニング (skinCluster) の複製同期
    _bind_and_copy_skin(model_mesh_node, actual_edge_trans, joint_node_names)

    # 階層の同期（元メッシュと同一の親へ配置）
    parent_nodes = mc.listRelatives(model_mesh_node, parent=True, fullPath=True) or []
    if parent_nodes:
        try:
            mc.parent(actual_edge_trans, parent_nodes[0])
        except Exception:
            pass

    print(f"[MMD Tools] PMX準拠エッジメッシュの構築が終了しました: {actual_edge_trans}")
    return actual_edge_trans


def create_inverted_hull_edge_mesh(mesh_node,
                                   edge_materials_info=None,
                                   base_thickness=DEFAULT_EDGE_BASE_SCALE,
                                   scale=8.0):
    """
    既存のポリゴンメッシュから反転法線押し出し（Inverted Hull）エッジメッシュを生成し、
    材質ごとのエッジカラー専用 surfaceShader を割り当ててスキニングを同期します。

    :param mesh_node: 対象となる元のメッシュノード（トランスフォームまたはシェイプ）
    :param edge_materials_info: 材質ごとのエッジ設定辞書リスト (省略時は既存シェーダーから自動抽出)
    :param base_thickness: 基本エッジ押し出し係数
    :param scale: シーンのスケール倍率
    :return: 生成されたエッジメッシュのトランスフォームノード名
    """
    if not mc.objExists(mesh_node):
        print(f"[MMD Tools] 対象メッシュが見つかりません: {mesh_node}")
        return None

    if mc.objectType(mesh_node) == 'mesh':
        shape_node = mesh_node
        trans_node = mc.listRelatives(shape_node, parent=True, fullPath=True)[0]
    else:
        trans_node = mesh_node
        shapes = mc.listRelatives(trans_node, shapes=True, fullPath=True) or []
        if not shapes:
            print(f"[MMD Tools] メッシュシェイプが存在しません: {trans_node}")
            return None
        shape_node = shapes[0]

    edge_trans_name = f"{trans_node}_Edge"
    if mc.objExists(edge_trans_name):
        try:
            mc.delete(edge_trans_name)
        except Exception:
            pass

    selection_list = om.MSelectionList()
    selection_list.add(shape_node)
    dag_path = selection_list.getDagPath(0)
    fn_mesh = om.MFnMesh(dag_path)

    points = fn_mesh.getPoints(om.MSpace.kObject)
    num_vertices = len(points)
    if num_vertices == 0:
        return None

    normals = fn_mesh.getVertexNormals(False, om.MSpace.kObject)

    # 頂点カラーセット (mmd_edge_scale) から頂点エッジ倍率を抽出
    vtx_edge_scales = [1.0] * num_vertices
    color_set_names = fn_mesh.getColorSetNames()
    edge_scale_set_name = None
    for cs_name in color_set_names:
        if "edge" in cs_name.lower():
            edge_scale_set_name = cs_name
            break

    if edge_scale_set_name:
        try:
            colors = fn_mesh.getVertexColors(edge_scale_set_name)
            if colors and len(colors) == num_vertices:
                for vi, col in enumerate(colors):
                    vtx_edge_scales[vi] = max(0.0, float(col.r))
        except Exception as e:
            print(f"[MMD Tools] 頂点エッジ倍率カラーセットの読み込みをスキップしました: {e}")

    polygon_count = fn_mesh.numPolygons
    shaders, shader_indices = fn_mesh.getConnectedShaders(0)
    shading_groups = [om.MFnDependencyNode(s).name() for s in shaders]

    mat_edge_settings = {}
    for s_idx, sg_name in enumerate(shading_groups):
        setting = {
            'enable': True,
            'color': (0.1, 0.1, 0.1, 1.0),
            'size': 1.0,
            'shader': None
        }
        surface_shaders = mc.listConnections(f"{sg_name}.surfaceShader", source=True, destination=False) or []
        if surface_shaders:
            shd = surface_shaders[0]
            setting['shader'] = shd
            if mc.attributeQuery('edgeEnable', node=shd, exists=True):
                try:
                    setting['enable'] = bool(mc.getAttr(f"{shd}.edgeEnable"))
                except Exception:
                    pass
            if mc.attributeQuery('edgeColor', node=shd, exists=True):
                try:
                    ec = mc.getAttr(f"{shd}.edgeColor")[0]
                    setting['color'] = (float(ec[0]), float(ec[1]), float(ec[2]), 1.0)
                except Exception:
                    pass
            if mc.attributeQuery('edgeSize', node=shd, exists=True):
                try:
                    setting['size'] = float(mc.getAttr(f"{shd}.edgeSize"))
                except Exception:
                    pass

            for a_attr in ['diffuseAlpha', 'opacity', 'transparency']:
                if mc.attributeQuery(a_attr, node=shd, exists=True):
                    try:
                        val = mc.getAttr(f"{shd}.{a_attr}")
                        if isinstance(val, (list, tuple)):
                            val = sum(val) / len(val)
                        if a_attr == 'transparency' and val > 0.95:
                            setting['enable'] = False
                        elif a_attr != 'transparency' and val < 0.05:
                            setting['enable'] = False
                    except Exception:
                        pass
                    break

        mat_edge_settings[s_idx] = setting

    if edge_materials_info and isinstance(edge_materials_info, dict):
        for k, v in edge_materials_info.items():
            if k in mat_edge_settings:
                mat_edge_settings[k].update(v)

    vtx_mat_sizes = [1.0] * num_vertices
    vtx_has_enabled_edge = [False] * num_vertices

    edge_face_counts = []
    edge_face_connects = []
    edge_face_sg_mapping = {}

    for face_id in range(polygon_count):
        sg_idx = shader_indices[face_id] if face_id < len(shader_indices) else 0
        sg_setting = mat_edge_settings.get(sg_idx, {'enable': True, 'size': 1.0})
        if not sg_setting.get('enable', True) or sg_setting.get('size', 1.0) <= 0.0:
            continue

        mat_size = sg_setting.get('size', 1.0)
        vtx_indices = fn_mesh.getPolygonVertices(face_id)
        for vi in vtx_indices:
            vtx_mat_sizes[vi] = max(vtx_mat_sizes[vi], mat_size)
            vtx_has_enabled_edge[vi] = True

        reversed_vtx = list(reversed(vtx_indices))
        edge_face_connects.extend(reversed_vtx)
        edge_face_counts.append(len(reversed_vtx))

        edge_face_id = len(edge_face_counts) - 1
        if sg_idx not in edge_face_sg_mapping:
            edge_face_sg_mapping[sg_idx] = []
        edge_face_sg_mapping[sg_idx].append(edge_face_id)

    if not edge_face_counts:
        print("[MMD Tools] エッジ描画対象となるフェースが存在しません。")
        return None

    effective_scale = base_thickness * (scale / 8.0)
    offset_points = om.MFloatPointArray(num_vertices, om.MFloatPoint())

    for vi in range(num_vertices):
        orig_p = points[vi]
        norm = normals[vi]
        e_scale = vtx_edge_scales[vi]
        m_size = vtx_mat_sizes[vi]
        is_en = vtx_has_enabled_edge[vi]

        offset_vec = _calc_effective_edge_offset(norm, e_scale, m_size, effective_scale, is_en)
        offset_points[vi] = om.MFloatPoint(
            orig_p.x + offset_vec.x,
            orig_p.y + offset_vec.y,
            orig_p.z + offset_vec.z,
            1.0
        )

    edge_trans_fn = om.MFnTransform()
    edge_trans_obj = edge_trans_fn.create()
    edge_trans_fn.setName(edge_trans_name)
    actual_edge_trans = edge_trans_fn.name()

    edge_mesh_fn = om.MFnMesh()
    edge_face_counts_m = om.MIntArray(edge_face_counts)
    edge_face_connects_m = om.MIntArray(edge_face_connects)

    dummy_u = om.MFloatArray([0.0] * num_vertices)
    dummy_v = om.MFloatArray([0.0] * num_vertices)

    edge_mesh_obj = edge_mesh_fn.create(
        offset_points, edge_face_counts_m, edge_face_connects_m, dummy_u, dummy_v, edge_trans_obj
    )
    edge_mesh_fn.setName(f"{actual_edge_trans}Shape")
    actual_edge_shape = edge_mesh_fn.name()

    try:
        mc.setAttr(f"{actual_edge_shape}.castsShadows", 0)
        mc.setAttr(f"{actual_edge_shape}.receiveShadows", 0)
        mc.setAttr(f"{actual_edge_shape}.motionBlur", 0)
        mc.setAttr(f"{actual_edge_shape}.primaryVisibility", 1)
        mc.setAttr(f"{actual_edge_shape}.doubleSided", 0)
        mc.setAttr(f"{actual_edge_shape}.opposite", 0)
        if mc.attributeQuery('backfaceCulling', node=actual_edge_shape, exists=True):
            mc.setAttr(f"{actual_edge_shape}.backfaceCulling", 1)
        mc.polyOptions(actual_edge_shape, backCulling=True)
    except Exception:
        pass

    if not mc.attributeQuery('edgeScale', node=actual_edge_trans, exists=True):
        mc.addAttr(actual_edge_trans, longName='edgeScale', niceName='エッジ太さ倍率', attributeType='float', defaultValue=1.0, keyable=True)
    if not mc.attributeQuery('mmdEdgeMesh', node=actual_edge_trans, exists=True):
        mc.addAttr(actual_edge_trans, longName='mmdEdgeMesh', attributeType='bool', defaultValue=True)

    for sg_idx, face_list in edge_face_sg_mapping.items():
        sg_setting = mat_edge_settings.get(sg_idx, {})
        edge_rgba = sg_setting.get('color', (0.1, 0.1, 0.1, 1.0))
        orig_shd = sg_setting.get('shader', f"mat_{sg_idx}")

        safe_shd_name = safe_node_name(orig_shd)
        edge_shd_name = f"{safe_shd_name}_Edge_shd"
        edge_sg_name = f"{safe_shd_name}_Edge_SG"

        trans_val = max(0.0, min(1.0, 1.0 - (edge_rgba[3] if len(edge_rgba) > 3 else 1.0)))

        if not mc.objExists(edge_shd_name):
            edge_shd = mc.shadingNode('surfaceShader', asShader=True, name=edge_shd_name)
            mc.setAttr(f"{edge_shd}.outColor", edge_rgba[0], edge_rgba[1], edge_rgba[2], typ='double3')
            mc.setAttr(f"{edge_shd}.outTransparency", trans_val, trans_val, trans_val, typ='double3')
        else:
            edge_shd = edge_shd_name
            mc.setAttr(f"{edge_shd}.outColor", edge_rgba[0], edge_rgba[1], edge_rgba[2], typ='double3')
            mc.setAttr(f"{edge_shd}.outTransparency", trans_val, trans_val, trans_val, typ='double3')

        if not mc.objExists(edge_sg_name):
            edge_sg = mc.sets(renderable=True, noSurfaceShader=True, empty=True, name=edge_sg_name)
            mc.connectAttr(f"{edge_shd}.outColor", f"{edge_sg}.surfaceShader", force=True)
        else:
            edge_sg = edge_sg_name

        face_components = [f"{actual_edge_shape}.f[{fid}]" for fid in face_list]
        if face_components:
            try:
                mc.sets(face_components, edit=True, forceElement=edge_sg)
            except Exception as e:
                print(f"[MMD Tools] エッジフェースへのマテリアル割り当てエラー: {e}")

    _bind_and_copy_skin(shape_node, actual_edge_trans)

    parent_nodes = mc.listRelatives(trans_node, parent=True, fullPath=True) or []
    if parent_nodes:
        try:
            mc.parent(actual_edge_trans, parent_nodes[0])
        except Exception:
            pass

    print(f"[MMD Tools] Inverted Hull エッジメッシュの生成が終了しました: {actual_edge_trans}")
    return actual_edge_trans


def _bind_and_copy_skin(source_node, target_edge_trans, joint_node_names=None):
    """
    元メッシュのスキン設定（skinCluster）を複製してエッジメッシュへ同期します。
    """
    orig_skin = None
    history = mc.listHistory(source_node, pruneDagObjects=True) or []
    for h in history:
        if mc.nodeType(h) == 'skinCluster':
            orig_skin = h
            break

    if not orig_skin:
        return None

    try:
        joints = joint_node_names if joint_node_names else (mc.skinCluster(orig_skin, query=True, influence=True) or [])
        if joints:
            edge_skin = mc.skinCluster(
                joints, target_edge_trans,
                toSelectedBones=True,
                bindMethod=0,
                normalizeWeights=1,
                name=f"{target_edge_trans}_skinCluster"
            )[0]

            mc.copySkinWeights(
                sourceSkin=orig_skin,
                destinationSkin=edge_skin,
                noMirror=True,
                surfaceAssociation='closestPoint',
                influenceAssociation='oneToOne'
            )
            print(f"[MMD Tools] エッジメッシュのスキニング同期が終了しました: {edge_skin}")
            return edge_skin
    except Exception as e:
        print(f"[MMD Tools] エッジメッシュのスキニング同期中にエラーが発生しました: {e}")
    return None


def apply_edge_mesh_to_current_scene(target=None, base_thickness=DEFAULT_EDGE_BASE_SCALE, scale=8.0):
    """
    現在のMayaシーン内の指定メッシュ（または自動検出されたMMDモデルメッシュ）に対し、
    反転押し出しエッジメッシュを即座に生成・適用します。
    """
    targets = []
    if target:
        targets = [target]
    else:
        selected = mc.ls(selection=True, transforms=True) or []
        if selected:
            targets = selected
        else:
            all_meshes = mc.ls(type='mesh', long=True) or []
            for m in all_meshes:
                p = mc.listRelatives(m, parent=True, fullPath=True)[0]
                if mc.attributeQuery('MMD_model', node=p, exists=True) and not p.endswith("_Edge"):
                    targets.append(p)
            if not targets:
                for m in all_meshes:
                    p = mc.listRelatives(m, parent=True, fullPath=True)[0]
                    if not p.endswith("_Edge"):
                        targets.append(p)

    targets = list(dict.fromkeys(targets))
    results = []
    for t in targets:
        if str(t).endswith("_Edge"):
            continue
        res = create_inverted_hull_edge_mesh(t, base_thickness=base_thickness, scale=scale)
        if res:
            results.append(res)

    return results


def remove_edge_mesh_from_scene(target=None):
    """
    指定されたモデル（または選択中モデル、未指定時はシーン内のMMDモデル）の
    反転法線エッジメッシュを解除・削除し、未使用となったエッジ専用シェーダーをクリーンアップします。

    :param target: 解除対象のメッシュまたはトランスフォームノード
    :return: 削除されたエッジメッシュノード名のリスト
    """
    removed_nodes = []
    targets_to_delete = set()

    if target:
        candidates = [target]
    else:
        selected = mc.ls(selection=True, transforms=True) or []
        if selected:
            candidates = selected
        else:
            all_edge_transforms = mc.ls("*_Edge", transforms=True) or []
            for em in all_edge_transforms:
                targets_to_delete.add(em)
            candidates = []

    for c in candidates:
        c_str = str(c)
        if c_str.endswith("_Edge"):
            targets_to_delete.add(c_str)
        else:
            direct_edge = f"{c_str}_Edge"
            if mc.objExists(direct_edge):
                targets_to_delete.add(direct_edge)

            descendants = mc.listRelatives(c, allDescendents=True, fullPath=True, type='transform') or []
            for d in descendants:
                d_short = d.split("|")[-1]
                if d_short.endswith("_Edge"):
                    targets_to_delete.add(d)

    for node in targets_to_delete:
        if mc.objExists(node):
            try:
                mc.delete(node)
                removed_nodes.append(node)
                print(f"[MMD Tools] エッジメッシュを解除・削除しました: {node}")
            except Exception as e:
                print(f"[MMD Tools] エッジメッシュ削除中にエラーが発生しました: {node} ({e})")

    edge_shaders = mc.ls("*_Edge_shd", type='surfaceShader') or []
    for es in edge_shaders:
        conns = mc.listConnections(es, source=False, destination=True) or []
        sgs = [c for c in conns if mc.nodeType(c) == 'shadingEngine']
        for sg in sgs:
            members = mc.sets(sg, query=True) or []
            if not members:
                try:
                    mc.delete(sg)
                except Exception:
                    pass
        if not mc.listConnections(es, source=False, destination=True):
            try:
                mc.delete(es)
            except Exception:
                pass

    return removed_nodes
