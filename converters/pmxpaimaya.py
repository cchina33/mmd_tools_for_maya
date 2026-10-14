# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MMDモデル (PMX/PMD/X) Mayaインポートエンジン

MMDモデルのデータを解析し、Mayaのポリゴンメッシュ、マテリアル、
ボーン（スケルトン）、スキニング、ブレンドシェイプを自動構築します。
中国語・多言語の大容量モデルにも対応した堅牢なエラーハンドリングを提供します。
"""

import os
import math
import itertools
import time
import re
import sys
import json
import unicodedata

try:
    from .. import mmd_core
    from ..asset.jaka import romaji, safe_node_name
    from ..asset.bone_dict import get_english_bone_name, get_japanese_bone_name
except Exception:
    import mmd_core
    from asset.jaka import romaji, safe_node_name
    from asset.bone_dict import get_english_bone_name, get_japanese_bone_name
import maya.cmds as mc
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

# place2dTexture ノードと file ノードを接続するアトリビュート定義
PLACE2D_ATTR_CONNECTIONS = [
    ['coverage', 'coverage'],
    ['translateFrame', 'translateFrame'],
    ['rotateFrame', 'rotateFrame'],
    ['mirrorU', 'mirrorU'],
    ['mirrorV', 'mirrorV'],
    ['stagger', 'stagger'],
    ['wrapU', 'wrapU'],
    ['wrapV', 'wrapV'],
    ['repeatUV', 'repeatUV'],
    ['offset', 'offset'],
    ['rotateUV', 'rotateUV'],
    ['noiseUV', 'noiseUV'],
    ['vertexUvOne', 'vertexUvOne'],
    ['vertexUvTwo', 'vertexUvTwo'],
    ['vertexUvThree', 'vertexUvThree'],
    ['vertexCameraOne', 'vertexCameraOne'],
    ['outUV', 'uv'],
    ['outUvFilterSize', 'uvFilterSize'],
]

# 後方互換性用エイリアス
chueam_placed2d = PLACE2D_ATTR_CONNECTIONS

def vector_cross_product(a, b):
    """3次元ベクトルの外積を計算します。"""
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0]
    ]

# 後方互換性用エイリアス
cross = vector_cross_product

def _image_has_transparency(img_path):
    """テクスチャ画像が有効な透過情報（アルファチャネル）を持っているか判定します。"""
    if not img_path or not os.path.isfile(img_path):
        return False
    ext = os.path.splitext(img_path)[1].lower()
    if ext not in ['.png', '.tga', '.dds', '.tif', '.tiff']:
        return False
    try:
        from PIL import Image
        with Image.open(img_path) as im:
            if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):
                extrema = im.getextrema()
                if im.mode == 'RGBA':
                    return extrema[3][0] < 254
                elif im.mode == 'LA':
                    return extrema[1][0] < 254
                return True
            return False
    except Exception:
        return ext in ['.png', '.tga', '.dds']

def _get_shared_toon_path(toon_idx):
    """
    共有トゥーンテクスチャ (toon01.bmp〜toon10.bmp) の実ファイルパスを解決します。
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(current_dir, "toon", f"toon{toon_idx + 1:02d}.bmp"),
        os.path.join(current_dir, "asset", "toon", f"toon{toon_idx + 1:02d}.bmp"),
        os.path.join(os.path.dirname(current_dir), "toon", f"toon{toon_idx + 1:02d}.bmp"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c.replace('\\', '/')
    return None

def _get_unique_node_name(base_name):
    """Mayaシーン内で既存のノード名と衝突しない一意な名前を生成します。"""
    candidate = base_name
    count = 1
    while mc.objExists(candidate):
        candidate = f"{base_name}_{count}"
        count += 1
    return candidate

def create_mesh(node_name, vertex_positions, face_indices, face_vertex_counts, uvs_u, uvs_v, normals=None, edge_scales=None):
    """
    Maya API 2.0 (MFnMesh) を使用してポリゴンメッシュを高速生成します。
    """
    arr_xyz = om.MFloatPointArray(vertex_positions)
    arr_face_indices = om.MIntArray(face_indices)
    arr_face_counts = om.MIntArray(face_vertex_counts)
    arr_u = om.MFloatArray(uvs_u)
    arr_v = om.MFloatArray(uvs_v)

    trans_fn = om.MFnTransform()
    trans_obj = trans_fn.create()
    trans_fn.setName(node_name)
    actual_node_name = trans_fn.name()

    fn_mesh = om.MFnMesh()
    fn_mesh.create(arr_xyz, arr_face_counts, arr_face_indices, arr_u, arr_v, trans_obj)
    fn_mesh.setName(f"{actual_node_name}Shape")
    fn_mesh.assignUVs(arr_face_counts, arr_face_indices)

    if normals:
        try:
            fn_mesh.setVertexNormals(normals, om.MIntArray(range(len(vertex_positions))))
        except Exception as e:
            print(f"[警告] 法線の割り当てをスキップしました: {e}")

    # PMX頂点エッジ倍率 (edge_scale) を頂点カラーセットとして格納
    if edge_scales:
        try:
            color_set_name = "mmd_edge_scale"
            actual_set_name = fn_mesh.createColorSet(color_set_name, False, om.MFnMesh.kRGBA)
            fn_mesh.setCurrentColorSetName(actual_set_name)
            color_array = om.MColorArray([om.MColor((float(s), float(s), float(s), 1.0)) for s in edge_scales])
            vertex_indices = om.MIntArray(range(len(edge_scales)))
            fn_mesh.setVertexColors(color_array, vertex_indices)
        except Exception as e:
            print(f"[警告] エッジ倍率カラーセットの作成をスキップしました: {e}")

    # MMD由来メッシュとしての識別用アトリビュートを付与
    mc.addAttr(actual_node_name, longName='MMD_model', niceName='MMDからのモデル', attributeType='bool')
    mc.setAttr(f"{actual_node_name}.MMD_model", True)
    try:
        mc.setAttr(f"{actual_node_name}.aiOpaque", 0) # Arnold 不透明度制御
    except Exception:
        pass

    return actual_node_name

# 後方互換性用エイリアス
sang_poly = create_mesh

def setup_mmd_ik(model_node=None, bone_map=None):
    """
    MMDモデルの足IKおよびつま先IKに対してMayaのikHandleとコンストレイントを構築します。
    また、Tda式等でメッシュがスキニングされている準標準「足D」「ひざD」「足首D」ボーン群
    に対しても通常ボーンの回転を自動追従（orientConstraint）させ、メッシュの連動を実現します。
    """
    if not bone_map:
        return []

    created_handles = []

    def _find_j(name):
        if not name or not bone_map:
            return None
        if name in bone_map:
            return bone_map[name]
        norm = unicodedata.normalize('NFKC', name).strip()
        for k, v in bone_map.items():
            if unicodedata.normalize('NFKC', k).strip() == norm:
                return v
        return None

    # 左右の足について処理
    for side_jp, side_en in [("左", "L"), ("右", "R")]:
        leg_j = _find_j(f"{side_jp}足")
        knee_j = _find_j(f"{side_jp}ひざ") or _find_j(f"{side_jp}膝")
        ankle_j = _find_j(f"{side_jp}足首")
        toe_j = _find_j(f"{side_jp}つま先")
        leg_ik_j = _find_j(f"{side_jp}足ＩＫ") or _find_j(f"{side_jp}足IK")
        toe_ik_j = _find_j(f"{side_jp}つま先ＩＫ") or _find_j(f"{side_jp}つま先IK")

        # 足IK (大腿からひざを経由して足首へ)
        if leg_j and ankle_j and leg_ik_j:
            if mc.objExists(leg_j) and mc.objExists(ankle_j) and mc.objExists(leg_ik_j):
                h_name = f"ikHandle_leg_{side_en}_{model_node}" if model_node else f"ikHandle_leg_{side_en}"
                guide_name = f"fkGuide_leg_{side_en}_{model_node}" if model_node else f"fkGuide_leg_{side_en}"
                pv_grp_name = f"poleVector_grp_leg_{side_en}_{model_node}" if model_node else f"poleVector_grp_leg_{side_en}"
                pv_name = f"poleVector_leg_{side_en}_{model_node}" if model_node else f"poleVector_leg_{side_en}"
                for old_node in [h_name, pv_name, pv_grp_name, guide_name]:
                    if mc.objExists(old_node):
                        try:
                            mc.delete(old_node)
                        except Exception:
                            pass
                try:
                    # ひざジョイントの優先角度（Preferred Angle）を設定
                    # 深くしゃがみ込んだ姿勢などでIKソルバー（ikRPsolver）が逆側（後ろ曲がり）の解を選択するのを防止
                    if knee_j and mc.objExists(knee_j):
                        try:
                            mc.setAttr(f"{knee_j}.preferredAngleX", 60.0)
                            mc.setAttr(f"{knee_j}.preferredAngleY", 0.0)
                            mc.setAttr(f"{knee_j}.preferredAngleZ", 0.0)
                        except Exception:
                            pass

                    h_leg, _ = mc.ikHandle(startJoint=leg_j, endEffector=ankle_j, solver='ikRPsolver', name=h_name)
                    mc.pointConstraint(leg_ik_j, h_leg, maintainOffset=False)
                    mc.orientConstraint(leg_ik_j, ankle_j, maintainOffset=True)
                    mc.setAttr(f"{h_leg}.visibility", False)
                    created_handles.append(h_leg)

                    # 大腿のFK回転に忠実追従するFKガイド階層とポールベクターの構築
                    if knee_j and mc.objExists(knee_j):
                        pos_a = mc.xform(leg_j, query=True, worldSpace=True, translation=True)
                        pos_k = mc.xform(knee_j, query=True, worldSpace=True, translation=True)

                        # 大腿長から適切なオフセット距離を算出
                        leg_len = math.sqrt(sum((pos_k[i]-pos_a[i])**2 for i in range(3)))
                        pv_dist = max(10.0, leg_len * 1.5)

                        # 大腿の親ジョイント（下半身）を取得してFKガイドを親付け
                        parent_j = (mc.listRelatives(leg_j, parent=True, fullPath=True) or [None])[0]
                        guide = mc.group(empty=True, name=guide_name)
                        if parent_j:
                            guide = mc.parent(guide, parent_j)[0]
                        mc.xform(guide, worldSpace=True, translation=pos_a)
                        mc.setAttr(f"{guide}.rotateOrder", mc.getAttr(f"{leg_j}.rotateOrder"))
                        mc.setAttr(f"{guide}.visibility", False)

                        # ガイドの子供としてポールベクターロケータを配置
                        # 脚が縦なら前、足を前に投げ出した姿勢なら上が効くよう前上方向にオフセット
                        pv_loc = mc.spaceLocator(name=pv_name)[0]
                        pv_loc = mc.parent(pv_loc, guide)[0]
                        mc.setAttr(f"{pv_loc}.translate", 0.0, pv_dist * 0.5, pv_dist, type='double3')
                        mc.setAttr(f"{pv_loc}.visibility", False)

                        # ポールベクターコンストレイントの設定（膝の内股ねじれ・裏返りを防止）
                        mc.poleVectorConstraint(pv_loc, h_leg)
                except Exception as e:
                    print(f"  [警告] 足IK ({side_jp}) の構築をスキップしました: {e}")

        # つま先IK (足首からつま先へ)
        if ankle_j and toe_j and toe_ik_j:
            if mc.objExists(ankle_j) and mc.objExists(toe_j) and mc.objExists(toe_ik_j):
                h_name = f"ikHandle_toe_{side_en}_{model_node}" if model_node else f"ikHandle_toe_{side_en}"
                if mc.objExists(h_name):
                    try:
                        mc.delete(h_name)
                    except Exception:
                        pass
                try:
                    h_toe, _ = mc.ikHandle(startJoint=ankle_j, endEffector=toe_j, solver='ikSCsolver', name=h_name)
                    mc.pointConstraint(toe_ik_j, h_toe, maintainOffset=False)
                    mc.setAttr(f"{h_toe}.visibility", False)
                    created_handles.append(h_toe)
                except Exception as e:
                    print(f"  [警告] つま先IK ({side_jp}) の構築をスキップしました: {e}")

        # 準標準 足Dボーン群（Tda式モデル等の並列スキニング階層）への回転追従連動
        leg_d_j = _find_j(f"{side_jp}足D")
        knee_d_j = _find_j(f"{side_jp}ひざD")
        ankle_d_j = _find_j(f"{side_jp}足首D")

        for src_j, dst_j, b_label in [(leg_j, leg_d_j, "足D"), (knee_j, knee_d_j, "ひざD"), (ankle_j, ankle_d_j, "足首D")]:
            if src_j and dst_j and mc.objExists(src_j) and mc.objExists(dst_j):
                try:
                    existing_c = mc.listConnections(dst_j, type="orientConstraint")
                    if not existing_c:
                        mc.orientConstraint(src_j, dst_j, maintainOffset=False)
                except Exception as e:
                    print(f"  [情報] {side_jp}{b_label} 連動コンストレイント設定: {e}")

    return created_handles

def import_pmx(file_path, scale=8.0, split_by_material=False, create_blendshapes=True, create_joints=True, material_type=1, create_light=True, set_untone_mapped=True, enable_toon=True, shadow_mode=1, show_completion_message=True):
    """
    MMDモデルファイル (.pmx / .pmd / .x) をMayaにインポートします。

    引数:
        file_path (str): モデルファイルの絶対パス
        scale (float): スケール倍率（標準: 8.0）
        split_by_material (bool): 材質ごとにポリゴンメッシュを分割するかどうか
        create_blendshapes (bool): ブレンドシェイプ（モーフ）を作成するかどうか
        create_joints (bool): ジョイント（ボーンスケルトン）を作成するかどうか
        material_type (int): マテリアル種別 (0: なし, 1: Blinn, 2: Phong, 3: Lambert, 4: StandardSurface, 5: sample_mmd_mat ベータ版)
        create_light (bool): MMD標準ライティング（平行光＆環境光）を作成するかどうか
        set_untone_mapped (bool): ビュー変換を 'Un-tone-mapped (sRGB)' に設定して発色を最適化するかどうか
        enable_toon (bool): Toonシェーディング（セル影）を適用するかどうか
        shadow_mode (int): セルフ影モード (0: なし, 1: モード1, 2: モード2)

    戻り値:
        tuple: (モデルノード名, ルートジョイント一覧, スキンクラスタ名, ブレンドシェイプ名)
    """
    start_time = time.time()
    ext = os.path.splitext(file_path)[1].lower() if file_path else ""
    print("==================================================")
    print(f"MMD モデルインポート開始: {os.path.basename(file_path)}")
    if ext == '.pmx':
        print("[PMXチェック] 事前チェック（未登録漢字・構成要素整合性）完了を確認")
    print("==================================================")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"モデルファイルが存在しません: {file_path}")

    # perspカメラの焦点距離をMMD標準画角に一番最初に設定
    setup_persp_camera_for_mmd()

    # MMD標準ライティングの作成
    if create_light:
        create_mmd_lighting(shadow_mode=shadow_mode)

    # ビュー変換を Un-tone-mapped (sRGB) に設定して色の沈み・暗化を防止
    if set_untone_mapped:
        set_untone_mapped_view_transform()

    # ビューポートのテクスチャ表示、アンチエイリアシング、深度ピーリングを一括適用
    setup_viewport_display(shadow_mode=shadow_mode if create_light else None)

    # モデルファイルのロード
    print("[1/6] モデルファイルを読み込み中...")
    try:
        if ext == '.pmx':
            pmx_model = mmd_core.pmx.load(file_path)
        elif ext == '.pmd':
            pmx_model = mmd_core.pmd.load2pmx(file_path)
        elif ext == '.x':
            pmx_model = mmd_core.x_file.load2pmx(file_path)
        else:
            raise ValueError(f"未対応の拡張子です: {ext}")
    except Exception as e:
        print(f"[エラー] ファイル読み込みに失敗しました: {e}")
        raise

    num_vertices = len(pmx_model.vertices)
    num_faces = len(pmx_model.faces)
    num_bones = len(pmx_model.bones)
    num_materials = len(pmx_model.materials)
    num_morphs = len(pmx_model.morphs)

    print(f"  - モデル名: {pmx_model.name} (英名: {getattr(pmx_model, 'name_e', '')})")
    print(f"  - 頂点数: {num_vertices:,} / 面数: {num_faces:,}")
    print(f"  - ボーン数: {num_bones:,} / 材質数: {num_materials:,} / モーフ数: {num_morphs:,}")

    # モデルノード名の安全な決定（中国語モデル・英名フォールバック対応）
    model_name_e = getattr(pmx_model, 'name_e', None)
    base_model_name = safe_node_name(pmx_model.name, name_e=model_name_e, prefix="MMD_Model")
    if not base_model_name or base_model_name == 'node':
        file_base = os.path.splitext(os.path.basename(file_path))[0]
        base_model_name = safe_node_name(file_base, prefix="MMD_Model")

    model_node_name = _get_unique_node_name(base_model_name)
    root_joint_names = []
    skin_node_name = None
    blendshape_node_name = None

    # 2. ポリゴンメッシュの生成
    print("[2/6] ポリゴンメッシュを作成中...")
    if split_by_material:
        material_mesh_nodes = []
    else:
        vtx_coords = []
        vtx_u = []
        vtx_v = []
        vtx_normals = []
        vtx_edge_scales = []
        # 各材質の頂点範囲とエッジ有効性をマッピング（透明モーフ材質の頂点エッジを抑止）
        vert_edge_enabled_map = {}
        f_idx = 0
        for mat in pmx_model.materials:
            f_count = int(mat.vertex_count / 3)
            m_alpha = mat.diffuse[3]
            m_has_edge = bool(getattr(mat, 'draw_flags', 0x10) & 0x10) if hasattr(mat, 'draw_flags') else (getattr(mat, 'edge_flag', 1) != 0)
            # アルファが微小なモーフ用材質はエッジを一律無効化
            if m_alpha <= 0.05:
                m_has_edge = False
            for face in pmx_model.faces[f_idx:f_idx + f_count]:
                for vi in face:
                    if vi not in vert_edge_enabled_map:
                        vert_edge_enabled_map[vi] = m_has_edge
                    else:
                        vert_edge_enabled_map[vi] = vert_edge_enabled_map[vi] and m_has_edge
            f_idx += f_count

        for v_i, vtx in enumerate(pmx_model.vertices):
            try:
                vtx_coords.append(om.MFloatPoint(vtx.co[0] * scale, vtx.co[1] * scale, -vtx.co[2] * scale))
            except Exception:
                vtx_coords.append(om.MFloatPoint(0.0, 0.0, 0.0))
            vtx_u.append(vtx.uv[0])
            vtx_v.append(1.0 - vtx.uv[1])
            e_scale = getattr(vtx, 'edge_scale', 1.0)
            if not vert_edge_enabled_map.get(v_i, True):
                e_scale = 0.0
            vtx_edge_scales.append(e_scale)
            if vtx.normal:
                vtx_normals.append(om.MFloatVector(vtx.normal[0], vtx.normal[1], -vtx.normal[2]))

        face_vertex_indices = []
        face_vertex_counts = []
        valid_face_flags = []

        for face in pmx_model.faces:
            unique_verts = list(dict.fromkeys(face))
            vert_count = len(unique_verts)
            if vert_count >= 3:
                face_vertex_indices.extend(unique_verts)
                face_vertex_counts.append(vert_count)
                valid_face_flags.append(True)
            else:
                valid_face_flags.append(False)

        model_mesh_node = create_mesh(
            model_node_name, vtx_coords, face_vertex_indices, face_vertex_counts, vtx_u, vtx_v, vtx_normals,
            edge_scales=vtx_edge_scales
        )

        if material_type == 0:
            mc.select(model_mesh_node)
            mc.hyperShade(assign='lambert1')

    # 3. テクスチャおよびマテリアルの作成
    print("[3/6] テクスチャおよびマテリアルを作成中...")
    # メインテクスチャ、スフィア、カスタムToonで使用されているインデックスを収集
    used_texture_indices = set()
    for mat in pmx_model.materials:
        if mat.texture >= 0:
            used_texture_indices.add(mat.texture)
        if getattr(mat, 'sphere_texture', -1) >= 0:
            used_texture_indices.add(mat.sphere_texture)
        if not getattr(mat, 'is_shared_toon_texture', False) and getattr(mat, 'toon_texture', -1) >= 0:
            used_texture_indices.add(mat.toon_texture)

    # オリジナルマテリアルプラグイン (sample_mmd_mat) のロード
    if material_type == 5:
        if not mc.pluginInfo("mmd_material", query=True, loaded=True):
            try:
                mc.loadPlugin("mmd_material")
                print("[MMD Tools for Maya] mmd_material プラグインをロードしました。")
            except Exception as e:
                # Maya.env未反映時のフルパスフォールバック
                plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                mll_path = os.path.join(plugin_root, "mmd_material_plugin", "bin", "mmd_material.mll")
                try:
                    mc.loadPlugin(mll_path)
                    print(f"[MMD Tools for Maya] mmd_material プラグインを絶対パスからロードしました: {mll_path}")
                except Exception as e2:
                    print(f"[警告] mmd_material プラグインのロードに失敗しました: {e} / {e2}")

    texture_file_nodes = []
    texture_has_alpha_map = {}
    model_dir = os.path.dirname(os.path.abspath(file_path))

    for tex_idx, tex in enumerate(pmx_model.textures):
        # テクスチャパスのマルチバイト・相対パス解決
        raw_tex_path = tex.path.replace('\\', '/')
        if os.path.isabs(raw_tex_path):
            resolved_tex_path = raw_tex_path
        else:
            resolved_tex_path = os.path.normpath(os.path.join(model_dir, raw_tex_path)).replace('\\', '/')

        tex_filename = os.path.basename(resolved_tex_path)
        safe_tex_id = safe_node_name(tex_filename, prefix="tex", index=tex_idx)
        file_node_name = f"{safe_tex_id}_file_{model_node_name}"

        is_tex_file_valid = tex_idx in used_texture_indices and os.path.isfile(resolved_tex_path)
        if is_tex_file_valid:
            texture_has_alpha_map[tex_idx] = _image_has_transparency(resolved_tex_path)
            file_node = mc.shadingNode('file', asTexture=True, name=file_node_name)
            mc.setAttr(f"{file_node}.ftn", resolved_tex_path, typ='string')
            # 透過テクスチャのMipmap境界白滲みを防止
            if texture_has_alpha_map.get(tex_idx, False):
                try:
                    mc.setAttr(f"{file_node}.filterType", 0) # Off
                except Exception:
                    pass
            place2d_node = mc.shadingNode('place2dTexture', asUtility=True, name=f"{safe_tex_id}_place2d_{model_node_name}")
            for src_attr, dst_attr in PLACE2D_ATTR_CONNECTIONS:
                try:
                    mc.connectAttr(f"{place2d_node}.{src_attr}", f"{file_node}.{dst_attr}", force=True)
                except Exception:
                    pass
        else:
            texture_has_alpha_map[tex_idx] = False
            file_node = file_node_name

        texture_file_nodes.append(file_node)

    # Toonシェーディング用受光輝度（法線×ライト）ネットワークの生成
    toon_range_node = None
    if enable_toon:
        toon_sampler = mc.shadingNode('samplerInfo', asUtility=True, name=f"toon_sampler_{model_node_name}")
        # カメラ空間法線をワールド空間法線に変換 (視点回転に左右されないMMD互換の不変法線)
        toon_world_norm = mc.shadingNode('vectorProduct', asUtility=True, name=f"toon_wnorm_{model_node_name}")
        mc.setAttr(f"{toon_world_norm}.operation", 3) # Vector Matrix Product (V * M)
        mc.setAttr(f"{toon_world_norm}.normalizeOutput", True)
        mc.connectAttr(f"{toon_sampler}.normalCamera", f"{toon_world_norm}.input1", force=True)
        mc.connectAttr(f"{toon_sampler}.matrixEyeToWorld", f"{toon_world_norm}.matrix", force=True)

        # ワールド法線とワールドライトベクトルの内積計算
        toon_vec_prod = mc.shadingNode('vectorProduct', asUtility=True, name=f"toon_vecprod_{model_node_name}")
        toon_range_node = mc.shadingNode('setRange', asUtility=True, name=f"toon_range_{model_node_name}")

        mc.setAttr(f"{toon_vec_prod}.operation", 1) # Dot Product (内積)
        mc.setAttr(f"{toon_vec_prod}.normalizeOutput", True)
        # MMD標準のワールド光線到来方向（斜め前方左上: 光源位置 (-0.5, 1.0, 0.5) を正規化）
        mc.setAttr(f"{toon_vec_prod}.input2", -0.4082, 0.8165, 0.4082, typ='double3')

        mc.connectAttr(f"{toon_world_norm}.output", f"{toon_vec_prod}.input1", force=True)

        # 内積結果 (-1.0 ~ 1.0) を 0.0 ~ 1.0 に正規化 (MMD公式仕様: Toon画像本来の滑らかな階調にマッピング)
        mc.setAttr(f"{toon_range_node}.minX", 0.0)
        mc.setAttr(f"{toon_range_node}.maxX", 1.0)
        mc.setAttr(f"{toon_range_node}.oldMinX", -1.0)
        mc.setAttr(f"{toon_range_node}.oldMaxX", 1.0)
        mc.connectAttr(f"{toon_vec_prod}.outputX", f"{toon_range_node}.valueX", force=True)

    # 共有トゥーンテクスチャ (toon01.bmp〜toon10.bmp) ファイルノードの生成
    shared_toon_file_nodes = {}
    if enable_toon:
        for i in range(10):
            t_path = _get_shared_toon_path(i)
            if t_path and os.path.isfile(t_path):
                t_node_name = f"toon{i+1:02d}_file_{model_node_name}"
                f_node = mc.shadingNode('file', asTexture=True, name=t_node_name)
                mc.setAttr(f"{f_node}.ftn", t_path, typ='string')
                # ポリゴンUVではなく、受光輝度（法線×ライト内積）をV座標に接続
                if toon_range_node:
                    try:
                        mc.setAttr(f"{f_node}.uCoord", 0.5)
                        mc.connectAttr(f"{toon_range_node}.outValueX", f"{f_node}.vCoord", force=True)
                    except Exception:
                        pass
                shared_toon_file_nodes[i] = f_node

    # スフィアマップ用 MatCap UV 変換ノード (カメラ空間法線 -> UV)
    matcap_range_node = None
    has_sphere = any(getattr(m, 'sphere_texture', -1) >= 0 and getattr(m, 'sphere_texture_mode', 0) in [1, 2] for m in pmx_model.materials)
    if has_sphere:
        sampler_node = mc.shadingNode('samplerInfo', asUtility=True, name=f"matcap_sampler_{model_node_name}")
        matcap_range_node = mc.shadingNode('setRange', asUtility=True, name=f"matcap_range_{model_node_name}")
        mc.setAttr(f"{matcap_range_node}.minX", 0.0)
        mc.setAttr(f"{matcap_range_node}.minY", 0.0)
        mc.setAttr(f"{matcap_range_node}.maxX", 1.0)
        mc.setAttr(f"{matcap_range_node}.maxY", 1.0)
        mc.setAttr(f"{matcap_range_node}.oldMinX", -1.0)
        mc.setAttr(f"{matcap_range_node}.oldMinY", -1.0)
        mc.setAttr(f"{matcap_range_node}.oldMaxX", 1.0)
        mc.setAttr(f"{matcap_range_node}.oldMaxY", 1.0)
        mc.connectAttr(f"{sampler_node}.normalCameraX", f"{matcap_range_node}.valueX", force=True)
        mc.connectAttr(f"{sampler_node}.normalCameraY", f"{matcap_range_node}.valueY", force=True)

    # MMDマテリアルプラグイン選択時は事前にプラグインロードを保証
    if material_type == 5:
        try:
            try:
                from ..mmd_material_plugin.scripts.mmd_material_setup import ensure_plugin_loaded
            except Exception:
                from mmd_material_plugin.scripts.mmd_material_setup import ensure_plugin_loaded
            if not ensure_plugin_loaded():
                print("[MMD Tools] MMDマテリアルプラグインをロードできなかったため、StandardSurfaceにフォールバックします。")
                material_type = 4
        except Exception as e:
            print(f"[MMD Tools] プラグインロード確認中にエラーが発生したためフォールバックします: {e}")
            material_type = 4

    material_shader_dict = {}
    material_alpha_mult_dict = {}

    face_offset = 0
    for mat_idx, mat in enumerate(pmx_model.materials):
        if mat.vertex_count == 0:
            continue

        num_faces_in_mat = int(mat.vertex_count / 3)
        safe_mat_id = safe_node_name(mat.name, name_e=getattr(mat, 'name_e', None), prefix="mat", index=mat_idx)
        shader_node_name = f"{safe_mat_id}_shd_{model_node_name}"

        tex_idx = mat.texture
        diffuse_color = mat.diffuse[:3]
        # 白飛び防止: アンビエント過大値（1.0等）の適正化
        # MMD標準の受光特性に合わせ、アンビエント色の上限を0.60に安全クランプ
        ambient_color = [min(c, 0.60) for c in mat.ambient]
        specular_color = mat.specular[:3]
        spec_factor = mat.specular[3] if len(mat.specular) > 3 else getattr(mat, 'specular_factor', 5.0)
        alpha = mat.diffuse[3]

        # 透過マテリアルの総合判定（ディフューズアルファ、材質名の透過キーワード、テクスチャ画像の透過情報）
        trans_keywords = ["透", "半透明", "transparent", "trans", "clear", "tear", "涙", "shadow", "影"]
        mat_name_for_kw = (mat.name or "").lower()
        mat_e_for_kw = (getattr(mat, 'name_e', '') or "").lower()
        has_trans_keyword = any(kw in mat_name_for_kw or kw in mat_e_for_kw for kw in trans_keywords)
        tex_has_alpha = texture_has_alpha_map.get(tex_idx, False)

        is_transparent = (alpha < 0.98) or has_trans_keyword or tex_has_alpha

        if alpha < 0.98:
            opacity = [alpha, alpha, alpha]
            transparency = [1.0 - alpha, 1.0 - alpha, 1.0 - alpha]
        else:
            opacity = [1.0, 1.0, 1.0] # 不透明
            transparency = [0.0, 0.0, 0.0] # 不透明

        # 初期透明モーフ材質（頬染め・涙等）の判定
        is_transparent_morph_mat = (alpha <= 0.05)
        if is_transparent_morph_mat:
            # 透明ポリゴンの受光漏れ・白線・白浮き防止のためディフューズ・アンビエント・スペキュラを遮断
            diffuse_color = [0.0, 0.0, 0.0]
            ambient_color = [0.0, 0.0, 0.0]
            specular_color = [0.0, 0.0, 0.0]
            spec_factor = 0.0
            transparency = [1.0, 1.0, 1.0]
            opacity = [0.0, 0.0, 0.0]

        # アニメモデルの顔・肌・表情保護判定 (ユーザー辞書連動)
        try:
            try:
                from ..asset.user_dict_manager import is_face_or_skin_material, is_toon_bypass_material
            except Exception:
                from asset.user_dict_manager import is_face_or_skin_material, is_toon_bypass_material
            is_face_material = is_face_or_skin_material(mat.name, getattr(mat, 'name_e', ''))
        except Exception:
            face_skin_keywords = [
                "顔", "head", "face", "目", "eye", "瞳", "眉", "brow", "口", "mouth",
                "舌", "牙", "歯", "teeth", "tooth", "唇", "lip", "表情", "涙", "頬",
                "cheek", "肌", "skin", "body", "体", "面", "nose", "鼻"
            ]
            is_face_material = any(k in mat_name_lower or k in mat_e_lower for k in face_skin_keywords)

        # エッジ描画フラグの取得と初期透明モーフ材質の無効化
        is_edge_enabled = bool(getattr(mat, 'draw_flags', 0x10) & 0x10) if hasattr(mat, 'draw_flags') else (getattr(mat, 'edge_flag', 1) != 0)
        edge_size_val = float(getattr(mat, 'edge_size', 1.0))
        edge_col_val = getattr(mat, 'edge_color', [0.0, 0.0, 0.0, 1.0])
        if is_transparent_morph_mat:
            is_edge_enabled = False
            edge_size_val = 0.0
            edge_col_val = [0.0, 0.0, 0.0, 0.0]

        # シェーダーの生成
        if material_type == 1: # Blinn
            shd = mc.shadingNode('blinn', asShader=True, name=shader_node_name)
            if is_face_material or is_transparent_morph_mat or sum(specular_color) < 0.05:
                mc.setAttr(f"{shd}.specularColor", 0.0, 0.0, 0.0, typ='double3')
            else:
                mc.setAttr(f"{shd}.specularColor", *specular_color, typ='double3')
                mc.setAttr(f"{shd}.specularRollOff", min(0.75 ** (math.log(max(spec_factor, 2 ** -10), 2) + 1), 1.0))
                mc.setAttr(f"{shd}.eccentricity", spec_factor * 0.01)
        elif material_type == 2: # Phong
            shd = mc.shadingNode('phong', asShader=True, name=shader_node_name)
            if is_face_material or is_transparent_morph_mat or sum(specular_color) < 0.05:
                mc.setAttr(f"{shd}.specularColor", 0.0, 0.0, 0.0, typ='double3')
            else:
                mc.setAttr(f"{shd}.specularColor", *specular_color, typ='double3')
                mc.setAttr(f"{shd}.cosinePower", max((10000.0 / max(spec_factor, 15.0) ** 2 - 3.357) / 0.454, 2.0))
        elif material_type == 3 or material_type == 0: # Lambert
            shd = mc.shadingNode('lambert', asShader=True, name=shader_node_name)
        elif material_type == 4: # StandardSurface (Maya 2022+)
            shd = mc.shadingNode('standardSurface', asShader=True, name=shader_node_name)
            mc.setAttr(f"{shd}.baseColor", *diffuse_color, typ='double3')
            mc.setAttr(f"{shd}.opacity", *opacity, typ='double3')
            has_specular = sum(specular_color) > 0.05 and not is_face_material and not is_transparent_morph_mat
            if has_specular:
                mc.setAttr(f"{shd}.specularColor", *specular_color, typ='double3')
                mc.setAttr(f"{shd}.specular", 0.75 ** (math.log(max(spec_factor, 0.5), 2) + 1))
                mc.setAttr(f"{shd}.specularRoughness", min(spec_factor * 0.01, 1.0))
            else:
                mc.setAttr(f"{shd}.specularColor", 0.0, 0.0, 0.0, typ='double3')
                mc.setAttr(f"{shd}.specular", 0.0)
                mc.setAttr(f"{shd}.specularRoughness", 1.0)
            if is_transparent_morph_mat:
                mc.setAttr(f"{shd}.base", 0.0)
            else:
                mc.setAttr(f"{shd}.base", 0.95)
        elif material_type == 5: # sample_mmd_mat (ベータ版: MMDオリジナルマテリアルプラグイン)
            try:
                shd = mc.shadingNode('mmdMaterial', asShader=True, name=shader_node_name)
            except Exception:
                shd = mc.shadingNode('standardSurface', asShader=True, name=shader_node_name)

            if mc.attributeQuery('diffuseColor', node=shd, exists=True):
                mc.setAttr(f"{shd}.diffuseColor", *diffuse_color, typ='double3')
                mc.setAttr(f"{shd}.color", *diffuse_color, typ='double3')
                mc.setAttr(f"{shd}.ambientColor", *ambient_color, typ='double3')
                mc.setAttr(f"{shd}.transparency", *transparency, typ='double3')
                mc.setAttr(f"{shd}.diffuseAlpha", alpha)
                mc.setAttr(f"{shd}.specularColor", *specular_color, typ='double3')
                mc.setAttr(f"{shd}.specularPower", min(100.0, max(1.0, float(spec_factor))))
                mc.setAttr(f"{shd}.cosinePower", min(100.0, max(2.0, float(spec_factor))))
                mc.setAttr(f"{shd}.diffuse", 0.0 if is_transparent_morph_mat else 1.0)

                sph_idx = getattr(mat, 'sphere_texture', -1)
                sph_mode = getattr(mat, 'sphere_texture_mode', 0)
                mc.setAttr(f"{shd}.sphereMode", int(sph_mode))
                mc.setAttr(f"{shd}.toonMode", 1 if enable_toon else 0)

                mc.setAttr(f"{shd}.edgeEnable", is_edge_enabled)
                if len(edge_col_val) >= 3:
                    mc.setAttr(f"{shd}.edgeColor", edge_col_val[0], edge_col_val[1], edge_col_val[2], typ='double3')
                mc.setAttr(f"{shd}.edgeSize", edge_size_val)
            else:
                # 万が一 mmdMaterial 属性が存在しない場合の安全フォールバック
                if mc.attributeQuery('baseColor', node=shd, exists=True):
                    mc.setAttr(f"{shd}.baseColor", *diffuse_color, typ='double3')
                elif mc.attributeQuery('color', node=shd, exists=True):
                    mc.setAttr(f"{shd}.color", *diffuse_color, typ='double3')


        material_shader_dict[mat_idx] = shd

        if material_type in [1, 2, 3]:
            mc.setAttr(f"{shd}.color", *diffuse_color, typ='double3')
            mc.setAttr(f"{shd}.ambientColor", *ambient_color, typ='double3')
            mc.setAttr(f"{shd}.transparency", *transparency, typ='double3')
            if is_transparent_morph_mat:
                if mc.attributeQuery('diffuse', node=shd, exists=True):
                    mc.setAttr(f"{shd}.diffuse", 0.0)
                if mc.attributeQuery('shadowAttenuation', node=shd, exists=True):
                    mc.setAttr(f"{shd}.shadowAttenuation", 0.0)

        # 日本語・中国語の元名称を保持
        mc.addAttr(shd, longName='originalName', niceName='元の名称', dataType='string')
        mc.setAttr(f"{shd}.originalName", mat.name, typ='string')

        # カラー出力ソースの初期化
        current_color_source = None
        if 0 <= tex_idx < len(texture_file_nodes) and mc.objExists(texture_file_nodes[tex_idx]):
            current_color_source = f"{texture_file_nodes[tex_idx]}.outColor"

        # スフィアマップの解決と MatCap UV 接続
        sphere_idx = getattr(mat, 'sphere_texture', -1)
        sphere_mode = getattr(mat, 'sphere_texture_mode', 0)
        sphere_node = None
        if 0 <= sphere_idx < len(texture_file_nodes) and sphere_mode in [1, 2]:
            candidate_sph = texture_file_nodes[sphere_idx]
            if mc.objExists(candidate_sph):
                sphere_node = candidate_sph
                if matcap_range_node:
                    try:
                        mc.connectAttr(f"{matcap_range_node}.outValueX", f"{sphere_node}.uCoord", force=True)
                        mc.connectAttr(f"{matcap_range_node}.outValueY", f"{sphere_node}.vCoord", force=True)
                    except Exception:
                        pass

        # 乗算スフィア (モード 1: .sph) のカラー合成
        if sphere_node and sphere_mode == 1:
            mult_node = mc.shadingNode('multiplyDivide', asUtility=True, name=f"{safe_mat_id}_sph_mult_{model_node_name}")
            mc.setAttr(f"{mult_node}.operation", 1) # Multiply
            if current_color_source:
                mc.connectAttr(current_color_source, f"{mult_node}.input1", force=True)
            else:
                mc.setAttr(f"{mult_node}.input1", *diffuse_color, typ='double3')
            mc.connectAttr(f"{sphere_node}.outColor", f"{mult_node}.input2", force=True)
            current_color_source = f"{mult_node}.output"

        # Toonマップ (セル調陰影グラデーション) の解決とカラー乗算合成
        toon_node = None
        if enable_toon:
            toon_idx = getattr(mat, 'toon_texture', -1)
            is_shared_toon = getattr(mat, 'is_shared_toon_texture', False)
            if is_shared_toon:
                if toon_idx in shared_toon_file_nodes:
                    toon_node = shared_toon_file_nodes[toon_idx]
                elif (toon_idx - 1) in shared_toon_file_nodes:
                    toon_node = shared_toon_file_nodes[toon_idx - 1]
            elif not is_shared_toon and 0 <= toon_idx < len(pmx_model.textures):
                raw_name = os.path.basename(pmx_model.textures[toon_idx].path).lower()
                matched_shared = False
                for si in range(10):
                    if f"toon{si+1:02d}" in raw_name or f"toon{si+1}." in raw_name:
                        toon_node = shared_toon_file_nodes.get(si)
                        matched_shared = True
                        break
                if not matched_shared:
                    custom_toon_path = pmx_model.textures[toon_idx].path.replace('\\', '/')
                    if not os.path.isabs(custom_toon_path):
                        custom_toon_path = os.path.normpath(os.path.join(model_dir, custom_toon_path)).replace('\\', '/')
                    if os.path.isfile(custom_toon_path):
                        ct_name = f"{safe_mat_id}_custoon_file_{model_node_name}"
                        toon_node = mc.shadingNode('file', asTexture=True, name=ct_name)
                        mc.setAttr(f"{toon_node}.ftn", custom_toon_path, typ='string')
                        if toon_range_node:
                            try:
                                mc.setAttr(f"{toon_node}.uCoord", 0.5)
                                mc.connectAttr(f"{toon_range_node}.outValueX", f"{toon_node}.vCoord", force=True)
                            except Exception:
                                pass

        # 全マテリアル種別（StandardSurface含む）に対してToonをカラー乗算合成 (瞳ハイライト等のみ除外・ユーザー辞書連動)
        try:
            try:
                from ..asset.user_dict_manager import is_toon_bypass_material
            except Exception:
                from asset.user_dict_manager import is_toon_bypass_material
            is_highlight_part = is_toon_bypass_material(mat.name, getattr(mat, 'name_e', ''))
        except Exception:
            is_highlight_part = any(k in mat.name.lower() for k in ["瞳-高光", "高光", "眼白", "highlight"])
        if enable_toon and toon_node and not is_highlight_part:
            toon_mult = mc.shadingNode('multiplyDivide', asUtility=True, name=f"{safe_mat_id}_toon_mult_{model_node_name}")
            mc.setAttr(f"{toon_mult}.operation", 1) # Multiply
            if current_color_source:
                mc.connectAttr(current_color_source, f"{toon_mult}.input1", force=True)
            else:
                mc.setAttr(f"{toon_mult}.input1", *diffuse_color, typ='double3')
            mc.connectAttr(f"{toon_node}.outColor", f"{toon_mult}.input2", force=True)
            current_color_source = f"{toon_mult}.output"

            # Toonテクスチャはディフューズカラーに乗算合成済みのため、
            # 白飛び防止のためambientColorへの直接接続は行わない

        # 基本カラーのシェーダー接続 (メインテクスチャ × スフィア × Toon の統合出力)
        if current_color_source:
            if material_type == 4:
                mc.connectAttr(current_color_source, f"{shd}.baseColor", force=True)
            else: # Blinn, Phong, Lambert, sample_mmd_mat
                mc.connectAttr(current_color_source, f"{shd}.color", force=True)

        # 加算スフィア (モード 2: .spa) の光沢・発光接続
        if sphere_node and sphere_mode == 2:
            if material_type == 4:
                mc.connectAttr(f"{sphere_node}.outColor", f"{shd}.emissionColor", force=True)
                mc.setAttr(f"{shd}.emission", 1.0)
            else: # Blinn, Phong, Lambert, sample_mmd_mat
                mc.connectAttr(f"{sphere_node}.outColor", f"{shd}.incandescence", force=True)

        # 透過テクスチャまたは半透明材質の透過接続処理
        if 0 <= tex_idx < len(texture_file_nodes) and tex_has_alpha:
            tex_file_node = texture_file_nodes[tex_idx]
            if mc.objExists(tex_file_node):
                try:
                    if alpha < 0.98:
                        # 材質ディフューズアルファとテクスチャアルファの乗算ブレンド
                        mult_node = mc.shadingNode('multDoubleLinear', asUtility=True, name=f"{safe_mat_id}_alpha_mult_{model_node_name}")
                        material_alpha_mult_dict[mat_idx] = mult_node
                        mc.connectAttr(f"{tex_file_node}.outAlpha", f"{mult_node}.input1", force=True)
                        mc.setAttr(f"{mult_node}.input2", float(alpha))
                        if material_type == 4:
                            mc.connectAttr(f"{mult_node}.output", f"{shd}.opacityR", force=True)
                            mc.connectAttr(f"{mult_node}.output", f"{shd}.opacityG", force=True)
                            mc.connectAttr(f"{mult_node}.output", f"{shd}.opacityB", force=True)
                        else:
                            rev_node = mc.shadingNode('reverse', asUtility=True, name=f"{safe_mat_id}_alpha_rev_{model_node_name}")
                            mc.connectAttr(f"{mult_node}.output", f"{rev_node}.inputX", force=True)
                            mc.connectAttr(f"{mult_node}.output", f"{rev_node}.inputY", force=True)
                            mc.connectAttr(f"{mult_node}.output", f"{rev_node}.inputZ", force=True)
                            mc.connectAttr(f"{rev_node}.output", f"{shd}.transparency", force=True)
                    else:
                        # 不透明材質アルファ時はテクスチャアルファをそのまま接続
                        if material_type == 4:
                            mc.connectAttr(f"{tex_file_node}.outAlpha", f"{shd}.opacityR", force=True)
                            mc.connectAttr(f"{tex_file_node}.outAlpha", f"{shd}.opacityG", force=True)
                            mc.connectAttr(f"{tex_file_node}.outAlpha", f"{shd}.opacityB", force=True)
                        else:
                            mc.connectAttr(f"{tex_file_node}.outTransparency", f"{shd}.transparency", force=True)
                except Exception:
                    pass
        elif is_transparent and 0 <= tex_idx < len(texture_file_nodes):
            # テクスチャアルファが無い場合でも透過指定材質なら透過接続を試行
            tex_file_node = texture_file_nodes[tex_idx]
            if mc.objExists(tex_file_node):
                tex_obj = pmx_model.textures[tex_idx]
                tex_path_lower = tex_obj.path.lower()
                if any(tex_path_lower.endswith(ext) for ext in ['.png', '.tga', '.dds', '.bmp']):
                    try:
                        if material_type == 4:
                            mc.connectAttr(f"{tex_file_node}.outAlpha", f"{shd}.opacityR", force=True)
                            mc.connectAttr(f"{tex_file_node}.outAlpha", f"{shd}.opacityG", force=True)
                            mc.connectAttr(f"{tex_file_node}.outAlpha", f"{shd}.opacityB", force=True)
                        else:
                            mc.connectAttr(f"{tex_file_node}.outTransparency", f"{shd}.transparency", force=True)
                    except Exception:
                        pass

        # シェーディンググループ (SG) の作成と割り当て
        sg_node = mc.sets(renderable=True, noSurfaceShader=True, empty=True, name=f"{shd}SG")
        mc.connectAttr(f"{shd}.outColor", f"{sg_node}.surfaceShader", force=True)

        if split_by_material:
            # 材質ごとのポリゴン分割処理
            mat_face_indices = []
            mat_face_counts = []
            vert_remap = {}
            vert_counter = 0

            for face in pmx_model.faces[face_offset:face_offset + num_faces_in_mat]:
                unique_f = list(dict.fromkeys(face))
                if len(unique_f) >= 3:
                    for v_idx in unique_f:
                        if v_idx not in vert_remap:
                            vert_remap[v_idx] = vert_counter
                            vert_counter += 1
                        mat_face_indices.append(vert_remap[v_idx])
                    mat_face_counts.append(len(unique_f))

            mat_vtx_coords = []
            mat_vtx_u = []
            mat_vtx_v = []
            mat_vtx_normals = []
            mat_vtx_edge_scales = []
            mat_alpha = mat.diffuse[3]
            mat_edge_on = bool(getattr(mat, 'draw_flags', 0x10) & 0x10) if hasattr(mat, 'draw_flags') else (getattr(mat, 'edge_flag', 1) != 0)
            if mat_alpha <= 0.05:
                mat_edge_on = False

            for orig_idx in vert_remap:
                v = pmx_model.vertices[orig_idx]
                mat_vtx_coords.append(om.MFloatPoint(v.co[0] * scale, v.co[1] * scale, -v.co[2] * scale))
                mat_vtx_u.append(v.uv[0])
                mat_vtx_v.append(1.0 - v.uv[1])
                e_s = getattr(v, 'edge_scale', 1.0) if mat_edge_on else 0.0
                mat_vtx_edge_scales.append(e_s)
                if v.normal:
                    mat_vtx_normals.append(om.MFloatVector(v.normal[0], v.normal[1], -v.normal[2]))

            sub_mesh_name = create_mesh(
                f"{model_node_name}_{mat_idx + 1}_{safe_mat_id}",
                mat_vtx_coords, mat_face_indices, mat_face_counts, mat_vtx_u, mat_vtx_v, mat_vtx_normals,
                edge_scales=mat_vtx_edge_scales
            )
            mc.sets(f"{sub_mesh_name}.f[0:{len(mat_face_counts) - 1}]", forceElement=sg_node)
            if is_transparent_morph_mat:
                try:
                    mc.setAttr(f"{sub_mesh_name}.castsShadows", 0)
                    mc.setAttr(f"{sub_mesh_name}.receiveShadows", 0)
                except Exception:
                    pass
            material_mesh_nodes.append(sub_mesh_name)
        else:
            face_start = sum(valid_face_flags[:face_offset])
            face_end = sum(valid_face_flags[:face_offset + num_faces_in_mat])
            if face_end > face_start:
                mc.sets(f"{model_mesh_node}.f[{face_start}:{face_end - 1}]", forceElement=sg_node)

        face_offset += num_faces_in_mat

    if split_by_material:
        model_mesh_node = mc.group(material_mesh_nodes, name=model_node_name)

    # 4. ブレンドシェイプ（モーフ）の作成
    morph_structure_map = {}
    if create_blendshapes and not split_by_material:
        print("[4/6] ブレンドシェイプ（モーフ）を作成中...")
        vertex_morphs = [m for m in pmx_model.morphs if m.type_index() == 1]
        if vertex_morphs:
            bs_mesh_nodes = []
            for m_idx, morph in enumerate(vertex_morphs):
                morph_name_e = getattr(morph, 'name_e', None)
                safe_morph_name = safe_node_name(morph.name, name_e=morph_name_e, prefix="morph", index=m_idx)
                target_attr_name = f"temp_bs_{m_idx:03d}_{safe_morph_name}"
                
                # メッシュの複製
                try:
                    dup_node = mc.duplicate(model_mesh_node, name=target_attr_name)[0]
                    sel = om.MSelectionList()
                    sel.add(dup_node)
                    dag_path = sel.getDagPath(0)
                    fn_mesh = om.MFnMesh(dag_path)
                    points = fn_mesh.getPoints()
                    num_pts = len(points)

                    for offset in morph.offsets:
                        vi = offset.index
                        if vi < num_pts:
                            off = offset.offset
                            p = points[vi]
                            points[vi] = om.MPoint(p[0] + off[0] * scale, p[1] + off[1] * scale, p[2] - off[2] * scale)

                    fn_mesh.setPoints(points)
                    bs_mesh_nodes.append(dup_node)
                    # BlendShapeターゲットとして登録される一意な識別名を記録
                    morph_structure_map[morph.name] = dup_node
                except Exception as e:
                    print(f"  [警告] モーフ '{morph.name}' の作成をスキップしました: {e}")

            if bs_mesh_nodes:
                mc.select(bs_mesh_nodes + [model_mesh_node])
                blendshape_node_name = mc.blendShape(name=f"bs_{model_mesh_node}")[0]
                mc.delete(bs_mesh_nodes) # 作業用複製メッシュを削除

                # 日本語モーフ名へのエイリアス設定
                for idx, m_name in enumerate(morph_structure_map.keys()):
                    try:
                        clean_alias = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', '_', m_name)
                        mc.aliasAttr(clean_alias, f"{blendshape_node_name}.w[{idx}]")
                    except Exception:
                        pass
                print(f"  - {len(bs_mesh_nodes)} 個の頂点モーフを登録しました")

    # 材質モーフ（Material Morph）の作成とシェーダー連携
    if create_blendshapes:
        material_morphs = [m for m in pmx_model.morphs if getattr(m, 'morph_type', 0) == 8 or (hasattr(m, 'type_index') and m.type_index() == 8)]
        if material_morphs:
            print(f"  - 材質モーフ ({len(material_morphs)} 個) を構築中...")
            for m_idx, morph in enumerate(material_morphs):
                morph_name_e = getattr(morph, 'name_e', None)
                safe_morph_name = safe_node_name(morph.name, name_e=morph_name_e, prefix="matmorph", index=m_idx)
                attr_name = f"matmorph_{safe_morph_name}"
                if mc.attributeQuery(attr_name, node=model_mesh_node, exists=True):
                    attr_name = f"matmorph_{m_idx:02d}_{safe_morph_name}"

                try:
                    mc.addAttr(model_mesh_node, longName=attr_name, niceName=morph.name, attributeType='double', min=0.0, max=1.0, defaultValue=0.0, keyable=True)
                    morph_structure_map[morph.name] = attr_name
                    if morph_name_e:
                        morph_structure_map[morph_name_e] = attr_name

                    # オフセット情報に基づき対象シェーダーへ接続
                    for off in getattr(morph, 'offsets', []):
                        target_mat_idx = off[0]
                        calc_op = off[1]
                        diff_data = off[2] if len(off) > 2 else [0.0, 0.0, 0.0, 0.0]
                        diff_rgb = diff_data[:3]
                        diff_a = diff_data[3] if len(diff_data) > 3 else 0.0
                        edge_data = off[5] if len(off) > 5 else [0.0, 0.0, 0.0, 0.0]
                        edge_a = edge_data[3] if len(edge_data) > 3 else 0.0

                        target_indices = [target_mat_idx] if target_mat_idx >= 0 else list(material_shader_dict.keys())
                        for ti in target_indices:
                            target_shd = material_shader_dict.get(ti)
                            if not target_shd or not mc.objExists(target_shd):
                                continue

                            # アルファ制御（表示および非表示）
                            if diff_a > 0.05:
                                # 透過から表示へのモーフ（頬染め、ガーン、肌3、下着2等）
                                alpha_mult = material_alpha_mult_dict.get(ti)
                                if alpha_mult and mc.objExists(alpha_mult):
                                    try:
                                        mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{alpha_mult}.input2", force=True)
                                    except Exception:
                                        pass
                                else:
                                    try:
                                        rev_n = mc.shadingNode('reverse', asUtility=True, name=f"{safe_morph_name}_{ti}_rev")
                                        mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{rev_n}.inputX", force=True)
                                        if material_type in [1, 2, 3]:
                                            mc.connectAttr(f"{rev_n}.outputX", f"{target_shd}.transparencyR", force=True)
                                            mc.connectAttr(f"{rev_n}.outputX", f"{target_shd}.transparencyG", force=True)
                                            mc.connectAttr(f"{rev_n}.outputX", f"{target_shd}.transparencyB", force=True)
                                        elif material_type == 4:
                                            mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{target_shd}.opacityR", force=True)
                                            mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{target_shd}.opacityG", force=True)
                                            mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{target_shd}.opacityB", force=True)
                                    except Exception:
                                        pass

                                # 受光強度の連動（モーフ値に応じて拡散受光を滑らかに有効化）
                                try:
                                    diff_gain = mc.shadingNode('multDoubleLinear', asUtility=True, name=f"{safe_morph_name}_{ti}_diff_gain")
                                    mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{diff_gain}.input1", force=True)
                                    mc.setAttr(f"{diff_gain}.input2", 0.8)
                                    if material_type in [1, 2, 3]:
                                        mc.connectAttr(f"{diff_gain}.output", f"{target_shd}.diffuse", force=True)
                                    elif material_type == 4:
                                        mc.connectAttr(f"{diff_gain}.output", f"{target_shd}.base", force=True)
                                except Exception:
                                    pass

                                # エッジ出現の連動
                                if edge_a > 0.05 and mc.attributeQuery("edgeSize", node=target_shd, exists=True):
                                    try:
                                        edge_appear = mc.shadingNode('multDoubleLinear', asUtility=True, name=f"{safe_morph_name}_{ti}_edge_appear")
                                        mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{edge_appear}.input1", force=True)
                                        mc.setAttr(f"{edge_appear}.input2", 1.0)
                                        mc.connectAttr(f"{edge_appear}.output", f"{target_shd}.edgeSize", force=True)
                                    except Exception:
                                        pass

                            elif diff_a < -0.05:
                                # 表示から非表示へのモーフ（帽子off、靴下off、ドロワoff等）
                                try:
                                    if material_type in [1, 2, 3]:
                                        mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{target_shd}.transparencyR", force=True)
                                        mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{target_shd}.transparencyG", force=True)
                                        mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{target_shd}.transparencyB", force=True)
                                    elif material_type == 4:
                                        rev_n = mc.shadingNode('reverse', asUtility=True, name=f"{safe_morph_name}_{ti}_off_rev")
                                        mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{rev_n}.inputX", force=True)
                                        mc.connectAttr(f"{rev_n}.outputX", f"{target_shd}.opacityR", force=True)
                                        mc.connectAttr(f"{rev_n}.outputX", f"{target_shd}.opacityG", force=True)
                                        mc.connectAttr(f"{rev_n}.outputX", f"{target_shd}.opacityB", force=True)
                                    elif material_type == 5:
                                        mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{target_shd}.transparencyR", force=True)
                                        mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{target_shd}.transparencyG", force=True)
                                        mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{target_shd}.transparencyB", force=True)
                                except Exception:
                                    pass

                                # 非表示化に伴う拡散受光の減衰（服が消えた際の受光・影の残存を遮断）
                                try:
                                    fade_rev = mc.shadingNode('reverse', asUtility=True, name=f"{safe_morph_name}_{ti}_diff_fade_rev")
                                    mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{fade_rev}.inputX", force=True)
                                    diff_fade = mc.shadingNode('multDoubleLinear', asUtility=True, name=f"{safe_morph_name}_{ti}_diff_fade")
                                    mc.connectAttr(f"{fade_rev}.outputX", f"{diff_fade}.input1", force=True)
                                    mc.setAttr(f"{diff_fade}.input2", 0.8)
                                    if material_type in [1, 2, 3]:
                                        mc.connectAttr(f"{diff_fade}.output", f"{target_shd}.diffuse", force=True)
                                    elif material_type == 4:
                                        mc.connectAttr(f"{diff_fade}.output", f"{target_shd}.base", force=True)
                                except Exception:
                                    pass

                                # エッジ消去の連動（輪郭線の残存を防止）
                                if edge_a < -0.05 and mc.attributeQuery("edgeSize", node=target_shd, exists=True):
                                    try:
                                        edge_fade_rev = mc.shadingNode('reverse', asUtility=True, name=f"{safe_morph_name}_{ti}_edge_fade_rev")
                                        mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{edge_fade_rev}.inputX", force=True)
                                        edge_fade = mc.shadingNode('multDoubleLinear', asUtility=True, name=f"{safe_morph_name}_{ti}_edge_fade")
                                        mc.connectAttr(f"{edge_fade_rev}.outputX", f"{edge_fade}.input1", force=True)
                                        cur_edge_sz = float(mc.getAttr(f"{target_shd}.edgeSize") or 1.0)
                                        mc.setAttr(f"{edge_fade}.input2", cur_edge_sz)
                                        mc.connectAttr(f"{edge_fade}.output", f"{target_shd}.edgeSize", force=True)
                                    except Exception:
                                        pass

                            # カラー変化（ダークアイ、ガーン赤、ガーン青等）
                            if any(abs(c) > 0.05 for c in diff_rgb):
                                try:
                                    blend_c = mc.shadingNode('blendColors', asUtility=True, name=f"{safe_morph_name}_{ti}_color_blend")
                                    color_target_attr = f"{target_shd}.color" if material_type in [1, 2, 3] else f"{target_shd}.baseColor"
                                    cur_col = mc.getAttr(color_target_attr)[0] if (mc.attributeQuery("color", node=target_shd, exists=True) or mc.attributeQuery("baseColor", node=target_shd, exists=True)) else [1.0, 1.0, 1.0]
                                    if calc_op == 1:
                                        target_col = [max(0.0, min(1.0, cur_col[i] + diff_rgb[i])) for i in range(3)]
                                    else:
                                        target_col = [max(0.0, min(1.0, cur_col[i] * diff_rgb[i])) for i in range(3)]
                                    mc.setAttr(f"{blend_c}.color1", *target_col, typ='double3')
                                    mc.setAttr(f"{blend_c}.color2", *cur_col, typ='double3')
                                    mc.connectAttr(f"{model_mesh_node}.{attr_name}", f"{blend_c}.blender", force=True)
                                    mc.connectAttr(f"{blend_c}.output", color_target_attr, force=True)
                                except Exception:
                                    pass
                except Exception as e:
                    print(f"  [警告] 材質モーフ '{morph.name}' の作成中にエラー: {e}")

    # 5. ジョイント（ボーンスケルトン）の作成
    if create_joints and not split_by_material:
        print("[5/6] ジョイント（ボーン）を作成中...")
        joint_node_names = []
        name_tracker = set()

        for b_idx, bone in enumerate(pmx_model.bones):
            mc.select(clear=True)
            bone_name_e = getattr(bone, 'name_e', None)
            safe_bone_id = safe_node_name(bone.name, name_e=bone_name_e, prefix="bone", index=b_idx)
            
            # 名前の重複防止
            unique_bone_name = f"{model_mesh_node}_{safe_bone_id}"
            if unique_bone_name in name_tracker:
                unique_bone_name = f"{unique_bone_name}_{b_idx}"
            name_tracker.add(unique_bone_name)

            loc = bone.location
            # 指ボーンや主要ボーンの半径調整
            if 'yubi' in safe_bone_id or 'finger' in safe_bone_id.lower():
                radius = scale / 4.0
            elif 'center' in safe_bone_id.lower() or 'sentaa' in safe_bone_id:
                radius = scale
            else:
                radius = scale / 2.0

            pos = [loc[0] * scale, loc[1] * scale, -loc[2] * scale]
            j_node = mc.joint(position=pos, radius=radius, name=unique_bone_name)
            mc.addAttr(j_node, longName='originalName', niceName='元の名称', dataType='string')
            mc.setAttr(f"{j_node}.originalName", bone.name, typ='string')

            if bone.isIK or not bone.visible:
                mc.setAttr(f"{j_node}.drawStyle", 2) # 非表示
            else:
                mc.setAttr(f"{j_node}.drawStyle", 0)

            # ひざボーンの場合はIKソルバー用の前方屈曲優先角度を初期設定
            bone_name_raw = getattr(bone, 'name', '') or ''
            if 'ひざ' in bone_name_raw or '膝' in bone_name_raw or 'knee' in bone_name_raw.lower():
                try:
                    mc.setAttr(f"{j_node}.preferredAngleX", 60.0)
                    mc.setAttr(f"{j_node}.preferredAngleY", 0.0)
                    mc.setAttr(f"{j_node}.preferredAngleZ", 0.0)
                except Exception:
                    pass

            # MMDボーンはモデル空間直交座標系に準拠するため、jointOrientは標準の(0,0,0)に統一
            # (表示用ローカル軸による不要な傾きを排除し、スキニングとモーションのねじれを確実に防止)
            joint_node_names.append(j_node)

        # 親子階層の結合
        for b_idx, bone in enumerate(pmx_model.bones):
            child_j = joint_node_names[b_idx]
            if bone.parent >= 0 and bone.parent < len(joint_node_names):
                parent_j = joint_node_names[bone.parent]
                mc.connectJoint(child_j, parent_j, parentMode=True)
            else:
                root_joint_names.append(child_j)

            # 付与親（追加トランスフォーム）のエクスプレッション生成
            if bone.hasAdditionalRotate:
                target_idx = bone.additionalTransform[0]
                if 0 <= target_idx < len(joint_node_names):
                    effect_j = joint_node_names[target_idx]
                    ratio = bone.additionalTransform[1]

                    # 腕捩り・手捩り系ボーンはMMD仕様に準拠し、長軸ロール(X軸)のみを分散連動
                    # 曲げ方向(Y/Z軸)を連動させると上腕メッシュが中途半端に絞り切られてキャンディ状にねじれるため除外
                    b_name = bone.name
                    is_twist_bone = any(k in b_name for k in ["腕捩", "手捩"])
                    if is_twist_bone:
                        expr = (
                            f"{child_j}.rotateX = {effect_j}.rotateX * {ratio};\n"
                            f"{child_j}.rotateY = 0.0;\n"
                            f"{child_j}.rotateZ = 0.0;\n"
                        )
                    else:
                        expr = (
                            f"{child_j}.rotateX = {effect_j}.rotateX * {ratio};\n"
                            f"{child_j}.rotateY = {effect_j}.rotateY * {ratio};\n"
                            f"{child_j}.rotateZ = {effect_j}.rotateZ * {ratio};\n"
                        )
                    mc.expression(string=expr, name=f"expr_rot_{child_j}_{effect_j}")

            if bone.hasAdditionalLocation:
                target_idx = bone.additionalTransform[0]
                if 0 <= target_idx < len(joint_node_names):
                    effect_j = joint_node_names[target_idx]
                    ratio = bone.additionalTransform[1]
                    expr = (
                        f"{child_j}.translateX = {effect_j}.translateX * {ratio};\n"
                        f"{child_j}.translateY = {effect_j}.translateY * {ratio};\n"
                        f"{child_j}.translateZ = {effect_j}.translateZ * {ratio};\n"
                    )
                    mc.expression(string=expr, name=f"expr_loc_{child_j}_{effect_j}")

        # 6. スキニングウェイト設定
        print("[6/6] スキニングウェイトを設定中...")
        sel = om.MSelectionList()
        sel.add(model_mesh_node)
        dag_path_mesh = sel.getDagPath(0)

        skin_cluster_name = f"skin_{model_mesh_node}"
        skin_cluster = mc.skinCluster(
            joint_node_names, model_mesh_node,
            maximumInfluences=4, toSelectedBones=True, name=skin_cluster_name
        )[0]
        skin_node_name = skin_cluster

        sel = om.MSelectionList()
        sel.add(skin_cluster)
        skin_mobject = sel.getDependNode(0)
        fn_skin = oma.MFnSkinCluster(skin_mobject)

        num_joints = len(pmx_model.bones)
        all_weights = []

        # 大容量モデル向けウェイト配列の安全構築
        for vtx in pmx_model.vertices:
            w = [0.0] * num_joints
            w_type = vtx.weight.type
            bones = vtx.weight.bones
            weights = vtx.weight.weights

            try:
                if w_type == mmd_core.pmx.BoneWeight.BDEF1:
                    w[bones[0]] = 1.0
                elif w_type == mmd_core.pmx.BoneWeight.BDEF2:
                    w[bones[0]] += weights[0]
                    w[bones[1]] += 1.0 - weights[0]
                elif w_type == mmd_core.pmx.BoneWeight.SDEF:
                    if hasattr(weights, 'weight'):
                        w[bones[0]] += weights.weight
                        w[bones[1]] += 1.0 - weights.weight
                    else:
                        w[bones[0]] += 0.5
                        w[bones[1]] += 0.5
                elif w_type == mmd_core.pmx.BoneWeight.BDEF4:
                    w[bones[0]] += weights[0]
                    w[bones[1]] += weights[1]
                    w[bones[2]] += weights[2]
                    w[bones[3]] += 1.0 - weights[0] - weights[1] - weights[2]
            except Exception:
                pass

            all_weights.extend(w)

        arr_vtx_indices = om.MIntArray(range(num_vertices))
        arr_weights = om.MDoubleArray(all_weights)
        arr_influences = om.MIntArray(range(num_joints))

        fn_comp = om.MFnSingleIndexedComponent()
        comp = fn_comp.create(om.MFn.kMeshVertComponent)
        fn_comp.addElements(arr_vtx_indices)

        fn_skin.setWeights(dag_path_mesh, comp, arr_influences, arr_weights, normalize=True)

        # ジョイント名からプレフィックスを削除してスッキリ整理
        final_joint_map = {}
        bone_map_jp = {}
        bone_map_en = {}
        bone_details = []

        for b_idx, j_name in enumerate(joint_node_names):
            bone_obj = pmx_model.bones[b_idx] if b_idx < len(pmx_model.bones) else None
            actual_j = j_name
            if j_name not in root_joint_names:
                try:
                    short_name = j_name.replace(f"{model_mesh_node}_", "")
                    actual_j = mc.rename(j_name, short_name)
                except Exception:
                    actual_j = j_name
            if bone_obj:
                # フルDAGパスを取得して名前重複衝突を防止
                try:
                    long_names = mc.ls(actual_j, long=True)
                    final_path = long_names[0] if long_names else actual_j
                except Exception:
                    final_path = actual_j

                name_jp = bone_obj.name
                name_en = getattr(bone_obj, 'name_e', '') or ''
                if not name_en:
                    # PMXに英語名が未定義の場合は標準MMDボーン日英辞書から自動補完
                    name_en = get_english_bone_name(name_jp)

                # 日本語名での登録
                if name_jp:
                    final_joint_map[name_jp] = final_path
                    bone_map_jp[name_jp] = final_path

                # 英語名での登録 (日英両方からノードが引けるようにする)
                if name_en:
                    final_joint_map[name_en] = final_path
                    bone_map_en[name_en] = final_path

                # MayaノードのUUID取得 (リネーム耐性の強化)
                maya_uuid = ""
                try:
                    uuid_list = mc.ls(final_path, uuid=True)
                    if uuid_list:
                        maya_uuid = uuid_list[0]
                except Exception:
                    pass

                bone_details.append({
                    'index': b_idx,
                    'name_jp': name_jp,
                    'name_en': name_en,
                    'parent_index': getattr(bone_obj, 'parent', -1),
                    'maya_node': final_path,
                    'maya_uuid': maya_uuid,
                    'is_ik': bool(getattr(bone_obj, 'is_ik', False))
                })

        bone_structure_map = final_joint_map

        # 足IKハンドルの自動構築
        try:
            ik_handles = setup_mmd_ik(model_mesh_node, bone_structure_map)
            if ik_handles:
                print(f"  - 足IKシステム ({len(ik_handles)}個のIKハンドル) を構築しました")
        except Exception as e:
            print(f"  [警告] 足IKシステムの構築中にエラー: {e}")

    # モデルのオリジナル名称を保持
    mc.addAttr(model_mesh_node, longName='originalName', niceName='元の名称', dataType='string')
    mc.setAttr(f"{model_mesh_node}.originalName", pmx_model.name, typ='string')

    # MMDモデルルート識別アトリビュート
    mc.addAttr(model_mesh_node, longName='mmdModelRoot', attributeType='bool')
    mc.setAttr(f"{model_mesh_node}.mmdModelRoot", True)

    # モデルノードのUUID取得
    model_uuid = ""
    try:
        uuid_l = mc.ls(model_mesh_node, uuid=True)
        if uuid_l:
            model_uuid = uuid_l[0]
    except Exception:
        pass

    # 剛体リストのシリアライズ
    rigid_bodies_data = []
    for r_idx, rb in enumerate(getattr(pmx_model, 'rigid_bodies', [])):
        rigid_bodies_data.append({
            'index': r_idx,
            'name_jp': rb.name,
            'name_en': getattr(rb, 'name_e', ''),
            'bone_index': rb.bone_index,
            'shape_type': rb.shape_type, # 0: 球, 1: 箱, 2: カプセル
            'size': [float(s) for s in rb.size],
            'position': [float(p) for p in rb.position],
            'rotation': [float(r) for r in rb.rotation],
            'mass': float(rb.mass),
            'linear_damping': float(rb.linear_damping),
            'angular_damping': float(rb.angular_damping),
            'restitution': float(rb.restitution),
            'friction': float(rb.friction),
            'group': int(rb.group),
            'collision_mask': int(rb.collision_mask),
            'physics_mode': int(rb.physics_mode) # 0: Kinematic, 1: Dynamic, 2: Aligned
        })

    # ジョイントリストのシリアライズ
    joints_data = []
    for j_idx, jt in enumerate(getattr(pmx_model, 'joints', [])):
        joints_data.append({
            'index': j_idx,
            'name_jp': jt.name,
            'name_en': getattr(jt, 'name_e', ''),
            'joint_type': getattr(jt, 'joint_type', 0),
            'rigid_body_a': jt.rigid_body_a,
            'rigid_body_b': jt.rigid_body_b,
            'position': [float(p) for p in jt.position],
            'rotation': [float(r) for r in jt.rotation],
            'linear_limit_min': [float(v) for v in jt.linear_limit_min],
            'linear_limit_max': [float(v) for v in jt.linear_limit_max],
            'angular_limit_min': [float(v) for v in jt.angular_limit_min],
            'angular_limit_max': [float(v) for v in jt.angular_limit_max],
            'spring_translation': [float(v) for v in jt.linear_spring],
            'spring_rotation': [float(v) for v in jt.angular_spring]
        })

    # モーフリストのシリアライズ (頂点以外のモーフ種別も保持)
    morphs_data = []
    morph_name_lookup = {}
    for m_idx, morph in enumerate(getattr(pmx_model, 'morphs', [])):
        m_name_jp = morph.name
        m_name_en = getattr(morph, 'name_e', '')
        m_type = getattr(morph, 'morph_type', 1)
        maya_target = morph_structure_map.get(m_name_jp) or morph_structure_map.get(m_name_en)
        supported = bool(maya_target and (m_type in [1, 8]))

        morph_entry = {
            'index': m_idx,
            'name_jp': m_name_jp,
            'name_en': m_name_en,
            'panel': getattr(morph, 'panel', 4),
            'morph_type': m_type,
            'offsets_count': len(getattr(morph, 'offsets', [])),
            'maya_target': maya_target,
            'maya_node': (model_mesh_node if m_type == 8 else blendshape_node_name) if maya_target else None,
            'supported_in_maya': supported
        }
        morphs_data.append(morph_entry)
        if m_name_jp:
            morph_name_lookup[m_name_jp] = m_idx
        if m_name_en:
            morph_name_lookup[m_name_en] = m_idx

    # 高速名前引き辞書 (name_lookup)
    bone_name_lookup = {}
    for b in (bone_details if 'bone_details' in locals() else []):
        if b['name_jp']:
            bone_name_lookup[b['name_jp']] = b['index']
        if b['name_en']:
            bone_name_lookup[b['name_en']] = b['index']

    name_lookup = {
        'bones': bone_name_lookup,
        'morphs': morph_name_lookup
    }

    # PMXモデル構造データ (バージョン 2.0 スキーマ)
    structure_data = {
        'schema_version': "2.0",
        'source': {
            'format': ext.replace('.', '').upper() if ext else "PMX",
            'pmx_version': getattr(pmx_model, 'version', 2.0),
            'model_name': pmx_model.name,
            'model_name_e': getattr(pmx_model, 'name_e', '')
        },
        'maya': {
            'model_node': model_mesh_node,
            'model_uuid': model_uuid,
            'scale': scale,
            'blendshape_node': blendshape_node_name,
            'root_joints': root_joint_names
        },
        'bones': bone_details if 'bone_details' in locals() else [],
        'morphs': morphs_data,
        'rigid_bodies': rigid_bodies_data,
        'joints': joints_data,
        'name_lookup': name_lookup,

        # 後方互換性レイヤー (旧コード・旧スクリプトからの安全な参照を確実に保証)
        'legacy_compatibility': {
            'bones': bone_structure_map if 'bone_structure_map' in locals() else {},
            'morphs': morph_structure_map if 'morph_structure_map' in locals() else {}
        },
        'model_name': pmx_model.name,
        'model_name_e': getattr(pmx_model, 'name_e', ''),
        'model_node': model_mesh_node,
        'bones_dict': bone_structure_map if 'bone_structure_map' in locals() else {},
        'morphs_dict': morph_structure_map if 'morph_structure_map' in locals() else {},
        'bone_details': bone_details if 'bone_details' in locals() else [],
        'blendshape_node': blendshape_node_name,
        'root_joints': root_joint_names,
        'scale': scale
    }

    try:
        # 新スキーマ全体のフルデータを格納する専用アトリビュート
        if not mc.attributeQuery('mmdModelStructure', node=model_mesh_node, exists=True):
            mc.addAttr(model_mesh_node, longName='mmdModelStructure', dataType='string')
        mc.setAttr(f"{model_mesh_node}.mmdModelStructure", json.dumps(structure_data, ensure_ascii=False), typ='string')

        # 既存コードとの後方互換性用アトリビュート (辞書形式)
        if not mc.attributeQuery('mmdBoneStructure', node=model_mesh_node, exists=True):
            mc.addAttr(model_mesh_node, longName='mmdBoneStructure', dataType='string')
        mc.setAttr(f"{model_mesh_node}.mmdBoneStructure", json.dumps(structure_data['legacy_compatibility']['bones'], ensure_ascii=False), typ='string')

        if not mc.attributeQuery('mmdMorphStructure', node=model_mesh_node, exists=True):
            mc.addAttr(model_mesh_node, longName='mmdMorphStructure', dataType='string')
        mc.setAttr(f"{model_mesh_node}.mmdMorphStructure", json.dumps(structure_data['legacy_compatibility']['morphs'], ensure_ascii=False), typ='string')

        # キャッシュファイル (last_imported_structure.json) の保存
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cache_path = os.path.join(plugin_root, 'asset', 'last_imported_structure.json')
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(structure_data, f, ensure_ascii=False, indent=2)
        print(f"  - モデル構造スキーマ 2.0 (ボーン: {len(structure_data['bones'])}本, 剛体: {len(structure_data['rigid_bodies'])}個, ジョイント: {len(structure_data['joints'])}個, モーフ: {len(structure_data['morphs'])}個) を保存しました")
    except Exception as e:
        print(f"  [警告] 構造メタデータの保存中に軽微なエラー: {e}")

    mc.select(model_mesh_node)
    if create_joints and root_joint_names:
        mc.select(root_joint_names, add=True)

    # ビューポートのリフレッシュ
    try:
        mc.refresh(force=True)
    except Exception:
        pass

    elapsed = time.time() - start_time
    if show_completion_message:
        print("==================================================")
        print(f"モデルインポートが完了しました！ (所要時間: {elapsed:.2f}秒)")
        print("==================================================")
    else:
        print(f"  - メッシュ・リグ構築が完了しました (所要時間: {elapsed:.2f}秒)")

    return model_mesh_node, root_joint_names, skin_node_name, blendshape_node_name

