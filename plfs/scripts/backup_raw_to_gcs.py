"""
Back up and restore PLFS raw source files to/from GCS.

Each release's raw data directory is uploaded to:
  gs://avantifellows-external-data/plfs/raw/<release_id>/

This is a backup/handoff store only — it has no downstream role in parsing
or loading. It exists so that files downloaded from the gated MoSPI source
(microdata.gov.in) are not lost if local disk is wiped, and so that anyone
re-running the pipeline on a fresh machine can pull from GCS instead of
re-downloading from MoSPI.

All file formats (fixed-width TXT, TSV, CSV) are uploaded as-is.

Usage:
  # Back up one release after downloading from MoSPI:
  python3 scripts/backup_raw_to_gcs.py upload --release calendar_2025

  # Back up all releases that exist locally:
  python3 scripts/backup_raw_to_gcs.py upload

  # Restore a release to local raw/ (avoids re-downloading from MoSPI):
  python3 scripts/backup_raw_to_gcs.py download --release calendar_2025

  # See what would be uploaded/downloaded without touching GCS or disk:
  python3 scripts/backup_raw_to_gcs.py upload --dry-run
  python3 scripts/backup_raw_to_gcs.py download --release calendar_2025 --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from releases import RELEASES, ROOT

GCS_BUCKET = "avantifellows-external-data"
GCS_RAW_PREFIX = "plfs/raw"  # gs://{bucket}/{prefix}/{release_id}/...


def _gcs_prefix(release_id: str) -> str:
    return f"{GCS_RAW_PREFIX}/{release_id}"


def _iter_releases(only: str | None) -> list[str]:
    if only:
        if only not in RELEASES:
            raise SystemExit(f"Unknown release {only!r}. Known: {sorted(RELEASES)}")
        return [only]
    return list(RELEASES)


# ─── Upload ─────────────────────────────────────────────────────────────────

def _upload_release(release_id: str, client, dry_run: bool) -> None:
    data_dir: Path = RELEASES[release_id]["data_dir"]
    if not data_dir.exists():
        print(f"  [{release_id}] skipped — local data_dir not found: {data_dir}")
        return

    files = sorted(f for f in data_dir.rglob("*") if f.is_file())
    if not files:
        print(f"  [{release_id}] skipped — data_dir is empty: {data_dir}")
        return

    prefix = _gcs_prefix(release_id)
    print(f"  [{release_id}] {len(files)} file(s) → gs://{GCS_BUCKET}/{prefix}/")
    for f in files:
        rel = f.relative_to(data_dir)
        blob_name = f"{prefix}/{rel}"
        if dry_run:
            print(f"    [dry-run] {f.name} → gs://{GCS_BUCKET}/{blob_name}")
        else:
            bucket = client.bucket(GCS_BUCKET)
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(str(f))
            print(f"    uploaded {f.name} → gs://{GCS_BUCKET}/{blob_name}")


# ─── Download ────────────────────────────────────────────────────────────────

def _download_release(release_id: str, client, dry_run: bool) -> None:
    data_dir: Path = RELEASES[release_id]["data_dir"]
    prefix = _gcs_prefix(release_id)

    bucket = client.bucket(GCS_BUCKET) if not dry_run else None
    blobs = list(client.list_blobs(GCS_BUCKET, prefix=prefix + "/")) if not dry_run else []

    if not dry_run and not blobs:
        print(f"  [{release_id}] skipped — nothing found at gs://{GCS_BUCKET}/{prefix}/")
        return

    print(f"  [{release_id}] gs://{GCS_BUCKET}/{prefix}/ → {data_dir}")
    if dry_run:
        print(f"    [dry-run] would download gs://{GCS_BUCKET}/{prefix}/ → {data_dir}")
        return

    data_dir.mkdir(parents=True, exist_ok=True)
    for blob in blobs:
        rel = blob.name[len(prefix) + 1:]  # strip "plfs/raw/<release_id>/"
        dest = data_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(dest))
        print(f"    downloaded {rel} → {dest}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["upload", "download"], help="upload: local → GCS. download: GCS → local.")
    ap.add_argument("--release", default=None, help="Process one release only (e.g. calendar_2025)")
    ap.add_argument("--dry-run", action="store_true", help="Print plan; don't touch GCS or disk")
    args = ap.parse_args()

    release_ids = _iter_releases(args.release)

    client = None
    if not args.dry_run or args.action == "download":
        from google.cloud import storage
        client = storage.Client()

    action_label = "dry-run" if args.dry_run else args.action
    print(f"PLFS raw backup — {action_label}   bucket: gs://{GCS_BUCKET}/{GCS_RAW_PREFIX}/")

    for rid in release_ids:
        if args.action == "upload":
            _upload_release(rid, client, args.dry_run)
        else:
            _download_release(rid, client, args.dry_run)

    print("✓ done.")


if __name__ == "__main__":
    main()
