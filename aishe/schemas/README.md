# AISHE HE Directory — concepts in 60 seconds

**AISHE** (All India Survey on Higher Education) is the Ministry of Education's
official annual census of every higher-education institution in India. It assigns
each institution a permanent **AISHE code** (a unique alphanumeric ID) and
collects data on enrolment, faculty, infrastructure, programmes, and finances.

The **HE Directory** tab on the AISHE dashboard
(dashboard.aishe.gov.in/hedirectory) is the public-facing directory of all
*currently active* institutions — it is updated in near-real-time as institutions
are registered or de-registered, and is separate from the annual survey microdata
(which is a point-in-time snapshot for a given academic year).

## Institution types in the HE Directory

AISHE classifies institutions into **five mutually exclusive registry tabs**:

| Tab | AISHE code prefix | What it covers |
|---|---|---|
| **Colleges** | `C-` | Affiliated/constituent colleges attached to a parent university. The largest category (~53,000 institutions). |
| **Universities** | `U-` | Degree-awarding bodies (central, state, deemed, private). Universities may have constituent colleges. |
| **Standalone** | `S-` | Institutions that offer programmes (usually diploma/certificate/technical) but are NOT affiliated to a university. Polytechnics, nursing schools, teacher-training institutes, etc. |
| **R&D** | `R-` | Research & development institutes recognised under the AISHE framework (ISRO, CSIR labs, ICAR institutes, etc.). |
| **PM Vidyalaxmi** | `U-`/`C-` | Subset of eligible institutions listed under the PM Vidyalaxmi scholarship scheme. Not a distinct institution type — it is an eligibility list drawn from the other tabs. |

## AISHE code anatomy

- Prefix letter encodes the institution type: `C` = college, `U` = university,
  `S` = standalone, `R` = R&D.
- The number after the dash is a serial registry ID (not hierarchical).
- Codes are **stable identifiers** — they don't change when an institution
  moves, renames, or changes affiliation. Use the AISHE code as the join key
  across datasets.

## Management categories (who runs it)

| Value | Meaning |
|---|---|
| State Government | Owned and funded by a state government |
| Central Government | Owned by the Government of India |
| Private Aided (Government Aided) | Privately managed but receives government grants |
| Private Un-Aided | Privately managed, self-financing |
| Local Body | Run by a municipal corporation or panchayat |

## College type taxonomy

Colleges are further classified by their relationship to a university:
- **Affiliated College** — independent college affiliated to a parent university
- **Constituent College** — a college that is an integral part of the university
- **Autonomous College** — affiliated but has academic autonomy for its own syllabus and exams

## Location

`Rural` / `Urban` based on the Census 2011 classification of the institution's
address block.

## Year of establishment

Year the institution was formally registered/established. May differ from the
year it started teaching. Some records show `-` where the year is unknown.

## PM Vidyalaxmi

Launched in 2024, PM Vidyalaxmi is a central-government scholarship scheme for
meritorious students from non-affluent families to access quality higher
education. Only institutions with a **NAAC grade A or A+** (or equivalent NIRF
ranking) are listed as eligible. The `aishe_fact_pm_vidyalaxmi` table is
effectively a filtered subset of the other institution tables.