def setup_viewport_display(shadow_mode=None):
    """
    ビューポートの表示品質を最適化:
    - テクスチャ表示（displayTextures=True / 6キー相当）を有効化
    - アンチエイリアシング（マルチサンプルAAおよびポストAA）を有効化
    - 透過アルゴリズム（Depth Peeling）を設定
    - ライティング・影表示を設定（shadow_mode指定時）
    """
    # ハードウェアレンダリング設定（アンチエイリアシング & 深度ピーリング）
    try:
        if mc.objExists('hardwareRenderingGlobals'):
            # マルチサンプルアンチエイリアシング (MSAA) の有効化
            if mc.attributeQuery('multiSampleEnable', node='hardwareRenderingGlobals', exists=True):
                mc.setAttr('hardwareRenderingGlobals.multiSampleEnable', 1)
            if mc.attributeQuery('multiSampleCount', node='hardwareRenderingGlobals', exists=True):
                mc.setAttr('hardwareRenderingGlobals.multiSampleCount', 8)
            # スクリーンスペース・ポストプロセスアンチエイリアシングの有効化
            if mc.attributeQuery('antiAliasingEnable', node='hardwareRenderingGlobals', exists=True):
                mc.setAttr('hardwareRenderingGlobals.antiAliasingEnable', 1)
            # 透過アルゴリズムを Depth Peeling に設定
            if mc.attributeQuery('transparencyAlgorithm', node='hardwareRenderingGlobals', exists=True):
                mc.setAttr('hardwareRenderingGlobals.transparencyAlgorithm', 3)
    except Exception:
        pass

    # 全ビューポートパネルの設定（テクスチャ表示を有効化）
    try:
        model_panels = mc.getPanel(type='modelPanel') or []
        for panel in model_panels:
            edit_kwargs = {'displayTextures': True}
            if shadow_mode is not None:
                edit_kwargs['displayLights'] = 'all'
                edit_kwargs['shadows'] = (shadow_mode > 0)
            mc.modelEditor(panel, edit=True, **edit_kwargs)
    except Exception:
        pass

    # perspカメラの焦点距離をMMD標準画角に設定
    setup_persp_camera_for_mmd()

