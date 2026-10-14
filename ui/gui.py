# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - モダン統合 GUI モジュール (PySide6 / PySide2 対応)

タブ型GUI
- タブ1: MMD → Maya (インポート)
- タブ2: MMDシェーダー
- タブ3: モーション(VMD)
- タブ4: Maya → MMD (エクスポート)
- タブ5: HumanIK 管理
- タブ6: クリーンアップ
- 実行時ログウィンドウ (リアルタイム進捗表示)
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
        QDialog, QTextEdit, QProgressBar, QSlider
    )
    from PySide6.QtCore import Qt, QSize
    from PySide6.QtGui import QDragEnterEvent, QDropEvent, QTextCursor, QFont
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2.QtWidgets import (
        QWidget, QLabel, QLineEdit, QComboBox, QPushButton,
        QCheckBox, QButtonGroup, QRadioButton, QHBoxLayout,
        QVBoxLayout, QScrollArea, QFileDialog, QMessageBox,
        QTabWidget, QGroupBox, QFrame, QSizePolicy, QApplication,
        QDialog, QTextEdit, QProgressBar, QSlider
    )
    from PySide2.QtCore import Qt, QSize
    from PySide2.QtGui import QDragEnterEvent, QDropEvent, QTextCursor, QFont
    try:
        from shiboken2 import wrapInstance
    except ImportError:
        wrapInstance = None

import maya.cmds as mc
from maya import mel
import maya.OpenMaya as om
import maya.OpenMayaUI as omui

try:
    from ..converters import pmxpaimaya, mayapaipmx, vmdpaimaya, physics_stream
    from ..asset.hik import dic_hik, kangkhaen, setup_leg_stance_and_angles, normalize_bone_name, get_bone_matching_candidates
    from ..pmx_analyzer import export_pmx_structure, check_and_prompt_user_dict
except Exception:
    try:
        from converters import pmxpaimaya, mayapaipmx, vmdpaimaya, physics_stream
        from asset.hik import dic_hik, kangkhaen, setup_leg_stance_and_angles, normalize_bone_name, get_bone_matching_candidates
        from pmx_analyzer import export_pmx_structure, check_and_prompt_user_dict
    except Exception:
        import pmxpaimaya, mayapaipmx, vmdpaimaya
        try:
            import physics_stream
        except Exception:
            physics_stream = None
        from asset.hik import dic_hik, kangkhaen, setup_leg_stance_and_angles, normalize_bone_name, get_bone_matching_candidates
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

