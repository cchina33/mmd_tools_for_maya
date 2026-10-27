# -*- coding: utf-8 -*-
"""
vmdpaimaya - MMD モーション (VMD) Maya インポートエンジン

モデルインポート時に保存されたボーン構造・モーフ構造（日本語名 <-> Mayaノード名）を
直接活用し、VMDヘッダーのモデル名に縛られず現在シーン内のモデルに強制適用します。
"""

import os
import math
import time
import json
import re
import unicodedata

try:
    from .. import mmd_core
    from ..asset.jaka import safe_node_name
    from ..asset.bone_dict import get_english_bone_name, get_japanese_bone_name
except Exception:
    import mmd_core
    from asset.jaka import safe_node_name
    from asset.bone_dict import get_english_bone_name, get_japanese_bone_name
import maya.cmds as mc
import maya.api.OpenMaya as om

# ボーン名エイリアス（同義語・表記揺れ）マッピングテーブル
BONE_ALIASES = {
    # IK系 (全角・半角・親)
    "左足ＩＫ": ["左足IK", "左足ik", "左足IK親", "左足_IK"],
    "右足ＩＫ": ["右足IK", "右足ik", "右足IK親", "右足_IK"],
    "左つま先ＩＫ": ["左つま先IK", "左つま先ik", "左足先EX"],
    "右つま先ＩＫ": ["右つま先IK", "右つま先ik", "右足先EX"],

    # 体幹・腰系 (準標準ボーン)
    "グルーブ": ["グルーブ", "センター2", "腰"],
    "腰": ["腰", "下半身"],
    "全ての親": ["全ての親", "すべての親", "親", "操作中心"],
    "上半身2": ["上半身2", "上半身２", "胸親"],

    # 足D系 (FK補助ボーンから通常FKボーンへのフォールバック)
    "左足D": ["左足"],
    "左ひざD": ["左ひざ"],
    "左足首D": ["左足首"],
    "右足D": ["右足"],
    "右ひざD": ["右ひざ"],
    "右足首D": ["右足首"],
}

def _match_bone_to_joint(bone_name, joint_map):
    """
    VMDボーン名をモデルのjoint_map（日本語名辞書）に対して正規化・エイリアスを用いてマッチングします。
    """
    if not bone_name or not joint_map:
        return None

    # 一致
    if bone_name in joint_map:
        return joint_map[bone_name]

    # 全角・半角正規化一致 (NFKC)
    norm_vmd = unicodedata.normalize('NFKC', bone_name).strip()
    norm_map = {unicodedata.normalize('NFKC', k).strip(): v for k, v in joint_map.items()}
    if norm_vmd in norm_map:
        return norm_map[norm_vmd]

    # 英語ボーン名から日本語ボーン名への変換照合 (VMDが英語名の場合)
    jp_from_en = get_japanese_bone_name(bone_name)
    if jp_from_en:
        if jp_from_en in joint_map:
            return joint_map[jp_from_en]
        jp_norm = unicodedata.normalize('NFKC', jp_from_en).strip()
        if jp_norm in norm_map:
            return norm_map[jp_norm]

    # 日本語ボーン名から英語ボーン名への変換照合 (joint_mapが英語名の場合)
    en_from_jp = get_english_bone_name(bone_name)
    if en_from_jp:
        if en_from_jp in joint_map:
            return joint_map[en_from_jp]
        en_norm = unicodedata.normalize('NFKC', en_from_jp).strip()
        if en_norm in norm_map:
            return norm_map[en_norm]

    # エイリアス辞書からの探索
    candidates = BONE_ALIASES.get(bone_name, []) or BONE_ALIASES.get(norm_vmd, [])
    for c in candidates:
        if c in joint_map:
            return joint_map[c]
        c_norm = unicodedata.normalize('NFKC', c).strip()
        if c_norm in norm_map:
            return norm_map[c_norm]

    # 逆方向探索: joint_map 側のボーンのエイリアスに bone_name が含まれているか
    for j_bone, aliases in BONE_ALIASES.items():
        aliases_norm = [unicodedata.normalize('NFKC', a).strip() for a in aliases]
        if bone_name in aliases or norm_vmd in aliases_norm:
            if j_bone in joint_map:
                return joint_map[j_bone]
            j_norm = unicodedata.normalize('NFKC', j_bone).strip()
            if j_norm in norm_map:
                return norm_map[j_norm]

    # 準標準ボーンのフォールバック (グルーブ -> センター, 腰 -> 下半身)
    if "グルーブ" in norm_vmd and "センター" in joint_map:
        return joint_map["センター"]
    if norm_vmd == "腰" and "下半身" in joint_map:
        return joint_map["下半身"]
    if "足IK親" in norm_vmd:
        base_ik = norm_vmd.replace("親", "")
        for ik_cand in [base_ik, base_ik.replace("IK", "ＩＫ")]:
            if ik_cand in joint_map:
                return joint_map[ik_cand]

    return None

def get_available_mmd_models():
    """シーン内の利用可能なMMDモデル一覧を取得します。戻り値: [(ノード名, 表示名), ...]"""
    models = []
    candidates = mc.ls('*.mmdModelRoot', objectsOnly=True) or []
    if not candidates:
        for node in mc.ls(type='transform') or []:
            if mc.attributeQuery('MMD_model', node=node, exists=True):
                candidates.append(node)

    # 重複ノードの排除
    unique_candidates = []
    for c in candidates:
        if c not in unique_candidates and mc.objExists(c):
            unique_candidates.append(c)

    # 親グループ（統合グループ *_grp や isMmdGroup 属性持ち）の除外
    valid_roots = []
    for r in unique_candidates:
        # 統合グループ属性 (isMmdGroup) を持つノードは除外
        if mc.attributeQuery('isMmdGroup', node=r, exists=True):
            continue

        # 配下に別の候補ノード（モデル実体）が含まれている親グループは除外
        descendants = mc.listRelatives(r, allDescendents=True, fullPath=False) or []
        has_child_candidate = any(d in unique_candidates for d in descendants)
        if has_child_candidate:
            continue

        valid_roots.append(r)

    # 表示名とタプル一覧の構築
    seen_nodes = set()
    for r in valid_roots:
        if r in seen_nodes:
            continue
        seen_nodes.add(r)
        orig = mc.getAttr(f"{r}.originalName") if mc.attributeQuery('originalName', node=r, exists=True) else r
        models.append((r, f"{r} ({orig})"))

    return models

def _find_scene_joints(target_root=None):
    """シーン内のジョイントを探索し、MMDボーン名からジョイントノード名へのフォールバック辞書を構築します。"""
    joint_map = {}
    if target_root and mc.objExists(target_root):
        joints = mc.listRelatives(target_root, allDescendents=True, type='joint') or []
        if mc.nodeType(target_root) == 'joint':
            joints.append(target_root)
    else:
        joints = mc.ls(type='joint') or []

    for j in joints:
        if mc.attributeQuery('originalName', node=j, exists=True):
            orig_name = mc.getAttr(f"{j}.originalName")
            if orig_name:
                joint_map[orig_name] = j

        short_name = j.split('|')[-1].split(':')[-1]
        if short_name not in joint_map:
            joint_map[short_name] = j

    return joint_map

def _find_blendshape_targets(target_root=None):
    """シーン内のBlendShapeノードとモーフターゲットの対応関係を探索します。"""
    target_map = {}
    bs_nodes = mc.ls(type='blendShape') or []

    for bs in bs_nodes:
        aliases = mc.listAttr(f"{bs}.w", multi=True) or []
        for alias in aliases:
            target_map[alias] = (bs, alias)

    return target_map

def _normalize_bone_map(raw_bones):
    """
    新スキーマ2.0 (配列形式) および旧スキーマ (辞書形式) の両方から、
    ボーン名 -> Mayaノードパスの照合辞書を安全に復元します。
    """
    if isinstance(raw_bones, dict):
        return raw_bones
    if isinstance(raw_bones, list):
        mapping = {}
        for b in raw_bones:
            if isinstance(b, dict):
                node = b.get('maya_node') or b.get('node')
                if node:
                    if b.get('name_jp'):
                        mapping[b['name_jp']] = node
                    if b.get('name_en') and b['name_en'] not in mapping:
                        mapping[b['name_en']] = node
        return mapping
    return {}

def _normalize_morph_map(raw_morphs):
    """
    新スキーマ2.0 (配列形式) および旧スキーマ (辞書形式) の両方から、
    モーフ名 -> Mayaターゲット情報辞書を安全に復元します。
    """
    if isinstance(raw_morphs, dict):
        return raw_morphs
    if isinstance(raw_morphs, list):
        mapping = {}
        for m in raw_morphs:
            if isinstance(m, dict):
                target = m.get('maya_target')
                if target:
                    if m.get('name_jp'):
                        mapping[m['name_jp']] = target
                    if m.get('name_en') and m['name_en'] not in mapping:
                        mapping[m['name_en']] = target
        return mapping
    return {}

def resolve_model_structure(target_model_node=None):
    """
    対象モデルのボーン構造マップおよびモーフ構造マップを取得します。
    モデルに埋め込まれたメタデータ属性（mmdModelStructure優先）、または直近インポート時の構造キャッシュを優先します。
    新スキーマ2.0（配列形式）と旧スキーマ（辞書形式）の両方に対応します。
    """
    bone_map = {}
    morph_map = {}
    resolved_model = None

    # target_model_node の自動検出（未指定の場合）
    if not target_model_node or not mc.objExists(target_model_node):
        sel = mc.ls(selection=True)
        if sel:
            for s in sel:
                if mc.attributeQuery('mmdModelStructure', node=s, exists=True) or mc.attributeQuery('mmdBoneStructure', node=s, exists=True):
                    target_model_node = s
                    break
        if not target_model_node:
            roots = mc.ls('*.mmdModelRoot', objectsOnly=True)
            if roots:
                target_model_node = roots[-1] # 最新のインポートモデル

    # モデルノードのアトリビュートから構造復元 (mmdModelStructure 優先)
    if target_model_node and mc.objExists(target_model_node):
        resolved_model = target_model_node
        if mc.attributeQuery('mmdModelStructure', node=target_model_node, exists=True):
            try:
                raw_json = mc.getAttr(f"{target_model_node}.mmdModelStructure")
                if raw_json:
                    sdata = json.loads(raw_json)
                    bone_map = _normalize_bone_map(sdata.get('bones'))
                    morph_map = _normalize_morph_map(sdata.get('morphs'))
            except Exception:
                pass

        if not bone_map and mc.attributeQuery('mmdBoneStructure', node=target_model_node, exists=True):
            try:
                raw_json = mc.getAttr(f"{target_model_node}.mmdBoneStructure")
                if raw_json:
                    bone_map = _normalize_bone_map(json.loads(raw_json))
            except Exception:
                pass
        if not morph_map and mc.attributeQuery('mmdMorphStructure', node=target_model_node, exists=True):
            try:
                raw_json = mc.getAttr(f"{target_model_node}.mmdMorphStructure")
                if raw_json:
                    morph_map = _normalize_morph_map(json.loads(raw_json))
            except Exception:
                pass

    # キャッシュファイル (last_imported_structure.json) からの復元
    if not bone_map:
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cache_path = os.path.join(plugin_root, 'asset', 'last_imported_structure.json')
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cdata = json.load(f)
                    bone_map = _normalize_bone_map(cdata.get('bones'))
                    morph_map = _normalize_morph_map(cdata.get('morphs'))
                    if not resolved_model:
                        resolved_model = cdata.get('maya', {}).get('model_node') or cdata.get('model_node')
            except Exception:
                pass

    # フォールバック探索
    if not bone_map:
        bone_map = _find_scene_joints(target_model_node)
    if not morph_map:
        morph_map = _find_blendshape_targets(target_model_node)

    return resolved_model, bone_map, morph_map

