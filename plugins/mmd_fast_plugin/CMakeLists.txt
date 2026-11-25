cmake_minimum_required(VERSION 3.13...4.4)

# プロジェクト名定義: MMD高速インポート＆モーション統合プラグイン
project(mmd_fast)

# C++17規格の指定
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# MSVCでUTF-8文字コードおよび最適化を有効化
if(MSVC)
    add_compile_options(/utf-8 /MP)
endif()

# Maya devkitの環境変数を自動設定
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
set(PROJECT_NAME mmd_fast)

# インクルードディレクトリ追加
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# ソースファイル定義
set(SOURCE_FILES
    src/plugin_main.cpp
    src/mmd_fast_baker_cmd.cpp
    src/pmx_binary_parser.cpp
    src/mmd_fast_pmx_cmd.cpp
    src/vmd_binary_parser.cpp
    src/mmd_fast_vmd_cmd.cpp
    include/mmd_fast_baker_cmd.h
    include/pmx_binary_parser.h
    include/mmd_fast_pmx_cmd.h
    include/vmd_binary_parser.h
    include/mmd_fast_vmd_cmd.h
)

# リンクライブラリ定義
set(LIBRARIES
    OpenMaya
    OpenMayaAnim
    Foundation
)

# Mayaプラグイン (.mll) のビルド
build_plugin()
