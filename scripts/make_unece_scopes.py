"""Build data/unece_scopes.json: the Scope paragraph of every catalogued UN Regulation,
taken from its newest full-text republication in the EU Official Journal (OJ), or from a
later OJ amendment act that rewrites that paragraph.

    python -X utf8 scripts/make_unece_scopes.py                  # whole catalogue
    python -X utf8 scripts/make_unece_scopes.py --only R148,R90  # just these (merged into the file)
    python -X utf8 scripts/make_unece_scopes.py --refresh-index  # re-run the SPARQL title query

unece.org refuses programs (HTTP 403 / bot check), but the EU Publications Office serves
the OJ copy of every UN Regulation the EU has acceded to through CELLAR content
negotiation (XHTML, no bot protection; robots.txt allows it). One SPARQL query lists all
English OJ titles naming a "Regulation" at once. For each catalogue entry:

1. the newest act holding the whole regulation wins: a full text, or a corrigendum that
   republishes it ("Regulation No 124 should read as follows"); up to MAX_TRIES full
   texts are read;
2. every OJ act for it dated after that (amendment-only acts such as "2010 amendments to
   Regulation No 30", partial corrigenda) is read too and listed in "later_oj_acts",
   oldest first: one that rewrites paragraph 1 ("Paragraph 1, amend to read") supplies the
   Scope ("scope_from"), one that changes only sub-paragraphs of 1 is flagged, and their
   version lines show how far the OJ text goes beyond the base act.

The build log lists every act dated after the chosen one, so coverage claims can be
checked. Only English XHTML is read: an act CELLAR has only as PDF (older, badly typeset
OJ issues) is logged and skipped. Raw downloads are cached under data/cache/unece_oj/
(gitignored) so a rebuild is cheap.

Only the Scope paragraph and citation metadata are committed, never the full text.
OJ copies are EU-published documentation: only the original UNECE texts are authentic,
and the OJ copy can lag the current UNECE series, so each entry keeps the OJ date and
the "Incorporating all valid text up to" line.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from regnav.sources import unece  # noqa: E402

CELLAR = "http://publications.europa.eu/resource/celex/"
SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
EURLEX = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:"
CACHE = ROOT / "data" / "cache" / "unece_oj"
UA = "RegNav/0.1 (scope snapshot builder; https://github.com/TaelyKim0119/regnav)"
NOTE = ("EU Official Journal copies; only the original UNECE texts are authentic. "
        "OJ copies can lag the current UNECE series: check each entry's oj_date and version line.")
SCOPE_CAP = 2000
MAX_TRIES = 4  # newest full-text candidates fetched per regulation before giving up

# Every English expression of a sector-4 (international agreements) act whose title names a
# "regulation" in any case or form ("Regulation No 30", "UN Regulation 44", ...); the Python
# side sorts out numbers, suffixes and kinds. SPARQL string literals here must not contain
# backslash escapes, hence CONTAINS, not REGEX.
QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?title ?date WHERE {
 ?work cdm:resource_legal_id_celex ?celex .
 FILTER(STRSTARTS(STR(?celex), "4"))
 ?expr cdm:expression_belongs_to_work ?work ;
       cdm:expression_title ?title ;
       cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> .
 FILTER(CONTAINS(LCASE(STR(?title)), "regulation"))
 OPTIONAL { ?work cdm:work_date_document ?date }
}
"""

# Titles (after clean_title): "UN Regulation No 148 – ...", "Regulation No. 90 of the Economic
# Commission for Europe ...", "UN Regulation No 13-H – ...", "Amendments to UN Regulation 44
# [2020/1223] – ...", "2010 amendments to Regulation No 30 ...", "Corrigendum to Regulation
# No 124 ...", "Technical requirements of Regulation No 48 ..." (1997 full texts). "No" is
# optional; "(?!/)" keeps EU acts such as "Regulation No 10/2011" out.
TITLE_RE = re.compile(
    r"^(?P<pre>corrigendum to (?:the technical requirements of )?|technical requirements of |"
    r"(?:\d{4} (?:and \d{4} )?)?amendments? to |(?:supplement|addendum) \d+ to )?"
    r"(?:the )?(?:UN )?Regulation (?:No\.? ?)?(?P<n>\d{1,3})(?P<h>-?H)?\b(?!/)", re.I)