def _resolve_full_joint_path(node_candidate, target_model=None):
    """
    ジョイント候補名から、名前重複を回避して一意のフルDAGパスを取得します。
    特殊文字や日本語名によるMaya lsコマンドのパースエラーを防止します。
    """
    if not node_candidate:
        return None

    # すでにフルパス（|で始まる）または直接存在する場合
    try:
        if mc.objExists(node_candidate):
            longs = mc.ls(node_candidate, long=True)
            return longs[0] if longs else node_candidate
    except Exception:
        pass

    # ショートネームからロングネームを解決
    short_name = node_candidate.split('|')[-1].split(':')[-1]
    matches = []
    try:
        if mc.objExists(short_name):
            matches = mc.ls(short_name, long=True, type='joint') or []
    except Exception:
        pass

    if not matches:
        try:
            matches = mc.ls(f"*{short_name}", long=True, type='joint') or []
        except Exception:
            pass

    if matches:
        if len(matches) == 1:
            return matches[0]
        # 複数マッチした場合: target_model 階層下のマッチを優先
        if target_model:
            for m in matches:
                if target_model in m:
                    return m
        return matches[-1]

    return None

def print_vmd_analysis_report(motion, joint_map, target_model=None):
    """
    VMDモーションデータの詳細解析レポートをコンソールに出力します。
    すべてのボーン、キーフレーム数、対応するMayaジョイントのマッピング状況を整形表示します。
    """
    total_bone_keys = sum(len(frames) for frames in motion.bone_frames.values())
    total_morph_keys = sum(len(frames) for frames in motion.morph_frames.values())
    cam_keys = len(motion.camera_frames)
    ik_keys = len(motion.ik_frames)

    print("==================================================")
    print("VMD モーション解析レポート")
    print("==================================================")
    print(f"  モデル名 (VMDヘッダー): {motion.model_name}")
    print(f"  最大フレーム数: {motion.max_frame} フレーム ({motion.max_frame / 30.0:.2f} 秒 @ 30fps)")
    print(f"  ボーン総数: {len(motion.bone_frames)} 本 (総キーフレーム数: {total_bone_keys})")
    print(f"  モーフ総数: {len(motion.morph_frames)} 種 (総キーフレーム数: {total_morph_keys})")
    print(f"  カメラキー数: {cam_keys} キー")
    print(f"  IK制御フレーム数: {ik_keys} フレーム")
    print("--------------------------------------------------")
    print("【全ボーン解析 & モデル対応マッピング一覧】")

    matched_count = 0
    unmatched_count = 0

    # ボーン名をソートして全件出力
    for idx, (b_name, frames) in enumerate(sorted(motion.bone_frames.items())):
        k_count = len(frames)
        candidate = _match_bone_to_joint(b_name, joint_map)

        if candidate:
            matched_count += 1
            resolved_path = _resolve_full_joint_path(candidate, target_model)
            final_path = resolved_path or candidate
            short_j = final_path.split('|')[-1]
            print(f"  [{idx+1:3d}] {b_name:<16s}: {k_count:5d} キー -> {short_j} [マッチ]")
        else:
            unmatched_count += 1
            print(f"  [{idx+1:3d}] {b_name:<16s}: {k_count:5d} キー -> [未対応/モデルなし]")

    print("--------------------------------------------------")
    print(f"  マッピング結果: マッチ={matched_count}本, 未対応={unmatched_count}本")

    # 特筆すべき重要ボーン（足・体幹・IK）のサマリー確認
    important_bones = ["全ての親", "センター", "グルーブ", "下半身", "上半身", "左足", "右足", "左ひざ", "右ひざ", "左足首", "右足首", "左足ＩＫ", "右足ＩＫ"]
    found_important = []
    for ib in important_bones:
        if ib in motion.bone_frames:
            found_important.append(f"{ib}({len(motion.bone_frames[ib])}キー)")
    if found_important:
        print(f"  主要ボーン検出: {', '.join(found_important)}")

    if "左足" in motion.bone_frames or "右足" in motion.bone_frames:
        print("  [重要] 「左足」「右足」のキーフレームを検出しました。モデルの対応ボーンへ確実に書き込みます。")

    print("==================================================")


def apply_ik_motion(motion, target_model=None):
    """
    VMDのIK制御フレーム（VmdShowIkFrame）をMayaの足IKおよびつま先IKハンドルの ikBlend にキーフレーム設定します。
    """
    if not motion.ik_frames:
        return

    # シーン内の足IKおよびつま先IKハンドルを探索
    ik_handles = {}
    for side_jp, side_en in [("左", "L"), ("右", "R")]:
        h_pattern = f"*ikHandle_leg_{side_en}*"
        matches = mc.ls(h_pattern, type='ikHandle') or []
        if matches:
            ik_handles[f"{side_jp}足ＩＫ"] = matches[0]
            ik_handles[f"{side_jp}足IK"] = matches[0]

        toe_pattern = f"*ikHandle_toe_{side_en}*"
        toe_matches = mc.ls(toe_pattern, type='ikHandle') or []
        if toe_matches:
            ik_handles[f"{side_jp}つま先ＩＫ"] = toe_matches[0]
            ik_handles[f"{side_jp}つま先IK"] = toe_matches[0]

    if not ik_handles:
        return

    applied_ik_keys = 0
    for ik_frame in motion.ik_frames:
        f = ik_frame.frame
        for ik_info in ik_frame.ik_list:
            ik_name = ik_info.name
            enabled = ik_info.enabled
            blend_val = 1.0 if enabled else 0.0

            if ik_name in ik_handles:
                h_node = ik_handles[ik_name]
                try:
                    mc.setKeyframe(h_node, attribute='ikBlend', time=f, value=blend_val)
                    applied_ik_keys += 1
                except Exception:
                    pass

    if applied_ik_keys > 0:
        print(f"  - IK制御キーフレームをIKハンドル群に設定しました ({applied_ik_keys} キー)")


def apply_leg_knee_orientation(motion, joint_map, target_model=None, scale=8.0):
    """
    大腿のVMD回転キーおよび足IK・センターの変位に基づき、
    膝の曲がり方向と外開き方向へポールベクターロケータの位置軌道を幾何学的に算出し、
    キーフレームを設定します。
    これにより、足IKの極端な移動やしゃがみ動作時にも膝が反転せず、自然な外開き姿勢を維持します。
    """
    if not motion.bone_frames:
        return 0

    applied_keys = 0

    for side_jp, side_en in [("左", "L"), ("右", "R")]:
        pv_name = f"poleVector_leg_{side_en}_{target_model}" if target_model else f"poleVector_leg_{side_en}"
        pv_candidates = mc.ls(f"*{pv_name}*", type='transform') or mc.ls(f"*poleVector_leg_{side_en}*", type='transform') or []
        if not pv_candidates:
            continue
        pv_node = pv_candidates[0]

        # 大腿のVMDキーフレームを取得
        leg_bone_name = f"{side_jp}足"
        leg_frames = motion.bone_frames.get(leg_bone_name, [])

        # 足IKやセンターのキーフレームも考慮（ポーズ変化フレームの網羅）
        ik_bone_name = f"{side_jp}足ＩＫ" if f"{side_jp}足ＩＫ" in motion.bone_frames else f"{side_jp}足IK"
        ik_frames = motion.bone_frames.get(ik_bone_name, [])
        center_frames = motion.bone_frames.get("センター", []) or motion.bone_frames.get("全ての親", [])

        # 評価対象フレーム一覧（大腿キー・足IK・センターのキーフレームを包含）
        target_frame_set = set()
        for bf in leg_frames:
            target_frame_set.add(bf.frame)
        for bf in ik_frames:
            target_frame_set.add(bf.frame)
        for bf in center_frames:
            target_frame_set.add(bf.frame)

        if not target_frame_set:
            continue

        sorted_frames = sorted(target_frame_set)

        # フレームマップの構築
        leg_frame_map = {bf.frame: bf for bf in leg_frames}
        ik_frame_map = {bf.frame: bf for bf in ik_frames}

        # 初期Zオフセット（前方基準距離）の取得
        try:
            base_dist = mc.getAttr(f"{pv_node}.translateZ")
            if abs(base_dist) < 1.0:
                base_dist = 25.0
        except Exception:
            base_dist = 25.0

        # 初期Yオフセット（上方基準距離）の取得
        try:
            base_up = mc.getAttr(f"{pv_node}.translateY")
        except Exception:
            base_up = base_dist * 0.5

        # 外開き方向の符号判定（左足・右足に応じた外向き基準）
        lateral_dir = 1.0 if side_en == "L" else -1.0

        # 直前の状態保持（キーが存在しないフレームでの補間用）
        curr_rot = om.MQuaternion()
        last_ik_pos = [0.0, 0.0, 0.0]

        frame_list = []

        for f in sorted_frames:
            has_leg_key = f in leg_frame_map
            if has_leg_key:
                bf = leg_frame_map[f]
                qx, qy, qz, qw = bf.rotation
                curr_rot = om.MQuaternion(-qx, -qy, qz, qw)

            if f in ik_frame_map:
                last_ik_pos = ik_frame_map[f].position

            # 前方単位ベクトルに大腿回転を適用
            fwd_vec = om.MVector(0.0, 0.0, 1.0)
            rot_vec = curr_rot.rotate(fwd_vec)

            # 足IKの移動量（VMDローカル座標系）による追従補正
            ik_px, ik_py, ik_pz = last_ik_pos
            ik_fwd = ik_pz * scale
            ik_up = ik_py * scale
            ik_side = ik_px * scale

            if has_leg_key:
                # 大腿回転キーが存在する場合の回転ベース計算
                vx = rot_vec.x
                vy = rot_vec.y
                vz = rot_vec.z

                # 外開きオフセット（大腿の横開きに追従）
                lateral_offset = vx * base_dist * 0.85
                if abs(lateral_offset) < base_dist * 0.15:
                    lateral_offset = lateral_dir * base_dist * 0.2

                # 前方距離（足上げ・前屈時のフリップ防止）
                forward_offset = max(base_dist * 0.8, vz * base_dist)
                vertical_offset = vy * base_dist * 0.5
            else:
                # 大腿キーがなく足IK主導で動作している場合の幾何学的追従
                # 足首が前・上に移動した分、ポールベクターも連動して前方・上方に押し出す
                forward_offset = max(base_dist * 0.85, base_dist + ik_fwd * 0.6)
                vertical_offset = base_up + max(0.0, ik_up * 0.5)

                # 股関節の自然な外開きを維持し、内股反転を防止
                lateral_spread = lateral_dir * max(0.0, ik_up * 0.3)
                lateral_offset = (lateral_dir * base_dist * 0.25) + lateral_spread + (ik_side * 0.2)

            mc.setKeyframe(pv_node, attribute='translateX', time=f, value=lateral_offset)
            mc.setKeyframe(pv_node, attribute='translateY', time=f, value=vertical_offset)
            mc.setKeyframe(pv_node, attribute='translateZ', time=f, value=forward_offset)

            frame_list.append(f)
            applied_keys += 1

        # カーブの滑らかなスプライン補間設定
        if len(frame_list) >= 2:
            try:
                mc.keyTangent(pv_node, attribute='translate', edit=True, inTangentType='spline', outTangentType='spline')
            except Exception:
                pass

    if applied_keys > 0:
        print(f"  - 膝の向き・外開きポールベクターキーフレームを設定しました ({applied_keys} キー)")
    return applied_keys


