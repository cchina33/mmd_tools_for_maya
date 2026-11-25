# -*- coding: utf-8 -*-
"""
Bullet Physics 2.83.7 MMD 物理演算エンジンパッケージ
ライセンス: zlib license (詳細は bullet_engine/LICENSE を参照)
"""

from .bullet_wrapper import BulletEngineWrapper

def is_available():
    """BulletエンジンおよびDLLが利用可能か検証"""
    import os
    dll_path = os.path.join(os.path.dirname(__file__), "bin", "mmd_bullet.dll")
    return os.path.exists(dll_path)
