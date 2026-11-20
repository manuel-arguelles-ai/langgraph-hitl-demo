"""CLI del demo: corre el grafo con un thread_id y maneja el ciclo
interrupt → input humano → resume.

Uso:
    python -m src.main --question "¿cuáles fueron los 5 productos más vendidos?"
    python -m src.main -q "..." --thread-id mi-sesion

El thread_id identifica la conversación en el checkpointer (SqliteSaver).
Si el proceso muere mientras el grafo está pausado en un interrupt, basta
relanzar con el MISMO thread_id: el grafo retoma exactamente donde quedó.
"""

import argparse
import sys
import uuid
from pathlib import Path

from langgraph.types import Command

from src.graph import CHECKPOINT_DB, build_graph


def ask_human(payload: dict) -> dict:
    """Muestra el SQL propuesto y captura la decisión por consola."""
    print("\n" + "=" * 60)
    print("⏸  GRAFO PAUSADO — se requiere aprobación humana")
    print("=" * 60)
    print(f"Pregunta: {payload['question']}\n")
    print("SQL propuesto:")
    print("-" * 60)
    print(payload["proposed_sql"])
    print("-" * 60)

    while True:
        choice = input("¿[a]probar / [r]echazar / [e]ditar? ").strip().lower()
        if choice in ("a", "approve"):
            return {"action": "approve"}
        if choice in ("r", "reject"):
            reason = input("Motivo del rechazo: ").strip()
            return {"action": "reject", "reason": reason}
        if choice in ("e", "edit"):
            print("Escribe el SQL nuevo (una línea, termina con Enter):")
            sql = input("> ").strip()
            return {"action": "edit", "sql": sql}
        print("Opción inválida. Usa a / r / e.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo multi-agente LangGraph")
    parser.add_argument("--question", "-q", required=True)
    parser.add_argument(
        "--thread-id",
        default=None,
        help="ID de conversación para el checkpointer (default: uno nuevo)",
    )
    parser.add_argument(
        "--pause-only",
        action="store_true",
        help="corre hasta la pausa de aprobación, imprime el SQL y termina el "
        "proceso (el estado queda en el checkpoint)",
    )
    parser.add_argument(
        "--decision",
        choices=["approve", "reject"],
        help="decisión no interactiva al reanudar (útil para scripts/CI)",
    )
    args = parser.parse_args()

    thread_id = args.thread_id or f"demo-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    graph = build_graph()

    print(f"▶ thread_id = {thread_id}")

    # ───────────────────────── ciclo interrupt → input → resume ──────────
    # 1. invoke() corre el grafo hasta terminar O hasta el primer interrupt().
    # 2. Si el resultado trae "__interrupt__", el grafo está pausado y el
    #    estado completo ya quedó persistido en SQLite (checkpoints.db).
    # 3. Pedimos la decisión al humano y reanudamos con Command(resume=...):
    #    LangGraph re-entra al nodo pausado y el interrupt() devuelve la
    #    decisión en lugar de pausar. El while cubre el caso de múltiples
    #    interrupts en una misma corrida.
    #
    # Caso "el proceso murió mientras estaba pausado": si el thread_id ya
    # tiene un interrupt pendiente en el checkpoint, NO mandamos input nuevo
    # (eso re-arrancaría el grafo); vamos directo a pedir la aprobación.
    snapshot = graph.get_state(config)
    if snapshot.interrupts:
        print("↻ Encontré un interrupt pendiente en el checkpoint; retomando…")
        result = dict(snapshot.values)
        result["__interrupt__"] = list(snapshot.interrupts)
    else:
        result = graph.invoke({"question": args.question}, config)

    while interrupts := result.get("__interrupt__"):
        if args.pause_only:
            p = interrupts[0].value
            print("\n⏸  PAUSADO en sql_execute, esperando aprobación. SQL propuesto:")
            print(p["proposed_sql"])
            print(f"\n(El proceso termina aquí; el estado está en {CHECKPOINT_DB.name}. "
                  f"Reanuda con --thread-id {thread_id})")
            return
        if args.decision:
            decision = {"action": args.decision, "reason": "decisión no interactiva"}
            print(f"\n▶ Decisión no interactiva: {args.decision}")
        else:
            decision = ask_human(interrupts[0].value)
        print("\n▶ Reanudando el grafo desde el checkpoint…")
        result = graph.invoke(Command(resume=decision), config)
    # ──────────────────────────────────────────────────────────────────────

    print("\n" + "=" * 60)
    print("✅ REPORTE FINAL")
    print("=" * 60)
    print(result.get("report", "(sin reporte)"))

    if result.get("report"):
        out = Path(__file__).parent.parent / "reports" / f"{thread_id}.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(result["report"], encoding="utf-8")
        print(f"\n💾 Reporte guardado en {out.relative_to(out.parent.parent)}")

    if result.get("executed_sql"):
        print("\n[SQL ejecutado con aprobación humana]")
        print(result["executed_sql"])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrumpido. El estado quedó en el checkpoint; "
              "relanza con el mismo --thread-id para continuar.")
        sys.exit(130)
