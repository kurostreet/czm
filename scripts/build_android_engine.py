#!/usr/bin/env python3
"""Build the pinned SDL and Xash3D sources for our single Android application."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from create_resource_pack import from_directories
from apply_engine_patches import apply_engine_patches

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "3rdparty/xash3d-fwgs"
SDL = ROOT / "3rdparty/SDL"
ABIS = ("arm64-v8a", "armeabi-v7a", "x86")
REQUIRED = ("libSDL2.so", "libxash.so", "libfilesystem_stdio.so",
            "libref_gles1.so", "libref_gl4es.so", "libref_gles3compat.so")

def run(command, env=None):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ENGINE, env=env, check=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ndk", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 2, 4))
    args = parser.parse_args()
    output = args.output.resolve()
    ndk = args.ndk.resolve()
    assert (ndk / "build/cmake/android.toolchain.cmake").is_file(), "Install the configured Android NDK"
    apply_engine_patches()
    for abi in ABIS:
        work = output / "work" / abi
        sdl_out = work / "sdl"
        engine_out = work / "engine"
        run(["cmake", "-S", SDL, "-B", sdl_out, "-G", "Ninja",
             "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_TOOLCHAIN_FILE=" + str(ndk / "build/cmake/android.toolchain.cmake"),
             "-DANDROID_ABI=" + abi, "-DANDROID_PLATFORM=android-21",
             "-DSDL_RENDER=OFF", "-DSDL_POWER=OFF", "-DSDL_VULKAN=OFF", "-DSDL_DISKAUDIO=OFF",
             "-DSDL_DUMMYAUDIO=OFF", "-DSDL_DUMMYVIDEO=OFF", "-DSDL_OFFSCREEN=OFF", "-DSDL_STATIC=OFF"])
        run(["cmake", "--build", sdl_out, "--parallel", args.jobs])
        env = os.environ.copy()
        env["ANDROID_NDK"] = str(ndk)
        env["WAFLOCK"] = ".lock-czm-" + abi
        env["BUILD_CMAKE_LIBRARY_OUTPUT_DIRECTORY"] = str(sdl_out)
        run([sys.executable, ENGINE / "waf", "configure", "-t", ENGINE, "-o", engine_out,
             "-T", "release", "--android=" + abi + ",,21", "-s", SDL,
             "--skip-sdl2-sanity-check", "--enable-bundled-deps"], env)
        run([sys.executable, ENGINE / "waf", "build", "-j", args.jobs], env)
        destination = output / "jniLibs" / abi
        destination.mkdir(parents=True, exist_ok=True)
        for name in REQUIRED:
            matches = list((sdl_out if name == "libSDL2.so" else engine_out).rglob(name))
            assert len(matches) == 1, (abi, name, matches)
            shutil.copy2(matches[0], destination / name)
        print("Engine libraries ready:", abi, flush=True)
    # The engine fallback UI must use the same artwork as the client. In
    # particular, its brightness sample must not contain a legacy game screenshot.
    shell = ROOT / "3rdparty/cs16client-extras/gfx/shell"
    from_directories(output.parent / "bundle-assets/bundled/engine-resources.zip",
                     [ENGINE / "3rdparty/extras/xash-extras"],
                     overrides={"gfx/shell/" + name: shell / name
                                for name in ("btns_main.bmp", "head_multi.tga", "gamma.tga")})

if __name__ == "__main__":
    main()
