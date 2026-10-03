"""RegNav CLI.  python cli.py "LED rear lamp module" [--live] [--lang=ko]

The part may be written in English, Korean or both. --lang=ko (or --ko) prints the report
with Korean labels and, with --live, asks Nemotron for a Korean rationale.
"""
import sys

from regnav.pipeline import review

part = " ".join(a for a in sys.argv[1:] if not a.startswith("--")) or "LED rear lamp module"
live = "--live" in sys.argv
lang = "ko" if "--ko" in sys.argv or "--lang=ko" in sys.argv else "en"
print(review(part, dry_run=not live, lang=lang).markdown())
