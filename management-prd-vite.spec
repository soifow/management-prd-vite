# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

构建命令::

    uv run pyinstaller management-prd-vite.spec --noconfirm

产物：``dist/management-prd-vite.exe``
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# 前端产物作为数据文件打包
frontend_dist = str(Path("frontend") / "dist")

datas = [(frontend_dist, "frontend/dist")]

# pywebview 子模块自动收集
hiddenimports = []
hiddenimports += collect_submodules("webview")


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="management-prd-vite",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
