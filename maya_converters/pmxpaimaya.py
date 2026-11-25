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
    from .. import mmd_parser
    from ..asset.jaka import romaji, safe_node_name
    from ..asset.bone_dict import get_english_bone_name, get_japanese_bone_name
except Exception:
    import mmd_parser
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
        pass

    # PIL未導入環境向けバイナリヘッダー解析 (PNG / TGA)
    try:
        import struct
        with open(img_path, 'rb') as f:
            head = f.read(64)
            if ext == '.png' and len(head) >= 29 and head[:8] == b'\x89PNG\r\n\x1a\n':
                color_type = head[25]
                if color_type in (4, 6):
                    return True
                f.seek(0)
                raw_chunk = f.read(4096)
                return b'tRNS' in raw_chunk
            elif ext == '.tga' and len(head) >= 18:
                bpp = head[16]
                attr_bits = head[17] & 0x0F
                return (bpp == 32) or (attr_bits > 0)
    except Exception:
        pass
    return ext in ['.dds']

def _get_shared_toon_path(toon_idx, model_dir=None):
    """
    共有トゥーンテクスチャ (toon01.bmp〜toon10.bmp) の実ファイルパスを解決します。
    モデルフォルダ内に同梱されている場合はそちらを最優先し、無ければプラグイン内のtoonフォルダを参照します。
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.dirname(current_dir)
    toon_num = toon_idx + 1
    base_names = [f"toon{toon_num:02d}.bmp", f"toon{toon_num:02d}.png", f"toon{toon_num:02d}.tga"]
    if toon_idx == 0:
        base_names.insert(0, "toon0.bmp")

    candidates = []
    if model_dir and os.path.isdir(model_dir):
        for b_name in base_names:
            candidates.append(os.path.join(model_dir, b_name))
            candidates.append(os.path.join(model_dir, "toon", b_name))
            candidates.append(os.path.join(model_dir, "tex", b_name))
            candidates.append(os.path.join(model_dir, "textures", b_name))

    toon_bmp = f"toon{toon_num:02d}.bmp"
    candidates.extend([
        os.path.join(plugin_root, "toon", toon_bmp),
        os.path.join(plugin_root, "asset", "toon", toon_bmp),
        os.path.join(current_dir, "toon", toon_bmp),
        os.path.join(current_dir, "asset", "toon", toon_bmp),
    ])
    for c in candidates:
        if os.path.isfile(c):
            return os.path.normpath(c).replace('\\', '/')
    return None


def _resolve_custom_toon_path(raw_path, model_dir=None):
    """
    PMX材質で個別指定されたToonテクスチャパスを解決します。
    モデルフォルダ内の同梱ファイルを最優先で探索し、見つからない場合のみ共有toonフォルダへフォールバックします。
    """
    if not raw_path:
        return None
    norm_rel = raw_path.replace('\\', '/').strip().lstrip('/')
    base_name = os.path.basename(norm_rel)
    base_lower = base_name.lower()

    if os.path.isabs(norm_rel) and os.path.isfile(norm_rel):
        return os.path.normpath(norm_rel).replace('\\', '/')

    if model_dir and os.path.isdir(model_dir):
        direct_candidates = [
            os.path.join(model_dir, norm_rel),
            os.path.join(model_dir, base_name),
            os.path.join(model_dir, "toon", base_name),
            os.path.join(model_dir, "tex", base_name),
            os.path.join(model_dir, "texture", base_name),
            os.path.join(model_dir, "textures", base_name),
        ]
        for cand in direct_candidates:
            if os.path.isfile(cand):
                return os.path.normpath(cand).replace('\\', '/')

        # 大文字小文字の違いやサブフォルダ階層を考慮してモデルフォルダ内を探索
        norm_rel_lower = norm_rel.lower()
        for root_d, _, files in os.walk(model_dir):
            for f in files:
                if f.lower() == base_lower:
                    full_p = os.path.join(root_d, f)
                    rel_p = os.path.relpath(full_p, model_dir).replace('\\', '/').lower()
                    if rel_p == norm_rel_lower:
                        return os.path.normpath(full_p).replace('\\', '/')
        for root_d, _, files in os.walk(model_dir):
            for f in files:
                if f.lower() == base_lower:
                    return os.path.normpath(os.path.join(root_d, f)).replace('\\', '/')

    # モデルフォルダ内に存在しない場合のみ、共有toonフォルダから探索
    current_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.dirname(current_dir)
    for si in range(10):
        if f"toon{si+1:02d}." in base_lower or f"toon{si+1}." in base_lower:
            shared_p = _get_shared_toon_path(si, model_dir=None)
            if shared_p:
                return shared_p
    if base_lower.startswith("toon0."):
        shared_p = _get_shared_toon_path(0, model_dir=None)
        if shared_p:
            return shared_p

    fallback_dirs = [
        os.path.join(plugin_root, "toon", base_name),
        os.path.join(plugin_root, "asset", "toon", base_name),
        os.path.join(current_dir, "toon", base_name),
    ]
    for fb in fallback_dirs:
        if os.path.isfile(fb):
            return os.path.normpath(fb).replace('\\', '/')
    return None


def _extract_toon_shadow_color(img_path):
    """
    Toonテクスチャ画像（BMP/PNG/TGA等）の下端（v=0.05付近）のピクセルから
    影色のsRGB値 (R, G, B) [0.0〜1.0] を抽出します。
    PILが未導入のMaya環境でも24/32bit BMPバイナリを直接解析して正確に色を取得します。
    """
    if not img_path or not os.path.isfile(img_path):
        return (0.88, 0.88, 0.88)

    # PIL (Pillow) が利用可能な場合は優先使用
    try:
        from PIL import Image
        with Image.open(img_path) as im:
            rgb_im = im.convert('RGB')
            w, h = rgb_im.size
            px = max(0, min(w - 1, int(w * 0.5)))
            py = max(0, min(h - 1, int(h * 0.95)))
            r, g, b = rgb_im.getpixel((px, py))
            return (r / 255.0, g / 255.0, b / 255.0)
    except Exception:
        pass

    # 標準BMPバイナリの直接解析 (toon01.bmp〜toon10.bmpおよびカスタムBMP対応)
    try:
        import struct
        with open(img_path, 'rb') as f:
            header = f.read(54)
            if len(header) >= 54 and header[:2] == b'BM':
                pixel_offset = struct.unpack_from('<I', header, 10)[0]
                width = struct.unpack_from('<i', header, 18)[0]
                height = struct.unpack_from('<i', header, 22)[0]
                bpp = struct.unpack_from('<H', header, 28)[0]
                abs_w = abs(width)
                abs_h = abs(height)
                if abs_w > 0 and abs_h > 0 and bpp in (24, 32):
                    bytes_per_pixel = bpp // 8
                    row_stride = ((abs_w * bytes_per_pixel + 3) // 4) * 4
                    # height > 0 の標準ボトムアップBMPでは row=0 が最下端
                    target_row = int(abs_h * 0.05) if height > 0 else int(abs_h * 0.95)
                    target_row = max(0, min(abs_h - 1, target_row))
                    target_col = max(0, min(abs_w - 1, abs_w // 2))
                    pos = pixel_offset + target_row * row_stride + target_col * bytes_per_pixel
                    f.seek(pos)
                    px_bytes = f.read(3)
                    if len(px_bytes) == 3:
                        b_val, g_val, r_val = px_bytes[0], px_bytes[1], px_bytes[2]
                        return (r_val / 255.0, g_val / 255.0, b_val / 255.0)
    except Exception:
        pass

    # ファイル名からのMMD標準共有Toonカラーフォールバック
    base_lower = os.path.basename(img_path).lower()
    if "toon02" in base_lower:
        return (0.949, 0.855, 0.859)
    elif "toon03" in base_lower:
        return (0.910, 0.835, 0.780)
    elif "toon04" in base_lower:
        return (0.855, 0.855, 0.855)
    return (0.88, 0.88, 0.88)


def _compute_mmd_light_colors_from_toon(toon_srgb):
    """
    抽出されたToon影色(sRGB)から、Maya Viewport 2.0のカラースペース下で
    - 明部（平行光＋環境光）が純白 (1.0, 1.0, 1.0) となり元のテクスチャ色を損なわず、
    - 落ち影領域（セルフシャドウで平行光が遮蔽された領域）がToon本来の影色（toon02.bmp等のピンクベージュ等）
    になるような環境光RGBおよび平行光RGBのペアを算出します。
    """
    r_s, g_s, b_s = toon_srgb
    # 純白に近いToon（影なし用）の場合は標準の控えめな陰影比率を維持
    if r_s > 0.98 and g_s > 0.98 and b_s > 0.98:
        amb_rgb = (0.78, 0.78, 0.78)
        dir_rgb = (0.22, 0.22, 0.22)
        return amb_rgb, dir_rgb

    # Mayaのリニア作業空間（Un-tone-mapped sRGBビュー変換）で画面上の落ち影が
    # MMDのToon乗算色（T_sRGB * Toon_sRGB）と一致するようガンマ2.2換算を適用
    amb_r = max(0.45, min(0.92, (r_s ** 2.2) * 0.96))
    amb_g = max(0.45, min(0.92, (g_s ** 2.2) * 0.94))
    amb_b = max(0.45, min(0.92, (b_s ** 2.2) * 0.94))

    dir_r = max(0.05, 1.0 - amb_r)
    dir_g = max(0.05, 1.0 - amb_g)
    dir_b = max(0.05, 1.0 - amb_b)
    return (amb_r, amb_g, amb_b), (dir_r, dir_g, dir_b)


def _apply_toon_color_to_mmd_lights(toon_srgb):
    """
    シーン内の mmd_ambient_light にモデルの主要Toon影色を反映し、
    服や顔に落ちるデプスマップシャドウ（落ち影）に toon02.bmp 等の影色が乗るようにします。
    平行光源（mmd_directional_light）はMMD本家標準の基準色 (RGB 154) を維持します。
    """
    amb_rgb, dir_rgb = _compute_mmd_light_colors_from_toon(toon_srgb)
    try:
        amb_shapes = mc.ls("mmd_ambient_light*Shape*", type="ambientLight") or []
        for a_shape in amb_shapes:
            mc.setAttr(f"{a_shape}.color", amb_rgb[0], amb_rgb[1], amb_rgb[2], typ='double3')
            mc.setAttr(f"{a_shape}.intensity", 1.0)
    except Exception:
        pass
    return amb_rgb, dir_rgb

def _get_unique_node_name(base_name):
    """Mayaシーン内で既存のノード名と衝突しない一意な名前を生成します。"""
    candidate = base_name
    count = 1
    while mc.objExists(candidate):
        candidate = f"{base_name}_{count}"
        count += 1
    return candidate


def ensure_mmd_fast_plugin_loaded():
    """
    C++ 高速インポート＆モーション統合プラグイン (mmd_fast.mll) のロード状態を確認し、
    未ロードの場合は対応する Maya バージョン向けバイナリを自動ロードします。
    旧 mmd_motion プラグインとのコマンド名衝突を自動で回避します。
    """
    # 旧 mmd_motion がロードされている場合は衝突回避のためアンロード
    for old_p in ["mmd_motion", "mmd_motion.mll"]:
        try:
            if mc.pluginInfo(old_p, query=True, loaded=True):
                mc.pluginInfo(old_p, edit=True, autoload=False)
                mc.unloadPlugin(old_p, force=True)
                print("[MMD Tools] 旧 mmd_motion プラグインをアンロードしました")
        except Exception:
            pass

    if hasattr(mc, "mmdFastImportPmxMesh") and hasattr(mc, "mmdFastImportVmdBone"):
        return True

    try:
        if mc.pluginInfo("mmd_fast", query=True, loaded=True) or mc.pluginInfo("mmd_fast.mll", query=True, loaded=True):
            if hasattr(mc, "mmdFastImportPmxMesh"):
                return True
    except Exception:
        pass

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    maya_ver = "2025"
    try:
        ver_str = str(mc.about(version=True))
        m = re.search(r"20\d{2}", ver_str)
        if m:
            maya_ver = m.group(0)
    except Exception:
        pass

    candidates = [
        os.path.join(base_dir, "plugins", "mmd_fast_plugin", "bin", maya_ver, "mmd_fast.mll"),
        os.path.join(base_dir, "plugins", "mmd_fast_plugin", "bin", "mmd_fast.mll"),
        os.path.join(base_dir, "plugins", "mmd_fast_plugin", "bin", "2025", "mmd_fast.mll"),
        os.path.join(base_dir, "mmd_fast_plugin", "bin", maya_ver, "mmd_fast.mll"),
        os.path.join(base_dir, "mmd_fast_plugin", "bin", "mmd_fast.mll"),
        os.path.join(base_dir, "mmd_fast_plugin", "bin", "2025", "mmd_fast.mll"),
    ]

    for mll_path in candidates:
        if os.path.exists(mll_path):
            try:
                mc.loadPlugin(mll_path)
                if hasattr(mc, "mmdFastImportPmxMesh"):
                    try:
                        mc.pluginInfo(mll_path, edit=True, autoload=True)
                        mc.pluginInfo("mmd_fast", edit=True, autoload=True)
                    except Exception:
                        pass
                    return True
            except Exception:
                pass

    return hasattr(mc, "mmdFastImportPmxMesh")

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
            color_array = om.MColorArray([om.MColor((float(s), 1.0, 0.0, 1.0)) for s in edge_scales])
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


def disable_mesh_edges(mesh_node):
    """
    指定されたメッシュ（スカイドームやステージ等）に対してエッジ描画を無効化します。
    - 割り当てられたシェーダー（mmdMaterial, mmdToonShader等）の edgeEnable を False、edgeSize を 0.0 に設定
    - 頂点カラーセット mmd_edge_scale を (0.0, 1.0, 0.0, 0.0) に更新（エッジ描画パスでのバイパス）
    """
    if not mesh_node or not mc.objExists(mesh_node):
        return
    try:
        shapes = mc.listRelatives(mesh_node, shapes=True, fullPath=True) or [mesh_node]
        for shp in shapes:
            if mc.nodeType(shp) != "mesh":
                continue
            # 接続されたシェーディンググループとマテリアルのエッジ属性を無効化
            sgs = mc.listConnections(shp, type="shadingEngine") or []
            for sg in set(sgs):
                shaders = mc.listConnections(f"{sg}.surfaceShader") or []
                for shd in shaders:
                    if mc.attributeQuery("edgeEnable", node=shd, exists=True):
                        try:
                            mc.setAttr(f"{shd}.edgeEnable", False)
                        except Exception:
                            pass
                    if mc.attributeQuery("edgeSize", node=shd, exists=True):
                        try:
                            mc.setAttr(f"{shd}.edgeSize", 0.0)
                        except Exception:
                            pass
                    if mc.attributeQuery("edgeColor", node=shd, exists=True):
                        try:
                            mc.setAttr(f"{shd}.edgeColor", 0.0, 0.0, 0.0, typ="double3")
                        except Exception:
                            pass

            # 頂点カラーセット mmd_edge_scale をスケール0.0（R=0.0, G=1.0, B=0.0, A=0.0）で更新
            try:
                sel = om.MSelectionList()
                sel.add(shp)
                dag = sel.getDagPath(0)
                fn_mesh = om.MFnMesh(dag)
                num_vtx = fn_mesh.numVertices
                num_polys = fn_mesh.numPolygons
                if num_vtx > 0:
                    cs_name = "mmd_edge_scale"
                    names = list(fn_mesh.getColorSetNames())
                    if cs_name not in names:
                        fn_mesh.createColorSet(cs_name, False, om.MFnMesh.kRGBA)
                    fn_mesh.setCurrentColorSetName(cs_name)
                    zero_colors = om.MColorArray([om.MColor((0.0, 1.0, 0.0, 0.0)) for _ in range(num_vtx)])
                    indices = om.MIntArray(range(num_vtx))
                    fn_mesh.setVertexColors(zero_colors, indices)

                    # 面頂点カラーもゼロ設定
                    if num_polys > 0:
                        colors = om.MColorArray()
                        face_ids = om.MIntArray()
                        vert_ids = om.MIntArray()
                        poly_verts = om.MIntArray()
                        for f in range(num_polys):
                            poly_verts.clear()
                            fn_mesh.getPolygonVertices(f, poly_verts)
                            for k in range(len(poly_verts)):
                                colors.append(om.MColor((0.0, 1.0, 0.0, 0.0)))
                                face_ids.append(f)
                                vert_ids.append(poly_verts[k])
                        fn_mesh.setFaceVertexColors(colors, face_ids, vert_ids)
                if mc.attributeQuery("displayColors", node=shp, exists=True):
                    mc.setAttr(f"{shp}.displayColors", 0)
            except Exception:
                pass
    except Exception:
        pass


def hide_viewport_grid():
    """
    ビューポートのグリッド線が表示されている場合、非表示に設定します。
    - 各 modelPanel のグリッド表示状態を確認し、表示中の場合は非表示化
    - Maya のグリッドコマンドで非表示を設定
    """
    try:
        model_panels = mc.getPanel(type='modelPanel') or []
        for panel in model_panels:
            try:
                if mc.modelEditor(panel, query=True, grid=True):
                    mc.modelEditor(panel, edit=True, grid=False)
            except Exception:
                pass
        try:
            if mc.grid(query=True, toggle=True):
                mc.grid(toggle=False)
        except Exception:
            try:
                mc.grid(display=False)
            except Exception:
                pass
    except Exception:
        pass


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

        # 足首ジョイントの既存orientConstraintおよび古いノードのエラーのないクリーンアップ
        toe_h_name = f"ikHandle_toe_{side_en}_{model_node}" if model_node else f"ikHandle_toe_{side_en}"
        if mc.objExists(toe_h_name):
            try:
                mc.delete(toe_h_name)
            except Exception:
                pass
        if ankle_j and mc.objExists(ankle_j):
            try:
                old_ankle_ocs = mc.listConnections(ankle_j, type="orientConstraint") or []
                if old_ankle_ocs:
                    mc.delete(old_ankle_ocs)
            except Exception:
                pass

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

                    # 脚IKハンドル（大腿〜ひざ〜足首）の構築
                    h_leg, _ = mc.ikHandle(startJoint=leg_j, endEffector=ankle_j, solver='ikRPsolver', name=h_name)
                    mc.pointConstraint(leg_ik_j, h_leg, maintainOffset=False)

                    # 足首の回転を足IKに追従させる（MMD仕様準拠）
                    # maintainOffset=False により、足IKの回転キー（Y回転等）を純粋に足首へそのまま伝達
                    oc_leg = mc.orientConstraint(leg_ik_j, ankle_j, maintainOffset=False)
                    if oc_leg:
                        try:
                            # 最短角度補間 (Shortest) を設定し、180度境界での反転フリップを抑制
                            mc.setAttr(f"{oc_leg[0]}.interpType", 2)
                        except Exception:
                            pass

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

        # つま先IKの処理
        # 足首ジョイントをstartJointとするikHandleは足首の回転を奪ってねじれ破綻させるため作成しない
        # つま先ジョイントへのつま先IK回転連動（つま先立ち・屈曲の反映）
        if toe_j and toe_ik_j and mc.objExists(toe_j) and mc.objExists(toe_ik_j):
            try:
                old_toe_ocs = mc.listConnections(toe_j, type="orientConstraint") or []
                if old_toe_ocs:
                    mc.delete(old_toe_ocs)
                oc_toe = mc.orientConstraint(toe_ik_j, toe_j, maintainOffset=False)
                if oc_toe:
                    try:
                        mc.setAttr(f"{oc_toe[0]}.interpType", 2)
                    except Exception:
                        pass
            except Exception as e:
                print(f"  [警告] つま先連動 ({side_jp}) の設定をスキップしました: {e}")

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

def _quat_from_euler_xyz(rx_deg, ry_deg, rz_deg):
    """XYZオイラー角から四元数を算出"""
    e = om.MEulerRotation(math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg), om.MEulerRotation.kXYZ)
    q = e.asQuaternion()
    return (q.x, q.y, q.z, q.w)

def _create_capsule_visualizer(radius, height, name):
    """円柱と両端半球を持つカプセルワイヤーフレームメッシュを生成"""
    r = max(0.01, float(radius))
    h = max(0.01, float(height))
    half_h = h * 0.5
    try:
        cyl = mc.polyCylinder(radius=r, height=h, subdivisionsX=12, subdivisionsY=1, subdivisionsCaps=0, constructionHistory=False)[0]
        sph_top = mc.polySphere(radius=r, subdivisionsX=12, subdivisionsY=8, constructionHistory=False)[0]
        mc.xform(sph_top, translation=(0.0, half_h, 0.0))
        sph_bottom = mc.polySphere(radius=r, subdivisionsX=12, subdivisionsY=8, constructionHistory=False)[0]
        mc.xform(sph_bottom, translation=(0.0, -half_h, 0.0))
        capsule = mc.polyUnite(cyl, sph_top, sph_bottom, constructionHistory=False, name=name)[0]
        return capsule
    except Exception:
        return mc.polyCylinder(radius=r, height=h, subdivisionsX=12, subdivisionsY=1, name=name, constructionHistory=False)[0]

def create_rigidbody_and_joint_nodes(pmx_model, model_mesh_node, joint_node_names, scale=8.0):
    """
    PMX剛体（球・箱・カプセル）およびJoint（6DOFスプリング関節）のワイヤーフレームを生成し、
    対応するジョイントに追従コンストレイントを設定します。
    モデル固有のグループ名を付与し、二重トランスフォーム防止のため inheritsTransform を False に設定します。
    """
    if not pmx_model or not getattr(pmx_model, 'rigid_bodies', None):
        return None

    # モデル固有のグループ名
    root_grp_name = f"{model_mesh_node}_RigidBody_Joint_Visualizers"
    rb_grp_name = f"{model_mesh_node}_RigidBody_Visualizers"
    joint_grp_name = f"{model_mesh_node}_Joint_Visualizers"

    if mc.objExists(root_grp_name):
        try:
            mc.delete(root_grp_name)
        except Exception:
            pass

    main_grp = mc.group(empty=True, name=root_grp_name)
    rb_grp = mc.group(empty=True, name=rb_grp_name, parent=main_grp)
    joint_grp = mc.group(empty=True, name=joint_grp_name, parent=main_grp)

    # 二重トランスフォーム防止: 剛体グループは親グループ移動を直接継承せずボーン追従に委ねる
    mc.setAttr(f"{main_grp}.inheritsTransform", False)

    # 剛体の生成
    for idx, rb in enumerate(pmx_model.rigid_bodies):
        rb_bind_p = (
            rb.position[0] * scale,
            rb.position[1] * scale,
            -rb.position[2] * scale
        )
        deg_x = -math.degrees(rb.rotation[0])
        deg_y = -math.degrees(rb.rotation[1])
        deg_z = math.degrees(rb.rotation[2])

        target_j = None
        if 0 <= rb.bone_index < len(joint_node_names):
            target_j = joint_node_names[rb.bone_index]

        safe_rb_name = safe_node_name(rb.name)
        node_name = f"{model_mesh_node}_rb_{idx:03d}_{safe_rb_name}"
        if mc.objExists(node_name):
            try:
                mc.delete(node_name)
            except Exception:
                pass

        mesh_node = None
        if rb.shape_type == 0:
            r = rb.size[0] * scale
            mesh_node = mc.polySphere(radius=max(0.1, r), subdivisionsX=12, subdivisionsY=8, name=node_name, constructionHistory=False)[0]
        elif rb.shape_type == 1:
            w = rb.size[0] * 2.0 * scale
            h = rb.size[1] * 2.0 * scale
            d = rb.size[2] * 2.0 * scale
            mesh_node = mc.polyCube(width=max(0.1, w), height=max(0.1, h), depth=max(0.1, d), name=node_name, constructionHistory=False)[0]
        elif rb.shape_type == 2:
            r = rb.size[0] * scale
            h = rb.size[1] * scale
            mesh_node = _create_capsule_visualizer(radius=r, height=h, name=node_name)

        if not mesh_node:
            continue

        mc.parent(mesh_node, rb_grp)
        mc.xform(mesh_node, worldSpace=True, translation=rb_bind_p)
        mc.xform(mesh_node, worldSpace=True, rotation=(deg_x, deg_y, deg_z))

        # ワイヤーフレーム表示設定
        shapes = mc.listRelatives(mesh_node, shapes=True) or []
        for shape in shapes:
            mc.setAttr(f"{shape}.overrideEnabled", 1)
            mc.setAttr(f"{shape}.overrideShading", 0)
            if rb.physics_mode == 0:
                color_idx = 6  # 青 (Kinematic)
            elif rb.physics_mode == 1:
                color_idx = 14 # 緑 (Dynamic)
            else:
                color_idx = 17 # 黄 (Aligned)
            mc.setAttr(f"{shape}.overrideColor", color_idx)

        mc.addAttr(mesh_node, longName="rbIndex", attributeType="short", defaultValue=idx)
        mc.addAttr(mesh_node, longName="rbMode", attributeType="short", defaultValue=rb.physics_mode)
        mc.addAttr(mesh_node, longName="rbGroup", attributeType="short", defaultValue=rb.group)

        # 対応ボーンへの追従コンストレイント設定
        if target_j and mc.objExists(target_j):
            try:
                c_res = mc.parentConstraint(target_j, mesh_node, maintainOffset=True)
                if c_res:
                    mc.addAttr(c_res[0], longName="isMmdPhysicsConstraint", attributeType="bool", defaultValue=True)
                    mc.addAttr(c_res[0], longName="rbMode", attributeType="short", defaultValue=rb.physics_mode)
            except Exception:
                pass

    # Joint（スプリング関節）の生成
    if hasattr(pmx_model, 'joints'):
        for j_idx, j in enumerate(pmx_model.joints):
            j_safe = safe_node_name(j.name)
            j_node_name = f"{model_mesh_node}_joint_{j_idx:03d}_{j_safe}"
            if mc.objExists(j_node_name):
                try:
                    mc.delete(j_node_name)
                except Exception:
                    pass

            j_bind_p = (
                j.position[0] * scale,
                j.position[1] * scale,
                -j.position[2] * scale
            )
            j_deg_x = -math.degrees(j.rotation[0])
            j_deg_y = -math.degrees(j.rotation[1])
            j_deg_z = math.degrees(j.rotation[2])

            cube_size = max(0.4, 0.15 * scale)
            cube = mc.polyCube(width=cube_size, height=cube_size, depth=cube_size, name=j_node_name, constructionHistory=False)[0]
            mc.parent(cube, joint_grp)
            mc.xform(cube, worldSpace=True, translation=j_bind_p)
            mc.xform(cube, worldSpace=True, rotation=(j_deg_x, j_deg_y, j_deg_z))

            cube_shape = mc.listRelatives(cube, shapes=True)[0]
            mc.setAttr(f"{cube_shape}.overrideEnabled", 1)
            mc.setAttr(f"{cube_shape}.overrideShading", 0)
            mc.setAttr(f"{cube_shape}.overrideColor", 17) # 黄色

            mc.addAttr(cube, longName="jointIndex", attributeType="short", defaultValue=j_idx)
            mc.addAttr(cube, longName="rbAIndex", attributeType="short", defaultValue=j.rigid_body_a)
            mc.addAttr(cube, longName="rbBIndex", attributeType="short", defaultValue=j.rigid_body_b)

            # 関連剛体Aのボーンにコンストレイント
            if 0 <= j.rigid_body_a < len(pmx_model.rigid_bodies):
                rb_a = pmx_model.rigid_bodies[j.rigid_body_a]
                if 0 <= rb_a.bone_index < len(joint_node_names):
                    target_j_a = joint_node_names[rb_a.bone_index]
                    if target_j_a and mc.objExists(target_j_a):
                        try:
                            c_res = mc.parentConstraint(target_j_a, cube, maintainOffset=True)
                            if c_res:
                                mc.addAttr(c_res[0], longName="isMmdJointConstraint", attributeType="bool", defaultValue=True)
                        except Exception:
                            pass

    print(f"  - 剛体 ({len(pmx_model.rigid_bodies)}個) および Joint ({len(getattr(pmx_model, 'joints', []))}個) のワイヤーフレームを生成しました")
    return main_grp

def create_rigidbody_visualizers(file_path_or_model, scale=8.0, model_mesh_node=None):
    """
    外部モジュールやスクリプト向けの互換インターフェース。
    指定されたPMXファイルまたはモデルから剛体・Joint可視化ノードを生成します。
    """
    if isinstance(file_path_or_model, str):
        model = mmd_parser.pmx.load(file_path_or_model)
        m_name = model_mesh_node or safe_node_name(os.path.splitext(os.path.basename(file_path_or_model))[0])
    else:
        model = file_path_or_model
        m_name = model_mesh_node or "MMD_Model"

    all_j = mc.ls(type="joint", long=True) or []
    model_j = [j for j in all_j if m_name in j] or all_j
    return create_rigidbody_and_joint_nodes(model, m_name, model_j, scale=scale)

def reconnect_visualizers_to_bones():
    """
    可視化ノード（剛体・Joint）に記録されたキーフレームをすべてクリアし、
    ボーン追従コンストレイントを通常状態（有効）に復元してモデルボーンに再吸着させます。
    """
    # シーン内の剛体・Joint可視化グループを検索
    vis_groups = mc.ls("*_RigidBody_Joint_Visualizers", "MMD_RigidBody_Joint_Visualizers", type="transform") or []
    if not vis_groups:
        print("[Visualizer] 剛体・Joint可視化グループが見つかりません。")
        return False

    # キーフレームの削除
    for grp in vis_groups:
        try:
            mc.cutKey(grp, hierarchy='below', attribute=['translateX', 'translateY', 'translateZ', 'rotateX', 'rotateY', 'rotateZ'])
        except Exception:
            pass

    # コンストレイントの追従復元 (PassThrough解除 & 通常状態設定)
    constraints = mc.ls(type=["parentConstraint", "pointConstraint", "orientConstraint"]) or []
    for c in constraints:
        is_rb = (
            (mc.attributeQuery("isMmdPhysicsConstraint", node=c, exists=True) and mc.getAttr(f"{c}.isMmdPhysicsConstraint")) or
            (mc.attributeQuery("isMmdRbConstraint", node=c, exists=True) and mc.getAttr(f"{c}.isMmdRbConstraint"))
        )
        is_jt = mc.attributeQuery("isMmdJointConstraint", node=c, exists=True) and mc.getAttr(f"{c}.isMmdJointConstraint")
        if is_rb or is_jt:
            try:
                # nodeState を Normal (0) に設定して追従を有効化
                mc.setAttr(f"{c}.nodeState", 0)
                mc.mute(c, disable=True)
            except Exception:
                pass

    print(f"[Visualizer] 剛体・Jointのキーフレームをクリアし、モデルボーンへの追従を復元しました（対象グループ数: {len(vis_groups)}）。")
    return True

def import_pmx(file_path, scale=8.0, split_by_material=False, create_blendshapes=True, create_joints=True, material_type=1, create_light=True, set_untone_mapped=True, enable_toon=True, shadow_mode=1, create_ground_shadow=True, show_completion_message=True, prevent_motion_darkening=True, create_physics=True, create_edge_mesh=True):
    """
    MMDモデルファイル (.pmx / .pmd / .x) をMayaにインポートします。

    引数:
        file_path (str): モデルファイルの絶対パス
        scale (float): スケール倍率（標準: 8.0）
        split_by_material (bool): 材質ごとにポリゴンメッシュを分割するかどうか
        create_blendshapes (bool): ブレンドシェイプ（モーフ）を作成するかどうか
        create_joints (bool): ジョイント（ボーンスケルトン）を作成するかどうか
        material_type (int): マテリアル種別 (0: なし, 1: Blinn, 2: Phong, 3: Lambert, 4: StandardSurface, 5: sample_mmd_mat ベータ版, 6: mmdToonShader)
        create_light (bool): MMD標準ライティング（平行光＆環境光）を作成するかどうか
        set_untone_mapped (bool): ビュー変換を 'Un-tone-mapped (sRGB)' に設定して発色を最適化するかどうか
        enable_toon (bool): Toonシェーディング（セル影）を適用するかどうか
        shadow_mode (int): セルフ影モード (0: なし, 1: モード1, 2: モード2)
        create_ground_shadow (bool): MMD標準の地面影プレーン (Y=0) を作成するかどうか
        prevent_motion_darkening (bool): モーション再生時の暗化を防止（シャッター開度0.01のブレなしHDRパス最適化）するかどうか
        create_physics (bool): 剛体・Jointコライダーのワイヤーフレームを生成しボーン追従バインドするかどうか
        create_edge_mesh (bool): 反転法線押し出し（Inverted Hull）方式によるエッジ輪郭線メッシュを生成するかどうか

    戻り値:
        tuple: (モデルノード名, ルートジョイント一覧, スキンクラスタ名, ブレンドシェイプ名)
    """
    start_time = time.time()
    ext = os.path.splitext(file_path)[1].lower() if file_path else ""
    print("==================================================")
    print(f"MMD モデルインポート開始: {os.path.basename(file_path)}")
    if ext == '.pmx':
        print("[PMXチェック] 事前チェック（未登録漢字・構成要素整合性）終了を確認")
    print("==================================================")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"モデルファイルが存在しません: {file_path}")

    # perspカメラの焦点距離をMMD標準画角に設定
    setup_persp_camera_for_mmd()

    # MMD標準ライティングの作成
    if create_light:
        create_mmd_lighting(shadow_mode=shadow_mode)

    # MMD標準地面影の作成 (Y=0平面シャドウキャッチャー)
    if create_ground_shadow:
        try:
            shadow_size = 500.0 * (scale / 8.0)
            create_mmd_ground_shadow(size=shadow_size)
        except Exception as e:
            print(f"[警告] 地面影プレーンの作成をスキップしました: {e}")

    # ビュー変換を Un-tone-mapped (sRGB) に設定して色の沈み・暗化を防止
    if set_untone_mapped:
        set_untone_mapped_view_transform()

    # ビューポートのテクスチャ表示、アンチエイリアシング、深度ピーリング、暗化防止を一括適用
    setup_viewport_display(shadow_mode=shadow_mode if create_light else None, prevent_motion_darkening=prevent_motion_darkening)

    # モデルファイルのロード
    print("[1/6] モデルファイルを読み込み中...")
    try:
        if ext == '.pmx':
            pmx_model = mmd_parser.pmx.load(file_path)
        elif ext == '.pmd':
            pmx_model = mmd_parser.pmd.load2pmx(file_path)
        elif ext == '.x':
            pmx_model = mmd_parser.x_file.load2pmx(file_path)
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

    # モデルノード名の堅牢な決定（中国語モデル・英名フォールバック対応）
    model_name_e = getattr(pmx_model, 'name_e', None)
    base_model_name = safe_node_name(pmx_model.name, name_e=model_name_e, prefix="MMD_Model")
    if not base_model_name or base_model_name == 'node':
        file_base = os.path.splitext(os.path.basename(file_path))[0]
        base_model_name = safe_node_name(file_base, prefix="MMD_Model")

    model_node_name = _get_unique_node_name(base_model_name)
    root_joint_names = []
    skin_node_name = None
    blendshape_node_name = None

    # スカイドーム / ステージモデルの事前判別
    is_skydome_model = False
    is_stage_model = False
    try:
        try:
            from ..asset.model_classifier_manager import ModelClassifierManager
        except Exception:
            from asset.model_classifier_manager import ModelClassifierManager
        classifier_mgr = ModelClassifierManager.get_instance()
        override_type = classifier_mgr.get_file_override(file_path)
        if override_type == 'skydome':
            is_skydome_model = True
        elif override_type == 'stage':
            is_stage_model = True
        else:
            fp_norm = (file_path or '').lower().replace('\\', '/')
            m_name_low = (getattr(pmx_model, 'name', '') or '').lower()
            m_name_e_low = (getattr(pmx_model, 'name_e', '') or '').lower()
            check_text = f"{fp_norm} {m_name_low} {m_name_e_low}"
            if any(k.lower() in check_text for k in classifier_mgr.skydome_keywords):
                is_skydome_model = True
            elif any(k.lower() in check_text for k in classifier_mgr.stage_keywords):
                is_stage_model = True
    except Exception:
        pass
    is_background_or_stage = is_skydome_model or is_stage_model

    # ポリゴンメッシュの生成
    print("[2/6] ポリゴンメッシュを作成中...")
    cpp_mat_valid_faces = None
    is_pmx_file = file_path.lower().endswith('.pmx')
    use_cpp_fast = False
    if is_pmx_file and not split_by_material:
        use_cpp_fast = ensure_mmd_fast_plugin_loaded()

    if split_by_material:
        material_mesh_nodes = []
    else:
        mesh_created_by_cpp = False
        if use_cpp_fast and hasattr(mc, "mmdFastImportPmxMesh"):
            try:
                cpp_res = mc.mmdFastImportPmxMesh(file_path, model_node_name, float(scale))
                if cpp_res and len(cpp_res) >= 1 and mc.objExists(cpp_res[0]):
                    model_mesh_node = cpp_res[0]
                    cpp_mat_valid_faces = [int(x) for x in cpp_res[1:]]
                    try:
                        mc.setAttr(f"{model_mesh_node}.aiOpaque", 0)
                    except Exception:
                        pass
                    mesh_created_by_cpp = True
                    print("  - C++ (mmd_fast.mll) によるメッシュ一括高速生成を実行しました")
            except Exception as e_cpp:
                print(f"  [情報] C++ メッシュ生成から Python フォールバックへ切り替えました: {e_cpp}")
                mesh_created_by_cpp = False

        if not mesh_created_by_cpp:
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
                # スカイドーム・ステージモデルまたはアルファ微小材質はエッジを一律無効化
                if is_background_or_stage or m_alpha <= 0.05:
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

        # メッシュ寸法・バウンディングボックスによるスカイドーム / ステージの追加判別
        if not is_skydome_model and is_skydome_mesh(model_mesh_node, file_path=file_path):
            is_skydome_model = True
        if not is_skydome_model and not is_stage_model:
            try:
                try:
                    from ..asset.model_classifier_manager import ModelClassifierManager
                except Exception:
                    from asset.model_classifier_manager import ModelClassifierManager
                mgr = ModelClassifierManager.get_instance()
                if mgr.is_stage_mesh(model_mesh_node, file_path=file_path):
                    is_stage_model = True
            except Exception:
                pass

        is_background_or_stage = is_skydome_model or is_stage_model

        # スカイドームまたはステージモデルの場合、エッジ描画を無効化
        if is_background_or_stage:
            disable_mesh_edges(model_mesh_node)

        # キャラクターメッシュで前髪・首元・襟などの落ち影（セルフシャドウ）を受け取るため receiveShadows を有効化
        mesh_shapes = mc.listRelatives(model_mesh_node, shapes=True, fullPath=True) or [model_mesh_node]
        for m_shp in mesh_shapes:
            try:
                if is_skydome_model:
                    mc.setAttr(f"{m_shp}.receiveShadows", 0)
                    mc.setAttr(f"{m_shp}.castsShadows", 0)
                else:
                    mc.setAttr(f"{m_shp}.receiveShadows", 1)
                    mc.setAttr(f"{m_shp}.castsShadows", 1)
                # シェーダーの Pass 1（裏面エッジ描画）を破棄させないための設定
                mc.setAttr(f"{m_shp}.doubleSided", 1)
                mc.setAttr(f"{m_shp}.opposite", 0)
                mc.setAttr(f"{m_shp}.backfaceCulling", 0)
            except Exception:
                pass

        if material_type == 0:
            mc.select(model_mesh_node)
            mc.hyperShade(assign='lambert1')

    # テクスチャおよびマテリアルの作成
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

    # MMD統合マテリアルプラグイン (mmd_material.mll: mmdMaterial / mmdToonShader 内包) のロード
    if material_type in (5, 6):
        if not mc.pluginInfo("mmd_material", query=True, loaded=True):
            try:
                mc.loadPlugin("mmd_material")
                print("[MMD Tools for Maya] mmd_material プラグインをロードしました。")
                try:
                    mc.pluginInfo("mmd_material", edit=True, autoload=True)
                except Exception:
                    pass
            except Exception as e:
                # Maya.env未反映時のフルパスフォールバック
                plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                maya_ver = mc.about(version=True).split()[0] if hasattr(mc, 'about') else '2025'
                candidate_paths = [
                    os.path.join(plugin_root, "plugins", "mmd_material_plugin", "bin", "mmd_material.mll"),
                    os.path.join(plugin_root, "plugins", "mmd_material_plugin", "bin", maya_ver, "mmd_material.mll"),
                    os.path.join(plugin_root, "plugins", "mmd_material_plugin", "bin", "2025", "mmd_material.mll"),
                    os.path.join(plugin_root, "mmd_material_plugin", "bin", "mmd_material.mll"),
                    os.path.join(plugin_root, "mmd_material_plugin", "bin", maya_ver, "mmd_material.mll"),
                    os.path.join(plugin_root, "mmd_material_plugin", "bin", "2025", "mmd_material.mll"),
                ]
                loaded = False
                for mll_path in candidate_paths:
                    if os.path.exists(mll_path):
                        try:
                            mc.loadPlugin(mll_path)
                            print(f"[MMD Tools for Maya] mmd_material プラグインを絶対パスからロードしました: {mll_path}")
                            loaded = True
                            try:
                                mc.pluginInfo(mll_path, edit=True, autoload=True)
                                mc.pluginInfo("mmd_material", edit=True, autoload=True)
                            except Exception:
                                pass
                            break
                        except Exception:
                            pass
                if not loaded:
                    print(f"[警告] mmd_material プラグインのロードに失敗しました: {e}")

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
    toon_bundle_cache = {}
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

        # シーン内のMMDディレクショナルライトから動的に光線方向ベクトルを取得・接続
        dir_lights = mc.ls("mmd_directional_light*", type='transform') or mc.ls(type='directionalLight') or []
        target_dir_light = dir_lights[0] if dir_lights else None
        if target_dir_light and mc.nodeType(target_dir_light) == 'directionalLight':
            target_dir_light = (mc.listRelatives(target_dir_light, parent=True, fullPath=True) or [None])[0]

        if target_dir_light and mc.objExists(target_dir_light):
            # ライトのワールドマトリクスからオブジェクトへの到来光線ベクトル（ローカル+Z）を動的算出
            light_vec_node = mc.shadingNode('vectorProduct', asUtility=True, name=f"toon_lvec_{model_node_name}")
            mc.setAttr(f"{light_vec_node}.operation", 3) # Vector Matrix Product (V * M)
            mc.setAttr(f"{light_vec_node}.normalizeOutput", True)
            mc.setAttr(f"{light_vec_node}.input1", 0.0, 0.0, 1.0, typ='double3')
            mc.connectAttr(f"{target_dir_light}.worldMatrix[0]", f"{light_vec_node}.matrix", force=True)
            mc.connectAttr(f"{light_vec_node}.output", f"{toon_vec_prod}.input2", force=True)
        else:
            # フォールバック: 顔・首・襟元の落ち影を自然に出す正面斜め上ライト [-25.0, 20.0, 0.0] の単位方向ベクトル
            mc.setAttr(f"{toon_vec_prod}.input2", 0.3099, 0.4226, 0.8517, typ='double3')

        mc.connectAttr(f"{toon_world_norm}.output", f"{toon_vec_prod}.input1", force=True)

        # 内積結果をMMD準拠の遷移幅（-0.05〜0.35）から 0.0〜1.0 の連続ブレンド率へマッピングし、
        # 境目を作らず自然に広がりつつ各材質のToon影色がしっかり発色する陰影を生成
        mc.setAttr(f"{toon_range_node}.minX", 0.0)
        mc.setAttr(f"{toon_range_node}.maxX", 1.0)
        mc.setAttr(f"{toon_range_node}.oldMinX", -0.05)
        mc.setAttr(f"{toon_range_node}.oldMaxX", 0.35)
        mc.connectAttr(f"{toon_vec_prod}.outputX", f"{toon_range_node}.valueX", force=True)

    def _get_or_create_toon_bundle(t_path, tag_prefix):
        """
        解決済みのToonテクスチャパスから、本家MMDセルフシャドウ方式に準拠して
        テクスチャ下端(v=0.05)の影色を抽出し、blendColorsで明部(1,1,1)と連続補間するノード群を生成・キャッシュします。
        Viewport 2.0でメッシュUV(map1)が自動バインドされて白い上半分(v>0.5)を参照してしまう現象を防ぐため、
        repeatUV=(0,0), offset=(0.5, 0.05) に固定した専用 place2dTexture を接続します。
        """
        if not t_path or not os.path.isfile(t_path):
            return None
        norm_key = os.path.normcase(os.path.normpath(t_path))
        if norm_key in toon_bundle_cache:
            return toon_bundle_cache[norm_key]

        ramp_node = mc.shadingNode('file', asTexture=True, name=f"{tag_prefix}_file_{model_node_name}")
        mc.setAttr(f"{ramp_node}.ftn", t_path, typ='string')
        toon_p2d = mc.shadingNode('place2dTexture', asUtility=True, name=f"{tag_prefix}_place2d_{model_node_name}")
        for src_attr, dst_attr in PLACE2D_ATTR_CONNECTIONS:
            try:
                mc.connectAttr(f"{toon_p2d}.{src_attr}", f"{ramp_node}.{dst_attr}", force=True)
            except Exception:
                pass
        try:
            # メッシュUVに依存せず常にToon画像最下端(u=0.5, v=0.05)の影色をサンプリングするよう固定
            mc.setAttr(f"{toon_p2d}.wrapU", False)
            mc.setAttr(f"{toon_p2d}.wrapV", False)
            mc.setAttr(f"{toon_p2d}.repeatU", 0.0)
            mc.setAttr(f"{toon_p2d}.repeatV", 0.0)
            mc.setAttr(f"{toon_p2d}.offsetU", 0.5)
            mc.setAttr(f"{toon_p2d}.offsetV", 0.05)
            mc.setAttr(f"{ramp_node}.wrapU", False)
            mc.setAttr(f"{ramp_node}.wrapV", False)
        except Exception:
            pass

        blend_node = mc.shadingNode('blendColors', asUtility=True, name=f"{tag_prefix}_blend_{model_node_name}")
        mc.setAttr(f"{blend_node}.color1", 1.0, 1.0, 1.0, typ='double3')
        mc.connectAttr(f"{ramp_node}.outColor", f"{blend_node}.color2", force=True)
        if toon_range_node:
            mc.connectAttr(f"{toon_range_node}.outValueX", f"{blend_node}.blender", force=True)
        else:
            mc.setAttr(f"{blend_node}.blender", 1.0)

        shadow_srgb = _extract_toon_shadow_color(t_path)
        bundle = {
            'ramp': ramp_node,
            'place2d': toon_p2d,
            'blend_toon': blend_node,
            'path': t_path,
            'shadow_srgb': shadow_srgb,
        }
        toon_bundle_cache[norm_key] = bundle
        return bundle

    # 共有トゥーンテクスチャ (toon01.bmp〜toon10.bmp、モデル同梱優先) のバンドル生成
    shared_toon_file_nodes = {}
    shared_toon_bundles = {}
    if enable_toon:
        for i in range(10):
            t_path = _get_shared_toon_path(i, model_dir=model_dir)
            if t_path and os.path.isfile(t_path):
                bundle = _get_or_create_toon_bundle(t_path, f"toon{i+1:02d}")
                if bundle:
                    shared_toon_file_nodes[i] = bundle['ramp']
                    shared_toon_bundles[i] = bundle

    # モデルの主要材質で使用されているToon影色を特定し、落ち影（セルフシャドウ）用ライトへ反映
    active_amb_rgb, active_dir_rgb = (0.75, 0.75, 0.75), (0.25, 0.25, 0.25)
    if enable_toon:
        toon_weight_counts = {}
        toon_path_map = {}
        for m in pmx_model.materials:
            v_cnt = getattr(m, 'vertex_count', 0)
            if v_cnt <= 0:
                continue
            t_idx = getattr(m, 'toon_texture', -1)
            is_sh = getattr(m, 'is_shared_toon_texture', False)
            resolved_tp = None
            if is_sh:
                if t_idx in shared_toon_bundles:
                    resolved_tp = shared_toon_bundles[t_idx]['path']
                elif (t_idx - 1) in shared_toon_bundles:
                    resolved_tp = shared_toon_bundles[t_idx - 1]['path']
            elif not is_sh and 0 <= t_idx < len(pmx_model.textures):
                resolved_tp = _resolve_custom_toon_path(pmx_model.textures[t_idx].path, model_dir=model_dir)
            if resolved_tp:
                n_key = os.path.normcase(os.path.normpath(resolved_tp))
                toon_weight_counts[n_key] = toon_weight_counts.get(n_key, 0) + v_cnt
                toon_path_map[n_key] = resolved_tp
        if toon_weight_counts:
            dominant_key = max(toon_weight_counts, key=toon_weight_counts.get)
            dominant_toon_path = toon_path_map[dominant_key]
            dominant_srgb = _extract_toon_shadow_color(dominant_toon_path)
            active_amb_rgb, active_dir_rgb = _apply_toon_color_to_mmd_lights(dominant_srgb)

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

    # MMDマテリアル・Toonプラグイン選択時は事前にロードを確認
    if material_type in (5, 6):
        try:
            try:
                from ..plugins.mmd_material_plugin.scripts.mmd_material_setup import ensure_plugin_loaded
            except Exception:
                try:
                    from plugins.mmd_material_plugin.scripts.mmd_material_setup import ensure_plugin_loaded
                except Exception:
                    try:
                        from ..mmd_material_plugin.scripts.mmd_material_setup import ensure_plugin_loaded
                    except Exception:
                        from mmd_material_plugin.scripts.mmd_material_setup import ensure_plugin_loaded
            if not ensure_plugin_loaded():
                is_mat_loaded = mc.pluginInfo("mmd_material", query=True, loaded=True) or mc.pluginInfo("mmd_material.mll", query=True, loaded=True)
                is_toon_loaded = mc.pluginInfo("mmd_toon_shader", query=True, loaded=True) or mc.pluginInfo("mmd_toon_shader.mll", query=True, loaded=True)
                if not (is_mat_loaded or is_toon_loaded):
                    print("[MMD Tools] MMDシェーダープラグイン (mmd_material) をロードできなかったため、StandardSurfaceにフォールバックします。")
                    material_type = 4
        except Exception as e:
            is_mat_loaded = mc.pluginInfo("mmd_material", query=True, loaded=True) or mc.pluginInfo("mmd_material.mll", query=True, loaded=True)
            is_toon_loaded = mc.pluginInfo("mmd_toon_shader", query=True, loaded=True) or mc.pluginInfo("mmd_toon_shader.mll", query=True, loaded=True)
            if not (is_mat_loaded or is_toon_loaded):
                print(f"[MMD Tools] プラグインロード確認中にエラーが発生したためフォールバックします: {e}")
                material_type = 4

    material_shader_dict = {}
    material_alpha_mult_dict = {}
    material_color_source_dict = {}
    material_tex_node_dict = {}
    material_has_alpha_morph_dict = {}

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
        # MMD標準の受光特性に合わせ、アンビエント色の上限を0.60に保護クランプ
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
        # 材質モーフの対象となっているか判定
        has_mat_morph_target = False
        for morph in getattr(pmx_model, 'morphs', []):
            if getattr(morph, 'morph_type', 0) == 8 or (hasattr(morph, 'type_index') and morph.type_index() == 8):
                for off in getattr(morph, 'offsets', []):
                    if off[0] == mat_idx or off[0] == -1:
                        has_mat_morph_target = True
                        break
                if has_mat_morph_target:
                    break

        # 顔オーバーレイ板ポリゴン（チーク・涙・顔斜線等）の判定
        overlay_kw = ["頬", "cheek", "照れ", "blush", "涙", "tear", "斜線", "ガーン", "gaan"]
        is_face_overlay_mat = any(k in mat_name_for_kw or k in mat_e_for_kw for k in overlay_kw)

        is_transparent_morph_mat = (alpha <= 0.05) and has_mat_morph_target
        if is_transparent_morph_mat and is_face_overlay_mat:
            # 顔透過板ポリゴンのみ受光漏れ・白枠線防止のためアンビエント・スペキュラを遮断
            ambient_color = [0.0, 0.0, 0.0]
            specular_color = [0.0, 0.0, 0.0]
            spec_factor = 0.0
            transparency = [1.0, 1.0, 1.0]
            opacity = [0.0, 0.0, 0.0]
        elif is_transparent_morph_mat:
            # 素肌（T_肌3）や衣装（T_下着2）等の独立本体メッシュは、影の黒沈み防止のため本来のアンビエント色・スペキュラ色を維持
            transparency = [1.0, 1.0, 1.0]
            opacity = [0.0, 0.0, 0.0]
        elif alpha <= 0.05 and not has_mat_morph_target:
            # 材質モーフがなく頂点モーフ等で手前展開される材質の場合、透明固定を回避して可視化を保証
            opacity = [1.0, 1.0, 1.0]
            transparency = [0.0, 0.0, 0.0]

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

        # エッジ描画フラグの取得
        is_edge_enabled = bool(getattr(mat, 'draw_flags', 0x10) & 0x10) if hasattr(mat, 'draw_flags') else (getattr(mat, 'edge_flag', 1) != 0)
        edge_size_val = min(10.0, max(0.0, float(getattr(mat, 'edge_size', 1.0))))
        edge_col_val = list(getattr(mat, 'edge_color', [0.0, 0.0, 0.0, 1.0]))
        # スカイドームまたはステージモデルはエッジ描画を対象外（無効化）に設定
        if is_background_or_stage:
            is_edge_enabled = False
            edge_size_val = 0.0
            edge_col_val = [0.0, 0.0, 0.0, 0.0]
        # モーフ対象の初期透明材質でも、PMX本来のエッジ描画設定を保持
        # エッジ描画時の不可視化を防止するためアルファ1.0を担保
        elif is_transparent_morph_mat:
            if len(edge_col_val) >= 4 and edge_col_val[3] <= 0.05:
                edge_col_val[3] = 1.0

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
            if is_transparent_morph_mat and is_face_overlay_mat:
                mc.setAttr(f"{shd}.base", 0.0)
            elif enable_toon:
                # 2重受光による黒沈み防止
                mc.setAttr(f"{shd}.base", 0.85)
            else:
                mc.setAttr(f"{shd}.base", 0.95)
        elif material_type in (5, 6): # MMDオリジナルシェーダー (Viewport 2.0 2パス Inverted Hull 描画エンジン)
            try:
                # 2パス Inverted Hull エッジ描画エンジン (MMDShaderOverride) を持つ mmdMaterial を優先生成
                shd = mc.shadingNode('mmdMaterial', asShader=True, name=shader_node_name)
            except Exception:
                try:
                    shd = mc.shadingNode('mmdToonShader', asShader=True, name=shader_node_name)
                except Exception:
                    shd = mc.shadingNode('standardSurface', asShader=True, name=shader_node_name)

            if mc.attributeQuery('diffuseColor', node=shd, exists=True):
                mc.setAttr(f"{shd}.diffuseColor", *diffuse_color, typ='double3')
                mc.setAttr(f"{shd}.color", *diffuse_color, typ='double3')
                # 白飛び防止: Maya Phongでの自己発光的な加算を排除し、適正な陰影を維持
                mc.setAttr(f"{shd}.ambientColor", 0.0, 0.0, 0.0, typ='double3')
                mc.setAttr(f"{shd}.transparency", *transparency, typ='double3')
                mc.setAttr(f"{shd}.diffuseAlpha", alpha)
                if is_face_material or is_transparent_morph_mat or sum(specular_color) < 0.05:
                    mc.setAttr(f"{shd}.specularColor", 0.0, 0.0, 0.0, typ='double3')
                else:
                    mc.setAttr(f"{shd}.specularColor", *specular_color, typ='double3')
                mc.setAttr(f"{shd}.specularPower", min(100.0, max(1.0, float(spec_factor))))
                mc.setAttr(f"{shd}.cosinePower", min(100.0, max(2.0, float(spec_factor))))
                mc.setAttr(f"{shd}.diffuse", 0.0 if (is_transparent_morph_mat and is_face_overlay_mat) else 1.0)

                sph_idx = getattr(mat, 'sphere_texture', -1)
                sph_mode = getattr(mat, 'sphere_texture_mode', 0)
                if mc.attributeQuery('sphereMode', node=shd, exists=True):
                    mc.setAttr(f"{shd}.sphereMode", int(sph_mode))
                if mc.attributeQuery('toonMode', node=shd, exists=True):
                    mc.setAttr(f"{shd}.toonMode", 1 if enable_toon else 0)
                if mc.attributeQuery('lightMode', node=shd, exists=True):
                    mc.setAttr(f"{shd}.lightMode", 1) # MMD基準輝度モード
                if mc.attributeQuery('shadowMode', node=shd, exists=True):
                    mc.setAttr(f"{shd}.shadowMode", 1) # MMD深度差判定モード

                # エッジ（輪郭線）パラメータの設定
                if mc.attributeQuery('edgeEnable', node=shd, exists=True):
                    mc.setAttr(f"{shd}.edgeEnable", is_edge_enabled)
                if len(edge_col_val) >= 3 and mc.attributeQuery('edgeColor', node=shd, exists=True):
                    mc.setAttr(f"{shd}.edgeColor", edge_col_val[0], edge_col_val[1], edge_col_val[2], typ='double3')
                if mc.attributeQuery('edgeSize', node=shd, exists=True):
                    mc.setAttr(f"{shd}.edgeSize", edge_size_val)
            else:
                if mc.attributeQuery('baseColor', node=shd, exists=True):
                    mc.setAttr(f"{shd}.baseColor", *diffuse_color, typ='double3')
                elif mc.attributeQuery('color', node=shd, exists=True):
                    mc.setAttr(f"{shd}.color", *diffuse_color, typ='double3')

        material_shader_dict[mat_idx] = shd

        if material_type in [1, 2, 3]:
            mc.setAttr(f"{shd}.color", *diffuse_color, typ='double3')
            mc.setAttr(f"{shd}.ambientColor", 0.0, 0.0, 0.0, typ='double3')
            mc.setAttr(f"{shd}.transparency", *transparency, typ='double3')
            if is_transparent_morph_mat and is_face_overlay_mat:
                if mc.attributeQuery('diffuse', node=shd, exists=True):
                    mc.setAttr(f"{shd}.diffuse", 0.0)
                if mc.attributeQuery('shadowAttenuation', node=shd, exists=True):
                    mc.setAttr(f"{shd}.shadowAttenuation", 0.0)
            else:
                if mc.attributeQuery('diffuse', node=shd, exists=True):
                    mc.setAttr(f"{shd}.diffuse", 1.0)

        # 日本語・中国語の元名称を保持
        mc.addAttr(shd, longName='originalName', niceName='元の名称', dataType='string')
        mc.setAttr(f"{shd}.originalName", mat.name, typ='string')

        # カラー出力ソースの初期化
        current_color_source = None
        if 0 <= tex_idx < len(texture_file_nodes) and mc.objExists(texture_file_nodes[tex_idx]):
            current_color_source = f"{texture_file_nodes[tex_idx]}.outColor"

        # スフィアマップの解決と MatCap UV 接続 (place2dTextureとのUV競合を解除してカメラ空間法線UVを適用)
        sphere_idx = getattr(mat, 'sphere_texture', -1)
        sphere_mode = getattr(mat, 'sphere_texture_mode', 0)
        sphere_node = None
        if 0 <= sphere_idx < len(texture_file_nodes) and sphere_mode in [1, 2]:
            candidate_sph = texture_file_nodes[sphere_idx]
            if mc.objExists(candidate_sph):
                sphere_node = candidate_sph
                if matcap_range_node:
                    try:
                        # 親複合アトリビュート uvCoord への place2dTexture.outUV 接続を解除して MatCap UV の上書き競合を防止
                        uv_conns = mc.listConnections(f"{sphere_node}.uvCoord", source=True, destination=False, plugs=True) or []
                        for src_p in uv_conns:
                            try:
                                mc.disconnectAttr(src_p, f"{sphere_node}.uvCoord")
                            except Exception:
                                pass
                        filter_conns = mc.listConnections(f"{sphere_node}.uvFilterSize", source=True, destination=False, plugs=True) or []
                        for src_f in filter_conns:
                            try:
                                mc.disconnectAttr(src_f, f"{sphere_node}.uvFilterSize")
                            except Exception:
                                pass
                        mc.setAttr(f"{sphere_node}.wrapU", False)
                        mc.setAttr(f"{sphere_node}.wrapV", False)
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

        # Toonマップ (モデル同梱Toon最優先・共有toonフォルダフォールバック) 
        toon_node = None
        toon_bundle = None
        if enable_toon:
            toon_idx = getattr(mat, 'toon_texture', -1)
            is_shared_toon = getattr(mat, 'is_shared_toon_texture', False)
            if is_shared_toon:
                if toon_idx in shared_toon_bundles:
                    toon_bundle = shared_toon_bundles[toon_idx]
                    toon_node = toon_bundle['ramp']
                elif (toon_idx - 1) in shared_toon_bundles:
                    toon_bundle = shared_toon_bundles[toon_idx - 1]
                    toon_node = toon_bundle['ramp']
            elif not is_shared_toon and 0 <= toon_idx < len(pmx_model.textures):
                custom_toon_path = _resolve_custom_toon_path(pmx_model.textures[toon_idx].path, model_dir=model_dir)
                if custom_toon_path and os.path.isfile(custom_toon_path):
                    toon_bundle = _get_or_create_toon_bundle(custom_toon_path, f"{safe_mat_id}_custoon")
                    if toon_bundle:
                        toon_node = toon_bundle['ramp']
            # 万一Toon指定が未解決の場合でも共有toon01が存在すればフォールバック利用
            if toon_bundle is None and 0 in shared_toon_bundles:
                toon_bundle = shared_toon_bundles[0]
                toon_node = toon_bundle['ramp']

        # 各マテリアル種別（mmdToonShader / mmdMaterial / StandardSurface 含む）に対してToonと落ち影を統合合成
        is_toon_bypass = False
        try:
            try:
                from ..asset.user_dict_manager import is_toon_bypass_material
            except Exception:
                from asset.user_dict_manager import is_toon_bypass_material
            is_toon_bypass = is_toon_bypass_material(mat.name, getattr(mat, 'name_e', ''))
        except Exception:
            is_toon_bypass = any(k in mat.name.lower() for k in ["瞳-高光", "高光", "眼白", "highlight"])

        # 白目・瞳ハイライト等、前髪の落ち影（セルフシャドウ）による黒沈みを防ぐため意図的に遮断すべき白色極小パーツの判定
        # 服・肌・髪等のメッシュは白ハイライト補色の対象外として保護
        white_hl_keywords = ["瞳-高光", "高光", "眼白", "白目", "highlight"]
        general_mesh_keywords = ["服", "cloth", "dress", "shirt", "skirt", "肌", "skin", "body", "髪", "hair", "帽子", "靴", "リボン"]
        mat_n_lower = (mat.name or "").lower()
        mat_ne_lower = (getattr(mat, 'name_e', '') or "").lower()
        is_white_highlight_part = any(k in mat_n_lower or k in mat_ne_lower for k in white_hl_keywords)
        if any(k in mat_n_lower or k in mat_ne_lower for k in general_mesh_keywords):
            is_white_highlight_part = False

        cutout_and_overlay_kw = ["まつげ", "睫毛", "lash", "アイライン", "ハイライト", "高光", "涙", "tear", "眉", "brow", "二重"]
        is_cutout_or_overlay = (
            any(k in mat_name_for_kw or k in mat_e_for_kw for k in cutout_and_overlay_kw)
            or is_face_overlay_mat
            or is_transparent_morph_mat
            or (alpha < 0.98)
        )
        mat_receives_shadow = bool(getattr(mat, 'draw_flags', 0x08) & 0x08)

        base_color_before_toon = current_color_source

        # Toon階調テクスチャの乗算処理（Toon除外設定時はスキップし、本来のテクスチャ色を維持）
        if enable_toon and toon_bundle and not is_toon_bypass:
            toon_mult = mc.shadingNode('multiplyDivide', asUtility=True, name=f"{safe_mat_id}_toon_mult_{model_node_name}")
            mc.setAttr(f"{toon_mult}.operation", 1) # Multiply
            if base_color_before_toon:
                mc.connectAttr(base_color_before_toon, f"{toon_mult}.input1", force=True)
            else:
                mc.setAttr(f"{toon_mult}.input1", *diffuse_color, typ='double3')

            if toon_bundle.get('blend_toon'):
                # 本家MMDセルフシャドウ方式: 下端影色(v=0.05)と明部(1,1,1)を連続補間したブレンド出力を乗算
                mc.connectAttr(f"{toon_bundle['blend_toon']}.output", f"{toon_mult}.input2", force=True)
            else:
                mc.connectAttr(f"{toon_node}.outColor", f"{toon_mult}.input2", force=True)

            current_color_source = f"{toon_mult}.output"

        # シェーダーの受光率（diffuse）と環境光（ambientColor）の設定
        if material_type in [1, 2, 3, 5, 6]:
            if is_transparent_morph_mat and is_face_overlay_mat:
                if mc.attributeQuery('ambientColor', node=shd, exists=True):
                    mc.setAttr(f"{shd}.ambientColor", 0.0, 0.0, 0.0, typ='double3')
                if mc.attributeQuery('diffuse', node=shd, exists=True):
                    mc.setAttr(f"{shd}.diffuse", 0.0)
            elif is_white_highlight_part and not (is_transparent_morph_mat and is_face_overlay_mat):
                # 瞳ハイライト・白目等は前髪の落ち影で暗くならないよう diffuse=0、環境光と合算で純白になる補色を設定
                if mc.attributeQuery('ambientColor', node=shd, exists=True):
                    mc.setAttr(f"{shd}.ambientColor", active_dir_rgb[0], active_dir_rgb[1], active_dir_rgb[2], typ='double3')
                if mc.attributeQuery('diffuse', node=shd, exists=True):
                    mc.setAttr(f"{shd}.diffuse", 0.0)
            elif not mat_receives_shadow and not is_cutout_or_overlay and is_white_highlight_part:
                if mc.attributeQuery('ambientColor', node=shd, exists=True):
                    mc.setAttr(f"{shd}.ambientColor", active_dir_rgb[0], active_dir_rgb[1], active_dir_rgb[2], typ='double3')
                if mc.attributeQuery('diffuse', node=shd, exists=True):
                    mc.setAttr(f"{shd}.diffuse", 0.0)
            else:
                # 服や肌、髪など通常の材質（Toon除外された一般材質を含む）は常に適正な diffuse=1.0 と自己発光しない ambientColor=0.0 を設定
                if mc.attributeQuery('ambientColor', node=shd, exists=True):
                    mc.setAttr(f"{shd}.ambientColor", 0.0, 0.0, 0.0, typ='double3')
                if mc.attributeQuery('diffuse', node=shd, exists=True):
                    mc.setAttr(f"{shd}.diffuse", 1.0)
        elif material_type == 4:
            if mc.attributeQuery('base', node=shd, exists=True):
                mc.setAttr(f"{shd}.base", 0.0 if (is_transparent_morph_mat and is_face_overlay_mat) else 1.0)

        # 加算スフィア (モード 2: .spa、sp\spa-cloth.bmp等) を本家MMD準拠でカラーパイプラインへ直接加算合成
        # これにより mmdToonShader / mmdMaterial を含む各シェーダーの Viewport 2.0 描画で加算スフィアが確実に反映される
        if sphere_node and sphere_mode == 2:
            sph_add_node = mc.shadingNode('plusMinusAverage', asUtility=True, name=f"{safe_mat_id}_sph_add_{model_node_name}")
            mc.setAttr(f"{sph_add_node}.operation", 1) # Sum (加算)
            if current_color_source:
                mc.connectAttr(current_color_source, f"{sph_add_node}.input3D[0]", force=True)
            else:
                mc.setAttr(f"{sph_add_node}.input3D[0]", *diffuse_color, typ='double3')
            mc.connectAttr(f"{sphere_node}.outColor", f"{sph_add_node}.input3D[1]", force=True)
            current_color_source = f"{sph_add_node}.output3D"

        # カラー出力ソースの保持
        material_color_source_dict[mat_idx] = current_color_source
        if 0 <= tex_idx < len(texture_file_nodes) and mc.objExists(texture_file_nodes[tex_idx]):
            material_tex_node_dict[mat_idx] = texture_file_nodes[tex_idx]

        # 基本カラーのシェーダー接続
        if current_color_source:
            if material_type == 4 and mc.attributeQuery('baseColor', node=shd, exists=True):
                mc.connectAttr(current_color_source, f"{shd}.baseColor", force=True)
            else: # Blinn, Phong, Lambert, mmdMaterial, mmdToonShader
                if mc.attributeQuery('color', node=shd, exists=True):
                    mc.connectAttr(current_color_source, f"{shd}.color", force=True)

        # 材質モーフによるアルファ操作の有無を事前チェック
        has_alpha_morph = False
        for morph in getattr(pmx_model, 'morphs', []):
            if getattr(morph, 'morph_type', 0) == 8 or (hasattr(morph, 'type_index') and morph.type_index() == 8):
                for off in getattr(morph, 'offsets', []):
                    if off[0] == mat_idx or off[0] == -1:
                        d_a = off[2][3] if len(off) > 2 and len(off[2]) > 3 else 0.0
                        calc_op = off[1]
                        if calc_op == 1 and abs(d_a) > 0.001:
                            has_alpha_morph = True
                            break
                        elif calc_op == 0 and abs(d_a - 1.0) > 0.001:
                            has_alpha_morph = True
                            break
                if has_alpha_morph:
                    break
        material_has_alpha_morph_dict[mat_idx] = has_alpha_morph

        # 透過接続処理 (モーフ制御材質は後段の統合ネットワークに委任)
        if not has_alpha_morph:
            # 意図的な板ポリ透過（睫毛・ハイライト等）の判定
            cutout_keywords = ["まつげ", "睫毛", "lash", "アイライン", "ハイライト", "高光", "涙", "tear"]
            is_cutout_part = any(k in mat_name_for_kw or k in mat_e_for_kw for k in cutout_keywords)

            # ステージ・床材質の保護判定（床や地面、ステージなどのメッシュ材質は不透明を維持）
            floor_keywords = ["floor", "床", "ground", "地面", "stage", "ステージ", "tile", "タイル", "checker", "carpet", "絨毯"]
            is_floor_part = any(k in mat_name_for_kw or k in mat_e_for_kw for k in floor_keywords)

            if is_floor_part and alpha >= 0.90:
                # ステージ床材質はテクスチャの誤アルファによる透過抜けを防ぎ、不透明として保護
                if material_type == 4:
                    mc.setAttr(f"{shd}.opacity", 1.0, 1.0, 1.0, typ='double3')
                else:
                    mc.setAttr(f"{shd}.transparency", 0.0, 0.0, 0.0, typ='double3')
            elif alpha < 0.98:
                # 半透明材質
                if 0 <= tex_idx < len(texture_file_nodes) and tex_has_alpha:
                    tex_file_node = texture_file_nodes[tex_idx]
                    if mc.objExists(tex_file_node):
                        mult_node = mc.shadingNode('multiplyDivide', asUtility=True, name=f"{safe_mat_id}_alpha_mult_{model_node_name}")
                        material_alpha_mult_dict[mat_idx] = mult_node
                        mc.connectAttr(f"{tex_file_node}.outAlpha", f"{mult_node}.input1X", force=True)
                        mc.setAttr(f"{mult_node}.input2X", float(alpha))
                        if material_type == 4:
                            mc.connectAttr(f"{mult_node}.outputX", f"{shd}.opacityR", force=True)
                            mc.connectAttr(f"{mult_node}.outputX", f"{shd}.opacityG", force=True)
                            mc.connectAttr(f"{mult_node}.outputX", f"{shd}.opacityB", force=True)
                        else:
                            rev_node = mc.shadingNode('reverse', asUtility=True, name=f"{safe_mat_id}_alpha_rev_{model_node_name}")
                            mc.connectAttr(f"{mult_node}.outputX", f"{rev_node}.inputX", force=True)
                            mc.connectAttr(f"{mult_node}.outputX", f"{rev_node}.inputY", force=True)
                            mc.connectAttr(f"{mult_node}.outputX", f"{rev_node}.inputZ", force=True)
                            mc.connectAttr(f"{rev_node}.output", f"{shd}.transparency", force=True)
                else:
                    # テクスチャアルファなしの半透明
                    trans_val = 1.0 - alpha
                    if material_type == 4:
                        mc.setAttr(f"{shd}.opacity", alpha, alpha, alpha, typ='double3')
                    else:
                        mc.setAttr(f"{shd}.transparency", trans_val, trans_val, trans_val, typ='double3')
            elif is_cutout_part and 0 <= tex_idx < len(texture_file_nodes) and tex_has_alpha:
                # 睫毛やハイライト等、明確な板ポリ透過パーツのみテクスチャ透過を接続
                tex_file_node = texture_file_nodes[tex_idx]
                if mc.objExists(tex_file_node):
                    try:
                        if material_type == 4:
                            mc.connectAttr(f"{tex_file_node}.outAlpha", f"{shd}.opacityR", force=True)
                            mc.connectAttr(f"{tex_file_node}.outAlpha", f"{shd}.opacityG", force=True)
                            mc.connectAttr(f"{tex_file_node}.outAlpha", f"{shd}.opacityB", force=True)
                        else:
                            mc.connectAttr(f"{tex_file_node}.outTransparency", f"{shd}.transparency", force=True)
                    except Exception:
                        pass
            else:
                # 顔、髪、服、肌など通常の不透明材質は透過接続を行わず、不透明（transparency=0）として保護
                if material_type == 4:
                    mc.setAttr(f"{shd}.opacity", 1.0, 1.0, 1.0, typ='double3')
                else:
                    mc.setAttr(f"{shd}.transparency", 0.0, 0.0, 0.0, typ='double3')

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
            # PMX材質のセルフシャドウフラグに準拠して影受け(receiveShadows)・影落とし(castsShadows)を設定
            mat_casts_shadow = bool(getattr(mat, 'draw_flags', 0x04) & 0x04) and not is_transparent_morph_mat and not is_cutout_or_overlay
            mat_recv_shadow = bool(getattr(mat, 'draw_flags', 0x08) & 0x08) and not is_transparent_morph_mat and not is_highlight_part
            try:
                sub_shapes = mc.listRelatives(sub_mesh_name, shapes=True, fullPath=True) or [sub_mesh_name]
                for s_shp in sub_shapes:
                    mc.setAttr(f"{s_shp}.receiveShadows", 1 if mat_recv_shadow else 0)
                    mc.setAttr(f"{s_shp}.castsShadows", 1 if mat_casts_shadow else 0)
            except Exception:
                pass
            material_mesh_nodes.append(sub_mesh_name)
        else:
            if cpp_mat_valid_faces is not None and mat_idx < len(cpp_mat_valid_faces):
                face_start = sum(cpp_mat_valid_faces[:mat_idx])
                face_end = face_start + cpp_mat_valid_faces[mat_idx]
            else:
                face_start = sum(valid_face_flags[:face_offset])
                face_end = sum(valid_face_flags[:face_offset + num_faces_in_mat])
            if face_end > face_start:
                mc.sets(f"{model_mesh_node}.f[{face_start}:{face_end - 1}]", forceElement=sg_node)

        face_offset += num_faces_in_mat

    if split_by_material:
        model_mesh_node = mc.group(material_mesh_nodes, name=model_node_name)
    else:
        # 単一メッシュの場合、各材質の edgeEnable / edgeSize を頂点カラーセットへ自動焼き込み
        try:
            from . import mmd_edge_bake
            mmd_edge_bake.bake_edge_scale([model_mesh_node])
        except Exception:
            try:
                import mmd_edge_bake
                mmd_edge_bake.bake_edge_scale([model_mesh_node])
            except Exception as e:
                print(f"[警告] エッジ倍率の自動焼き込みをスキップしました: {e}")

    # ブレンドシェイプ（モーフ）の作成
    morph_structure_map = {}
    if create_blendshapes and not split_by_material:
        print("[4/6] ブレンドシェイプ（モーフ）を作成中...")
        vertex_morphs = [m for m in pmx_model.morphs if m.type_index() == 1]
        if vertex_morphs:
            # ベースメッシュのみを指定して空の blendShape ノードを作成
            blendshape_node_name = mc.blendShape(model_mesh_node, name=f"bs_{model_mesh_node}")[0]

            bs_applied_by_cpp = False
            if use_cpp_fast and hasattr(mc, "mmdFastApplyPmxBlendShapes"):
                try:
                    cpp_bs_count = mc.mmdFastApplyPmxBlendShapes(file_path, blendshape_node_name, float(scale))
                    if cpp_bs_count is not None and int(cpp_bs_count) >= 0:
                        registered_count = 0
                        for m_idx, morph in enumerate(vertex_morphs):
                            if not morph.offsets:
                                continue
                            morph_name_e = getattr(morph, 'name_e', None)
                            safe_morph_name = safe_node_name(morph.name, name_e=morph_name_e, prefix="morph", index=m_idx)
                            target_attr_name = f"temp_bs_{m_idx:03d}_{safe_morph_name}"
                            try:
                                mc.aliasAttr(target_attr_name, f"{blendshape_node_name}.w[{m_idx}]")
                            except Exception:
                                pass
                            morph_structure_map[morph.name] = target_attr_name
                            if morph_name_e:
                                morph_structure_map[morph_name_e] = target_attr_name
                            registered_count += 1
                        bs_applied_by_cpp = True
                        print(f"  - C++ (mmd_fast.mll) により {registered_count} 個の頂点モーフを一括高速登録しました")
                except Exception as e_bs:
                    print(f"  [情報] C++ ブレンドシェイプ登録から Python フォールバックへ切り替えました: {e_bs}")
                    bs_applied_by_cpp = False

            if not bs_applied_by_cpp:
                # OpenMaya 2.0 によるプラグ直接書き込み
                sel = om.MSelectionList()
                sel.add(blendshape_node_name)
                bs_mobj = sel.getDependNode(0)
                fn_bs_node = om.MFnDependencyNode(bs_mobj)

                plug_input_target_0 = fn_bs_node.findPlug('inputTarget', False).elementByLogicalIndex(0)
                plug_target_group = plug_input_target_0.child(0)

                registered_count = 0
                for m_idx, morph in enumerate(vertex_morphs):
                    try:
                        if not morph.offsets:
                            continue

                        morph_name_e = getattr(morph, 'name_e', None)
                        safe_morph_name = safe_node_name(morph.name, name_e=morph_name_e, prefix="morph", index=m_idx)
                        target_attr_name = f"temp_bs_{m_idx:03d}_{safe_morph_name}"

                        # inputTargetGroup[m_idx].inputTargetItem[6000] プラグの取得
                        plug_grp = plug_target_group.elementByLogicalIndex(m_idx)
                        plug_item = plug_grp.child(0).elementByLogicalIndex(6000)

                        plug_pts = None
                        plug_comps = None
                        for c_i in range(plug_item.numChildren()):
                            ch = plug_item.child(c_i)
                            if 'inputPointsTarget' in ch.name():
                                plug_pts = ch
                            elif 'inputComponentsTarget' in ch.name():
                                plug_comps = ch

                        if not plug_pts or not plug_comps:
                            continue

                        # 移動対象頂点と差分ベクトル配列（Sparse Delta）の構築
                        pts_array = om.MPointArray()
                        fn_comp = om.MFnSingleIndexedComponent()
                        comp_obj = fn_comp.create(om.MFn.kMeshVertComponent)

                        for offset in morph.offsets:
                            vi = offset.index
                            if vi < num_vertices:
                                off = offset.offset
                                # 座標系変換: X * scale, Y * scale, -Z * scale
                                pts_array.append(om.MPoint(off[0] * scale, off[1] * scale, -off[2] * scale, 1.0))
                                fn_comp.addElement(vi)

                        if len(pts_array) == 0:
                            continue

                        # 差分頂点配列の書き込み
                        fn_pts = om.MFnPointArrayData()
                        plug_pts.setMObject(fn_pts.create(pts_array))

                        # コンポーネントリストの書き込み
                        fn_comp_data = om.MFnComponentListData()
                        data_comp = fn_comp_data.create()
                        fn_comp_data.add(comp_obj)
                        plug_comps.setMObject(data_comp)

                        # 初期ウェイト属性を0.0に設定
                        mc.setAttr(f"{blendshape_node_name}.weight[{m_idx}]", 0.0)

                        # 問題のないターゲット属性名としてエイリアス登録 (MayaのチャネルボックスおよびUI認識を確保)
                        try:
                            mc.aliasAttr(target_attr_name, f"{blendshape_node_name}.w[{m_idx}]")
                        except Exception:
                            pass

                        # 構造マップにターゲット属性名を記録（表情操作UIおよびVMDインポートとの整合性を維持）
                        morph_structure_map[morph.name] = target_attr_name
                        if morph_name_e:
                            morph_structure_map[morph_name_e] = target_attr_name

                        registered_count += 1
                    except Exception as e:
                        print(f"  [警告] モーフ '{morph.name}' の作成をスキップしました: {e}")

                print(f"  - {registered_count} 個の頂点モーフを高速登録しました")

    # 材質モーフ（Material Morph）の作成とMMD純正方式による統合シェーダー連携
    if create_blendshapes:
        material_morphs = [m for m in pmx_model.morphs if getattr(m, 'morph_type', 0) == 8 or (hasattr(m, 'type_index') and m.type_index() == 8)]
        if material_morphs:
            print(f"  - 材質モーフ ({len(material_morphs)} 個) を構築中...")

            # モデルノードへ各モーフのアトリビュートを登録
            morph_attr_list = []
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
                    morph_attr_list.append((attr_name, safe_morph_name, morph))
                except Exception as e:
                    print(f"  [警告] 材質モーフ属性 '{morph.name}' の追加に失敗: {e}")
                    morph_attr_list.append((None, safe_morph_name, morph))

            # 各材質に影響を与えるモーフオフセットを辞書に収集
            mat_morph_affects = {i: [] for i in range(len(pmx_model.materials))}
            for attr_name, safe_m_name, morph in morph_attr_list:
                if not attr_name:
                    continue
                for off in getattr(morph, 'offsets', []):
                    target_mat_idx = off[0]
                    calc_op = off[1]
                    diff_data = off[2] if len(off) > 2 else [0.0, 0.0, 0.0, 0.0]
                    spec_data = off[3] if len(off) > 3 else [0.0, 0.0, 0.0]
                    amb_data = off[4] if len(off) > 4 else [0.0, 0.0, 0.0]
                    edge_data = off[5] if len(off) > 5 else [0.0, 0.0, 0.0, 0.0]
                    edge_sz = off[6] if len(off) > 6 else 0.0

                    target_indices = [target_mat_idx] if target_mat_idx >= 0 else list(mat_morph_affects.keys())
                    for ti in target_indices:
                        if ti in mat_morph_affects:
                            mat_morph_affects[ti].append({
                                'morph_attr': f"{model_mesh_node}.{attr_name}",
                                'morph_name': morph.name,
                                'safe_morph_name': safe_m_name,
                                'calc_op': calc_op,  # MULまたはADD演算
                                'diff_rgb': diff_data[:3],
                                'diff_a': diff_data[3] if len(diff_data) > 3 else 0.0,
                                'amb_rgb': amb_data[:3],
                                'spec_rgb': spec_data[:3],
                                'edge_rgb': edge_data[:3],
                                'edge_a': edge_data[3] if len(edge_data) > 3 else 0.0,
                                'edge_sz': edge_sz
                            })

            # 各材質ごとに統合シェーダー合成ネットワークを構築
            for mat_idx, affects in mat_morph_affects.items():
                if not affects:
                    continue
                target_shd = material_shader_dict.get(mat_idx)
                if not target_shd or not mc.objExists(target_shd):
                    continue

                mat_data = pmx_model.materials[mat_idx]
                safe_mat_id = safe_node_name(mat_data.name, name_e=getattr(mat_data, 'name_e', None), prefix="mat", index=mat_idx)
                base_alpha = float(mat_data.diffuse[3])
                base_diff = mat_data.diffuse[:3]
                tex_file_node = material_tex_node_dict.get(mat_idx)
                color_source = material_color_source_dict.get(mat_idx)

                # アルファ合成ネットワーク（加算・乗算の統合）
                alpha_affects = [a for a in affects if abs(a['diff_a']) > 0.001 or (a['calc_op'] == 0 and abs(a['diff_a'] - 1.0) > 0.001)]
                if alpha_affects:
                    try:
                        add_alpha_terms = []
                        for idx, aff in enumerate(alpha_affects):
                            diff_a = aff['diff_a']
                            calc_op = aff['calc_op']
                            m_attr = aff['morph_attr']
                            if calc_op == 1 and abs(diff_a) > 0.001:
                                term_node = mc.shadingNode('multiplyDivide', asUtility=True, name=f"{safe_mat_id}_a_term{idx}_{model_node_name}")
                                mc.connectAttr(m_attr, f"{term_node}.input1X", force=True)
                                mc.setAttr(f"{term_node}.input2X", float(diff_a))
                                add_alpha_terms.append(f"{term_node}.outputX")
                            elif calc_op == 0 and diff_a < 0.999:
                                term_node = mc.shadingNode('multiplyDivide', asUtility=True, name=f"{safe_mat_id}_a_mult_term{idx}_{model_node_name}")
                                mc.connectAttr(m_attr, f"{term_node}.input1X", force=True)
                                mc.setAttr(f"{term_node}.input2X", float(diff_a - 1.0))
                                add_alpha_terms.append(f"{term_node}.outputX")

                        # ベースアルファと各加算項の合算
                        sum_alpha_node = mc.shadingNode('plusMinusAverage', asUtility=True, name=f"{safe_mat_id}_alpha_sum_{model_node_name}")
                        mc.setAttr(f"{sum_alpha_node}.input1D[0]", float(base_alpha))
                        for term_idx, term_out in enumerate(add_alpha_terms):
                            mc.connectAttr(term_out, f"{sum_alpha_node}.input1D[{term_idx + 1}]", force=True)

                        # アルファ値の 0.0 〜 1.0 クランプ (3チャンネル揃えて設定し Viewport 2.0 フラグメントの不整合を防止)
                        clamp_alpha = mc.shadingNode('clamp', asUtility=True, name=f"{safe_mat_id}_alpha_clamp_{model_node_name}")
                        mc.setAttr(f"{clamp_alpha}.min", 0.0, 0.0, 0.0, typ='double3')
                        mc.setAttr(f"{clamp_alpha}.max", 1.0, 1.0, 1.0, typ='double3')
                        mc.connectAttr(f"{sum_alpha_node}.output1D", f"{clamp_alpha}.inputR", force=True)
                        mc.connectAttr(f"{sum_alpha_node}.output1D", f"{clamp_alpha}.inputG", force=True)
                        mc.connectAttr(f"{sum_alpha_node}.output1D", f"{clamp_alpha}.inputB", force=True)
                        final_alpha_out = f"{clamp_alpha}.outputR"

                        mat_n_low = (mat_data.name or "").lower()
                        mat_ne_low = (getattr(mat_data, 'name_e', '') or "").lower()
                        is_target_face_overlay = any(k in mat_n_low or k in mat_ne_low for k in ["頬", "cheek", "照れ", "blush", "涙", "tear", "斜線", "ガーン", "gaan"])
                        is_target_cutout = any(k in mat_n_low or k in mat_ne_low for k in ["まつげ", "睫毛", "lash", "アイライン", "ハイライト", "高光", "涙", "tear", "透", "半透明", "transparent", "trans", "clear", "shadow", "影"])

                        # 初期状態で半透明または切り抜き・オーバーレイ板材質の場合のみテクスチャアルファを乗算ブレンド
                        use_tex_alpha_in_morph = (
                            tex_file_node and mc.objExists(tex_file_node) and
                            texture_has_alpha_map.get(mat_data.texture, False) and
                            (base_alpha < 0.98 or is_target_face_overlay or is_target_cutout)
                        )
                        if use_tex_alpha_in_morph:
                            tex_alpha_mult = mc.shadingNode('multiplyDivide', asUtility=True, name=f"{safe_mat_id}_final_tex_alpha_{model_node_name}")
                            mc.connectAttr(final_alpha_out, f"{tex_alpha_mult}.input1X", force=True)
                            mc.connectAttr(f"{tex_file_node}.outAlpha", f"{tex_alpha_mult}.input2X", force=True)
                            final_opacity_source = f"{tex_alpha_mult}.outputX"
                        else:
                            final_opacity_source = final_alpha_out

                        # 反転ノード経由でシェーダーの transparency に接続 (inputX/Y/Z の3軸を揃え G/B 抜けによる半透明化を防止)
                        rev_alpha = mc.shadingNode('reverse', asUtility=True, name=f"{safe_mat_id}_final_rev_{model_node_name}")
                        mc.connectAttr(final_opacity_source, f"{rev_alpha}.inputX", force=True)
                        mc.connectAttr(final_opacity_source, f"{rev_alpha}.inputY", force=True)
                        mc.connectAttr(final_opacity_source, f"{rev_alpha}.inputZ", force=True)

                        if material_type in [1, 2, 3]:
                            mc.connectAttr(f"{rev_alpha}.output", f"{target_shd}.transparency", force=True)
                        elif material_type == 4:
                            mc.connectAttr(final_opacity_source, f"{target_shd}.opacityR", force=True)
                            mc.connectAttr(final_opacity_source, f"{target_shd}.opacityG", force=True)
                            mc.connectAttr(final_opacity_source, f"{target_shd}.opacityB", force=True)
                        elif material_type in [5, 6]:
                            mc.connectAttr(f"{rev_alpha}.output", f"{target_shd}.transparency", force=True)
                            if mc.attributeQuery("diffuseAlpha", node=target_shd, exists=True):
                                mc.connectAttr(final_opacity_source, f"{target_shd}.diffuseAlpha", force=True)

                        # アルファ変化に連動して拡散受光（diffuse / base）を動的制御し、透明化時の残存受光を遮断
                        if base_alpha <= 0.05 and is_target_face_overlay:
                            diff_gain = mc.shadingNode('multiplyDivide', asUtility=True, name=f"{safe_mat_id}_diff_gain_{model_node_name}")
                            mc.connectAttr(final_opacity_source, f"{diff_gain}.input1X", force=True)
                            mc.setAttr(f"{diff_gain}.input2X", 0.8)
                            if material_type in [1, 2, 3]:
                                mc.connectAttr(f"{diff_gain}.outputX", f"{target_shd}.diffuse", force=True)
                            elif material_type == 4:
                                mc.connectAttr(f"{diff_gain}.outputX", f"{target_shd}.base", force=True)
                            elif material_type in [5, 6]:
                                if mc.attributeQuery("diffuse", node=target_shd, exists=True):
                                    mc.connectAttr(f"{diff_gain}.outputX", f"{target_shd}.diffuse", force=True)
                        else:
                            if material_type in [1, 2, 3]:
                                mc.connectAttr(final_opacity_source, f"{target_shd}.diffuse", force=True)
                            elif material_type == 4:
                                mc.connectAttr(final_opacity_source, f"{target_shd}.base", force=True)
                            elif material_type in [5, 6]:
                                if mc.attributeQuery("diffuse", node=target_shd, exists=True):
                                    mc.connectAttr(final_opacity_source, f"{target_shd}.diffuse", force=True)
                    except Exception as e:
                        print(f"  [警告] 材質 '{mat_data.name}' のアルファモーフ統合に失敗: {e}")

                # カラー合成ネットワーク（色加算・乗算の統合）
                color_affects = [a for a in affects if any(abs(c) > 0.01 for c in a['diff_rgb']) or any(abs(c) > 0.01 for c in a['amb_rgb'])]
                if color_affects:
                    try:
                        add_col_terms = []
                        for idx, aff in enumerate(color_affects):
                            diff_rgb = aff['diff_rgb']
                            calc_op = aff['calc_op']
                            m_attr = aff['morph_attr']
                            if calc_op == 1 and any(abs(c) > 0.01 for c in diff_rgb):
                                mult_col = mc.shadingNode('multiplyDivide', asUtility=True, name=f"{safe_mat_id}_c_term{idx}_{model_node_name}")
                                mc.setAttr(f"{mult_col}.operation", 1) # Multiply
                                mc.setAttr(f"{mult_col}.input1", *diff_rgb, typ='double3')
                                mc.connectAttr(m_attr, f"{mult_col}.input2X", force=True)
                                mc.connectAttr(m_attr, f"{mult_col}.input2Y", force=True)
                                mc.connectAttr(m_attr, f"{mult_col}.input2Z", force=True)
                                add_col_terms.append(f"{mult_col}.output")

                        if add_col_terms:
                            sum_col_node = mc.shadingNode('plusMinusAverage', asUtility=True, name=f"{safe_mat_id}_color_sum_{model_node_name}")
                            sum_col_node_op = 1 # Sum
                            if color_source and mc.objExists(color_source.split('.')[0]):
                                mc.connectAttr(color_source, f"{sum_col_node}.input3D[0]", force=True)
                            else:
                                mc.setAttr(f"{sum_col_node}.input3D[0]", *base_diff, typ='double3')

                            for c_idx, c_out in enumerate(add_col_terms):
                                mc.connectAttr(c_out, f"{sum_col_node}.input3D[{c_idx + 1}]", force=True)

                            color_target = f"{target_shd}.color" if material_type in [1, 2, 3, 5, 6] else f"{target_shd}.baseColor"
                            mc.connectAttr(f"{sum_col_node}.output3D", color_target, force=True)
                            if material_type == 6 and mc.attributeQuery("diffuseColor", node=target_shd, exists=True):
                                mc.connectAttr(f"{sum_col_node}.output3D", f"{target_shd}.diffuseColor", force=True)
                    except Exception as e:
                        print(f"  [警告] 材質 '{mat_data.name}' のカラーモーフ統合に失敗: {e}")

                # エッジ制御の連動
                edge_affects = [a for a in affects if abs(a['edge_a']) > 0.01 or abs(a['edge_sz']) > 0.01]
                if edge_affects and mc.attributeQuery("edgeSize", node=target_shd, exists=True):
                    try:
                        pmx_edge_sz = float(getattr(mat_data, 'edge_size', 1.0))
                        if pmx_edge_sz <= 0.0:
                            pmx_edge_sz = float(mc.getAttr(f"{target_shd}.edgeSize") or 1.0)

                        # 初期透明材質でモーフ加算によりエッジが現れる場合は初期0.0から開始
                        is_init_transparent = (base_alpha <= 0.05)
                        has_additive_edge = any(a.get('calc_op', 1) == 1 and a['edge_a'] > 0.01 for a in edge_affects)

                        if is_init_transparent and has_additive_edge:
                            start_edge_sz = 0.0
                        else:
                            start_edge_sz = pmx_edge_sz

                        add_edge_terms = []
                        for idx, aff in enumerate(edge_affects):
                            edge_a = aff['edge_a']
                            edge_sz_val = aff.get('edge_sz', 0.0)
                            calc_op = aff.get('calc_op', 1)
                            m_attr = aff['morph_attr']

                            # エッジアルファ加算またはエッジサイズ加算の係数を算出
                            if calc_op == 1:
                                factor = edge_sz_val if abs(edge_sz_val) > 0.01 else (edge_a * pmx_edge_sz)
                            else:
                                factor = (edge_sz_val - 1.0) * pmx_edge_sz if abs(edge_sz_val - 1.0) > 0.01 else ((edge_a - 1.0) * pmx_edge_sz)

                            if abs(factor) > 0.001:
                                term_e = mc.shadingNode('multiplyDivide', asUtility=True, name=f"{safe_mat_id}_e_term{idx}_{model_node_name}")
                                mc.connectAttr(m_attr, f"{term_e}.input1X", force=True)
                                mc.setAttr(f"{term_e}.input2X", float(factor))
                                add_edge_terms.append(f"{term_e}.outputX")

                        if add_edge_terms:
                            sum_edge_node = mc.shadingNode('plusMinusAverage', asUtility=True, name=f"{safe_mat_id}_edge_sum_{model_node_name}")
                            mc.setAttr(f"{sum_edge_node}.input1D[0]", float(start_edge_sz))
                            for e_idx, e_out in enumerate(add_edge_terms):
                                mc.connectAttr(e_out, f"{sum_edge_node}.input1D[{e_idx + 1}]", force=True)
                            clamp_edge = mc.shadingNode('clamp', asUtility=True, name=f"{safe_mat_id}_edge_clamp_{model_node_name}")
                            mc.setAttr(f"{clamp_edge}.minR", 0.0)
                            mc.setAttr(f"{clamp_edge}.maxR", 10.0)
                            mc.connectAttr(f"{sum_edge_node}.output1D", f"{clamp_edge}.inputR", force=True)
                            mc.connectAttr(f"{clamp_edge}.outputR", f"{target_shd}.edgeSize", force=True)
                    except Exception as e:
                        print(f"  [警告] 材質 '{mat_data.name}' のエッジモーフ統合に失敗: {e}")


    # ジョイント（ボーンスケルトン）の作成
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

        # 各ジョイントの初期バインド位置を mmdInitialTranslate として記録 (VPD/VMDポーズ適用の基準値)
        for j_node in joint_node_names:
            try:
                if not mc.attributeQuery('mmdInitialTranslate', node=j_node, exists=True):
                    cur_t = mc.getAttr(f"{j_node}.translate")[0]
                    mc.addAttr(j_node, longName='mmdInitialTranslate', attributeType='double3')
                    mc.addAttr(j_node, longName='mmdInitialTranslateX', attributeType='double', parent='mmdInitialTranslate')
                    mc.addAttr(j_node, longName='mmdInitialTranslateY', attributeType='double', parent='mmdInitialTranslate')
                    mc.addAttr(j_node, longName='mmdInitialTranslateZ', attributeType='double', parent='mmdInitialTranslate')
                    mc.setAttr(f"{j_node}.mmdInitialTranslate", cur_t[0], cur_t[1], cur_t[2], type='double3')
            except Exception:
                pass

        # スキニングウェイト設定
        print("[6/6] スキニングウェイトを設定中...")
        skin_cluster_name = f"skin_{model_mesh_node}"
        skin_cluster = mc.skinCluster(
            joint_node_names, model_mesh_node,
            maximumInfluences=4, toSelectedBones=True, name=skin_cluster_name
        )[0]
        skin_node_name = skin_cluster

        weights_applied_by_cpp = False
        if use_cpp_fast and hasattr(mc, "mmdFastApplyPmxSkinWeights"):
            try:
                cpp_sw_res = mc.mmdFastApplyPmxSkinWeights(file_path, model_mesh_node, skin_cluster)
                if cpp_sw_res == 1:
                    weights_applied_by_cpp = True
                    print("  - C++ (mmd_fast.mll) によるスキニングウェイト一括高速注入を実行しました")
            except Exception as e_sw:
                print(f"  [情報] C++ スキニングウェイト注入から Python フォールバックへ切り替えました: {e_sw}")
                weights_applied_by_cpp = False

        if not weights_applied_by_cpp:
            sel = om.MSelectionList()
            sel.add(model_mesh_node)
            dag_path_mesh = sel.getDagPath(0)

            sel = om.MSelectionList()
            sel.add(skin_cluster)
            skin_mobject = sel.getDependNode(0)
            fn_skin = oma.MFnSkinCluster(skin_mobject)

            num_joints = len(pmx_model.bones)
            all_weights = []

            # 大容量モデル向けウェイト配列の堅牢構築
            for vtx in pmx_model.vertices:
                w = [0.0] * num_joints
                w_type = vtx.weight.type
                bones = vtx.weight.bones
                weights = vtx.weight.weights

                try:
                    if w_type == mmd_parser.pmx.BoneWeight.BDEF1:
                        b0 = bones[0]
                        if 0 <= b0 < num_joints:
                            w[b0] = 1.0
                        elif num_joints > 0:
                            w[0] = 1.0
                    elif w_type == mmd_parser.pmx.BoneWeight.BDEF2:
                        b0, b1 = bones[0], bones[1]
                        w0 = weights[0]
                        if 0 <= b0 < num_joints:
                            w[b0] += w0
                        if 0 <= b1 < num_joints:
                            w[b1] += (1.0 - w0)
                    elif w_type == mmd_parser.pmx.BoneWeight.SDEF:
                        b0, b1 = bones[0], bones[1]
                        s_weight = weights.weight if hasattr(weights, 'weight') else 0.5
                        if 0 <= b0 < num_joints:
                            w[b0] += s_weight
                        if 0 <= b1 < num_joints:
                            w[b1] += (1.0 - s_weight)
                    elif w_type == mmd_parser.pmx.BoneWeight.BDEF4 or w_type == getattr(mmd_parser.pmx.BoneWeight, 'QDEF', 4):
                        for idx in range(4):
                            b_i = bones[idx]
                            if 0 <= b_i < num_joints:
                                w[b_i] += weights[idx]
                except Exception:
                    pass

                # ウェイト合計がゼロ、またはNaNの場合のフォールバック
                sum_w = sum(w)
                if sum_w <= 1e-6 or math.isnan(sum_w):
                    if num_joints > 0:
                        w = [0.0] * num_joints
                        w[0] = 1.0
                else:
                    # 正規化
                    w = [v / sum_w for v in w]

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

            # フルDAGパスを取得して名前重複衝突を防止
            try:
                long_names = mc.ls(actual_j, long=True)
                final_path = long_names[0] if long_names else actual_j
            except Exception:
                final_path = actual_j

            # 剛体・Jointバインド用にリネーム後のノード参照を更新
            joint_node_names[b_idx] = final_path

            if bone_obj:

                name_jp = bone_obj.name
                name_en = getattr(bone_obj, 'name_e', '') or ''
                if not name_en:
                    # PMXに英語名が未定義の場合は標準MMDボーン日英辞書から自動補足
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

    # モデルの元ファイルパスを保持 (複数モデル物理ベイク等の自動参照用)
    if not mc.attributeQuery('mmdModelPath', node=model_mesh_node, exists=True):
        mc.addAttr(model_mesh_node, longName='mmdModelPath', niceName='PMXファイルパス', dataType='string')
    mc.setAttr(f"{model_mesh_node}.mmdModelPath", os.path.abspath(file_path).replace('\\', '/'), typ='string')

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
            'shape_type': rb.shape_type,  # 形状種別 (球、箱、カプセル)
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
            'physics_mode': int(rb.physics_mode)  # 物理モード (Kinematic, Dynamic, Aligned)
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

        # 後方互換性レイヤー (旧コード・旧スクリプトからの確実な参照を保証)
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
        # 元モデルファイルパスの記録（モデル種別個別指定・連動用）
        target_nodes_for_src = [model_mesh_node]
        child_shapes = mc.listRelatives(model_mesh_node, shapes=True, fullPath=True) or []
        target_nodes_for_src.extend(child_shapes)
        for tn in target_nodes_for_src:
            if not mc.attributeQuery('mmdSourceFilePath', node=tn, exists=True):
                mc.addAttr(tn, longName='mmdSourceFilePath', dataType='string')
            mc.setAttr(f"{tn}.mmdSourceFilePath", file_path, typ='string')

        # 新スキーマ各部のフルデータを格納する専用アトリビュート
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

    # 剛体・Jointコライダーの自動生成
    physics_root_group = None
    if create_physics and create_joints and getattr(pmx_model, 'rigid_bodies', None):
        try:
            physics_root_group = create_rigidbody_and_joint_nodes(
                pmx_model, model_mesh_node, joint_node_names, scale=scale
            )
        except Exception as e:
            print(f"  [警告] 剛体・Joint生成エラー: {e}")

    # アプローチB（同一メッシュ方式）への移行のため、別メッシュ（_Edge）の生成はスキップ
    edge_mesh_node = None
    if False and create_edge_mesh and not split_by_material:
        try:
            try:
                from .edge_mesh_builder import build_edge_mesh_from_pmx, create_inverted_hull_edge_mesh
            except Exception:
                from maya_converters.edge_mesh_builder import build_edge_mesh_from_pmx, create_inverted_hull_edge_mesh
            try:
                edge_mesh_node = build_edge_mesh_from_pmx(
                    pmx_model, model_mesh_node, joint_node_names=joint_node_names, blendshape_node=blendshape_node_name, scale=scale
                )
            except Exception as e_pmx:
                print(f"  [情報] PMXダイレクトエッジ生成からフォールバックします: {e_pmx}")
                edge_mesh_node = create_inverted_hull_edge_mesh(model_mesh_node, scale=scale)
        except Exception as e:
            print(f"  [警告] エッジメッシュ生成中にエラーが発生しました: {e}")

    # シーン内のMMDメッシュおよび地面影プレーンのシャドウ・ステージ自動設定を最適化
    try:
        optimize_model_meshes_for_mmd_lighting()
    except Exception:
        pass

    # スカイドームまたはステージモデルの場合のエッジ無効化・ボーン非表示化処理
    if is_background_or_stage:
        # マテリアル割り当て後のメッシュに対してエッジ描画を確実に無効化
        disable_mesh_edges(model_mesh_node)
        all_child_shapes = mc.listRelatives(model_mesh_node, shapes=True, fullPath=True) or []
        for ch_s in all_child_shapes:
            disable_mesh_edges(ch_s)

        # モデル種別アトリビュートの記録
        target_kind = "skydome" if is_skydome_model else "stage"
        for t_node in [model_mesh_node] + all_child_shapes:
            if mc.objExists(t_node):
                try:
                    if not mc.attributeQuery('mmdModelType', node=t_node, exists=True):
                        mc.addAttr(t_node, longName='mmdModelType', dataType='string')
                    mc.setAttr(f"{t_node}.mmdModelType", target_kind, typ='string')
                except Exception:
                    pass

        # ボーン（ジョイント）の表示を非表示化
        if create_joints:
            # 作成された各ジョイントの drawStyle を 2 (None / 非表示) に設定
            if 'joint_node_names' in locals() and joint_node_names:
                for j_node in joint_node_names:
                    if mc.objExists(j_node):
                        try:
                            mc.setAttr(f"{j_node}.drawStyle", 2)
                        except Exception:
                            pass
            # ルートジョイントの visibility も False に設定
            if root_joint_names:
                for r_j in root_joint_names:
                    if mc.objExists(r_j):
                        try:
                            mc.setAttr(f"{r_j}.visibility", False)
                        except Exception:
                            pass
            total_j_count = len(joint_node_names) if 'joint_node_names' in locals() and joint_node_names else len(root_joint_names)
            print(f"  - スカイドーム/ステージモデルのため、ボーン表示を非表示に設定しました (計 {total_j_count} ジョイント)")

    mc.select(model_mesh_node)
    if not is_background_or_stage and create_joints and root_joint_names:
        mc.select(root_joint_names, add=True)

    # グリッド線が表示されている場合は非表示に設定
    try:
        hide_viewport_grid()
    except Exception:
        pass

    # ビューポートのリフレッシュ
    try:
        mc.refresh(force=True)
    except Exception:
        pass

    elapsed = time.time() - start_time
    if show_completion_message:
        print("==================================================")
        print(f"モデルインポートが終了しました！ (所要時間: {elapsed:.2f}秒)")
        print("==================================================")
    else:
        print(f"  - メッシュ・リグ構築が終了しました (所要時間: {elapsed:.2f}秒)")

    return model_mesh_node, root_joint_names, skin_node_name, blendshape_node_name

def setup_viewport_display(shadow_mode=None, prevent_motion_darkening=True, hide_lights=True, hide_grid=True):
    """
    ビューポートの表示品質を最適化:
    - テクスチャ表示（displayTextures=True / 6キー相当）を有効化
    - アンチエイリアシング（マルチサンプルAAおよびポストAA）を有効化
    - 透過アルゴリズム（Depth Peeling）を設定
    - モーション再生時の暗化防止（シャッター開度0.01によるブレなしHDRパス最適化）
    - ライティング・影表示を設定（shadow_mode指定時）
    - ビューポートのShowメニューでライトアイコンを非表示化（hide_lights=True時）
    - グリッド線を非表示化（hide_grid=True時）
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
            # モーション再生時の暗化防止（シャッター開度0.01によるブレなしHDRポストパス最適化）
            if mc.attributeQuery('motionBlurEnable', node='hardwareRenderingGlobals', exists=True):
                mc.setAttr('hardwareRenderingGlobals.motionBlurEnable', bool(prevent_motion_darkening))
            if prevent_motion_darkening:
                if mc.attributeQuery('motionBlurShutterOpenFraction', node='hardwareRenderingGlobals', exists=True):
                    mc.setAttr('hardwareRenderingGlobals.motionBlurShutterOpenFraction', 0.01)
                if mc.attributeQuery('floatingPointRTEnable', node='hardwareRenderingGlobals', exists=True):
                    mc.setAttr('hardwareRenderingGlobals.floatingPointRTEnable', True)
                if mc.attributeQuery('floatingPointRTFormat', node='hardwareRenderingGlobals', exists=True):
                    mc.setAttr('hardwareRenderingGlobals.floatingPointRTFormat', 1)
    except Exception:
        pass

    # 各ビューポートパネルの設定（テクスチャ表示有効化、ライトアイコン非表示化、グリッド非表示化）
    try:
        model_panels = mc.getPanel(type='modelPanel') or []
        for panel in model_panels:
            edit_kwargs = {'displayTextures': True}
            if hide_lights:
                edit_kwargs['lights'] = False
            if hide_grid:
                edit_kwargs['grid'] = False
            if shadow_mode is not None:
                edit_kwargs['displayLights'] = 'all'
                edit_kwargs['shadows'] = (shadow_mode > 0)
            # MMD Edge Renderer (同一メッシュエッジ描画オーバーライド) の適用
            try:
                if mc.pluginInfo("mmd_edge", query=True, loaded=True) or mc.pluginInfo("mmd_edge.mll", query=True, loaded=True):
                    edit_kwargs['rendererOverrideName'] = "MMDEdgeRenderer"
            except Exception:
                pass
            mc.modelEditor(panel, edit=True, **edit_kwargs)
    except Exception:
        pass

    if hide_grid:
        try:
            hide_viewport_grid()
        except Exception:
            pass

    # シーン内のMMDモデルメッシュおよび地面影プレーンのシャドウ設定を適正化
    optimize_model_meshes_for_mmd_lighting()

    # perspカメラの焦点距離をMMD標準画角に設定
    setup_persp_camera_for_mmd()

