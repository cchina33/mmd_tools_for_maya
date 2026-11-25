# -*- coding: utf-8 -*-
"""
pmm.py - MMD (Polygon Movie Maker) プロジェクトファイル解析モジュール

_MikuDanceStudio の実装および MMD 本家のバイナリ仕様に準拠し、
PMM ファイルから基本設定、モデル情報、タイムラインキーフレーム、
モーション/ポーズ判定、モデル構成要素の照合、アクセサリ情報、音声パスなどを抽出します。
"""

import os
import struct
import re
from typing import List, Dict, Optional, Any, Tuple

try:
    from . import vmd as vmd_mod
except Exception:
    try:
        import vmd as vmd_mod
    except Exception:
        vmd_mod = None


class PmmItem:
    """
    PMM に含まれる参照ファイル（モデル、アクセサリ、音声等）の情報クラス
    """
    def __init__(self, kind: str, name: str, raw_path: str, resolved_path: str = "",
                 exists: bool = False, slot: int = -1, source_name: str = ""):
        self.kind = kind  # "Model", "Accessory", "Audio", "Background" など
        self.name = name
        self.source_name = source_name
        self.raw_path = raw_path
        self.resolved_path = resolved_path
        self.exists = exists
        self.slot = slot
        self.file_type = os.path.splitext(raw_path)[1].lower() if raw_path else ""

        # モーション / ポーズ情報
        self.has_motion: bool = False
        self.motion_type: str = "なし"  # "モーション (1,200F)", "ポーズデータ (1F)", "なし"
        self.max_frame: int = 0
        self.bone_key_count: int = 0
        self.morph_key_count: int = 0

        # モデル照合情報 (PMX / PMD との突合結果)
        self.bone_count: int = 0
        self.morph_count: int = 0
        self.match_status: str = "未照合"  # "一致", "部分一致", "不一致", "モデル未検出", "-"
        self.match_detail: str = ""
        self.bone_names: List[str] = []
        self.morph_names: List[str] = []

        # 重複・過去残骸判定フラグ
        self.is_old_data: bool = False

        # 抽出されたVMDモーションデータ (VmdMotionオブジェクト)
        self.motion: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "source_name": self.source_name,
            "raw_path": self.raw_path,
            "resolved_path": self.resolved_path,
            "exists": self.exists,
            "slot": self.slot,
            "file_type": self.file_type,
            "has_motion": self.has_motion,
            "motion_type": self.motion_type,
            "max_frame": self.max_frame,
            "match_status": self.match_status,
            "match_detail": self.match_detail,
            "bone_count": self.bone_count,
            "morph_count": self.morph_count,
            "bone_key_count": self.bone_key_count,
            "morph_key_count": self.morph_key_count,
            "is_old_data": self.is_old_data,
        }


class PmmCameraInfo:
    """
    PMM のカメラトラックおよび初期カメラ設定を保持するクラス
    """
    def __init__(self):
        self.has_motion: bool = False
        self.motion_type: str = "固定カメラ設定"
        self.key_count: int = 0
        self.max_frame: int = 0
        self.fov: float = 30.0
        self.distance: float = 45.0
        self.position: Tuple[float, float, float] = (0.0, 10.0, 0.0)
        self.rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)


class PmmProject:
    """
    PMM プロジェクト全体の解析結果を保持するクラス
    """
    def __init__(self, filepath: str = ""):
        self.filepath: str = filepath
        self.version: str = ""  # "0001" または "0002"
        self.signature: str = ""
        self.render_width: int = 0
        self.render_height: int = 0
        self.camera_fov: float = 0.0
        self.last_registered_frame: int = 0
        self.models: List[PmmItem] = []
        self.accessories: List[PmmItem] = []
        self.audio: Optional[PmmItem] = None
        self.background_avi: Optional[PmmItem] = None
        self.background_pic: Optional[PmmItem] = None
        self.camera_info: PmmCameraInfo = PmmCameraInfo()
        self.camera_motion: Any = None
        self.logs: List[str] = []

    def log(self, message: str):
        self.logs.append(message)

    def all_items(self) -> List[PmmItem]:
        """登録されている全ての外部参照アイテムを一覧で取得"""
        items: List[PmmItem] = []
        items.extend(self.models)
        items.extend(self.accessories)
        if self.audio and self.audio.raw_path:
            items.append(self.audio)
        if self.background_avi and self.background_avi.raw_path:
            items.append(self.background_avi)
        if self.background_pic and self.background_pic.raw_path:
            items.append(self.background_pic)
        return items


# 実体モデル情報キャッシュ (パス -> {name, bone_count, morph_count})
_MODEL_CACHE: Dict[str, Dict[str, Any]] = {}


def get_model_info_quick(filepath: str) -> Optional[Dict[str, Any]]:
    """
    PMX または PMD ファイルからモデル名、ボーン数、モーフ数を取得します。
    """
    if not filepath or not os.path.exists(filepath):
        return None

    norm_path = os.path.abspath(filepath)
    if norm_path in _MODEL_CACHE:
        return _MODEL_CACHE[norm_path]

    ext = os.path.splitext(norm_path)[1].lower()
    res = None
    if ext == '.pmx':
        res = _read_pmx_info(norm_path)
    elif ext == '.pmd':
        res = _read_pmd_info(norm_path)

    if res:
        _MODEL_CACHE[norm_path] = res
    return res


