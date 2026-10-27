# -*- coding: utf-8 -*-
"""
mmd_core.pmx - PMX 2.0 / 2.1 独自入出力エンジン

PMX (Polygon Model eXtended) 公式バイナリフォーマットに準拠した
純粋な Python 標準ライブラリのみによる高速バイナリパーサー＆ライターです。
"""

import struct
import os
import io
import math

class PMXFormatError(Exception):
    """PMXフォーマット不正エラー"""
    pass

# ==============================================================================
# データモデル定義
# ==============================================================================
class BoneWeight:
    """スキニングウェイト情報"""
    BDEF1 = 0
    BDEF2 = 1
    BDEF4 = 2
    SDEF  = 3
    QDEF  = 4

    def __init__(self, weight_type=0):
        self.type = weight_type
        self.bones = [0, 0, 0, 0]
        self.weights = [0.0, 0.0, 0.0, 0.0]

class SdefWeights:
    """SDEF (球面変形) ウェイト情報"""
    def __init__(self, weight=0.5, c=None, r0=None, r1=None):
        self.weight = weight
        self.c = c or [0.0, 0.0, 0.0]
        self.r0 = r0 or [0.0, 0.0, 0.0]
        self.r1 = r1 or [0.0, 0.0, 0.0]

class Vertex:
    """PMX頂点データ"""
    def __init__(self):
        self.co = [0.0, 0.0, 0.0]
        self.normal = [0.0, 1.0, 0.0]
        self.uv = [0.0, 0.0]
        self.additional_uvs = []
        self.weight = BoneWeight()
        self.edge_scale = 1.0

class Material:
    """PMX材質データ"""
    def __init__(self):
        self.name = ""
        self.name_e = ""
        self.diffuse = [0.8, 0.8, 0.8, 1.0] # R, G, B, A
        self.specular = [0.0, 0.0, 0.0, 5.0] # R, G, B, Power
        self.ambient = [0.4, 0.4, 0.4] # R, G, B
        self.draw_flags = 0x01 | 0x02 | 0x04 | 0x08 | 0x10
        self.is_double_sided = True
        self.edge_color = [0.0, 0.0, 0.0, 1.0]
        self.edge_size = 1.0
        self.texture = -1
        self.sphere_texture = -1
        self.sphere_texture_mode = 0 # 0:無効, 1:乗算, 2:加算, 3:サブテクスチャ
        self.is_shared_toon_texture = False
        self.toon_texture = -1
        self.comment = ""
        self.vertex_count = 0

class BoneLocalCoordinate:
    """ボーンローカル軸設定"""
    def __init__(self, x_axis=None, z_axis=None):
        self.x_axis = x_axis or [1.0, 0.0, 0.0]
        self.z_axis = z_axis or [0.0, 0.0, 1.0]

class Bone:
    """PMXボーンデータ"""
    def __init__(self):
        self.name = ""
        self.name_e = ""
        self.location = [0.0, 0.0, 0.0]
        self.parent = -1
        self.transform_level = 0
        self.flags = 0

        # フラグ解析プロパティ
        self.displayConnection = None # 接続先ボーンIndex
        self.isRotatable = True
        self.isMovable = True
        self.visible = True
        self.isControllable = True
        self.isIK = False
        self.hasAdditionalRotate = False
        self.hasAdditionalLocation = False
        self.additionalTransform = (0, 0.0) # (対象ボーン, 付与率)
        self.axis = None # 固定軸ベクトル [x, y, z]
        self.localCoordinate = None # BoneLocalCoordinate
        self.external_parent = None
        self.ik_target = None
        self.ik_loop = 0
        self.ik_limit_angle = 0.0
        self.ik_links = []

class VertexMorphOffset:
    """頂点モーフオフセット"""
    def __init__(self, index=0, offset=None):
        self.index = index
        self.offset = offset or [0.0, 0.0, 0.0]

class Morph:
    """PMXモーフデータ"""
    GROUP = 0
    VERTEX = 1
    BONE = 2
    UV = 3
    MATERIAL = 8

    def __init__(self):
        self.name = ""
        self.name_e = ""
        self.panel = 4 # 1:眉, 2:目, 3:口, 4:その他
        self.category = 4
        self.morph_type = 1
        self.offsets = []

    def type_index(self):
        return self.morph_type

class Display:
    """PMX表示枠データ"""
    def __init__(self):
        self.name = ""
        self.name_e = ""
        self.isSpecial = False
        self.data = [] # (type, index) のタプルリスト (0: ボーン, 1: モーフ)

class Texture:
    """PMXテクスチャデータ"""
    def __init__(self, path=""):
        self.path = path

