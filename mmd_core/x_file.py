# -*- coding: utf-8 -*-
"""
mmd_core.x_file - DirectX .x ファイルパーサー

DirectX .x メッシュファイルを解析し、PMX互換の Model オブジェクトとして変換します。
template定義やメタ情報の安全なスキップ、自由書式（コメント、多様な区切り記号）に
完全対応したオリジナル字句解析エンジンです。
"""

import os
import re
from . import pmx

class XTokenReader:
    """
    DirectX .x ファイルのトークンを読み進める字句解析クラス
    """
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.length = len(tokens)

    def has_next(self):
        return self.pos < self.length

    def peek(self):
        if self.pos < self.length:
            return self.tokens[self.pos]
        return None

    def next_token(self):
        if self.pos < self.length:
            tok = self.tokens[self.pos]
            self.pos += 1
            return tok
        return None

    def next_value(self):
        """区切り記号（セミコロンやカンマ）を自動的にスキップし、次の値トークンを取得"""
        while self.pos < self.length:
            tok = self.tokens[self.pos]
            self.pos += 1
            if tok not in (';', ','):
                return tok
        return None

    def next_float(self):
        val = self.next_value()
        if val is None:
            raise ValueError("予期せぬファイルの終端に達しました")
        return float(val)

    def next_int(self):
        val = self.next_value()
        if val is None:
            raise ValueError("予期せぬファイルの終端に達しました")
        return int(val)

    def next_string(self):
        val = self.next_value()
        if val is None:
            return ""
        if val.startswith('"') and val.endswith('"'):
            return val[1:-1]
        return val

    def skip_until(self, target):
        """指定のトークンまで読み飛ばす"""
        while self.pos < self.length:
            if self.tokens[self.pos] == target:
                self.pos += 1
                return True
            self.pos += 1
        return False

    def skip_block(self):
        """現在の位置から波括弧ブロック（{ ... }）の終端まで安全にスキップ"""
        if not self.skip_until('{'):
            return
        depth = 1
        while self.pos < self.length and depth > 0:
            tok = self.tokens[self.pos]
            self.pos += 1
            if tok == '{':
                depth += 1
            elif tok == '}':
                depth -= 1


def _remove_comments(content):
    """
    クォート内の文字列を保護しつつ、コメント（# または //）を除去
    """
    lines = []
    for line in content.splitlines():
        idx_slash = line.find('//')
        idx_hash = line.find('#')
        cut_idx = -1
        if idx_slash != -1 and idx_hash != -1:
            cut_idx = min(idx_slash, idx_hash)
        elif idx_slash != -1:
            cut_idx = idx_slash
        elif idx_hash != -1:
            cut_idx = idx_hash

        if cut_idx != -1:
            quotes_before = line[:cut_idx].count('"')
            if quotes_before % 2 == 0:
                line = line[:cut_idx]
        lines.append(line)
    return '\n'.join(lines)


def _parse_material(reader, file_dir, texture_paths, model):
    """
    Material ブロックを解析し、pmx.Material オブジェクトを返します。
    """
    reader.skip_until('{')
    diff_r = reader.next_float()
    diff_g = reader.next_float()
    diff_b = reader.next_float()
    diff_a = reader.next_float()
    diffuse = [diff_r, diff_g, diff_b, diff_a]

    spec_power = reader.next_float()
    spec_r = reader.next_float()
    spec_g = reader.next_float()
    spec_b = reader.next_float()
    specular = [spec_r, spec_g, spec_b, spec_power]

    amb_r = reader.next_float()
    amb_g = reader.next_float()
    amb_b = reader.next_float()
    ambient = [amb_r, amb_g, amb_b]

    mat = pmx.Material()
    mat.name = f"Material_{len(model.materials) + 1}"
    mat.diffuse = diffuse
    mat.specular = specular
    mat.ambient = ambient
    mat.is_double_sided = True
    mat.texture = -1

    # サブ定義（テクスチャファイル名など）を走査
    depth = 1
    while reader.has_next() and depth > 0:
        sub_tok = reader.next_token()
        if sub_tok == '{':
            depth += 1
        elif sub_tok == '}':
            depth -= 1
        elif sub_tok == 'TextureFilename':
            reader.skip_until('{')
            raw_tex_name = reader.next_string()
            # MMD特有のメインテクスチャ*スフィアマップ分離
            if '*' in raw_tex_name:
                raw_tex_name = raw_tex_name.split('*')[0]
            clean_tex_name = raw_tex_name.replace('\\\\', '/').replace('\\', '/')
            if clean_tex_name:
                if clean_tex_name not in texture_paths:
                    texture_paths.append(clean_tex_name)
                    full_tex_path = os.path.join(file_dir, clean_tex_name)
                    tex_obj = pmx.Texture(full_tex_path)
                    model.textures.append(tex_obj)
                mat.texture = texture_paths.index(clean_tex_name)
            reader.skip_until('}')

    return mat


