#!/usr/bin/env python3
"""Check all apksigner signer certificates, including SDK-range (v3.1) labels."""
import hashlib
import os
from pathlib import Path
import re
import sys


def verify(report, expected):
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise ValueError("Missing or invalid ANDROID_CERTIFICATE_SHA256 repository variable")
    certificates = {value.lower() for value in re.findall(
        r"^Signer [^\r\n]+ certificate SHA-256 digest: ([0-9a-fA-F]{64})[ \t]*\r?$",
        report, re.MULTILINE)}
    if certificates != {expected.lower()}:
        raise ValueError(f"APK certificate mismatch: actual={sorted(certificates)}, expected={expected.lower()}")
    print(f"Verified certificate SHA-256: {expected.lower()}")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        digest = "a" * 64
        for label in ("#1", "(minSdkVersion=28, maxSdkVersion=32)", "(minSdkVersion=33, maxSdkVersion=2147483647)"):
            verify(f"Signer {label} certificate SHA-256 digest: {digest}\r\n", digest)
        for report in ("", f"Signer #1 certificate SHA-256 digest: {'b' * 64}",
                       f"Signer #1 certificate SHA-256 digest: {digest}\nSigner #2 certificate SHA-256 digest: {'b' * 64}"):
            try:
                verify(report, digest)
                raise AssertionError("Accepted a missing or different signer")
            except ValueError:
                pass
        print("Signing verification self-test passed")
    elif sys.argv[1] == "--certificate":
        actual = hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()
        print(f"Restored keystore certificate SHA-256: {actual}")
        verify(f"Signer #1 certificate SHA-256 digest: {actual}", os.environ.get("EXPECTED_CERTIFICATE_SHA256", ""))
    else:
        verify(Path(sys.argv[1]).read_text(), os.environ.get("EXPECTED_CERTIFICATE_SHA256", ""))