# A title that names a UN Regulation somewhere; if TITLE_RE cannot parse it the build says so.
UN_MENTION_RE = re.compile(r"\bUN Regulation\b|\bRegulation (?:No\.? ?)?\d{1,3}\b(?!/).*"
                           r"(?:Economic Commission for Europe|UN/?ECE)", re.I)
# "Regulation No 124 should read as follows:": a corrigendum that republishes the whole text
REPUBLISHED_RE = re.compile(r"\bRegulation (?:No\.? ?)?\d{1,3}(?:-?H)? (?:should|shall) read as follows", re.I)


class Fetcher:
    """Polite HTTP: at most ~1 request per second, every download cached on disk."""

    def __init__(self):
        self.client = httpx.Client(timeout=240, follow_redirects=True, headers={"User-Agent": UA})
        self.last = 0.0
        self.requests = 0

    def _wait(self):
        pause = 1.1 - (time.monotonic() - self.last)
        if pause > 0:
            time.sleep(pause)
        self.last = time.monotonic()
        self.requests += 1

    def titles(self, refresh: bool = False) -> list[dict]:
        cached = CACHE / "sparql_titles.json"
        if cached.exists() and not refresh:
            return json.loads(cached.read_text(encoding="utf-8"))
        self._wait()
        t0 = time.monotonic()
        r = self.client.post(SPARQL, data={"query": QUERY},
                             headers={"Accept": "application/sparql-results+json"})
        r.raise_for_status()
        rows = [{k: v["value"] for k, v in b.items()} for b in r.json()["results"]["bindings"]]
        CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"SPARQL: {len(rows)} titles in {time.monotonic() - t0:.0f}s")
        return rows

    def get(self, celex: str) -> bytes | None:
        """English XHTML of one OJ act; None when CELLAR has none.

        An empty cache file records "not available" so it is not asked for again, but only
        for a definite answer (404/406, or a 200 of another type such as PDF): a transient
        429/5xx is retried and then stops the build, so it can never quietly push an entry
        onto an older act.
        """
        cached = CACHE / f"{re.sub(r'[^\w.-]', '_', celex)}.xhtml"
        if cached.exists():
            return cached.read_bytes() or None
        for attempt in range(3):
            self._wait()
            # CELLAR answers 404 for "42014X0808(02)" unless the parentheses are percent-encoded
            r = self.client.get(CELLAR + quote(celex, safe=""),
                                headers={"Accept": "application/xhtml+xml", "Accept-Language": "eng"})
            if r.status_code not in (429, 500, 502, 503, 504):
                break
            time.sleep(10 * (attempt + 1))
        ok = r.status_code == 200 and "xhtml" in r.headers.get("content-type", "")
        if not ok and r.status_code not in (200, 404, 406):
            raise RuntimeError(f"{celex}: HTTP {r.status_code} from CELLAR; not caching, rerun later")
        CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(r.content if ok else b"")
        if not ok:
            print(f"  {celex}: HTTP {r.status_code} {r.headers.get('content-type', '')}: no English XHTML")
        return r.content if ok else None


def classify(title: str) -> tuple[str, str] | None:
    """(code, kind) for an OJ title naming a UN Regulation; kind is "full", "amendment" or
    "corrigendum" (a corrigendum may still republish the whole text: see REPUBLISHED_RE)."""
    m = TITLE_RE.match(clean_title(title))
    if not m:
        return None
    pre = (m.group("pre") or "").lower()
    kind = ("corrigendum" if pre.startswith("corrigendum") else
            "amendment" if pre and not pre.startswith("technical") else "full")
    return f"UN R{int(m.group('n'))}{'-H' if m.group('h') else ''}", kind


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.replace("\u00a0", " ")).strip()