def extract_vmd_bone_bezier_points(interpolation_bytes, channel_idx):
    """
    VMDボーンキーフレームの64バイト補間データから制御点 (x1, y1, x2, y2) を抽出します。
    channel_idx: 0=X移動, 1=Y移動, 2=Z移動, 3=回転
    """
    if not interpolation_bytes or len(interpolation_bytes) < 16:
        return 20.0 / 127.0, 20.0 / 127.0, 107.0 / 127.0, 107.0 / 127.0
    c = channel_idx
    x1 = float(interpolation_bytes[c]) / 127.0
    y1 = float(interpolation_bytes[4 + c]) / 127.0
    x2 = float(interpolation_bytes[8 + c]) / 127.0
    y2 = float(interpolation_bytes[12 + c]) / 127.0
    return x1, y1, x2, y2


def extract_vmd_camera_bezier_points(interpolation_bytes, channel_idx):
    """
    VMDカメラキーフレームの24バイト補間データから制御点 (x1, y1, x2, y2) を抽出します。
    channel_idx: 0=X移動, 1=Y移動, 2=Z移動, 3=回転, 4=距離, 5=画角
    """
    if not interpolation_bytes or len(interpolation_bytes) < 24:
        return 20.0 / 127.0, 20.0 / 127.0, 107.0 / 127.0, 107.0 / 127.0
    offset = channel_idx * 4
    x1 = float(interpolation_bytes[offset + 0]) / 127.0
    x2 = float(interpolation_bytes[offset + 1]) / 127.0
    y1 = float(interpolation_bytes[offset + 2]) / 127.0
    y2 = float(interpolation_bytes[offset + 3]) / 127.0
    return x1, y1, x2, y2


def apply_curve_bezier_tangents(node, attr, key_frames, key_values, bezier_params_list):
    """
    指定ノード・属性のアニメーションカーブに対して、MMDベジェ補間曲線に基づく重み付き接線を設定します。
    key_frames: キーフレーム番号のリスト
    key_values: キーフレームの値のリスト
    bezier_params_list: 各キーフレームの (x1, y1, x2, y2) のリスト
    """
    if len(key_frames) < 2:
        return

    attr_plug = f"{node}.{attr}"
    try:
        mc.keyTangent(attr_plug, edit=True, weightedTangents=True)
    except Exception:
        pass

    num_keys = len(key_frames)
    for i in range(num_keys - 1):
        f0 = key_frames[i]
        f1 = key_frames[i + 1]
        dt = float(f1 - f0)
        if dt <= 0:
            continue

        v0 = key_values[i]
        v1 = key_values[i + 1]
        dv = float(v1 - v0)

        # MMD仕様: 遷移 k0 -> k1 の補間パラメータは k1 に格納されている
        x1, y1, x2, y2 = bezier_params_list[i + 1]

        # 出接線ベクトル (k0 側)
        dx_out = max(1e-4, x1 * dt)
        dv_out = y1 * dv
        out_angle = math.degrees(math.atan2(dv_out, dx_out))
        out_weight = math.sqrt(dx_out * dx_out + dv_out * dv_out) / 3.0

        # 入接線ベクトル (k1 側)
        dx_in = max(1e-4, (1.0 - x2) * dt)
        dv_in = (1.0 - y2) * dv
        in_angle = math.degrees(math.atan2(dv_in, dx_in))
        in_weight = math.sqrt(dx_in * dx_in + dv_in * dv_in) / 3.0

        # k0 の出接線
        try:
            mc.keyTangent(
                attr_plug, edit=True, time=(f0, f0),
                lock=False, outTangentType='fixed',
                outAngle=out_angle, outWeight=max(1e-4, out_weight)
            )
        except Exception:
            pass

        # k1 の入接線
        try:
            mc.keyTangent(
                attr_plug, edit=True, time=(f1, f1),
                lock=False, inTangentType='fixed',
                inAngle=in_angle, inWeight=max(1e-4, in_weight)
            )
        except Exception:
            pass


def apply_bone_motion(motion, joint_map, scale=8.0, target_model=None, progress_callback=None):
    """
    VMDボーンモーションをMayaのジョイント階層にキーフレーム設定します。
    すべてのキーフレームをモデル対応するボーンへ漏れなく書き込みます。
    """
    applied_bones = 0
    total_keys = 0
    failed_bones = []

    # 足IKハンドルが未構築の場合は自動構築
    try:
        try:
            from .pmxpaimaya import setup_mmd_ik
        except Exception:
            from pmxpaimaya import setup_mmd_ik
        setup_mmd_ik(target_model, joint_map)
    except Exception as e:
        print(f"  [情報] IK自動構築チェック: {e}")

    # ジョイント固有アトリビュートの事前キャッシュ (jointOrient, rotateAxis, rotateOrder, 初期移動値)
    initial_translates = {}
    joint_rot_props = {}
    valid_joints = {}

    for bone_name, frames in motion.bone_frames.items():
        candidate = _match_bone_to_joint(bone_name, joint_map)
        if candidate:
            resolved_path = _resolve_full_joint_path(candidate, target_model)
            if resolved_path and mc.objExists(resolved_path):
                valid_joints[bone_name] = resolved_path
                try:
                    initial_translates[resolved_path] = mc.getAttr(f"{resolved_path}.translate")[0]
                except Exception:
                    initial_translates[resolved_path] = (0.0, 0.0, 0.0)

                # jointOrient, rotateAxis, rotateOrder を OpenMaya クォータニオンとして取得
                try:
                    jo = mc.getAttr(f"{resolved_path}.jointOrient")[0]
                    jo_e = om.MEulerRotation(math.radians(jo[0]), math.radians(jo[1]), math.radians(jo[2]), om.MEulerRotation.kXYZ)
                    inv_jo_q = jo_e.asQuaternion().inverse()

                    ra = mc.getAttr(f"{resolved_path}.rotateAxis")[0]
                    ra_e = om.MEulerRotation(math.radians(ra[0]), math.radians(ra[1]), math.radians(ra[2]), om.MEulerRotation.kXYZ)
                    inv_ra_q = ra_e.asQuaternion().inverse()

                    ro = mc.getAttr(f"{resolved_path}.rotateOrder")
                    joint_rot_props[resolved_path] = (inv_jo_q, inv_ra_q, ro)
                except Exception:
                    joint_rot_props[resolved_path] = (om.MQuaternion(), om.MQuaternion(), 0)

    # 各ジョイントの直前フレームオイラー角キャッシュ (フリップ防止用)
    prev_joint_eulers = {}

    # 進捗計測用の有効キーフレーム総数を事前集計
    total_expected_keys = sum(len(frames) for b, frames in motion.bone_frames.items() if b in valid_joints)
    last_reported_frame = -1

    for bone_name, frames in motion.bone_frames.items():
        if bone_name not in valid_joints:
            continue

        j_node = valid_joints[bone_name]

        # コンストレイントで駆動されている足首やDボーン等の従属ジョイントは直接キー打ちをスキップして追従連動を保護
        # (足IKハンドルのorientConstraintと直接キー打ちが競合して足首が180度反転ねじれを起こす現象を確実に防止)
        if any(k in bone_name for k in ["足首", "足D", "ひざD", "足首D"]):
            try:
                if mc.listConnections(j_node, type="orientConstraint"):
                    continue
            except Exception:
                pass

        # 腕捩1..3、手捩1..3等の分散補助ボーンはモデル側の付与エクスプレッションによる自動ロール分散を優先
        if re.search(r'(腕捩|手捩)[0-9]', bone_name):
            continue

        # 直列捩り階層モデルにおける二重回転防止
        if bone_name in ["左腕捩", "右腕捩", "左手捩", "右手捩"]:
            side_prefix = "左" if "左" in bone_name else "右" if "右" in bone_name else ""
            parent_bone_key = f"{side_prefix}腕" if "腕捩" in bone_name else f"{side_prefix}ひじ"
            if parent_bone_key in motion.bone_frames:
                children = mc.listRelatives(j_node, children=True, type='joint') or []
                is_serial_parent = any("hiji" in c.lower() or "tekubi" in c.lower() for c in children)
                if is_serial_parent:
                    continue

        # エクスプレッション競合の解除: VMDキーフレームが存在するボーンにエクスプレッションが接続されている場合は切断
        try:
            expr_conns = mc.listConnections(f"{j_node}.rotate", type="expression") or []
            if expr_conns:
                mc.delete(expr_conns)
        except Exception:
            pass

        init_t = initial_translates.get(j_node, (0.0, 0.0, 0.0))
        inv_jo_q, inv_ra_q, ro = joint_rot_props.get(j_node, (om.MQuaternion(), om.MQuaternion(), 0))
        bone_success = False

        rot_keys = []
        rx_vals = []
        ry_vals = []
        rz_vals = []
        rot_beziers = []

        trans_keys = []
        tx_vals = []
        ty_vals = []
        tz_vals = []
        trans_x_beziers = []
        trans_y_beziers = []
        trans_z_beziers = []

        for bf in frames:
            f = bf.frame
            try:
                # クォータニオン回転の変換 (MMD左手系 -> Maya右手系, Z軸反転)
                qx, qy, qz, qw = bf.rotation
                q_maya = om.MQuaternion(-qx, -qy, qz, qw)

                # jointOrient および rotateAxis を数学的に相殺した純粋なローカル回転
                # 姿勢 = jointOrient * rotate * rotateAxis => rotate = inv(jointOrient) * 姿勢 * inv(rotateAxis)
                local_rot_q = inv_jo_q * q_maya * inv_ra_q

                # ジョイントの rotateOrder を適用してオイラー角へ変換
                euler = local_rot_q.asEulerRotation()
                euler.reorderIt(ro)

                # 前フレームからの最短連続角度を維持 (180度フリップ・裏返りを防止)
                if j_node in prev_joint_eulers:
                    euler = euler.closestSolution(prev_joint_eulers[j_node])
                prev_joint_eulers[j_node] = euler

                rx = math.degrees(euler.x)
                ry = math.degrees(euler.y)
                rz = math.degrees(euler.z)

                mc.setKeyframe(j_node, attribute='rotateX', time=f, value=rx)
                mc.setKeyframe(j_node, attribute='rotateY', time=f, value=ry)
                mc.setKeyframe(j_node, attribute='rotateZ', time=f, value=rz)

                rot_keys.append(f)
                rx_vals.append(rx)
                ry_vals.append(ry)
                rz_vals.append(rz)
                rot_beziers.append(extract_vmd_bone_bezier_points(bf.interpolation, 3))

                # 移動オフセットの適用（IK・ルート・センター等の移動可能ボーン、または有意な移動値がある場合）
                px, py, pz = bf.position
                has_pos_val = (abs(px) > 1e-4 or abs(py) > 1e-4 or abs(pz) > 1e-4)
                # 回転専用ボーン（髪・スカート・紐・手足等）への意図しない平行移動の書き込みを防止
                is_rotation_only_part = any(k in bone_name for k in ["スカート", "髪", "コード", "紐", "リボン", "ネクタイ", "胸", "指", "腕", "ひじ", "手首", "ひざ", "足首", "目", "頭", "首"])
                is_movable_bone = (
                    any(keyword in bone_name for keyword in ["ＩＫ", "IK", "親", "センター", "グルーブ", "全ての親", "下半身", "腰", "足先EX"])
                    or (has_pos_val and not is_rotation_only_part)
                )
                if is_movable_bone:
                    tx = init_t[0] + px * scale
                    ty = init_t[1] + py * scale
                    tz = init_t[2] - pz * scale
                    mc.setKeyframe(j_node, attribute='translateX', time=f, value=tx)
                    mc.setKeyframe(j_node, attribute='translateY', time=f, value=ty)
                    mc.setKeyframe(j_node, attribute='translateZ', time=f, value=tz)

                    trans_keys.append(f)
                    tx_vals.append(tx)
                    ty_vals.append(ty)
                    tz_vals.append(tz)
                    trans_x_beziers.append(extract_vmd_bone_bezier_points(bf.interpolation, 0))
                    trans_y_beziers.append(extract_vmd_bone_bezier_points(bf.interpolation, 1))
                    trans_z_beziers.append(extract_vmd_bone_bezier_points(bf.interpolation, 2))

                total_keys += 1
                bone_success = True

                # 進捗コールバック通知 (約30キーごと、またはフレーム単位)
                if progress_callback and (total_keys % 30 == 0 or total_keys == total_expected_keys):
                    progress_callback(f, motion.max_frame, total_keys, max(1, total_expected_keys))
            except Exception:
                pass

        # 回転カーブへのMMDベジェ接線適用
        if len(rot_keys) >= 2:
            apply_curve_bezier_tangents(j_node, 'rotateX', rot_keys, rx_vals, rot_beziers)
            apply_curve_bezier_tangents(j_node, 'rotateY', rot_keys, ry_vals, rot_beziers)
            apply_curve_bezier_tangents(j_node, 'rotateZ', rot_keys, rz_vals, rot_beziers)
        else:
            try:
                mc.keyTangent(j_node, attribute='rotate', edit=True, inTangentType='spline', outTangentType='spline')
            except Exception:
                pass

        # 大腿ボーンの回転カーブをFKガイド（fkGuide_leg_*）へ接続し、膝の向き・ポールベクターを忠実追従
        if bone_name in ("左足", "右足"):
            side_en = "L" if bone_name.startswith("左") else "R"
            g_name = f"fkGuide_leg_{side_en}_{target_model}" if target_model else f"fkGuide_leg_{side_en}"
            g_candidates = mc.ls(f"*{g_name}*", type='transform') or mc.ls(f"*fkGuide_leg_{side_en}*", type='transform') or []
            if g_candidates:
                target_g = g_candidates[0]
                for ax in "XYZ":
                    crv = mc.listConnections(f"{j_node}.rotate{ax}", source=True, destination=False, type='animCurve') or []
                    if crv:
                        try:
                            mc.connectAttr(f"{crv[0]}.output", f"{target_g}.rotate{ax}", force=True)
                        except Exception:
                            pass

        # 移動カーブへのMMDベジェ接線適用
        if len(trans_keys) >= 2:
            apply_curve_bezier_tangents(j_node, 'translateX', trans_keys, tx_vals, trans_x_beziers)
            apply_curve_bezier_tangents(j_node, 'translateY', trans_keys, ty_vals, trans_y_beziers)
            apply_curve_bezier_tangents(j_node, 'translateZ', trans_keys, tz_vals, trans_z_beziers)
        elif trans_keys:
            try:
                mc.keyTangent(j_node, attribute='translate', edit=True, inTangentType='spline', outTangentType='spline')
            except Exception:
                pass

        if bone_success:
            applied_bones += 1
        else:
            failed_bones.append(bone_name)

    # VMD内のIK制御情報をMaya足IKハンドルへ適用
    try:
        apply_ik_motion(motion, target_model)
    except Exception as e:
        print(f"  [情報] IKモーション適用: {e}")

    if failed_bones:
        print(f"  [情報] スキップされたボーン: {len(failed_bones)}本")

    return applied_bones, total_keys

