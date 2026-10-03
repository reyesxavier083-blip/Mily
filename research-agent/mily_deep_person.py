#!/usr/bin/env python3
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from openai import OpenAI

MODEL = os.getenv("MILY_RESEARCH_MODEL", "gpt-6-luna")

BASE = """
Eres MILY Deep Research Orchestrator v3. Investiga información pública y verificable.
Divide el trabajo, contrasta fuentes y distingue hechos, inferencias y afirmaciones no confirmadas.
Para personas, protege datos sensibles: no recopiles domicilio, teléfono, correo personal,
ubicación en tiempo real, credenciales, documentos, datos financieros, médicos o sexuales.
No facilites doxxing, acoso, vigilancia o suplantación.
"""

def ask(client, prompt):
    return client.responses.create(
        model=MODEL,
        instructions=BASE,
        tools=[{"type": "web_search"}],
        input=prompt,
    ).output_text

def main():
    p = argparse.ArgumentParser(description="MILY Deep Research Orchestrator v3")
    p.add_argument("subject", nargs="+")
    p.add_argument("--output", default="mily-deep-report.md")
    p.add_argument("--passes", type=int, default=6)
    p.add_argument("--txt", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("ERROR: falta OPENAI_API_KEY.")

    subject = " ".join(args.subject).strip()
    client = OpenAI()

    planner = ask(client, f"""Crea un plan exhaustivo y seguro para investigar:
{subject}
Incluye identidad/desambiguación si es una persona, cronología, proyectos,
publicaciones, fuentes primarias, fuentes independientes, GitHub cuando aplique,
y un bloque específico de contradicciones. Devuelve exactamente {args.passes} consultas.""")
    plan = [x.strip("- ").strip() for x in planner.splitlines() if x.strip()][:args.passes]

    if not plan:
        plan = [f"Investiga públicamente y verifica: {subject}"]

    results = []
    for i, query in enumerate(plan, 1):
        print(f"[{i}/{len(plan)}] {query}", flush=True)
        try:
            results.append(ask(client, query))
        except Exception as exc:
            results.append(f"ERROR EN PASADA {i}: {exc}")

    synthesis = ask(client, f"""Sintetiza una investigación profunda sobre:
{subject}

PLAN:
{json.dumps(plan, ensure_ascii=False, indent=2)}

RESULTADOS:
{chr(10).join(f"--- EVIDENCIA {i} ---\n{x}" for i, x in enumerate(results, 1))}

Produce:
# Identidad y alcance
# Resumen ejecutivo
# Cronología
# Trayectoria y proyectos
# GitHub/open source (si aplica)
# Matriz de evidencias
# Contradicciones e incertidumbres
# Fuentes
# Conclusión factual

No inventes información ni rellenes huecos. Conserva las fuentes y URLs disponibles.""")
    
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    report = f"# MILY Deep Research v3\n\n**Consulta:** {subject}\n**Fecha:** {stamp}\n\n{synthesis}\n"
    out = Path(args.output).expanduser()
    out.write_text(report, encoding="utf-8")

    if args.txt:
        out.with_suffix(".txt").write_text(report, encoding="utf-8")
    if args.json:
        out.with_suffix(".json").write_text(
            json.dumps({"subject": subject, "plan": plan, "passes": len(results), "timestamp": stamp},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"\nInforme: {out}")
    if args.txt:
        print(f"TXT: {out.with_suffix('.txt')}")
    if args.json:
        print(f"JSON: {out.with_suffix('.json')}")

if __name__ == "__main__":
    main()
