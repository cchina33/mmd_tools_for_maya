# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - Maya用 MMD (PMX/PMD/X) 統合ツールセット
Author: Hina33
"""

import sys
from . import gui
from .gui import Natanglak, MmdMayaMainWindow, show_ui

def yamikuma():
    """従来の起動関数（後方互換性用）"""
    return show_ui()
