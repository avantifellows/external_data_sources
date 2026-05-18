"""
Write per-variable code-map CSVs sourced from PLFS Instruction Manual Vol I.

Each code map has columns: code, description.
Codes are stored as zero-padded strings (matches what the parser emits when it
slices fixed-width fields).

Source: raw/docs/InstructionManual_VolI.pdf  (extracted to ...VolI.txt)
Section refs cite paragraph numbers in Chapter Three of Vol I.
"""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "codemaps"
OUT.mkdir(exist_ok=True)


def write(name, source_ref, rows):
    """rows = list of (code, description). All codes coerced to strings as-given."""
    p = OUT / f"{name}.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code", "description"])
        for code, desc in rows:
            w.writerow([str(code), desc])
    print(f"  {name:32s} {len(rows):>4} codes  ({source_ref})")


# --- Block 1 (FSU) and survey identifiers ---------------------------------

write(
    "sector",
    "Vol I §1.4 / layout",
    [("1", "Rural"), ("2", "Urban")],
)

write(
    "sub_sample",
    "Vol I §1.2.12 / layout",
    [("1", "Sub-sample 1"), ("2", "Sub-sample 2")],
)

write(
    "quarter",
    "README §A / layout",
    [
        ("1", "Q1: Jul-Sep"),
        ("2", "Q2: Oct-Dec"),
        ("3", "Q3: Jan-Mar"),
        ("4", "Q4: Apr-Jun"),
    ],
)

write(
    "visit",
    "README §A / layout",
    [
        ("1", "Visit 1 (first visit)"),
        ("2", "Visit 2 (revisit 1)"),
        ("3", "Visit 3 (revisit 2)"),
        ("4", "Visit 4 (revisit 3)"),
    ],
)

# --- Block 3: Household characteristics -----------------------------------

write(
    "household_type_rural",
    "Vol I §3.3.2",
    [
        ("1", "Self-employed in agriculture"),
        ("2", "Self-employed in non-agriculture"),
        ("3", "Regular wage/salary earning"),
        ("4", "Casual labour in agriculture"),
        ("5", "Casual labour in non-agriculture"),
        ("9", "Others"),
    ],
)

write(
    "household_type_urban",
    "Vol I §3.3.2",
    [
        ("1", "Self-employed"),
        ("2", "Regular wage/salary earning"),
        ("3", "Casual labour"),
        ("9", "Others"),
    ],
)

write(
    "religion",
    "Vol I §3.3.3",
    [
        ("1", "Hinduism"),
        ("2", "Islam"),
        ("3", "Christianity"),
        ("4", "Sikhism"),
        ("5", "Jainism"),
        ("6", "Buddhism"),
        ("7", "Zoroastrianism"),
        ("9", "Others"),
    ],
)

write(
    "social_group",
    "Vol I §3.3.4",
    [
        ("1", "Scheduled Tribe"),
        ("2", "Scheduled Caste"),
        ("3", "Other Backward Classes"),
        ("9", "Others"),
    ],
)

# --- Block 4: Demographic particulars -------------------------------------

write(
    "membership_status",
    "Vol I §3.4.3",
    [
        ("1", "Yes - also a member during earlier visit(s)"),
        ("2", "Yes - new member by birth"),
        ("3", "Yes - new member, others"),
        ("4", "No - due to death"),
        ("5", "No - others"),
    ],
)

write(
    "relation_to_head",
    "Vol I §3.4.4",
    [
        ("1", "Self"),
        ("2", "Spouse of head"),
        ("3", "Married child"),
        ("4", "Spouse of married child"),
        ("5", "Unmarried child"),
        ("6", "Grandchild"),
        ("7", "Father/mother/father-in-law/mother-in-law"),
        ("8", "Brother/sister/brother-in-law/sister-in-law/other relatives"),
        ("9", "Servant/employees/other non-relatives"),
    ],
)

write(
    "sex",
    "Vol I §3.4.5",
    [("1", "Male"), ("2", "Female"), ("3", "Transgender")],
)

