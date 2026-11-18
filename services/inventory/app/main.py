from fastapi import FastAPI

from app.products import router as products_router

app = FastAPI(title="Tally Inventory Service")

app.include_router(products_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "inventory"}
