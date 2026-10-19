# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("ui/dist", "ui/dist"),
    ("app.ico", "."),
]
datas += collect_data_files("webview")

hiddenimports = collect_submodules("webview") + [
    "clr",
    "pythonnet",
    "bottle",
    "Crypto",
    "Crypto.Cipher",
    "Crypto.Cipher.AES",
]

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="智慧树答题",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="app.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="智慧树答题",
)