def apply_morph_motion(motion, morph_map, target_model_node=None):
    """
    VMDモーフ（表情）モーションをBlendShapeノードにキーフレーム設定します。
    """
    applied_morphs = 0
    total_keys = 0

    # シーン内のBlendShapeノード一覧
    bs_nodes = mc.ls(type='blendShape') or []

    for morph_name, frames in motion.morph_frames.items():
        target_info = None

        # 構造マップからターゲット属性名を取得
        if morph_name in morph_map:
            target_info = morph_map[morph_name]
        else:
            safe_name = safe_node_name(morph_name, prefix="")
            if safe_name in morph_map:
                target_info = morph_map[safe_name]

        if not target_info:
            continue

        # target_info が (bs_node, attr) または 単なる attr 名の場合の解決
        if isinstance(target_info, (list, tuple)):
            bs_node, attr_name = target_info
        else:
            attr_name = target_info
            bs_node = None
            for bs in bs_nodes:
                if mc.attributeQuery(attr_name, node=bs, exists=True):
                    bs_node = bs
                    break

        if not bs_node or not mc.objExists(bs_node):
            continue

        applied_morphs += 1
        for mf in frames:
            f = mf.frame
            w = max(0.0, min(1.0, mf.weight))
            mc.setKeyframe(f"{bs_node}.{attr_name}", time=f, value=w)
            total_keys += 1

        try:
            mc.keyTangent(f"{bs_node}.{attr_name}", edit=True, inTangentType='spline', outTangentType='spline')
        except Exception:
            pass

    return applied_morphs, total_keys

def apply_camera_motion(motion, scale=8.0):
    """
    VMDカメラモーションからMayaカメラを生成し、アニメーションを設定します。
    注視点ロケータを中心とした公転（オービット）2階層リグを自動構築します。
    """
    if not motion.camera_frames:
        return None

    # 既存のカメラリグがあればクリーンアップして再生成
    for node_name in ["MMD_Camera_Aim", "MMD_Camera"]:
        if mc.objExists(node_name):
            try:
                mc.delete(node_name)
            except Exception:
                pass

    aim_locator = mc.spaceLocator(name="MMD_Camera_Aim")[0]
    cam_trans, cam_shape = mc.camera(name="MMD_Camera")
    cam_trans = mc.parent(cam_trans, aim_locator)[0]

    # カメラのフィルムゲート設定 (35mm換算アスペクト)
    mc.setAttr(f"{cam_shape}.filmFit", 3) # Overscan
    aperture_inch = mc.camera(cam_shape, query=True, verticalFilmAperture=True)
    aperture_mm = aperture_inch * 25.4

    cam_keys = []
    aim_tx = []
    aim_ty = []
    aim_tz = []
    aim_rx = []
    aim_ry = []
    aim_rz = []
    cam_dist_vals = []
    cam_fl_vals = []

    cam_bx = []
    cam_by = []
    cam_bz = []
    cam_brot = []
    cam_bdist = []
    cam_bfov = []

    for cf in motion.camera_frames:
        f = cf.frame

        # 注視点の位置 (MMD左手系 -> Maya右手系, Z反転)
        tx = cf.position[0] * scale
        ty = cf.position[1] * scale
        tz = -cf.position[2] * scale
        mc.setKeyframe(aim_locator, attribute='translateX', time=f, value=tx)
        mc.setKeyframe(aim_locator, attribute='translateY', time=f, value=ty)
        mc.setKeyframe(aim_locator, attribute='translateZ', time=f, value=tz)

        # カメラの公転回転角度
        rx = math.degrees(cf.rotation[0])
        ry = -math.degrees(cf.rotation[1])
        rz = -math.degrees(cf.rotation[2])
        mc.setKeyframe(aim_locator, attribute='rotateX', time=f, value=rx)
        mc.setKeyframe(aim_locator, attribute='rotateY', time=f, value=ry)
        mc.setKeyframe(aim_locator, attribute='rotateZ', time=f, value=rz)

        # 注視点からの距離オフセット (MMD distanceは通常負値)
        cam_dist = -cf.distance * scale
        mc.setKeyframe(cam_trans, attribute='translateX', time=f, value=0.0)
        mc.setKeyframe(cam_trans, attribute='translateY', time=f, value=0.0)
        mc.setKeyframe(cam_trans, attribute='translateZ', time=f, value=cam_dist)
        mc.setKeyframe(cam_trans, attribute='rotateX', time=f, value=0.0)
        mc.setKeyframe(cam_trans, attribute='rotateY', time=f, value=0.0)
        mc.setKeyframe(cam_trans, attribute='rotateZ', time=f, value=0.0)

        # 視野角 (FOV) から焦点距離 (focalLength) への変換
        fov_rad = math.radians(cf.fov) if cf.fov > 0 else math.radians(30.0)
        fl = (aperture_mm / 2.0) / math.tan(fov_rad / 2.0)
        mc.setKeyframe(cam_shape, attribute='focalLength', time=f, value=fl)

        cam_keys.append(f)
        aim_tx.append(tx)
        aim_ty.append(ty)
        aim_tz.append(tz)
        aim_rx.append(rx)
        aim_ry.append(ry)
        aim_rz.append(rz)
        cam_dist_vals.append(cam_dist)
        cam_fl_vals.append(fl)

        cam_bx.append(extract_vmd_camera_bezier_points(cf.interpolation, 0))
        cam_by.append(extract_vmd_camera_bezier_points(cf.interpolation, 1))
        cam_bz.append(extract_vmd_camera_bezier_points(cf.interpolation, 2))
        cam_brot.append(extract_vmd_camera_bezier_points(cf.interpolation, 3))
        cam_bdist.append(extract_vmd_camera_bezier_points(cf.interpolation, 4))
        cam_bfov.append(extract_vmd_camera_bezier_points(cf.interpolation, 5))

    # カメラアニメーションカーブへのMMDベジェ接線適用
    if len(cam_keys) >= 2:
        apply_curve_bezier_tangents(aim_locator, 'translateX', cam_keys, aim_tx, cam_bx)
        apply_curve_bezier_tangents(aim_locator, 'translateY', cam_keys, aim_ty, cam_by)
        apply_curve_bezier_tangents(aim_locator, 'translateZ', cam_keys, aim_tz, cam_bz)
        apply_curve_bezier_tangents(aim_locator, 'rotateX', cam_keys, aim_rx, cam_brot)
        apply_curve_bezier_tangents(aim_locator, 'rotateY', cam_keys, aim_ry, cam_brot)
        apply_curve_bezier_tangents(aim_locator, 'rotateZ', cam_keys, aim_rz, cam_brot)
        apply_curve_bezier_tangents(cam_trans, 'translateZ', cam_keys, cam_dist_vals, cam_bdist)
        apply_curve_bezier_tangents(cam_shape, 'focalLength', cam_keys, cam_fl_vals, cam_bfov)
    else:
        for node in [aim_locator, cam_trans, cam_shape]:
            try:
                mc.keyTangent(node, edit=True, inTangentType='spline', outTangentType='spline')
            except Exception:
                pass

    print(f"[情報] カメラアニメーションを適用しました: {len(motion.camera_frames)} フレーム")
    return aim_locator

