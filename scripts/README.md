# Scripts used to maintain linux-insides

This directory provides a set of helper scripts for maintaining and building this repository.

| Script                                             | What it does                                                                           |
| -------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [`check_code_snippets.py`](check_code_snippets.py) | Verifies that kernel source snippets in the book still match the real source on GitHub |
| [`latex.py`](latex.py)                             | Converts the whole book into a single LaTeX-typeset PDF                                |

External links are not checked by a script from this directory. The [check links](../.github/workflows/check-links.yaml) workflow does it with [lychee](https://github.com/lycheeverse/lychee), configured in [`lychee.toml`](../lychee.toml).

## `check_code_snippets.py` - snippet validator

Keeps the code in the book honest. Each snippet is annotated with an HTML comment pointing at a GitHub raw URL and a line range, for example:

```
<!-- https://raw.githubusercontent.com/torvalds/linux/<commit>/path/to/file.c#L10-L20 -->
```

The script fetches that range from GitHub and compares it against the code block in the book. If they have drifted apart, it prints both versions and exits with a non-zero status - handy for CI.

Each source file is fetched only once per run and the result is reused by every snippet that refers to it. Requests that GitHub throttles are retried with a growing delay. If `GITHUB_TOKEN` is set, the sources are read through the GitHub contents API instead of the raw endpoint, which counts against the authenticated rate limit and makes `429 Too Many Requests` far less likely:

```bash
GITHUB_TOKEN=$(gh auth token) uv run --project scripts ./scripts/check_code_snippets.py .
```

Its dependencies are declared in [`pyproject.toml`](pyproject.toml) and pinned in [`uv.lock`](uv.lock), so [uv](https://docs.astral.sh/uv/) provides both the interpreter and the packages. Nothing has to be installed by hand.

Usage, from the repository root:

```bash
# Check the whole repository
uv run --project scripts ./scripts/check_code_snippets.py .

# Check a single chapter
uv run --project scripts ./scripts/check_code_snippets.py ./Initialization
```

From inside this directory the `--project` flag can be dropped:

```bash
uv run ./check_code_snippets.py ../Initialization
```

If you prefer a plain virtual environment, `uv sync` creates one in `scripts/.venv` and the script can be run directly after activating it.

## `latex.py` - PDF builder

Converts the Markdown of each chapter directory into LaTeX with `pandoc`, compiles each one with `pdflatex`, and stitches everything into a single `LinuxKernelInsides.pdf` with `pdfunite`. The intermediate files are left in a `build` directory, which is where you find the `pdflatex` logs if a chapter does not typeset.

> You only need this if you want to **build the PDF yourself**. To just read the book, grab the pre-built [`LinuxKernelInsides.pdf`](LinuxKernelInsides.pdf).

It uses only the standard library, so plain Python 3 is enough - no `uv` and no packages to install. It requires the following utils and packages:

- [TeX Live](https://www.tug.org/texlive/)
- [Pandoc](https://pandoc.org/)
- `pdfunite` from [poppler-utils](https://poppler.freedesktop.org/)

Usage, from this directory:

```bash
./latex.py
```

The `build` directory and the resulting PDF are written to the current working directory, so run it from wherever you want them.
