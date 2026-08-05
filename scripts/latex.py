#!/usr/bin/env python3
"""
A script for converting markdown files in each of the subdirectories into a
unified PDF typeset in LaTeX. Requires TeX Live, pandoc templates and pdfunite.
Not necessary if you just want to read the PDF, only if you're compiling it
yourself.
"""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = Path("build")


def pandoc(sources, tex):
    subprocess.run(["pandoc", *map(str, sources), "-o", tex, "--template", "default"], check=True)


shutil.rmtree(BUILD, ignore_errors=True)
BUILD.mkdir()

for chapter in sorted(ROOT.iterdir()):
    if not (chapter / "README.md").is_file() or not any(chapter.glob("linux-*.md")):
        continue

    print(f"Converting {chapter.name} . . .")
    pandoc([chapter / "README.md", *sorted(chapter.glob("linux-*.md"))], f"{BUILD}/{chapter.name}.tex")

pandoc([ROOT / md for md in ("README.md", "SUMMARY.md", "CONTRIBUTING.md", "contributors.md")],
       f"{BUILD}/Preface.tex")

for tex in sorted(BUILD.glob("*.tex")):
    subprocess.run(["pdflatex", "-interaction=nonstopmode", tex.name], cwd=BUILD, check=False)

subprocess.run(["pdfunite", *map(str, sorted(BUILD.glob("*.pdf"))), "LinuxKernelInsides.pdf"], check=True)
