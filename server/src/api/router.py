from fastapi import APIRouter
from src.api.endpoints.health import router as health_router
from src.api.users import router as users_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(users_router)
