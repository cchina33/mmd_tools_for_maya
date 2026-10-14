# -*- coding: utf-8 -*-
"""
ユーザー辞書・マテリアル保護設定管理モジュール
上級ユーザーがカスタマイズしたマテリアルキーワード、ボーン辞書、名称変換辞書を永続化・管理します。
キーワードは日本語と英語で左右に分離して管理・表示されます。
"""

import os
import json
import re

# デフォルト設定値 (日本語・英語を分離)
DEFAULT_SETTINGS = {
    # 顔・肌・表情マテリアル判定キーワード (日本語 / 英語)
    "face_skin_keywords_ja": [
        "顔", "目", "瞳", "眉", "口", "舌", "牙", "歯", "唇", "表情", "涙", "頬", "肌", "体", "面", "鼻"
    ],
    "face_skin_keywords_en": [
        "head", "face", "eye", "brow", "mouth", "teeth", "tooth", "lip", "cheek", "skin", "body", "nose"
    ],

    # Toon乗算除外キーワード (日本語 / 英語)
    "toon_bypass_keywords_ja": [
        "瞳-高光", "高光", "眼白", "ハイライト"
    ],
    "toon_bypass_keywords_en": [
        "highlight"
    ],

    # カスタムボーン日英変換辞書 (和名: 英名)
    "custom_bone_dict": {},
    # カスタムモーフ日英変換辞書 (和名: 英名)
    "custom_morph_dict": {},
    # カスタム名称変換ルール (変換前: 変換後)
    "custom_name_translations": {}
}

def get_settings_file_path():
    """設定ファイルの保存先パスを返します"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "user_dictionary.json")

def _is_mostly_ascii(text):
    """英数字・記号のみで構成されているかを判定します"""
    return bool(re.match(r'^[a-zA-Z0-9_\-\s]+$', text))

def load_user_settings():
    """
    保存された設定を読み込みます。
    ファイルが存在しないか壊れている場合はデフォルト設定を返します。
    旧形式の一体型リストが存在する場合は自動で日本語と英語に振り分けます。
    """
    filepath = get_settings_file_path()
    if not os.path.exists(filepath):
        return get_default_settings()

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        merged = get_default_settings()

        # 旧形式（face_skin_keywords）の互換対応
        if "face_skin_keywords" in data and "face_skin_keywords_ja" not in data:
            old_list = data["face_skin_keywords"]
            merged["face_skin_keywords_ja"] = [k for k in old_list if not _is_mostly_ascii(k)]
            merged["face_skin_keywords_en"] = [k for k in old_list if _is_mostly_ascii(k)]
        else:
            if "face_skin_keywords_ja" in data:
                merged["face_skin_keywords_ja"] = data["face_skin_keywords_ja"]
            if "face_skin_keywords_en" in data:
                merged["face_skin_keywords_en"] = data["face_skin_keywords_en"]

        # 旧形式（toon_bypass_keywords）の互換対応
        if "toon_bypass_keywords" in data and "toon_bypass_keywords_ja" not in data:
            old_list = data["toon_bypass_keywords"]
            merged["toon_bypass_keywords_ja"] = [k for k in old_list if not _is_mostly_ascii(k)]
            merged["toon_bypass_keywords_en"] = [k for k in old_list if _is_mostly_ascii(k)]
        else:
            if "toon_bypass_keywords_ja" in data:
                merged["toon_bypass_keywords_ja"] = data["toon_bypass_keywords_ja"]
            if "toon_bypass_keywords_en" in data:
                merged["toon_bypass_keywords_en"] = data["toon_bypass_keywords_en"]

        if "custom_bone_dict" in data:
            merged["custom_bone_dict"] = data["custom_bone_dict"]
        if "custom_morph_dict" in data:
            merged["custom_morph_dict"] = data["custom_morph_dict"]
        if "custom_name_translations" in data:
            merged["custom_name_translations"] = data["custom_name_translations"]

        return merged
    except Exception as e:
        print(f"[警告] ユーザー辞書の読み込みに失敗しました。デフォルト値を使用します: {e}")
        return get_default_settings()

def save_user_settings(settings):
    """設定をJSONファイルへ保存します"""
    filepath = get_settings_file_path()
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[エラー] ユーザー辞書の保存に失敗しました: {e}")
        return False

def get_default_settings():
    """安全な初期デフォルト設定のコピーを返します"""
    import copy
    return copy.deepcopy(DEFAULT_SETTINGS)

def get_all_face_skin_keywords():
    """日本語・英語を合算した顔・肌保護キーワードリストを返します"""
    settings = load_user_settings()
    ja = settings.get("face_skin_keywords_ja", [])
    en = settings.get("face_skin_keywords_en", [])
    return ja + en

def get_all_toon_bypass_keywords():
    """日本語・英語を合算したToon除外キーワードリストを返します"""
    settings = load_user_settings()
    ja = settings.get("toon_bypass_keywords_ja", [])
    en = settings.get("toon_bypass_keywords_en", [])
    return ja + en

def is_face_or_skin_material(mat_name, orig_name=""):
    """マテリアル名が顔・肌・表情に該当するかを判定します"""
    keywords = get_all_face_skin_keywords()
    lower_mat = mat_name.lower()
    lower_orig = orig_name.lower() if orig_name else ""
    return any(k.lower() in lower_mat or (lower_orig and k.lower() in lower_orig) for k in keywords)

def is_toon_bypass_material(mat_name, orig_name=""):
    """マテリアル名がToon乗算除外（瞳ハイライト等）に該当するかを判定します"""
    keywords = get_all_toon_bypass_keywords()
    lower_mat = mat_name.lower()
    lower_orig = orig_name.lower() if orig_name else ""
    return any(k.lower() in lower_mat or (lower_orig and k.lower() in lower_orig) for k in keywords)


# ==============================================================================
# ボーン日英辞書・HumanIK辞書・日本語ローマ字変換辞書のJSON管理
# ==============================================================================
def get_bone_dict_file_path():
    """ボーン日英対応表JSONのパスを返します"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "bone_dict.json")

