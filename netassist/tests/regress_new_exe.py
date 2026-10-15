# -*- coding: utf-8 -*-
"""在「本次新打包的 exe」上跑既有的 TCP 双实例联调（tests/e2e_test.py 的逻辑），
以验证新增 MQTT 后新构建的 TCP 既有功能零回归。
（e2e_test.py 原脚本硬编码了历史 exe 路径，这里仅替换 EXE 指向新 dist。）
"""
import os
import sys
import asyncio

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import e2e_test  # noqa: E402

NEW_EXE = os.path.normpath(os.path.join(
    HERE, "..", "backend", "dist", "debug-assistant", "debug-assistant.exe"))

# 让 kill_all 也能按新 exe 名清理
_orig_kill = e2e_test.kill_all


def kill_all_new():
    import psutil
    for p in psutil.process_iter(['pid', 'exe']):
        try:
            if (p.info.get('exe') or '').endswith('debug-assistant.exe'):
                p.kill()
        except Exception:
            pass


e2e_test.EXE = NEW_EXE
e2e_test.CWD = os.path.dirname(NEW_EXE)
e2e_test.kill_all = kill_all_new

print("回归目标 exe:", NEW_EXE)
asyncio.run(e2e_test.main())
