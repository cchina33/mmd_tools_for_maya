# -*- coding: utf-8 -*-
"""
PMX モデル解析・一括保存コアモジュール (analyzer_core.py)

ユーザーが読み込んだモデルの材質、ボーン、モーフ、剛体、Jointを一括保存し、
jaka.py およびユーザー辞書に未登録の漢字・ボーン名を高精度に検出します。
"""

import os
import re
import json
import unicodedata

try:
    from .. import mmd_core
    from ..asset import jaka, user_dict_manager
except Exception:
    import mmd_core
    from asset import jaka, user_dict_manager

# CJK統合漢字の正規表現パターン
KANJI_PATTERN = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')

def export_pmx_structure(pmx_path, output_json_path=None):
    """
    PMXモデルから材質、ボーン、モーフ、剛体、Jointの全要素を抽出し、
    詳細な構造情報として一括保存（JSON）します。
    """
    if not os.path.exists(pmx_path):
        raise FileNotFoundError(f"PMXファイルが見つかりません: {pmx_path}")

    model = mmd_core.pmx.load(pmx_path)

    # 1. モデル基本情報
    analysis_data = {
        "model_info": {
            "name": model.name,
            "name_e": getattr(model, 'name_e', ''),
            "comment": getattr(model, 'comment', ''),
            "comment_e": getattr(model, 'comment_e', ''),
            "vertex_count": len(model.vertices),
            "face_count": len(model.faces),
            "texture_count": len(model.textures),
            "file_path": (
                os.path.abspath(pmx_path).replace(
                    f"Users\\{os.path.basename(os.environ.get('USERPROFILE', ''))}", "Users\\<ユーザー名>"
                ).replace(
                    f"Users/{os.path.basename(os.environ.get('USERPROFILE', ''))}", "Users/<ユーザー名>"
                ) if os.environ.get('USERPROFILE') else os.path.abspath(pmx_path)
            )
        },
        "textures": [getattr(t, 'path', str(t)) for t in model.textures],
        "materials": [],
        "bones": [],
        "morphs": [],
        "rigid_bodies": [],
        "joints": []
    }

    # 2. 材質 (Materials)
    for idx, mat in enumerate(model.materials):
        mat_info = {
            "index": idx,
            "name": mat.name,
            "name_e": getattr(mat, 'name_e', ''),
            "diffuse": [float(v) for v in mat.diffuse],
            "specular": [float(v) for v in mat.specular],
            "ambient": [float(v) for v in mat.ambient],
            "edge_color": [float(v) for v in getattr(mat, 'edge_color', [])],
            "edge_size": float(getattr(mat, 'edge_size', 0.0)),
            "texture": getattr(mat, 'texture', -1),
            "sphere_texture": getattr(mat, 'sphere_texture', -1),
            "sphere_texture_mode": getattr(mat, 'sphere_texture_mode', 0),
            "toon_texture": getattr(mat, 'toon_texture', -1),
            "is_shared_toon_texture": bool(getattr(mat, 'is_shared_toon_texture', False)),
            "is_double_sided": bool(getattr(mat, 'is_double_sided', False)),
            "vertex_count": getattr(mat, 'vertex_count', 0)
        }
        analysis_data["materials"].append(mat_info)

    # 3. ボーン (Bones)
    for idx, bone in enumerate(model.bones):
        bone_info = {
            "index": idx,
            "name": bone.name,
            "name_e": getattr(bone, 'name_e', ''),
            "location": [round(float(v), 5) for v in bone.location],
            "parent_index": bone.parent,
            "transform_level": getattr(bone, 'transform_level', 0),
            "is_ik": getattr(bone, 'isIK', False),
            "visible": getattr(bone, 'visible', True),
            "rotatable": getattr(bone, 'rotatable', True),
            "translatable": getattr(bone, 'translatable', True),
            "has_additional_rotate": getattr(bone, 'hasAdditionalRotate', False),
            "has_additional_location": getattr(bone, 'hasAdditionalLocation', False)
        }
        if bone_info["has_additional_rotate"] or bone_info["has_additional_location"]:
            bone_info["additional_transform"] = getattr(bone, 'additionalTransform', [])
        if bone_info["is_ik"] and hasattr(bone, 'ik'):
            ik_data = bone.ik
            bone_info["ik_target"] = getattr(ik_data, 'target', -1)
            bone_info["ik_loop"] = getattr(ik_data, 'loop', 0)
            bone_info["ik_limit_radian"] = getattr(ik_data, 'limit_radian', 0.0)
            bone_info["ik_links"] = []
            for link in getattr(ik_data, 'links', []):
                bone_info["ik_links"].append({
                    "target": link.target,
                    "has_limit": link.has_limit,
                    "limit_min": [float(v) for v in link.limit_min] if link.has_limit else [],
                    "limit_max": [float(v) for v in link.limit_max] if link.has_limit else []
                })
        analysis_data["bones"].append(bone_info)

    # 4. モーフ (Morphs)
    for idx, morph in enumerate(model.morphs):
        morph_info = {
            "index": idx,
            "name": morph.name,
            "name_e": getattr(morph, 'name_e', ''),
            "panel": getattr(morph, 'panel', 0),
            "type_index": morph.type_index(),
            "offset_count": len(getattr(morph, 'offsets', []))
        }
        analysis_data["morphs"].append(morph_info)

    # 5. 剛体 (Rigid Bodies)
    for idx, rb in enumerate(model.rigid_bodies):
        rb_info = {
            "index": idx,
            "name": rb.name,
            "name_e": getattr(rb, 'name_e', ''),
            "bone_index": getattr(rb, 'bone_index', -1),
            "collision_group": getattr(rb, 'group', 0),
            "collision_mask": getattr(rb, 'collision_mask', 0),
            "shape_type": getattr(rb, 'shape_type', 0),
            "shape_size": [round(float(v), 5) for v in getattr(rb, 'size', [0, 0, 0])],
            "position": [round(float(v), 5) for v in getattr(rb, 'position', [0, 0, 0])],
            "rotation": [round(float(v), 5) for v in getattr(rb, 'rotation', [0, 0, 0])],
            "mass": float(getattr(rb, 'mass', 1.0)),
            "linear_damping": float(getattr(rb, 'linear_damping', 0.0)),
            "angular_damping": float(getattr(rb, 'angular_damping', 0.0)),
            "restitution": float(getattr(rb, 'restitution', 0.0)),
            "friction": float(getattr(rb, 'friction', 0.0)),
            "physics_mode": getattr(rb, 'physics_mode', 0)
        }
        analysis_data["rigid_bodies"].append(rb_info)

    # 6. Joint (コンストレイント)
    for idx, jt in enumerate(model.joints):
        jt_info = {
            "index": idx,
            "name": jt.name,
            "name_e": getattr(jt, 'name_e', ''),
            "joint_type": getattr(jt, 'joint_type', 0),
            "rigid_body_a": getattr(jt, 'rigid_body_a', -1),
            "rigid_body_b": getattr(jt, 'rigid_body_b', -1),
            "position": [round(float(v), 5) for v in getattr(jt, 'position', [0, 0, 0])],
            "rotation": [round(float(v), 5) for v in getattr(jt, 'rotation', [0, 0, 0])],
            "linear_limit_min": [round(float(v), 5) for v in getattr(jt, 'linear_limit_min', [0, 0, 0])],
            "linear_limit_max": [round(float(v), 5) for v in getattr(jt, 'linear_limit_max', [0, 0, 0])],
            "angular_limit_min": [round(float(v), 5) for v in getattr(jt, 'angular_limit_min', [0, 0, 0])],
            "angular_limit_max": [round(float(v), 5) for v in getattr(jt, 'angular_limit_max', [0, 0, 0])],
            "linear_spring": [round(float(v), 5) for v in getattr(jt, 'linear_spring', [0, 0, 0])],
            "angular_spring": [round(float(v), 5) for v in getattr(jt, 'angular_spring', [0, 0, 0])]
        }
        analysis_data["joints"].append(jt_info)

    # 保存先ファイルの決定 (asset/User_pmx_data フォルダ配下に保存)
    if not output_json_path:
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        user_pmx_dir = os.path.join(plugin_root, "asset", "User_pmx_data")
        base_name = os.path.splitext(os.path.basename(pmx_path))[0]
        output_json_path = os.path.join(user_pmx_dir, f"{base_name}_pmx_analysis.json")

    os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(analysis_data, f, ensure_ascii=False, indent=2)

    print(f"[PMX解析] 一括保存完了: {output_json_path}")
    print(f"  - 材質: {len(analysis_data['materials'])} 件, ボーン: {len(analysis_data['bones'])} 件")
    print(f"  - モーフ: {len(analysis_data['morphs'])} 件, 剛体: {len(analysis_data['rigid_bodies'])} 件, Joint: {len(analysis_data['joints'])} 件")
    return output_json_path, analysis_data

