"""
Canonical column-name mapping for PLFS releases.

PLFS releases use inconsistent column naming:
  - CY2024/CY2025 ship layouts with explicit 'field_name' (lowercase mnemonic).
  - CY2022/CY2023 layouts have only 'Full Name' (e.g., "State/Ut Code").
  - Annual 2018-19 layout has 'Full Name' too, with older field set.
  - The pre-converted CSVs (txt2csv output) use a third naming style mixing
    mnemonics (panel, qtr) with schedule codes (B1q2, b3q5pt4, b6q10).

This module gives ONE function `canonical_name(full_name, block=None)` that
maps a layout's "Full Name" (with optional Block context for disambiguation)
to a single canonical mnemonic. Every release then resolves to the same
column names, so analyses are write-once-run-everywhere.

The canonical names follow CY2024's convention (lowercase, snake_case).
"""

import re

# Direct mapping (Full Name → canonical) — block-independent
DIRECT = {
    # Identifiers / household-level
    'panel': 'panel',
    'file identification': 'file_id',
    'schdule': 'sch',  # PLFS source typo, kept as-is
    'schedule': 'sch',
    'quarter': 'qtr',
    'month': 'month',
    'visit': 'visit',
    'sector': 'sec',
    'state/ut code': 'st',
    'state code': 'st',
    'district code': 'dc',
    'nss-region': 'nss_reg',
    'nss region': 'nss_reg',
    'stratum': 'strm',
    'sub-stratum': 'sstrm',
    'sub-sample': 'ss',
    'fod sub-region': 'sro',
    'fsu': 'mfsu',
    'sample sg/sb no.': 'seg',
    'sample hg/sb no.': 'seg',
    'second stage stratum no.': 'sss',
    'sample household number': 'ssu',
    'month of survey': 'smonth',
    'response code': 'resp_code',
    'survey code': 'svc',
    'reason for substitution of original household': 'rsr',
    'basic stratum': 'bstrm',
    'group': 'grp',
    # Block 3
    'household size': 'hh_size',
    'household type': 'hh_type',
    'religion': 'religion',
    'social group': 'social_grp',
    "household'susual consumer expenditure in a month (rs.)": 'hce_tot',
    "household's usual consumer expenditure in a month (rs.)": 'hce_tot',
    "household's usual consumer expenditure in a month": 'hce_tot',
    "household's usual consumer expenditure in a month for purposes out of goods and services(rs.)": 'hce1',
    'imputed value of usual consumption in a month out of home grown stock (rs.)': 'hce2',
    'imputed value of usual consumption in a month from wages in kind,free collection, gifts etc. (rs.)': 'hce3',
    "household's annual expenditure on purchase of items like clothing, footwear etc.(rs.)": 'hce4',
    "household's annual expenditure on purchase of durables like bedstead, tv, fridge etc.(rs.)": 'hce5',
    'informant serial no.': 'inf_srl',
    'survey date': 'sur_date',
    'total time taken to canvass sch. 10.4': 'sur_time',
    # Weights
    'ns count for sector x stratum x substratum x sub-sample': 'nss',
    'ns count for sector x stratum x substratum': 'nsc',
    'sub-sample wise multiplier': 'mult',
    # no_qtr field has many variant spellings across PLFS releases (Occurance / Occurence,
    # 'FSUs in' / no 'FSUs in', '4 Quarters' / 'that Quarter ...').
    'occurance of state x sector x stratum x substratum in 4 quarters': 'no_qtr',
    'occurance of fsus in state x sector x stratum x substratum in 4 quarters': 'no_qtr',
    'occurance of state x sector x stratum x substratum in that quarter including earlier visits': 'no_qtr',
    'occurance of fsus in state x sector x stratum x substratum in that quarter including earlier visits': 'no_qtr',
    'occurence of state x sector x stratum x substratum in 4 quarters': 'no_qtr',
    'occurence of fsus in state x sector x stratum x substratum in 4 quarters': 'no_qtr',
    'occurence of fsus in state x sector x stratum x substratum in that quarter including earlier visits': 'no_qtr',
    'count of contributing state x sector x stratum x substratum in 4 quarters': 'no_qtr',
    'count of contributing samples for state x sector x stratum x sub-stratum in 4 quarters': 'no_qtr',
    'current weekly status (cws)': 'aps_cws',
    # CY2025 additions
    'size of basic stratum': 'zst',
    'total number of households listed in a second stage stratum of a particular first stage unit (fsu)': 'caph',
    'total number of sample households surveyed in the second stage stratum within a particular first stage unit (fsu)': 'smallh',
    # Block 4 (person demographics)
    'person serial no.': 'srl_no',
    'relationship to head': 'rel',
    'whether a member on the date of revisit': 'whether_member',
    'sex': 'sex',
    'age': 'age',
    'marital status': 'marst',
    'general educaion level': 'gedu_lvl',  # PLFS source typo "Educaion"
    'general education level': 'gedu_lvl',
    'technical educaion level': 'tedu_lvl',
    'technical education level': 'tedu_lvl',
    'class/grade successfully completed': 'grade',
    'year(s) of education completed prior to class i': 'yrsbef1',
    'year(s) of education completed after the class/grade recorded in column 10': 'yrsaft',
    'whether the last completed year of education recorded in column 12 was the last year of education attended': 'iflastyr',
    'no. of months attended in the last year of education': 'mnths',
    'status of current attendance in educational institution': 'curr_att',
    'whether attended secondary education': 'secondary',
    'whether received any vocational/technical training': 'voc',
    # Block 4.1 vocational training
    'whether the training was completed during last 365 days': 'vt_complete_365',
    'field of training': 'vt_field',
    'duration of training': 'vt_dur',
    'type of training': 'vt_type',
    'source of funding': 'vt_fund',
    'nature of the certifying body from which vocational / technical training received': 'voc_cert',
}


