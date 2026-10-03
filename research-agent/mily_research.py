#!/usr/bin/env python3
import argparse
import os
import sys
from datetime import datetime

from openai import OpenAI

MODEL = os.getenv("MILY_RESEARCH_MODEL", "gpt-6-luna")

INSTRUCTIONS = """
Eres MILY Research Agent, un agente general de investigación.
Investiga la solicitud del usuario usando búsqueda web cuando sea necesaria.
Descompón preguntas complejas en subtemas, contrasta fuentes y prioriza fuentes
primarias, documentación oficial, publicaciones académicas y fuentes reputadas.

Reglas:
- No inventes fuentes, citas, datos ni URLs.
- Distingue hechos comprobables, inferencias y opiniones.
- Para información actual, verifica fechas y cambios recientes.
- Si las fuentes discrepan, explica la discrepancia y cita las fuentes.
- No reveles secretos, API keys ni credenciales.
- Si no existe evidencia suficiente, dilo claramente.
- Responde en español salvo que el usuario pida otro idioma.

Formato:
# Resumen
# Hallazgos
# Evidencias y fuentes
# Contradicciones o incertidumbres
# Conclusión factual
"""

def research(question: str) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Falta OPENAI_API_KEY. Configúrala como variable de entorno.")

    client = OpenAI()
    response = client.responses.create(
        model=MODEL,
        instructions=INSTRUCTIONS,
        tools=[{"type": "web_search"}],
        input=question,
    )
    return response.output_text

def main():
    parser = argparse.ArgumentParser(description="MILY Research Agent")
    parser.add_argument("question", nargs="+", help="Pregunta o tema que quieres investigar")
    args = parser.parse_args()

    question = " ".join(args.question).strip()
    print(f"\nMILY Research Agent")
    print(f"Consulta: {question}")
    print(f"Fecha: {datetime.now().astimezone().isoformat(timespec='seconds')}\n")

    try:
        print(research(question))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
