#!/usr/bin/env python3
"""
调试助手桌面壳入口
后台线程启动 FastAPI 服务，主线程用 pywebview 弹原生窗口
"""

import base64
import os
import sys
import time
import socket
import threading
from pathlib import Path


def setup_paths():
    """设置路径和环境"""
    if getattr(sys, "frozen", False):
        # 单文件模式：模块解压在 _MEIPASS 临时目录
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            sys.path.insert(0, str(meipass))
        # 目录模式兼容：_internal 目录
        internal_path = Path(sys.executable).parent / "_internal"
        if internal_path.exists():
            sys.path.insert(0, str(internal_path))
        base_path = Path(sys.executable).parent
    else:
        base_path = Path(__file__).parent
        sys.path.insert(0, str(base_path))

    os.chdir(base_path)
    return base_path


def _port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    """检测端口是否已监听"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _can_bind(host: str, port: int) -> bool:
    """检测端口是否可被本机绑定（真空闲）"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 注意：Windows 下不要设置 SO_REUSEADDR，它会允许多个进程抢占同一端口
        sock.bind((host, port))
        sock.close()
        return True
    except OSError:
        return False


def _bind_listen(host: str, port: int, backlog: int = 128):
    """
    绑定并监听端口，成功返回 socket，失败返回 None。
    返回的 socket 会一直持有到服务启动，用于消除"多开时两个实例选中同一端口"的竞态。
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((host, port))
        sock.listen(backlog)
        return sock
    except OSError:
        return None


def _is_self_instance(host: str, port: int) -> bool:
    """判断端口上跑的是不是本程序（用于区分"已开着的调试助手"和"别的程序占用"）"""
    try:
        import json
        import urllib.request

        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=0.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("status") == "healthy"
    except Exception:
        return False


def _scan_ports(host: str, start: int, span: int = 50):
    """
    启动前扫描端口占用情况，返回 (port, sock, report)。
    port/sock 为本次可用的端口与已 bind+listen 的 socket；都为空表示无可用端口。
    """
    busy_self = []
    busy_other = []
    chosen_port = None
    chosen_sock = None

    for port in range(start, start + span):
        if _port_open(host, port):
            (busy_self if _is_self_instance(host, port) else busy_other).append(port)
            continue
        sock = _bind_listen(host, port)
        if sock is not None:
            chosen_port = port
            chosen_sock = sock
            break

    report = (
        f"端口扫描 {start}~{start + span - 1}："
        f"本程序已运行 {len(busy_self)} 个 {busy_self[:10]}，"
        f"其他程序占用 {len(busy_other)} 个 {busy_other[:10]}，"
        f"本次绑定 {chosen_port}"
    )
    return chosen_port, chosen_sock, report


def _get_screen_size():
    """获取屏幕逻辑分辨率（宽, 高），失败返回兜底值"""
    try:
        import ctypes

        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        if w and h:
            return int(w), int(h)
    except Exception:
        pass
    return 1440, 900


def _run_server(app, host: str, port: int, err_log: Path, sock=None):
    """在线程中运行 uvicorn，异常写入日志文件"""
    try:
        import uvicorn

        # windowed（无控制台）exe 下 sys.stdout/stderr 可能为 None，
        # uvicorn 配置日志时会调用 isatty() 导致崩溃，这里兜底重定向
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")

        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            log_config=None,  # 禁用 uvicorn 自带日志配置，避免 isatty 崩溃
        )
        server = uvicorn.Server(config)
        # 传入已 bind+listen 的 socket，避免多开竞态导致的端口冲突
        if sock is not None:
            server.run(sockets=[sock])
        else:
            server.run()
    except Exception:
        import traceback

        try:
            with open(err_log, "a", encoding="utf-8") as f:
                f.write("=== 内嵌服务线程异常 ===\n")
                f.write(traceback.format_exc() + "\n")
        except Exception:
            pass


def _alert(msg: str):
    """弹系统消息框（不依赖 GUI 库）"""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, msg, "调试助手", 0x10)
    except Exception:
        pass


def main():
    base_path = setup_paths()

    from main import app
    from config import settings

    host = "127.0.0.1"
    base_port = settings.PORT

    log_path = Path(sys.executable).parent if getattr(sys, "frozen", False) else base_path
    err_log = log_path / "startup_error.log"

    # 启动前先扫描端口占用情况，跳过已占用的端口，避免冲突
    port, sock, scan_report = _scan_ports(host, base_port)
    print(scan_report)

    if port is None or sock is None:
        _alert(
            f"端口扫描完成，但 {base_port} ~ {base_port + 49} 均不可用。\n\n"
            f"{scan_report}\n\n"
            "请先关闭部分调试助手窗口或占用端口的程序后重试。"
        )
        sys.exit(1)

    instance_no = port - base_port + 1
    url = f"http://{host}:{port}"

    server_thread = threading.Thread(
        target=_run_server, args=(app, host, port, err_log, sock), daemon=True
    )
    server_thread.start()

    # 等待服务就绪（最多 15 秒），服务线程死亡则提前结束
    ready = False
    for _ in range(150):
        if _port_open(host, port):
            ready = True
            break
        if not server_thread.is_alive():
            break
        time.sleep(0.1)

    if not ready:
        # 服务启动失败：写日志 + 消息框告知，绝不弹一个"拒绝连接"的空窗口
        try:
            with open(err_log, "a", encoding="utf-8") as f:
                f.write("=== 内嵌服务启动失败 ===\n")
                f.write(
                    f"端口 {port} 未能监听。可能原因：被其他程序占用，"
                    f"或服务线程异常（详见上方日志）。\n"
                )
        except Exception:
            pass
        _alert(
            f"内嵌服务启动失败（端口 {port} 被占用或异常）。\n\n"
            "请关闭已打开的调试助手窗口后重新运行。\n\n"
            "详情见程序目录下 startup_error.log"
        )
        sys.exit(1)

    print(f"实例 #{instance_no} 服务地址: {url}")

    # 桌面壳
    try:
        import webview

        class Api:
            def choose_dir(self):
                """打开系统文件夹选择对话框，返回选中的目录路径"""
                try:
                    result = webview.windows[0].create_file_dialog(
                        webview.FOLDER_DIALOG
                    )
                    if result and len(result) > 0:
                        return result[0]
                except Exception as e:
                    print(f"选择目录失败: {e}")
                return None

            def choose_file(self):
                """打开系统文件选择对话框，返回文件名和 base64 内容"""
                try:
                    result = webview.windows[0].create_file_dialog(webview.OPEN_DIALOG)
                    if result and len(result) > 0:
                        path = result[0]
                        with open(path, "rb") as f:
                            data = base64.b64encode(f.read()).decode("utf-8")
                        return {
                            "path": path,
                            "name": os.path.basename(path),
                            "data": data,
                        }
                except Exception as e:
                    print(f"选择文件失败: {e}")
                return None

        # 窗口大小 = 全屏四分之一（宽高各取屏幕一半），设下限保证三栏界面不挤
        sw, sh = _get_screen_size()
        width = max(sw // 2, 1000)
        height = max(sh // 2, 640)

        # 多开时窗口标题带实例序号，方便在任务栏区分；同时带版本号便于现场核对
        base_title = f"调试助手 v{settings.VERSION}"
        title = base_title if instance_no <= 1 else f"{base_title} #{instance_no}"

        webview.create_window(
            title,
            url,
            width=width,
            height=height,
            min_size=(900, 560),
            js_api=Api(),
        )

        with open(log_path / "startup.log", "a", encoding="utf-8") as f:
            f.write(f"{scan_report}\n")
            f.write(f"实例 #{instance_no} 端口 {port}，webview 窗口已创建，进入 GUI 循环\n")

        webview.start()
    except Exception:
        import traceback

        try:
            with open(err_log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        print(f"桌面壳启动失败，请在浏览器中打开 {url}")
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
