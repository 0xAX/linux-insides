"""
A script that takes the lines of the Linux kernel source code from the comments
in the markdown files that are attached to the code and checks their validity.
"""
import os
import re
import sys
from typing import Optional, Tuple

import requests

exclude_dirs = ["./.github"]

def __split_url_and_range__(url: str) -> Tuple[str, Optional[int], Optional[int]]:
    base, frag = url.split("#", 1)
    m = re.match(r'L(\d+)(?:-L?(\d+))?$', frag)
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else None
    return base, start, end

def __fetch_raw__(source: str) -> str:
    r = requests.get(source, timeout=5.0)
    return r.text

def __handle_md__(md: str):
    in_code = False
    code = ''
    content = ''

    md_lines = md.splitlines()

    for line in md_lines:
        if in_code:
            if re.search("^```[a-zA-Z].*", line):
                continue

            if re.search("^```$", line):
                in_code = False
                continue

            code += line + '\n'
            continue

        if line.startswith("<!--"):
            in_code = True
            (uri, start, end) = __split_url_and_range__(line.split(' ')[1])
            content = "\n".join(__fetch_raw__(uri).splitlines()[start-1:end]).rstrip()
            continue

        if code != '':
            if code.rstrip() != content:
                print("Error in", sys.argv[1])
                print("Code in book:")
                print(code)
                print("Code from github:")
                print(content)
                sys.exit(1)

            code = ''
            content = ''
            continue

def __main__():
    md_files = []

    for root, _dirs, files in os.walk(sys.argv[1]):
        for name in files:
            if name.endswith('.md'):
                md_files.append(os.path.join(root, name))
            else:
                continue

    for md in md_files:
        print("Checking code in the", md)
        if os.path.dirname(md) in exclude_dirs:
            continue

        with open(md, "r", encoding="utf-8") as f:
            md = f.read()

        __handle_md__(md)

if __name__ == "__main__":
    __main__()
