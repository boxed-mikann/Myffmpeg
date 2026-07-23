# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets'), ('tools', 'tools'), ('LICENSE_FFmpeg.txt', '.'), ('LICENSE', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[#変化なかったのでコメントアウト
    #     # --- 超巨大で使っていないQtモジュール（これだけで100MB以上減ります）---
    #     'PySide6.QtWebEngineCore',
    #     'PySide6.QtWebEngineWidgets',
    #     'PySide6.QtWebEngineQuick',
    #     'PySide6.QtQml',
    #     'PySide6.QtQuick',
    #     'PySide6.QtQuick3D',
    #     'PySide6.QtQuickWidgets',
    #     'PySide6.Qt3DCore',
    #     'PySide6.Qt3DRender',
    #     'PySide6.Qt3DInput',
    #     'PySide6.Qt3DLogic',
    #     'PySide6.Qt3DAnimation',
    #     'PySide6.Qt3DExtras',
        
    #     # --- 使っていないUI/データベース/特殊モジュール ---
    #     'PySide6.QtSql',
    #     'PySide6.QtTest',
    #     'PySide6.QtSensors',
    #     'PySide6.QtPositioning',
    #     'PySide6.QtPdf',
    #     'PySide6.QtPdfWidgets',
    #     'PySide6.QtCharts',
    #     'PySide6.QtSpatialAudio',
    #     'PySide6.QtScxml',
    #     'PySide6.QtStateMachine',
    #     'PySide6.QtDesigner',
    #     'PySide6.QtHelp',
    #     'PySide6.QtNfc',
    #     'PySide6.QtBluetooth',
        
    #     # --- Python標準の不要ライブラリ ---
    #     'tkinter',
    #     'unittest',
    #     'pydoc',
    #     'doctest',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Myffmpeg',
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
    icon=['assets\\app_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Myffmpeg',
)
