# -*- coding: utf-8 -*-
"""
MMD Tools for Maya プラグインエントリポイント
plug-ins 直下配置用ローダー

Maya のプラグインマネージャからロードされた際、
隣接する mmd_tools_for_maya フォルダを検索パスに追加し、
Mayaメインメニューバーに「MMD」メニューを追加します。
"""

import os
import sys
import maya.cmds as mc
import maya.mel as mel
import maya.api.OpenMaya as om

# プラグイン基本情報
PLUGIN_NAME = "MMD Tools for Maya"
PLUGIN_VENDOR = "Hina33"
PLUGIN_VERSION = "1.0.1"
MENU_NAME = "mmd_tools_for_maya_main_menu"
MENU_LABEL = "MMD"

# キャッシュ用ディレクトリパス
_cached_plugin_dir = None

def maya_useNewAPI():
    """Maya API 2.0 を使用することをMayaに伝えます。"""
    pass

def _get_plugin_dir(plugin_fn=None):
    """
    プラグインが存在するディレクトリパスを安全に取得します。
    Mayaのプラグインローダー環境で __file__ が定義されていない場合にも対応します。
    """
    global _cached_plugin_dir
    if _cached_plugin_dir and os.path.isdir(_cached_plugin_dir):
        return _cached_plugin_dir

    # 1. MFnPlugin インスタンスから取得（最も確実）
    if plugin_fn is not None:
        try:
            load_path = plugin_fn.loadPath()
            if load_path and os.path.isdir(load_path):
                _cached_plugin_dir = load_path
                return _cached_plugin_dir
        except Exception:
            pass

    # 2. globals() の __file__ を安全に確認
    file_path = globals().get("__file__")
    if file_path:
        _cached_plugin_dir = os.path.dirname(os.path.abspath(file_path))
        return _cached_plugin_dir

    # 3. sys.modules から確認
    mod = sys.modules.get(__name__)
    if mod and hasattr(mod, "__file__") and mod.__file__:
        _cached_plugin_dir = os.path.dirname(os.path.abspath(mod.__file__))
        return _cached_plugin_dir

    # 4. Mayaのユーザープラグインフォルダ（フォールバック）
    try:
        maya_ver = mc.about(version=True) if hasattr(mc, "about") else "2025"
    except Exception:
        maya_ver = "2025"

    user_docs = os.path.expanduser("~")
    fallback_path = os.path.join(user_docs, "Documents", "maya", str(maya_ver), "plug-ins")
    if os.path.isdir(fallback_path):
        _cached_plugin_dir = fallback_path
        return _cached_plugin_dir

    _cached_plugin_dir = os.path.abspath(".")
    return _cached_plugin_dir

def _ensure_sys_path(plugin_fn=None):
    """プラグイン本体のフォルダを sys.path に追加します。"""
    current_dir = _get_plugin_dir(plugin_fn)
    candidates = [
        os.path.join(current_dir, "mmd_tools_for_maya"),
        os.path.join(current_dir, "mmd_tools_for_maya", "ui"),
        os.path.join(current_dir, "mmd_tools_for_maya", "converters"),
        os.path.join(current_dir, "mmd_tools_for_maya", "plug-ins"),
        current_dir,
    ]
    for p in candidates:
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)

def create_menu():
    """MayaのメインウィンドウメニューバーにMMDメニューを作成します。"""
    delete_menu()
    
    # Mayaメインウィンドウ名を取得
    main_window = mel.eval('$tmp = $gMainWindow;')
    if not main_window:
        main_window = "MayaWindow"
        
    if not mc.window(main_window, exists=True):
        return

    # メニュー作成
    mc.menu(MENU_NAME, label=MENU_LABEL, parent=main_window, tearOff=True)
    
    # メニューアイテム追加
    mc.menuItem(
        label="MMD Tools for Maya",
        command=lambda *args: on_open_gui(),
        annotation="PMX/PMDのインポート・エクスポート・物理演算ツールを開きます"
    )
    mc.menuItem(
        label="高度なユーザー辞書・マテリアル設定 (上級者向け)...",
        command=lambda *args: on_open_advanced_dict(),
        annotation="マテリアル保護キーワード、Toon除外設定、ボーン辞書、名称変換ルールを編集します (上級者向け)"
    )
    mc.menuItem(divider=True)
    mc.menuItem(
        label="プラグインについて (About)",
        command=lambda *args: on_show_about(),
        annotation="MMD Tools for Maya の情報を表示します"
    )

