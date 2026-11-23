"""Check the packaged APK with the released client's naming and checksum parser."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def verify(source, tag, apk, checksums):
    source, apk, checksums = map(Path, (source, apk, checksums))
    update = (source / "lib/common/app_update.dart").read_text(encoding="utf-8")
    start, end = "String releaseAssetName(", "Future<String> fileSha256("
    asset_helpers = source / "lib/common/release_asset.dart"
    if asset_helpers.exists():
        start = "String updateAssetName("
        fields = re.search(r"(?ms)^typedef SelfUpdateAsset = \(\{.*?^\}\);", update)
        line = re.findall(r"(?m)^const appReleaseLine = ReleaseLine\.\w+;$", update)
        if fields is None or len(line) != 1:
            raise ValueError("Review changed upstream update target declaration")
        declarations = asset_helpers.read_text(encoding="utf-8") + "\n" + line[0] + "\n" + fields[0] + "\n"
        name_expression = "updateAssetName(args[0], (os: ReleaseOs.android, arch: ReleaseArch.arm64, form: null, extension: 'apk'))"
        checksums_expression = "updateChecksumsName(args[0])"
    else:
        names = re.findall(r"(?m)^const releaseChecksumsName = '[^']+';$", update)
        if len(names) != 1:
            raise ValueError("Review changed upstream checksum artifact name")
        declarations = names[0] + "\n"
        name_expression = "releaseAssetName(args[0], 'android-arm64-v8a.apk')"
        checksums_expression = "releaseChecksumsName"
    if update.count(start) != 1 or update.count(end) != 1:
        raise ValueError("Review changed upstream update artifact helpers")
    helpers = declarations + update[update.index(start):update.index(end)]
    constants = (source / "lib/common/constant.dart").read_text(encoding="utf-8")
    constants = re.findall(r"(?m)^const (?:appName|repository) = '[^']+';$", constants)
    if len(constants) != 2:
        raise ValueError("Expected the installed client's app and repository constants")
    exceptions = (source / "lib/common/exception.dart").read_text(encoding="utf-8")
    exception = re.search(r"(?ms)^final class ReleaseNotVerifiedException\b.*?^}", exceptions)
    if exception is None:
        raise ValueError("Review changed upstream release verification error")
    program = "import 'dart:convert';\nimport 'dart:io';\n" + "\n".join(constants) + "\n"
    program += helpers + exception[0] + r"""
void main(List<String> args) {
  final name = NAME_EXPRESSION;
  final checksums = CHECKSUMS_EXPRESSION;
  final expected = releaseChecksum(File(args[2]).readAsStringSync(), name);
  stdout.writeln(jsonEncode({
    'name': name,
    'checksums': checksums,
    'sha256': expected,
    'url': releaseAssetUri(args[0], name).toString(),
  }));
  if (expected == null) throw ReleaseNotVerifiedException(name);
  if (File(args[1]).uri.pathSegments.last != name) {
    throw StateError('Published APK name differs from the update request');
  }
  if (File(args[2]).uri.pathSegments.last != checksums) {
    throw StateError('Published checksum name differs from the update request');
  }
}
""".replace("NAME_EXPRESSION", name_expression).replace("CHECKSUMS_EXPRESSION", checksums_expression)
    with tempfile.TemporaryDirectory(prefix="flclash-update-contract-") as directory:
        runner = Path(directory) / "check.dart"
        runner.write_text(program, encoding="utf-8", newline="\n")
        result = subprocess.run(["dart", "--suppress-analytics", "run", str(runner), tag,
                                 str(apk.resolve()), str(checksums.resolve())],
                                text=True, encoding="utf-8", capture_output=True,
                                cwd=directory, env=dict(os.environ, CI="true"))
    if result.returncode:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    contract = json.loads(result.stdout)
    with apk.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != contract["sha256"]:
            raise ValueError("Packaged APK does not match the client's expected SHA-256")
    print(json.dumps(contract))


if __name__ == "__main__":
    verify(*sys.argv[1:])