def setup_persp_camera_for_mmd(target_fov_deg=30.0):
    """
    Mayaのperspカメラの焦点距離をMMD標準（垂直画角30度）に設定します。
    """
    try:
        cam_shape = 'perspShape'
        if not mc.objExists(cam_shape):
            shapes = mc.ls('persp', shapes=True) or []
            if shapes:
                cam_shape = shapes[0]
            else:
                return

        # 垂直フィルムゲート寸法 (インチ) をミリメートルへ変換
        aperture_inch = mc.camera(cam_shape, query=True, verticalFilmAperture=True)
        aperture_mm = aperture_inch * 25.4

        # 垂直視野角から焦点距離を計算
        fov_rad = math.radians(target_fov_deg)
        focal_length = (aperture_mm / 2.0) / math.tan(fov_rad / 2.0)

        mc.setAttr(f"{cam_shape}.focalLength", focal_length)
        print(f"[情報] perspカメラの焦点距離を MMD準拠 ({focal_length:.2f}mm, 画角 {target_fov_deg}°) に設定しました。")
    except Exception as e:
        print(f"[警告] perspカメラの焦点距離設定中に軽微な例外: {e}")


def set_untone_mapped_view_transform():
    """
    Mayaのカラーマネジメントのビュー変換を 'Un-tone-mapped (sRGB)' に設定します。
    トーンマッパーによるテクスチャやToon影の暗化を防ぎ、MMD本来の明るく鮮やかな発色を再現します。
    """
    try:
        if not mc.colorManagementPrefs(query=True, cmEnabled=True):
            return

        available_views = mc.colorManagementPrefs(query=True, viewTransformNames=True) or []
        target_name = None
        for cand in ['Un-tone-mapped (sRGB)', 'Un-tone-mapped', 'sRGB']:
            if cand in available_views:
                target_name = cand
                break

        if target_name:
            current_view = mc.colorManagementPrefs(query=True, viewTransformName=True)
            if current_view != target_name:
                mc.colorManagementPrefs(edit=True, viewTransformName=target_name)
                print(f"[情報] ビュー変換を '{target_name}' に設定しました（MMD最適化発色）。")
    except Exception as e:
        print(f"[警告] ビュー変換の設定をスキップしました: {e}")

