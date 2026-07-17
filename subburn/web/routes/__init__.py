from fastapi import APIRouter

from subburn.web.routes.jobs import router as jobs_router
from subburn.web.routes.logs import router as logs_router
from subburn.web.routes.models import router as models_router
from subburn.web.routes.settings import router as settings_router

api_router = APIRouter()
api_router.include_router(jobs_router)
api_router.include_router(models_router)
api_router.include_router(settings_router)
api_router.include_router(logs_router)
