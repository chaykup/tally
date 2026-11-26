from fastapi import FastAPI

from app.inventory_reports import router as inventory_router
from app.order_reports import router as order_router
from app.sales_reports import router as sales_router

app = FastAPI(
    title="Tally Analytics Service",
    description="Read-only reports over the analytics views. Admin and sales users only.",
)

app.include_router(sales_router)
app.include_router(order_router)
app.include_router(inventory_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "analytics"}
