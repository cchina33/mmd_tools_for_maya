# -*- coding: utf-8 -*-
"""
HumanIK に使用するジョイント名・正規表現辞書および T ポーズ展開ユーティリティ
"""
import maya.cmds as mc
import math
import unicodedata

dic_hik = {
    0: ['センター', '.*sentaa'],
    1: ['下半身', 'kahanshin'],
    2: ['左足', 'hidariashi'],
    3: ['左膝', 'hidarihiza'],
    4: ['左足首', 'hidariashikubi'],
    5: ['右足', 'migiashi'],
    6: ['右膝', 'migihiza'],
    7: ['右足首', 'migiashikubi'],
    8: ['上半身', 'jouhanshin'],
    9: ['左腕', 'hidariude'],
    10: ['左肘', 'hidarihiji'],
    11: ['左手首', 'hidarite(kubi)?'],
    12: ['右腕', 'migiude'],
    13: ['右肘', 'migihiji'],
    14: ['右手首', 'migite(kubi)?'],
    15: ['頭', 'atama'],
    16: ['左つま先', 'hidari(tsuma|ashi)saki'],
    17: ['右つま先', 'migi(tsuma|ashi)saki'],
    18: ['左肩', 'hidarikata'],
    19: ['右肩', 'migikata'],
    20: ['首', 'kubi'],
    23: ['上半身2', 'jouhanshin2'],
    45: ['左腕捩', 'hidariudemojiri'],
    46: ['左手捩', 'hidaritemojiri'],
    47: ['右腕捩', 'migiudemojiri'],
    48: ['右手捩', 'migitemojiri'],
    50: ['左親指0', 'hidarioyayubi0M?'],
    51: ['左親指1', 'hidarioyayubi1'],
    52: ['左親指2', 'hidarioyayubi2'],
    53: ['左親指先', 'hidarioyayubi.*saki'],
    54: ['左人差指1', 'hidari(hitosashi|nin)yubi1'],
    55: ['左人差指2', 'hidari(hitosashi|nin)yubi2'],
    56: ['左人差指3', 'hidari(hitosashi|nin)yubi3'],
    57: ['左人差指先', 'hidari(hitosashi|nin)yubi.*saki'],
    58: ['左中指1', '(sachuu|hidarinaka)yubi1'],
    59: ['左中指2', '(sachuu|hidarinaka)yubi2'],
    60: ['左中指3', '(sachuu|hidarinaka)yubi3'],
    61: ['左中指先', '(sachuu|hidarinaka)yubi.*saki'],
    62: ['左薬指1', 'hidarikusuriyubi1'],
    63: ['左薬指2', 'hidarikusuriyubi2'],
    64: ['左薬指3', 'hidarikusuriyubi3'],
    65: ['左薬指先', 'hidarikusuriyubi.*saki'],
    66: ['左小指1', 'hidarikoyubi1'],
    67: ['左小指2', 'hidarikoyubi2'],
    68: ['左小指3', 'hidarikoyubi3'],
    69: ['左小指先', 'hidarikoyubi.*saki'],
    74: ['右親指0', 'migioyayubi0M?'],
    75: ['右親指1', 'migioyayubi1'],
    76: ['右親指2', 'migioyayubi2'],
    77: ['右親指先', 'migioyayubi.*saki'],
    78: ['右人差指1', 'migi(hitosashi|nin)yubi1'],
    79: ['右人差指2', 'migi(hitosashi|nin)yubi2'],
    80: ['右人差指3', 'migi(hitosashi|nin)yubi3'],
    81: ['右人差指先', 'migi(hitosashi|nin)yubi.*saki'],
    82: ['右中指1', '(uchuu|miginaka)yubi1'],
    83: ['右中指2', '(uchuu|miginaka)yubi2'],
    84: ['右中指3', '(uchuu|miginaka)yubi3'],
    85: ['右中指先', '(uchuu|miginaka)yubi.*saki'],
    86: ['右薬指1', 'migikusuriyubi1'],
    87: ['右薬指2', 'migikusuriyubi2'],
    88: ['右薬指3', 'migikusuriyubi3'],
    89: ['右薬指先', 'migikusuriyubi.*saki'],
    90: ['右小指1', 'migikoyubi1'],
    91: ['右小指2', 'migikoyubi2'],
    92: ['右小指3', 'migikoyubi3'],
    93: ['右小指先', 'migikoyubi.*saki']
}

