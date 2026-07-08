import time
import uuid
from collections import defaultdict, deque
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],         
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

T = 51          
R = 15          
orders_catalog = [{"id": i, "item": f"item-{i}", "amount": i * 10} for i in range(1, T + 1)]
idempotency_store = {}     
created_orders = {}        
next_order_id = 1000      

rate_buckets = defaultdict(deque)   

def check_rate_limit(client_id: str):
    now = time.time()
    q = rate_buckets[client_id]
    while q and now - q[0] > 10:
        q.popleft()
    if len(q) >= R:
        retry_after = int(10 - (now - q[0])) + 1
        raise HTTPException(status_code=429, detail="Rate limit exceeded",
                             headers={"Retry-After": str(retry_after)})
    q.append(now)


@app.post("/orders", status_code=201)
async def create_order(request: Request,
                        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
                        x_client_id: Optional[str] = Header(None, alias="X-Client-Id")):
    check_rate_limit(x_client_id or "anonymous")

    if idempotency_key and idempotency_key in idempotency_store:
        return JSONResponse(status_code=201, content=idempotency_store[idempotency_key])

    global next_order_id
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    order = {"id": str(next_order_id), "item": body.get("item", "unknown"), "status": "created"}
    next_order_id += 1

    if idempotency_key:
        idempotency_store[idempotency_key] = order

    return order


@app.get("/orders")
async def list_orders(limit: int = 10, cursor: Optional[str] = None,
                       x_client_id: Optional[str] = Header(None, alias="X-Client-Id")):
    check_rate_limit(x_client_id or "anonymous")

    start = int(cursor) if cursor else 0
    end = start + limit
    items = orders_catalog[start:end]
    next_cursor = str(end) if end < len(orders_catalog) else None

    return {"items": items, "next_cursor": next_cursor, "next": next_cursor, "orders": items}
