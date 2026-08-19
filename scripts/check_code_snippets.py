#!/usr/bin/env python3
"""
A script that takes the lines of the Linux kernel source code from the comments
in the markdown files that are attached to the code and checks their validity.
"""
import os
import re
import sys
import time
from typing import Dict, Optional, Tuple

import requests

# directories that hold no book content, but may hold example snippet
# annotations that must not be fetched
exclude_dirs = [".github", "scripts"]

# Every snippet fetches the whole source file, and a single file usually backs
# many snippets, so the sources are cached to keep the request count down.
cache: Dict[str, str] = {}
session = requests.Session()

MAX_RETRIES = 5
MAX_BACKOFF = 60.0

def __split_url_and_range__(url: str) -> Tuple[str, Optional[int], Optional[int]]:
    base, frag = url.split("#", 1)
    m = re.match(r'L(\d+)(?:-L?(\d+))?$', frag)
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else None
    return base, start, end

def __split_ref__(rest: str) -> Tuple[str, str]:
    parts = rest.split("/")

    if len(parts) > 3 and parts[0] == "refs" and parts[1] in ("heads", "tags"):
        return parts[2], "/".join(parts[3:])

    return parts[0], "/".join(parts[1:])

def __api_url__(source: str) -> Optional[str]:
    """
    Rewrite a github url to the contents API, so that the request is counted
    against the (much higher) authenticated rate limit of the given token.
    """
    m = re.match(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/(.+)$", source)

    if not m:
        m = re.match(r"https://github\.com/([^/]+)/([^/]+)/raw/(.+)$", source)

    if not m:
        return None

    owner, repo, rest = m.groups()
    (ref, path) = __split_ref__(rest)

    if not path:
        return None

    return f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"

def __get__(source: str) -> str:
    headers = {}
    token = os.environ.get("GITHUB_TOKEN")
    url = source

    if token:
        api_url = __api_url__(source)

        if api_url:
            url = api_url
            headers["Accept"] = "application/vnd.github.raw"
            headers["Authorization"] = f"Bearer {token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"

    backoff = 2.0
    response = None

    for attempt in range(MAX_RETRIES):
        response = session.get(url, timeout=30.0, headers=headers)

        if response.status_code == 200:
            return response.text

        # github throttles anonymous requests, especially from shared CI
        # addresses, so back off and try again instead of comparing the book
        # against an error page
        if response.status_code not in (403, 429) and response.status_code < 500:
            break

        if attempt == MAX_RETRIES - 1:
            break

        delay = min(float(response.headers.get("Retry-After", backoff)), MAX_BACKOFF)
        print(f"{response.status_code} for {url}, retrying in {delay:.0f}s",
              file=sys.stderr)
        time.sleep(delay)
        backoff *= 2

    print(f"Failed to fetch {url}: {response.status_code} {response.text[:200]}",
          file=sys.stderr)
    sys.exit(1)

def __fetch_raw__(source: str) -> str:
    if source not in cache:
        cache[source] = __get__(source)

    return cache[source]

def __compare__(code: str, content: str, path: str):
    if code.rstrip() != content:
        print("Error in", path)
        print("Code in book:")
        print(code)
        print("Code from github:")
        print(content)
        sys.exit(1)

def __handle_md__(md: str, path: str):
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
            __compare__(code, content, path)
            code = ''
            content = ''
            continue

    # A snippet that ends the file has no trailing line to trigger the
    # comparison above, so flush it here.
    if code != '':
        __compare__(code, content, path)

def __excluded__(md_path: str, root: str) -> bool:
    rel = os.path.relpath(md_path, root)
    return any(rel == d or rel.startswith(d + os.sep) for d in exclude_dirs)

def __main__():
    path = ''
    md_files = []

    if len(sys.argv) == 1:
        path = '.'
    else:
        path = sys.argv[1]

    for root, _dirs, files in os.walk(path):
        for name in files:
            if name.endswith('.md'):
                md_files.append(os.path.join(root, name))
            else:
                continue

    for md_path in md_files:
        if __excluded__(md_path, path):
            continue

        print("Checking code in the", md_path)

        with open(md_path, "r", encoding="utf-8") as f:
            md = f.read()

        __handle_md__(md, md_path)

if __name__ == "__main__":
    __main__()