def get_registered_kanji_words():
    """
    jaka.py の標準辞書およびユーザー辞書に登録されているすべての単語・漢字セットを取得します。
    """
    registered = set(jaka.MMD_KANJI_DICT.keys())
    try:
        user_settings = user_dict_manager.load_user_settings()
        user_trans = user_settings.get("custom_name_translations", {})
        registered.update(user_trans.keys())
    except Exception:
        pass
    return registered

def find_unregistered_kanji_in_bones(pmx_path_or_model):
    """
    モデル内のボーン名を走査し、jaka.py およびユーザー辞書に未登録の漢字を抽出します。
    
    戻り値:
        list of dict: [
            {"kanji": "椛", "bones": ["椛_髪1", "椛_リボン"]},
            ...
        ]
    """
    if isinstance(pmx_path_or_model, str):
        if not os.path.exists(pmx_path_or_model):
            return []
        model = mmd_core.pmx.load(pmx_path_or_model)
    else:
        model = pmx_path_or_model

    registered_words = get_registered_kanji_words()
    # 長い単語から優先してマッチング
    sorted_words = sorted(registered_words, key=len, reverse=True)

    unregistered_map = {} # 漢字 -> 出現ボーン名のリスト

    for bone in model.bones:
        name = bone.name
        if not name:
            continue
        norm_name = unicodedata.normalize('NFKC', name)

        # 登録済みの語句を取り除く
        temp_name = norm_name
        for word in sorted_words:
            if word in temp_name:
                temp_name = temp_name.replace(word, " ")

        # 残った文字列から漢字文字を抽出
        found_kanji = KANJI_PATTERN.findall(temp_name)
        for k in found_kanji:
            unregistered_map.setdefault(k, []).append(name)

    # リスト形式で整理
    results = []
    for k, bone_list in sorted(unregistered_map.items()):
        # 重複ボーン名を除去して一意化
        unique_bones = list(dict.fromkeys(bone_list))
        results.append({
            "kanji": k,
            "bones": unique_bones
        })

    return results
