"""Agente reporter: sintetiza los hallazgos en un reporte markdown."""

from src.llm import get_llm

SYSTEM = (
    "Eres un redactor de reportes ejecutivos. Con los hallazgos provistos, "
    "escribe un reporte en markdown con: título, hallazgos de ventas (incluye "
    "la tabla de datos), política comercial aplicable y una recomendación. "
    "Sé conciso y no inventes datos que no estén en los hallazgos."
)


def reporter_node(state: dict) -> dict:
    llm = get_llm()
    response = llm.invoke(
        [
            ("system", SYSTEM),
            (
                "user",
                f"Pregunta original: {state['question']}\n\n"
                f"Hallazgos de la base de conocimiento:\n{state.get('kb_findings', '(ninguno)')}\n\n"
                f"Hallazgos de la base de datos:\n{state.get('sql_findings', '(ninguno)')}\n\n"
                f"SQL ejecutado: {state.get('executed_sql') or '(ninguno)'}",
            ),
        ]
    )
    return {"report": response.content}
