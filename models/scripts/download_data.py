"""FB-05 — download the Kaggle brain-tumour MRI dataset.

    python scripts/download_data.py

Uses the official ``kaggle`` CLI, so it needs Kaggle API credentials: a token
from https://www.kaggle.com/settings -> "Create New Token", saved as
``~/.kaggle/kaggle.json`` (the script explains this if the file is missing).

The default dataset is ``masoudnickparvar/brain-tumor-mri-dataset``: about 7,200
T1-weighted MRI slices across four classes (glioma, meningioma, pituitary,
no_tumor) with a ready-made Training/Testing split.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

DEFAULT_DATASET = "masoudnickparvar/brain-tumor-mri-dataset"
SERVICE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = SERVICE_ROOT / "data" / "brain_tumor"
KAGGLE_CREDENTIALS = Path.home() / ".kaggle" / "kaggle.json"


def _check_credentials() -> bool:
    return KAGGLE_CREDENTIALS.exists()


def _check_cli() -> bool:
    return shutil.which("kaggle") is not None


def _print_setup_help() -> None:
    print(
        "\nKaggle credentials are missing.\n"
        "\n"
        "  1. Sign in at https://www.kaggle.com and open Settings.\n"
        "  2. Under 'API', choose 'Create New Token'.\n"
        f"  3. Save the downloaded file as {KAGGLE_CREDENTIALS}\n"
        "  4. Install the CLI if you have not:  pip install kaggle\n"
        "\n"
        "The dataset also downloads fine by hand — put it in\n"
        f"  {DEFAULT_DEST}\n"
        "keeping the Training/ and Testing/ subdirectories intact.\n",
        file=sys.stderr,
    )


def download(dataset: str, dest: Path, *, force: bool) -> int:
    """Fetch and unzip the dataset. Returns a process exit code."""
    if not _check_cli():
        print("The `kaggle` CLI is not installed. Run: pip install kaggle", file=sys.stderr)
        _print_setup_help()
        return 2
    if not _check_credentials():
        _print_setup_help()
        return 2

    if dest.exists() and any(dest.iterdir()) and not force:
        print(f"Dataset already present at {dest}. Use --force to download again.")
        return 0

    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {dataset} into {dest} ...")
    result = subprocess.run(
        ["kaggle", "datasets", "download", "-d", dataset, "-p", str(dest), "--unzip"],
        check=False,
    )
    if result.returncode != 0:
        print("kaggle download failed; see the output above.", file=sys.stderr)
        return result.returncode

    # Older CLI versions leave a zip behind instead of honouring --unzip.
    for archive in dest.glob("*.zip"):
        print(f"Extracting {archive.name} ...")
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(dest)
        archive.unlink()

    print(f"Done. Dataset root: {dest}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="Kaggle dataset slug")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="Destination directory")
    parser.add_argument("--force", action="store_true", help="Download even if data exists")
    args = parser.parse_args()
    return download(args.dataset, args.dest, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
