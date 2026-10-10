# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - Maya用 MMD (PMX/PMD/X) 統合ツールセット
Author: Hina33
"""

__version__ = "1.0.2"
__author__ = "Hina33"

import os
import sys

# パッケージ内ディレクトリを sys.path に安全に追加
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
for _sub in ["ui", "converters", "mmd_core", "bullet_engine", "cpp_engine", "asset"]:
    _p = os.path.join(_pkg_dir, _sub)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# サブパッケージのインポート
from . import ui
from . import converters
from .ui.gui import MmdMayaMainWindow, show_ui, close_existing_ui, Natanglak
from .ui.advanced_dict_dialog import AdvancedDictDialog, show_advanced_dict_dialog

# 後方互換エクスポート (以前のルート直下モジュール名でのアクセスをサポート)
from .converters import pmxpaimaya
from .converters import mayapaipmx
from .converters import vmdpaimaya
from .converters import vmd_analyzer
from .converters import bullet_builder
from .ui import gui

def yamikuma():
    """従来の起動関数（後方互換性用）"""
    return show_ui()

__all__ = [
    "ui",
    "converters",
    "MmdMayaMainWindow",
    "show_ui",
    "close_existing_ui",
    "AdvancedDictDialog",
    "show_advanced_dict_dialog",
    "pmxpaimaya",
    "mayapaipmx",
    "vmdpaimaya",
    "vmd_analyzer",
    "bullet_builder",
    "gui",
    "yamikuma"
]