def restore_viewport_lighting():
    """
    ビューポートのライティング（全ライト使用: displayLights='all'）および
    テクスチャ表示（displayTextures=True）を安定化・復元します。
    """
    try:
        has_lights = bool(mc.ls(type=["directionalLight", "ambientLight", "pointLight", "spotLight"]))
        target_mode = "all" if has_lights else "default"
        panels = mc.getPanel(type="modelPanel") or []
        for p in panels:
            try:
                mc.modelEditor(p, edit=True, displayLights=target_mode, displayTextures=True)
            except Exception:
                pass
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

        # 1. ファイル選択ゾーン (ドラッグ＆ドロップ対応)
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

        layout.addWidget(file_box)

        # 2. スケール設定
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
        self.cb_create_physics = QCheckBox("剛体・Jointコライダーを生成")
        self.cb_create_physics.setChecked(True)
        self.cb_create_bs = QCheckBox("ブレンドシェイプ（モーフ）を作成する")
        
        scale_layout.addWidget(self.cb_split_poly)
        scale_layout.addWidget(self.cb_create_bones)
        scale_layout.addWidget(self.cb_create_physics)
        scale_layout.addWidget(self.cb_create_bs)
        
        self.cb_split_poly.toggled.connect(self._on_split_toggled)

        # マテリアルタイプ
        h_mat = QHBoxLayout()
        h_mat.addWidget(QLabel("マテリアル種別:"))
        self.cbb_material = QComboBox()
        self.cbb_material.addItems(["マテリアルなし", "Blinn", "Phong", "Lambert", "StandardSurface (Maya 2022+)", "MMD Shader (オリジナル,ベータ版)"])
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

        self.cb_enable_toon = QCheckBox("Toonシェーディング（セル影）を適用する")
        self.cb_enable_toon.setChecked(True)
        self.cb_enable_toon.setToolTip("光の当たり具合に応じたセルアニメ調の影（Toon）を適用します。OFFにするとメッシュ本来の綺麗なテクスチャを維持します。")
        light_layout.addWidget(self.cb_enable_toon)

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

        # 3. 実行アクション
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
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    file_path = f.readline().split('=')[-1].strip()
                    scale = f.readline().split('=')[-1].strip()
                    split = int(f.readline().split('=')[-1].strip())
                    bs = int(f.readline().split('=')[-1].strip())
                    bones = int(f.readline().split('=')[-1].strip())
                    mat = int(f.readline().split('=')[-1].strip())
                    close = int(f.readline().split('=')[-1].strip())
                    light_line = f.readline()
                    light = int(light_line.split('=')[-1].strip()) if light_line else 1
                    untone_line = f.readline()
                    untone = int(untone_line.split('=')[-1].strip()) if untone_line else 1
                    physics_line = f.readline()
                    physics = int(physics_line.split('=')[-1].strip()) if physics_line else 1
                    shadow_line = f.readline()
                    shadow_mode = int(shadow_line.split('=')[-1].strip()) if shadow_line else 1

                self.le_file_path.setText(file_path)
                self.le_scale.setText(scale)
                self.cb_split_poly.setChecked(bool(split))
                self.cb_create_bs.setChecked(bool(bs))
                self.cb_create_bones.setChecked(bool(bones))
                self.cb_create_physics.setChecked(bool(physics))
                if 0 <= mat < self.cbb_material.count():
                    self.cbb_material.setCurrentIndex(mat)
                self.cb_close_on_finish.setChecked(bool(close))
                self.cb_create_light.setChecked(bool(light))
                self.cb_untone_mapped.setChecked(bool(untone))
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
        self.cbb_material.setCurrentIndex(5) # MMD Shader (オリジナル,ベータ版)
        self.cb_close_on_finish.setChecked(False)
        self.cb_create_light.setChecked(True)
        self.cb_untone_mapped.setChecked(True)
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
                f.write(f"トゥーン = {int(self.cb_enable_toon.isChecked())}\n")
                f.write(f"剛体物理 = {int(self.cb_create_physics.isChecked())}\n")
                f.write(f"シャドウモード = {self.get_shadow_mode()}\n")
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

    def _on_split_toggled(self):
        split = self.cb_split_poly.isChecked()
        ext = os.path.splitext(self.le_file_path.text())[1].lower()
        can_rig = (ext != '.x') and not split
        self.cb_create_bones.setEnabled(can_rig)
        self.cb_create_bs.setEnabled(can_rig)

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
            # 1. ユーザー辞書の未登録ボーン名チェック & 登録GUI
            if check_and_prompt_user_dict:
                check_and_prompt_user_dict(self.parent_window or self, file_path)

            # 2. モデル構造の一括保存 (JSON)
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

        # PMX事前チェック & 未登録ボーン辞書確認
        if file_path.lower().endswith('.pmx') and check_and_prompt_user_dict:
            model_filename = os.path.basename(file_path)
            print(f"[PMXチェック] モデルファイル（{model_filename}）の未登録漢字およびユーザー辞書チェックを実行中...")
            try:
                check_and_prompt_user_dict(self.parent_window or self, file_path)
            except Exception as e:
                print(f"[PMXチェック] 辞書チェック中に軽微な警告: {e}")

        # 材質・ボーン・モーフ・剛体・Joint の一括保存
        if file_path.lower().endswith('.pmx') and export_pmx_structure:
            print(f"[PMXチェック] モデル構成要素（材質/ボーン/モーフ/剛体/Joint）の一括保存を実行中...")
            try:
                export_pmx_structure(file_path)
            except Exception as e:
                print(f"[PMXチェック] 一括保存中に軽微な警告: {e}")

        try:
            scale = float(self.le_scale.text())
        except ValueError:
            scale = 1.0

        split_poly = self.cb_split_poly.isChecked()
        create_bs = not split_poly and self.cb_create_bs.isChecked()
        create_bones = not split_poly and self.cb_create_bones.isChecked()
        material_type = self.cbb_material.currentIndex()
        create_light = self.cb_create_light.isChecked()
        set_untone_mapped = self.cb_untone_mapped.isChecked()
        enable_toon = self.cb_enable_toon.isChecked()
        shadow_mode = self.get_shadow_mode() if enable_toon else 0

        create_physics = self.cb_create_physics.isChecked()

        def full_import_task():
            total_start_time = time.time()
            if file_path.lower().endswith('.pmx'):
                print("==================================================")
                print(f"[PMXチェック] モデルファイル: {os.path.basename(file_path)}")
                print("  - 未登録漢字およびユーザー辞書の照合: 完了")
                print("  - モデル構成要素（材質/ボーン/モーフ/剛体/Joint）データ保存: 完了")
                print("==================================================")
            import importlib
            importlib.reload(pmxpaimaya)
            import_func = getattr(pmxpaimaya, 'import_pmx', pmxpaimaya.sang)
            res = import_func(
                file_path, scale, split_poly, create_bs, create_bones, material_type, create_light, set_untone_mapped, enable_toon, shadow_mode=shadow_mode, show_completion_message=False
            )
            # ボーン作成時、Aポーズの状態で剛体・Jointコライダーを同時生成 (ログダイアログ内で実行)
            if create_bones and create_physics and file_path.lower().endswith('.pmx'):
                try:
                    try:
                        from ..cpp_engine import xpbd_visualizer
                    except Exception:
                        from cpp_engine import xpbd_visualizer
                    xpbd_visualizer.create_rigidbody_visualizers(file_path, scale=scale)
                    print("[MMD Tools for Maya] 初期Aポーズにて剛体・Jointコライダーを自動生成しました。")
                except Exception as e:
                    print(f"[MMD Tools for Maya] 剛体自動生成のスキップ/エラー: {e}")

            # すべてのインポート工程（メッシュ・ボーン・剛体・Joint等）の終了直後に総括完了メッセージを表示
            total_elapsed = time.time() - total_start_time
            print("==================================================")
            print(f"モデルインポートが完了しました！ (所要時間: {total_elapsed:.2f}秒)")
            print("==================================================")
            return res

        # ログウィンドウを起動して実行
        log_dialog = ExecutionLogDialog(self.parent_window or self, title="モデルインポート実行ログ")
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
    """MayaシーンからPMXファイルへエクスポートするためのUIタブ"""
    def __init__(self, parent=None):
        super(ExportTabWidget, self).__init__(parent)
        self.parent_window = parent
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_file = os.path.join(plugin_root, 'asset', 'khatangton2.txt')

        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # 1. 保存先ファイル
        file_box = QGroupBox("保存先 PMX ファイル")
        file_layout = QHBoxLayout(file_box)

        self.le_file_path = QLineEdit()
        self.le_file_path.setPlaceholderText("出力先パス (.pmx)")
        self.le_file_path.textChanged.connect(self._on_file_changed)
        file_layout.addWidget(self.le_file_path)

        self.btn_browse = QPushButton("保存先...")
        self.btn_browse.setFixedWidth(95)
        self.btn_browse.clicked.connect(self._browse_save_file)
        file_layout.addWidget(self.btn_browse)

        self.btn_clear_file = QPushButton("クリア")
        self.btn_clear_file.setFixedWidth(65)
        self.btn_clear_file.clicked.connect(self._clear_file)
        file_layout.addWidget(self.btn_clear_file)

        layout.addWidget(file_box)

        # 2. エクスポートオプション
        opt_box = QGroupBox("エクスポート設定")
        opt_layout = QVBoxLayout(opt_box)

        h_scale = QHBoxLayout()
        h_scale.addWidget(QLabel("スケール倍率:"))
        self.le_scale = QLineEdit("0.125")
        self.le_scale.setFixedWidth(80)
        self.le_scale.textEdited.connect(self._validate_scale)
        h_scale.addWidget(self.le_scale)
        h_scale.addWidget(QLabel("(インポート時が8.0の場合は 0.125 を推奨)"))
        h_scale.addStretch()
        opt_layout.addLayout(h_scale)

        self.cb_export_bones = QCheckBox("スケルトン（ボーン）を出力")
        self.cb_export_morphs = QCheckBox("ブレンドシェイプ（モーフ）を出力")
        self.cb_export_materials = QCheckBox("マテリアル（材質）を出力")
        self.cb_copy_textures = QCheckBox("テクスチャファイルを保存先フォルダへコピー")

        opt_layout.addWidget(self.cb_export_bones)
        opt_layout.addWidget(self.cb_export_morphs)
        opt_layout.addWidget(self.cb_export_materials)
        opt_layout.addWidget(self.cb_copy_textures)

        # 対象ポリゴン
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
        opt_layout.addLayout(h_poly)

        layout.addWidget(opt_box)

        layout.addStretch()

        # 実行アクション
        h_action = QHBoxLayout()
        self.cb_close_on_finish = QCheckBox("完了後にウィンドウを閉じる")
        h_action.addWidget(self.cb_close_on_finish)
        h_action.addStretch()

        self.btn_execute = QPushButton("PMX をエクスポート")
        self.btn_execute.setProperty("class", "primary")
        self.btn_execute.setFixedHeight(46)
        self.btn_execute.setMinimumWidth(180)
        self.btn_execute.clicked.connect(self._execute_export)
        h_action.addWidget(self.btn_execute)

        layout.addLayout(h_action)

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

        # 1. VMDファイル選択
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

        # BGM音量スライダー
        h_volume = QHBoxLayout()
        h_volume.addWidget(QLabel("BGM音量:"))
        self.slider_audio_volume = QSlider(Qt.Horizontal)
        self.slider_audio_volume.setRange(0, 100)
        self.slider_audio_volume.setValue(100)
        self.lbl_audio_volume = QLabel("100%")
        self.lbl_audio_volume.setFixedWidth(45)
        self.slider_audio_volume.valueChanged.connect(self._on_audio_volume_changed)
        h_volume.addWidget(self.slider_audio_volume)
        h_volume.addWidget(self.lbl_audio_volume)

        self.btn_apply_audio_volume = QPushButton("確定")
        self.btn_apply_audio_volume.setFixedWidth(60)
        self.btn_apply_audio_volume.clicked.connect(self._on_apply_audio_volume)
        h_volume.addWidget(self.btn_apply_audio_volume)
        file_layout.addLayout(h_volume)

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

    def _on_audio_volume_changed(self, value):
        """BGM音量スライダー変更時の数値ラベル表示更新"""
        self.lbl_audio_volume.setText(f"{value}%")

    def _on_apply_audio_volume(self):
        """音量確定ボタン押下時にPCM波形をゲイン乗算した一時WAVを出力し、MMD_Audioノードに即時反映"""
        vol = self.slider_audio_volume.value()
        dlg = ExecutionLogDialog(self, title="BGM音量調整 実行ログ")

        def _task():
            print(f">>> BGM音量を {vol}% に設定中...")
            try:
                from ..converters import vmdpaimaya
            except Exception:
                from converters import vmdpaimaya
            vmdpaimaya.set_audio_volume(vol)
            msg = f"[MMD Audio] Python 標準ライブラリ（wave + struct）によりPCM波形をゲイン乗算した一時WAVを出力し、Maya の MMD_Audio ノードに即時反映しました（音量: {vol}%）"
            om.MGlobal.displayInfo(msg)
            print(msg)

        dlg.run_task(_task)

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
        audio_volume = self.slider_audio_volume.value()

        if audio_path and os.path.exists(audio_path):
            mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", audio_path))
        if file_path and os.path.exists(file_path):
            mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", file_path))
        if camera_path and os.path.exists(camera_path):
            mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", camera_path))

        success = log_dialog.run_task(
            import_func,
            file_path,
            camera_path,
            audio_path,
            scale,
            target_model,
            audio_volume,
            progress_callback=log_dialog.update_progress
        )

        # インポート完了後のビューポートライティングを確実に復元
        restore_viewport_lighting()

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

        # 物理シミュレーション設定
        param_box = QGroupBox("物理演算パラメータ (XPBD / Bullet 共通)")
        param_layout = QVBoxLayout(param_box)

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

        if loaded:
            self.lbl_motion_plugin_status.setText("<span style='color:#55ff77; font-weight:bold;'>● プラグイン読み込み済み (mmd_motion.mll)</span>")
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
            self._check_motion_plugin_status()
            if success:
                QMessageBox.information(self, "プラグイン", "MMDモーションプラグイン (mmd_motion.mll) が正常にロードされました。")
            else:
                QMessageBox.warning(self, "プラグイン", "MMDモーションプラグイン (mmd_motion.mll) のロードに失敗しました。")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"プラグインのロード中にエラーが発生しました: {e}")

    def _is_bullet_available(self):
        """Bullet物理モジュール (bullet_engine) が存在し利用可能か判定"""
        try:
            plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            bullet_dir = os.path.join(plugin_root, "bullet_engine")
            dll_path = os.path.join(bullet_dir, "bin", "mmd_bullet.dll")
            bridge_path = os.path.join(bullet_dir, "bullet_maya_bridge.py")
            return os.path.exists(dll_path) and os.path.exists(bridge_path)
        except Exception:
            return False

    def _refresh_bullet_status(self):
        """Bulletボタンの活性化状態を更新 (フォルダ削除時は自動無効化)"""
        available = self._is_bullet_available()
        self.btn_bullet_bake.setEnabled(available)
        if available:
            self.btn_bullet_bake.setToolTip("本家MMD仕様のBullet Physics (2.83.7) により、柔らかくしなやかな髪やスカートの物理をベイクします。")
        else:
            self.btn_bullet_bake.setToolTip("Bullet物理モジュール (bullet_engine) は削除または未導入です。\n下の「XPBD 物理ベイク実行」をご利用ください。")

    def _on_physics_mode_toggled(self, checked):
        """ダンスモーションモードと簡易モードの切り替え"""
        if self.rb_mode_dance.isChecked():
            self.le_substeps.setText("30")
        else:
            self.le_substeps.setText("10")

    def showEvent(self, event):
        super(PhysicsTabWidget, self).showEvent(event)
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

        log_dialog = ExecutionLogDialog(self.parent_window or self, title="Bullet 物理演算ベイク実行ログ (MMD本家仕様)", show_cancel=True)

        def run_bullet_task():
            try:
                from ..bullet_engine import bullet_maya_bridge
            except Exception:
                from bullet_engine import bullet_maya_bridge
            bridge = bullet_maya_bridge.BulletMayaBridge(pmx_path=pmx_path, scale=scale)
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
                from ..cpp_engine import xpbd_visualizer
            except Exception:
                from cpp_engine import xpbd_visualizer
            ok = xpbd_visualizer.reconnect_visualizers_to_bones()
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
                from ..cpp_engine import xpbd_visualizer
            except Exception:
                from cpp_engine import xpbd_visualizer
            xpbd_visualizer.create_rigidbody_visualizers(pmx_path, scale=scale)
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
        self.btn_refresh_scene_status.setFixedWidth(110)
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
        h_stream_model.addWidget(QLabel("適用対象モデル:"))
        self.cbb_stream_target_model = QComboBox()
        self.cbb_stream_target_model.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        h_stream_model.addWidget(self.cbb_stream_target_model)

        self.btn_refresh_stream_models = QPushButton("更新")
        self.btn_refresh_stream_models.setFixedWidth(60)
        self.btn_refresh_stream_models.clicked.connect(self._refresh_stream_target_models)
        h_stream_model.addWidget(self.btn_refresh_stream_models)
        stream_bake_layout.addLayout(h_stream_model)

        # VMDファイル出力オプション
        vmd_out_box = QGroupBox("物理ベイク済みモーションの書き出し設定")
        vmd_out_layout = QVBoxLayout(vmd_out_box)

        h_vmd_out_choice = QHBoxLayout()
        self.rb_vmd_out_enable = QRadioButton("VMDファイルを出力する (推奨)")
        self.rb_vmd_out_disable = QRadioButton("VMDファイルを出力しない (Mayaへの直接ベイクのみ)")
        self.rb_vmd_out_enable.setChecked(True)
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
        h_vmd_out_path.addWidget(self.le_vmd_output_path)

        self.btn_browse_vmd_output = QPushButton("参照...")
        self.btn_browse_vmd_output.setFixedWidth(75)
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

        h_stream_params = QHBoxLayout()
        h_stream_params.addWidget(QLabel("先行フレーム数:"))
        init_lookahead = mc.optionVar(q="MMDToolsForMaya_StreamLookahead") if mc.optionVar(exists="MMDToolsForMaya_StreamLookahead") else "16"
        self.le_stream_lookahead = QLineEdit(str(init_lookahead))
        self.le_stream_lookahead.setFixedWidth(70)
        self.le_stream_lookahead.setToolTip("ビューアが先行して物理計算を行うフレーム数です (ACK同期用)。")
        self.le_stream_lookahead.textChanged.connect(lambda val: mc.optionVar(sv=("MMDToolsForMaya_StreamLookahead", val.strip())))
        h_stream_params.addWidget(self.le_stream_lookahead)

        h_stream_params.addWidget(QLabel("安定化時間(秒):"))
        init_warmup = mc.optionVar(q="MMDToolsForMaya_StreamWarmup") if mc.optionVar(exists="MMDToolsForMaya_StreamWarmup") else "0.0"
        self.le_stream_warmup = QLineEdit(str(init_warmup))
        self.le_stream_warmup.setFixedWidth(70)
        self.le_stream_warmup.setToolTip("ベイク開始前にフレーム0の姿勢で物理演算を先行実行し、スカートや髪の垂れ下がりを落ち着かせる時間(秒)です。タイミングの一致を優先する場合は0.0秒を設定します。")
        self.le_stream_warmup.textChanged.connect(lambda val: mc.optionVar(sv=("MMDToolsForMaya_StreamWarmup", val.strip())))
        h_stream_params.addWidget(self.le_stream_warmup)

        h_stream_params.addWidget(QLabel("オフセット:"))
        init_offset = mc.optionVar(q="MMDToolsForMaya_StreamOffset") if mc.optionVar(exists="MMDToolsForMaya_StreamOffset") else "0"
        self.le_stream_offset = QLineEdit(str(init_offset))
        self.le_stream_offset.setFixedWidth(70)
        self.le_stream_offset.setToolTip("身体モーションや楽曲に対して物理ベイクの開始フレームを前後にずらす値です (例: -60 または 60)。")
        self.le_stream_offset.textChanged.connect(lambda val: mc.optionVar(sv=("MMDToolsForMaya_StreamOffset", val.strip())))
        h_stream_params.addWidget(self.le_stream_offset)

        h_stream_params.addWidget(QLabel("スケール倍率:"))
        init_scale = mc.optionVar(q="MMDToolsForMaya_StreamScale") if mc.optionVar(exists="MMDToolsForMaya_StreamScale") else "8.0"
        self.le_stream_scale = QLineEdit(str(init_scale))
        self.le_stream_scale.setFixedWidth(70)
        self.le_stream_scale.textChanged.connect(lambda val: mc.optionVar(sv=("MMDToolsForMaya_StreamScale", val.strip())))
        h_stream_params.addWidget(self.le_stream_scale)
        h_stream_params.addStretch()
        stream_bake_layout.addLayout(h_stream_params)

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

        log_dialog = ExecutionLogDialog(
            self.parent_window or self,
            title="リアルタイム物理ベイク実行ログ (新3D物理ビューア連携)",
            show_cancel=True
        )

        def run_task():
            physics_stream.stream_bake_physics(
                pmx_path=pmx_path,
                vmd_path=vmd_path,
                target_model=target_model,
                scale=scale,
                lookahead=lookahead,
                warmup=warmup,
                out_vmd=out_vmd,
                frame_offset=frame_offset,
                start_frame=start_frame,
                end_frame=end_frame,
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
    """シーン内のMMD要素の一括削除およびモーション初期化を行うクリーンアップタブ"""
    def __init__(self, parent=None):
        super(CleanupTabWidget, self).__init__(parent)
        self.parent_window = parent
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 14, 14, 14)

        # 1. 対象モデル指定
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

        # 2. 削除オプション
        opt_box = QGroupBox("削除オプション (一括クリーンアップ設定)")
        opt_layout = QVBoxLayout(opt_box)
        opt_layout.setSpacing(10)

        self.cb_delete_lights = QCheckBox("MMDライトも削除する (Mmd_Lighting_Grp)")
        del_lights_default = True
        if mc.optionVar(exists="MMDToolsForMaya_DeleteLightsOnClear"):
            del_lights_default = bool(mc.optionVar(q="MMDToolsForMaya_DeleteLightsOnClear"))
        self.cb_delete_lights.setChecked(del_lights_default)
        self.cb_delete_lights.toggled.connect(self._on_delete_lights_toggled)
        opt_layout.addWidget(self.cb_delete_lights)

        self.cb_delete_cameras = QCheckBox("MMDカメラも削除する (MMD_Camera_Aim / MMD_Camera)")
        self.cb_delete_cameras.setChecked(True)
        opt_layout.addWidget(self.cb_delete_cameras)

        self.cb_delete_audio = QCheckBox("MMDオーディオも削除する (BGM音声を解除・削除)")
        del_audio_default = True
        if mc.optionVar(exists="MMDToolsForMaya_DeleteAudioOnClear"):
            del_audio_default = bool(mc.optionVar(q="MMDToolsForMaya_DeleteAudioOnClear"))
        self.cb_delete_audio.setChecked(del_audio_default)
        self.cb_delete_audio.toggled.connect(self._on_delete_audio_toggled)
        opt_layout.addWidget(self.cb_delete_audio)

        self.cb_delete_unused = QCheckBox("未使用マテリアル・テクスチャ・ノードを削除 (Delete Unused Nodes)")
        self.cb_delete_unused.setChecked(True)
        opt_layout.addWidget(self.cb_delete_unused)

        lbl_opt_info = QLabel(
            "・メッシュおよび付随するスケルトンジョイント、IK、コンストレイント、BlendShapeは常に一括削除されます。\n"
            "・「未使用マテリアル」の削除を実行すると、Maya標準の 'MLdeleteUnused;' が実行され、シーンが軽量化されます。"
        )
        lbl_opt_info.setStyleSheet("color: #aaa; font-size: 13px; line-height: 1.5; margin-top: 6px;")
        opt_layout.addWidget(lbl_opt_info)
        layout.addWidget(opt_box)

        layout.addStretch()

        # 3. 実行アクション
        act_box = QGroupBox("クリーンアップ実行")
        act_layout = QVBoxLayout(act_box)
        act_layout.setSpacing(12)

        # モーション初期化ボタン
        self.btn_clear_anim = QPushButton("モーションのみ初期化 (動作不安定)")
        self.btn_clear_anim.setFixedHeight(44)
        self.btn_clear_anim.setStyleSheet(
            "QPushButton { background-color: #3b3a28; color: #fff8cc; border: 1px solid #66633a; border-radius: 4px; font-weight: bold; font-size: 14px; }"
            "QPushButton:hover { background-color: #4d4b32; color: #ffffff; border-color: #99944a; }"
            "QPushButton:pressed { background-color: #2b2a1a; }"
        )
        self.btn_clear_anim.clicked.connect(self._execute_clear_anim_only)
        act_layout.addWidget(self.btn_clear_anim)

        # MMD全削除ボタン
        self.btn_delete_all = QPushButton("MMDモデル一括削除 (モデル・リグ・カメラ・マテリアル類)")
        self.btn_delete_all.setFixedHeight(48)
        self.btn_delete_all.setStyleSheet(
            "QPushButton { background-color: #5d2525; color: #ffcccc; border: 1px solid #853333; border-radius: 4px; font-weight: bold; font-size: 15px; }"
            "QPushButton:hover { background-color: #782e2e; color: #ffffff; border-color: #ba4444; }"
            "QPushButton:pressed { background-color: #401818; }"
        )
        self.btn_delete_all.clicked.connect(self._execute_delete_all)
        act_layout.addWidget(self.btn_delete_all)

        layout.addWidget(act_box)

        self._refresh_models()

    def _on_delete_lights_toggled(self, checked):
        mc.optionVar(iv=("MMDToolsForMaya_DeleteLightsOnClear", int(checked)))

    def _on_delete_audio_toggled(self, checked):
        mc.optionVar(iv=("MMDToolsForMaya_DeleteAudioOnClear", int(checked)))

    def _refresh_models(self):
        self.cbb_target_model.clear()
        self.cbb_target_model.addItem("シーン内の全MMDモデル / 自動検出", None)
        try:
            models = vmdpaimaya.get_available_mmd_models()
            for node_name, label in models:
                self.cbb_target_model.addItem(label, node_name)
        except Exception:
            pass

    def _execute_clear_anim_only(self):
        target_model = self.cbb_target_model.currentData()
        target_label = self.cbb_target_model.currentText()
        res = QMessageBox.question(
            self,
            "モーション初期化の確認",
            f"対象 ({target_label}) のキーフレームをすべて削除し、初期ポーズへ復元しますか？\n（メッシュやスケルトン、剛体・Jointは削除されません）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return

        try:
            b_cnt, m_cnt = vmdpaimaya.clear_model_animation(target_model)
            mc.inViewMessage(
                amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> モーションを初期化しました (ボーン: {b_cnt}, モーフ: {m_cnt}, 剛体・Joint再吸着完了)。',
                pos='topCenter',
                fade=True
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"モーション初期化中にエラーが発生しました:\n{e}")

    def _execute_delete_all(self):
        target_model = self.cbb_target_model.currentData()
        target_label = self.cbb_target_model.currentText()
        delete_lights = self.cb_delete_lights.isChecked()
        delete_cameras = self.cb_delete_cameras.isChecked()
        delete_audio = self.cb_delete_audio.isChecked()
        delete_unused = self.cb_delete_unused.isChecked()

        items = ["モデル・スケルトン・IK階層"]
        if delete_cameras:
            items.append("MMDカメラ")
        if delete_audio:
            items.append("MMDオーディオ (BGM)")
        if delete_lights:
            items.append("MMDライト (Mmd_Lighting_Grp)")
        if delete_unused:
            items.append("未使用マテリアル (Delete Unused Nodes)")

        msg = f"対象 ({target_label}) および以下の項目をきれいに削除しますか？\n\n・" + "\n・".join(items) + "\n\n※この操作は取り消せません。"

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
            del_cnt = vmdpaimaya.delete_mmd_scene_elements(
                target_model_node=target_model,
                delete_lights=delete_lights,
                delete_cameras=delete_cameras,
                delete_audio=delete_audio,
                delete_unused_nodes=delete_unused
            )

            # 物理可視化ノードおよびBulletリグの一括クリーンアップ
            for phys_grp in ["MMD_RigidBody_Joint_Visualizers", "MMD_RigidBody_Visualizers", "MMD_Bullet_Physics_Rig", "MMD_BulletSolver"]:
                if mc.objExists(phys_grp):
                    try:
                        mc.delete(phys_grp)
                        print(f"[MMD Tools for Maya] 物理関連ノード '{phys_grp}' を削除しました。")
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

        lbl_motion_info = QLabel("・Maya C++ APIによる超高速キーフレーム書き込みノード (mmdFastBakeBone) を提供します。")
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
            "・新3D物理ビューア (MmdPhysicsViewer.exe): WPF3Dによるリアルタイム物理シミュレーションで柔らかくしなやかな剛体挙動とMayaへの同期ベイク機能です。"
        )
        lbl_phys_info.setStyleSheet("color: #999; font-size: 12px; line-height: 1.4;")
        physics_layout.addWidget(lbl_phys_info)
        layout.addWidget(physics_box)

        # MMDシェーダープラグイン
        mat_box = QGroupBox("MMDシェーダープラグイン (mmd_material.mll)")
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

        lbl_mat_info = QLabel("・Viewport 2.0上でMMDのToon陰影・スフィアマップをリアルタイム描画するカスタムマテリアルノードです。")
        lbl_mat_info.setStyleSheet("color: #999; font-size: 12px;")
        mat_layout.addWidget(lbl_mat_info)
        layout.addWidget(mat_box)

        # 全プラグイン一括再読み込み
        all_box = QGroupBox("全プラグイン一括管理")
        all_layout = QVBoxLayout(all_box)
        self.btn_reload_all = QPushButton("すべてのプラグインを一括再読み込み")
        self.btn_reload_all.setFixedHeight(40)
        self.btn_reload_all.setStyleSheet(
            "QPushButton { background-color: #2b4c6f; color: #ffffff; border-radius: 4px; font-weight: bold; font-size: 13px; }"
            "QPushButton:hover { background-color: #38618d; }"
        )
        self.btn_reload_all.clicked.connect(self._reload_all_plugins)
        all_layout.addWidget(self.btn_reload_all)
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

        if loaded:
            self.lbl_motion_status.setText("<span style='color:#55ff77; font-weight:bold;'>● プラグイン読み込み済み (mmd_motion.mll)</span>")
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

        # 新3D物理ビューア (MmdPhysicsViewer.exe)
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
            self.lbl_viewer_status.setText("<span style='color:#55ff77; font-weight:bold;'>● 新3D物理ビューア: 利用可能 (MmdPhysicsViewer.exe / .NET 8 WPF)</span>")
        else:
            self.lbl_viewer_status.setText("<span style='color:#ffaa55; font-weight:bold;'>△ 新3D物理ビューア: 未検出 (physics_bake_cs をビルドしてください)</span>")

    def _check_material_status(self):
        loaded = False
        try:
            if "mmdMaterial" in (mc.allNodeTypes() or []):
                loaded = True
            elif any("mmd_material" in p.lower() for p in (mc.pluginInfo(query=True, listPlugins=True) or [])):
                loaded = True
            elif mc.pluginInfo("mmd_material.mll", query=True, loaded=True) or mc.pluginInfo("mmd_material", query=True, loaded=True):
                loaded = True
        except Exception:
            pass

        if loaded:
            self.lbl_mat_status.setText("<span style='color:#55ff77; font-weight:bold;'>● プラグイン読み込み済み (mmd_material.mll)</span>")
        else:
            self.lbl_mat_status.setText("<span style='color:#ff7777; font-weight:bold;'>○ プラグイン未読み込み (mmd_material.mll)</span>")

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
            self._check_motion_status()
            if success:
                QMessageBox.information(self, "プラグイン", "MMDモーションプラグイン (mmd_motion.mll) が正常にロードされました。")
            else:
                QMessageBox.warning(self, "プラグイン", "MMDモーションプラグイン (mmd_motion.mll) のロードに失敗しました。")
        else:
            QMessageBox.warning(self, "エラー", "bullet_maya_bridge モジュールが見つかりません。")

    def _reload_physics_plugins(self):
        self._check_physics_status()
        QMessageBox.information(self, "物理プラグイン", "物理演算ライブラリ (Bullet / XPBD) の状態を更新しました。")

    def _reload_material_plugin(self):
        if mmd_material_setup:
            success = mmd_material_setup.ensure_plugin_loaded()
            self._check_material_status()
            if success:
                QMessageBox.information(self, "プラグイン", "MMDシェーダープラグイン (mmd_material.mll) が正常にロードされました。")
            else:
                QMessageBox.warning(self, "プラグイン", "MMDシェーダープラグインのロードに失敗しました。")
        else:
            QMessageBox.warning(self, "エラー", "mmd_material_setup モジュールが見つかりません。")

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

        if mmd_material_setup:
            mmd_material_setup.ensure_plugin_loaded()

        self.refresh_all_status()
        QMessageBox.information(self, "プラグイン一括再読み込み", "すべてのプラグインの再読み込み処理を完了しました。")