def load_bone_dict_json():
    """ボーン日英対応表JSONを読み込みます"""
    filepath = get_bone_dict_file_path()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[警告] bone_dict.json の読み込みに失敗しました: {e}")
    try:
        from .bone_dict import BASE_BONE_MAP_JA_TO_EN
        return dict(BASE_BONE_MAP_JA_TO_EN)
    except Exception:
        return {}

def save_bone_dict_json(data):
    """ボーン日英対応表JSONを保存します"""
    filepath = get_bone_dict_file_path()
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # モジュール内のメモリキャッシュも更新
        try:
            from . import bone_dict
            bone_dict.reload_bone_map()
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[エラー] bone_dict.json の保存に失敗しました: {e}")
        return False

def get_hik_dict_file_path():
    """HumanIK辞書JSONのパスを返します"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "hik_dict.json")

def load_hik_dict_json():
    """HumanIK辞書JSONを読み込みます (ID文字列をintにマッピング)"""
    filepath = get_hik_dict_file_path()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw = json.load(f)
                result = {}
                for k, v in raw.items():
                    item_id = int(v.get("id", k))
                    result[item_id] = [v.get("label", ""), v.get("pattern", "")]
                return result
        except Exception as e:
            print(f"[警告] hik_dict.json の読み込みに失敗しました: {e}")
    try:
        from .hik import dic_hik
        return dict(dic_hik)
    except Exception:
        return {}

def save_hik_dict_json(data):
    """HumanIK辞書JSONを保存します"""
    filepath = get_hik_dict_file_path()
    try:
        json_obj = {}
        for k, v in sorted(data.items(), key=lambda x: int(x[0])):
            item_id = int(k)
            label = v[0] if isinstance(v, (list, tuple)) and len(v) > 0 else ""
            pattern = v[1] if isinstance(v, (list, tuple)) and len(v) > 1 else ""
            json_obj[str(item_id)] = {
                "id": item_id,
                "label": label,
                "pattern": pattern
            }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(json_obj, f, ensure_ascii=False, indent=2)
        # モジュール内のメモリキャッシュも更新
        try:
            from . import hik
            hik.reload_hik_dict()
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[エラー] hik_dict.json の保存に失敗しました: {e}")
        return False

def get_jaka_dict_file_path():
    """日本語ローマ字変換辞書JSONのパスを返します"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "jaka_dict.json")

def load_jaka_dict_json():
    """日本語ローマ字変換辞書JSONを読み込みます"""
    filepath = get_jaka_dict_file_path()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[警告] jaka_dict.json の読み込みに失敗しました: {e}")
    try:
        from .jaka import MMD_KANJI_DICT
        return dict(MMD_KANJI_DICT)
    except Exception:
        return {}

def save_jaka_dict_json(data):
    """日本語ローマ字変換辞書JSONを保存します"""
    filepath = get_jaka_dict_file_path()
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # モジュール内のメモリキャッシュも更新
        try:
            from . import jaka
            jaka.reload_kanji_dict()
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[エラー] jaka_dict.json の保存に失敗しました: {e}")
        return False

def get_morph_dict_file_path():
    """モーフ日英対応表JSONのパスを返します"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "morph_dict.json")

def load_morph_dict_json():
    """モーフ日英対応表JSONを読み込みます"""
    filepath = get_morph_dict_file_path()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[警告] morph_dict.json の読み込みに失敗しました: {e}")
    # 標準デフォルトモーフ辞書
    return {
        "まばたき": "blink",
        "笑い": "smile",
        "ウィンク": "wink",
        "ウィンク右": "wink_R",
        "ウィンク２": "wink2",
        "ジト目": "jitome",
        "じと目": "jitome",
        "なごみ": "nagomi",
        "びっくり": "surprise",
        "怒り": "anger",
        "あ": "a",
        "い": "i",
        "う": "u",
        "え": "e",
        "お": "o",
        "ワ": "wa",
        "ω": "omega",
        "▲": "triangle",
        "口角上げ": "lip_up",
        "口角下げ": "lip_down",
        "照れ": "blush",
        "頬染め": "blush",
        "青ざめ": "pale",
        "涙": "tear",
        "瞳小": "pupil_small",
        "光下": "light_down"
    }

def save_morph_dict_json(data):
    """モーフ日英対応表JSONを保存します"""
    filepath = get_morph_dict_file_path()
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[エラー] morph_dict.json の保存に失敗しました: {e}")
        return False

