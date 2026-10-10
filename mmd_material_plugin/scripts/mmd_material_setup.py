# -*- coding: utf-8 -*-
"""
MMD Material Setup Helper for Maya
MMDオリジナルマテリアルプラグイン (mmdMaterial) の生成・設定用ヘルパースクリプト
"""

import os
import maya.cmds as cmds
import maya.mel as mel

# プラグイン名
PLUGIN_NAME = "mmd_material.mll"

def get_plugin_path():
    """プラグインバイナリの絶対パスを取得"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_dir = os.path.abspath(os.path.join(script_dir, "..", "bin"))
    return os.path.join(plugin_dir, PLUGIN_NAME)

def setup_hypershade_callbacks():
    """
    Hypershade に MmdMat > Material カテゴリを登録し、
    Maya 標準の Surface カテゴリから mmdMaterial を除外するためのコールバックを設定
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mel_path = os.path.join(script_dir, "mmd_material_hypershade.mel").replace("\\", "/")

    if os.path.exists(mel_path):
        try:
            mel.eval('source "{}";'.format(mel_path))
            mel.eval("mmdMaterial_RegisterCallbacks();")
        except Exception as e:
            cmds.warning("Hypershade コールバックの登録に失敗しました: {}".format(e))


def ensure_plugin_loaded():
    """mmd_materialプラグインがロードされていることを確認し、Hypershade連携を設定"""
    loaded = False
    if cmds.pluginInfo(PLUGIN_NAME, query=True, loaded=True):
        loaded = True
    else:
        plugin_path = get_plugin_path()
        if os.path.exists(plugin_path):
            try:
                cmds.loadPlugin(plugin_path)
                loaded = True
            except Exception as e:
                cmds.warning("MMDマテリアルプラグインのロードに失敗しました: {}".format(e))
                return False
        else:
            cmds.warning("プラグインファイルが存在しません: {}".format(plugin_path))
            return False

    if loaded:
        # 次回以降の自動ロードを有効化
        try:
            cmds.pluginInfo(PLUGIN_NAME, edit=True, autoload=True)
        except Exception:
            pass
        # Hypershade 用のコールバックを有効化
        setup_hypershade_callbacks()

    return loaded