class RigidBody:
    """PMX剛体データ"""
    def __init__(self):
        self.name = ""
        self.name_e = ""
        self.bone_index = -1
        self.group = 0
        self.collision_mask = 0xFFFF
        self.shape_type = 0 # 0: 球, 1: 箱, 2: カプセル
        self.size = [1.0, 1.0, 1.0]
        self.position = [0.0, 0.0, 0.0]
        self.rotation = [0.0, 0.0, 0.0]
        self.mass = 1.0
        self.linear_damping = 0.0
        self.angular_damping = 0.0
        self.restitution = 0.0
        self.friction = 0.5
        self.physics_mode = 0 # 0: ボーン追従(Kinematic), 1: 物理演算(Dynamic), 2: 物理演算+位置合わせ(Aligned)

class Joint:
    """PMXジョイントデータ"""
    def __init__(self):
        self.name = ""
        self.name_e = ""
        self.joint_type = 0 # 0: 6DOF スプリング
        self.rigid_body_a = -1
        self.rigid_body_b = -1
        self.position = [0.0, 0.0, 0.0]
        self.rotation = [0.0, 0.0, 0.0]
        self.linear_limit_min = [0.0, 0.0, 0.0]
        self.linear_limit_max = [0.0, 0.0, 0.0]
        self.angular_limit_min = [0.0, 0.0, 0.0]
        self.angular_limit_max = [0.0, 0.0, 0.0]
        self.linear_spring = [0.0, 0.0, 0.0]
        self.angular_spring = [0.0, 0.0, 0.0]

class Model:
    """PMXモデル全体データ構造"""
    def __init__(self):
        self.version = 2.0
        self.name = ""
        self.name_e = ""
        self.comment = ""
        self.comment_e = ""
        self.vertices = []
        self.faces = []
        self.textures = []
        self.materials = []
        self.bones = []
        self.morphs = []
        self.display = []
        self.rigid_bodies = []
        self.joints = []

# ==============================================================================
# バイナリ ストリーム リーダー & ライター
# ==============================================================================
class BinaryStreamReader:
    def __init__(self, f):
        self.f = f

    def read(self, n):
        b = self.f.read(n)
        if len(b) < n:
            # 途切れたPMXでもstruct.unpackがクラッシュしないようゼロパディング
            b = b + b'\x00' * (n - len(b))
        return b

    def read_byte(self):
        return struct.unpack('<b', self.read(1))[0]

    def read_ubyte(self):
        return struct.unpack('<B', self.read(1))[0]

    def read_short(self):
        return struct.unpack('<h', self.read(2))[0]

    def read_ushort(self):
        return struct.unpack('<H', self.read(2))[0]

    def read_int(self):
        return struct.unpack('<i', self.read(4))[0]

    def read_uint(self):
        return struct.unpack('<I', self.read(4))[0]

    def read_float(self):
        val = struct.unpack('<f', self.read(4))[0]
        if math.isnan(val) or math.isinf(val):
            return 0.0
        return val

    def read_floats(self, count):
        raw = list(struct.unpack(f'<{count}f', self.read(4 * count)))
        return [0.0 if (math.isnan(v) or math.isinf(v)) else v for v in raw]

    def read_text(self, encoding_flag):
        length = self.read_int()
        if length <= 0:
            return ""
        # 異常に巨大な文字列長（ファイル破損や不正データ）の防護
        if length > 1048576:
            return ""
        raw_bytes = self.read(length)
        preferred = 'utf-8' if encoding_flag == 1 else 'utf-16le'
        encodings = [preferred, 'utf-16le', 'utf-8', 'cp932', 'shift_jis', 'gbk', 'euc-jp']
        for enc in encodings:
            try:
                text = raw_bytes.decode(enc)
                return text.split('\x00')[0]
            except Exception:
                continue
        return raw_bytes.decode('utf-8', errors='replace').split('\x00')[0]

    def read_index(self, size, signed=False):
        if size == 1:
            return self.read_byte() if signed else self.read_ubyte()
        elif size == 2:
            return self.read_short() if signed else self.read_ushort()
        elif size == 4:
            return self.read_int() if signed else self.read_uint()
        # 不正なサイズの場合は 0 を返してクラッシュ防止
        return 0

