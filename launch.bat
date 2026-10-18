@echo off
title S7-1200 虚拟 3D 实训平台
cd /d %~dp0

rem -- 选择 Python：优先 conda torch 环境，找不到退回系统 PATH --
set "PY=C:\Users\wubingying\.conda\envs\torch\python.exe"
if not exist "%PY%" set "PY=python"

rem -- 依赖自检：缺 fastapi 时自动安装 --
"%PY%" -c "import fastapi, uvicorn, pydantic" 2>nul
if errorlevel 1 (
    echo 首次运行，正在安装后端依赖，请稍候...
    "%PY%" -m pip install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo 依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)

echo ==================================================
echo   S7-1200 虚拟 3D 实训平台
echo   地址: http://localhost:8000/   启动后自动打开浏览器
echo   学生机访问: http://本机IP:8000/?role=student
echo   关闭本窗口即停止服务
echo ==================================================
"%PY%" -m backend.main
pause
