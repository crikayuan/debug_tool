"""把最新打包产物同步到交付目录（逐文件删除 + 复制，避免 rmtree 回收站 shim 失败）"""
import os
import shutil
import sys

SRC = r"D:\workbuddy\2026-10-10-14-59-54\netassist\backend\dist\debug-assistant"
TARGETS = [
    r"D:\workbuddy\2026-10-10-14-59-54\调试助手",
    r"C:\Users\yuanj\调试助手",
]


def clear_dir(path):
    """删除目录内所有内容（保留目录本身）"""
    if not os.path.isdir(path):
        return
    for root, dirs, files in os.walk(path, topdown=False):
        for f in files:
            try:
                os.remove(os.path.join(root, f))
            except Exception as e:
                print(f"  [warn] remove file failed: {os.path.join(root, f)} -> {e}")
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except Exception as e:
                print(f"  [warn] rmdir failed: {os.path.join(root, d)} -> {e}")


def copy_tree(src, dst):
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        out = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(out, exist_ok=True)
        for f in files:
            s = os.path.join(root, f)
            d = os.path.join(out, f)
            shutil.copy2(s, d)


ok = True
for t in TARGETS:
    print(f"=== {t} ===")
    os.makedirs(t, exist_ok=True)
    clear_dir(t)
    left = os.listdir(t)
    if left:
        print(f"  [warn] 残留: {left}")
    try:
        copy_tree(os.path.join(SRC, "_internal"), os.path.join(t, "_internal"))
        shutil.copy2(os.path.join(SRC, "debug-assistant.exe"), os.path.join(t, "调试助手.exe"))
    except Exception as e:
        ok = False
        print(f"  [error] copy failed: {e}")
        continue
    exe = os.path.join(t, "调试助手.exe")
    print(f"  exe: {os.path.getsize(exe)} bytes, mtime={os.path.getmtime(exe):.0f}")
    print(f"  _internal items: {len(os.listdir(os.path.join(t, '_internal')))}")

sys.exit(0 if ok else 1)
