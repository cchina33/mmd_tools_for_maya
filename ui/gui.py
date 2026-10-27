# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - モダン統合 GUI モジュール (PySide6 / PySide2 対応)
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
        QDialog, QTextEdit, QProgressBar, QSlider, QSpinBox,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
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
        QDialog, QTextEdit, QProgressBar, QSlider, QSpinBox,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
    )
    from PySide2.QtCore import Qt, QSize
    from PySide2.QtGui import QDragEnterEvent, QDropEvent, QTextCursor, QFont, QColor
    try:
        from shiboken2 import wrapInstance
    except ImportError:
        wrapInstance = None

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

# グローバルウィンドウ参照保持用（ガベージコレクション防止）
_main_window_instance = None

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
            self.append_log("\n>>> ベイク中止要求を受信しました。安全に中断しています...\n")
            self.lb_status.setText("中断中: 安全に停止しています...")
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

        # 4引数呼び出し update_progress(current_frame, end_frame, step_idx, total_steps) の互換処理
        if total_steps is not None and step_idx is not None:
            curr_step = float(step_idx)
            max_step = max(1.0, float(total_steps))
            curr_val = current
            end_val = total
            val_unit = unit or "フレーム"
        else:
            curr_step = float(current)
            max_step = max(1.0, float(total if total is not None else 100))
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
                self.append_log("\n>>> 処理が正常に完了しました！\n")
                self.lb_status.setText("完了: 正常に処理が終了しました")
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

# ==============================================================================
# 複数モデルインポート 実行ログダイアログ (別ウィンドウ)
# ==============================================================================
class MultiModelLogDialog(QDialog):
    """複数モデルインポート用の独立した実行ログウィンドウ"""
    def __init__(self, parent=None):
        super(MultiModelLogDialog, self).__init__(parent)
        self.setWindowTitle("複数モデルインポート - 実行ログ")
        self.resize(720, 500)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ログテキスト表示エリア
        self.te_log = QTextEdit()
        self.te_log.setReadOnly(True)
        self.te_log.setStyleSheet(
            "QTextEdit { background-color: #1a1a1a; color: #ddd; font-family: Consolas, monospace; font-size: 12px; }"
        )
        layout.addWidget(self.te_log)

        # ボタングループ
        h_btn = QHBoxLayout()
        self.btn_copy = QPushButton("ログをコピー")
        self.btn_copy.setFixedHeight(32)
        self.btn_copy.setFixedWidth(110)
        self.btn_copy.clicked.connect(self._copy_log)
        h_btn.addWidget(self.btn_copy)

        self.btn_clear = QPushButton("ログをクリア")
        self.btn_clear.setFixedHeight(32)
        self.btn_clear.setFixedWidth(110)
        self.btn_clear.clicked.connect(self.clear_log)
        h_btn.addWidget(self.btn_clear)

        h_btn.addStretch()

        self.btn_close = QPushButton("閉じる")
        self.btn_close.setFixedHeight(32)
        self.btn_close.setFixedWidth(100)
        self.btn_close.clicked.connect(self.close)
        h_btn.addWidget(self.btn_close)

        layout.addLayout(h_btn)

    def append_log(self, text):
        """ログを追加して末尾へ自動スクロール"""
        cursor = self.te_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.te_log.setTextCursor(cursor)
        self.te_log.ensureCursorVisible()
        QApplication.processEvents()

    def clear_log(self):
        """ログをクリア"""
        self.te_log.clear()

    def _copy_log(self):
        """ログをクリップボードにコピー"""
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.te_log.toPlainText())
            mc.inViewMessage(amg='<span style="color:#52b7ff;">MMD Tools for Maya:</span> 実行ログをクリップボードにコピーしました。', pos='topCenter', fade=True)


# ==============================================================================
# ドラッグ＆ドロップ対応 モデル一覧テーブル
# ==============================================================================
class MultiModelDropTableWidget(QTableWidget):
    """外部エクスプローラー等からのドラッグ＆ドロップを受け付けるモデル一覧テーブル"""
    def __init__(self, dialog=None, parent=None):
        super(MultiModelDropTableWidget, self).__init__(parent)
        self.dialog = dialog
        self.setAcceptDrops(True)
        if self.viewport():
            self.viewport().setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            files = []
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if p:
                    files.append(p)
            if files and self.dialog and hasattr(self.dialog, 'add_model_files'):
                event.acceptProposedAction()
                self.dialog.add_model_files(files)
                return
        event.ignore()


