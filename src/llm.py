"""Factory del LLM.

Por defecto usa DeepSeek V4 Flash vía langchain-openai (la API de DeepSeek
es compatible con OpenAI; requiere DEEPSEEK_API_KEY). Con FAKE_LLM=1 (o si no hay DEEPSEEK_API_KEY) devuelve
un modelo determinístico que responde según el rol del prompt — útil para
probar la mecánica del grafo (routing, interrupt/resume, checkpointer) sin
consumir API.
"""

import os

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage

MODEL_ID = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"


class _FakeRoleAwareLLM(FakeMessagesListChatModel):
    """Responde según marcadores del system prompt de cada agente."""

    def __init__(self) -> None:
        super().__init__(responses=[AIMessage(content="")])

    def invoke(self, input, config=None, **kwargs):  # type: ignore[override]
        text = self._flatten(input)
        if "supervisor de un equipo" in text:
            return AIMessage(content='{"agents": ["researcher", "sql_agent"]}')
        if "analista de la base de conocimiento" in text:
            return AIMessage(
                content=(
                    "Según la política de descuentos, los 5 productos más vendidos "
                    "del trimestre son 'productos protegidos': admiten un descuento "
                    "máximo del 5% sin importar su categoría, y superar ese tope "
                    "requiere aprobación de Gerencia General. Además, Electrónica "
                    "tiene un máximo general del 10% y Deportes del 15% (8% en "
                    "temporada alta)."
                )
            )
        if "experto en SQL" in text:
            return AIMessage(
                content=(
                    "```sql\n"
                    "SELECT p.nombre, p.categoria, SUM(v.cantidad) AS unidades,\n"
                    "       ROUND(SUM(v.monto), 2) AS ingresos\n"
                    "FROM ventas v\n"
                    "JOIN productos p ON p.id = v.producto_id\n"
                    "GROUP BY p.id\n"
                    "ORDER BY unidades DESC\n"
                    "LIMIT 5;\n"
                    "```"
                )
            )
        if "redactor de reportes" in text:
            return AIMessage(
                content=(
                    "# Reporte: top 5 productos y política de descuentos\n\n"
                    "## Hallazgos de ventas\n"
                    "Los 5 productos más vendidos surgen de la consulta aprobada "
                    "sobre sales.db (ver datos en la sección de evidencia).\n\n"
                    "## Política aplicable\n"
                    "Esos 5 productos califican como 'protegidos': descuento "
                    "máximo del 5%, con excepciones solo vía Gerencia General.\n\n"
                    "## Recomendación\n"
                    "Actualizar la lista trimestral de protegidos con este ranking."
                )
            )
        return AIMessage(content="(respuesta fake genérica)")

    @staticmethod
    def _flatten(input) -> str:
        if isinstance(input, str):
            return input
        parts = []
        for m in input:
            if isinstance(m, BaseMessage):
                parts.append(str(m.content))
            elif isinstance(m, tuple):
                parts.append(str(m[1]))
        return "\n".join(parts)


def get_llm():
    # Sin clave de API se usa el LLM falso: la demo corre sin gastar nada.
    if os.environ.get("FAKE_LLM") == "1" or not os.environ.get("DEEPSEEK_API_KEY"):
        return _FakeRoleAwareLLM()
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=MODEL_ID,
        base_url=BASE_URL,
        api_key=os.environ["DEEPSEEK_API_KEY"],
        max_tokens=2048,
        temperature=0,
    )
