from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager
from typing import Optional

app = FastAPI(title="Preisvergleich")
templates = Jinja2Templates(directory="templates")

DB_PATH = os.environ.get("DB_PATH", "data/prices.db")


# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT NOT NULL,
                unit    TEXT NOT NULL DEFAULT 'kg',  -- kg, L, Stück, g, ml
                notes   TEXT
            );
            CREATE TABLE IF NOT EXISTS stores (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS prices (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                store_id   INTEGER NOT NULL REFERENCES stores(id)   ON DELETE CASCADE,
                price      REAL NOT NULL,
                quantity   REAL NOT NULL DEFAULT 1.0,  -- how much per package
                date       TEXT NOT NULL,
                notes      TEXT
            );

            -- Seed default stores if empty
            INSERT OR IGNORE INTO stores (name)
            VALUES ('Rewe'),('Edeka'),('Lidl'),('Aldi'),('Penny'),('Kaufland'),('Netto');
        """)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


init_db()


# ── Helpers ───────────────────────────────────────────────────────────────────

def unit_price(price: float, quantity: float) -> float:
    """Price per unit (per kg/L/Stück)."""
    if quantity <= 0:
        return price
    return round(price / quantity, 4)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    with get_db() as db:
        stores   = db.execute("SELECT * FROM stores ORDER BY name").fetchall()
        products = db.execute("SELECT * FROM products ORDER BY name").fetchall()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "stores":  [dict(s) for s in stores],
        "products": [dict(p) for p in products],
    })


# ── Products API ──────────────────────────────────────────────────────────────

@app.get("/api/products")
async def list_products():
    with get_db() as db:
        rows = db.execute("SELECT * FROM products ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/products")
async def create_product(name: str = Form(...), unit: str = Form("kg"), notes: str = Form("")):
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO products (name, unit, notes) VALUES (?,?,?)",
            (name.strip(), unit, notes.strip())
        )
        product_id = cur.lastrowid
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    return dict(row)


@app.delete("/api/products/{product_id}")
async def delete_product(product_id: int):
    with get_db() as db:
        db.execute("DELETE FROM products WHERE id=?", (product_id,))
    return {"ok": True}


# ── Stores API ────────────────────────────────────────────────────────────────

@app.get("/api/stores")
async def list_stores():
    with get_db() as db:
        rows = db.execute("SELECT * FROM stores ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/stores")
async def create_store(name: str = Form(...)):
    with get_db() as db:
        cur = db.execute("INSERT OR IGNORE INTO stores (name) VALUES (?)", (name.strip(),))
        store_id = cur.lastrowid or db.execute(
            "SELECT id FROM stores WHERE name=?", (name.strip(),)
        ).fetchone()["id"]
        row = db.execute("SELECT * FROM stores WHERE id=?", (store_id,)).fetchone()
    return dict(row)


@app.delete("/api/stores/{store_id}")
async def delete_store(store_id: int):
    with get_db() as db:
        db.execute("DELETE FROM stores WHERE id=?", (store_id,))
    return {"ok": True}


# ── Prices API ────────────────────────────────────────────────────────────────

@app.post("/api/prices")
async def add_price(
    product_id: int  = Form(...),
    store_id:   int  = Form(...),
    price:      float = Form(...),
    quantity:   float = Form(1.0),
    date:       str  = Form(default=""),
    notes:      str  = Form(""),
):
    if not date:
        date = datetime.today().strftime("%Y-%m-%d")
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO prices (product_id, store_id, price, quantity, date, notes) VALUES (?,?,?,?,?,?)",
            (product_id, store_id, price, quantity, date, notes.strip())
        )
    return {"ok": True, "id": cur.lastrowid}


@app.delete("/api/prices/{price_id}")
async def delete_price(price_id: int):
    with get_db() as db:
        db.execute("DELETE FROM prices WHERE id=?", (price_id,))
    return {"ok": True}


# ── Comparison view ───────────────────────────────────────────────────────────

@app.get("/api/compare")
async def compare(product_ids: str = ""):
    """
    Returns latest price per (product, store), with unit price.
    product_ids: comma-separated list, or empty for all products.
    """
    with get_db() as db:
        stores   = db.execute("SELECT * FROM stores ORDER BY name").fetchall()
        products_q = "SELECT * FROM products ORDER BY name"
        if product_ids:
            ids = ",".join(str(int(x)) for x in product_ids.split(",") if x.strip())
            products_q = f"SELECT * FROM products WHERE id IN ({ids}) ORDER BY name"
        products = db.execute(products_q).fetchall()

        # Latest price for each (product, store) pair
        rows = db.execute("""
            SELECT p.product_id, p.store_id, p.price, p.quantity, p.date, p.notes,
                   pr.name AS product_name, pr.unit,
                   s.name  AS store_name
            FROM prices p
            JOIN products pr ON pr.id = p.product_id
            JOIN stores   s  ON s.id  = p.store_id
            WHERE p.date = (
                SELECT MAX(p2.date)
                FROM prices p2
                WHERE p2.product_id = p.product_id
                  AND p2.store_id   = p.store_id
            )
            ORDER BY pr.name, s.name
        """).fetchall()

    # Build grid: {product_id: {store_id: {price, unit_price, ...}}}
    grid = {}
    for r in rows:
        pid, sid = r["product_id"], r["store_id"]
        if pid not in grid:
            grid[pid] = {}
        up = unit_price(r["price"], r["quantity"])
        grid[pid][sid] = {
            "price":      r["price"],
            "quantity":   r["quantity"],
            "unit_price": up,
            "date":       r["date"],
            "notes":      r["notes"],
        }

    # Find cheapest store per product (by unit price)
    cheapest = {}
    for pid, store_map in grid.items():
        if store_map:
            cheapest[pid] = min(store_map, key=lambda sid: store_map[sid]["unit_price"])

    return {
        "stores":   [dict(s) for s in stores],
        "products": [dict(p) for p in products],
        "grid":     {str(k): {str(sk): sv for sk, sv in v.items()} for k, v in grid.items()},
        "cheapest": {str(k): v for k, v in cheapest.items()},
    }


@app.get("/api/history/{product_id}")
async def price_history(product_id: int):
    """All price entries for a product, grouped by store."""
    with get_db() as db:
        product = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product:
            raise HTTPException(404, "Product not found")
        rows = db.execute("""
            SELECT p.*, s.name AS store_name
            FROM prices p
            JOIN stores s ON s.id = p.store_id
            WHERE p.product_id = ?
            ORDER BY p.date DESC, s.name
        """, (product_id,)).fetchall()

    result = {}
    for r in rows:
        sn = r["store_name"]
        if sn not in result:
            result[sn] = []
        result[sn].append({
            "date":       r["date"],
            "price":      r["price"],
            "quantity":   r["quantity"],
            "unit_price": unit_price(r["price"], r["quantity"]),
            "notes":      r["notes"],
            "id":         r["id"],
        })
    return {"product": dict(product), "history": result}