def create_mmd_material(name="mmdMaterial",
                        diffuse=(1.0, 1.0, 1.0),
                        alpha=1.0,
                        specular=(0.0, 0.0, 0.0),
                        power=5.0,
                        ambient=(0.5, 0.5, 0.5),
                        color_tex_path="",
                        sphere_tex_path="",
                        sphere_mode=0,
                        toon_tex_path="",
                        toon_mode=1,
                        edge_enable=True,
                        edge_color=(0.0, 0.0, 0.0, 1.0),
                        edge_size=1.0):
    """
    MMDオリジナルマテリアルノードおよびシェーディンググループを生成

    :param name: マテリアル名
    :param diffuse: 拡散色 (R, G, B)
    :param alpha: 不透明度
    :param specular: 反射色 (R, G, B)
    :param power: 光沢度 (Shininess)
    :param ambient: 環境光色 (R, G, B)
    :param color_tex_path: 通常テクスチャファイルパス
    :param sphere_tex_path: スフィアテクスチャファイルパス
    :param sphere_mode: スフィアモード (0: 無効, 1: 乗算, 2: 加算, 3: 減算)
    :param toon_tex_path: Toonテクスチャファイルパス
    :param toon_mode: Toonモード (0: 無効, 1: MMD標準)
    :param edge_enable: エッジ有効フラグ
    :param edge_color: エッジ色 (R, G, B, A)
    :param edge_size: エッジサイズ
    :return: (material_node, shading_engine)
    """
    if not ensure_plugin_loaded():
        raise RuntimeError("MMDマテリアルプラグインが利用できません。")

    # マテリアルノードの作成
    mat_node = cmds.shadingNode("mmdMaterial", asShader=True, name=name)

    # シェーディンググループ (shadingEngine) の作成
    sg_node = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")

    # サーフェスシェーダーとしての接続
    cmds.connectAttr(mat_node + ".outColor", sg_node + ".surfaceShader", force=True)

    # 基礎カラーパラメータの設定
    try:
        cmds.setAttr(mat_node + ".color", diffuse[0], diffuse[1], diffuse[2], type="double3")
    except Exception:
        pass

    try:
        cmds.setAttr(mat_node + ".diffuseColor", diffuse[0], diffuse[1], diffuse[2], type="double3")
    except Exception:
        pass

    try:
        cmds.setAttr(mat_node + ".diffuseAlpha", float(alpha))
    except Exception:
        pass

    # 透過度設定 (alphaからtransparencyへの逆算)
    try:
        inv_alpha = max(0.0, min(1.0, 1.0 - float(alpha)))
        cmds.setAttr(mat_node + ".transparency", inv_alpha, inv_alpha, inv_alpha, type="double3")
    except Exception:
        pass

    try:
        cmds.setAttr(mat_node + ".specularColor", specular[0], specular[1], specular[2], type="double3")
        cmds.setAttr(mat_node + ".specularPower", float(power))
        cmds.setAttr(mat_node + ".cosinePower", float(power))
        cmds.setAttr(mat_node + ".ambientColor", ambient[0], ambient[1], ambient[2], type="double3")
    except Exception:
        pass

    # スフィア・Toon設定（属性が存在しない場合でも安全にスキップ）
    try:
        if cmds.attributeQuery("sphereMode", node=mat_node, exists=True):
            cmds.setAttr(mat_node + ".sphereMode", int(sphere_mode))
    except Exception:
        pass

    try:
        if cmds.attributeQuery("toonMode", node=mat_node, exists=True):
            cmds.setAttr(mat_node + ".toonMode", int(toon_mode))
    except Exception:
        pass

    # テクスチャパスアトリビュートが存在する場合のみ安全に設定
    try:
        if color_tex_path and cmds.attributeQuery("colorTexturePath", node=mat_node, exists=True):
            cmds.setAttr(mat_node + ".colorTexturePath", str(color_tex_path), type="string")
    except Exception:
        pass

    try:
        if sphere_tex_path and cmds.attributeQuery("sphereTexturePath", node=mat_node, exists=True):
            cmds.setAttr(mat_node + ".sphereTexturePath", str(sphere_tex_path), type="string")
    except Exception:
        pass

    try:
        if toon_tex_path and cmds.attributeQuery("toonTexturePath", node=mat_node, exists=True):
            cmds.setAttr(mat_node + ".toonTexturePath", str(toon_tex_path), type="string")
    except Exception:
        pass

    # エッジパラメータの設定
    try:
        if cmds.attributeQuery("edgeEnable", node=mat_node, exists=True):
            cmds.setAttr(mat_node + ".edgeEnable", bool(edge_enable))
        if len(edge_color) >= 3 and cmds.attributeQuery("edgeColor", node=mat_node, exists=True):
            cmds.setAttr(mat_node + ".edgeColor", edge_color[0], edge_color[1], edge_color[2], type="double3")
        if cmds.attributeQuery("edgeSize", node=mat_node, exists=True):
            cmds.setAttr(mat_node + ".edgeSize", float(edge_size))
    except Exception:
        pass

    return mat_node, sg_node


def find_color_source_plug(src_node):
    """
    既存シェーダーのカラー入力に接続されているソースプラグ (file.outColor 等) を探索
    """
    if not src_node or not cmds.objExists(src_node):
        return None

    # カラーを表す主要アトリビュート候補
    color_attrs = ["color", "baseColor", "diffuseColor", "Color", "diffuse"]
    for attr in color_attrs:
        full_attr = "{}.{}".format(src_node, attr)
        if cmds.objExists(full_attr):
            conns = cmds.listConnections(full_attr, source=True, destination=False, plugs=True)
            if conns:
                return conns[0]
    return None


def find_transparency_source_plug(src_node):
    """
    既存シェーダーの透過度入力に接続されているソースプラグを探索
    """
    if not src_node or not cmds.objExists(src_node):
        return None

    transp_attrs = [
        "transparency", "opacity", "cutoutOpacity", "Transparency",
        "opacityR", "opacityG", "opacityB",
        "transparencyR", "transparencyG", "transparencyB",
        "transparencyX", "transparencyY", "transparencyZ"
    ]
    for attr in transp_attrs:
        full_attr = "{}.{}".format(src_node, attr)
        if cmds.objExists(full_attr):
            conns = cmds.listConnections(full_attr, source=True, destination=False, plugs=True)
            if conns:
                return conns[0]
    return None


