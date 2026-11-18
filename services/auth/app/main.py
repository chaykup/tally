from fastapi import FastAPI

from app.auth import router as auth_router
from app.users import router as users_router

app = FastAPI(title="Tally Auth Service")

app.include_router(auth_router)
app.include_router(users_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "auth"}
