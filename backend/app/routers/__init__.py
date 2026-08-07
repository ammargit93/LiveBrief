from fastapi import APIRouter
from backend.app.routers.workspaces import router as workspaces_router
from backend.app.routers.documents import router as documents_router
from backend.app.routers.project_summary import router as summary_router
from backend.app.routers.conflicts import router as conflicts_router
from backend.app.routers.reviews import router as reviews_router
from backend.app.routers.timeline import router as timeline_router
from backend.app.routers.jobs import router as jobs_router

api_router = APIRouter()
api_router.include_router(workspaces_router)
api_router.include_router(documents_router)
api_router.include_router(summary_router)
api_router.include_router(conflicts_router)
api_router.include_router(reviews_router)
api_router.include_router(timeline_router)
api_router.include_router(jobs_router)
