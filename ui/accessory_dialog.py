# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - アクセサリ追従アタッチダイアログ
"""

from .common import *

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