def _read_pmx_info(filepath: str) -> Optional[Dict[str, Any]]:
    """PMXファイルからヘッダーおよびボーン数・モーフ数を安全に取得"""
    pmx_mod = None
    try:
        from . import pmx as pmx_mod
    except Exception:
        try:
            import pmx as pmx_mod
        except Exception:
            try:
                import importlib.util
                pmx_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pmx.py")
                spec = importlib.util.spec_from_file_location("pmx", pmx_file)
                pmx_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(pmx_mod)
            except Exception:
                pmx_mod = None

    if pmx_mod and hasattr(pmx_mod, 'load'):
        try:
            model = pmx_mod.load(filepath)
            return {
                "name": model.name,
                "name_e": getattr(model, "name_e", ""),
                "bone_count": len(model.bones),
                "morph_count": len(model.morphs),
                "bone_names": [b.name for b in model.bones],
                "morph_names": [m.name for m in model.morphs],
            }
        except Exception:
            pass

    # 軽量フォールバック読み込み
    try:
        with open(filepath, 'rb') as f:
            sig = f.read(4)
            if sig != b'PMX ':
                return None
            ver = struct.unpack('<f', f.read(4))[0]
            header_len = f.read(1)[0]
            header_bytes = f.read(header_len)
            text_encoding = header_bytes[0]
            enc = 'utf-8' if text_encoding == 1 else 'utf-16le'

            name_len = struct.unpack('<i', f.read(4))[0]
            name_j = f.read(name_len).decode(enc, errors='replace')
            name_e_len = struct.unpack('<i', f.read(4))[0]
            name_e = f.read(name_e_len).decode(enc, errors='replace')
            return {
                "name": name_j,
                "name_e": name_e,
                "bone_count": -1,
                "morph_count": -1,
                "bone_names": [],
                "morph_names": []
            }
    except Exception:
        return None


def _read_pmd_info(filepath: str) -> Optional[Dict[str, Any]]:
    """PMDファイルからヘッダーおよびボーン・モーフ情報を安全に取得"""
    try:
        try:
            from . import pmd
        except Exception:
            try:
                import mmd_parser.pmd as pmd
            except Exception:
                import pmd

        pmd_model = pmd.load2pmx(filepath)
        bone_names = [getattr(b, 'name', '') for b in getattr(pmd_model, 'bones', [])]
        morph_names = [getattr(m, 'name', '') for m in getattr(pmd_model, 'morphs', [])]
        model_name = getattr(pmd_model, 'name', '') or os.path.splitext(os.path.basename(filepath))[0]
        name_e = getattr(pmd_model, 'name_e', '')

        return {
            "name": model_name,
            "name_e": name_e,
            "bone_count": len(bone_names),
            "morph_count": len(morph_names),
            "bone_names": bone_names,
            "morph_names": morph_names
        }
    except Exception:
        # パース失敗時の安全フォールバック（バイナリヘッダー読み込み）
        try:
            with open(filepath, 'rb') as f:
                sig = f.read(3)
                if sig != b'Pmd':
                    return None
                f.seek(4)
                name_bytes = f.read(20)
                name_j = name_bytes.decode('cp932', errors='replace').rstrip('\x00')
                return {
                    "name": name_j,
                    "name_e": "",
                    "bone_count": -1,
                    "morph_count": -1,
                    "bone_names": [],
                    "morph_names": []
                }
        except Exception:
            return None


def resolve_pmm_file_path(raw_path: str, pmm_filepath: str) -> Tuple[str, bool]:
    """
    PMM に記録されているパスから実在するファイルパスを解決します。
    Windows パス区切りに対応し、絶対パス、PMM と同一フォルダ、
    親階層からの相対パスなどを順次検証します。
    """
    if not raw_path or not raw_path.strip():
        return "", False

    cleaned_path = raw_path.strip().replace('/', '\\')
    pmm_dir = os.path.dirname(os.path.abspath(pmm_filepath)) if pmm_filepath else ""

    # 記録されたパスが絶対パスとしてそのまま存在するか確認
    if os.path.exists(cleaned_path):
        return os.path.abspath(cleaned_path), True

    if pmm_dir:
        # PMM と同一ディレクトリに存在するか確認
        basename = os.path.basename(cleaned_path)
        same_dir_candidate = os.path.join(pmm_dir, basename)
        if os.path.exists(same_dir_candidate):
            return os.path.abspath(same_dir_candidate), True

        # 相対パスとして結合して存在するか確認
        rel_candidate = os.path.join(pmm_dir, cleaned_path)
        if os.path.exists(rel_candidate):
            return os.path.abspath(rel_candidate), True

        # ドライブ文字などを除去したパス結合を確認
        drive, rest = os.path.splitdrive(cleaned_path)
        if rest:
            rel_candidate2 = os.path.join(pmm_dir, rest.lstrip('\\/'))
            if os.path.exists(rel_candidate2):
                return os.path.abspath(rel_candidate2), True

        # 一般的な MMD フォルダ構造 (UserFile/Model 等) の親階層探索
        curr_dir = pmm_dir
        for _ in range(4):
            parent = os.path.dirname(curr_dir)
            if not parent or parent == curr_dir:
                break
            candidate = os.path.join(parent, cleaned_path)
            if os.path.exists(candidate):
                return os.path.abspath(candidate), True
            candidate_base = os.path.join(parent, basename)
            if os.path.exists(candidate_base):
                return os.path.abspath(candidate_base), True
            curr_dir = parent

        # 同一フォルダ以下の浅い階層を探索
        try:
            for root, dirs, files in os.walk(pmm_dir):
                for f in files:
                    if f.lower() == basename.lower():
                        return os.path.abspath(os.path.join(root, f)), True
                rel = os.path.relpath(root, pmm_dir)
                if rel.count(os.sep) >= 2:
                    dirs.clear()
        except Exception:
            pass

    # 見つからない場合は記録されたパスを返却
    return cleaned_path, False


def _read_sjis_len_string(data: bytes, offset: int) -> Tuple[str, int]:
    """1バイト長プレフィックス付きの Shift-JIS 文字列を安全に読み込みます"""
    if offset >= len(data):
        return "", offset
    length = data[offset]
    offset += 1
    if offset + length > len(data):
        return "", len(data)
    text_bytes = data[offset:offset + length]
    offset += length

    # ナル文字以降の不要バイトを切り詰め
    null_pos = text_bytes.find(b'\x00')
    if null_pos != -1:
        text_bytes = text_bytes[:null_pos]

    try:
        text = text_bytes.decode('cp932')
    except Exception:
        try:
            text = text_bytes.decode('utf-8')
        except Exception:
            text = text_bytes.decode('cp932', errors='replace')

    # 表示不能な制御文字を除去して文字化けを防止
    cleaned = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\t\r\n")
    return cleaned.strip(), offset


