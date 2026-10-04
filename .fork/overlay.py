"""Apply the fork's source changes and verify the resulting build policy."""
import hashlib
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
CORE_URL = "https://github.com/aldington-david/mihomo"
OVERLAY_FILES = ("app.patch", "firebase-native-symbols.patch", "overlay.py")


def fingerprint():
    digest = hashlib.sha256()
    for name in OVERLAY_FILES:
        digest.update(name.encode() + b"\0" + (HERE / name).read_text(encoding="utf-8").encode())
    return digest.hexdigest()


def replace_literal(text, old, new, *, optional=False):
    count = text.count(old) + text.count(new)
    if count != 1 and not (optional and count == 0):
        raise ValueError(f"Expected one occurrence of {old!r} or its fork value; found {count}")
    return text.replace(old, new)


def verify(source):
    source = Path(source)
    about = (source / "lib/views/about.dart").read_text(encoding="utf-8")
    if about.count(CORE_URL) != 1 or "chen08209/Clash.Meta" in about:
        raise ValueError("About page must link only to the custom core")
    constants = (source / "lib/common/constant.dart").read_text(encoding="utf-8")
    if constants.count("'aldington-david/FlClash'") != 1 or "'chen08209/FlClash'" in constants:
        raise ValueError("App update repository is not the fork")
    app = (source / "android/app/build.gradle.kts").read_text(encoding="utf-8")
    for required in ('applicationId = "com.github.aldingtondavid.flclash"', 'storeType = "PKCS12"',
                     'error("Release signing is required for the AnyTLS REALITY fork")'):
        if required not in app:
            raise ValueError("Missing Android identity/signing constraint: " + required)
    properties = (source / "android/gradle.properties").read_text(encoding="utf-8")
    if properties.splitlines().count("force-version-code-ignoring-abi=true") != 1:
        raise ValueError("Android versionCode must not include an ABI offset")
    tracked = subprocess.check_output(["git", "ls-files", "-z", "--", "android"], cwd=source).decode().split("\0")
    for name in filter(None, tracked):
        if name.endswith((".gradle", ".gradle.kts")):
            pattern = r"firebase|crashlytics|google-services"
        elif "/src/main/" in name and name.endswith((".kt", ".java", ".xml")):
            pattern = r"com\.google\.firebase|FirebaseApp|FirebaseCrashlytics"
        else:
            continue
        for number, line in enumerate((source / name).read_text(encoding="utf-8").splitlines(), 1):
            if not line.lstrip().startswith("//") and re.search(pattern, line, re.IGNORECASE):
                raise ValueError(f"Firebase executable reference remains at {name}:{number}: {line.strip()}")


def apply(source):
    source = Path(source)
    patches = [HERE / "app.patch"]
    app = (source / "android/app/build.gradle.kts").read_text(encoding="utf-8")
    if "CrashlyticsExtension" in app or "uploadCrashlytics" in app:
        patches.append(HERE / "firebase-native-symbols.patch")
    for patch in patches:
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=source, check=True)
        subprocess.run(["git", "apply", str(patch)], cwd=source, check=True)
    replacements = {
        "lib/common/constant.dart": [("'chen08209/FlClash'", "'aldington-david/FlClash'", False)],
        "lib/views/about.dart": [
            ("'https://github.com/chen08209/Clash.Meta/tree/FlClash'", f"'{CORE_URL}'", False),
            ("'github.com/chen08209/Clash.Meta'", "'github.com/aldington-david/mihomo'", True),
        ],
    }
    for name, changes in replacements.items():
        path = source / name
        text = path.read_text(encoding="utf-8")
        for old, new, optional in changes:
            text = replace_literal(text, old, new, optional=optional)
        path.write_text(text, encoding="utf-8", newline="\n")
    settings = source / "android/settings.gradle.kts"
    text = settings.read_text(encoding="utf-8")
    for plugin in ("com.google.gms.google-services", "com.google.firebase.crashlytics"):
        text, count = re.subn(r'(?m)^[ \t]*id\("' + re.escape(plugin) + r'"\)[^\r\n]*\r?\n', "", text)
        if count > 1:
            raise ValueError("Duplicate plugin declaration: " + plugin)
    settings.write_text(text, encoding="utf-8", newline="\n")
    verify(source)


if __name__ == "__main__":
    {"apply": apply, "verify": verify}[sys.argv[1]](sys.argv[2])
