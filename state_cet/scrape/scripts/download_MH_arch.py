"""
Download all 59 institute × 4 round B.Arch CAP allotment PDFs from
arch2025.mahacet.org.in (the SPA portal — direct PDF URL pattern was
discovered via Chrome MCP inspection).

URL pattern: https://arch2025.mahacet.org.in/downloaddoc/cap<R>/<5digit>_final.pdf
"""
from __future__ import annotations
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "source" / "MH" / "architecture" / "pdfs"
OUT.mkdir(parents=True, exist_ok=True)

INSTITUTE_CODES = [
    "1116", "1289", "1298", "2113", "2599", "3018", "3019", "3244", "3245",
    "3246", "3247", "3248", "3249", "3251", "3427", "3450", "3451", "3468",
    "3472", "3478", "3483", "3484", "3488", "3495", "3496", "3516", "3727",
    "4214", "4216", "4218", "4635", "5158", "5445", "5457", "5673", "6009",
    "6245", "6261", "6263", "6264", "6532", "6533", "6534", "6535", "6536",
    "6538", "6742", "6818", "6837", "6840", "6880", "6883", "6885", "6895",
    "6896", "6897", "6919", "6920", "6959",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) "
    "Gecko/20100101 Firefox/128.0"
)


def fetch(round_num: int, code: str) -> tuple[str, int, int | str]:
    fname = f"MH_arch_CAP{round_num}_{code}.pdf"
    out = OUT / fname
    url = f"https://arch2025.mahacet.org.in/downloaddoc/cap{round_num}/{code}_final.pdf"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        out.write_bytes(data)
        return (fname, len(data), "ok")
    except Exception as e:
        return (fname, 0, str(e)[:60])


def main():
    tasks = [(r, c) for r in (1, 2, 3, 4) for c in INSTITUTE_CODES]
    print(f"Downloading {len(tasks)} PDFs in parallel (8 workers)…")
    t0 = time.time()
    ok = err = empty = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for fname, size, status in ex.map(lambda t: fetch(*t), tasks):
            if status != "ok":
                err += 1
                print(f"  ✗ {fname}: {status}")
            elif size < 5000:
                empty += 1
            else:
                ok += 1
    print(f"\n{ok} OK, {empty} empty (≤5KB likely 404), {err} errors  in {time.time()-t0:.1f}s")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
