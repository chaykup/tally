from fastapi import FastAPI

from auth import router as auth_router
from users import router as users_router


app = FastAPI(title="Tally API")


app.include_router(auth_router)
app.include_router(users_router)


@app.get("/health")
def health():
    return {"status": "ok"}
