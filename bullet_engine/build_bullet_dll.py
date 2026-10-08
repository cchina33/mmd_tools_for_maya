# -*- coding: utf-8 -*-
"""
Bullet Physics 2.83.7 MMD エンジン - 自動DLLビルドスクリプト
MSVC (Visual Studio 64bit) を自動検出し、Bullet のコアソースと MMD C-API を
単一の mmd_bullet.dll として高速最適化コンパイルします。
"""

import os
import sys
import glob
import subprocess
import time

print("=== MMD Bullet Physics Engine - Build Script ===")

script_dir = os.path.dirname(os.path.abspath(__file__))
bin_dir = os.path.join(script_dir, "bin")
src_dir = os.path.join(script_dir, "src")
include_dir = os.path.join(script_dir, "include")

os.makedirs(bin_dir, exist_ok=True)

vs_candidates = [
    r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\18\Professional\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\18\Enterprise\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2026\Community\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat",
]

vcvars = None
for cand in vs_candidates:
    if os.path.exists(cand):
        vcvars = cand
        break

if not vcvars:
    print("[ERROR] vcvars64.bat not found.")
    sys.exit(1)

print(f"[INFO] Using vcvars: {vcvars}")

# 1. コンパイル対象の全 C++ ソースファイルを収集
cpp_files = []

# MMD ブリッジ
bridge_src = os.path.join(src_dir, "mmd_bullet_bridge.cpp")
if os.path.exists(bridge_src):
    cpp_files.append(bridge_src)

# LinearMath
cpp_files.extend(glob.glob(os.path.join(src_dir, "LinearMath", "*.cpp")))

# BulletCollision (再帰)
for root, _, files in os.walk(os.path.join(src_dir, "BulletCollision")):
    for f in files:
        if f.endswith(".cpp"):
            cpp_files.append(os.path.join(root, f))

# BulletDynamics (再帰、不要なFeatherstone多体系は除外)
for root, _, files in os.walk(os.path.join(src_dir, "BulletDynamics")):
    if "Featherstone" in root:
        continue
    for f in files:
        if f.endswith(".cpp"):
            cpp_files.append(os.path.join(root, f))

print(f"[INFO] Collected {len(cpp_files)} C++ source files.")

out_dll = os.path.join(bin_dir, "mmd_bullet.dll")

# 既存DLLのロック退避
if os.path.exists(out_dll):
    try:
        os.remove(out_dll)
    except PermissionError:
        bak_name = os.path.join(bin_dir, f"mmd_bullet_old_{int(time.time())}.dll")
        try:
            os.rename(out_dll, bak_name)
            print(f"[INFO] ロック中の既存DLLを一時退避しました: {bak_name}")
        except Exception as e:
            print(f"[WARN] 既存DLLのリネームに失敗しました: {e}")

# コンパイルコマンドの生成
# コマンド長制限 (Windows 8191文字) を回避するため、レスポンスファイル (@sources.rsp) を使用
rsp_path = os.path.join(script_dir, "sources.rsp")
with open(rsp_path, "w", encoding="utf-8") as f:
    for cpp in cpp_files:
        f.write(f'"{cpp}"\n')

inc_flags = f'/I "{src_dir}" /I "{include_dir}"'
opt_flags = "/utf-8 /O2 /LD /std:c++17 /EHsc /W3 /D_CRT_SECURE_NO_WARNINGS"

cmd = f'call "{vcvars}" >nul 2>&1 && cl.exe {opt_flags} {inc_flags} @"sources.rsp" /Fe:"{out_dll}"'

print("[INFO] Compiling and linking mmd_bullet.dll (this may take a minute)...")
res = subprocess.run(cmd, shell=True, cwd=script_dir)

# レスポンスファイルおよび中間 .obj のクリーンアップ
if os.path.exists(rsp_path):
    try: os.remove(rsp_path)
    except Exception: pass

for obj in glob.glob(os.path.join(script_dir, "*.obj")):
    try: os.remove(obj)
    except Exception: pass

for exp in glob.glob(os.path.join(script_dir, "*.exp")):
    try: os.remove(exp)
    except Exception: pass

for lib in glob.glob(os.path.join(script_dir, "*.lib")):
    try: os.remove(lib)
    except Exception: pass

if res.returncode == 0 and os.path.exists(out_dll):
    size_kb = os.path.getsize(out_dll) / 1024
    print("==================================================")
    print(f"[SUCCESS] mmd_bullet.dll successfully created! ({size_kb:.1f} KB)")
    print(f"Path: {out_dll}")
    print("==================================================")
else:
    print("[ERROR] Build failed with return code:", res.returncode)
    sys.exit(res.returncode)
