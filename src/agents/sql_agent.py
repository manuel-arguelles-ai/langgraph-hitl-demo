"""Agente SQL: genera una consulta sobre sales.db y la ejecuta SOLO tras
aprobación humana (human-in-the-loop con interrupt()).

El agente está partido en DOS nodos a propósito:

  1. sql_generate  — llama al LLM y propone el SQL.
  2. sql_execute   — interrupt() + ejecución.

¿Por qué dos nodos? Cuando un grafo se reanuda después de un interrupt(),
LangGraph RE-EJECUTA desde el inicio del nodo que se interrumpió (no desde la
línea del interrupt). Si la llamada al LLM viviera en el mismo nodo que el
interrupt, al reanudar se regeneraría el SQL — gastando tokens y, peor,
pudiendo producir un SQL distinto al que el humano aprobó. Separando la
generación en su propio nodo, su resultado queda persistido en el checkpoint
y al reanudar solo se re-ejecuta el nodo de aprobación/ejecución.
"""

import re
import sqlite3
from pathlib import Path

from langgraph.types import interrupt

from src.llm import get_llm

DB_PATH = Path(__file__).parent.parent.parent / "data" / "sales.db"

SYSTEM = (
    "Eres un experto en SQL para SQLite. Genera UNA sola consulta SELECT que "
    "responda la parte de la pregunta que puede resolverse con los DATOS del "
    "esquema dado (otro agente se encarga de políticas y documentos; no "
    "inventes columnas ni literales para eso). Devuélvela dentro de un "
    "bloque ```sql```. No uses INSERT/UPDATE/DELETE/DDL."
)


def _schema() -> str:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    conn.close()
    return "\n".join(r[0] for r in rows)


def _extract_sql(text: str) -> str:
    match = re.search(r"```sql\s*(.+?)```", text, re.DOTALL | re.IGNORECASE)
    return (match.group(1) if match else text).strip()


def sql_generate_node(state: dict) -> dict:
    """Nodo 1: el LLM propone el SQL. Su salida queda en el checkpoint."""
    llm = get_llm()
    response = llm.invoke(
        [
            ("system", SYSTEM),
            ("user", f"Esquema:\n{_schema()}\n\nPregunta: {state['question']}"),
        ]
    )
    return {"proposed_sql": _extract_sql(response.content)}


def sql_execute_node(state: dict) -> dict:
    """Nodo 2: PAUSA el grafo y pide aprobación humana antes de ejecutar.

    interrupt() lanza una excepción especial que LangGraph captura: el grafo
    se detiene, el estado completo queda persistido en el checkpointer
    (SqliteSaver) y el payload que pasamos aquí viaja al cliente (main.py)
    dentro de result["__interrupt__"]. El proceso puede incluso morir y
    relanzarse: con el mismo thread_id, el checkpoint restaura todo.

    Cuando el cliente reanuda con Command(resume=decision), este nodo se
    RE-EJECUTA desde el principio, pero esta vez interrupt() NO pausa:
    devuelve `decision` y el código continúa hacia la ejecución.
    """
    decision = interrupt(
        {
            "type": "sql_approval",
            "proposed_sql": state["proposed_sql"],
            "question": state["question"],
            "options": ["approve", "reject", "edit"],
        }
    )

    action = decision.get("action", "reject")

    if action == "reject":
        reason = decision.get("reason", "sin motivo indicado")
        return {
            "sql_findings": f"El humano RECHAZÓ la consulta propuesta ({reason}). "
            "No se ejecutó SQL.",
            "executed_sql": None,
        }

    # "edit": el humano reemplaza el SQL propuesto por el suyo.
    sql = decision.get("sql", state["proposed_sql"]) if action == "edit" else state["proposed_sql"]

    # Guardrail mínimo: solo lecturas, una sola sentencia.
    if not sql.lstrip().lower().startswith(("select", "with")):
        return {
            "sql_findings": "Consulta no ejecutada: solo se permiten SELECT.",
            "executed_sql": None,
        }

    # Solo lectura a nivel de conexión: defensa real además del chequeo de prefijo.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(50)
    except sqlite3.Error as exc:
        return {
            "sql_findings": f"Error al ejecutar el SQL aprobado: {exc}",
            "executed_sql": sql,
        }
    finally:
        conn.close()

    table = " | ".join(cols) + "\n" + "\n".join(
        " | ".join(str(v) for v in row) for row in rows
    )
    return {
        "sql_findings": f"Resultado de la consulta aprobada:\n{table}",
        "executed_sql": sql,
    }