def normalize_bone_name(name):
    """
    ボーン名の全角/半角、ひらがな/漢字の表記揺れを統一正規化します。
    """
    if not name:
        return ""
    n = unicodedata.normalize('NFKC', str(name))
    n = n.replace('ひじ', '肘').replace('ヒジ', '肘')
    n = n.replace('ひざ', '膝').replace('ヒザ', '膝')
    n = n.replace('人差指', '人指').replace('にんゆび', '人指')
    return n

def get_bone_matching_candidates(label_text):
    """
    HumanIK定義ラベルから、MMDモデルで想定される全てのボーン名候補（正規化済み）を返します。
    """
    norm = normalize_bone_name(label_text)
    candidates = [norm]
    # 指先表記の相互補完
    if '先' in norm:
        if '親指' in norm:
            candidates.append(norm.replace('先', '3'))
        else:
            candidates.append(norm.replace('先', '4'))
            candidates.append(norm.replace('先', '3'))
    elif any(f in norm for f in ['人指', '中指', '薬指', '小指']):
        if norm.endswith('4'):
            candidates.append(norm[:-1] + '先')
    elif '親指' in norm:
        if norm.endswith('3'):
            candidates.append(norm[:-1] + '先')
    return candidates

def calculate_aim_euler_angles(v_current, v_target):
    """
    2つの3Dベクトル間の最短回転オイラー角 (XYZ順、度数法) を計算します。
    """
    def cross(a, b):
        return [a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0]]

    def dot(a, b):
        return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

    def norm(a):
        l = math.sqrt(dot(a, a))
        if l < 1e-9:
            return [0.0, 0.0, 0.0]
        return [x/l for x in a]

    u = norm(v_current)
    v = norm(v_target)
    
    d = dot(u, v)
    if d >= 1.0 - 1e-7:
        return [0.0, 0.0, 0.0]
    if d <= -1.0 + 1e-7:
        return [0.0, 0.0, 180.0]

    c = cross(u, v)
    s = math.sqrt(2.0 * (1.0 + d))
    q = [s * 0.5, c[0] / s, c[1] / s, c[2] / s]

    w, x, y, z = q
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    rx = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    if abs(sinp) >= 1.0:
        ry = math.copysign(math.pi / 2.0, sinp)
    else:
        ry = math.asin(sinp)

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    rz = math.atan2(siny_cosp, cosy_cosp)

    return [math.degrees(rx), math.degrees(ry), math.degrees(rz)]

def setup_leg_stance_and_angles(dic_chue):
    """
    HumanIK ソルバーが自然な屈曲方向（膝が後ろへ曲がる）を正しく認識できるよう、
    脚部ジョイント（膝・足首）に優先屈曲角度 (preferredAngle) および自然なプレベンド（微小屈曲）を設定します。
    """
    for knee_id in [3, 6]:
        knee_j = dic_chue.get(knee_id)
        if knee_j and mc.objExists(knee_j):
            try:
                # 優先屈曲角度を設定（X軸屈曲ヒント: マイナス方向）
                mc.setAttr(f"{knee_j}.preferredAngleX", -10.0)
                mc.setAttr(f"{knee_j}.preferredAngleY", 0.0)
                mc.setAttr(f"{knee_j}.preferredAngleZ", 0.0)

                # 微小なプレベンド（-0.2度）を適用してHumanIKソルバーの逆関節誤認を確実に防止
                mc.setAttr(f"{knee_j}.rx", -0.2)
            except Exception as e:
                print(f"[HumanIK] 膝ジョイントのプレベンド設定スキップ: {e}")

