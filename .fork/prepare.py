#!/usr/bin/env python3
"""Pin both releases, preserve FlClash's core APIs, and tag reproducible sources."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from overlay import apply as apply_overlay, fingerprint as overlay_fingerprint, verify as verify_overlay

UPSTREAM = "chen08209/FlClash"
CORE = "aldington-david/mihomo"
REPO = "aldington-david/FlClash"
ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None, env=None, strip=True):
    result = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed: {result.stderr}")
    return result.stdout.strip() if strip else result.stdout


def api(path, missing_ok=False):
    result = subprocess.run(["gh", "api", path], text=True, capture_output=True)
    if result.returncode:
        if missing_ok and "HTTP 404" in result.stderr:
            return None
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def stable_tag(release):
    tag = release["tag_name"]
    if release.get("draft") or release.get("prerelease") or not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError(f"Expected a stable semantic version, got {tag!r}")
    return tag


def output(**values):
    for key, value in values.items():
        print(f"{key}={value}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as file:
            for key, value in values.items():
                file.write(f"{key}={value}\n")


def auth_env():
    token = base64.b64encode(f"x-access-token:{os.environ['GH_TOKEN']}".encode()).decode()
    return dict(os.environ, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {token}")


def main():
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        last_commit = int(run("git", "log", "-1", "--format=%ct", cwd=ROOT))
        if time.time() - last_commit > 30 * 86400:
            if run("git", "status", "--porcelain", cwd=ROOT):
                raise ValueError("Refusing a keepalive commit with a dirty maintenance checkout")
            run("git", "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com", "commit", "--allow-empty", "-m", "Keep upstream release synchronization active", cwd=ROOT)
            run("git", "push", f"https://github.com/{REPO}.git", f"HEAD:refs/heads/{os.environ['GITHUB_REF_NAME']}", cwd=ROOT, env=auth_env())
    app_tag = stable_tag(api(f"repos/{UPSTREAM}/releases/latest"))
    core_release = api(f"repos/{CORE}/releases/latest", missing_ok=True)
    if core_release is None:
        output(build="false", reason="Waiting for the first published custom mihomo release")
        return
    core_tag = stable_tag(core_release)
    release_tag = f"{app_tag}-anytls-{core_tag}"
    existing = api(f"repos/{REPO}/releases/tags/{release_tag}", missing_ok=True)
    if existing and not existing["draft"]:
        required = {f"FlClash-{app_tag[1:]}-android-arm64-v8a.apk", "SHA256SUMS", "BUILD-PROVENANCE.json", "SIGNING-CERTIFICATE.txt"}
        if {asset["name"] for asset in existing["assets"]} != required or any(asset["size"] == 0 for asset in existing["assets"]):
            raise ValueError("Published release has missing or unexpected assets; refusing to overwrite it")
        output(build="false", tag=release_tag)
        return
    destination = Path(os.environ.get("RELEASE_SOURCE", ROOT / "_release")).resolve()
    if destination.exists():
        raise ValueError(f"Refusing to reuse an existing build directory: {destination}")
    tag_exists = run("git", "ls-remote", f"https://github.com/{REPO}.git", f"refs/tags/{release_tag}")
    clone_repo, clone_tag = (REPO, release_tag) if tag_exists else (UPSTREAM, app_tag)
    run("git", "clone", "--filter=blob:none", "--single-branch", "--branch", clone_tag, f"https://github.com/{clone_repo}.git", str(destination))
    core_path = destination / "core/Clash.Meta"
    if tag_exists:
        provenance = json.loads((destination / ".fork/provenance.json").read_text())
        if provenance["app_tag"] != app_tag or provenance["core_tag"] != core_tag:
            raise ValueError("Existing tag has different source provenance")
        if provenance.get("overlay_sha256") != overlay_fingerprint():
            raise ValueError("Unpublished source tag uses a different overlay; back it up and recreate it before retrying")
        verify_overlay(destination)
        run("git", "submodule", "update", "--init", "--depth", "1", cwd=destination)
    else:
        app_sha = run("git", "rev-parse", "HEAD", cwd=destination)
        upstream_core_sha = run("git", "ls-tree", "HEAD", "core/Clash.Meta", cwd=destination).split()[2]
        workflow = (destination / ".github/workflows/build.yaml").read_text()
        versions = {}
        for name in ("FLUTTER_VERSION", "GO_VERSION", "NDK_VERSION"):
            match = re.search(rf"(?m)^  {name}: ['\"]?([\w.]+)", workflow)
            if not match:
                raise ValueError(f"Missing upstream toolchain version: {name}")
            versions[name.lower()] = match.group(1)
        shutil.copytree(ROOT / ".fork", destination / ".fork", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        for file in (destination / ".github/workflows").iterdir():
            if file.is_file():
                file.unlink()
        shutil.copy2(ROOT / ".github/workflows/anytls-release.yml", destination / ".github/workflows/anytls-release.yml")
        apply_overlay(destination)
        if core_path.exists():
            core_path.rmdir()  # git creates an empty directory for an uninitialized submodule.
        run("git", "clone", "--depth", "1", "--branch", core_tag, f"https://github.com/{CORE}.git", str(core_path))
        core_sha = run("git", "rev-parse", "HEAD", cwd=core_path)
        # Upstream currently rebases one compatibility commit onto mihomo. Refuse
        # a different layout rather than silently discard its Android API changes.
        with tempfile.TemporaryDirectory(prefix="flclash-compat-", dir=destination.parent) as directory:
            run("git", "init", directory)
            run("git", "fetch", "--depth", "2", "https://github.com/chen08209/Clash.Meta.git", upstream_core_sha, cwd=directory)
            subject = run("git", "show", "-s", "--format=%s", upstream_core_sha, cwd=directory)
            if subject != "feat: support FlClash":
                raise ValueError(f"Review new upstream core compatibility layout: {subject}")
            compatibility = run("git", "diff", "--binary", f"{upstream_core_sha}^", upstream_core_sha, cwd=directory, strip=False)
        (destination / ".fork/flclash-compat.patch").write_text(compatibility, encoding="utf-8", newline="\n")
        run("git", "config", "-f", ".gitmodules", "submodule.core/Clash.Meta.url", f"https://github.com/{CORE}.git", cwd=destination)
        run("git", "config", "-f", ".gitmodules", "--unset", "submodule.core/Clash.Meta.branch", cwd=destination)
        code = 1_000_000_000 + int(os.environ["GITHUB_RUN_NUMBER"])
        if code >= 2_100_000_000:
            raise ValueError("Android versionCode limit reached")
        pubspec = destination / "pubspec.yaml"
        content, count = re.subn(r"(?m)^version: .+$", f"version: {app_tag[1:]}+{code}", pubspec.read_text())
        if count != 1:
            raise ValueError("Could not set the single pubspec version")
        pubspec.write_text(content, encoding="utf-8", newline="\n")
        provenance = dict(app_repository=UPSTREAM, app_tag=app_tag, app_sha=app_sha,
                          core_repository=CORE, core_tag=core_tag, core_sha=core_sha,
                          compatibility_repository="chen08209/Clash.Meta", compatibility_sha=upstream_core_sha,
                          compatibility_patch_sha256=hashlib.sha256(compatibility.encode()).hexdigest(),
                          version_code=code, overlay_sha256=overlay_fingerprint(), firebase_disabled=True, **versions)
        (destination / ".fork/provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        run("git", "apply", "--check", str(destination / ".fork/flclash-compat.patch"), cwd=core_path)
        run("git", "add", "--all", cwd=destination)
        run("git", "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com", "commit", "-m", f"Build {app_tag} with AnyTLS REALITY core {core_tag}", cwd=destination)
        run("git", "tag", release_tag, cwd=destination)
        run("git", "push", f"https://github.com/{REPO}.git", f"refs/tags/{release_tag}", cwd=destination, env=auth_env())
    patch = destination / ".fork/flclash-compat.patch"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != provenance["compatibility_patch_sha256"]:
        raise ValueError("Compatibility patch hash differs from release provenance")
    run("git", "apply", "--check", str(patch), cwd=core_path)
    run("git", "apply", str(patch), cwd=core_path)
    if run("git", "rev-parse", "HEAD", cwd=core_path) != provenance["core_sha"]:
        raise ValueError("Mihomo checkout does not match release provenance")
    if not (core_path / "adapter/outbound/anytls_reality_test.go").exists():
        raise ValueError("The selected core has no AnyTLS REALITY regression test")
    output(build="true", tag=release_tag, version=app_tag[1:], version_code=provenance["version_code"],
           flutter_version=provenance["flutter_version"], go_version=provenance["go_version"],
           ndk_version=provenance["ndk_version"], source=str(destination))


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        assert stable_tag({"tag_name": "v0.8.98"}) == "v0.8.98"
        for value in ({"tag_name": "v0.8.98-beta"}, {"tag_name": "v0.8.98", "prerelease": True}):
            try:
                stable_tag(value)
                raise AssertionError("Accepted a prerelease")
            except ValueError:
                pass
        assert "com.github.aldingtondavid.flclash" in (ROOT / ".fork/app.patch").read_text()
        print("prepare self-test passed")
    else:
        main()
