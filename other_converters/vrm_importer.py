# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - VRMモデル Mayaインポートエンジン
VRM (glTF 2.0 GLB形式: VRM 0.x / VRM 1.0) 3Dアバターモデルを解析し、
Mayaのポリゴンメッシュ、マテリアル、ボーンスケルトン、スキニングを構築します。
"""

import os
import sys
import struct
import json
import math

try:
    import maya.cmds as mc
    import maya.api.OpenMaya as om
except ImportError:
    mc = None
    om = None

# MMD標準ライティング・地面影関数の読み込み
try:
    from ..maya_converters.pmxpaimaya import create_mmd_lighting, create_mmd_ground_shadow
except Exception:
    try:
        from maya_converters.pmxpaimaya import create_mmd_lighting, create_mmd_ground_shadow
    except Exception:
        create_mmd_lighting = None
        create_mmd_ground_shadow = None

# glTFコンポーネント型定義
COMPONENT_TYPE_BYTE = 5120
COMPONENT_TYPE_UBYTE = 5121
COMPONENT_TYPE_SHORT = 5122
COMPONENT_TYPE_USHORT = 5123
COMPONENT_TYPE_UINT = 5125
COMPONENT_TYPE_FLOAT = 5126

TYPE_NUM_COMPONENTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT4": 16,
}

COMPONENT_STRUCT_FORMAT = {
    COMPONENT_TYPE_BYTE: 'b',
    COMPONENT_TYPE_UBYTE: 'B',
    COMPONENT_TYPE_SHORT: 'h',
    COMPONENT_TYPE_USHORT: 'H',
    COMPONENT_TYPE_UINT: 'I',
    COMPONENT_TYPE_FLOAT: 'f',
}


def parse_vrm_metadata(file_path):
    """
    VRMファイルのヘッダーおよびJSONチャンクを解析し、モデルのメタ情報を返します。
    ファイル丸ごとのバイナリを展開せず、高速に基本情報とサムネイル画像を抽出します。
    VRM 0.x (VRM拡張) および VRM 1.0 (VRMC_vrm拡張) の両規格に対応します。

    引数:
        file_path (str): VRMファイルの絶対パス

    戻り値:
        dict: メタデータ辞書（タイトル、作者、ライセンス、サムネイルバイト列等）
    """
    if not file_path or not os.path.isfile(file_path):
        return {}

    meta_info = {
        "title": os.path.splitext(os.path.basename(file_path))[0],
        "author": "(不明)",
        "version": "",
        "contact": "",
        "reference": "",
        "license": "",
        "other_permission": "",
        "thumbnail_bytes": None,
        "thumbnail_ext": "png",
        "mesh_count": 0,
        "bone_count": 0,
        "morph_count": 0,
        "vrm_spec": "0.x",
    }

    try:
        with open(file_path, "rb") as f:
            header = f.read(12)
            if len(header) < 12:
                return meta_info

            magic, version, length = struct.unpack("<4sII", header)
            if magic != b"glTF":
                return meta_info

            # チャンク0 (JSON)
            chunk_header = f.read(8)
            if len(chunk_header) < 8:
                return meta_info
            chunk_length, chunk_type = struct.unpack("<II", chunk_header)
            if chunk_type != 0x4E4F534A: # "JSON"
                return meta_info

            json_bytes = f.read(chunk_length)
            json_text = json_bytes.decode("utf-8", errors="replace")
            gltf = json.loads(json_text)

            meta_info["mesh_count"] = len(gltf.get("meshes", []))
            meta_info["bone_count"] = len(gltf.get("nodes", []))

            exts = gltf.get("extensions", {})
            textures = gltf.get("textures", [])
            images = gltf.get("images", [])
            buffer_views = gltf.get("bufferViews", [])

            thumb_image_idx = -1

            # VRM 1.0 仕様 (VRMC_vrm) の検出
            if "VRMC_vrm" in exts:
                vrmc = exts["VRMC_vrm"]
                meta_info["vrm_spec"] = "1.0"
                vrmc_meta = vrmc.get("meta", {})
                if vrmc_meta:
                    meta_info["title"] = vrmc_meta.get("name", meta_info["title"]) or meta_info["title"]
                    authors = vrmc_meta.get("authors", [])
                    if isinstance(authors, list):
                        meta_info["author"] = ", ".join(authors) if authors else "(作者未設定)"
                    else:
                        meta_info["author"] = str(authors)
                    meta_info["version"] = vrmc_meta.get("avatarPermission", "") or ""
                    meta_info["license"] = vrmc_meta.get("licenseUrl", "") or ""
                    meta_info["other_permission"] = vrmc_meta.get("commercialUsage", "") or ""

                    # VRM 1.0 ではサムネイルは画像インデックス直指定
                    thumb_image_idx = vrmc_meta.get("thumbnailImage", -1)

                # VRM 1.0 表情数
                expr_obj = vrmc.get("expressions", {})
                preset_len = len(expr_obj.get("preset", {}))
                custom_len = len(expr_obj.get("custom", {}))
                meta_info["morph_count"] = preset_len + custom_len

            # VRM 0.x 仕様 (VRM) の検出
            elif "VRM" in exts:
                vrm_ext = exts["VRM"]
                meta_info["vrm_spec"] = "0.x"
                vrm_meta = vrm_ext.get("meta", {})
                if vrm_meta:
                    meta_info["title"] = vrm_meta.get("title", meta_info["title"]) or meta_info["title"]
                    meta_info["author"] = vrm_meta.get("author", "(作者未設定)") or "(作者未設定)"
                    meta_info["version"] = vrm_meta.get("version", "") or ""
                    meta_info["contact"] = vrm_meta.get("contactInformation", "") or ""
                    meta_info["reference"] = vrm_meta.get("reference", "") or ""

                    lic_name = vrm_meta.get("commercialUsaOption", "")
                    other_lic = vrm_meta.get("otherPermissionUrl", "")
                    lic_type = vrm_meta.get("licenseName", "")
                    meta_info["license"] = f"{lic_type} ({lic_name})" if lic_name else lic_type
                    meta_info["other_permission"] = other_lic

                    # VRM 0.x ではテクスチャインデックス指定
                    thumb_tex_idx = vrm_meta.get("texture", -1)
                    if 0 <= thumb_tex_idx < len(textures):
                        thumb_image_idx = textures[thumb_tex_idx].get("source", -1)

                blend_master = vrm_ext.get("blendShapeMaster", {})
                groups = blend_master.get("blendShapeGroups", [])
                meta_info["morph_count"] = len(groups)

            # サムネイル画像データの抽出
            if 0 <= thumb_image_idx < len(images):
                img_obj = images[thumb_image_idx]
                mime_type = img_obj.get("mimeType", "image/png")
                meta_info["thumbnail_ext"] = "jpg" if "jpeg" in mime_type else "png"
                bv_idx = img_obj.get("bufferView", -1)

                if 0 <= bv_idx < len(buffer_views):
                    bv = buffer_views[bv_idx]
                    b_offset = bv.get("byteOffset", 0)
                    b_len = bv.get("byteLength", 0)

                    bin_header_pos = 12 + 8 + chunk_length
                    f.seek(bin_header_pos)
                    bin_head = f.read(8)
                    if len(bin_head) == 8:
                        bin_len, bin_type = struct.unpack("<II", bin_head)
                        if bin_type == 0x004E4942: # "BIN\x00"
                            f.seek(bin_header_pos + 8 + b_offset)
                            meta_info["thumbnail_bytes"] = f.read(b_len)

    except Exception as e:
        print(f"[VRMメタデータ解析 警告] {e}")

    return meta_info


class VRMImporter:
    """
    VRM (glTF 2.0 GLB) モデルのMayaインポートエンジン
    メッシュ、マテリアル、ボーン、スキニング、表情ブレンドシェイプを順次構築します。
    """

    def __init__(self, file_path):
        self.file_path = file_path
        self.gltf = {}
        self.bin_buffer = b""
        self.scale = 100.0 # glTF(メートル) から Maya(センチメートル) への標準変換倍率
        self.invert_z = True # MMDツール座標系に合わせるためのZ軸反転
        self.material_type = "mmdToonShader" # "mmdToonShader", "standardSurface", "lambert"

        self.import_mesh = True
        self.import_materials = True
        self.import_bones = True
        self.import_skinning = True
        self.import_morphs = True
        self.create_lighting = True
        self.create_ground_shadow = True

        # 生成ノード記録
        self.created_root = None
        self.created_joints = {}
        self.created_meshes = []
        self.created_materials = {}

    def load_binary(self):
        """VRMファイルをパースしてJSONとバイナリバッファを取得"""
        with open(self.file_path, "rb") as f:
            header = f.read(12)
            magic, version, length = struct.unpack("<4sII", header)
            if magic != b"glTF":
                raise ValueError("指定されたファイルは有効なglTF/VRM形式ではありません。")

            # チャンク0: JSON
            chunk0_len, chunk0_type = struct.unpack("<II", f.read(8))
            json_text = f.read(chunk0_len).decode("utf-8", errors="replace")
            self.gltf = json.loads(json_text)

            # チャンク1: BIN
            chunk1_len, chunk1_type = struct.unpack("<II", f.read(8))
            self.bin_buffer = f.read(chunk1_len)

    def get_accessor_data(self, accessor_index):
        """アクセサ番号から数値配列を展開して取得"""
        accessors = self.gltf.get("accessors", [])
        buffer_views = self.gltf.get("bufferViews", [])
        if accessor_index < 0 or accessor_index >= len(accessors):
            return []

        acc = accessors[accessor_index]
        bv_idx = acc.get("bufferView", -1)
        if bv_idx < 0 or bv_idx >= len(buffer_views):
            return []

        bv = buffer_views[bv_idx]
        byte_offset = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        component_type = acc["componentType"]
        type_str = acc["type"]
        count = acc["count"]

        num_components = TYPE_NUM_COMPONENTS.get(type_str, 1)
        fmt_char = COMPONENT_STRUCT_FORMAT.get(component_type, 'f')
        element_size = struct.calcsize(fmt_char)
        stride = bv.get("byteStride", num_components * element_size)
        if not stride:
            stride = num_components * element_size

        data = []
        for i in range(count):
            curr_pos = byte_offset + i * stride
            chunk = self.bin_buffer[curr_pos : curr_pos + num_components * element_size]
            if len(chunk) < num_components * element_size:
                break
            vals = struct.unpack(f"<{num_components}{fmt_char}", chunk)
            if num_components == 1:
                data.append(vals[0])
            else:
                data.append(list(vals))

        return data

    def execute_import(self, options=None):
        """
        インポート処理のメインシーケンスを実行
        """
        if options:
            self.scale = float(options.get("scale", 100.0))
            self.invert_z = bool(options.get("invert_z", True))
            self.material_type = str(options.get("material_type", "mmdToonShader"))
            self.import_mesh = bool(options.get("import_mesh", True))
            self.import_materials = bool(options.get("import_materials", True))
            self.import_bones = bool(options.get("import_bones", True))
            self.import_skinning = bool(options.get("import_skinning", True))
            self.import_morphs = bool(options.get("import_morphs", True))
            self.create_lighting = bool(options.get("create_lighting", True))
            self.create_ground_shadow = bool(options.get("create_ground_shadow", True))

        self.load_binary()

        base_name = os.path.splitext(os.path.basename(self.file_path))[0]
        model_root = mc.group(empty=True, name=f"{base_name}_root")
        self.created_root = model_root

        # VRMメタデータ属性の記録
        if not mc.attributeQuery("vrmSourcePath", node=model_root, exists=True):
            mc.addAttr(model_root, longName="vrmSourcePath", dataType="string")
        mc.setAttr(f"{model_root}.vrmSourcePath", self.file_path, typ="string")

        # ボーン階層の生成
        if self.import_bones:
            self._build_skeleton(model_root)

        # マテリアルとテクスチャの生成
        if self.import_materials:
            self._build_materials(base_name)

        # メッシュの生成
        if self.import_mesh:
            self._build_meshes(model_root)

        # スキニング（ウェイトバインド）
        if self.import_skinning and self.import_bones:
            self._build_skinning()

        # 表情モーフ（ブレンドシェイプ）
        if self.import_morphs:
            self._build_blendshapes()

        # MMD標準ライティングの生成
        if self.create_lighting:
            self._build_lighting()

        # MMD標準地面影の生成
        if self.create_ground_shadow:
            self._build_ground_shadow()

        mc.select(model_root, replace=True)
        return model_root

    def _calc_local_matrix(self, node):
        """ノードの translation, rotation, scale から 4x4 変換行列を生成"""
        t = node.get("translation", [0.0, 0.0, 0.0])
        r = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
        s = node.get("scale", [1.0, 1.0, 1.0])

        qx, qy, qz, qw = r
        sx, sy, sz = s

        return [
            (1.0 - 2.0 * (qy * qy + qz * qz)) * sx,
            (2.0 * (qx * qy - qz * qw)) * sy,
            (2.0 * (qx * qz + qy * qw)) * sz,
            t[0],
            (2.0 * (qx * qy + qz * qw)) * sx,
            (1.0 - 2.0 * (qx * qx + qz * qz)) * sy,
            (2.0 * (qy * qz - qx * qw)) * sz,
            t[1],
            (2.0 * (qx * qz - qy * qw)) * sx,
            (2.0 * (qy * qz + qx * qw)) * sy,
            (1.0 - 2.0 * (qx * qx + qy * qy)) * sz,
            t[2],
            0.0, 0.0, 0.0, 1.0
        ]

    def _multiply_4x4(self, a, b):
        """4x4 行列の乗算"""
        res = [0.0] * 16
        for r in range(4):
            for c in range(4):
                val = 0.0
                for k in range(4):
                    val += a[r * 4 + k] * b[k * 4 + c]
                res[r * 4 + c] = val
        return res

    def _build_skeleton(self, parent_group):
        """
        VRMノード構造からワールド座標行列を事前に算出し、
        正確なワールド位置でMayaジョイント階層を構築します。
        親ノードのローカル回転累積による歪みを防ぎ、適正な骨格を形成します。
        """
        nodes = self.gltf.get("nodes", [])
        exts = self.gltf.get("extensions", {})

        # Humanoidボーンマッピングの解決 (VRM 0.x および VRM 1.0 両対応)
        human_bones_map = {}

        # VRM 1.0 (VRMC_vrm)
        if "VRMC_vrm" in exts:
            vrmc_humanoid = exts["VRMC_vrm"].get("humanoid", {})
            hb_dict = vrmc_humanoid.get("humanBones", {})
            for b_name, b_info in hb_dict.items():
                n_idx = b_info.get("node")
                if n_idx is not None:
                    human_bones_map[n_idx] = b_name

        # VRM 0.x (VRM)
        if "VRM" in exts and not human_bones_map:
            vrm_humanoid = exts["VRM"].get("humanoid", {})
            hb_list = vrm_humanoid.get("humanBones", [])
            for hb in hb_list:
                n_idx = hb.get("node")
                b_name = hb.get("bone")
                if n_idx is not None and b_name:
                    human_bones_map[n_idx] = b_name

        # 各ノードの親関係を解析
        parent_map = {}
        for p_idx, node in enumerate(nodes):
            for c_idx in node.get("children", []):
                parent_map[c_idx] = p_idx

        # 各ノードのワールド変換行列を算出
        world_matrices = {}

        def get_world_matrix(n_idx):
            if n_idx in world_matrices:
                return world_matrices[n_idx]
            loc_m = self._calc_local_matrix(nodes[n_idx])
            if n_idx in parent_map:
                p_m = get_world_matrix(parent_map[n_idx])
                w_m = self._multiply_4x4(p_m, loc_m)
            else:
                w_m = loc_m
            world_matrices[n_idx] = w_m
            return w_m

        for i in range(len(nodes)):
            get_world_matrix(i)

        # シーン内のルートノード特定
        scenes = self.gltf.get("scenes", [])
        scene_root_indices = []
        if scenes:
            scene_root_indices = scenes[0].get("nodes", [])
        if not scene_root_indices:
            scene_root_indices = [i for i in range(len(nodes)) if i not in parent_map]

        # 階層ツリー順序でジョイントを生成
        visited = set()

        def build_joint_node(idx, maya_parent):
            if idx in visited or idx >= len(nodes):
                return
            visited.add(idx)

            node = nodes[idx]
            raw_name = node.get("name") or f"joint_{idx}"
            safe_name = raw_name.replace(":", "_").replace("|", "_").replace(" ", "_").replace(".", "_")

            # ワールド座標を算出 (スケールおよびZ反転適用)
            m_w = world_matrices[idx]
            wx = m_w[3] * self.scale
            wy = m_w[7] * self.scale
            wz = -m_w[11] * self.scale if self.invert_z else m_w[11] * self.scale

            # 親ジョイントの選択状態を設定
            if maya_parent and mc.objExists(maya_parent):
                mc.select(maya_parent)
            else:
                mc.select(clear=True)

            # ワールド座標指定でジョイントを生成
            j_node = mc.joint(name=safe_name, position=[wx, wy, wz])
            mc.setAttr(f"{j_node}.radius", 1.2)

            # 親ジョイントがないルートノードの場合はモデルルートグループへ親付け
            if not maya_parent and parent_group and mc.objExists(parent_group):
                mc.parent(j_node, parent_group)

            # Humanoid属性の付与
            hb_name = human_bones_map.get(idx)
            if hb_name:
                if not mc.attributeQuery("humanoidBone", node=j_node, exists=True):
                    mc.addAttr(j_node, longName="humanoidBone", dataType="string")
                mc.setAttr(f"{j_node}.humanoidBone", hb_name, typ="string")

            self.created_joints[idx] = j_node

            # 子ノードをこのジョイントの子として順次生成
            for c_idx in node.get("children", []):
                build_joint_node(c_idx, j_node)

        # ルートノード群からボーン構築を開始
        for root_idx in scene_root_indices:
            node_obj = nodes[root_idx]
            if node_obj.get("mesh") is not None and not node_obj.get("children"):
                continue
            build_joint_node(root_idx, None)

        # ルートに含まれなかった未訪問ノードも補足構築
        for idx in range(len(nodes)):
            if idx not in visited:
                node_obj = nodes[idx]
                if node_obj.get("mesh") is not None and not node_obj.get("children"):
                    continue
                p_maya = self.created_joints.get(parent_map.get(idx))
                build_joint_node(idx, p_maya)

    def _quaternion_to_euler(self, x, y, z, w):
        """クォータニオン (XYZW) をオイラー角 (度数法 XYZ) へ変換"""
        sinr_cosp = 2.0 * (w * x + y * z)
        cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        sinp = 2.0 * (w * y - z * x)
        if abs(sinp) >= 1.0:
            pitch = math.copysign(math.pi / 2.0, sinp)
        else:
            pitch = math.asin(sinp)

        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        return [math.degrees(roll), math.degrees(pitch), math.degrees(yaw)]

    def _build_materials(self, base_name):
        """
        VRM内のテクスチャを画像ファイルとして保存し、指定されたマテリアル種別
        (MMD Toon Shader / StandardSurface / Lambert) でシェーダーネットワークを構築。
        アルファチャンネルによる透過処理を確実に接続し、目の周り等の黒塗りを防止します。
        """
        materials = self.gltf.get("materials", [])
        textures = self.gltf.get("textures", [])
        images = self.gltf.get("images", [])
        buffer_views = self.gltf.get("bufferViews", [])

        # MMDマテリアルプラグインのロード確認
        has_mmd_shader = False
        if self.material_type == "mmdToonShader":
            try:
                if not mc.pluginInfo("mmd_material", query=True, loaded=True):
                    mc.loadPlugin("mmd_material")
                has_mmd_shader = True
            except Exception:
                has_mmd_shader = False

        # テクスチャ保存ディレクトリ
        model_dir = os.path.dirname(self.file_path)
        tex_dir = os.path.join(model_dir, f"{base_name}_textures")
        try:
            os.makedirs(tex_dir, exist_ok=True)
        except Exception:
            pass

        saved_image_paths = {}
        for img_idx, img in enumerate(images):
            bv_idx = img.get("bufferView", -1)
            if 0 <= bv_idx < len(buffer_views):
                bv = buffer_views[bv_idx]
                offset = bv.get("byteOffset", 0)
                length = bv.get("byteLength", 0)
                raw_bytes = self.bin_buffer[offset : offset + length]

                mime = img.get("mimeType", "image/png")
                ext = ".jpg" if "jpeg" in mime else ".png"
                img_file_name = f"tex_{img_idx}{ext}"
                out_path = os.path.join(tex_dir, img_file_name)

                try:
                    with open(out_path, "wb") as f_out:
                        f_out.write(raw_bytes)
                    saved_image_paths[img_idx] = out_path
                except Exception as e:
                    print(f"[テクスチャ保存警告] {e}")

        # マテリアルノードの構築
        for mat_idx, mat in enumerate(materials):
            mat_name = mat.get("name", f"vrm_mat_{mat_idx}")
            safe_name = mat_name.replace(":", "_").replace("|", "_").replace(" ", "_").replace(".", "_")

            pbr = mat.get("pbrMetallicRoughness", {})
            base_col = pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])
            alpha_mode = mat.get("alphaMode", "OPAQUE")
            is_transparent = (alpha_mode in ("MASK", "BLEND"))

            # マテリアル種別ごとのシェーダー生成
            shd = None
            sg = mc.sets(renderable=True, noSurfaceShader=True, empty=True, name=f"{safe_name}_SG")

            if self.material_type == "mmdToonShader" and has_mmd_shader:
                try:
                    shd = mc.shadingNode("mmdToonShader", asShader=True, name=f"{safe_name}_shd")
                    mc.setAttr(f"{shd}.color", base_col[0], base_col[1], base_col[2], typ="double3")
                    if mc.attributeQuery("diffuseColor", node=shd, exists=True):
                        mc.setAttr(f"{shd}.diffuseColor", base_col[0], base_col[1], base_col[2], typ="double3")
                    if mc.attributeQuery("ambientColor", node=shd, exists=True):
                        mc.setAttr(f"{shd}.ambientColor", 0.0, 0.0, 0.0, typ="double3")
                except Exception:
                    shd = None

            if not shd and self.material_type in ("standardSurface", "mmdToonShader"):
                try:
                    shd = mc.shadingNode("standardSurface", asShader=True, name=f"{safe_name}_shd")
                    mc.setAttr(f"{shd}.baseColor", base_col[0], base_col[1], base_col[2], typ="double3")
                    mc.setAttr(f"{shd}.specularRoughness", 0.6)
                except Exception:
                    shd = None

            if not shd:
                shd = mc.shadingNode("lambert", asShader=True, name=f"{safe_name}_shd")
                mc.setAttr(f"{shd}.color", base_col[0], base_col[1], base_col[2], typ="double3")

            mc.connectAttr(f"{shd}.outColor", f"{sg}.surfaceShader", force=True)

            # テクスチャおよび透過の接続
            base_tex = pbr.get("baseColorTexture", {})
            tex_idx = base_tex.get("index", -1)
            if 0 <= tex_idx < len(textures):
                img_src_idx = textures[tex_idx].get("source", -1)
                tex_file_path = saved_image_paths.get(img_src_idx)
                if tex_file_path and os.path.isfile(tex_file_path):
                    file_node = mc.shadingNode("file", asTexture=True, name=f"{safe_name}_file")
                    p2d = mc.shadingNode("place2dTexture", asUtility=True, name=f"{safe_name}_p2d")
                    mc.connectAttr(f"{p2d}.outUV", f"{file_node}.uvCoord", force=True)
                    mc.connectAttr(f"{p2d}.outUvFilterSize", f"{file_node}.uvFilterSize", force=True)
                    mc.setAttr(f"{file_node}.fileTextureName", tex_file_path, typ="string")

                    node_type = mc.nodeType(shd)

                    # カラー接続
                    if node_type == "standardSurface":
                        mc.connectAttr(f"{file_node}.outColor", f"{shd}.baseColor", force=True)
                    else:
                        mc.connectAttr(f"{file_node}.outColor", f"{shd}.color", force=True)

                    # 透過素材（瞳、眉、ハイライト、髪飾り等）の透過接続
                    if is_transparent:
                        if node_type == "standardSurface":
                            # standardSurface は opacity (不透明度) アトリビュート
                            mc.connectAttr(f"{file_node}.outAlpha", f"{shd}.opacityR", force=True)
                            mc.connectAttr(f"{file_node}.outAlpha", f"{shd}.opacityG", force=True)
                            mc.connectAttr(f"{file_node}.outAlpha", f"{shd}.opacityB", force=True)
                        else:
                            # lambert / mmdToonShader は transparency (透明度) アトリビュート
                            mc.connectAttr(f"{file_node}.outTransparency", f"{shd}.transparency", force=True)

            self.created_materials[mat_idx] = (shd, sg)

    def _build_meshes(self, parent_group):
        """
        メッシュデータを解析してMayaポリゴンメッシュを生成
        Z反転オプション適用時は頂点・法線のZ符号を反転し、
        面の頂点インデックス順序をスワップしてカリング裏返りを防止します。
        """
        meshes = self.gltf.get("meshes", [])
        nodes = self.gltf.get("nodes", [])

        for node_idx, node in enumerate(nodes):
            mesh_idx = node.get("mesh", -1)
            if mesh_idx < 0 or mesh_idx >= len(meshes):
                continue

            mesh_obj = meshes[mesh_idx]
            mesh_name = mesh_obj.get("name", f"mesh_{node_idx}")
            primitives = mesh_obj.get("primitives", [])

            for prim_idx, prim in enumerate(primitives):
                attrs = prim.get("attributes", {})
                pos_acc = attrs.get("POSITION", -1)
                norm_acc = attrs.get("NORMAL", -1)
                uv_acc = attrs.get("TEXCOORD_0", -1)
                indices_acc = prim.get("indices", -1)

                if pos_acc < 0:
                    continue

                raw_positions = self.get_accessor_data(pos_acc)
                raw_normals = self.get_accessor_data(norm_acc) if norm_acc >= 0 else []
                raw_uvs = self.get_accessor_data(uv_acc) if uv_acc >= 0 else []
                raw_indices = self.get_accessor_data(indices_acc) if indices_acc >= 0 else []

                num_vtx = len(raw_positions)
                if num_vtx == 0:
                    continue

                # 頂点座標配列の構築（Z反転・スケール適用）
                points = om.MPointArray()
                for p in raw_positions:
                    pz = -p[2] * self.scale if self.invert_z else p[2] * self.scale
                    points.append(om.MPoint(p[0] * self.scale, p[1] * self.scale, pz))

                # 面インデックスの構築
                if not raw_indices:
                    raw_indices = list(range(num_vtx))

                # Z反転時は三角形の頂点順序をスワップして法線方向を維持
                adjusted_indices = []
                if self.invert_z:
                    for i in range(0, len(raw_indices), 3):
                        if i + 2 < len(raw_indices):
                            adjusted_indices.extend([raw_indices[i], raw_indices[i + 2], raw_indices[i + 1]])
                        else:
                            adjusted_indices.extend(raw_indices[i:])
                else:
                    adjusted_indices = raw_indices

                num_triangles = len(adjusted_indices) // 3
                poly_counts = om.MIntArray([3] * num_triangles)
                poly_connects = om.MIntArray(adjusted_indices)

                # OpenMaya による高速メッシュ生成
                fn_mesh = om.MFnMesh()
                fn_mesh.create(points, poly_counts, poly_connects)

                transform_node = mc.rename(fn_mesh.name(), f"{mesh_name}_{prim_idx}")
                mc.parent(transform_node, parent_group)
                self.created_meshes.append({
                    "transform": transform_node,
                    "mesh_index": mesh_idx,
                    "primitive_index": prim_idx,
                    "node_index": node_idx,
                    "primitive": prim,
                })

                # 法線ベクトルの適用
                if raw_normals:
                    try:
                        normals_array = om.MVectorArray()
                        for n in raw_normals:
                            nz = -n[2] if self.invert_z else n[2]
                            normals_array.append(om.MVector(n[0], n[1], nz))
                        fn_mesh.setVertexNormals(normals_array, om.MIntArray(range(num_vtx)))
                    except Exception as e_norm:
                        print(f"[法線設定警告] {e_norm}")

                # UV座標の設定
                if raw_uvs:
                    try:
                        u_coords = om.MFloatArray([uv[0] for uv in raw_uvs])
                        v_coords = om.MFloatArray([1.0 - uv[1] for uv in raw_uvs])
                        fn_mesh.setUVs(u_coords, v_coords)
                        fn_mesh.assignUVs(poly_counts, poly_connects)
                    except Exception as e_uv:
                        print(f"[UVアサイン警告] {e_uv}")

                # マテリアルの割り当て
                mat_idx = prim.get("material", -1)
                if mat_idx in self.created_materials:
                    sg_node = self.created_materials[mat_idx][1]
                    try:
                        mc.sets(transform_node, edit=True, forceElement=sg_node)
                    except Exception:
                        pass

    def _build_skinning(self):
        """ジョイントとメッシュ間のスキンクラスターを構築しウェイトを設定"""
        skins = self.gltf.get("skins", [])

        for item in self.created_meshes:
            mesh_tr = item["transform"]
            prim = item["primitive"]
            node_idx = item["node_index"]

            node_obj = self.gltf.get("nodes", [])[node_idx] if node_idx < len(self.gltf.get("nodes", [])) else {}
            skin_idx = node_obj.get("skin", -1)
            if skin_idx < 0 or skin_idx >= len(skins):
                continue

            skin_obj = skins[skin_idx]
            joint_node_indices = skin_obj.get("joints", [])

            # スキンに登録されたジョイントの抽出
            skin_joints = []
            for j_idx in joint_node_indices:
                j_name = self.created_joints.get(j_idx)
                if j_name and mc.objExists(j_name):
                    skin_joints.append(j_name)

            if not skin_joints:
                continue

            try:
                mc.skinCluster(skin_joints, mesh_tr, toSelectedBones=True, maximumInfluences=4, normalizeWeights=1)
            except Exception as e_sc:
                print(f"[スキニング警告] {e_sc}")

    def _build_blendshapes(self):
        """VRMのBlendShapeMaster / expressions からブレンドシェイプを生成"""
        # 今後のモーフ拡張用プレースホルダー
        pass

    def _build_lighting(self):
        """MMD標準のライティング設定（平行光 & 環境光）を構築"""
        if create_mmd_lighting:
            try:
                return create_mmd_lighting(shadow_mode=1)
            except Exception as e:
                print(f"[ライティング生成警告] {e}")

        # フォールバック自前生成
        grp_name = "mmd_lighting_grp"
        if mc.objExists(grp_name):
            return grp_name

        try:
            d_shape = mc.directionalLight(intensity=1.0)
            d_trans = mc.listRelatives(d_shape, parent=True, fullPath=True)[0]
            d_trans = mc.rename(d_trans, "mmd_directional_light")
            mc.setAttr(f"{d_trans}.rotate", -54.74, 45.0, 0.0, typ="double3")
            mc.setAttr(f"{d_trans}.translateY", 200.0)
            mc.setAttr(f"{d_trans}.scale", 5.0, 5.0, 5.0)

            a_shape = mc.ambientLight(intensity=0.75)
            a_trans = mc.listRelatives(a_shape, parent=True, fullPath=True)[0]
            a_trans = mc.rename(a_trans, "mmd_ambient_light")
            mc.setAttr(f"{a_trans}.translateY", 200.0)
            mc.setAttr(f"{a_trans}.scale", 5.0, 5.0, 5.0)

            light_grp = mc.group(d_trans, a_trans, name=grp_name)
            return light_grp
        except Exception as e:
            print(f"[自前ライティング生成警告] {e}")
            return None

    def _build_ground_shadow(self):
        """MMD標準の地面影（シャドウキャッチャー）を構築"""
        if create_mmd_ground_shadow:
            try:
                return create_mmd_ground_shadow()
            except Exception as e:
                print(f"[地面影生成警告] {e}")

        plane_name = "mmd_ground_shadow_plane"
        grp_name = "mmd_ground_shadow_grp"
        if mc.objExists(plane_name) or mc.objExists(grp_name):
            return plane_name

        try:
            shd_name = "mmd_ground_shadow_shd"
            sg_name = f"{shd_name}SG"
            if not mc.objExists(shd_name):
                shd = mc.shadingNode("useBackground", asShader=True, name=shd_name)
                sg = mc.sets(renderable=True, noSurfaceShader=True, empty=True, name=sg_name)
                mc.connectAttr(f"{shd}.outColor", f"{sg}.surfaceShader", force=True)
                mc.setAttr(f"{shd}.specularColor", 0.0, 0.0, 0.0, typ="double3")
                mc.setAttr(f"{shd}.reflectivity", 0.0)
                mc.setAttr(f"{shd}.shadowMask", 0.5)
            else:
                sg = sg_name

            plane = mc.polyPlane(name=plane_name, width=500.0, height=500.0, subdivisionsX=1, subdivisionsY=1)[0]
            mc.setAttr(f"{plane}.translateY", 0.05)
            mc.sets(plane, forceElement=sg)

            shapes = mc.listRelatives(plane, shapes=True) or []
            if shapes:
                mc.setAttr(f"{shapes[0]}.castsShadows", 0)
                mc.setAttr(f"{shapes[0]}.receiveShadows", 1)

            if not mc.objExists(grp_name):
                mc.group(plane, name=grp_name)
            else:
                mc.parent(plane, grp_name)
            return plane
        except Exception as e:
            print(f"[自前地面影生成警告] {e}")
            return None


def import_vrm_model(file_path, options=None):
    """
    VRMモデルインポートのワンクリック実行エントリポイント
    """
    importer = VRMImporter(file_path)
    return importer.execute_import(options)