def create_mmd_lighting(shadow_mode=1):
    """
    MMD標準のライティング設定（平行光 & 環境光）を構築します。
    MMDデフォルト値:
      - 光源色: 赤154, 緑154, 青154 (約 0.6039)
      - 光源方向: X: -0.5, Y: -1.0, Z: +0.5 (Maya座標系: X: -0.5, Y: -1.0, Z: -0.5)
      - 方向角: RotateX: -54.74, RotateY: 45.0, RotateZ: 0.0

    shadow_mode:
      - 0: セルフ影なし (シャドウOFF)
      - 1: モード1 (標準セルフ影)
      - 2: モード2 (高精細セルフ影)
    """
    # 既存のMMDライトが存在する場合は再作成せず最適化・更新
    existing_dir_shapes = mc.ls("mmd_directional_light*Shape*", type="directionalLight") or []
    existing_amb_shapes = mc.ls("mmd_ambient_light*Shape*", type="ambientLight") or []

    if existing_dir_shapes or existing_amb_shapes:
        if existing_dir_shapes:
            d_shape = existing_dir_shapes[0]
            d_trans = mc.listRelatives(d_shape, parent=True, fullPath=True)[0]
            mc.setAttr(f"{d_trans}.rotate", -54.74, -45.0, 0.0, typ='double3')
            mc.setAttr(f"{d_trans}.translateY", 200.0)
            mc.setAttr(f"{d_trans}.scale", 5.0, 5.0, 5.0)
            mc.setAttr(f"{d_shape}.color", 0.6039, 0.6039, 0.6039, typ='double3')
            mc.setAttr(f"{d_shape}.intensity", 0.85)
            _apply_shadow_mode(d_shape, shadow_mode)
        if existing_amb_shapes:
            a_shape = existing_amb_shapes[0]
            a_trans = mc.listRelatives(a_shape, parent=True, fullPath=True)[0]
            mc.setAttr(f"{a_trans}.translateY", 200.0)
            mc.setAttr(f"{a_trans}.scale", 5.0, 5.0, 5.0)
            mc.setAttr(f"{a_shape}.ambientShade", 0.15)
            mc.setAttr(f"{a_shape}.color", 0.50, 0.50, 0.50, typ='double3')
            mc.setAttr(f"{a_shape}.intensity", 0.35)
        # ビューポートのテクスチャ表示とアンチエイリアシングを最適化
        setup_viewport_display(shadow_mode=shadow_mode)
        print("[情報] 既存のMMD標準ライティングを適正化しました（白飛び防止設定適用）。")
        return "mmd_lighting_grp"

    print(f"[情報] MMD標準ライティング（シャドウモード: {shadow_mode}）を作成中...")

    # 名前の衝突を防止するためユニーク名を決定
    dir_light_name = _get_unique_node_name("mmd_directional_light")
    dir_shape_name = _get_unique_node_name(f"{dir_light_name}Shape")
    amb_light_name = _get_unique_node_name("mmd_ambient_light")
    amb_shape_name = _get_unique_node_name(f"{amb_light_name}Shape")
    grp_name = _get_unique_node_name("mmd_lighting_grp")

    # 平行光源 (MMDデフォルトキーライト: 白飛び防止のため強度0.85に設定)
    dir_shape = mc.directionalLight(name=dir_shape_name, intensity=0.85)
    dir_transform = mc.listRelatives(dir_shape, parent=True)[0]
    dir_light = mc.rename(dir_transform, dir_light_name)

    # MMDデフォルト値: X: -0.5 (左), Y: -1.0 (下), Z: +0.5 (奥) へ進む光 -> Maya右手系角度 [-54.74, -45.0, 0.0]
    mc.setAttr(f"{dir_light}.rotate", -54.74, -45.0, 0.0, typ='double3')
    mc.setAttr(f"{dir_light}.color", 0.6039, 0.6039, 0.6039, typ='double3')
    # 頭上への配置（Y=200）および視認性向上のための拡大（スケール=5）
    mc.setAttr(f"{dir_light}.translateY", 200.0)
    mc.setAttr(f"{dir_light}.scale", 5.0, 5.0, 5.0)

    # シャドウモードの適用
    _apply_shadow_mode(dir_shape, shadow_mode)

    # アンビエントライト (MMDの自然で明るい環境光: 白飛び防止のため強度0.35、Color 0.50に設定)
    amb_shape = mc.ambientLight(name=amb_shape_name, intensity=0.35)
    amb_transform = mc.listRelatives(amb_shape, parent=True)[0]
    amb_light = mc.rename(amb_transform, amb_light_name)
    mc.setAttr(f"{amb_light}.ambientShade", 0.15)
    mc.setAttr(f"{amb_light}.color", 0.50, 0.50, 0.50, typ='double3')
    mc.setAttr(f"{amb_light}.translateY", 200.0)
    mc.setAttr(f"{amb_light}.scale", 5.0, 5.0, 5.0)

    # グループ化
    light_grp = mc.group(dir_light, amb_light, name=grp_name)

    # ビューポートのテクスチャ表示・ライティング・アンチエイリアシングを最適化
    setup_viewport_display(shadow_mode=shadow_mode)

    print(f"[情報] MMD標準ライティングを作成しました ({light_grp})。")
    return light_grp