# ---- document -> lines ------------------------------------------------------------------

HEAD = "\x01"  # prefix of lines that are headings (class "oj-ti-grseq-1")
NUM_ONLY = re.compile(r"^(?:\d+(?:\.\d+)*\.?|\(\w{1,4}\)|[a-z]\)|—|–|-|•|\*)$")


def xhtml_lines(xhtml: str) -> list[str]:
    """Flatten OJ XHTML to one line per paragraph / table row.

    Footnote call-outs are dropped, subscripts are glued to their base ("M1"), and a
    paragraph-number cell is joined with the text cell next to it ("1.1. This Regulation").
    Headings are prefixed with HEAD so the scope section can be cut cleanly.
    """
    x = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>|<!--.*?-->", "", xhtml, flags=re.S)
    x = re.sub(r"<head\b.*?</head>", "", x, flags=re.S)
    x = re.sub(r"\s+", " ", x)  # source line breaks are not text breaks
    x = re.sub(r'<a\b[^>]*(?:\bid="ntc|\bhref="#ntr)[^>]*>.*?</a>', "", x)  # footnote call-outs
    x = re.sub(r'\s<span class="oj-super">[^<]{1,3}</span>', "", x)  # loose footnote numbers
    x = re.sub(r'<p\b[^>]*class="(?:oj-)?ti-grseq-1"[^>]*>', "\n" + HEAD, x)
    x = re.sub(r"</(?:p|tr|h\d|div|li|table|caption)>|<table\b[^>]*>|<br\s*/?>|<hr\b[^>]*>", "\n", x)
    x = re.sub(r"</td>", " ", x)
    x = re.sub(r"<[^>]+>", "", x)
    return _join(html.unescape(x).replace("\u00a0", " ").split("\n"))


def _join(raw_lines: list[str]) -> list[str]:
    out: list[str] = []
    for raw in raw_lines:
        head = raw.lstrip().startswith(HEAD)
        line = re.sub(r"\s+", " ", raw.replace(HEAD, "")).strip()
        # tidy what dropped footnote call-outs leave behind: "braking ." / "B )" / "N1. ."
        line = re.sub(r"(?<=[\w)’\"])\s+(?=[.,;:](?:\s|$))", "", line)
        line = re.sub(r"(?<=\w)\s+\)", ")", line)
        line = re.sub(r"\.\s+\.(?=\s|$)", ".", line)
        if not line:
            continue
        if out and not head and (NUM_ONLY.match(out[-1].lstrip(HEAD)) or re.fullmatch(r"[.,;:]", line)):
            out[-1] = f"{out[-1]}{'' if re.fullmatch(r'[.,;:]', line) else ' '}{line}"
        else:
            out.append(HEAD + line if head else line)
    return out


# ---- lines -> scope + metadata ----------------------------------------------------------

SCOPE_HEAD = re.compile(r"^1\.?\s+(?:[A-Z]+\s+AND\s+)?SCOPE\b", re.I)
SUB_OF_1 = re.compile(r"^1\.\d")
TEXT_SCOPE_HEAD = re.compile(r"^1\.?\s+SCOPE\b")  # fallback: upper case only, never a TOC entry
TEXT_NEXT_HEAD = re.compile(r"^(?:[2-9]|1\d)\.?\s+[A-Z]{4,}\b")  # "2. DEFINITIONS", even run on


def scope_section(lines: list[str]) -> str:
    """Body of the regulation's section 1 (Scope), empty when there is none.

    The first match is the regulation's own Scope: tables of contents are not headings, and
    annex scopes (R48 Annex 6 has one) come later. The section ends at the next heading that
    is not a sub-paragraph of section 1 ("2. DEFINITIONS", "2.1. General", ...).
    """
    for i, line in enumerate(lines):
        if line.startswith(HEAD) and SCOPE_HEAD.match(line[1:]):
            body = []
            for nxt in lines[i + 1:]:
                if nxt.startswith(HEAD) and not SUB_OF_1.match(nxt[1:]):
                    break
                body.append(nxt.lstrip(HEAD))
            if _substantive(body):
                return "\n".join(body)
    for i, line in enumerate(lines):  # markup without heading classes (older OJ issues)
        if TEXT_SCOPE_HEAD.match(line.lstrip(HEAD)):
            body = []
            for nxt in lines[i + 1:]:
                if TEXT_NEXT_HEAD.match(nxt.lstrip(HEAD)) or (nxt.startswith(HEAD) and not SUB_OF_1.match(nxt[1:])):
                    break
                body.append(nxt.lstrip(HEAD))
            if _substantive(body):
                return "\n".join(body)
    return ""


