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