def _apply_shadow_mode(dir_shape, shadow_mode):
    """Directional Lightノードおよびビューポートにセルフシャドウ設定を適用"""
    if not mc.objExists(dir_shape):
        return
    try:
        if shadow_mode == 0:
            # セルフ影なし
            mc.setAttr(f"{dir_shape}.useDepthMapShadows", 0)
        elif shadow_mode == 1:
            # モード1 (標準セルフ影) - MMD準拠の自然で柔らかい半透明影
            mc.setAttr(f"{dir_shape}.useDepthMapShadows", 1)
            mc.setAttr(f"{dir_shape}.dmapResolution", 2048)
            mc.setAttr(f"{dir_shape}.dmapFilterSize", 5)
            mc.setAttr(f"{dir_shape}.dmapBias", 0.02)
            mc.setAttr(f"{dir_shape}.shadowColor", 0.45, 0.45, 0.45, typ='double3')
        elif shadow_mode == 2:
            # モード2 (高精細セルフ影) - MMD準拠の自然で柔らかい半透明影
            mc.setAttr(f"{dir_shape}.useDepthMapShadows", 1)
            mc.setAttr(f"{dir_shape}.dmapResolution", 4096)
            mc.setAttr(f"{dir_shape}.dmapFilterSize", 5)
            mc.setAttr(f"{dir_shape}.dmapBias", 0.02)
            mc.setAttr(f"{dir_shape}.shadowColor", 0.45, 0.45, 0.45, typ='double3')

        # ビューポート連動（影とテクスチャ表示）
        model_panels = mc.getPanel(type='modelPanel') or []
        for panel in model_panels:
            mc.modelEditor(panel, edit=True, shadows=(shadow_mode > 0), displayTextures=True)
    except Exception:
        pass