def _substantive(body: list[str]) -> bool:
    text = " ".join(body)
    return len(re.findall(r"[A-Za-z]", text)) >= 40 and "....." not in text


def version_line(lines: list[str]) -> str:
    """The "Incorporating all valid text up to:" entries (each names an amendment and its date
    of entry into force; amendment acts say just "Incorporating:"); failing that, the
    "... Date of entry into force" lines near the top (an original text, or an amendment act
    such as "Supplement 18 to the 04 series of amendments – Date of entry into force: ...")."""
    for i, l in enumerate(lines[:60]):
        if re.match(r"incorporating(?: all valid text up to)?\s*:", l, re.I):
            rest = l.split(":", 1)[1].strip()
            found = [rest] if rest else []
            for nxt in lines[i + 1:i + 8]:
                if "entry into force" not in nxt.lower():
                    break
                found.append(nxt)
            return "; ".join(found)
    return "; ".join(l for l in lines[:25] if re.search(r"(?:^|[—–-]\s)Date of entry into force", l))


def parse(lines: list[str], header: str) -> dict:
    """OJ reference/date, version line, Scope, paragraph-1 edits and "republished" flag of
    one OJ act (full text, corrigendum or amendment-only act).

    ``header`` is the OJ masthead text: "16.11.2018 EN Official Journal ... L 290/54" for
    the numbered OJ, or "... L series 2026/746 13.4.2026" for the act-by-act OJ (Oct 2023 on).
    """
    oj_date = oj_ref = ""
    d = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", header)
    if d:
        oj_date = f"{d.group(3)}-{int(d.group(2)):02d}-{int(d.group(1)):02d}"
    numbered = re.search(r"\bL (\d+)/(\d+)\b", header)
    series = re.search(r"\bL series\b.*?\b(\d{4}/\d+)\b", header)
    if numbered and d:
        oj_ref = f"OJ L {numbered.group(1)}, {d.group(0)}, p. {numbered.group(2)}"
    elif series and d:
        oj_ref = f"OJ L, {series.group(1)}, {d.group(0)}"
    plain = [l.lstrip(HEAD) for l in lines]
    return {"oj_ref": oj_ref, "oj_date": oj_date, "version": version_line(plain),
            "scope": _cap(scope_section(lines)), "paragraph_1": paragraph_1_change(lines),
            "republished": bool(REPUBLISHED_RE.search(" ".join(plain[:40])))}


def _cap(scope: str) -> str:
    return scope[:SCOPE_CAP].rsplit(" ", 1)[0] + " [...]" if len(scope) > SCOPE_CAP else scope


# Editing instructions in amendment acts and corrigenda: "Paragraph 1, amend to read ...",
# "Paragraphs 1.1. to 1.3., amend to read", "Insert a new paragraph 1.4., to read",
# "Paragraph 6.1.3., amend to read". Annex paragraphs ("Annex 6, paragraph 1, ...") start
# with "Annex" and so never count as the regulation's own paragraph 1.
INSTRUCTION_RE = re.compile(r"^(?:(?:On )?page \d+,\s*)?(?:(?:Insert|Add|Delete)\s+(?:a\s+)?(?:new\s+)?)?"
                            r"(?:paragraphs?|annex|footnote|the\s+title)\b", re.I)
PARA_1_RE = re.compile(r"^(?:(?:On )?page \d+,\s*)?(?:(?:Insert|Add|Delete)\s+(?:a\s+)?(?:new\s+)?)?"
                       r"paragraphs?\s+(1(?:\.\d+)*)\.?(?=[\s,:;(])", re.I)
