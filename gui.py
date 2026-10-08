# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - モダン統合 GUI モジュール (PySide6 / PySide2 対応)

タブ型GUI
- タブ1: MMD → Maya (インポート)
- タブ2: モーション(VMD)
- タブ3: Maya → MMD (エクスポート)
- タブ4: HumanIK 管理
- タブ5: クリーンアップ
- 実行時ログウィンドウ (リアルタイム進捗表示)
"""

import os
import re
import sys
import importlib
import traceback

try:
    from PySide6.QtWidgets import (
        QWidget, QLabel, QLineEdit, QComboBox, QPushButton,
        QCheckBox, QButtonGroup, QRadioButton, QHBoxLayout,
        QVBoxLayout, QScrollArea, QFileDialog, QMessageBox,
        QTabWidget, QGroupBox, QFrame, QSizePolicy, QApplication,
        QDialog, QTextEdit, QProgressBar
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
        QDialog, QTextEdit, QProgressBar
    )
    from PySide2.QtCore import Qt, QSize
    from PySide2.QtGui import QDragEnterEvent, QDropEvent, QTextCursor, QFont
    try:
        from shiboken2 import wrapInstance
    except ImportError:
        wrapInstance = None

import maya.cmds as mc
from maya import mel
import maya.OpenMayaUI as omui

from . import pmxpaimaya, mayapaipmx, vmdpaimaya
from .asset.hik import dic_hik, kangkhaen

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
    def __init__(self, parent=None, title="実行ログ"):
        super(ExecutionLogDialog, self).__init__(parent)
        self.setWindowTitle(title)
        self.resize(620, 440)
        self.setMinimumSize(480, 320)
        self.setStyleSheet(MODERN_STYLE)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint | Qt.WindowStaysOnTopHint)

        self.success = False

        # レイアウト構築
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # ステータス表示
        self.lb_status = QLabel("処理を実行中...")
        self.lb_status.setStyleSheet("font-weight: bold; font-size: 15px; color: #52b7ff;")
        layout.addWidget(self.lb_status)

        # ログテキストエリア
        self.te_log = QTextEdit()
        self.te_log.setReadOnly(True)
        self.te_log.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.te_log)

        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setRange(0, 0) # 実行中はアニメーション
        layout.addWidget(self.progress_bar)

        # ボタングループ
        h_btn = QHBoxLayout()
        self.btn_copy = QPushButton("ログをコピー")
        self.btn_copy.setFixedWidth(120)
        self.btn_copy.clicked.connect(self._copy_log)
        h_btn.addWidget(self.btn_copy)

        h_btn.addStretch()

        self.btn_close = QPushButton("閉じる")
        self.btn_close.setFixedWidth(100)
        self.btn_close.setEnabled(False) # 実行中は無効化
        self.btn_close.clicked.connect(self.accept)
        h_btn.addWidget(self.btn_close)

        layout.addLayout(h_btn)

    def append_log(self, text):
        """ログを追加して最下部へスクロール"""
        cursor = self.te_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.te_log.setTextCursor(cursor)
        self.te_log.ensureCursorVisible()
        QApplication.processEvents()

    def _copy_log(self):
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.te_log.toPlainText())
            mc.inViewMessage(amg='<span style="color:#52b7ff;">MMD Tools for Maya:</span> ログをクリップボードにコピーしました。', pos='topCenter', fade=True)

    def run_task(self, task_func, *args, **kwargs):
        """タスクを実行し、ログをキャプチャ"""
        self.show()
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
            self.append_log("\n>>> 処理が正常に完了しました！\n")
            self.lb_status.setText("完了: 正常に処理が終了しました")
            self.lb_status.setStyleSheet("font-weight: bold; font-size: 15px; color: #2ecc71;")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
        except Exception as e:
            self.success = False
            err_trace = traceback.format_exc()
            self.append_log(f"\n[エラー] 処理中に問題が発生しました:\n{err_trace}\n")
            self.lb_status.setText("エラー: 処理が中断されました")
            self.lb_status.setStyleSheet("font-weight: bold; font-size: 15px; color: #ff7675;")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr
            self.btn_close.setEnabled(True)
            self.btn_close.setProperty("class", "primary")
            self.btn_close.setStyleSheet(self.styleSheet()) # スタイル再適用
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
        self.config_file = os.path.join(os.path.dirname(__file__), 'asset', 'khatangton1.txt')
        
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # 1. ファイル選択ゾーン (ドラッグ＆ドロップ対応)
        file_box = QGroupBox("モデルファイル (.pmx / .pmd / .x)")
        file_layout = QHBoxLayout(file_box)
        
        self.le_file_path = QLineEdit()
        self.le_file_path.setPlaceholderText("ファイルパスを入力、またはここにファイルをドラッグ＆ドロップ")
        self.le_file_path.textChanged.connect(self._on_file_changed)
        file_layout.addWidget(self.le_file_path)

        self.btn_browse = QPushButton("参照...")
        self.btn_browse.setFixedWidth(75)
        self.btn_browse.clicked.connect(self._browse_file)
        file_layout.addWidget(self.btn_browse)

        self.btn_clear_file = QPushButton("クリア")
        self.btn_clear_file.setFixedWidth(65)
        self.btn_clear_file.clicked.connect(self._clear_file)
        file_layout.addWidget(self.btn_clear_file)

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
        self.cbb_material.addItems(["マテリアルなし", "Blinn", "Phong", "Lambert", "StandardSurface (Maya 2022+)"])
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
                return
        except Exception:
            pass

        # デフォルト値
        self.le_scale.setText("8")
        self.cb_create_bones.setChecked(True)
        self.cb_create_physics.setChecked(True)
        self.cb_create_bs.setChecked(True)
        self.cbb_material.setCurrentIndex(4) # StandardSurface
        self.cb_close_on_finish.setChecked(False)
        self.cb_create_light.setChecked(True)
        self.cb_untone_mapped.setChecked(True)
        self.cb_enable_toon.setChecked(True)

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

    def _execute_import(self):
        file_path = self.le_file_path.text().strip()
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "エラー", "指定されたモデルファイルが存在しません。")
            return

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

        create_physics = self.cb_create_physics.isChecked()

        def full_import_task():
            import_func = getattr(pmxpaimaya, 'import_pmx', pmxpaimaya.sang)
            res = import_func(
                file_path, scale, split_poly, create_bs, create_bones, material_type, create_light, set_untone_mapped, enable_toon
            )
            # ボーン作成時、Aポーズの状態で剛体・Jointコライダーを同時生成 (ログダイアログ内で実行)
            if create_bones and create_physics and file_path.lower().endswith('.pmx'):
                try:
                    from .cpp_engine import xpbd_visualizer
                    xpbd_visualizer.create_rigidbody_visualizers(file_path, scale=scale)
                    print("[MMD Tools for Maya] 初期Aポーズにて剛体・Jointコライダーを自動生成しました。")
                except Exception as e:
                    print(f"[MMD Tools for Maya] 剛体自動生成のスキップ/エラー: {e}")
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
        self.config_file = os.path.join(os.path.dirname(__file__), 'asset', 'khatangton2.txt')

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
        self.btn_browse.setFixedWidth(75)
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
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # キャラクタモデルの選択
        model_box = QGroupBox("対象モデル選択")
        model_layout = QHBoxLayout(model_box)

        self.cbb_models = QComboBox()
        self.cbb_models.setEditable(True)
        model_layout.addWidget(self.cbb_models)

        self.btn_refresh = QPushButton("更新")
        self.btn_refresh.setFixedWidth(80)
        self.btn_refresh.clicked.connect(self._refresh_models)
        model_layout.addWidget(self.btn_refresh)

        self.btn_define = QPushButton("キャラクタ定義を作成")
        self.btn_define.setFixedWidth(150)
        self.btn_define.clicked.connect(self._define_hik)
        model_layout.addWidget(self.btn_define)

        layout.addWidget(model_box)

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

        # 3リグ生成アクション
        h_action = QHBoxLayout()
        h_action.addStretch()

        self.btn_create_rig = QPushButton("コントロールリグを作成")
        self.btn_create_rig.setProperty("class", "primary")
        self.btn_create_rig.setFixedHeight(44)
        self.btn_create_rig.setMinimumWidth(200)
        self.btn_create_rig.setEnabled(False)
        self.btn_create_rig.clicked.connect(self._create_control_rig)
        h_action.addWidget(self.btn_create_rig)

        layout.addLayout(h_action)

        self._refresh_models()

    def _refresh_models(self):
        self.cbb_models.clear()
        found_models = []
        try:
            for shape in mc.ls('*Shape', shapes=True) or []:
                transform = shape[:-5]
                if mc.objExists(transform) and 'MMD_model' in (mc.listAttr(transform) or []):
                    found_models.append(transform)
                    self.cbb_models.addItem(transform)
        except Exception:
            pass

    def _define_hik(self):
        model_name = self.cbb_models.currentText().strip()
        root_joint = None
        if mc.objExists(model_name):
            for candidate in [f"{model_name}_sentaa", f"{model_name}_subetenooya"]:
                if mc.objExists(candidate):
                    root_joint = candidate
                    break

        if not root_joint:
            QMessageBox.warning(self, "エラー", "該当するMMDジョイントのルートが見つかりません。")
            return

        # スクロールエリア内をクリア
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.btn_define.setEnabled(False)
        self.cbb_models.setEnabled(False)

        if not root_joint.startswith('|'):
            root_joint = '|' + root_joint

        current_hik_nodes = set(mc.ls(type='HIKCharacterNode') or [])
        mel.eval('hikCreateDefinition')
        new_nodes = set(mc.ls(type='HIKCharacterNode') or []) - current_hik_nodes
        hik_node = new_nodes.pop() if new_nodes else 'Character1'
        hik_node = mc.rename(hik_node, f"HIK_{model_name}")

        all_joints = [root_joint] + (mc.listRelatives(root_joint, allDescendents=True, fullPath=True) or [])
        mapped_dict = {}

        for bone_id, bone_info in dic_hik.items():
            label_text, regex_name = bone_info[0], bone_info[1]
            h_row = QHBoxLayout()

            lb_name = QLabel(label_text)
            lb_name.setFixedWidth(100)
            h_row.addWidget(lb_name)

            # ジョイント名を検索
            matched_joint = None
            for j_path in all_joints:
                if re.findall(rf'\|{regex_name}$', j_path):
                    matched_joint = j_path
                    mapped_dict[bone_id] = j_path
                    break
            else:
                # 指の末端などのフォールバック
                if bone_id >= 51 and bone_id not in range(54, 94, 4):
                    prev_joint = mapped_dict.get(bone_id - 1)
                    if prev_joint:
                        children = mc.listRelatives(prev_joint, fullPath=True) or []
                        if len(children) == 1:
                            matched_joint = children[0]
                            mapped_dict[bone_id] = matched_joint

            if matched_joint:
                mel.eval(f'hikSetCharacterObject {matched_joint} {hik_node} {bone_id} 0')
                btn_sel = QPushButton("選択")
                btn_sel.setFixedSize(50, 28)
                le_joint = QLineEdit(matched_joint)
                le_joint.setReadOnly(True)
                btn_sel.clicked.connect(lambda _, j=matched_joint: mc.select(j))
                h_row.addWidget(btn_sel)
                h_row.addWidget(le_joint)
            else:
                lb_none = QLabel("未検出")
                lb_none.setStyleSheet("color: #ff7675;")
                h_row.addWidget(lb_none)

            h_row.addStretch()
            self.scroll_layout.addLayout(h_row)

        kangkhaen(mapped_dict) # Tポーズ（腕水平）への展開処理
        self.btn_create_rig.setEnabled(True)
        mc.inViewMessage(amg='<span style="color:#52b7ff;">HumanIK:</span> キャラクタ定義が完了しました。', pos='topCenter', fade=True)

    def _create_control_rig(self):
        try:
            mel.eval('hikCreateControlRig')
            mc.inViewMessage(amg='<span style="color:#52b7ff;">HumanIK:</span> コントロールリグを作成しました。', pos='topCenter', fade=True)
            if self.parent_window:
                self.parent_window.close()
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"コントロールリグの作成に失敗しました:\n{str(e)}")

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
        lbl_cam = QLabel("カメラモーション (.vmd) ※省略可能:")
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

        # 空白状態も含めて正確に保存
        mc.optionVar(sv=("MMDToolsForMaya_LastModelVmdPath", path1 if valid1 else ""))
        mc.optionVar(sv=("MMDToolsForMaya_LastCameraVmdPath", path2 if valid2 else ""))
        mc.optionVar(sv=("MMDToolsForMaya_LastAudioPath", path3 if valid3 else ""))

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
            from . import vmd_analyzer
            if file_path and os.path.exists(file_path):
                report = vmd_analyzer.analyze_vmd(file_path)
                print(report.generate_summary_text())
        except Exception:
            pass

        log_dialog = ExecutionLogDialog(self.parent_window or self, title="VMDモーションインポート実行ログ")
        import_func = vmdpaimaya.import_vmd
        success = log_dialog.run_task(import_func, file_path, camera_path, audio_path, scale, target_model)

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
        param_box = QGroupBox("XPBD 物理演算パラメータ")
        param_layout = QVBoxLayout(param_box)

        # 重力設定
        h_grav = QHBoxLayout()
        h_grav.addWidget(QLabel("重力加速度 (Y):"))
        self.le_gravity = QLineEdit("-980.0")
        self.le_gravity.setFixedWidth(80)
        h_grav.addWidget(self.le_gravity)
        h_grav.addWidget(QLabel("cm/s² (Maya標準単位)"))
        h_grav.addStretch()
        param_layout.addLayout(h_grav)

        # サブステップ数
        h_sub = QHBoxLayout()
        h_sub.addWidget(QLabel("サブステップ数:"))
        self.le_substeps = QLineEdit("10")
        self.le_substeps.setFixedWidth(80)
        h_sub.addWidget(self.le_substeps)
        h_sub.addWidget(QLabel("(推奨: 8～15、高いほど高精度・安定)"))
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
        self.le_start_frame.setFixedWidth(60)
        self.le_start_frame.setEnabled(False)
        h_custom_frame.addWidget(self.le_start_frame)

        h_custom_frame.addWidget(QLabel("終了フレーム:"))
        self.le_end_frame = QLineEdit()
        self.le_end_frame.setFixedWidth(60)
        self.le_end_frame.setEnabled(False)
        h_custom_frame.addWidget(self.le_end_frame)
        h_custom_frame.addStretch()
        param_layout.addLayout(h_custom_frame)

        layout.addWidget(param_box)
        layout.addStretch()

        # 実行ボタンエリア
        v_action = QVBoxLayout()

        # 上段: 物理ベイク実行ボタン (Bullet と XPBD を横並び)
        h_bake_action = QHBoxLayout()

        self.btn_bullet_bake = QPushButton("Bullet 物理ベイク実行 (MMD本家仕様)")
        self.btn_bullet_bake.setFixedHeight(44)
        self.btn_bullet_bake.setStyleSheet("QPushButton { background-color: #2e6b9e; color: #fff; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #3b88c7; } QPushButton:disabled { background-color: #444; color: #888; }")
        self.btn_bullet_bake.clicked.connect(self._execute_bullet_bake)
        h_bake_action.addWidget(self.btn_bullet_bake)

        self.btn_bake = QPushButton("XPBD 物理ベイク実行")
        self.btn_bake.setProperty("class", "primary")
        self.btn_bake.setFixedHeight(44)
        self.btn_bake.clicked.connect(self._execute_bake)
        h_bake_action.addWidget(self.btn_bake)

        v_action.addLayout(h_bake_action)

        # 下段: ユーティリティ操作 (再吸着とキーフレームクリアを横並び)
        h_sub_action = QHBoxLayout()

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

    def _is_bullet_available(self):
        """Bullet物理モジュール (bullet_engine) が存在し利用可能か判定"""
        try:
            bullet_dir = os.path.join(os.path.dirname(__file__), "bullet_engine")
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
            except ValueError:
                QMessageBox.warning(self, "エラー", "開始・終了フレーム番号を正しく入力してください。")
                return

        def run_bullet_task():
            from .bullet_engine import bullet_maya_bridge
            bridge = bullet_maya_bridge.BulletMayaBridge(pmx_path=pmx_path, scale=scale)
            bridge.bake_simulation(
                start_frame=start_frame,
                end_frame=end_frame,
                sub_steps=substeps
            )

        log_dialog = ExecutionLogDialog(self.parent_window or self, title="Bullet 物理演算ベイク実行ログ (MMD本家仕様)")
        success = log_dialog.run_task(run_bullet_task)
        if success:
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
            except ValueError:
                QMessageBox.warning(self, "エラー", "開始・終了フレーム番号を正しく入力してください。")
                return

        def run_physics_task():
            from .cpp_engine import xpbd_maya_bridge
            self.bridge = xpbd_maya_bridge.XpbdMayaBridge(scale=scale)
            ok = self.bridge.initialize_from_pmx(pmx_path)
            if not ok:
                raise RuntimeError("PMX剛体データの読み込みに失敗しました。")
            self.bridge.bake_simulation(
                start_frame=start_frame,
                end_frame=end_frame,
                gravity_y=gravity,
                substeps=substeps
            )

        log_dialog = ExecutionLogDialog(self.parent_window or self, title="XPBD 物理演算ベイク実行ログ")
        success = log_dialog.run_task(run_physics_task)
        if success:
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
            from .cpp_engine import xpbd_maya_bridge
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
            from .cpp_engine import xpbd_visualizer
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

# ==============================================================================
# MMD削除・クリーンアップタブ
# ==============================================================================
class CleanupTabWidget(QWidget):
    """シーン内のMMD要素の一括削除およびアニメーション初期化を行うクリーンアップタブ"""
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

        self.cb_delete_lights = QCheckBox("MMDライトも削除する (mmd_lighting_grp)")
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

        # アニメーション初期化ボタン
        self.btn_clear_anim = QPushButton("アニメーションのみ初期化 (モデル・リグは残して初期ポーズ復元)")
        self.btn_clear_anim.setFixedHeight(44)
        self.btn_clear_anim.setStyleSheet(
            "QPushButton { background-color: #3b3a28; color: #fff8cc; border: 1px solid #66633a; border-radius: 4px; font-weight: bold; font-size: 14px; }"
            "QPushButton:hover { background-color: #4d4b32; color: #ffffff; border-color: #99944a; }"
            "QPushButton:pressed { background-color: #2b2a1a; }"
        )
        self.btn_clear_anim.clicked.connect(self._execute_clear_anim_only)
        act_layout.addWidget(self.btn_clear_anim)

        # MMD全削除ボタン
        self.btn_delete_all = QPushButton("MMD全削除を実行 (モデル / リグ / カメラ / マテリアル)")
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
            "アニメーション初期化の確認",
            f"対象 ({target_label}) のキーフレームをすべて削除し、初期ポーズへ復元しますか？\n（メッシュやスケルトンは削除されません）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return

        try:
            b_cnt, m_cnt = vmdpaimaya.clear_model_animation(target_model)
            mc.inViewMessage(
                amg=f'<span style="color:#52b7ff;">MMD Tools for Maya:</span> アニメーションを初期化しました (ボーン: {b_cnt}, モーフ: {m_cnt})。',
                pos='topCenter',
                fade=True
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"アニメーション初期化中にエラーが発生しました:\n{e}")

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
            items.append("MMDライト (mmd_lighting_grp)")
        if delete_unused:
            items.append("未使用マテリアル (Delete Unused Nodes)")

        msg = f"対象 ({target_label}) および以下の項目を完全に削除しますか？\n\n・" + "\n・".join(items) + "\n\n※この操作は取り消せません。"

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
            for phys_grp in ["MMD_RigidBody_Visualizers", "MMD_Bullet_Physics_Rig", "MMD_BulletSolver"]:
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
# メインウィンドウ (タブ統合)
# ==============================================================================
class MmdMayaMainWindow(QWidget):
    """MMD Tools for Maya のメイン統合ウィンドウ"""
    def __init__(self, parent=None):
        if parent is None:
            parent = get_maya_main_window()
        super(MmdMayaMainWindow, self).__init__(parent)
        
        self.setWindowTitle("MMD Tools for Maya")

        # メインウィンドウサイズ設定 (視認性向上・ボタン文字見切れ防止のワイドレイアウト)
        self.resize(880, 820)
        self.setMinimumSize(820, 640)
        # Mayaの子ウィンドウとして独立させつつ前面表示
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(MODERN_STYLE)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # タブコンテナ
        self.tabs = QTabWidget()
        self.tab_import = ImportTabWidget(self)
        self.tab_vmd = VmdImportTabWidget(self)
        self.tab_physics = PhysicsTabWidget(self)
        self.tab_export = ExportTabWidget(self)
        self.tab_hik = HikTabWidget(self)
        self.tab_cleanup = CleanupTabWidget(self)

        self.tabs.addTab(self.tab_import, "MMD → Maya (インポート)")
        self.tabs.addTab(self.tab_vmd, "モーション (VMD)")
        self.tabs.addTab(self.tab_physics, "物理演算 (XPBD)")
        self.tabs.addTab(self.tab_export, "Maya → MMD (エクスポート)")
        self.tabs.addTab(self.tab_hik, "HumanIK 管理")
        self.tabs.addTab(self.tab_cleanup, "MMD削除 (クリーンアップ)")

        main_layout.addWidget(self.tabs)

        # フッタークレジット
        footer = QLabel("MMD Tools for Maya v1.0.0 | Developer: Hina33")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #777; font-size: 13px; padding: 4px;")
        main_layout.addWidget(footer)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()

def show_ui():
    """UIウィンドウを表示します（インスタンス保持 & 最前面化）"""
    global _main_window_instance
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    if _main_window_instance is not None:
        try:
            _main_window_instance.close()
            _main_window_instance.deleteLater()
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