def fix_toon_shading_in_scene(shadow_mode=1):
    """
    シーン内の既存MMDシェーダーに対してToon設定およびスペキュラ設定を最適化
    - Toon計算をカメラ空間からワールド空間（matrixEyeToWorld変換）に切り替え、視点移動による影の変化を解消
    - MMD照明のセルフ影モード（0: なし, 1: モード1, 2: モード2）を適用
    - 顔・肌パーツも含め、全材質のToon乗算を最適なしきい値で再接続
    - 顔・肌および反射なし材質のプラスチック調スペキュラ光沢を除去
    """
    fixed_count = 0

    # ライティングとシャドウモードの更新
    dir_shapes = mc.ls("mmd_directional_lightShape", type="directionalLight") or []
    if dir_shapes:
        dir_shape = dir_shapes[0]
        dir_transform = mc.listRelatives(dir_shape, parent=True, fullPath=True)[0]
        mc.setAttr(f"{dir_transform}.rotate", -54.74, -45.0, 0.0, typ='double3')
        mc.setAttr(f"{dir_transform}.translateY", 200.0)
        mc.setAttr(f"{dir_transform}.scale", 5.0, 5.0, 5.0)
        mc.setAttr(f"{dir_shape}.color", 0.6039, 0.6039, 0.6039, typ='double3')
        _apply_shadow_mode(dir_shape, shadow_mode)
    elif mc.objExists("mmd_lighting_grp"):
        _apply_shadow_mode("mmd_directional_lightShape", shadow_mode)

    amb_shapes = mc.ls("mmd_ambient_light*Shape*", type="ambientLight") or []
    if amb_shapes:
        amb_transform = mc.listRelatives(amb_shapes[0], parent=True, fullPath=True)[0]
        mc.setAttr(f"{amb_transform}.translateY", 200.0)
        mc.setAttr(f"{amb_transform}.scale", 5.0, 5.0, 5.0)

    # Toon計算ネットワークのワールド空間化 (視点回転に左右されないMMD互換設定)
    vecprod_nodes = mc.ls("toon_vecprod_*", type="vectorProduct") or []
    for vp in vecprod_nodes:
        try:
            conns = mc.listConnections(f"{vp}.input1", source=True, destination=False, plugs=True) or []
            if conns:
                src_plug = conns[0]
                src_node = src_plug.split('.')[0]
                if mc.nodeType(src_node) == 'samplerInfo':
                    suffix = vp.replace("toon_vecprod_", "")
                    wnorm_name = f"toon_wnorm_{suffix}"
                    if not mc.objExists(wnorm_name):
                        wnorm_node = mc.shadingNode('vectorProduct', asUtility=True, name=wnorm_name)
                    else:
                        wnorm_node = wnorm_name

                    mc.setAttr(f"{wnorm_node}.operation", 3) # Vector Matrix Product
                    mc.setAttr(f"{wnorm_node}.normalizeOutput", True)
                    mc.connectAttr(f"{src_node}.normalCamera", f"{wnorm_node}.input1", force=True)
                    mc.connectAttr(f"{src_node}.matrixEyeToWorld", f"{wnorm_node}.matrix", force=True)
                    mc.connectAttr(f"{wnorm_node}.output", f"{vp}.input1", force=True)

            # MMD標準のワールド光線方向に設定 (斜め前方左上)
            mc.setAttr(f"{vp}.input2", -0.40825, 0.81650, 0.40825, typ='double3')
            fixed_count += 1
        except Exception:
            pass

    # toon_range ノードのしきい値更新 (正面は白、側面〜裏面が自然に陰るMMD最適化)
    range_nodes = mc.ls("toon_range_*", type="setRange") or []
    for r_node in range_nodes:
        try:
            mc.setAttr(f"{r_node}.minX", 0.0)
            mc.setAttr(f"{r_node}.maxX", 1.0)
            mc.setAttr(f"{r_node}.oldMinX", -1.0)
            mc.setAttr(f"{r_node}.oldMaxX", 1.0)
            fixed_count += 1
        except Exception:
            pass

    # 顔・肌・表情マテリアルの保護とテカリ除去 (ユーザー辞書連動)
    try:
        try:
            from ..asset.user_dict_manager import is_face_or_skin_material, is_toon_bypass_material
        except Exception:
            from asset.user_dict_manager import is_face_or_skin_material, is_toon_bypass_material
    except Exception:
        is_face_or_skin_material = None
        is_toon_bypass_material = None

    all_shaders = mc.ls(materials=True) or []
    for shd in all_shaders:
        shd_name = shd.lower()
        orig_name = mc.getAttr(f"{shd}.originalName").lower() if mc.attributeQuery("originalName", node=shd, exists=True) else ""
        if is_face_or_skin_material:
            is_skin_mat = is_face_or_skin_material(shd, orig_name)
            is_highlight = is_toon_bypass_material(shd, orig_name)
        else:
            face_skin_keywords = [
                "顔", "head", "face", "目", "eye", "瞳", "眉", "brow", "口", "mouth",
                "舌", "牙", "歯", "teeth", "tooth", "唇", "lip", "表情", "涙", "頬",
                "cheek", "肌", "skin", "body", "体", "面", "nose", "鼻"
            ]
            is_skin_mat = any(k in shd_name or k in orig_name for k in face_skin_keywords)
            is_highlight = any(k in shd_name or k in orig_name for k in ["瞳-高光", "高光", "眼白", "highlight"])

        # 瞳のハイライトパーツ等のみToon乗算をバイパス（顔・肌はToon適用）
        if is_highlight:
            target_attr = "baseColor" if mc.attributeQuery("baseColor", node=shd, exists=True) else "color"
            conns = mc.listConnections(f"{shd}.{target_attr}", source=True, destination=False, plugs=True) or []
            if conns:
                source_plug = conns[0]
                source_node = source_plug.split('.')[0]
                if mc.nodeType(source_node) == "multiplyDivide" and "toon_mult" in source_node:
                    input1_conns = mc.listConnections(f"{source_node}.input1", source=True, destination=False, plugs=True) or []
                    if input1_conns:
                        main_color_plug = input1_conns[0]
                        mc.connectAttr(main_color_plug, f"{shd}.{target_attr}", force=True)
                        fixed_count += 1

        # スペキュラ（反射テカリ）の最適化
        if mc.attributeQuery("specular", node=shd, exists=True):
            try:
                spec_color = [0.0, 0.0, 0.0]
                if mc.attributeQuery("specularColor", node=shd, exists=True):
                    spec_conns = mc.listConnections(f"{shd}.specularColor", source=True, destination=False)
                    if not spec_conns:
                        spec_color = mc.getAttr(f"{shd}.specularColor")[0]

                if is_skin_mat or sum(spec_color) < 0.05:
                    mc.setAttr(f"{shd}.specular", 0.0)
                    mc.setAttr(f"{shd}.specularRoughness", 1.0)
                    if mc.attributeQuery("specularColor", node=shd, exists=True) and not mc.listConnections(f"{shd}.specularColor"):
                        mc.setAttr(f"{shd}.specularColor", 0.0, 0.0, 0.0, typ='double3')
                    fixed_count += 1
                else:
                    cur_spec = mc.getAttr(f"{shd}.specular")
                    if cur_spec > 0.5:
                        mc.setAttr(f"{shd}.specular", 0.3)
                    mc.setAttr(f"{shd}.specularRoughness", 0.6)
            except Exception:
                pass
        elif mc.attributeQuery("specularColor", node=shd, exists=True) and is_skin_mat:
            try:
                mc.setAttr(f"{shd}.specularColor", 0.0, 0.0, 0.0, typ='double3')
            except Exception:
                pass

    print(f"[MMD Tools for Maya] Toonシェーディング＆テカリ除去を最適化しました (更新要素: {fixed_count}, シャドウモード: {shadow_mode})。")
    return fixed_count


