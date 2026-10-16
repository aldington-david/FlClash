"""Apply the fork's source changes and verify the resulting build policy."""
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
CORE_URL = "https://github.com/aldington-david/mihomo"
OVERLAY_FILES = ("app.patch", "firebase-native-symbols.patch", "overlay.py", "fork_update_test.dart.in")
UPDATE_CHECK = r"""final body = RELEASE['body'] as String?;
int? remoteBuild;
if (body == null || body.isEmpty) {
  final tag = Uri.encodeComponent(RELEASE['tag_name'] as String);
  final response = await dio.get<String>(
    'https://github.com/$repository/releases/download/$tag/BUILD-PROVENANCE.json',
    options: Options(responseType: ResponseType.plain),
  );
  final metadata = jsonDecode(response.data ?? '');
  final versionCode =
      metadata is Map<String, dynamic> ? metadata['version_code'] : null;
  if (versionCode is int) {
    remoteBuild = versionCode;
  }
} else {
  final releaseBuild = RegExp(
    r'^Android version code: (\d+)$',
    multiLine: true,
  ).firstMatch(body);
  remoteBuild = int.tryParse(releaseBuild?.group(1) ?? '');
}
if (remoteBuild == null || remoteBuild <= 0 || remoteBuild >= 2100000000) {
  throw const FormatException('Missing or invalid Android version code');
}
final hasUpdate =
    remoteBuild > int.parse(globalState.packageInfo.buildNumber);"""


def replace_update_check(text):
    matches = []
    for release, cast, indent in (("data", "", "      "), ("release", " as String", "    ")):
        old = (f"{indent}final remoteVersion = {release}['tag_name']{cast};\n"
               f"{indent}final version = globalState.packageInfo.version;\n"
               f"{indent}final hasUpdate =\n"
               f"{indent}    compareVersions(remoteVersion.replaceAll('v', ''), version) > 0;")
        matches.extend([(old, release, indent)] * text.count(old))
    if len(matches) != 1 or text.count("Future<Map<String, dynamic>?> checkForUpdate() async {") != 1:
        raise ValueError("Unknown or ambiguous upstream update-check structure")
    old, release, indent = matches[0]
    text = text.replace(old, textwrap.indent(UPDATE_CHECK.replace("RELEASE", release), indent))
    if "import 'dart:convert';" not in text:
        text = replace_literal(text, "import 'dart:async';", "import 'dart:async';\nimport 'dart:convert';")
    return text


def fingerprint():
    digest = hashlib.sha256()
    for name in OVERLAY_FILES:
        digest.update(name.encode() + b"\0" + (HERE / name).read_text(encoding="utf-8").encode())
    return digest.hexdigest()


def replace_literal(text, old, new, *, optional=False):
    new_count = text.count(new)
    count = text.replace(new, "").count(old) + new_count
    if count != 1 and not (optional and count == 0):
        raise ValueError(f"Expected one occurrence of {old!r} or its fork value; found {count}")
    return text if new_count else text.replace(old, new)


def verify(source):
    source = Path(source)
    request = (source / "lib/common/request.dart").read_text(encoding="utf-8")
    compact = "".join(request.split())
    comparisons = sum(compact.count("".join(UPDATE_CHECK.replace("RELEASE", value).split()))
                      for value in ("data", "release"))
    if comparisons != 1 or "compareVersions(" in request or request.count("import 'dart:convert';") != 1:
        raise ValueError("Fork updates must compare verified Android version codes")
    strings = ET.parse(source / "android/common/src/main/res/values/strings.xml").getroot()
    if [item.text for item in strings.findall("string[@name='app_name']")] != ["IFlClash"]:
        raise ValueError("Android display name must be IFlClash")
    about = (source / "lib/views/about.dart").read_text(encoding="utf-8")
    if about.count(CORE_URL) != 1 or "chen08209/Clash.Meta" in about:
        raise ValueError("About page must link only to the custom core")
    constants = (source / "lib/common/constant.dart").read_text(encoding="utf-8")
    if constants.count("'aldington-david/FlClash'") != 1 or "'chen08209/FlClash'" in constants:
        raise ValueError("App update repository is not the fork")
    if "const appName = 'FlClash';" not in constants:
        raise ValueError("The existing backup directory and internal app name must remain unchanged")
    for name in ("lib/application.dart", "lib/views/about.dart"):
        if (source / name).read_text(encoding="utf-8").count("globalState.packageInfo.appName") != 1:
            raise ValueError("UI must use the installed app display name: " + name)
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
    request = source / "lib/common/request.dart"
    text = request.read_text(encoding="utf-8")
    request.write_text(replace_update_check(text), encoding="utf-8", newline="\n")
    tests = (HERE / "fork_update_test.dart.in").read_text(encoding="utf-8")
    if "Future<Map<String, dynamic>> latestRelease() async {" in text:
        tests = tests.replace("const hasReleaseRedirect = false;", "const hasReleaseRedirect = true;")
    target = source / "test/common/fork_update_test.dart"
    if target.exists():
        raise ValueError("Upstream already defines the fork update test")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(tests, encoding="utf-8", newline="\n")
    replacements = {
        "lib/application.dart": [("title: appName,", "title: globalState.packageInfo.appName,", False)],
        "lib/common/constant.dart": [("'chen08209/FlClash'", "'aldington-david/FlClash'", False)],
        "lib/views/about.dart": [
            ("appName,", "globalState.packageInfo.appName,", False),
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
