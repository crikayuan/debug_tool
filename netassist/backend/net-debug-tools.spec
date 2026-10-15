# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 收集相关数据文件
fastapi_datas = collect_data_files('fastapi')
uvicorn_datas = collect_data_files('uvicorn')
pydantic_datas = collect_data_files('pydantic')
webview_datas = collect_data_files('webview')

# 随包数据：前端静态资源(static) + 网络扫描 OUI 厂商库(data/oui.txt)
# data 目录与 static 同样按 (源, 目标相对路径) 收集，打包后位于 _internal/data（onedir）
# 或 _MEIPASS/data（onefile），与 utils/vendor_utils.py 的路径查找一致
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

# 显式把 WebView2 DLL 收集到 exe 根目录（_internal 根），兜底 pywebview 的 interop_dll_path 定位
import webview as _wv
_webview_lib = os.path.join(os.path.dirname(_wv.__file__), 'lib')

binaries = [
    (os.path.join(_webview_lib, 'Microsoft.Web.WebView2.Core.dll'), '.'),
    (os.path.join(_webview_lib, 'Microsoft.Web.WebView2.WinForms.dll'), '.'),
    (os.path.join(_webview_lib, 'WebBrowserInterop.x64.dll'), '.'),
    (os.path.join(_webview_lib, 'runtimes', 'win-x64', 'native', 'WebView2Loader.dll'), 'win-x64'),
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
    [],
    exclude_binaries=True,
    name='debug-assistant',
    icon='icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='debug-assistant',
)
