"""Assemble and verify a Hugging Face Space folder for RegNav (Gradio SDK, CPU basic).

    NEBIUS_API_KEY= .venv/Scripts/python.exe -X utf8 scripts/make_space.py --out space_build

1. Copies only git-tracked files (so .env, notes/ and caches can never leak) into --out,
   with README.md = space/README.md front matter + the project README.
2. Checks the Space contract: front matter has sdk: gradio and app_file: space_app.py.
   Free HF accounts can only run Gradio Spaces on ZeroGPU (Docker and CPU basic are paid),
   and ZeroGPU refuses to start without a registered @spaces.GPU function, so
   space_app.py is a Gradio app that registers one (never called; RegNav needs no GPU).
3. Boots `python space_app.py` from the built folder on a free port in dry-run mode and
   checks the page and one review through the Gradio API, as the Space runtime would.

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
    files = [f for f in tracked_files() if f != "README.md" and not f.startswith(("space/", "docs/")) and f not in SKIP]
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
    if meta.get("app_file") != "space_app.py":
        problems.append("README front matter: app_file must be space_app.py")
    app = (out / "space_app.py").read_text(encoding="utf-8")
    if "@spaces.GPU" not in app or "demo.launch(" not in app:
        problems.append("space_app.py must register a @spaces.GPU function and call demo.launch()")
    if (out / "data" / "budget.json").exists():
        problems.append("data/budget.json must not ship (the Space keeps its own daily counter)")
    for path in out.rglob("*"):
        rel = path.relative_to(out).as_posix()
        if rel == ".env" or rel.startswith("notes/"):
            problems.append(f"secret or internal file in build: {rel}")
    return problems


def boot(out: Path, timeout: float = 120.0) -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, GRADIO_SERVER_PORT=str(port), GRADIO_SERVER_NAME="127.0.0.1",
               NEBIUS_API_KEY="", TAVILY_API_KEY="", PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen([sys.executable, "space_app.py"], cwd=out, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + timeout
        while True:
            try:
                home = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read().decode()
                break
            except OSError:
                if proc.poll() is not None or time.time() > deadline:
                    raise SystemExit("space app did not start:\n" + proc.stdout.read().decode(errors="replace")[-2000:])
                time.sleep(1)
        if "RegNav" not in home:
            raise SystemExit("home page did not render")
        from gradio_client import Client
        client = Client(f"http://127.0.0.1:{port}/", verbose=False)
        status, report = client.predict(
            "Aftermarket brake pad set for passenger car disc brakes", api_name="/run_review")
        if "Offline demo mode" not in status or "UN R90" not in report:
            raise SystemExit(f"unexpected review output: {status[:200]} / {report[:300]}")
        # Korean description with the 한국어 report language (the page's language switch)
        status_ko, report_ko = client.predict(
            "승용차 디스크 브레이크용 애프터마켓 브레이크 패드 세트", "ko", api_name="/run_review")
        if "오프라인 데모 모드" not in status_ko or "UN R90" not in report_ko or "#### 🔴 필수 검토" not in report_ko:
            raise SystemExit(f"unexpected Korean review output: {status_ko[:200]} / {report_ko[:300]}")
        print(f"boot ok on port {port}: page renders, review returns {report.count(chr(10))} lines, UN R90 present; "
              f"Korean review returns {report_ko.count(chr(10))} lines in Korean, UN R90 present")
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