def _read_fixed_sjis_string(data: bytes, offset: int, length: int) -> Tuple[str, int]:
    """固定長の Shift-JIS 文字列（ナル終端）を安全に読み込みます"""
    if offset >= len(data):
        return "", offset
    raw = data[offset:offset + length]
    offset += length
    null_idx = raw.find(b'\x00')
    if null_idx != -1:
        raw = raw[:null_idx]
    try:
        text = raw.decode('cp932')
    except Exception:
        try:
            text = raw.decode('utf-8')
        except Exception:
            text = raw.decode('cp932', errors='replace')
    cleaned = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\t\r\n")
    return cleaned.strip(), offset


def _clean_path_candidate(text: str) -> str:
    """スキャンで抽出した文字列から前後の不要なバイナリゴミを除去して正規化"""
    cleaned = text.strip()
    # ドライブレター (C:\ や D:\ 等) があればそこを先頭にする
    for i in range(len(cleaned) - 2):
        if cleaned[i].isalpha() and cleaned[i + 1] == ':' and cleaned[i + 2] in ['\\', '/']:
            cleaned = cleaned[i:]
            break

    # 相対パス開始記号があれば手前のゴミを除去
    for prefix in ['.\\', './', '..\\', '../']:
        pos = cleaned.find(prefix)
        if 0 < pos <= 4:
            cleaned = cleaned[pos:]
            break

    cleaned = cleaned.lstrip('\x00\r\n\t /\\')
    return cleaned


def _is_valid_path_candidate(path_str: str, ext_lower: str, exists: bool) -> bool:
    """
    バイナリスキャンで抽出された文字列が妥当なファイルパスであるかを厳密に判定します。
    """
    if not path_str or len(path_str) < 4:
        return False

    invalid_chars = ['<', '>', '"', '|', '?', '*']
    if any(ch in path_str for ch in invalid_chars):
        return False

    if any(ord(ch) < 0x20 for ch in path_str):
        return False

    if exists:
        return True

    has_separator = ('\\' in path_str) or ('/' in path_str)
    basename = os.path.basename(path_str)
    name_without_ext = os.path.splitext(basename)[0]

    if len(name_without_ext) < 2:
        return False

    if ext_lower == '.x':
        if not has_separator:
            return False
        suspicious_symbols = ['=', ';', '{', '}', '^', '~', '!', '[', ']', '(', ')', '%', '$', '#', '@', '&']
        if any(ch in path_str for ch in suspicious_symbols):
            return False
        if re.search(r'[ｦ-ﾟ]', name_without_ext):
            return False

    elif ext_lower in ['.pmx', '.pmd']:
        if not has_separator:
            return False
        if any(ch in path_str for ch in ['=', ';', '{', '}', '^', '~']):
            return False

    elif ext_lower in ['.wav', '.avi']:
        if not has_separator:
            return False

    return True


def _find_next_model_offset(data: bytes, current_offset: int, file_size: int) -> int:
    """
    複数モデル解析時において、次のモデルヘッダーの開始位置を正確に検証・再同期します。
    モデルスロット番号、モデル名長、ソース名長、および256バイトの固定長ファイルパス領域
    （.pmx または .pmd シグネチャ）の整合性を照合します。
    """
    if current_offset >= file_size:
        return current_offset

    def _is_valid_header_at(pos: int) -> bool:
        if pos + 3 + 0x100 > file_size:
            return False
        slot = data[pos]
        if slot >= 100:
            return False
        m_len = data[pos + 1]
        if m_len > 120 or pos + 2 + m_len >= file_size:
            return False
        s_len = data[pos + 2 + m_len]
        if s_len > 120 or pos + 3 + m_len + s_len + 0x100 > file_size:
            return False
        path_bytes = data[pos + 3 + m_len + s_len : pos + 3 + m_len + s_len + 0x100]
        path_lower = path_bytes.lower()
        if b'.pmx' in path_lower or b'.pmd' in path_lower:
            return True
        if m_len > 0 and path_bytes.strip(b'\x00') == b'':
            return True
        return False

    # 現在のオフセットがそのまま妥当であれば即座に返却
    if _is_valid_header_at(current_offset):
        return current_offset

    # オフセットがズレている場合、前方にスキャンして再同期位置を探索
    search_limit = min(file_size - 0x100, current_offset + 500000)
    for pos in range(current_offset, search_limit):
        if _is_valid_header_at(pos):
            return pos

    return current_offset


def _verify_model_item(item: PmmItem, filepath: str):
    """
    モデルアイテムについて、実体ファイル（PMX/PMD）とPMM記録情報を突合し、
    照合ステータスと詳細テキストを設定します。
    """
    if not item.exists or not item.resolved_path:
        item.match_status = "モデル未検出"
        item.match_detail = "PC上にモデルファイルが見つかりません"
        return

    real_info = get_model_info_quick(item.resolved_path)
    if not real_info:
        item.match_status = "未照合"
        item.match_detail = "ファイルは存在しますがモデル情報の読み取りに失敗しました"
        return

    real_name = real_info.get("name", "")
    real_name_e = real_info.get("name_e", "")
    real_bones = real_info.get("bone_count", -1)
    real_morphs = real_info.get("morph_count", -1)

    base_file = os.path.splitext(os.path.basename(item.resolved_path))[0].lower()
    pmm_name = (item.name or "").lower()
    pmm_src = (item.source_name or "").lower()

    name_matched = False
    if real_name:
        rn_lower = real_name.lower()
        if (pmm_name and pmm_name in rn_lower) or (pmm_src and pmm_src in rn_lower) or (rn_lower in (pmm_name, pmm_src)):
            name_matched = True
        if base_file in rn_lower or rn_lower in base_file:
            name_matched = True

    if not name_matched and real_name_e:
        rne_lower = real_name_e.lower()
        if (pmm_name and pmm_name in rne_lower) or (pmm_src and pmm_src in rne_lower):
            name_matched = True

    bone_diff = abs(item.bone_count - real_bones) if (item.bone_count > 0 and real_bones >= 0) else -1
    morph_diff = abs(item.morph_count - real_morphs) if (item.morph_count > 0 and real_morphs >= 0) else -1

    if item.bone_count > 0 and real_bones >= 0:
        if bone_diff == 0 and morph_diff == 0:
            item.match_status = "一致"
            item.match_detail = f"モデル名・構成要素が合致 (ボーン: {real_bones}本 / モーフ: {real_morphs}個)"
        elif name_matched:
            item.match_status = "部分一致"
            item.match_detail = f"モデル名合致 / 構成差異あり (ボーン PMM:{item.bone_count}本 vs 実体:{real_bones}本)"
        else:
            item.match_status = "不一致"
            item.match_detail = f"構成相違あり (PMM: {item.name} / 実体: {real_name})"
    else:
        if name_matched:
            item.match_status = "一致"
            item.match_detail = f"モデル名合致: '{real_name}'"
        else:
            item.match_status = "部分一致"
            item.match_detail = f"ファイル名は一致 (実体名: '{real_name}')"


