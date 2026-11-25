# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - モデル改造・お着替え処理パッケージ
スキンウェイトの保存・復元・頂点番号付け替え、Undoチャンク制御、
シーン自動バックアップ、標準ボーン基準の自動位置合わせ、
ウェイト基準の頭・体自動パーツ分け、非結合方式の首継ぎ目処理、
ボーン対応表によるボーン統合、剛体・Jointの物理統合、
および書き出し前最終チェック機能を提供します。
"""

import importlib
from . import skin_utils
from . import align
from . import part_split
from . import neck_seam
from . import bone_merge
from . import physics_merge
from . import validate

importlib.reload(skin_utils)
importlib.reload(align)
importlib.reload(part_split)
importlib.reload(neck_seam)
importlib.reload(bone_merge)
importlib.reload(physics_merge)
importlib.reload(validate)

from .skin_utils import (
    CACHE_HOLDER_NODE,
    CACHE_ATTR_NAME,
    undo_chunk,
    create_scene_backup,
    get_skin_cluster,
    get_model_meshes,
    get_model_joints,
    get_bone_canonical_name,
    extract_mesh_skin_weights,
    remap_skin_weights,
    apply_mesh_skin_weights,
    save_model_weights_to_scene,
    load_model_weights_from_scene,
    has_scene_weight_cache,
    list_scene_weight_caches,
    clear_scene_weight_cache,
    rebind_mesh_from_scene_cache,
    set_models_bone_visibility,
)

from .align import (
    check_standard_bones,
    get_common_anchor_bones,
    estimate_alignment_transform,
    preview_alignment_transform,
    reset_alignment_preview,
    commit_alignment_transform,
)

from .part_split import (
    get_head_bone_set,
    classify_head_body_faces,
    preview_part_split,
    commit_part_split_deletion,
)

from .neck_seam import (
    PREVIEW_GROUP_NAME,
    extract_neck_boundary_vertices,
    find_neck_seam_pairs,
    preview_neck_seam,
    clear_neck_seam_preview,
    process_neck_seam,
    smooth_single_model_neck_normals,
    measure_neck_seam_gap,
    test_neck_bend,
    reset_neck_bend,
)

from .bone_merge import (
    load_bone_name_dictionary,
    normalize_mmd_bone_name,
    build_bone_merge_plan,
    execute_bone_merge,
)

from .physics_merge import (
    collect_model_physics_data,
    analyze_collision_groups,
    build_physics_merge_plan,
    execute_physics_merge,
)

from .validate import (
    clamp_max_4_influences,
    validate_dressup_models,
)

__all__ = [
    "CACHE_HOLDER_NODE",
    "CACHE_ATTR_NAME",
    "undo_chunk",
    "create_scene_backup",
    "get_skin_cluster",
    "get_model_meshes",
    "get_model_joints",
    "get_bone_canonical_name",
    "extract_mesh_skin_weights",
    "remap_skin_weights",
    "apply_mesh_skin_weights",
    "save_model_weights_to_scene",
    "load_model_weights_from_scene",
    "has_scene_weight_cache",
    "list_scene_weight_caches",
    "clear_scene_weight_cache",
    "rebind_mesh_from_scene_cache",
    "set_models_bone_visibility",
    "check_standard_bones",
    "get_common_anchor_bones",
    "estimate_alignment_transform",
    "preview_alignment_transform",
    "reset_alignment_preview",
    "commit_alignment_transform",
    "get_head_bone_set",
    "classify_head_body_faces",
    "preview_part_split",
    "commit_part_split_deletion",
    "PREVIEW_GROUP_NAME",
    "extract_neck_boundary_vertices",
    "find_neck_seam_pairs",
    "preview_neck_seam",
    "clear_neck_seam_preview",
    "process_neck_seam",
    "smooth_single_model_neck_normals",
    "measure_neck_seam_gap",
    "test_neck_bend",
    "reset_neck_bend",
    "load_bone_name_dictionary",
    "normalize_mmd_bone_name",
    "build_bone_merge_plan",
    "execute_bone_merge",
    "collect_model_physics_data",
    "analyze_collision_groups",
    "build_physics_merge_plan",
    "execute_physics_merge",
    "clamp_max_4_influences",
    "validate_dressup_models",
]