# ==============================================================================
# 複数モデルインポート ダイアログ (試験的機能)
# ==============================================================================
class MultiModelImportDialog(QDialog):
    """複数の MMD モデル (.pmx / .pmd) を順次インポートし、アンカーへ自動配置するダイアログ"""
    def __init__(self, parent=None):
        super(MultiModelImportDialog, self).__init__(parent)
        self.parent_tab = parent
        self.setWindowTitle("複数のモデルをインポート (試験的機能)")
        self.resize(920, 520)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.setAcceptDrops(True)

        # 独立した実行ログウィンドウを保持
        self.log_dialog = MultiModelLogDialog(parent=self)

        # モデル登録アイテム一覧: [ {'path': str, 'name': str, 'anchor': str, 'status': str} ]
        self.model_items = []
        self._is_importing = False
        self._cancel_requested = False

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ヘッダー説明
        desc_box = QGroupBox("複数モデルの順次インポートについて")
        desc_box.setStyleSheet("QGroupBox { font-weight: bold; color: #ffaa00; border: 1px solid #7a581e; padding: 10px; border-radius: 4px; background-color: #262016; }")
        desc_layout = QVBoxLayout(desc_box)
        lbl_desc = QLabel(
            "複数の PMX / PMD モデルを追加し、事前作成されたアンカーロケーターの位置へ自動配置します。\n"
            "※モデルの構築・剛体生成・グループ化は原点（中心）で安全に行われ、完了後にアンカーへ移動して次のモデルの読み込みを開始します。\n"
            "※モデルファイル（.pmx / .pmd）やモデル格納フォルダを一覧表へ直接ドラッグ＆ドロップして追加することも可能です。"
        )
        lbl_desc.setStyleSheet("color: #ffd180; font-size: 12px; font-weight: normal;")
        lbl_desc.setWordWrap(True)
        desc_layout.addWidget(lbl_desc)
        main_layout.addWidget(desc_box)

        # モデル一覧テーブル
        table_box = QGroupBox("インポート対象モデル一覧 (ドラッグ＆ドロップ対応)")
        table_layout = QVBoxLayout(table_box)
        table_layout.setSpacing(8)

        self.table = MultiModelDropTableWidget(dialog=self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["No.", "モデル名", "アンカー (ロケーター)", "状態", "ファイルパス"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(2, 180)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(200)
        table_layout.addWidget(self.table)

        # リスト操作ボタン
        h_table_btn = QHBoxLayout()
        self.btn_add = QPushButton("モデルを追加...")
        self.btn_add.setFixedHeight(34)
        self.btn_add.setStyleSheet("QPushButton { background-color: #2b5b84; color: #fff; font-weight: bold; border-radius: 4px; padding: 0 14px; } QPushButton:hover { background-color: #3872a4; }")
        self.btn_add.setToolTip("PMX または PMD ファイルを選択して一覧へ追加します（複数選択可、ドラッグ＆ドロップ可、.x ファイルは不可）。自動的にアンカーロケーターを作成します。")
        self.btn_add.clicked.connect(self._on_add_models)
        h_table_btn.addWidget(self.btn_add)

        self.btn_remove = QPushButton("選択項目を削除")
        self.btn_remove.setFixedHeight(34)
        self.btn_remove.setToolTip("選択中のモデルを一覧から削除します。")
        self.btn_remove.clicked.connect(self._on_remove_selected)
        h_table_btn.addWidget(self.btn_remove)

        self.btn_clear = QPushButton("一覧をクリア")
        self.btn_clear.setFixedHeight(34)
        self.btn_clear.clicked.connect(self._on_clear_all)
        h_table_btn.addWidget(self.btn_clear)

        h_table_btn.addSpacing(16)

        self.btn_assign_anchor = QPushButton("選択オブジェクトをアンカーに設定")
        self.btn_assign_anchor.setFixedHeight(34)
        self.btn_assign_anchor.setToolTip("現在Mayaビューポートで選択しているノード（ロケーター等）を選択行のアンカーとして再設定します。")
        self.btn_assign_anchor.clicked.connect(self._on_assign_anchor_from_selection)
        h_table_btn.addWidget(self.btn_assign_anchor)

        self.btn_focus_anchor = QPushButton("アンカーを選択・表示")
        self.btn_focus_anchor.setFixedHeight(34)
        self.btn_focus_anchor.setToolTip("選択行のアンカーロケーターをMaya上で選択し、カメラをフォーカスします。")
        self.btn_focus_anchor.clicked.connect(self._on_focus_anchor)
        h_table_btn.addWidget(self.btn_focus_anchor)

        h_table_btn.addStretch()
        table_layout.addLayout(h_table_btn)
        main_layout.addWidget(table_box)

        # インポート共通オプション
        opt_box = QGroupBox("インポート共通設定")
        opt_layout = QHBoxLayout(opt_box)
        opt_layout.setSpacing(14)

        opt_layout.addWidget(QLabel("スケール:"))
        self.le_scale = QLineEdit("8.0")
        self.le_scale.setFixedWidth(50)
        opt_layout.addWidget(self.le_scale)

        opt_layout.addWidget(QLabel("マテリアル:"))
        self.cbb_material = QComboBox()
        self.cbb_material.addItems(["マテリアルなし", "Blinn", "Phong", "Lambert", "StandardSurface (Maya 2022+)", "MMD Shader (オリジナル,ベータ版)", "MMD Toon Shader (新プラグイン, 忠実再現)"])
        self.cbb_material.setCurrentText("MMD Toon Shader (新プラグイン, 忠実再現)")
        opt_layout.addWidget(self.cbb_material)

        self.cb_bones = QCheckBox("スケルトン生成")
        self.cb_bones.setChecked(True)
        opt_layout.addWidget(self.cb_bones)

        self.cb_physics = QCheckBox("剛体・Joint生成")
        self.cb_physics.setChecked(True)
        opt_layout.addWidget(self.cb_physics)

        self.cb_bs = QCheckBox("ブレンドシェイプ生成")
        self.cb_bs.setChecked(True)
        opt_layout.addWidget(self.cb_bs)

        self.cb_check_mb = QCheckBox("モーフ・ボーン検査")
        self.cb_check_mb.setChecked(True)
        opt_layout.addWidget(self.cb_check_mb)

        opt_layout.addStretch()
        main_layout.addWidget(opt_box)

        # 進捗バーと状態ラベル
        prog_layout = QHBoxLayout()
        self.lbl_progress = QLabel("待機中: モデルを追加して「順次インポートを開始」をクリックしてください")
        self.lbl_progress.setStyleSheet("color: #ccc; font-size: 13px;")
        prog_layout.addWidget(self.lbl_progress)
        prog_layout.addStretch()
        main_layout.addLayout(prog_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # 実行ボタンエリア
        h_exec = QHBoxLayout()

        self.btn_show_log = QPushButton("実行ログを表示...")
        self.btn_show_log.setFixedHeight(44)
        self.btn_show_log.setFixedWidth(150)
        self.btn_show_log.setStyleSheet("QPushButton { background-color: #3e3e3e; color: #fff; font-size: 13px; border-radius: 4px; } QPushButton:hover { background-color: #4e4e4e; }")
        self.btn_show_log.setToolTip("独立した実行ログウィンドウを開きます。")
        self.btn_show_log.clicked.connect(self.show_log_dialog)
        h_exec.addWidget(self.btn_show_log)

        h_exec.addStretch()

        self.btn_start = QPushButton("順次インポートを開始")
        self.btn_start.setFixedHeight(44)
        self.btn_start.setMinimumWidth(200)
        self.btn_start.setStyleSheet("QPushButton { background-color: #2b7a4b; color: #fff; font-size: 14px; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #38965d; }")
        self.btn_start.clicked.connect(self._start_sequential_import)
        h_exec.addWidget(self.btn_start)

        self.btn_close = QPushButton("閉じる")
        self.btn_close.setFixedHeight(44)
        self.btn_close.setFixedWidth(100)
        self.btn_close.clicked.connect(self.close)
        h_exec.addWidget(self.btn_close)

        main_layout.addLayout(h_exec)

    def dragEnterEvent(self, event):
        """ダイアログ全体でのドラッグ受付"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """ダイアログ余白等へのドロップ受付"""
        if event.mimeData().hasUrls():
            files = []
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if p:
                    files.append(p)
            if files:
                event.acceptProposedAction()
                self.add_model_files(files)
                return
        event.ignore()

    def show_log_dialog(self):
        """実行ログウィンドウを前面に表示"""
        if self.log_dialog:
            self.log_dialog.show()
            self.log_dialog.raise_()
            self.log_dialog.activateWindow()

    def append_log(self, text):
        """実行ログウィンドウへテキストを書き込み"""
        if self.log_dialog:
            self.log_dialog.append_log(text)

    def closeEvent(self, event):
        """親ダイアログが閉じられたらログウィンドウも閉じる"""
        if self.log_dialog:
            self.log_dialog.close()
        event.accept()

    def _refresh_table(self):
        """テーブルの行表示を更新"""
        self.table.setRowCount(len(self.model_items))
        for row, item in enumerate(self.model_items):
            item_no = QTableWidgetItem(str(row + 1))
            item_no.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_no)

            item_name = QTableWidgetItem(item['name'])
            self.table.setItem(row, 1, item_name)

            item_anchor = QTableWidgetItem(item['anchor'])
            self.table.setItem(row, 2, item_anchor)

            item_status = QTableWidgetItem(item['status'])
            item_status.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, item_status)

            item_path = QTableWidgetItem(item['path'])
            self.table.setItem(row, 4, item_path)

    def add_model_files(self, file_paths):
        """モデルファイル一覧（またはフォルダ）を受け取り、一覧およびアンカーを追加"""
        if not file_paths:
            return

        # フォルダが渡された場合は内部のモデルファイルを探索
        collected_files = []
        for fp in file_paths:
            if os.path.isdir(fp):
                for root_dir, _, filenames in os.walk(fp):
                    for fn in filenames:
                        ext = os.path.splitext(fn)[1].lower()
                        if ext in ['.pmx', '.pmd']:
                            collected_files.append(os.path.join(root_dir, fn))
            else:
                collected_files.append(fp)

        if not collected_files:
            self.append_log("[案内] 追加可能な MMD モデルファイル (.pmx / .pmd) が見つかりませんでした。\n")
            self.show_log_dialog()
            return

        # 登録済みパスのセット（重複防止用）
        existing_paths = {item['path'].replace('\\', '/').lower() for item in self.model_items}

        added_count = 0
        for f in collected_files:
            norm_f = f.replace('\\', '/').lower()
            ext = os.path.splitext(f)[1].lower()
            base_name = os.path.splitext(os.path.basename(f))[0]

            if not os.path.exists(f):
                self.append_log(f"[スキップ] 指定されたファイルが存在しません: {os.path.basename(f)}\n")
                continue

            if ext not in ['.pmx', '.pmd']:
                self.append_log(f"[スキップ] 非対応のファイル形式です (.x ファイルは複数インポート非対応): {os.path.basename(f)}\n")
                continue

            if norm_f in existing_paths:
                self.append_log(f"[スキップ] 既に一覧に追加されています: {os.path.basename(f)}\n")
                continue

            safe_name = safe_node_name(base_name)

            # アンカーロケーターを自動生成
            loc_base = f"anchor_{safe_name}"
            loc_name = loc_base
            idx = 1
            while mc.objExists(loc_name):
                loc_name = f"{loc_base}_{idx}"
                idx += 1

            try:
                # 複数配置時に重ならないようオフセット配置
                offset_x = len(self.model_items) * 20.0
                loc_node = mc.spaceLocator(name=loc_name)[0]
                mc.setAttr(f"{loc_node}.translateX", offset_x)
                mc.setAttr(f"{loc_node}.localScaleX", 5.0)
                mc.setAttr(f"{loc_node}.localScaleY", 5.0)
                mc.setAttr(f"{loc_node}.localScaleZ", 5.0)
            except Exception as e:
                loc_node = loc_name
                self.append_log(f"[警告] ロケーター生成エラー: {e}\n")

            self.model_items.append({
                'path': f,
                'name': base_name,
                'anchor': loc_node,
                'status': "待機中"
            })
            existing_paths.add(norm_f)
            added_count += 1
            self.append_log(f"[追加] モデル: {base_name} (アンカー: {loc_node}, X={offset_x})\n")

        self._refresh_table()
        if added_count > 0:
            self.append_log(f">> {added_count} 体のモデルを追加しました。ビューポート上でアンカーロケーターを希望の位置・向きへ移動できます。\n")
            self.lbl_progress.setText(f"登録完了: 現在 {len(self.model_items)} 体のモデルが登録されています")
            self.show_log_dialog()

    def _on_add_models(self):
        """モデル選択ダイアログを表示してアンカーロケーターを自動生成"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "MMDモデルファイルを選択 (複数可)",
            "",
            "MMD Models (*.pmx *.pmd);;PMX (*.pmx);;PMD (*.pmd)"
        )
        if files:
            self.add_model_files(files)

    def _on_remove_selected(self):
        """選択行のモデルをリストから削除"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self.model_items):
            QMessageBox.information(self, "案内", "削除する行を選択してください。")
            return

        item = self.model_items.pop(row)
        # アンカーロケーターが残っていればクリーンアップ
        if item.get('anchor') and mc.objExists(item['anchor']):
            try:
                mc.delete(item['anchor'])
            except Exception:
                pass

        self._refresh_table()
        self.append_log(f"[削除] モデル '{item['name']}' をリストから除外しました。\n")

    def _on_clear_all(self):
        """すべてのモデル登録をクリア"""
        if not self.model_items:
            return
        res = QMessageBox.question(self, "確認", "登録中のすべてのモデルをリストからクリアしますか？", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            for item in self.model_items:
                if item.get('anchor') and mc.objExists(item['anchor']):
                    try:
                        mc.delete(item['anchor'])
                    except Exception:
                        pass
            self.model_items.clear()
            self._refresh_table()
            self.append_log("[クリア] モデル登録をすべてクリアしました。\n")

    def _on_assign_anchor_from_selection(self):
        """シーン内で選択中のオブジェクトを選択行のアンカーとして再設定"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self.model_items):
            QMessageBox.information(self, "案内", "アンカーを設定する対象行をテーブルで選択してください。")
            return

        sel = mc.ls(selection=True) or []
        if not sel:
            QMessageBox.warning(self, "未選択", "Mayaビューポートでアンカーに指定するオブジェクト（ロケーター等）を選択してください。")
            return

        target_node = sel[0]
        self.model_items[row]['anchor'] = target_node
        self._refresh_table()
        self.append_log(f"[アンカー変更] モデル '{self.model_items[row]['name']}' のアンカーを '{target_node}' に設定しました。\n")

    def _on_focus_anchor(self):
        """選択行のアンカーロケーターをMaya上で選択・フォーカス"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self.model_items):
            return
        anchor = self.model_items[row]['anchor']
        if anchor and mc.objExists(anchor):
            mc.select(anchor)
            try:
                mc.viewFit()
            except Exception:
                pass

    def _start_sequential_import(self):
        """登録されたモデルを原点で安全にインポートし、グループ化後にアンカーへ移動して順次進行"""
        if not self.model_items:
            QMessageBox.warning(self, "未登録", "インポート対象のモデルが追加されていません。")
            return

        if self._is_importing:
            return

        self._is_importing = True
        self.btn_start.setEnabled(False)
        self.btn_add.setEnabled(False)
        self.btn_remove.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.progress_bar.setValue(0)

        total_count = len(self.model_items)
        success_count = 0

        # パラメータ取得
        try:
            scale = float(self.le_scale.text())
        except ValueError:
            scale = 8.0

        material_type = self.cbb_material.currentIndex()
        create_bones = self.cb_bones.isChecked()
        create_physics = self.cb_physics.isChecked()
        create_bs = self.cb_bs.isChecked()
        check_morph_bone = self.cb_check_mb.isChecked()

        self.show_log_dialog()
        self.append_log("\n==================================================\n")
        self.append_log(f">>> 複数モデルの順次インポートを開始します (全 {total_count} 体)\n")
        self.append_log("==================================================\n")

        for idx, item in enumerate(self.model_items):
            file_path = item['path']
            model_name = item['name']
            anchor_name = item['anchor']

            self.lbl_progress.setText(f"インポート中 ({idx + 1}/{total_count}): {model_name}")
            item['status'] = "インポート中..."
            self._refresh_table()
            self.append_log(f"\n[{idx + 1}/{total_count}] モデルの読み込み開始: {model_name}\n")
            self.append_log(f"  - ファイル: {file_path}\n")

            # PMD形式の自動PMX変換
            if file_path.lower().endswith('.pmd'):
                try:
                    try:
                        from ..converters.pmd2pmx import convert_pmd_to_pmx
                    except Exception:
                        from converters.pmd2pmx import convert_pmd_to_pmx
                    self.append_log("  - PMD形式を検出: PMXへ自動変換中...\n")
                    file_path = convert_pmd_to_pmx(file_path)
                    self.append_log(f"  - PMX変換完了: {os.path.basename(file_path)}\n")
                except Exception as e:
                    self.append_log(f"  [警告] PMD変換エラー: {e}\n")

            # 原点でインポートする前のトップレベルノードを記録
            before_assemblies = set(mc.ls(assemblies=True) or [])

            try:
                # ユーザー辞書チェック
                if file_path.lower().endswith('.pmx') and check_morph_bone and check_and_prompt_user_dict:
                    try:
                        check_and_prompt_user_dict(self, file_path)
                    except Exception as e:
                        self.append_log(f"  [警告] モーフボーン検査エラー: {e}\n")

                # 原点での安全なインポート実行
                import importlib
                importlib.reload(pmxpaimaya)
                import_func = getattr(pmxpaimaya, 'import_pmx', pmxpaimaya.sang)

                # 初回のみライト生成、2体目以降はスキップ
                create_light = (idx == 0)
                ret = import_func(
                    file_path, scale, False, create_bs,
                    create_bones, material_type,
                    create_light, True,
                    True, shadow_mode=1, create_ground_shadow=create_light,
                    show_completion_message=False, prevent_motion_darkening=True,
                    create_physics=create_physics
                )
                self.append_log("  - 原点でのメッシュ・スケルトンおよび剛体・Joint構築完了\n")

                # メッシュの二重トランスフォーム防止
                mesh_node = ret[0] if ret else None
                if mesh_node and mc.objExists(mesh_node):
                    mc.setAttr(f"{mesh_node}.inheritsTransform", False)

                # インポート後のトップレベルノード差分を検出
                after_assemblies = set(mc.ls(assemblies=True) or [])
                new_nodes = [
                    n for n in (after_assemblies - before_assemblies)
                    if not n.startswith("mmd_lighting") and not n.startswith("mmd_ground_shadow")
                ]

                # すべての生成ノードを1つのグループにまとめる
                safe_name = safe_node_name(model_name)
                grp_name = f"{safe_name}_grp"
                g_idx = 1
                while mc.objExists(grp_name):
                    grp_name = f"{safe_name}_{g_idx}_grp"
                    g_idx += 1

                if new_nodes:
                    model_group = mc.group(new_nodes, name=grp_name)
                    # 識別用カスタムアトリビュートを付与 (親グループとして識別)
                    if not mc.attributeQuery('isMmdGroup', node=model_group, exists=True):
                        mc.addAttr(model_group, longName='isMmdGroup', attributeType='bool', defaultValue=True)
                    self.append_log(f"  - 生成ノードを統合グループ '{model_group}' にまとめました\n")
                else:
                    model_group = None

                # アンカーロケーターが存在する場合、その位置・回転へ移動して追従接続
                if model_group and anchor_name and mc.objExists(anchor_name):
                    anc_pos = mc.xform(anchor_name, query=True, worldSpace=True, translation=True)
                    anc_rot = mc.xform(anchor_name, query=True, worldSpace=True, rotation=True)
                    mc.xform(model_group, worldSpace=True, translation=anc_pos, rotation=anc_rot)

                    # アンカーロケーター移動にモデル全体（メッシュ・ボーン・剛体・Joint）が連動するようコンストレイント設定
                    try:
                        c_anc = mc.parentConstraint(anchor_name, model_group, maintainOffset=True)
                        if c_anc:
                            mc.addAttr(c_anc[0], longName="isMmdAnchorConstraint", attributeType="bool", defaultValue=True)
                    except Exception as e_anc:
                        self.append_log(f"  [警告] アンカー追従接続スキップ: {e_anc}\n")

                    self.append_log(f"  - アンカー '{anchor_name}' の位置へモデルを配置・追従接続しました: {anc_pos}\n")
                else:
                    self.append_log("  - アンカー未指定または不在のため、原点に配置を維持しました\n")

                # 次のモデル読み込み前にビューポートを描画更新し、原点スペースを解放
                try:
                    mc.refresh()
                except Exception:
                    pass

                item['status'] = "完了"
                success_count += 1
                self.append_log(f"  -> モデル '{model_name}' の読み込み・配置が完了しました。\n")
            except Exception as e:
                item['status'] = "エラー"
                err_trace = traceback.format_exc()
                self.append_log(f"  [エラー] モデル '{model_name}' のインポートに失敗しました:\n{err_trace}\n")

            self.progress_bar.setValue(int(((idx + 1) / total_count) * 100))
            self._refresh_table()
            QApplication.processEvents()

        self._is_importing = False
        self.btn_start.setEnabled(True)
        self.btn_add.setEnabled(True)
        self.btn_remove.setEnabled(True)
        self.btn_clear.setEnabled(True)
        self.lbl_progress.setText(f"完了: {success_count}/{total_count} 体のインポートが終了しました")

        self.append_log("\n==================================================\n")
        self.append_log(f">>> 全モデルの順次インポート処理が終了しました ({success_count}/{total_count} 体成功)\n")
        self.append_log("==================================================\n")

        QMessageBox.information(
            self,
            "インポート終了",
            f"複数モデルの順次インポートが終了しました。\n\n"
            f"・成功: {success_count} 体\n"
            f"・合計: {total_count} 体"
        )


# ==============================================================================
# ==============================================================================
# ベイクするモデルの確認ダイアログ (単体・複数共通)
# ==============================================================================
class MultiModelPhysicsBakeDialog(QDialog):
    """
    現在ベイク対象として設定されているMMDモデル一覧（単体・複数問わず）を確認するダイアログ
    """
    def __init__(self, parent=None):
        super(MultiModelPhysicsBakeDialog, self).__init__(parent)
        self.parent_tab = parent
        self.setWindowTitle("ベイクするモデルの確認")
        self.resize(760, 400)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.model_items = []
        self._init_ui()
        self._refresh_models_from_scene()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 説明ヘッダー
        lbl_info = QLabel(
            "<b>ベイク対象モデル一覧の確認</b><br>"
            "現在ベイク対象として設定されているMMDモデル一覧です。<br>"
            "物理ベイクはメイン画面の「リアルタイム物理ベイク実行」ボタンから行います。<br>"
            "複数モデルが存在する場合は、剛体の追突や反発を防ぐため1体ずつ順次ベイクされます。"
        )
        lbl_info.setStyleSheet("color: #cccccc; padding: 8px; background-color: #2b2b2b; border-radius: 4px; line-height: 140%;")
        main_layout.addWidget(lbl_info)

        # モデルテーブル
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["No", "モデル表示名", "Mayaノード名", "PMXモデルパス", "ベイク対象"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        main_layout.addWidget(self.table)

        # 状態表示ラベル
        self.lbl_status = QLabel("検出中...")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #52b7ff; padding: 2px;")
        main_layout.addWidget(self.lbl_status)

        # 下部ボタングループ
        h_bottom = QHBoxLayout()
        self.btn_refresh_scene = QPushButton("シーンから再取得")
        self.btn_refresh_scene.setFixedHeight(34)
        self.btn_refresh_scene.setFixedWidth(130)
        self.btn_refresh_scene.clicked.connect(self._refresh_models_from_scene)
        h_bottom.addWidget(self.btn_refresh_scene)

        h_bottom.addStretch()

        self.btn_close = QPushButton("閉じる")
        self.btn_close.setFixedWidth(100)
        self.btn_close.setFixedHeight(34)
        self.btn_close.clicked.connect(self.close)
        h_bottom.addWidget(self.btn_close)

        main_layout.addLayout(h_bottom)

    def _refresh_models_from_scene(self):
        """シーン内のMMDモデル一覧およびベイク対象状態を取得し、テーブルを更新"""
        try:
            from ..converters import vmdpaimaya
        except Exception:
            try:
                from converters import vmdpaimaya
            except Exception:
                import vmdpaimaya

        models = []
        try:
            models = vmdpaimaya.get_available_mmd_models()
        except Exception:
            pass

        default_pmx = ""
        if self.parent_tab and hasattr(self.parent_tab, 'le_pmx_path'):
            default_pmx = self.parent_tab.le_pmx_path.text().strip()

        # 親タブで選択されている対象モデル
        selected_target = None
        if self.parent_tab and hasattr(self.parent_tab, 'cbb_stream_target_model'):
            selected_target = self.parent_tab.cbb_stream_target_model.currentData()

        self.model_items = []
        is_auto_detect = not selected_target

        for node, label in models:
            # モデルノードに保存されたPMXパスがあれば優先取得
            pmx_path = default_pmx
            if mc.attributeQuery('mmdModelPath', node=node, exists=True):
                saved_path = mc.getAttr(f"{node}.mmdModelPath")
                if saved_path and os.path.exists(saved_path):
                    pmx_path = saved_path

            # ベイク対象判定
            if is_auto_detect:
                if len(models) > 1:
                    target_status = "対象 (順次ベイク)"
                else:
                    target_status = "対象 (単体ベイク)"
                is_target = True
            else:
                if node == selected_target:
                    target_status = "対象 (個別指定)"
                    is_target = True
                else:
                    target_status = "非対象 (個別指定外)"
                    is_target = False

            # 表示名から純粋なモデル名を抽出
            display_name = label
            if "(" in label and label.endswith(")"):
                inner = label[label.find("(") + 1:-1].strip()
                if inner:
                    display_name = inner

            self.model_items.append({
                'node': node,
                'name': display_name,
                'full_label': label,
                'pmx_path': pmx_path,
                'status': target_status,
                'is_target': is_target
            })

        self._update_table_view()

        active_count = sum(1 for m in self.model_items if m['is_target'])
        if is_auto_detect:
            if len(self.model_items) > 1:
                self.lbl_status.setText(f"自動検出: シーン内の全 {len(self.model_items)} 体を順次ベイク予定 (追突防止アイソレーション方式)")
            elif len(self.model_items) == 1:
                self.lbl_status.setText(f"自動検出: シーン内の {self.model_items[0]['name']} (1体) をベイク予定")
            else:
                self.lbl_status.setText("未検出: シーン内にMMDモデルが見つかりません")
        else:
            self.lbl_status.setText(f"個別指定: 選択中のモデル (1体) のみをベイク予定 (全 {len(self.model_items)} 体中)")

    def _update_table_view(self):
        """テーブルの行表示を更新"""
        self.table.setRowCount(len(self.model_items))
        for row, item in enumerate(self.model_items):
            item_no = QTableWidgetItem(str(row + 1))
            item_no.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_no)

            item_name = QTableWidgetItem(item['name'])
            self.table.setItem(row, 1, item_name)

            item_node = QTableWidgetItem(item['node'])
            self.table.setItem(row, 2, item_node)

            item_pmx = QTableWidgetItem(item['pmx_path'] or "(未設定 / メイン設定参照)")
            self.table.setItem(row, 3, item_pmx)

            item_status = QTableWidgetItem(item['status'])
            item_status.setTextAlignment(Qt.AlignCenter)
            if item['is_target']:
                item_status.setForeground(QColor("#2ecc71"))
            else:
                item_status.setForeground(QColor("#888888"))
            self.table.setItem(row, 4, item_status)


# ==============================================================================
# インポートタブ (MMD → Maya)
# ==============================================================================
class ImportTabWidget(QWidget):
    """MMDモデルをMayaへインポートするためのUIタブ"""
    def __init__(self, parent=None):
        super(ImportTabWidget, self).__init__(parent)
        self.parent_window = parent
        self.setAcceptDrops(True)
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_file = os.path.join(plugin_root, 'asset', 'khatangton1.txt')
        
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # ファイル選択ゾーン (ドラッグ＆ドロップ対応)
        file_box = QGroupBox("モデルファイル (.pmx / .pmd / .x)")
        file_layout = QVBoxLayout(file_box)
        
        h_file_input = QHBoxLayout()
        self.le_file_path = QLineEdit()
        self.le_file_path.setPlaceholderText("ファイルパスを入力、またはここにファイルをドラッグ＆ドロップ")
        self.le_file_path.textChanged.connect(self._on_file_changed)
        h_file_input.addWidget(self.le_file_path)

        self.btn_browse = QPushButton("参照...")
        self.btn_browse.setFixedWidth(75)
        self.btn_browse.clicked.connect(self._browse_file)
        h_file_input.addWidget(self.btn_browse)

        self.btn_clear_file = QPushButton("クリア")
        self.btn_clear_file.setFixedWidth(65)
        self.btn_clear_file.clicked.connect(self._clear_file)
        h_file_input.addWidget(self.btn_clear_file)
        file_layout.addLayout(h_file_input)

        # 複数モデル一括インポートボタン (試験的機能)
        self.btn_multi_import = QPushButton("複数のモデルをインポートする (試験的機能)...")
        self.btn_multi_import.setStyleSheet("font-weight: bold; padding: 6px;")
        self.btn_multi_import.clicked.connect(self._open_multi_model_import_window)
        file_layout.addWidget(self.btn_multi_import)

        layout.addWidget(file_box)

        # スケール設定

        scale_box = QGroupBox("インポート設定")
        scale_layout = QVBoxLayout(scale_box)

        h_scale = QHBoxLayout()
        h_scale.addWidget(QLabel("スケール倍率:"))
        self.le_scale = QLineEdit("8.0")
        self.le_scale.setFixedWidth(80)
        self.le_scale.textEdited.connect(self._validate_scale)
        h_scale.addWidget(self.le_scale)
        h_scale.addWidget(QLabel("(標準: 8.0)"))
        h_scale.addStretch()
        scale_layout.addLayout(h_scale)

        # チェックオプション
        self.cb_split_poly = QCheckBox("材質ごとにメッシュ（ポリゴン）を分割する")
        self.cb_create_bones = QCheckBox("スケルトン（ジョイント）を作成する")
        self.cb_create_bones.setChecked(True)
        self.cb_create_physics = QCheckBox("剛体・Jointコライダーを生成")
        self.cb_create_physics.setChecked(True)
        self.cb_create_bs = QCheckBox("ブレンドシェイプ（モーフ）を作成する")
        self.cb_create_bs.setChecked(True)
        self.cb_check_morph_bone = QCheckBox("モーフ・ボーン名チェックを実行する (辞書照合)")
        self.cb_check_morph_bone.setChecked(True)
        self.cb_check_morph_bone.setToolTip("モデルインポート時にモーフ名およびボーン名を走査し、ユーザー辞書への未登録漢字や未知名称のチェック・照合を行います。")

        scale_layout.addWidget(self.cb_split_poly)
        scale_layout.addWidget(self.cb_create_bones)
        scale_layout.addWidget(self.cb_create_physics)
        scale_layout.addWidget(self.cb_create_bs)
        scale_layout.addWidget(self.cb_check_morph_bone)

        self.cb_split_poly.toggled.connect(self._on_split_toggled)

        # マテリアルタイプ
        h_mat = QHBoxLayout()
        h_mat.addWidget(QLabel("マテリアル種別:"))
        self.cbb_material = QComboBox()
        self.cbb_material.addItems(["マテリアルなし", "Blinn", "Phong", "Lambert", "StandardSurface (Maya 2022+)", "MMD Shader (オリジナル,ベータ版)", "MMD Toon Shader (新プラグイン, 忠実再現)"])
        self.cbb_material.setCurrentText("MMD Toon Shader (新プラグイン, 忠実再現)")
        h_mat.addWidget(self.cbb_material)
        h_mat.addStretch()
        scale_layout.addLayout(h_mat)

        layout.addWidget(scale_box)

        # ライティング＆シェーディング設定
        light_box = QGroupBox("ライティング＆シェーディング設定")
        light_layout = QVBoxLayout(light_box)
        self.cb_create_light = QCheckBox("MMD標準ライトを作成する (Directional & Ambient)")
        self.cb_create_light.setChecked(True)
        self.cb_create_light.setToolTip("MMDと同等の平行光源と環境光を作成し、モデルの黒化を防ぎます。シーン内にすでにライトがある場合は自動的にスキップされます。")
        light_layout.addWidget(self.cb_create_light)

        self.cb_untone_mapped = QCheckBox("ビュー変換を Un-tone-mapped (sRGB) に設定する")
        self.cb_untone_mapped.setChecked(True)
        self.cb_untone_mapped.setToolTip("トーンマッピングによる色の暗化・沈みを防ぎ、MMD本来の明るく鮮やかな発色にします。")
        light_layout.addWidget(self.cb_untone_mapped)

        self.cb_prevent_motion_darkening = QCheckBox("モーション再生時の暗化を防止する（ブレなし最適化）")
        self.cb_prevent_motion_darkening.setChecked(True)
        self.cb_prevent_motion_darkening.setToolTip("モーション再生時にビューポートのHDRポストプロセスを最適化し、アニメーション再生時でもモデルが暗く沈むのを防止します。シャッター開度を最小(0.01)に抑えるため、ボケやブレは発生しません。")
        light_layout.addWidget(self.cb_prevent_motion_darkening)

        self.cb_enable_toon = QCheckBox("Toonシェーディング（セル影）を適用する")
        self.cb_enable_toon.setChecked(True)
        self.cb_enable_toon.setToolTip("光の当たり具合に応じたセルアニメ調の影（Toon）を適用します。OFFにするとメッシュ本来の綺麗なテクスチャを維持します。")
        light_layout.addWidget(self.cb_enable_toon)

        self.cb_create_ground_shadow = QCheckBox("MMD標準地面影 (Ground Shadow) を作成する")
        self.cb_create_ground_shadow.setChecked(True)
        self.cb_create_ground_shadow.setToolTip("MMD同等の地面（Y=0平面）に落ちる半透明シャドウプレーンを作成し、足元の浮きを防ぎます。")
        light_layout.addWidget(self.cb_create_ground_shadow)

        # セルフ影モードラジオボタン
        self.shadow_btn_group = QButtonGroup(self)
        h_shadow = QHBoxLayout()
        h_shadow.setContentsMargins(20, 0, 0, 0)
        h_shadow.setSpacing(14)

        self.rb_shadow_none = QRadioButton("セルフ影なし")
        self.rb_shadow_none.setToolTip("前髪などの落とし影を生成せず、Toonの階調表現のみを適用します。")
        self.rb_shadow_mode1 = QRadioButton("モード1 (標準セルフ影)")
        self.rb_shadow_mode1.setToolTip("MMDのモード1相当。適度に柔らかな標準セルフシャドウを生成します。")
        self.rb_shadow_mode2 = QRadioButton("モード2 (高精細セルフ影)")
        self.rb_shadow_mode2.setToolTip("MMDのモード2相当。高解像度かつシャープな落とし影を生成します。")

        self.shadow_btn_group.addButton(self.rb_shadow_none, 0)
        self.shadow_btn_group.addButton(self.rb_shadow_mode1, 1)
        self.shadow_btn_group.addButton(self.rb_shadow_mode2, 2)
        self.rb_shadow_mode1.setChecked(True)

        h_shadow.addWidget(self.rb_shadow_none)
        h_shadow.addWidget(self.rb_shadow_mode1)
        h_shadow.addWidget(self.rb_shadow_mode2)
        h_shadow.addStretch()
        light_layout.addLayout(h_shadow)

        self.cb_enable_toon.toggled.connect(self._on_toon_toggled)

        # 既存シーンのToonシェーディング修復ボタン
        h_toon_fix = QHBoxLayout()
        self.btn_fix_toon = QPushButton("Toonシェーディング設定を変更")
        self.btn_fix_toon.setToolTip("現在開いているシーンのToonシェーダーのしきい値を調整し、現在選択中の影モードを適用します。")
        self.btn_fix_toon.clicked.connect(self._fix_toon_shading)
        h_toon_fix.addWidget(self.btn_fix_toon)
        light_layout.addLayout(h_toon_fix)

        layout.addWidget(light_box)

        layout.addStretch()

        # 実行アクション
        h_action = QHBoxLayout()
        self.cb_close_on_finish = QCheckBox("完了後にウィンドウを閉じる")
        h_action.addWidget(self.cb_close_on_finish)
        h_action.addStretch()

        self.btn_execute = QPushButton("モデルをインポート")
        self.btn_execute.setProperty("class", "primary")
        self.btn_execute.setFixedHeight(46)
        self.btn_execute.setMinimumWidth(180)
        self.btn_execute.clicked.connect(self._execute_import)
        h_action.addWidget(self.btn_execute)

        layout.addLayout(h_action)

    def _load_settings(self):
        """前回のインポート設定を復元"""
        try:
            if os.path.exists(self.config_file):
                settings = {}
                ordered_lines = []
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line_str = line.strip()
                        if not line_str:
                            continue
                        if '=' in line_str:
                            k, v = line_str.split('=', 1)
                            settings[k.strip()] = v.strip()
                        ordered_lines.append(line_str)

                # キー照合、またはフォールバックとして順序照合
                file_path = settings.get("ファイルの名前", ordered_lines[0].split('=')[-1].strip() if len(ordered_lines) > 0 else "")
                scale = settings.get("尺度", ordered_lines[1].split('=')[-1].strip() if len(ordered_lines) > 1 else "8.0")
                split = int(settings.get("ポリゴンの分割", ordered_lines[2].split('=')[-1].strip() if len(ordered_lines) > 2 else 0))
                bs = int(settings.get("ブレンドシェープ", ordered_lines[3].split('=')[-1].strip() if len(ordered_lines) > 3 else 1))
                bones = int(settings.get("ジョイント", ordered_lines[4].split('=')[-1].strip() if len(ordered_lines) > 4 else 1))
                mat = int(settings.get("材質", ordered_lines[5].split('=')[-1].strip() if len(ordered_lines) > 5 else 6))
                close = int(settings.get("閉じる", ordered_lines[6].split('=')[-1].strip() if len(ordered_lines) > 6 else 0))
                light = int(settings.get("ライト", ordered_lines[7].split('=')[-1].strip() if len(ordered_lines) > 7 else 1))
                untone = int(settings.get("アントーンマップ", ordered_lines[8].split('=')[-1].strip() if len(ordered_lines) > 8 else 1))
                toon = int(settings.get("トゥーン", 1))
                physics = int(settings.get("剛体物理", 1))
                shadow_mode = int(settings.get("シャドウモード", 1))
                check_mb = int(settings.get("モーフボーンチェック", 1))
                prevent_darkening = int(settings.get("モーション暗化防止", 1))

                self.le_file_path.setText(file_path)
                self.le_scale.setText(scale)
                self.cb_split_poly.setChecked(bool(split))
                self.cb_create_bs.setChecked(bool(bs))
                self.cb_create_bones.setChecked(bool(bones))
                self.cb_create_physics.setChecked(bool(physics))
                self.cb_check_morph_bone.setChecked(bool(check_mb))
                if 0 <= mat < self.cbb_material.count():
                    self.cbb_material.setCurrentIndex(mat)
                self.cb_close_on_finish.setChecked(bool(close))
                self.cb_create_light.setChecked(bool(light))
                self.cb_untone_mapped.setChecked(bool(untone))
                self.cb_prevent_motion_darkening.setChecked(bool(prevent_darkening))
                self.cb_enable_toon.setChecked(bool(toon))
                if shadow_mode == 0:
                    self.rb_shadow_none.setChecked(True)
                elif shadow_mode == 2:
                    self.rb_shadow_mode2.setChecked(True)
                else:
                    self.rb_shadow_mode1.setChecked(True)
                self._on_toon_toggled(bool(toon))
                return
        except Exception:
            pass

        # デフォルト値
        self.le_scale.setText("8.0") # インポート時 スケールサイズ
        self.cb_create_bones.setChecked(True)
        self.cb_create_physics.setChecked(True)
        self.cb_create_bs.setChecked(True)
        self.cb_check_morph_bone.setChecked(True)
        self.cbb_material.setCurrentIndex(6) # MMD Toon Shader (新プラグイン, 忠実再現)
        self.cb_close_on_finish.setChecked(False)
        self.cb_create_light.setChecked(True)
        self.cb_untone_mapped.setChecked(True)
        self.cb_prevent_motion_darkening.setChecked(True)
        self.cb_enable_toon.setChecked(True)
        self.rb_shadow_mode1.setChecked(True)
        self._on_toon_toggled(True)

    def _save_settings(self):
        """現在の設定を保存"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(f"ファイルの名前 = {self.le_file_path.text()}\n")
                f.write(f"尺度 = {self.le_scale.text()}\n")
                f.write(f"ポリゴンの分割 = {int(self.cb_split_poly.isChecked())}\n")
                f.write(f"ブレンドシェープ = {int(self.cb_create_bs.isChecked())}\n")
                f.write(f"ジョイント = {int(self.cb_create_bones.isChecked())}\n")
                f.write(f"材質 = {self.cbb_material.currentIndex()}\n")
                f.write(f"閉じる = {int(self.cb_close_on_finish.isChecked())}\n")
                f.write(f"ライト = {int(self.cb_create_light.isChecked())}\n")
                f.write(f"アントーンマップ = {int(self.cb_untone_mapped.isChecked())}\n")
                f.write(f"モーション暗化防止 = {int(self.cb_prevent_motion_darkening.isChecked())}\n")
                f.write(f"トゥーン = {int(self.cb_enable_toon.isChecked())}\n")
                f.write(f"剛体物理 = {int(self.cb_create_physics.isChecked())}\n")
                f.write(f"シャドウモード = {self.get_shadow_mode()}\n")
                f.write(f"モーフボーンチェック = {int(self.cb_check_morph_bone.isChecked())}\n")
        except Exception:
            pass

    def _on_file_changed(self, path):
        ext = os.path.splitext(path)[1].lower()
        valid = ext in ['.pmx', '.pmd', '.x'] and os.path.exists(path)
        self.btn_execute.setEnabled(valid)
        self._on_split_toggled()
        self._save_settings()

    def _clear_file(self):
        """モデルファイル入力欄をクリア"""
        self.le_file_path.clear()
        self._save_settings()

    def _on_split_toggled(self, checked=None):
        """材質分割チェック変更時の制限事項確認ダイアログおよび連動制御"""
        split = self.cb_split_poly.isChecked()

        # ユーザーが「材質ごとにメッシュを分割」にチェックを入れた場合の確認
        if split:
            dialog_msg = (
                "【材質分割インポートの制限事項】\n\n"
                "材質ごとにメッシュ（ポリゴン）を分割してインポートする場合、"
                "MMDモデルの構造上の理由により以下の制限が発生します：\n\n"
                "・スケルトン（ジョイント）は作成されません\n"
                "・剛体およびJointは作成されません\n"
                "・ブレンドシェイプ（モーフ）は作成されません\n"
                "・モーション（VMD）を適用・再生することはできなくなります\n\n"
                "材質ごとにメッシュを分割してインポートしますか？"
            )
            res = QMessageBox.warning(
                self,
                "材質分割インポートの確認",
                dialog_msg,
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel
            )

            if res != QMessageBox.Ok:
                # キャンセルされた場合はチェックをOFFに戻す
                self.cb_split_poly.blockSignals(True)
                self.cb_split_poly.setChecked(False)
                self.cb_split_poly.blockSignals(False)
                split = False

        ext = os.path.splitext(self.le_file_path.text())[1].lower()
        can_rig = (ext != '.x') and not split

        self.cb_create_bones.setEnabled(can_rig)
        self.cb_create_bs.setEnabled(can_rig)
        self.cb_create_physics.setEnabled(can_rig)

        if split:
            # 分割時は作成されない項目をOFFにする
            self.cb_create_bones.setChecked(False)
            self.cb_create_bs.setChecked(False)
            self.cb_create_physics.setChecked(False)
        else:
            # 分割解除時は標準の有効状態に戻す
            if can_rig:
                self.cb_create_bones.setChecked(True)
                self.cb_create_bs.setChecked(True)
                self.cb_create_physics.setChecked(True)

    def _browse_file(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "MMDモデルファイルを選択",
            self.le_file_path.text(),
            "MMD Models (*.pmx *.pmd *.x);;PMX (*.pmx);;PMD (*.pmd);;DirectX (*.x)"
        )
        if path:
            self.le_file_path.setText(path)
            self._save_settings()

    def _open_multi_model_import_window(self):
        """複数モデル順次インポート用のダイアログを表示"""
        if not hasattr(self, '_multi_import_dialog') or self._multi_import_dialog is None:
            self._multi_import_dialog = MultiModelImportDialog(self)
        self._multi_import_dialog.show()
        self._multi_import_dialog.raise_()
        self._multi_import_dialog.activateWindow()

    def _validate_scale(self, text):
        try:
            float(text)
        except ValueError:
            self.le_scale.setText("1.0")

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.le_file_path.setText(path)

    def _on_toon_toggled(self, checked):
        """ToonチェックボックスのON/OFFに応じて影モードのラジオボタンを有効/無効化"""
        self.rb_shadow_none.setEnabled(checked)
        self.rb_shadow_mode1.setEnabled(checked)
        self.rb_shadow_mode2.setEnabled(checked)

    def get_shadow_mode(self):
        """選択されているセルフ影モード (0: なし, 1: モード1, 2: モード2)"""
        return max(self.shadow_btn_group.checkedId(), 0)

    def _fix_toon_shading(self):
        """現在のMayaシーン内のToonシェーダーおよびセルフ影モードを修復・最適化"""
        try:
            shadow_mode = self.get_shadow_mode() if self.cb_enable_toon.isChecked() else 0
            fixed_count = pmxpaimaya.fix_toon_shading_in_scene(shadow_mode=shadow_mode)
            mode_names = ["セルフ影なし", "モード1 (標準セルフ影)", "モード2 (高精細セルフ影)"]
            mc.inViewMessage(amg=f'<span style="color:#2ecc71;">MMD Tools for Maya:</span> Toon設定完了（{mode_names[shadow_mode]}）。', pos='topCenter', fade=True)
            QMessageBox.information(
                self,
                "Toon設定完了",
                f"{fixed_count} 個の要素を設定しました。\n"
                f"影設定: {mode_names[shadow_mode]}\n"
            )
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"Toonシェーディング設定中にエラーが発生しました:\n{e}")

    def _analyze_and_save_structure(self):
        """選択中モデルの材質、ボーン、モーフ、剛体、Jointを一括保存し、未登録ボーン辞書チェックを実行"""
        file_path = self.le_file_path.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "エラー", "有効なPMXモデルファイルを指定してください。")
            return

        if not file_path.lower().endswith('.pmx'):
            QMessageBox.information(self, "案内", "詳細解析および辞書照合はPMXモデル形式 (.pmx) のみ対応しています。")
            return

        try:
            # ユーザー辞書の未登録ボーン名チェック & 登録GUI
            if check_and_prompt_user_dict:
                check_and_prompt_user_dict(self.parent_window or self, file_path)

            # モデル構造の一括保存 (JSON)
            if export_pmx_structure:
                saved_path, data = export_pmx_structure(file_path)
                QMessageBox.information(
                    self,
                    "PMXモデル解析完了",
                    f"モデル構造の一括保存が完了しました！\n\n"
                    f"保存先:\n{saved_path}\n\n"
                    f"・材質: {len(data['materials'])} 件\n"
                    f"・ボーン: {len(data['bones'])} 件\n"
                    f"・モーフ: {len(data['morphs'])} 件\n"
                    f"・剛体: {len(data['rigid_bodies'])} 件\n"
                    f"・Joint: {len(data['joints'])} 件"
                )
        except Exception as e:
            QMessageBox.warning(self, "解析エラー", f"PMXモデルの解析中にエラーが発生しました:\n{e}")

    def _open_morph_window(self):
        """MMD本家風の表情操作ウィンドウを開く"""
        try:
            from .morph_window import show_morph_window
        except Exception:
            try:
                from morph_window import show_morph_window
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"表情操作モジュールの読み込みに失敗しました:\n{e}")
                return

        show_morph_window(parent=get_maya_main_window())

    def _execute_import(self):
        file_path = self.le_file_path.text().strip()
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "エラー", "指定されたモデルファイルが存在しません。")
            return

        # 旧形式 PMD の検知と PMX 変換プロンプト
        if file_path.lower().endswith('.pmd'):
            reply = QMessageBox.question(
                self,
                "PMD形式の検出 (非推奨形式)",
                "旧形式の PMD モデルファイルが選択されています。\n"
                "現在、PMD形式は非推奨となっております。\n\n"
                "推奨される PMX 形式へ変換してインポートしますか？\n"
                "（「はい」をクリックすると変換が始まり、元の PMD と同一フォルダに変換した PMX が保存され、その PMX をインポートします）",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Cancel:
                print("[MMD Tools for Maya] インポートがキャンセルされました。")
                return
            elif reply == QMessageBox.Yes:
                print(f"[PMD変換] PMDからPMXへの自動変換を開始します: {os.path.basename(file_path)}")
                try:
                    try:
                        from ..converters.pmd2pmx import convert_pmd_to_pmx
                    except Exception:
                        from converters.pmd2pmx import convert_pmd_to_pmx

                    converted_pmx_path = convert_pmd_to_pmx(file_path)
                    print(f"[PMD変換] 変換が完了しました: {converted_pmx_path}")
                    # ファイルパス入力欄を更新し、以後のインポート対象を生成された PMX に切り替え
                    self.le_file_path.setText(converted_pmx_path)
                    file_path = converted_pmx_path
                    self._save_settings()
                except Exception as e:
                    QMessageBox.critical(self, "PMD変換エラー", f"PMXへの変換中にエラーが発生しました:\n{e}\n\n従来のPMDとしてインポートを試みます。")
                    print(f"[PMD変換エラー] {e}")

        check_morph_bone = self.cb_check_morph_bone.isChecked()
        try:
            scale = float(self.le_scale.text())
        except ValueError:
            scale = 1.0

        split_poly = self.cb_split_poly.isChecked()
        create_bs = not split_poly and self.cb_create_bs.isChecked()
        create_bones = not split_poly and self.cb_create_bones.isChecked()
        material_type = self.cbb_material.currentIndex()
        create_light = self.cb_create_light.isChecked()
        create_ground_shadow = self.cb_create_ground_shadow.isChecked()
        set_untone_mapped = self.cb_untone_mapped.isChecked()
        prevent_motion_darkening = self.cb_prevent_motion_darkening.isChecked()
        enable_toon = self.cb_enable_toon.isChecked()
        shadow_mode = self.get_shadow_mode() if enable_toon else 0

        create_physics = self.cb_create_physics.isChecked()

        # インポート開始直後に実行ログダイアログを生成・起動
        log_dialog = ExecutionLogDialog(self.parent_window or self, title="モデルインポート実行ログ")

        def full_import_task():
            total_start_time = time.time()

            # [PMXチェック] モーフ・ボーン名チェック & ユーザー辞書照合、構成要素データ保存
            if file_path.lower().endswith('.pmx'):
                print("==================================================")
                print(f"[PMXチェック] モデルファイル: {os.path.basename(file_path)}")
                if check_morph_bone:
                    print("  - モーフ・ボーン名チェック（辞書照合）: 実行中...")
                    if check_and_prompt_user_dict:
                        try:
                            check_and_prompt_user_dict(log_dialog, file_path)
                            print("  - モーフ・ボーン名チェック: 完了")
                        except Exception as e:
                            print(f"  - モーフ・ボーン名チェック: 完了 (警告: {e})")
                    else:
                        print("  - モーフ・ボーン名チェック: スキップ (モジュールなし)")
                else:
                    print("  - モーフ・ボーン名チェック: スキップ (設定OFF)")

                # 材質・ボーン・モーフ・剛体・Joint の一括保存
                if export_pmx_structure:
                    print("  - モデル構成要素（材質/ボーン/モーフ/剛体/Joint）データ保存: 実行中...")
                    try:
                        export_pmx_structure(file_path)
                        print("  - モデル構成要素データ保存: 完了")
                    except Exception as e:
                        print(f"  - モデル構成要素データ保存: 完了 (警告: {e})")
                print("==================================================")

            import importlib
            importlib.reload(pmxpaimaya)
            import_func = getattr(pmxpaimaya, 'import_pmx', pmxpaimaya.sang)
            res = import_func(
                file_path, scale, split_poly, create_bs, create_bones, material_type, create_light, set_untone_mapped, enable_toon, shadow_mode=shadow_mode, create_ground_shadow=create_ground_shadow, show_completion_message=False, prevent_motion_darkening=prevent_motion_darkening, create_physics=create_physics
            )

            # すべてのインポート工程（メッシュ・ボーン・剛体・Joint等）の終了直後に総括完了メッセージを表示
            total_elapsed = time.time() - total_start_time
            print("==================================================")
            print(f"モデルインポートが完了しました！ (所要時間: {total_elapsed:.2f}秒)")
            print("==================================================")
            return res

        # ログウィンドウを直ちに起動して全タスクを実行
        success = log_dialog.run_task(full_import_task)

        if success:
            # 物理演算タブおよびoptionVarへモデルパスを自動反映
            if file_path.lower().endswith('.pmx'):
                mc.optionVar(sv=("MMDToolsForMaya_LastPmxPath", file_path))
                if self.parent_window and hasattr(self.parent_window, 'tab_physics'):
                    try:
                        self.parent_window.tab_physics.le_pmx_path.setText(file_path)
                    except Exception:
                        pass

            mc.inViewMessage(amg='<span style="color:#52b7ff;">MMD Tools for Maya:</span> インポートが完了しました。', pos='topCenter', fade=True)
            self._save_settings()

            if self.cb_close_on_finish.isChecked() and self.parent_window:
                self.parent_window.close()

# ==============================================================================
# エクスポートタブ (Maya → MMD)
# ==============================================================================
class ExportTabWidget(QWidget):
    """MayaシーンからPMX、VMDモーション、VPDポーズへエクスポートするための統合UIタブ"""
    def __init__(self, parent=None):
        super(ExportTabWidget, self).__init__(parent)
        self.parent_window = parent
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_file = os.path.join(plugin_root, 'asset', 'khatangton2.txt')

        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # スクロールエリアを導入して縦長レイアウトに対応
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(14)
        layout.setContentsMargins(12, 12, 12, 12)

        # モデルデータ (.pmx) エクスポートグループ
        pmx_box = QGroupBox("モデルデータ (.pmx) エクスポート(試験機能)")
        pmx_layout = QVBoxLayout(pmx_box)
        pmx_layout.setSpacing(10)

        # 保存先 PMX ファイル
        h_pmx_file = QHBoxLayout()
        self.le_file_path = QLineEdit()
        self.le_file_path.setPlaceholderText("出力先パス (.pmx)")
        self.le_file_path.textChanged.connect(self._on_file_changed)
        h_pmx_file.addWidget(self.le_file_path)

        self.btn_browse = QPushButton("保存先...")
        self.btn_browse.setFixedWidth(95)
        self.btn_browse.clicked.connect(self._browse_save_file)
        h_pmx_file.addWidget(self.btn_browse)

        self.btn_clear_file = QPushButton("クリア")
        self.btn_clear_file.setFixedWidth(65)
        self.btn_clear_file.clicked.connect(self._clear_file)
        h_pmx_file.addWidget(self.btn_clear_file)
        pmx_layout.addLayout(h_pmx_file)

        # PMX オプション
        h_scale = QHBoxLayout()
        h_scale.addWidget(QLabel("スケール倍率:"))
        self.le_scale = QLineEdit("0.125")
        self.le_scale.setFixedWidth(80)
        self.le_scale.textEdited.connect(self._validate_scale)
        h_scale.addWidget(self.le_scale)
        h_scale.addWidget(QLabel("(インポート時が8.0の場合は 0.125 を推奨)"))
        h_scale.addStretch()
        pmx_layout.addLayout(h_scale)

        self.cb_export_bones = QCheckBox("スケルトン（ボーン）を出力")
        self.cb_export_morphs = QCheckBox("ブレンドシェイプ（モーフ）を出力")
        self.cb_export_materials = QCheckBox("マテリアル（材質）を出力")
        self.cb_copy_textures = QCheckBox("テクスチャファイルを保存先フォルダへコピー")

        pmx_layout.addWidget(self.cb_export_bones)
        pmx_layout.addWidget(self.cb_export_morphs)
        pmx_layout.addWidget(self.cb_export_materials)
        pmx_layout.addWidget(self.cb_copy_textures)

        # 出力対象メッシュ
        h_poly = QHBoxLayout()
        h_poly.addWidget(QLabel("出力対象メッシュ:"))
        self.btng_target = QButtonGroup(self)
        self.rb_all_mesh = QRadioButton("シーン内のすべての対象メッシュ")
        self.rb_selected_mesh = QRadioButton("選択中のメッシュのみ")
        self.btng_target.addButton(self.rb_all_mesh)
        self.btng_target.addButton(self.rb_selected_mesh)
        self.rb_all_mesh.setChecked(True)
        h_poly.addWidget(self.rb_all_mesh)
        h_poly.addWidget(self.rb_selected_mesh)
        h_poly.addStretch()
        pmx_layout.addLayout(h_poly)

        # PMX 実行ボタン
        self.btn_execute = QPushButton("PMX をエクスポート")
        self.btn_execute.setProperty("class", "primary")
        self.btn_execute.setFixedHeight(42)
        self.btn_execute.clicked.connect(self._execute_export)
        pmx_layout.addWidget(self.btn_execute)

        layout.addWidget(pmx_box)

        # MMD モーションデータ (.vmd) エクスポート (試験的機能) グループ
        vmd_box = QGroupBox("MMD モーションデータ (.vmd) エクスポート (試験的機能)")
        vmd_layout = QVBoxLayout(vmd_box)
        vmd_layout.setSpacing(10)

        # 適用先モデル選択
        h_vmd_model = QHBoxLayout()
        h_vmd_model.addWidget(QLabel("対象モデル:"))
        self.cbb_vmd_target_model = QComboBox()
        self.btn_refresh_vmd_models = QPushButton("更新")
        self.btn_refresh_vmd_models.setFixedWidth(75)
        self.btn_refresh_vmd_models.clicked.connect(self._refresh_models)
        h_vmd_model.addWidget(self.cbb_vmd_target_model)
        h_vmd_model.addWidget(self.btn_refresh_vmd_models)
        vmd_layout.addLayout(h_vmd_model)

        h_vmd_scale = QHBoxLayout()
        h_vmd_scale.addWidget(QLabel("スケール倍率:"))
        self.le_vmd_scale = QLineEdit("8.0")
        self.le_vmd_scale.setFixedWidth(80)
        h_vmd_scale.addWidget(self.le_vmd_scale)
        h_vmd_scale.addWidget(QLabel("(インポート時と同じ倍率を指定)"))
        h_vmd_scale.addStretch()
        vmd_layout.addLayout(h_vmd_scale)

        h_vmd_targets = QHBoxLayout()
        self.cb_vmd_exp_bones = QCheckBox("ボーンアニメーション")
        self.cb_vmd_exp_bones.setChecked(True)
        h_vmd_targets.addWidget(self.cb_vmd_exp_bones)

        self.cb_vmd_exp_morphs = QCheckBox("表情モーフアニメーション")
        self.cb_vmd_exp_morphs.setChecked(True)
        h_vmd_targets.addWidget(self.cb_vmd_exp_morphs)

        self.cb_vmd_exp_camera = QCheckBox("カメラアニメーション")
        self.cb_vmd_exp_camera.setChecked(False)
        h_vmd_targets.addWidget(self.cb_vmd_exp_camera)
        h_vmd_targets.addStretch()
        vmd_layout.addLayout(h_vmd_targets)

        h_vmd_range = QHBoxLayout()
        self.rb_vmd_exp_slider = QRadioButton("タイムスライダー範囲")
        self.rb_vmd_exp_slider.setChecked(True)
        h_vmd_range.addWidget(self.rb_vmd_exp_slider)

        self.rb_vmd_exp_custom = QRadioButton("カスタム範囲:")
        h_vmd_range.addWidget(self.rb_vmd_exp_custom)

        self.spn_vmd_start = QSpinBox()
        self.spn_vmd_start.setRange(-999999, 999999)
        self.spn_vmd_start.setValue(0)
        self.spn_vmd_start.setEnabled(False)
        h_vmd_range.addWidget(self.spn_vmd_start)

        lbl_to = QLabel("〜")
        h_vmd_range.addWidget(lbl_to)

        self.spn_vmd_end = QSpinBox()
        self.spn_vmd_end.setRange(-999999, 999999)
        self.spn_vmd_end.setValue(100)
        self.spn_vmd_end.setEnabled(False)
        h_vmd_range.addWidget(self.spn_vmd_end)

        self.rb_vmd_exp_custom.toggled.connect(self.spn_vmd_start.setEnabled)
        self.rb_vmd_exp_custom.toggled.connect(self.spn_vmd_end.setEnabled)
        h_vmd_range.addStretch()
        vmd_layout.addLayout(h_vmd_range)

        h_vmd_opts = QHBoxLayout()
        self.cb_vmd_exp_simplify = QCheckBox("静止フレームの重複キーを間引く (軽量化)")
        self.cb_vmd_exp_simplify.setChecked(True)
        h_vmd_opts.addWidget(self.cb_vmd_exp_simplify)
        h_vmd_opts.addStretch()
        vmd_layout.addLayout(h_vmd_opts)

        self.btn_export_vmd = QPushButton("アニメーションをVMD書き出し (エクスポート) (試験的機能)")
        self.btn_export_vmd.setFixedHeight(40)
        self.btn_export_vmd.setStyleSheet("QPushButton { background-color: #2b5b84; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3b7bb4; }")
        self.btn_export_vmd.setToolTip("選択中モデルのボーンおよびモーフアニメーションをMMD公式モーション (.vmd) として保存します。")
        self.btn_export_vmd.clicked.connect(self._on_export_vmd)
        vmd_layout.addWidget(self.btn_export_vmd)

        layout.addWidget(vmd_box)

        # MMD ポーズデータ (.vpd) エクスポート (試験的機能) グループ
        vpd_box = QGroupBox("MMD ポーズデータ (.vpd) エクスポート (試験的機能)")
        vpd_layout = QVBoxLayout(vpd_box)
        vpd_layout.setSpacing(10)

        h_vpd_model = QHBoxLayout()
        h_vpd_model.addWidget(QLabel("対象モデル:"))
        self.cbb_vpd_target_model = QComboBox()
        self.btn_refresh_vpd_models = QPushButton("更新")
        self.btn_refresh_vpd_models.setFixedWidth(75)
        self.btn_refresh_vpd_models.clicked.connect(self._refresh_models)
        h_vpd_model.addWidget(self.cbb_vpd_target_model)
        h_vpd_model.addWidget(self.btn_refresh_vpd_models)
        vpd_layout.addLayout(h_vpd_model)

        h_vpd_scale = QHBoxLayout()
        h_vpd_scale.addWidget(QLabel("スケール倍率:"))
        self.le_vpd_scale = QLineEdit("8.0")
        self.le_vpd_scale.setFixedWidth(80)
        h_vpd_scale.addWidget(self.le_vpd_scale)
        h_vpd_scale.addWidget(QLabel("(インポート時と同じ倍率を指定)"))
        h_vpd_scale.addStretch()
        vpd_layout.addLayout(h_vpd_scale)

        self.btn_export_vpd = QPushButton("現在のポーズをVPD保存 (エクスポート) (試験的機能)")
        self.btn_export_vpd.setFixedHeight(40)
        self.btn_export_vpd.setStyleSheet("QPushButton { background-color: #346856; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #458a72; }")
        self.btn_export_vpd.setToolTip("現在フレームのモデルのボーン姿勢および表情モーフを .vpd ファイルとして保存します。")
        self.btn_export_vpd.clicked.connect(self._on_export_vpd)
        vpd_layout.addWidget(self.btn_export_vpd)

        layout.addWidget(vpd_box)

        layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        # 実行完了後アクション
        h_action = QHBoxLayout()
        h_action.setContentsMargins(12, 6, 12, 10)
        self.cb_close_on_finish = QCheckBox("完了後にウィンドウを閉じる")
        h_action.addWidget(self.cb_close_on_finish)
        h_action.addStretch()
        main_layout.addLayout(h_action)

        self._refresh_models()

    def showEvent(self, event):
        super(ExportTabWidget, self).showEvent(event)
        self._refresh_models()

    def _refresh_models(self):
        """シーン内のMMDモデル一覧を取得してVMD/VPDの対象モデルコンボボックスへ設定"""
        for cbb in [getattr(self, 'cbb_vmd_target_model', None), getattr(self, 'cbb_vpd_target_model', None)]:
            if cbb is None:
                continue
            cur = cbb.currentData()
            cbb.clear()
            cbb.addItem("シーン内の全MMDモデル / 自動検出", None)
            try:
                models = vmdpaimaya.get_available_mmd_models()
                for node_name, label in models:
                    cbb.addItem(label, node_name)
            except Exception:
                pass
            if cur:
                idx = cbb.findData(cur)
                if idx >= 0:
                    cbb.setCurrentIndex(idx)

    def _load_settings(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    file_path = f.readline().split('=')[-1].strip()
                    scale = f.readline().split('=')[-1].strip()
                    bs = int(f.readline().split('=')[-1].strip())
                    bones = int(f.readline().split('=')[-1].strip())
                    mat = int(f.readline().split('=')[-1].strip())
                    copy_tex = int(f.readline().split('=')[-1].strip())
                    all_poly = int(f.readline().split('=')[-1].strip())
                    close = int(f.readline().split('=')[-1].strip())

                self.le_file_path.setText(file_path)
                self.le_scale.setText(scale)
                self.cb_export_morphs.setChecked(bool(bs))
                self.cb_export_bones.setChecked(bool(bones))
                self.cb_export_materials.setChecked(bool(mat))
                self.cb_copy_textures.setChecked(bool(copy_tex))
                if all_poly:
                    self.rb_all_mesh.setChecked(True)
                else:
                    self.rb_selected_mesh.setChecked(True)
                self.cb_close_on_finish.setChecked(bool(close))
                return
        except Exception:
            pass

        self.le_scale.setText("0.125")
        self.cb_export_bones.setChecked(True)
        self.cb_export_morphs.setChecked(True)
        self.cb_export_materials.setChecked(True)
        self.cb_copy_textures.setChecked(False)
        self.cb_close_on_finish.setChecked(False)

    def _save_settings(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(f"ファイルの名前 = {self.le_file_path.text()}\n")
                f.write(f"尺度 = {self.le_scale.text()}\n")
                f.write(f"ブレンドシェープ = {int(self.cb_export_morphs.isChecked())}\n")
                f.write(f"ジョイント = {int(self.cb_export_bones.isChecked())}\n")
                f.write(f"材質 = {int(self.cb_export_materials.isChecked())}\n")
                f.write(f"テクスチャのコピー = {int(self.cb_copy_textures.isChecked())}\n")
                f.write(f"ポリゴン全部 = {int(self.rb_all_mesh.isChecked())}\n")
                f.write(f"閉じる = {int(self.cb_close_on_finish.isChecked())}\n")
        except Exception:
            pass

    def _on_file_changed(self, path):
        valid = path.lower().endswith('.pmx')
        self.btn_execute.setEnabled(valid)
        self._save_settings()

    def _clear_file(self):
        """保存先ファイル入力欄をクリア"""
        self.le_file_path.clear()
        self._save_settings()

    def _browse_save_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "エクスポート先 PMX を指定",
            self.le_file_path.text(),
            "PMX Model (*.pmx)"
        )
        if path:
            if not path.lower().endswith('.pmx'):
                path += '.pmx'
            self.le_file_path.setText(path)
            self._save_settings()

    def _validate_scale(self, text):
        try:
            float(text)
        except ValueError:
            self.le_scale.setText("0.125")

    def _execute_export(self):
        file_path = self.le_file_path.text().strip()
        if not file_path:
            QMessageBox.warning(self, "エラー", "保存先のファイルパスを指定してください。")
            return

        try:
            scale = float(self.le_scale.text())
        except ValueError:
            scale = 0.125

        export_bones = self.cb_export_bones.isChecked()
        export_morphs = self.cb_export_morphs.isChecked()
        export_materials = self.cb_export_materials.isChecked()
        copy_textures = self.cb_copy_textures.isChecked()
        all_mesh = self.rb_all_mesh.isChecked()

        # ログウィンドウを起動して実行
        log_dialog = ExecutionLogDialog(self.parent_window or self, title="PMXエクスポート実行ログ")
        export_func = getattr(mayapaipmx, 'export_pmx', mayapaipmx.sang)
        success = log_dialog.run_task(
            export_func,
            file_path, scale, export_bones, export_morphs, export_materials, copy_textures, all_mesh
        )

        if success:
            mc.inViewMessage(amg='<span style="color:#52b7ff;">MMD Tools for Maya:</span> エクスポートが完了しました。', pos='topCenter', fade=True)
            self._save_settings()

            if self.cb_close_on_finish.isChecked() and self.parent_window:
                self.parent_window.close()

    def _on_export_vpd(self):
        """現在のポーズをVPDファイルとして保存 (試験的機能)"""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "VPDポーズの保存先を指定",
            "",
            "VPD Pose Data (*.vpd);;All Files (*.*)"
        )
        if not path:
            return

        if not path.lower().endswith('.vpd'):
            path += '.vpd'

        target_model = self.cbb_vpd_target_model.currentData()
        try:
            scale = float(self.le_vpd_scale.text())
        except ValueError:
            scale = 8.0

        try:
            from ..converters import vmdpaimaya
        except Exception:
            from converters import vmdpaimaya

        try:
            res = vmdpaimaya.export_vpd(path, target_model_node=target_model, scale=scale)
            QMessageBox.information(
                self,
                "VPD保存完了",
                f"現在の姿勢をVPDポーズファイルとして保存しました。\n"
                f"・ボーン数: {res['bones_exported']} 本\n"
                f"・モーフ数: {res['morphs_exported']} 個\n"
                f"・保存先: {os.path.basename(path)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"VPDポーズの保存中にエラーが発生しました:\n{e}")

    def _on_export_vmd(self):
        """現在のシーンアニメーションをVMDファイルとして保存 (試験的機能)"""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "VMDモーションの保存先を指定",
            "",
            "VMD Motion Data (*.vmd);;All Files (*.*)"
        )
        if not path:
            return

        if not path.lower().endswith('.vmd'):
            path += '.vmd'

        target_model = self.cbb_vmd_target_model.currentData()
        try:
            scale = float(self.le_vmd_scale.text())
        except ValueError:
            scale = 8.0

        if self.rb_vmd_exp_custom.isChecked():
            start_f = self.spn_vmd_start.value()
            end_f = self.spn_vmd_end.value()
        else:
            try:
                start_f = int(mc.playbackOptions(query=True, minTime=True))
                end_f = int(mc.playbackOptions(query=True, maxTime=True))
            except Exception:
                start_f = 0
                end_f = 100

        exp_bones = self.cb_vmd_exp_bones.isChecked()
        exp_morphs = self.cb_vmd_exp_morphs.isChecked()
        exp_camera = self.cb_vmd_exp_camera.isChecked()
        simplify = self.cb_vmd_exp_simplify.isChecked()

        try:
            from ..converters import vmdpaimaya
        except Exception:
            from converters import vmdpaimaya

        try:
            res = vmdpaimaya.export_vmd(
                path,
                target_model_node=target_model,
                start_frame=start_f,
                end_frame=end_f,
                scale=scale,
                export_bones=exp_bones,
                export_morphs=exp_morphs,
                export_camera=exp_camera,
                simplify_keys=simplify
            )
            QMessageBox.information(
                self,
                "VMD保存完了",
                f"アニメーションをVMDモーションファイルとして保存しました。\n"
                f"・ボーンキー総数: {res['total_bone_frames']:,}\n"
                f"・モーフキー総数: {res['total_morph_frames']:,}\n"
                f"・カメラキー総数: {res['total_camera_frames']:,}\n"
                f"・保存先: {os.path.basename(path)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"VMDモーションの保存中にエラーが発生しました:\n{e}")

# ==============================================================================
# HumanIK タブ
# ==============================================================================
class HikTabWidget(QWidget):
    """MMDモデルのボーンをMayaのHumanIKに自動定義するUIタブ"""
    def __init__(self, parent=None):
        super(HikTabWidget, self).__init__(parent)
        self.parent_window = parent
        self.current_hik_node = None
        self.current_mapped_dict = {}
        self.last_log_text = ""
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # キャラクターモデルの選択
        model_box = QGroupBox("対象モデル選択")
        model_layout = QHBoxLayout(model_box)

        self.cbb_models = QComboBox()
        self.cbb_models.setEditable(False)
        model_layout.addWidget(self.cbb_models)

        self.btn_refresh = QPushButton("更新")
        self.btn_refresh.setFixedWidth(80)
        self.btn_refresh.clicked.connect(self._refresh_models)
        model_layout.addWidget(self.btn_refresh)

        self.btn_define = QPushButton("キャラクター定義を作成")
        self.btn_define.setFixedWidth(160)
        self.btn_define.clicked.connect(self._on_click_define_hik)
        model_layout.addWidget(self.btn_define)

        layout.addWidget(model_box)

        # ステータス情報表示
        self.lbl_status = QLabel("※ モデルを選択し、「キャラクター定義を作成」を押してください。")
        self.lbl_status.setStyleSheet("color: #aaa; font-size: 13px; margin: 2px 4px;")
        layout.addWidget(self.lbl_status)

        # ボーンマッピング一覧
        mapping_box = QGroupBox("HumanIK ボーンマッピング一覧")
        mapping_layout = QVBoxLayout(mapping_box)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_area.setWidget(self.scroll_content)
        mapping_layout.addWidget(self.scroll_area)

        layout.addWidget(mapping_box)

        # アクションボタン
        h_action = QHBoxLayout()

        self.btn_show_log = QPushButton("実行ログを表示 / コピー")
        self.btn_show_log.setFixedHeight(40)
        self.btn_show_log.clicked.connect(self._show_last_log)
        h_action.addWidget(self.btn_show_log)

        self.btn_reapply_tpose = QPushButton("Tポーズ (腕水平化) を再適用")
        self.btn_reapply_tpose.setFixedHeight(40)
        self.btn_reapply_tpose.setEnabled(False)
        self.btn_reapply_tpose.clicked.connect(self._reapply_tpose)
        h_action.addWidget(self.btn_reapply_tpose)

        h_action.addStretch()

        self.btn_create_rig = QPushButton("コントロールリグを作成")
        self.btn_create_rig.setProperty("class", "primary")
        self.btn_create_rig.setFixedHeight(44)
        self.btn_create_rig.setMinimumWidth(200)
        self.btn_create_rig.setEnabled(False)
        self.btn_create_rig.clicked.connect(self._on_click_create_rig)
        h_action.addWidget(self.btn_create_rig)

        layout.addLayout(h_action)

        self._refresh_models()

    def _show_last_log(self):
        """直近の実行ログダイアログを表示します"""
        dlg = ExecutionLogDialog(self.parent_window or self, title="HumanIK 実行ログ")
        dlg.progress_bar.setRange(0, 1)
        dlg.progress_bar.setValue(1)
        dlg.btn_close.setEnabled(True)
        dlg.lb_status.setText("直近の実行ログ")
        dlg.append_log(self.last_log_text if self.last_log_text else "（まだ実行ログはありません）\n")
        dlg.exec_()

    def _refresh_models(self):
        """シーン内のMMDモデル一覧を取得してコンボボックスを更新します"""
        self.cbb_models.clear()
        found = False
        try:
            try:
                from ..converters import vmdpaimaya
            except Exception:
                try:
                    from converters import vmdpaimaya
                except Exception:
                    import vmdpaimaya

            models = vmdpaimaya.get_available_mmd_models()
            for node_name, label in models:
                self.cbb_models.addItem(label, node_name)
                found = True
        except Exception:
            pass

        # フォールバック検出
        if not found:
            try:
                for node in mc.ls(type='transform') or []:
                    if mc.attributeQuery('MMD_model', node=node, exists=True) or mc.attributeQuery('mmdModelRoot', node=node, exists=True):
                        orig = mc.getAttr(f"{node}.originalName") if mc.attributeQuery('originalName', node=node, exists=True) else node
                        self.cbb_models.addItem(f"{node} ({orig})", node)
                        found = True
            except Exception:
                pass

        if not found:
            self.cbb_models.addItem("（シーン内にMMDモデルが見つかりません）", None)

    def _on_click_define_hik(self):
        """キャラクター定義作成タスクを事前確認の上で実行します"""
        target_model = self.cbb_models.currentData()
        if not target_model:
            target_text = self.cbb_models.currentText().strip()
            if target_text and not target_text.startswith("（"):
                target_model = target_text.split(" ")[0].strip()

        if not target_model or not mc.objExists(target_model):
            QMessageBox.warning(self, "エラー", "有効なMMDモデルを選択してください。")
            return

        # 事前ボーン存在チェック
        joints = mc.listRelatives(target_model, allDescendents=True, type='joint') or []
        if not joints and mc.nodeType(target_model) == 'joint':
            joints = [target_model]
        if not joints:
            joints = mc.ls(type='joint') or []

        if not joints:
            QMessageBox.warning(
                self,
                "ボーン未検出",
                "選択されたモデルにボーン（スケルトンジョイント）が存在しません。\n\n"
                "「Maya → MMD (インポート)」タブにて、『ボーン（スケルトン）を作成』にチェックを入れて再度モデルをインポートしてください。"
            )
            return

        log_dialog = ExecutionLogDialog(self.parent_window or self, title="HumanIK キャラクター定義実行ログ")
        success = log_dialog.run_task(self._define_hik_task)
        self.last_log_text = log_dialog.te_log.toPlainText()
        self._build_mapping_widgets()

    def _define_hik_task(self):
        """キャラクター定義のバックエンド処理を実行します"""
        print("==================================================")
        print("HumanIK キャラクター定義処理を開始します...")
        print("==================================================")

        # HumanIKプラグインのロードとMEL環境の初期化
        try:
            if not mc.pluginInfo('mayaHIK', query=True, loaded=True):
                print("[HumanIK] mayaHIK プラグインをロード中...")
                mc.loadPlugin('mayaHIK', quiet=True)
        except Exception as e:
            print(f"[警告] プラグインロードエラー: {e}")

        try:
            mel.eval('source "hikGlobalUtils.mel";')
            mel.eval('source "hikCharacterControlsUI.mel";')
        except Exception as e:
            print(f"[警告] MELスクリプト初期化エラー: {e}")

        # 対象モデルの取得
        target_model = self.cbb_models.currentData()
        if not target_model:
            target_text = self.cbb_models.currentText().strip()
            if target_text and not target_text.startswith("（"):
                target_model = target_text.split(" ")[0].strip()

        if not target_model or not mc.objExists(target_model):
            raise RuntimeError("有効なMMDモデルを選択してください。")

        print(f"対象モデル: {target_model}")

        # 対象モデル配下のジョイントを網羅的に収集
        candidate_joints = []
        if mc.nodeType(target_model) == 'joint':
            candidate_joints.append(target_model)

        desc_joints = mc.listRelatives(target_model, allDescendents=True, type='joint', fullPath=True) or []
        candidate_joints.extend(desc_joints)

        # モデル階層下にジョイントが見つからない場合のシーン全ジョイント探索（long=True）
        if not candidate_joints:
            print("[探索] モデル階層下にジョイントが見つからないため、シーン内全ジョイントを探索中...")
            candidate_joints = mc.ls(type='joint', long=True) or []

        if not candidate_joints:
            raise RuntimeError(
                "対象モデルにボーン（スケルトンジョイント）が存在しません。\n\n"
                "モデルインポート画面にて、『ボーン（スケルトン）を作成』にチェックを入れて再インポートしてください。"
            )

        print(f"検出ジョイント総数: {len(candidate_joints)} 個")

        # 和名・短縮名マップの構築（表記揺れ正規化対応）
        norm_orig_to_joints = {}
        for j in candidate_joints:
            if mc.attributeQuery('originalName', node=j, exists=True):
                orig = mc.getAttr(f"{j}.originalName")
                if orig:
                    norm_key = normalize_bone_name(orig)
                    norm_orig_to_joints.setdefault(norm_key, []).append(j)

            # ノード名短縮名も正規化マップにフォールバック追加
            short_j = j.split('|')[-1]
            norm_short = normalize_bone_name(short_j)
            norm_orig_to_joints.setdefault(norm_short, []).append(j)

        # HumanIKキャラクター定義ノードを作成
        current_hik_nodes = set(mc.ls(type='HIKCharacterNode') or [])
        print("[HumanIK] hikCreateDefinition を実行中...")
        mel.eval('hikCreateDefinition;')

        new_nodes = set(mc.ls(type='HIKCharacterNode') or []) - current_hik_nodes
        raw_hik_node = new_nodes.pop() if new_nodes else 'Character1'

        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', target_model)
        unique_hik_name = f"HIK_{clean_name}"
        try:
            hik_node = mc.rename(raw_hik_node, unique_hik_name)
        except Exception:
            hik_node = raw_hik_node

        print(f"[HumanIK] 定義ノード作成完了: {hik_node}")

        # カレントキャラクターとして同期設定
        try:
            mel.eval(f'hikSetCurrentCharacter "{hik_node}";')
            mel.eval('hikUpdateCharacterList();')
        except Exception as e:
            print(f"[警告] カレントキャラクター同期警告: {e}")

        # ボーンのマッピング（正規化候補優先 + アンダースコア正規表現フォールバック）
        mapped_dict = {}
        matched_count = 0
        total_count = len(dic_hik)

        print("--------------------------------------------------")
        print("ボーンマッピングを開始します...")

        for bone_id, bone_info in sorted(dic_hik.items()):
            label_text, regex_name = bone_info[0], bone_info[1]
            matched_joint = None

            # 照合1: 日本語名正規化候補リストによる一律一致
            candidates = get_bone_matching_candidates(label_text)
            for cand in candidates:
                if cand in norm_orig_to_joints:
                    matched_joint = norm_orig_to_joints[cand][0]
                    break

            # 照合2: プレフィックス対応の正規表現照合 (アンダースコア有無吸収)
            if not matched_joint:
                pattern = re.compile(rf'(?:^|_){regex_name}$', re.IGNORECASE)
                for j_path in candidate_joints:
                    short = j_path.split('|')[-1]
                    short_no_us = short.replace('_', '')
                    if pattern.search(short) or pattern.search(short_no_us):
                        matched_joint = j_path
                        break

            # 照合3: 指関節の連続性フォールバック（親ジョイントの唯一の子）
            if not matched_joint and bone_id >= 51 and bone_id not in range(54, 94, 4):
                prev_joint = mapped_dict.get(bone_id - 1)
                if prev_joint and mc.objExists(prev_joint):
                    children = mc.listRelatives(prev_joint, type='joint', fullPath=True) or []
                    if len(children) == 1:
                        matched_joint = children[0]

            if matched_joint:
                mapped_dict[bone_id] = matched_joint
                matched_count += 1
                try:
                    mel.eval(f'hikSetCharacterObject "{matched_joint}" "{hik_node}" {bone_id} 0;')
                    short_j_name = matched_joint.split('|')[-1]
                    print(f"  [OK] ID {bone_id:02d} ({label_text}): {short_j_name}")
                except Exception as e:
                    print(f"  [エラー] ID {bone_id:02d} ({label_text}) マッピング失敗: {e}")
            else:
                print(f"  [未検出] ID {bone_id:02d} ({label_text})")

        self.current_hik_node = hik_node
        self.current_mapped_dict = mapped_dict

        print("--------------------------------------------------")
        print(f"マッピング完了: {matched_count} / {total_count} 個")

        # 既存MMD足IKハンドルおよびコンストレイントの競合解除
        self._cleanup_conflicting_mmd_ik(target_model)

        # Tポーズ（腕水平化＆脚部スタンス安定化）の適用
        print("[HumanIK] Tポーズ（腕水平化・脚部スタンス）を展開中...")
        t_pose_ok = kangkhaen(mapped_dict)
        if t_pose_ok:
            print("[HumanIK] Tポーズ展開成功。")
        else:
            print("[警告] Tポーズ展開がスキップされました。")

        # 必須ボーン充足判定
        required_ids = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
        missing_required = [rid for rid in required_ids if rid not in mapped_dict]

        if missing_required:
            missing_names = [dic_hik[rid][0] for rid in missing_required]
            print(f"[警告] 必須ボーンが不足しています: {missing_names}")
        else:
            print("[HumanIK] 必須ボーンがすべて充足されました！コントロールリグを作成可能です。")

        print("==================================================")
        print("HumanIK キャラクター定義処理が完了しました！")
        print("==================================================")
        return True

    def _build_mapping_widgets(self):
        """スクロールエリア内にボーンマッピング行ウィジェットを再構築します"""
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        mapped_dict = getattr(self, 'current_mapped_dict', {})
        total_count = len(dic_hik)
        matched_count = len(mapped_dict)

        for bone_id, bone_info in sorted(dic_hik.items()):
            label_text = bone_info[0]
            h_row = QHBoxLayout()

            lb_name = QLabel(f"{label_text} (ID:{bone_id})")
            lb_name.setFixedWidth(140)
            h_row.addWidget(lb_name)

            matched_joint = mapped_dict.get(bone_id)
            if matched_joint and mc.objExists(matched_joint):
                btn_sel = QPushButton("選択")
                btn_sel.setFixedSize(50, 26)
                short_display = matched_joint.split('|')[-1]
                le_joint = QLineEdit(short_display)
                le_joint.setToolTip(matched_joint)
                le_joint.setReadOnly(True)
                btn_sel.clicked.connect(lambda _, j=matched_joint: mc.select(j) if mc.objExists(j) else None)
                h_row.addWidget(btn_sel)
                h_row.addWidget(le_joint)
            else:
                lb_none = QLabel("未検出")
                lb_none.setStyleSheet("color: #ff7675; font-weight: bold;")
                h_row.addWidget(lb_none)

            h_row.addStretch()
            self.scroll_layout.addLayout(h_row)

        required_ids = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
        missing_required = [rid for rid in required_ids if rid not in mapped_dict]

        self.btn_reapply_tpose.setEnabled(matched_count > 0)
        self.btn_create_rig.setEnabled(len(missing_required) == 0 and matched_count > 0)

        if missing_required:
            missing_names = [dic_hik[rid][0] for rid in missing_required]
            status_text = f"検出: {matched_count}/{total_count} 件 | 不足必須ボーン: {', '.join(missing_names)}"
            self.lbl_status.setText(f"<span style=\'color:#ff7675;\'>{status_text}</span>")
            mc.warning(f"HumanIK: 必須ボーンが不足しています: {missing_names}")
        else:
            status_text = f"検出: {matched_count}/{total_count} 件 | 必須ボーン充足完了 (コントロールリグ作成可能)"
            self.lbl_status.setText(f"<span style=\'color:#55efc4;\'>{status_text}</span>")
            mc.inViewMessage(amg='<span style="color:#52b7ff;">HumanIK:</span> キャラクター定義が正常に完了しました。', pos='topCenter', fade=True)

    def _reapply_tpose(self):
        """現在のマッピングに基づき腕のTポーズ（水平化）を安全に再適用します"""
        if not self.current_mapped_dict:
            QMessageBox.warning(self, "エラー", "先にキャラクター定義を作成してください。")
            return

        # コントロールリグ作成後の破綻防止安全ガード
        has_rig = False
        if hasattr(self, 'current_hik_node') and self.current_hik_node and mc.objExists(self.current_hik_node):
            rig_nodes = mc.ls(f"*{self.current_hik_node}*Ctrl*", type="transform") or []
            if not rig_nodes:
                rig_nodes = mc.ls(type="HIKControlRigNode") or []
            has_rig = len(rig_nodes) > 0

        if has_rig:
            res = QMessageBox.warning(
                self,
                "コントロールリグ作成済み警告",
                "コントロールリグ（IK/FKリグ）が作成された状態でスケルトンを直接Tポーズ化すると、\n"
                "IKエフェクタとの整合性が崩れ手足が激しく破綻します。\n\n"
                "リグを初期姿勢に戻すにはリグのポーズ初期化を実行するか、\n"
                "クリーンアップタブからリグを削除した上で再実行してください。\n\n"
                "強制的に実行しますか？（※非推奨）",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if res != QMessageBox.Yes:
                return

        success = kangkhaen(self.current_mapped_dict)
        if success:
            mc.inViewMessage(amg='<span style="color:#52b7ff;">HumanIK:</span> Tポーズを再適用しました。', pos='topCenter', fade=True)
        else:
            QMessageBox.warning(self, "警告", "Tポーズの適用に必要なジョイントが不足しています。")

    def _on_click_create_rig(self):
        """コントロールリグ作成タスクを ExecutionLogDialog 経由で実行します"""
        log_dialog = ExecutionLogDialog(self.parent_window or self, title="HumanIK コントロールリグ作成実行ログ")
        success = log_dialog.run_task(self._create_control_rig_task)
        self.last_log_text = log_dialog.te_log.toPlainText()
        if success:
            # リグ作成後は誤操作による破綻防止のためTポーズボタンを無効化
            self.btn_reapply_tpose.setEnabled(False)
            self.btn_reapply_tpose.setToolTip("コントロールリグ作成後はスケルトンの直接Tポーズ変更は行えません（リグ破綻防止）。")
            self.btn_create_rig.setEnabled(False)

    def _cleanup_conflicting_mmd_ik(self, target_model=None):
        """
        HumanIK コントロールリグと二重衝突する既存の MMD 足IKハンドル (ikHandle) および
        コンストレイントを安全に整理・削除し、足の跳ね上がり・逆関節破綻を防止します。
        """
        deleted_handles = []
        patterns = ['ikHandle_leg_*', 'ikHandle_toe_*', '*ikHandle_leg*', '*ikHandle_toe*']
        for pat in patterns:
            handles = mc.ls(pat, type='ikHandle') or []
            for h in handles:
                if mc.objExists(h) and h not in deleted_handles:
                    try:
                        mc.delete(h)
                        deleted_handles.append(h)
                    except Exception:
                        pass

        # 足首・つま先ジョイントを直接ロックしている orientConstraint / pointConstraint の検出と解除
        constraints = mc.ls(type=['orientConstraint', 'pointConstraint']) or []
        for c in constraints:
            if not mc.objExists(c):
                continue
            try:
                targets = mc.listConnections(f"{c}.target", destination=False, source=True) or []
                if any('ＩＫ' in t or 'IK' in t for t in targets):
                    mc.delete(c)
            except Exception:
                pass

        if deleted_handles:
            print(f"[HumanIK] コントロールリグ競合防止のため既存のMMD足IKハンドルを整理しました: {deleted_handles}")
        return deleted_handles

    def _create_control_rig_task(self):
        """コントロールリグのバックエンド処理を実行します"""
        print("==================================================")
        print("HumanIK コントロールリグ作成を開始します...")
        print("==================================================")

        # リグ作成直前にも既存IKハンドルの競合を漏れなく排除
        self._cleanup_conflicting_mmd_ik()

        if hasattr(self, 'current_hik_node') and self.current_hik_node and mc.objExists(self.current_hik_node):
            print(f"カレントキャラクター設定: {self.current_hik_node}")
            mel.eval(f'hikSetCurrentCharacter "{self.current_hik_node}";')
            mel.eval('hikUpdateCharacterList();')

        print("[HumanIK] hikCreateControlRig を実行中...")
        mel.eval('hikCreateControlRig;')
        print("[HumanIK] コントロールリグの作成が完了しました！")
        print("==================================================")
        mc.inViewMessage(amg='<span style="color:#52b7ff;">HumanIK:</span> コントロールリグを作成しました。', pos='topCenter', fade=True)
        return True

# ==============================================================================
# HumanIK 管理独立ウィンドウ
# ==============================================================================
class HikWindow(QWidget):
    """MMD HumanIK管理独立ウィンドウ"""
    def __init__(self, parent=None):
        super(HikWindow, self).__init__(parent)
        self.setWindowTitle("HumanIK 管理 - MMD Tools for Maya")
        self.setObjectName("MmdHikWindow")
        self.resize(760, 680)
        self.setMinimumSize(640, 520)
        self.setWindowFlags(Qt.Window)
        self.setStyleSheet(MODERN_STYLE)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        self.hik_widget = HikTabWidget(self)
        main_layout.addWidget(self.hik_widget)

    def showEvent(self, e):
        super().showEvent(e)
        if hasattr(self, "hik_widget"):
            self.hik_widget._refresh_models()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()

_hik_window_instance = None

def show_hik_window(parent=None):
    """HumanIK管理ウィンドウを表示"""
    global _hik_window_instance
    if _hik_window_instance is not None:
        try:
            _hik_window_instance.close()
            _hik_window_instance.deleteLater()
        except Exception:
            pass
    _hik_window_instance = HikWindow(parent=parent)
    _hik_window_instance.show()
    _hik_window_instance.raise_()
    _hik_window_instance.activateWindow()
    return _hik_window_instance

# ==============================================================================
# モーションインポートタブ (VMD → Maya)
# ==============================================================================
class VmdImportTabWidget(QWidget):
    """MMDモーション (VMD) をMayaシーンにインポートするためのUIタブ"""
    def __init__(self, parent=None):
        super(VmdImportTabWidget, self).__init__(parent)
        self.parent_window = parent
        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # VMDファイル選択
        file_box = QGroupBox("VMD モーションファイル指定")
        file_layout = QVBoxLayout(file_box)

        # キャラクタモーション (ボーン・表情)
        lbl_model = QLabel("キャラクタモーション (.vmd):")
        file_layout.addWidget(lbl_model)
        h_model_file = QHBoxLayout()
        self.le_file_path = QLineEdit()
        self.le_file_path.setPlaceholderText("ダンス・表情モーションファイル (.vmd)")
        self.le_file_path.textChanged.connect(self._on_file_changed)
        h_model_file.addWidget(self.le_file_path)

        self.btn_browse = QPushButton("参照...")
        self.btn_browse.setFixedWidth(75)
        self.btn_browse.clicked.connect(self._browse_file)
        h_model_file.addWidget(self.btn_browse)

        self.btn_clear_model = QPushButton("クリア")
        self.btn_clear_model.setFixedWidth(65)
        self.btn_clear_model.clicked.connect(self._clear_model_file)
        h_model_file.addWidget(self.btn_clear_model)
        file_layout.addLayout(h_model_file)

        # カメラモーション
        lbl_cam = QLabel("カメラモーション (.vmd) ※省略可能,ベータ版:")
        lbl_cam.setStyleSheet("margin-top: 6px;")
        file_layout.addWidget(lbl_cam)
        h_cam_file = QHBoxLayout()
        self.le_camera_path = QLineEdit()
        self.le_camera_path.setPlaceholderText("カメラワーク専用ファイル (.vmd)")
        self.le_camera_path.textChanged.connect(self._on_file_changed)
        h_cam_file.addWidget(self.le_camera_path)

        self.btn_browse_camera = QPushButton("参照...")
        self.btn_browse_camera.setFixedWidth(75)
        self.btn_browse_camera.clicked.connect(self._browse_camera_file)
        h_cam_file.addWidget(self.btn_browse_camera)

        self.btn_clear_camera = QPushButton("クリア")
        self.btn_clear_camera.setFixedWidth(65)
        self.btn_clear_camera.clicked.connect(self._clear_camera_file)
        h_cam_file.addWidget(self.btn_clear_camera)
        file_layout.addLayout(h_cam_file)

        # BGM / 音声ファイル (.wav)
        lbl_audio = QLabel("BGM / 音声ファイル (.wav) ※省略可能:")
        lbl_audio.setStyleSheet("margin-top: 6px;")
        file_layout.addWidget(lbl_audio)
        h_audio_file = QHBoxLayout()
        self.le_audio_path = QLineEdit()
        self.le_audio_path.setPlaceholderText("BGM音源ファイル (.wav)")
        self.le_audio_path.textChanged.connect(self._on_file_changed)
        h_audio_file.addWidget(self.le_audio_path)

        self.btn_browse_audio = QPushButton("参照...")
        self.btn_browse_audio.setFixedWidth(75)
        self.btn_browse_audio.clicked.connect(self._browse_audio_file)
        h_audio_file.addWidget(self.btn_browse_audio)

        self.btn_clear_audio = QPushButton("クリア")
        self.btn_clear_audio.setFixedWidth(65)
        self.btn_clear_audio.clicked.connect(self._clear_audio_file)
        h_audio_file.addWidget(self.btn_clear_audio)
        file_layout.addLayout(h_audio_file)

        layout.addWidget(file_box)

        # 設定

        opt_box = QGroupBox("モーション設定")
        opt_layout = QVBoxLayout(opt_box)

        # 適用先モデル選択
        h_model = QHBoxLayout()
        h_model.addWidget(QLabel("適用先モデル:"))
        self.cbb_target_model = QComboBox()
        self.btn_refresh_models = QPushButton("更新")
        self.btn_refresh_models.setFixedWidth(80)
        self.btn_refresh_models.clicked.connect(self._refresh_models)
        h_model.addWidget(self.cbb_target_model)
        h_model.addWidget(self.btn_refresh_models)
        opt_layout.addLayout(h_model)

        h_scale = QHBoxLayout()
        h_scale.addWidget(QLabel("スケール倍率:"))
        self.le_scale = QLineEdit("8.0")
        self.le_scale.setFixedWidth(80)
        h_scale.addWidget(self.le_scale)
        h_scale.addWidget(QLabel("(モデルインポート時と同じ倍率を指定)"))
        h_scale.addStretch()
        opt_layout.addLayout(h_scale)

        info_lbl = QLabel(
            "・キャラクタモーションとカメラモーションを別々に、または同時にインポートできます。\n"
            "・カメラモーション読み込み時、MMDと同等の注視点オービットカメラを自動構築します。\n"
            "・足IKシステムがモデル内に未作成の場合でも、インポート時に自動構築されて滑らかに連動します。"
        )
        info_lbl.setStyleSheet("color: #999; font-size: 12px; margin-top: 4px; line-height: 1.4;")
        opt_layout.addWidget(info_lbl)

        layout.addWidget(opt_box)
        layout.addStretch()

        self._refresh_models()

        # 実行アクション
        h_action = QHBoxLayout()
        h_action.setSpacing(12)

        self.cb_close_on_finish = QCheckBox("完了後にウィンドウを閉じる")
        h_action.addWidget(self.cb_close_on_finish)
        h_action.addStretch()

        # モーションインポート実行ボタン
        self.btn_execute = QPushButton("モーションをインポート")
        self.btn_execute.setProperty("class", "primary")
        self.btn_execute.setFixedHeight(46)
        self.btn_execute.setMinimumWidth(200)
        self.btn_execute.setEnabled(False)
        self.btn_execute.clicked.connect(self._execute_import)
        h_action.addWidget(self.btn_execute)

        layout.addLayout(h_action)

        # 初期化中フラグ
        self._is_initializing = True

        # 前回パスの復元 (空白が保存されている場合は空白を維持)
        if mc.optionVar(exists="MMDToolsForMaya_LastModelVmdPath"):
            last_model_vmd = mc.optionVar(q="MMDToolsForMaya_LastModelVmdPath")
            if last_model_vmd and os.path.exists(last_model_vmd):
                self.le_file_path.setText(last_model_vmd)

        if mc.optionVar(exists="MMDToolsForMaya_LastCameraVmdPath"):
            last_cam_vmd = mc.optionVar(q="MMDToolsForMaya_LastCameraVmdPath")
            if last_cam_vmd and os.path.exists(last_cam_vmd):
                self.le_camera_path.setText(last_cam_vmd)

        if mc.optionVar(exists="MMDToolsForMaya_LastAudioPath"):
            last_audio = mc.optionVar(q="MMDToolsForMaya_LastAudioPath")
            if last_audio and os.path.exists(last_audio):
                self.le_audio_path.setText(last_audio)

        self._is_initializing = False
        self._on_file_changed()

    def _open_morph_window(self):
        """MMD本家風の表情操作ウィンドウを開く"""
        try:
            from .morph_window import show_morph_window
        except Exception:
            try:
                from morph_window import show_morph_window
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"表情操作モジュールの読み込みに失敗しました:\n{e}")
                return

        show_morph_window(parent=get_maya_main_window())

    def _refresh_models(self):
        self.cbb_target_model.clear()
        self.cbb_target_model.addItem("シーン内の全MMDモデル / 自動検出", None)
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for node_name, label in models:
                self.cbb_target_model.addItem(label, node_name)
        except Exception:
            pass

    def _on_file_changed(self, text=""):
        path1 = self.le_file_path.text().strip()
        path2 = self.le_camera_path.text().strip()
        path3 = self.le_audio_path.text().strip()
        valid1 = path1.lower().endswith('.vmd') and os.path.exists(path1)
        valid2 = path2.lower().endswith('.vmd') and os.path.exists(path2)
        valid3 = path3.lower().endswith('.wav') and os.path.exists(path3)
        self.btn_execute.setEnabled(valid1 or valid2 or valid3)

        if getattr(self, "_is_initializing", False):
            return

        if valid1:
            mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", path1))
        if valid2:
            mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", path2))
        if valid3:
            mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", path3))

    def _clear_model_file(self):
        """モデルモーション入力欄をクリア"""
        self.le_file_path.clear()
        mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", ""))

    def _clear_camera_file(self):
        """カメラモーション入力欄をクリア"""
        self.le_camera_path.clear()
        mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", ""))

    def _clear_audio_file(self):
        """BGM音声ファイル入力欄をクリア"""
        self.le_audio_path.clear()
        mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", ""))

    def _browse_file(self):

        start_dir = self.le_file_path.text().strip()
        if not start_dir or not os.path.exists(start_dir):
            if mc.optionVar(exists="MMDToolsForMaya_LastModelVmdPath"):
                cand = mc.optionVar(q="MMDToolsForMaya_LastModelVmdPath")
                if cand and os.path.exists(cand):
                    start_dir = cand
        if start_dir and os.path.isfile(start_dir):
            start_dir = os.path.dirname(start_dir)

        path, _ = QFileDialog.getOpenFileName(
            self,
            "キャラクタモーションファイルを選択",
            start_dir,
            "VMD Motion (*.vmd);;All Files (*.*)"
        )
        if path:
            self.le_file_path.setText(path)
            mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", path))

    def _browse_camera_file(self):
        start_dir = self.le_camera_path.text().strip()
        if not start_dir or not os.path.exists(start_dir):
            if mc.optionVar(exists="MMDToolsForMaya_LastCameraVmdPath"):
                cand = mc.optionVar(q="MMDToolsForMaya_LastCameraVmdPath")
                if cand and os.path.exists(cand):
                    start_dir = cand
        if start_dir and os.path.isfile(start_dir):
            start_dir = os.path.dirname(start_dir)

        path, _ = QFileDialog.getOpenFileName(
            self,
            "カメラモーションファイルを選択",
            start_dir,
            "VMD Camera (*.vmd);;All Files (*.*)"
        )
        if path:
            self.le_camera_path.setText(path)
            mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", path))

    def _browse_audio_file(self):
        start_dir = self.le_audio_path.text().strip()
        if not start_dir or not os.path.exists(start_dir):
            if mc.optionVar(exists="MMDToolsForMaya_LastAudioPath"):
                cand = mc.optionVar(q="MMDToolsForMaya_LastAudioPath")
                if cand and os.path.exists(cand):
                    start_dir = cand
            else:
                wav_dir = os.path.join(os.path.dirname(__file__), "wav")
                if os.path.exists(wav_dir):
                    start_dir = wav_dir
        if start_dir and os.path.isfile(start_dir):
            start_dir = os.path.dirname(start_dir)

        path, _ = QFileDialog.getOpenFileName(
            self,
            "BGM / 音声ファイルを選択",
            start_dir,
            "WAV Audio (*.wav);;All Files (*.*)"
        )
        if path:
            self.le_audio_path.setText(path)
            mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", path))

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        local_files = [u.toLocalFile() for u in urls]
        vmd_files = [f for f in local_files if f.lower().endswith('.vmd')]
        wav_files = [f for f in local_files if f.lower().endswith('.wav')]

        if wav_files:
            self.le_audio_path.setText(wav_files[0])
            mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", wav_files[0]))

        if len(vmd_files) >= 2:
            # 複数ファイルドロップ時のカメラ/モデル自動振り分け
            for f in vmd_files:
                base_low = os.path.basename(f).lower()
                if any(k in base_low for k in ["cam", "camera", "カメラ"]):
                    self.le_camera_path.setText(f)
                    mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", f))
                else:
                    self.le_file_path.setText(f)
                    mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", f))
        elif len(vmd_files) == 1:
            single = vmd_files[0]
            base_low = os.path.basename(single).lower()
            if any(k in base_low for k in ["cam", "camera", "カメラ"]):
                self.le_camera_path.setText(single)
                mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", single))
            else:
                self.le_file_path.setText(single)
                mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", single))

    def _execute_import(self):
        file_path = self.le_file_path.text().strip() or None
        camera_path = self.le_camera_path.text().strip() or None
        audio_path = self.le_audio_path.text().strip() or None

        if not file_path and not camera_path and not audio_path:
            QMessageBox.warning(self, "エラー", "モーションまたは音声ファイルが指定されていません。")
            return

        # キャラクタモーション指定時、シーン内にボーンが存在するか検証
        if file_path:
            joints = mc.ls(type="joint") or []
            if not joints:
                QMessageBox.warning(
                    self,
                    "スケルトン未検出エラー",
                    "シーン内にモデルのスケルトン（ボーン）が存在しません。\n\n"
                    "キャラクタモーションを適用するには、先に「MMD → Maya (インポート)」タブで\n"
                    "「スケルトン（ジョイント）を作成する」にチェックを入れてモデルをインポートしてください。"
                )
                return

        try:
            scale = float(self.le_scale.text())
        except ValueError:
            scale = 8.0

        target_model = self.cbb_target_model.currentData()

        # VMDアナライザーによる概要診断の出力
        try:
            try:
                from ..converters import vmd_analyzer
            except Exception:
                from converters import vmd_analyzer
            if file_path and os.path.exists(file_path):
                report = vmd_analyzer.analyze_vmd(file_path)
                print(report.generate_summary_text())
        except Exception:
            pass

        log_dialog = ExecutionLogDialog(self.parent_window or self, title="VMDモーションインポート実行ログ")
        import_func = vmdpaimaya.import_vmd
        # 音量調整はMaya標準機能へ委任（標準値100%を適用）
        audio_volume = 100

        if audio_path and os.path.exists(audio_path):
            mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", audio_path))
        if file_path and os.path.exists(file_path):
            mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", file_path))
        if camera_path and os.path.exists(camera_path):
            mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", camera_path))

        prevent_darkening = True
        if self.parent_window and hasattr(self.parent_window, "tab_import"):
            if hasattr(self.parent_window.tab_import, "cb_prevent_motion_darkening"):
                prevent_darkening = self.parent_window.tab_import.cb_prevent_motion_darkening.isChecked()

        success = log_dialog.run_task(
            import_func,
            file_path,
            camera_path,
            audio_path,
            scale,
            target_model,
            audio_volume,
            progress_callback=log_dialog.update_progress,
            prevent_motion_darkening=prevent_darkening
        )

        # インポート完了後のビューポートライティングを確実に復元
        restore_viewport_lighting(prevent_motion_darkening=prevent_darkening)

        if success:
            mc.inViewMessage(amg='<span style="color:#52b7ff;">MMD Tools for Maya:</span> モーション・音声インポートが完了しました。', pos='topCenter', fade=True)
            if self.cb_close_on_finish.isChecked() and self.parent_window:
                self.parent_window.close()

# ==============================================================================
# 物理演算 (XPBD) タブ
# ==============================================================================
class PhysicsTabWidget(QWidget):
    """自前C++ XPBD物理エンジンによるシミュレーションおよびベイクUI"""
    def __init__(self, parent=None):
        super(PhysicsTabWidget, self).__init__(parent)
        self.parent_window = parent
        self.setAcceptDrops(True)
        self.bridge = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # モデルファイル指定
        file_box = QGroupBox("PMX モデルファイル (物理定義)")
        file_layout = QHBoxLayout(file_box)

        self.le_pmx_path = QLineEdit()
        self.le_pmx_path.setPlaceholderText("物理設定を含む .pmx ファイルを指定")
        # 直前のPMXモデルパスがあれば初期値設定
        last_pmx = mc.optionVar(q="MMDToolsForMaya_LastPmxPath") if mc.optionVar(exists="MMDToolsForMaya_LastPmxPath") else ""
        if last_pmx and os.path.exists(last_pmx):
            self.le_pmx_path.setText(last_pmx)
        self.le_pmx_path.textChanged.connect(self._on_pmx_changed)
        file_layout.addWidget(self.le_pmx_path)

        self.btn_browse = QPushButton("参照...")
        self.btn_browse.setFixedWidth(75)
        self.btn_browse.clicked.connect(self._browse_pmx)
        file_layout.addWidget(self.btn_browse)

        self.btn_clear_pmx = QPushButton("クリア")
        self.btn_clear_pmx.setFixedWidth(65)
        self.btn_clear_pmx.clicked.connect(self._clear_pmx_file)
        file_layout.addWidget(self.btn_clear_pmx)

        layout.addWidget(file_box)

        # 適用対象モデル指定
        model_box = QGroupBox("適用対象モデル")
        model_layout = QHBoxLayout(model_box)
        self.cbb_target_model = QComboBox()
        self.cbb_target_model.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        model_layout.addWidget(self.cbb_target_model)

        self.btn_refresh_models = QPushButton("更新")
        self.btn_refresh_models.setFixedWidth(60)
        self.btn_refresh_models.clicked.connect(self._refresh_target_models)
        model_layout.addWidget(self.btn_refresh_models)
        layout.addWidget(model_box)

        # 物理シミュレーション設定
        param_box = QGroupBox("物理演算パラメータ (XPBD / Bullet 共通)")
        param_layout = QVBoxLayout(param_box)

        # Bullet エンジンバージョン選択 (本家MMD採用 2.75 vs 改良 2.83.7)
        h_bullet_ver = QHBoxLayout()
        h_bullet_ver.addWidget(QLabel("Bullet エンジン:"))
        self.rb_bullet_275 = QRadioButton("Bullet 2.75 (本家MMD採用・挙動再現重視)")
        self.rb_bullet_283 = QRadioButton("Bullet 2.83.7 (後発・改良バージョン・安定性重視)")

        saved_ver = "2.75"
        if mc.optionVar(exists="MMDToolsForMaya_BulletVersion"):
            saved_ver = str(mc.optionVar(q="MMDToolsForMaya_BulletVersion"))
        if "2.83" in saved_ver:
            self.rb_bullet_283.setChecked(True)
        else:
            self.rb_bullet_275.setChecked(True)

        self.rb_bullet_275.toggled.connect(self._on_bullet_version_toggled)
        self.rb_bullet_283.toggled.connect(self._on_bullet_version_toggled)

        self.bg_bullet_ver = QButtonGroup(self)
        self.bg_bullet_ver.addButton(self.rb_bullet_275)
        self.bg_bullet_ver.addButton(self.rb_bullet_283)

        h_bullet_ver.addWidget(self.rb_bullet_275)
        h_bullet_ver.addWidget(self.rb_bullet_283)
        h_bullet_ver.addStretch()
        param_layout.addLayout(h_bullet_ver)

        # 動作モード選択 (ダンスモーションモード vs 簡易モード)
        h_mode = QHBoxLayout()
        h_mode.addWidget(QLabel("物理演算モード:"))
        self.rb_mode_dance = QRadioButton("ダンスモーションモード (高精度・しなやか)")
        self.rb_mode_simple = QRadioButton("簡易モード (ベイク速さ重視)")
        self.rb_mode_dance.setChecked(True)
        self.rb_mode_dance.toggled.connect(self._on_physics_mode_toggled)

        self.bg_physics_mode = QButtonGroup(self)
        self.bg_physics_mode.addButton(self.rb_mode_dance)
        self.bg_physics_mode.addButton(self.rb_mode_simple)

        h_mode.addWidget(self.rb_mode_dance)
        h_mode.addWidget(self.rb_mode_simple)
        h_mode.addStretch()
        param_layout.addLayout(h_mode)

        # 重力設定 (MMD本家仕様: 加速度 9.80)
        h_grav = QHBoxLayout()
        h_grav.addWidget(QLabel("重力加速度 (Y):"))
        self.le_gravity = QLineEdit("-9.80")
        self.le_gravity.setFixedWidth(75)
        self.le_gravity.setToolTip(
            "MMD重力加速度 (下向き: -9.80)\n"
            "・MMD標準地球重力 (1.0G): -9.80 (通常・ダンス推奨)\n"
            "・ふんわり軽め (0.5G): -4.90 (スカートがふわっと浮き上がる)\n"
            "・重め (1.5G): -14.70 (素早く下へ落ち着かせる)\n"
            "・無重力 (0.0G): 0.0"
        )
        h_grav.addWidget(self.le_gravity)
        lbl_grav_hint = QLabel("(MMD標準 1.0G: -9.80 ／ ふんわり: -4.90 ／ 重め: -14.70)")
        lbl_grav_hint.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        h_grav.addWidget(lbl_grav_hint)
        h_grav.addStretch()
        param_layout.addLayout(h_grav)

        # サブステップ数
        h_sub = QHBoxLayout()
        h_sub.addWidget(QLabel("サブステップ数:"))
        self.le_substeps = QLineEdit("30")
        self.le_substeps.setFixedWidth(75)
        self.le_substeps.setToolTip(
            "1フレームあたりの物理計算分割数。\n"
            "・ダンスモーションモード: 30 (激しいステップやターンでも剛体・Jointが破綻せずしなやか)\n"
            "・簡易モード: 10～15 (ベイク速さ重視)\n"
            "※数値を高くするほど剛体の貫通や伸びが抑制され安定しますが、計算時間が増加します。"
        )
        h_sub.addWidget(self.le_substeps)
        lbl_sub_hint = QLabel("(ダンス推奨: 30 ／ 簡易速さ重視: 10～15)")
        lbl_sub_hint.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        h_sub.addWidget(lbl_sub_hint)
        h_sub.addStretch()
        param_layout.addLayout(h_sub)

        # スケール倍率
        h_scale = QHBoxLayout()
        h_scale.addWidget(QLabel("スケール倍率:"))
        self.le_scale = QLineEdit("8.0")
        self.le_scale.setFixedWidth(80)
        h_scale.addWidget(self.le_scale)
        h_scale.addWidget(QLabel("(インポート時と同一の倍率)"))
        h_scale.addStretch()
        param_layout.addLayout(h_scale)

        # フレーム範囲 (ラジオボタン選択 & 一段下げレイアウト)
        h_frame_mode = QHBoxLayout()
        h_frame_mode.addWidget(QLabel("シミュレーション範囲:"))
        self.rb_auto_frame = QRadioButton("タイムライン全体")
        self.rb_auto_frame.setChecked(True)
        self.rb_custom_frame = QRadioButton("フレーム指定")
        self.rb_auto_frame.toggled.connect(self._on_frame_mode_toggled)

        self.bg_frame_mode = QButtonGroup(self)
        self.bg_frame_mode.addButton(self.rb_auto_frame)
        self.bg_frame_mode.addButton(self.rb_custom_frame)

        h_frame_mode.addWidget(self.rb_auto_frame)
        h_frame_mode.addWidget(self.rb_custom_frame)
        h_frame_mode.addStretch()
        param_layout.addLayout(h_frame_mode)

        # 一段下げたフレーム数値入力レイアウト
        h_custom_frame = QHBoxLayout()
        h_custom_frame.setContentsMargins(24, 0, 0, 0)
        h_custom_frame.addWidget(QLabel("開始フレーム:"))
        self.le_start_frame = QLineEdit()
        self.le_start_frame.setFixedWidth(70)
        self.le_start_frame.setEnabled(False)
        h_custom_frame.addWidget(self.le_start_frame)

        h_custom_frame.addWidget(QLabel("終了フレーム:"))
        self.le_end_frame = QLineEdit()
        self.le_end_frame.setFixedWidth(70)
        self.le_end_frame.setEnabled(False)
        h_custom_frame.addWidget(self.le_end_frame)
        h_custom_frame.addStretch()
        param_layout.addLayout(h_custom_frame)

        # ベイク完了後の補助ノード非表示設定
        self.cb_hide_helpers = QCheckBox("物理ベイク完了後に補助ノード (Apose_view_cnt / Apose_subetenoya / *_master / 剛体・ジョイント可視化メッシュ) を非表示にする")
        hide_default = True
        if mc.optionVar(exists="MMDToolsForMaya_HideHelpersAfterBake"):
            hide_default = bool(mc.optionVar(q="MMDToolsForMaya_HideHelpersAfterBake"))
        self.cb_hide_helpers.setChecked(hide_default)
        self.cb_hide_helpers.toggled.connect(self._on_hide_helpers_toggled)
        param_layout.addWidget(self.cb_hide_helpers)

        # 床判定（Y=0 地面衝突）
        self.cb_enable_floor = QCheckBox("床判定 (地面無限平面 Y=0) を有効化する ※ひもやスカートの床下沈み込みを防止")
        self.cb_enable_floor.setChecked(True)
        param_layout.addWidget(self.cb_enable_floor)
        layout.addWidget(param_box)
        layout.addStretch()

        # 実行ボタンエリア
        v_action = QVBoxLayout()

        # 中段: 従来の物理ベイク実行ボタン (Bullet と XPBD を横並び)
        h_bake_action = QHBoxLayout()

        self.btn_bullet_bake = QPushButton("Bullet 物理ベイク実行 (MMD本家仕様)")
        self.btn_bullet_bake.setFixedHeight(40)
        self.btn_bullet_bake.setStyleSheet("QPushButton { background-color: #2e6b9e; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3b88c7; } QPushButton:disabled { background-color: #444; color: #888; }")
        self.btn_bullet_bake.clicked.connect(self._execute_bullet_bake)
        h_bake_action.addWidget(self.btn_bullet_bake)

        self.btn_bake = QPushButton("XPBD 物理ベイク実行(ベータ版)")
        self.btn_bake.setProperty("class", "primary")
        self.btn_bake.setFixedHeight(40)
        self.btn_bake.clicked.connect(self._execute_bake)
        h_bake_action.addWidget(self.btn_bake)

        v_action.addLayout(h_bake_action)

        # 下段: ユーティリティ操作 (可視化生成、再吸着、キーフレームクリアを横並び)
        h_sub_action = QHBoxLayout()

        self.btn_create_vis = QPushButton("剛体・Joint可視化を生成")
        self.btn_create_vis.setFixedHeight(40)
        self.btn_create_vis.clicked.connect(self._execute_create_visualizers)
        h_sub_action.addWidget(self.btn_create_vis)

        self.btn_reconnect = QPushButton("剛体・Jointをモデルに再吸着")
        self.btn_reconnect.setFixedHeight(40)
        self.btn_reconnect.clicked.connect(self._execute_reconnect)
        h_sub_action.addWidget(self.btn_reconnect)

        self.btn_clear_keys = QPushButton("物理キーフレームをクリア")
        self.btn_clear_keys.setFixedHeight(40)
        self.btn_clear_keys.clicked.connect(self._execute_clear_keys)
        h_sub_action.addWidget(self.btn_clear_keys)

        v_action.addLayout(h_sub_action)
        layout.addLayout(v_action)

        self._refresh_bullet_status()

    def _check_motion_plugin_status(self):
        """mmd_motion.mll プラグインのロード状況を確認しラベルを更新"""
        loaded = False
        try:
            if hasattr(mc, "mmdFastBakeBone"):
                loaded = True
            elif hasattr(mel, "eval") and mel.eval('exists "mmdFastBakeBone"') == 1:
                loaded = True
            elif any("mmd_motion" in p.lower() for p in (mc.pluginInfo(query=True, listPlugins=True) or [])):
                loaded = True
            elif mc.pluginInfo("mmd_motion.mll", query=True, loaded=True) or mc.pluginInfo("mmd_motion", query=True, loaded=True):
                loaded = True
        except Exception:
            pass

        motion_autoload = False
        if loaded:
            try:
                motion_autoload = mc.pluginInfo("mmd_motion.mll", query=True, autoload=True) or mc.pluginInfo("mmd_motion", query=True, autoload=True)
            except Exception:
                motion_autoload = False
            if not motion_autoload:
                try:
                    mc.pluginInfo("mmd_motion.mll", edit=True, autoload=True)
                    motion_autoload = True
                except Exception:
                    try:
                        mc.pluginInfo("mmd_motion", edit=True, autoload=True)
                        motion_autoload = True
                    except Exception:
                        pass

        if loaded:
            auto_str = " (自動ロード: 有効)" if motion_autoload else ""
            self.lbl_motion_plugin_status.setText(f"<span style='color:#55ff77; font-weight:bold;'>● プラグイン読み込み済み (mmd_motion.mll{auto_str})</span>")
        else:
            self.lbl_motion_plugin_status.setText("<span style='color:#ff7777; font-weight:bold;'>○ プラグイン未読み込み (mmd_motion.mll)</span>")

    def _reload_motion_plugin(self):
        """mmd_motion.mll プラグインを強制リロード"""
        try:
            try:
                from ..bullet_engine import bullet_maya_bridge
            except Exception:
                from bullet_engine import bullet_maya_bridge
            bridge = bullet_maya_bridge.BulletMayaBridge.__new__(bullet_maya_bridge.BulletMayaBridge)
            success = bridge._ensure_motion_plugin_loaded()
            if success:
                try:
                    mc.pluginInfo("mmd_motion", edit=True, autoload=True)
                except Exception:
                    pass
                try:
                    mc.pluginInfo("mmd_motion.mll", edit=True, autoload=True)
                except Exception:
                    pass
            self._check_motion_plugin_status()
            if success:
                QMessageBox.information(self, "プラグイン", "MMDモーションプラグイン (mmd_motion.mll) が正常にロードされ、自動ロードが設定されました。")
            else:
                QMessageBox.warning(self, "プラグイン", "MMDモーションプラグイン (mmd_motion.mll) のロードに失敗しました。")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"プラグインのロード中にエラーが発生しました: {e}")

    def _is_bullet_available(self):
        """Bullet物理モジュール (bullet_engine) が存在し利用可能か判定"""
        try:
            plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            bullet_dir = os.path.join(plugin_root, "bullet_engine")
            bin_dir = os.path.join(bullet_dir, "bin")
            dll_275 = os.path.join(bin_dir, "mmd_bullet_275.dll")
            dll_283 = os.path.join(bin_dir, "mmd_bullet_283.dll")
            dll_common = os.path.join(bin_dir, "mmd_bullet.dll")
            has_dll = os.path.exists(dll_275) or os.path.exists(dll_283) or os.path.exists(dll_common)
            bridge_path = os.path.join(bullet_dir, "bullet_maya_bridge.py")
            return has_dll and os.path.exists(bridge_path)
        except Exception:
            return False

    def _refresh_bullet_status(self):
        """Bulletボタンの活性化状態を更新 (フォルダ削除時は自動無効化)"""
        available = self._is_bullet_available()
        self.btn_bullet_bake.setEnabled(available)
        if available:
            ver = "2.83.7 (改良版)" if hasattr(self, 'rb_bullet_283') and self.rb_bullet_283.isChecked() else "2.75 (本家MMD仕様)"
            self.btn_bullet_bake.setToolTip(f"Bullet Physics {ver} により、柔らかくしなやかな髪やスカートの物理をベイクします。")
        else:
            self.btn_bullet_bake.setToolTip("Bullet物理モジュール (bullet_engine) は削除または未導入です。\n下の「XPBD 物理ベイク実行」をご利用ください。")

    def _on_bullet_version_toggled(self, checked):
        """Bulletバージョン切り替え時の設定保存"""
        ver = "2.83.7" if self.rb_bullet_283.isChecked() else "2.75"
        mc.optionVar(sv=("MMDToolsForMaya_BulletVersion", ver))
        self._refresh_bullet_status()

    def _on_physics_mode_toggled(self, checked):
        """ダンスモーションモードと簡易モードの切り替え"""
        if self.rb_mode_dance.isChecked():
            self.le_substeps.setText("30")
        else:
            self.le_substeps.setText("10")

    def _refresh_target_models(self):
        """シーン内の対象MMDモデル一覧を更新"""
        if not hasattr(self, 'cbb_target_model'):
            return
        self.cbb_target_model.clear()
        self.cbb_target_model.addItem("自動検出 (シーン内のMMDモデル)", "")
        try:
            from ..converters import vmdpaimaya
        except Exception:
            try:
                from converters import vmdpaimaya
            except Exception:
                import vmdpaimaya
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for node, label in models:
                self.cbb_target_model.addItem(label, node)
        except Exception:
            pass

    def showEvent(self, event):
        super(PhysicsTabWidget, self).showEvent(event)
        self._refresh_target_models()
        # タブ表示時に最新のモデルパスが未入力であれば自動反映
        if not self.le_pmx_path.text().strip():
            last_pmx = mc.optionVar(q="MMDToolsForMaya_LastPmxPath") if mc.optionVar(exists="MMDToolsForMaya_LastPmxPath") else ""
            if last_pmx and os.path.exists(last_pmx):
                self.le_pmx_path.setText(last_pmx)

    def _on_frame_mode_toggled(self, checked):
        is_custom = self.rb_custom_frame.isChecked()
        self.le_start_frame.setEnabled(is_custom)
        self.le_end_frame.setEnabled(is_custom)

    def _on_pmx_changed(self, text=""):
        path = self.le_pmx_path.text().strip()
        valid = path.lower().endswith('.pmx') and os.path.exists(path)
        mc.optionVar(sv=("MMDToolsForMaya_LastPmxPath", path if valid else ""))

    def _clear_pmx_file(self):
        """PMXモデルファイル入力欄をクリア"""
        self.le_pmx_path.clear()
        mc.optionVar(sv=("MMDToolsForMaya_LastPmxPath", ""))

    def _browse_pmx(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "PMXモデルファイルを選択",
            self.le_pmx_path.text(),
            "PMX Files (*.pmx);;All Files (*.*)"
        )
        if path:
            self.le_pmx_path.setText(path)
            mc.optionVar(sv=("MMDToolsForMaya_LastPmxPath", path))

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith('.pmx'):
                self.le_pmx_path.setText(path)
                mc.optionVar(sv=("MMDToolsForMaya_LastPmxPath", path))

    def _on_hide_helpers_toggled(self, checked):
        mc.optionVar(iv=("MMDToolsForMaya_HideHelpersAfterBake", int(checked)))

    def _hide_helper_nodes_if_needed(self):
        """物理ベイク完了後に補助ノード（カメラビューコントローラ、全ての親、*_master、剛体・ジョイント可視化メッシュ等）を非表示化"""
        if not self.cb_hide_helpers.isChecked():
            return

        target_names = ["Apose_view_cnt", "Apose_subetenoya", "MMD_RigidBody_Joint_Visualizers"]
        for name in target_names:
            if mc.objExists(name):
                try:
                    mc.setAttr(f"{name}.visibility", False)
                except Exception:
                    pass

        # 剛体・ジョイント可視化グループのワイルドカード非表示
        for pat in ["*_RigidBody_Joint_Visualizers*", "*_RigidBody_Visualizers*", "*_Joint_Visualizers*"]:
            for v_node in mc.ls(pat, type=["transform", "joint"]) or []:
                try:
                    mc.setAttr(f"{v_node}.visibility", False)
                except Exception:
                    pass

        # ワイルドカード検索でマッチする補助ノード（カメラ、全ての親、*_master）も非表示化
        # ライトやカメラ関連ノードを誤って非表示に巻き込まないよう保護
        for pattern in ["*view_cnt*", "*subetenoya*", "*_master*"]:
            matched = mc.ls(pattern, type=["transform", "joint"]) or []
            for m in matched:
                m_lower = m.lower()
                if any(ex in m_lower for ex in ["light", "camera", "aim"]):
                    continue
                try:
                    mc.setAttr(f"{m}.visibility", False)
                except Exception:
                    pass

        # ビューポートライティングを確実に復元
        restore_viewport_lighting()
    def _execute_bullet_bake(self):
        """Bullet Physics (MMD本家仕様) による物理ベイク実行"""
        if not self._is_bullet_available():
            QMessageBox.information(
                self, "案内",
                "Bullet物理モジュール (bullet_engine) は削除または未導入です。\n"
                "「XPBD 物理ベイク実行」をご利用ください。"
            )
            return

        pmx_path = self.le_pmx_path.text().strip()
        if not pmx_path or not os.path.exists(pmx_path):
            QMessageBox.warning(self, "エラー", "有効なPMXモデルファイルを指定してください。")
            return

        try:
            scale = float(self.le_scale.text())
            gravity = float(self.le_gravity.text())
            substeps = int(self.le_substeps.text())
        except ValueError:
            QMessageBox.warning(self, "エラー", "パラメータの数値が正しくありません。")
            return

        if self.rb_auto_frame.isChecked():
            start_frame = int(mc.playbackOptions(query=True, minTime=True))
            end_frame = int(mc.playbackOptions(query=True, maxTime=True))
        else:
            try:
                start_frame = int(self.le_start_frame.text())
                end_frame = int(self.le_end_frame.text())
                # 開始・最終フレームが入力されている場合はタイムライン範囲を指定値に更新
                mc.playbackOptions(minTime=start_frame, maxTime=end_frame, animationStartTime=start_frame, animationEndTime=end_frame)
            except ValueError:
                QMessageBox.warning(self, "エラー", "開始・終了フレーム番号を正しく入力してください。")
                return

        enable_floor = self.cb_enable_floor.isChecked()
        fps = 30.0
        physics_mode = "dance" if self.rb_mode_dance.isChecked() else "simple"
        target_mode = self.cbb_target_model.currentData() if hasattr(self, 'cbb_target_model') else ""
        bullet_ver = "2.83.7" if self.rb_bullet_283.isChecked() else "2.75"

        try:
            from ..bullet_engine import bullet_maya_bridge
        except Exception:
            from bullet_engine import bullet_maya_bridge

        try:
            from ..converters import vmdpaimaya
        except Exception:
            try:
                from converters import vmdpaimaya
            except Exception:
                import vmdpaimaya

        models = []
        try:
            models = vmdpaimaya.get_available_mmd_models()
        except Exception:
            pass

        # 複数モデル順次ベイクの自動判定 (自動検出時に複数モデルが存在する場合)
        if not target_mode and len(models) > 1:
            log_dialog = ExecutionLogDialog(
                self.parent_window or self,
                title="Bullet 複数モデル順次物理ベイク実行ログ (追突防止・個別実行)",
                show_cancel=True
            )

            def run_multi_bullet_task():
                total = len(models)
                log_dialog.append_log("--- Bullet 複数モデル順次物理ベイク開始 ---\n")
                log_dialog.append_log(f"使用Bulletエンジン: Bullet {bullet_ver}\n")
                log_dialog.append_log(f"自動検出: {total} 体のモデルが見つかりました。\n")
                log_dialog.append_log("剛体の追突や反発・吹き飛びを防ぐため、1体ずつ順番に独立してベイクします。\n\n")

                for idx, (m_node, m_label) in enumerate(models, start=1):
                    if log_dialog.check_cancelled():
                        log_dialog.append_log("\n[中断] ユーザーによりベイクが中断されました。\n")
                        break

                    log_dialog.append_log("==================================================\n")
                    log_dialog.append_log(f"[{idx}/{total}] モデル物理ベイク開始: {m_label}\n")
                    log_dialog.append_log("==================================================\n")

                    # モデル固有のPMXパスを取得 (保存されている場合は優先)
                    model_pmx = pmx_path
                    if mc.attributeQuery('mmdModelPath', node=m_node, exists=True):
                        saved_path = mc.getAttr(f"{m_node}.mmdModelPath")
                        if saved_path and os.path.exists(saved_path):
                            model_pmx = saved_path

                    bridge = bullet_maya_bridge.BulletMayaBridge(pmx_path=model_pmx, scale=scale, target_model=m_node, bullet_version=bullet_ver)

                    def make_progress_cb(m_idx):
                        def _progress_cb(*args, **kwargs):
                            if len(args) >= 4:
                                cur_f, end_f, cur_step, tot_step = args[:4]
                                step_ratio = float(cur_step) / max(1.0, float(tot_step))
                                overall_p = int(((m_idx - 1) + step_ratio) / total * 100)
                                log_dialog.update_progress(
                                    overall_p,
                                    label_prefix=f"[{m_idx}/{total}]",
                                    unit=f"フレーム {cur_f} / {end_f}"
                                )
                            elif len(args) == 2:
                                p, msg = args
                                overall_p = int(((m_idx - 1) + (float(p) / 100.0)) / total * 100)
                                log_dialog.update_progress(overall_p, label_prefix=f"[{m_idx}/{total}]", unit=str(msg))
                            elif len(args) == 1:
                                p = args[0]
                                overall_p = int(((m_idx - 1) + (float(p) / 100.0)) / total * 100)
                                log_dialog.update_progress(overall_p)
                        return _progress_cb

                    bridge.bake_simulation(
                        start_frame=start_frame,
                        end_frame=end_frame,
                        sub_steps=substeps,
                        enable_floor=enable_floor,
                        gravity_y=gravity,
                        fps=fps,
                        physics_mode=physics_mode,
                        progress_callback=make_progress_cb(idx),
                        cancel_callback=log_dialog.check_cancelled
                    )
                    log_dialog.append_log(f"[{idx}/{total}] 完了: {m_label}\n\n")

                log_dialog.update_progress(100, "すべてのモデルの物理ベイクが完了しました")
                restore_viewport_lighting()

            success = log_dialog.run_task(run_multi_bullet_task)
        else:
            # 単一モデル時のPMXパスおよび対象モデルの解決
            single_pmx = pmx_path
            single_target = target_mode or None
            if not single_target and len(models) == 1:
                single_target = models[0][0]
            if single_target and mc.attributeQuery('mmdModelPath', node=single_target, exists=True):
                saved_path = mc.getAttr(f"{single_target}.mmdModelPath")
                if saved_path and os.path.exists(saved_path):
                    single_pmx = saved_path

            log_dialog = ExecutionLogDialog(self.parent_window or self, title="Bullet 物理演算ベイク実行ログ (MMD本家仕様)", show_cancel=True)

            def run_bullet_task():
                log_dialog.append_log(f"使用Bulletエンジン: Bullet {bullet_ver}\n")
                bridge = bullet_maya_bridge.BulletMayaBridge(pmx_path=single_pmx, scale=scale, target_model=single_target, bullet_version=bullet_ver)
                bridge.bake_simulation(
                    start_frame=start_frame,
                    end_frame=end_frame,
                    sub_steps=substeps,
                    enable_floor=enable_floor,
                    gravity_y=gravity,
                    fps=fps,
                    physics_mode=physics_mode,
                    progress_callback=log_dialog.update_progress,
                    cancel_callback=log_dialog.check_cancelled
                )
                restore_viewport_lighting()

            success = log_dialog.run_task(run_bullet_task)
        if success:
            self._hide_helper_nodes_if_needed()
            if log_dialog.is_cancelled:
                mc.inViewMessage(
                    amg='<span style="color:#ffaa55;">MMD Tools for Maya:</span> Bullet物理ベイクがユーザーにより中断されました。',
                    pos='topCenter',
                    fade=True
                )
            else:
                mc.inViewMessage(
                    amg='<span style="color:#2ecc71;">MMD Tools for Maya:</span> Bullet物理シミュレーションのベイクが完了しました。',
                    pos='topCenter',
                    fade=True
                )

    def _execute_bake(self):
        pmx_path = self.le_pmx_path.text().strip()
        if not pmx_path or not os.path.exists(pmx_path):
            QMessageBox.warning(self, "エラー", "有効なPMXモデルファイルが指定されていません。")
            return

        try:
            scale = float(self.le_scale.text())
            gravity = float(self.le_gravity.text())
            substeps = int(self.le_substeps.text())
        except ValueError:
            QMessageBox.warning(self, "エラー", "パラメータの数値が正しくありません。")
            return

        if self.rb_auto_frame.isChecked():
            start_frame = int(mc.playbackOptions(query=True, minTime=True))
            end_frame = int(mc.playbackOptions(query=True, maxTime=True))
        else:
            try:
                start_frame = int(self.le_start_frame.text())
                end_frame = int(self.le_end_frame.text())
                # 開始・最終フレームが入力されている場合はタイムライン範囲を指定値に更新
                mc.playbackOptions(minTime=start_frame, maxTime=end_frame, animationStartTime=start_frame, animationEndTime=end_frame)
            except ValueError:
                QMessageBox.warning(self, "エラー", "開始・終了フレーム番号を正しく入力してください。")
                return

        fps = 30.0
        physics_mode = "dance" if self.rb_mode_dance.isChecked() else "simple"

        log_dialog = ExecutionLogDialog(self.parent_window or self, title="XPBD 物理演算ベイク実行ログ", show_cancel=True)

        def run_physics_task():
            try:
                from ..cpp_engine import xpbd_maya_bridge
            except Exception:
                from cpp_engine import xpbd_maya_bridge
            self.bridge = xpbd_maya_bridge.XpbdMayaBridge(scale=scale)
            ok = self.bridge.initialize_from_pmx(pmx_path)
            if not ok:
                raise RuntimeError("PMX剛体データの読み込みに失敗しました。")
            self.bridge.bake_simulation(
                start_frame=start_frame,
                end_frame=end_frame,
                gravity_y=gravity,
                substeps=substeps,
                fps=fps,
                physics_mode=physics_mode,
                progress_callback=log_dialog.update_progress,
                cancel_callback=log_dialog.check_cancelled
            )

        success = log_dialog.run_task(run_physics_task)
        if success:
            self._hide_helper_nodes_if_needed()
            if log_dialog.is_cancelled:
                mc.inViewMessage(
                    amg='<span style="color:#ffaa55;">MMD Tools for Maya:</span> XPBD物理ベイクがユーザーにより中断されました。',
                    pos='topCenter',
                    fade=True
                )
            else:
                mc.inViewMessage(
                    amg='<span style="color:#2ecc71;">MMD Tools for Maya:</span> XPBD物理シミュレーションのベイクが完了しました。',
                    pos='topCenter',
                    fade=True
                )

    def _execute_clear_keys(self):
        pmx_path = self.le_pmx_path.text().strip()
        if not pmx_path or not os.path.exists(pmx_path):
            QMessageBox.warning(self, "エラー", "有効なPMXモデルファイルを指定してください。")
            return

        try:
            try:
                from ..cpp_engine import xpbd_maya_bridge
            except Exception:
                from cpp_engine import xpbd_maya_bridge
            bridge = xpbd_maya_bridge.XpbdMayaBridge()
            if bridge.initialize_from_pmx(pmx_path):
                bridge.clear_physics_keyframes()
                mc.inViewMessage(
                    amg='<span style="color:#ffaa55;">MMD Tools for Maya:</span> 物理キーフレームをクリアしました。',
                    pos='topCenter',
                    fade=True
                )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"キーフレーム削除中にエラーが発生しました:\n{e}")

    def _execute_reconnect(self):
        try:
            try:
                from ..converters import reconnect_visualizers_to_bones
            except Exception:
                from converters import reconnect_visualizers_to_bones
            ok = reconnect_visualizers_to_bones()
            if ok:
                mc.inViewMessage(
                    amg='<span style="color:#2ecc71;">MMD Tools for Maya:</span> 剛体とJointをモデルボーンに再吸着しました。',
                    pos='topCenter',
                    fade=True
                )
            else:
                QMessageBox.information(self, "情報", "シーン内に剛体・Joint可視化ノードが存在しません。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"再吸着処理中にエラーが発生しました:\n{e}")

    def _execute_create_visualizers(self):
        pmx_path = self.le_pmx_path.text().strip()
        if not pmx_path or not os.path.exists(pmx_path):
            QMessageBox.warning(self, "エラー", "有効なPMXモデルファイルを指定してください。")
            return

        try:
            scale = float(self.le_scale.text())
        except ValueError:
            scale = 8.0

        try:
            try:
                from ..converters import create_rigidbody_visualizers
            except Exception:
                from converters import create_rigidbody_visualizers
            create_rigidbody_visualizers(pmx_path, scale=scale)
            mc.inViewMessage(
                amg='<span style="color:#2ecc71;">MMD Tools for Maya:</span> 剛体とJointの可視化を生成しました。',
                pos='topCenter',
                fade=True
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"可視化生成中にエラーが発生しました:\n{e}")

# ==============================================================================
# 物理演算GUI タブ（外部物理エンジン連携・キーフレームベイク）
# ==============================================================================
class PhysicsGuiTabWidget(QWidget):
    """外部物理演算エンジンとのデータ連携（モーション書き出し＆キーフレームベイク）を行うUIタブ"""
    def __init__(self, parent=None):
        super(PhysicsGuiTabWidget, self).__init__(parent)
        self.parent_window = parent
        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # シーン内インポート状態確認
        status_box = QGroupBox("シーン読み込み状態の確認")
        status_layout = QVBoxLayout(status_box)

        h_status_row = QHBoxLayout()
        h_status_row.setContentsMargins(6, 4, 6, 4)
        h_status_row.setSpacing(12)
        v_status_labels = QVBoxLayout()
        self.lbl_scene_pmx_status = QLabel("PMXモデル: 確認中...")
        self.lbl_scene_pmx_status.setStyleSheet("font-weight: bold;")
        self.lbl_scene_motion_status = QLabel("モーション: 確認中...")
        self.lbl_scene_motion_status.setStyleSheet("font-weight: bold;")
        v_status_labels.addWidget(self.lbl_scene_pmx_status)
        v_status_labels.addWidget(self.lbl_scene_motion_status)
        h_status_row.addLayout(v_status_labels)

        h_status_row.addStretch()
        self.btn_refresh_scene_status = QPushButton("状態を再確認")
        self.btn_refresh_scene_status.setFixedWidth(120)
        self.btn_refresh_scene_status.setFixedHeight(34)
        self.btn_refresh_scene_status.setStyleSheet("padding: 4px 8px; font-weight: bold;")
        self.btn_refresh_scene_status.clicked.connect(self._check_scene_import_status)
        h_status_row.addWidget(self.btn_refresh_scene_status)
        status_layout.addLayout(h_status_row)
        content_layout.addWidget(status_box)

        # PMXモデル参照情報
        pmx_box = QGroupBox("PMX モデル情報")
        pmx_layout = QVBoxLayout(pmx_box)

        h_pmx_path = QHBoxLayout()
        self.le_pmx_path = QLineEdit()
        self.le_pmx_path.setPlaceholderText("PMXファイルのパス（インポートタブと連動）")
        last_pmx = mc.optionVar(q="MMDToolsForMaya_LastPmxPath") if mc.optionVar(exists="MMDToolsForMaya_LastPmxPath") else ""
        if last_pmx and os.path.exists(last_pmx):
            self.le_pmx_path.setText(last_pmx)
        self.le_pmx_path.textChanged.connect(self._on_pmx_changed)
        h_pmx_path.addWidget(self.le_pmx_path)

        self.btn_sync_pmx = QPushButton("インポートタブから取得")
        self.btn_sync_pmx.clicked.connect(self._sync_pmx_from_import_tab)
        h_pmx_path.addWidget(self.btn_sync_pmx)

        self.btn_browse_pmx = QPushButton("参照...")
        self.btn_browse_pmx.setFixedWidth(75)
        self.btn_browse_pmx.clicked.connect(self._browse_pmx)
        h_pmx_path.addWidget(self.btn_browse_pmx)
        pmx_layout.addLayout(h_pmx_path)
        content_layout.addWidget(pmx_box)

        default_dir = os.path.dirname(last_pmx) if last_pmx and os.path.exists(last_pmx) else mc.workspace(q=True, rootDirectory=True)

        # VMDモーション参照情報
        vmd_src_box = QGroupBox("VMD モーション情報 (ベイク元モーション)")
        vmd_src_layout = QVBoxLayout(vmd_src_box)

        h_vmd_src = QHBoxLayout()
        self.le_vmd_source_path = QLineEdit()
        self.le_vmd_source_path.setPlaceholderText("ベイク元となるVMDモーションのファイルパス")
        last_vmd = mc.optionVar(q="MMDToolsForMaya_LastModelVmdPath") if mc.optionVar(exists="MMDToolsForMaya_LastModelVmdPath") else ""
        if last_vmd and os.path.exists(last_vmd):
            self.le_vmd_source_path.setText(last_vmd)
        self.le_vmd_source_path.textChanged.connect(self._on_vmd_changed)
        h_vmd_src.addWidget(self.le_vmd_source_path)

        self.btn_sync_vmd = QPushButton("モーションタブから取得")
        self.btn_sync_vmd.clicked.connect(self._sync_vmd_from_motion_tab)
        h_vmd_src.addWidget(self.btn_sync_vmd)

        self.btn_browse_vmd_src = QPushButton("参照...")
        self.btn_browse_vmd_src.setFixedWidth(75)
        self.btn_browse_vmd_src.clicked.connect(self._browse_source_vmd)
        h_vmd_src.addWidget(self.btn_browse_vmd_src)
        vmd_src_layout.addLayout(h_vmd_src)
        content_layout.addWidget(vmd_src_box)

        # リアルタイム物理ベイク (新3D物理ビューア連携)
        stream_bake_box = QGroupBox("リアルタイム物理ベイク (新3D物理ビューア連携)")
        stream_bake_layout = QVBoxLayout(stream_bake_box)

        h_stream_model = QHBoxLayout()
        h_stream_model.setSpacing(10)
        h_stream_model.addWidget(QLabel("適用対象モデル:"))
        self.cbb_stream_target_model = QComboBox()
        self.cbb_stream_target_model.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        h_stream_model.addWidget(self.cbb_stream_target_model)

        self.btn_refresh_stream_models = QPushButton("更新")
        self.btn_refresh_stream_models.setFixedWidth(85)
        self.btn_refresh_stream_models.setFixedHeight(34)
        self.btn_refresh_stream_models.setStyleSheet("padding: 2px 10px;")
        self.btn_refresh_stream_models.clicked.connect(self._refresh_stream_target_models)
        h_stream_model.addWidget(self.btn_refresh_stream_models)

        self.btn_multi_stream_bake = QPushButton("ベイクするモデルの確認")
        self.btn_multi_stream_bake.setFixedWidth(170)
        self.btn_multi_stream_bake.setFixedHeight(34)
        self.btn_multi_stream_bake.setToolTip("現在ベイク対象として設定されているMMDモデル一覧を確認します。")
        self.btn_multi_stream_bake.clicked.connect(self._open_multi_stream_bake_dialog)
        h_stream_model.addWidget(self.btn_multi_stream_bake)

        stream_bake_layout.addLayout(h_stream_model)
        stream_bake_layout.addSpacing(16)

        # Bullet エンジンバージョン選択 (本家MMD採用 2.75 vs 改良 2.83.7)
        h_stream_bullet_ver = QHBoxLayout()
        h_stream_bullet_ver.addWidget(QLabel("Bullet エンジン:"))
        self.rb_stream_bullet_275 = QRadioButton("Bullet 2.75 (本家MMD採用・挙動再現重視)")
        self.rb_stream_bullet_283 = QRadioButton("Bullet 2.83.7 (後発・改良バージョン・安定性重視)")

        saved_stream_ver = "2.75"
        if mc.optionVar(exists="MMDToolsForMaya_StreamBulletVersion"):
            saved_stream_ver = str(mc.optionVar(q="MMDToolsForMaya_StreamBulletVersion"))
        elif mc.optionVar(exists="MMDToolsForMaya_BulletVersion"):
            saved_stream_ver = str(mc.optionVar(q="MMDToolsForMaya_BulletVersion"))

        if "2.83" in saved_stream_ver:
            self.rb_stream_bullet_283.setChecked(True)
        else:
            self.rb_stream_bullet_275.setChecked(True)

        self.rb_stream_bullet_275.toggled.connect(self._on_stream_bullet_version_toggled)
        self.rb_stream_bullet_283.toggled.connect(self._on_stream_bullet_version_toggled)

        self.bg_stream_bullet_ver = QButtonGroup(self)
        self.bg_stream_bullet_ver.addButton(self.rb_stream_bullet_275)
        self.bg_stream_bullet_ver.addButton(self.rb_stream_bullet_283)

        h_stream_bullet_ver.addWidget(self.rb_stream_bullet_275)
        h_stream_bullet_ver.addWidget(self.rb_stream_bullet_283)
        h_stream_bullet_ver.addStretch()
        stream_bake_layout.addLayout(h_stream_bullet_ver)

        # VMDファイル出力オプション
        vmd_out_box = QGroupBox("物理ベイク済みモーションの書き出し設定")
        vmd_out_layout = QVBoxLayout(vmd_out_box)

        h_vmd_out_choice = QHBoxLayout()
        self.rb_vmd_out_enable = QRadioButton("VMDファイルを出力する")
        self.rb_vmd_out_disable = QRadioButton("VMDファイルを出力しない (Mayaへの直接ベイクのみ)")
        self.rb_vmd_out_disable.setChecked(True)
        self.rb_vmd_out_enable.toggled.connect(self._on_vmd_output_toggled)

        self.bg_vmd_output = QButtonGroup(self)
        self.bg_vmd_output.addButton(self.rb_vmd_out_enable)
        self.bg_vmd_output.addButton(self.rb_vmd_out_disable)

        h_vmd_out_choice.addWidget(self.rb_vmd_out_enable)
        h_vmd_out_choice.addWidget(self.rb_vmd_out_disable)
        h_vmd_out_choice.addStretch()
        vmd_out_layout.addLayout(h_vmd_out_choice)

        h_vmd_out_path = QHBoxLayout()
        h_vmd_out_path.addWidget(QLabel("保存先:"))
        self.le_vmd_output_path = QLineEdit()
        self.le_vmd_output_path.setPlaceholderText("出力先VMDファイルパス")
        self.le_vmd_output_path.setEnabled(False)
        h_vmd_out_path.addWidget(self.le_vmd_output_path)

        self.btn_browse_vmd_output = QPushButton("参照...")
        self.btn_browse_vmd_output.setFixedWidth(75)
        self.btn_browse_vmd_output.setEnabled(False)
        self.btn_browse_vmd_output.clicked.connect(self._browse_vmd_output)
        h_vmd_out_path.addWidget(self.btn_browse_vmd_output)
        vmd_out_layout.addLayout(h_vmd_out_path)

        stream_bake_layout.addWidget(vmd_out_box)

        # シミュレーション範囲設定 (ラジオボタン選択 & 入力欄)
        h_stream_frame_mode = QHBoxLayout()
        h_stream_frame_mode.addWidget(QLabel("シミュレーション範囲:"))
        self.rb_stream_auto_frame = QRadioButton("タイムライン全体 (自動)")
        self.rb_stream_auto_frame.setChecked(True)
        self.rb_stream_custom_frame = QRadioButton("フレーム指定")
        self.rb_stream_auto_frame.toggled.connect(self._on_stream_frame_mode_toggled)

        self.bg_stream_frame_mode = QButtonGroup(self)
        self.bg_stream_frame_mode.addButton(self.rb_stream_auto_frame)
        self.bg_stream_frame_mode.addButton(self.rb_stream_custom_frame)

        h_stream_frame_mode.addWidget(self.rb_stream_auto_frame)
        h_stream_frame_mode.addWidget(self.rb_stream_custom_frame)
        h_stream_frame_mode.addStretch()
        stream_bake_layout.addLayout(h_stream_frame_mode)

        # 一段下げたフレーム数値入力レイアウト
        h_stream_custom_frame = QHBoxLayout()
        h_stream_custom_frame.setContentsMargins(24, 0, 0, 0)
        h_stream_custom_frame.addWidget(QLabel("開始フレーム:"))
        self.le_stream_start_frame = QLineEdit()
        self.le_stream_start_frame.setFixedWidth(70)
        self.le_stream_start_frame.setEnabled(False)
        h_stream_custom_frame.addWidget(self.le_stream_start_frame)

        h_stream_custom_frame.addWidget(QLabel("終了フレーム:"))
        self.le_stream_end_frame = QLineEdit()
        self.le_stream_end_frame.setFixedWidth(70)
        self.le_stream_end_frame.setEnabled(False)
        h_stream_custom_frame.addWidget(self.le_stream_end_frame)
        h_stream_custom_frame.addStretch()
        stream_bake_layout.addLayout(h_stream_custom_frame)

        # タイムライン初期値を設定
        try:
            min_t = int(mc.playbackOptions(query=True, minTime=True))
            max_t = int(mc.playbackOptions(query=True, maxTime=True))
            self.le_stream_start_frame.setText(str(min_t))
            self.le_stream_end_frame.setText(str(max_t))
        except Exception:
            self.le_stream_start_frame.setText("0")
            self.le_stream_end_frame.setText("100")

        # 物理パラメータ設定 (上段: 先行フレーム数・安定化時間)
        h_stream_params_top = QHBoxLayout()
        h_stream_params_top.addWidget(QLabel("先行フレーム数:"))
        init_lookahead = mc.optionVar(q="MMDToolsForMaya_StreamLookahead") if mc.optionVar(exists="MMDToolsForMaya_StreamLookahead") else "16"
        self.le_stream_lookahead = QLineEdit(str(init_lookahead))
        self.le_stream_lookahead.setFixedWidth(70)
        self.le_stream_lookahead.setToolTip("ビューアが先行して物理計算を行うフレーム数です (ACK同期用)。")
        self.le_stream_lookahead.textChanged.connect(lambda val: mc.optionVar(sv=("MMDToolsForMaya_StreamLookahead", val.strip())))
        h_stream_params_top.addWidget(self.le_stream_lookahead)

        h_stream_params_top.addWidget(QLabel("安定化時間(秒):"))
        init_warmup = mc.optionVar(q="MMDToolsForMaya_StreamWarmup") if mc.optionVar(exists="MMDToolsForMaya_StreamWarmup") else "0.0"
        self.le_stream_warmup = QLineEdit(str(init_warmup))
        self.le_stream_warmup.setFixedWidth(70)
        self.le_stream_warmup.setToolTip("ベイク開始前にフレーム0の姿勢で物理演算を先行実行し、スカートや髪の垂れ下がりを落ち着かせる時間(秒)です。タイミングの一致を優先する場合は0.0秒を設定します。")
        self.le_stream_warmup.textChanged.connect(lambda val: mc.optionVar(sv=("MMDToolsForMaya_StreamWarmup", val.strip())))
        h_stream_params_top.addWidget(self.le_stream_warmup)
        h_stream_params_top.addStretch()
        stream_bake_layout.addLayout(h_stream_params_top)

        # 物理パラメータ設定 (下段: オフセット・スケール倍率・精度)
        h_stream_params_bottom = QHBoxLayout()
        h_stream_params_bottom.addWidget(QLabel("オフセット:"))
        init_offset = mc.optionVar(q="MMDToolsForMaya_StreamOffset") if mc.optionVar(exists="MMDToolsForMaya_StreamOffset") else "0"
        self.le_stream_offset = QLineEdit(str(init_offset))
        self.le_stream_offset.setFixedWidth(70)
        self.le_stream_offset.setToolTip("身体モーションや楽曲に対して物理ベイクの開始フレームを前後にずらす値です (例: -60 または 60)。")
        self.le_stream_offset.textChanged.connect(lambda val: mc.optionVar(sv=("MMDToolsForMaya_StreamOffset", val.strip())))
        h_stream_params_bottom.addWidget(self.le_stream_offset)

        h_stream_params_bottom.addWidget(QLabel("スケール倍率:"))
        init_scale = mc.optionVar(q="MMDToolsForMaya_StreamScale") if mc.optionVar(exists="MMDToolsForMaya_StreamScale") else "8.0"
        self.le_stream_scale = QLineEdit(str(init_scale))
        self.le_stream_scale.setFixedWidth(70)
        h_stream_params_bottom.addWidget(self.le_stream_scale)

        h_stream_params_bottom.addWidget(QLabel("精度 (貫通防止):"))
        self.cbb_stream_substep = QComboBox()
        self.cbb_stream_substep.addItem("高精度 (120Hz・貫通防止推奨)", 120)
        self.cbb_stream_substep.addItem("超高精度 (240Hz・激しいダンス用)", 240)
        self.cbb_stream_substep.addItem("標準 (60Hz)", 60)
        init_substep = int(mc.optionVar(q="MMDToolsForMaya_StreamSubstep")) if mc.optionVar(exists="MMDToolsForMaya_StreamSubstep") else 120
        idx = self.cbb_stream_substep.findData(init_substep)
        if idx >= 0:
            self.cbb_stream_substep.setCurrentIndex(idx)
        self.cbb_stream_substep.currentIndexChanged.connect(
            lambda _: mc.optionVar(iv=("MMDToolsForMaya_StreamSubstep", self.cbb_stream_substep.currentData() or 120))
        )
        self.cbb_stream_substep.setToolTip("物理シミュレーションの内部計算周波数を指定します。120Hz以上に設定することで足やスカートの剛体貫通を大幅に防止します。")
        h_stream_params_bottom.addWidget(self.cbb_stream_substep)
        h_stream_params_bottom.addStretch()
        stream_bake_layout.addLayout(h_stream_params_bottom)

        # ベイク完了後の補助ノード非表示設定
        self.cb_stream_hide_helpers = QCheckBox("物理ベイク完了後に補助ノード (Apose_view_cnt / Apose_subetenoya / *_master / 剛体・ジョイント可視化メッシュ) を非表示にする")
        self.cb_stream_hide_helpers.setChecked(True)
        stream_bake_layout.addWidget(self.cb_stream_hide_helpers)

        self.btn_stream_bake = QPushButton("リアルタイム物理ベイク実行")
        self.btn_stream_bake.setFixedHeight(44)
        self.btn_stream_bake.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: #fff; font-size: 13px; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3498db; }"
        )
        self.btn_stream_bake.setToolTip("新3D物理ビューアを起動し、揺れものボーン（スカート・髪等）の計算結果をリアルタイムにMayaへ同期・ベイクします。")
        self.btn_stream_bake.clicked.connect(self._run_realtime_stream_bake)
        stream_bake_layout.addWidget(self.btn_stream_bake)

        content_layout.addWidget(stream_bake_box)

        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # 対象モデル一覧および状態の初期設定
        self._refresh_stream_target_models()
        self._update_default_vmd_output_path()
        self._on_vmd_output_toggled(False)
        self._check_scene_import_status()

    def _get_default_vmd_output_dir(self):
        """プラグイン内の asset/vmd_bake_data フォルダパスを取得し、自動作成"""
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bake_dir = os.path.join(plugin_root, "asset", "vmd_bake_data")
        try:
            os.makedirs(bake_dir, exist_ok=True)
        except Exception:
            pass
        return bake_dir

    def _update_default_vmd_output_path(self):
        """モデル名またはVMD名に基づいてデフォルトの出力先パスを設定"""
        bake_dir = self._get_default_vmd_output_dir()
        base_name = "physics_baked"
        pmx_path = self.le_pmx_path.text().strip()
        vmd_path = self.le_vmd_source_path.text().strip()
        if vmd_path:
            base_name = os.path.splitext(os.path.basename(vmd_path))[0] + "_physics_baked"
        elif pmx_path:
            base_name = os.path.splitext(os.path.basename(pmx_path))[0] + "_physics_baked"
        self.le_vmd_output_path.setText(os.path.join(bake_dir, f"{base_name}.vmd").replace("\\", "/"))

    def _on_pmx_changed(self, text=""):
        """PMXファイルパス変更時の連動処理"""
        self._update_default_vmd_output_path()
        self._check_scene_import_status()

    def _on_vmd_changed(self, text=""):
        """VMDファイルパス変更時の連動処理"""
        self._update_default_vmd_output_path()
        self._check_scene_import_status()

    def _on_vmd_output_toggled(self, checked):
        """VMD出力ラジオボタンの切り替え"""
        self.le_vmd_output_path.setEnabled(checked)
        self.btn_browse_vmd_output.setEnabled(checked)

    def _browse_vmd_output(self):
        """VMD保存先ファイル選択ダイアログ"""
        current_path = self.le_vmd_output_path.text().strip()
        start_dir = os.path.dirname(current_path) if current_path else self._get_default_vmd_output_dir()
        path, _ = QFileDialog.getSaveFileName(
            self, "物理ベイクVMDファイルの保存先を指定", current_path or start_dir, "VMDファイル (*.vmd);;全てのファイル (*.*)"
        )
        if path:
            self.le_vmd_output_path.setText(path.replace("\\", "/"))

    def _check_scene_import_status(self):
        """シーン内のPMXモデルおよびモーションのインポート状態を確認"""
        # PMXモデル確認
        try:
            from ..converters import vmdpaimaya
        except Exception:
            try:
                from converters import vmdpaimaya
            except Exception:
                import vmdpaimaya

        models = []
        try:
            models = vmdpaimaya.get_available_mmd_models()
        except Exception:
            pass

        if models:
            model_names = [m[1] for m in models]
            self.lbl_scene_pmx_status.setText(f"✔ PMXモデル: インポート済み ({len(models)} 体検出: {model_names[0]})")
            self.lbl_scene_pmx_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            joints = mc.ls(type="joint") or []
            if joints:
                self.lbl_scene_pmx_status.setText(f"✔ PMXモデル: ジョイント検出済み (全 {len(joints)} 本)")
                self.lbl_scene_pmx_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
            else:
                self.lbl_scene_pmx_status.setText("✖ PMXモデル: 未インポート (「MMD → Maya」タブからインポートしてください)")
                self.lbl_scene_pmx_status.setStyleSheet("color: #e67e22; font-weight: bold;")

        # モーション確認
        anim_curves = mc.ls(type=["animCurveTA", "animCurveTL", "animCurveTT", "animCurveTU"]) or []
        if anim_curves:
            try:
                min_t = mc.playbackOptions(query=True, minTime=True)
                max_t = mc.playbackOptions(query=True, maxTime=True)
                self.lbl_scene_motion_status.setText(f"✔ モーション: インポート済み (タイムライン: {int(min_t)} ～ {int(max_t)} フレーム)")
                self.lbl_scene_motion_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
            except Exception:
                self.lbl_scene_motion_status.setText(f"✔ モーション: キーフレーム検出済み ({len(anim_curves)} カーブ)")
                self.lbl_scene_motion_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            self.lbl_scene_motion_status.setText("✖ モーション: 未インポート (「モーション(VMD)」タブからインポートしてください)")
            self.lbl_scene_motion_status.setStyleSheet("color: #e67e22; font-weight: bold;")

    def _open_multi_stream_bake_dialog(self):
        """複数モデル順次物理ベイクダイアログを表示"""
        if not hasattr(self, '_multi_bake_dialog') or self._multi_bake_dialog is None:
            self._multi_bake_dialog = MultiModelPhysicsBakeDialog(self)
        self._multi_bake_dialog._refresh_models_from_scene()
        self._multi_bake_dialog.show()
        self._multi_bake_dialog.raise_()
        self._multi_bake_dialog.activateWindow()

    def _refresh_stream_target_models(self):
        """リアルタイム物理ベイク用の対象MMDモデル一覧を更新"""
        self.cbb_stream_target_model.clear()
        self.cbb_stream_target_model.addItem("自動検出 (シーン内のMMDモデル)", "")
        try:
            from ..converters import vmdpaimaya
        except Exception:
            try:
                from converters import vmdpaimaya
            except Exception:
                import vmdpaimaya
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for node, label in models:
                self.cbb_stream_target_model.addItem(label, node)
        except Exception:
            pass

    def _sync_pmx_from_import_tab(self, silent=False):
        """インポートタブから現在設定されているPMXパスを取得"""
        path = ""
        if self.parent_window and hasattr(self.parent_window, "tab_import"):
            path = self.parent_window.tab_import.le_file_path.text().strip()
        if not path and mc.optionVar(exists="MMDToolsForMaya_LastPmxPath"):
            path = mc.optionVar(q="MMDToolsForMaya_LastPmxPath")
        if path:
            if self.le_pmx_path.text().strip() != path:
                self.le_pmx_path.setText(path)
                self._update_default_paths(path)
                self._update_default_vmd_output_path()
            if not silent:
                mc.inViewMessage(
                    amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> PMXパスを取得しました: {os.path.basename(path)}',
                    pos='topCenter',
                    fade=True
                )
        elif not silent:
            QMessageBox.information(self, "情報", "インポートタブにPMXパスが設定されていません。")

    def _sync_vmd_from_motion_tab(self, silent=False):
        """モーションタブから現在設定されているVMDパスを取得"""
        path = ""
        if self.parent_window and hasattr(self.parent_window, "tab_vmd"):
            path = self.parent_window.tab_vmd.le_file_path.text().strip()
        if not path and mc.optionVar(exists="MMDToolsForMaya_LastModelVmdPath"):
            path = mc.optionVar(q="MMDToolsForMaya_LastModelVmdPath")
        if path:
            if self.le_vmd_source_path.text().strip() != path:
                self.le_vmd_source_path.setText(path)
                self._update_default_vmd_output_path()
            if not silent:
                mc.inViewMessage(
                    amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> VMDモーションパスを取得しました: {os.path.basename(path)}',
                    pos='topCenter',
                    fade=True
                )
        elif not silent:
            QMessageBox.information(self, "情報", "モーションタブにVMDパスが設定されていません。")

    def refresh_all_tab_info(self):
        """タブ選択時にシーン読み込み状態、PMXモデル情報、VMDモーション情報を即時更新"""
        self._check_scene_import_status()
        self._sync_pmx_from_import_tab(silent=True)
        self._sync_vmd_from_motion_tab(silent=True)
        self._refresh_stream_target_models()

    def _browse_source_vmd(self):
        """ベイク元VMDファイル選択ダイアログ"""
        path, _ = QFileDialog.getOpenFileName(
            self, "ベイク元VMDモーションファイルを選択", self.le_vmd_source_path.text(), "VMDファイル (*.vmd);;全てのファイル (*.*)"
        )
        if path:
            self.le_vmd_source_path.setText(path.replace("\\", "/"))
            self._update_default_vmd_output_path()

    def _on_stream_frame_mode_toggled(self, checked):
        """シミュレーション範囲ラジオボタンの切り替え連動"""
        is_custom = not checked
        self.le_stream_start_frame.setEnabled(is_custom)
        self.le_stream_end_frame.setEnabled(is_custom)

    def _on_stream_bullet_version_toggled(self, checked):
        """リアルタイム物理ベイクのBulletバージョン切り替えイベント"""
        if not checked:
            return
        ver = "2.83.7" if hasattr(self, 'rb_stream_bullet_283') and self.rb_stream_bullet_283.isChecked() else "2.75"
        mc.optionVar(sv=("MMDToolsForMaya_StreamBulletVersion", ver))

    def _hide_helper_nodes_after_bake(self):
        """ベイク完了後に補助ノード群を非表示化"""
        if hasattr(self, 'cb_stream_hide_helpers') and not self.cb_stream_hide_helpers.isChecked():
            return

        # 剛体・Joint可視化ノードを非表示化
        for node in mc.ls("MMD_Physics_RigidBodies*", "MMD_Physics_Joints*", "MMD_Physics_Locators*","MMD_RigidBody_Joint_Visualizers", type=["transform", "joint"]) or []:
            try:
                mc.setAttr(f"{node}.visibility", False)
            except Exception:
                pass

        # 補助コントローラーを非表示化
        target_names = [
            "Apose_view_cnt",
            "Apose_subetenoya",
            "view_cnt",
            "subetenoya",
            "Apose_view_cnt_master",
            "Apose_subetenoya_master"
        ]
        for name in target_names:
            if mc.objExists(name):
                try:
                    mc.setAttr(f"{name}.visibility", False)
                except Exception:
                    pass

        # ワイルドカード検索でマッチする補助ノードを非表示化 (カメラ・ライト・エイムは除外保護)
        for pattern in ["*view_cnt*", "*subetenoya*", "*_master*"]:
            matched = mc.ls(pattern, type=["transform", "joint"]) or []
            for m in matched:
                m_lower = m.lower()
                if any(ex in m_lower for ex in ["light", "camera", "aim"]):
                    continue
                try:
                    mc.setAttr(f"{m}.visibility", False)
                except Exception:
                    pass

        restore_viewport_lighting()

    def _run_realtime_stream_bake(self):
        """新3D物理ビューアと同期しながらリアルタイム物理ベイクを実行"""
        pmx_path = self.le_pmx_path.text().strip()
        vmd_path = self.le_vmd_source_path.text().strip()

        if not pmx_path or not os.path.exists(pmx_path):
            QMessageBox.warning(self, "警告", "有効なPMXモデルファイルを指定してください。")
            return

        if not vmd_path or not os.path.exists(vmd_path):
            QMessageBox.warning(self, "警告", "有効なベイク元VMDモーションファイルを指定してください。")
            return

        # シミュレーション範囲の取得
        start_frame = None
        end_frame = None
        if not self.rb_stream_auto_frame.isChecked():
            try:
                start_frame = int(self.le_stream_start_frame.text().strip())
                end_frame = int(self.le_stream_end_frame.text().strip())
                mc.playbackOptions(minTime=start_frame, maxTime=end_frame, animationStartTime=start_frame, animationEndTime=end_frame)
            except ValueError:
                QMessageBox.warning(self, "エラー", "開始・終了フレーム番号を正しく入力してください。")
                return

        try:
            scale = float(self.le_stream_scale.text().strip())
        except ValueError:
            scale = 8.0
        mc.optionVar(sv=("MMDToolsForMaya_StreamScale", str(scale)))

        try:
            lookahead = int(self.le_stream_lookahead.text().strip())
        except ValueError:
            lookahead = 16
        mc.optionVar(sv=("MMDToolsForMaya_StreamLookahead", str(lookahead)))

        try:
            warmup = float(self.le_stream_warmup.text().strip())
        except ValueError:
            warmup = 0.0
        mc.optionVar(sv=("MMDToolsForMaya_StreamWarmup", str(warmup)))

        try:
            frame_offset = int(self.le_stream_offset.text().strip())
        except ValueError:
            frame_offset = 0
        mc.optionVar(sv=("MMDToolsForMaya_StreamOffset", str(frame_offset)))

        out_vmd = "none"
        if self.rb_vmd_out_enable.isChecked():
            out_vmd = self.le_vmd_output_path.text().strip()
            if not out_vmd:
                self._update_default_vmd_output_path()
                out_vmd = self.le_vmd_output_path.text().strip()
            out_dir = os.path.dirname(out_vmd)
            if out_dir:
                try:
                    os.makedirs(out_dir, exist_ok=True)
                except Exception:
                    pass

        target_model = self.cbb_stream_target_model.currentData() or None

        try:
            from ..converters import physics_stream
        except Exception:
            try:
                from converters import physics_stream
            except Exception:
                import physics_stream

        try:
            from ..converters import vmdpaimaya
        except Exception:
            try:
                from converters import vmdpaimaya
            except Exception:
                import vmdpaimaya

        substep = self.cbb_stream_substep.currentData() if hasattr(self, 'cbb_stream_substep') else 120
        bullet_ver = "2.83.7" if hasattr(self, 'rb_stream_bullet_283') and self.rb_stream_bullet_283.isChecked() else "2.75"

        models = []
        try:
            models = vmdpaimaya.get_available_mmd_models()
        except Exception:
            pass

        # 複数モデル順次ベイクの自動判定 (自動検出時に複数モデルが存在する場合)
        if not target_model and len(models) > 1:
            log_dialog = ExecutionLogDialog(
                self.parent_window or self,
                title="リアルタイム複数モデル順次物理ベイク実行ログ (追突防止・個別実行)",
                show_cancel=True
            )

            def run_multi_task():
                total = len(models)
                log_dialog.append_log("--- リアルタイム複数モデル順次物理ベイク開始 ---\n")
                log_dialog.append_log(f"自動検出: {total} 体のモデルが見つかりました。\n")
                log_dialog.append_log("剛体の追突や反発・吹き飛びを防ぐため、1体ずつ順番に独立してビューアを起動してベイクします。\n\n")

                for idx, (m_node, m_label) in enumerate(models, start=1):
                    if log_dialog.check_cancelled():
                        log_dialog.append_log("\n[中断] ユーザーによりベイクが中断されました。\n")
                        break

                    log_dialog.append_log("==================================================\n")
                    log_dialog.append_log(f"[{idx}/{total}] モデル物理ベイク開始: {m_label}\n")
                    log_dialog.append_log("==================================================\n")

                    # モデル固有のPMXパスを取得 (保存されている場合は優先)
                    model_pmx = pmx_path
                    if mc.attributeQuery('mmdModelPath', node=m_node, exists=True):
                        saved_path = mc.getAttr(f"{m_node}.mmdModelPath")
                        if saved_path and os.path.exists(saved_path):
                            model_pmx = saved_path

                    # モデルごとのVMD出力パス
                    model_out_vmd = out_vmd
                    if out_vmd and str(out_vmd).lower() != "none":
                        base_vmd, vmd_ext = os.path.splitext(out_vmd)
                        safe_label = safe_node_name(m_label.split(' ')[0])
                        model_out_vmd = f"{base_vmd}_{safe_label}{vmd_ext}"

                    physics_stream.stream_bake_physics(
                        pmx_path=model_pmx,
                        vmd_path=vmd_path,
                        target_model=m_node,
                        scale=scale,
                        lookahead=lookahead,
                        warmup=warmup,
                        out_vmd=model_out_vmd,
                        frame_offset=frame_offset,
                        start_frame=start_frame,
                        end_frame=end_frame,
                        substep=substep,
                        bullet_version=bullet_ver,
                        log_dialog=log_dialog
                    )
                    log_dialog.append_log(f"[{idx}/{total}] 完了: {m_label}\n\n")

                restore_viewport_lighting()

            success = log_dialog.run_task(run_multi_task)
            if success and not log_dialog.is_cancelled:
                self._hide_helper_nodes_after_bake()
                self._check_scene_import_status()
                mc.inViewMessage(
                    amg='<span style="color:#2ecc71;">MMD Tools for Maya:</span> 複数モデルのリアルタイム物理ベイクが完了しました。',
                    pos='topCenter',
                    fade=True
                )
            return

        # 単一モデルベイク（モデル1体、または個別モデル指定時）
        single_pmx = pmx_path
        single_target = target_model or None
        if not single_target and len(models) == 1:
            single_target = models[0][0]
        if single_target and mc.attributeQuery('mmdModelPath', node=single_target, exists=True):
            saved_path = mc.getAttr(f"{single_target}.mmdModelPath")
            if saved_path and os.path.exists(saved_path):
                single_pmx = saved_path

        log_dialog = ExecutionLogDialog(
            self.parent_window or self,
            title="リアルタイム物理ベイク実行ログ (新3D物理ビューア連携)",
            show_cancel=True
        )

        def run_task():
            physics_stream.stream_bake_physics(
                pmx_path=single_pmx,
                vmd_path=vmd_path,
                target_model=single_target,
                scale=scale,
                lookahead=lookahead,
                warmup=warmup,
                out_vmd=out_vmd,
                frame_offset=frame_offset,
                start_frame=start_frame,
                end_frame=end_frame,
                substep=substep,
                bullet_version=bullet_ver,
                log_dialog=log_dialog
            )
            restore_viewport_lighting()

        success = log_dialog.run_task(run_task)
        if success and not log_dialog.is_cancelled:
            self._hide_helper_nodes_after_bake()
            self._check_scene_import_status()
            mc.inViewMessage(
                amg='<span style="color:#2ecc71;">MMD Tools for Maya:</span> リアルタイム物理ベイクが完了しました。',
                pos='topCenter',
                fade=True
            )

    def _hide_helper_nodes_after_bake(self):
        """物理ベイク完了後に補助ノード（*_RigidBody_Joint_Visualizers、カメラビューコントローラ、全ての親、*_master等）を非表示化"""
        # 剛体・ジョイント可視化グループの非表示化
        vis_patterns = [
            "*_RigidBody_Joint_Visualizers*",
            "*_RigidBody_Visualizers*",
            "*_Joint_Visualizers*",
            "MMD_RigidBody_Joint_Visualizers*",
            "MMD_RigidBody_Visualizers*",
            "MMD_Joint_Visualizers*"
        ]
        for pat in vis_patterns:
            for v_node in mc.ls(pat, type=["transform", "joint"]) or []:
                try:
                    mc.setAttr(f"{v_node}.visibility", False)
                except Exception:
                    pass

        # 補助ノード非表示チェックボックスがOFFの場合はここで終了
        if hasattr(self, 'cb_stream_hide_helpers') and not self.cb_stream_hide_helpers.isChecked():
            restore_viewport_lighting()
            return

        target_names = ["Apose_view_cnt", "Apose_subetenoya"]
        for name in target_names:
            if mc.objExists(name):
                try:
                    mc.setAttr(f"{name}.visibility", False)
                except Exception:
                    pass

        # ワイルドカード検索でマッチする補助ノード（カメラ、全ての親、*_master）も非表示化
        for pattern in ["*view_cnt*", "*subetenoya*", "*_master*"]:
            matched = mc.ls(pattern, type=["transform", "joint"]) or []
            for m in matched:
                m_lower = m.lower()
                if any(ex in m_lower for ex in ["light", "camera", "aim"]):
                    continue
                try:
                    mc.setAttr(f"{m}.visibility", False)
                except Exception:
                    pass

        restore_viewport_lighting()

    def _update_default_paths(self, pmx_path):
        """PMXパス設定時の補助処理"""
        self._update_default_vmd_output_path()

    def _browse_pmx(self):
        """PMXファイル選択ダイアログ"""
        path, _ = QFileDialog.getOpenFileName(
            self, "PMXモデルファイルを選択", "", "PMXファイル (*.pmx);;全てのファイル (*.*)"
        )
        if path:
            self.le_pmx_path.setText(path)
            self._update_default_paths(path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """ドラッグ侵入時のファイル拡張子確認"""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                ext = os.path.splitext(url.toLocalFile())[1].lower()
                if ext in [".pmx", ".vmd"]:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        """ドロップ時のファイルパス反映"""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".pmx":
                self.le_pmx_path.setText(file_path)
                self._update_default_paths(file_path)
                mc.inViewMessage(
                    amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> PMXモデルを設定しました: {os.path.basename(file_path)}',
                    pos='topCenter',
                    fade=True
                )
                event.acceptProposedAction()
                return
            elif ext == ".vmd":
                self.le_vmd_source_path.setText(file_path)
                mc.inViewMessage(
                    amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> ベイク元VMDを設定しました: {os.path.basename(file_path)}',
                    pos='topCenter',
                    fade=True
                )
                event.acceptProposedAction()
                return
        event.ignore()

# ==============================================================================
# MMD削除・クリーンアップタブ
# ==============================================================================
class CleanupTabWidget(QWidget):
    """シーン内のMMD要素の一括削除を行うクリーンアップタブ"""
    def __init__(self, parent=None):
        super(CleanupTabWidget, self).__init__(parent)
        self.parent_window = parent
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 14, 14, 14)

        # 対象モデル指定
        target_box = QGroupBox("対象モデルの選択")
        target_layout = QVBoxLayout(target_box)

        h_model = QHBoxLayout()
        h_model.addWidget(QLabel("削除対象モデル:"))
        self.cbb_target_model = QComboBox()
        self.btn_refresh = QPushButton("更新")
        self.btn_refresh.setFixedWidth(80)
        self.btn_refresh.clicked.connect(self._refresh_models)
        h_model.addWidget(self.cbb_target_model)
        h_model.addWidget(self.btn_refresh)
        target_layout.addLayout(h_model)

        lbl_target_info = QLabel("※「シーン内の全MMDモデル / 自動検出」を選択すると、シーン内に存在するすべてのMMDモデル・リグが対象となります。")
        lbl_target_info.setStyleSheet("color: #999; font-size: 13px; margin-top: 4px;")
        target_layout.addWidget(lbl_target_info)
        layout.addWidget(target_box)

        layout.addStretch()

        # 実行アクション
        act_box = QGroupBox("クリーンアップ実行")
        act_layout = QVBoxLayout(act_box)
        act_layout.setSpacing(12)

        # 全削除ボタン
        self.btn_delete_all = QPushButton("全削除 (MMDモデル・関連ノード一括削除)")
        self.btn_delete_all.setFixedHeight(50)
        self.btn_delete_all.setStyleSheet(
            "QPushButton { background-color: #5d2525; color: #ffcccc; border: 1px solid #853333; border-radius: 4px; font-weight: bold; font-size: 15px; }"
            "QPushButton:hover { background-color: #782e2e; color: #ffffff; border-color: #ba4444; }"
            "QPushButton:pressed { background-color: #401818; }"
        )
        self.btn_delete_all.clicked.connect(self._execute_delete_all)
        act_layout.addWidget(self.btn_delete_all)

        lbl_act_info = QLabel("※選択した対象モデル（またはシーン内の全MMDモデル）、付随するスケルトン、IK、カメラ、ライト、地面影、および未使用マテリアルを一括で消去します。")
        lbl_act_info.setStyleSheet("color: #aaa; font-size: 13px; line-height: 1.5;")
        act_layout.addWidget(lbl_act_info)

        layout.addWidget(act_box)

        self._refresh_models()

    def _refresh_models(self):
        self.cbb_target_model.clear()
        self.cbb_target_model.addItem("シーン内の全MMDモデル / 自動検出", None)
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for node_name, label in models:
                self.cbb_target_model.addItem(label, node_name)
        except Exception:
            pass

    def _execute_delete_all(self):
        target_model = self.cbb_target_model.currentData()
        target_label = self.cbb_target_model.currentText()

        msg = f"対象 ({target_label}) および関連するMMD要素（モデル・スケルトン・カメラ・ライト・地面影・マテリアル等）を一括削除しますか？\n\n※この操作は取り消せません。"

        res = QMessageBox.question(
            self,
            "MMD全削除の確認",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return

        try:
            # 子ノード削除前に親グループ（統合グループ *_grp）を事前検出・キャッシュ
            pre_cached_groups = []
            if target_model and mc.objExists(target_model):
                parents = mc.listRelatives(target_model, parent=True, fullPath=False) or []
                for p in parents:
                    if p.endswith("_grp") or mc.attributeQuery("isMmdGroup", node=p, exists=True):
                        pre_cached_groups.append(p)
            else:
                for m_item in mc.ls("*.mmdModelRoot", "*.MMD_model", objectsOnly=True) or []:
                    if mc.objExists(m_item):
                        parents = mc.listRelatives(m_item, parent=True, fullPath=False) or []
                        for p in parents:
                            if (p.endswith("_grp") or mc.attributeQuery("isMmdGroup", node=p, exists=True)) and p not in pre_cached_groups:
                                pre_cached_groups.append(p)

            del_cnt = vmdpaimaya.delete_mmd_scene_elements(
                target_model_node=target_model,
                delete_lights=True,
                delete_cameras=True,
                delete_audio=True,
                delete_unused_nodes=True
            )

            # 物理可視化ノードおよびBulletリグ、統合グループの一括クリーンアップ
            phys_nodes_to_delete = list(pre_cached_groups)
            if target_model:
                # 対象モデル個別指定時: 当該モデルの物理グループおよび関連ノード
                clean_target = re.sub(r'[^a-zA-Z0-9_]', '_', target_model)
                candidates = [
                    f"{target_model}_RigidBody_Joint_Visualizers",
                    f"{clean_target}_RigidBody_Joint_Visualizers",
                    f"{target_model}_RigidBody_Visualizers",
                    f"{target_model}_Joint_Visualizers",
                    f"{target_model}_Bullet_Physics_Rig",
                ]
                for cand in candidates:
                    for n in mc.ls(cand, f"*{cand}*", type="transform") or []:
                        if mc.objExists(n) and n not in phys_nodes_to_delete:
                            phys_nodes_to_delete.append(n)
                # モデル固有プレフィックスの剛体・Jointノード
                for p_item in mc.ls(f"{target_model}_rb_*", f"{target_model}_joint_*", f"{clean_target}_rb_*", f"{clean_target}_joint_*", type="transform") or []:
                    if mc.objExists(p_item) and p_item not in phys_nodes_to_delete:
                        phys_nodes_to_delete.append(p_item)
                # 複数インポート時の統合グループおよびアンカーロケーター
                for grp_cand in mc.ls(f"{target_model}_grp", f"{clean_target}_grp", f"*{target_model}*_grp", f"*{clean_target}*_grp", f"anchor_*{target_model}*", f"anchor_*{clean_target}*", type="transform") or []:
                    if mc.objExists(grp_cand) and grp_cand not in phys_nodes_to_delete:
                        phys_nodes_to_delete.append(grp_cand)
            else:
                # 全削除時: シーン内の全物理可視化グループ、Bulletリグ、および剛体・Jointノード
                all_phys_patterns = [
                    "*_RigidBody_Joint_Visualizers", "*_RigidBody_Visualizers", "*_Joint_Visualizers",
                    "MMD_RigidBody_Joint_Visualizers", "MMD_RigidBody_Visualizers", "MMD_Joint_Visualizers",
                    "*_Bullet_Physics_Rig", "MMD_Bullet_Physics_Rig",
                    "*_BulletSolver", "MMD_BulletSolver",
                    "*_rb_*", "*_joint_*", "rb_vis_*", "joint_vis_*",
                    "anchor_*"
                ]
                for pat in all_phys_patterns:
                    for n in mc.ls(pat, type="transform") or []:
                        if mc.objExists(n) and n not in phys_nodes_to_delete:
                            phys_nodes_to_delete.append(n)

                # MMDモデル統合グループ (*_grp) の探索・クリーンアップ
                for grp in mc.ls("*_grp", type="transform") or []:
                    children = mc.listRelatives(grp, allDescendents=True) or []
                    has_mmd_attr = mc.attributeQuery("isMmdGroup", node=grp, exists=True) or mc.attributeQuery("mmdModelRoot", node=grp, exists=True)
                    has_mmd_children = any("RigidBody" in c or "joint" in c or "ikHandle" in c or "master" in c or "view_cnt" in c for c in children)
                    is_empty_grp = (len(children) == 0)
                    if (has_mmd_attr or has_mmd_children or is_empty_grp) and mc.objExists(grp) and grp not in phys_nodes_to_delete:
                        phys_nodes_to_delete.append(grp)

            for phys_item in phys_nodes_to_delete:
                if mc.objExists(phys_item):
                    try:
                        mc.delete(phys_item)
                        print(f"[MMD Tools for Maya] 関連ノード '{phys_item}' を削除しました。")
                        del_cnt += 1
                    except Exception:
                        pass

            # 地面影ノードの一括クリーンアップ
            for shadow_node in ["mmd_ground_shadow_grp", "mmd_ground_shadow_plane", "mmd_ground_shadow_shd", "mmd_ground_shadow_shdSG"]:
                for s_item in mc.ls(shadow_node) or []:
                    if mc.objExists(s_item):
                        try:
                            mc.delete(s_item)
                            print(f"[MMD Tools for Maya] 地面影ノード '{s_item}' を削除しました。")
                        except Exception:
                            pass

            self._refresh_models()
            mc.inViewMessage(
                amg=f'<span style="color:#ffaa55;">MMD Tools for Maya:</span> MMD全削除を完了しました ({del_cnt} 個ノード削除)。',
                pos='topCenter',
                fade=True
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"MMD全削除中にエラーが発生しました:\n{e}")

# ==============================================================================
# プラグイン管理タブ (各種プラグインの状態確認・再読み込み)
# ==============================================================================
class PluginTabWidget(QWidget):
    """MMD Tools for Maya で使用する各種 C++ / 物理演算 / シェーダープラグインの管理タブ"""
    def __init__(self, parent=None):
        super(PluginTabWidget, self).__init__(parent)
        self.parent_window = parent
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 14, 14, 14)

        # モーション高速化プラグイン
        motion_box = QGroupBox("C++ モーション高速化プラグイン (mmd_motion.mll)")
        motion_layout = QVBoxLayout(motion_box)
        motion_layout.setSpacing(8)

        h_motion = QHBoxLayout()
        self.lbl_motion_status = QLabel()
        self.btn_reload_motion = QPushButton("プラグイン再読み込み")
        self.btn_reload_motion.setFixedWidth(160)
        self.btn_reload_motion.clicked.connect(self._reload_motion_plugin)
        h_motion.addWidget(self.lbl_motion_status)
        h_motion.addStretch()
        h_motion.addWidget(self.btn_reload_motion)
        motion_layout.addLayout(h_motion)

        lbl_motion_info = QLabel("・Maya C++ APIによる超高速キーフレーム書き込みノード (mmdFastBakeBone) です。")
        lbl_motion_info.setStyleSheet("color: #999; font-size: 12px;")
        motion_layout.addWidget(lbl_motion_info)
        layout.addWidget(motion_box)

        # 物理演算プラグイン (Bullet / XPBD)
        physics_box = QGroupBox("物理演算プラグイン (Bullet / XPBD)")
        physics_layout = QVBoxLayout(physics_box)
        physics_layout.setSpacing(8)

        h_bullet = QHBoxLayout()
        self.lbl_bullet_status = QLabel()
        h_bullet.addWidget(self.lbl_bullet_status)
        h_bullet.addStretch()
        physics_layout.addLayout(h_bullet)

        h_xpbd = QHBoxLayout()
        self.lbl_xpbd_status = QLabel()
        h_xpbd.addWidget(self.lbl_xpbd_status)
        h_xpbd.addStretch()
        physics_layout.addLayout(h_xpbd)

        h_viewer = QHBoxLayout()
        self.lbl_viewer_status = QLabel()
        h_viewer.addWidget(self.lbl_viewer_status)
        h_viewer.addStretch()
        physics_layout.addLayout(h_viewer)

        h_phys_action = QHBoxLayout()
        h_phys_action.addStretch()
        self.btn_reload_physics = QPushButton("物理プラグイン再読み込み")
        self.btn_reload_physics.setFixedWidth(180)
        self.btn_reload_physics.clicked.connect(self._reload_physics_plugins)
        h_phys_action.addWidget(self.btn_reload_physics)
        physics_layout.addLayout(h_phys_action)

        lbl_phys_info = QLabel(
            "・Bullet Physics (mmd_bullet.dll): 本家MMD準拠の剛体シミュレーションを機能です。\n"
            "・XPBD Physics (mmd_xpbd.dll): 位置ベース物理による高速かつ安定したソルバーを機能です。\n"
            "・物理演算ベイクプレビューア (PhysicsSimulationBakeViewer.exe): WPF3Dによるリアルタイム物理シミュレーションで柔らかくしなやかな剛体挙動とMayaへの同期ベイク機能です。"
        )
        lbl_phys_info.setStyleSheet("color: #999; font-size: 12px; line-height: 1.4;")
        physics_layout.addWidget(lbl_phys_info)
        layout.addWidget(physics_box)

        # MMDマテリアルプラグイン
        mat_box = QGroupBox("MMDマテリアルプラグイン (mmd_material.mll / mmd_toon_shader.mll)")
        mat_layout = QVBoxLayout(mat_box)
        mat_layout.setSpacing(8)

        h_mat = QHBoxLayout()
        self.lbl_mat_status = QLabel()
        self.btn_reload_mat = QPushButton("プラグイン再読み込み")
        self.btn_reload_mat.setFixedWidth(160)
        self.btn_reload_mat.clicked.connect(self._reload_material_plugin)
        h_mat.addWidget(self.lbl_mat_status)
        h_mat.addStretch()
        h_mat.addWidget(self.btn_reload_mat)
        mat_layout.addLayout(h_mat)

        lbl_mat_info = QLabel("・Viewport 2.0上でMMD準拠のToon陰影・セルフシャドウ・スフィアマップをリアルタイム描画するマテリアルプラグインです。")
        lbl_mat_info.setStyleSheet("color: #999; font-size: 12px;")
        mat_layout.addWidget(lbl_mat_info)
        layout.addWidget(mat_box)

        # 全プラグイン一括再読み込み
        all_box = QGroupBox("全プラグイン一括管理")
        all_layout = QVBoxLayout(all_box)
        all_layout.setSpacing(8)
        self.btn_reload_all = QPushButton("すべてのプラグインを一括再読み込み")
        self.btn_reload_all.setFixedHeight(38)
        self.btn_reload_all.setStyleSheet(
            "QPushButton { background-color: #2b4c6f; color: #ffffff; border-radius: 4px; font-weight: bold; font-size: 13px; }"
            "QPushButton:hover { background-color: #38618d; }"
        )
        self.btn_reload_all.clicked.connect(self._reload_all_plugins)
        all_layout.addWidget(self.btn_reload_all)

        self.btn_enable_autoload_all = QPushButton("すべてのプラグインの自動ロードを設定 (Auto Load ON)")
        self.btn_enable_autoload_all.setFixedHeight(34)
        self.btn_enable_autoload_all.setStyleSheet(
            "QPushButton { background-color: #2d5a3f; color: #ffffff; border-radius: 4px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background-color: #3b7552; }"
        )
        self.btn_enable_autoload_all.clicked.connect(self._enable_all_autoload)
        all_layout.addWidget(self.btn_enable_autoload_all)
        layout.addWidget(all_box)

        layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        self.refresh_all_status()

    def refresh_all_status(self):
        """全プラグインの状態表示を最新化"""
        self._check_motion_status()
        self._check_physics_status()
        self._check_material_status()

    def _check_motion_status(self):
        loaded = False
        try:
            if hasattr(mc, "mmdFastBakeBone"):
                loaded = True
            elif hasattr(mel, "eval") and mel.eval('exists "mmdFastBakeBone"') == 1:
                loaded = True
            elif any("mmd_motion" in p.lower() for p in (mc.pluginInfo(query=True, listPlugins=True) or [])):
                loaded = True
            elif mc.pluginInfo("mmd_motion.mll", query=True, loaded=True) or mc.pluginInfo("mmd_motion", query=True, loaded=True):
                loaded = True
        except Exception:
            pass

        motion_autoload = False
        if loaded:
            try:
                motion_autoload = mc.pluginInfo("mmd_motion.mll", query=True, autoload=True) or mc.pluginInfo("mmd_motion", query=True, autoload=True)
            except Exception:
                motion_autoload = False
            if not motion_autoload:
                try:
                    mc.pluginInfo("mmd_motion.mll", edit=True, autoload=True)
                    motion_autoload = True
                except Exception:
                    try:
                        mc.pluginInfo("mmd_motion", edit=True, autoload=True)
                        motion_autoload = True
                    except Exception:
                        pass

        if loaded:
            auto_str = " (自動ロード: 有効)" if motion_autoload else ""
            self.lbl_motion_status.setText(f"<span style='color:#55ff77; font-weight:bold;'>● プラグイン読み込み済み (mmd_motion.mll{auto_str})</span>")
        else:
            self.lbl_motion_status.setText("<span style='color:#ff7777; font-weight:bold;'>○ プラグイン未読み込み (mmd_motion.mll)</span>")

    def _check_physics_status(self):
        # Bullet
        bullet_ok = False
        try:
            plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            dll_path = os.path.join(plugin_root, "bullet_engine", "bin", "mmd_bullet.dll")
            bullet_ok = os.path.exists(dll_path)
        except Exception:
            pass

        if bullet_ok:
            self.lbl_bullet_status.setText("<span style='color:#55ff77; font-weight:bold;'>● Bullet 物理エンジン: 利用可能 (mmd_bullet.dll)</span>")
        else:
            self.lbl_bullet_status.setText("<span style='color:#ffaa55; font-weight:bold;'>△ Bullet 物理エンジン: 未検出 (mmd_bullet.dll)</span>")

        # XPBD
        xpbd_ok = False
        try:
            plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            dll_path = os.path.join(plugin_root, "cpp_engine", "bin", "mmd_xpbd.dll")
            xpbd_ok = os.path.exists(dll_path)
        except Exception:
            pass

        if xpbd_ok:
            self.lbl_xpbd_status.setText("<span style='color:#55ff77; font-weight:bold;'>● XPBD 物理エンジン: 利用可能 (mmd_xpbd.dll)</span>")
        else:
            self.lbl_xpbd_status.setText("<span style='color:#ffaa55; font-weight:bold;'>△ XPBD 物理エンジン: 未検出 (mmd_xpbd.dll)</span>")

        # 新3D物理ビューア (PhysicsSimulationBakeViewer.exe)
        viewer_ok = False
        try:
            from ..converters import physics_stream
            viewer_exe = physics_stream.get_viewer_executable_path()
            viewer_ok = os.path.exists(viewer_exe)
        except Exception:
            try:
                from converters import physics_stream
                viewer_exe = physics_stream.get_viewer_executable_path()
                viewer_ok = os.path.exists(viewer_exe)
            except Exception:
                pass

        if viewer_ok:
            self.lbl_viewer_status.setText("<span style='color:#55ff77; font-weight:bold;'>● 新3D物理ビューア: 利用可能 (PhysicsSimulationBakeViewer.exe / .NET 8 WPF)</span>")
        else:
            self.lbl_viewer_status.setText("<span style='color:#ffaa55; font-weight:bold;'>△ 新3D物理ビューア: 未検出 (physics_bake_cs をビルドしてください)</span>")

    def _check_material_status(self):
        mat_loaded = False
        toon_loaded = False
        try:
            if "mmdMaterial" in (mc.allNodeTypes() or []):
                mat_loaded = True
            elif mc.pluginInfo("mmd_material.mll", query=True, loaded=True) or mc.pluginInfo("mmd_material", query=True, loaded=True):
                mat_loaded = True

            if "mmdToonShader" in (mc.allNodeTypes() or []):
                toon_loaded = True
            elif mc.pluginInfo("mmd_toon_shader.mll", query=True, loaded=True) or mc.pluginInfo("mmd_toon_shader", query=True, loaded=True):
                toon_loaded = True
        except Exception:
            pass

        mat_autoload = False
        toon_autoload = False
        if mat_loaded:
            try:
                mat_autoload = mc.pluginInfo("mmd_material.mll", query=True, autoload=True) or mc.pluginInfo("mmd_material", query=True, autoload=True)
            except Exception:
                mat_autoload = False
            if not mat_autoload:
                try:
                    mc.pluginInfo("mmd_material.mll", edit=True, autoload=True)
                    mat_autoload = True
                except Exception:
                    try:
                        mc.pluginInfo("mmd_material", edit=True, autoload=True)
                        mat_autoload = True
                    except Exception:
                        pass

        if toon_loaded:
            try:
                toon_autoload = mc.pluginInfo("mmd_toon_shader.mll", query=True, autoload=True) or mc.pluginInfo("mmd_toon_shader", query=True, autoload=True)
            except Exception:
                toon_autoload = False
            if not toon_autoload:
                try:
                    mc.pluginInfo("mmd_toon_shader.mll", edit=True, autoload=True)
                    toon_autoload = True
                except Exception:
                    try:
                        mc.pluginInfo("mmd_toon_shader", edit=True, autoload=True)
                        toon_autoload = True
                    except Exception:
                        pass

        status_parts = []
        if mat_loaded:
            auto_str = " (自動ロード: 有効)" if mat_autoload else ""
            status_parts.append(f"<span style='color:#55ff77; font-weight:bold;'>● mmd_material.mll ロード済み{auto_str}</span>")
        else:
            status_parts.append("<span style='color:#ff7777; font-weight:bold;'>○ mmd_material.mll 未ロード</span>")

        if toon_loaded:
            auto_str = " (自動ロード: 有効)" if toon_autoload else ""
            status_parts.append(f"<span style='color:#55ff77; font-weight:bold;'>● mmd_toon_shader.mll ロード済み{auto_str}</span>")
        else:
            status_parts.append("<span style='color:#ff7777; font-weight:bold;'>○ mmd_toon_shader.mll 未ロード</span>")

        self.lbl_mat_status.setText("<br>".join(status_parts))

    def _reload_motion_plugin(self):
        try:
            from ..bullet_engine import bullet_maya_bridge
        except Exception:
            try:
                from bullet_engine import bullet_maya_bridge
            except Exception:
                bullet_maya_bridge = None
        if bullet_maya_bridge:
            bridge = bullet_maya_bridge.BulletMayaBridge.__new__(bullet_maya_bridge.BulletMayaBridge)
            success = bridge._ensure_motion_plugin_loaded()
            if success:
                try:
                    mc.pluginInfo("mmd_motion", edit=True, autoload=True)
                except Exception:
                    pass
                try:
                    mc.pluginInfo("mmd_motion.mll", edit=True, autoload=True)
                except Exception:
                    pass
            self._check_motion_status()
            if success:
                QMessageBox.information(self, "プラグイン", "MMDモーションプラグイン (mmd_motion.mll) が正常にロードされ、自動ロードが設定されました。")
            else:
                QMessageBox.warning(self, "プラグイン", "MMDモーションプラグイン (mmd_motion.mll) のロードに失敗しました。")
        else:
            QMessageBox.warning(self, "エラー", "bullet_maya_bridge モジュールが見つかりません。")

    def _reload_physics_plugins(self):
        self._check_physics_status()
        QMessageBox.information(self, "物理プラグイン", "物理演算ライブラリ (Bullet / XPBD) の状態を更新しました。")

    def _ensure_toon_shader_loaded(self):
        """MMDトゥーンシェーダープラグイン (mmd_toon_shader.mll) のロードを保証し自動ロードを設定"""
        def _set_autoload(target):
            try:
                mc.pluginInfo(target, edit=True, autoload=True)
            except Exception:
                pass

        try:
            if mc.pluginInfo("mmd_toon_shader", query=True, loaded=True) or mc.pluginInfo("mmd_toon_shader.mll", query=True, loaded=True):
                _set_autoload("mmd_toon_shader")
                _set_autoload("mmd_toon_shader.mll")
                return True
        except Exception:
            pass

        try:
            mc.loadPlugin("mmd_toon_shader")
            _set_autoload("mmd_toon_shader")
            _set_autoload("mmd_toon_shader.mll")
            return True
        except Exception:
            pass

        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        maya_ver = mc.about(version=True).split()[0] if hasattr(mc, 'about') else '2025'
        candidate_paths = [
            os.path.join(plugin_root, "mmd_toon_plugin", "bin", maya_ver, "mmd_toon_shader.mll"),
            os.path.join(plugin_root, "mmd_toon_plugin", "bin", "2025", "mmd_toon_shader.mll"),
            os.path.join(plugin_root, "mmd_toon_plugin", "bin", "mmd_toon_shader.mll"),
        ]
        for mll_path in candidate_paths:
            if os.path.exists(mll_path):
                try:
                    mc.loadPlugin(mll_path)
                    _set_autoload(mll_path)
                    _set_autoload("mmd_toon_shader.mll")
                    _set_autoload("mmd_toon_shader")
                    return True
                except Exception:
                    pass
        return False

    def _reload_material_plugin(self):
        mat_success = False
        if mmd_material_setup:
            try:
                mat_success = mmd_material_setup.ensure_plugin_loaded()
                if mat_success:
                    try:
                        mc.pluginInfo("mmd_material", edit=True, autoload=True)
                    except Exception:
                        pass
                    try:
                        mc.pluginInfo("mmd_material.mll", edit=True, autoload=True)
                    except Exception:
                        pass
            except Exception:
                pass

        toon_success = self._ensure_toon_shader_loaded()

        self._check_material_status()

        if mat_success and toon_success:
            QMessageBox.information(self, "プラグイン", "MMDマテリアルプラグイン (mmd_material.mll / mmd_toon_shader.mll) が正常にロードされ、自動ロードが設定されました。")
        elif toon_success:
            QMessageBox.information(self, "プラグイン", "MMDトゥーンシェーダー (mmd_toon_shader.mll) が正常にロードされ、自動ロードが設定されました。")
        elif mat_success:
            QMessageBox.information(self, "プラグイン", "MMDマテリアル (mmd_material.mll) が正常にロードされ、自動ロードが設定されました。")
        else:
            QMessageBox.warning(self, "プラグイン", "マテリアルプラグインのロードに失敗しました。")

    def _enable_all_autoload(self):
        """全MMDプラグインの自動ロードフラグを設定"""
        target_plugins = [
            "mmd_toon_shader", "mmd_toon_shader.mll",
            "mmd_motion", "mmd_motion.mll",
            "mmd_material", "mmd_material.mll",
        ]
        count = 0
        for p in target_plugins:
            try:
                if mc.pluginInfo(p, query=True, loaded=True):
                    mc.pluginInfo(p, edit=True, autoload=True)
                    count += 1
            except Exception:
                pass
        self.refresh_all_status()
        QMessageBox.information(
            self,
            "自動ロード設定",
            "ロード済みの各プラグインに対して自動ロード (Auto Load) 設定を有効化しました。"
        )

    def _reload_all_plugins(self):
        try:
            from ..bullet_engine import bullet_maya_bridge
        except Exception:
            try:
                from bullet_engine import bullet_maya_bridge
            except Exception:
                bullet_maya_bridge = None
        if bullet_maya_bridge:
            bridge = bullet_maya_bridge.BulletMayaBridge.__new__(bullet_maya_bridge.BulletMayaBridge)
            bridge._ensure_motion_plugin_loaded()
            try:
                mc.pluginInfo("mmd_motion", edit=True, autoload=True)
            except Exception:
                pass

        if mmd_material_setup:
            try:
                mmd_material_setup.ensure_plugin_loaded()
                mc.pluginInfo("mmd_material", edit=True, autoload=True)
            except Exception:
                pass

        self._ensure_toon_shader_loaded()

        self.refresh_all_status()
        QMessageBox.information(self, "プラグイン一括再読み込み", "すべてのプラグインの再読み込みおよび自動ロード設定を完了しました。")

