"""
Unified PLFS data parser. Handles all three input formats:

  input_kind="txt"  →  fixed-width source (CY2024, CY2025), sliced by byte_start/byte_end
  input_kind="csv"  →  pre-converted CSV with header row (annual_2018_19, calendar_2022)
  input_kind="tsv"  →  Nesstar-exported tab-separated, no header (most releases)

Reads the layout from the per-release consolidated CSV at
clean/layouts/{release_id}.csv (filtered by file_key), then writes one
parsed CSV per file at clean/{release_id}/{file_key}.csv with canonical
column names.

Usage:
    python3 scripts/parse_data.py                               # all releases
    python3 scripts/parse_data.py calendar_2024                 # one release
    python3 scripts/parse_data.py calendar_2024 --only chhv1    # one file
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from releases import RELEASES, ROOT


LAYOUTS_DIR = ROOT / "clean" / "layouts"


def load_layout(release_id: str, file_key: str):
    """Return list of dicts with keys: srl, field_name, byte_start, byte_end."""
    layout_csv = LAYOUTS_DIR / f"{release_id}.csv"
    out = []
    with layout_csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["file_key"] != file_key:
                continue
            fn = (row.get("field_name") or "").strip() or f"col_{row['srl']}"
            out.append({
                "srl": int(row["srl"]),
                "field_name": fn,
                "byte_start": int(row["byte_start"]),
                "byte_end": int(row["byte_end"]),
            })
    return out


def find_input_file(data_dir: Path, filename: str) -> Path | None:
    """Case-insensitive lookup for the data file."""
    target = filename.lower()
    for p in data_dir.glob("*"):
        if p.name.lower() == target:
            return p
    stem = Path(filename).stem.lower()
    for p in data_dir.glob("*"):
        if p.suffix.lower() in (".txt", ".csv", ".tsv") and p.stem.lower() == stem:
            return p
    return None


def _normalize_cell(s: str) -> str:
    """Strip whitespace + normalize float-style integers ('625717.0' → '625717').

    Some pre-converted CSVs (e.g., CY2022) store integers as floats.
    """
    s = s.strip()
    if s.endswith(".0"):
        head = s[:-2]
        if head and (head.isdigit() or (head.startswith("-") and head[1:].isdigit())):
            return head
    return s


# ---- Per-input-kind parsers ----------------------------------------------

def _parse_txt_fixed_width(src: Path, layout, expected_len: int, fout):
    """Fixed-width: slice each line by byte_start..byte_end (1-indexed inclusive)."""
    writer = csv.writer(fout)
    writer.writerow([f["field_name"] for f in layout])
    n = 0
    n_short = 0
    with src.open(encoding="latin-1") as fin:
        for line in fin:
            line = line.rstrip("\r\n")
            if not line:
                continue
            if len(line) < expected_len:
                line = line.ljust(expected_len)
                n_short += 1
            row = [line[f["byte_start"] - 1: f["byte_end"]].strip() for f in layout]
            writer.writerow(row)
            n += 1
    return n, n_short


def _parse_delimited(src: Path, layout, delim: str, has_header: bool, fout):
    """CSV or TSV input. Position-align with layout, write canonical headers."""
    writer = csv.writer(fout)
    field_names = [f["field_name"] for f in layout]
    n_expected = len(field_names)

    with src.open(encoding="latin-1", newline="") as fin:
        reader = csv.reader(fin, delimiter=delim)
        if has_header:
            src_headers = next(reader)
            n_src_cols = len(src_headers)
        else:
            n_src_cols = n_expected

        # Trim or pad headers to source column width
        if n_src_cols <= n_expected:
            out_headers = field_names[:n_src_cols]
        else:
            out_headers = field_names + [f"extra_{i}" for i in range(n_src_cols - n_expected)]
        writer.writerow(out_headers[:n_src_cols])

        n = 0
        n_short = 0
        n_long = 0
        for row in reader:
            if len(row) < n_src_cols:
                row = row + [""] * (n_src_cols - len(row))
                n_short += 1
            elif len(row) > n_src_cols:
                row = row[:n_src_cols]
                n_long += 1
            writer.writerow([_normalize_cell(c) for c in row])
            n += 1
    return n, n_short + n_long


# ---- Driver --------------------------------------------------------------

def parse_file(release_id: str, file_cfg: dict):
    cfg = RELEASES[release_id]
    layout = load_layout(release_id, file_cfg["key"])

    # Resolve source file path (data_filename for txt, csv_name for csv/tsv)
    filename = file_cfg.get("data_filename") or file_cfg.get("csv_name")
    if not filename:
        print(f"  SKIP {release_id}/{file_cfg['key']}: no data_filename/csv_name in config")
        return None

    src = find_input_file(cfg["data_dir"], filename)
    if src is None:
        print(f"  SKIP {release_id}/{file_cfg['key']}: missing {filename} in "
              f"{cfg['data_dir'].relative_to(ROOT)}")
        return None

    out = cfg["out_dir"] / f"{file_cfg['key']}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    kind = cfg["input_kind"]
    with out.open("w", newline="", encoding="utf-8") as fout:
        if kind == "txt":
            n, anomalies = _parse_txt_fixed_width(src, layout, file_cfg["byte_total"], fout)
        elif kind == "csv":
            n, anomalies = _parse_delimited(src, layout, delim=",", has_header=True, fout=fout)
        elif kind == "tsv":
            n, anomalies = _parse_delimited(src, layout, delim="\t", has_header=False, fout=fout)
        else:
            raise ValueError(f"Unknown input_kind: {kind}")

    rel_src = src.relative_to(ROOT)
    rel_out = out.relative_to(ROOT)
    anom_msg = f"  anomalies={anomalies}" if anomalies else ""
    print(f"  {file_cfg['key']:<8} {n:>9,} rows  src={rel_src}  out={rel_out}{anom_msg}")
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("releases", nargs="*", choices=list(RELEASES),
                    help="Release(s) to parse; default: all")
    ap.add_argument("--only", nargs="*", help="If given, parse only these file keys")
    args = ap.parse_args()

    targets = args.releases or list(RELEASES)
    grand = 0
    for rid in targets:
        cfg = RELEASES[rid]
        print(f"\n=== {rid} — {cfg['label']} ({cfg['input_kind']}) ===")
        for fc in cfg["files"]:
            if args.only and fc["key"] not in args.only:
                continue
            n = parse_file(rid, fc)
            if n:
                grand += n
    print(f"\nTotal rows written: {grand:,}")


if __name__ == "__main__":
    main()