def get_material_info(shader_node):
    """
    既存シェーダーから各種カラー値およびテクスチャ接続情報を抽出
    """
    info = {
        "color_plug": None,
        "color_val": (1.0, 1.0, 1.0),
        "transp_plug": None,
        "alpha_val": 1.0,
        "specular_val": (0.0, 0.0, 0.0),
        "power_val": 5.0,
        "ambient_val": (0.5, 0.5, 0.5), # MMD標準環境光
        "sphere_plug": None,
        "toon_plug": None,
        "edge_enable": True,
        "edge_color": (0.0, 0.0, 0.0),
        "edge_size": 1.0,
    }

    if not shader_node or not cmds.objExists(shader_node):
        return info

    # カラー接続および静的カラー
    info["color_plug"] = find_color_source_plug(shader_node)
    for cattr in ["color", "baseColor", "diffuseColor"]:
        if cmds.attributeQuery(cattr, node=shader_node, exists=True):
            conns = cmds.listConnections(f"{shader_node}.{cattr}", source=True, destination=False)
            if not conns:
                try:
                    c = cmds.getAttr("{}.{}".format(shader_node, cattr))[0]
                    if sum(c) > 0.01:
                        info["color_val"] = (float(c[0]), float(c[1]), float(c[2]))
                        break
                except Exception:
                    pass

    # 透過接続および静的透過度
    info["transp_plug"] = find_transparency_source_plug(shader_node)
    if cmds.attributeQuery("diffuseAlpha", node=shader_node, exists=True):
        # mmdMaterial等: 1.0=不透明, 0.0=透明
        try:
            val = cmds.getAttr("{}.diffuseAlpha".format(shader_node))
            info["alpha_val"] = max(0.0, min(1.0, float(val)))
        except Exception:
            pass
    elif cmds.attributeQuery("opacity", node=shader_node, exists=True):
        # standardSurface等: 白(1,1,1)=不透明, 黒(0,0,0)=透明
        try:
            op = cmds.getAttr("{}.opacity".format(shader_node))[0]
            avg_op = (float(op[0]) + float(op[1]) + float(op[2])) / 3.0
            info["alpha_val"] = max(0.0, min(1.0, avg_op))
        except Exception:
            pass
    elif cmds.attributeQuery("transparency", node=shader_node, exists=True):
        # blinn, phong, lambert等: 黒(0,0,0)=不透明, 白(1,1,1)=透明
        try:
            t = cmds.getAttr("{}.transparency".format(shader_node))[0]
            avg_t = (float(t[0]) + float(t[1]) + float(t[2])) / 3.0
            info["alpha_val"] = max(0.0, min(1.0, 1.0 - avg_t))
        except Exception:
            pass

    # 反射色
    for sattr in ["specularColor", "specular_color"]:
        if cmds.attributeQuery(sattr, node=shader_node, exists=True):
            try:
                sc = cmds.getAttr("{}.{}".format(shader_node, sattr))[0]
                info["specular_val"] = (float(sc[0]), float(sc[1]), float(sc[2]))
                break
            except Exception:
                pass

    # 環境光色
    for aattr in ["ambientColor"]:
        if cmds.attributeQuery(aattr, node=shader_node, exists=True):
            try:
                ac = cmds.getAttr("{}.{}".format(shader_node, aattr))[0]
                info["ambient_val"] = (float(ac[0]), float(ac[1]), float(ac[2]))
                break
            except Exception:
                pass

    # スフィア・Toon（incandescence等に接続されている場合やmmd固有アトリビュートからの探索）
    try:
        if cmds.attributeQuery("sphereTexturePath", node=shader_node, exists=True):
            conns = cmds.listConnections("{}.sphereTexturePath".format(shader_node), source=True, destination=False, plugs=True)
            if conns:
                info["sphere_plug"] = conns[0]
    except Exception:
        pass

    try:
        if cmds.attributeQuery("toonTexturePath", node=shader_node, exists=True):
            conns = cmds.listConnections("{}.toonTexturePath".format(shader_node), source=True, destination=False, plugs=True)
            if conns:
                info["toon_plug"] = conns[0]
    except Exception:
        pass

    # エッジパラメータの取得
    if cmds.attributeQuery("edgeEnable", node=shader_node, exists=True):
        try:
            info["edge_enable"] = bool(cmds.getAttr("{}.edgeEnable".format(shader_node)))
        except Exception:
            pass
    if cmds.attributeQuery("edgeColor", node=shader_node, exists=True):
        try:
            ec = cmds.getAttr("{}.edgeColor".format(shader_node))[0]
            info["edge_color"] = (float(ec[0]), float(ec[1]), float(ec[2]))
        except Exception:
            pass
    if cmds.attributeQuery("edgeSize", node=shader_node, exists=True):
        try:
            info["edge_size"] = float(cmds.getAttr("{}.edgeSize".format(shader_node)))
        except Exception:
            pass

    return info


