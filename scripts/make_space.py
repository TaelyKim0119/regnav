"""Assemble and verify a Hugging Face Space folder for RegNav (Gradio SDK, CPU basic).

    NEBIUS_API_KEY= .venv/Scripts/python.exe -X utf8 scripts/make_space.py --out space_build

1. Copies only git-tracked files (so .env, notes/ and caches can never leak) into --out,
   with README.md = space/README.md front matter + the project README.
2. Checks the Space contract: front matter has sdk: gradio and app_file: app.py (the
   Gradio runtime runs `python app.py` and serves whatever listens on port 7860; our
   FastAPI app defaults to 0.0.0.0:7860). Docker Spaces are a paid option on HF now.
3. Boots `python app.py` from the built folder on a free port in dry-run mode and
   checks /health and the home page, as the Space runtime would.

Upload: push the --out folder to https://huggingface.co/spaces/<user>/regnav, then set
NEBIUS_API_KEY as a Space *secret* (never in files). The spending caps in
regnav/budget.py stay active on the Space.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (".env", "notes/", "data/cache/", "proposal_text.txt")
# not needed on a Gradio-SDK Space (kept in the repo for container deployments)
SKIP = ("Dockerfile", ".dockerignore", "data/budget.json")


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def front_matter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def build(out: Path) -> list[str]:
    if out.exists():
        shutil.rmtree(out)
    files = [f for f in tracked_files() if f != "README.md" and not f.startswith("space/") and f not in SKIP]
    bad = [f for f in files if any(f == p or (p.endswith("/") and f.startswith(p)) for p in FORBIDDEN)]
    if bad:
        raise SystemExit(f"refusing: forbidden files are tracked: {bad}")
    for rel in files:
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    header = (ROOT / "space" / "README.md").read_text(encoding="utf-8").rstrip() + "\n\n"
    (out / "README.md").write_text(header + (ROOT / "README.md").read_text(encoding="utf-8"), encoding="utf-8")
    return files


def check_contract(out: Path) -> list[str]:
    problems = []
    meta = front_matter((out / "README.md").read_text(encoding="utf-8"))
    if meta.get("sdk") != "gradio":
        problems.append("README front matter: sdk must be gradio")
    if meta.get("app_file") != "app.py":
        problems.append("README front matter: app_file must be app.py")
    app = (out / "app.py").read_text(encoding="utf-8")
    if 'os.environ.get("PORT", "7860")' not in app or 'os.environ.get("HOST", "0.0.0.0")' not in app:
        problems.append("app.py must listen on 0.0.0.0:7860 by default")
    if (out / "data" / "budget.json").exists():
        problems.append("data/budget.json must not ship (the Space keeps its own daily counter)")
    for path in out.rglob("*"):
        rel = path.relative_to(out).as_posix()
        if rel == ".env" or rel.startswith("notes/"):
            problems.append(f"secret or internal file in build: {rel}")
    return problems


def boot(out: Path, timeout: float = 60.0) -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, PORT=str(port), HOST="127.0.0.1", NEBIUS_API_KEY="", TAVILY_API_KEY="")
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=out, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + timeout
        while True:
            try:
                health = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3).read().decode()
                break
            except OSError:
                if proc.poll() is not None or time.time() > deadline:
                    raise SystemExit("app did not start:\n" + proc.stdout.read().decode(errors="replace")[-2000:])
                time.sleep(0.5)
        if '"ok":true' not in health.replace(" ", "") or "dry-run" not in health:
            raise SystemExit(f"unexpected /health: {health}")
        home = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10).read().decode()
        if "RegNav" not in home:
            raise SystemExit("home page did not render")
        print(f"boot ok on port {port}: {health}")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "space_build")
    parser.add_argument("--no-boot", action="store_true")
    args = parser.parse_args()
    if os.environ.get("NEBIUS_API_KEY"):
        sys.exit("refusing to run: unset NEBIUS_API_KEY (the boot check must stay offline)")
    files = build(args.out)
    problems = check_contract(args.out)
    if problems:
        sys.exit("Space contract failed:\n- " + "\n- ".join(problems))
    print(f"built {args.out} with {len(files) + 1} files; contract ok")
    if not args.no_boot:
        boot(args.out)


if __name__ == "__main__":
    main()
