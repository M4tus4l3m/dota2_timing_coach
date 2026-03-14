# -*- mode: python ; coding: utf-8 -*-
import sys

block_cipher = None

hidden = [
    "pyttsx3",
    "pyttsx3.engine",
    "pyttsx3.driver",
    "pyttsx3.voice",
    "pyttsx3.drivers",
    "pyttsx3.drivers.espeak",
    "pyttsx3.drivers._espeak",
    "pyttsx3.drivers.sapi5",
    "pyttsx3.drivers.dummy",
    "pyttsx3.drivers.nsss",
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
    datas=[("assets", "assets")],
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

import os

icon_file = os.path.join("assets", "dota.ico")
if not os.path.exists(icon_file):
    icon_file = None

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
    icon=icon_file,
)
