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

    # 完全一致
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
    roots = mc.ls('*.mmdModelRoot', objectsOnly=True) or []
    for r in roots:
        orig = mc.getAttr(f"{r}.originalName") if mc.attributeQuery('originalName', node=r, exists=True) else r
        models.append((r, f"{r} ({orig})"))

    # mmdModelRoot がない場合のフォールバック（MMD_Modelで始まるノード等）
    if not models:
        for node in mc.ls(type='transform') or []:
            if mc.attributeQuery('MMD_model', node=node, exists=True):
                orig = mc.getAttr(f"{node}.originalName") if mc.attributeQuery('originalName', node=node, exists=True) else node
                models.append((node, f"{node} ({orig})"))

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

def resolve_model_structure(target_model_node=None):
    """
    対象モデルのボーン構造マップおよびモーフ構造マップを取得します。
    モデルに埋め込まれたメタデータ属性、または直近インポート時の構造キャッシュを優先します。
    """
    bone_map = {}
    morph_map = {}
    resolved_model = None

    # 1. target_model_node の自動検出（未指定の場合）
    if not target_model_node or not mc.objExists(target_model_node):
        sel = mc.ls(selection=True)
        if sel:
            for s in sel:
                if mc.attributeQuery('mmdBoneStructure', node=s, exists=True):
                    target_model_node = s
                    break
        if not target_model_node:
            roots = mc.ls('*.mmdModelRoot', objectsOnly=True)
            if roots:
                target_model_node = roots[-1] # 最新のインポートモデル

    # 2. モデルノードのアトリビュートから構造復元
    if target_model_node and mc.objExists(target_model_node):
        resolved_model = target_model_node
        if mc.attributeQuery('mmdBoneStructure', node=target_model_node, exists=True):
            try:
                raw_json = mc.getAttr(f"{target_model_node}.mmdBoneStructure")
                if raw_json:
                    bone_map = json.loads(raw_json)
            except Exception:
                pass
        if mc.attributeQuery('mmdMorphStructure', node=target_model_node, exists=True):
            try:
                raw_json = mc.getAttr(f"{target_model_node}.mmdMorphStructure")
                if raw_json:
                    morph_map = json.loads(raw_json)
            except Exception:
                pass

    # 3. キャッシュファイル (last_imported_structure.json) からの復元
    if not bone_map:
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cache_path = os.path.join(plugin_root, 'asset', 'last_imported_structure.json')
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cdata = json.load(f)
                    bone_map = cdata.get('bones', {})
                    morph_map = cdata.get('morphs', {})
                    if not resolved_model:
                        resolved_model = cdata.get('model_node')
            except Exception:
                pass

    # 4. フォールバック探索
    if not bone_map:
        bone_map = _find_scene_joints(target_model_node)
    if not morph_map:
        morph_map = _find_blendshape_targets(target_model_node)

    return resolved_model, bone_map, morph_map

def _resolve_full_joint_path(node_candidate, target_model=None):
    """
    ジョイント候補名から、名前重複を回避して一意のフルDAGパスを取得します。
    """
    if not node_candidate:
        return None

    # 1. すでにフルパス（|で始まる）で存在する場合
    if node_candidate.startswith('|') and mc.objExists(node_candidate):
        return node_candidate

    # 2. ショートネームからロングネームを解決
    short_name = node_candidate.split('|')[-1].split(':')[-1]
    matches = mc.ls(short_name, long=True, type='joint') or []
    if not matches:
        matches = mc.ls(f"*{short_name}", long=True, type='joint') or []

    if matches:
        if len(matches) == 1:
            return matches[0]
        # 複数マッチした場合: target_model 階層下のマッチを優先
        if target_model:
            for m in matches:
                if target_model in m:
                    return m
        return matches[-1]

    # 3. 単純存在チェック
    if mc.objExists(node_candidate):
        longs = mc.ls(node_candidate, long=True)
        return longs[0] if longs else node_candidate

    return None