def clear_model_animation(target_model_node=None, clear_camera=True):
    """
    指定モデル（または検出モデル）のボーンおよびモーフのモーションキーを全削除し、
    初期ポーズへ復元します。剛体・Jointのキーフレームも初期化してボーンへ再吸着させます。
    """
    resolved_model, joint_map, morph_map = resolve_model_structure(target_model_node)
    cleared_bones = 0
    cleared_morphs = 0

    # ボーンのモーションキー削除 (構造マップ登録ボーン + 階層下全ジョイント)
    processed_joints = set()
    for bone_name, candidate in joint_map.items():
        resolved_path = _resolve_full_joint_path(candidate, resolved_model)
        if resolved_path and mc.objExists(resolved_path):
            try:
                mc.cutKey(resolved_path, clear=True)
                cleared_bones += 1
                processed_joints.add(resolved_path)
                short_names = mc.ls(resolved_path, shortNames=True)
                if short_names:
                    processed_joints.add(short_names[0])
            except Exception:
                pass

    # モデル階層下（または未指定時はシーン内全域）のジョイントも漏れなくキー削除
    if resolved_model and mc.objExists(resolved_model):
        hierarchy_joints = mc.listRelatives(resolved_model, allDescendents=True, type='joint', fullPath=True) or []
    else:
        hierarchy_joints = mc.ls(type='joint', long=True) or []

    for j in hierarchy_joints:
        if j not in processed_joints:
            try:
                mc.cutKey(j, clear=True)
                cleared_bones += 1
                processed_joints.add(j)
            except Exception:
                pass

    # 足IKハンドルのモーションキー削除 & 初期化
    ik_handles = mc.ls("*ikHandle_leg_*", type='ikHandle') or []
    for ikh in ik_handles:
        try:
            mc.cutKey(ikh, clear=True)
            if mc.attributeQuery('ikBlend', node=ikh, exists=True):
                mc.setAttr(f"{ikh}.ikBlend", 1.0)
        except Exception:
            pass

    # ポールベクターロケータのキー削除 & 初期オフセット位置へのリセット
    for pv in (mc.ls("*poleVector_leg_*", type='transform') or []):
        try:
            mc.cutKey(pv, clear=True)
            if mc.attributeQuery('translateX', node=pv, exists=True):
                mc.setAttr(f"{pv}.translateX", 0.0)
            if mc.attributeQuery('translateY', node=pv, exists=True):
                mc.setAttr(f"{pv}.translateY", 0.0)
        except Exception:
            pass

    # FKガイドの回転・接続初期化
    for g in (mc.ls("fkGuide_leg_*", type='transform') or mc.ls("*fkGuide_leg_*", type='transform') or []):
        try:
            for ax in "XYZ":
                conns = mc.listConnections(f"{g}.rotate{ax}", source=True, destination=False, plugs=True) or []
                for c_plug in conns:
                    try:
                        mc.disconnectAttr(c_plug, f"{g}.rotate{ax}")
                    except Exception:
                        pass
            mc.setAttr(f"{g}.rotate", 0.0, 0.0, 0.0, type='double3')
        except Exception:
            pass

    # バインドポーズの復元 (Translate, Rotate を含む初期ポーズ復元)
    restored_pose = False
    dag_poses = mc.ls(type="dagPose") or []
    for dp in dag_poses:
        try:
            if mc.attributeQuery("bindPose", node=dp, exists=True) and mc.getAttr(f"{dp}.bindPose"):
                mc.dagPose(dp, restore=True)
                restored_pose = True
        except Exception:
            pass

    # dagPoseで復元されなかった場合の回転初期化
    if not restored_pose:
        for bone_name, candidate in joint_map.items():
            resolved_path = _resolve_full_joint_path(candidate, resolved_model)
            if resolved_path and mc.objExists(resolved_path):
                try:
                    mc.setAttr(f"{resolved_path}.rotate", 0.0, 0.0, 0.0)
                except Exception:
                    pass

    # 剛体およびJointノードのキーフレーム初期化
    vis_groups = mc.ls(
        "*_RigidBody_Joint_Visualizers",
        "*_RigidBody_Visualizers",
        "*_Joint_Visualizers",
        "MMD_RigidBody_Joint_Visualizers",
        "MMD_RigidBody_Visualizers",
        "MMD_Joint_Visualizers",
        "MMD_Bullet_Physics_Rig",
        type="transform"
    ) or []
    for grp in vis_groups:
        if mc.objExists(grp):
            try:
                mc.cutKey(grp, hierarchy='below', clear=True)
            except Exception:
                pass

    # 個別剛体・Jointトランスフォームノードのキーフレーム削除
    phys_nodes = mc.ls(
        "*_rb_*", "*_joint_*",
        "rb_vis_*", "joint_vis_*",
        "bullet_rb_*", "bullet_joint_*",
        transforms=True
    ) or []
    for p_node in phys_nodes:
        try:
            mc.cutKey(p_node, clear=True)
        except Exception:
            pass

    # 剛体・Joint追従コンストレイントの復元 & モデルボーンへの再吸着
    try:
        try:
            from .pmxpaimaya import reconnect_visualizers_to_bones
        except Exception:
            from converters.pmxpaimaya import reconnect_visualizers_to_bones
        reconnect_visualizers_to_bones()
    except Exception as e:
        print(f"  [情報] 剛体・Joint再吸着スキップ: {e}")

    # BlendShapeのキーフレーム削除 & ウェイトリセット (0.0)
    bs_nodes = mc.ls(type='blendShape') or []
    for bs in bs_nodes:
        try:
            mc.cutKey(bs, clear=True)
            weights = mc.blendShape(bs, query=True, weight=True) or []
            for i in range(len(weights)):
                mc.setAttr(f"{bs}.weight[{i}]", 0.0)
            cleared_morphs += 1
        except Exception:
            pass

    # カメラのキーフレーム削除またはノードクリーンアップ
    if clear_camera:
        for cam_name in ["MMD_Camera_Aim", "MMD_Camera"]:
            if mc.objExists(cam_name):
                try:
                    mc.delete(cam_name)
                except Exception:
                    pass

    # カレントフレームを0へ戻し、ビューポート表示を強制同期
    try:
        mc.currentTime(0)
        mc.dgdirty(allPlugs=True)
        mc.refresh(force=True)
    except Exception:
        pass

    print(f"[情報] モーションをクリアしました: ボーン={cleared_bones}, BlendShape={cleared_morphs}, 剛体・Joint復元完了")
    return cleared_bones, cleared_morphs

import wave
import struct
import tempfile

_current_audio_source_path = None
_current_audio_offset = 0

def scale_wav_volume(input_wav_path, output_wav_path, volume_ratio):
    """
    WAVファイルのPCM振幅を volume_ratio (0.0〜1.0) でスケーリングして出力
    """
    with wave.open(input_wav_path, 'rb') as r:
        params = r.getparams()
        nchannels, sampwidth, framerate, nframes = params[:4]
        raw_data = r.readframes(nframes)

    if volume_ratio >= 0.999:
        with wave.open(output_wav_path, 'wb') as w:
            w.setparams(params)
            w.writeframes(raw_data)
        return

    # サンプル幅に応じたPCM振幅のスケーリング
    if sampwidth == 2:
        count = len(raw_data) // 2
        fmt = f"<{count}h"
        samples = struct.unpack(fmt, raw_data)
        scaled = [max(-32768, min(32767, int(s * volume_ratio))) for s in samples]
        out_bytes = struct.pack(fmt, *scaled)
    elif sampwidth == 1:
        samples = list(raw_data)
        scaled = [max(0, min(255, int(128 + (s - 128) * volume_ratio))) for s in samples]
        out_bytes = bytes(scaled)
    elif sampwidth == 4:
        count = len(raw_data) // 4
        fmt = f"<{count}i"
        samples = struct.unpack(fmt, raw_data)
        scaled = [max(-2147483648, min(2147483647, int(s * volume_ratio))) for s in samples]
        out_bytes = struct.pack(fmt, *scaled)
    else:
        out_bytes = raw_data

    with wave.open(output_wav_path, 'wb') as w:
        w.setparams(params)
        w.writeframes(out_bytes)

def set_audio_volume(volume_percent):
    """
    現在の BGM 音声ノードの音量を volume_percent (0〜100) に調節
    """
    global _current_audio_source_path, _current_audio_offset
    audio_nodes = mc.ls("MMD_Audio*", type="audio") or []
    if not audio_nodes:
        return False

    audio_node = audio_nodes[0]
    src_path = _current_audio_source_path
    if not src_path or not os.path.exists(src_path):
        src_path = mc.getAttr(f"{audio_node}.filename")
        if not src_path or not os.path.exists(src_path):
            return False
        _current_audio_source_path = src_path

    vol_ratio = max(0.0, min(1.0, float(volume_percent) / 100.0))
    temp_dir = tempfile.gettempdir()
    scaled_wav = os.path.join(temp_dir, "mmd_temp_scaled_volume.wav")

    try:
        scale_wav_volume(src_path, scaled_wav, vol_ratio)
        mc.setAttr(f"{audio_node}.filename", scaled_wav, type="string")
        return True
    except Exception as e:
        print(f"[警告] 音量調節に失敗しました: {e}")
        return False

def import_audio(wav_file_path, offset=0, volume_percent=100):
    """
    WAVオーディオファイルをMayaにインポートし、タイムスライダーに接続して再生同期を有効化します。
    """
    global _current_audio_source_path, _current_audio_offset
    if not wav_file_path or not os.path.isfile(wav_file_path):
        return None

    _current_audio_source_path = os.path.abspath(wav_file_path)
    _current_audio_offset = offset

    # 既存の MMD_Audio ノードを整理
    for old_audio in mc.ls("MMD_Audio*", type="audio") or []:
        if mc.objExists(old_audio):
            try:
                mc.delete(old_audio)
            except Exception:
                pass

    try:
        # 音量指定がある場合スケーリングしたファイルを作成
        actual_wav = _current_audio_source_path
        if volume_percent < 99.9:
            temp_dir = tempfile.gettempdir()
            scaled_wav = os.path.join(temp_dir, "mmd_temp_scaled_volume.wav")
            scale_wav_volume(_current_audio_source_path, scaled_wav, float(volume_percent) / 100.0)
            actual_wav = scaled_wav

        # sound ノードを作成
        audio_node = mc.sound(file=actual_wav, offset=offset, name="MMD_Audio")

        # タイムスライダー（PlaybackSlider）にアタッチ
        try:
            import maya.mel as mel
            slider = mel.eval('global string $gPlayBackSlider; $tmpVar = $gPlayBackSlider;')
            if slider and mc.timeControl(slider, exists=True):
                mc.timeControl(slider, edit=True, sound=audio_node, displaySound=True)
        except Exception:
            pass

        print(f"[情報] BGM音声をタイムスライダーに読み込みました: {os.path.basename(wav_file_path)} (音量: {volume_percent}%, ノード: {audio_node})")
        return audio_node
    except Exception as e:
        print(f"[警告] 音声ファイルの読み込みに失敗しました: {e}")
        return None