EDIT_VERB_RE = re.compile(r"\b(?:amend\w*|read|insert\w*|delet\w*|replac\w*|add\w*)\b", re.I)
QUOTES = "‘’'\"“”"


def paragraph_1_change(lines: list[str]) -> dict:
    """How an amendment act or corrigendum touches the regulation's paragraph 1 (Scope):
    {"change": "replaced", "scope": new text} when paragraph 1 is rewritten as a whole,
    {"change": "amended in part"} when only its sub-paragraphs change (or the new text
    cannot be cut out), else {"change": "none"}. Only meaningful for amendment acts.
    """
    found = []
    for i, line in enumerate(lines):
        m = PARA_1_RE.match(line.lstrip(HEAD))
        if not m or not EDIT_VERB_RE.search(line):
            continue
        if m.group(1) != "1":
            found.append({"change": "amended in part"})
            continue
        # the new paragraph 1 runs up to the next editing instruction
        block = []
        for nxt in lines[i + 1:]:
            text = nxt.lstrip(HEAD)
            if INSTRUCTION_RE.match(text):
                break
            block.append((HEAD if nxt.startswith(HEAD) else "") + text.lstrip(QUOTES))
        scope = scope_section(block)
        if not scope and block:  # no "1. SCOPE" heading in the new text: take it as it stands
            first = re.sub(r"^1\.?\s+(?:SCOPE\b\.?\s*)?", "", block[0].lstrip(HEAD), count=1, flags=re.I)
            scope = "\n".join(x for x in [first] + [b.lstrip(HEAD) for b in block[1:]] if x)
        scope = scope.strip().rstrip(QUOTES).strip()
        found.append({"change": "replaced", "scope": _cap(scope)} if scope else {"change": "amended in part"})
    if any(f["change"] == "amended in part" for f in found):
        return {"change": "amended in part"}  # conservative: the stored Scope is not the whole story
    return found[-1] if found else {"change": "none"}