class BinaryStreamWriter:
    def __init__(self, f):
        self.f = f

    def write(self, b):
        self.f.write(b)

    def write_byte(self, v):
        self.f.write(struct.pack('<b', v))

    def write_ubyte(self, v):
        self.f.write(struct.pack('<B', v))

    def write_short(self, v):
        self.f.write(struct.pack('<h', v))

    def write_ushort(self, v):
        self.f.write(struct.pack('<H', v))

    def write_int(self, v):
        self.f.write(struct.pack('<i', v))

    def write_uint(self, v):
        self.f.write(struct.pack('<I', v))

    def write_float(self, v):
        self.f.write(struct.pack('<f', v))

    def write_floats(self, vals):
        self.f.write(struct.pack(f'<{len(vals)}f', *vals))

    def write_text(self, s, encoding_flag):
        if not s:
            self.write_int(0)
            return
        enc = 'utf-8' if encoding_flag == 1 else 'utf-16le'
        encoded = s.encode(enc, errors='replace')
        self.write_int(len(encoded))
        self.f.write(encoded)

    def write_index(self, v, size, signed=False):
        if size == 1:
            self.write_byte(v) if signed else self.write_ubyte(v)
        elif size == 2:
            self.write_short(v) if signed else self.write_ushort(v)
        elif size == 4:
            self.write_int(v) if signed else self.write_uint(v)