def _mark_old_data(project: PmmProject):
    """
    同種のアセット内で名称が重複・類似しており、一方が存在し他方が未検出である場合、
    未検出側のアイテムを旧データ（過去の残骸データ）として判定します。
    パスの確認を行えるよう、データ自体は破棄せずフラグを付与して保持します。
    """
    items = project.all_items()
    existing_items = [it for it in items if it.exists]
    missing_items = [it for it in items if not it.exists]

    for m_item in missing_items:
        m_name = (m_item.name or "").lower().strip()
        m_base = os.path.splitext(os.path.basename(m_item.raw_path))[0].lower().strip() if m_item.raw_path else ""

        is_duplicate = False
        matched_exist_name = ""

        for e_item in existing_items:
            # 同一種別のみ比較（モデル同士、アクセサリ同士など）
            if e_item.kind != m_item.kind:
                continue

            e_name = (e_item.name or "").lower().strip()
            e_base = os.path.splitext(os.path.basename(e_item.raw_path))[0].lower().strip() if e_item.raw_path else ""

            # 名称の一致
            if m_name and e_name and m_name == e_name:
                is_duplicate = True
                matched_exist_name = e_item.name
                break

            # ファイルベース名の一致
            if m_base and e_base and m_base == e_base:
                is_duplicate = True
                matched_exist_name = e_item.name
                break

            # 部分一致・包含関係（例: 「空中に漂う埃」が「東空中に漂う埃」に含まれる場合）
            # 誤判定を防ぐため共通部分が3文字以上である場合を対象
            if e_name and len(e_name) >= 3 and (e_name in m_name or m_name in e_name):
                is_duplicate = True
                matched_exist_name = e_item.name
                break

            if e_base and len(e_base) >= 3 and (e_base in m_base or m_base in e_base):
                is_duplicate = True
                matched_exist_name = e_item.name
                break

        if is_duplicate:
            m_item.is_old_data = True
            m_item.match_detail = f"過去の重複残骸パス (現行: '{matched_exist_name}')"
            project.log(f"  [旧データ判定] '{m_item.name}' は現行アセット '{matched_exist_name}' の過去残骸としてマークされました")