def get_scene_mmd_materials(target_model=None):
    """
    シーン内（または指定モデル配下）のMMDマテリアル情報を収集して返します。
    戻り値: マテリアル情報の辞書リスト
    """
    try:
        try:
            from ..asset.user_dict_manager import is_face_or_skin_material, is_toon_bypass_material
        except Exception:
            from asset.user_dict_manager import is_face_or_skin_material, is_toon_bypass_material
    except Exception:
        is_face_or_skin_material = None
        is_toon_bypass_material = None

    shaders = set()
    if target_model and mc.objExists(target_model):
        meshes = mc.listRelatives(target_model, allDescendents=True, type='mesh', fullPath=True) or []
        if mc.nodeType(target_model) == 'mesh':
            meshes.append(target_model)
        for m in meshes:
            sgs = mc.listConnections(m, type='shadingEngine') or []
            for sg in sgs:
                shds = mc.listConnections(f"{sg}.surfaceShader") or []
                for s in shds:
                    shaders.add(s)
    else:
        for s in mc.ls(materials=True) or []:
            if mc.attributeQuery("originalName", node=s, exists=True):
                shaders.add(s)
            elif any(prefix in s for prefix in ["mat_", "mmd_"]):
                shaders.add(s)

    results = []
    for shd in sorted(list(shaders)):
        orig_name = mc.getAttr(f"{shd}.originalName") if mc.attributeQuery("originalName", node=shd, exists=True) else ""
        if not orig_name:
            orig_name = shd.split('|')[-1].split(':')[-1]

        is_skin = False
        is_toon_bp = False
        if is_face_or_skin_material:
            is_skin = is_face_or_skin_material(shd, orig_name)
            is_toon_bp = is_toon_bypass_material(shd, orig_name)

        results.append({
            "shader": shd,
            "original_name": orig_name,
            "is_face_skin": is_skin,
            "is_toon_bypass": is_toon_bp
        })
    return results


