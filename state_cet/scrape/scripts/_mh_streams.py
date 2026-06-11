"""
Shared infrastructure for Maharashtra State CET Cell scrapers.

The CET Cell runs ~10 parallel CAPs (Engineering, Pharmacy, Agriculture, etc.)
each on its own subdomain (fe2025/ph2025/agri2025/...). For the three portals
that use the classic ASP.NET wrapper (fe2025, ph2025, bdesigncap2025), every
PDF is reachable as `https://<portal>/ViewPublicDocument.aspx?MenuId=<id>` —
the actual PDF binary is base64-encoded inside a JS string in the HTML.

This module:
  - lists the MenuId → PDF mappings per stream
  - exposes the base64 wrapper-decoder
  - documents which streams use SPAs (need Chrome MCP) instead

Streams covered by ASP.NET wrapper (this module fully):
  - engineering (fe2025.mahacet.org)
  - pharmacy    (ph2025.mahacet.org)
  - bdesign     (bdesigncap2025.mahacet.org)

Streams using SPAs (separate fetch path):
  - agriculture (agri2025.mahacet.org)
  - architecture(arch2025.mahacet.org.in)
  - llb5        (llb5cap25.mahacet.org)
  - bhmct       (under cetcell.mahacet.org with no dedicated subdomain)

PG / lateral streams (out of scope for JNV-12 cohort):
  - mba/mca/llb3/bed/dse — postgraduate or diploma-holder lateral entry
"""
from __future__ import annotations
import base64
import re
import urllib.request
from pathlib import Path

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) "
    "Gecko/20100101 Firefox/128.0"
)

# ---- Stream → portal subdomain ----
PORTALS = {
    "engineering": "fe2025.mahacet.org",
    "pharmacy":    "ph2025.mahacet.org",
    "bdesign":     "bdesigncap2025.mahacet.org",
}


# ---- Stream → list of (filename, MenuId, description) for downloads ----
# MenuIds are extracted from each portal's homepage HTML (see _mh_streams scrap).
DOWNLOADS = {
    "engineering": [
        # CAP I
        ("MH_CAP1_state_quota_2025.pdf", 2449, "CAP Round I — MH state quota cutoff"),
        ("MH_CAP1_all_india_2025.pdf",   2450, "CAP Round I — All India quota cutoff"),
        ("MH_seat_matrix_2025.pdf",      2441, "Seat matrix"),
        # CAP II
        ("MH_CAP2_state_quota_2025.pdf", 3475, "CAP Round II — MH state quota cutoff"),
        ("MH_CAP2_all_india_2025.pdf",   3476, "CAP Round II — All India quota cutoff"),
        # CAP III
        ("MH_CAP3_state_quota_2025.pdf", 3483, "CAP Round III — MH state quota cutoff"),
        ("MH_CAP3_all_india_2025.pdf",   3484, "CAP Round III — All India quota cutoff"),
        # CAP IV (FINAL main round, admissions closed for 2025-26)
        ("MH_CAP4_state_quota_2025.pdf", 9822, "CAP Round IV (FINAL) — MH state quota cutoff"),
        ("MH_CAP4_all_india_2025.pdf",   9823, "CAP Round IV (FINAL) — All India quota cutoff"),
    ],
    "pharmacy": [
        # CAP I
        ("MH_pharm_CAP1_mh_2025.pdf",  1272, "CAP Round I — MH state quota cutoff"),
        ("MH_pharm_CAP1_ai_2025.pdf",  1273, "CAP Round I — All India quota cutoff"),
        ("MH_pharm_seat_matrix_2025.pdf", 1368, "Seat matrix CAP-I"),
        # CAP II
        ("MH_pharm_CAP2_mh_2025.pdf",  1281, "CAP Round II — MH state quota cutoff"),
        ("MH_pharm_CAP2_ai_2025.pdf",  1282, "CAP Round II — All India quota cutoff"),
        # CAP III
        ("MH_pharm_CAP3_mh_2025.pdf",  1288, "CAP Round III — MH state quota cutoff"),
        ("MH_pharm_CAP3_ai_2025.pdf",  1289, "CAP Round III — All India quota cutoff"),
        # CAP IV (FINAL main round)
        ("MH_pharm_CAP4_mh_2025.pdf",  1747, "CAP Round IV (FINAL) — MH state quota cutoff"),
        ("MH_pharm_CAP4_ai_2025.pdf",  1748, "CAP Round IV (FINAL) — All India quota cutoff"),
    ],
    "bdesign": [
        # MenuIds confirmed from bdesigncap2025.mahacet.org HTML (different document than fe2025
        # despite some shared ID numbers — each portal has its own MenuId namespace).
        ("MH_bdesign_seat_matrix_2025.pdf", 1343, "Seat matrix CAP-I"),
        ("MH_bdesign_CAP2_mh_2025.pdf",     3475, "CAP Round II — MH cutoff"),
        ("MH_bdesign_CAP2_ai_2025.pdf",     3476, "CAP Round II — AI cutoff"),
        ("MH_bdesign_CAP3_mh_2025.pdf",     3483, "CAP Round III — MH cutoff"),
        ("MH_bdesign_CAP4_mh_2025.pdf",     8767, "CAP Round IV — MH cutoff"),
        # Note: B.Design's CAP-I cutoff link wasn't on the homepage menu we scraped.
        # Will need a follow-up portal probe if needed.
    ],
}

# Subfolder under source/MH/ for each stream
SOURCE_SUBDIR = {
    "engineering":  "engineering",
    "pharmacy":     "pharmacy",
    "bdesign":      "bdesign",
    "agriculture":  "agriculture",
    "architecture": "architecture",
    "bhmct":        "bhmct",
    "llb5":         "llb5",
}


def fetch_pdf_via_wrapper(portal: str, menu_id: int) -> bytes:
    """Fetch a PDF from a MH State CET Cell ASP.NET wrapper portal.

    Each ASP.NET wrapper page embeds the PDF as a base64 string inside a JS
    variable. We extract and decode.
    """
    url = f"https://{portal}/ViewPublicDocument.aspx?MenuId={menu_id}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    # The PDF is a long base64 string in a JS literal. Match the JVBERi prefix
    # which is base64 of "%PDF" — defensive against unrelated long base64 blobs.
    m = re.search(r"['\"]((?:JVBERi[A-Za-z0-9+/=]{500,}))['\"]", html)
    if m is None:
        candidates = re.findall(r"['\"]([A-Za-z0-9+/=]{1000,})['\"]", html)
        if not candidates:
            raise RuntimeError(
                f"No base64 blob found at {portal} MenuId={menu_id} "
                f"(HTML may have changed format)"
            )
        b64 = candidates[0]
    else:
        b64 = m.group(1)

    data = base64.b64decode(b64)
    if data[:4] != b"%PDF":
        raise RuntimeError(
            f"Decoded blob at {portal} MenuId={menu_id} is not a PDF "
            f"(header: {data[:8]!r})"
        )
    return data