# ==============================================================================
# ロード処理 (PMX バイナリ読み込み)
# ==============================================================================
def load(file_path):
    """PMXファイルをバイナリ解析し、Modelオブジェクトを構築して返します。"""
    with open(file_path, 'rb') as f:
        reader = BinaryStreamReader(f)

        # 1. ヘッダーシグネチャ検証
        sig = reader.read(4)
        if sig != b'PMX ':
            raise PMXFormatError("PMXシグネチャが見つかりません (非対応ファイル形式)")

        model = Model()
        model.version = reader.read_float()

        # グローバルフラグテーブル (8バイト)
        flag_count = reader.read_ubyte()
        if flag_count < 8:
            raise PMXFormatError("無効なPMXグローバル情報テーブルです")
        flags = [reader.read_ubyte() for _ in range(flag_count)]

        encoding_flag = flags[0]       # 0: UTF-16LE, 1: UTF-8
        additional_uv_count = flags[1] # 0〜4
        vtx_idx_size = flags[2]        # 1, 2, 4
        tex_idx_size = flags[3]
        mat_idx_size = flags[4]
        bone_idx_size = flags[5]
        morph_idx_size = flags[6]
        rigid_idx_size = flags[7]

        # 2. モデル情報
        model.name = reader.read_text(encoding_flag)
        model.name_e = reader.read_text(encoding_flag)
        model.comment = reader.read_text(encoding_flag)
        model.comment_e = reader.read_text(encoding_flag)

        # 頂点データ
        vtx_count = reader.read_int()
        for _ in range(vtx_count):
            vtx = Vertex()
            vtx.co = reader.read_floats(3)
            vtx.normal = reader.read_floats(3)
            vtx.uv = reader.read_floats(2)

            for _ in range(additional_uv_count):
                vtx.additional_uvs.append(reader.read_floats(4))

            weight_type = reader.read_ubyte()
            bw = BoneWeight(weight_type)

            if weight_type == BoneWeight.BDEF1:
                bw.bones[0] = reader.read_index(bone_idx_size, signed=False)
                bw.weights[0] = 1.0
            elif weight_type == BoneWeight.BDEF2:
                bw.bones[0] = reader.read_index(bone_idx_size, signed=False)
                bw.bones[1] = reader.read_index(bone_idx_size, signed=False)
                w0 = reader.read_float()
                # 異常値・NaN・範囲外の保護
                if math.isnan(w0) or math.isinf(w0):
                    w0 = 1.0
                w0 = max(0.0, min(1.0, w0))
                bw.weights[0] = w0
                bw.weights[1] = 1.0 - w0
            elif weight_type == BoneWeight.BDEF4 or weight_type == BoneWeight.QDEF:
                for i in range(4):
                    bw.bones[i] = reader.read_index(bone_idx_size, signed=False)
                raw_w = reader.read_floats(4)
                cleaned_w = [max(0.0, float(v)) for v in raw_w]
                sum_w = sum(cleaned_w)
                if sum_w > 1e-6:
                    bw.weights = [v / sum_w for v in cleaned_w]
                else:
                    bw.weights = [1.0, 0.0, 0.0, 0.0]
            elif weight_type == BoneWeight.SDEF:
                bw.bones[0] = reader.read_index(bone_idx_size, signed=False)
                bw.bones[1] = reader.read_index(bone_idx_size, signed=False)
                w0 = reader.read_float()
                if math.isnan(w0) or math.isinf(w0):
                    w0 = 0.5
                w0 = max(0.0, min(1.0, w0))
                c = reader.read_floats(3)
                r0 = reader.read_floats(3)
                r1 = reader.read_floats(3)
                bw.weights = SdefWeights(w0, c, r0, r1)
            else:
                # 未知のウェイトタイプへの安全フォールバック
                bw.weights[0] = 1.0

            vtx.weight = bw
            vtx.edge_scale = reader.read_float()
            model.vertices.append(vtx)

        # 面データ (3頂点インデックスごとに1面)
        face_vert_count = reader.read_int()
        num_triangles = face_vert_count // 3
        for _ in range(num_triangles):
            i0 = reader.read_index(vtx_idx_size, signed=False)
            i1 = reader.read_index(vtx_idx_size, signed=False)
            i2 = reader.read_index(vtx_idx_size, signed=False)
            # 頂点インデックスの範囲外アクセス防護
            if vtx_count > 0:
                i0 = min(max(0, i0), vtx_count - 1)
                i1 = min(max(0, i1), vtx_count - 1)
                i2 = min(max(0, i2), vtx_count - 1)
            model.faces.append([i0, i1, i2])

        # テクスチャテーブル
        tex_count = reader.read_int()
        for _ in range(tex_count):
            t_path = reader.read_text(encoding_flag)
            model.textures.append(Texture(t_path))

        # 材質データ
        mat_count = reader.read_int()
        for _ in range(mat_count):
            mat = Material()
            mat.name = reader.read_text(encoding_flag)
            mat.name_e = reader.read_text(encoding_flag)
            mat.diffuse = reader.read_floats(4)
            mat.specular = reader.read_floats(4)
            mat.ambient = reader.read_floats(3)
            mat.draw_flags = reader.read_ubyte()
            mat.is_double_sided = bool(mat.draw_flags & 0x01)
            mat.edge_color = reader.read_floats(4)
            mat.edge_size = reader.read_float()
            mat.texture = reader.read_index(tex_idx_size, signed=True)
            if mat.texture >= tex_count:
                mat.texture = -1
            mat.sphere_texture = reader.read_index(tex_idx_size, signed=True)
            if mat.sphere_texture >= tex_count:
                mat.sphere_texture = -1
            mat.sphere_texture_mode = reader.read_ubyte()
            mat.is_shared_toon_texture = (reader.read_ubyte() == 1)
            if mat.is_shared_toon_texture:
                mat.toon_texture = reader.read_ubyte()
            else:
                mat.toon_texture = reader.read_index(tex_idx_size, signed=True)
                if mat.toon_texture >= tex_count:
                    mat.toon_texture = -1
            mat.comment = reader.read_text(encoding_flag)
            mat.vertex_count = max(0, reader.read_int())
            model.materials.append(mat)

        # ボーンデータ
        bone_count = reader.read_int()
        for b_idx in range(bone_count):
            b = Bone()
            b.name = reader.read_text(encoding_flag)
            b.name_e = reader.read_text(encoding_flag)
            b.location = reader.read_floats(3)
            b.parent = reader.read_index(bone_idx_size, signed=True)
            if b.parent >= bone_count or b.parent == b_idx:
                b.parent = -1
            b.transform_level = reader.read_int()
            flags = reader.read_ushort()
            b.flags = flags

            b.displayConnection = reader.read_index(bone_idx_size, signed=True) if (flags & 0x0001) else reader.read_floats(3)
            b.isRotatable = bool(flags & 0x0002)
            b.isMovable = bool(flags & 0x0004)
            b.visible = bool(flags & 0x0008)
            b.isControllable = bool(flags & 0x0010)
            b.isIK = bool(flags & 0x0020)

            if flags & 0x0100 or flags & 0x0200:
                parent_idx = reader.read_index(bone_idx_size, signed=True)
                ratio = reader.read_float()
                if parent_idx < 0 or parent_idx >= bone_count:
                    parent_idx = -1
                    ratio = 0.0
                b.additionalTransform = (parent_idx, ratio)
                b.hasAdditionalRotate = bool(flags & 0x0100) and (parent_idx >= 0)
                b.hasAdditionalLocation = bool(flags & 0x0200) and (parent_idx >= 0)

            if flags & 0x0400: # 固定軸
                b.axis = reader.read_floats(3)

            if flags & 0x0800: # ローカル軸
                x_axis = reader.read_floats(3)
                z_axis = reader.read_floats(3)
                b.localCoordinate = BoneLocalCoordinate(x_axis, z_axis)

            if flags & 0x2000: # 外部親
                b.external_parent = reader.read_int()

            if b.isIK:
                b.ik_target = reader.read_index(bone_idx_size, signed=True)
                if b.ik_target is not None and (b.ik_target < 0 or b.ik_target >= bone_count):
                    b.ik_target = None
                b.ik_loop = reader.read_int()
                b.ik_limit_angle = reader.read_float()
                link_count = reader.read_int()
                for _ in range(link_count):
                    link_idx = reader.read_index(bone_idx_size, signed=True)
                    has_limits = (reader.read_ubyte() == 1)
                    lim_min = reader.read_floats(3) if has_limits else None
                    lim_max = reader.read_floats(3) if has_limits else None

                    # 無効なボーンインデックスのリンクを除外
                    if 0 <= link_idx < bone_count:
                        if has_limits and lim_min and lim_max:
                            safe_min = [min(lim_min[k], lim_max[k]) for k in range(3)]
                            safe_max = [max(lim_min[k], lim_max[k]) for k in range(3)]
                            b.ik_links.append((link_idx, safe_min, safe_max))
                        else:
                            b.ik_links.append((link_idx, lim_min, lim_max))

            model.bones.append(b)

        # モーフデータ
        morph_count = reader.read_int()
        for _ in range(morph_count):
            m = Morph()
            m.name = reader.read_text(encoding_flag)
            m.name_e = reader.read_text(encoding_flag)
            m.panel = reader.read_ubyte()
            m.category = m.panel
            m.morph_type = reader.read_ubyte()
            offset_count = reader.read_int()

            if m.morph_type == Morph.VERTEX:
                for _ in range(offset_count):
                    v_idx = reader.read_index(vtx_idx_size, signed=False)
                    v_off = reader.read_floats(3)
                    # 範囲外頂点インデックスのスキップ
                    if 0 <= v_idx < vtx_count:
                        m.offsets.append(VertexMorphOffset(v_idx, v_off))
            elif m.morph_type == Morph.GROUP:
                for _ in range(offset_count):
                    g_idx = reader.read_index(morph_idx_size, signed=True)
                    g_rate = reader.read_float()
                    if 0 <= g_idx < morph_count:
                        m.offsets.append((g_idx, g_rate))
            elif m.morph_type == Morph.BONE:
                for _ in range(offset_count):
                    b_idx = reader.read_index(bone_idx_size, signed=True)
                    trans = reader.read_floats(3)
                    rot = reader.read_floats(4)
                    if 0 <= b_idx < bone_count:
                        m.offsets.append((b_idx, trans, rot))
            elif m.morph_type in [Morph.UV, 4, 5, 6, 7]: # UV または 追加UV
                for _ in range(offset_count):
                    v_idx = reader.read_index(vtx_idx_size, signed=False)
                    uv_off = reader.read_floats(4)
                    if 0 <= v_idx < vtx_count:
                        m.offsets.append((v_idx, uv_off))
            elif m.morph_type == Morph.MATERIAL:
                for _ in range(offset_count):
                    mat_idx = reader.read_index(mat_idx_size, signed=True)
                    calc_op = reader.read_ubyte()
                    diff = reader.read_floats(4)
                    spec = reader.read_floats(4)
                    amb = reader.read_floats(3)
                    edge = reader.read_floats(4)
                    edge_sz = reader.read_float()
                    tex_tint = reader.read_floats(4)
                    sphere_tint = reader.read_floats(4)
                    toon_tint = reader.read_floats(4)
                    if -1 <= mat_idx < mat_count:
                        m.offsets.append((mat_idx, calc_op, diff, spec, amb, edge, edge_sz, tex_tint, sphere_tint, toon_tint))

            model.morphs.append(m)

        # 表示枠データ
        disp_count = reader.read_int()
        for _ in range(disp_count):
            d = Display()
            d.name = reader.read_text(encoding_flag)
            d.name_e = reader.read_text(encoding_flag)
            d.isSpecial = (reader.read_ubyte() == 1)
            elem_count = reader.read_int()
            for _ in range(elem_count):
                elem_type = reader.read_ubyte()
                if elem_type == 0:
                    elem_idx = reader.read_index(bone_idx_size, signed=True)
                else:
                    elem_idx = reader.read_index(morph_idx_size, signed=True)
                d.data.append((elem_type, elem_idx))
            model.display.append(d)

        # 剛体データ読み込み (末尾破損でも読めた要素まで安全に保持)
        try:
            rigid_count = reader.read_int()
            for _ in range(rigid_count):
                rb = RigidBody()
                rb.name = reader.read_text(encoding_flag)
                rb.name_e = reader.read_text(encoding_flag)
                rb.bone_index = reader.read_index(bone_idx_size, signed=True)
                if rb.bone_index >= bone_count:
                    rb.bone_index = -1
                rb.group = reader.read_ubyte()
                rb.collision_mask = reader.read_ushort()
                rb.shape_type = reader.read_ubyte()
                rb.size = reader.read_floats(3)
                rb.position = reader.read_floats(3)
                rb.rotation = reader.read_floats(3)
                rb.mass = reader.read_float()
                rb.linear_damping = reader.read_float()
                rb.angular_damping = reader.read_float()
                rb.restitution = reader.read_float()
                rb.friction = reader.read_float()
                rb.physics_mode = reader.read_ubyte()
                model.rigid_bodies.append(rb)
        except Exception:
            pass

        # ジョイントデータ読み込み (末尾破損でも読めた要素まで安全に保持)
        try:
            joint_count = reader.read_int()
            for _ in range(joint_count):
                j = Joint()
                j.name = reader.read_text(encoding_flag)
                j.name_e = reader.read_text(encoding_flag)
                j.joint_type = reader.read_ubyte()
                j.rigid_body_a = reader.read_index(rigid_idx_size, signed=True)
                j.rigid_body_b = reader.read_index(rigid_idx_size, signed=True)
                if hasattr(model, 'rigid_bodies'):
                    rb_len = len(model.rigid_bodies)
                    if j.rigid_body_a >= rb_len:
                        j.rigid_body_a = -1
                    if j.rigid_body_b >= rb_len:
                        j.rigid_body_b = -1
                j.position = reader.read_floats(3)
                j.rotation = reader.read_floats(3)
                j.linear_limit_min = reader.read_floats(3)
                j.linear_limit_max = reader.read_floats(3)
                j.angular_limit_min = reader.read_floats(3)
                j.angular_limit_max = reader.read_floats(3)
                j.linear_spring = reader.read_floats(3)
                j.angular_spring = reader.read_floats(3)
                model.joints.append(j)
        except Exception:
            pass

    return model