def apply_material_protection_to_scene(target_model=None):
    """
    シーン内（または指定モデル配下）のMMDマテリアルに対して、
    現在のユーザー辞書設定（顔・肌保護キーワード、Toon除外キーワード）を即時反映します。
    """
    mat_list = get_scene_mmd_materials(target_model)
    skin_applied_count = 0
    toon_bypass_count = 0
    toon_restored_count = 0

    for item in mat_list:
        shd = item["shader"]
        is_skin = item["is_face_skin"]
        is_toon_bp = item["is_toon_bypass"]

        # 顔・肌マテリアルのスペキュラ（反射テカリ）保護
        if mc.attributeQuery("specular", node=shd, exists=True):
            try:
                if is_skin:
                    mc.setAttr(f"{shd}.specular", 0.0)
                    mc.setAttr(f"{shd}.specularRoughness", 1.0)
                    if mc.attributeQuery("specularColor", node=shd, exists=True) and not mc.listConnections(f"{shd}.specularColor"):
                        mc.setAttr(f"{shd}.specularColor", 0.0, 0.0, 0.0, typ='double3')
                    skin_applied_count += 1
                else:
                    cur_spec = mc.getAttr(f"{shd}.specular")
                    if cur_spec < 0.01:
                        mc.setAttr(f"{shd}.specular", 0.25)
                        mc.setAttr(f"{shd}.specularRoughness", 0.6)
            except Exception:
                pass
        elif mc.attributeQuery("specularColor", node=shd, exists=True) and not mc.listConnections(f"{shd}.specularColor"):
            try:
                if is_skin:
                    mc.setAttr(f"{shd}.specularColor", 0.0, 0.0, 0.0, typ='double3')
                    if mc.attributeQuery("reflectivity", node=shd, exists=True):
                        mc.setAttr(f"{shd}.reflectivity", 0.0)
                    skin_applied_count += 1
            except Exception:
                pass

        # 表情モーフ用透明材質（頬染め、顔斜線、涙、肌3等）の白枠線・エッジ自動抑止
        orig_name_str = item["original_name"]
        is_transparent_morph = any(k in orig_name_str for k in ["頬染め", "顔斜線", "肌3", "照れ", "涙"])
        if mc.attributeQuery("opacity", node=shd, exists=True):
            try:
                op_val = mc.getAttr(f"{shd}.opacity")[0]
                if sum(op_val) < 0.05:
                    is_transparent_morph = True
            except Exception:
                pass
        elif mc.attributeQuery("transparency", node=shd, exists=True):
            try:
                tr_val = mc.getAttr(f"{shd}.transparency")[0]
                if min(tr_val) > 0.95:
                    is_transparent_morph = True
            except Exception:
                pass

        if is_transparent_morph:
            try:
                if mc.attributeQuery("diffuse", node=shd, exists=True):
                    mc.setAttr(f"{shd}.diffuse", 0.0)
                if mc.attributeQuery("shadowAttenuation", node=shd, exists=True):
                    mc.setAttr(f"{shd}.shadowAttenuation", 0.0)
                if mc.attributeQuery("ambientColor", node=shd, exists=True):
                    mc.setAttr(f"{shd}.ambientColor", 0.0, 0.0, 0.0, typ="double3")
                if mc.attributeQuery("color", node=shd, exists=True):
                    # テクスチャ接続がない場合のみ黒に設定
                    if not mc.listConnections(f"{shd}.color", source=True):
                        mc.setAttr(f"{shd}.color", 0.0, 0.0, 0.0, typ="double3")
                if mc.attributeQuery("specularColor", node=shd, exists=True):
                    mc.setAttr(f"{shd}.specularColor", 0.0, 0.0, 0.0, typ="double3")
                if mc.attributeQuery("specular", node=shd, exists=True):
                    mc.setAttr(f"{shd}.specular", 0.0)
                    mc.setAttr(f"{shd}.specularRoughness", 1.0)
                if mc.attributeQuery("base", node=shd, exists=True):
                    mc.setAttr(f"{shd}.base", 0.0)
                if mc.attributeQuery("edgeEnable", node=shd, exists=True):
                    mc.setAttr(f"{shd}.edgeEnable", False)
                if mc.attributeQuery("edgeSize", node=shd, exists=True):
                    mc.setAttr(f"{shd}.edgeSize", 0.0)
            except Exception:
                pass

        # Toon除外設定（瞳ハイライト等の乗算バイパス / 復帰）
        target_attr = "baseColor" if mc.attributeQuery("baseColor", node=shd, exists=True) else "color"
        conns = mc.listConnections(f"{shd}.{target_attr}", source=True, destination=False, plugs=True) or []
        if is_toon_bp:
            if conns:
                src_plug = conns[0]
                src_node = src_plug.split('.')[0]
                if mc.nodeType(src_node) == "multiplyDivide" and "toon_mult" in src_node:
                    in1_conns = mc.listConnections(f"{src_node}.input1", source=True, destination=False, plugs=True) or []
                    if in1_conns:
                        mc.connectAttr(in1_conns[0], f"{shd}.{target_attr}", force=True)
                        toon_bypass_count += 1
        else:
            safe_id = shd.replace(':', '_').replace('|', '_')
            candidate_mults = mc.ls(f"*{safe_id}*toon_mult*", type="multiplyDivide") or []
            if not candidate_mults:
                all_mults = mc.ls("*toon_mult*", type="multiplyDivide") or []
                for tm in all_mults:
                    if safe_id in tm:
                        candidate_mults.append(tm)
            if candidate_mults:
                tm_node = candidate_mults[0]
                if conns and conns[0] != f"{tm_node}.output":
                    try:
                        mc.connectAttr(f"{tm_node}.output", f"{shd}.{target_attr}", force=True)
                        toon_restored_count += 1
                    except Exception:
                        pass

    return {
        "total_materials": len(mat_list),
        "skin_protected": skin_applied_count,
        "toon_bypassed": toon_bypass_count,
        "toon_restored": toon_restored_count
    }


# 後方互換性用エイリアス
sang = import_pmx