#!/usr/bin/env python3
"""Récupère les sondages du 1er tour de la présidentielle 2027 sur Wikipédia
et écrit site/data/polls.json.

Source : tableau « Liste de sondages sur l'élection présidentielle française
de 2027 » (Wikipédia). Le script lit la page via l'API MediaWiki, parse les
tableaux de premier tour (une ligne = un scénario de candidatures testé) et
produit un fichier « long » : une ligne par (sondage, scénario, candidat).

Usage :  python scripts/update_polls.py [--min-year 2025] [--html fichier.html]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

PAGE = "Liste_de_sondages_sur_l'élection_présidentielle_française_de_2027"
API = "https://fr.wikipedia.org/w/api.php"
PAGE_URL = "https://fr.wikipedia.org/wiki/" + urllib.parse.quote(PAGE)
USER_AGENT = "sondages-presidentielle-2027/1.0 (GitHub Actions; tableau de bord de sondages)"
OUT = Path(__file__).resolve().parent.parent / "site" / "data" / "polls.json"

MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
# Libellés génériques de colonnes (« CandidatRN »…) sans nom propre dans la cellule.
GENERIC = re.compile(r"^(RN|EPR|LR|ENS|PS ?/ ?PP|PS ?/ ?DVG|EELV|LFI|PS|PP)$")
MIN_SCENARIO_COLUMNS = 8  # un tableau de 1er tour a au moins 8 colonnes de candidats


def clean(s: str | None) -> str:
    s = re.sub(r"\[[^\]]*\]", "", s or "")  # renvois de notes [a], [archive]
    return re.sub(r"\s+", " ", s).strip()


def to_num(s: str) -> float:
    return float(s.replace(",", "."))


def end_date(text: str, year: int) -> str | None:
    """« 12-17 novembre » -> 2026-11-17 ; « 30 septembre-2 octobre » -> …-10-02."""
    d = clean(text).lower().replace("1er", "1")
    parts = re.split(r"\s*[-–]\s*", d)
    m = re.search(r"(\d+)\s+([a-zéû]+)\s*$", parts[-1])
    if m:
        day, mon = int(m.group(1)), MONTHS.get(m.group(2))
    else:
        m2 = re.search(r"([a-zéû]+)\s*$", d)
        mon = MONTHS.get(m2.group(1)) if m2 else None
        nums = re.findall(r"\d+", d)
        day = int(nums[-1]) if nums else 1
    if not mon:
        return None
    try:
        return dt.date(year, mon, day).isoformat()
    except ValueError:
        return None


def clean_name(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", s)).strip()


def parse_cell(text: str, column: str) -> dict[str, float]:
    """Retourne {candidat: valeur} pour une cellule de résultat."""
    out: dict[str, float] = {}
    text = clean(text)
    if not text or text in {"—", "-", "–"}:
        return out
    if column == "Autres":
        for m in re.finditer(r"(<?)(\d+(?:,\d+)?)\s*([^\d<][^\d<]*)?", text):
            name = clean_name(m.group(3) or "")
            if name and name[0].isalpha():
                out[name] = 0.5 if m.group(1) else to_num(m.group(2))
        return out
    m = re.match(r"^(<?)(\d+(?:,\d+)?)\s*(.*)$", text)
    if not m:
        return out
    name = clean_name(m.group(3)) if m.group(3) else re.sub(r"^Candidat", "", column).strip()
    if not name or not name[0].isalpha() or GENERIC.match(name):
        return out
    out[name] = 0.5 if m.group(1) else to_num(m.group(2))
    return out


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parse_html(html: str, min_year: int = 2025) -> tuple[list[dict], dict]:
    """Parse la page. Retourne (lignes, statistiques)."""
    soup = BeautifulSoup(html, "lxml")
    rows_out: list[dict] = []
    stats = {"tables": 0, "polls": 0, "scenarios": 0, "skipped_rows": 0}
    counters: dict[str, int] = {}

    for table in soup.select("table.wikitable"):
        heading = table.find_previous(["h2", "h3", "h4"])
        ym = re.search(r"(20\d\d)", clean(heading.get_text()) if heading else "")
        if not ym or int(ym.group(1)) < min_year:
            continue
        year = int(ym.group(1))
        trs = table.find_all("tr")
        if not trs:
            continue
        header = [clean(c.get_text()) for c in trs[0].find_all(["th", "td"], recursive=False)]
        idx = next((i for i, h in enumerate(header) if "chantillon" in h), -1)
        if idx < 0:
            continue
        cols = []
        for h in header[idx + 1:]:
            m = re.match(r"^(.*?)\(([^)]*)\)", h)
            cols.append((m.group(1) if m else h).strip())
        if len(cols) < MIN_SCENARIO_COLUMNS:
            continue
        stats["tables"] += 1

        carry: list[str | None] = [None, None, None]
        left = [0, 0, 0]
        poll_key = None
        scenario = 0
        for tr in trs[1:]:
            cells = tr.find_all(["td", "th"], recursive=False)
            if not cells or not any(clean(c.get_text()) for c in cells):
                continue
            new_poll = left[0] == 0  # pas de cellule « institut » reportée => nouveau sondage
            meta: list[str | None] = []
            ci = 0
            for k in range(3):
                if left[k] > 0:
                    meta.append(carry[k])
                    left[k] -= 1
                else:
                    if ci >= len(cells):
                        meta.append(None)
                        continue
                    c = cells[ci]
                    ci += 1
                    txt = clean(c.get_text())
                    meta.append(txt)
                    span = int(re.sub(r"\D", "", c.get("rowspan", "1")) or 1)
                    if span > 1:
                        carry[k] = txt
                        left[k] = span - 1
            rest = [clean(c.get_text()) for c in cells[ci:]]
            if not rest:
                continue
            if len(rest) == len(cols) - 1 and cols[-1] == "Autres":
                rest.append("")  # cellule « Autres » absente (fusionnée dans le tableau source)
            if len(rest) != len(cols):
                stats["skipped_rows"] += 1  # mise en forme irrégulière : on préfère ignorer
                continue
            pollster, date_txt, sample_txt = meta
            iso = end_date(date_txt or "", year)
            if not pollster or not iso:
                stats["skipped_rows"] += 1
                continue
            pollster = re.sub(r"^Opinionway$", "OpinionWay", pollster)
            sample = int(re.sub(r"\D", "", sample_txt or "") or 0) or None

            if new_poll or poll_key is None:
                base = f"{iso}-{slug(pollster)}"
                counters[base] = counters.get(base, 0) + 1
                poll_key = f"{base}-{counters[base]}"
                scenario = 0
                stats["polls"] += 1
            scenario += 1
            stats["scenarios"] += 1
            values: dict[str, float] = {}
            for col, cell in zip(cols, rest):
                values.update(parse_cell(cell, col))
            for name, v in values.items():
                rows_out.append({
                    "poll_id": poll_key, "scenario": scenario, "pollster": pollster,
                    "date": iso, "sample": sample, "candidate": name, "value": v,
                })
    return rows_out, stats


def fetch_html() -> str:
    params = urllib.parse.urlencode({
        "action": "parse", "page": PAGE, "prop": "text", "format": "json",
        "formatversion": "2", "redirects": "1",
    })
    req = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)
    return payload["parse"]["text"]


def write_json(rows: list[dict], stats: dict, path: Path) -> None:
    doc_head = {
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "source": PAGE_URL,
        "polls": stats["polls"],
        "scenarios": stats["scenarios"],
    }
    lines = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows]
    text = json.dumps(doc_head, ensure_ascii=False)[:-1] + ',"rows":[\n' + ",\n".join(lines) + "\n]}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rows_signature(rows: list[dict]) -> str:
    return json.dumps(rows, sort_keys=True, ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-year", type=int, default=2025)
    ap.add_argument("--html", help="fichier HTML local (tests) au lieu de l'API")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--min-polls", type=int, default=40,
                    help="garde-fou : en dessous, on n'écrase pas le fichier existant")
    args = ap.parse_args()

    html = Path(args.html).read_text(encoding="utf-8") if args.html else fetch_html()
    rows, stats = parse_html(html, args.min_year)
    print(f"Tableaux lus : {stats['tables']} · sondages : {stats['polls']} · "
          f"scénarios : {stats['scenarios']} · lignes ignorées : {stats['skipped_rows']}")

    if stats["polls"] < args.min_polls:
        print(f"ERREUR : seulement {stats['polls']} sondages (minimum {args.min_polls}). "
              "La structure de la page a peut-être changé ; fichier existant conservé.",
              file=sys.stderr)
        return 1

    out = Path(args.out)
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))["rows"]
            if rows_signature(old) == rows_signature(rows):
                print("Aucun changement dans les sondages ; fichier inchangé.")
                return 0
        except (ValueError, KeyError):
            pass
    write_json(rows, stats, out)
    print(f"Écrit : {out} ({len(rows)} lignes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
