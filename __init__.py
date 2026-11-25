# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - Maya用 MMD (PMX/PMD/X) 統合ツールセット
Author: Hina33
"""

__version__ = "1.0.6"
__author__ = "Hina33"

import os
import sys

# パッケージ内ディレクトリを sys.path に確実に追加
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
for _sub in ["ui", "maya_converters", "mmd_parser", "physics", "plugins", "converters", "mmd_core", "asset"]:
    _p = os.path.join(_pkg_dir, _sub)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# サブパッケージのインポート
from . import ui
from . import maya_converters
from . import mmd_parser
try:
    from . import physics
except Exception:
    physics = None
try:
    from . import plugins
except Exception:
    plugins = None

# 後方互換エイリアスとモジュールマッピング
converters = maya_converters
mmd_core = mmd_parser
sys.modules["mmd_tools_for_maya.converters"] = maya_converters
sys.modules["mmd_tools_for_maya.mmd_core"] = mmd_parser
sys.modules["converters"] = maya_converters
sys.modules["mmd_core"] = mmd_parser

from .ui.gui import MmdMayaMainWindow, show_ui, close_existing_ui, Natanglak
from .ui.advanced_dict_dialog import AdvancedDictDialog, show_advanced_dict_dialog
from .ui.material_protect_dialog import MaterialProtectDialog, show_material_protect_dialog
from .ui.user_dict_dialog import UserDictDialog, show_user_dict_dialog

# 後方互換エクスポート (以前のルート直下モジュール名でのアクセスをサポート)
from .maya_converters import pmxpaimaya
from .maya_converters import mayapaipmx
from .maya_converters import vmdpaimaya
from .maya_converters import vmd_analyzer
from .maya_converters import bullet_builder
from .ui import gui

def yamikuma():
    """従来の起動関数（後方互換性用）"""
    return show_ui()

__all__ = [
    "ui",
    "maya_converters",
    "mmd_parser",
    "converters",
    "mmd_core",
    "physics",
    "plugins",
    "MmdMayaMainWindow",
    "show_ui",
    "close_existing_ui",
    "AdvancedDictDialog",
    "show_advanced_dict_dialog",
    "MaterialProtectDialog",
    "show_material_protect_dialog",
    "UserDictDialog",
    "show_user_dict_dialog",
    "pmxpaimaya",
    "mayapaipmx",
    "vmdpaimaya",
    "vmd_analyzer",
    "bullet_builder",
    "gui",
    "yamikuma"
]
