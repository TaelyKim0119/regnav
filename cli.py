"""RegNav CLI.  python cli.py "LED rear lamp module" [--live]"""
import sys

from regnav.pipeline import review

part = " ".join(a for a in sys.argv[1:] if not a.startswith("--")) or "LED rear lamp module"
live = "--live" in sys.argv
print(review(part, dry_run=not live).markdown())
