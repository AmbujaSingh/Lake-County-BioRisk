#!/usr/bin/env python3
"""
Scrapes the IDPH "West Nile Virus - Numbers at a Glance" page for the current
year and writes the results to a JSON file that the BioRisk Mapper site can
fetch client-side (same-origin, no API keys, no CORS issues).

Run this on a schedule via GitHub Actions (see update-wnv.yml).
"""

import json
import re
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

YEAR = datetime.now().year
URL = f"https://idph.illinois.gov/wnvpublic/wnvglance.aspx?year={YEAR}"
OUTPUT_PATH = "data/wnv-current.json"

# Cache-busting headers -- the page appeared to be served stale on at least
# one fetch during development, so we explicitly ask for a fresh copy.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LakeCountyBioRiskMapper/1.0; +https://github.com/)",
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
}

# Each pattern captures a single integer (or decimal for median age, in case
# IDPH ever reports a non-whole median) that precedes the given label text.
PATTERNS = {
    "human_cases":        r"([\d,]+)\s*human cases",
    "human_deaths":       r"([\d,]+)\s*human deaths",
    "median_age":         r"([\d.]+)\s*years?\s*-\s*median age of human cases",
    "youngest_case_age":  r"([\d.]+)\s*years?\s*-\s*youngest human case",
    "oldest_case_age":    r"([\d.]+)\s*years?\s*-\s*oldest human case",
    "counties_positive":  r"([\d,]+)\s*counties with positive",
    "positive_birds":     r"([\d,]+)\s*positive birds",
    "positive_batches":   r"([\d,]+)\s*positive mosquito batches",
    "positive_horses":    r"([\d,]+)\s*positive horses",
}

LAST_UPDATED_PATTERN = r"Last Updated[^\d]{0,40}([\d]{1,2}/[\d]{1,2}/[\d]{4})"


def fetch_page(url: str) -> str:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_stats(html: str) -> dict:
    # Strip HTML tags first -- the number and its label often sit in
    # separate elements (e.g. <div>24</div><div>human cases</div>), so
    # leaving tags in place breaks a simple "(\d+)\s*human cases" match.
    # Replace tags with a single space so we don't accidentally glue
    # adjacent words together.
    no_tags = re.sub(r"<[^>]+>", " ", html)
    # Decode the handful of HTML entities likely to appear in this content.
    no_tags = (no_tags
               .replace("&nbsp;", " ")
               .replace("&amp;", "&")
               .replace("&#39;", "'")
               .replace("&quot;", '"'))
    # Collapse whitespace/newlines so patterns match across line breaks.
    flat = re.sub(r"\s+", " ", no_tags)

    stats = {}
    for key, pattern in PATTERNS.items():
        m = re.search(pattern, flat, re.IGNORECASE)
        stats[key] = int(m.group(1).replace(",", "")) if m else None

    m = re.search(LAST_UPDATED_PATTERN, flat, re.IGNORECASE)
    stats["idph_last_updated"] = m.group(1) if m else None

    return stats


def main():
    try:
        html = fetch_page(URL)
    except (URLError, HTTPError) as e:
        print(f"ERROR fetching {URL}: {e}", file=sys.stderr)
        sys.exit(1)

    stats = extract_stats(html)
    stats["year"] = YEAR
    stats["source_url"] = URL
    stats["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Sanity check -- if every field came back None, the page layout probably
    # changed and the regexes need updating. Fail loudly instead of writing
    # a garbage file that silently breaks the site.
    if all(v is None for k, v in stats.items() if k not in ("year", "source_url", "fetched_at")):
        print("ERROR: no stats matched -- IDPH page structure may have changed.", file=sys.stderr)
        print(html[:2000], file=sys.stderr)
        sys.exit(1)

    import os
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"Wrote {OUTPUT_PATH}:")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
