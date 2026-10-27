# -*- coding: utf-8 -*-
"""
VPD (Vocaloid Pose Data) 入出力エンジン (vpd.py)

MMDのポーズデータファイル (.vpd) を読み込み・保存するモジュールです。
Shift_JIS (CP932) および UTF-8 のテキストエンコーディングに対応し、
ボーンの姿勢（平行移動量・回転クォータニオン）および表情モーフ（ウェイト値）を
高精度に相互変換します。
"""

import os
import re


class VpdBonePose:
    """ボーンのポーズデータ"""
    def __init__(self, name="", trans=(0.0, 0.0, 0.0), quat=(0.0, 0.0, 0.0, 1.0)):
        self.name = name
        self.trans = list(trans)  # [x, y, z]
        self.quat = list(quat)    # [x, y, z, w]

    def __repr__(self):
        return f"<VpdBonePose '{self.name}' trans={self.trans} quat={self.quat}>"


class VpdMorphPose:
    """表情モーフのポーズデータ"""
    def __init__(self, name="", weight=0.0):
        self.name = name
        self.weight = float(weight)

    def __repr__(self):
        return f"<VpdMorphPose '{self.name}' weight={self.weight:.3f}>"


class VpdPoseData:
    """VPDファイル全体のデータコンテナ"""
    def __init__(self, model_name="", bones=None, morphs=None):
        self.model_name = model_name
        self.bones = bones if bones is not None else []
        self.morphs = morphs if morphs is not None else []

    def get_bone(self, name):
        """ボーン名でポーズを検索"""
        for b in self.bones:
            if b.name == name:
                return b
        return None

    def get_morph(self, name):
        """モーフ名でポーズを検索"""
        for m in self.morphs:
            if m.name == name:
                return m
        return None


def load(file_path):
    """
    VPDファイルを読み込んで VpdPoseData オブジェクトを返します。

    引数:
        file_path (str): .vpd ファイルの絶対パス

    戻り値:
        VpdPoseData: 解析されたポーズデータ
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"VPDファイルが見つかりません: {file_path}")

    raw_text = ""
    # Shift_JIS (CP932) を優先し、失敗時は UTF-8 でフォールバック
    for enc in ["cp932", "shift_jis", "utf-8", "utf-8-sig"]:
        try:
            with open(file_path, "r", encoding=enc) as f:
                raw_text = f.read()
            break
        except UnicodeDecodeError:
            continue

    if not raw_text:
        with open(file_path, "rb") as f:
            raw_bytes = f.read()
        raw_text = raw_bytes.decode("cp932", errors="replace")

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return VpdPoseData()

    # ヘッダー検証 (Vocaloid Pose Data file)
    header = lines[0]
    if "Vocaloid Pose Data" not in header:
        print(f"[VPD警告] 標準ヘッダーと一致しません: {header}")

    model_name = ""
    bones = []
    morphs = []

    # 各行のパース
    i = 1
    # モデル名行 (.osm;)
    while i < len(lines):
        line = lines[i]
        if line.endswith(";"):
            # コメント除去
            clean = line.split("//")[0].strip().rstrip(";")
            if not model_name and not clean.isdigit():
                model_name = clean
                i += 1
                continue
            elif clean.isdigit():
                # ボーン数
                i += 1
                break
        i += 1

    content_str = "\n".join(lines[i:])

    # 全ボーンブロックの抽出
    # Bone0{ボーン名
    #   0.000000,0.000000,0.000000;
    #   0.000000,0.000000,0.000000,1.000000;
    # }
    for block in re.finditer(r"Bone\d+\{([^\}]+)\}", content_str):
        body = block.group(1).strip()
        body_lines = [l.split("//")[0].strip() for l in body.splitlines() if l.split("//")[0].strip()]
        if not body_lines:
            continue
        bone_name = body_lines[0].strip()
        trans = [0.0, 0.0, 0.0]
        quat = [0.0, 0.0, 0.0, 1.0]

        if len(body_lines) >= 2:
            t_str = body_lines[1].rstrip(";")
            parts = [p.strip() for p in t_str.split(",") if p.strip()]
            if len(parts) >= 3:
                try:
                    trans = [float(parts[0]), float(parts[1]), float(parts[2])]
                except ValueError:
                    pass

        if len(body_lines) >= 3:
            q_str = body_lines[2].rstrip(";")
            parts = [p.strip() for p in q_str.split(",") if p.strip()]
            if len(parts) >= 4:
                try:
                    quat = [float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])]
                except ValueError:
                    pass

        bones.append(VpdBonePose(bone_name, trans, quat))

    # 全モーフブロックの抽出
    # Morph0{まばたき
    #   1.000000;
    # }
    for block in re.finditer(r"Morph\d+\{([^\}]+)\}", content_str):
        body = block.group(1).strip()
        body_lines = [l.split("//")[0].strip() for l in body.splitlines() if l.split("//")[0].strip()]
        if not body_lines:
            continue
        morph_name = body_lines[0].strip()
        weight = 0.0
        if len(body_lines) >= 2:
            w_str = body_lines[1].rstrip(";")
            try:
                weight = float(w_str)
            except ValueError:
                weight = 0.0
        morphs.append(VpdMorphPose(morph_name, weight))

    return VpdPoseData(model_name=model_name, bones=bones, morphs=morphs)


def save(file_path, pose_data):
    """
    VpdPoseData オブジェクトを MMD互換の .vpd ファイルとして保存します。

    引数:
        file_path (str): 出力先 .vpd ファイルパス
        pose_data (VpdPoseData): 出力するポーズデータ
    """
    model_name = pose_data.model_name if pose_data.model_name else "model.osm"
    if not model_name.endswith(".osm"):
        model_name += ".osm"

    lines = []
    lines.append("Vocaloid Pose Data file")
    lines.append("")
    lines.append(f"{model_name};")
    lines.append(f"{len(pose_data.bones)};")
    lines.append("")

    # ボーンデータ書き出し
    for idx, bone in enumerate(pose_data.bones):
        lines.append(f"Bone{idx}{{{bone.name}")
        lines.append(f"  {bone.trans[0]:.6f},{bone.trans[1]:.6f},{bone.trans[2]:.6f};")
        lines.append(f"  {bone.quat[0]:.6f},{bone.quat[1]:.6f},{bone.quat[2]:.6f},{bone.quat[3]:.6f};")
        lines.append("}")

    # モーフデータ書き出し (モーフが存在する場合)
    if pose_data.morphs:
        lines.append("")
        lines.append(f"{len(pose_data.morphs)};")
        lines.append("")
        for idx, morph in enumerate(pose_data.morphs):
            lines.append(f"Morph{idx}{{{morph.name}")
            lines.append(f"  {morph.weight:.6f};")
            lines.append("}")

    out_content = "\r\n".join(lines) + "\r\n"

    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    # MMD標準の Shift_JIS (CP932) で保存
    try:
        with open(file_path, "w", encoding="cp932", errors="replace") as f:
            f.write(out_content)
    except Exception:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(out_content)