def parse_pmm(filepath: str) -> PmmProject:
    """
    PMM ファイルを解析してプロジェクト情報を返します。
    空スロットやパースズレによる無効なゴーストモデルを確実に排除し、
    正規のモデルおよびモーション情報を抽出します。
    """
    project = PmmProject(filepath)
    project.log(f"PMM ファイル解析を開始: {filepath}")

    if not os.path.exists(filepath):
        project.log(f"エラー: 指定されたファイルが存在しません: {filepath}")
        return project

    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except Exception as e:
        project.log(f"エラー: ファイルの読み込みに失敗しました: {e}")
        return project

    file_size = len(data)
    project.log(f"ファイルサイズ: {file_size:,} バイト")

    if file_size < 30:
        project.log("エラー: ファイルヘッダーのサイズが不足しています")
        return project

    # シグネチャ確認 (最初の 30 バイト付近)
    header_bytes = data[:30]
    sig_index = header_bytes.find(b"Polygon Movie maker")
    is_v1 = False
    if sig_index == -1:
        project.log("警告: 標準のシグネチャが見つかりません。バイナリ走査を併用します。")
        project.signature = "Unknown"
        project.version = "0002"
    else:
        project.signature = "Polygon Movie maker"
        ver_bytes = header_bytes[sig_index + 20:sig_index + 24]
        try:
            project.version = ver_bytes.decode('ascii', errors='ignore')
        except Exception:
            project.version = "0002"
        if project.version == "0001":
            is_v1 = True
        project.log(f"シグネチャ検出: {project.signature} (バージョン: {project.version})")

    bone_key_size = 57 if is_v1 else 58
    morph_key_size = 17

    offset = 30

    # 構造化ヘッダーの解析
    try:
        if offset + 23 <= file_size:
            w, h, sidebar, fov = struct.unpack_from('<IIif', data, offset)
            project.render_width = w
            project.render_height = h
            project.camera_fov = fov
            project.camera_info.fov = fov
            offset += 16
            # UI オプションフラグ (7 バイト)
            offset += 7
            project.log(f"出力解像度: {project.render_width}x{project.render_height}, カメラ視野角: {project.camera_fov:.1f}度")

            # 選択スロットおよびモデル数
            if offset + 2 <= file_size:
                selected_slot, model_count = struct.unpack_from('<BB', data, offset)
                offset += 2
                project.log(f"登録モデル数: {model_count}")

                # 各モデルの読み込み
                for m_idx in range(model_count):
                    if offset >= file_size:
                        break

                    # 複数モデル登録時、後続モデルのヘッダー先頭位置を正確に同期
                    if m_idx > 0:
                        synced_offset = _find_next_model_offset(data, offset, file_size)
                        if synced_offset != offset:
                            project.log(f"  [注記] モデルスロット {m_idx} の境界を再同期しました (オフセット: {offset} -> {synced_offset})")
                            offset = synced_offset

                    slot_byte = data[offset]
                    offset += 1

                    model_name, offset = _read_sjis_len_string(data, offset)
                    source_name, offset = _read_sjis_len_string(data, offset)
                    raw_path, offset = _read_fixed_sjis_string(data, offset, 0x100)

                    # ゴーストモデル除外ガード:
                    # パスもモデル名も空である場合、または有効な拡張子（.pmx/.pmd）を持たず名前も存在しない場合は無効データとして除外
                    cleaned_raw_path = raw_path.strip().replace('/', '\\')
                    ext_check = os.path.splitext(cleaned_raw_path)[1].lower()
                    has_valid_ext = ext_check in ['.pmx', '.pmd']
                    has_valid_name = bool(model_name and model_name.strip()) or bool(source_name and source_name.strip())

                    if not has_valid_ext and not has_valid_name:
                        # 無効なスロット・パースゴミはスキップ
                        project.log(f"  [注記] スロット {slot_byte} は未設定または無効なため除外しました")
                        continue

                    # 表示名
                    display_name = model_name or source_name
                    if not display_name and has_valid_ext:
                        display_name = os.path.splitext(os.path.basename(cleaned_raw_path))[0]

                    resolved_path, exists = resolve_pmm_file_path(cleaned_raw_path, filepath)
                    item = PmmItem(
                        kind="Model",
                        name=display_name,
                        raw_path=cleaned_raw_path,
                        resolved_path=resolved_path,
                        exists=exists,
                        slot=slot_byte,
                        source_name=source_name
                    )

                    # モデル内部構成要素 (ボーン群・モーフ群・タイムラインキーフレーム) の精密パース
                    try:
                        if offset < file_size:
                            bone_group_count = data[offset]
                            offset += 1

                            bone_count = struct.unpack_from('<i', data, offset)[0]
                            offset += 4
                            item.bone_count = max(bone_count, 0)

                            # 各ボーン名
                            for _ in range(min(item.bone_count, 4000)):
                                bname, offset = _read_sjis_len_string(data, offset)
                                item.bone_names.append(bname)

                            morph_count = struct.unpack_from('<i', data, offset)[0]
                            offset += 4
                            item.morph_count = max(morph_count, 0)

                            # 各モーフ名
                            for _ in range(min(item.morph_count, 4000)):
                                mname, offset = _read_sjis_len_string(data, offset)
                                item.morph_names.append(mname)

                            # IK数・セレクタ数
                            ik_count = struct.unpack_from('<i', data, offset)[0]
                            offset += 4 + (ik_count * 4)

                            selector_count = struct.unpack_from('<i', data, offset)[0]
                            offset += 4 + (selector_count * 4)

                            # comboSelIndex (1 byte)
                            offset += 1

                            # 状態ブロック (loadComplete: 1, selectedBone: 4, selectedMorphs: 16)
                            offset += 1 + 4 + 16

                            # displayGroups (1 byte flag + boneGroupCount bytes)
                            offset += 1 + bone_group_count

                            # boneListPos (4 bytes)
                            offset += 4

                            # maxFrame (4 bytes int32)
                            header_max_frame = struct.unpack_from('<i', data, offset)[0]
                            offset += 4
                            if header_max_frame > 0:
                                item.max_frame = header_max_frame

                            # 初期ボーンキーの読み込み (0フレーム目, boneCount 個)
                            dense_bone_keys = []
                            for b_i in range(item.bone_count):
                                if offset + bone_key_size > file_size:
                                    break
                                if is_v1:
                                    f_num, prev_idx, next_idx, ipl_bytes, px, py, pz, qx, qy, qz, qw, alloc = struct.unpack_from('<iii16s3f4fB', data, offset)
                                else:
                                    f_num, prev_idx, next_idx, ipl_bytes, px, py, pz, qx, qy, qz, qw, alloc, phys_dis = struct.unpack_from('<iii16s3f4fBB', data, offset)
                                offset += bone_key_size
                                dense_bone_keys.append({
                                    'frame': f_num,
                                    'prev': prev_idx,
                                    'next': next_idx,
                                    'pos': [px, py, pz],
                                    'rot': [qx, qy, qz, qw],
                                    'ipl': ipl_bytes,
                                    'alloc': alloc,
                                })

                            # タイムライン追加ボーンキーフレーム数
                            sparse_bone_keys = {}
                            if offset + 4 <= file_size:
                                added_bone_keys = struct.unpack_from('<i', data, offset)[0]
                                offset += 4
                                item.bone_key_count = max(added_bone_keys, 0)

                                # 追加ボーンキーのフレーム走査と抽出
                                for _ in range(min(item.bone_key_count, 500000)):
                                    if offset + 4 + bone_key_size > file_size:
                                        break
                                    frame_idx = struct.unpack_from('<i', data, offset)[0]
                                    offset += 4
                                    if is_v1:
                                        f_num, prev_idx, next_idx, ipl_bytes, px, py, pz, qx, qy, qz, qw, alloc = struct.unpack_from('<iii16s3f4fB', data, offset)
                                    else:
                                        f_num, prev_idx, next_idx, ipl_bytes, px, py, pz, qx, qy, qz, qw, alloc, phys_dis = struct.unpack_from('<iii16s3f4fBB', data, offset)
                                    offset += bone_key_size
                                    if f_num > item.max_frame:
                                        item.max_frame = f_num
                                    sparse_bone_keys[frame_idx] = {
                                        'frame': f_num,
                                        'prev': prev_idx,
                                        'next': next_idx,
                                        'pos': [px, py, pz],
                                        'rot': [qx, qy, qz, qw],
                                        'ipl': ipl_bytes,
                                        'alloc': alloc,
                                    }

                            # VmdMotion オブジェクトの構築（ボーンモーション）
                            if vmd_mod:
                                if not item.motion:
                                    item.motion = vmd_mod.VmdMotion()
                                    item.motion.model_name = item.name

                                bone_frames_dict = {}
                                for b_idx in range(len(item.bone_names)):
                                    b_name = item.bone_names[b_idx]
                                    if b_idx >= len(dense_bone_keys):
                                        break
                                    k_list = [dense_bone_keys[b_idx]]
                                    curr = dense_bone_keys[b_idx]['next']
                                    visited = set()
                                    while curr > 0 and curr not in visited and curr in sparse_bone_keys:
                                        visited.add(curr)
                                        k_list.append(sparse_bone_keys[curr])
                                        curr = sparse_bone_keys[curr]['next']

                                    vmd_bone_list = []
                                    for k in k_list:
                                        bf = vmd_mod.VmdBoneFrame()
                                        bf.name = b_name
                                        bf.frame = k['frame']
                                        bf.position = k['pos']
                                        bf.rotation = k['rot']
                                        raw_ipl = k['ipl']
                                        if len(raw_ipl) == 16:
                                            full_ipl = bytearray(64)
                                            for lane in range(4):
                                                for pt in range(4):
                                                    full_ipl[lane + pt * 4] = raw_ipl[lane * 4 + pt]
                                            bf.interpolation = bytes(full_ipl)
                                        else:
                                            bf.interpolation = getattr(vmd_mod, 'DEFAULT_BONE_INTERPOLATION', b'\x14' * 64)
                                        vmd_bone_list.append(bf)

                                    vmd_bone_list.sort(key=lambda x: x.frame)
                                    if vmd_bone_list:
                                        bone_frames_dict[b_name] = vmd_bone_list

                                item.motion.bone_frames = bone_frames_dict

                            # 初期モーフキーの読み込み (0フレーム目, morphCount 個)
                            dense_morph_keys = []
                            for m_i in range(item.morph_count):
                                if offset + morph_key_size > file_size:
                                    break
                                f_num, prev_idx, next_idx, val, alloc = struct.unpack_from('<iiifB', data, offset)
                                offset += morph_key_size
                                dense_morph_keys.append({
                                    'frame': f_num,
                                    'prev': prev_idx,
                                    'next': next_idx,
                                    'val': val,
                                    'alloc': alloc,
                                })

                            # タイムライン追加モーフキーフレーム数
                            sparse_morph_keys = {}
                            if offset + 4 <= file_size:
                                added_morph_keys = struct.unpack_from('<i', data, offset)[0]
                                offset += 4
                                item.morph_key_count = max(added_morph_keys, 0)

                                # 追加モーフキーのフレーム走査と抽出
                                for _ in range(min(item.morph_key_count, 200000)):
                                    if offset + 4 + morph_key_size > file_size:
                                        break
                                    frame_idx = struct.unpack_from('<i', data, offset)[0]
                                    offset += 4
                                    f_num, prev_idx, next_idx, val, alloc = struct.unpack_from('<iiifB', data, offset)
                                    offset += morph_key_size
                                    if f_num > item.max_frame:
                                        item.max_frame = f_num
                                    sparse_morph_keys[frame_idx] = {
                                        'frame': f_num,
                                        'prev': prev_idx,
                                        'next': next_idx,
                                        'val': val,
                                        'alloc': alloc,
                                    }

                            # VmdMotion オブジェクトの構築（モーフモーション）
                            if vmd_mod and item.motion:
                                morph_frames_dict = {}
                                for m_idx in range(len(item.morph_names)):
                                    m_name = item.morph_names[m_idx]
                                    if m_idx >= len(dense_morph_keys):
                                        break
                                    k_list = [dense_morph_keys[m_idx]]
                                    curr = dense_morph_keys[m_idx]['next']
                                    visited = set()
                                    while curr > 0 and curr not in visited and curr in sparse_morph_keys:
                                        visited.add(curr)
                                        k_list.append(sparse_morph_keys[curr])
                                        curr = sparse_morph_keys[curr]['next']

                                    vmd_morph_list = []
                                    for k in k_list:
                                        mf = vmd_mod.VmdMorphFrame()
                                        mf.name = m_name
                                        mf.frame = k['frame']
                                        mf.weight = max(0.0, min(1.0, float(k['val'])))
                                        vmd_morph_list.append(mf)

                                    vmd_morph_list.sort(key=lambda x: x.frame)
                                    if vmd_morph_list:
                                        morph_frames_dict[m_name] = vmd_morph_list

                                item.motion.morph_frames = morph_frames_dict

                            # 後続データ（表示枠キーフレーム、物理設定、ポーズ状態テーブル等）のスキップ
                            # 表示・IK・外部親初期キーフレーム
                            disp_key_len = 14 + ik_count + (selector_count * 8)
                            offset += disp_key_len

                            # タイムライン追加表示キーフレーム走査
                            if offset + 4 <= file_size:
                                added_disp_keys = struct.unpack_from('<i', data, offset)[0]
                                offset += 4
                                if added_disp_keys > 0:
                                    added_disp_keys = min(added_disp_keys, 500000)
                                    for _ in range(added_disp_keys):
                                        if offset + 4 > file_size:
                                            break
                                        disp_frame = struct.unpack_from('<i', data, offset)[0]
                                        offset += 4 + disp_key_len
                                        if disp_frame > item.max_frame:
                                            item.max_frame = disp_frame

                            # ボーン物理状態および選択テーブル
                            offset += item.bone_count * 31

                            # モーフ現在値テーブル
                            offset += item.morph_count * 4

                            # IK有効状態テーブル
                            offset += ik_count * 1

                            # 外部親・セレクタ状態テーブル
                            offset += selector_count * 16

                            # モデル末尾フラグ群
                            offset += 7

                            # モーション / ポーズ判定の確定
                            total_keys = item.bone_key_count + item.morph_key_count
                            if total_keys > 0 or item.max_frame > 0:
                                item.has_motion = True
                                item.motion_type = f"モーション ({item.max_frame:,}F)"
                            elif item.bone_count > 0 or item.morph_count > 0:
                                item.has_motion = True
                                item.motion_type = "ポーズデータ (1F)"
                            else:
                                item.has_motion = False
                                item.motion_type = "なし"

                    except Exception as parse_m_err:
                        project.log(f"  [モデル {slot_byte}] 構成解析注記: {parse_m_err}")

                    # モデル照合の実行
                    _verify_model_item(item, filepath)

                    project.models.append(item)
                    status_text = "存在" if exists else "見つかりません"
                    project.log(f"  [モデル {slot_byte}] '{item.name}' ({status_text}, {item.match_status}, {item.motion_type}): {resolved_path or cleaned_raw_path}")

                # 全モデル完了後、カメラトラックのバイナリ解析
                offset = _parse_camera_track(data, offset, file_size, is_v1, project)

    except Exception as e:
        project.log(f"構造化パーサー注記: {e}")

    # バイナリ全体からのアセットパス補完走査 (セーフティネット)
    _scan_and_merge_assets(data, project, filepath)

    # カメラトラックおよびプロジェクト全体設定の解析
    _parse_camera_and_timeline(data, project)

    # 各モデルの照合完了をログに記録
    project.log(f"照合完了モデル数: {len(project.models)} 体")
    for m in project.models:
        if m.match_detail:
            project.log(f"  - {m.name}: {m.match_status} ({m.match_detail}) / 判定: {m.motion_type} (ボーンキー: {m.bone_key_count}, モーフキー: {m.morph_key_count})")

    if project.camera_info.has_motion:
        project.log(f"カメラ判定: {project.camera_info.motion_type} (キー数: {project.camera_info.key_count}, 最大 {project.camera_info.max_frame}F)")
    else:
        project.log(f"カメラ判定: {project.camera_info.motion_type}")

    if project.last_registered_frame > 0:
        project.log(f"プロジェクト最終登録フレーム: {project.last_registered_frame:,}F")

    # 重複・未検出の過去残骸アイテム（旧データ）の判定
    _mark_old_data(project)

    project.log("PMM 解析処理が完了しました。")
    return project


