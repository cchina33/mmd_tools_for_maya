# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - GitHub Releases用 ZIPアーカイブ自動作成スクリプト

Maya の標準 plug-ins ディレクトリにそのまま展開可能な構造で、
不要な中間生成物やキャッシュを除外したクリーンな配布用 ZIP を生成します。
アーカイブ内パスおよびテキストファイル内にユーザー名が含まれていないかを自動検査します。
"""

import os
import sys
import re
import getpass
import zipfile
from pathlib import Path

# テキストファイル検査対象の拡張子
TEXT_EXTENSIONS = {
    ".py", ".md", ".txt", ".json", ".cs", ".cpp", ".h",
    ".cmake", ".bat", ".ps1", ".yaml", ".yml", ".xml",
    ".ini", ".cfg", ".toml", ".hlsl", ".fx"
}


def get_version(root_dir: Path) -> str:
    """README.md または gui.py から現在のバージョン番号を取得"""
    readme_path = root_dir / "README.md"
    if readme_path.exists():
        try:
            content = readme_path.read_text(encoding="utf-8")
            match = re.search(r"MMD Tools for Maya \((v[\d\.]+)\)", content)
            if match:
                return match.group(1)
            match_sub = re.search(r"\*\*(v[\d\.]+)\*\*", content)
            if match_sub:
                return match_sub.group(1)
        except Exception:
            pass
    return "v1.0.4"


def get_forbidden_keywords() -> list:
    """検査対象のユーザー名・個人情報キーワードリストを取得"""
    keywords = set()

    # ログインユーザー名の自動取得
    user = os.environ.get("USERNAME") or os.environ.get("USER")
    if not user:
        try:
            user = getpass.getuser()
        except Exception:
            pass
    if user and len(user.strip()) >= 3:
        keywords.add(user.strip())

    # ユーザープロファイルフォルダ名の取得
    userprofile = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if userprofile:
        prof_name = Path(userprofile).name
        if prof_name and len(prof_name.strip()) >= 3:
            keywords.add(prof_name.strip())

    return [k for k in keywords if k]


def scan_file_content_for_keywords(file_path: Path, keywords: list) -> list:
    """テキストファイルの内容に対象キーワードが含まれていないか検査"""
    if file_path.suffix.lower() not in TEXT_EXTENSIONS:
        return []

    violations = []
    content = None
    for enc in ("utf-8", "cp932", "shift_jis", "utf-16"):
        try:
            content = file_path.read_text(encoding=enc)
            break
        except Exception:
            continue

    if content is None:
        return []

    lines = content.splitlines()
    for line_idx, line in enumerate(lines, start=1):
        line_lower = line.lower()
        for kw in keywords:
            if kw.lower() in line_lower:
                violations.append((line_idx, kw, line.strip()))

    return violations


def should_exclude(rel_path_str: str) -> bool:
    """除外対象ファイル・ディレクトリの判定"""
    # Windows/POSIX パス区切りの正規化
    p = rel_path_str.replace("\\", "/")
    parts = p.split("/")
    filename = parts[-1]

    # バージョン管理・開発ドキュメント・設定
    if any(part in (".git", "ai-task-docs", ".vs", ".vscode", ".idea") for part in parts):
        return True
    if filename in (".gitignore", ".gitattributes", "package_release.py", "package_release.bat"):
        return True

    # スクラッチ・バックアップ作業領域
    if any(part in ("_old", "scratch", "_maya_mmd_tools-main", "_boneDynamicsNode-0.5.0") for part in parts):
        return True
    if "_old_" in filename:
        return True

    # テスト・サンプルメディアファイル
    if any(part in ("vmd", "wav", "tes_model", "tests") for part in parts):
        return True
    if any(filename.lower().endswith(ext) for ext in (".pmx", ".pmd", ".x")):
        return True

    # Python キャッシュ
    if any(part == "__pycache__" for part in parts):
        return True
    if any(filename.endswith(ext) for ext in (".pyc", ".pyo", ".pyd")):
        return True

    # Maya 一時ファイル・OS 生成ファイル
    if any(part == ".mayaSwatches" for part in parts):
        return True
    if any(filename.endswith(ext) for ext in (".swp", ".lock", ".log", ".bak")):
        return True
    if filename in (".DS_Store", "Thumbs.db", "desktop.ini"):
        return True

    # ローカルキャッシュ・一時出力データ
    if filename == "last_imported_structure.json":
        return True
    if any(part in ("User_pmx_data", "vmd_bake_data") for part in parts):
        return True
    if parts[0] == "asset":
        if filename.endswith(".txt") or filename == "bone_motion_export.json":
            return True

    # C# (.NET) 中間生成物
    if any(part.lower() == "obj" for part in parts):
        return True
    if "bin/debug" in p.lower():
        return True
    if filename.endswith((".sourcelink.json", ".FileListAbsolute.txt")):
        return True

    # C++ ビルド中間ファイル
    if any(part.startswith("build") or part in ("x64", "CMakeFiles") for part in parts):
        return True
    if any(filename.endswith(ext) for ext in (
        ".obj", ".lib", ".exp", ".ilk", ".ninja", ".tlog", ".recipe",
        ".VC.db", ".sln.docstates", ".suo", ".user", ".userprefs"
    )):
        return True
    if filename.startswith(".ninja_"):
        return True

    # デバッグシンボル（Release 配下であっても除外）
    if filename.endswith(".pdb"):
        return True

    return False


def build_release_zip():
    """配布用 ZIP アーカイブを生成"""
    script_dir = Path(__file__).resolve().parent
    parent_dir = script_dir.parent

    # プラグインローダーの存在確認
    plugin_loader = parent_dir / "mmd_tools_for_maya_plugin.py"
    if not plugin_loader.exists():
        print(f"[エラー] プラグインローダーが見つかりません: {plugin_loader}")
        sys.exit(1)

    version = get_version(script_dir)
    output_dir = script_dir / "dist"
    output_dir.mkdir(exist_ok=True)
    zip_filename = f"MMD_Tools_for_Maya_{version}.zip"
    zip_path = output_dir / zip_filename

    print("=" * 70)
    print(" MMD Tools for Maya - リリース用アーカイブ作成")
    print(f" バージョン: {version}")
    print(f" 出力先    : {zip_path}")
    print("=" * 70)

    # 収集対象ファイルのリストアップ
    target_files = []

    # プラグインローダー
    target_files.append((plugin_loader, "mmd_tools_for_maya_plugin.py"))

    # ツール本体ディレクトリ内のファイル
    for root, dirs, files in os.walk(script_dir):
        rel_root = Path(root).relative_to(script_dir)

        for file in files:
            file_path = Path(root) / file
            rel_file_path = rel_root / file if str(rel_root) != "." else Path(file)
            rel_str = str(rel_file_path)

            if "dist" in rel_file_path.parts:
                continue

            if should_exclude(rel_str):
                continue

            arcname = f"mmd_tools_for_maya/{rel_str.replace(os.sep, '/')}"
            target_files.append((file_path, arcname))

    # ユーザー名・個人情報キーワードのセキュリティ事前検査
    forbidden_keywords = get_forbidden_keywords()
    print(f"セキュリティ検査を実行中... (検査対象ファイル数: {len(target_files)} 件)")

    path_violations = []
    content_violations = []

    for file_path, arcname in target_files:
        # アーカイブ内パスの検査
        arcname_lower = arcname.lower()
        for kw in forbidden_keywords:
            if kw.lower() in arcname_lower:
                path_violations.append((arcname, kw))

        # ファイル内容の検査
        violations = scan_file_content_for_keywords(file_path, forbidden_keywords)
        for line_no, kw, line_text in violations:
            content_violations.append((arcname, line_no, kw, line_text))

    # 違反が検出された場合は処理を中断
    if path_violations or content_violations:
        print("\n" + "!" * 70)
        print("【セキュリティ警告】ユーザー名が検出されたため処理を中断します！")
        print("GitHubおよびリリースアーカイブへの混入を防ぐため、ZIP生成を中止しました。")
        print("!" * 70)

        if path_violations:
            print("\n[パス・ファイル名における検出]:")
            for arc, kw in path_violations:
                print(f"  ・パス: {arc} (キーワード: {kw})")

        if content_violations:
            print("\n[ファイル内容における検出]:")
            for arc, line_no, kw, line_text in content_violations:
                print(f"  ・ファイル: {arc} ({line_no}行目)")
                print(f"    行内容  : {line_text}")

        print("\n" + "!" * 70)
        sys.exit(1)

    print("セキュリティ検査に合格しました（ユーザー名の混入はありません）。")
    print("-" * 70)

    # ZIP アーカイブの作成
    included_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path, arcname in target_files:
            zf.write(file_path, arcname)
            included_count += 1

    file_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"アーカイブ作成が終了しました。")
    print(f"・格納ファイル数: {included_count} 件")
    print(f"・ファイルサイズ: {file_size_mb:.2f} MB")
    print(f"・生成ファイル  : {zip_path}")
    print("=" * 70)


if __name__ == "__main__":
    build_release_zip()
