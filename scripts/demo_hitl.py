"""Demo automática del HITL (sin claves, LLM falso, sin teclado).

Muestra tres cosas:
  1. Con checkpointer: el grafo PAUSA en el interrupt() y no ejecuta SQL.
  2. Un grafo NUEVO (simula otro proceso) sobre el mismo thread_id ve la pausa
     y reanuda desde el checkpoint con la decisión humana.
  3. Control: sin checkpointer no hay estado que consultar ni desde dónde reanudar.

Uso:  python scripts/demo_hitl.py
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ["FAKE_LLM"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from src.graph import build_graph  # noqa: E402

Q = "¿cuáles fueron los 5 productos más vendidos y qué dice la política de descuentos?"


def saver(path):
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def main() -> None:
    db = Path(tempfile.mkdtemp()) / "ckpt.db"
    cfg = {"configurable": {"thread_id": "demo"}}

    print("== 1. Corrida inicial con checkpointer ==")
    g1 = build_graph(saver(db))
    r = g1.invoke({"question": Q}, cfg)
    assert "__interrupt__" in r, "el grafo debía pausar"
    st = g1.get_state(cfg)
    print("pausado:", bool(r["__interrupt__"]), "| siguiente nodo:", st.next)
    print("executed_sql antes de aprobar:", st.values.get("executed_sql"))
    assert st.values.get("executed_sql") is None
    print("SQL propuesto (primera línea):", st.values["proposed_sql"].splitlines()[0])

    print("\n== 2. 'Proceso nuevo': otro grafo, mismo thread_id y misma BD ==")
    g2 = build_graph(saver(db))
    st2 = g2.get_state(cfg)
    print("pausa recuperada del checkpoint:", bool(st2.interrupts), "| next:", st2.next)
    assert st2.interrupts and st2.values["proposed_sql"] == st.values["proposed_sql"]
    r2 = g2.invoke(Command(resume={"action": "approve"}), cfg)
    assert "__interrupt__" not in r2 and r2.get("report")
    print("reanudó y terminó; executed_sql == proposed_sql:",
          r2["executed_sql"] == st.values["proposed_sql"])
    print("resultado SQL:\n" + r2["sql_findings"])

    print("\n== 3. Control: sin checkpointer ==")
    g3 = build_graph(checkpointer=False)  # False -> compila sin persistencia
    c3 = {"configurable": {"thread_id": "x"}}
    r3 = g3.invoke({"question": Q}, c3)
    print("la pausa se emite:", "__interrupt__" in r3, "(pero no queda nada guardado)")
    for nombre, fn in [
        ("get_state", lambda: g3.get_state(c3)),
        ("resume", lambda: g3.invoke(Command(resume={"action": "approve"}), c3)),
    ]:
        try:
            fn()
            print(f"{nombre}: INESPERADO, no falló")
        except Exception as exc:  # noqa: BLE001
            print(f"{nombre} falla: {type(exc).__name__}: {exc}")

if __name__ == "__main__":
    main()