write(
    "marital_status",
    "Vol I §3.4.7",
    [
        ("1", "Never married"),
        ("2", "Currently married"),
        ("3", "Widowed"),
        ("4", "Divorced/separated"),
    ],
)

write(
    "general_education",
    "Vol I §3.4.9",
    [
        ("01", "Not literate"),
        ("02", "Literate without formal schooling: EGS/NFEC/AEC"),
        ("03", "Literate without formal schooling: TLC"),
        ("04", "Literate without formal schooling: others"),
        ("05", "Literate: below primary"),
        ("06", "Literate: primary"),
        ("07", "Literate: middle"),
        ("08", "Literate: secondary"),
        ("10", "Literate: higher secondary"),
        ("11", "Literate: diploma/certificate course"),
        ("12", "Literate: graduate"),
        ("13", "Literate: postgraduate and above"),
    ],
)

write(
    "technical_education",
    "Vol I §3.4.10",
    [
        ("01", "No technical education"),
        ("02", "Technical degree in agriculture"),
        ("03", "Technical degree in engineering/technology"),
        ("04", "Technical degree in medicine"),
        ("05", "Technical degree in crafts"),
        ("06", "Technical degree in other subjects"),
        ("07", "Diploma/certificate (below graduate) in agriculture"),
        ("08", "Diploma/certificate (below graduate) in engineering/technology"),
        ("09", "Diploma/certificate (below graduate) in medicine"),
        ("10", "Diploma/certificate (below graduate) in crafts"),
        ("11", "Diploma/certificate (below graduate) in other subjects"),
        ("12", "Diploma/certificate (graduate+) in agriculture"),
        ("13", "Diploma/certificate (graduate+) in engineering/technology"),
        ("14", "Diploma/certificate (graduate+) in medicine"),
        ("15", "Diploma/certificate (graduate+) in crafts"),
        ("16", "Diploma/certificate (graduate+) in other subjects"),
    ],
)

write(
    "vocational_training_received",
    "Vol I §3.4.13",
    [
        ("1", "Received formal vocational/technical training"),
        ("2", "Hereditary"),
        ("3", "Self-learning"),
        ("4", "Learning on the job"),
        ("5", "Other"),
        ("9", "Did not receive any vocational/technical training"),
    ],
)

# --- Block 4.1: Vocational/technical training particulars -----------------

write(
    "vt_field_of_training",
    "Vol I §3.4.1.3",
    [
        ("01", "Aerospace and aviation"),
        ("02", "Agriculture, non-crop based agriculture, food processing"),
        ("03", "Allied manufacturing - gems and jewellery, leather, rubber, furniture, fittings, printing"),
        ("04", "Artisan/craftsman/handicraft/creative arts and cottage based production"),
        ("05", "Automotive"),
        ("06", "Beauty and wellness"),
        ("07", "Chemical engineering, hydrocarbons, chemicals, petrochemicals"),
        ("08", "Civil engineering - construction, plumbing, paints and coatings"),
        ("09", "Electrical, power and electronics"),
        ("10", "Healthcare and life sciences"),
        ("11", "Hospitality and tourism"),
        ("12", "Iron and steel, mining, earthmoving and infra building"),
        ("13", "IT-ITeS"),
        ("14", "Logistics"),
        ("15", "Mechanical engineering - capital goods, strategic manufacturing"),
        ("16", "Media - journalism, mass communication and entertainment"),
        ("17", "Office and business related work"),
        ("18", "Security"),
        ("19", "Telecom"),
        ("20", "Textiles and handlooms, apparels"),
        ("21", "Childcare, nutrition, pre-school and crèche"),
        ("99", "Others"),
    ],
)

write(
    "vt_duration",
    "Vol I §3.4.1.4",
    [
        ("1", "Less than 3 months"),
        ("2", "3 months to less than 6 months"),
        ("3", "6 months to less than 12 months"),
        ("4", "12 months to less than 18 months"),
        ("5", "18 months to less than 24 months"),
        ("6", "24 months or more"),
    ],
)

write(
    "vt_type_of_training",
    "Vol I §3.4.1.5",
    [
        ("1", "On the job"),
        ("2", "Other than on the job - part time"),
        ("3", "Other than on the job - full time"),
    ],
)