def convert_shader_to_mmd_material(shader_node, inherit_textures=True):
    """
    既存シェーダーを解析し、対応する mmdMaterial ノードを生成してテクスチャやパラメータを引き継ぐ
    """
    if not ensure_plugin_loaded():
        raise RuntimeError("MMDマテリアルプラグインが利用できません。")

    base_name = shader_node
    clean_name = base_name.lstrip("_")
    if not clean_name:
        clean_name = "mat"
    mat_name = f"mmd_{clean_name}"


    info = get_material_info(shader_node) if inherit_textures else {
        "color_plug": None,
        "color_val": (1.0, 1.0, 1.0),
        "transp_plug": None,
        "alpha_val": 1.0,
        "specular_val": (0.0, 0.0, 0.0),
        "power_val": 5.0,
        "ambient_val": (0.5, 0.5, 0.5),
        "sphere_plug": None,
        "toon_plug": None,
    }

    # 新規 mmdMaterial ノードの作成
    mmd_node = cmds.shadingNode("mmdMaterial", asShader=True, name=mat_name)

    # 基礎カラー設定
    c = info["color_val"]
    # カラーテクスチャが接続されている場合や値が極小の場合は MMD標準ディフューズカラー (1,1,1) を適用
    if info["color_plug"] or sum(c) < 0.05:
        c = (1.0, 1.0, 1.0)
    try:
        cmds.setAttr(mmd_node + ".color", c[0], c[1], c[2], type="double3")
    except Exception:
        pass
    try:
        cmds.setAttr(mmd_node + ".diffuseColor", c[0], c[1], c[2], type="double3")
    except Exception:
        pass

    # 不透明度・透過度設定
    alpha = info["alpha_val"]
    try:
        cmds.setAttr(mmd_node + ".diffuseAlpha", alpha)
        inv_a = max(0.0, min(1.0, 1.0 - alpha))
        cmds.setAttr(mmd_node + ".transparency", inv_a, inv_a, inv_a, type="double3")
    except Exception:
        pass

    # 反射・環境光・拡散反射係数 (MMD本来の明るく鮮やかな発色に最適化)
    sc = info["specular_val"]
    ac = info["ambient_val"]
    # 環境光が未設定または極小の場合は MMD標準環境光 (0.5, 0.5, 0.5) を適用
    if sum(ac) < 0.15:
        ac = (0.5, 0.5, 0.5)
    try:
        cmds.setAttr(mmd_node + ".diffuse", 1.0)
        cmds.setAttr(mmd_node + ".specularColor", sc[0], sc[1], sc[2], type="double3")
        cmds.setAttr(mmd_node + ".ambientColor", ac[0], ac[1], ac[2], type="double3")
    except Exception:
        pass

    # テクスチャノードの引き継ぎ接続
    if inherit_textures and info["color_plug"]:
        try:
            cmds.connectAttr(info["color_plug"], mmd_node + ".color", force=True)
        except Exception as e:
            cmds.warning("カラーテクスチャの引き継ぎ接続に失敗しました: {}".format(e))

    if inherit_textures and info["transp_plug"]:
        try:
            transp_source = info["transp_plug"]
            src_node_name = transp_source.split(".")[0]
            # 接続元が file ノードの outAlpha（StandardSurface等の不透明度）の場合、
            # mmdMaterial は transparency（0=不透明, 1=透明）のため、
            # 同一 file ノードの outTransparency を接続して白黒反転を防止
            if cmds.nodeType(src_node_name) == "file" and transp_source.endswith(".outAlpha"):
                transp_source = f"{src_node_name}.outTransparency"
            elif cmds.nodeType(src_node_name) == "multDoubleLinear" and transp_source.endswith(".output"):
                # 乗算アルファ（材質アルファ × テクスチャアルファ）の場合は reverse ノードを介して接続
                rev_name = f"{mat_name}_alpha_rev"
                rev_node = cmds.shadingNode("reverse", asUtility=True, name=rev_name)
                cmds.connectAttr(transp_source, f"{rev_node}.inputX", force=True)
                cmds.connectAttr(transp_source, f"{rev_node}.inputY", force=True)
                cmds.connectAttr(transp_source, f"{rev_node}.inputZ", force=True)
                transp_source = f"{rev_node}.output"

            cmds.connectAttr(transp_source, mmd_node + ".transparency", force=True)
        except Exception as e:
            cmds.warning(f"透過テクスチャの引き継ぎ接続に失敗しました: {e}")

    # スフィア・Toon のフォールバック（存在しなくてもエラーにしない）
    try:
        if cmds.attributeQuery("sphereMode", node=mmd_node, exists=True):
            cmds.setAttr(mmd_node + ".sphereMode", 0)
    except Exception:
        pass

    try:
        if cmds.attributeQuery("toonMode", node=mmd_node, exists=True):
            cmds.setAttr(mmd_node + ".toonMode", 1)
    except Exception:
        pass

    # MMDエッジパラメータの反映
    try:
        if cmds.attributeQuery("edgeEnable", node=mmd_node, exists=True):
            cmds.setAttr(mmd_node + ".edgeEnable", bool(info.get("edge_enable", True)))
        if cmds.attributeQuery("edgeColor", node=mmd_node, exists=True):
            ec = info.get("edge_color", (0.0, 0.0, 0.0))
            cmds.setAttr(mmd_node + ".edgeColor", ec[0], ec[1], ec[2], type="double3")
        if cmds.attributeQuery("edgeSize", node=mmd_node, exists=True):
            cmds.setAttr(mmd_node + ".edgeSize", float(info.get("edge_size", 1.0)))
    except Exception:
        pass

    return mmd_node


