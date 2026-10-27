# -*- coding: utf-8 -*-
"""
mmd_core.pmd - PMD (Polygon Model Data) バイナリパーサー

旧規格である MMD PMD モデルファイルをバイナリ解析し、
PMX 互換の Model オブジェクトに変換して読み込みます。
IK（インバースキネマティクス）やモーフ（表情）を含む高精度な独自実装です。
"""

import struct
import os
import math
from . import pmx

def _decode_cjk(raw_bytes):
    """Shift-JIS / CP932 または GBK (中国語) でデコードします。"""
    clean_bytes = raw_bytes.split(b'\x00')[0]
    for enc in ['shift_jis', 'cp932', 'gbk', 'utf-8']:
        try:
            return clean_bytes.decode(enc)
        except Exception:
            continue
    return clean_bytes.decode('utf-8', errors='ignore')

def load2pmx(file_path):
    """
    PMDファイルをバイナリ解析し、PMX互換の Model オブジェクトとして返します。
    """
    model_name = os.path.splitext(os.path.basename(file_path))[0]
    model = pmx.Model()
    model.name = model_name
    model.name_e = model_name

    with open(file_path, 'rb') as f:
        # ヘッダー (Signature: 'Pmd', Version: 1.0)
        sig = f.read(3)
        if sig != b'Pmd':
            raise pmx.PMXFormatError("無効なPMDファイルです (シグネチャ不一致)")

        model.version = struct.unpack('<f', f.read(4))[0]
        read_name = _decode_cjk(f.read(20))
        if read_name:
            model.name = read_name
            model.name_e = read_name
        model.comment = _decode_cjk(f.read(256))

        # 頂点データ
        vtx_buf = f.read(4)
        if len(vtx_buf) < 4:
            return model
        vtx_count = struct.unpack('<I', vtx_buf)[0]

        for _ in range(vtx_count):
            co = list(struct.unpack('<3f', f.read(12)))
            normal = list(struct.unpack('<3f', f.read(12)))
            uv = list(struct.unpack('<2f', f.read(8)))
            b0, b1, w_byte, edge_flag = struct.unpack('<2H2B', f.read(6))

            vtx = pmx.Vertex()
            vtx.co = co
            vtx.normal = normal
            vtx.uv = uv

            bw = pmx.BoneWeight(pmx.BoneWeight.BDEF2 if b0 != b1 and 0 < w_byte < 100 else pmx.BoneWeight.BDEF1)
            bw.bones[0] = b0
            bw.bones[1] = b1
            w0 = w_byte / 100.0
            bw.weights[0] = w0
            bw.weights[1] = 1.0 - w0
            vtx.weight = bw
            vtx.edge_scale = 0.0 if edge_flag else 1.0
            model.vertices.append(vtx)

        # 面データ
        face_buf = f.read(4)
        if len(face_buf) < 4:
            return model
        face_vert_count = struct.unpack('<I', face_buf)[0]
        face_indices = struct.unpack(f'<{face_vert_count}H', f.read(face_vert_count * 2))

        # MMD/OpenGL座標系への面インデックス反転（巻き順調整）
        for i in range(0, face_vert_count, 3):
            model.faces.append([face_indices[i + 2], face_indices[i + 1], face_indices[i]])

        # 材質データ
        mat_buf = f.read(4)
        if len(mat_buf) < 4:
            return model
        mat_count = struct.unpack('<I', mat_buf)[0]
        tex_path_map = {}

        for mat_idx in range(mat_count):
            diff = list(struct.unpack('<4f', f.read(16)))
            # PMDモデル特有のアルファ値異常値 (例: 99.0 や 100.0) を0.0〜1.0へ正規化
            if diff[3] > 1.0:
                diff[3] = min(1.0, max(0.0, diff[3] / 100.0))
            spec_pow = struct.unpack('<f', f.read(4))[0]
            spec = list(struct.unpack('<3f', f.read(12))) + [spec_pow]
            amb = list(struct.unpack('<3f', f.read(12)))
            toon_idx, edge_flag, face_cnt = struct.unpack('<2BI', f.read(6))
            tex_file_raw = f.read(20)
            tex_file_str = _decode_cjk(tex_file_raw)

            mat = pmx.Material()
            mat.name = f"Material_{mat_idx + 1}"
            mat.diffuse = diff
            mat.specular = spec
            mat.ambient = amb
            mat.vertex_count = face_cnt
            mat.texture = -1

            # Toonテクスチャの設定 (0〜9: 共有トゥーン toon01〜toon10)
            if toon_idx != 255 and 0 <= toon_idx < 10:
                mat.is_shared_toon_texture = True
                mat.toon_texture = toon_idx
            else:
                mat.is_shared_toon_texture = False
                mat.toon_texture = -1

            # スフィアマップとテクスチャの分離 (例: "tex.png*sphere.spa")
            tex_parts = tex_file_str.split('*')
            main_tex = tex_parts[0].strip() if len(tex_parts) > 0 else ""
            if main_tex:
                clean_tex = main_tex.replace('\\\\', '/').replace('\\', '/')
                if clean_tex not in tex_path_map:
                    tex_path_map[clean_tex] = len(model.textures)
                    model.textures.append(pmx.Texture(clean_tex))
                mat.texture = tex_path_map[clean_tex]

            if len(tex_parts) > 1:
                sphere_tex = tex_parts[1].strip()
                if sphere_tex:
                    clean_sph = sphere_tex.replace('\\\\', '/').replace('\\', '/')
                    if clean_sph not in tex_path_map:
                        tex_path_map[clean_sph] = len(model.textures)
                        model.textures.append(pmx.Texture(clean_sph))
                    mat.sphere_texture = tex_path_map[clean_sph]
                    if clean_sph.lower().endswith('.spa'):
                        mat.sphere_texture_mode = 2
                    elif clean_sph.lower().endswith('.sph'):
                        mat.sphere_texture_mode = 1
                    else:
                        mat.sphere_texture_mode = 1

            model.materials.append(mat)

        # ボーンデータ
        bone_buf = f.read(2)
        if len(bone_buf) < 2:
            return model
        bone_count = struct.unpack('<H', bone_buf)[0]

        for _ in range(bone_count):
            b_name = _decode_cjk(f.read(20))
            parent_idx, tail_idx, b_type, ik_idx = struct.unpack('<2HBH', f.read(7))
            b_pos = list(struct.unpack('<3f', f.read(12)))

            bone = pmx.Bone()
            bone.name = b_name
            bone.name_e = b_name
            bone.location = b_pos
            bone.parent = parent_idx if parent_idx != 65535 else -1
            bone.isIK = (b_type == 2 or b_type == 9)
            model.bones.append(bone)

        # IK データ（PMD仕様: ボーンの直後に配置）
        ik_buf = f.read(2)
        if len(ik_buf) < 2:
            return model
        ik_count = struct.unpack('<H', ik_buf)[0]

        for _ in range(ik_count):
            b_idx, target_idx = struct.unpack('<2H', f.read(4))
            ik_chain = struct.unpack('<B', f.read(1))[0]
            iterations = struct.unpack('<H', f.read(2))[0]
            control_weight = struct.unpack('<f', f.read(4))[0]

            child_bones = []
            for _ in range(ik_chain):
                c_idx = struct.unpack('<H', f.read(2))[0]
                child_bones.append(c_idx)

            if b_idx < len(model.bones):
                bone = model.bones[b_idx]
                bone.isIK = True
                bone.ik_target = target_idx
                bone.ik_loop = iterations
                bone.ik_limit_angle = control_weight * 4.0
                for c_idx in child_bones:
                    lim_min = None
                    lim_max = None
                    # ひざボーンの可動域制限を設定
                    if c_idx < len(model.bones) and "ひざ" in model.bones[c_idx].name:
                        lim_min = [math.radians(0.5), 0.0, 0.0]
                        lim_max = [math.radians(180.0), 0.0, 0.0]
                    bone.ik_links.append((c_idx, lim_min, lim_max))

        # モーフ（表情）データ
        morph_buf = f.read(2)
        if len(morph_buf) < 2:
            return model
        morph_count = struct.unpack('<H', morph_buf)[0]

        base_morph_indices = []
        for _ in range(morph_count):
            m_name = _decode_cjk(f.read(20))
            m_vert_cnt, m_type = struct.unpack('<IB', f.read(5))

            morph = pmx.Morph()
            morph.name = m_name
            morph.name_e = m_name
            morph.panel = m_type
            morph.category = m_type
            morph.morph_type = pmx.Morph.VERTEX

            if m_type == 0:
                # base モーフ (base頂点インデックスのキャッシュ)
                for _ in range(m_vert_cnt):
                    v_idx = struct.unpack('<I', f.read(4))[0]
                    _v_pos = struct.unpack('<3f', f.read(12))
                    base_morph_indices.append(v_idx)
            else:
                for _ in range(m_vert_cnt):
                    b_idx = struct.unpack('<I', f.read(4))[0]
                    v_off = list(struct.unpack('<3f', f.read(12)))
                    real_idx = base_morph_indices[b_idx] if b_idx < len(base_morph_indices) else b_idx
                    morph.offsets.append(pmx.VertexMorphOffset(real_idx, v_off))
                model.morphs.append(morph)

        # 表情枠データのスキップ
        face_frame_buf = f.read(1)
        if len(face_frame_buf) == 1:
            face_frame_count = struct.unpack('<B', face_frame_buf)[0]
            f.read(face_frame_count * 2)

        # ボーン枠名リストのスキップ
        bone_frame_name_buf = f.read(1)
        bone_frame_name_count = 0
        if len(bone_frame_name_buf) == 1:
            bone_frame_name_count = struct.unpack('<B', bone_frame_name_buf)[0]
            f.read(bone_frame_name_count * 50)

        # ボーン枠要素リストのスキップ
        bone_frame_buf = f.read(4)
        if len(bone_frame_buf) == 4:
            bone_frame_count = struct.unpack('<I', bone_frame_buf)[0]
            f.read(bone_frame_count * 3)

        # 英語拡張ブロック
        english_flag_buf = f.read(1)
        if len(english_flag_buf) == 1 and struct.unpack('<B', english_flag_buf)[0] == 1:
            eng_name = _decode_cjk(f.read(20))
            if eng_name:
                model.name_e = eng_name
            eng_comment = _decode_cjk(f.read(256))
            if eng_comment:
                model.comment_e = eng_comment
            for b in model.bones:
                eng_b_name = _decode_cjk(f.read(20))
                if eng_b_name:
                    b.name_e = eng_b_name
            for m in model.morphs:
                eng_m_name = _decode_cjk(f.read(20))
                if eng_m_name:
                    m.name_e = eng_m_name
            f.read(bone_frame_name_count * 50)

        # Toonテクスチャ名リストのスキップ (10個 x 100バイト)
        f.read(1000)

        # 剛体データ (RigidBody)
        rigid_count_buf = f.read(4)
        if len(rigid_count_buf) == 4:
            rigid_count = struct.unpack('<I', rigid_count_buf)[0]
            for _ in range(rigid_count):
                rb_raw = f.read(83)
                if len(rb_raw) < 83:
                    break
                rb_name = _decode_cjk(rb_raw[:20])
                rel_bone, group_id, no_coll_mask, shape_type = struct.unpack('<HBHB', rb_raw[20:26])
                shape_size = list(struct.unpack('<3f', rb_raw[26:38]))
                shape_pos = list(struct.unpack('<3f', rb_raw[38:50]))
                shape_rot = list(struct.unpack('<3f', rb_raw[50:62]))
                mass, lin_damp, ang_damp, restitution, friction = struct.unpack('<5f', rb_raw[62:82])
                physics_mode = struct.unpack('<B', rb_raw[82:83])[0]

                rb = pmx.RigidBody()
                rb.name = rb_name
                rb.name_e = rb_name
                rb.bone_index = rel_bone if rel_bone != 65535 else -1
                rb.group = group_id
                rb.collision_mask = no_coll_mask
                rb.shape_type = shape_type
                rb.size = shape_size
                # PMD剛体位置は関連ボーンからの相対オフセット(ローカル座標)のため、
                # PMX規格準拠のワールド絶対座標に変換
                if rel_bone != 65535 and rel_bone < len(model.bones):
                    b_loc = model.bones[rel_bone].location
                    rb.position = [b_loc[0] + shape_pos[0], b_loc[1] + shape_pos[1], b_loc[2] + shape_pos[2]]
                else:
                    rb.position = shape_pos
                rb.rotation = shape_rot
                rb.mass = mass
                rb.linear_damping = lin_damp
                rb.angular_damping = ang_damp
                rb.restitution = restitution
                rb.friction = friction
                rb.physics_mode = physics_mode
                model.rigid_bodies.append(rb)

        # ジョイントデータ (Joint)
        joint_count_buf = f.read(4)
        if len(joint_count_buf) == 4:
            joint_count = struct.unpack('<I', joint_count_buf)[0]
            for _ in range(joint_count):
                j_raw = f.read(124)
                if len(j_raw) < 124:
                    break
                j_name = _decode_cjk(j_raw[:20])
                rb_a, rb_b = struct.unpack('<2I', j_raw[20:28])
                j_pos = list(struct.unpack('<3f', j_raw[28:40]))
                j_rot = list(struct.unpack('<3f', j_raw[40:52]))
                lin_min = list(struct.unpack('<3f', j_raw[52:64]))
                lin_max = list(struct.unpack('<3f', j_raw[64:76]))
                ang_min = list(struct.unpack('<3f', j_raw[76:88]))
                ang_max = list(struct.unpack('<3f', j_raw[88:100]))
                spring_lin = list(struct.unpack('<3f', j_raw[100:112]))
                spring_ang = list(struct.unpack('<3f', j_raw[112:124]))

                joint = pmx.Joint()
                joint.name = j_name
                joint.name_e = j_name
                joint.rigid_body_a = rb_a
                joint.rigid_body_b = rb_b
                joint.position = j_pos
                joint.rotation = j_rot
                joint.linear_limit_min = lin_min
                joint.linear_limit_max = lin_max
                joint.angular_limit_min = ang_min
                joint.angular_limit_max = ang_max
                joint.linear_spring = spring_lin
                joint.angular_spring = spring_ang
                model.joints.append(joint)

    return model
