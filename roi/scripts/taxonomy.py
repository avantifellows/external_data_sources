#!/usr/bin/env python3
"""
taxonomy.py — the common field language shared by AISHE and PLFS.

AISHE tags every graduate by discipline, so it can resolve all nine fields.
PLFS only tags technical/professional education (tedu_lvl), so it resolves wages
for just four "observable" fields — Engineering, Medical, Other Technical, and
one Non-Technical (general-degree) cell that every academic/professional degree
shares. The crosswalk below routes each common field to:
    • its AISHE disciplines (for graduate counts), and
    • the PLFS-observable field whose wage/employment it borrows.

So Science, Commerce, Management, Law, IT & Computer and Other all currently
inherit the PLFS Non-Technical (general-degree) baseline — until we enrich the
high-value professional pathways (Management/Law) from NIRF later.
"""
from __future__ import annotations

# First-level common fields (order = presentation order).
COMMON_FIELDS = [
    "Engineering", "Medical", "Other Technical", "IT & Computer",
    "Science", "Commerce", "Management", "Law", "Other",
]

# STEM subset → the "STEM UG" denominator.
STEM_FIELDS = {"Engineering", "Medical", "Other Technical", "IT & Computer", "Science"}

# AISHE discipline → common field. Anything not listed falls to "Other".
AISHE_TO_FIELD = {
    "Engineering & Technology": "Engineering",
    "Medical Science": "Medical",
    "IT & Computer": "IT & Computer",
    "Agriculture": "Other Technical",
    "Paramedical Science": "Other Technical",
    "Veterinary & Animal Sciences": "Other Technical",
    "Fisheries Science": "Other Technical",
    "Marine Science / Oceanography": "Other Technical",
    "Design": "Other Technical",
    "Fashion Technology": "Other Technical",
    "Footwear  Design": "Other Technical",
    "Science": "Science",
    "Commerce": "Commerce",
    "Management": "Management",
    "Law": "Law",
}

# Common field → PLFS-observable field whose wage/employment it borrows.
# PLFS resolves distinct wages only for the first three; the rest share the
# Non-Technical (general academic degree) cell.
PLFS_WAGE_FIELD = {
    "Engineering": "Engineering",
    "Medical": "Medical",
    "Other Technical": "Other Technical",
    "IT & Computer": "Non-Technical",
    "Science": "Non-Technical",
    "Commerce": "Non-Technical",
    "Management": "Non-Technical",
    "Law": "Non-Technical",
    "Other": "Non-Technical",
}


def aishe_field(discipline: str) -> str:
    return AISHE_TO_FIELD.get(discipline, "Other")


def plfs_field(common_field: str) -> str:
    return PLFS_WAGE_FIELD[common_field]


# ── NIRF "top-college" tier layer ─────────────────────────────────────────────
# A third level: the ranked sub-cohorts NIRF measures (placement + salary) inside
# the common fields. Engineering splits into IIT / NIT / IIIT / the rest of the
# top-200; the other ranked disciplines each stay whole.
NIRF_TIERS = [
    "IIT", "NIT", "IIIT", "Other NIRF Top-200 Eng",
    "Top NIRF Medical & Dental", "Top NIRF Architecture & Planning",
    "Top NIRF Law", "Top NIRF Pharmacy",
]

# NIRF tier → common field (so the ranked cohorts roll up into the same language).
NIRF_TIER_TO_FIELD = {
    "IIT": "Engineering",
    "NIT": "Engineering",
    "IIIT": "Engineering",
    "Other NIRF Top-200 Eng": "Engineering",
    "Top NIRF Medical & Dental": "Medical",
    "Top NIRF Architecture & Planning": "Engineering",
    "Top NIRF Law": "Law",
    "Top NIRF Pharmacy": "Other Technical",
}


def nirf_tier(ranking_category: str, institute_name: str) -> str | None:
    """Classify a NIRF institute row into a top-college tier (or None to skip)."""
    nm = institute_name or ""
    if ranking_category == "Engineering":
        if "Indian Institute of Information Technology" in nm:
            return "IIIT"
        if "National Institute of Technology" in nm:
            return "NIT"
        if "Indian Institute of Technology" in nm:
            return "IIT"
        return "Other NIRF Top-200 Eng"
    if ranking_category in ("Medical", "Dental"):
        return "Top NIRF Medical & Dental"
    if ranking_category in ("Architecture", "Architecture and Planning"):
        return "Top NIRF Architecture & Planning"
    if ranking_category == "Law":
        return "Top NIRF Law"
    if ranking_category == "Pharmacy":
        return "Top NIRF Pharmacy"
    return None
