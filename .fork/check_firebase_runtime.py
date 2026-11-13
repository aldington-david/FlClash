"""Reject telemetry SDKs without removing barcode scanning's support libraries."""
from pathlib import Path
import re
import sys

BARCODE_SUPPORT = {"firebase-annotations", "firebase-components", "firebase-encoders",
                   "firebase-encoders-json", "firebase-encoders-proto"}


def verify(report):
    firebase = set(re.findall(r"com\.google\.firebase:([\w.-]+):", report))
    measurement = set(re.findall(r"com\.google\.android\.gms:(play-services-measurement[\w.-]*):", report))
    rejected = (firebase - BARCODE_SUPPORT) | measurement
    if rejected:
        raise ValueError("Unexpected Firebase/Analytics runtime SDKs: " + ", ".join(sorted(rejected)))
    print("No Firebase telemetry SDKs; barcode support modules: " + ", ".join(sorted(firebase)))


if __name__ == "__main__":
    verify(Path(sys.argv[1]).read_text(encoding="utf-8"))
