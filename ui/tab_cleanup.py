# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - MMD削除・クリーンアップタブ
"""

from .common import *

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
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(14)
        layout.setContentsMargins(0, 0, 0, 0)

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
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

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