# ==============================================================================
# アクセサリ追従アタッチダイアログ
# ==============================================================================
class AccessoryAttachDialog(QDialog):
    """小物をMMDモデルのボーンへ追従アタッチ・デタッチする操作ダイアログ"""
    def __init__(self, parent=None):
        super(AccessoryAttachDialog, self).__init__(parent)
        self.setWindowTitle("MMD アクセサリ追従アタッチ (試験的機能)")
        self.resize(440, 340)
        self._init_ui()
        self._refresh_models()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 14, 14, 14)

        # アクセサリ対象オブジェクトグループ
        acc_box = QGroupBox("アクセサリオブジェクト")
        acc_layout = QHBoxLayout(acc_box)
        self.le_accessory = QLineEdit()
        self.le_accessory.setPlaceholderText("アクセサリのノード名（未選択時は選択から自動取得）")
        acc_layout.addWidget(self.le_accessory)

        self.btn_pick_sel = QPushButton("選択から取得")
        self.btn_pick_sel.setFixedWidth(90)
        self.btn_pick_sel.clicked.connect(self._pick_selection)
        acc_layout.addWidget(self.btn_pick_sel)
        layout.addWidget(acc_box)

        # アタッチ先モデル＆ボーン設定グループ
        target_box = QGroupBox("アタッチ先設定")
        target_layout = QVBoxLayout(target_box)
        target_layout.setSpacing(8)

        h_mod = QHBoxLayout()
        h_mod.addWidget(QLabel("対象モデル:"))
        self.cbb_target_model = QComboBox()
        h_mod.addWidget(self.cbb_target_model)
        self.btn_ref_model = QPushButton("更新")
        self.btn_ref_model.setFixedWidth(50)
        self.btn_ref_model.clicked.connect(self._refresh_models)
        h_mod.addWidget(self.btn_ref_model)
        target_layout.addLayout(h_mod)

        h_bone = QHBoxLayout()
        h_bone.addWidget(QLabel("追従先ボーン:"))
        self.cbb_bone = QComboBox()
        self.cbb_bone.addItems(["右手", "左手", "頭", "腰", "胸", "首", "右足", "左足", "センター", "全ての親", "カスタム入力..."])
        self.cbb_bone.currentIndexChanged.connect(self._on_bone_preset_changed)
        h_bone.addWidget(self.cbb_bone)
        target_layout.addLayout(h_bone)

        self.le_custom_bone = QLineEdit()
        self.le_custom_bone.setPlaceholderText("追従先ボーン名を入力 (例: 右人指３)")
        self.le_custom_bone.setEnabled(False)
        target_layout.addWidget(self.le_custom_bone)

        self.cb_maintain_offset = QCheckBox("現在の相対位置・角度を維持する (Maintain Offset)")
        self.cb_maintain_offset.setChecked(True)
        target_layout.addWidget(self.cb_maintain_offset)

        layout.addWidget(target_box)

        # アクションボタン
        h_actions = QHBoxLayout()
        self.btn_attach = QPushButton("ボーンに追従アタッチ")
        self.btn_attach.setProperty("class", "primary")
        self.btn_attach.setFixedHeight(36)
        self.btn_attach.clicked.connect(self._on_attach)
        h_actions.addWidget(self.btn_attach)

        self.btn_detach = QPushButton("アタッチを解除 (デタッチ)")
        self.btn_detach.setFixedHeight(36)
        self.btn_detach.clicked.connect(self._on_detach)
        h_actions.addWidget(self.btn_detach)

        layout.addLayout(h_actions)

        # 閉じるボタン
        h_close = QHBoxLayout()
        h_close.addStretch()
        btn_close = QPushButton("閉じる")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.close)
        h_close.addWidget(btn_close)
        layout.addLayout(h_close)

    def _on_bone_preset_changed(self, idx):
        is_custom = (self.cbb_bone.currentText() == "カスタム入力...")
        self.le_custom_bone.setEnabled(is_custom)

    def _pick_selection(self):
        sel = mc.ls(selection=True)
        if sel:
            self.le_accessory.setText(sel[0])

    def _refresh_models(self):
        self.cbb_target_model.clear()
        models = []
        for xform in mc.ls(type='transform') or []:
            if mc.attributeQuery('MMD_model', node=xform, exists=True):
                models.append(xform)
            elif mc.attributeQuery('MMD_Model_Root', node=xform, exists=True):
                models.append(xform)

        if not models:
            for j in mc.ls(type='joint') or []:
                if mc.attributeQuery('originalName', node=j, exists=True):
                    root_candidates = mc.ls(j, root=True) or [j]
                    if root_candidates[0] not in models:
                        models.append(root_candidates[0])

        for m in sorted(list(set(models))):
            self.cbb_target_model.addItem(m, m)

        if self.cbb_target_model.count() == 0:
            self.cbb_target_model.addItem("(シーン内ボーンから自動探索)", None)

    def _on_attach(self):
        acc = self.le_accessory.text().strip()
        if not acc:
            sel = mc.ls(selection=True)
            if sel:
                acc = sel[0]
                self.le_accessory.setText(acc)
            else:
                QMessageBox.warning(self, "未選択", "アタッチするアクセサリオブジェクトを指定または選択してください。")
                return

        target_model = self.cbb_target_model.currentData()
        bone_text = self.cbb_bone.currentText()
        if bone_text == "カスタム入力...":
            bone_name = self.le_custom_bone.text().strip()
            if not bone_name:
                QMessageBox.warning(self, "入力不足", "追従先ボーン名を入力してください。")
                return
        else:
            bone_name = bone_text

        maintain = self.cb_maintain_offset.isChecked()

        try:
            from ..converters import pmxpaimaya
        except Exception:
            from converters import pmxpaimaya

        try:
            res = pmxpaimaya.attach_accessory_to_bone(
                accessory_node=acc,
                target_model_node=target_model,
                target_bone_name=bone_name,
                maintain_offset=maintain
            )
            QMessageBox.information(
                self,
                "アタッチ完了",
                f"アクセサリ '{acc}' をボーン '{bone_name}' に追従接続しました。\n"
                f"・接続ボーン: {res['bone']}\n"
                f"・オフセット親グループ: {res['offset_group']}"
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"アタッチ処理中にエラーが発生しました:\n{e}")

    def _on_detach(self):
        acc = self.le_accessory.text().strip()
        if not acc:
            sel = mc.ls(selection=True)
            if sel:
                acc = sel[0]
                self.le_accessory.setText(acc)
            else:
                QMessageBox.warning(self, "未選択", "アタッチを解除するアクセサリオブジェクトを指定または選択してください。")
                return

        try:
            from ..converters import pmxpaimaya
        except Exception:
            from converters import pmxpaimaya

        try:
            success = pmxpaimaya.detach_accessory(acc)
            if success:
                QMessageBox.information(self, "解除完了", f"アクセサリ '{acc}' の追従コンストレイントを解除しました。")
            else:
                QMessageBox.warning(self, "解除失敗", f"アクセサリ '{acc}' が見つからないか、解除対象の接続がありません。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"解除処理中にエラーが発生しました:\n{e}")

# ==============================================================================
# 試験的機能 ダイアログ
# ==============================================================================
class ExperimentalFeaturesDialog(QDialog):
    """動作確認が不十分な機能や開発中の機能をまとめた試験的機能ウィンドウ"""
    def __init__(self, parent=None):
        super(ExperimentalFeaturesDialog, self).__init__(parent)
        self.parent_tab = parent
        self.setWindowTitle("試験的機能")
        self.resize(820, 780)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self._init_ui()
        self._refresh_vpd_models()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 小画面対応スクロールエリア
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(14)
        layout.setContentsMargins(10, 10, 10, 10)

        # 注意文表示ボックス
        notice_box = QGroupBox("試験的機能に関するご注意")
        notice_box.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; color: #ffaa00; border: 1px solid #7a581e; margin-top: 6px; padding: 12px; border-radius: 4px; background-color: #262016; }")
        notice_layout = QVBoxLayout(notice_box)
        notice_layout.setSpacing(6)
        lbl_notice_title = QLabel("【注意・未確認の試験的機能】")
        lbl_notice_title.setStyleSheet("color: #ffaa00; font-size: 15px; font-weight: bold;")
        notice_layout.addWidget(lbl_notice_title)

        lbl_notice = QLabel(
            "本ウィンドウに掲載されている機能は、開発中または正しく動作するか確認できていない試験的機能です。\n"
            "予期せぬ動作、エラー、フリーズなどが発生する可能性がありますのでご注意ください。"
        )
        lbl_notice.setWordWrap(True)
        lbl_notice.setStyleSheet("color: #ffd180; font-size: 13px; line-height: 1.4; font-weight: normal;")
        notice_layout.addWidget(lbl_notice)
        layout.addWidget(notice_box)

        # 《モデル操作グループ》
        oper_box = QGroupBox("モデル操作")
        oper_layout = QVBoxLayout(oper_box)
        oper_layout.setSpacing(10)

        # Maya → MMD (エクスポート) ボタン
        self.btn_open_export = QPushButton("Maya → MMD (エクスポート)")
        self.btn_open_export.setFixedHeight(42)
        self.btn_open_export.setToolTip("PMXモデル・VMDモーション・VPDポーズのエクスポート機能を別ウィンドウで表示します。")
        self.btn_open_export.setStyleSheet("QPushButton { background-color: #2e6b52; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3b8767; }")
        self.btn_open_export.clicked.connect(self._open_export_window)
        oper_layout.addWidget(self.btn_open_export)

        # HumanIK管理ボタン
        self.btn_hik_ui = QPushButton("HumanIK管理")
        self.btn_hik_ui.setFixedHeight(42)
        self.btn_hik_ui.setToolTip("HumanIK管理パネルを別ウィンドウで開き、キャラクター定義の作成やボーンマッピングを行います。")
        self.btn_hik_ui.setStyleSheet("QPushButton { background-color: #2e607a; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3b7696; }")
        self.btn_hik_ui.clicked.connect(self._open_hik_window)
        oper_layout.addWidget(self.btn_hik_ui)

        # アクセサリ追従アタッチボタン
        self.btn_accessory_attach = QPushButton("アクセサリ追従アタッチ (右手/左手/頭/腰) (試験的機能)")
        self.btn_accessory_attach.setFixedHeight(42)
        self.btn_accessory_attach.setToolTip("小物（.x / .pmx / 任意メッシュ）をMMDモデルのボーンへ追従アタッチ・デタッチするパネルを開きます。")
        self.btn_accessory_attach.setStyleSheet("QPushButton { background-color: #7b4a2e; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #965a38; }")
        self.btn_accessory_attach.clicked.connect(self._open_accessory_attach_window)
        oper_layout.addWidget(self.btn_accessory_attach)

        # VPDポーズデータ適用サブグループ
        pose_box = QGroupBox("MMD ポーズデータ (.vpd) 適用")
        pose_layout = QVBoxLayout(pose_box)
        pose_layout.setSpacing(8)

        h_pose_opt = QHBoxLayout()
        lbl_target_m = QLabel("対象モデル:")
        lbl_target_m.setStyleSheet("font-size: 13px;")
        h_pose_opt.addWidget(lbl_target_m)

        self.cbb_vpd_target_model = QComboBox()
        self.cbb_vpd_target_model.setFixedHeight(34)
        self.cbb_vpd_target_model.setStyleSheet("QComboBox { font-size: 13px; }")
        h_pose_opt.addWidget(self.cbb_vpd_target_model, 1)

        self.btn_vpd_refresh_model = QPushButton("更新")
        self.btn_vpd_refresh_model.setFixedWidth(75)
        self.btn_vpd_refresh_model.setFixedHeight(34)
        self.btn_vpd_refresh_model.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 13px; font-weight: bold; }")
        self.btn_vpd_refresh_model.clicked.connect(self._refresh_vpd_models)
        h_pose_opt.addWidget(self.btn_vpd_refresh_model)

        lbl_scale = QLabel("スケール:")
        lbl_scale.setStyleSheet("font-size: 13px;")
        h_pose_opt.addWidget(lbl_scale)

        self.le_vpd_scale = QLineEdit("8.0")
        self.le_vpd_scale.setFixedWidth(60)
        self.le_vpd_scale.setFixedHeight(34)
        self.le_vpd_scale.setStyleSheet("QLineEdit { font-size: 13px; padding: 2px 4px; }")
        h_pose_opt.addWidget(self.le_vpd_scale)
        pose_layout.addLayout(h_pose_opt)

        self.btn_import_vpd = QPushButton("VPDポーズを適用 (インポート)")
        self.btn_import_vpd.setFixedHeight(38)
        self.btn_import_vpd.setStyleSheet("QPushButton { background-color: #2b5b84; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3872a4; }")
        self.btn_import_vpd.setToolTip("MMDのポーズデータ (.vpd) を読み込み、現在フレームのモデルへ適用します。")
        self.btn_import_vpd.clicked.connect(self._on_import_vpd)
        pose_layout.addWidget(self.btn_import_vpd)

        self.cb_vpd_keyframe = QCheckBox("ポーズ適用時にカレントフレームへキーフレームを登録する")
        self.cb_vpd_keyframe.setChecked(True)
        pose_layout.addWidget(self.cb_vpd_keyframe)

        lbl_vpd_info = QLabel("※MMD標準のポーズファイル (.vpd) を読み込み、シーン内のモデルにポーズを反映します。")
        lbl_vpd_info.setStyleSheet("color: #999; font-size: 12px;")
        pose_layout.addWidget(lbl_vpd_info)

        oper_layout.addWidget(pose_box)
        layout.addWidget(oper_box)

        # 《モデル解析グループ》
        analysis_box = QGroupBox("モデル解析")
        analysis_layout = QVBoxLayout(analysis_box)
        analysis_layout.setSpacing(10)

        lbl_radio_guide = QLabel("実行する解析・エクスポート機能を選択してください:")
        lbl_radio_guide.setStyleSheet("color: #bbb; font-size: 12px;")
        analysis_layout.addWidget(lbl_radio_guide)

        # ラジオボタンによる機能統合
        self.rb_analyze_pmx = QRadioButton("PMXモデルチェック・データ一括保存 (材質/ボーン/モーフ/剛体/Joint)")
        self.rb_analyze_pmx.setStyleSheet("QRadioButton { font-size: 13px; color: #e0e0e0; font-weight: bold; }")
        self.rb_analyze_pmx.setChecked(True)
        self.rb_analyze_pmx.toggled.connect(self._on_analysis_option_changed)
        analysis_layout.addWidget(self.rb_analyze_pmx)

        self.rb_export_bones = QRadioButton("ボーン状態JSONエクスポート (指定フレーム範囲)")
        self.rb_export_bones.setStyleSheet("QRadioButton { font-size: 13px; color: #e0e0e0; font-weight: bold; }")
        analysis_layout.addWidget(self.rb_export_bones)

        # 統合実行ボタン
        self.btn_execute_analysis = QPushButton("PMXモデルチェック・データ一括保存を実行")
        self.btn_execute_analysis.setFixedHeight(42)
        self.btn_execute_analysis.setToolTip("インポートタブで指定されたPMXの構成要素（材質・ボーン・モーフ・剛体・Joint）をJSONに一括保存し、未登録漢字のユーザー辞書登録を行います。")
        self.btn_execute_analysis.setStyleSheet("QPushButton { background-color: #2b5b84; color: #fff; font-weight: bold; font-size: 13px; border-radius: 4px; } QPushButton:hover { background-color: #3872a4; }")
        self.btn_execute_analysis.clicked.connect(self._on_execute_analysis_clicked)
        analysis_layout.addWidget(self.btn_execute_analysis)

        # 互換性参照用
        self.btn_analyze_model = self.btn_execute_analysis
        self.btn_export_bone_states = self.btn_execute_analysis

        layout.addWidget(analysis_box)

        # 《外部ツールグループ》
        viewer_box = QGroupBox("外部ツール (3D物理ビューア)")
        viewer_layout = QVBoxLayout(viewer_box)
        viewer_layout.setSpacing(8)

        # MMD Physics Brige - 3D物理ビューア起動ボタン (試験的機能)
        self.btn_launch_viewer = QPushButton("MMD Physics Brige - 3D物理ビューア(試験的機能)")
        self.btn_launch_viewer.setFixedHeight(42)
        self.btn_launch_viewer.setToolTip("physics_bridge_cs フォルダー内の MMD Physics Brige を単体起動します。Norton CyberCapture等の誤検知を回避する正規ホスト起動に対応しています。")
        self.btn_launch_viewer.setStyleSheet("QPushButton { background-color: #5c3b7a; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #734a99; }")
        self.btn_launch_viewer.clicked.connect(self._launch_standalone_viewer)
        viewer_layout.addWidget(self.btn_launch_viewer)

        lbl_viewer_info = QLabel("※.NET 8公式ホスト経由で起動し、Norton等のセキュリティソフトによる誤検知を抑制します。")
        lbl_viewer_info.setStyleSheet("color: #999; font-size: 12px;")
        viewer_layout.addWidget(lbl_viewer_info)

        layout.addWidget(viewer_box)
        layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # ウィンドウ下部ボタン
        h_bottom = QHBoxLayout()
        h_bottom.addStretch()
        btn_close = QPushButton("閉じる")
        btn_close.setFixedWidth(100)
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.close)
        h_bottom.addWidget(btn_close)
        main_layout.addLayout(h_bottom)

    def _get_target_pmx_path(self):
        """対象PMXパスを取得"""
        if self.parent_tab and hasattr(self.parent_tab, "_get_target_pmx_path"):
            return self.parent_tab._get_target_pmx_path()
        return ""

    def _sync_pmx_path(self):
        """対象PMXパスを同期"""
        if self.parent_tab and hasattr(self.parent_tab, "_sync_pmx_path"):
            return self.parent_tab._sync_pmx_path()
        return ""

    def _on_analysis_option_changed(self):
        """解析ラジオボタンの選択変更時にボタン表示とスタイルを連動更新"""
        if self.rb_analyze_pmx.isChecked():
            self.btn_execute_analysis.setText("PMXモデルチェック・データ一括保存を実行")
            self.btn_execute_analysis.setToolTip("インポートタブで指定されたPMXの構成要素（材質・ボーン・モーフ・剛体・Joint）をJSONに一括保存し、未登録漢字のユーザー辞書登録を行います。")
            self.btn_execute_analysis.setStyleSheet("QPushButton { background-color: #2b5b84; color: #fff; font-weight: bold; font-size: 13px; border-radius: 4px; } QPushButton:hover { background-color: #3872a4; }")
        else:
            self.btn_execute_analysis.setText("ボーン状態JSONエクスポートダイアログを開く")
            self.btn_execute_analysis.setToolTip("指定したフレーム範囲のすべてのボーンの移動・回転状態（ローカルおよびワールド）をJSONファイルとして書き出します。")
            self.btn_execute_analysis.setStyleSheet("QPushButton { background-color: #2e6b52; color: #fff; font-weight: bold; font-size: 13px; border-radius: 4px; } QPushButton:hover { background-color: #3b8767; }")

    def _on_execute_analysis_clicked(self):
        """選択中の解析・エクスポート機能を実行"""
        if self.rb_analyze_pmx.isChecked():
            self._analyze_and_save_structure()
        else:
            self._open_bone_state_export_window()

    def _analyze_and_save_structure(self):
        """PMXモデル詳細チェック・データ一括保存を実行"""
        if self.parent_tab and hasattr(self.parent_tab, "_analyze_and_save_structure"):
            self.parent_tab._analyze_and_save_structure()

    def _open_morph_window(self):
        """表情操作ウィンドウを開く"""
        if self.parent_tab and hasattr(self.parent_tab, "_open_morph_window"):
            self.parent_tab._open_morph_window()

    def _open_export_window(self):
        """Maya → MMD エクスポートウィンドウを開く"""
        if self.parent_tab and hasattr(self.parent_tab, "_open_export_window"):
            self.parent_tab._open_export_window()

    def _open_hik_window(self):
        """HumanIK管理ウィンドウを開く"""
        if self.parent_tab and hasattr(self.parent_tab, "_open_hik_window"):
            self.parent_tab._open_hik_window()

    def _launch_standalone_viewer(self):
        """3D物理ビューアを単体起動"""
        if self.parent_tab and hasattr(self.parent_tab, "_launch_standalone_viewer"):
            self.parent_tab._launch_standalone_viewer()

    def _open_bone_state_export_window(self):
        """ボーン状態JSONエクスポートダイアログを開く"""
        if self.parent_tab and hasattr(self.parent_tab, "_open_bone_state_export_window"):
            self.parent_tab._open_bone_state_export_window()

    def _open_accessory_attach_window(self):
        """アクセサリアタッチダイアログを開く"""
        if self.parent_tab and hasattr(self.parent_tab, "_open_accessory_attach_window"):
            self.parent_tab._open_accessory_attach_window()

    def _refresh_vpd_models(self):
        """VPDポーズ適用対象のMMDモデル一覧を更新"""
        self.cbb_vpd_target_model.clear()
        try:
            from ..converters import vmdpaimaya
        except Exception:
            from converters import vmdpaimaya
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for node_name, label in models:
                self.cbb_vpd_target_model.addItem(label, node_name)
        except Exception:
            pass

    def _on_import_vpd(self):
        """VPDポーズファイルを読み込んでモデルに適用"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "VPDポーズファイルを選択",
            "",
            "VPD Pose Data (*.vpd);;All Files (*.*)"
        )
        if not path:
            return

        target_model = self.cbb_vpd_target_model.currentData()
        try:
            scale = float(self.le_vpd_scale.text())
        except ValueError:
            scale = 8.0

        set_key = self.cb_vpd_keyframe.isChecked()

        try:
            from ..converters import vmdpaimaya
        except Exception:
            from converters import vmdpaimaya

        try:
            res = vmdpaimaya.import_vpd(path, target_model_node=target_model, scale=scale, set_keyframe=set_key)
            QMessageBox.information(
                self,
                "VPDインポート完了",
                f"VPDポーズを適用しました。\n"
                f"・ボーン: {res['bones_applied']} 本\n"
                f"・モーフ: {res['morphs_applied']} 個\n"
                f"・モデル: {res.get('model_name', '')}"
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"VPDポーズの適用中にエラーが発生しました:\n{e}")

# ==============================================================================
# その他機能タブ
# ==============================================================================
class ExtraTabWidget(QWidget):
    """共通設定管理および試験的機能へのアクセスを提供するユーティリティタブ"""
    def __init__(self, parent=None):
        super(ExtraTabWidget, self).__init__(parent)
        self.parent_window = parent
        self._exp_dialog = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 14, 14, 14)

        # 共通設定・マテリアル管理グループ
        setting_box = QGroupBox("共通設定・マテリアル管理")
        setting_layout = QVBoxLayout(setting_box)
        setting_layout.setSpacing(12)

        # マテリアル保護・Toon除外設定ボタン
        self.btn_material_protect = QPushButton("マテリアル保護・Toon除外設定")
        self.btn_material_protect.setFixedHeight(42)
        self.btn_material_protect.setToolTip("顔・肌のテカリ（スペキュラ）除去、瞳ハイライトのToon除外キーワードを設定します。")
        self.btn_material_protect.setStyleSheet("QPushButton { background-color: #3b5f7a; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #4b7496; }")
        self.btn_material_protect.clicked.connect(self._open_material_protect_window)
        setting_layout.addWidget(self.btn_material_protect)

        # ユーザー辞書・対応表設定ボタン
        self.btn_user_dict = QPushButton("ユーザー辞書・対応表設定 (ボーン/HumanIK/名称)")
        self.btn_user_dict.setFixedHeight(42)
        self.btn_user_dict.setToolTip("ボーン日英辞書、HumanIK対応表、日本語ローマ字変換辞書の対応表（JSON）を設定・編集します。")
        self.btn_user_dict.setStyleSheet("QPushButton { background-color: #4d5b7a; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #5d6f96; }")
        self.btn_user_dict.clicked.connect(self._open_user_dict_window)
        setting_layout.addWidget(self.btn_user_dict)

        # PMD → PMX に変換ボタン (単独変換・保存)
        self.btn_convert_pmd = QPushButton("PMD → PMX に変換")
        self.btn_convert_pmd.setFixedHeight(42)
        self.btn_convert_pmd.setToolTip("指定した PMD ファイルを最新の PMX 形式へ変換し、同一フォルダに保存します（モデルのインポートは行いません）。")
        self.btn_convert_pmd.setStyleSheet("QPushButton { background-color: #3b6b58; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #4b876e; }")
        self.btn_convert_pmd.clicked.connect(self._on_convert_pmd_to_pmx)
        setting_layout.addWidget(self.btn_convert_pmd)

        layout.addWidget(setting_box)

        # 試験的機能グループ
        exp_box = QGroupBox("試験的機能")
        exp_layout = QVBoxLayout(exp_box)
        exp_layout.setSpacing(10)

        lbl_exp_notice = QLabel("※開発中・試験的な機能群を別ウィンドウで開きます。")
        lbl_exp_notice.setStyleSheet("color: #ffaa00; font-size: 12px;")
        exp_layout.addWidget(lbl_exp_notice)

        # 試験的機能を表示ボタン
        self.btn_open_experimental = QPushButton("試験的機能を表示")
        self.btn_open_experimental.setFixedHeight(44)
        self.btn_open_experimental.setToolTip("正しく動作するか確認できていない試験的機能群（モデル解析、HumanIK、物理ビューア、ボーンエクスポート、アクセサリアタッチ、VPDポーズ適用等）を別ウィンドウで表示します。")
        self.btn_open_experimental.setStyleSheet("QPushButton { background-color: #7b4a2e; color: #fff; font-size: 13px; font-weight: bold; border-radius: 4px; border: 1px solid #965a38; } QPushButton:hover { background-color: #965a38; }")
        self.btn_open_experimental.clicked.connect(self._open_experimental_window)
        exp_layout.addWidget(self.btn_open_experimental)

        # 表情操作 (モーフ) ボタン
        self.btn_morph_ui = QPushButton("表情操作 (モーフ)")
        self.btn_morph_ui.setFixedHeight(44)
        self.btn_morph_ui.setToolTip("表情操作パネルを開き、目・リップ・まゆ・その他のモーフを操作・登録します。")
        self.btn_morph_ui.setStyleSheet("QPushButton { background-color: #3e6852; color: #fff; font-size: 13px; font-weight: bold; border-radius: 4px; border: 1px solid #4e8267; } QPushButton:hover { background-color: #4e8267; }")
        self.btn_morph_ui.clicked.connect(self._open_morph_window)
        exp_layout.addWidget(self.btn_morph_ui)

        # MMDシェーダーボタン
        self.btn_open_material = QPushButton("MMDシェーダー")
        self.btn_open_material.setFixedHeight(44)
        self.btn_open_material.setToolTip("MMDシェーダー (mmdMaterial) のアサイン・管理機能を別ウィンドウで表示します。")
        self.btn_open_material.setStyleSheet("QPushButton { background-color: #2e607a; color: #fff; font-size: 13px; font-weight: bold; border-radius: 4px; border: 1px solid #3b7696; } QPushButton:hover { background-color: #3b7696; }")
        self.btn_open_material.clicked.connect(self._open_material_window)
        exp_layout.addWidget(self.btn_open_material)

        layout.addWidget(exp_box)
        layout.addStretch()

    def _open_experimental_window(self):
        """試験的機能ウィンドウを表示"""
        self._exp_dialog = ExperimentalFeaturesDialog(self)
        self._exp_dialog.show()

    def _open_material_window(self):
        """MMDシェーダーウィンドウを別ウィンドウで表示"""
        self._material_dialog = MaterialDialog(self)
        self._material_dialog.show()

    def _open_export_window(self):
        """Maya → MMD エクスポートウィンドウを別ウィンドウで表示"""
        self._export_dialog = ExportDialog(self)
        self._export_dialog.show()

    def _open_accessory_attach_window(self):
        """アクセサリアタッチダイアログを開く"""
        dlg = AccessoryAttachDialog(self)
        dlg.show()

    def _open_bone_state_export_window(self):
        """ボーン状態JSONエクスポートダイアログを開く"""
        try:
            from .bone_state_export_dialog import show_bone_state_export_dialog
        except Exception:
            try:
                from ui.bone_state_export_dialog import show_bone_state_export_dialog
            except Exception:
                import bone_state_export_dialog
                show_bone_state_export_dialog = bone_state_export_dialog.show_bone_state_export_dialog
        show_bone_state_export_dialog()

    def _open_material_protect_window(self):
        """マテリアル保護・Toon除外設定ダイアログを開く"""
        try:
            from .material_protect_dialog import show_material_protect_dialog
        except Exception:
            try:
                from ui.material_protect_dialog import show_material_protect_dialog
            except Exception:
                import material_protect_dialog
                show_material_protect_dialog = material_protect_dialog.show_material_protect_dialog
        show_material_protect_dialog()

    def _open_user_dict_window(self):
        """ユーザー辞書・対応表設定ダイアログを開く"""
        try:
            from .user_dict_dialog import show_user_dict_dialog
        except Exception:
            try:
                from ui.user_dict_dialog import show_user_dict_dialog
            except Exception:
                import user_dict_dialog
                show_user_dict_dialog = user_dict_dialog.show_user_dict_dialog
        show_user_dict_dialog()

    def _on_convert_pmd_to_pmx(self):
        """PMDファイルを選択して最新のPMX形式へ変換・保存（インポートは行わない）"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "変換する PMD ファイルを選択",
            "",
            "MMD Model (*.pmd);;All Files (*.*)"
        )
        if not file_path:
            return

        if not os.path.exists(file_path):
            QMessageBox.warning(self, "エラー", "指定された PMD ファイルが存在しません。")
            return

        try:
            try:
                from ..converters.pmd2pmx import convert_pmd_to_pmx
            except Exception:
                from converters.pmd2pmx import convert_pmd_to_pmx

            converted_pmx_path = convert_pmd_to_pmx(file_path)
            QMessageBox.information(
                self,
                "変換完了",
                f"PMDからPMXへの変換が正常に完了しました。\n\n保存先:\n{converted_pmx_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "PMD変換エラー", f"PMXへの変換中にエラーが発生しました:\n{e}")

    def _launch_standalone_viewer(self):

        """physics_bridge_cs フォルダー内の MMD Physics Brige を単体起動する (Norton対策・dotnet経由対応)"""
        warning_msg = (
            "【注意・試験的機能】\n\n"
            "本機能は physics_bridge_cs フォルダー内の MMD Physics Brige を起動します。\n"
            "本ツールは試験的に作成された機能であり、動作中にエラー、フリーズ、強制終了などが発生する可能性や、"
            "今後メンテナンスされない可能性があります。\n\n"
            "※Norton等のセキュリティソフトにより「Norton CyberCapture」等の確認画面が表示された場合は、"
            "「信頼して起動」を選択するか、除外リストへプラグインフォルダーを追加してください。\n\n"
            "起動を続行しますか？"
        )
        reply = QMessageBox.warning(
            self,
            "MMD Physics Brige - 3D物理ビューア(試験的機能)",
            warning_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # physics_bridge_cs フォルダー内の実行ファイルおよびDLLパスを取得
        plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bridge_candidates = [
            os.path.join(plugin_dir, "physics_bridge_cs", "bin", "Release", "net8.0-windows", "MmdPhysicsBridge.exe"),
            os.path.join(plugin_dir, "physics_bridge_cs", "bin", "Debug", "net8.0-windows", "MmdPhysicsBridge.exe"),
        ]
        exe_path = ""
        for cand in bridge_candidates:
            if os.path.isfile(cand):
                exe_path = cand
                break
        if not exe_path:
            exe_path = bridge_candidates[0]

        dll_candidates = [
            os.path.join(plugin_dir, "physics_bridge_cs", "bin", "Release", "net8.0-windows", "MmdPhysicsBridge.dll"),
            os.path.join(plugin_dir, "physics_bridge_cs", "bin", "Debug", "net8.0-windows", "MmdPhysicsBridge.dll"),
        ]
        dll_path = ""
        for cand in dll_candidates:
            if os.path.isfile(cand):
                dll_path = cand
                break
        if not dll_path:
            dll_path = dll_candidates[0]

        if not os.path.isfile(exe_path) and not os.path.isfile(dll_path):
            QMessageBox.critical(
                self,
                "エラー",
                f"physics_bridge_cs フォルダー内に MMD Physics Brige の実行ファイルが見つかりません:\n{exe_path}\n\n事前にビルドされているか確認してください。"
            )
            return

        # PMXファイルパスとVMDファイルパスの取得 (選択されていれば引数として渡す)
        pmx_path = self._get_target_pmx_path()
        vmd_path = ""
        if hasattr(self.parent_window, "tab_vmd"):
            vmd_path = self.parent_window.tab_vmd.le_file_path.text().strip()

        args = []
        if pmx_path and os.path.isfile(pmx_path):
            args.extend(["--pmx", pmx_path])
        if vmd_path and os.path.isfile(vmd_path):
            args.extend(["--vmd", vmd_path])

        # Zone.Identifier の解除 (セキュリティ警告抑止)
        for p in [exe_path, dll_path]:
            if p and os.path.exists(p) and sys.platform == 'win32':
                zone_stream = p + ":Zone.Identifier"
                try:
                    if os.path.exists(zone_stream):
                        os.remove(zone_stream)
                except Exception:
                    pass

        # Norton CyberCapture 対策: dotnet コマンド経由での起動を優先
        import shutil
        dotnet_exe = shutil.which("dotnet")
        if not dotnet_exe:
            common_paths = [
                os.path.expandvars(r"%ProgramFiles%\dotnet\dotnet.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\dotnet\dotnet.exe"),
            ]
            for cp in common_paths:
                if os.path.isfile(cp):
                    dotnet_exe = cp
                    break

        try:
            import subprocess
            if dotnet_exe and os.path.isfile(dll_path):
                cmd = [dotnet_exe, dll_path] + args
            else:
                cmd = [exe_path] + args
            subprocess.Popen(cmd)
        except Exception as e:
            QMessageBox.critical(self, "起動エラー", f"ビューアの起動に失敗しました:\n{e}")

    def _get_target_pmx_path(self):
        """インポートタブで指定されているPMXモデルのパスを取得"""
        path = ""
        if hasattr(self.parent_window, "tab_import") and hasattr(self.parent_window.tab_import, "le_file_path"):
            path = self.parent_window.tab_import.le_file_path.text().strip()
        return path

    def _sync_pmx_path(self):
        """インポートタブのモデルパスを取得"""
        return self._get_target_pmx_path()

    def _analyze_and_save_structure(self):
        """インポートタブで指定されたモデルの材質、ボーン、モーフ、剛体、Jointを一括保存し、未登録ボーン辞書チェックを実行"""
        file_path = self._sync_pmx_path()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(
                self,
                "エラー",
                "有効なPMXモデルファイルが指定されていません。\n\n"
                "[MMD → Maya (インポート)] タブでPMXモデルファイルを指定してください。"
            )
            return

        if not file_path.lower().endswith('.pmx'):
            QMessageBox.information(self, "案内", "詳細解析および辞書照合はPMXモデル形式 (.pmx) のみ対応しています。")
            return

        try:
            if check_and_prompt_user_dict:
                check_and_prompt_user_dict(self.parent_window or self, file_path)

            if export_pmx_structure:
                saved_path, data = export_pmx_structure(file_path)
                QMessageBox.information(
                    self,
                    "PMXモデル解析完了",
                    f"モデル構造の一括保存が完了しました！\n\n"
                    f"保存先:\n{saved_path}\n\n"
                    f"・材質: {len(data['materials'])} 件\n"
                    f"・ボーン: {len(data['bones'])} 件\n"
                    f"・モーフ: {len(data['morphs'])} 件\n"
                    f"・剛体: {len(data['rigid_bodies'])} 件\n"
                    f"・Joint: {len(data['joints'])} 件"
                )
        except Exception as e:
            QMessageBox.warning(self, "解析エラー", f"PMXモデルの解析中にエラーが発生しました:\n{e}")

    def _open_morph_window(self):
        """MMD本家風の表情操作ウィンドウを開く（ボーン・モーフ・ブレンドシェイプ事前検証付き）"""
        # ボーン(Joint)存在確認
        joints = mc.ls(type="joint") if mc else []

        # BlendShapeノード存在確認
        bs_nodes = mc.ls(type="blendShape") if mc else []

        # ターゲット/モーフ存在確認
        has_targets = False
        if bs_nodes and mc:
            for bs in bs_nodes:
                try:
                    aliases = mc.listAttr(f"{bs}.w", multi=True) or []
                    targets = mc.blendShape(bs, query=True, target=True) or []
                    if aliases or targets:
                        has_targets = True
                        break
                except Exception:
                    pass

        # 必要な要素が揃っていない場合は再インポートを案内
        if not joints or not bs_nodes or not has_targets:
            missing_items = []
            if not joints:
                missing_items.append("・ボーン (Joint)")
            if not bs_nodes or not has_targets:
                missing_items.append("・ブレンドシェイプ / モーフ (blendShape)")

            missing_str = "\n".join(missing_items)
            QMessageBox.warning(
                self,
                "表情操作の準備ができていません",
                f"モデル（ボーン・モーフ・ブレンドシェイプ）がインポートされていないか、必要な要素が不足しています。\n\n"
                f"不足している要素:\n{missing_str}\n\n"
                f"[MMD → Maya (インポート)] タブからモデルをインポートし直してください。\n"
                f"（※インポート設定で「ボーン生成」「ブレンドシェイプ生成」にチェックが入っていることをご確認ください）"
            )
            return

        try:
            from .morph_window import show_morph_window
        except Exception:
            try:
                from morph_window import show_morph_window
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"表情操作モジュールの読み込みに失敗しました:\n{e}")
                return

        show_morph_window(parent=get_maya_main_window())

    def _open_hik_window(self):
        """HumanIK管理ウィンドウを別ウィンドウで開く"""
        show_hik_window(parent=get_maya_main_window())

    def _refresh_vpd_models(self):
        """VPDポーズ適用対象のMMDモデル一覧を更新"""
        self.cbb_vpd_target_model.clear()
        try:
            from ..converters import vmdpaimaya
        except Exception:
            from converters import vmdpaimaya
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for node_name, label in models:
                self.cbb_vpd_target_model.addItem(label, node_name)
        except Exception:
            pass

    def _on_import_vpd(self):
        """VPDポーズファイルを読み込んでモデルに適用"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "VPDポーズファイルを選択",
            "",
            "VPD Pose Data (*.vpd);;All Files (*.*)"
        )
        if not path:
            return

        target_model = self.cbb_vpd_target_model.currentData()
        try:
            scale = float(self.le_vpd_scale.text())
        except ValueError:
            scale = 8.0

        set_key = self.cb_vpd_keyframe.isChecked()

        try:
            from ..converters import vmdpaimaya
        except Exception:
            from converters import vmdpaimaya

        try:
            res = vmdpaimaya.import_vpd(path, target_model_node=target_model, scale=scale, set_keyframe=set_key)
            QMessageBox.information(
                self,
                "VPDインポート完了",
                f"VPDポーズを適用しました。\n"
                f"・ボーン: {res['bones_applied']} 本\n"
                f"・モーフ: {res['morphs_applied']} 個\n"
                f"・モデル: {res.get('model_name', '')}"
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"VPDポーズの適用中にエラーが発生しました:\n{e}")

# ==============================================================================
# シェーダー設定タブ (mmdMaterial 管理)
# ==============================================================================
class MaterialTabWidget(QWidget):
    """MMDシェーダー (mmdMaterial) のアサイン・管理タブ"""
    def __init__(self, parent=None):
        super(MaterialTabWidget, self).__init__(parent)
        self.parent_window = parent
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # スクロールエリア（小画面でも見切れを防止）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 14, 14, 14)

        # 対象モデル・メッシュ指定グループ
        target_box = QGroupBox("アサイン対象モデル / メッシュの選択")
        target_layout = QVBoxLayout(target_box)
        target_layout.setSpacing(8)

        h_model = QHBoxLayout()
        h_model.addWidget(QLabel("対象:"))
        self.cbb_target = QComboBox()
        self.btn_refresh = QPushButton("更新")
        self.btn_refresh.setFixedWidth(80)
        self.btn_refresh.clicked.connect(self._refresh_targets)
        h_model.addWidget(self.cbb_target)
        h_model.addWidget(self.btn_refresh)
        target_layout.addLayout(h_model)

        lbl_target_info = QLabel("※「現在選択中のオブジェクト」を選ぶと、ビューポートで選択中の全メッシュが対象になります。")
        lbl_target_info.setStyleSheet("color: #999; font-size: 12px;")
        target_layout.addWidget(lbl_target_info)
        layout.addWidget(target_box)

        # ツール連携 ＆ MMDライティング（横並び統合グループ）
        tool_box = QGroupBox("ツール連携 & MMDライティング")
        tool_layout = QVBoxLayout(tool_box)
        tool_layout.setSpacing(8)

        h_tools = QHBoxLayout()
        h_tools.setSpacing(10)

        self.btn_open_hypershade = QPushButton("Hypershade を開く")
        self.btn_open_hypershade.setFixedHeight(34)
        self.btn_open_hypershade.setToolTip("Hypershade のノード作成ツリー [MmdMat] > [Material] から直接ノードを作成できます。")
        self.btn_open_hypershade.setStyleSheet(
            "QPushButton { background-color: #383838; color: #e0e0e0; border: 1px solid #555; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #484848; color: #ffffff; border-color: #777; }"
        )
        self.btn_open_hypershade.clicked.connect(self._open_hypershade)
        h_tools.addWidget(self.btn_open_hypershade)

        self.btn_create_light = QPushButton("MMD標準ライトを作成 / 最適化")
        self.btn_create_light.setFixedHeight(34)
        self.btn_create_light.setToolTip("MMD公式準拠の平行光源と環境光を作成し、白飛びを防止してビューポート描画を最適化します。")
        self.btn_create_light.setStyleSheet(
            "QPushButton { background-color: #383838; color: #e0e0e0; border: 1px solid #555; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #484848; color: #ffffff; border-color: #777; }"
        )
        self.btn_create_light.clicked.connect(self._create_mmd_lighting)
        h_tools.addWidget(self.btn_create_light)

        self.btn_create_ground_shadow = QPushButton("MMD地面影を作成 / 最適化")
        self.btn_create_ground_shadow.setFixedHeight(34)
        self.btn_create_ground_shadow.setToolTip("Y=0平面上に半透明のシャドウキャッチャー平面を配置し、MMD標準の地面影を再現します。")
        self.btn_create_ground_shadow.setStyleSheet(
            "QPushButton { background-color: #383838; color: #e0e0e0; border: 1px solid #555; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #484848; color: #ffffff; border-color: #777; }"
        )
        self.btn_create_ground_shadow.clicked.connect(self._create_mmd_ground_shadow)
        h_tools.addWidget(self.btn_create_ground_shadow)

        tool_layout.addLayout(h_tools)

        lbl_tool_info = QLabel("※Hypershadeでのノード作成や、MMD標準ライトによるビューポート発色・陰影の最適化を行えます。")
        lbl_tool_info.setStyleSheet("color: #999; font-size: 12px;")
        tool_layout.addWidget(lbl_tool_info)
        layout.addWidget(tool_box)

        # 実行ボタングループ
        act_box = QGroupBox("アサイン実行")
        act_layout = QVBoxLayout(act_box)
        act_layout.setSpacing(8)

        lbl_act_info = QLabel("※既存テクスチャ（fileノード）は自動で引き継がれ、スフィア・Toon未設定時も安全に処理されます。")
        lbl_act_info.setStyleSheet("color: #aaa; font-size: 12px;")
        act_layout.addWidget(lbl_act_info)

        self.btn_assign = QPushButton("MMDシェーダーを選択モデルにアサイン")
        self.btn_assign.setFixedHeight(46)
        self.btn_assign.setStyleSheet(
            "QPushButton { background-color: #1e4d75; color: #e6f3ff; border: 1px solid #2d6ca3; border-radius: 4px; font-weight: bold; font-size: 15px; }"
            "QPushButton:hover { background-color: #276396; color: #ffffff; border-color: #438fcf; }"
            "QPushButton:pressed { background-color: #153856; }"
        )
        self.btn_assign.clicked.connect(self._execute_assign)
        act_layout.addWidget(self.btn_assign)

        self.lbl_result = QLabel("")
        self.lbl_result.setStyleSheet("color: #52b7ff; font-size: 13px; padding: 2px;")
        act_layout.addWidget(self.lbl_result)

        layout.addWidget(act_box)
        layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        self._check_plugin_status()
        self._refresh_targets()

    def _check_plugin_status(self):
        """プラグインのロード状況を確認（互換性のためのスタブ）"""
        pass

    def _refresh_targets(self):
        """対象モデル一覧コンボボックスを更新"""
        self.cbb_target.clear()
        self.cbb_target.addItem("現在選択中のオブジェクト (メッシュ / モデル)", None)
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for m in models:
                self.cbb_target.addItem(f"モデル: {m}", m)
        except Exception:
            pass

    def _open_hypershade(self):
        """MayaのHypershadeウィンドウを開く（コールバックを適用した上で表示）"""
        if mmd_material_setup:
            try:
                mmd_material_setup.ensure_plugin_loaded()
                mmd_material_setup.setup_hypershade_callbacks()
            except Exception:
                pass

        try:
            mel.eval("HypershadeWindow;")
        except Exception as e:
            QMessageBox.warning(self, "Hypershade", f"Hypershadeを開けませんでした:\n{e}")

    def _create_mmd_lighting(self):
        """MMD標準ライティングを作成または最適化"""
        if mmd_material_setup:
            try:
                grp = mmd_material_setup.ensure_mmd_lighting()
                if grp:
                    QMessageBox.information(
                        self,
                        "ライティング",
                        "MMD標準ライティングを作成・適用しました。\n白飛び防止パラメータが適用され、ビューポートのライティングが適正化されました。"
                    )
                else:
                    QMessageBox.warning(self, "ライティング", "ライティングの作成に失敗しました。")
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"ライト作成中にエラーが発生しました:\n{e}")
        else:
            QMessageBox.warning(self, "エラー", "mmd_material_setup モジュールが見つかりません。")

    def _create_mmd_ground_shadow(self):
        """MMD標準地面影プレーンを作成または最適化"""
        try:
            from ..converters import pmxpaimaya
        except Exception:
            try:
                from converters import pmxpaimaya
            except Exception:
                import pmxpaimaya
        try:
            plane = pmxpaimaya.create_mmd_ground_shadow()
            if plane:
                QMessageBox.information(
                    self,
                    "地面影 (Ground Shadow)",
                    f"MMD標準地面影プレーン ({plane}) を作成・適用しました。\nY=0平面に半透明の落ち影が投影されます。"
                )
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"地面影プレーン作成中にエラーが発生しました:\n{e}")

    def _execute_assign(self):
        """選択モデルまたはメッシュに mmdMaterial をアサイン"""
        if not mmd_material_setup:
            QMessageBox.critical(self, "エラー", "mmd_material_setup モジュールが利用できません。")
            return

        selected_model = self.cbb_target.currentData()
        inherit_tex = True

        targets = None
        if selected_model:
            targets = [selected_model]
        else:
            targets = mc.ls(selection=True, long=True) or []
            if not targets:
                QMessageBox.warning(self, "警告", "アサイン対象のオブジェクトまたはメッシュをビューポートで選択してください。")
                return

        try:
            results = mmd_material_setup.assign_mmd_material_to_model(
                targets=targets,
                inherit_textures=inherit_tex
            )

            if results:
                count = len(results)
                msg = f"MMDシェーダーをアサインしました ({count} 個のシェーダー設定完了)。"
                self.lbl_result.setText(f"<span style='color:#55ff77;'>✓ {msg}</span>")
                mc.inViewMessage(
                    amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> {msg}',
                    pos='topCenter',
                    fade=True
                )
            else:
                msg = "アサイン対象のメッシュまたはシェーダーが見つかりませんでした。"
                self.lbl_result.setText(f"<span style='color:#ffaa55;'>! {msg}</span>")
                QMessageBox.information(self, "情報", msg)

        except Exception as e:
            err_msg = f"シェーダーアサイン中にエラーが発生しました:\n{e}"
            self.lbl_result.setText(f"<span style='color:#ff7777;'>✕ エラー</span>")
            QMessageBox.critical(self, "エラー", err_msg)

# ==============================================================================
# MMDシェーダー 独立ダイアログ
# ==============================================================================
class MaterialDialog(QDialog):
    """MMDシェーダー (mmdMaterial) を別ウィンドウで表示するダイアログ"""
    def __init__(self, parent=None):
        super(MaterialDialog, self).__init__(parent)
        self.setWindowTitle("MMDシェーダー")
        self.resize(840, 760)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        self.material_widget = MaterialTabWidget(self)
        main_layout.addWidget(self.material_widget)

        # 下部ボタングループ
        h_bottom = QHBoxLayout()
        h_bottom.addStretch()
        btn_close = QPushButton("閉じる")
        btn_close.setFixedWidth(100)
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.close)
        h_bottom.addWidget(btn_close)
        main_layout.addLayout(h_bottom)


# ==============================================================================
# Maya → MMD (エクスポート) 独立ダイアログ
# ==============================================================================
class ExportDialog(QDialog):
    """Maya → MMD エクスポートを別ウィンドウで表示するダイアログ"""
    def __init__(self, parent=None):
        super(ExportDialog, self).__init__(parent)
        self.setWindowTitle("Maya → MMD (エクスポート)")
        self.resize(840, 780)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        self.export_widget = ExportTabWidget(self)
        main_layout.addWidget(self.export_widget)

        # 下部ボタングループ
        h_bottom = QHBoxLayout()
        h_bottom.addStretch()
        btn_close = QPushButton("閉じる")
        btn_close.setFixedWidth(100)
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.close)
        h_bottom.addWidget(btn_close)
        main_layout.addLayout(h_bottom)


# ==============================================================================
# メインウィンドウ (タブ統合)
# ==============================================================================
class MmdMayaMainWindow(QWidget):
    """MMD Tools for Maya のメイン統合ウィンドウ"""
    def __init__(self, parent=None):
        if parent is None:
            parent = get_maya_main_window()
        super(MmdMayaMainWindow, self).__init__(parent)
        
        self.setWindowTitle("MMD Tools for Maya v1.0.4")
        self.setObjectName("MmdToolsForMayaMainWindow")

        # メインウィンドウサイズ設定 (視認性向上・タブ文字収まり向上のワイドレイアウト)
        self.resize(980, 820)
        self.setMinimumSize(880, 640)

        # Mayaの子ウィンドウとして独立表示（他アプリより前面固定にはしない）
        self.setWindowFlags(Qt.Window)
        self.setStyleSheet(MODERN_STYLE)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # タブコンテナ
        self.tabs = QTabWidget()
        self.tab_plugin = PluginTabWidget(self)
        self.tab_import = ImportTabWidget(self)
        self.tab_vmd = VmdImportTabWidget(self)
        self.tab_physics = PhysicsTabWidget(self)
        self.tab_physics_gui = PhysicsGuiTabWidget(self)
        self.tab_extra = ExtraTabWidget(self)
        self.tab_material = None
        self.tab_export = None
        self.tab_cleanup = CleanupTabWidget(self)

        # タブ登録 (プラグイン管理を先頭、物理演算GUIを物理演算の次へ配置)
        self.tabs.addTab(self.tab_plugin, "プラグイン管理")
        self.tabs.addTab(self.tab_import, "MMD → Maya (インポート)")
        self.tabs.addTab(self.tab_vmd, "モーション (VMD)")
        self.tabs.addTab(self.tab_physics, "物理演算ベイク")
        self.tabs.addTab(self.tab_physics_gui, "物理演算ベイクGUI")
        self.tabs.addTab(self.tab_extra, "その他機能")
        self.tabs.addTab(self.tab_cleanup, "MMD削除 (クリーンアップ)")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs)

        # フッタークレジット
        footer = QLabel("MMD Tools for Maya v1.0.4 | Developer: Hina33")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #777; font-size: 13px; padding: 4px;")
        main_layout.addWidget(footer)

    def _on_tab_changed(self, index):
        """タブ切り替え時にプラグイン状態を再確認およびパス同期"""
        if getattr(self, "tab_plugin", None):
            self.tab_plugin.refresh_all_status()
        if getattr(self, "tab_material", None):
            self.tab_material._check_plugin_status()
        if getattr(self, "tab_physics", None):
            self.tab_physics._refresh_bullet_status()
        if getattr(self, "tab_physics_gui", None) and self.tabs.currentWidget() == self.tab_physics_gui:
            self.tab_physics_gui.refresh_all_tab_info()
        if getattr(self, "tab_extra", None):
            self.tab_extra._sync_pmx_path()

    def showEvent(self, e):
        """ウィンドウ表示時にプラグイン状態を最新化およびパス同期"""
        super().showEvent(e)
        if getattr(self, "tab_plugin", None):
            self.tab_plugin.refresh_all_status()
        if getattr(self, "tab_material", None):
            self.tab_material._check_plugin_status()
        if getattr(self, "tab_physics", None):
            self.tab_physics._refresh_bullet_status()
        if getattr(self, "tab_physics_gui", None) and self.tabs.currentWidget() == self.tab_physics_gui:
            self.tab_physics_gui.refresh_all_tab_info()
        if getattr(self, "tab_extra", None):
            self.tab_extra._sync_pmx_path()


    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()

def close_existing_ui():
    """既に表示されているMMD Tools for Mayaウィンドウを検索してすべて閉じます"""
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        try:
            if widget.objectName() == "MmdToolsForMayaMainWindow" or widget.__class__.__name__ == "MmdMayaMainWindow":
                widget.close()
                widget.deleteLater()
        except Exception:
            pass

def show_ui():
    """UIウィンドウを表示します（既に表示されている場合は閉じてから再表示）"""
    global _main_window_instance
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # 既存ウィンドウを検索して安全に破棄（多重起動防止）
    close_existing_ui()
    _main_window_instance = None

    # プラグインの自動ロード試行
    try:
        if mmd_material_setup:
            mmd_material_setup.ensure_plugin_loaded()
    except Exception:
        pass
    try:
        try:
            from ..bullet_engine import bullet_maya_bridge
        except Exception:
            from bullet_engine import bullet_maya_bridge
        bridge = bullet_maya_bridge.BulletMayaBridge.__new__(bullet_maya_bridge.BulletMayaBridge)
        bridge._ensure_motion_plugin_loaded()
    except Exception:
        pass

    _main_window_instance = MmdMayaMainWindow()
    _main_window_instance.show()
    _main_window_instance.raise_()
    _main_window_instance.activateWindow()
    return _main_window_instance

# ==============================================================================
# 後方互換クラス & エントリポイント
# ==============================================================================
Natanglak = MmdMayaMainWindow
Natang_mmdmaya = ImportTabWidget
Natang_mayammd = ExportTabWidget
Natang_humanik = HikTabWidget
