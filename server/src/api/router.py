from fastapi import APIRouter
from src.api.endpoints.agent import router as agent_router
from src.api.endpoints.auth_github import router as auth_github_router
from src.api.endpoints.health import router as health_router
from src.api.users import router as users_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(users_router)
router.include_router(auth_github_router)
router.include_router(agent_router)
