"""Agente researcher: recupera docs de data/kb/ y sintetiza lo relevante."""

import re
from pathlib import Path

from src.llm import get_llm

KB_DIR = Path(__file__).parent.parent.parent / "data" / "kb"

SYSTEM = (
    "Eres un analista de la base de conocimiento comercial de la empresa. "
    "Responde SOLO con información presente en los documentos provistos. "
    "Sintetiza en 1-2 párrafos lo relevante para la pregunta, citando el "
    "documento de origen entre paréntesis."
)


def _retrieve(question: str, top_k: int = 3) -> list[tuple[str, str]]:
    """Retrieval simple por solapamiento de palabras clave (sin embeddings)."""
    tokens = {t for t in re.findall(r"\w+", question.lower()) if len(t) > 3}
    scored = []
    for doc in sorted(KB_DIR.glob("*.md")):
        text = doc.read_text(encoding="utf-8")
        score = sum(text.lower().count(t) for t in tokens)
        scored.append((score, doc.name, text))
    scored.sort(reverse=True)
    return [(name, text) for score, name, text in scored[:top_k] if score > 0]


def researcher_node(state: dict) -> dict:
    docs = _retrieve(state["question"])
    if not docs:
        return {"kb_findings": "No se encontraron documentos relevantes en la KB."}

    context = "\n\n".join(f"--- {name} ---\n{text}" for name, text in docs)
    llm = get_llm()
    response = llm.invoke(
        [
            ("system", SYSTEM),
            ("user", f"Documentos:\n{context}\n\nPregunta: {state['question']}"),
        ]
    )
    return {"kb_findings": response.content}
