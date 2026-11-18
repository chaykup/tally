from fastapi import FastAPI

from app.reports import router as reports_router

app = FastAPI(title="Tally Analytics Service")

app.include_router(reports_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "analytics"}
