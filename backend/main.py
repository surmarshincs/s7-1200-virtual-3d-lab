# -*- coding: utf-8 -*-
"""FastAPI 入口。

启动（在 PLC_1 目录下）：
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
浏览器打开 http://localhost:8000/ （FastAPI 静态托管 frontend/，一条命令起全部）。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import rest, ws
from .app_state import state


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时装载默认项目（项目1）并启动扫描循环；其余项目首次切换时懒加载
    state.load(state.project_id)
    await state.engine.start()
    yield
    await state.engine.stop()


app = FastAPI(title="S7-1200 虚拟 3D 实训平台", lifespan=lifespan)
app.include_router(rest.router)
app.include_router(ws.router)


@app.middleware("http")
async def no_cache_index(request, call_next):
    # 单文件前端经常迭代：强制浏览器每次 revalidate，避免打到旧的启发式缓存
    resp = await call_next(request)
    if request.url.path in ("/", "/index.html"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp

# 静态托管前端单文件（frontend/index.html），根路径直接打开页面
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    # 便捷入口：在 PLC_1 目录下执行  python -m backend.main
    # （注意必须是 -m 模块方式；直接 python backend/main.py 会因相对导入报错）
    # 脚本直启时自动打开浏览器；uvicorn CLI 方式启动则不打扰
    import threading
    import webbrowser

    import uvicorn

    threading.Timer(1.2, lambda: webbrowser.open("http://localhost:8000/")).start()
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000)
