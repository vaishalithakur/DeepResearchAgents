"""
Print (or save) the compiled LangGraph analysis graph's own structure.

Builds the same graph `main.py`'s lifespan builds -- via a throwaway
`ClaudeClient` that's never actually called -- and asks it to describe its
own topology. No Anthropic API key needs to be real: constructing
`ClaudeClient` only builds an (unused) `anthropic.AsyncAnthropic` instance,
it doesn't make a network call.

Usage (from the `backend` directory, with the venv active):
    python -m scripts.print_graph            # ASCII art in the terminal
    python -m scripts.print_graph --mermaid   # print Mermaid source instead
    python -m scripts.print_graph --png out.png   # save a rendered PNG

`--png` calls out to a remote renderer (mermaid.ink) and needs network
access; the other two modes are fully offline.
"""

from __future__ import annotations

import argparse
import sys

from app.agents.claude_client import ClaudeClient
from app.agents.graph import build_analysis_graph
from app.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mermaid", action="store_true", help="print Mermaid source instead of ASCII")
    parser.add_argument("--png", metavar="PATH", help="save a rendered PNG to this path instead")
    args = parser.parse_args()

    settings = Settings(ANTHROPIC_API_KEY="sk-ant-not-a-real-key-graph-inspection-only")
    graph = build_analysis_graph(ClaudeClient(settings), settings)
    structure = graph.get_graph()

    if args.png:
        structure.draw_mermaid_png(output_file_path=args.png)
        print(f"saved {args.png}")
    elif args.mermaid:
        print(structure.draw_mermaid())
    else:
        try:
            print(structure.draw_ascii())
        except ImportError:
            print("ASCII rendering needs `grandalf` (pip install grandalf); "
                  "falling back to Mermaid source:\n", file=sys.stderr)
            print(structure.draw_mermaid())


if __name__ == "__main__":
    main()
