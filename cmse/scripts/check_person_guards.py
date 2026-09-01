#!/usr/bin/env python3
"""Prove that every guard on cmse_fact_person actually fires.

WHY THIS EXISTS. cmse_fact_person is the one CMS-E table with no published MoSPI
figure behind it — the PIB release carries no out-of-school or age-band enrolment
number — so its correctness rests entirely on assertions inside the transform
rather than on a reconciliation anyone can eyeball. A guard nobody has watched fail
is a guard nobody has tested, and this source's whole design is that the build
refuses rather than emits unverified numbers.

So each guard is broken on purpose here and must stop the build. The important one
is the ROW-SET anchor: it is fed an enrolled half with the *identical row count* to
cmse_fact_student's resident cut but two different people in it, which is precisely
the case a count-based check would wave through. That ambiguity is not theoretical —
it is the reason the old `enrolment_level IS NOT NULL` filter stayed unproven until
someone read the raw file.

Usage:
  python3 scripts/check_person_guards.py        # exits non-zero if any guard is asleep

Needs the three raw CSVs in raw/ (see README).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clean_cmse as C
import sources as S

CTX_COLS = [
    "household_id", "household_size", "household_type_code", "household_type_name",
    "religion_code", "religion_name", "social_group_code", "social_group_name",
    "mpce", "mpce_per_capita", "is_student_hostel_household",
]


def build_all():
    states = S.load_state_map()
    hh = C._read("CMSE80HH25.csv")
    per = C._read("CMSE80PER25.csv")
    erst = C._read("CMSE80PERST25.csv")
    households = C.build_household(hh, states)
    ctx = households[CTX_COLS]
    students = pd.concat(
        [C.build_resident_students(per, ctx, states),
         C.build_away_students(erst, ctx, states)],
        ignore_index=True,
    )
    return per, students, C.build_person_roster(per, ctx, states)


def main() -> None:
    per, students, persons = build_all()
    asleep = []

    def expect_fail(label, call):
        try:
            call()
        except SystemExit as exc:
            print(f"  [fires] {label}")
            print(f"          → {str(exc).splitlines()[0][:100]}")
            return
        print(f"  [ASLEEP] {label}")
        asleep.append(label)

    print("cmse_fact_person guards — each is broken on purpose and must stop the build:\n")

    # 1. The age gate. If MoSPI ever asks the enrolment question of a different set
    # of people, every rate built on this table silently changes denominator.
    bad_per = per.copy()
    bad_per.loc[bad_per.index[bad_per.currently_enrolled_school.isna()][0], "age"] = 9
    expect_fail("age gate catches a school-age member who was never asked",
                lambda: C.assert_person_grain(persons, bad_per, students))

    # 2. THE ONE THAT MATTERS. Same count, different people.
    swapped = persons.copy()
    swapped.loc[swapped.index[swapped.is_enrolled == True][0], "person_serial_no"] = "99"
    expect_fail("row-set anchor catches a swapped person at an IDENTICAL row count",
                lambda: C.assert_person_grain(swapped, per, students))

    # 3. Same rows, drifted multiplier — the roster and the student table would
    # then report different populations for the same people.
    reweighted = persons.copy()
    reweighted.loc[reweighted.index[reweighted.is_enrolled == True][0], "weight"] += 5000
    expect_fail("weight anchor catches a drifted multiplier",
                lambda: C.assert_person_grain(reweighted, per, students))

    # 4. Grain. A duplicated member double-counts in every rate.
    duped = pd.concat([persons, persons.head(1)], ignore_index=True)
    expect_fail("grain catches a duplicated (household_id, person_serial_no)",
                lambda: C.assert_person_grain(duped, per, students))

    # 5. An unbanded age drops that person out of every by-band rate — quietly,
    # which is the failure mode this source exists to refuse.
    unbanded = persons.copy()
    unbanded.loc[unbanded.index[0], "age_band"] = None
    expect_fail("band check catches a person in no age band",
                lambda: C.assert_person_grain(unbanded, per, students))

    if asleep:
        raise SystemExit(f"\n{len(asleep)} guard(s) did not fire: {asleep}\n"
                         "The transform would accept a broken roster. Fix before loading.")
    print("\nall guards fire. The unmodified roster still passes:")
    C.assert_person_grain(persons, per, students)


if __name__ == "__main__":
    main()
