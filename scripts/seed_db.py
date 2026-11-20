"""Crea data/sales.db con datos sintéticos de ventas.

Tablas:
  - productos(id, nombre, categoria, precio)
  - clientes(id, nombre, region, segmento)
  - ventas(id, producto_id, cliente_id, fecha, cantidad, monto)

Uso:
    python scripts/seed_db.py
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "sales.db"

# Coherente con data/kb/catalogo-productos.md
PRODUCTOS = [
    ("Auriculares BT Nova", "Electrónica", 45.00),
    ("Teclado Mecánico K2", "Electrónica", 78.00),
    ("Mouse Inalámbrico M1", "Electrónica", 25.00),
    ("Webcam HD Lite", "Electrónica", 39.00),
    ("Lámpara LED Aura", "Hogar", 32.00),
    ("Hervidor Eléctrico H3", "Hogar", 28.00),
    ("Aspiradora Compacta V", "Hogar", 120.00),
    ("Botella Térmica Polar", "Deportes", 18.00),
    ("Banda Elástica Pro", "Deportes", 12.00),
    ("Mochila Trail 30L", "Deportes", 55.00),
    ("Silla Ergo Basic", "Oficina", 145.00),
    ("Organizador Modular", "Oficina", 22.00),
]

CLIENTES = [
    ("Comercial Lima Norte", "Norte", "Retail"),
    ("Grupo Pacífico SAC", "Centro", "Corporativo"),
    ("Distribuciones del Sur", "Sur", "Mayorista"),
    ("Tienda Oriente Express", "Oriente", "Retail"),
    ("Oficinas Modernas SA", "Centro", "Corporativo"),
    ("MegaRetail Andino", "Norte", "Retail"),
    ("Importadora Cusco", "Sur", "Mayorista"),
    ("Selva Trading", "Oriente", "Mayorista"),
]

# Pesos de popularidad por producto: hace que el "top 5" sea estable y creíble
PESOS = [10, 3, 8, 2, 4, 5, 1, 9, 7, 2, 1, 6]

N_VENTAS = 200
random.seed(42)


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.unlink(missing_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            categoria TEXT NOT NULL,
            precio REAL NOT NULL
        );
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            region TEXT NOT NULL,
            segmento TEXT NOT NULL
        );
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY,
            producto_id INTEGER NOT NULL REFERENCES productos(id),
            cliente_id INTEGER NOT NULL REFERENCES clientes(id),
            fecha TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            monto REAL NOT NULL
        );
        """
    )

    cur.executemany(
        "INSERT INTO productos (nombre, categoria, precio) VALUES (?, ?, ?)",
        PRODUCTOS,
    )
    cur.executemany(
        "INSERT INTO clientes (nombre, region, segmento) VALUES (?, ?, ?)",
        CLIENTES,
    )

    inicio = date(2026, 1, 1)
    producto_ids = list(range(1, len(PRODUCTOS) + 1))
    for _ in range(N_VENTAS):
        pid = random.choices(producto_ids, weights=PESOS)[0]
        cid = random.randint(1, len(CLIENTES))
        fecha = inicio + timedelta(days=random.randint(0, 150))
        cantidad = random.randint(1, 40)
        precio = PRODUCTOS[pid - 1][2]
        monto = round(cantidad * precio * random.uniform(0.88, 1.0), 2)
        cur.execute(
            "INSERT INTO ventas (producto_id, cliente_id, fecha, cantidad, monto)"
            " VALUES (?, ?, ?, ?, ?)",
            (pid, cid, fecha.isoformat(), cantidad, monto),
        )

    conn.commit()
    total = cur.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
    conn.close()
    print(f"OK: {DB_PATH} creado con {total} ventas, "
          f"{len(PRODUCTOS)} productos y {len(CLIENTES)} clientes.")


if __name__ == "__main__":
    main()
