# -*- coding: utf-8 -*-
"""
converters.pmd2pmx - PMDからPMXへの自動変換エンジン

旧形式である MMD PMD モデルファイルを解析し、
最新の PMX 2.0 形式ファイルへと変換・保存するコンバータモジュールです。
頂点・面・材質・スフィアマップ・ボーン・IK・モーフに加え、
剛体およびジョイント情報も保持して出力します。
"""

import os
import sys

try:
    from ..mmd_core import pmd, pmx
except Exception:
    try:
        from mmd_core import pmd, pmx
    except Exception:
        import pmd
        import pmx


def convert_pmd_to_pmx(pmd_path, pmx_path=None):
    """
    指定された PMD ファイルを PMX 形式へ変換し、ディスクへ保存します。

    引数:
        pmd_path (str): 変換対象の PMD ファイルパス。
        pmx_path (str, optional): 出力先の PMX ファイルパス。省略時は PMD と同一フォルダ・同名拡張子違い。

    戻り値:
        str: 生成された PMX ファイルの絶対パス。
    """
    if not os.path.exists(pmd_path):
        raise FileNotFoundError(f"変換対象の PMD ファイルが見つかりません: {pmd_path}")

    # 出力先パスの自動決定
    if not pmx_path:
        base_name, _ = os.path.splitext(pmd_path)
        pmx_path = base_name + ".pmx"

    abs_pmd_path = os.path.abspath(pmd_path)
    abs_pmx_path = os.path.abspath(pmx_path)

    print(f"[PMD2PMX] PMDファイルの読み込みを開始: {os.path.basename(abs_pmd_path)}")
    model = pmd.load2pmx(abs_pmd_path)

    # モデルの基本情報ログ出力
    print(f"[PMD2PMX] モデル解析が完了しました:")
    print(f"  - モデル名: {model.name}")
    print(f"  - 頂点数: {len(model.vertices):,} / 面数: {len(model.faces):,}")
    print(f"  - ボーン数: {len(model.bones):,} / 材質数: {len(model.materials):,}")
    print(f"  - モーフ数: {len(model.morphs):,} / 剛体数: {len(model.rigid_bodies):,} / ジョイント数: {len(model.joints):,}")

    # PMX ファイルへの書き出し保存
    print(f"[PMD2PMX] PMXファイルへの書き出しを実行中: {os.path.basename(abs_pmx_path)}")
    pmx.save(abs_pmx_path, model)

    if not os.path.exists(abs_pmx_path):
        raise IOError(f"PMX ファイルの書き出しに失敗しました: {abs_pmx_path}")

    print(f"[PMD2PMX] 正常に変換・保存が完了しました: {abs_pmx_path}")
    return abs_pmx_path
