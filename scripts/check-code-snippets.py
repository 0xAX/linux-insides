import os
import re
import sys
from typing import Optional, Tuple

import requests

def split_url_and_range(url: str) -> Tuple[str, Optional[int], Optional[int]]:
    base, frag = url.split("#", 1)
    m = re.match(r'L(\d+)(?:-L?(\d+))?$', frag)
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else None
    return base, start, end

def fetch_raw(source: str) -> str:
    r = requests.get(source)
    return r.text

def main():
    in_code = False
    code = ''
    content = ''
    start_line = 0
    end_line = 0
    md_files = []
    
    for root, dirs, files in os.walk(sys.argv[1]):
        for name in files:
            if name.endswith('.md'):
                md_files.append(os.path.join(root, name))
            else:
                continue

    for md in md_files:
        print("Checking code in the", md)

        with open(md, "r", encoding="utf-8") as f:
            md = f.read()

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
                (uri, start, end) = split_url_and_range(line.split(' ')[1])
                content = "\n".join(fetch_raw(uri).splitlines()[start-1:end]).rstrip()
                continue

            if code != '':
                if code.rstrip() != content:
                    print("Error in", sys.argv[1])
                    print("Code in book:")
                    print(code)
                    print("Code from github:")
                    print(content)
                    exit(1)

                code = ''
                content = ''
                continue

if __name__ == "__main__":
    main()