def on_open_advanced_dict():
    """高度なユーザー辞書・マテリアル設定ダイアログを開くコールバック関数"""
    _ensure_sys_path()
    try:
        try:
            from mmd_tools_for_maya.ui.advanced_dict_dialog import show_advanced_dict_dialog
            show_advanced_dict_dialog()
            return
        except Exception:
            pass

        try:
            from mmd_tools_for_maya.advanced_dict_dialog import show_advanced_dict_dialog
            show_advanced_dict_dialog()
            return
        except Exception:
            pass

        import advanced_dict_dialog
        advanced_dict_dialog.show_advanced_dict_dialog()
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        om.MGlobal.displayError(f"[{PLUGIN_NAME}] 高度な設定の起動に失敗しました:\n{err_msg}")
        mc.warning(f"{PLUGIN_NAME} 高度な設定の起動に失敗しました: {e}")

def delete_menu():
    """作成したMMDメニューを削除します。"""
    if mc.menu(MENU_NAME, exists=True):
        try:
            mc.deleteUI(MENU_NAME, menu=True)
        except Exception:
            pass

def on_open_gui():
    """GUIを開くコールバック関数（既に表示されている場合は閉じて再表示）"""
    _ensure_sys_path()
    try:
        # 多重起動防止: Maya上の既存MMDウィンドウを検索して破棄
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            try:
                from PySide2.QtWidgets import QApplication
            except ImportError:
                QApplication = None

        if QApplication and QApplication.instance():
            for widget in QApplication.instance().topLevelWidgets():
                try:
                    if widget.objectName() == "MmdToolsForMayaMainWindow" or widget.__class__.__name__ == "MmdMayaMainWindow":
                        widget.close()
                        widget.deleteLater()
                except Exception:
                    pass

        import importlib
        # 更新されたコードを即時反映するための強制リロード
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("mmd_tools_for_maya") or mod_name in ["gui", "pmxpaimaya", "mayapaipmx"]:
                try:
                    importlib.reload(sys.modules[mod_name])
                except Exception:
                    pass

        # 優先度1: mmd_tools_for_maya.ui.gui から show_ui を実行
        try:
            from mmd_tools_for_maya.ui import gui as mmd_gui
            mmd_gui.show_ui()
            return
        except Exception:
            pass

        # 優先度2: mmd_tools_for_maya.gui から show_ui を実行
        try:
            from mmd_tools_for_maya import gui as mmd_gui
            mmd_gui.show_ui()
            return
        except Exception:
            pass

        # 優先度3: sys.path 直下の gui から show_ui を実行
        try:
            import gui as mmd_gui
            mmd_gui.show_ui()
            return
        except Exception:
            pass

        # 優先度4: パッケージの show_ui
        import mmd_tools_for_maya
        mmd_tools_for_maya.show_ui()

    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        om.MGlobal.displayError(f"[{PLUGIN_NAME}] GUIの起動に失敗しました:\n{err_msg}")
        mc.warning(f"{PLUGIN_NAME} GUIの起動に失敗しました: {e}")

def on_show_about():
    """プラグイン情報ダイアログを表示します。"""
    mc.confirmDialog(
        title="About MMD Tools for Maya",
        message=(
            f"MMD Tools for Maya v{PLUGIN_VERSION}\n\n"
            "制作者: Hina33\n"
            "Maya用 MMD (PMX/PMD/X) 統合プラグイン\n\n"
            "・完全オリジナル入出力エンジン（外部ライブラリ非依存）\n"
            "・PMX 2.0/2.1、PMD、DirectX .x（モデル・アクセサリ）対応\n"
            "・VMDモーション＆カメラ＆音源インポート\n"
            "・C++ XPBD物理演算エンジン（リアルタイムシミュレーション＆ベイク）\n"
            "・剛体・Joint可視化＆モデル自動再吸着機能\n"
            "・プログレスバー付きリアルタイムログウィンドウ\n"
            "・大容量・中国語モデル対応＆安全な自動ノード名変換\n"
            "・Autodesk Maya 2022+ (Maya 2025 動作確認済み)\n"
            "ライセンス: MIT License"
        ),
        button=["OK"],
        defaultButton="OK"
    )

def initializePlugin(plugin_obj):
    """プラグインロード時にMayaによって呼び出されます。"""
    plugin = om.MFnPlugin(plugin_obj, PLUGIN_VENDOR, PLUGIN_VERSION, "Any")
    _ensure_sys_path(plugin)
    
    # Mayaがバッチモードでない場合にメニューを作成
    if not mc.about(batch=True):
        mc.evalDeferred(create_menu)
        
    om.MGlobal.displayInfo(f"[{PLUGIN_NAME}] プラグインが正常にロードされました。")

def uninitializePlugin(plugin_obj):
    """プラグインアンロード時にMayaによって呼び出されます。"""
    plugin = om.MFnPlugin(plugin_obj)
    
    # メニューを削除
    if not mc.about(batch=True):
        delete_menu()
        
    om.MGlobal.displayInfo(f"[{PLUGIN_NAME}] プラグインがアンロードされました。")