def is_skydome_mesh(mesh_node, file_path=None):
    """
    指定されたメッシュが純粋なスカイドーム（天球・背景球・空単体モデル）であるかを判定します。
    ユーザー定義キーワードおよび個別指定設定（ModelClassifierManager）を参照します。
    床や階段、建築物を含む大型ステージモデルはスカイドームとは判定しません。
    """
    if not mesh_node or not mc.objExists(mesh_node):
        return False

    # 判定マネージャーによる照合
    try:
        try:
            from ..asset.model_classifier_manager import ModelClassifierManager
        except Exception:
            from asset.model_classifier_manager import ModelClassifierManager
        mgr = ModelClassifierManager.get_instance()
        return mgr.is_skydome_mesh(mesh_node, file_path=file_path)
    except Exception:
        pass

    # マネージャー未ロード時のフォールバック処理
    stage_keywords = [
        "stage", "ステージ", "floor", "床", "ground", "地面",
        "room", "館", "hall", "house", "building", "建物", "城", "街",
        "acute", "plaza", "広場", "checker", "tile", "タイル"
    ]

    skydome_keywords = [
        "skydome", "sky_dome", "dome_", "スカイドーム", "天球",
        "青空", "夜空", "宇宙", "skysphere", "celestial"
    ]

    full_path = mc.ls(mesh_node, long=True)[0] if mc.ls(mesh_node, long=True) else mesh_node
    path_lower = full_path.lower()

    if any(k in path_lower for k in stage_keywords):
        return False

    num_materials = 0
    try:
        shading_groups = mc.listConnections(mesh_node, type="shadingEngine") or []
        num_materials = len(set(shading_groups))
    except Exception:
        pass

    if num_materials > 4:
        return False

    if any(k in path_lower for k in skydome_keywords):
        return True

    try:
        bb = mc.exactWorldBoundingBox(mesh_node)
        width = abs(bb[3] - bb[0])
        height = abs(bb[4] - bb[1])
        depth = abs(bb[5] - bb[2])
        if width >= 200.0 and depth >= 200.0 and height >= 80.0 and num_materials <= 4:
            return True
    except Exception:
        pass

    return False