def apply_bone_motion(motion, joint_map, scale=8.0, target_model=None):
    """
    VMDボーンモーションをMayaのジョイント階層にキーフレーム設定します。
    フルDAGパス解決と個別例外保護により名前重複エラーによる途中中断を防止します。
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

    for bone_name, frames in motion.bone_frames.items():
        if bone_name not in valid_joints:
            continue

        j_node = valid_joints[bone_name]

        # コンストレイントで駆動されているDボーン等の従属ジョイントは直接キー打ちをスキップして追従連動を保護
        if any(k in bone_name for k in ["足D", "ひざD", "足首D"]):
            try:
                if mc.listConnections(j_node, type="orientConstraint"):
                    continue
            except Exception:
                pass

        # 腕捩1..3、手捩1..3等の分散補助ボーンはモデル側の付与エクスプレッションによる自動ロール分散を優先
        # (VMDの直接キー打ちとエクスプレッションが競合してメッシュがキャンディ状にねじれる現象を完全防止)
        if re.search(r'(腕捩|手捩)[0-9]', bone_name):
            continue

        # 直列捩り階層モデル（腕 -> 腕捩 -> ひじ）における二重回転防止
        # 親の「腕」や「ひじ」に既にキーフレームが存在する場合、直列の中間捩りボーンへの重複キー打ちをスキップ
        if bone_name in ["左腕捩", "右腕捩", "左手捩", "右手捩"]:
            side_prefix = "左" if "左" in bone_name else "右" if "右" in bone_name else ""
            parent_bone_key = f"{side_prefix}腕" if "腕捩" in bone_name else f"{side_prefix}ひじ"
            if parent_bone_key in motion.bone_frames:
                # 直列階層の親（ひじの親が腕捩になっている構造）かどうかを判定
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

                # 前フレームからの最短連続角度を維持 (180度フリップ・裏返りを完全防止)
                if j_node in prev_joint_eulers:
                    euler = euler.closestSolution(prev_joint_eulers[j_node])
                prev_joint_eulers[j_node] = euler

                rx = math.degrees(euler.x)
                ry = math.degrees(euler.y)
                rz = math.degrees(euler.z)

                mc.setKeyframe(j_node, attribute='rotateX', time=f, value=rx)
                mc.setKeyframe(j_node, attribute='rotateY', time=f, value=ry)
                mc.setKeyframe(j_node, attribute='rotateZ', time=f, value=rz)

                # 移動オフセットの適用（移動値が存在する場合、またはIK・ルート・下半身系）
                px, py, pz = bf.position
                is_movable_bone = (
                    any(keyword in bone_name for keyword in ["ＩＫ", "IK", "親", "センター", "グルーブ", "全ての親", "下半身", "腰"])
                    or abs(px) > 1e-5 or abs(py) > 1e-5 or abs(pz) > 1e-5
                )
                if is_movable_bone:
                    tx = init_t[0] + px * scale
                    ty = init_t[1] + py * scale
                    tz = init_t[2] - pz * scale
                    mc.setKeyframe(j_node, attribute='translateX', time=f, value=tx)
                    mc.setKeyframe(j_node, attribute='translateY', time=f, value=ty)
                    mc.setKeyframe(j_node, attribute='translateZ', time=f, value=tz)

                total_keys += 1
                bone_success = True
            except Exception:
                pass

        if bone_success:
            applied_bones += 1
        else:
            failed_bones.append(bone_name)

    # アニメーションカーブの補間をスプラインに設定
    for j_node in valid_joints.values():
        try:
            mc.keyTangent(j_node, edit=True, inTangentType='spline', outTangentType='spline')
        except Exception:
            pass

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

    # スプライン補間設定
    for node in [aim_locator, cam_trans, cam_shape]:
        try:
            mc.keyTangent(node, edit=True, inTangentType='spline', outTangentType='spline')
        except Exception:
            pass

    print(f"[情報] カメラアニメーションを適用しました: {len(motion.camera_frames)} フレーム")
    return aim_locator

def clear_model_animation(target_model_node=None, clear_camera=True):
    """
    指定モデル（または検出モデル）のボーンおよびモーフのアニメーションキーを全削除し、
    初期ポーズへ復元します。カメラアニメーションのクリアも行います。
    """
    resolved_model, joint_map, morph_map = resolve_model_structure(target_model_node)
    cleared_bones = 0
    cleared_morphs = 0

    # ボーンのアニメーション削除 & 初期化
    for bone_name, candidate in joint_map.items():
        resolved_path = _resolve_full_joint_path(candidate, resolved_model)
        if resolved_path and mc.objExists(resolved_path):
            try:
                mc.cutKey(resolved_path, clear=True)
                mc.setAttr(f"{resolved_path}.rotate", 0.0, 0.0, 0.0)
                cleared_bones += 1
            except Exception:
                pass

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

    mc.currentTime(0)
    print(f"[情報] アニメーションをクリアしました: ボーン={cleared_bones}, BlendShape={cleared_morphs}")
    return cleared_bones, cleared_morphs

def import_audio(wav_file_path, offset=0):
    """
    WAVオーディオファイルをMayaにインポートし、タイムスライダーに接続して再生同期を有効化します。
    """
    if not wav_file_path or not os.path.isfile(wav_file_path):
        return None

    # 既存の MMD_Audio ノードを整理
    for old_audio in mc.ls("MMD_Audio*", type="audio") or []:
        if mc.objExists(old_audio):
            try:
                mc.delete(old_audio)
            except Exception:
                pass

    try:
        # sound ノードを作成
        audio_node = mc.sound(file=wav_file_path, offset=offset, name="MMD_Audio")

        # タイムスライダー（PlaybackSlider）にアタッチ
        try:
            import maya.mel as mel
            slider = mel.eval('global string $gPlayBackSlider; $tmpVar = $gPlayBackSlider;')
            if slider and mc.timeControl(slider, exists=True):
                mc.timeControl(slider, edit=True, sound=audio_node, displaySound=True)
        except Exception:
            pass

        print(f"[情報] BGM音声をタイムスライダーに読み込みました: {os.path.basename(wav_file_path)} (ノード: {audio_node})")
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

            # メッシュ自体の削除
            if mc.objExists(m):
                mc.delete(m)
                deleted_count += 1
        except Exception:
            pass

    # シーン内の未接続IKハンドル・MMDジョイントのクリーンアップ
    for ik_h in mc.ls('ikHandle_*') or []:
        if mc.objExists(ik_h):
            try:
                mc.delete(ik_h)
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

def import_vmd(vmd_file_path=None, camera_vmd_path=None, audio_wav_path=None, scale=8.0, target_model_node=None):
    """
    VMDファイルをMayaにインポートし、対象モデル、カメラ、およびBGM音声を適用します。
    モデルモーション、カメラモーション、BGM音声の個別・一括指定に対応します。
    """
    start_time = time.time()
    print("==================================================")
    print("VMD モーションインポート開始")
    print("==================================================")

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

    # 1. カメラモーションの読み込み・適用
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

    # 2. キャラクターモーションの読み込み・適用
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
            # ボーン構造・モーフ構造の解決
            resolved_model, joint_map, morph_map = resolve_model_structure(target_model_node)
            target_display = resolved_model if resolved_model else "シーン全体"
            print(f"  - 適用対象モデル: {target_display}")
            print(f"  - 認識されたボーンマッピング数: {len(joint_map)} 本")

            # ボーンアニメーションの適用
            b_count, b_keys = apply_bone_motion(motion, joint_map, scale, resolved_model)
            result['bones_applied'] = b_count
            print(f"  - {b_count} 個のボーンにキーフレームを設定しました (総キー数: {b_keys})")

            # モーフ（ブレンドシェイプ）アニメーションの適用
            m_count, m_keys = apply_morph_motion(motion, morph_map, resolved_model)
            result['morphs_applied'] = m_count
            print(f"  - {m_count} 個のモーフにキーフレームを設定しました (総キー数: {m_keys})")

            # 同一ファイルにカメラが含まれていた場合の適用
            if motion.camera_frames and not result['camera_applied']:
                apply_camera_motion(motion, scale)
                result['camera_applied'] = True
                print(f"  - 複合VMD内のカメラモーションを適用しました")

    # 3. BGM音声 (.wav) の読み込み・タイムライン接続
    if audio_wav_path and os.path.isfile(audio_wav_path):
        print(f"[音声] ファイル読み込み中: {os.path.basename(audio_wav_path)}")
        audio_node = import_audio(audio_wav_path)
        if audio_node:
            result['audio_applied'] = True

    # 4. Maya再生環境の設定 (MMD標準 30 fps)
    result['max_frame'] = max_frame
    if max_frame > 0:
        mc.currentUnit(time='ntsc') # 30 fps
        mc.playbackOptions(minTime=0, maxTime=max_frame, animationStartTime=0, animationEndTime=max_frame)
        mc.currentTime(0)

    elapsed = time.time() - start_time
    print(f"[完了] VMD インポートが完了しました ({elapsed:.2f} 秒)")
    return result
