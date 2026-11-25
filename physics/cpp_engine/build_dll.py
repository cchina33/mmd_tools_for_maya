# -*- coding: utf-8 -*-
import os
import sys
import subprocess

print("=== MMD XPBD Physics Engine - Build Script ===")

script_dir = os.path.dirname(os.path.abspath(__file__))
bin_dir = os.path.join(script_dir, "bin")
os.makedirs(bin_dir, exist_ok=True)

vs_candidates = [
    # Visual Studio 2026 (バージョン 18) を最優先
    r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\18\Professional\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\18\Enterprise\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2026\Community\VC\Auxiliary\Build\vcvars64.bat",
    # フォールバック (Visual Studio 2022)
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

# vcvars64.bat 経由でコンパイルコマンドを実行
include_dir = os.path.join(script_dir, "include")
src1 = os.path.join(script_dir, "src", "xpbd_engine.cpp")
src2 = os.path.join(script_dir, "src", "xpbd_c_api.cpp")
out_dll = os.path.join(bin_dir, "mmd_xpbd.dll")

# 既存DLLがMaya等でロックされている場合のリネーム退避
if os.path.exists(out_dll):
    try:
        os.remove(out_dll)
    except PermissionError:
        import time
        bak_name = os.path.join(bin_dir, f"mmd_xpbd_old_{int(time.time())}.dll")
        try:
            os.rename(out_dll, bak_name)
            print(f"[INFO] ロック中の既存DLLを一時退避しました: {bak_name}")
        except Exception as e:
            print(f"[WARN] 既存DLLのリネームに失敗しました: {e}")

cmd = f'call "{vcvars}" >nul 2>&1 && cl.exe /utf-8 /O2 /LD /std:c++17 /EHsc /W3 /I "{include_dir}" "{src1}" "{src2}" /Fe:"{out_dll}"'

print("[INFO] Compiling and linking mmd_xpbd.dll...")
res = subprocess.run(cmd, shell=True, cwd=script_dir)

if res.returncode == 0:
    print("===================================================")
    print(f"[SUCCESS] Built: {out_dll}")
    print("===================================================")
    # 中間ファイルのクリーンアップ
    for fname in os.listdir(script_dir):
        if fname.endswith(".obj"):
            try: os.remove(os.path.join(script_dir, fname))
            except Exception: pass
    for fname in os.listdir(bin_dir):
        if fname.endswith(".exp") or fname.endswith(".lib"):
            try: os.remove(os.path.join(bin_dir, fname))
            except Exception: pass
    sys.exit(0)
else:
    print(f"[ERROR] Build failed with return code {res.returncode}")
    sys.exit(res.returncode)
