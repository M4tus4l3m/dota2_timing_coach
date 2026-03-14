# -*- mode: python ; coding: utf-8 -*-
import sys

block_cipher = None

hidden = [
    "pyttsx3.drivers",
    "pyttsx3.drivers.espeak",
    "pyttsx3.drivers._espeak",
    "pyttsx3.drivers.sapi5",
    "pyttsx3.drivers.dummy",
]

if sys.platform == "win32":
    hidden += [
        "comtypes",
        "comtypes.client",
        "comtypes.gen",
        "pythoncom",
        "win32com",
        "win32api",
    ]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="dota2_timer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=(sys.platform != "win32"),
)
