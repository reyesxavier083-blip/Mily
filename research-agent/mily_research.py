#!/usr/bin/env python3
import argparse
import os
import sys
from datetime import datetime

from openai import OpenAI

MODEL = os.getenv("MILY_RESEARCH_MODEL", "gpt-6-luna")

GENERAL_INSTRUCTIONS = """
Eres MILY Research Agent, un agente general de investigación.
Investiga usando búsqueda web cuando sea necesaria. Descompón preguntas complejas,
contrasta fuentes y prioriza fuentes primarias, documentación oficial, publicaciones
académicas y fuentes reputadas.

Reglas:
- No inventes fuentes, citas, datos ni URLs.
- Distingue hechos comprobables, inferencias y opiniones.
- Para información actual, verifica fechas y cambios recientes.
- Si las fuentes discrepan, explica la discrepancia.
- No reveles secretos, API keys ni credenciales.
- Si no existe evidencia suficiente, dilo claramente.
- Responde en español salvo que el usuario pida otro idioma.
"""

PERSON_INSTRUCTIONS = GENERAL_INSTRUCTIONS + """
MODO INVESTIGACIÓN DE PERSONA:
Investiga únicamente información pública y relevante sobre una persona, especialmente
trayectoria profesional, obras, publicaciones, cargos públicos, empresas/proyectos,
perfiles profesionales o presencia pública verificable.

Objetivos:
1. Desambiguar a la persona usando nombre, profesión, organización, país o identificadores
   públicos proporcionados por el usuario.
2. Construir una cronología de hechos públicos verificables.
3. Comparar biografías y perfiles oficiales con fuentes independientes.
4. Identificar publicaciones, proyectos, cargos, premios y declaraciones públicas
   cuando existan fuentes fiables.
5. Marcar explícitamente las afirmaciones no confirmadas, homónimos y posibles errores.
6. Para GitHub, revisar repositorios, README, commits, issues y PRs cuando sean relevantes.

LÍMITES DE PRIVACIDAD:
- No buscar, inferir ni compilar domicilio, teléfono, correo personal, ubicación en tiempo
  real, contraseñas, credenciales, documentos de identidad, datos financieros, información
  médica, datos sexuales, ni otros datos personales sensibles.
- No facilitar acoso, vigilancia, doxxing, suplantación ni seguimiento de una persona.
- No convertir información dispersa en un perfil invasivo de una persona privada.
- Si el objetivo es una persona privada y la petición busca datos sensibles o localización,
  rechaza esa parte y ofrece investigación pública y no sensible.
- No confundas personas con el mismo nombre.

Formato:
# Identidad y desambiguación
# Resumen
# Cronología pública
# Trayectoria y proyectos
# Evidencia y fuentes
# Contradicciones o incertidumbres
# Conclusión factual
"""

def research(question: str, person_mode: bool = False) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Falta OPENAI_API_KEY. Configúrala como variable de entorno.")

    client = OpenAI()
    instructions = PERSON_INSTRUCTIONS if person_mode else GENERAL_INSTRUCTIONS
    response = client.responses.create(
        model=MODEL,
        instructions=instructions,
        tools=[{"type": "web_search"}],
        input=question,
    )
    return response.output_text

def main():
    parser = argparse.ArgumentParser(description="MILY Research Agent")
    parser.add_argument("question", nargs="+", help="Pregunta o tema que quieres investigar")
    parser.add_argument(
        "--person",
        action="store_true",
        help="Activa investigación profunda de una persona usando solo información pública y no sensible",
    )
    args = parser.parse_args()

    question = " ".join(args.question).strip()
    print("\nMILY Research Agent")
    print(f"Modo: {'PERSONA' if args.person else 'GENERAL'}")
    print(f"Consulta: {question}")
    print(f"Fecha: {datetime.now().astimezone().isoformat(timespec='seconds')}\n")

    try:
        print(research(question, person_mode=args.person))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
