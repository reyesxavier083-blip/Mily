#!/usr/bin/env python3
"""Start the LEYRA API + web interface.

Usage:
    python run.py [--host 0.0.0.0] [--port 8000] [--reload]

The repository root is added to ``sys.path`` so ``leyra_core`` and ``mily_core``
resolve without installing anything.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="LEYRA API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run("app.main:create_app", factory=True, host=args.host, port=args.port,
                reload=args.reload, log_level="info", proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
