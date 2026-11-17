#!/usr/bin/env python3
"""Write the paper list into the site's pages.

The papers are kept in two files next to this script:

  pubs.json     the papers, grouped by year: title, url, authors, venue, note, links
  authors.json  co-author name -> homepage; every paper that lists the name links to it

After editing either file, run (from any folder):

  python3 _pubs/build.py

It rewrites
  index.html            the lines between the "BEGIN paper list" and "END paper list" comments
  beta-next/index.html  the same lines, if that page exists (the working copy of the next main page)
  beta/index.html       the `const PUBS = [...]` line, if that page exists

so the list is plain HTML in the main page and shows without scripts. The folder name
starts with an underscore, so GitHub Pages does not publish it.

How a paper is written in pubs.json:
  - authors: names separated by ", "; "<b>Wonjun Kang</b>" for this site's owner;
    "*" after a name for equal contribution, "&dagger;" for equal advising.
  - note: a workshop's name ending in "Workshop", or a track first ("Oral, Top ~1%").
  - inside a year: newest conference first, main-track papers before workshop papers.
A name in authors.json must be spelled exactly as in the papers. Add a homepage only
after checking that it belongs to that person.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

ME = "<b>Wonjun Kang</b>"
LABELS = {
    "Preprints": "Preprints",
    "Pubs-2026": "2026",
    "Pubs-2025": "2025",
    "Pubs-2024-and-Earlier": "2024 and Earlier",
}
# the chip carries the venue and the kind of paper ("NeurIPS 2026 Workshop", "ICML 2025 Oral");
# what is left of the note (the workshop's name, "Top ~1%") follows it in gray
WORKSHOP = re.compile(r"\s*Workshop\Z")
TRACKS = ("Oral", "Spotlight", "Main", "Findings")
VENUE_NAMES = {"Arxiv": "arXiv"}
# an author is a name plus optional marks (*, †)
AUTHOR = re.compile(r"(.*?)((?:\*|&dagger;|†)*)", re.S)

BEGIN = "<!-- BEGIN paper list"
END = "<!-- END paper list -->"
INDENT = " " * 10


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def role(p):
    """first: first or co-first author; last: last or co-advising author; co: the rest."""
    a = p["authors"]
    if a.startswith(ME) or ME + "*" in a:
        return "first"
    if a.strip().endswith(ME) or ME + "&dagger;" in a or ME + "†" in a:
        return "last"
    return "co"


def venue_parts(p):
    venue = VENUE_NAMES.get(p["venue"], p["venue"])
    note = p.get("note", "")
    if WORKSHOP.search(note):
        return f"{venue} Workshop", WORKSHOP.sub("", note)
    head, _, rest = note.partition(", ")
    if head in TRACKS:
        return f"{venue} {head}", rest
    return venue, note


def link_authors(authors, links, seen):
    out = []
    for part in authors.split(", "):
        name, marks = AUTHOR.fullmatch(part).groups()
        if name != ME:
            seen.add(name)
        url = links.get(name)
        out.append(f'<a href="{esc(url)}">{name}</a>{marks}' if url else part)
    return ", ".join(out)


def render(groups, links, seen):
    lines = []
    for g in groups:
        if not g["entries"]:
            continue
        label = esc(LABELS.get(g["id"], g["id"]))
        lines.append(f'{INDENT}<section class="grp" aria-label="{label}">')
        lines.append(f'{INDENT}  <h3 class="grp-h">{label}<span class="gc">{len(g["entries"])}</span></h3>')
        lines.append(f'{INDENT}  <ul class="pubs">')
        for p in g["entries"]:
            chip, note = venue_parts(p)
            meta = f'<span class="venue">{esc(chip)}</span>'
            if note:
                meta += f'<span class="p-note">{esc(note)}</span>'
            for link in p.get("links", []):
                code = link["type"] == "code"
                icon = "i-code" if code else "i-globe"
                text = "Code" if code else "Project Page"
                meta += f'<a class="plink" href="{esc(link["url"])}"><svg class="icon"><use href="#{icon}"/></svg>{text}</a>'
            lines.append(f'{INDENT}    <li class="pub" data-role="{role(p)}">')
            lines.append(f'{INDENT}      <a class="p-title" href="{esc(p["url"])}">{esc(p["title"])}</a>')
            lines.append(f'{INDENT}      <p class="p-authors">{link_authors(p["authors"], links, seen)}</p>')
            lines.append(f'{INDENT}      <p class="item-m">{meta}</p>')
            lines.append(f'{INDENT}    </li>')
        lines.append(f'{INDENT}  </ul>')
        lines.append(f'{INDENT}</section>')
    return lines


def save(path, old, new):
    if new != old:
        path.write_bytes(new.encode("utf-8"))
    print(f'{path.relative_to(ROOT)}: {"updated" if new != old else "no change"}')


def write_main(path, block):
    old = path.read_bytes().decode("utf-8")
    lines = old.split("\n")
    begin = [i for i, line in enumerate(lines) if BEGIN in line]
    end = [i for i, line in enumerate(lines) if END in line]
    if len(begin) != 1 or len(end) != 1 or begin[0] >= end[0]:
        sys.exit(f'{path.relative_to(ROOT)}: expected one "{BEGIN} ..." comment followed by one "{END}" comment')
    save(path, old, "\n".join(lines[: begin[0] + 1] + block + lines[end[0]:]))


def write_beta(path, groups):
    if not path.exists():
        return
    old = path.read_bytes().decode("utf-8")
    line = re.compile(r"^([ \t]*)const PUBS = .*;$", re.M)
    if len(line.findall(old)) != 1:
        sys.exit(f"{path.relative_to(ROOT)}: expected exactly one `const PUBS = [...];` line")
    data = json.dumps(groups, ensure_ascii=False)
    save(path, old, line.sub(lambda m: f"{m.group(1)}const PUBS = {data};", old))


def main():
    groups = json.loads((HERE / "pubs.json").read_text(encoding="utf-8"))
    links = json.loads((HERE / "authors.json").read_text(encoding="utf-8"))

    seen = set()
    block = render(groups, links, seen)
    papers = [p for g in groups for p in g["entries"]]
    roles = [role(p) for p in papers]
    linked = sum(line.count("<a href=") for line in block if 'class="p-authors"' in line)
    print(f'{len(papers)} papers (first author {roles.count("first")}, last author {roles.count("last")}), {linked} author links')

    unknown = sorted(set(links) - seen)
    if unknown:
        print(f'warning: in authors.json but in no paper (check the spelling): {", ".join(unknown)}')
    missing = sorted(seen - set(links))
    if missing:
        print(f'no homepage on file for {len(missing)} co-authors: {", ".join(missing)}')

    write_main(ROOT / "index.html", block)
    # the working copy of the next main page has the same two comments and the same markup for a paper
    nxt = ROOT / "beta-next" / "index.html"
    if nxt.exists():
        write_main(nxt, block)
    write_beta(ROOT / "beta" / "index.html", groups)


if __name__ == "__main__":
    main()