def kangkhaen(dic_chue):
    """
    MMDモデルの腕（Aポーズ）を数学的に正確な水平Tポーズへ展開します。
    """
    # 必須ボーンの取得
    la = dic_chue.get(9)   # 左腕
    le = dic_chue.get(10)  # 左ひじ
    lh = dic_chue.get(11)  # 左手首
    ra = dic_chue.get(12)  # 右腕
    re = dic_chue.get(13)  # 右ひじ
    rh = dic_chue.get(14)  # 右手首

    if not (la and ra and mc.objExists(la) and mc.objExists(ra)):
        print("[HumanIK] 腕ジョイントが存在しないため、Tポーズ展開をスキップします。")
        return False

    # 全ジョイントの回転を安全に初期化 (初期Aポーズ基準)
    for kho in dic_chue.values():
        if mc.objExists(kho):
            try:
                mc.setAttr(kho + '.r', 0, 0, 0)
            except Exception:
                pass

    # 脚部の自然な屈曲角度・プレベンドを初期化
    setup_leg_stance_and_angles(dic_chue)

    try:
        # 左上腕の水平化 (肩 -> 肘、または 肩 -> 手首)
        left_target_child = le if (le and mc.objExists(le)) else lh
        if left_target_child and mc.objExists(left_target_child):
            p_la = mc.xform(la, query=True, translation=True, worldSpace=True)
            p_lt = mc.xform(left_target_child, query=True, translation=True, worldSpace=True)
            vl = [p_lt[0] - p_la[0], p_lt[1] - p_la[1], p_lt[2] - p_la[2]]
            el = calculate_aim_euler_angles(vl, [1.0, 0.0, 0.0])
            mc.setAttr(f"{la}.rx", el[0])
            mc.setAttr(f"{la}.ry", el[1])
            mc.setAttr(f"{la}.rz", el[2])

        # 右上腕の水平化 (肩 -> 肘、または 肩 -> 手首)
        right_target_child = re if (re and mc.objExists(re)) else rh
        if right_target_child and mc.objExists(right_target_child):
            p_ra = mc.xform(ra, query=True, translation=True, worldSpace=True)
            p_rt = mc.xform(right_target_child, query=True, translation=True, worldSpace=True)
            vr = [p_rt[0] - p_ra[0], p_rt[1] - p_ra[1], p_rt[2] - p_ra[2]]
            er = calculate_aim_euler_angles(vr, [-1.0, 0.0, 0.0])
            mc.setAttr(f"{ra}.rx", er[0])
            mc.setAttr(f"{ra}.ry", er[1])
            mc.setAttr(f"{ra}.rz", er[2])

        # 前腕（肘）の水平化補正 (肘 -> 手首)
        if le and lh and mc.objExists(le) and mc.objExists(lh):
            p_le = mc.xform(le, query=True, translation=True, worldSpace=True)
            p_lh = mc.xform(lh, query=True, translation=True, worldSpace=True)
            v_forearm_l = [p_lh[0] - p_le[0], p_lh[1] - p_le[1], p_lh[2] - p_le[2]]
            el_forearm = calculate_aim_euler_angles(v_forearm_l, [1.0, 0.0, 0.0])
            mc.setAttr(f"{le}.rx", el_forearm[0])
            mc.setAttr(f"{le}.ry", el_forearm[1])
            mc.setAttr(f"{le}.rz", el_forearm[2])

        if re and rh and mc.objExists(re) and mc.objExists(rh):
            p_re = mc.xform(re, query=True, translation=True, worldSpace=True)
            p_rh = mc.xform(rh, query=True, translation=True, worldSpace=True)
            v_forearm_r = [p_rh[0] - p_re[0], p_rh[1] - p_re[1], p_rh[2] - p_re[2]]
            er_forearm = calculate_aim_euler_angles(v_forearm_r, [-1.0, 0.0, 0.0])
            mc.setAttr(f"{re}.rx", er_forearm[0])
            mc.setAttr(f"{re}.ry", er_forearm[1])
            mc.setAttr(f"{re}.rz", er_forearm[2])

        print(f"[HumanIK] Tポーズ展開完了: 左腕={el}, 右腕={er}")
        return True
    except Exception as e:
        print(f"[HumanIK] 腕のTポーズ展開中に例外が発生しました: {e}")
        return False