def detect_stage_meshes():
    """
    シーン内のメッシュからステージモデル（広大な床メッシュや背景・ステージ建造物）を自動検出します。
    ユーザー定義キーワードおよび個別指定設定（ModelClassifierManager）を参照します。
    戻り値: ステージ床またはステージ本体と判定されたメッシュシェイプのリスト
    """
    try:
        try:
            from ..asset.model_classifier_manager import ModelClassifierManager
        except Exception:
            from asset.model_classifier_manager import ModelClassifierManager
        mgr = ModelClassifierManager.get_instance()
    except Exception:
        mgr = None

    stage_meshes = []
    stage_keywords = [
        "stage", "ステージ", "floor", "床", "ground", "地面",
        "room", "hall", "field", "広場", "house", "building", "建物", "城", "街",
        "bg", "background", "背景", "checker", "tile", "タイル", "acute", "plaza"
    ]
    try:
        all_meshes = mc.ls(type="mesh", long=True) or []
        for m in all_meshes:
            if "mmd_ground_shadow" in m or any(k in m for k in ["Camera", "Light", "light", "mmd_rigid", "mmd_joint"]):
                continue

            # マネージャーによるステージ判定
            if mgr:
                if mgr.is_stage_mesh(m):
                    stage_meshes.append(m)
                    continue
                if mgr.is_skydome_mesh(m):
                    continue

            # フォールバック処理
            if is_skydome_mesh(m):
                continue

            # スキニング（skinCluster）が存在するメッシュはキャラクターとみなし除外
            try:
                skin_clusters = mc.ls(mc.listHistory(m), type="skinCluster") or []
                if skin_clusters:
                    continue
            except Exception:
                pass

            m_full = m
            parents = mc.listRelatives(m, parent=True, fullPath=True) or []
            shading_groups = mc.listConnections(m, type="shadingEngine") or []
            mat_names = []
            for sg in shading_groups:
                mat_names.extend(mc.listConnections(f"{sg}.surfaceShader") or [])
            path_str = (m_full + " " + " ".join(parents) + " " + " ".join(mat_names)).lower()

            has_keyword = any(k in path_str for k in stage_keywords)
            is_large_stage = False
            try:
                bb = mc.exactWorldBoundingBox(m)
                width = abs(bb[3] - bb[0])
                height = abs(bb[4] - bb[1])
                depth = abs(bb[5] - bb[2])

                # 縦長の人型キャラクタープロポーションは除外
                if height >= 60.0 and height > width * 0.6 and height > depth * 0.6:
                    continue

                is_flat_floor = (width >= 80.0 or depth >= 80.0) and (height <= 25.0 or (height <= width * 0.15 and height <= depth * 0.15))
                num_materials = len(set(shading_groups))
                is_multi_mat_large = (width >= 250.0 and depth >= 250.0) and num_materials >= 5

                if is_flat_floor or is_multi_mat_large:
                    is_large_stage = True
            except Exception:
                pass

            if has_keyword or is_large_stage:
                stage_meshes.append(m)
    except Exception:
        pass
    return stage_meshes