def xhtml_header(xhtml: str) -> str:
    """Text of the OJ masthead paragraphs (date, OJ number or L-series act number)."""
    parts = re.findall(r'class="oj-hd-(?:date|oj|coll|uniq)"[^>]*>(.*?)</p>', xhtml[:20000], flags=re.S)
    return " ".join(re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", p))).strip() for p in parts)


# ---- build ------------------------------------------------------------------------------

def acts_by_code(rows: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    """({code: every OJ act naming that UN Regulation, newest first, with its "kind"},
    titles that mention a UN Regulation but could not be parsed)."""
    by_code: dict[str, list[dict]] = {}
    unparsed = []
    for row in rows:
        c = classify(row["title"])
        if c:
            by_code.setdefault(c[0], []).append({**row, "kind": c[1]})
        elif UN_MENTION_RE.search(clean_title(row["title"])):
            unparsed.append(row)
    for acts in by_code.values():
        acts.sort(key=lambda r: (r.get("date", ""), r["celex"]), reverse=True)
    return by_code, unparsed


def read_act(celex: str, fetch: Fetcher) -> dict | None:
    """Parsed act from its English XHTML; None when CELLAR has none."""
    xhtml = fetch.get(celex)
    if not xhtml:
        return None
    text = xhtml.decode("utf-8", "replace")
    return parse(xhtml_lines(text), xhtml_header(text))


def build_one(reg, acts: list[dict], fetch: Fetcher) -> dict:
    """Snapshot entry for one regulation from its OJ acts (newest first); see module docstring."""
    if not acts:
        return {"status": "not_in_oj"}
    base = info = None
    tried = []
    for i, act in enumerate(acts):
        if act["kind"] == "amendment" or (act["kind"] == "full" and len(tried) >= MAX_TRIES):
            continue
        got = read_act(act["celex"], fetch)
        if act["kind"] == "full":
            tried.append(act["celex"])
        if got and got["scope"] and (act["kind"] == "full" or got["republished"]):
            base, info = i, got
            break
    if base is None:
        first = tried[0] if tried else acts[0]["celex"]
        return {"status": "no_scope_found", "celex": first, "tried": tried, "url": EURLEX + first}
    act = acts[base]
    entry = {"status": "ok", "celex": act["celex"], "title": clean_title(act["title"]),
             "oj_ref": info["oj_ref"], "oj_date": info["oj_date"] or act.get("date", ""),
             "version": info["version"], "scope": info["scope"], "url": EURLEX + act["celex"]}
    later = []
    for newer in reversed(acts[:base]):  # oldest first, so the last replacement of paragraph 1 wins
        got = read_act(newer["celex"], fetch)
        change = got["paragraph_1"]["change"] if got else "unread"
        if newer["kind"] == "full":  # a newer full text whose Scope could not be cut out
            change = "unread"
        elif newer["kind"] == "corrigendum" and change == "replaced":
            change = "amended in part"  # "for ... read ..." corrections are not whole new texts
        later.append({"celex": newer["celex"], "kind": newer["kind"],
                      "oj_ref": got["oj_ref"] if got else "",
                      "oj_date": (got and got["oj_date"]) or newer.get("date", ""),
                      "version": got["version"] if got else "", "paragraph_1": change,
                      "url": EURLEX + newer["celex"]})
        if change == "replaced":
            entry["scope"] = got["paragraph_1"]["scope"]
            entry["scope_from"] = newer["celex"]
    if later:
        entry["later_oj_acts"] = later
    return entry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated, e.g. R148,R90,R13-H")
    ap.add_argument("--refresh-index", action="store_true", help="re-run the SPARQL title query")
    args = ap.parse_args()
    regs = unece.CATALOGUE
    if args.only:
        want = {"UN " + w.strip().upper().removeprefix("UN").strip() for w in args.only.split(",")}
        regs = [r for r in regs if r.code in want]
        missing = want - {r.code for r in regs}
        if missing:
            sys.exit(f"not in unece.CATALOGUE: {sorted(missing)}")

    fetch = Fetcher()
    rows = fetch.titles(refresh=args.refresh_index)
    by_code, unparsed = acts_by_code(rows)
    print(f"{len(rows)} OJ titles, {sum(map(len, by_code.values()))} name a UN Regulation")
    for row in unparsed:
        print(f"WARNING title names a UN Regulation but was not parsed: {row['celex']} {clean_title(row['title'])[:120]}")
    snap = json.loads(unece.SCOPES.read_text(encoding="utf-8")) if unece.SCOPES.exists() else {}
    entries = snap.get("regulations", {}) if args.only else {}
    for reg in regs:
        entry = build_one(reg, by_code.get(reg.code, []), fetch)
        entries[reg.code] = entry
        print(f"{reg.code:9} {entry['status']:15} {entry.get('celex', '-'):20} "
              f"{entry.get('oj_date', '')} {entry.get('scope', '')[:70]!r}")
        # every act dated after the chosen one, whatever its kind, so coverage can be checked
        for a in entry.get("later_oj_acts", []):
            print(f"{'':9} later {a['kind']:11} {a['celex']:20} {a['oj_date']} paragraph 1: {a['paragraph_1']:15} "
                  f"{a['version'][:70]!r}")
    order = {r.code: i for i, r in enumerate(unece.CATALOGUE)}
    snap = {"source": "EU Official Journal (OJ) copies of UN Regulations, fetched from the EU Publications "
                      "Office CELLAR (http://publications.europa.eu/resource/celex/<CELEX>, English XHTML); "
                      "only the Scope section and citation data are kept",
            "built": date.today().isoformat(), "note": NOTE,
            "regulations": dict(sorted(entries.items(), key=lambda kv: order.get(kv[0], 999)))}
    unece.SCOPES.write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for e in snap["regulations"].values():
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    print(f"wrote {unece.SCOPES}: {counts}, {fetch.requests} network requests, "
          f"{unece.SCOPES.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
