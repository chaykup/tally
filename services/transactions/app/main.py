from fastapi import FastAPI

from app.customers import router as customers_router
from app.orders import router as orders_router
app = FastAPI(title="Tally Transactions Service")

app.include_router(customers_router)
app.include_router(orders_router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "transactions"}