def set_ground_shadow_mode(stage_mode=None):
    """
    MMD地面影プレーンとステージモデル床への影投影モードを切り替えます。
    引数:
        stage_mode (bool, optional):
            True: ステージ影モード（地面影プレーン非表示、ステージ床で影を受け止める）
            False: 標準地面影プレーンモード（Y=0に影プレーン表示）
            None: シーン内のステージモデル有無から自動判別
    戻り値:
        bool: 適用されたモード (True: ステージ影, False: 地面影プレーン)
    """
    detected_stages = detect_stage_meshes()
    if stage_mode is None:
        stage_mode = len(detected_stages) > 0

    plane_name = "mmd_ground_shadow_plane"
    grp_name = "mmd_ground_shadow_grp"

    # 地面影プレーンの表示状態切り替え
    target_nodes = []
    if mc.objExists(plane_name):
        target_nodes.append(plane_name)
    if mc.objExists(grp_name):
        target_nodes.append(grp_name)

    for node in target_nodes:
        try:
            # ステージ影モード時は非表示 (0)、標準地面影時は表示 (1)
            mc.setAttr(f"{node}.visibility", 0 if stage_mode else 1)
        except Exception:
            pass

    # ステージメッシュ側の受光属性最適化
    if stage_mode and detected_stages:
        for s_mesh in detected_stages:
            try:
                if mc.attributeQuery("receiveShadows", node=s_mesh, exists=True):
                    mc.setAttr(f"{s_mesh}.receiveShadows", 1)
                # 広大なステージメッシュ自身が影を落としてシャドウマップ解像度を奪うのを抑制
                bb = mc.exactWorldBoundingBox(s_mesh)
                width = abs(bb[3] - bb[0])
                depth = abs(bb[5] - bb[2])
                if width >= 50.0 or depth >= 50.0:
                    if mc.attributeQuery("castsShadows", node=s_mesh, exists=True):
                        mc.setAttr(f"{s_mesh}.castsShadows", 0)
            except Exception:
                pass
        print(f"[情報] ステージ影モードを有効化しました (地面影プレーン非表示 / ステージ受光有効: {len(detected_stages)} メッシュ)")
    else:
        print("[情報] 標準地面影プレーンモードを有効化しました (Y=0 地面影プレーン表示)")

    return stage_mode


