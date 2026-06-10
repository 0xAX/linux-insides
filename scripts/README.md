# Scripts used to maintain linux-insides

This directory provides a set of helper scripts for maintaining and building this repository.

| Script                                             | What it does                                                                           |
| -------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [`get_all_links.py`](get_all_links.py)             | Crawls every `.md` file and reports which external links are alive or dead             |
| [`check_code_snippets.py`](check_code_snippets.py) | Verifies that kernel source snippets in the book still match the real source on GitHub |
| [`latex.sh`](latex.sh)                             | Converts the whole book into a single LaTeX-typeset PDF                                |

## `get_all_links.py` - link checker

This script walks the given directory tree, extracts every link from the Markdown files, and checks each external URL with a real network request. Live links are printed to **stdout**; dead or unreachable links go to **stderr**, so you can split them apart.

It requires Python 3 and the [`markdown`](https://pypi.org/project/Markdown/) package. Before using this script, you have to install it:

```bash
pip install markdown
```

Usage:

```bash
python ./scripts/get_all_links.py .
```

## `check_code_snippets.py` - snippet validator

Keeps the code in the book honest. Each snippet is annotated with an HTML comment pointing at a GitHub raw URL and a line range, for example:

```
<!-- https://raw.githubusercontent.com/torvalds/linux/<commit>/path/to/file.c#L10-L20 -->
```

The script fetches that range from GitHub and compares it against the code block in the book. If they have drifted apart, it prints both versions and exits with a non-zero status - handy for CI.

It requires Python 3 and the [`requests`](https://pypi.org/project/requests/) package. To install this package, use the following command:

```bash
pip install requests
```

Usage:

```
# Check the whole repository
python3 check_code_snippets.py ../

# Check a single chapter
python3 check_code_snippets.py ../Initialization
```

## `latex.sh` - PDF builder

Converts the Markdown of each chapter directory into LaTeX with `pandoc`, compiles each one with `pdflatex`, and stitches everything into a single `LinuxKernelInsides.pdf` with `pdfunite`.

> You only need this if you want to **build the PDF yourself**. To just read the book, grab the pre-built [`LinuxKernelInsides.pdf`](LinuxKernelInsides.pdf).

It requires the following utils and packages:

- [TeX Live](https://www.tug.org/texlive/)
- [Pandoc](https://pandoc.org/)

Usage:

```bash
./latex.sh
```
