# -*- coding: utf-8 -*-
"""
MMD 標準ボーン日英対応辞書モジュール
mikudan, blender2pmxem, usausakokoko などの仕様・標準対応表に完全準拠し、
ボーンの和名・英名相互変換および正規化マッピングを提供します。
"""

import re
import unicodedata

# 基本ボーンの日英直接対応テーブル (左右修飾子なし、または代表的な単語)
BASE_BONE_MAP_JA_TO_EN = {
    # 主要階層・センター系
    "全ての親": "master",
    "すべての親": "master",
    "操作中心": "view cnt",
    "センター": "center",
    "グルーブ": "groove",
    "腰": "waist",
    "下半身": "lower body",
    "上半身": "upper body",
    "上半身2": "upper body2",
    "首": "neck",
    "頭": "head",
    "両目": "eyes",
    
    # 左右部位のベース単語 (左/右は後段で解決)
    "肩": "shoulder",
    "肩P": "shoulderP",
    "肩C": "shoulderC",
    "腕": "arm",
    "腕捩": "arm twist",
    "腕捩1": "arm twist1",
    "腕捩2": "arm twist2",
    "腕捩3": "arm twist3",
    "ひじ": "elbow",
    "肘": "elbow",
    "ひじ+": "elbow+",
    "ひじ++": "elbow++",
    "手捩": "wrist twist",
    "手捩1": "wrist twist1",
    "手捩2": "wrist twist2",
    "手首": "wrist",
    "手先": "finger tip",
    "ダミー": "dummy",
    "袖口-上": "cuff_top",
    "袖口-下": "cuff_bottom",
    
    # 指ボーン
    "親指０": "thumb0",
    "親指1": "thumb1",
    "親指１": "thumb1",
    "親指2": "thumb2",
    "親指２": "thumb2",
    "親指先": "thumb tip",
    "人指１": "fore1",
    "人指1": "fore1",
    "人指２": "fore2",
    "人指2": "fore2",
    "人指３": "fore3",
    "人指3": "fore3",
    "人指先": "fore tip",
    "中指１": "middle1",
    "中指1": "middle1",
    "中指２": "middle2",
    "中指2": "middle2",
    "中指３": "middle3",
    "中指3": "middle3",
    "中指先": "middle tip",
    "薬指１": "third1",
    "薬指1": "third1",
    "薬指２": "third2",
    "薬指2": "third2",
    "薬指３": "third3",
    "薬指3": "third3",
    "薬指先": "third tip",
    "小指１": "little1",
    "小指1": "little1",
    "小指２": "little2",
    "小指2": "little2",
    "小指３": "little3",
    "小指3": "little3",
    "小指先": "little tip",
    
    # 脚・足・IK
    "足": "leg",
    "足D": "leg_D",
    "足IK": "leg IK",
    "足ＩＫ": "leg IK",
    "太もも": "thigh",
    "ひざ": "knee",
    "膝": "knee",
    "ひざD": "knee_D",
    "足首": "ankle",
    "足首D": "ankle_D",
    "つま先": "toe",
    "つま先IK": "toe IK",
    "つま先ＩＫ": "toe IK",
    "かかと": "heel",
    
    # 目・顔
    "目": "eye",
    "瞳": "pupil",
    "眉": "eyebrow",
    "舌": "tongue",
    
    # 衣服・装飾・揺れもの
    "胸": "breast",
    "スカート": "skirt",
    "前髪": "front hair",
    "横髪": "side hair",
    "後髪": "back hair",
    "ポニーテール": "ponytail",
    "ツインテール": "twintail",
    "アホ毛": "ahoge",
    "リボン": "ribbon",
    "マント": "cape",
    "尾": "tail"
}

# 左右逆引きテーブルの自動生成用
BASE_BONE_MAP_EN_TO_JA = {v: k for k, v in BASE_BONE_MAP_JA_TO_EN.items()}

def get_english_bone_name(japanese_name):
    """
    日本語ボーン名から標準英語ボーン名を解決します。
    「左腕」 -> "arm_L", 「右足ＩＫ」 -> "leg IK_R", 「全ての親」 -> "master"
    """
    if not japanese_name:
        return ""
        
    jp = unicodedata.normalize('NFKC', str(japanese_name).strip())
    
    # 1. 完全一致
    if jp in BASE_BONE_MAP_JA_TO_EN:
        return BASE_BONE_MAP_JA_TO_EN[jp]
        
    # 2. 左右プレフィックス ("左", "右") の解決
    side = None
    core_name = jp
    if jp.startswith("左"):
        side = "_L"
        core_name = jp[1:]
    elif jp.startswith("右"):
        side = "_R"
        core_name = jp[1:]
        
    if core_name in BASE_BONE_MAP_JA_TO_EN:
        en_core = BASE_BONE_MAP_JA_TO_EN[core_name]
        return f"{en_core}{side}" if side else en_core
        
    # 3. スカート系ボーン (q_0_0 -> Skirt_0_0)
    if jp.startswith("q_"):
        return jp.replace("q_", "Skirt_")
        
    return ""

def get_japanese_bone_name(english_name):
    """
    英語ボーン名から標準日本語ボーン名を解決します。
    "arm_L" -> 「左腕」, "leg IK_R" -> 「右足IK」, "master" -> 「全ての親」
    """
    if not english_name:
        return ""
        
    en = str(english_name).strip()
    
    # 1. 完全一致
    if en in BASE_BONE_MAP_EN_TO_JA:
        return BASE_BONE_MAP_EN_TO_JA[en]
        
    # 2. 左右サフィックス ("_L", "_R", ".L", ".R") の解決
    side = None
    core_name = en
    if en.endswith("_L") or en.endswith(".L"):
        side = "左"
        core_name = en[:-2]
    elif en.endswith("_R") or en.endswith(".R"):
        side = "右"
        core_name = en[:-2]
    elif en.startswith("left_") or en.startswith("Left_") or en.startswith("left"):
        side = "左"
        core_name = en[4:].lstrip('_')
    elif en.startswith("right_") or en.startswith("Right_") or en.startswith("right"):
        side = "右"
        core_name = en[5:].lstrip('_')
        
    if core_name in BASE_BONE_MAP_EN_TO_JA:
        jp_core = BASE_BONE_MAP_EN_TO_JA[core_name]
        return f"{side}{jp_core}" if side else jp_core
        
    return ""
