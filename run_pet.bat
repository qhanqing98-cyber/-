@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title DeskPet 一键启动

rem ═══ 1. 定位 Python（优先用项目自带虚拟环境）═══
set "PYCMD="
if exist ".venv\Scripts\python.exe" set "PYCMD=.venv\Scripts\python.exe"
if not defined PYCMD (
    where py >nul 2>nul && set "PYCMD=py -3"
)
if not defined PYCMD (
    where python >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
    echo [错误] 未找到 Python。请先安装 Python 3.9+ 并勾选 "Add Python to PATH"。
    pause
    exit /b 1
)

rem ═══ 2. 首次运行：自动创建虚拟环境并安装依赖 ═══
if not exist ".venv\Scripts\python.exe" (
    echo [初始化] 正在创建虚拟环境 .venv ...
    %PYCMD% -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败。
        pause
        exit /b 1
    )
    echo [初始化] 正在安装依赖，首次约 1-2 分钟 ...
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
    if errorlevel 1 (
        echo [提示] 默认源安装失败，改用清华镜像重试 ...
        ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
        if errorlevel 1 (
            echo [错误] 依赖安装失败，请检查网络后重新运行本脚本。
            pause
            exit /b 1
        )
    )
    echo [初始化] 完成。
)

rem ═══ 3. 启动桌宠（pythonw = 无黑色控制台窗口）═══
echo [启动] DeskPet 已运行，右键桌宠可打开菜单。
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%~dp0main.py"
) else (
    start "" %PYCMD% "%~dp0main.py"
)
exit /b 0
