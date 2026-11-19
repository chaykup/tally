from fastapi import FastAPI

from app.auth import router as auth_router
from app.users import router as users_router

def create_app() -> FastAPI:
    app = FastAPI(title="Tally Auth Service", version="1.0.0")

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")

    # Preserve existing callers while the other services adopt the versioned API.
    app.include_router(auth_router, include_in_schema=False)
    app.include_router(users_router, include_in_schema=False)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "auth"}

    return app


app = create_app()