def load2pmx(file_path):
    """
    DirectX .x ファイルを読み込み、PMX互換の Model オブジェクトとして返します。
    """
    model_name = os.path.splitext(os.path.basename(file_path))[0]
    model = pmx.Model()
    model.name = model_name
    model.name_e = model_name

    # エンコーディングの自動判別（UTF-8 または CP932/Shift_JIS）
    raw_bytes = None
    with open(file_path, 'rb') as f:
        raw_bytes = f.read()

    text_content = None
    for enc in ('utf-8-sig', 'utf-8', 'cp932', 'shift_jis'):
        try:
            text_content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if text_content is None:
        text_content = raw_bytes.decode('cp932', errors='ignore')

    # コメントの除去
    clean_text = _remove_comments(text_content)

    # トークン分割（GUID識別子 <...>, ダブルクォート文字列, 波括弧, 区切り文字, 単語）
    token_pattern = re.compile(r'"[^"]*"|<[^>]*>|[{};,]|[^{};,\s<>]+')
    tokens = token_pattern.findall(clean_text)

    reader = XTokenReader(tokens)

    texture_paths = []
    file_dir = os.path.dirname(file_path)

    while reader.has_next():
        tok = reader.next_token()

        # テンプレート仕様定義ブロックの安全なスキップ
        if tok == 'template':
            reader.skip_block()
            continue

        # ヘッダー定義ブロックの安全なスキップ
        if tok == 'Header':
            reader.skip_block()
            continue

        # 実メッシュデータの解析
        if tok == 'Mesh':
            reader.skip_until('{')
            mesh_vert_start = len(model.vertices)

            # 頂点数と座標の取得
            vert_count = reader.next_int()
            for _ in range(vert_count):
                vx = reader.next_float()
                vy = reader.next_float()
                vz = reader.next_float()
                v = pmx.Vertex()
                v.co = [vx, vy, vz]
                model.vertices.append(v)

            # 面数とインデックスの取得
            face_count = reader.next_int()
            mesh_faces = []
            for _ in range(face_count):
                poly_size = reader.next_int()
                indices = [reader.next_int() + mesh_vert_start for _ in range(poly_size)]
                indices.reverse()

                if poly_size == 3:
                    mesh_faces.append(indices)
                elif poly_size == 4:
                    mesh_faces.append([indices[0], indices[1], indices[2]])
                    mesh_faces.append([indices[0], indices[2], indices[3]])
                elif poly_size > 4:
                    for pi in range(1, poly_size - 1):
                        mesh_faces.append([indices[0], indices[pi], indices[pi + 1]])

            mesh_mat_indices = []
            mesh_materials = []

            # Mesh 内部のサブ定義（UV、マテリアル等）を巡回
            mesh_depth = 1
            while reader.has_next() and mesh_depth > 0:
                sub_tok = reader.next_token()
                if sub_tok == '{':
                    mesh_depth += 1
                elif sub_tok == '}':
                    mesh_depth -= 1
                elif sub_tok == 'MeshTextureCoords':
                    reader.skip_until('{')
                    uv_count = reader.next_int()
                    for i in range(uv_count):
                        u = reader.next_float()
                        v = reader.next_float()
                        target_v_idx = mesh_vert_start + i
                        if target_v_idx < len(model.vertices):
                            model.vertices[target_v_idx].uv = [u, v]
                    reader.skip_until('}')
                elif sub_tok == 'MeshMaterialList':
                    reader.skip_until('{')
                    _mat_count = reader.next_int()
                    f_count = reader.next_int()
                    for _ in range(f_count):
                        mesh_mat_indices.append(reader.next_int())
                elif sub_tok == 'Material':
                    mat = _parse_material(reader, file_dir, texture_paths, model)
                    mesh_materials.append(mat)

            # メッシュごとの面とマテリアルのバインド処理
            if mesh_materials and mesh_mat_indices:
                mat_start_idx = len(model.materials)
                for m in mesh_materials:
                    model.materials.append(m)

                mat_faces_map = [[] for _ in range(len(mesh_materials))]
                for f_idx, m_local_idx in enumerate(mesh_mat_indices):
                    if f_idx < len(mesh_faces) and m_local_idx < len(mat_faces_map):
                        mat_faces_map[m_local_idx].append(mesh_faces[f_idx])

                for m_idx, mat in enumerate(mesh_materials):
                    assigned_faces = mat_faces_map[m_idx]
                    mat.vertex_count = len(assigned_faces) * 3
                    for tri in assigned_faces:
                        model.faces.append(tri)
            elif mesh_materials:
                # 面の個別材質指定がない場合、最初の材質に全ポリゴンを割り当て
                for m in mesh_materials:
                    model.materials.append(m)
                mesh_materials[0].vertex_count = len(mesh_faces) * 3
                for tri in mesh_faces:
                    model.faces.append(tri)
            else:
                # 材質定義がない場合のデフォルトマテリアル
                def_mat = pmx.Material()
                def_mat.name = f"Material_{len(model.materials) + 1}"
                def_mat.vertex_count = len(mesh_faces) * 3
                model.materials.append(def_mat)
                for tri in mesh_faces:
                    model.faces.append(tri)

    return model