def optimize_model_meshes_for_mmd_lighting(target_model_root=None, auto_stage_detect=True):
    """
    MMDモデルのメッシュに対し、前髪・首元・服などの落ち影（セルフシャドウ）を受け取るため
    receiveShadowsを有効化します。
    また、地面影プレーン (mmd_ground_shadow_plane) の castsShadows を無効化することで、
    ディレクショナルライトのデプスマップ解像度がキャラクター身体各部に集中するように最適化します。
    ステージモデルが検出された場合は、地面影プレーンを自動非表示にしてステージ床へ影を落とします。
    """
    try:
        stage_meshes_set = set(detect_stage_meshes())
        all_meshes = mc.ls(type="mesh", long=True) or []
        for m in all_meshes:
            # 地面影プレーンは影を受け止めるのみで、自身は影を落とさない設定にする（シャドウマップ解像度の分散防止）
            if "mmd_ground_shadow" in m:
                if mc.attributeQuery("receiveShadows", node=m, exists=True):
                    mc.setAttr(f"{m}.receiveShadows", 1)
                if mc.attributeQuery("castsShadows", node=m, exists=True):
                    mc.setAttr(f"{m}.castsShadows", 0)
                continue
            # スカイドーム（天球）メッシュの影落とし・受光を無効化、およびエッジ描画を無効化
            # (シャドウマップ解像度の巨大空間への分散抑止、天球による遮光・黒ずみ防止、およびエッジの視界浸食防止)
            if is_skydome_mesh(m):
                if mc.attributeQuery("castsShadows", node=m, exists=True):
                    mc.setAttr(f"{m}.castsShadows", 0)
                if mc.attributeQuery("receiveShadows", node=m, exists=True):
                    mc.setAttr(f"{m}.receiveShadows", 0)
                disable_mesh_edges(m)
                continue
            # カメラやライト、剛体補助形状はスキップ
            if any(k in m for k in ["Camera", "Light", "light", "mmd_rigid", "mmd_joint"]):
                continue

            # ステージメッシュ以外のキャラクター通常メッシュは影落とし (castsShadows) を復元・保証
            # （過去に誤って0に設定された場合でも確実に1へ戻す）
            is_stg = (m in stage_meshes_set) if 'stage_meshes_set' in locals() else False
            if is_stg:
                disable_mesh_edges(m)
            elif mc.attributeQuery("castsShadows", node=m, exists=True):
                try:
                    # 初期透明モーフ板等の特定材質で明示的に0に設定されている場合を除き1を保証
                    mc.setAttr(f"{m}.castsShadows", 1)
                except Exception:
                    pass

            if mc.attributeQuery("receiveShadows", node=m, exists=True):
                # セルフシャドウ受光を有効化
                mc.setAttr(f"{m}.receiveShadows", 1)

        # ステージモデル自動判別と影プレーン連動
        if auto_stage_detect:
            set_ground_shadow_mode(stage_mode=None)

    except Exception:
        pass

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
    各マテリアル種別（mmdToonShader / mmdMaterial / StandardSurface / Phong等）対応仕様:
      - 光源方向: MMD標準の照明操作（X: 0.50, Y: -1.00, Z: -0.50）に準拠した Rotate [-54.74, 45.0, 0.0]
      - 平行光カラー: (1.0, 1.0, 1.0), 強度 0.32 （落ち影とのコントラストを形成）
      - 環境光カラー: (1.0, 1.0, 1.0), 強度 0.68 （セルフシャドウ領域の黒潰れを防ぎ、Toon影色の自然な発色を維持）

    shadow_mode:
      - 0: セルフ影なし (シャドウOFF)
      - 1: モード1 (標準セルフ影)
      - 2: モード2 (高精細セルフ影)
    """
    # 既存のMMDライトが存在する場合は再作成せず最適化・更新
    existing_dir_shapes = mc.ls("mmd_directional_light*Shape*", type="directionalLight") or []
    existing_amb_shapes = mc.ls("mmd_ambient_light*Shape*", type="ambientLight") or []

    # MMD本家標準の初期ライト色: RGB 154 (約 0.60392)
    mmd_light_val = 154.0 / 255.0

    if existing_dir_shapes or existing_amb_shapes:
        if existing_dir_shapes:
            d_shape = existing_dir_shapes[0]
            d_trans = mc.listRelatives(d_shape, parent=True, fullPath=True)[0]
            mc.setAttr(f"{d_trans}.rotate", -54.74, 45.0, 0.0, typ='double3')
            mc.setAttr(f"{d_trans}.translateY", 200.0)
            mc.setAttr(f"{d_trans}.scale", 5.0, 5.0, 5.0)
            mc.setAttr(f"{d_shape}.color", mmd_light_val, mmd_light_val, mmd_light_val, typ='double3')
            mc.setAttr(f"{d_shape}.intensity", 1.0)
            # MMD照明初期値カスタムアトリビュートの保持
            for attr_n, attr_v in [('mmdLightX', 0.50), ('mmdLightY', -1.00), ('mmdLightZ', -0.50)]:
                if not mc.attributeQuery(attr_n, node=d_trans, exists=True):
                    mc.addAttr(d_trans, longName=attr_n, attributeType='double', defaultValue=attr_v)
                mc.setAttr(f"{d_trans}.{attr_n}", attr_v)
            _apply_shadow_mode(d_shape, shadow_mode)
        if existing_amb_shapes:
            a_shape = existing_amb_shapes[0]
            a_trans = mc.listRelatives(a_shape, parent=True, fullPath=True)[0]
            mc.setAttr(f"{a_trans}.translateY", 200.0)
            mc.setAttr(f"{a_trans}.scale", 5.0, 5.0, 5.0)
            mc.setAttr(f"{a_shape}.ambientShade", 0.0)
            mc.setAttr(f"{a_shape}.color", 1.0, 1.0, 1.0, typ='double3')
            mc.setAttr(f"{a_shape}.intensity", 0.75)
        # ビューポートのテクスチャ表示とアンチエイリアシングを最適化
        setup_viewport_display(shadow_mode=shadow_mode, hide_lights=True)
        try:
            for panel in mc.getPanel(type='modelPanel') or []:
                mc.modelEditor(panel, edit=True, lights=False)
        except Exception:
            pass
        print("[情報] 既存のMMD標準ライティングを適正化しました（MMD Toon & セルフシャドウ対応）。")
        return "mmd_lighting_grp"

    print(f"[情報] MMD標準ライティング（シャドウモード: {shadow_mode}）を作成中...")

    # 名前の衝突を防止するためユニーク名を決定
    dir_light_name = _get_unique_node_name("mmd_directional_light")
    dir_shape_name = _get_unique_node_name(f"{dir_light_name}Shape")
    amb_light_name = _get_unique_node_name("mmd_ambient_light")
    amb_shape_name = _get_unique_node_name(f"{amb_light_name}Shape")
    grp_name = _get_unique_node_name("mmd_lighting_grp")

    # 平行光源 (MMD本家基準: 強度 1.0, カラー RGB 154)
    dir_shape_raw = mc.directionalLight(intensity=1.0)
    dir_transform_nodes = mc.listRelatives(dir_shape_raw, parent=True, fullPath=True) or [dir_shape_raw]
    dir_light = mc.rename(dir_transform_nodes[0], dir_light_name)
    actual_dir_shapes = mc.listRelatives(dir_light, shapes=True, fullPath=True) or []
    dir_shape = actual_dir_shapes[0] if actual_dir_shapes else dir_shape_raw

    # MMD標準の照明操作（X: 0.50, Y: -1.00, Z: -0.50）に準拠した角度 [-54.74, 45.0, 0.0]
    mc.setAttr(f"{dir_light}.rotate", -54.74, 45.0, 0.0, typ='double3')
    mc.setAttr(f"{dir_shape}.color", mmd_light_val, mmd_light_val, mmd_light_val, typ='double3')
    mc.setAttr(f"{dir_shape}.intensity", 1.0)
    # MMD照明初期値カスタムアトリビュートの保持 (X: 0.50, Y: -1.00, Z: -0.50)
    for attr_n, attr_v in [('mmdLightX', 0.50), ('mmdLightY', -1.00), ('mmdLightZ', -0.50)]:
        if not mc.attributeQuery(attr_n, node=dir_light, exists=True):
            mc.addAttr(dir_light, longName=attr_n, attributeType='double', defaultValue=attr_v)
        mc.setAttr(f"{dir_light}.{attr_n}", attr_v)
    # 頭上への配置（Y=200）および視認性向上のための拡大（スケール=5）
    mc.setAttr(f"{dir_light}.translateY", 200.0)
    mc.setAttr(f"{dir_light}.scale", 5.0, 5.0, 5.0)

    # シャドウモードの適用
    _apply_shadow_mode(dir_shape, shadow_mode)

    # アンビエントライト (セルフシャドウ領域の下限輝度 0.75 を維持し、黒潰れを防止)
    amb_shape_raw = mc.ambientLight(intensity=0.75)
    amb_transform_nodes = mc.listRelatives(amb_shape_raw, parent=True, fullPath=True) or [amb_shape_raw]
    amb_light = mc.rename(amb_transform_nodes[0], amb_light_name)
    actual_amb_shapes = mc.listRelatives(amb_light, shapes=True, fullPath=True) or []
    amb_shape = actual_amb_shapes[0] if actual_amb_shapes else amb_shape_raw

    mc.setAttr(f"{amb_shape}.ambientShade", 0.0)
    mc.setAttr(f"{amb_shape}.color", 1.0, 1.0, 1.0, typ='double3')
    mc.setAttr(f"{amb_shape}.intensity", 0.75)
    mc.setAttr(f"{amb_light}.translateY", 200.0)
    mc.setAttr(f"{amb_light}.scale", 5.0, 5.0, 5.0)

    # グループ化
    light_grp = mc.group(dir_light, amb_light, name=grp_name)

    # MMD標準地面影プレーンの自動作成
    create_mmd_ground_shadow()

    # ビューポートのテクスチャ表示・ライティング・アンチエイリアシングを最適化
    setup_viewport_display(shadow_mode=shadow_mode, hide_lights=True)

    # ビューポートのShowメニューでライトの表示をオフにする
    try:
        for panel in mc.getPanel(type='modelPanel') or []:
            mc.modelEditor(panel, edit=True, lights=False)
    except Exception:
        pass

    print(f"[情報] MMD標準ライティングを作成しました ({light_grp})。")
    return light_grp


def create_mmd_ground_shadow(size=500.0, shadow_intensity=0.5):
    """
    MMD標準の地面影（Y=0.05平面上のシャドウキャッチャー）を作成します。
    ビューポート上でメッシュ自体は透明となり、落ち影のみを自然に受け止めます。
    ※ 参照実装準拠で地面グリッドとのZファイティング（重なりチラつき）を防止するためY=0.05に微小オフセット。
    """
    grp_name = "mmd_ground_shadow_grp"
    plane_name = "mmd_ground_shadow_plane"

    if mc.objExists(plane_name):
        shapes = mc.listRelatives(plane_name, shapes=True, fullPath=True) or []
        for s in shapes:
            try:
                mc.setAttr(f"{s}.castsShadows", 0)
                mc.setAttr(f"{s}.receiveShadows", 1)
            except Exception:
                pass
        return plane_name

    # シャドウキャッチャー用シェーダーの構築 (useBackground)
    shd_name = "mmd_ground_shadow_shd"
    sg_name = f"{shd_name}SG"

    if not mc.objExists(shd_name):
        shd = mc.shadingNode('useBackground', asShader=True, name=shd_name)
        sg = mc.sets(renderable=True, noSurfaceShader=True, empty=True, name=sg_name)
        mc.connectAttr(f"{shd}.outColor", f"{sg}.surfaceShader", force=True)

        # 影のみを受け止める設定 (反射・ハイライトを遮断し、半透明の影のみ生成)
        mc.setAttr(f"{shd}.specularColor", 0.0, 0.0, 0.0, typ='double3')
        mc.setAttr(f"{shd}.reflectivity", 0.0)
        mc.setAttr(f"{shd}.reflectionLimit", 0)
        mc.setAttr(f"{shd}.shadowMask", float(shadow_intensity))
    else:
        sg = sg_name

    # ポリゴン平面の作成（Zファイティング防止のためY=0.05にオフセット配置）
    plane = mc.polyPlane(name=plane_name, width=size, height=size, subdivisionsX=1, subdivisionsY=1)[0]
    mc.setAttr(f"{plane}.translateY", 0.05)
    mc.sets(plane, forceElement=sg)

    # 煽りアングル（下から見上げた際）にモデルが隠れないよう、片面描画＆バックフェイスカリングを設定
    # また、広大な地面プレーンがシャドウマップの投影範囲を広げないよう castsShadows=0 に設定
    shapes = mc.listRelatives(plane, shapes=True) or []
    if shapes:
        plane_shape = shapes[0]
        try:
            mc.setAttr(f"{plane_shape}.doubleSided", 0)
            mc.setAttr(f"{plane_shape}.backfaceCulling", 3)
            mc.setAttr(f"{plane_shape}.castsShadows", 0)
            mc.setAttr(f"{plane_shape}.receiveShadows", 1)
        except Exception:
            pass

    # 選択誤爆防止のためレンダー専用フラグ設定
    mc.addAttr(plane, longName='mmdGroundShadow', attributeType='bool')
    mc.setAttr(f"{plane}.mmdGroundShadow", True)

    # グループ化
    if not mc.objExists(grp_name):
        grp = mc.group(plane, name=grp_name)
    else:
        grp = mc.parent(plane, grp_name)[0]

    print(f"[情報] MMD標準地面影プレーンを作成しました ({plane_name})。")
    # ステージモデルが存在する場合は自動でステージ影モード（プレーン非表示）に切り替え
    set_ground_shadow_mode(stage_mode=None)
    return plane

def _apply_shadow_mode(dir_shape, shadow_mode):
    """Directional Lightノードおよびビューポートにセルフシャドウ設定を適用"""
    if not mc.objExists(dir_shape):
        return
    try:
        if shadow_mode == 0:
            # セルフ影なし
            mc.setAttr(f"{dir_shape}.useDepthMapShadows", 0)
        elif shadow_mode == 1:
            # モード1 (標準セルフ影) - シャドウアクネを抑止しつつ境界を柔らかく馴染ませた落ち影を生成
            mc.setAttr(f"{dir_shape}.useDepthMapShadows", 1)
            mc.setAttr(f"{dir_shape}.dmapResolution", 4096)
            mc.setAttr(f"{dir_shape}.dmapFilterSize", 6)
            mc.setAttr(f"{dir_shape}.dmapBias", 0.006)
            mc.setAttr(f"{dir_shape}.shadowColor", 0.0, 0.0, 0.0, typ='double3')
        elif shadow_mode == 2:
            # モード2 (高精細セルフ影) - 柔らかい境界フィルタリング付きセルフ影
            mc.setAttr(f"{dir_shape}.useDepthMapShadows", 1)
            mc.setAttr(f"{dir_shape}.dmapResolution", 4096)
            mc.setAttr(f"{dir_shape}.dmapFilterSize", 8)
            mc.setAttr(f"{dir_shape}.dmapBias", 0.006)
            mc.setAttr(f"{dir_shape}.shadowColor", 0.0, 0.0, 0.0, typ='double3')

        # ビューポート連動（影とテクスチャ表示、ライト非表示化）
        model_panels = mc.getPanel(type='modelPanel') or []
        for panel in model_panels:
            mc.modelEditor(panel, edit=True, shadows=(shadow_mode > 0), displayTextures=True, lights=False)
    except Exception:
        pass

def fix_toon_shading_in_scene(shadow_mode=1):
    """
    シーン内の既存MMDシェーダーに対してToon設定およびスペキュラ設定を最適化
    - Toon計算をカメラ空間からワールド空間（matrixEyeToWorld変換）に切り替え、視点移動による影の変化を解消
    - MMD照明のセルフ影モード（0: なし, 1: モード1, 2: モード2）を適用
    - 顔・肌パーツも含め、すべての材質のToon乗算を最適なしきい値で再接続
    - 顔・肌および反射なし材質のプラスチック調スペキュラ光沢を除去
    """
    fixed_count = 0

    # モデルメッシュおよび地面影プレーンのシャドウ属性を適正化
    optimize_model_meshes_for_mmd_lighting()

    # ライティングとシャドウモードの更新
    dir_shapes = mc.ls("mmd_directional_light*Shape*", type="directionalLight") or []
    if dir_shapes:
        dir_shape = dir_shapes[0]
        dir_transform = mc.listRelatives(dir_shape, parent=True, fullPath=True)[0]
        mc.setAttr(f"{dir_transform}.rotate", -25.0, 20.0, 0.0, typ='double3')
        mc.setAttr(f"{dir_transform}.translateY", 200.0)
        mc.setAttr(f"{dir_transform}.scale", 5.0, 5.0, 5.0)
        _apply_shadow_mode(dir_shape, shadow_mode)
    elif mc.objExists("mmd_lighting_grp"):
        _apply_shadow_mode("mmd_directional_lightShape", shadow_mode)

    amb_shapes = mc.ls("mmd_ambient_light*Shape*", type="ambientLight") or []
    if amb_shapes:
        amb_transform = mc.listRelatives(amb_shapes[0], parent=True, fullPath=True)[0]
        mc.setAttr(f"{amb_transform}.translateY", 200.0)
        mc.setAttr(f"{amb_transform}.scale", 5.0, 5.0, 5.0)
        mc.setAttr(f"{amb_shapes[0]}.ambientShade", 0.0)

    # シーン内のToonテクスチャノードから最頻出のToon影色を抽出してライトおよび固定UVサンプリングを適正化
    toon_file_nodes = (mc.ls("toon*_file_*", type="file") or []) + (mc.ls("*_custoon_file_*", type="file") or [])
    best_toon_path = None
    max_conns = -1
    for tf_node in toon_file_nodes:
        try:
            ftn_val = mc.getAttr(f"{tf_node}.ftn")
            if ftn_val and os.path.isfile(ftn_val):
                # Viewport 2.0でメッシュUVがバインドされないよう専用place2dTextureを保証
                uv_in = mc.listConnections(f"{tf_node}.uvCoord", source=True, destination=False) or []
                if not uv_in:
                    p2d = mc.shadingNode('place2dTexture', asUtility=True, name=f"{tf_node}_place2d")
                    for s_a, d_a in PLACE2D_ATTR_CONNECTIONS:
                        try:
                            mc.connectAttr(f"{p2d}.{s_a}", f"{tf_node}.{d_a}", force=True)
                        except Exception:
                            pass
                    mc.setAttr(f"{p2d}.wrapU", False)
                    mc.setAttr(f"{p2d}.wrapV", False)
                    mc.setAttr(f"{p2d}.repeatU", 0.0)
                    mc.setAttr(f"{p2d}.repeatV", 0.0)
                    mc.setAttr(f"{p2d}.offsetU", 0.5)
                    mc.setAttr(f"{p2d}.offsetV", 0.05)
                out_c = mc.listConnections(f"{tf_node}.outColor", source=False, destination=True) or []
                conn_cnt = len(out_c)
                for b_n in out_c:
                    b_outs = mc.listConnections(f"{b_n}.output", source=False, destination=True) or []
                    conn_cnt += len(b_outs)
                if conn_cnt > max_conns:
                    max_conns = conn_cnt
                    best_toon_path = ftn_val
        except Exception:
            pass

    if best_toon_path:
        _apply_toon_color_to_mmd_lights(_extract_toon_shadow_color(best_toon_path))
    else:
        if dir_shapes:
            mc.setAttr(f"{dir_shapes[0]}.color", 1.0, 1.0, 1.0, typ='double3')
            mc.setAttr(f"{dir_shapes[0]}.intensity", 0.25)
        if amb_shapes:
            mc.setAttr(f"{amb_shapes[0]}.color", 1.0, 1.0, 1.0, typ='double3')
            mc.setAttr(f"{amb_shapes[0]}.intensity", 0.75)

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

            # ライトのワールドマトリクスからオブジェクトへの到来光線ベクトル（ローカル+Z）を動的算出
            dir_lights = mc.ls("mmd_directional_light*", type='transform') or mc.ls(type='directionalLight') or []
            target_dir_light = dir_lights[0] if dir_lights else None
            if target_dir_light and mc.nodeType(target_dir_light) == 'directionalLight':
                target_dir_light = (mc.listRelatives(target_dir_light, parent=True, fullPath=True) or [None])[0]

            if target_dir_light and mc.objExists(target_dir_light):
                suffix = vp.replace("toon_vecprod_", "")
                lvec_name = f"toon_lvec_{suffix}"
                if not mc.objExists(lvec_name):
                    lvec_node = mc.shadingNode('vectorProduct', asUtility=True, name=lvec_name)
                else:
                    lvec_node = lvec_name
                mc.setAttr(f"{lvec_node}.operation", 3) # Vector Matrix Product
                mc.setAttr(f"{lvec_node}.normalizeOutput", True)
                mc.setAttr(f"{lvec_node}.input1", 0.0, 0.0, 1.0, typ='double3')
                mc.connectAttr(f"{target_dir_light}.worldMatrix[0]", f"{lvec_node}.matrix", force=True)
                mc.connectAttr(f"{lvec_node}.output", f"{vp}.input2", force=True)
            else:
                # 顔・首・襟元の落ち影を自然に出す正面斜め上ライト [-25.0, 20.0, 0.0] の単位方向ベクトル
                mc.setAttr(f"{vp}.input2", 0.3099, 0.4226, 0.8517, typ='double3')

            fixed_count += 1
        except Exception:
            pass

    # MMD標準地面影プレーンの生成・確認
    try:
        create_mmd_ground_shadow()
    except Exception:
        pass

    # toon_range ノードのしきい値更新（MMD準拠の遷移幅かつ境目なく自然に広がる設定）
    range_nodes = mc.ls("toon_range_*", type="setRange") or []
    for r_node in range_nodes:
        try:
            mc.setAttr(f"{r_node}.minX", 0.0)
            mc.setAttr(f"{r_node}.maxX", 1.0)
            mc.setAttr(f"{r_node}.oldMinX", -0.05)
            mc.setAttr(f"{r_node}.oldMaxX", 0.35)
            fixed_count += 1
        except Exception:
            pass

    # 旧シーンに存在する受光分母除算ノードの無効化（落ち影内部の逆グラデーション白縁を解消）
    denom_nodes = mc.ls("toon_denom_range_*", type="setRange") or []
    for d_node in denom_nodes:
        try:
            mc.setAttr(f"{d_node}.minX", 1.0)
            mc.setAttr(f"{d_node}.maxX", 1.0)
            mc.setAttr(f"{d_node}.oldMinX", 0.0)
            mc.setAttr(f"{d_node}.oldMaxX", 1.0)
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


def find_model_bone(target_model_node=None, target_bone_name="右手"):
    """
    モデル内の指定ボーン名に対応するMayaジョイントノードを検索します。

    引数:
        target_model_node (str, optional): 対象モデルのノード名
        target_bone_name (str): 検索するボーン名 (例: '右手', '左手', '頭', '腰')

    戻り値:
        str or None: 見つかったジョイント名
    """
    if not target_bone_name:
        return None

    # ボーン名エイリアス定義
    target_norm = unicodedata.normalize('NFKC', target_bone_name).strip()
    candidates = [target_norm]

    en_name = get_english_bone_name(target_norm)
    if en_name:
        candidates.append(en_name)
    jp_name = get_japanese_bone_name(target_norm)
    if jp_name:
        candidates.append(jp_name)

    # 探索対象ジョイントの収集
    if target_model_node and mc.objExists(target_model_node):
        joints = mc.listRelatives(target_model_node, allDescendents=True, type='joint') or []
        if mc.nodeType(target_model_node) == 'joint':
            joints.append(target_model_node)
    else:
        joints = mc.ls(type='joint') or []

    # originalName アトリビュートでの一致探索
    for j in joints:
        if mc.attributeQuery('originalName', node=j, exists=True):
            orig = mc.getAttr(f"{j}.originalName") or ""
            orig_norm = unicodedata.normalize('NFKC', orig).strip()
            if orig_norm in candidates:
                return j

    # ジョイント名そのものでの一致探索
    for j in joints:
        short_name = j.split('|')[-1].split(':')[-1]
        short_norm = unicodedata.normalize('NFKC', short_name).strip()
        for cand in candidates:
            if cand.lower() == short_norm.lower() or cand.lower() in short_norm.lower():
                return j

    return joints[0] if joints else None


def attach_accessory_to_bone(accessory_node, target_model_node=None, target_bone_name="右手", maintain_offset=True):
    """
    アクセサリ（.x / .pmx / 任意メッシュ）をモデルのボーンへ追従アタッチします。
    位置・角度の微調整が可能なオフセットグループ構造を自動構築します。

    引数:
        accessory_node (str): アタッチするアクセサリのノード名
        target_model_node (str, optional): 対象モデルルートノード名
        target_bone_name (str): アタッチ先ボーン名（'頭', '右手', '左手', '腰', '胸' 等）
        maintain_offset (bool): 現在の位置関係を維持するかどうか

    戻り値:
        dict: アタッチ結果
    """
    if not accessory_node or not mc.objExists(accessory_node):
        raise ValueError(f"アクセサリノードが存在しません: {accessory_node}")

    bone_node = find_model_bone(target_model_node, target_bone_name)
    if not bone_node or not mc.objExists(bone_node):
        raise ValueError(f"アタッチ先ボーンが見つかりません: {target_bone_name}")

    # 既存の追従コンストレイントをクリーンアップ
    detach_accessory(accessory_node)

    # オフセット微調整用親グループの構築
    acc_parent = (mc.listRelatives(accessory_node, parent=True) or [None])[0]
    grp_name = f"{accessory_node}_attachOffset_grp"

    if not mc.objExists(grp_name):
        offset_grp = mc.group(empty=True, name=grp_name)
        # ジョイント位置へ移動（maintain_offsetがFalseの場合）
        if not maintain_offset:
            b_pos = mc.xform(bone_node, query=True, worldSpace=True, translation=True)
            b_rot = mc.xform(bone_node, query=True, worldSpace=True, rotation=True)
            mc.xform(offset_grp, worldSpace=True, translation=b_pos, rotation=b_rot)

        if acc_parent:
            offset_grp = mc.parent(offset_grp, acc_parent)[0]
        mc.parent(accessory_node, offset_grp)
    else:
        offset_grp = grp_name

    # 親子コンストレイント（移動＋回転）の接続
    constraint = mc.parentConstraint(bone_node, offset_grp, maintainOffset=maintain_offset, name=f"{accessory_node}_pConstraint")[0]

    # アタッチ情報のメタデータ記録
    if not mc.attributeQuery('mmdAttachedBone', node=accessory_node, exists=True):
        mc.addAttr(accessory_node, longName='mmdAttachedBone', dataType='string')
    mc.setAttr(f"{accessory_node}.mmdAttachedBone", bone_node, typ='string')

    print(f"[アクセサリアタッチ終了] '{accessory_node}' を '{bone_node}' ({target_bone_name}) に追従接続しました。")
    return {
        'accessory': accessory_node,
        'bone': bone_node,
        'offset_group': offset_grp,
        'constraint': constraint
    }


def detach_accessory(accessory_node):
    """
    アクセサリの追従コンストレイントを解除し、独立化します。

    引数:
        accessory_node (str): 解除するアクセサリのノード名

    戻り値:
        bool: 解除成功かどうか
    """
    if not accessory_node or not mc.objExists(accessory_node):
        return False

    grp_name = f"{accessory_node}_attachOffset_grp"
    target_grp = grp_name if mc.objExists(grp_name) else accessory_node

    # 親コンストレイントの探索と削除
    constraints = mc.listConnections(target_grp, type='parentConstraint') or []
    for c in set(constraints):
        try:
            mc.delete(c)
        except Exception:
            pass

    # アタッチアトリビュートの削除
    if mc.attributeQuery('mmdAttachedBone', node=accessory_node, exists=True):
        try:
            mc.deleteAttr(f"{accessory_node}.mmdAttachedBone")
        except Exception:
            pass

    print(f"[アクセサリ解除終了] '{accessory_node}' の追従コンストレイントを解除しました。")
    return True


def disable_stage_and_skydome_edges_and_bones():
    """
    シーン内に存在するスカイドームおよびステージモデルを自動検出し、
    エッジ描画の無効化（白浮き・突き抜け抑止）およびボーンの非表示化を一括適用します。
    """
    try:
        try:
            from ..asset.model_classifier_manager import ModelClassifierManager
        except Exception:
            from asset.model_classifier_manager import ModelClassifierManager
        mgr = ModelClassifierManager.get_instance()
    except Exception:
        mgr = None

    all_meshes = mc.ls(type="mesh", long=True) or []
    target_stage_meshes = []
    target_skydome_meshes = []

    for m in all_meshes:
        if "mmd_ground_shadow" in m or any(k in m for k in ["Camera", "Light", "light", "mmd_rigid", "mmd_joint"]):
            continue
        if is_skydome_mesh(m):
            target_skydome_meshes.append(m)
        elif mgr and mgr.is_stage_mesh(m):
            target_stage_meshes.append(m)

    target_meshes = list(dict.fromkeys(target_skydome_meshes + target_stage_meshes))
    if not target_meshes:
        print("[情報] シーン内にスカイドームまたはステージモデルは検出されませんでした。")
        return False

    # エッジ描画の無効化
    for m in target_meshes:
        disable_mesh_edges(m)
        parent_tr = mc.listRelatives(m, parent=True, fullPath=True)
        if parent_tr:
            disable_mesh_edges(parent_tr[0])

    # ボーン（ジョイント）の非表示化
    hidden_joints_count = 0
    all_joints = mc.ls(type="joint", long=True) or []
    for j in all_joints:
        j_short = j.split('|')[-1]
        # ステージ・スカイドームに属するジョイントか判定
        for m in target_meshes:
            p_name = mc.listRelatives(m, parent=True)
            p_prefix = p_name[0] if p_name else ""
            if p_prefix and (j_short.startswith(f"{p_prefix}_") or p_prefix in j):
                try:
                    mc.setAttr(f"{j}.drawStyle", 2)
                    mc.setAttr(f"{j}.visibility", False)
                    hidden_joints_count += 1
                except Exception:
                    pass
                break

    print(f"[適用終了] スカイドーム/ステージ ({len(target_meshes)} メッシュ) のエッジ描画を無効化し、{hidden_joints_count} 個のジョイントを非表示にしました。")
    return True


def build_bones_and_skin_for_model(model_node, file_path=None, scale=8.0, use_cpp_fast=True):
    """
    ボーンが存在しないモデルに対し、PMXファイル情報からボーン階層を構築してスキニングウェイトを設定します。

    引数:
        model_node (str): 対象MMDモデルのルートTransformまたはMeshノード名
        file_path (str, optional): PMXファイルの絶対パス。省略時はノードアトリビュートから探索
        scale (float): スケール倍率（標準: 8.0）
        use_cpp_fast (bool): C++プラグインによるウェイト高速注入を利用するかどうか
    戻り値:
        tuple: (生成されたジョイント名リスト, ルートジョイント名リスト, スキンクラスタ名) 失敗時は None
    """
    if not mc.objExists(model_node):
        print(f"[エラー] 指定されたモデルノード '{model_node}' がシーン内に存在しません。")
        return None

    # メッシュノードの解決
    model_mesh_node = model_node
    if mc.nodeType(model_node) != "mesh":
        child_meshes = mc.listRelatives(model_node, shapes=True, type="mesh") or []
        if child_meshes:
            model_mesh_node = child_meshes[0]
        else:
            desc_meshes = mc.listRelatives(model_node, allDescendents=True, type="mesh") or []
            if desc_meshes:
                model_mesh_node = desc_meshes[0]

    # PMXファイルパスの解決
    resolved_path = file_path
    if not resolved_path:
        # ノード自身および親・子孫のアトリビュートから探索
        nodes_to_check = [model_node, model_mesh_node]
        p_nodes = mc.listRelatives(model_node, parent=True) or []
        nodes_to_check.extend(p_nodes)

        for n in nodes_to_check:
            if mc.attributeQuery('mmdModelPath', node=n, exists=True):
                p = mc.getAttr(f"{n}.mmdModelPath")
                if p and os.path.isfile(p):
                    resolved_path = p
                    break

    if not resolved_path or not os.path.isfile(resolved_path):
        print(f"[エラー] PMXファイルパスが解決できませんでした: {resolved_path}")
        return None

    print(f"[ボーン作成開始] 対象モデル: {model_mesh_node}, PMX: {resolved_path}")

    # PMXモデルの構文解析
    try:
        try:
            from .. import mmd_parser
        except Exception:
            import mmd_parser
        pmx_model = mmd_parser.pmx.load(resolved_path)
    except Exception as e:
        print(f"[エラー] PMXファイルの読み込みに失敗しました: {e}")
        return None

    if not getattr(pmx_model, 'bones', None):
        print("[警告] PMXファイル内にボーンデータが存在しません。")
        return None

    # 既存の同名スキンクラスタが存在する場合は事前にバインド解除
    existing_skins = mc.ls(type="skinCluster") or []
    for sc in existing_skins:
        geoms = mc.skinCluster(sc, query=True, geometry=True) or []
        if model_mesh_node in geoms:
            try:
                mc.skinCluster(model_mesh_node, edit=True, unbind=True)
                print(f"  - 既存のスキンクラスタ {sc} を解除しました")
            except Exception:
                pass

    # ジョイント階層の生成
    joint_node_names = []
    root_joint_names = []
    name_tracker = set()
    root_node_prefix = model_node.split('|')[-1].split(':')[-1]

    for b_idx, bone in enumerate(pmx_model.bones):
        mc.select(clear=True)
        bone_name_e = getattr(bone, 'name_e', None)
        safe_bone_id = safe_node_name(bone.name, name_e=bone_name_e, prefix="bone", index=b_idx)

        unique_bone_name = f"{root_node_prefix}_{safe_bone_id}"
        if unique_bone_name in name_tracker:
            unique_bone_name = f"{unique_bone_name}_{b_idx}"
        name_tracker.add(unique_bone_name)

        loc = bone.location
        if 'yubi' in safe_bone_id or 'finger' in safe_bone_id.lower():
            radius = scale / 4.0
        elif 'center' in safe_bone_id.lower() or 'sentaa' in safe_bone_id:
            radius = scale
        else:
            radius = scale / 2.0

        pos = [loc[0] * scale, loc[1] * scale, -loc[2] * scale]
        j_node = mc.joint(position=pos, radius=radius, name=unique_bone_name)

        if not mc.attributeQuery('originalName', node=j_node, exists=True):
            mc.addAttr(j_node, longName='originalName', niceName='元の名称', dataType='string')
        mc.setAttr(f"{j_node}.originalName", bone.name, typ='string')

        if getattr(bone, 'name_e', None):
            if not mc.attributeQuery('englishName', node=j_node, exists=True):
                mc.addAttr(j_node, longName='englishName', niceName='英語名称', dataType='string')
            mc.setAttr(f"{j_node}.englishName", bone.name_e, typ='string')

        if bone.isIK or not bone.visible:
            mc.setAttr(f"{j_node}.drawStyle", 2) # 非表示
        else:
            mc.setAttr(f"{j_node}.drawStyle", 0)

        bone_name_raw = getattr(bone, 'name', '') or ''
        if 'ひざ' in bone_name_raw or '膝' in bone_name_raw or 'knee' in bone_name_raw.lower():
            try:
                mc.setAttr(f"{j_node}.preferredAngleX", 60.0)
                mc.setAttr(f"{j_node}.preferredAngleY", 0.0)
                mc.setAttr(f"{j_node}.preferredAngleZ", 0.0)
            except Exception:
                pass

        joint_node_names.append(j_node)

    # 親子階層の結合
    for b_idx, bone in enumerate(pmx_model.bones):
        child_j = joint_node_names[b_idx]
        if 0 <= bone.parent < len(joint_node_names):
            parent_j = joint_node_names[bone.parent]
            mc.connectJoint(child_j, parent_j, parentMode=True)
        else:
            root_joint_names.append(child_j)

        # 付与親エクスプレッション生成
        if getattr(bone, 'hasAdditionalRotate', False):
            target_idx = bone.additionalTransform[0]
            if 0 <= target_idx < len(joint_node_names):
                effect_j = joint_node_names[target_idx]
                ratio = bone.additionalTransform[1]
                b_name = bone.name
                is_twist = any(k in b_name for k in ["腕捩", "手捩"])
                if is_twist:
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
                try:
                    mc.expression(string=expr, name=f"expr_rot_{child_j}_{effect_j}")
                except Exception:
                    pass

        if getattr(bone, 'hasAdditionalLocation', False):
            target_idx = bone.additionalTransform[0]
            if 0 <= target_idx < len(joint_node_names):
                effect_j = joint_node_names[target_idx]
                ratio = bone.additionalTransform[1]
                expr = (
                    f"{child_j}.translateX = {effect_j}.translateX * {ratio};\n"
                    f"{child_j}.translateY = {effect_j}.translateY * {ratio};\n"
                    f"{child_j}.translateZ = {effect_j}.translateZ * {ratio};\n"
                )
                try:
                    mc.expression(string=expr, name=f"expr_loc_{child_j}_{effect_j}")
                except Exception:
                    pass

    # 初期基準座標の記録
    for j_node in joint_node_names:
        try:
            if not mc.attributeQuery('mmdInitialTranslate', node=j_node, exists=True):
                cur_t = mc.getAttr(f"{j_node}.translate")[0]
                mc.addAttr(j_node, longName='mmdInitialTranslate', attributeType='double3')
                mc.addAttr(j_node, longName='mmdInitialTranslateX', attributeType='double', parent='mmdInitialTranslate')
                mc.addAttr(j_node, longName='mmdInitialTranslateY', attributeType='double', parent='mmdInitialTranslate')
                mc.addAttr(j_node, longName='mmdInitialTranslateZ', attributeType='double', parent='mmdInitialTranslate')
                mc.setAttr(f"{j_node}.mmdInitialTranslate", cur_t[0], cur_t[1], cur_t[2], type='double3')
        except Exception:
            pass

    # スキニングウェイト設定
    skin_cluster_name = f"skin_{root_node_prefix}"
    skin_cluster = mc.skinCluster(
        joint_node_names, model_mesh_node,
        maximumInfluences=4, toSelectedBones=True, name=skin_cluster_name
    )[0]

    weights_applied = False
    if use_cpp_fast and hasattr(mc, "mmdFastApplyPmxSkinWeights"):
        try:
            cpp_res = mc.mmdFastApplyPmxSkinWeights(resolved_path, model_mesh_node, skin_cluster)
            if cpp_res == 1:
                weights_applied = True
                print("  - C++ (mmd_fast.mll) によるスキニングウェイト高速注入を実行しました")
        except Exception as e_cpp:
            print(f"  [情報] C++ スキニングウェイト注入から Python フォールバックへ移行: {e_cpp}")
            weights_applied = False

    if not weights_applied:
        try:
            sel = om.MSelectionList()
            sel.add(model_mesh_node)
            dag_path_mesh = sel.getDagPath(0)

            sel = om.MSelectionList()
            sel.add(skin_cluster)
            skin_mobject = sel.getDependNode(0)
            fn_skin = oma.MFnSkinCluster(skin_mobject)

            num_joints = len(pmx_model.bones)
            all_weights = []

            for vtx in pmx_model.vertices:
                w = [0.0] * num_joints
                w_type = vtx.weight.type
                bones = vtx.weight.bones
                weights = vtx.weight.weights

                try:
                    if w_type == mmd_parser.pmx.BoneWeight.BDEF1:
                        b0 = bones[0]
                        if 0 <= b0 < num_joints:
                            w[b0] = 1.0
                        elif num_joints > 0:
                            w[0] = 1.0
                    elif w_type == mmd_parser.pmx.BoneWeight.BDEF2:
                        b0, b1 = bones[0], bones[1]
                        w0 = weights[0]
                        if 0 <= b0 < num_joints:
                            w[b0] += w0
                        if 0 <= b1 < num_joints:
                            w[b1] += (1.0 - w0)
                    elif w_type == mmd_parser.pmx.BoneWeight.SDEF:
                        b0, b1 = bones[0], bones[1]
                        s_weight = weights.weight if hasattr(weights, 'weight') else 0.5
                        if 0 <= b0 < num_joints:
                            w[b0] += s_weight
                        if 0 <= b1 < num_joints:
                            w[b1] += (1.0 - s_weight)
                    elif w_type == mmd_parser.pmx.BoneWeight.BDEF4 or w_type == getattr(mmd_parser.pmx.BoneWeight, 'QDEF', 4):
                        for idx in range(4):
                            b_i = bones[idx]
                            if 0 <= b_i < num_joints:
                                w[b_i] += weights[idx]
                except Exception:
                    pass

                sum_w = sum(w)
                if sum_w <= 0.00001 or math.isnan(sum_w):
                    w[0] = 1.0
                else:
                    inv_sum = 1.0 / sum_w
                    w = [val * inv_sum for val in w]

                all_weights.extend(w)

            fn_mesh = om.MFnMesh(dag_path_mesh)
            num_verts = fn_mesh.numVertices

            single_comp = om.MFnSingleIndexedComponent()
            vertex_comp = single_comp.create(om.MFn.kMeshVertComponent)
            single_comp.addElements(list(range(num_verts)))

            influence_indices = om.MIntArray(range(num_joints))
            weights_array = om.MDoubleArray(all_weights)

            fn_skin.setWeights(dag_path_mesh, vertex_comp, influence_indices, weights_array, False)
            print(f"  - Python (OpenMaya) による頂点ウェイト設定が終了しました ({num_verts} 頂点)")
        except Exception as e_py_w:
            print(f"  [警告] Python による頂点ウェイト設定中にエラー: {e_py_w}")

    # 足IKシステムの構築
    try:
        ik_handles = setup_mmd_ik(pmx_model, joint_node_names, scale=scale)
        if ik_handles:
            print(f"  - 足IKシステム ({len(ik_handles)}個) を構築しました")
    except Exception as e_ik:
        print(f"  [警告] 足IKシステムの構築中にエラー: {e_ik}")

    # モデルルートへのジョイント階層親付け
    if mc.objExists(model_node) and root_joint_names:
        for r_j in root_joint_names:
            try:
                # 既に親付けされていない場合のみ親付け
                cur_parent = mc.listRelatives(r_j, parent=True)
                if not cur_parent or cur_parent[0] != model_node:
                    mc.parent(r_j, model_node)
            except Exception:
                pass

    print(f"[ボーン作成終了] 計 {len(joint_node_names)} 個のジョイントを生成し、メッシュへのスキニングを確立しました。")
    return joint_node_names, root_joint_names, skin_cluster


# 後方互換性用エイリアス
sang = import_pmx