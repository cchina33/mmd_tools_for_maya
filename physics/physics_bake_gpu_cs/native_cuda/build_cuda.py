# -*- coding: utf-8 -*-
"""
mmd_physics_cuda.dll ビルド自動化スクリプト
MSVC (cl.exe) + CUDA Driver API (cuda.lib) + NVRTC (nvrtc.lib) によるネイティブ DLL ビルド
"""
import os
import subprocess
import shutil

def build():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    bin_dir = os.path.join(os.path.dirname(current_dir), "bin", "Release", "net8.0-windows")
    os.makedirs(bin_dir, exist_ok=True)

    # vswhere で Visual Studio パスを検出
    vswhere = r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    vs_path = r"C:\Program Files\Microsoft Visual Studio\18\Community"
    if os.path.exists(vswhere):
        try:
            out = subprocess.check_output([vswhere, "-latest", "-property", "installationPath"], text=True).strip()
            if out and os.path.exists(out):
                vs_path = out
        except Exception:
            pass

    vcvars = os.path.join(vs_path, r"VC\Auxiliary\Build\vcvars64.bat")
    cuda_path = os.environ.get("CUDA_PATH", r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9")
    output_dll = os.path.join(bin_dir, "mmd_physics_cuda.dll")

    src_cpp = os.path.join(current_dir, "cuda_physics_api.cpp")

    # MSVC cl.exe によるコンパイルとリンク
    cmd = (
        f'call "{vcvars}" && '
        f'cl /LD /O2 /MD /utf-8 /EHsc '
        f'/I"{current_dir}" /I"{cuda_path}\\include" '
        f'"{src_cpp}" '
        f'/link /LIBPATH:"{cuda_path}\\lib\\x64" cuda.lib cudart.lib nvrtc.lib '
        f'/OUT:"{output_dll}"'
    )

    print("Building mmd_physics_cuda.dll with cl.exe + cuda.lib + nvrtc.lib...")
    res = subprocess.run(cmd, shell=True, capture_output=True)
    stdout = res.stdout.decode("cp932", errors="replace")
    stderr = res.stderr.decode("cp932", errors="replace")

    if stdout.strip():
        print("STDOUT:")
        print(stdout)
    if res.returncode != 0:
        print("STDERR:")
        print(stderr)
        return False

    if os.path.exists(output_dll):
        size_kb = os.path.getsize(output_dll) / 1024
        print(f"SUCCESS: Built {output_dll} ({size_kb:.1f} KB)")

        # CUDA 実行時 DLL を bin フォルダへコピー
        cuda_bin = os.path.join(cuda_path, "bin")
        for dll_name in ["cudart64_12.dll", "nvrtc64_120_0.dll", "nvrtc-builtins64_120.dll"]:
            src_dll = os.path.join(cuda_bin, dll_name)
            dst_dll = os.path.join(bin_dir, dll_name)
            if os.path.exists(src_dll) and not os.path.exists(dst_dll):
                try:
                    shutil.copy2(src_dll, dst_dll)
                    print(f"Copied {dll_name} to bin directory.")
                except Exception as e:
                    print(f"Warning: Failed to copy {dll_name}: {e}")

        return True
    else:
        print(f"Error: Output file {output_dll} not created.")
        return False

if __name__ == "__main__":
    build()
