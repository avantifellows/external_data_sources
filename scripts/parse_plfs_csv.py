"""
Parse PLFS releases that ship as already-converted CSVs (txt2csv output).

For each file in a release configured with `input_kind: "csv"`:
  - Load the source CSV
  - Position-align columns with the layout we just built (by index)
  - Rename columns to canonical names from clean/<release>/layout/<file>_layout.csv
  - Write to clean/<release>/<file>.csv

Usage:
    python3 scripts/parse_plfs_csv.py                          # all csv-input releases
    python3 scripts/parse_plfs_csv.py calendar_2022            # one release
    python3 scripts/parse_plfs_csv.py annual_2018_19 --only hhv1
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from releases import RELEASES, ROOT


def load_layout_field_names(layout_csv: Path) -> list[str]:
    out = []
    with layout_csv.open(encoding='utf-8') as f:
        for row in csv.DictReader(f):
            fn = (row.get('field_name') or '').strip()
            out.append(fn or f"col_{row['srl']}")
    return out


def parse_file(release_name: str, file_cfg: dict):
    cfg = RELEASES[release_name]
    layout_csv = cfg['layout_dir'] / f"{file_cfg['key']}_layout.csv"
    field_names = load_layout_field_names(layout_csv)
    n_expected = len(field_names)

    src = cfg['data_dir'] / file_cfg['csv_name']
    if not src.exists():
        print(f"  SKIP {release_name}/{file_cfg['key']}: missing {src}")
        return None

    out = cfg['out_dir'] / f"{file_cfg['key']}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    n_short = 0
    n_long = 0
    with src.open(encoding='latin-1', newline='') as fin, out.open('w', newline='', encoding='utf-8') as fout:
        reader = csv.reader(fin)
        writer = csv.writer(fout)
        src_headers = next(reader)
        n_src_cols = len(src_headers)

        if n_src_cols < n_expected:
            print(f"  WARN {file_cfg['key']}: source has {n_src_cols} cols, layout expects {n_expected}")
        elif n_src_cols > n_expected:
            print(f"  WARN {file_cfg['key']}: source has {n_src_cols} cols, layout expects {n_expected} — extra cols dropped")

        # Trim or pad field_names to source width
        out_headers = field_names[:n_src_cols] if n_src_cols <= n_expected else field_names + [f'extra_{i}' for i in range(n_src_cols - n_expected)]
        writer.writerow(out_headers[:n_src_cols])

        for row in reader:
            if len(row) < n_src_cols:
                row = row + [''] * (n_src_cols - len(row))
                n_short += 1
            elif len(row) > n_src_cols:
                row = row[:n_src_cols]
                n_long += 1
            # Strip whitespace AND normalize float-style integers ("625717.0" -> "625717")
            cleaned = []
            for cell in row:
                s = cell.strip()
                if s.endswith('.0'):
                    head = s[:-2]
                    if head and (head.isdigit() or (head.startswith('-') and head[1:].isdigit())):
                        s = head
                cleaned.append(s)
            writer.writerow(cleaned)
            n += 1

    rel_src = src.relative_to(ROOT)
    rel_out = out.relative_to(ROOT)
    short_msg = f" short_rows={n_short}" if n_short else ""
    long_msg = f" long_rows={n_long}" if n_long else ""
    print(f"  {file_cfg['key']:<8} {n:>9,} rows  src={rel_src}  out={rel_out}{short_msg}{long_msg}")
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('releases', nargs='*', help='Release(s) to parse; default: all CSV-input releases')
    ap.add_argument('--only', nargs='*', help='If given, parse only these file keys')
    args = ap.parse_args()

    targets = args.releases or [
        r for r, cfg in RELEASES.items() if cfg.get('input_kind') == 'csv'
    ]
    grand = 0
    for r in targets:
        cfg = RELEASES[r]
        if cfg.get('input_kind') != 'csv':
            print(f"  SKIP {r}: not a csv-input release")
            continue
        print(f"\n=== {r} — {cfg['label']} ===")
        for fc in cfg['files']:
            if args.only and fc['key'] not in args.only:
                continue
            n = parse_file(r, fc)
            if n: grand += n
    print(f"\nTotal rows written: {grand:,}")


if __name__ == '__main__':
    main()