def delete_mmd_scene_elements(target_model_node=None, delete_lights=True, delete_cameras=True, delete_audio=True, delete_unused_nodes=True):
    """
    指定されたMMDモデル（またはシーン内の全MMD要素）、ジョイント、リグ、
    カメラ、ライト、オーディオ、および未使用マテリアルノードを安全に削除します。
    """
    import maya.mel as mel

    deleted_count = 0

    # 削除対象モデルの特定
    models_to_delete = []
    if target_model_node and mc.objExists(target_model_node):
        models_to_delete.append(target_model_node)
    else:
        # シーン内の全MMDモデル
        roots = mc.ls('*.mmdModelRoot', objectsOnly=True) or []
        for r in roots:
            if mc.objExists(r) and r not in models_to_delete:
                models_to_delete.append(r)
        # MMD_model アトリビュートを持つメッシュ
        meshes = mc.ls('*.MMD_model', objectsOnly=True) or []
        for m in meshes:
            if mc.objExists(m) and m not in models_to_delete:
                models_to_delete.append(m)

    # モデル階層および関連ジョイント・IK・BlendShapeの削除
    for m in models_to_delete:
        try:
            # 埋め込みボーン情報からルートジョイントを特定して削除
            if mc.attributeQuery('mmdBoneStructure', node=m, exists=True):
                try:
                    b_json = mc.getAttr(f"{m}.mmdBoneStructure")
                    if b_json:
                        b_dict = json.loads(b_json)
                        for j_path in b_dict.values():
                            if j_path and mc.objExists(j_path):
                                root_parts = j_path.split('|')
                                if len(root_parts) > 1 and root_parts[1]:
                                    root_j = f"|{root_parts[1]}"
                                    if mc.objExists(root_j):
                                        mc.delete(root_j)
                                        deleted_count += 1
                except Exception:
                    pass

            # メッシュおよび親統合グループ (*_grp) の削除
            if mc.objExists(m):
                parents = mc.listRelatives(m, parent=True, fullPath=False) or []
                parent_grp_to_delete = None
                for p in parents:
                    if p.endswith("_grp") or mc.attributeQuery("isMmdGroup", node=p, exists=True):
                        parent_grp_to_delete = p
                        break

                mc.delete(m)
                deleted_count += 1

                if parent_grp_to_delete and mc.objExists(parent_grp_to_delete):
                    try:
                        mc.delete(parent_grp_to_delete)
                        deleted_count += 1
                    except Exception:
                        pass
        except Exception:
            pass

    # シーン内の未接続IKハンドル・ポールベクター・FKガイド・MMDジョイントのクリーンアップ
    for ik_h in (mc.ls('ikHandle_*') or []) + (mc.ls('poleVector_leg_*') or []) + (mc.ls('poleVector_grp_leg_*') or []) + (mc.ls('fkGuide_leg_*') or []):
        if mc.objExists(ik_h):
            try:
                mc.delete(ik_h)
                deleted_count += 1
            except Exception:
                pass

    # 物理可視化ノードおよびBulletリグのクリーンアップ (モデル別・全体両対応)
    phys_candidates = []
    if target_model_node:
        clean_m = re.sub(r'[^a-zA-Z0-9_]', '_', target_model_node)
        phys_candidates.extend(mc.ls(
            f"{target_model_node}_RigidBody_Joint_Visualizers",
            f"{clean_m}_RigidBody_Joint_Visualizers",
            f"*{target_model_node}*_RigidBody_Joint_Visualizers*",
            f"{target_model_node}_Bullet_Physics_Rig",
            f"{target_model_node}_rb_*",
            f"{target_model_node}_joint_*",
            f"*{target_model_node}*_grp",
            f"anchor_*{target_model_node}*",
            type="transform"
        ) or [])
    else:
        phys_candidates.extend(mc.ls(
            "*_RigidBody_Joint_Visualizers",
            "MMD_RigidBody_Joint_Visualizers",
            "*_RigidBody_Visualizers",
            "MMD_RigidBody_Visualizers",
            "*_Joint_Visualizers",
            "MMD_Joint_Visualizers",
            "*_Bullet_Physics_Rig",
            "MMD_Bullet_Physics_Rig",
            "*_BulletSolver",
            "MMD_BulletSolver",
            "*_rb_*",
            "*_joint_*",
            "rb_vis_*",
            "joint_vis_*",
            "anchor_*",
            type="transform"
        ) or [])

    for p_item in phys_candidates:
        if mc.objExists(p_item):
            try:
                mc.delete(p_item)
                deleted_count += 1
            except Exception:
                pass

    # MMDカメラの削除 (指定時のみ実行)
    if delete_cameras:
        for cam in ["MMD_Camera_Aim", "MMD_Camera"]:
            for cam_node in mc.ls(f"*{cam}*", type='transform') or []:
                if mc.objExists(cam_node):
                    try:
                        mc.delete(cam_node)
                        deleted_count += 1
                    except Exception:
                        pass

    # MMDオーディオ (BGM) の削除 (指定時のみ実行)
    if delete_audio:
        # タイムスライダーから音声を解除
        try:
            slider = mel.eval('global string $gPlayBackSlider; $tmpVar = $gPlayBackSlider;')
            if slider and mc.timeControl(slider, exists=True):
                mc.timeControl(slider, edit=True, sound="", displaySound=False)
        except Exception:
            pass

        # シーン内の MMD_Audio ノードを削除
        for a_node in mc.ls("MMD_Audio*", "*MMD_Audio*", type="audio") or []:
            if mc.objExists(a_node):
                try:
                    mc.delete(a_node)
                    deleted_count += 1
                except Exception:
                    pass

    # MMDライトの削除 (指定時のみ実行)
    if delete_lights:
        # mmd_lighting_grp グループおよび関連ノードの探索と削除
        lighting_nodes = mc.ls("mmd_lighting_grp*", "*mmd_lighting_grp*", "MMD_DirectionalLight*", "MMD_AmbientLight*", type="transform") or []
        for lt_node in lighting_nodes:
            if mc.objExists(lt_node):
                try:
                    mc.delete(lt_node)
                    deleted_count += 1
                except Exception:
                    pass

        # シェイプノード直接の探索と安全なクリーンアップ
        for shp_type in ["directionalLight", "ambientLight"]:
            for shp in mc.ls(type=shp_type) or []:
                if any(k in shp for k in ["MMD_DirectionalLight", "MMD_AmbientLight"]):
                    parent_node = mc.listRelatives(shp, parent=True, fullPath=True)
                    target = parent_node[0] if parent_node else shp
                    if mc.objExists(target):
                        try:
                            mc.delete(target)
                            deleted_count += 1
                        except Exception:
                            pass

        # MMD地面影（mmd_ground_shadow_grpおよび関連ノード）の探索と削除
        for shadow_node in ["mmd_ground_shadow_grp", "*mmd_ground_shadow_grp*", "mmd_ground_shadow_plane", "*mmd_ground_shadow_plane*", "mmd_ground_shadow_shd", "mmd_ground_shadow_shdSG"]:
            for s_item in mc.ls(shadow_node) or []:
                if mc.objExists(s_item):
                    try:
                        mc.delete(s_item)
                        deleted_count += 1
                    except Exception:
                        pass

    # HumanIK キャラクタ定義およびコントロールリグのクリーンアップ
    hik_characters = []
    if target_model_node:
        clean_target = re.sub(r'[^a-zA-Z0-9_]', '_', target_model_node)
        hik_characters = mc.ls(f"HIK_{clean_target}*", type="HIKCharacterNode") or []
    else:
        hik_characters = mc.ls("HIK_*", type="HIKCharacterNode") or []

    for char_node in hik_characters:
        if mc.objExists(char_node):
            try:
                mel.eval(f'hikSetCurrentCharacter "{char_node}";')
                mel.eval('hikDeleteControlRig;')
            except Exception:
                pass
            try:
                mel.eval(f'hikDeleteCharacter "{char_node}";')
                deleted_count += 1
            except Exception:
                try:
                    mc.delete(char_node)
                    deleted_count += 1
                except Exception:
                    pass

    # 残存するコントロールリグ・エフェクタノードの安全なフォールバック削除
    hik_remnants = mc.ls("*_Ctrl_*", "*_Reference", "*_CtrlRig*", type="transform") or []
    for r_node in hik_remnants:
        if mc.objExists(r_node) and any(k in r_node for k in ["HIK_", "Ctrl_", "Reference"]):
            try:
                mc.delete(r_node)
                deleted_count += 1
            except Exception:
                pass

    # 未使用マテリアル・テクスチャ・ユーティリティノードの削除 (指定時のみ実行)
    if delete_unused_nodes:
        try:
            mel.eval('MLdeleteUnused;')
        except Exception as e:
            print(f"  [情報] MLdeleteUnused: {e}")

    # 再生位置リセット
    mc.currentTime(0)
    print(f"[完了] MMD関連ノードをクリーンアップしました (削除数: {deleted_count})")
    return deleted_count

def restore_viewport_lighting(force_reset=False, prevent_motion_darkening=True):
    """
    ビューポートの画面再描画を実行し、ユーザー設定のライティングおよびマテリアル表示を保護・維持します。
    ※ force_reset=True が明示的に指定されない限り、ユーザーが意図して設定した
       displayLights やトーンマップ設定、マテリアル発色を勝手に書き換えません。
    """
    if force_reset:
        try:
            try:
                from . import pmxpaimaya
            except Exception:
                try:
                    from converters import pmxpaimaya
                except Exception:
                    import pmxpaimaya

            # 明示的なリセット要求時のみビュー変換および表示設定を適用
            if hasattr(pmxpaimaya, "set_untone_mapped_view_transform"):
                pmxpaimaya.set_untone_mapped_view_transform()

            if hasattr(pmxpaimaya, "setup_viewport_display"):
                pmxpaimaya.setup_viewport_display(shadow_mode=1, prevent_motion_darkening=prevent_motion_darkening)
        except Exception as e:
            print(f"  [警告] ビューポート表示の復元中に軽微な例外: {e}")

    # MMDモデルメッシュの影受け適正化（顔・脚の黒潰れ防止設定を維持）
    try:
        try:
            from . import pmxpaimaya
        except Exception:
            try:
                from converters import pmxpaimaya
            except Exception:
                import pmxpaimaya
        if hasattr(pmxpaimaya, "optimize_model_meshes_for_mmd_lighting"):
            pmxpaimaya.optimize_model_meshes_for_mmd_lighting()
    except Exception:
        pass

    # モーション再生時の暗化防止（シャッター開度0.01によるブレなしHDRポストパス最適化）
    try:
        if mc.objExists('hardwareRenderingGlobals'):
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

    # ビューポートの再描画のみを安全に実行
    try:
        mc.refresh(force=True)
    except Exception:
        pass

