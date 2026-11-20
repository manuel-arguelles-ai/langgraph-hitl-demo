"""Definición del grafo multi-agente.

Topología:

    START → supervisor ──┬→ researcher ──────────────┐
                         ├→ sql_generate → sql_execute┤   (vuelven al supervisor)
                         └→ reporter → END            │
                         ▲────────────────────────────┘

El supervisor decide (con el LLM, una sola vez) qué agentes hacen falta y
luego rutea de forma determinística hasta agotar el plan; al final manda al
reporter. sql_execute contiene el interrupt() de human-in-the-loop — ver
src/agents/sql_agent.py para la explicación del patrón interrupt/resume.
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from src.agents.reporter import reporter_node
from src.agents.researcher import researcher_node
from src.agents.sql_agent import sql_execute_node, sql_generate_node
from src.llm import get_llm

CHECKPOINT_DB = Path(__file__).parent.parent / "data" / "checkpoints.db"


class AgentState(TypedDict, total=False):
    question: str
    plan: list[str]          # agentes que el supervisor decidió usar
    completed: list[str]     # agentes ya ejecutados
    kb_findings: str         # salida del researcher
    proposed_sql: str        # SQL propuesto por sql_generate (pre-aprobación)
    executed_sql: Optional[str]  # SQL realmente ejecutado (post-aprobación)
    sql_findings: str        # salida del sql_agent
    report: str              # salida del reporter


SUPERVISOR_SYSTEM = (
    "Eres el supervisor de un equipo de agentes. Dada la pregunta del usuario, "
    "decide qué agentes necesitas:\n"
    "- researcher: busca en documentos de políticas comerciales y catálogo.\n"
    "- sql_agent: consulta la base de datos de ventas (productos, clientes, ventas).\n"
    "Responde SOLO un JSON: {\"agents\": [...]} con uno o ambos agentes."
)


def supervisor_node(state: AgentState) -> dict:
    """Arma el plan en la primera pasada; las siguientes solo marcan progreso."""
    if "plan" in state:
        return {}  # el plan ya existe; el routing lo hace route_from_supervisor
    llm = get_llm()
    response = llm.invoke(
        [("system", SUPERVISOR_SYSTEM), ("user", state["question"])]
    )
    try:
        agents = json.loads(str(response.content)).get("agents", [])
        agents = [a for a in agents if a in ("researcher", "sql_agent")]
    except (json.JSONDecodeError, AttributeError):
        agents = ["researcher", "sql_agent"]  # fallback: usar ambos
    return {"plan": agents or ["researcher", "sql_agent"], "completed": []}


def route_from_supervisor(state: AgentState) -> str:
    """Siguiente agente pendiente del plan; si no queda ninguno → reporter."""
    pending = [a for a in state.get("plan", []) if a not in state.get("completed", [])]
    if not pending:
        return "reporter"
    nxt = pending[0]
    return "sql_generate" if nxt == "sql_agent" else nxt


def _mark(agent: str):
    def node(state: AgentState) -> dict:
        return {"completed": state.get("completed", []) + [agent]}
    return node


def build_graph(checkpointer=None):
    """Compila el grafo. Si no se pasa checkpointer, abre el SqliteSaver local
    (checkpointer=False compila sin persistencia: solo para demostrar que falla).

    El checkpointer es OBLIGATORIO para interrupt(): sin él no hay dónde
    persistir el estado pausado ni desde dónde reanudar.
    """
    builder = StateGraph(AgentState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("sql_generate", sql_generate_node)
    builder.add_node("sql_execute", sql_execute_node)
    builder.add_node("reporter", reporter_node)
    # Nodos triviales que marcan el agente como completado al volver al supervisor
    builder.add_node("done_researcher", _mark("researcher"))
    builder.add_node("done_sql", _mark("sql_agent"))

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        ["researcher", "sql_generate", "reporter"],
    )
    builder.add_edge("researcher", "done_researcher")
    builder.add_edge("done_researcher", "supervisor")
    builder.add_edge("sql_generate", "sql_execute")
    builder.add_edge("sql_execute", "done_sql")
    builder.add_edge("done_sql", "supervisor")
    builder.add_edge("reporter", END)

    if checkpointer is False:  # solo para el control de la demo: sin persistencia
        checkpointer = None
    elif checkpointer is None:
        # check_same_thread=False: el saver puede usarse desde el hilo del CLI
        conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
        checkpointer = SqliteSaver(conn)

    return builder.compile(checkpointer=checkpointer)
