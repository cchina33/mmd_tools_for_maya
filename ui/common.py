# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - UI 共通基盤モジュール
PySide6 / PySide2 互換インポート、Mayaメインウィンドウ取得、ビューポート照明復元、
および共通実行ログダイアログ (ExecutionLogDialog) を提供します。
"""

import os
import re
import sys
import importlib
import traceback
import time
import json

try:
    from PySide6.QtWidgets import (
        QWidget, QLabel, QLineEdit, QComboBox, QPushButton,
        QCheckBox, QButtonGroup, QRadioButton, QHBoxLayout,
        QVBoxLayout, QScrollArea, QFileDialog, QMessageBox,
        QTabWidget, QGroupBox, QFrame, QSizePolicy, QApplication,
        QDialog, QTextEdit, QProgressBar, QSlider, QSpinBox, QDoubleSpinBox,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
        QSplitter, QMenu
    )
    from PySide6.QtCore import Qt, QSize
    from PySide6.QtGui import QDragEnterEvent, QDropEvent, QTextCursor, QFont, QColor
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2.QtWidgets import (
        QWidget, QLabel, QLineEdit, QComboBox, QPushButton,
        QCheckBox, QButtonGroup, QRadioButton, QHBoxLayout,
        QVBoxLayout, QScrollArea, QFileDialog, QMessageBox,
        QTabWidget, QGroupBox, QFrame, QSizePolicy, QApplication,
        QDialog, QTextEdit, QProgressBar, QSlider, QSpinBox, QDoubleSpinBox,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
        QSplitter, QMenu
    )
    from PySide2.QtCore import Qt, QSize
    from PySide2.QtGui import QDragEnterEvent, QDropEvent, QTextCursor, QFont, QColor
    try:
        from shiboken2 import wrapInstance
    except ImportError:
        wrapInstance = None

try:
    from ..mmd_core import pmm
except Exception:
    try:
        from mmd_core import pmm
    except Exception:
        pmm = None

import maya.cmds as mc
from maya import mel
import maya.OpenMaya as om
import maya.OpenMayaUI as omui

try:
    from ..converters import pmxpaimaya, mayapaipmx, vmdpaimaya, physics_stream, pmd2pmx
    from ..asset.hik import dic_hik, kangkhaen, setup_leg_stance_and_angles, normalize_bone_name, get_bone_matching_candidates
    from ..asset.jaka import safe_node_name
    from ..pmx_analyzer import export_pmx_structure, check_and_prompt_user_dict
except Exception:
    try:
        from converters import pmxpaimaya, mayapaipmx, vmdpaimaya, physics_stream, pmd2pmx
        from asset.hik import dic_hik, kangkhaen, setup_leg_stance_and_angles, normalize_bone_name, get_bone_matching_candidates
        from asset.jaka import safe_node_name
        from pmx_analyzer import export_pmx_structure, check_and_prompt_user_dict
    except Exception:
        import pmxpaimaya, mayapaipmx, vmdpaimaya
        try:
            import physics_stream
        except Exception:
            physics_stream = None
        try:
            import pmd2pmx
        except Exception:
            pmd2pmx = None
        from asset.hik import dic_hik, kangkhaen, setup_leg_stance_and_angles, normalize_bone_name, get_bone_matching_candidates
        try:
            from asset.jaka import safe_node_name
        except Exception:
            def safe_node_name(name, *args, **kwargs):
                return re.sub(r'[^a-zA-Z0-9_]', '_', str(name))
        try:
            import pmx_analyzer
            export_pmx_structure = pmx_analyzer.export_pmx_structure
            check_and_prompt_user_dict = pmx_analyzer.check_and_prompt_user_dict
        except Exception:
            export_pmx_structure = None
            check_and_prompt_user_dict = None

# MMシェーダープラグイン用セットアップモジュールのインポート
try:
    from ..mmd_material_plugin.scripts import mmd_material_setup
except Exception:
    try:
        from mmd_material_plugin.scripts import mmd_material_setup
    except Exception:
        try:
            import mmd_material_setup
        except Exception:
            mmd_material_setup = None

def get_maya_main_window():
    """MayaのメインウィンドウQWidgetを取得します。"""
    try:
        ptr = omui.MQtUtil.mainWindow()
        if ptr is not None and wrapInstance is not None:
            return wrapInstance(int(ptr), QWidget)
    except Exception:
        pass
    return None

def restore_viewport_lighting(force_reset=False, prevent_motion_darkening=True):
    """
    ビューポートの画面再描画を実行し、ユーザー設定のライティングおよびマテリアル表示を保護・維持します。
    ※ force_reset=True が明示的に指定されない限り、ユーザーが意図して設定した
       displayLights やマテリアルの発色を勝手に書き換えません。
    """
    if force_reset:
        try:
            has_lights = bool(mc.ls(type=["directionalLight", "ambientLight", "pointLight", "spotLight"]))
            target_mode = "all" if has_lights else "default"
            panels = mc.getPanel(type="modelPanel") or []
            for p in panels:
                try:
                    mc.modelEditor(p, edit=True, displayLights=target_mode, displayTextures=True)
                except Exception:
                    pass
        except Exception:
            pass

    # MMDモデルメッシュの影受け適正化（顔・脚の黒潰れ防止設定を維持）
    try:
        try:
            from ..converters import pmxpaimaya
        except Exception:
            try:
                from converters import pmxpaimaya
            except Exception:
                import pmxpaimaya
        if hasattr(pmxpaimaya, "optimize_model_meshes_for_mmd_lighting"):
            pmxpaimaya.optimize_model_meshes_for_mmd_lighting()
    except Exception:
        pass

    # モーション再生時の暗化防止（シャッター開度0.01によるブレなしHDRポストパス最適化）
    try:
        if mc.objExists('hardwareRenderingGlobals'):
            if prevent_motion_darkening:
                if mc.attributeQuery('motionBlurEnable', node='hardwareRenderingGlobals', exists=True):
                    mc.setAttr('hardwareRenderingGlobals.motionBlurEnable', True)
                if mc.attributeQuery('motionBlurShutterOpenFraction', node='hardwareRenderingGlobals', exists=True):
                    mc.setAttr('hardwareRenderingGlobals.motionBlurShutterOpenFraction', 0.01)
                if mc.attributeQuery('floatingPointRTEnable', node='hardwareRenderingGlobals', exists=True):
                    mc.setAttr('hardwareRenderingGlobals.floatingPointRTEnable', True)
                if mc.attributeQuery('floatingPointRTFormat', node='hardwareRenderingGlobals', exists=True):
                    mc.setAttr('hardwareRenderingGlobals.floatingPointRTFormat', 1)
    except Exception:
        pass

    try:
        mc.refresh(force=True)
    except Exception:
        pass

# ==============================================================================
# モダン QSS スタイルシート (gui_style.py からインポート)
# ==============================================================================
from .gui_style import MODERN_STYLE


# ==============================================================================
# ログ出力リダイレクタ & ログウィンドウ
# ==============================================================================
class StreamRedirector(object):
    """sys.stdout / sys.stderr をフックしてコールバックに渡すクラス"""
    def __init__(self, original_stream, callback):
        self.original_stream = original_stream
        self.callback = callback

    def write(self, text):
        if self.original_stream:
            try:
                self.original_stream.write(text)
            except Exception:
                pass
        if self.callback and text:
            self.callback(text)

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass

class ExecutionLogDialog(QDialog):
    """インポート／エクスポート処理のリアルタイムログダイアログ"""
    def __init__(self, parent=None, title="実行ログ", show_cancel=False):
        super(ExecutionLogDialog, self).__init__(parent)
        self.setWindowTitle(title)
        self.resize(620, 440)
        self.setMinimumSize(480, 320)
        self.setStyleSheet(MODERN_STYLE)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint | Qt.WindowStaysOnTopHint)

        self.show_cancel = show_cancel
        self.success = False
        self.is_cancelled = False
        self._start_time = None

        # レイアウト構築
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # ステータス表示
        self.lb_status = QLabel("処理を実行中...")
        self.lb_status.setStyleSheet("font-weight: bold; font-size: 15px; color: #52b7ff;")
        layout.addWidget(self.lb_status)

        # 進捗詳細情報（フレーム数 / 残りフレーム / ETA）
        h_info = QHBoxLayout()
        self.lb_frame_info = QLabel("進捗: 待機中")
        self.lb_frame_info.setStyleSheet("font-size: 13px; color: #e0e0e0; font-weight: bold;")
        self.lb_eta_info = QLabel("推定残り時間: --")
        self.lb_eta_info.setStyleSheet("font-size: 13px; color: #aaa;")
        h_info.addWidget(self.lb_frame_info)
        h_info.addStretch()
        h_info.addWidget(self.lb_eta_info)
        layout.addLayout(h_info)

        # ログテキストエリア
        self.te_log = QTextEdit()
        self.te_log.setReadOnly(True)
        self.te_log.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.te_log)

        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(22)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # ボタングループ
        h_btn = QHBoxLayout()
        self.btn_copy = QPushButton("ログをコピー")
        self.btn_copy.setFixedWidth(110)
        self.btn_copy.clicked.connect(self._copy_log)
        h_btn.addWidget(self.btn_copy)

        h_btn.addStretch()

        if self.show_cancel:
            self.btn_cancel = QPushButton("ベイク中止")
            self.btn_cancel.setFixedWidth(110)
            self.btn_cancel.setStyleSheet(
                "QPushButton { background-color: #5d2525; color: #ffcccc; border: 1px solid #853333; border-radius: 4px; font-weight: bold; font-size: 13px; }"
                "QPushButton:hover { background-color: #782e2e; color: #ffffff; }"
            )
            self.btn_cancel.clicked.connect(self._on_cancel_clicked)
            h_btn.addWidget(self.btn_cancel)
        else:
            self.btn_cancel = None

        self._last_process_time = 0

        self.btn_close = QPushButton("閉じる")
        self.btn_close.setFixedWidth(100)
        self.btn_close.setEnabled(False) # 実行中は無効化
        self.btn_close.clicked.connect(self.close)
        h_btn.addWidget(self.btn_close)

        layout.addLayout(h_btn)

    def _on_cancel_clicked(self):
        """ベイク中止ボタン押下時の処理"""
        if not self.is_cancelled:
            self.is_cancelled = True
            if self.btn_cancel:
                self.btn_cancel.setEnabled(False)
                self.btn_cancel.setText("中止中...")
            self.append_log("\n>>> ベイク中止要求を受信しました。安定して中断しています...\n")
            self.lb_status.setText("中断中: 安定して停止しています...")
            self.lb_status.setStyleSheet("font-weight: bold; font-size: 15px; color: #ffaa55;")
            QApplication.processEvents()

    def check_cancelled(self):
        """物理エンジン等から定期ポーリングされるキャンセル確認"""
        QApplication.processEvents()
        return self.is_cancelled

    def update_progress(self, current, total=None, step_idx=None, total_steps=None, label_prefix="進捗", unit=""):
        """進捗の更新および推定残り時間(ETA)の算出・表示"""
        if self._start_time is None:
            self._start_time = time.time()

        # 第2引数に文字列が渡された場合のフォールバック保護 (totalが文字列の場合はunitに回す)
        if isinstance(total, str):
            if not unit:
                unit = total
            total = 100

        # 4引数呼び出し update_progress(current_frame, end_frame, step_idx, total_steps) の互換処理
        if total_steps is not None and step_idx is not None:
            curr_step = float(step_idx)
            max_step = max(1.0, float(total_steps))
            curr_val = current
            end_val = total
            val_unit = unit or "フレーム"
        else:
            try:
                curr_step = float(current)
            except (ValueError, TypeError):
                curr_step = 0.0
            try:
                max_step = max(1.0, float(total if total is not None else 100))
            except (ValueError, TypeError):
                max_step = 100.0
            curr_val = current
            end_val = total
            val_unit = unit

        percent = int(min(100, max(0, (curr_step / max_step) * 100)))
        self.progress_bar.setValue(percent)

        if self.lb_frame_info and self.lb_eta_info:
            if end_val is not None:
                if val_unit:
                    info_text = f"{label_prefix}: {val_unit} {curr_val} / {end_val} ({percent}%)"
                else:
                    info_text = f"{label_prefix}: {curr_val} / {end_val} ({percent}%)"
            else:
                info_text = f"{label_prefix}: {percent}%"
            self.lb_frame_info.setText(info_text)

            elapsed = time.time() - self._start_time
            if curr_step > 0 and elapsed > 0.2:
                remain_steps = max(0.0, max_step - curr_step)
                sec_per_step = elapsed / curr_step
                remain_sec = sec_per_step * remain_steps
                if remain_sec < 60:
                    eta_str = f"約 {max(0, int(remain_sec))} 秒"
                else:
                    eta_m = int(remain_sec // 60)
                    eta_s = int(remain_sec % 60)
                    eta_str = f"約 {eta_m} 分 {eta_s} 秒"
                self.lb_eta_info.setText(f"推定残り時間: {eta_str}")

        now = time.time()
        if now - self._last_process_time > 0.05 or curr_step >= max_step:
            self._last_process_time = now
            QApplication.processEvents()

    def append_log(self, text):
        """ログを追加して最下部へスクロール。ステップログを解析して進捗と残り時間を自動更新"""
        cursor = self.te_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.te_log.setTextCursor(cursor)
        self.te_log.ensureCursorVisible()

        # ログ文字列からステップ進捗（例: [1/6] や [2/5] 等）を検出して進捗バー・ETAを自動連動
        m_step = re.search(r'\[(\d+)/(\d+)\]', text)
        if m_step:
            cur_s = int(m_step.group(1))
            tot_s = int(m_step.group(2))
            self.update_progress(cur_s, tot_s, label_prefix="工程進捗", unit="ステップ")

        QApplication.processEvents()

    def _copy_log(self):
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.te_log.toPlainText())
            mc.inViewMessage(amg='<span style="color:#52b7ff;">MMD Tools for Maya:</span> ログをクリップボードにコピーしました。', pos='topCenter', fade=True)

    def run_task(self, task_func, *args, **kwargs):
        """タスクを実行し、ログをキャプチャ"""
        self.show()
        self.is_cancelled = False
        self._start_time = time.time()
        if self.btn_cancel:
            self.btn_cancel.setEnabled(True)
            self.btn_cancel.setText("ベイク中止")
        QApplication.processEvents()

        # 標準出力・標準エラーを一時リダイレクト
        orig_stdout = sys.stdout
        orig_stderr = sys.stderr
        redirector = StreamRedirector(orig_stdout, self.append_log)
        sys.stdout = redirector
        sys.stderr = redirector

        self.success = False
        try:
            self.append_log(">>> 処理を開始しました...\n")
            task_func(*args, **kwargs)
            self.success = True
            if self.is_cancelled:
                self.append_log("\n>>> 処理がユーザーにより中断されました。\n")
                self.lb_status.setText("中断: ユーザーにより処理が停止されました")
                self.lb_status.setStyleSheet("font-weight: bold; font-size: 15px; color: #ffaa55;")
            else:
                self.append_log("\n>>> 処理が正常に終了しました！\n")
                self.lb_status.setText("終了: 正常に処理が終了しました")
                self.lb_status.setStyleSheet("font-weight: bold; font-size: 15px; color: #2ecc71;")
                self.progress_bar.setValue(100)
        except Exception as e:
            self.success = False
            err_trace = traceback.format_exc()
            self.append_log(f"\n[エラー] 処理中に問題が発生しました:\n{err_trace}\n")
            self.lb_status.setText("エラー: 処理が中断されました")
            self.lb_status.setStyleSheet("font-weight: bold; font-size: 15px; color: #ff7675;")
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr
            if self.btn_cancel:
                self.btn_cancel.setEnabled(False)
            self.btn_close.setEnabled(True)
            self.btn_close.setProperty("class", "primary")
            self.btn_close.setStyleSheet(self.styleSheet())
            self.btn_close.setFocus()
            QApplication.processEvents()

        return self.success


def populate_mmd_model_combo(combo_box, include_all_label=None, empty_label="（シーン内にMMDモデルが見つかりません）"):
    """シーン内のMMDモデル一覧を取得してコンボボックスへ設定する共通ヘルパー"""
    combo_box.clear()
    if include_all_label:
        combo_box.addItem(include_all_label, None)

    found = False
    try:
        models = vmdpaimaya.get_available_mmd_models()
        for item in models:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                node_name, label = item[0], item[1]
                combo_box.addItem(label, node_name)
            else:
                combo_box.addItem(str(item), item)
            found = True
    except Exception:
        pass

    if not found and not include_all_label and empty_label:
        combo_box.addItem(empty_label, None)
    return found


def set_viewport_renderer_override(override_name="mmdRenderOverride"):
    """3Dビューポートパネルのレンダラーオーバーライドを設定"""
    if not mc:
        return False
    if override_name == "mmdRenderOverride" and mmd_material_setup:
        try:
            mmd_material_setup.ensure_plugin_loaded()
        except Exception:
            pass

    panels = mc.getPanel(type="modelPanel") or []
    success = False
    for p in panels:
        try:
            mc.modelEditor(p, edit=True, rendererOverrideName=override_name)
            success = True
        except Exception:
            pass
    return success


def is_mmd_viewport_renderer_active():
    """現在いずれかの3Dビューポートで MMD Viewport Renderer が有効か判定"""
    if not mc:
        return False
    panels = mc.getPanel(type="modelPanel") or []
    for p in panels:
        try:
            cur = mc.modelEditor(p, query=True, rendererOverrideName=True)
            if cur == "mmdRenderOverride":
                return True
        except Exception:
            pass
    return False


def toggle_viewport_renderer_override():
    """Viewport 2.0 と MMD Viewport Renderer を交互に切り替え"""
    if is_mmd_viewport_renderer_active():
        set_viewport_renderer_override("")
        return False
    else:
        set_viewport_renderer_override("mmdRenderOverride")
        return True
