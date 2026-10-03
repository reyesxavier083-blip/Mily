#!/usr/bin/env python3
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from openai import OpenAI

MODEL = os.getenv("MILY_RESEARCH_MODEL", "gpt-6-luna")

INSTRUCTIONS = """
Eres MILY Deep Person Research Agent. Investiga solo información pública, relevante y no sensible sobre una persona.
Desambigua homónimos usando profesión, organización, país, proyecto y otros identificadores públicos.
Prioriza fuentes oficiales/institucionales, publicaciones primarias, GitHub cuando corresponda y medios reputados.
Contrasta afirmaciones importantes y marca incertidumbres.

NO busques, infieras ni compiles domicilio, teléfono, correo personal, ubicación en tiempo real,
contraseñas, credenciales, documentos de identidad, datos financieros, médicos, sexuales u otros datos sensibles.
No facilites acoso, vigilancia, doxxing, suplantación o seguimiento.

Devuelve un informe factual con:
# Identidad y desambiguación
# Plan de investigación
# Cronología pública
# Trayectoria, obras y proyectos
# GitHub y actividad pública (si aplica)
# Matriz de evidencias
# Contradicciones o incertidumbres
# Fuentes
# Conclusión factual
"""

def run_pass(client, prompt):
    r = client.responses.create(
        model=MODEL,
        instructions=INSTRUCTIONS,
        tools=[{"type": "web_search"}],
        input=prompt,
    )
    return r.output_text

def build_plan(person):
    return [
        f"Desambiguación pública de {person}: nombres, profesión, organización, país, perfiles oficiales y homónimos.",
        f"Trayectoria profesional y cronología pública verificable de {person}.",
        f"Obras, publicaciones, proyectos, empresas o contribuciones públicas de {person}.",
        f"GitHub y actividad open source públicamente atribuible a {person}, si existe.",
        f"Verificación cruzada de afirmaciones importantes y contradicciones sobre {person}.",
    ]

def main():
    p = argparse.ArgumentParser(description="MILY Deep Person Research v2")
    p.add_argument("person", nargs="+", help="Nombre y contexto público de la persona")
    p.add_argument("--output", default="mily-person-report.md")
    p.add_argument("--txt", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--max-passes", type=int, default=5)
    args = p.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: falta OPENAI_API_KEY.", file=sys.stderr)
        sys.exit(1)

    person = " ".join(args.person).strip()
    client = OpenAI()
    plan = build_plan(person)[:max(1, min(args.max_passes, 5))]

    print(f"\nMILY Deep Person Research v2")
    print(f"Persona: {person}")
    print(f"Pasadas: {len(plan)}\n")

    evidence = []
    for i, subquery in enumerate(plan, 1):
        print(f"[{i}/{len(plan)}] Investigando...", flush=True)
        try:
            evidence.append(run_pass(client, subquery))
        except Exception as exc:
            evidence.append(f"PASADA {i} ERROR: {exc}")

    synthesis_prompt = f"""
Persona objetivo: {person}

Plan ejecutado:
{json.dumps(plan, ensure_ascii=False, indent=2)}

Resultados:
{chr(10).join(f"--- PASADA {i} ---\n{x}" for i, x in enumerate(evidence, 1))}

Construye un único informe final. No agregues datos que no estén respaldados.
Deduplica fuentes, señala contradicciones y conserva las citas/URLs disponibles.
"""
    report = run_pass(client, synthesis_prompt)

    out = Path(args.output).expanduser()
    out.write_text(
        f"# MILY Deep Person Research v2\n\n"
        f"**Persona:** {person}\n"
        f"**Fecha:** {datetime.now().astimezone().isoformat(timespec='seconds')}\n\n"
        + report + "\n",
        encoding="utf-8",
    )

    if args.txt:
        out.with_suffix(".txt").write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    if args.json:
        out.with_suffix(".json").write_text(
            json.dumps({"person": person, "plan": plan, "passes": len(evidence)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"\nInforme guardado: {out}")

if __name__ == "__main__":
    main()