# ==============================================================================
# セーブ処理 (PMX バイナリ書き込み)
# ==============================================================================
def save(file_path, model):
    """ModelオブジェクトのデータをPMXファイルとして書き出します。"""
    with open(file_path, 'wb') as f:
        writer = BinaryStreamWriter(f)

        # 1. ヘッダー
        writer.write(b'PMX ')
        writer.write_float(2.0) # バージョン 2.0

        # インデックスサイズの決定
        num_vtx = len(model.vertices)
        num_tex = len(model.textures)
        num_mat = len(model.materials)
        num_bone = len(model.bones)
        num_morph = len(model.morphs)
        num_rigid = len(model.rigid_bodies)

        vtx_idx_size = 4 if num_vtx > 65535 else (2 if num_vtx > 255 else 1)
        tex_idx_size = 4 if num_tex > 32767 else (2 if num_tex > 127 else 1)
        mat_idx_size = 4 if num_mat > 32767 else (2 if num_mat > 127 else 1)
        bone_idx_size = 4 if num_bone > 32767 else (2 if num_bone > 127 else 1)
        morph_idx_size = 4 if num_morph > 32767 else (2 if num_morph > 127 else 1)
        rigid_idx_size = 4 if num_rigid > 32767 else (2 if num_rigid > 127 else 1)

        encoding_flag = 0 # 0: UTF-16LE, 1: UTF-8 (UTF-16LEが標準的)

        writer.write_ubyte(8) # フラグ数
        writer.write_ubyte(encoding_flag)
        writer.write_ubyte(0) # 追加UV数 0
        writer.write_ubyte(vtx_idx_size)
        writer.write_ubyte(tex_idx_size)
        writer.write_ubyte(mat_idx_size)
        writer.write_ubyte(bone_idx_size)
        writer.write_ubyte(morph_idx_size)
        writer.write_ubyte(rigid_idx_size)

        # 2. モデル情報
        writer.write_text(model.name, encoding_flag)
        writer.write_text(model.name_e, encoding_flag)
        writer.write_text(model.comment, encoding_flag)
        writer.write_text(model.comment_e, encoding_flag)

        # 3. 頂点データ
        writer.write_int(num_vtx)
        for vtx in model.vertices:
            writer.write_floats(vtx.co)
            writer.write_floats(vtx.normal)
            writer.write_floats(vtx.uv)

            bw = vtx.weight
            writer.write_ubyte(bw.type)
            if bw.type == BoneWeight.BDEF1:
                writer.write_index(bw.bones[0], bone_idx_size, signed=False)
            elif bw.type == BoneWeight.BDEF2:
                writer.write_index(bw.bones[0], bone_idx_size, signed=False)
                writer.write_index(bw.bones[1], bone_idx_size, signed=False)
                writer.write_float(bw.weights[0])
            elif bw.type == BoneWeight.BDEF4 or bw.type == BoneWeight.QDEF:
                for b_i in range(4):
                    writer.write_index(bw.bones[b_i], bone_idx_size, signed=False)
                writer.write_floats(bw.weights[:4])
            elif bw.type == BoneWeight.SDEF:
                writer.write_index(bw.bones[0], bone_idx_size, signed=False)
                writer.write_index(bw.bones[1], bone_idx_size, signed=False)
                if isinstance(bw.weights, SdefWeights):
                    writer.write_float(bw.weights.weight)
                    writer.write_floats(bw.weights.c)
                    writer.write_floats(bw.weights.r0)
                    writer.write_floats(bw.weights.r1)
                else:
                    writer.write_float(0.5)
                    writer.write_floats([0, 0, 0, 0, 0, 0, 0, 0, 0])

            writer.write_float(vtx.edge_scale)

        # 4. 面データ
        num_faces = len(model.faces)
        writer.write_int(num_faces * 3)
        for f_tri in model.faces:
            writer.write_index(f_tri[0], vtx_idx_size, signed=False)
            writer.write_index(f_tri[1], vtx_idx_size, signed=False)
            writer.write_index(f_tri[2], vtx_idx_size, signed=False)

        # 5. テクスチャ
        writer.write_int(num_tex)
        for tex in model.textures:
            writer.write_text(tex.path, encoding_flag)

        # 6. 材質
        writer.write_int(num_mat)
        for mat in model.materials:
            writer.write_text(mat.name, encoding_flag)
            writer.write_text(mat.name_e, encoding_flag)
            writer.write_floats(mat.diffuse)
            writer.write_floats(mat.specular)
            writer.write_floats(mat.ambient)
            writer.write_ubyte(mat.draw_flags)
            writer.write_floats(mat.edge_color)
            writer.write_float(mat.edge_size)
            writer.write_index(mat.texture, tex_idx_size, signed=True)
            writer.write_index(mat.sphere_texture, tex_idx_size, signed=True)
            writer.write_ubyte(mat.sphere_texture_mode)
            writer.write_ubyte(1 if mat.is_shared_toon_texture else 0)
            if mat.is_shared_toon_texture:
                writer.write_ubyte(mat.toon_texture if mat.toon_texture >= 0 else 0)
            else:
                writer.write_index(mat.toon_texture, tex_idx_size, signed=True)
            writer.write_text(mat.comment, encoding_flag)
            writer.write_int(mat.vertex_count)

        # ボーン
        writer.write_int(num_bone)
        for b in model.bones:
            writer.write_text(b.name, encoding_flag)
            writer.write_text(b.name_e, encoding_flag)
            writer.write_floats(b.location)
            writer.write_index(b.parent, bone_idx_size, signed=True)
            writer.write_int(b.transform_level)
            
            # フラグ計算
            if hasattr(b, 'flags') and b.flags != 0:
                flags = b.flags
            else:
                flags = 0
                if b.displayConnection is not None and isinstance(b.displayConnection, int):
                    flags |= 0x0001
                if getattr(b, 'isRotatable', True):
                    flags |= 0x0002
                if getattr(b, 'isMovable', True):
                    flags |= 0x0004
                if getattr(b, 'visible', True):
                    flags |= 0x0008
                if getattr(b, 'isControllable', True):
                    flags |= 0x0010
                if getattr(b, 'isIK', False):
                    flags |= 0x0020
                if getattr(b, 'hasAdditionalRotate', False):
                    flags |= 0x0100
                if getattr(b, 'hasAdditionalLocation', False):
                    flags |= 0x0200
                if getattr(b, 'axis', None) is not None:
                    flags |= 0x0400
                if getattr(b, 'localCoordinate', None) is not None:
                    flags |= 0x0800
                if getattr(b, 'external_parent', None) is not None:
                    flags |= 0x2000

            writer.write_ushort(flags)

            # 接続先
            if flags & 0x0001:
                conn_idx = b.displayConnection if isinstance(b.displayConnection, int) else 0
                writer.write_index(conn_idx, bone_idx_size, signed=True)
            else:
                conn_pos = b.displayConnection if (b.displayConnection and isinstance(b.displayConnection, (list, tuple))) else [0.0, 0.0, 0.0]
                writer.write_floats(conn_pos)

            # 付与親
            if flags & (0x0100 | 0x0200):
                add_p, add_r = getattr(b, 'additionalTransform', (-1, 0.0))
                writer.write_index(add_p, bone_idx_size, signed=True)
                writer.write_float(add_r)

            # 軸固定
            if flags & 0x0400:
                ax = getattr(b, 'axis', [0.0, 1.0, 0.0]) or [0.0, 1.0, 0.0]
                writer.write_floats(ax)

            # ローカル軸
            if flags & 0x0800:
                loc_coord = getattr(b, 'localCoordinate', None)
                if loc_coord and hasattr(loc_coord, 'x_axis') and hasattr(loc_coord, 'z_axis'):
                    writer.write_floats(loc_coord.x_axis)
                    writer.write_floats(loc_coord.z_axis)
                else:
                    writer.write_floats([1.0, 0.0, 0.0])
                    writer.write_floats([0.0, 0.0, 1.0])

            # 外部親
            if flags & 0x2000:
                ext_p = getattr(b, 'external_parent', 0) or 0
                writer.write_int(ext_p)

            # IKデータ
            if flags & 0x0020:
                ik_target = getattr(b, 'ik_target', -1)
                ik_loop = getattr(b, 'ik_loop', 40)
                ik_limit_angle = getattr(b, 'ik_limit_angle', 3.14159265)
                ik_links = getattr(b, 'ik_links', []) or []

                writer.write_index(ik_target if ik_target is not None else -1, bone_idx_size, signed=True)
                writer.write_int(ik_loop)
                writer.write_float(ik_limit_angle)
                writer.write_int(len(ik_links))

                for link in ik_links:
                    link_idx = link[0]
                    lim_min = link[1] if len(link) > 1 else None
                    lim_max = link[2] if len(link) > 2 else None
                    has_limits = 1 if (lim_min is not None and lim_max is not None) else 0

                    writer.write_index(link_idx, bone_idx_size, signed=True)
                    writer.write_ubyte(has_limits)
                    if has_limits:
                        writer.write_floats(lim_min)
                        writer.write_floats(lim_max)

        # 8. モーフ
        writer.write_int(num_morph)
        for m in model.morphs:
            writer.write_text(m.name, encoding_flag)
            writer.write_text(m.name_e, encoding_flag)
            writer.write_ubyte(m.panel)
            writer.write_ubyte(m.morph_type)
            writer.write_int(len(m.offsets))
            if m.morph_type == Morph.VERTEX:
                for off in m.offsets:
                    writer.write_index(off.index, vtx_idx_size, signed=False)
                    writer.write_floats(off.offset)
            else:
                pass # その他のモーフは簡易出力

        # 9. 表示枠
        writer.write_int(len(model.display))
        for d in model.display:
            writer.write_text(d.name, encoding_flag)
            writer.write_text(d.name_e, encoding_flag)
            writer.write_ubyte(1 if d.isSpecial else 0)
            writer.write_int(len(d.data))
            for elem_type, elem_idx in d.data:
                writer.write_ubyte(elem_type)
                if elem_type == 0:
                    writer.write_index(elem_idx, bone_idx_size, signed=True)
                else:
                    writer.write_index(elem_idx, morph_idx_size, signed=True)

        # 10. 剛体
        writer.write_int(num_rigid)
        for rb in model.rigid_bodies:
            writer.write_text(rb.name, encoding_flag)
            writer.write_text(rb.name_e, encoding_flag)
            writer.write_index(rb.bone_index, bone_idx_size, signed=True)
            writer.write_ubyte(rb.group)
            writer.write_ushort(rb.collision_mask)
            writer.write_ubyte(rb.shape_type)
            writer.write_floats(rb.size)
            writer.write_floats(rb.position)
            writer.write_floats(rb.rotation)
            writer.write_float(rb.mass)
            writer.write_float(rb.linear_damping)
            writer.write_float(rb.angular_damping)
            writer.write_float(rb.restitution)
            writer.write_float(rb.friction)
            writer.write_ubyte(rb.physics_mode)

        # 11. ジョイント
        writer.write_int(len(model.joints))
        for j in model.joints:
            writer.write_text(j.name, encoding_flag)
            writer.write_text(j.name_e, encoding_flag)
            writer.write_ubyte(j.joint_type)
            writer.write_index(j.rigid_body_a, rigid_idx_size, signed=True)
            writer.write_index(j.rigid_body_b, rigid_idx_size, signed=True)
            writer.write_floats(j.position)
            writer.write_floats(j.rotation)
            writer.write_floats(j.linear_limit_min)
            writer.write_floats(j.linear_limit_max)
            writer.write_floats(j.angular_limit_min)
            writer.write_floats(j.angular_limit_max)
            writer.write_floats(j.linear_spring)
            writer.write_floats(j.angular_spring)
