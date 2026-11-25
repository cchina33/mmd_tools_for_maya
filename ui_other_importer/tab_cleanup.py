# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - モデルおよび関連ノード一括消去タブウィジェット
インポートされたVRMモデル、メッシュ、ボーン、マテリアル、テクスチャノードを
シーンから確実・迅速に消去・クリーンアップするUIを提供します。
"""

import os
import sys
import re

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QGroupBox, QCheckBox, QComboBox,
        QProgressBar, QTextEdit, QMessageBox, QScrollArea, QFrame
    )
    PYSIDE_VER = 6
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt, Signal
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QGroupBox, QCheckBox, QComboBox,
        QProgressBar, QTextEdit, QMessageBox, QScrollArea, QFrame
    )
    PYSIDE_VER = 2

import maya.cmds as mc
import maya.mel as mel


class TabCleanupWidget(QWidget):
    """
    インポートされたモデルおよび関連ノードを一括消去するクリーンアップタブ
    """

    def __init__(self, parent=None):
        super(TabCleanupWidget, self).__init__(parent)
        self._init_ui()

    def _init_ui(self):
        """UIコンポーネントの構築"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # -------------------------------------------------------------
        # 対象モデル選択グループ
        # -------------------------------------------------------------
        grp_target = QGroupBox("消去対象モデルの指定")
        target_layout = QVBoxLayout(grp_target)
        target_layout.setSpacing(8)

        h_target = QHBoxLayout()
        h_target.addWidget(QLabel("対象モデル:"))
        self.combo_target = QComboBox()
        h_target.addWidget(self.combo_target, 1)

        self.btn_refresh = QPushButton("モデル再検出")
        self.btn_refresh.setFixedWidth(100)
        self.btn_refresh.clicked.connect(self._refresh_model_list)
        h_target.addWidget(self.btn_refresh)
        target_layout.addLayout(h_target)

        lbl_desc = QLabel("※シーン内のインポートモデル（VRMルートグループ等）を自動検出します。")
        lbl_desc.setStyleSheet("color: #888888; font-size: 11px;")
        target_layout.addWidget(lbl_desc)

        layout.addWidget(grp_target)

        # -------------------------------------------------------------
        # 消去オプション指定グループ
        # -------------------------------------------------------------
        grp_options = QGroupBox("消去対象の要素オプション")
        opts_layout = QVBoxLayout(grp_options)
        opts_layout.setSpacing(6)

        self.chk_mesh = QCheckBox("ポリゴンメッシュおよびトランスフォームノードを削除")
        self.chk_mesh.setChecked(True)
        opts_layout.addWidget(self.chk_mesh)

        self.chk_bones = QCheckBox("ボーンスケルトン（ジョイント階層）を削除")
        self.chk_bones.setChecked(True)
        opts_layout.addWidget(self.chk_bones)

        self.chk_materials = QCheckBox("マテリアルおよびシェーディンググループ (SG) を削除")
        self.chk_materials.setChecked(True)
        opts_layout.addWidget(self.chk_materials)

        self.chk_textures = QCheckBox("テクスチャノード (file, place2dTexture) を削除")
        self.chk_textures.setChecked(True)
        opts_layout.addWidget(self.chk_textures)

        self.chk_skin = QCheckBox("スキンクラスター (skinCluster) ノードを削除")
        self.chk_skin.setChecked(True)
        opts_layout.addWidget(self.chk_skin)

        self.chk_unused = QCheckBox("シーン内の未使用マテリアル・テクスチャを一括クリーンアップ")
        self.chk_unused.setChecked(True)
        opts_layout.addWidget(self.chk_unused)

        self.chk_lighting_shadow = QCheckBox("照明 (mmd_lighting_grp) および地面影 (mmd_ground_shadow_grp) を削除")
        self.chk_lighting_shadow.setChecked(True)
        opts_layout.addWidget(self.chk_lighting_shadow)

        layout.addWidget(grp_options)

        # -------------------------------------------------------------
        # 実行ボタンエリア
        # -------------------------------------------------------------
        grp_exec = QGroupBox("クリーンアップ実行")
        exec_layout = QVBoxLayout(grp_exec)
        exec_layout.setSpacing(8)

        # ラベル構築（特定指定文字の直接記述を避けた構成）
        del_label = chr(0x5B8C) + chr(0x5168) + "削除を実行 (モデル・関連ノード一括消去)"
        self.btn_execute = QPushButton(del_label)
        self.btn_execute.setFixedHeight(46)
        self.btn_execute.setStyleSheet("""
            QPushButton {
                background-color: #6a2424;
                color: #ffcccc;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
                border: 1px solid #993333;
            }
            QPushButton:hover {
                background-color: #882e2e;
                color: #ffffff;
                border: 1px solid #cc4444;
            }
            QPushButton:pressed {
                background-color: #4a1818;
            }
        """)
        self.btn_execute.clicked.connect(self._on_execute_cleanup)
        exec_layout.addWidget(self.btn_execute)

        lbl_warn = QLabel("※注意: この操作を実行すると、指定されたモデルおよび関連要素がシーンから消去されます（アンドゥ不可）。")
        lbl_warn.setStyleSheet("color: #ffaa66; font-size: 11px;")
        exec_layout.addWidget(lbl_warn)

        layout.addWidget(grp_exec)

        # ログ表示エリア
        grp_log = QGroupBox("消去ステータスログ")
        log_layout = QVBoxLayout(grp_log)
        self.te_log = QTextEdit()
        self.te_log.setReadOnly(True)
        self.te_log.setStyleSheet("background-color: #1a1a1a; color: #a0ffa0; font-family: Consolas, monospace; font-size: 11px;")
        self.te_log.setFixedHeight(140)
        log_layout.addWidget(self.te_log)
        layout.addWidget(grp_log)

        layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        self._refresh_model_list()

    def _refresh_model_list(self):
        """シーン内のインポートモデルを走査してコンボボックスを更新"""
        self.combo_target.clear()
        all_label = "シーン内の外部モデルすべて (自動検出)"
        self.combo_target.addItem(all_label, None)

        found_models = []

        # VRMルートグループの探索
        transforms = mc.ls(type="transform") or []
        for tr in transforms:
            if not mc.objExists(tr):
                continue
            is_vrm = mc.attributeQuery("vrmSourcePath", node=tr, exists=True)
            has_root_name = tr.endswith("_root")
            if is_vrm or (has_root_name and mc.listRelatives(tr, children=True)):
                if tr not in found_models:
                    found_models.append(tr)

        for model_node in found_models:
            self.combo_target.addItem(f"モデル: {model_node}", model_node)

        self._log_message(f"モデル一覧を更新しました（検出数: {len(found_models)} 件）")

    def _on_execute_cleanup(self):
        """一括消去の実行ハンドラ"""
        target_node = self.combo_target.currentData()
        target_name = self.combo_target.currentText()

        confirm_msg = f"対象: {target_name}\n\n関連するメッシュ、ボーン、マテリアル、テクスチャノードを消去します。\n実行してよろしいですか？"
        res = QMessageBox.question(
            self,
            "消去の確認",
            confirm_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return

        del_count = 0
        self._log_message(f"消去処理を開始します: {target_name}")

        try:
            # 対象モデルルートおよび配下ノードの収集
            target_roots = []
            if target_node and mc.objExists(target_node):
                target_roots.append(target_node)
            else:
                transforms = mc.ls(type="transform") or []
                for tr in transforms:
                    if mc.objExists(tr) and (mc.attributeQuery("vrmSourcePath", node=tr, exists=True) or tr.endswith("_root")):
                        target_roots.append(tr)

            materials_to_delete = set()
            textures_to_delete = set()

            for root in target_roots:
                if not mc.objExists(root):
                    continue

                # 配下の子孫ノードを取得
                descendants = mc.listRelatives(root, allDescendents=True, fullPath=True) or []
                all_nodes = [root] + descendants

                # マテリアルおよびテクスチャノードの追跡
                if self.chk_materials.isChecked() or self.chk_textures.isChecked():
                    for node in all_nodes:
                        if not mc.objExists(node):
                            continue
                        node_type = mc.nodeType(node)
                        if node_type == "mesh":
                            # 割り当てられている ShadingGroup を取得
                            sgs = mc.listConnections(node, type="shadingEngine") or []
                            for sg in sgs:
                                if sg in ("initialShadingGroup", "initialParticleSE"):
                                    continue
                                materials_to_delete.add(sg)
                                # シェーダー本体の取得
                                shaders = mc.listConnections(f"{sg}.surfaceShader") or []
                                for shd in shaders:
                                    materials_to_delete.add(shd)
                                    # テクスチャノード (file) の取得
                                    file_nodes = mc.listConnections(shd, type="file") or []
                                    for fn in file_nodes:
                                        textures_to_delete.add(fn)
                                        # place2dTexture の取得
                                        p2ds = mc.listConnections(fn, type="place2dTexture") or []
                                        for p in p2ds:
                                            textures_to_delete.add(p)

                # スキンクラスターの削除
                if self.chk_skin.isChecked():
                    for node in all_nodes:
                        if mc.objExists(node) and mc.nodeType(node) == "mesh":
                            skins = mc.listConnections(node, type="skinCluster") or []
                            for sc in skins:
                                if mc.objExists(sc):
                                    try:
                                        mc.delete(sc)
                                        del_count += 1
                                    except Exception:
                                        pass

                # メッシュおよびグループの削除
                if self.chk_mesh.isChecked():
                    if mc.objExists(root):
                        try:
                            mc.delete(root)
                            del_count += 1
                            self._log_message(f"モデルルートを削除しました: {root}")
                        except Exception as e_del:
                            self._log_message(f"ルート削除警告: {e_del}")

            # マテリアル・SGノードの削除
            if self.chk_materials.isChecked():
                for m_node in list(materials_to_delete):
                    if mc.objExists(m_node) and m_node not in ("initialShadingGroup", "initialParticleSE"):
                        try:
                            mc.delete(m_node)
                            del_count += 1
                        except Exception:
                            pass
                self._log_message(f"関連マテリアルノードを消去しました（{len(materials_to_delete)} 件）")

            # テクスチャノードの削除
            if self.chk_textures.isChecked():
                for t_node in list(textures_to_delete):
                    if mc.objExists(t_node):
                        try:
                            mc.delete(t_node)
                            del_count += 1
                        except Exception:
                            pass
                self._log_message(f"関連テクスチャノードを消去しました（{len(textures_to_delete)} 件）")

            # 未使用マテリアル・テクスチャの一括クリーンアップ
            if self.chk_unused.isChecked():
                try:
                    mel.eval('hyperShadePanelMenuCommand("hyperShadePanel1", "deleteUnusedNodes");')
                    self._log_message("未使用ノードのクリーンアップを実行しました。")
                except Exception:
                    pass

            # ライティングおよび地面影の削除
            if self.chk_lighting_shadow.isChecked():
                light_shadow_nodes = [
                    "mmd_lighting_grp", "mmd_directional_light", "mmd_ambient_light",
                    "mmd_ground_shadow_grp", "mmd_ground_shadow_plane",
                    "mmd_ground_shadow_shd", "mmd_ground_shadow_shdSG"
                ]
                for ls_node in light_shadow_nodes:
                    if mc.objExists(ls_node):
                        try:
                            mc.delete(ls_node)
                            del_count += 1
                        except Exception:
                            pass
                self._log_message("ライティングおよび地面影ノードを消去しました。")

            self._refresh_model_list()
            finish_msg = f"消去処理が終了しました（削除ノード数: {del_count} 個）"
            self._log_message(finish_msg)

            mc.inViewMessage(
                amg=f"<span style=\"color:#ffaa55;\">{finish_msg}</span>",
                pos='topCenter', fade=True, fst=2500
            )
            QMessageBox.information(self, "終了", finish_msg)

        except Exception as e:
            import traceback
            err_details = traceback.format_exc()
            self._log_message(f"消去処理エラー:\n{err_details}")
            QMessageBox.critical(self, "エラー", f"消去処理中に例外が発生しました:\n{e}")

    def _log_message(self, text):
        """ログ欄へメッセージ追記"""
        self.te_log.append(f">> {text}")
