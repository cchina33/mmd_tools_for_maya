cmake_minimum_required(VERSION 3.13)

# プロジェクト名定義
project(mmd_material)

# MSVCでUTF-8文字コードを有効化
if(MSVC)
    add_compile_options(/utf-8)
endif()

# Maya devkitの環境変数を自動補完
if(NOT DEFINED ENV{DEVKIT_LOCATION})
    if(DEFINED ENV{USERPROFILE})
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
    include/mmd_material_node.h
    include/mmd_shader_override.h
    include/mmd_shader_code.h
)

# リンクライブラリ定義
set(LIBRARIES
    OpenMaya
    OpenMayaRender
    Foundation
)

# Mayaプラグイン (.mll) のビルド
build_plugin()
