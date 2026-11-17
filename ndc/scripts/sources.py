"""
National Dental Commission (NDC, formerly the Dental Council of India) — the
single source of truth for paths, URLs, GCS and BQ names.

Source: dciindia.gov.in "College Search" for BDS (CourseId=1): every dental
college with state, year of establishment, type and the year's permitted BDS
seats; each row's "View College Details" opens the college's own page
(address, hospital, administering body, website, course essentiality letters,
university affiliations, seats by course x speciality x year, hostels, dental
chairs, built area).

The list is one ASP.NET page; a details link is a postback that redirects to
SearchCollegeDetails.aspx?Id=<opaque id>. fetch.py saves the list page and
every details page, as served, into raw/<YYYY-MM-DD>/.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

LIST_URL = "https://dciindia.gov.in/CollegeSearch.aspx?ColName=&CourseId=1&StateId=0"
DETAILS_URL = "https://dciindia.gov.in/SearchCollegeDetails.aspx?Id={id}"
# one request a second: a government site, ~660 requests a fetch
PAUSE_S = 1.0

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "ndc"
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"


def latest_raw() -> Path:
    days = sorted(p for p in RAW.glob("20*") if p.is_dir())
    if not days:
        raise SystemExit("no raw fetch: run scripts/fetch.py")
    return days[-1]