def _parse_camera_track(data: bytes, offset: int, file_size: int, is_v1: bool, project: PmmProject) -> int:
    """
    全モデルセクション直後のカメラトラック（初期キーおよび追加スパースキー）をパースし、
    project.camera_motion (VmdMotion) を構築します。
    """
    if offset >= file_size or not vmd_mod:
        return offset

    cam_key_size = 70 if is_v1 else 78
    if offset + cam_key_size > file_size:
        return offset

    try:
        def read_cam_record(pos):
            # PMMバイナリ仕様: dist の直後は eye[3](注視点位置: tx, ty, tz)、続いて target[3](回転角度: rx, ry, rz)
            if is_v1:
                f_num, prev_idx, next_idx, dist, tx, ty, tz, rx, ry, rz, ipl, pers, fov, sel = struct.unpack_from(
                    '<IIIf3f3f24sBiB', data, pos
                )
                pm, pb = -1, -1
            else:
                f_num, prev_idx, next_idx, dist, tx, ty, tz, rx, ry, rz, pm, pb, ipl, pers, fov, sel = struct.unpack_from(
                    '<IIIf3f3fii24sBiB', data, pos
                )
            return {
                'frame': f_num,
                'prev': prev_idx,
                'next': next_idx,
                'dist': dist,
                'rot': [rx, ry, rz],
                'pos': [tx, ty, tz],
                'parent_model': pm,
                'parent_bone': pb,
                'ipl': ipl,
                'perspective': pers == 1,
                'fov': fov,
                'selected': sel == 1
            }

        initial_cam = read_cam_record(offset)
        offset += cam_key_size

        camera_frames = []
        cf0 = vmd_mod.VmdCameraFrame()
        cf0.frame = initial_cam['frame']
        cf0.distance = initial_cam['dist']
        cf0.position = initial_cam['pos']
        cf0.rotation = initial_cam['rot']
        cf0.fov = initial_cam['fov'] if initial_cam['fov'] > 0 else int(round(project.camera_fov or 30))
        cf0.perspective = initial_cam['perspective']
        cf0.interpolation = initial_cam['ipl']
        camera_frames.append(cf0)

        sparse_keys = {}
        if offset + 4 <= file_size:
            cnt = struct.unpack_from('<i', data, offset)[0]
            offset += 4
            project.camera_info.key_count = max(cnt + 1, 1)

            for _ in range(min(cnt, 200000)):
                if offset + 4 + cam_key_size > file_size:
                    break
                frame_idx = struct.unpack_from('<i', data, offset)[0]
                offset += 4
                ck = read_cam_record(offset)
                offset += cam_key_size

                cf = vmd_mod.VmdCameraFrame()
                cf.frame = ck['frame']
                cf.distance = ck['dist']
                cf.position = ck['pos']
                cf.rotation = ck['rot']
                cf.fov = ck['fov'] if ck['fov'] > 0 else int(round(project.camera_fov or 30))
                cf.perspective = ck['perspective']
                cf.interpolation = ck['ipl']
                camera_frames.append(cf)
                if ck['frame'] > project.camera_info.max_frame:
                    project.camera_info.max_frame = ck['frame']

        camera_frames.sort(key=lambda x: x.frame)
        if camera_frames:
            project.camera_motion = vmd_mod.VmdMotion()
            project.camera_motion.camera_frames = camera_frames
            project.camera_motion.max_frame = max(cf.frame for cf in camera_frames)

            has_valid_anim = len(camera_frames) > 1 or project.camera_motion.max_frame > 0
            if has_valid_anim:
                project.camera_info.has_motion = True
                project.camera_info.motion_type = f"カメラモーション ({project.camera_motion.max_frame:,}F, {len(camera_frames)}キー)"
            else:
                project.camera_info.has_motion = False
                project.camera_info.motion_type = f"固定カメラ設定 (FOV {cf0.fov}度)"

            project.log(f"カメラトラック解析完了: {len(camera_frames)} キーフレーム (最大 {project.camera_motion.max_frame}F)")

    except Exception as e:
        project.log(f"カメラトラック解析注記: {e}")

    return offset