def get_meshes_from_targets(targets=None):
    """
    指定されたターゲット（または現在選択されているオブジェクト）からメッシュシェイプを全取得
    """
    if targets is None or not targets:
        targets = cmds.ls(selection=True, long=True) or []

    if not targets:
        return []

    mesh_shapes = set()
    for obj in targets:
        if not cmds.objExists(obj):
            continue
        if cmds.objectType(obj) == "mesh":
            mesh_shapes.add(obj)
        else:
            # トランスフォームノードまたはグループの場合、子孫のメッシュを探索
            shapes = cmds.listRelatives(obj, shapes=True, fullPath=True, noIntermediate=True) or []
            for s in shapes:
                if cmds.objectType(s) == "mesh":
                    mesh_shapes.add(s)
            # さらに深い階層の子孫も取得
            descendants = cmds.listRelatives(obj, allDescendents=True, fullPath=True, noIntermediate=True, type="mesh") or []
            for d in descendants:
                mesh_shapes.add(d)

    return list(mesh_shapes)


def ensure_mmd_lighting(shadow_mode=1):
    """
    シーン内に MMD 標準ライト (mmd_lighting_grp) が存在しない場合、
    MMD公式仕様に準拠した平行光源およびアンビエントライトを自動生成します。
    """
    # converters.pmxpaimaya の create_mmd_lighting を優先呼び出し (安全な重複防止と最適化)
    try:
        try:
            from ..converters import pmxpaimaya
        except Exception:
            import converters.pmxpaimaya as pmxpaimaya
        import importlib
        importlib.reload(pmxpaimaya)
        return pmxpaimaya.create_mmd_lighting(shadow_mode=shadow_mode)
    except Exception as e:
        cmds.warning(f"pmxpaimaya.create_mmd_lighting 呼び出しエラー: {e}")

    # フォールバック: 直接 Maya コマンドで MMD 標準ライトを作成
    try:
        dir_shape = cmds.directionalLight(name="mmd_directional_lightShape", intensity=1.0)
        dir_transform = cmds.listRelatives(dir_shape, parent=True)[0]
        cmds.rename(dir_transform, "mmd_directional_light")
        dir_light = "mmd_directional_light"
        cmds.setAttr(dir_light + ".rotate", -54.74, 45.0, 0.0, type="double3")
        cmds.setAttr(dir_light + ".color", 0.6039, 0.6039, 0.6039, type="double3")

        # アンビエントライト
        amb_shape = cmds.ambientLight(name="mmd_ambient_lightShape", intensity=0.55)
        amb_transform = cmds.listRelatives(amb_shape, parent=True)[0]
        cmds.rename(amb_transform, "mmd_ambient_light")
        amb_light = "mmd_ambient_light"
        cmds.setAttr(amb_light + ".ambientShade", 0.0)
        cmds.setAttr(amb_light + ".color", 0.50, 0.50, 0.50, type="double3")

        light_grp = cmds.group(dir_light, amb_light, name="mmd_lighting_grp")

        # ビューポートのライト表示を有効化
        try:
            panels = cmds.getPanel(type="modelPanel") or []
            for p in panels:
                cmds.modelEditor(p, edit=True, displayLights="all")
        except Exception:
            pass

        return light_grp
    except Exception as e:
        cmds.warning("MMD標準ライトの作成に失敗しました: {}".format(e))
        return None


