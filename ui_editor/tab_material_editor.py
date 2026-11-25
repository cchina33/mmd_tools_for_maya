# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MMD Model Editor 材質管理タブモジュール
MMDモデルの材質一覧表示およびアトリビュート編集機能を提供します。
"""

import os
import sys
import maya.cmds as mc
import maya.mel as mel

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QSplitter, QScrollArea, QGroupBox, QCheckBox, QDoubleSpinBox,
        QComboBox, QTextEdit, QFileDialog, QColorDialog, QFrame,
        QAbstractItemView
    )
    from PySide6.QtGui import QColor, QBrush, QPixmap, QPainter
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt, Signal
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QSplitter, QScrollArea, QGroupBox, QCheckBox, QDoubleSpinBox,
        QComboBox, QTextEdit, QFileDialog, QColorDialog, QFrame,
        QAbstractItemView
    )
    from PySide2.QtGui import QColor, QBrush, QPixmap, QPainter


def _safe_set_double3(node, attr, r, g, b):
    """入力接続およびロック状態を確認し、確実に double3 アトリビュートを設定"""
    if not mc.attributeQuery(attr, node=node, exists=True):
        return False
    plug = f"{node}.{attr}"
    if mc.getAttr(plug, lock=True):
        return False
    conns = mc.listConnections(plug, source=True, destination=False)
    if conns:
        return False
    for sub in ["R", "G", "B", "X", "Y", "Z"]:
        sub_attr = f"{attr}{sub}"
        if mc.attributeQuery(sub_attr, node=node, exists=True):
            if mc.listConnections(f"{node}.{sub_attr}", source=True, destination=False):
                return False
    try:
        mc.setAttr(plug, float(r), float(g), float(b), typ="double3")
        return True
    except Exception:
        return False


def _safe_set_float(node, attr, val):
    """入力接続およびロック状態を確認し、確実に float アトリビュートを設定"""
    if not mc.attributeQuery(attr, node=node, exists=True):
        return False
    plug = f"{node}.{attr}"
    if mc.getAttr(plug, lock=True):
        return False
    if mc.listConnections(plug, source=True, destination=False):
        return False
    try:
        mc.setAttr(plug, float(val))
        return True
    except Exception:
        return False


def _safe_set_bool(node, attr, val):
    """入力接続およびロック状態を確認し、確実に bool アトリビュートを設定"""
    if not mc.attributeQuery(attr, node=node, exists=True):
        return False
    plug = f"{node}.{attr}"
    if mc.getAttr(plug, lock=True):
        return False
    if mc.listConnections(plug, source=True, destination=False):
        return False
    try:
        mc.setAttr(plug, bool(val))
        return True
    except Exception:
        return False


def _find_upstream_file_nodes(shader_node):
    """
    シェーダーノードの上流に接続されているすべての file ノードを再帰探索して収集
    """
    file_nodes = set()
    visited = set()

    def _traverse(node):
        if not node or node in visited:
            return
        visited.add(node)

        if mc.nodeType(node) == "file":
            file_nodes.add(node)
            return

        inputs = mc.listConnections(node, source=True, destination=False) or []
        for inp in set(inputs):
            _traverse(inp)

    # カラー系および透過系アトリビュートから探索
    color_attrs = ["color", "diffuseColor", "baseColor", "transparency", "opacity"]
    for attr in color_attrs:
        if mc.attributeQuery(attr, node=shader_node, exists=True):
            conns = mc.listConnections(f"{shader_node}.{attr}", source=True, destination=False) or []
            for c in conns:
                _traverse(c)

    # 見つからない場合はヒストリからフォールバック探索
    if not file_nodes:
        history = mc.listHistory(shader_node) or []
        for h in history:
            if mc.nodeType(h) == "file":
                file_nodes.add(h)

    return list(file_nodes)


class ColorChipButton(QPushButton):
    """色プレビューおよびクリックでカラーダイアログを開くカスタムボタン"""
    colorChanged = Signal(QColor)

    def __init__(self, initial_color=None, parent=None):
        super(ColorChipButton, self).__init__(parent)
        self._color = initial_color or QColor(255, 255, 255)
        self.setFixedHeight(24)
        self.setMinimumWidth(36)
        self._update_style()
        self.clicked.connect(self._choose_color)

    def get_color(self):
        """現在の色を取得"""
        return self._color

    def set_color(self, color):
        """色を設定してスタイルを更新"""
        if isinstance(color, (tuple, list)):
            if len(color) >= 3:
                r = int(max(0.0, min(1.0, color[0])) * 255)
                g = int(max(0.0, min(1.0, color[1])) * 255)
                b = int(max(0.0, min(1.0, color[2])) * 255)
                self._color = QColor(r, g, b)
        elif isinstance(color, QColor):
            self._color = color
        self._update_style()

    def _update_style(self):
        """ボタンの背景色を描画更新"""
        hex_col = self._color.name()
        # 視認性の高い枠線付き背景スタイル
        self.setStyleSheet(
            f"QPushButton {{ background-color: {hex_col}; border: 1px solid #777; border-radius: 3px; }}"
            f"QPushButton:hover {{ border: 2px solid #52b7ff; }}"
        )

    def _choose_color(self):
        """Maya標準カラーエディタまたはスタイリング済みカラーダイアログを表示"""
        # Maya標準カラーエディタを優先試行（スポイト機能・色空間対応）
        try:
            curr_r = self._color.redF()
            curr_g = self._color.greenF()
            curr_b = self._color.blueF()

            res = mc.colorEditor(rgbValue=(curr_r, curr_g, curr_b))
            parts = res.split()
            if len(parts) >= 4:
                # 確定された場合（末尾フラグが "1"）
                if parts[3] == "1":
                    r = float(parts[0])
                    g = float(parts[1])
                    b = float(parts[2])
                    new_col = QColor(
                        int(max(0.0, min(1.0, r)) * 255),
                        int(max(0.0, min(1.0, g)) * 255),
                        int(max(0.0, min(1.0, b)) * 255)
                    )
                    self.set_color(new_col)
                    self.colorChanged.emit(self._color)
                return
        except Exception:
            pass

        # フォールバック: QColorDialog を専用スタイルで表示（OK・キャンセルボタン白潰れを抑止）
        dialog = QColorDialog(self._color, self)
        dialog.setWindowTitle("色を選択")
        dialog.setStyleSheet("""
            QColorDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QPushButton {
                min-width: 80px;
                min-height: 26px;
                padding: 4px 14px;
                background-color: #3b3b3b;
                color: #ffffff;
                border: 1px solid #666666;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4c4c4c;
                border: 1px solid #52b7ff;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #555555;
            }
            QLabel {
                color: #e0e0e0;
            }
        """)
        if dialog.exec_():
            chosen = dialog.selectedColor()
            if chosen.isValid():
                self.set_color(chosen)
                self.colorChanged.emit(self._color)


class MaterialEditorTabWidget(QWidget):
    """
    MMD Model Editor 材質管理タブウィジェット
    Mayaシーン内の材質を一覧表示し、詳細パラメータの編集と双方向同期を行います。
    """

    def __init__(self, parent=None):
        super(MaterialEditorTabWidget, self).__init__(parent)
        self.current_model = None
        self.material_data_list = []
        self.selected_mat_index = -1
        self._block_signals = False

        self._init_ui()

    def _init_ui(self):
        """ユーザーインターフェースの構築"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 水平スプリッター (左: 材質リスト、右: 詳細パラメータ)
        splitter = QSplitter(Qt.Horizontal)

        # -------------------------------------------------------------
        # 左ペイン: 材質一覧リスト・検索・選択連動
        # -------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(6)

        # 検索フィルターバー
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)
        search_label = QLabel("絞り込み:")
        search_label.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText("材質名 / ノード名で検索...")
        self.le_search.textChanged.connect(self._filter_material_list)
        btn_clear_search = QPushButton("クリア")
        btn_clear_search.setFixedWidth(54)
        btn_clear_search.clicked.connect(lambda: self.le_search.clear())

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.le_search)
        search_layout.addWidget(btn_clear_search)
        left_layout.addLayout(search_layout)

        # 材質テーブル
        self.table_materials = QTableWidget()
        self.table_materials.setColumnCount(5)
        self.table_materials.setHorizontalHeaderLabels(["No", "材質名 (日本語)", "英語名", "シェーダーノード", "色"])
        self.table_materials.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_materials.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_materials.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_materials.verticalHeader().setVisible(False)
        self.table_materials.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_materials.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_materials.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_materials.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_materials.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_materials.setStyleSheet(
            "QTableWidget { background-color: #222; border: 1px solid #444; border-radius: 4px; gridline-color: #333; }"
            "QTableWidget::item:selected { background-color: #2c5d88; color: #ffffff; }"
            "QHeaderView::section { background-color: #2e2e2e; color: #bbb; padding: 4px; border: 1px solid #3c3c3c; font-weight: bold; }"
        )
        self.table_materials.itemSelectionChanged.connect(self._on_table_selection_changed)
        left_layout.addWidget(self.table_materials)

        # ビューポート連動ボタン群
        btn_grid = QVBoxLayout()
        btn_grid.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(4)
        self.btn_select_mesh = QPushButton("該当メッシュ / 面を選択")
        self.btn_select_mesh.setToolTip("選択中の材質がアサインされているメッシュまたはポリゴン面をビューポート上で選択します。")
        self.btn_select_mesh.clicked.connect(self._select_assigned_geometry)
        self.btn_find_from_vp = QPushButton("選択から材質を特定")
        self.btn_find_from_vp.setToolTip("現在ビューポートで選択されているメッシュや面から、該当する材質をリスト上で選択します。")
        self.btn_find_from_vp.clicked.connect(self._find_material_from_viewport)
        row1.addWidget(self.btn_select_mesh)
        row1.addWidget(self.btn_find_from_vp)

        row2 = QHBoxLayout()
        row2.setSpacing(4)
        self.btn_select_shader = QPushButton("シェーダーノードを選択")
        self.btn_select_shader.setToolTip("アトリビュートエディタ等で直接操作できるよう、Mayaのシェーダーノードを選択します。")
        self.btn_select_shader.clicked.connect(self._select_shader_node)
        self.btn_refresh = QPushButton("リスト再取得")
        self.btn_refresh.setToolTip("シーンの最新状態を再読込して材質リストを更新します。")
        self.btn_refresh.clicked.connect(self.refresh_materials)
        row2.addWidget(self.btn_select_shader)
        row2.addWidget(self.btn_refresh)

        btn_grid.addLayout(row1)
        btn_grid.addLayout(row2)
        left_layout.addLayout(btn_grid)

        splitter.addWidget(left_widget)

        # -------------------------------------------------------------
        # 右ペイン: 詳細パラメータ編集パネル (スクロール対応)
        # -------------------------------------------------------------
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)

        right_widget = QWidget()
        self.right_layout = QVBoxLayout(right_widget)
        self.right_layout.setContentsMargins(8, 8, 8, 8)
        self.right_layout.setSpacing(10)

        # 連動設定ヘッダー（ボタン幅・パディングをゆったり確保して文字欠けを解消）
        header_sync_layout = QHBoxLayout()
        header_sync_layout.setContentsMargins(2, 2, 2, 4)
        header_sync_layout.setSpacing(8)

        self.chk_auto_sync = QCheckBox("変更をシーンに即時反映")
        self.chk_auto_sync.setChecked(True)
        self.chk_auto_sync.setToolTip("スライダーや数値を操作した際、Mayaシーンのノードへ即座に反映します。")
        header_sync_layout.addWidget(self.chk_auto_sync)
        header_sync_layout.addStretch()

        self.btn_apply = QPushButton("シーンへ反映")
        self.btn_apply.setMinimumWidth(125)
        self.btn_apply.setFixedHeight(32)
        self.btn_apply.setStyleSheet(
            "QPushButton { background-color: #2f6f9f; color: #ffffff; font-weight: bold; border-radius: 4px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #3b82b8; border: 1px solid #6ac5fe; }"
        )
        self.btn_apply.clicked.connect(self._apply_current_parameters)
        header_sync_layout.addWidget(self.btn_apply)

        self.btn_revert = QPushButton("ノードから読込")
        self.btn_revert.setMinimumWidth(125)
        self.btn_revert.setFixedHeight(32)
        self.btn_revert.setStyleSheet(
            "QPushButton { background-color: #444444; color: #ffffff; border: 1px solid #5a5a5a; border-radius: 4px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #555555; border-color: #888888; }"
        )
        self.btn_revert.clicked.connect(self._revert_current_parameters)
        header_sync_layout.addWidget(self.btn_revert)

        self.right_layout.addLayout(header_sync_layout)

        # 基本情報グループ
        grp_basic = QGroupBox("基本情報")
        grp_basic_layout = QVBoxLayout(grp_basic)
        grp_basic_layout.setSpacing(6)

        h_name_ja = QHBoxLayout()
        h_name_ja.addWidget(QLabel("材質名 (日本語):"))
        self.le_mat_name_ja = QLineEdit()
        self.le_mat_name_ja.editingFinished.connect(self._on_parameter_changed)
        h_name_ja.addWidget(self.le_mat_name_ja)
        grp_basic_layout.addLayout(h_name_ja)

        h_name_en = QHBoxLayout()
        h_name_en.addWidget(QLabel("材質名 (英語):"))
        self.le_mat_name_en = QLineEdit()
        self.le_mat_name_en.editingFinished.connect(self._on_parameter_changed)
        h_name_en.addWidget(self.le_mat_name_en)
        grp_basic_layout.addLayout(h_name_en)

        h_node_info = QHBoxLayout()
        h_node_info.addWidget(QLabel("シェーダーノード:"))
        self.le_shader_node = QLineEdit()
        self.le_shader_node.setReadOnly(True)
        self.le_shader_node.setStyleSheet("background-color: #1a1a1a; color: #88c;")
        h_node_info.addWidget(self.le_shader_node)

        h_node_info.addWidget(QLabel("種別:"))
        self.lbl_shader_type = QLabel("-")
        self.lbl_shader_type.setStyleSheet("color: #77dd77; font-weight: bold;")
        h_node_info.addWidget(self.lbl_shader_type)
        grp_basic_layout.addLayout(h_node_info)

        self.right_layout.addWidget(grp_basic)

        # 色・非透過度グループ
        grp_colors = QGroupBox("色・非透過度 (Diffuse / Alpha / Specular / Ambient)")
        grp_colors_layout = QVBoxLayout(grp_colors)
        grp_colors_layout.setSpacing(6)

        # 拡散色 (Diffuse)
        h_diffuse = QHBoxLayout()
        h_diffuse.addWidget(QLabel("拡散色 (RGB):"))
        self.spin_diff_r = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.spin_diff_g = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.spin_diff_b = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.btn_diff_color = ColorChipButton()
        self.btn_diff_color.colorChanged.connect(self._on_diff_color_picked)
        h_diffuse.addWidget(QLabel("R:"))
        h_diffuse.addWidget(self.spin_diff_r)
        h_diffuse.addWidget(QLabel("G:"))
        h_diffuse.addWidget(self.spin_diff_g)
        h_diffuse.addWidget(QLabel("B:"))
        h_diffuse.addWidget(self.spin_diff_b)
        h_diffuse.addWidget(self.btn_diff_color)
        grp_colors_layout.addLayout(h_diffuse)

        # 非透過度 (Alpha)
        h_alpha = QHBoxLayout()
        h_alpha.addWidget(QLabel("非透過度 (Alpha):"))
        self.spin_alpha = self._create_double_spin(0.0, 1.0, 0.01, 3)
        h_alpha.addWidget(self.spin_alpha)
        h_alpha.addWidget(QLabel("(1.0 = 不透明, 0.0 = 透明)"))
        h_alpha.addStretch()
        grp_colors_layout.addLayout(h_alpha)

        # 反射色 (Specular) ＆ 反射強度 (Power)
        h_spec = QHBoxLayout()
        h_spec.addWidget(QLabel("反射色 (RGB):"))
        self.spin_spec_r = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.spin_spec_g = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.spin_spec_b = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.btn_spec_color = ColorChipButton()
        self.btn_spec_color.colorChanged.connect(self._on_spec_color_picked)
        h_spec.addWidget(QLabel("R:"))
        h_spec.addWidget(self.spin_spec_r)
        h_spec.addWidget(QLabel("G:"))
        h_spec.addWidget(self.spin_spec_g)
        h_spec.addWidget(QLabel("B:"))
        h_spec.addWidget(self.spin_spec_b)
        h_spec.addWidget(self.btn_spec_color)
        grp_colors_layout.addLayout(h_spec)

        h_power = QHBoxLayout()
        h_power.addWidget(QLabel("反射強度 (Power):"))
        self.spin_power = self._create_double_spin(0.0, 200.0, 0.5, 2)
        h_power.addWidget(self.spin_power)
        h_power.addStretch()
        grp_colors_layout.addLayout(h_power)

        # 環境色 (Ambient)
        h_amb = QHBoxLayout()
        h_amb.addWidget(QLabel("環境色 (RGB):"))
        self.spin_amb_r = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.spin_amb_g = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.spin_amb_b = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.btn_amb_color = ColorChipButton()
        self.btn_amb_color.colorChanged.connect(self._on_amb_color_picked)
        h_amb.addWidget(QLabel("R:"))
        h_amb.addWidget(self.spin_amb_r)
        h_amb.addWidget(QLabel("G:"))
        h_amb.addWidget(self.spin_amb_g)
        h_amb.addWidget(QLabel("B:"))
        h_amb.addWidget(self.spin_amb_b)
        h_amb.addWidget(self.btn_amb_color)
        grp_colors_layout.addLayout(h_amb)

        self.right_layout.addWidget(grp_colors)

        # 描画フラググループ
        grp_flags = QGroupBox("描画フラグ (Flags)")
        grp_flags_layout = QHBoxLayout(grp_flags)
        self.chk_flag_double_sided = QCheckBox("両面描画")
        self.chk_flag_ground_shadow = QCheckBox("地面影")
        self.chk_flag_cast_shadow = QCheckBox("影マップ投射")
        self.chk_flag_recv_shadow = QCheckBox("影受容")
        self.chk_flag_edge = QCheckBox("輪郭線描画")

        self.chk_flag_double_sided.stateChanged.connect(self._on_parameter_changed)
        self.chk_flag_ground_shadow.stateChanged.connect(self._on_parameter_changed)
        self.chk_flag_cast_shadow.stateChanged.connect(self._on_parameter_changed)
        self.chk_flag_recv_shadow.stateChanged.connect(self._on_parameter_changed)
        self.chk_flag_edge.stateChanged.connect(self._on_parameter_changed)

        grp_flags_layout.addWidget(self.chk_flag_double_sided)
        grp_flags_layout.addWidget(self.chk_flag_ground_shadow)
        grp_flags_layout.addWidget(self.chk_flag_cast_shadow)
        grp_flags_layout.addWidget(self.chk_flag_recv_shadow)
        grp_flags_layout.addWidget(self.chk_flag_edge)
        self.right_layout.addWidget(grp_flags)

        # 輪郭線 (Edge) グループ
        grp_edge = QGroupBox("輪郭線 (Edge)")
        grp_edge_layout = QVBoxLayout(grp_edge)
        grp_edge_layout.setSpacing(6)

        h_edge_col = QHBoxLayout()
        h_edge_col.addWidget(QLabel("エッジ色 (RGBA):"))
        self.spin_edge_r = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.spin_edge_g = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.spin_edge_b = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.spin_edge_a = self._create_double_spin(0.0, 1.0, 0.01, 3)
        self.btn_edge_color = ColorChipButton()
        self.btn_edge_color.colorChanged.connect(self._on_edge_color_picked)
        h_edge_col.addWidget(QLabel("R:"))
        h_edge_col.addWidget(self.spin_edge_r)
        h_edge_col.addWidget(QLabel("G:"))
        h_edge_col.addWidget(self.spin_edge_g)
        h_edge_col.addWidget(QLabel("B:"))
        h_edge_col.addWidget(self.spin_edge_b)
        h_edge_col.addWidget(QLabel("A:"))
        h_edge_col.addWidget(self.spin_edge_a)
        h_edge_col.addWidget(self.btn_edge_color)
        grp_edge_layout.addLayout(h_edge_col)

        h_edge_size = QHBoxLayout()
        h_edge_size.addWidget(QLabel("エッジサイズ (太さ):"))
        self.spin_edge_size = self._create_double_spin(0.0, 20.0, 0.1, 2)
        h_edge_size.addWidget(self.spin_edge_size)
        h_edge_size.addStretch()
        grp_edge_layout.addLayout(h_edge_size)

        self.right_layout.addWidget(grp_edge)

        # テクスチャ・スフィア・Toon グループ
        grp_tex = QGroupBox("テクスチャ / スフィア / Toon")
        grp_tex_layout = QVBoxLayout(grp_tex)
        grp_tex_layout.setSpacing(6)

        # 通常テクスチャ
        h_tex = QHBoxLayout()
        h_tex.addWidget(QLabel("テクスチャ:"))
        self.le_tex_path = QLineEdit()
        self.le_tex_path.editingFinished.connect(self._on_parameter_changed)
        btn_browse_tex = QPushButton("...")
        btn_browse_tex.setFixedWidth(32)
        btn_browse_tex.clicked.connect(self._browse_texture_file)
        h_tex.addWidget(self.le_tex_path)
        h_tex.addWidget(btn_browse_tex)
        grp_tex_layout.addLayout(h_tex)

        # スフィアテクスチャ
        h_sph = QHBoxLayout()
        h_sph.addWidget(QLabel("スフィア:"))
        self.le_sph_path = QLineEdit()
        self.le_sph_path.editingFinished.connect(self._on_parameter_changed)
        btn_browse_sph = QPushButton("...")
        btn_browse_sph.setFixedWidth(32)
        btn_browse_sph.clicked.connect(self._browse_sphere_file)
        h_sph.addWidget(self.le_sph_path)
        h_sph.addWidget(btn_browse_sph)

        h_sph.addWidget(QLabel("モード:"))
        self.cbb_sph_mode = QComboBox()
        self.cbb_sph_mode.addItems(["0: 無効", "1: 乗算 (.sph)", "2: 加算 (.spa)", "3: サブテクスチャ"])
        self.cbb_sph_mode.currentIndexChanged.connect(self._on_parameter_changed)
        h_sph.addWidget(self.cbb_sph_mode)
        grp_tex_layout.addLayout(h_sph)

        # Toonテクスチャ
        h_toon = QHBoxLayout()
        h_toon.addWidget(QLabel("Toon:"))
        self.le_toon_path = QLineEdit()
        self.le_toon_path.editingFinished.connect(self._on_parameter_changed)
        btn_browse_toon = QPushButton("...")
        btn_browse_toon.setFixedWidth(32)
        btn_browse_toon.clicked.connect(self._browse_toon_file)
        h_toon.addWidget(self.le_toon_path)
        h_toon.addWidget(btn_browse_toon)
        grp_tex_layout.addLayout(h_toon)

        self.right_layout.addWidget(grp_tex)

        # メモ欄
        grp_memo = QGroupBox("メモ")
        grp_memo_layout = QVBoxLayout(grp_memo)
        self.te_memo = QTextEdit()
        self.te_memo.setFixedHeight(60)
        self.te_memo.textChanged.connect(self._on_parameter_changed)
        grp_memo_layout.addWidget(self.te_memo)
        self.right_layout.addWidget(grp_memo)

        self.right_layout.addStretch()

        right_scroll.setWidget(right_widget)
        splitter.addWidget(right_scroll)

        # スプリッターの初期分割比率 (リスト:詳細 = 480:620)
        splitter.setSizes([480, 620])
        main_layout.addWidget(splitter)

    def _create_double_spin(self, min_val, max_val, step, decimals):
        """汎用数値スピンボックスを生成"""
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setFixedWidth(70)
        spin.valueChanged.connect(self._on_parameter_changed)
        return spin

    # -------------------------------------------------------------
    # カラーチップ連携スロット
    # -------------------------------------------------------------
    def _on_diff_color_picked(self, color):
        """拡散色ピッカー連動"""
        self._block_signals = True
        self.spin_diff_r.setValue(color.redF())
        self.spin_diff_g.setValue(color.greenF())
        self.spin_diff_b.setValue(color.blueF())
        self._block_signals = False
        self._on_parameter_changed()

    def _on_spec_color_picked(self, color):
        """反射色ピッカー連動"""
        self._block_signals = True
        self.spin_spec_r.setValue(color.redF())
        self.spin_spec_g.setValue(color.greenF())
        self.spin_spec_b.setValue(color.blueF())
        self._block_signals = False
        self._on_parameter_changed()

    def _on_amb_color_picked(self, color):
        """環境色ピッカー連動"""
        self._block_signals = True
        self.spin_amb_r.setValue(color.redF())
        self.spin_amb_g.setValue(color.greenF())
        self.spin_amb_b.setValue(color.blueF())
        self._block_signals = False
        self._on_parameter_changed()

    def _on_edge_color_picked(self, color):
        """エッジ色ピッカー連動"""
        self._block_signals = True
        self.spin_edge_r.setValue(color.redF())
        self.spin_edge_g.setValue(color.greenF())
        self.spin_edge_b.setValue(color.blueF())
        self._block_signals = False
        self._on_parameter_changed()

    # -------------------------------------------------------------
    # シーン情報の取得とテーブル構築
    # -------------------------------------------------------------
    def set_target_model(self, model_name):
        """対象とするMMDモデルルートまたはノードを指定"""
        self.current_model = model_name
        try:
            self.refresh_materials()
        except Exception as e:
            print(f"[材質タブ 警告] 材質情報の読み込み中に軽微な例外を捕捉: {e}")

    def refresh_materials(self):
        """Mayaシーンから材質情報を収集してテーブルを構築"""
        self.material_data_list = []
        self.table_materials.setRowCount(0)
        self.selected_mat_index = -1

        # 対象モデルから関連シェーダーを特定
        shaders = set()
        if self.current_model and mc.objExists(self.current_model):
            meshes = mc.listRelatives(self.current_model, allDescendents=True, type="mesh", fullPath=True) or []
            if mc.nodeType(self.current_model) == "mesh":
                meshes.append(self.current_model)

            for m in meshes:
                sgs = mc.listConnections(m, type="shadingEngine") or []
                for sg in set(sgs):
                    shds = mc.listConnections(f"{sg}.surfaceShader") or []
                    for s in shds:
                        shaders.add(s)
        else:
            for s in mc.ls(materials=True) or []:
                if mc.attributeQuery("originalName", node=s, exists=True):
                    shaders.add(s)
                elif any(p in s for p in ["mat_", "mmd_"]):
                    shaders.add(s)

        # 順序をソートして情報抽出
        sorted_shaders = sorted(list(shaders))
        for idx, shd in enumerate(sorted_shaders):
            data = self._gather_shader_info(idx, shd)
            self.material_data_list.append(data)

        self._populate_table()

    def _gather_shader_info(self, index, shd):
        """シェーダーノードおよび上流ネットワークからアトリビュート情報を抽出"""
        node_type = mc.nodeType(shd)

        # 日本語名
        name_ja = ""
        if mc.attributeQuery("originalName", node=shd, exists=True):
            name_ja = mc.getAttr(f"{shd}.originalName") or ""
        if not name_ja:
            name_ja = shd.split("|")[-1].split(":")[-1]

        # 英語名
        name_en = ""
        if mc.attributeQuery("englishName", node=shd, exists=True):
            name_en = mc.getAttr(f"{shd}.englishName") or ""

        # 拡散色・ベースカラー
        diff_col = [1.0, 1.0, 1.0]
        for attr in ["diffuseColor", "color", "baseColor"]:
            if mc.attributeQuery(attr, node=shd, exists=True):
                val = mc.getAttr(f"{shd}.{attr}")
                if val and isinstance(val, list) and len(val) > 0:
                    diff_col = list(val[0])
                break

        # 非透過度 (Alpha)
        alpha = 1.0
        if mc.attributeQuery("diffuseAlpha", node=shd, exists=True):
            alpha = float(mc.getAttr(f"{shd}.diffuseAlpha"))
        elif mc.attributeQuery("opacity", node=shd, exists=True):
            op = mc.getAttr(f"{shd}.opacity")
            if op and isinstance(op, list) and len(op) > 0:
                alpha = float(op[0][0])
        elif mc.attributeQuery("transparency", node=shd, exists=True):
            tr = mc.getAttr(f"{shd}.transparency")
            if tr and isinstance(tr, list) and len(tr) > 0:
                alpha = max(0.0, min(1.0, 1.0 - float(tr[0][0])))

        # 反射色
        spec_col = [0.0, 0.0, 0.0]
        if mc.attributeQuery("specularColor", node=shd, exists=True):
            val = mc.getAttr(f"{shd}.specularColor")
            if val and isinstance(val, list) and len(val) > 0:
                spec_col = list(val[0])

        # 反射強度
        power = 5.0
        for attr in ["specularPower", "cosinePower", "eccentricity"]:
            if mc.attributeQuery(attr, node=shd, exists=True):
                power = float(mc.getAttr(f"{shd}.{attr}"))
                break

        # 環境色
        amb_col = [0.0, 0.0, 0.0]
        if mc.attributeQuery("ambientColor", node=shd, exists=True):
            val = mc.getAttr(f"{shd}.ambientColor")
            if val and isinstance(val, list) and len(val) > 0:
                amb_col = list(val[0])

        # 輪郭線 (Edge)
        edge_enable = False
        edge_col = [0.0, 0.0, 0.0, 1.0]
        edge_size = 1.0
        if mc.attributeQuery("edgeEnable", node=shd, exists=True):
            edge_enable = bool(mc.getAttr(f"{shd}.edgeEnable"))
        if mc.attributeQuery("edgeColor", node=shd, exists=True):
            val = mc.getAttr(f"{shd}.edgeColor")
            if val and isinstance(val, list) and len(val) > 0:
                edge_col[0] = float(val[0][0])
                edge_col[1] = float(val[0][1])
                edge_col[2] = float(val[0][2])
        if mc.attributeQuery("edgeSize", node=shd, exists=True):
            edge_size = float(mc.getAttr(f"{shd}.edgeSize"))

        # 上流ノード探索によるテクスチャ・スフィア・Toonの分類特定
        tex_path = ""
        tex_node = None
        sph_path = ""
        sph_node = None
        sph_mode = 0
        toon_path = ""
        toon_node = None

        file_nodes = _find_upstream_file_nodes(shd)

        for fn in file_nodes:
            ftn = mc.getAttr(f"{fn}.fileTextureName") or ""
            ftn_lower = ftn.lower().replace("\\", "/")
            fn_lower = fn.lower()

            # Toon判定
            is_toon = False
            if "toon" in fn_lower or "custoon" in fn_lower:
                is_toon = True
            elif any(f"toon{i:02d}" in ftn_lower for i in range(1, 11)) or "toon0." in ftn_lower or "toon00" in ftn_lower:
                is_toon = True

            if is_toon:
                if not toon_path:
                    toon_path = ftn
                    toon_node = fn
                continue

            # スフィア判定
            is_sph = False
            if "sph" in fn_lower or "spa" in fn_lower:
                is_sph = True
            elif ftn_lower.endswith(".sph") or ftn_lower.endswith(".spa"):
                is_sph = True

            if is_sph:
                if not sph_path:
                    sph_path = ftn
                    sph_node = fn
                continue

            # 通常テクスチャ
            if not tex_path:
                tex_path = ftn
                tex_node = fn

        # スフィアモードの推定
        if sph_node:
            outputs = mc.listConnections(sph_node, source=False, destination=True) or []
            for out_n in outputs:
                o_type = mc.nodeType(out_n)
                o_name = out_n.lower()
                if o_type == "multiplyDivide" or "sph_mult" in o_name:
                    sph_mode = 1 # 乗算 (.sph)
                    break
                elif o_type == "plusMinusAverage" or "sph_add" in o_name:
                    sph_mode = 2 # 加算 (.spa)
                    break
        elif mc.attributeQuery("sphereMode", node=shd, exists=True):
            sph_mode = int(mc.getAttr(f"{shd}.sphereMode"))

        # 描画フラグ (メッシュ由来)
        double_sided = True
        cast_shadow = True
        recv_shadow = True
        ground_shadow = True

        return {
            "index": index,
            "shader": shd,
            "type": node_type,
            "name_ja": name_ja,
            "name_en": name_en,
            "diff_col": diff_col,
            "alpha": alpha,
            "spec_col": spec_col,
            "power": power,
            "amb_col": amb_col,
            "edge_enable": edge_enable,
            "edge_col": edge_col,
            "edge_size": edge_size,
            "double_sided": double_sided,
            "ground_shadow": ground_shadow,
            "cast_shadow": cast_shadow,
            "recv_shadow": recv_shadow,
            "tex_path": tex_path,
            "tex_node": tex_node,
            "sph_path": sph_path,
            "sph_node": sph_node,
            "sph_mode": sph_mode,
            "toon_path": toon_path,
            "toon_node": toon_node,
            "memo": "",
        }

    def _populate_table(self):
        """抽出したデータからテーブルアイテムを生成"""
        self.table_materials.blockSignals(True)
        self.table_materials.setRowCount(len(self.material_data_list))

        for row, data in enumerate(self.material_data_list):
            item_no = QTableWidgetItem(f"{data['index']}")
            item_no.setTextAlignment(Qt.AlignCenter)

            item_ja = QTableWidgetItem(data["name_ja"])
            item_en = QTableWidgetItem(data["name_en"])
            item_shd = QTableWidgetItem(data["shader"])

            diff = data["diff_col"]
            r = int(max(0.0, min(1.0, diff[0])) * 255)
            g = int(max(0.0, min(1.0, diff[1])) * 255)
            b = int(max(0.0, min(1.0, diff[2])) * 255)

            pix = QPixmap(24, 16)
            pix.fill(QColor(r, g, b))
            icon = QtGui.QIcon(pix)
            item_col = QTableWidgetItem(icon, "")
            item_col.setTextAlignment(Qt.AlignCenter)

            self.table_materials.setItem(row, 0, item_no)
            self.table_materials.setItem(row, 1, item_ja)
            self.table_materials.setItem(row, 2, item_en)
            self.table_materials.setItem(row, 3, item_shd)
            self.table_materials.setItem(row, 4, item_col)

        self.table_materials.blockSignals(False)

        if self.material_data_list:
            self.table_materials.selectRow(0)

    def _filter_material_list(self, text):
        """テーブルのインクリメンタル絞り込み"""
        pattern = text.lower().strip()
        for row in range(self.table_materials.rowCount()):
            match = False
            for col in [1, 2, 3]:
                item = self.table_materials.item(row, col)
                if item and pattern in item.text().lower():
                    match = True
                    break
            self.table_materials.setRowHidden(row, not match)

    # -------------------------------------------------------------
    # 選択イベントと右ペインへの展開
    # -------------------------------------------------------------
    def _on_table_selection_changed(self):
        """テーブル行選択時の詳細パネル更新"""
        selected_rows = self.table_materials.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        if 0 <= row < len(self.material_data_list):
            self.selected_mat_index = row
            self._load_parameters_to_ui(self.material_data_list[row])

    def _load_parameters_to_ui(self, data):
        """データを右ペインのウィジェットへ反映"""
        self._block_signals = True

        # 基本情報
        self.le_mat_name_ja.setText(data["name_ja"])
        self.le_mat_name_en.setText(data["name_en"])
        self.le_shader_node.setText(data["shader"])
        self.lbl_shader_type.setText(data["type"])

        # 色・非透過度
        diff = data["diff_col"]
        self.spin_diff_r.setValue(diff[0])
        self.spin_diff_g.setValue(diff[1])
        self.spin_diff_b.setValue(diff[2])
        self.btn_diff_color.set_color(diff)

        self.spin_alpha.setValue(data["alpha"])

        spec = data["spec_col"]
        self.spin_spec_r.setValue(spec[0])
        self.spin_spec_g.setValue(spec[1])
        self.spin_spec_b.setValue(spec[2])
        self.btn_spec_color.set_color(spec)

        self.spin_power.setValue(data["power"])

        amb = data["amb_col"]
        self.spin_amb_r.setValue(amb[0])
        self.spin_amb_g.setValue(amb[1])
        self.spin_amb_b.setValue(amb[2])
        self.btn_amb_color.set_color(amb)

        # フラグ
        self.chk_flag_double_sided.setChecked(data["double_sided"])
        self.chk_flag_ground_shadow.setChecked(data["ground_shadow"])
        self.chk_flag_cast_shadow.setChecked(data["cast_shadow"])
        self.chk_flag_recv_shadow.setChecked(data["recv_shadow"])
        self.chk_flag_edge.setChecked(data["edge_enable"])

        # 輪郭線
        edge = data["edge_col"]
        self.spin_edge_r.setValue(edge[0])
        self.spin_edge_g.setValue(edge[1])
        self.spin_edge_b.setValue(edge[2])
        self.spin_edge_a.setValue(edge[3] if len(edge) > 3 else 1.0)
        self.btn_edge_color.set_color(edge[:3])
        self.spin_edge_size.setValue(data["edge_size"])

        # テクスチャ・スフィア・Toon
        self.le_tex_path.setText(data["tex_path"])
        self.le_sph_path.setText(data["sph_path"])
        mode_idx = max(0, min(3, data["sph_mode"]))
        self.cbb_sph_mode.setCurrentIndex(mode_idx)

        # Toonパスの設定
        self.le_toon_path.setText(data["toon_path"])

        # メモ
        self.te_memo.setPlainText(data["memo"])

        self._block_signals = False

    # -------------------------------------------------------------
    # パラメータ変更の通知とシーン同期
    # -------------------------------------------------------------
    def _on_parameter_changed(self, *args):
        """UIパラメータ変更時のハンドラ"""
        if self._block_signals or self.selected_mat_index < 0:
            return

        self._collect_ui_to_data(self.material_data_list[self.selected_mat_index])

        if self.chk_auto_sync.isChecked():
            self._apply_current_parameters()

    def _collect_ui_to_data(self, data):
        """UIの現在値を辞書へ格納"""
        data["name_ja"] = self.le_mat_name_ja.text().strip()
        data["name_en"] = self.le_mat_name_en.text().strip()

        data["diff_col"] = [
            self.spin_diff_r.value(),
            self.spin_diff_g.value(),
            self.spin_diff_b.value()
        ]
        data["alpha"] = self.spin_alpha.value()

        data["spec_col"] = [
            self.spin_spec_r.value(),
            self.spin_spec_g.value(),
            self.spin_spec_b.value()
        ]
        data["power"] = self.spin_power.value()

        data["amb_col"] = [
            self.spin_amb_r.value(),
            self.spin_amb_g.value(),
            self.spin_amb_b.value()
        ]

        data["double_sided"] = self.chk_flag_double_sided.isChecked()
        data["ground_shadow"] = self.chk_flag_ground_shadow.isChecked()
        data["cast_shadow"] = self.chk_flag_cast_shadow.isChecked()
        data["recv_shadow"] = self.chk_flag_recv_shadow.isChecked()
        data["edge_enable"] = self.chk_flag_edge.isChecked()

        data["edge_col"] = [
            self.spin_edge_r.value(),
            self.spin_edge_g.value(),
            self.spin_edge_b.value(),
            self.spin_edge_a.value()
        ]
        data["edge_size"] = self.spin_edge_size.value()

        data["tex_path"] = self.le_tex_path.text().strip()
        data["sph_path"] = self.le_sph_path.text().strip()
        data["sph_mode"] = self.cbb_sph_mode.currentIndex()
        data["toon_path"] = self.le_toon_path.text().strip()
        data["memo"] = self.te_memo.toPlainText()

        # テーブル上の行表示も更新
        row = self.selected_mat_index
        item_ja = self.table_materials.item(row, 1)
        if item_ja:
            item_ja.setText(data["name_ja"])
        item_en = self.table_materials.item(row, 2)
        if item_en:
            item_en.setText(data["name_en"])

        diff = data["diff_col"]
        r = int(max(0.0, min(1.0, diff[0])) * 255)
        g = int(max(0.0, min(1.0, diff[1])) * 255)
        b = int(max(0.0, min(1.0, diff[2])) * 255)
        pix = QPixmap(24, 16)
        pix.fill(QColor(r, g, b))
        item_col = self.table_materials.item(row, 4)
        if item_col:
            item_col.setIcon(QtGui.QIcon(pix))

    def _apply_current_parameters(self):
        """現在のパラメータをMayaシーン内のシェーダーノードへ反映（接続・ロック保護付き）"""
        if self.selected_mat_index < 0 or self.selected_mat_index >= len(self.material_data_list):
            return

        data = self.material_data_list[self.selected_mat_index]
        shd = data["shader"]
        if not mc.objExists(shd):
            return

        try:
            # 日本語名
            if not mc.attributeQuery("originalName", node=shd, exists=True):
                mc.addAttr(shd, longName="originalName", niceName="元の名称", dataType="string")
            mc.setAttr(f"{shd}.originalName", data["name_ja"], typ="string")

            # 英語名
            if not mc.attributeQuery("englishName", node=shd, exists=True):
                mc.addAttr(shd, longName="englishName", niceName="英語名称", dataType="string")
            mc.setAttr(f"{shd}.englishName", data["name_en"], typ="string")

            # 拡散色 (入力接続またはロックがある場合は直接setAttrをスキップして警告を抑止)
            diff = data["diff_col"]
            for attr in ["diffuseColor", "color", "baseColor"]:
                _safe_set_double3(shd, attr, diff[0], diff[1], diff[2])

            # 非透過度
            alpha = data["alpha"]
            _safe_set_float(shd, "diffuseAlpha", alpha)
            _safe_set_double3(shd, "opacity", alpha, alpha, alpha)
            _safe_set_double3(shd, "transparency", 1.0 - alpha, 1.0 - alpha, 1.0 - alpha)

            # 反射色
            spec = data["spec_col"]
            _safe_set_double3(shd, "specularColor", spec[0], spec[1], spec[2])

            # 反射強度
            power = data["power"]
            for attr in ["specularPower", "cosinePower", "eccentricity"]:
                _safe_set_float(shd, attr, power)

            # 環境色
            amb = data["amb_col"]
            _safe_set_double3(shd, "ambientColor", amb[0], amb[1], amb[2])

            # 輪郭線
            _safe_set_bool(shd, "edgeEnable", data["edge_enable"])
            ec = data["edge_col"]
            _safe_set_double3(shd, "edgeColor", ec[0], ec[1], ec[2])
            _safe_set_float(shd, "edgeSize", data["edge_size"])

            # スフィアモード
            if mc.attributeQuery("sphereMode", node=shd, exists=True):
                if not mc.listConnections(f"{shd}.sphereMode", source=True, destination=False):
                    try:
                        mc.setAttr(f"{shd}.sphereMode", int(data["sph_mode"]))
                    except Exception:
                        pass

            # テクスチャファイルパスのシーン反映
            tex_n = data.get("tex_node")
            if tex_n and mc.objExists(tex_n) and data.get("tex_path"):
                cur_ftn = mc.getAttr(f"{tex_n}.fileTextureName") or ""
                if cur_ftn != data["tex_path"]:
                    try:
                        mc.setAttr(f"{tex_n}.fileTextureName", data["tex_path"], typ="string")
                    except Exception:
                        pass

            # スフィアテクスチャパスのシーン反映
            sph_n = data.get("sph_node")
            if sph_n and mc.objExists(sph_n) and data.get("sph_path"):
                cur_ftn = mc.getAttr(f"{sph_n}.fileTextureName") or ""
                if cur_ftn != data["sph_path"]:
                    try:
                        mc.setAttr(f"{sph_n}.fileTextureName", data["sph_path"], typ="string")
                    except Exception:
                        pass

            # Toonテクスチャパスのシーン反映
            toon_n = data.get("toon_node")
            if toon_n and mc.objExists(toon_n) and data.get("toon_path"):
                cur_ftn = mc.getAttr(f"{toon_n}.fileTextureName") or ""
                if cur_ftn != data["toon_path"] and data["toon_path"] != "なし":
                    try:
                        mc.setAttr(f"{toon_n}.fileTextureName", data["toon_path"], typ="string")
                    except Exception:
                        pass

            # 割り当て先メッシュの描画フラグを同期
            self._sync_assigned_mesh_flags(shd, data)

        except Exception as e:
            mc.warning(f"パラメータ反映中に警告が発生しました: {e}")

    def _sync_assigned_mesh_flags(self, shader_node, data):
        """シェーダーが割り当てられているメッシュシェイプのフラグを更新"""
        sgs = mc.listConnections(shader_node, type="shadingEngine") or []
        for sg in set(sgs):
            members = mc.sets(sg, query=True) or []
            for m in members:
                obj = m.split(".")[0]
                shapes = mc.listRelatives(obj, shapes=True, fullPath=True) or []
                if mc.nodeType(obj) == "mesh":
                    shapes.append(obj)
                for shp in shapes:
                    try:
                        if mc.attributeQuery("doubleSided", node=shp, exists=True):
                            if not mc.getAttr(f"{shp}.doubleSided", lock=True) and not mc.listConnections(f"{shp}.doubleSided", source=True):
                                mc.setAttr(f"{shp}.doubleSided", 1 if data["double_sided"] else 0)
                        if mc.attributeQuery("castsShadows", node=shp, exists=True):
                            if not mc.getAttr(f"{shp}.castsShadows", lock=True) and not mc.listConnections(f"{shp}.castsShadows", source=True):
                                mc.setAttr(f"{shp}.castsShadows", 1 if data["cast_shadow"] else 0)
                        if mc.attributeQuery("receiveShadows", node=shp, exists=True):
                            if not mc.getAttr(f"{shp}.receiveShadows", lock=True) and not mc.listConnections(f"{shp}.receiveShadows", source=True):
                                mc.setAttr(f"{shp}.receiveShadows", 1 if data["recv_shadow"] else 0)
                    except Exception:
                        pass

    def _revert_current_parameters(self):
        """Mayaシーンから値を再読込"""
        if self.selected_mat_index >= 0 and self.selected_mat_index < len(self.material_data_list):
            shd = self.material_data_list[self.selected_mat_index]["shader"]
            fresh_data = self._gather_shader_info(self.selected_mat_index, shd)
            self.material_data_list[self.selected_mat_index] = fresh_data
            self._load_parameters_to_ui(fresh_data)

    # -------------------------------------------------------------
    # ファイルブラウザ連携
    # -------------------------------------------------------------
    def _browse_texture_file(self):
        """通常テクスチャファイルを参照"""
        path, _ = QFileDialog.getOpenFileName(
            self, "テクスチャファイルを選択", "", "画像ファイル (*.png *.bmp *.tga *.dds *.jpg);;すべてのファイル (*.*)"
        )
        if path:
            self.le_tex_path.setText(path)
            self._on_parameter_changed()

    def _browse_sphere_file(self):
        """スフィアテクスチャファイルを参照"""
        path, _ = QFileDialog.getOpenFileName(
            self, "スフィアテクスチャを選択", "", "スフィア画像 (*.sph *.spa *.png *.bmp *.tga);;すべてのファイル (*.*)"
        )
        if path:
            self.le_sph_path.setText(path)
            self._on_parameter_changed()

    def _browse_toon_file(self):
        """Toonテクスチャファイルを参照"""
        path, _ = QFileDialog.getOpenFileName(
            self, "Toonテクスチャを選択", "", "画像ファイル (*.bmp *.png *.tga);;すべてのファイル (*.*)"
        )
        if path:
            self.le_toon_path.setText(path)
            self._on_parameter_changed()

    # -------------------------------------------------------------
    # ビューポート・ノード連携
    # -------------------------------------------------------------
    def _select_assigned_geometry(self):
        """選択中材質が割り当てられているメッシュや面をMaya上で選択"""
        if self.selected_mat_index < 0 or self.selected_mat_index >= len(self.material_data_list):
            return

        shd = self.material_data_list[self.selected_mat_index]["shader"]
        sgs = mc.listConnections(shd, type="shadingEngine") or []
        if not sgs:
            mc.warning(f"シェーダー {shd} に接続されたシェーディンググループがありません。")
            return

        all_members = []
        for sg in set(sgs):
            members = mc.sets(sg, query=True) or []
            all_members.extend(members)

        if all_members:
            mc.select(all_members, replace=True)
        else:
            mc.warning(f"材質 {shd} が割り当てられたジオメトリが見つかりません。")

    def _find_material_from_viewport(self):
        """ビューポート選択オブジェクト/面から材質を特定してテーブル選択"""
        sel = mc.ls(selection=True) or []
        if not sel:
            mc.warning("ビューポート上でメッシュまたは面を選択してください。")
            return

        target_shaders = set()
        for item in sel:
            shapes = mc.listRelatives(item, shapes=True, fullPath=True) or []
            if mc.nodeType(item) == "mesh":
                shapes.append(item)
            elif "." in item:
                sgs = mc.listConnections(item, type="shadingEngine") or []
                for sg in sgs:
                    shds = mc.listConnections(f"{sg}.surfaceShader") or []
                    target_shaders.update(shds)

            for shp in shapes:
                sgs = mc.listConnections(shp, type="shadingEngine") or []
                for sg in sgs:
                    shds = mc.listConnections(f"{sg}.surfaceShader") or []
                    target_shaders.update(shds)

        if not target_shaders:
            mc.warning("選択対象から材質ノードを特定できませんでした。")
            return

        for row, data in enumerate(self.material_data_list):
            if data["shader"] in target_shaders:
                self.table_materials.selectRow(row)
                return

        mc.warning("選択対象の材質は現在のリストに含まれていません。")

    def _select_shader_node(self):
        """Mayaシーン内でシェーダーノードを選択"""
        if self.selected_mat_index < 0 or self.selected_mat_index >= len(self.material_data_list):
            return

        shd = self.material_data_list[self.selected_mat_index]["shader"]
        if mc.objExists(shd):
            mc.select(shd, replace=True)
            try:
                mel.eval(f'showEditor "{shd}"')
            except Exception:
                pass
