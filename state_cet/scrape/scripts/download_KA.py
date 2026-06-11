"""
Download KEA UGCET cutoff PDFs (Karnataka).

KEA publishes consolidated annual cutoff PDFs for each stream × variant
(General / Hyderabad-Karnataka 371J) for the LAST main round only:
  - R2_FIN — Round 2 Final cutoff
  - EXT_RND — Extended Round (the final round, after Round 2)

Per-round R1 cutoff is NOT published as a PDF (data is on cutoffanalyser.aspx).

For 2025-26 admissions: KEA has not yet published a final cutoff PDF (the
flat URL pattern returns 404 for all expected names). We download 2024-25
EXT_RND data as a proxy until 2025 is published — same pattern used by the
medical-side Rajasthan scrape.

Streams covered:
  - engineering (engg)
  - pharmacy (pharma)
  - agriculture (agri)
  - architecture (arch)  [if available]
  - B.Sc Nursing (BSCNURS)

Variants:
  - GEN: General quota (rest of Karnataka)
  - HK: Hyderabad-Karnataka quota (Article 371J — 7 NE Karnataka districts)

Output: PDFs saved to source/KA/<stream>/.
"""
from __future__ import annotations
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_ROOT = HERE.parent / "source" / "KA"

STREAMS = {
    "engg":     "engineering",
    "agri":     "agriculture",
    "pharma":   "pharmacy",
    "BSCNURS":  "nursing",
    # arch — try too but may not exist with same prefix
    "arch":     "architecture",
}

VARIANTS = ["GEN", "HK"]
ROUNDS = ["R2_FIN", "EXT_RND"]   # last round = EXT_RND
YEAR = 2024  # 2025 not yet published; using 2024 as proxy

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) "
    "Gecko/20100101 Firefox/128.0"
)


def try_download(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if data[:4] == b"%PDF":
            return data
    except Exception:
        pass
    return None


def main():
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    n_ok = 0
    for stream, subdir in STREAMS.items():
        out_dir = SOURCE_ROOT / subdir
        out_dir.mkdir(parents=True, exist_ok=True)
        for variant in VARIANTS:
            for rnd in ROUNDS:
                # KEA's filename casing varies per stream:
                # engg/pharma/BSCNURS use UPPER, agri uses lower, arch unknown
                if stream in ("engg", "pharma", "BSCNURS"):
                    upper = stream.upper()
                    candidates = [
                        f"{upper}_CUTOFF_{YEAR}_{variant}_{rnd}",
                        f"{upper}_CUTOFF_{YEAR}_{variant}_{rnd}kannada",
                    ]
                elif stream == "agri":
                    candidates = [
                        f"{stream}_cutoff_{YEAR}_{variant.lower()}_{rnd.lower()}",
                        f"{stream}_cutoff_{YEAR}_{variant.lower()}_{rnd.lower()}kannada",
                        f"{stream}_cutoff_{YEAR}_{variant.lower()}_{rnd.lower()}_1",
                    ]
                elif stream == "arch":
                    candidates = [
                        f"{stream.upper()}_CUTOFF_{YEAR}_{variant}_{rnd}",
                        f"{stream}_cutoff_{YEAR}_{variant.lower()}_{rnd.lower()}",
                    ]
                else:
                    continue

                downloaded = False
                for fname in candidates:
                    url = f"https://cetonline.karnataka.gov.in/keawebentry456/ugcet{YEAR}/{fname}.pdf"
                    data = try_download(url)
                    if data:
                        out_path = out_dir / f"KA_{stream}_{YEAR}_{variant}_{rnd}.pdf"
                        out_path.write_bytes(data)
                        rel = str(out_path.relative_to(HERE.parent))
                        print(f"  ✓ {rel:60s} {len(data)/1024:>7.1f} KB")
                        n_ok += 1
                        downloaded = True
                        break
                if not downloaded:
                    print(f"  ✗ {stream:8s} {variant:3s} {rnd:8s} — no working URL "
                          f"(tried {len(candidates)} variants)")
    print(f"\n{n_ok} downloads OK")


if __name__ == "__main__":
    main()
