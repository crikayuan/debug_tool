# -*- mode: python ; coding: utf-8 -*-
# 单文件（onefile）打包配置：产出单个 exe，双击即用，可直接拷贝分发
# 与 onedir 版（net-debug-tools.spec）的唯一区别：EXE 内联 binaries/datas，不再 COLLECT

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 收集相关数据文件
fastapi_datas = collect_data_files('fastapi')
uvicorn_datas = collect_data_files('uvicorn')
pydantic_datas = collect_data_files('pydantic')
webview_datas = collect_data_files('webview')

# 随包数据：前端静态资源(static) + 网络扫描 OUI 厂商库(data/oui.txt)
# onefile 下会解压到 _MEIPASS/data/oui.txt，与 utils/vendor_utils.py 的路径查找一致
app_datas = [('static', 'static'), ('data', 'data')]

# 收集所有隐藏导入
hidden_imports = []
hidden_imports.extend(collect_submodules('fastapi'))
hidden_imports.extend(collect_submodules('uvicorn'))
hidden_imports.extend(collect_submodules('pydantic'))
hidden_imports.extend(collect_submodules('serial'))
hidden_imports.extend(collect_submodules('webview'))
hidden_imports.extend(collect_submodules('paho'))
hidden_imports.extend(['uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
                      'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.websockets',
                      'uvicorn.lifespan', 'uvicorn.lifespan.on',
                      'webview.platforms.edgechromium', 'webview.platforms.winforms'])

# 显式把 WebView2 DLL 收集到解压根目录，兜底 pywebview 的 interop_dll_path 定位
# （onefile 下这些文件会被解压到 _MEIPASS，collect_data_files('webview') 同时保留 lib 原始结构）
import webview as _wv
_webview_lib = os.path.join(os.path.dirname(_wv.__file__), 'lib')

binaries = [
    (os.path.join(_webview_lib, 'Microsoft.Web.WebView2.Core.dll'), '.'),
    (os.path.join(_webview_lib, 'Microsoft.Web.WebView2.WinForms.dll'), '.'),
    (os.path.join(_webview_lib, 'WebBrowserInterop.x64.dll'), '.'),
    (os.path.join(_webview_lib, 'runtimes', 'win-x64', 'native', 'WebView2Loader.dll'), 'win-x64'),
    (os.path.join(_webview_lib, 'runtimes', 'win-x64', 'native', 'WebView2Loader.dll'),
     os.path.join('runtimes', 'win-x64', 'native')),
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=fastapi_datas + uvicorn_datas + pydantic_datas + webview_datas + app_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='debug-assistant-standalone',
    icon='icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