def import_vmd(vmd_file_path=None, camera_vmd_path=None, audio_wav_path=None, scale=8.0, target_model_node=None, audio_volume=100, progress_callback=None, prevent_motion_darkening=True):
    """
    VMDファイルをMayaにインポートし、対象モデル、カメラ、およびBGM音声を適用します。
    モデルモーション、カメラモーション、BGM音声の個別・一括指定に対応します。
    """
    start_time = time.time()
    print("==================================================")
    print("VMD モーションインポート開始")
    print("==================================================")

    # インポート開始前のビューポートライティング状態を保護・最適化
    restore_viewport_lighting(prevent_motion_darkening=prevent_motion_darkening)

    # タイムライン開始フレームを0に設定し、フレーム0を基準に初期化
    try:
        mc.playbackOptions(minTime=0, animationStartTime=0)
        mc.currentTime(0)
    except Exception:
        pass

    max_frame = 0
    result = {
        'source_model_name': "",
        'max_frame': 0,
        'bones_applied': 0,
        'morphs_applied': 0,
        'camera_applied': False,
        'audio_applied': False
    }

    try:
        # カメラモーションの読み込み・適用
        cam_file = camera_vmd_path
        if not cam_file and vmd_file_path:
            # モデルファイル側にカメラが含まれているかのチェック用
            pass

        # 明示的なカメラVMDがある場合
        if cam_file and os.path.isfile(cam_file):
            print(f"[カメラ] ファイル読み込み中: {os.path.basename(cam_file)}")
            cam_motion = mmd_core.vmd.load(cam_file)
            if cam_motion.camera_frames:
                apply_camera_motion(cam_motion, scale)
                result['camera_applied'] = True
                max_frame = max(max_frame, cam_motion.max_frame)
                print(f"  - カメラモーションを適用しました ({len(cam_motion.camera_frames)} キー)")

        # キャラクターモーションの読み込み・適用
        if vmd_file_path and os.path.isfile(vmd_file_path):
            print(f"[モデル] ファイル読み込み中: {os.path.basename(vmd_file_path)}")
            motion = mmd_core.vmd.load(vmd_file_path)
            result['source_model_name'] = motion.model_name
            max_frame = max(max_frame, motion.max_frame)

            # 単体カメラモーションだった場合の自動判定
            if motion.is_camera_motion and not result['camera_applied']:
                apply_camera_motion(motion, scale)
                result['camera_applied'] = True
                print(f"  - 単体カメラモーションを検出・適用しました")
            else:
                # 適用対象モデルリストの決定 (全MMDモデル対象時はシーン内の全モデルへ順次適用)
                target_models = []
                if target_model_node and mc.objExists(target_model_node):
                    target_models = [target_model_node]
                else:
                    available = get_available_mmd_models()
                    if available:
                        target_models = [m[0] for m in available]
                    else:
                        target_models = [None]

                total_bones_applied = 0
                total_morphs_applied = 0

                for t_idx, t_model in enumerate(target_models):
                    # ボーン構造・モーフ構造の解決
                    resolved_model, joint_map, morph_map = resolve_model_structure(t_model)
                    target_display = resolved_model if resolved_model else "シーン全体"
                    print(f"  - [{t_idx+1}/{len(target_models)}] 適用対象モデル: {target_display}")
                    print(f"    認識されたボーンマッピング数: {len(joint_map)} 本")

                    # VMDモーションの詳細解析レポート（初回のみ出力）
                    if t_idx == 0:
                        print_vmd_analysis_report(motion, joint_map, resolved_model)

                    # VMD再インポート時に0フレームからモーションを上書きするため、既存キー・ポーズを自動初期化
                    try:
                        clear_model_animation(resolved_model, clear_camera=False)
                        mc.currentTime(0)
                    except Exception as e:
                        print(f"    [情報] 既存モーション初期化: {e}")

                    # ボーンアニメーションの適用
                    b_count, b_keys = apply_bone_motion(motion, joint_map, scale, resolved_model, progress_callback=progress_callback)
                    total_bones_applied += b_count
                    print(f"    - {b_count} 個のボーンにキーフレームを設定しました (総キー数: {b_keys})")

                    # モーフ（ブレンドシェイプ）アニメーションの適用
                    m_count, m_keys = apply_morph_motion(motion, morph_map, resolved_model)
                    total_morphs_applied += m_count
                    print(f"    - {m_count} 個のモーフにキーフレームを設定しました (総キー数: {m_keys})")

                result['bones_applied'] = total_bones_applied
                result['morphs_applied'] = total_morphs_applied

                # 同一ファイルにカメラが含まれていた場合の適用
                if motion.camera_frames and not result['camera_applied']:
                    apply_camera_motion(motion, scale)
                    result['camera_applied'] = True
                    print(f"  - 複合VMD内のカメラモーションを適用しました")

        # BGM音声 (.wav) の読み込み・タイムライン接続
        if audio_wav_path and os.path.isfile(audio_wav_path):
            print(f"[音声] ファイル読み込み中: {os.path.basename(audio_wav_path)}")
            audio_node = import_audio(audio_wav_path, volume_percent=audio_volume)
            if audio_node:
                result['audio_applied'] = True

        # Maya再生環境の設定 (MMD標準 30 fps)
        result['max_frame'] = max_frame
        if max_frame > 0:
            mc.currentUnit(time='ntsc') # 30 fps
            mc.playbackOptions(minTime=0, maxTime=max_frame, animationStartTime=0, animationEndTime=max_frame)
            mc.currentTime(0)

    finally:
        # インポート完了後にビューポートのライティングとシェーディングを確実に復元
        restore_viewport_lighting(prevent_motion_darkening=prevent_motion_darkening)

    elapsed = time.time() - start_time
    print(f"[完了] VMD インポートが完了しました ({elapsed:.2f} 秒)")
    return result


# ==============================================================================
# VPD (Vocaloid Pose Data) 入出力処理
# ==============================================================================

