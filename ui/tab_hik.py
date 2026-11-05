# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - HumanIK 管理タブおよび独立ウィンドウ
"""

from .common import *

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
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

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
        self.scroll_area.setMinimumHeight(220)
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
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

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
