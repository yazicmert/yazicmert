"""Replace the arXiv section of README.md with the latest astrodynamics papers.

Only the text between <!-- ARXIV:START --> and <!-- ARXIV:END --> is touched.
If the arXiv API is unreachable, README.md is left unchanged.
"""

import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

README = sys.argv[1] if len(sys.argv) > 1 else "README.md"
MAX_RESULTS = 3
QUERY = ('cat:astro-ph.EP AND (abs:trajectory OR abs:"orbit determination" '
         'OR abs:"near-Earth asteroid" OR abs:lunar)')

ATOM = "{http://www.w3.org/2005/Atom}"
START, END = "<!-- ARXIV:START -->", "<!-- ARXIV:END -->"


def fetch():
    params = urllib.parse.urlencode({
        "search_query": QUERY, "sortBy": "submittedDate",
        "sortOrder": "descending", "max_results": MAX_RESULTS,
    })
    url = f"https://export.arxiv.org/api/query?{params}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def parse(xml_bytes):
    root = ET.fromstring(xml_bytes)
    papers = []
    for entry in root.iter(f"{ATOM}entry"):
        title = " ".join(entry.findtext(f"{ATOM}title", "").split())
        link = entry.findtext(f"{ATOM}id", "").strip()
        date = entry.findtext(f"{ATOM}published", "")[:10]
        authors = [a.findtext(f"{ATOM}name", "") for a in entry.findall(f"{ATOM}author")]
        if len(authors) > 2:
            authors = authors[:2] + ["et al."]
        papers.append((title, link, date, ", ".join(authors)))
    return papers


def render(papers):
    lines = [f"- 📄 [{t.replace('[', '(').replace(']', ')')}]({l}) — *{a}* ({d})"
             for t, l, d, a in papers]
    return "\n".join(lines)


def main():
    try:
        papers = parse(fetch())
    except Exception as exc:
        print(f"arXiv fetch failed ({exc}); README unchanged", file=sys.stderr)
        return
    if not papers:
        print("no papers returned; README unchanged", file=sys.stderr)
        return
    with open(README, encoding="utf-8") as f:
        text = f.read()
    new = re.sub(f"{re.escape(START)}.*?{re.escape(END)}",
                 f"{START}\n{render(papers)}\n{END}", text, flags=re.S)
    with open(README, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"updated {len(papers)} papers")


if __name__ == "__main__":
    main()