def _parse_camera_and_timeline(data: bytes, project: PmmProject):
    """
    PMM 内のカメラトラックおよびプロジェクト全体のタイムライン登録フレームを解析します。
    """
    try:
        project.camera_info.fov = project.camera_fov or 30.0

        max_model_frame = max([m.max_frame for m in project.models], default=0)
        max_cam_frame = project.camera_motion.max_frame if getattr(project, 'camera_motion', None) else 0
        total_max_frame = max(max_model_frame, max_cam_frame)
        project.last_registered_frame = total_max_frame

        if getattr(project, 'camera_motion', None) and len(project.camera_motion.camera_frames) > 1:
            project.camera_info.has_motion = True
            project.camera_info.max_frame = max_cam_frame
            project.camera_info.motion_type = f"カメラモーション (最大 {max_cam_frame:,}F)"
        elif max_model_frame > 0 and not getattr(project, 'camera_motion', None):
            project.camera_info.has_motion = True
            project.camera_info.max_frame = max_model_frame
            project.camera_info.motion_type = f"カメラモーション (最大 {max_model_frame:,}F)"
        elif not project.camera_info.has_motion:
            project.camera_info.has_motion = False
            project.camera_info.motion_type = f"固定カメラ (画角 {project.camera_info.fov:.1f}度)"

    except Exception:
        pass