def import_vpd(file_path, target_model_node=None, scale=8.0, set_keyframe=False):
    """
    MMD標準のポーズデータ (.vpd) をMayaシーンのモデルへ適用します。

    引数:
        file_path (str): .vpd ファイルの絶対パス
        target_model_node (str, optional): 対象モデルルートノード名
        scale (float): スケール倍率（標準: 8.0）
        set_keyframe (bool): 現在のフレームにキーフレームを打刻するかどうか

    戻り値:
        dict: 適用結果 ('bones_applied', 'morphs_applied', 'model_name')
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"VPDファイルが存在しません: {file_path}")

    # VPDファイルの読み込み
    pose_data = mmd_core.vpd.load(file_path)

    # モデル構造の解決
    resolved_model, joint_map, morph_map = resolve_model_structure(target_model_node)
    target_display = resolved_model if resolved_model else "シーン全体"
    print(f"[VPDインポート] 対象モデル: {target_display} (ソース: {pose_data.model_name})")

    result = {
        'bones_applied': 0,
        'morphs_applied': 0,
        'model_name': pose_data.model_name
    }

    current_frame = mc.currentTime(query=True) if set_keyframe else None

    # ボーンポーズの適用
    for bone_pose in pose_data.bones:
        bone_name = bone_pose.name
        j_node = _match_bone_to_joint(bone_name, joint_map)
        if not j_node or not mc.objExists(j_node):
            continue

        try:
            # ジョイントの初期属性・方向クォータニオンを取得
            ro = mc.getAttr(f"{j_node}.rotateOrder")
            jo = mc.getAttr(f"{j_node}.jointOrient")[0]
            ra = mc.getAttr(f"{j_node}.rotateAxis")[0]

            jo_rad = [math.radians(a) for a in jo]
            ra_rad = [math.radians(a) for a in ra]
            jo_euler = om.MEulerRotation(jo_rad[0], jo_rad[1], jo_rad[2])
            ra_euler = om.MEulerRotation(ra_rad[0], ra_rad[1], ra_rad[2])

            inv_jo_q = jo_euler.asQuaternion().inverse()
            inv_ra_q = ra_euler.asQuaternion().inverse()

            # MMD左手系クォータニオン -> Maya右手系クォータニオン
            qx, qy, qz, qw = bone_pose.quat
            q_maya = om.MQuaternion(-qx, -qy, qz, qw)

            # jointOrient と rotateAxis を相殺
            local_rot_q = inv_jo_q * q_maya * inv_ra_q
            euler = local_rot_q.asEulerRotation()
            euler.reorderIt(ro)

            rx = math.degrees(euler.x)
            ry = math.degrees(euler.y)
            rz = math.degrees(euler.z)

            mc.setAttr(f"{j_node}.rotateX", rx)
            mc.setAttr(f"{j_node}.rotateY", ry)
            mc.setAttr(f"{j_node}.rotateZ", rz)

            if set_keyframe:
                mc.setKeyframe(j_node, attribute='rotateX', time=current_frame, value=rx)
                mc.setKeyframe(j_node, attribute='rotateY', time=current_frame, value=ry)
                mc.setKeyframe(j_node, attribute='rotateZ', time=current_frame, value=rz)

            # 平行移動の適用（移動値が存在する場合）
            px, py, pz = bone_pose.trans
            if abs(px) > 1e-4 or abs(py) > 1e-4 or abs(pz) > 1e-4:
                # 移動可能ボーンか判定
                is_movable = any(k in bone_name for k in ["ＩＫ", "IK", "親", "センター", "グルーブ", "全ての親", "下半身", "腰", "足先EX"])
                if is_movable:
                    # 初期位置属性の確認、なければ現在の位置にオフセット加算
                    init_t = [0.0, 0.0, 0.0]
                    if mc.attributeQuery('mmdInitialTranslate', node=j_node, exists=True):
                        try:
                            init_t = mc.getAttr(f"{j_node}.mmdInitialTranslate")[0]
                        except Exception:
                            pass
                    tx = init_t[0] + px * scale
                    ty = init_t[1] + py * scale
                    tz = init_t[2] - pz * scale
                    mc.setAttr(f"{j_node}.translateX", tx)
                    mc.setAttr(f"{j_node}.translateY", ty)
                    mc.setAttr(f"{j_node}.translateZ", tz)
                    if set_keyframe:
                        mc.setKeyframe(j_node, attribute='translateX', time=current_frame, value=tx)
                        mc.setKeyframe(j_node, attribute='translateY', time=current_frame, value=ty)
                        mc.setKeyframe(j_node, attribute='translateZ', time=current_frame, value=tz)

            result['bones_applied'] += 1
        except Exception as e:
            print(f"[VPD警告] ボーン適用エラー ({bone_name}): {e}")

    # 表情モーフの適用
    for morph_pose in pose_data.morphs:
        morph_name = morph_pose.name
        weight = morph_pose.weight

        target_info = None
        if morph_name in morph_map:
            target_info = morph_map[morph_name]
        else:
            # クリーン名による照合
            clean = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', '_', morph_name)
            for m_key, m_val in morph_map.items():
                if m_key == clean or clean in m_key:
                    target_info = m_val
                    break

        if target_info:
            if isinstance(target_info, (list, tuple)) and len(target_info) >= 2:
                bs_node, attr_name = target_info[0], target_info[1]
            else:
                bs_node = None
                attr_name = str(target_info)
                # blendShapeノードを探索
                bs_nodes = mc.ls(type='blendShape') or []
                for b in bs_nodes:
                    if mc.attributeQuery(attr_name, node=b, exists=True):
                        bs_node = b
                        break

            if bs_node and mc.objExists(f"{bs_node}.{attr_name}"):
                try:
                    mc.setAttr(f"{bs_node}.{attr_name}", weight)
                    if set_keyframe:
                        mc.setKeyframe(bs_node, attribute=attr_name, time=current_frame, value=weight)
                    result['morphs_applied'] += 1
                except Exception:
                    pass

    print(f"[VPDインポート完了] {result['bones_applied']} 本のボーン、{result['morphs_applied']} 個のモーフにポーズを適用しました。")
    return result


def export_vpd(file_path, target_model_node=None, scale=8.0):
    """
    Mayaシーンの現在のボーン・モーフ姿勢をMMD互換のポーズデータ (.vpd) として保存します。

    引数:
        file_path (str): 出力先 .vpd ファイルパス
        target_model_node (str, optional): 対象モデルルートノード名
        scale (float): スケール倍率（標準: 8.0）

    戻り値:
        dict: 保存結果 ('bones_exported', 'morphs_exported', 'file_path')
    """
    resolved_model, joint_map, morph_map = resolve_model_structure(target_model_node)
    model_name = resolved_model if resolved_model else "model.osm"

    bones = []
    morphs = []

    # ボーン姿勢の収集
    for bone_name, j_node in joint_map.items():
        if not mc.objExists(j_node):
            continue

        try:
            # 回転クォータニオンの計算
            ro = mc.getAttr(f"{j_node}.rotateOrder")
            rx = math.radians(mc.getAttr(f"{j_node}.rotateX"))
            ry = math.radians(mc.getAttr(f"{j_node}.rotateY"))
            rz = math.radians(mc.getAttr(f"{j_node}.rotateZ"))

            euler = om.MEulerRotation(rx, ry, rz, ro)
            local_rot_q = euler.asQuaternion()

            jo = mc.getAttr(f"{j_node}.jointOrient")[0]
            ra = mc.getAttr(f"{j_node}.rotateAxis")[0]
            jo_rad = [math.radians(a) for a in jo]
            ra_rad = [math.radians(a) for a in ra]
            jo_euler = om.MEulerRotation(jo_rad[0], jo_rad[1], jo_rad[2])
            ra_euler = om.MEulerRotation(ra_rad[0], ra_rad[1], ra_rad[2])

            jo_q = jo_euler.asQuaternion()
            ra_q = ra_euler.asQuaternion()

            # 姿勢 = jo_q * local_rot_q * ra_q
            q_maya = jo_q * local_rot_q * ra_q

            # Maya右手系 -> MMD左手系
            qx = -q_maya.x
            qy = -q_maya.y
            qz = q_maya.z
            qw = q_maya.w

            # 平行移動量の計算
            px, py, pz = 0.0, 0.0, 0.0
            is_movable = any(k in bone_name for k in ["ＩＫ", "IK", "親", "センター", "グルーブ", "全ての親", "下半身", "腰", "足先EX"])
            if is_movable:
                tx = mc.getAttr(f"{j_node}.translateX")
                ty = mc.getAttr(f"{j_node}.translateY")
                tz = mc.getAttr(f"{j_node}.translateZ")

                init_t = [0.0, 0.0, 0.0]
                if mc.attributeQuery('mmdInitialTranslate', node=j_node, exists=True):
                    try:
                        init_t = mc.getAttr(f"{j_node}.mmdInitialTranslate")[0]
                    except Exception:
                        pass
                px = (tx - init_t[0]) / scale
                py = (ty - init_t[1]) / scale
                pz = -(tz - init_t[2]) / scale

            bones.append(mmd_core.vpd.VpdBonePose(bone_name, trans=(px, py, pz), quat=(qx, qy, qz, qw)))
        except Exception:
            pass

    # 表情モーフの収集
    for morph_name, target_info in morph_map.items():
        try:
            bs_node = None
            attr_name = None
            if isinstance(target_info, (list, tuple)) and len(target_info) >= 2:
                bs_node, attr_name = target_info[0], target_info[1]
            else:
                attr_name = str(target_info)
                bs_nodes = mc.ls(type='blendShape') or []
                for b in bs_nodes:
                    if mc.attributeQuery(attr_name, node=b, exists=True):
                        bs_node = b
                        break

            if bs_node and mc.objExists(f"{bs_node}.{attr_name}"):
                w = float(mc.getAttr(f"{bs_node}.{attr_name}"))
                if abs(w) > 0.0005:
                    morphs.append(mmd_core.vpd.VpdMorphPose(morph_name, weight=w))
        except Exception:
            pass

    pose_data = mmd_core.vpd.VpdPoseData(model_name=model_name, bones=bones, morphs=morphs)
    mmd_core.vpd.save(file_path, pose_data)

    print(f"[VPD保存完了] {len(bones)} 本のボーン、{len(morphs)} 個のモーフ姿勢を保存しました: {file_path}")
    return {
        'bones_exported': len(bones),
        'morphs_exported': len(morphs),
        'file_path': file_path
    }


def export_vmd(file_path, target_model_node=None, start_frame=None, end_frame=None, step=1, scale=8.0, export_bones=True, export_morphs=True, export_camera=False, target_camera=None, simplify_keys=True):
    """
    Mayaのシーン内アニメーションからMMD公式モーション (.vmd) をエクスポートします。

    引数:
        file_path (str): 出力先 .vmd ファイルパス
        target_model_node (str, optional): 対象モデルルートノード名
        start_frame (int, optional): 開始フレーム（省略時はタイムスライダー開始値）
        end_frame (int, optional): 終了フレーム（省略時はタイムスライダー終了値）
        step (int): サンプリングステップ（標準: 1）
        scale (float): スケール倍率（標準: 8.0）
        export_bones (bool): ボーンアニメーションを出力するかどうか
        export_morphs (bool): モーフ（表情）アニメーションを出力するかどうか
        export_camera (bool): カメラアニメーションを出力するかどうか
        target_camera (str, optional): 対象カメラノード
        simplify_keys (bool): 静止時の不要な同一キーフレームを間引いて軽量化するかどうか

    戻り値:
        dict: エクスポート結果情報
    """
    # フレーム範囲の決定
    if start_frame is None:
        start_frame = int(mc.playbackOptions(query=True, minTime=True))
    if end_frame is None:
        end_frame = int(mc.playbackOptions(query=True, maxTime=True))
    if start_frame > end_frame:
        start_frame, end_frame = end_frame, start_frame
    step = max(1, int(step))

    motion = mmd_core.vmd.VmdMotion()
    resolved_model, joint_map, morph_map = resolve_model_structure(target_model_node)
    motion.model_name = resolved_model if resolved_model else "MMD Model"

    original_time = mc.currentTime(query=True)

    print("==================================================")
    print(f"MMD VMDモーションエクスポート開始: {os.path.basename(file_path)}")
    print(f"  - 対象モデル: {motion.model_name}")
    print(f"  - フレーム範囲: {start_frame} 〜 {end_frame} (ステップ: {step})")
    print(f"  - 出力対象: ボーン={export_bones}, モーフ={export_morphs}, カメラ={export_camera}")
    print("==================================================")

    bone_frames_dict = {}
    morph_frames_dict = {}
    camera_frames_list = []

    last_bone_states = {}
    last_morph_states = {}

    try:
        # タイムラインサンプリングループ
        for f in range(start_frame, end_frame + 1, step):
            mc.currentTime(f, edit=True)
            vmd_frame_num = max(0, int(round(f)))

            # ボーン姿勢のサンプリング
            if export_bones and joint_map:
                for bone_name, j_node in joint_map.items():
                    if not mc.objExists(j_node):
                        continue

                    try:
                        # 回転クォータニオンの計算
                        ro = mc.getAttr(f"{j_node}.rotateOrder")
                        rx = math.radians(mc.getAttr(f"{j_node}.rotateX"))
                        ry = math.radians(mc.getAttr(f"{j_node}.rotateY"))
                        rz = math.radians(mc.getAttr(f"{j_node}.rotateZ"))

                        euler = om.MEulerRotation(rx, ry, rz, ro)
                        local_rot_q = euler.asQuaternion()

                        jo = mc.getAttr(f"{j_node}.jointOrient")[0]
                        ra = mc.getAttr(f"{j_node}.rotateAxis")[0]
                        jo_rad = [math.radians(a) for a in jo]
                        ra_rad = [math.radians(a) for a in ra]
                        jo_euler = om.MEulerRotation(jo_rad[0], jo_rad[1], jo_rad[2])
                        ra_euler = om.MEulerRotation(ra_rad[0], ra_rad[1], ra_rad[2])

                        jo_q = jo_euler.asQuaternion()
                        ra_q = ra_euler.asQuaternion()

                        q_maya = jo_q * local_rot_q * ra_q

                        # Maya右手系 -> MMD左手系クォータニオン
                        qx = -q_maya.x
                        qy = -q_maya.y
                        qz = q_maya.z
                        qw = q_maya.w

                        # 平行移動量の計算
                        px, py, pz = 0.0, 0.0, 0.0
                        is_movable = any(k in bone_name for k in ["ＩＫ", "IK", "親", "センター", "グルーブ", "全ての親", "下半身", "腰", "足先EX"])
                        if is_movable:
                            tx = mc.getAttr(f"{j_node}.translateX")
                            ty = mc.getAttr(f"{j_node}.translateY")
                            tz = mc.getAttr(f"{j_node}.translateZ")

                            init_t = [0.0, 0.0, 0.0]
                            if mc.attributeQuery('mmdInitialTranslate', node=j_node, exists=True):
                                try:
                                    init_t = mc.getAttr(f"{j_node}.mmdInitialTranslate")[0]
                                except Exception:
                                    pass
                            px = (tx - init_t[0]) / scale
                            py = (ty - init_t[1]) / scale
                            pz = -(tz - init_t[2]) / scale

                        cur_state = (px, py, pz, qx, qy, qz, qw)
                        should_record = True
                        if simplify_keys and bone_name in last_bone_states:
                            prev_f, prev_state = last_bone_states[bone_name]
                            pos_diff = sum(abs(cur_state[i] - prev_state[i]) for i in range(3))
                            rot_diff = sum(abs(cur_state[i] - prev_state[i]) for i in range(3, 7))
                            if pos_diff < 1e-4 and rot_diff < 1e-4 and f != end_frame:
                                should_record = False

                        if should_record:
                            bf = mmd_core.vmd.VmdBoneFrame()
                            bf.name = bone_name
                            bf.frame = vmd_frame_num
                            bf.position = [px, py, pz]
                            bf.rotation = [qx, qy, qz, qw]
                            bf.interpolation = mmd_core.vmd.DEFAULT_BONE_INTERPOLATION

                            if bone_name not in bone_frames_dict:
                                bone_frames_dict[bone_name] = []
                            bone_frames_dict[bone_name].append(bf)
                            last_bone_states[bone_name] = (f, cur_state)

                    except Exception:
                        pass

            # 表情モーフのサンプリング
            if export_morphs and morph_map:
                for morph_name, target_info in morph_map.items():
                    try:
                        bs_node = None
                        attr_name = None
                        if isinstance(target_info, (list, tuple)) and len(target_info) >= 2:
                            bs_node, attr_name = target_info[0], target_info[1]
                        else:
                            attr_name = str(target_info)
                            bs_nodes = mc.ls(type='blendShape') or []
                            for b in bs_nodes:
                                if mc.attributeQuery(attr_name, node=b, exists=True):
                                    bs_node = b
                                    break

                        if bs_node and mc.objExists(f"{bs_node}.{attr_name}"):
                            w = float(mc.getAttr(f"{bs_node}.{attr_name}"))

                            should_record = True
                            if simplify_keys and morph_name in last_morph_states:
                                prev_f, prev_w = last_morph_states[morph_name]
                                if abs(w - prev_w) < 1e-4 and f != end_frame:
                                    should_record = False

                            if should_record:
                                mf = mmd_core.vmd.VmdMorphFrame()
                                mf.name = morph_name
                                mf.frame = vmd_frame_num
                                mf.weight = w

                                if morph_name not in morph_frames_dict:
                                    morph_frames_dict[morph_name] = []
                                morph_frames_dict[morph_name].append(mf)
                                last_morph_states[morph_name] = (f, w)
                    except Exception:
                        pass

            # カメラのサンプリング
            if export_camera:
                cam = target_camera or "persp"
                if mc.objExists(cam):
                    try:
                        cam_shape = cam if mc.nodeType(cam) == 'camera' else (mc.listRelatives(cam, shapes=True, type='camera') or [None])[0]
                        cam_trans = cam if mc.nodeType(cam) == 'transform' else (mc.listRelatives(cam, parent=True) or [None])[0]

                        pos = mc.xform(cam_trans, query=True, worldSpace=True, translation=True)
                        rot = mc.xform(cam_trans, query=True, worldSpace=True, rotation=True)
                        fl = mc.getAttr(f"{cam_shape}.focalLength")
                        h_ap = mc.getAttr(f"{cam_shape}.horizontalFilmAperture") * 25.4 # mm
                        fov = 2.0 * math.atan((h_ap * 0.5) / fl) * (180.0 / math.pi)

                        cf = mmd_core.vmd.VmdCameraFrame()
                        cf.frame = vmd_frame_num
                        cf.distance = 0.0 # ターゲットカメラ非使用時は位置を直接注視点として設定
                        cf.position = [pos[0] / scale, pos[1] / scale, -pos[2] / scale]
                        cf.rotation = [math.radians(rot[0]), -math.radians(rot[1]), -math.radians(rot[2])]
                        cf.fov = int(round(fov))
                        cf.perspective = True
                        camera_frames_list.append(cf)
                    except Exception:
                        pass

    finally:
        mc.currentTime(original_time, edit=True)

    motion.bone_frames = bone_frames_dict
    motion.morph_frames = morph_frames_dict
    motion.camera_frames = camera_frames_list

    total_bones_k = sum(len(v) for v in bone_frames_dict.values())
    total_morphs_k = sum(len(v) for v in morph_frames_dict.values())
    total_cam_k = len(camera_frames_list)

    mmd_core.vmd.save(file_path, motion)

    print("==================================================")
    print(f"[VMDエクスポート完了] {file_path}")
    print(f"  - ボーンキーフレーム総数: {total_bones_k:,} ({len(bone_frames_dict)} 系統)")
    print(f"  - モーフキーフレーム総数: {total_morphs_k:,} ({len(morph_frames_dict)} 系統)")
    if total_cam_k > 0:
        print(f"  - カメラキーフレーム総数: {total_cam_k:,}")
    print("==================================================")

    return {
        'total_bone_frames': total_bones_k,
        'total_morph_frames': total_morphs_k,
        'total_camera_frames': total_cam_k,
        'file_path': file_path
    }
