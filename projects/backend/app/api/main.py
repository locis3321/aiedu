"""FastAPI 应用入口：`uvicorn app.api.main:app --reload`。"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.accounts.router import router as accounts_router
from app.admin_api.router import router as admin_router
from app.api import health, jobs
from app.core.errors import register_error_handlers
from app.learning.router import router as learning_router
from app.points.router import router as points_router
from app.profile.router import router as profile_router
from app.questionbank.router import router as questionbank_router
from app.reports.router import router as reports_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Edu", version="0.1.0")
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(accounts_router)
    app.include_router(learning_router)
    app.include_router(points_router)
    app.include_router(profile_router)
    app.include_router(questionbank_router)
    app.include_router(reports_router)
    app.include_router(admin_router)
    # Web 运营后台前端（projects/admin，同源服务免 CORS）
    admin_dir = Path(__file__).resolve().parents[3] / "admin"
    if admin_dir.exists():
        app.mount("/admin", StaticFiles(directory=str(admin_dir), html=True), name="admin")
    return app


app = create_app()
