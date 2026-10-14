# -*- coding: utf-8 -*-
"""
ボーン状態JSONエクスポートダイアログ
指定フレーム範囲におけるモデルの全ボーン（ジョイント）の移動・回転状態をJSON形式で書き出します。
PySide6 (Maya 2025+) および PySide2 (Maya 2022-2024) 両対応。
"""

import sys
import os
import json
import time

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    PYSIDE_VER = 6
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
        PYSIDE_VER = 2
    except ImportError:
        raise ImportError("PySide6 または PySide2 が見つかりません。")

import maya.cmds as mc

_bone_state_export_dialog_instance = None


class BoneStateExportDialog(QtWidgets.QDialog):
    """指定フレーム範囲のボーン状態（移動・回転）をJSONへ書き出すダイアログ"""

    def __init__(self, parent=None):
        super(BoneStateExportDialog, self).__init__(parent)
        self.setWindowTitle("ボーン状態 JSON エクスポート")
        self.resize(560, 380)
        self.setMinimumSize(480, 320)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)

        self._init_ui()
        self._populate_models()
        self._init_frame_range()

    def _init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 説明ヘッダーパネル
        info_frame = QtWidgets.QFrame()
        info_frame.setStyleSheet(
            "background-color: #1e262f; border: 1px solid #324759; border-radius: 6px; padding: 10px;"
        )
        info_layout = QtWidgets.QVBoxLayout(info_frame)
        info_layout.setSpacing(4)

        lbl_title = QtWidgets.QLabel("【ボーン状態（移動・回転）のJSON一括書き出し】")
        lbl_title.setStyleSheet("color: #70b5f5; font-weight: bold; font-size: 13px;")
        info_layout.addWidget(lbl_title)

        lbl_desc = QtWidgets.QLabel(
            "指定したフレーム範囲におけるすべてのボーンのローカルおよびワールド座標（移動・回転）を取得し、"
            "ポーズ解析やMMDとの比較検証が容易なJSONファイルとして保存します。"
        )
        lbl_desc.setStyleSheet("color: #cfd8dc; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        info_layout.addWidget(lbl_desc)
        main_layout.addWidget(info_frame)

        # 設定グループ
        settings_group = QtWidgets.QGroupBox("エクスポート設定")
        settings_group.setStyleSheet("QGroupBox { font-weight: bold; color: #90caf9; }")
        settings_layout = QtWidgets.QVBoxLayout(settings_group)
        settings_layout.setSpacing(10)

        # 対象モデル選択
        row_model = QtWidgets.QHBoxLayout()
        lbl_model = QtWidgets.QLabel("対象モデル:")
        lbl_model.setFixedWidth(90)
        self.cmb_model = QtWidgets.QComboBox()
        self.btn_refresh_models = QtWidgets.QPushButton("更新")
        self.btn_refresh_models.setFixedWidth(60)
        self.btn_refresh_models.clicked.connect(self._populate_models)
        row_model.addWidget(lbl_model)
        row_model.addWidget(self.cmb_model)
        row_model.addWidget(self.btn_refresh_models)
        settings_layout.addLayout(row_model)

        # フレーム範囲設定
        row_frames = QtWidgets.QHBoxLayout()
        lbl_start = QtWidgets.QLabel("開始フレーム:")
        lbl_start.setFixedWidth(90)
        self.spn_start = QtWidgets.QSpinBox()
        self.spn_start.setRange(-999999, 999999)
        self.spn_start.setValue(0)

        lbl_end = QtWidgets.QLabel("終了フレーム:")
        self.spn_end = QtWidgets.QSpinBox()
        self.spn_end.setRange(-999999, 999999)
        self.spn_end.setValue(100)

        lbl_step = QtWidgets.QLabel("ステップ:")
        self.spn_step = QtWidgets.QSpinBox()
        self.spn_step.setRange(1, 1000)
        self.spn_step.setValue(1)

        row_frames.addWidget(lbl_start)
        row_frames.addWidget(self.spn_start)
        row_frames.addWidget(lbl_end)
        row_frames.addWidget(self.spn_end)
        row_frames.addWidget(lbl_step)
        row_frames.addWidget(self.spn_step)
        settings_layout.addLayout(row_frames)

        # 保存先ファイルパス設定
        row_path = QtWidgets.QHBoxLayout()
        lbl_path = QtWidgets.QLabel("保存先パス:")
        lbl_path.setFixedWidth(90)
        self.txt_path = QtWidgets.QLineEdit()
        self.txt_path.setPlaceholderText("保存するJSONファイルのパスを指定してください...")
        self.btn_browse = QtWidgets.QPushButton("参照...")
        self.btn_browse.setFixedWidth(75)
        self.btn_browse.clicked.connect(self._on_browse_file)
        row_path.addWidget(lbl_path)
        row_path.addWidget(self.txt_path)
        row_path.addWidget(self.btn_browse)
        settings_layout.addLayout(row_path)

        main_layout.addWidget(settings_group)

        # 進捗バー
        self.prog_bar = QtWidgets.QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setTextVisible(True)
        self.prog_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #444; border-radius: 4px; text-align: center; } "
            "QProgressBar::chunk { background-color: #2b78e4; }"
        )
        main_layout.addWidget(self.prog_bar)

        # 下部ボタングループ
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_export = QtWidgets.QPushButton("エクスポート実行")
        self.btn_export.setStyleSheet(
            "background-color: #1e5631; color: #ffffff; font-weight: bold; border: 1px solid #2e7d32; padding: 7px 22px; border-radius: 4px;"
        )
        self.btn_export.clicked.connect(self._on_execute_export)
        btn_layout.addWidget(self.btn_export)

        self.btn_close = QtWidgets.QPushButton("閉じる")
        self.btn_close.setStyleSheet(
            "background-color: #333333; color: #dddddd; border: 1px solid #555555; padding: 7px 16px; border-radius: 4px;"
        )
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_close)

        main_layout.addLayout(btn_layout)

    def _populate_models(self):
        """シーン内のMMDモデルを検出してコンボボックスに登録"""
        self.cmb_model.clear()
        self.cmb_model.addItem("シーン全体 (全ジョイント)", None)

        try:
            try:
                from ..converters.vmdpaimaya import get_available_mmd_models
            except Exception:
                from converters.vmdpaimaya import get_available_mmd_models
            models = get_available_mmd_models()
            for node, label in models:
                self.cmb_model.addItem(label, node)
        except Exception:
            pass

    def _init_frame_range(self):
        """現在のタイムライン設定から開始・終了フレームを初期設定"""
        try:
            start_f = int(mc.playbackOptions(query=True, minTime=True))
            end_f = int(mc.playbackOptions(query=True, maxTime=True))
            self.spn_start.setValue(start_f)
            self.spn_end.setValue(end_f)
        except Exception:
            self.spn_start.setValue(0)
            self.spn_end.setValue(100)

    def _on_browse_file(self):
        """保存先JSONファイル選択ダイアログ"""
        default_dir = os.path.expanduser("~/Documents")
        default_name = os.path.join(default_dir, "mmd_bone_states.json")

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "ボーン状態JSONファイルの保存先を選択",
            default_name,
            "JSON ファイル (*.json);;すべてのファイル (*.*)"
        )
        if file_path:
            self.txt_path.setText(file_path)

    def _collect_joints(self, target_model_node):
        """対象モデル配下の全ジョイントを収集"""
        if target_model_node and mc.objExists(target_model_node):
            joints = mc.listRelatives(target_model_node, allDescendents=True, type='joint', fullPath=True) or []
            if mc.nodeType(target_model_node) == 'joint':
                joints.append(target_model_node)
        else:
            joints = mc.ls(type='joint', long=True) or []
        return sorted(list(set(joints)))

    def _on_execute_export(self):
        """エクスポート実行処理"""
        save_path = self.txt_path.text().strip()
        if not save_path:
            QtWidgets.QMessageBox.warning(self, "パス未指定", "保存先ファイルパスを指定してください。")
            self._on_browse_file()
            save_path = self.txt_path.text().strip()
            if not save_path:
                return

        start_frame = self.spn_start.value()
        end_frame = self.spn_end.value()
        step = self.spn_step.value()

        if start_frame > end_frame:
            QtWidgets.QMessageBox.warning(self, "フレーム指定エラー", "開始フレームは終了フレーム以下に設定してください。")
            return

        target_model_node = self.cmb_model.currentData()
        joints = self._collect_joints(target_model_node)

        if not joints:
            QtWidgets.QMessageBox.warning(self, "ジョイント未検出", "エクスポート対象のジョイントが見つかりませんでした。")
            return

        # 元の現在フレームを退避
        orig_frame = mc.currentTime(query=True)

        total_steps = len(range(start_frame, end_frame + 1, step))
        self.prog_bar.setMaximum(total_steps)
        self.prog_bar.setValue(0)
        self.btn_export.setEnabled(False)

        start_time = time.time()
        exported_data = {
            "meta": {
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "model_node": target_model_node,
                "total_joints": len(joints),
                "start_frame": start_frame,
                "end_frame": end_frame,
                "step": step,
                "total_exported_frames": total_steps
            },
            "joints_list": [],
            "frames": {}
        }

        # ジョイント基本情報リストの構築
        joint_info_map = {}
        for j in joints:
            short_name = j.split('|')[-1].split(':')[-1]
            orig_name = short_name
            if mc.attributeQuery('originalName', node=j, exists=True):
                val = mc.getAttr(f"{j}.originalName")
                if val:
                    orig_name = val
            j_info = {
                "dag_path": j,
                "short_name": short_name,
                "original_name": orig_name
            }
            joint_info_map[j] = j_info
            exported_data["joints_list"].append(j_info)

        # 各フレームの状態収集
        try:
            curr_idx = 0
            for f in range(start_frame, end_frame + 1, step):
                mc.currentTime(f, update=True)
                frame_data = {}

                for j in joints:
                    info = joint_info_map[j]
                    key_name = info["original_name"]

                    # ローカル移動・回転
                    try:
                        t = mc.getAttr(f"{j}.translate")[0]
                        loc_t = [round(v, 5) for v in t]
                    except Exception:
                        loc_t = [0.0, 0.0, 0.0]

                    try:
                        r = mc.getAttr(f"{j}.rotate")[0]
                        loc_r = [round(v, 5) for v in r]
                    except Exception:
                        loc_r = [0.0, 0.0, 0.0]

                    # ワールド座標移動・回転
                    try:
                        ws_t = mc.xform(j, query=True, worldSpace=True, translation=True)
                        world_t = [round(v, 5) for v in ws_t]
                    except Exception:
                        world_t = [0.0, 0.0, 0.0]

                    try:
                        ws_r = mc.xform(j, query=True, worldSpace=True, rotation=True)
                        world_r = [round(v, 5) for v in ws_r]
                    except Exception:
                        world_r = [0.0, 0.0, 0.0]

                    frame_data[key_name] = {
                        "short_name": info["short_name"],
                        "dag_path": info["dag_path"],
                        "translate": loc_t,
                        "rotate": loc_r,
                        "world_translation": world_t,
                        "world_rotation": world_r
                    }

                exported_data["frames"][str(f)] = frame_data
                curr_idx += 1
                self.prog_bar.setValue(curr_idx)
                QtWidgets.QApplication.processEvents()

            # ディレクトリの自動作成とファイル書き込み
            out_dir = os.path.dirname(save_path)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir)

            with open(save_path, 'w', encoding='utf-8') as fp:
                json.dump(exported_data, fp, ensure_ascii=False, indent=2)

            elapsed = time.time() - start_time
            QtWidgets.QMessageBox.information(
                self,
                "エクスポート完了",
                f"ボーン状態データの書き出しが完了しました。\n\n"
                f"出力先: {save_path}\n"
                f"出力フレーム数: {total_steps} フレーム\n"
                f"対象ボーン数: {len(joints)} 本\n"
                f"所要時間: {elapsed:.2f} 秒"
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "エクスポート失敗", f"データ書き出し中にエラーが発生しました:\n{e}"
            )
        finally:
            # タイムラインを元のフレームへ復元
            try:
                mc.currentTime(orig_frame, update=True)
            except Exception:
                pass
            self.btn_export.setEnabled(True)


def show_bone_state_export_dialog():
    """ボーン状態JSONエクスポートダイアログを表示"""
    global _bone_state_export_dialog_instance

    try:
        from maya import OpenMayaUI as omui
        if PYSIDE_VER == 6:
            from shiboken6 import wrapInstance
        else:
            from shiboken2 import wrapInstance
        ptr = omui.MQtUtil.mainWindow()
        parent = wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None
    except Exception:
        parent = None

    if _bone_state_export_dialog_instance is not None:
        try:
            _bone_state_export_dialog_instance.close()
            _bone_state_export_dialog_instance.deleteLater()
        except Exception:
            pass
        _bone_state_export_dialog_instance = None

    _bone_state_export_dialog_instance = BoneStateExportDialog(parent)
    _bone_state_export_dialog_instance.show()
    _bone_state_export_dialog_instance.raise_()
    _bone_state_export_dialog_instance.activateWindow()