def _scan_and_merge_assets(data: bytes, project: PmmProject, pmm_filepath: str):
    """
    バイナリ全体からファイルパス（.pmx, .pmd, .x, .wav, .avi 等）を走査し、
    未登録のアイテムを補完します。
    """
    existing_model_basenames = {
        os.path.basename(m.raw_path).lower() for m in project.models if m.raw_path
    }
    existing_acc_basenames = {
        os.path.basename(a.raw_path).lower() for a in project.accessories if a.raw_path
    }

    extensions = [b".pmx", b".pmd", b".x", b".wav", b".avi", b".bmp", b".png", b".jpg"]

    for ext in extensions:
        start = 0
        while True:
            idx = data.lower().find(ext, start)
            if idx == -1:
                break
            start = idx + len(ext)

            left = idx
            while left > 0 and data[left - 1] != 0 and data[left - 1] >= 0x20:
                left -= 1
                if idx - left > 260:
                    break

            right = idx + len(ext)
            while right < len(data) and data[right] != 0 and data[right] >= 0x20:
                right += 1
                if right - idx > 60:
                    break

            raw_candidate = data[left:right]
            try:
                candidate_str = raw_candidate.decode('cp932', errors='ignore')
            except Exception:
                candidate_str = raw_candidate.decode('utf-8', errors='ignore')

            candidate_str = _clean_path_candidate(candidate_str)
            if not candidate_str:
                continue

            ext_lower = os.path.splitext(candidate_str)[1].lower()
            base_lower = os.path.basename(candidate_str).lower()

            # 実在確認
            resolved, exists = resolve_pmm_file_path(candidate_str, pmm_filepath)

            # 妥当性判定
            if not _is_valid_path_candidate(candidate_str, ext_lower, exists):
                continue

            if ext_lower in ['.pmx', '.pmd']:
                if base_lower not in existing_model_basenames:
                    existing_model_basenames.add(base_lower)
                    item_name = os.path.splitext(os.path.basename(candidate_str))[0]
                    item = PmmItem(
                        kind="Model",
                        name=item_name,
                        raw_path=candidate_str,
                        resolved_path=resolved,
                        exists=exists,
                        slot=len(project.models),
                        source_name=item_name
                    )
                    _verify_model_item(item, pmm_filepath)
                    project.models.append(item)
                    status_text = "存在" if exists else "見つかりません"
                    project.log(f"  [検出モデル] '{item.name}' ({status_text}, {item.match_status}): {resolved or candidate_str}")

            elif ext_lower == '.x':
                item_name = os.path.splitext(os.path.basename(candidate_str))[0]

                # 既に登録されている実在アクセサリと照合し、先頭にゴミ文字が付いた未検出候補を除外
                is_garbage = False
                if not exists:
                    for a in project.accessories:
                        if a.exists and a.name:
                            if item_name.endswith(a.name) and len(item_name) > len(a.name) and (len(item_name) - len(a.name) <= 3):
                                is_garbage = True
                                project.log(f"  [除外] バイナリゴミ文字が付着したアクセサリ候補を除外しました: '{item_name}' (正規: '{a.name}')")
                                break
                if is_garbage:
                    continue

                if base_lower not in existing_acc_basenames:
                    existing_acc_basenames.add(base_lower)
                    item = PmmItem(
                        kind="Accessory",
                        name=item_name,
                        raw_path=candidate_str,
                        resolved_path=resolved,
                        exists=exists,
                        slot=len(project.accessories)
                    )
                    item.match_status = "存在" if exists else "未検出"
                    project.accessories.append(item)
                    status_text = "存在" if exists else "見つかりません"
                    project.log(f"  [アクセサリ] '{item.name}' ({status_text}): {resolved or candidate_str}")

            elif ext_lower == '.wav':
                if not project.audio:
                    item_name = os.path.splitext(os.path.basename(candidate_str))[0]
                    project.audio = PmmItem(
                        kind="Audio",
                        name=item_name,
                        raw_path=candidate_str,
                        resolved_path=resolved,
                        exists=exists
                    )
                    project.audio.match_status = "存在" if exists else "未検出"
                    status_text = "存在" if exists else "見つかりません"
                    project.log(f"  [音声WAV] '{item_name}' ({status_text}): {resolved or candidate_str}")

            elif ext_lower == '.avi':
                if not project.background_avi:
                    project.background_avi = PmmItem(
                        kind="Background (AVI)",
                        name=os.path.basename(candidate_str),
                        raw_path=candidate_str,
                        resolved_path=resolved,
                        exists=exists
                    )
                    project.log(f"  [背景動画] {candidate_str}")

            elif ext_lower in ['.bmp', '.png', '.jpg']:
                if not project.background_pic and ("bg" in base_lower or "back" in base_lower or "haikei" in base_lower):
                    project.background_pic = PmmItem(
                        kind="Background (Image)",
                        name=os.path.basename(candidate_str),
                        raw_path=candidate_str,
                        resolved_path=resolved,
                        exists=exists
                    )
                    project.log(f"  [背景静止画] {candidate_str}")

    # 事後フィルタ: 実在する正規アセットに直前のバイナリゴミ文字が付着した未検出アイテムを安全に除外
    valid_acc_names = [a.name for a in project.accessories if a.exists and a.name]
    cleaned_accs = []
    for a in project.accessories:
        if not a.exists and a.name:
            is_trash = False
            for v_name in valid_acc_names:
                if a.name.endswith(v_name) and len(a.name) > len(v_name) and (len(a.name) - len(v_name) <= 3):
                    is_trash = True
                    project.log(f"  [除外] バイナリゴミ文字が付着した未検出アクセサリを除外しました: '{a.name}' (正規: '{v_name}')")
                    break
            if is_trash:
                continue
        cleaned_accs.append(a)
    project.accessories = cleaned_accs

    valid_model_names = [m.name for m in project.models if m.exists and m.name]
    cleaned_models = []
    for m in project.models:
        if not m.exists and m.name:
            is_trash = False
            for v_name in valid_model_names:
                if m.name.endswith(v_name) and len(m.name) > len(v_name) and (len(m.name) - len(v_name) <= 3):
                    is_trash = True
                    project.log(f"  [除外] バイナリゴミ文字が付着した未検出モデルを除外しました: '{m.name}' (正規: '{v_name}')")
                    break
            if is_trash:
                continue
        cleaned_models.append(m)
    project.models = cleaned_models
