"""
Build the CMS-E clean tables from the three MoSPI unit-level CSVs.

    raw/CMSE80HH25.csv      52,085 households
    raw/CMSE80PER25.csv    221,617 persons (57,742 carry the education block)
    raw/CMSE80PERST25.csv    1,675 members studying away from home
                                        │
                                        ▼
    clean/cmse_fact_student.parquet     59,417 students  (resident + away, `cut` discriminates)
    clean/cmse_fact_household.parquet   52,085 households
    clean/cmse_fact_person.parquet     214,757 household members, ENROLLED OR NOT

What this script owns
---------------------
1. Decoding every numeric code to a label using the official code lists (sources.py).
2. Deriving state_code from nss_region — the raw files carry NO state column.
3. Applying the weight rule (mult / 100) that MoSPI documents in README_CMSE_2025.docx.
4. Correcting two MoSPI column names that say the opposite of what they mean
   (see MISNAMED below) — the single highest-value thing this transform does.
5. Distinguishing a true zero from an unknown across both expenditure blocks.
6. Unifying two different expenditure schemas (itemised for resident students,
   lump-sum for students away from home) into one comparable set of columns.
7. Asserting the grain and reconciling against the totals MoSPI itself published.
8. Emitting the household ROSTER as well as the student list, which is the only way
   to ask who is NOT in school — and anchoring it on the student table, since MoSPI
   publishes no out-of-school figure for CMS-E to check directly.

Usage:
  python3 scripts/clean_cmse.py
  python3 scripts/clean_cmse.py --no-verify     # skip the published-total reconciliation
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sources as S

# The seven raw columns that together identify a sampled household.
HH_KEY = [
    "nss_region", "district", "stratum", "sub_stratum",
    "fsu_serial_no", "second_stage_stratum_no", "sample_hhld_no",
]

# ── MoSPI column names that mean the opposite of what they say ────────────────
# In the released CSVs the household file labels block 3 items 7 and 8 as if they
# were about ANY member attending school. The Data Layout is unambiguous that both
# are about ERSTWHILE members — people who have LEFT the household and are studying
# elsewhere. Only 1,273 households answer yes, against 34,468 households that
# actually contain a student. Read at face value the column undercounts by 27x.
MISNAMED = {
    "any_member_attending_school": "has_erstwhile_student",
    "num_members_attending_school": "num_erstwhile_students",
}


def _read(name: str) -> pd.DataFrame:
    path = S.RAW / name
    if not path.exists():
        raise SystemExit(
            f"missing {path}\nDownload the CMS-E unit-level CSVs from {S.SOURCE_URL}"
        )
    return pd.read_csv(path, low_memory=False)


def _zpad(s: pd.Series, width: int) -> pd.Series:
    """Codes are STRING and zero-padded as published — INT loses the padding."""
    return s.astype("Int64").astype(str).str.zfill(width).replace("<NA>", pd.NA)


def _household_id(df: pd.DataFrame) -> pd.Series:
    """Stable composite household id. Unique within this round only."""
    return (
        _zpad(df.nss_region, 3) + "-" + _zpad(df.district, 2) + "-"
        + _zpad(df.stratum, 3) + "-" + _zpad(df.sub_stratum, 2) + "-"
        + _zpad(df.fsu_serial_no, 5) + "-" + _zpad(df.second_stage_stratum_no, 1)
        + "-" + _zpad(df.sample_hhld_no, 2)
    )


def _geo(df: pd.DataFrame, states: dict[str, str]) -> pd.DataFrame:
    """State is NOT a column in the raw files — it is the first 2 digits of nss_region."""
    out = pd.DataFrame(index=df.index)
    out["nss_region"] = _zpad(df.nss_region, 3)
    out["state_code"] = out.nss_region.str[:2]
    out["state_name"] = out.state_code.map(states)
    out["district_code"] = _zpad(df.district, 2)
    out["sector_code"] = df.sector.astype("Int64")
    out["sector_name"] = df.sector.map(S.SECTOR)
    out["stratum"] = _zpad(df.stratum, 3)
    out["sub_stratum"] = _zpad(df.sub_stratum, 2)
    out["fsu_serial_no"] = _zpad(df.fsu_serial_no, 5)
    return out


def _zero_where(value: pd.Series, is_true_zero: pd.Series) -> pd.Series:
    """Fill a genuine surveyed zero; leave anything unascertained as NULL."""
    return value.where(~(value.isna() & is_true_zero), 0.0)


# ── Household ─────────────────────────────────────────────────────────────────

def build_household(hh: pd.DataFrame, states: dict[str, str]) -> pd.DataFrame:
    out = _geo(hh, states)
    out.insert(0, "household_id", _household_id(hh))
    out["survey_year"] = S.SURVEY_YEAR

    out["household_size"] = hh.household_size.astype("Int64")
    out["household_type_code"] = hh.household_type.astype("Int64")
    out["household_type_name"] = np.where(
        hh.sector == 1,
        hh.household_type.map(S.HOUSEHOLD_TYPE_RURAL),
        hh.household_type.map(S.HOUSEHOLD_TYPE_URBAN),
    )
    out["religion_code"] = hh.religion.astype("Int64")
    out["religion_name"] = hh.religion.map(S.RELIGION)
    out["social_group_code"] = hh.social_group.astype("Int64")
    out["social_group_name"] = hh.social_group.map(S.SOCIAL_GROUP)

    # Consumption block (block 6). mpce is MoSPI's own A+B+C+((D+E)/12).
    out["monthly_exp_purchased_goods"] = hh.monthly_expenditure_purchased_goods
    out["monthly_exp_homegrown"] = hh.monthly_expenditure_homegrown
    out["monthly_exp_in_kind_gifts"] = hh.monthly_expenditure_in_kind_gifts
    out["annual_exp_clothing_footwear"] = hh.annual_expenditure_clothing_footwear
    out["annual_exp_durables"] = hh.annual_expenditure_durables
    out["mpce"] = hh.usual_monthly_consumption_expenditure
    out["mpce_per_capita"] = (
        hh.usual_monthly_consumption_expenditure / hh.household_size.replace(0, np.nan)
    )

    # See MISNAMED. These are about members who have LEFT the household.
    out["has_erstwhile_student"] = hh[list(MISNAMED)[0]].map(S.YES_NO)
    out["num_erstwhile_students"] = hh[list(MISNAMED)[1]].astype("Int64")

    # Single-member hostel "households": a student surveyed as their own household.
    # Their per-capita consumption is one teenager's and ranks spuriously high.
    out["is_student_hostel_household"] = hh.in_hostel_or_mess.notna() & (hh.household_size <= 2)

    out["informant_response_code"] = hh.response_code.astype("Int64")
    out["survey_code"] = hh.survey_code.astype("Int64")
    out["weight"] = hh.mult / S.WEIGHT_DIVISOR
    out["people_weight"] = out.weight * out.household_size
    return out


# ── Students living at home (person file, block 5) ────────────────────────────

def build_resident_students(per: pd.DataFrame, hh_ctx: pd.DataFrame,
                            states: dict[str, str]) -> pd.DataFrame:
    st = per[per.enrolment_level.notna()].copy()
    out = _geo(st, states)
    out.insert(0, "household_id", _household_id(st))
    out.insert(1, "person_serial_no", _zpad(st.person_serial_no, 2))
    out.insert(2, "cut", "resident")
    out["survey_year"] = S.SURVEY_YEAR

    out["gender_code"] = st.gender.astype("Int64")
    out["gender_name"] = st.gender.map(S.GENDER)
    out["age"] = st.age.astype("Int64")
    out["relation_to_head_code"] = st.relation_to_head.astype("Int64")
    out["relation_to_head_name"] = st.relation_to_head.map(S.RELATION_TO_HEAD)

    out["enrolment_level_code"] = _zpad(st.enrolment_level, 2)
    out["enrolment_level_name"] = st.enrolment_level.map(S.ENROLMENT_LEVEL)
    out["enrolment_stage"] = st.enrolment_level.map(S.ENROLMENT_STAGE)
    out["school_type_code"] = st.school_type.astype("Int64")
    out["school_type_name"] = st.school_type.map(S.SCHOOL_TYPE)
    out["is_government_school"] = (st.school_type == 1).astype("boolean")

    # Itemised school expenditure. "No expenditure incurred" is a surveyed zero.
    no_school_spend = st.school_expenditure_incurred == 2
    for src, dst in [
        ("school_exp_course_fee", "school_exp_course_fee"),
        ("school_exp_transport", "school_exp_transport"),
        ("school_exp_uniform", "school_exp_uniform"),
        ("school_exp_textbooks_stationery", "school_exp_textbooks_stationery"),
        ("school_exp_other", "school_exp_other"),
        ("school_exp_total", "school_expenditure"),
    ]:
        out[dst] = _zero_where(st[src], no_school_spend)

    out["received_private_coaching"] = st.received_private_coaching.map(S.YES_NO)
    # No coaching at all, or coaching taken but nothing paid — both true zeros.
    no_coach_spend = (st.received_private_coaching == 2) | (
        st.private_coaching_expenditure_incurred == 2
    )
    for src, dst in [
        ("private_coaching_exp_course_fee", "coaching_exp_course_fee"),
        ("private_coaching_exp_transport", "coaching_exp_transport"),
        ("private_coaching_exp_uniform", "coaching_exp_uniform"),
        ("private_coaching_exp_textbooks_material", "coaching_exp_textbooks_material"),
        ("private_coaching_exp_other", "coaching_exp_other"),
        ("private_coaching_exp_total", "coaching_expenditure"),
    ]:
        out[dst] = _zero_where(st[src], no_coach_spend)

    # Hostel fee is asked only of single-member hostel households; elsewhere it is
    # not applicable, which for a resident student is a genuine zero.
    out["boarding_expenditure"] = st.hostel_fee_expenditure.fillna(0.0)
    out["unallocated_expenditure"] = 0.0

    out["funding_source_1_code"] = _zpad(st.funding_source_1, 2)
    out["funding_source_1_name"] = st.funding_source_1.map(S.FUNDING_SOURCE)
    out["funding_source_2_code"] = _zpad(st.funding_source_2, 2)
    out["funding_source_2_name"] = st.funding_source_2.map(S.FUNDING_SOURCE)

    # Away-only columns, absent by construction on this cut.
    out["residence_type_code"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out["residence_type_name"] = pd.NA
    out["present_place_of_residence"] = pd.NA
    out["school_exp_reporting_status"] = pd.NA
    out["coaching_exp_reporting_status"] = pd.NA
    out["boarding_exp_reporting_status"] = pd.NA
    out["household_funds_majority"] = pd.NA

    out["weight"] = st.mult / S.WEIGHT_DIVISOR
    return out.merge(hh_ctx, on="household_id", how="left", validate="m:1")


# ── The roster: every surveyed member the enrolment question was put to ───────

def build_person_roster(per: pd.DataFrame, hh_ctx: pd.DataFrame,
                        states: dict[str, str]) -> pd.DataFrame:
    """One row per household member who was asked whether they are enrolled.

    WHY THIS TABLE EXISTS. cmse_fact_student holds only enrolled students, so the
    question "who is NOT in school" cannot be asked of it at all — and that is the
    cut this survey can answer better than anything else Avanti has, because the
    person file is a full household roster, not a list of students.

    THE FILTER IS THE GATE ITSELF, not a populated enrolment level. Block 5 item 3
    (`currently_enrolled_school`) is 1 or 2 for everyone it was put to and blank
    otherwise; those blanks are exactly the household members aged 0, 1 and 2, for
    whom MoSPI never asks. Filtering on the gate makes the denominator correct by
    construction: a rate computed over this table cannot accidentally include a
    toddler who was never asked. assert_person_grain() checks that the excluded set
    really is ages 0-2 rather than trusting it.
    """
    r = per[per.currently_enrolled_school.notna()].copy()
    out = _geo(r, states)
    out.insert(0, "household_id", _household_id(r))
    out.insert(1, "person_serial_no", _zpad(r.person_serial_no, 2))
    out["survey_year"] = S.SURVEY_YEAR

    out["gender_code"] = r.gender.astype("Int64")
    out["gender_name"] = r.gender.map(S.GENDER)
    out["age"] = r.age.astype("Int64")
    out["age_band"] = pd.NA
    for lo, hi, label in S.AGE_BANDS:
        out.loc[r.age.between(lo, hi), "age_band"] = label
    # The one filter that makes an out-of-school rate defensible. CMS-E is a
    # school-education survey, so above 17 it cannot separate "not in school" from
    # "in higher education" — a rate on an 18+ band measures neither.
    out["is_school_age"] = r.age.between(S.SCHOOL_AGE_MIN, S.SCHOOL_AGE_MAX)
    out["relation_to_head_code"] = r.relation_to_head.astype("Int64")
    out["relation_to_head_name"] = r.relation_to_head.map(S.RELATION_TO_HEAD)

    out["is_enrolled"] = r.currently_enrolled_school.map(S.CURRENTLY_ENROLLED).astype("boolean")

    # Enrolment detail exists only for the enrolled half, and is NULL rather than
    # zero on the other — a child who is not in school has no class and no school
    # type, which is a different fact from having one that was not recorded.
    out["enrolment_level_code"] = _zpad(r.enrolment_level, 2)
    out["enrolment_level_name"] = r.enrolment_level.map(S.ENROLMENT_LEVEL)
    out["enrolment_stage"] = r.enrolment_level.map(S.ENROLMENT_STAGE)
    out["school_type_code"] = r.school_type.astype("Int64")
    out["school_type_name"] = r.school_type.map(S.SCHOOL_TYPE)

    out["weight"] = r.mult / S.WEIGHT_DIVISOR
    return out.merge(hh_ctx, on="household_id", how="left", validate="m:1")


# ── Students living away from home (erstwhile file, block 4) ──────────────────

def build_away_students(erst: pd.DataFrame, hh_ctx: pd.DataFrame,
                        states: dict[str, str]) -> pd.DataFrame:
    e = erst.copy()
    out = _geo(e, states)
    out.insert(0, "household_id", _household_id(e))
    out.insert(1, "person_serial_no", "E" + _zpad(e.erstwhile_person_serial_no, 2))
    out.insert(2, "cut", "away_from_home")
    out["survey_year"] = S.SURVEY_YEAR

    out["gender_code"] = e.gender.astype("Int64")
    out["gender_name"] = e.gender.map(S.GENDER)
    out["age"] = e.age.astype("Int64")
    out["relation_to_head_code"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out["relation_to_head_name"] = pd.NA

    out["enrolment_level_code"] = _zpad(e.current_enrolment_level, 2)
    out["enrolment_level_name"] = e.current_enrolment_level.map(S.ENROLMENT_LEVEL)
    out["enrolment_stage"] = e.current_enrolment_level.map(S.ENROLMENT_STAGE)
    # Block 4 never asks what kind of school the student attends.
    out["school_type_code"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out["school_type_name"] = pd.NA
    out["is_government_school"] = pd.Series(pd.NA, index=out.index, dtype="boolean")

    # Block 4 collects lump sums, not the five-way itemisation of block 5.
    for col in [
        "school_exp_course_fee", "school_exp_transport", "school_exp_uniform",
        "school_exp_textbooks_stationery", "school_exp_other",
        "coaching_exp_course_fee", "coaching_exp_transport", "coaching_exp_uniform",
        "coaching_exp_textbooks_material", "coaching_exp_other",
    ]:
        out[col] = np.nan

    no_spend = e.any_expenditure_incurred == 2
    # Reporting-status codes separate "not known" from "it was free". A blank
    # under "free tuition" is a real zero; a blank under "not known" is not.
    out["school_exp_reporting_status"] = e.school_expenditure_nonreporting_code.map(
        S.NONREPORTING_SCHOOL
    )
    out["coaching_exp_reporting_status"] = e.private_coaching_nonreporting_code.map(
        S.NONREPORTING_COACHING
    )
    out["boarding_exp_reporting_status"] = e.boarding_lodging_nonreporting_code.map(
        S.NONREPORTING_BOARDING
    )

    out["school_expenditure"] = _zero_where(e.school_education_expenditure, no_spend)
    out["coaching_expenditure"] = _zero_where(
        e.private_coaching_expenditure,
        no_spend | e.private_coaching_nonreporting_code.isin([3, 4]),
    )
    out["boarding_expenditure"] = _zero_where(
        e.boarding_lodging_expenditure,
        no_spend | (e.boarding_lodging_nonreporting_code == 3),
    )
    out["received_private_coaching"] = np.where(
        e.private_coaching_nonreporting_code.isin([1, 3]), "Yes",
        np.where(e.private_coaching_nonreporting_code == 4, "No", None),
    )

    # The lump sum is the authoritative all-in figure. What it exceeds the named
    # components by is the residual — for a residential coaching package, this is
    # where the coaching fee that could not be separated out ends up.
    total = _zero_where(e.total_education_expenditure, no_spend)
    parts = (
        out.school_expenditure.fillna(0)
        + out.coaching_expenditure.fillna(0)
        + out.boarding_expenditure.fillna(0)
    )
    out["unallocated_expenditure"] = (total - parts).clip(lower=0)

    out["residence_type_code"] = e.type_of_residence.astype("Int64")
    out["residence_type_name"] = e.type_of_residence.map(S.RESIDENCE_TYPE)
    out["present_place_of_residence"] = e.present_place_of_residence.map(S.PLACE_OF_RESIDENCE)
    out["household_funds_majority"] = e.household_majority_funding.map(S.YES_NO)

    out["funding_source_1_code"] = pd.NA
    out["funding_source_1_name"] = pd.NA
    out["funding_source_2_code"] = pd.NA
    out["funding_source_2_name"] = pd.NA

    out["weight"] = e.mult / S.WEIGHT_DIVISOR
    return out.merge(hh_ctx, on="household_id", how="left", validate="m:1")


# ── Verification ──────────────────────────────────────────────────────────────

def _wshare(df: pd.DataFrame, mask: pd.Series) -> float:
    return df.loc[mask, "weight"].sum() / df.weight.sum() * 100


def _wmean(df: pd.DataFrame, col: str) -> float:
    d = df[df[col].notna()]
    return float(np.average(d[col], weights=d.weight))


def verify(students: pd.DataFrame, households: pd.DataFrame) -> None:
    """Reconcile against the figures MoSPI published in PIB release 275295.

    Every one of these is a number the source itself asserts. If the transform
    drifts, this fails loudly rather than emitting numbers nobody checked.
    """
    res = students[students.cut == "resident"]
    gov = res[res.school_type_code == 1]
    nongov = res[res.school_type_code != 1]

    checks = [
        ("households surveyed", len(households), 52085, 0),
        ("resident students", len(res), 57742, 0),
        ("government school share %", _wshare(res, res.school_type_code == 1), 55.9, 0.1),
        ("  rural government share %",
         _wshare(res[res.sector_code == 1], res[res.sector_code == 1].school_type_code == 1), 66.0, 0.1),
        ("  urban government share %",
         _wshare(res[res.sector_code == 2], res[res.sector_code == 2].school_type_code == 1), 30.1, 0.1),
        ("govt students paying course fee %",
         _wshare(gov, gov.school_exp_course_fee > 0), 26.7, 0.1),
        ("non-govt students paying course fee %",
         _wshare(nongov, nongov.school_exp_course_fee > 0), 95.7, 0.1),
        ("avg annual school spend, government (Rs)",
         _wmean(gov.assign(school_expenditure=gov.school_expenditure.fillna(0)), "school_expenditure"), 2863, 2),
        ("avg annual school spend, non-government (Rs)",
         _wmean(nongov.assign(school_expenditure=nongov.school_expenditure.fillna(0)), "school_expenditure"), 25002, 2),
        ("students taking private coaching %",
         _wshare(res, res.received_private_coaching == "Yes"), 27.0, 0.1),
        ("  rural coaching %",
         _wshare(res[res.sector_code == 1], res[res.sector_code == 1].received_private_coaching == "Yes"), 25.5, 0.1),
        ("  urban coaching %",
         _wshare(res[res.sector_code == 2], res[res.sector_code == 2].received_private_coaching == "Yes"), 30.7, 0.1),
        ("funded by other household members %",
         _wshare(res[res.funding_source_1_code.notna()],
                 res[res.funding_source_1_code.notna()].funding_source_1_code == "02"), 95.0, 0.1),
        ("funded by government scholarship %",
         _wshare(res[res.funding_source_1_code.notna()],
                 res[res.funding_source_1_code.notna()].funding_source_1_code == "06"), 1.2, 0.1),
    ]

    print("\nReconciliation against MoSPI PIB release 275295:")
    failures = []
    for label, got, want, tol in checks:
        ok = abs(got - want) <= tol
        flag = "ok " if ok else "FAIL"
        print(f"  [{flag}] {label:44s} got {got:>10,.1f}   published {want:>10,.1f}")
        if not ok:
            failures.append(label)
    if failures:
        raise SystemExit(
            f"\n{len(failures)} check(s) did not reconcile: {failures}\n"
            "Refusing to emit unverified numbers."
        )
    print("  all published figures reconcile.")


def assert_grain(students: pd.DataFrame, households: pd.DataFrame) -> None:
    dup_h = households.household_id.duplicated().sum()
    if dup_h:
        raise SystemExit(f"cmse_fact_household is not unique on household_id ({dup_h} dupes)")
    key = ["household_id", "person_serial_no", "cut"]
    dup_s = students.duplicated(subset=key).sum()
    if dup_s:
        raise SystemExit(f"cmse_fact_student is not unique on {key} ({dup_s} dupes)")
    orphan = students.state_name.isna().sum()
    if orphan:
        raise SystemExit(f"{orphan} student rows have no state_name — check the state codemap")
    print(f"\ngrain ok: {len(households):,} households, {len(students):,} students "
          f"({(students.cut == 'resident').sum():,} resident, "
          f"{(students.cut == 'away_from_home').sum():,} away from home)")


def assert_person_grain(persons: pd.DataFrame, per_raw: pd.DataFrame,
                       students: pd.DataFrame) -> None:
    """Grain, the age gate, and the tie back to the reconciled student table.

    cmse_fact_person has no published MoSPI figure of its own to reconcile against
    — the PIB release does not carry an out-of-school or age-band enrolment number.
    So its anchor is INTERNAL and it is a strong one: the enrolled half of this
    roster must be exactly, row for row, the resident students in
    cmse_fact_student, which is the table whose fourteen figures MoSPI does
    publish. If those two sets ever diverge, one of them is wrong and the build
    stops rather than emitting an out-of-school rate over an unverified
    denominator.
    """
    dup = persons.duplicated(subset=["household_id", "person_serial_no"]).sum()
    if dup:
        raise SystemExit(
            f"cmse_fact_person is not unique on (household_id, person_serial_no) ({dup} dupes)"
        )

    orphan = persons.state_name.isna().sum()
    if orphan:
        raise SystemExit(f"{orphan} person rows have no state_name — check the state codemap")

    # Every gate value must decode. S.CURRENTLY_ENROLLED covers 1 and 2, which is all
    # MoSPI uses today; a third code would map to NA on a column the schema declares
    # REQUIRED and fail in BigQuery at load time instead of here, next to the cause.
    undecoded = persons.is_enrolled.isna().sum()
    if undecoded:
        raise SystemExit(
            f"{undecoded} person rows have an is_enrolled that did not decode — "
            f"currently_enrolled_school carries a value outside {sorted(S.CURRENTLY_ENROLLED)}. "
            "Add it to S.CURRENTLY_ENROLLED; do NOT let it through as NULL."
        )

    # The household context is left-joined, so a household_id absent from the context
    # would silently blank social group, consumption and household type — the columns
    # every equity cut on this table reads. Left joins fail quietly by design; this is
    # the check that makes it loud.
    ctx_cols = ["social_group_name", "mpce", "household_type_name", "household_size"]
    blank_ctx = {c: int(persons[c].isna().sum()) for c in ctx_cols if persons[c].isna().any()}
    if blank_ctx:
        raise SystemExit(
            f"person rows carry no household context: {blank_ctx}. Some household_id in the "
            "person file has no row in cmse_fact_household — the two files disagree."
        )

    # THE AGE GATE, checked rather than assumed. The rows the enrolment question
    # was never put to must be exactly the under-3s; anything else means MoSPI's
    # gate is not what this transform believes it is, and every rate built on this
    # table would carry a denominator nobody checked.
    ungated = per_raw[per_raw.currently_enrolled_school.isna()]
    bad = ungated.loc[ungated.age >= S.SCHOOL_AGE_MIN, "age"]
    if len(bad):
        raise SystemExit(
            f"{len(bad)} rows were never asked the enrolment question but are aged "
            f"{S.SCHOOL_AGE_MIN}+ (ages {sorted(bad.unique())[:8]}). The age gate is not "
            "what the transform assumes; do NOT publish an out-of-school rate on this."
        )

    # Every band must resolve. A NULL age_band on a row that passed the gate would
    # silently drop that person out of every rate.
    unbanded = persons.age_band.isna().sum()
    if unbanded:
        raise SystemExit(f"{unbanded} person rows fall in no age band — check S.AGE_BANDS")

    # THE ANCHOR: enrolled roster == resident students, as SETS, not as counts.
    # Counts agreeing is much weaker: two different row sets of the same size
    # would pass it, which is exactly the ambiguity that made the old
    # enrolment_level filter unproven until it was checked against the raw file.
    # `== True` rather than a truthiness test, throughout: is_enrolled is pandas'
    # nullable `boolean`, where NA is neither True nor False, and `df[df.is_enrolled]`
    # raises on NA rather than excluding it. The explicit comparison is the form that
    # treats "did not decode" as "not enrolled" instead of blowing up — and the guard
    # above means NA cannot reach here anyway.
    key = ["household_id", "person_serial_no"]
    enrolled = set(map(tuple, persons.loc[persons.is_enrolled == True, key].to_numpy()))
    resident = set(map(tuple, students.loc[students.cut == "resident", key].to_numpy()))
    if enrolled != resident:
        raise SystemExit(
            f"the enrolled roster and cmse_fact_student's resident cut are different row "
            f"sets: {len(enrolled):,} vs {len(resident):,}, "
            f"{len(enrolled ^ resident):,} in one but not the other. One of the two "
            "enrolment filters is wrong."
        )

    w_enrolled = persons.loc[persons.is_enrolled == True, "weight"].sum()
    w_resident = students.loc[students.cut == "resident", "weight"].sum()
    if abs(w_enrolled - w_resident) > 1:
        raise SystemExit(
            f"weighted enrolled roster {w_enrolled:,.0f} != weighted resident students "
            f"{w_resident:,.0f} — the same rows carry different multipliers."
        )

    def oos(df):
        return 100 * df.loc[df.is_enrolled == False, "weight"].sum() / df.weight.sum()

    sa = persons[persons.is_school_age]
    compulsory = sa[sa.age >= 6]
    # `max()` on an empty frame is NaN and int(NaN) raises — so if MoSPI ever put the
    # question to everyone, the summary line would crash on the SUCCESS path.
    excluded = (f"{len(ungated):,} under-{S.SCHOOL_AGE_MIN}s excluded, max excluded age "
                f"{int(ungated.age.max())}" if len(ungated) else "none excluded")
    print(f"\nperson roster ok: {len(persons):,} members asked the enrolment question "
          f"({excluded})")
    print(f"  enrolled half is row-for-row cmse_fact_student's resident cut "
          f"({len(enrolled):,} rows, {w_enrolled / 1e6:,.1f}mn weighted)")
    # Both, deliberately: the 3-17 blend is the number a reader will reach for and
    # it is not the one they mean, because pre-primary is optional. Printing the
    # pair is how the caveat travels with the figure instead of living in a yaml.
    print(f"  out of school, ages {S.SCHOOL_AGE_MIN}-{S.SCHOOL_AGE_MAX}: {oos(sa):.1f}% "
          f"({len(sa):,} sampled) — BLENDS optional pre-primary with compulsory schooling")
    print(f"  out of school, ages 6-{S.SCHOOL_AGE_MAX}: {oos(compulsory):.1f}% "
          f"({len(compulsory):,} sampled) — the compulsory-schooling figure, report this one")
    print("  by age band (weighted; 18+ shown for completeness but NOT a supported figure):")
    for _, _, label in S.AGE_BANDS:
        b = persons[persons.age_band == label]
        if not len(b):
            continue
        flag = ("   <- optional stage" if label == "3-5"
                else "" if label in ("6-10", "11-14", "15-17")
                else "   <- NOT school age")
        print(f"    {label:6s} n {len(b):7,d}   {oos(b):5.1f}%{flag}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-verify", action="store_true",
                    help="Skip reconciliation against MoSPI's published figures")
    args = ap.parse_args()

    states = S.load_state_map()
    print(f"{S.SURVEY_NAME} — {S.SURVEY_ROUND}, {S.REFERENCE_PERIOD}")

    hh = _read("CMSE80HH25.csv")
    per = _read("CMSE80PER25.csv")
    erst = _read("CMSE80PERST25.csv")

    households = build_household(hh, states)

    # Household context denormalized onto every student row so the common cuts —
    # state x gender x social group x consumption — need no join.
    hh_ctx = households[[
        "household_id", "household_size", "household_type_code", "household_type_name",
        "religion_code", "religion_name", "social_group_code", "social_group_name",
        "mpce", "mpce_per_capita", "is_student_hostel_household",
    ]]

    students = pd.concat(
        [build_resident_students(per, hh_ctx, states),
         build_away_students(erst, hh_ctx, states)],
        ignore_index=True,
    )
    persons = build_person_roster(per, hh_ctx, states)

    # All-in education spend, comparable across both cuts. NULL components are
    # treated as zero here so the total is always usable; the component columns
    # keep their NULLs so an analyst can see what was never ascertained.
    students["total_education_expenditure"] = (
        students.school_expenditure.fillna(0)
        + students.coaching_expenditure.fillna(0)
        + students.boarding_expenditure.fillna(0)
        + students.unallocated_expenditure.fillna(0)
    )

    assert_grain(students, households)
    # The roster is checked AFTER the student table, because its anchor is the
    # student table: the order is what makes "enrolled == resident" meaningful.
    assert_person_grain(persons, per, students)
    if not args.no_verify:
        verify(students, households)

    S.CLEAN.mkdir(exist_ok=True)
    for df, table in [(students, S.FACT_STUDENT), (households, S.FACT_HOUSEHOLD),
                      (persons, S.FACT_PERSON)]:
        df.to_parquet(table.local_path, index=False)
        print(f"  wrote {table.local_path.name:34s} {len(df):>7,} rows x {len(df.columns)} cols")


if __name__ == "__main__":
    main()
