@echo off
chcp 65001 >nul
title 智能健康测评系统 - 一键启动
echo ============================================
echo   智能健康测评系统 (NRS2002 营养风险筛查)
echo ============================================
echo.

cd /d "%~dp0"

REM --- 检查并自动准备 Python venv（首次或缺失时重建） ---
if not exist "backend\venv\Scripts\python.exe" (
    echo [准备] 首次启动，初始化 Python 虚拟环境并安装依赖（需 1-3 分钟）...
    where python >nul 2>nul || (
        echo 错误：未检测到 Python，请先安装 Python 3.10+ 并重新运行
        pause & exit /b 1
    )
    cd /d "%~dp0backend"
    python -m venv venv
    venv\Scripts\python.exe -m pip install --upgrade pip -q
    venv\Scripts\python.exe -m pip install -r requirements.txt -q
    cd /d "%~dp0"
    echo [准备] Python 虚拟环境就绪
)

REM --- 前端依赖检查 ---
if not exist "frontend\node_modules" (
    echo [准备] 首次启动，安装前端 npm 依赖（需 1-3 分钟）...
    cd /d "%~dp0frontend"
    call npm install
    cd /d "%~dp0"
    echo [准备] 前端依赖就绪
)

echo.
echo [1/2] 启动后端 FastAPI (http://127.0.0.1:8000) ...
start "后端-智能健康测评" cmd /k "cd /d %~dp0backend && venv\Scripts\python -m uvicorn app.main:app --reload --port 8000"

echo [2/2] 启动前端 Vue3 (http://127.0.0.1:5173) ...
start "前端-智能健康测评" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo 前端地址: http://127.0.0.1:5173
echo 后端文档: http://127.0.0.1:8000/docs
echo.
pause