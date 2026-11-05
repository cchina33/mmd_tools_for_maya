# -*- coding: utf-8 -*-
"""
モデル種別判定マネージャー (スカイドーム / 大型ステージ / 通常キャラクター)
ユーザー定義キーワードおよび個別モデルファイル指定のJSON永続化と判定ロジックを提供します。
"""

import os
import json
try:
    import maya.cmds as mc
except ImportError:
    mc = None

# デフォルトキーワード定義
DEFAULT_SKYDOME_KEYWORDS = [
    "skydome", "sky_dome", "dome_", "スカイドーム", "天球",
    "青空", "夜空", "宇宙", "skysphere", "celestial"
]

DEFAULT_STAGE_KEYWORDS = [
    "stage", "ステージ", "floor", "床", "ground", "地面",
    "room", "hall", "house", "building", "建物", "城", "街",
    "acute", "plaza", "広場", "checker", "tile", "タイル"
]

def _get_settings_file_path():
    """設定JSONファイルの保存先パスを返します"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "model_classifier_settings.json")


class ModelClassifierManager:
    """
    モデル種別の判定および設定を管理するクラスです。
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        """シングルトンインスタンスを取得します"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.settings_path = _get_settings_file_path()
        self.skydome_keywords = list(DEFAULT_SKYDOME_KEYWORDS)
        self.stage_keywords = list(DEFAULT_STAGE_KEYWORDS)
        # ファイルパス（またはファイル名） -> 種別 ('skydome', 'stage', 'character')
        self.file_overrides = {}
        self.load_settings()

    def reset_to_defaults(self):
        """キーワードを初期デフォルト値に戻します（個別指定は保持）"""
        self.skydome_keywords = list(DEFAULT_SKYDOME_KEYWORDS)
        self.stage_keywords = list(DEFAULT_STAGE_KEYWORDS)

    def load_settings(self):
        """設定ファイルから読み込みます"""
        if not os.path.exists(self.settings_path):
            self.reset_to_defaults()
            self.file_overrides = {}
            return

        try:
            with open(self.settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.skydome_keywords = data.get("skydome_keywords") or list(DEFAULT_SKYDOME_KEYWORDS)
            self.stage_keywords = data.get("stage_keywords") or list(DEFAULT_STAGE_KEYWORDS)
            self.file_overrides = data.get("file_overrides", {})
        except Exception as e:
            print(f"[ModelClassifier] 設定読み込みエラー（デフォルトを使用します）: {e}")
            self.reset_to_defaults()
            self.file_overrides = {}

    def save_settings(self):
        """現在の設定をJSONファイルへ保存します"""
        data = {
            "skydome_keywords": self.skydome_keywords,
            "stage_keywords": self.stage_keywords,
            "file_overrides": self.file_overrides
        }
        try:
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[ModelClassifier] 設定保存エラー: {e}")
            return False

    def set_file_override(self, file_path, kind):
        """
        特定モデルファイルの種別を明示的に登録・上書きします。
        kind: 'skydome', 'stage', 'character'
        """
        if not file_path:
            return
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        self.file_overrides[norm_path] = kind

    def remove_file_override(self, file_path):
        """特定モデルファイルの個別指定を解除します"""
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        norm_lower = norm_path.lower()
        b_name_lower = os.path.basename(norm_path).lower()

        keys_to_del = []
        for k in self.file_overrides.keys():
            k_lower = k.lower()
            if k_lower == norm_lower or os.path.basename(k_lower) == b_name_lower:
                keys_to_del.append(k)

        for k in keys_to_del:
            del self.file_overrides[k]
        return len(keys_to_del) > 0

    def get_file_override(self, file_path_or_name):
        """指定されたファイルパスまたはファイル名に対する個別指定種別を取得します"""
        if not file_path_or_name:
            return None
        norm_path = os.path.normpath(file_path_or_name).replace("\\", "/")
        norm_lower = norm_path.lower()
        b_name_lower = os.path.basename(norm_path).lower()

        # パスまたはファイル名による検索（大文字小文字問わず照合）
        for k, v in self.file_overrides.items():
            k_lower = k.lower()
            if k_lower == norm_lower or os.path.basename(k_lower) == b_name_lower:
                return v

        return None

    def resolve_model_source_file(self, mesh_node):
        """メッシュまたは親ノードから記録された元モデルファイルパスを逆引きします"""
        if not mesh_node or not mc.objExists(mesh_node):
            return None

        # メッシュ自身のカスタム属性
        if mc.attributeQuery("mmdSourceFilePath", node=mesh_node, exists=True):
            val = mc.getAttr(f"{mesh_node}.mmdSourceFilePath")
            if val:
                return val

        # 親ノード（トランスフォームまたはモデルルート）を走査
        parents = mc.listRelatives(mesh_node, parent=True, fullPath=True) or []
        for p in parents:
            if mc.attributeQuery("mmdSourceFilePath", node=p, exists=True):
                val = mc.getAttr(f"{p}.mmdSourceFilePath")
                if val:
                    return val

        return None

    def is_skydome_mesh(self, mesh_node, file_path=None):
        """
        指定されたメッシュがスカイドーム（天球・背景空）であるかを判定します。
        個別指定が設定されている場合はそれを最優先します。
        """
        if not mesh_node or not mc.objExists(mesh_node):
            return False

        # ファイルパスの個別指定を確認
        target_path = file_path or self.resolve_model_source_file(mesh_node)
        override = self.get_file_override(target_path)
        if override:
            return override == "skydome"

        # ノード名・親グループ名の文字列取得
        full_path = mc.ls(mesh_node, long=True)[0] if mc.ls(mesh_node, long=True) else mesh_node
        path_lower = full_path.lower()

        # ステージ系キーワードが含まれる場合はスカイドームから除外
        if any(k.lower() in path_lower for k in self.stage_keywords):
            return False

        # メッシュに割り当てられている材質（シェーディンググループ）数を調査
        num_materials = 0
        try:
            shading_groups = mc.listConnections(mesh_node, type="shadingEngine") or []
            num_materials = len(set(shading_groups))
        except Exception:
            pass

        # 材質数が5個以上の複合モデルは除外
        if num_materials > 4:
            return False

        # スカイドームキーワードの照合
        if any(k.lower() in path_lower for k in self.skydome_keywords):
            return True

        # キーワードがなくとも、材質数が少なく（4以下）、かつ巨大な球体・ドーム形状の場合
        try:
            bb = mc.exactWorldBoundingBox(mesh_node)
            width = abs(bb[3] - bb[0])
            height = abs(bb[4] - bb[1])
            depth = abs(bb[5] - bb[2])
            if width >= 200.0 and depth >= 200.0 and height >= 80.0 and num_materials <= 4:
                return True
        except Exception:
            pass

        return False

    def is_stage_mesh(self, mesh_node, file_path=None):
        """
        指定されたメッシュがステージ（床・建物・広域背景）であるかを判定します。
        個別指定が設定されている場合はそれを最優先します。
        """
        if not mesh_node or not mc.objExists(mesh_node):
            return False

        # カメラ、ライト、地面影、剛体補助は除外
        if "mmd_ground_shadow" in mesh_node or any(k in mesh_node for k in ["Camera", "Light", "light", "mmd_rigid", "mmd_joint"]):
            return False

        # ファイルパスの個別指定を確認
        target_path = file_path or self.resolve_model_source_file(mesh_node)
        override = self.get_file_override(target_path)
        if override:
            return override == "stage"

        # スカイドームと判定されたものはステージから除外
        if self.is_skydome_mesh(mesh_node, file_path=target_path):
            return False

        # スキニング（skinCluster）やジョイントが存在するキャラクターメッシュはステージから除外
        try:
            skin_clusters = mc.ls(mc.listHistory(mesh_node), type="skinCluster") or []
            if skin_clusters:
                return False
        except Exception:
            pass

        # フルパスと親ノード名
        parents = mc.listRelatives(mesh_node, parent=True, fullPath=True) or []
        path_str = (mesh_node + " " + " ".join(parents)).lower()

        # ステージキーワード照合
        if any(k.lower() in path_str for k in self.stage_keywords):
            return True

        # バウンディングボックスによる寸法・形状判定
        try:
            bb = mc.exactWorldBoundingBox(mesh_node)
            width = abs(bb[3] - bb[0])
            height = abs(bb[4] - bb[1])
            depth = abs(bb[5] - bb[2])

            # 人型キャラクター特有の縦長プロポーション（高さがあり、幅・奥行きより背が高い）は除外
            # レミリアやフランドール等の羽・装飾付きキャラクターの誤認を防止
            if height >= 60.0 and height > width * 0.6 and height > depth * 0.6:
                return False

            # 水平方向に広く、高さが平坦な床状メッシュ
            is_flat_floor = (width >= 80.0 or depth >= 80.0) and (height <= 25.0 or (height <= width * 0.15 and height <= depth * 0.15))

            # 幅と奥行きの双方が十分に広大な大型複合ステージ（建物・街・広域背景）
            # キャラクターの誤認を防ぐため幅・奥行き双方250以上を要求
            shading_groups = mc.listConnections(mesh_node, type="shadingEngine") or []
            num_materials = len(set(shading_groups))
            is_multi_mat_large = (width >= 250.0 and depth >= 250.0) and num_materials >= 5

            if is_flat_floor or is_multi_mat_large:
                return True
        except Exception:
            pass

        return False
