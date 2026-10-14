cmake_minimum_required(VERSION 3.13)

# プロジェクト名定義
project(mmd_motion)

# MSVCでUTF-8文字コードを有効化
if(MSVC)
    add_compile_options(/utf-8)
endif()

# Maya devkitの環境変数を自動補完
if(DEFINED DEVKIT_LOCATION)
    set(ENV{DEVKIT_LOCATION} "${DEVKIT_LOCATION}")
endif()
if(NOT DEFINED ENV{DEVKIT_LOCATION})
    if(DEFINED ENV{USERPROFILE})
        file(TO_CMAKE_PATH "$ENV{USERPROFILE}/devkitBase" DEVKIT_PATH)
        set(ENV{DEVKIT_LOCATION} "${DEVKIT_PATH}")
    endif()
endif()

# Maya devkitの設定読み込み
include($ENV{DEVKIT_LOCATION}/cmake/pluginEntry.cmake)

# プロジェクト名定義
set(PROJECT_NAME mmd_motion)

# インクルードディレクトリ追加
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# ソースファイル定義
set(SOURCE_FILES
    src/plugin_main.cpp
    src/mmd_fast_baker_cmd.cpp
    include/mmd_fast_baker_cmd.h
)

# リンクライブラリ定義
set(LIBRARIES
    OpenMaya
    OpenMayaAnim
    Foundation
)

# Mayaプラグイン (.mll) のビルド
build_plugin()
