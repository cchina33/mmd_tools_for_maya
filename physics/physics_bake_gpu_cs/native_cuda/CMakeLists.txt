cmake_minimum_required(VERSION 3.20)
project(mmd_physics_cuda LANGUAGES CXX CUDA)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_STANDARD_REQUIRED ON)

# RTX 4060 (sm_89) および主要アーキテクチャの指定
set(CMAKE_CUDA_ARCHITECTURES "75;80;86;89")

add_library(mmd_physics_cuda SHARED
    cuda_physics_api.h
    cuda_physics_api.cpp
    cuda_physics_kernel.cu
)

target_include_directories(mmd_physics_cuda PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CUDA_TOOLKIT_INCLUDE_DIRECTORIES}
)

set_target_properties(mmd_physics_cuda PROPERTIES
    CUDA_SEPARABLE_COMPILATION ON
    OUTPUT_NAME "mmd_physics_cuda"
)

