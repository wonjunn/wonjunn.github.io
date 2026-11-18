#!/usr/bin/env python3
"""Write cv.pdf, the copy of the CV that the homepage links to.

Usage (from the repo root; needs latexmk and LuaLaTeX):

    python3 -I _cv/build.py

The CV itself is cv-overleaf/cv.tex. That folder is the Overleaf project, a git
repository of its own, and this repository ignores it, so nothing in it is ever
published. This script builds cv.tex once more with \\publiccopy defined, which
leaves the phone number out of the heading, and puts the result at the repo root
as cv.pdf. The page links to it as "cv.pdf".

Run it after the CV changes, then commit cv.pdf: the homepage does not follow the
CV by itself. A second run with nothing changed leaves cv.pdf byte for byte the
same (the PDF's dates are taken from cv.tex, not from the clock).
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "cv-overleaf"
OUT = ROOT / "cv.pdf"
JOB = "cv_public"
SWITCH = r"\ifdefined\publiccopy"


def main():
    tex = SRC / "cv.tex"
    if not tex.exists():
        sys.exit(f"{tex.relative_to(ROOT)} not found")
    if SWITCH not in tex.read_text(encoding="utf-8"):
        sys.exit(f"cv.tex has no {SWITCH}: the phone number would be published. Nothing written.")

    # always the same folder, outside both repositories: the PDF's ID depends on the path
    build = Path(tempfile.gettempdir()) / "wonjunn-cv-public"
    build.mkdir(exist_ok=True)
    env = dict(os.environ, SOURCE_DATE_EPOCH=str(int(tex.stat().st_mtime)), FORCE_SOURCE_DATE="1")
    cmd = ["latexmk", "-g", "-interaction=nonstopmode", "-halt-on-error", f"-jobname={JOB}",
           f"-outdir={build}", r"-usepretex=\def\publiccopy{1}", "cv.tex"]
    run = subprocess.run(cmd, cwd=SRC, env=env, capture_output=True, text=True)
    pdf = build / f"{JOB}.pdf"
    if run.returncode or not pdf.exists():
        print((run.stdout + run.stderr)[-2000:])
        sys.exit("the CV did not build; cv.pdf is unchanged")

    new = pdf.read_bytes()
    old = OUT.read_bytes() if OUT.exists() else None
    if new != old:
        OUT.write_bytes(new)
    print(f'cv.pdf: {"updated" if new != old else "no change"}')


if __name__ == "__main__":
    main()
