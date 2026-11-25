cmake_minimum_required(VERSION 3.20...4.4)

# プロジェクト名定義: MMD統合マテリアル・独自レンダラープラグイン
project(mmd_material)

# C++17規格の指定
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# MSVCでUTF-8文字コードを有効化
if(MSVC)
    add_compile_options(/utf-8)
endif()

# Maya devkitの環境変数を自動補完
if(DEFINED DEVKIT_LOCATION)
    set(ENV{DEVKIT_LOCATION} "${DEVKIT_LOCATION}")
endif()
if(NOT DEFINED ENV{DEVKIT_LOCATION})
    if(EXISTS "C:/Autodesk_devkit/devkitBase_2025")
        set(ENV{DEVKIT_LOCATION} "C:/Autodesk_devkit/devkitBase_2025")
    elseif(DEFINED ENV{USERPROFILE})
        file(TO_CMAKE_PATH "$ENV{USERPROFILE}/devkitBase" DEVKIT_PATH)
        set(ENV{DEVKIT_LOCATION} "${DEVKIT_PATH}")
    endif()
endif()

# Maya devkitの設定読み込み
include($ENV{DEVKIT_LOCATION}/cmake/pluginEntry.cmake)

# プロジェクト名定義
set(PROJECT_NAME mmd_material)

# インクルードディレクトリ追加
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# ソースファイル定義
set(SOURCE_FILES
    src/plugin_main.cpp
    src/mmd_material_node.cpp
    src/mmd_shader_override.cpp
    src/mmd_toon_node.cpp
    src/mmd_toon_override.cpp
    src/mmd_render_override.cpp
    src/mmd_render_cmd.cpp
    src/mmd_edge_scene_pass.cpp
    include/mmd_material_node.h
    include/mmd_shader_override.h
    include/mmd_shader_code.h
    include/mmd_toon_node.h
    include/mmd_toon_override.h
    include/mmd_render_override.h
    include/mmd_render_cmd.h
    include/mmd_edge_scene_pass.h
    include/mmd_edge_shader_code.h
)

# リンクライブラリ定義 (RenderView / レンダラーUI連携を見据えて OpenMayaUI を追加)
set(LIBRARIES
    OpenMaya
    OpenMayaRender
    OpenMayaUI
    Foundation
)

# Mayaプラグイン (.mll) のビルド
build_plugin()