write(
    "vt_funding_source",
    "Vol I §3.4.1.6",
    [
        ("1", "Government sources"),
        ("2", "Own funding"),
        ("9", "Others"),
    ],
)

# --- Block 5.1: Usual principal/subsidiary activity status ----------------

write(
    "activity_status",
    "Vol I §3.5.1.7 (also CWS — Block 6 same codes plus CWS-specific)",
    [
        ("11", "Worked in household enterprise (self-employed) as own account worker"),
        ("12", "Worked in household enterprise (self-employed) as employer"),
        ("21", "Worked as helper in household enterprise (unpaid family worker)"),
        ("31", "Worked as regular salaried/wage employee"),
        ("41", "Worked as casual wage labour: in public works"),
        ("42", "Worked as casual wage labour: in MGNREG public works (CWS only)"),
        ("51", "Worked as casual wage labour: in other types of work"),
        ("61", "Did not work though there was work in HH enterprise (CWS only)"),
        ("62", "Did not work due to sickness though there was work (CWS only)"),
        ("71", "Did not work due to other reasons though there was work (CWS only)"),
        ("72", "Did not work but was seeking work (CWS only)"),
        ("81", "Did not work but was seeking and/or available for work"),
        ("82", "Did not work but was available for work (CWS only)"),
        ("91", "Attended educational institutions"),
        ("92", "Attended domestic duties only"),
        ("93", "Attended domestic duties and engaged in free collection / sewing / weaving for HH use"),
        ("94", "Rentiers, pensioners, remittance recipients, etc."),
        ("95", "Not able to work due to disability"),
        ("97", "Others (including begging, prostitution, etc.)"),
        ("98", "Children of age 0-4 years (CWS-specific extension; varies)"),
    ],
)

write(
    "enterprise_type",
    "Vol I §3.5.1.16",
    [
        ("01", "Proprietary - male"),
        ("02", "Proprietary - female"),
        ("03", "Partnership with members from same household"),
        ("04", "Partnership with members from different household"),
        ("05", "Government/local body"),
        ("06", "Public Sector Enterprises"),
        ("07", "Autonomous Bodies"),
        ("08", "Public/Private limited company"),
        ("10", "Co-operative societies"),
        ("11", "Trust/other non-profit institutions"),
        ("12", "Employer's households (private households employing maid, watchman, cook, etc.)"),
        ("19", "Others"),
    ],
)

write(
    "no_of_workers",
    "Vol I §3.5.1.17",
    [
        ("1", "Less than 6"),
        ("2", "6 to less than 10"),
        ("3", "10 to less than 20"),
        ("4", "20 and above"),
        ("9", "Not known"),
    ],
)

write(
    "job_contract",
    "Vol I §3.5.1.19",
    [
        ("1", "No written job contract"),
        ("2", "Written job contract for 1 year or less"),
        ("3", "Written job contract for more than 1 year to 3 years"),
        ("4", "Written job contract for more than 3 years"),
    ],
)

write(
    "paid_leave_eligible",
    "Vol I §3.5.1.20",
    [("1", "Yes"), ("2", "No")],
)

write(
    "social_security",
    "Vol I §3.5.1.21",
    [
        ("1", "Only PF/pension"),
        ("2", "Only gratuity"),
        ("3", "Only health care/maternity benefits"),
        ("4", "Only PF/pension and gratuity"),
        ("5", "Only PF/pension and health care/maternity benefits"),
        ("6", "Only gratuity and health care/maternity benefits"),
        ("7", "PF/pension AND gratuity AND health care/maternity benefits"),
        ("8", "Not eligible for any of the above"),
        ("9", "Not known"),
    ],
)

write(
    "product_destination",
    "Vol I §3.5.1.22",
    [
        ("1", "For own consumption only; did not intend to sell"),
        ("2", "For own consumption + intended to sell <50%"),
        ("3", "For own consumption + intended to sell ≥50%"),
        ("4", "Entire produce is for selling"),
    ],
)

print("\nDone — all code maps written to codemaps/")
