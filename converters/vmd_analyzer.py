import os
import sys
import unicodedata
from collections import defaultdict

try:
    from ..mmd_core import vmd
except Exception:
    try:
        from .mmd_core import vmd
    except Exception:
        import mmd_core.vmd as vmd

# MMDの標準ボーン定義
STANDARD_BONES = {
    "全ての親", "センター", "下半身", "上半身", "首", "頭",
    "左肩", "左腕", "左ひじ", "左手首",
    "右肩", "右腕", "右ひじ", "右手首",
    "左足", "左ひざ", "左足首", "左つま先",
    "右足", "右ひざ", "右足首", "右つま先",
    "左足ＩＫ", "左つま先ＩＫ", "右足ＩＫ", "右つま先ＩＫ",
    "目", "両目", "左目", "右目"
}

# 準標準ボーン（ダンス・トレースで頻出する拡張ボーン）
SEMI_STANDARD_BONES = {
    "グルーブ", "腰", "上半身2", "親", "操作中心",
    "左足IK親", "右足IK親",
    "左足D", "左ひざD", "左足首D", "左足先EX",
    "右足D", "右ひざD", "右足首D", "右足先EX",
    "左腕捩", "左腕捩1", "左腕捩2", "左腕捩3", "左手捩", "左手捩1", "左手捩2", "左手捩3",
    "右腕捩", "右腕捩1", "右腕捩2", "右腕捩3", "右手捩", "右手捩1", "右手捩2", "右手捩3",
    "左肩P", "左肩C", "右肩P", "右肩C",
    "腰キャンセル左", "腰キャンセル右", "胸親"
}

def normalize_bone_name(name):
    """
    ボーン名の全角英数を半角化し、前後空白を除去します。
    """
    if not name:
        return ""
    # 前後空白除去
    n = name.strip()
    # 全角英数・記号の正規化 (NFKC)
    return unicodedata.normalize('NFKC', n)

class VmdAnalysisReport:
    """VMD解析結果を格納するデータクラス"""
    def __init__(self, file_path):
        self.file_path = file_path
        self.model_name = ""
        self.max_frame = 0
        self.duration_sec = 0.0

        # ボーン統計
        self.total_bone_keyframes = 0
        self.unique_bones = []
        self.standard_bones_found = []
        self.semi_standard_bones_found = []
        self.ik_bones_found = []
        self.unknown_bones_found = []

        # 特徴フラグ
        self.has_groove = False
        self.has_waist = False
        self.has_leg_ik = False
        self.has_leg_d = False
        self.has_parent_all = False

        # モーフ統計
        self.total_morph_keyframes = 0
        self.unique_morphs = []

        # カメラ・照明
        self.camera_keyframe_count = 0
        self.light_keyframe_count = 0

    def generate_summary_text(self):
        """可読性の高い日本語レポートテキストを生成します。"""
        lines = []
        lines.append("=" * 60)
        lines.append(f"VMD モーション解析レポート: {os.path.basename(self.file_path)}")
        lines.append("=" * 60)
        lines.append(f"・対象モデル名 (ヘッダー): {self.model_name or '(なし / カメラ専用)'}")
        lines.append(f"・総フレーム数: {self.max_frame:,} f (約 {self.duration_sec:.2f} 秒 / 30fps)")
        lines.append("")

        lines.append("【ボーンアニメーション構成】")
        lines.append(f"・総ボーンキーフレーム数: {self.total_bone_keyframes:,} 個")
        lines.append(f"・登録ボーン総数: {len(self.unique_bones)} 本")

        # 準標準ボーン診断
        lines.append("・主要ボーン検出状況:")
        lines.append(f"  - グルーブボーン: {'あり (上下動・ステップ必須)' if self.has_groove else 'なし'}")
        lines.append(f"  - 腰ボーン: {'あり (骨盤回転)' if self.has_waist else 'なし'}")
        lines.append(f"  - 全ての親: {'あり (全体移動)' if self.has_parent_all else 'なし'}")
        lines.append(f"  - 足IKボーン: {'あり (標準IK制御)' if self.has_leg_ik else 'なし'}")
        lines.append(f"  - 準標準 足Dボーン: {'あり (FK補助ボーン制御)' if self.has_leg_d else 'なし'}")

        if self.semi_standard_bones_found:
            lines.append(f"・検出された準標準ボーン一覧 ({len(self.semi_standard_bones_found)}本):")
            lines.append(f"  {', '.join(sorted(self.semi_standard_bones_found))}")

        if self.ik_bones_found:
            lines.append(f"・検出されたIKボーン一覧 ({len(self.ik_bones_found)}本):")
            lines.append(f"  {', '.join(sorted(self.ik_bones_found))}")

        if self.unknown_bones_found:
            lines.append(f"・特殊・独自ボーン ({len(self.unknown_bones_found)}本):")
            lines.append(f"  {', '.join(sorted(self.unknown_bones_found)[:20])}" + ("..." if len(self.unknown_bones_found) > 20 else ""))

        lines.append("")
        lines.append("【モーフ (表情) 構成】")
        lines.append(f"・総表情キーフレーム数: {self.total_morph_keyframes:,} 個 (モーフ種類: {len(self.unique_morphs)} 種)")
        if self.unique_morphs:
            lines.append(f"・登録表情一覧: {', '.join(sorted(self.unique_morphs)[:20])}" + ("..." if len(self.unique_morphs) > 20 else ""))

        lines.append("")
        lines.append("【カメラ・その他】")
        lines.append(f"・カメラキーフレーム数: {self.camera_keyframe_count:,} 個")
        lines.append(f"・照明キーフレーム数: {self.light_keyframe_count:,} 個")
        lines.append("=" * 60)

        return "\n".join(lines)

