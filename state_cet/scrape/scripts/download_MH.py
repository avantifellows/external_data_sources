"""
Download MH State CET Cell CAP cutoff PDFs (2025-26 cycle), one stream at a time.

Usage:
    python3 download_MH.py engineering    # fe2025.mahacet.org
    python3 download_MH.py pharmacy        # ph2025.mahacet.org
    python3 download_MH.py bdesign         # bdesigncap2025.mahacet.org
    python3 download_MH.py all             # all 3 ASP.NET-wrapper streams

(Streams using SPAs — agriculture / architecture / llb5 / bhmct — need
 a separate fetch path through Chrome MCP; not handled by this script.)

Re-run anytime — idempotent (overwrites existing files).
"""
from __future__ import annotations
import sys
from pathlib import Path

from _mh_streams import (
    DOWNLOADS, PORTALS, SOURCE_SUBDIR, fetch_pdf_via_wrapper,
)

HERE = Path(__file__).resolve().parent
SOURCE_ROOT = HERE.parent / "source" / "MH"


def download_stream(stream: str) -> int:
    """Download all PDFs for one stream. Returns exit code."""
    if stream not in DOWNLOADS:
        print(f"ERROR: stream '{stream}' is not configured in _mh_streams.DOWNLOADS")
        print(f"Available: {sorted(DOWNLOADS)}")
        return 1

    portal = PORTALS[stream]
    out_dir = SOURCE_ROOT / SOURCE_SUBDIR[stream]
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Downloading MH {stream} from {portal} → {out_dir.relative_to(HERE.parent)} ===")
    failures = []
    for fname, menu_id, desc in DOWNLOADS[stream]:
        out = out_dir / fname
        try:
            data = fetch_pdf_via_wrapper(portal, menu_id)
            out.write_bytes(data)
            print(f"  ✓ {fname:42s} {len(data)/1024:7.1f} KB  ({desc})")
        except Exception as e:
            print(f"  ✗ {fname:42s} FAILED: {e}")
            failures.append((fname, menu_id, str(e)))

    if failures:
        print(f"\n  {len(failures)} download(s) failed for {stream}:")
        for f, mid, err in failures:
            print(f"    {f} (MenuId={mid}): {err}")
        return 1
    print(f"  All {len(DOWNLOADS[stream])} downloads complete.")
    return 0


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)

    arg = sys.argv[1]
    if arg == "all":
        codes = [download_stream(s) for s in DOWNLOADS]
        sys.exit(max(codes))
    sys.exit(download_stream(arg))


if __name__ == "__main__":
    main()