# ==============================================================================
# その他機能タブ
# ==============================================================================
class ExtraTabWidget(QWidget):
    """PMXモデル詳細チェック・データ一括保存および表情操作を提供するユーティリティタブ"""
    def __init__(self, parent=None):
        super(ExtraTabWidget, self).__init__(parent)
        self.parent_window = parent
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 14, 14, 14)

        # 対象PMXモデルファイル表示グループ (インポートタブと連動)
        file_box = QGroupBox("対象PMXモデル (インポートタブ連動)")
        file_layout = QVBoxLayout(file_box)
        file_layout.setSpacing(10)

        h_file = QHBoxLayout()
        h_file.addWidget(QLabel("PMXファイル:"))
        self.le_file_path = QLineEdit()
        self.le_file_path.setReadOnly(True)
        self.le_file_path.setPlaceholderText("[MMD → Maya (インポート)] タブで選択されたPMXファイルが自動的に反映されます...")
        h_file.addWidget(self.le_file_path)

        self.btn_sync = QPushButton("更新")
        self.btn_sync.setFixedWidth(75)
        self.btn_sync.setToolTip("インポートタブで現在選択されているモデルパスを再取得して反映します。")
        self.btn_sync.clicked.connect(self._sync_pmx_path)
        h_file.addWidget(self.btn_sync)
        file_layout.addLayout(h_file)

        lbl_file_info = QLabel("※[MMD → Maya (インポート)] タブで指定されたPMXモデルが解析および操作の対象となります。")
        lbl_file_info.setStyleSheet("color: #999; font-size: 12px;")
        file_layout.addWidget(lbl_file_info)
        layout.addWidget(file_box)

        # モデル解析・操作機能グループ
        tool_box = QGroupBox("モデル解析・操作機能")
        tool_layout = QVBoxLayout(tool_box)
        tool_layout.setSpacing(12)

        # PMXモデルチェック・データ一括保存ボタン
        self.btn_analyze_model = QPushButton("PMXモデルチェック・データ一括保存 (材質/ボーン/モーフ/剛体/Joint)")
        self.btn_analyze_model.setFixedHeight(42)
        self.btn_analyze_model.setToolTip("インポートタブで指定されたPMXの構成要素（材質・ボーン・モーフ・剛体・Joint）をJSONに一括保存し、未登録漢字のユーザー辞書登録を行います。")
        self.btn_analyze_model.setStyleSheet("QPushButton { background-color: #2b5b84; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3872a4; }")
        self.btn_analyze_model.clicked.connect(self._analyze_and_save_structure)
        tool_layout.addWidget(self.btn_analyze_model)

        # 表情操作 (モーフ) ボタン
        self.btn_morph_ui = QPushButton("表情操作 (モーフ)")
        self.btn_morph_ui.setFixedHeight(42)
        self.btn_morph_ui.setToolTip("MMD本家風の表情操作パネルを開き、目・リップ・まゆ・その他のモーフを操作・登録します。")
        self.btn_morph_ui.setStyleSheet("QPushButton { background-color: #3e6852; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #4e8267; }")
        self.btn_morph_ui.clicked.connect(self._open_morph_window)
        tool_layout.addWidget(self.btn_morph_ui)

        # HumanIK管理ボタン
        self.btn_hik_ui = QPushButton("HumanIK管理")
        self.btn_hik_ui.setFixedHeight(42)
        self.btn_hik_ui.setToolTip("HumanIK管理パネルを別ウィンドウで開き、キャラクター定義の作成やボーンマッピングを行います。")
        self.btn_hik_ui.setStyleSheet("QPushButton { background-color: #2e607a; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3b7696; }")
        self.btn_hik_ui.clicked.connect(self._open_hik_window)
        tool_layout.addWidget(self.btn_hik_ui)

        # MMD Physics Brige - 3D物理ビューア起動ボタン (試験的機能)
        self.btn_launch_viewer = QPushButton("MMD Physics Brige - 3D物理ビューア(試験的機能)")
        self.btn_launch_viewer.setFixedHeight(42)
        self.btn_launch_viewer.setToolTip("physics_bridge_cs フォルダー内の MMD Physics Brige を単体起動します。試験的機能のため注意ダイアログが表示されます。")
        self.btn_launch_viewer.setStyleSheet("QPushButton { background-color: #5c3b7a; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #734a99; }")
        self.btn_launch_viewer.clicked.connect(self._launch_standalone_viewer)
        tool_layout.addWidget(self.btn_launch_viewer)

        # マテリアル保護・Toon除外設定ボタン
        self.btn_material_protect = QPushButton("マテリアル保護・Toon除外設定")
        self.btn_material_protect.setFixedHeight(42)
        self.btn_material_protect.setToolTip("顔・肌のテカリ（スペキュラ）除去、瞳ハイライトのToon除外キーワードを設定します。")
        self.btn_material_protect.setStyleSheet("QPushButton { background-color: #3b5f7a; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #4b7496; }")
        self.btn_material_protect.clicked.connect(self._open_material_protect_window)
        tool_layout.addWidget(self.btn_material_protect)

        # ユーザー辞書・対応表設定ボタン
        self.btn_user_dict = QPushButton("ユーザー辞書・対応表設定 (ボーン/HumanIK/名称)")
        self.btn_user_dict.setFixedHeight(42)
        self.btn_user_dict.setToolTip("ボーン日英辞書、HumanIK対応表、日本語ローマ字変換辞書の対応表（JSON）を設定・編集します。")
        self.btn_user_dict.setStyleSheet("QPushButton { background-color: #4d5b7a; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #5d6f96; }")
        self.btn_user_dict.clicked.connect(self._open_user_dict_window)
        tool_layout.addWidget(self.btn_user_dict)

        # ボーン状態JSONエクスポートボタン
        self.btn_export_bone_states = QPushButton("ボーン状態JSONエクスポート (指定フレーム範囲)")
        self.btn_export_bone_states.setFixedHeight(42)
        self.btn_export_bone_states.setToolTip("指定したフレーム範囲のすべてのボーンの移動・回転状態（ローカルおよびワールド）をJSONファイルとして書き出します。")
        self.btn_export_bone_states.setStyleSheet("QPushButton { background-color: #2e6b52; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3b8767; }")
        self.btn_export_bone_states.clicked.connect(self._open_bone_state_export_window)
        tool_layout.addWidget(self.btn_export_bone_states)

        layout.addWidget(tool_box)
        layout.addStretch()

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

    def _launch_standalone_viewer(self):
        """physics_bridge_cs フォルダー内の MMD Physics Brige を単体起動する (試験的機能の確認ダイアログ付き)"""
        warning_msg = (
            "【注意・試験的機能】\n\n"
            "本機能は physics_bridge_cs フォルダー内の MMD Physics Brige を起動します。\n"
            "本ツールは試験的に作成された機能であり、動作中にエラー、フリーズ、強制終了などが発生する可能性や、"
            "今後メンテナンスされない可能性があります。\n\n"
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

        # physics_bridge_cs フォルダー内の実行ファイルパスを取得
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

        if not os.path.isfile(exe_path):
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

        try:
            # 独立プロセスとして起動
            import subprocess
            cmd = [exe_path] + args
            subprocess.Popen(cmd)
        except Exception as e:
            QMessageBox.critical(self, "起動エラー", f"ビューアの起動に失敗しました:\n{e}")

    def _get_target_pmx_path(self):
        """インポートタブで指定されているPMXモデルのパスを取得"""
        path = ""
        if hasattr(self.parent_window, "tab_import"):
            path = self.parent_window.tab_import.le_file_path.text().strip()
        if not path and hasattr(self, "le_file_path"):
            path = self.le_file_path.text().strip()
        return path

    def _sync_pmx_path(self):
        """インポートタブのモデルパスを取得して表示を更新"""
        path = self._get_target_pmx_path()
        self.le_file_path.setText(path)
        return path

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
        # 1. ボーン(Joint)存在確認
        joints = mc.ls(type="joint") if mc else []

        # 2. BlendShapeノード存在確認
        bs_nodes = mc.ls(type="blendShape") if mc else []

        # 3. ターゲット/モーフ存在確認
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

        # 3. ツール連携 ＆ MMDライティング（横並び統合グループ）
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

        tool_layout.addLayout(h_tools)

        lbl_tool_info = QLabel("※Hypershadeでのノード作成や、MMD標準ライトによるビューポート発色・陰影の最適化を行えます。")
        lbl_tool_info.setStyleSheet("color: #999; font-size: 12px;")
        tool_layout.addWidget(lbl_tool_info)
        layout.addWidget(tool_box)

        # 4. 実行ボタングループ
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
# メインウィンドウ (タブ統合)
# ==============================================================================
class MmdMayaMainWindow(QWidget):
    """MMD Tools for Maya のメイン統合ウィンドウ"""
    def __init__(self, parent=None):
        if parent is None:
            parent = get_maya_main_window()
        super(MmdMayaMainWindow, self).__init__(parent)
        
        self.setWindowTitle("MMD Tools for Maya v1.0.3")
        self.setObjectName("MmdToolsForMayaMainWindow")

        # メインウィンドウサイズ設定 (視認性向上・ボタン文字見切れ防止のワイドレイアウト)
        self.resize(880, 820)
        self.setMinimumSize(820, 640)
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
        self.tab_material = MaterialTabWidget(self)
        self.tab_export = ExportTabWidget(self)
        self.tab_cleanup = CleanupTabWidget(self)

        # タブ登録 (プラグイン管理を先頭、物理演算GUIを物理演算の次へ配置)
        self.tabs.addTab(self.tab_plugin, "プラグイン管理")
        self.tabs.addTab(self.tab_import, "MMD → Maya (インポート)")
        self.tabs.addTab(self.tab_vmd, "モーション (VMD)")
        self.tabs.addTab(self.tab_physics, "物理演算ベイク")
        self.tabs.addTab(self.tab_physics_gui, "物理演算ベイクGUI")
        self.tabs.addTab(self.tab_extra, "その他機能")
        self.tabs.addTab(self.tab_material, "MMDシェーダー")
        self.tabs.addTab(self.tab_export, "Maya → MMD (エクスポート)")
        self.tabs.addTab(self.tab_cleanup, "MMD削除 (クリーンアップ)")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs)

        # フッタークレジット
        footer = QLabel("MMD Tools for Maya v1.0.3 | Developer: Hina33")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #777; font-size: 13px; padding: 4px;")
        main_layout.addWidget(footer)

    def _on_tab_changed(self, index):
        """タブ切り替え時にプラグイン状態を再確認およびパス同期"""
        if hasattr(self, "tab_plugin"):
            self.tab_plugin.refresh_all_status()
        if hasattr(self, "tab_material"):
            self.tab_material._check_plugin_status()
        if hasattr(self, "tab_physics"):
            self.tab_physics._refresh_bullet_status()
        if hasattr(self, "tab_physics_gui") and self.tabs.currentWidget() == self.tab_physics_gui:
            self.tab_physics_gui.refresh_all_tab_info()
        if hasattr(self, "tab_extra"):
            self.tab_extra._sync_pmx_path()

    def showEvent(self, e):
        """ウィンドウ表示時にプラグイン状態を最新化およびパス同期"""
        super().showEvent(e)
        if hasattr(self, "tab_plugin"):
            self.tab_plugin.refresh_all_status()
        if hasattr(self, "tab_material"):
            self.tab_material._check_plugin_status()
        if hasattr(self, "tab_physics"):
            self.tab_physics._refresh_bullet_status()
        if hasattr(self, "tab_physics_gui") and self.tabs.currentWidget() == self.tab_physics_gui:
            self.tab_physics_gui.refresh_all_tab_info()
        if hasattr(self, "tab_extra"):
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