# Block-aware mappings — same Full Name appears in multiple blocks with different meaning.
# Key: (full_name_normalized, block). Value: canonical name.
BLOCK_AWARE = {
    # Status code
    ('status code', '5.1'): 'pas',     # Usual Principal Activity Status
    ('status code', '5.2'): 'sas',     # Usual Subsidiary Activity Status
    ('status code', '6'):   'aps_cws', # CWS principal activity (consolidated)
    # Industry codes (NIC)
    ('industry code (nic)', '5.1'): 'ind_pas',
    ('industry code (nic)', '5.2'): 'ind_sas',
    ('industry code (cws)', '6'):   'aind_cws',
    # Occupation codes (NCO)
    ('occupation code (nco)', '5.1'): 'ocu_pas',
    ('occupation code (nco)', '5.2'): 'ocu_sas',
    ('occupation code (cws)', '6'):   'ocu_cws',
    # Enterprise type
    ('(principal) enterprise type code', '5.1'): 'etyp_pas',
    ('(subsidiary)  enterprise type code', '5.2'): 'etyp_sas',
    ('(subsidiary) enterprise type code', '5.2'): 'etyp_sas',
    # Workplace location
    ('(principal)location of workplace code', '5.1'): 'loc_pas',
    ('(subsidiary) location of workplace code', '5.2'): 'loc_sas',
    # Number of workers
    ('(principal) no. of workers in the enterprise', '5.1'): 'wrkr_pas',
    ('(subsidiary)  no. of workers in the enterprise', '5.2'): 'wrkr_sas',
    ('(subsidiary) no. of workers in the enterprise', '5.2'): 'wrkr_sas',
    # Job contract
    ('(principal)  type of job contract', '5.1'): 'job_pas',
    ('(principal) type of job contract', '5.1'): 'job_pas',
    ('(subsidiary)   type of job contract', '5.2'): 'job_sas',
    ('(subsidiary) type of job contract', '5.2'): 'job_sas',
    # Paid leave
    ('(principal) eligble of paid leave', '5.1'): 'leave_pas',
    ('(subsidiary) eligble of paid leave', '5.2'): 'leave_sas',
    # Social security
    ('(principal) social security benefits', '5.1'): 'ssec_pas',
    ('(subsidiary) social security benefits', '5.2'): 'ssec_sas',
    # Product / economic activity output
    ('(principal) usage of product of the economic activity', '5.1'): 'ecoprd_pas',
    # Subsidiary work flag
    ('whether engaged in any work in subsidiary capacity', '5.1'): 'has_sas',
    # Earnings
    ('earnings for regular salaried/wage activity', '6'): 'ern_reg',
    ('earnings for regular salarid/wage activity', '6'): 'ern_reg',  # PLFS typo
    ('earnings for self employed', '6'): 'ern_self',
    # Training/exam-prep
    ('whether received or receiving any training or course for entrance in higher education or for employment exams by an institute / training center', '4'): 'trg',
}


def _normalize(name: str) -> str:
    if name is None: return ''
    s = str(name).lower().strip()
    s = re.sub(r'\s+', ' ', s)
    return s


def canonical_name(full_name: str, block=None, item=None, srl=None, length=None):
    """Map ('Full Name', block?) → canonical mnemonic.

    Returns None when no mapping found — caller should fall back to a slug.
    """
    n = _normalize(full_name)
    if not n: return None

    if block is not None:
        b = str(block).strip()
        if (n, b) in BLOCK_AWARE:
            return BLOCK_AWARE[(n, b)]

    if n in DIRECT:
        return DIRECT[n]

    # Heuristic: per-day CWS columns (block 6, items 5/3.1 .. 5/3.7)
    # named like "Industry Code (NIC) for activity 1" / "Status Code for activity 2"
    # These get serial mnemonic ind11..ind17, ind21..ind27, ocu11..ocu17, etc.
    # We don't try to resolve these here — handled by the caller using Item info.

    return None


def slug(full_name: str) -> str:
    """Fallback: slugify a full name when no canonical mapping exists."""
    s = _normalize(full_name)
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return s.strip('_')[:40] or 'unknown'
