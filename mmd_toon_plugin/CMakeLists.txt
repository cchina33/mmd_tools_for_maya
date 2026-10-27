cmake_minimum_required(VERSION 3.13)

# プロジェクト名定義: 新規MMDトゥーンシェーダープラグイン
project(mmd_toon_shader)

# MSVC環境でUTF-8文字コードを有効化
if(MSVC)
    add_compile_options(/utf-8)
endif()

# Maya Devkitの環境変数を自動設定
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

# Maya Devkitの設定読み込み
include($ENV{DEVKIT_LOCATION}/cmake/pluginEntry.cmake)

# プロジェクト名設定
set(PROJECT_NAME mmd_toon_shader)

# インクルードディレクトリの指定
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# ソースファイルの一覧定義
set(SOURCE_FILES
    src/plugin_main.cpp
    src/mmd_toon_node.cpp
    src/mmd_toon_override.cpp
    include/mmd_toon_node.h
    include/mmd_toon_override.h
)

# リンクライブラリの指定
set(LIBRARIES
    OpenMaya
    OpenMayaRender
    Foundation
)

# Mayaプラグイン (.mll) のビルド
build_plugin()
