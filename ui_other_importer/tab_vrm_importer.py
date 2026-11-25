# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - VRMインポート専用タブウィジェット
VRMアバターモデルのドラッグ＆ドロップ、メタデータおよびサムネイル表示、
マテリアル種別選択、Z軸座標系反転、インポート実行制御を提供します。
"""

import os
import sys

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QGroupBox, QCheckBox, QDoubleSpinBox,
        QProgressBar, QTextEdit, QFileDialog, QMessageBox,
        QScrollArea, QFrame, QSplitter, QComboBox
    )
    PYSIDE_VER = 6
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt, Signal
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QGroupBox, QCheckBox, QDoubleSpinBox,
        QProgressBar, QTextEdit, QFileDialog, QMessageBox,
        QScrollArea, QFrame, QSplitter, QComboBox
    )
    PYSIDE_VER = 2

import maya.cmds as mc

try:
    from ..other_converters.vrm_importer import import_vrm_model, parse_vrm_metadata
except Exception:
    try:
        from other_converters.vrm_importer import import_vrm_model, parse_vrm_metadata
    except Exception:
        import_vrm_model = None
        parse_vrm_metadata = None


class VrmDropAreaLineEdit(QLineEdit):
    """
    ドラッグ＆ドロップによるVRMファイル受け入れをサポートする入力欄
    """
    fileDropped = Signal(str)

    def __init__(self, parent=None):
        super(VrmDropAreaLineEdit, self).__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("VRMファイルをここにドラッグ＆ドロップ、または右の参照ボタンを押下")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                f_path = url.toLocalFile()
                if f_path.lower().endswith(".vrm"):
                    event.acceptProposedAction()
                    return
        super(VrmDropAreaLineEdit, self).dragEnterEvent(event)

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        for url in urls:
            f_path = url.toLocalFile()
            if f_path.lower().endswith(".vrm"):
                self.setText(f_path)
                self.fileDropped.emit(f_path)
                event.acceptProposedAction()
                return
        super(VrmDropAreaLineEdit, self).dropEvent(event)


class TabVrmImporterWidget(QWidget):
    """
    VRMインポート機能を提供するUIウィジェット
    """

    def __init__(self, parent=None):
        super(TabVrmImporterWidget, self).__init__(parent)
        self.current_metadata = {}
        self._init_ui()

    def _init_ui(self):
        """UIコンポーネントの構築"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)

        # -------------------------------------------------------------
        # 左ペイン: ファイル選択 & モデルメタ情報プレビュー
        # -------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(8)

        # ファイル選択グループ
        grp_file = QGroupBox("VRMファイル選択")
        file_layout = QVBoxLayout(grp_file)
        file_layout.setSpacing(6)

        h_file = QHBoxLayout()
        self.le_file_path = VrmDropAreaLineEdit()
        self.le_file_path.fileDropped.connect(self._on_file_selected)
        self.le_file_path.textChanged.connect(self._on_text_changed)

        btn_browse = QPushButton("参照...")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._browse_vrm_file)

        h_file.addWidget(self.le_file_path)
        h_file.addWidget(btn_browse)
        file_layout.addLayout(h_file)
        left_layout.addWidget(grp_file)

        # モデル情報プレビューカード
        grp_info = QGroupBox("モデル情報 (VRMメタデータ)")
        info_layout = QVBoxLayout(grp_info)
        info_layout.setSpacing(6)

        # サムネイルプレビュー
        h_thumb = QHBoxLayout()
        self.lbl_thumbnail = QLabel()
        self.lbl_thumbnail.setFixedSize(140, 140)
        self.lbl_thumbnail.setStyleSheet(
            "background-color: #1a1a1a; border: 1px dashed #555555; border-radius: 6px;"
        )
        self.lbl_thumbnail.setAlignment(Qt.AlignCenter)
        self.lbl_thumbnail.setText("サムネイルなし")
        h_thumb.addStretch()
        h_thumb.addWidget(self.lbl_thumbnail)
        h_thumb.addStretch()
        info_layout.addLayout(h_thumb)

        self.lbl_title = QLabel("タイトル: (未選択)")
        self.lbl_title.setStyleSheet("font-weight: bold; color: #52b7ff; font-size: 13px;")
        info_layout.addWidget(self.lbl_title)

        self.lbl_author = QLabel("作者: -")
        self.lbl_author.setStyleSheet("color: #cccccc;")
        info_layout.addWidget(self.lbl_author)

        self.lbl_spec = QLabel("VRM仕様: -")
        self.lbl_spec.setStyleSheet("color: #77ddaa;")
        info_layout.addWidget(self.lbl_spec)

        self.lbl_version = QLabel("バージョン: -")
        self.lbl_version.setStyleSheet("color: #888888;")
        info_layout.addWidget(self.lbl_version)

        self.lbl_license = QLabel("ライセンス: -")
        self.lbl_license.setStyleSheet("color: #ffaa55;")
        self.lbl_license.setWordWrap(True)
        info_layout.addWidget(self.lbl_license)

        self.lbl_counts = QLabel("構成: メッシュ 0 / ボーン 0 / モーフ 0")
        self.lbl_counts.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        info_layout.addWidget(self.lbl_counts)

        info_layout.addStretch()
        left_layout.addWidget(grp_info)

        # -------------------------------------------------------------
        # 右ペイン: インポート設定 & 実行操作
        # -------------------------------------------------------------
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)

        # 設定グループ
        grp_opts = QGroupBox("インポート設定オプション")
        opts_layout = QVBoxLayout(grp_opts)
        opts_layout.setSpacing(8)

        self.chk_mesh = QCheckBox("ポリゴンメッシュを生成する")
        self.chk_mesh.setChecked(True)
        opts_layout.addWidget(self.chk_mesh)

        self.chk_materials = QCheckBox("マテリアルおよびテクスチャを抽出して適用する")
        self.chk_materials.setChecked(True)
        opts_layout.addWidget(self.chk_materials)

        self.chk_bones = QCheckBox("ボーン（Humanoidスケルトン）を構築する")
        self.chk_bones.setChecked(True)
        opts_layout.addWidget(self.chk_bones)

        self.chk_skinning = QCheckBox("スキニング（ウェイトバインド）を設定する")
        self.chk_skinning.setChecked(True)
        opts_layout.addWidget(self.chk_skinning)

        self.chk_morphs = QCheckBox("表情モーフ（ブレンドシェイプ）を構築する")
        self.chk_morphs.setChecked(True)
        opts_layout.addWidget(self.chk_morphs)

        # 座標系オプション
        self.chk_invert_z = QCheckBox("MMD座標系に合わせる（Z軸反転・正面向き統一）")
        self.chk_invert_z.setChecked(True)
        self.chk_invert_z.setToolTip("MMDモデルと同じ正面向き（+Z）となるよう頂点・ボーンのZ座標を変換します。")
        opts_layout.addWidget(self.chk_invert_z)

        # ライティング・地面影オプション
        self.chk_lighting = QCheckBox("ライト（MMD標準照明グループ）を作成する")
        self.chk_lighting.setChecked(True)
        self.chk_lighting.setToolTip("MMD標準の平行光と環境光を生成し、適正な陰影を表現します。")
        opts_layout.addWidget(self.chk_lighting)

        self.chk_ground_shadow = QCheckBox("地面影（シャドウキャッチャー）を作成する")
        self.chk_ground_shadow.setChecked(True)
        self.chk_ground_shadow.setToolTip("地面プレーン上にモデルの落ち影のみを自然に描画します。")
        opts_layout.addWidget(self.chk_ground_shadow)

        # マテリアル種別選択
        h_mat = QHBoxLayout()
        h_mat.addWidget(QLabel("マテリアル種別:"))
        self.combo_material = QComboBox()
        self.combo_material.addItem("MMD Toon Shader (推奨)", "mmdToonShader")
        self.combo_material.addItem("StandardSurface (Maya 2022+)", "standardSurface")
        self.combo_material.addItem("Lambert (標準)", "lambert")
        self.combo_material.setCurrentIndex(0)
        h_mat.addWidget(self.combo_material)
        h_mat.addStretch()
        opts_layout.addLayout(h_mat)

        # スケール設定
        h_scale = QHBoxLayout()
        h_scale.addWidget(QLabel("スケール倍率 (glTFメートル → Mayaセンチメートル):"))
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(0.01, 10000.0)
        self.spin_scale.setValue(100.0)
        self.spin_scale.setSingleStep(10.0)
        self.spin_scale.setDecimals(2)
        h_scale.addWidget(self.spin_scale)
        h_scale.addStretch()
        opts_layout.addLayout(h_scale)

        right_layout.addWidget(grp_opts)

        # 実行ボタン
        self.btn_import = QPushButton("VRMモデルをMayaへインポート")
        self.btn_import.setFixedHeight(42)
        self.btn_import.setStyleSheet("""
            QPushButton {
                background-color: #1e6fa8;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
                border: 1px solid #3399dd;
            }
            QPushButton:hover {
                background-color: #288bc9;
                border: 1px solid #77ccff;
            }
            QPushButton:pressed {
                background-color: #164f77;
            }
        """)
        self.btn_import.clicked.connect(self._run_import)
        right_layout.addWidget(self.btn_import)

        # 進行インジケータ
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        # 実行ログエリア
        grp_log = QGroupBox("実行ステータスログ")
        log_layout = QVBoxLayout(grp_log)
        self.te_log = QTextEdit()
        self.te_log.setReadOnly(True)
        self.te_log.setStyleSheet("background-color: #1a1a1a; color: #a0ffa0; font-family: Consolas, monospace; font-size: 11px;")
        self.te_log.setFixedHeight(160)
        log_layout.addWidget(self.te_log)
        right_layout.addWidget(grp_log)

        right_layout.addStretch()
        right_scroll.setWidget(right_widget)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)

        main_layout.addWidget(splitter)

    def _browse_vrm_file(self):
        """ファイル選択ダイアログの表示"""
        f_path, _ = QFileDialog.getOpenFileName(
            self,
            "VRMファイルを選択",
            "",
            "VRMモデル (*.vrm);;すべてのファイル (*.*)"
        )
        if f_path:
            self.le_file_path.setText(f_path)
            self._on_file_selected(f_path)

    def _on_text_changed(self, text):
        """テキスト入力欄変更時のハンドラ"""
        clean_path = text.strip().strip('"').strip("'")
        if os.path.isfile(clean_path) and clean_path.lower().endswith(".vrm"):
            self._on_file_selected(clean_path)

    def _on_file_selected(self, file_path):
        """VRMファイルが確定した際のメタデータ抽出と表示更新"""
        if not file_path or not os.path.isfile(file_path):
            return

        if parse_vrm_metadata:
            meta = parse_vrm_metadata(file_path)
            self.current_metadata = meta

            self.lbl_title.setText(f"タイトル: {meta.get('title', '-')}")
            self.lbl_author.setText(f"作者: {meta.get('author', '-')}")
            spec_ver = meta.get("vrm_spec", "0.x")
            self.lbl_spec.setText(f"VRM仕様: VRM {spec_ver}")
            self.lbl_version.setText(f"バージョン: {meta.get('version', '-') if meta.get('version') else '(未設定)'}")
            self.lbl_license.setText(f"ライセンス: {meta.get('license', '-') if meta.get('license') else '(未設定)'}")
            self.lbl_counts.setText(
                f"構成: メッシュ {meta.get('mesh_count', 0)} / ボーン {meta.get('bone_count', 0)} / モーフ {meta.get('morph_count', 0)}"
            )

            # サムネイル画像の読み込み
            thumb_bytes = meta.get("thumbnail_bytes")
            if thumb_bytes:
                pix = QtGui.QPixmap()
                pix.loadFromData(thumb_bytes)
                if not pix.isNull():
                    scaled_pix = pix.scaled(130, 130, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.lbl_thumbnail.setPixmap(scaled_pix)
                else:
                    self.lbl_thumbnail.setText("画像読込失敗")
            else:
                self.lbl_thumbnail.setText("サムネイルなし")

            self._log_message(f"VRMファイルを認識しました: {os.path.basename(file_path)} (VRM {spec_ver})")

    def _run_import(self):
        """インポート処理の実行"""
        file_path = self.le_file_path.text().strip().strip('"').strip("'")
        if not file_path or not os.path.isfile(file_path):
            QMessageBox.warning(self, "エラー", "有効なVRMファイルを選択してください。")
            return

        if not import_vrm_model:
            QMessageBox.critical(self, "エラー", "VRMインポートエンジンがロードされていません。")
            return

        mat_type = self.combo_material.currentData()

        options = {
            "scale": self.spin_scale.value(),
            "invert_z": self.chk_invert_z.isChecked(),
            "material_type": mat_type,
            "import_mesh": self.chk_mesh.isChecked(),
            "import_materials": self.chk_materials.isChecked(),
            "import_bones": self.chk_bones.isChecked(),
            "import_skinning": self.chk_skinning.isChecked(),
            "import_morphs": self.chk_morphs.isChecked(),
            "create_lighting": self.chk_lighting.isChecked(),
            "create_ground_shadow": self.chk_ground_shadow.isChecked(),
        }

        self.btn_import.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(20)
        self._log_message(f"インポートを開始します: {file_path}")
        self._log_message(f"マテリアル種別: {mat_type} / Z軸反転: {self.chk_invert_z.isChecked()}")
        QtWidgets.QApplication.processEvents()

        try:
            self.progress_bar.setValue(50)
            res_node = import_vrm_model(file_path, options)
            self.progress_bar.setValue(100)
            self._log_message(f"インポートが正常に終了しました。生成ノード: '{res_node}'")

            mc.inViewMessage(
                amg=f"<span style=\"color:#88ff88;\">VRMインポート終了: {os.path.basename(file_path)}</span>",
                pos='topCenter', fade=True, fst=2500
            )
            QMessageBox.information(self, "終了", f"VRMモデルのインポートが終了しました。\n生成ノード: {res_node}")
        except Exception as e:
            import traceback
            err_details = traceback.format_exc()
            self._log_message(f"エラーが発生しました:\n{err_details}")
            QMessageBox.critical(self, "インポートエラー", f"VRMインポート中にエラーが発生しました:\n{e}")
        finally:
            self.btn_import.setEnabled(True)
            self.progress_bar.setVisible(False)

    def _log_message(self, text):
        """ログ欄へメッセージを追記"""
        self.te_log.append(f">> {text}")


# 後方互換クラス名エイリアス
VrmImporterTabWidget = TabVrmImporterWidget