def analyze_vmd(vmd_file_path):
    """
    VMDファイルをパースし、詳細な構造レポートオブジェクトを返します。
    """
    if not os.path.exists(vmd_file_path):
        raise FileNotFoundError(f"VMDファイルが存在しません: {vmd_file_path}")

    motion = vmd.load(vmd_file_path)
    report = VmdAnalysisReport(vmd_file_path)

    report.model_name = motion.model_name
    report.max_frame = motion.max_frame
    report.duration_sec = motion.max_frame / 30.0
    report.camera_keyframe_count = len(motion.camera_frames)
    report.light_keyframe_count = len(motion.light_frames)

    # ボーン解析
    total_b_keys = 0
    unique_bone_names = list(motion.bone_frames.keys())
    report.unique_bones = unique_bone_names

    for b_name, frames in motion.bone_frames.items():
        total_b_keys += len(frames)
        norm_name = normalize_bone_name(b_name)

        # フラグ判定
        if norm_name == "グルーブ":
            report.has_groove = True
        elif norm_name == "腰":
            report.has_waist = True
        elif "全ての親" in norm_name or "親" in norm_name:
            report.has_parent_all = True
        elif "足IK" in norm_name or "足ＩＫ" in norm_name:
            report.has_leg_ik = True
        elif norm_name.endswith("足D") or norm_name.endswith("ひざD") or norm_name.endswith("足首D"):
            report.has_leg_d = True

        # 分類
        if "IK" in norm_name or "ＩＫ" in b_name:
            report.ik_bones_found.append(b_name)
        elif b_name in STANDARD_BONES or norm_name in STANDARD_BONES:
            report.standard_bones_found.append(b_name)
        elif b_name in SEMI_STANDARD_BONES or norm_name in SEMI_STANDARD_BONES:
            report.semi_standard_bones_found.append(b_name)
        else:
            report.unknown_bones_found.append(b_name)

    report.total_bone_keyframes = total_b_keys

    # モーフ解析
    total_m_keys = 0
    unique_morph_names = list(motion.morph_frames.keys())
    report.unique_morphs = unique_morph_names
    for m_name, frames in motion.morph_frames.items():
        total_m_keys += len(frames)
    report.total_morph_keyframes = total_m_keys

    return report

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
        try:
            res = analyze_vmd(target_path)
            print(res.generate_summary_text())
        except Exception as e:
            print(f"[エラー] 解析に失敗しました: {e}")
    else:
        print("使用法: python vmd_analyzer.py <VMDファイルパス>")