def assign_mmd_material_to_model(targets=None, inherit_textures=True):
    """
    対象モデルまたはメッシュに mmdMaterial を生成してアサインする。
    既存マテリアルに file ノード等が設定されている場合は自動で引き継ぎ、
    スフィア・Toon が存在しない場合でも安全にフォールバック処理を行う。

    :param targets: 対象ノードのリスト（None時は現在選択中のオブジェクト）
    :param inherit_textures: 既存テクスチャ接続を引き継ぐかどうか
    :return: 変換・アサインされた (mmd_material_node, shading_engine) のリスト
    """
    if not ensure_plugin_loaded():
        cmds.warning("MMDマテリアルプラグインをロードできなかったため処理を中止します。")
        return []

    # MMD標準ライトが存在しない場合は自動作成して発色を最適化
    ensure_mmd_lighting()

    # Undo チャンクを開始（Ctrl+Z で一括復元可能にする）
    cmds.undoInfo(openChunk=True, chunkName="assignMmdMaterial")
    try:
        mesh_shapes = get_meshes_from_targets(targets)
        if not mesh_shapes:
            cmds.warning("アサイン対象のメッシュが見つかりませんでした。モデルまたはメッシュを選択してください。")
            return []

        assigned_results = []
        processed_sgs = set()

        for mesh in mesh_shapes:
            # メッシュに接続されているシェーディンググループ (shadingEngine) を取得
            sgs = cmds.listConnections(mesh, type="shadingEngine") or []
            for sg in sgs:
                if sg in processed_sgs:
                    continue
                processed_sgs.add(sg)

                # 現在のサーフェスシェーダーを取得
                surface_shaders = cmds.listConnections(sg + ".surfaceShader", source=True, destination=False) or []
                old_shader = surface_shaders[0] if surface_shaders else None

                if old_shader and cmds.nodeType(old_shader) == "mmdMaterial":
                    # 既に mmdMaterial の場合はスキップまたは報告
                    assigned_results.append((old_shader, sg))
                    continue

                # 新規 mmdMaterial の生成とパラメータ引き継ぎ
                shader_name = old_shader if old_shader else (sg.replace("SG", "") + "_mat")
                new_mmd_mat = convert_shader_to_mmd_material(shader_name, inherit_textures=inherit_textures)

                # シェーディンググループへの再接続
                try:
                    cmds.connectAttr(new_mmd_mat + ".outColor", sg + ".surfaceShader", force=True)
                    assigned_results.append((new_mmd_mat, sg))
                except Exception as e:
                    cmds.warning("シェーディンググループ {} への接続に失敗しました: {}".format(sg, e))

        # 透過材質の前後重なり（首影・頬色など）を描画順破綻なく綺麗に表現するため、
        # Viewport 2.0 の透過アルゴリズムを Depth Peeling (深度ピーリング) に設定
        try:
            if cmds.objExists('hardwareRenderingGlobals'):
                cmds.setAttr('hardwareRenderingGlobals.transparencyAlgorithm', 3)
        except Exception:
            pass

        # ビュー変換を 'Un-tone-mapped (sRGB)' に設定してトーンマッパーによる暗化・くすみを防止
        try:
            try:
                from ..converters import pmxpaimaya
            except Exception:
                import converters.pmxpaimaya as pmxpaimaya
            pmxpaimaya.set_untone_mapped_view_transform()
        except Exception:
            pass

        cmds.select(targets or [], replace=True)
        return assigned_results
    finally:
        # Undo チャンクを確実に終了
        cmds.undoInfo(closeChunk=True)

