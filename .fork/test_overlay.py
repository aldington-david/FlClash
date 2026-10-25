import argparse
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from overlay import apply, replace_literal, replace_update_check, verify
from check_firebase_runtime import verify as verify_runtime
from prepare import compatibility_base


class LiteralTest(unittest.TestCase):
    def test_layout_does_not_matter_and_replacement_is_idempotent(self):
        for layout in ("openUrl('old')", "Link(url: 'old', label: 'name')"):
            result = replace_literal(layout, "'old'", "'new'")
            self.assertEqual(replace_literal(result, "'old'", "'new'"), result)
        old, new = "appName,", "globalState.packageInfo.appName,"
        self.assertEqual(replace_literal(old, old, new), new)
        self.assertEqual(replace_literal(new, old, new), new)
        with self.assertRaises(ValueError):
            replace_literal(old + new, old, new)

    def test_missing_or_duplicate_values_stop_the_build(self):
        for text in ("", "old old", "old new", "new new"):
            with self.assertRaises(ValueError):
                replace_literal(text, "old", "new")
        self.assertEqual(replace_literal("unrelated", "old", "new", optional=True), "unrelated")

    def test_runtime_keeps_barcode_support_but_rejects_telemetry_and_unknown_sdks(self):
        verify_runtime("com.google.firebase:firebase-components:18.0.0\ncom.google.firebase:firebase-encoders-json:18.0.0")
        for dependency in ("com.google.firebase:firebase-crashlytics-ndk:20.0.0",
                           "com.google.firebase:firebase-analytics:23.0.0",
                           "com.google.firebase:firebase-new-unknown:1.0.0",
                           "com.google.android.gms:play-services-measurement-api:23.0.0"):
            with self.assertRaises(ValueError):
                verify_runtime(dependency)


class UpdateCheckTest(unittest.TestCase):
    def test_known_comparisons_keep_the_network_and_result_paths(self):
        for name, cast, spaces in (("data", "", "      "), ("release", " as String", "    ")):
            text = ("import 'dart:async';\n  Future<Map<String, dynamic>?> checkForUpdate() async {\n"
                    f"{spaces}final remoteVersion = {name}['tag_name']{cast};\n"
                    f"{spaces}final version = globalState.packageInfo.version;\n"
                    f"{spaces}final hasUpdate =\n"
                    f"{spaces}    compareVersions(remoteVersion.replaceAll('v', ''), version) > 0;\n"
                    f"{spaces}return hasUpdate ? {name} : null;\n  }}\n"
                    "  Future<Map<String, dynamic>> latestRelease() async { return {}; }")
            updated = replace_update_check(text)
            self.assertNotIn("compareVersions(", updated)
            self.assertIn(f"return hasUpdate ? {name} : null;", updated)
            self.assertTrue(updated.endswith("latestRelease() async { return {}; }"))
            self.assertIn("versionCode is int", updated)
            self.assertIn("Uri.encodeComponent", updated)
            self.assertIn("ResponseType.plain", updated)
            self.assertEqual(updated.count("import 'dart:convert';"), 1)
            with self.assertRaisesRegex(ValueError, "Unknown or ambiguous"):
                replace_update_check(text + text)
            with self.assertRaisesRegex(ValueError, "Unknown or ambiguous"):
                replace_update_check(text.replace("compareVersions(", "differentComparison("))


class CompatibilityBaseTest(unittest.TestCase):
    def test_v092_requires_the_complete_reviewed_commit_chain(self):
        rows = [
            ("c5062921054902b25215a6a933e72ccd714c9bfa", "86e56192ddd815e2094212531c48a364eb35659d", "feat: resolve the route a connection would take without dialing it"),
            ("86e56192ddd815e2094212531c48a364eb35659d", "6aeff178349cbbc89f1729d717a4eb8eba64a198", "feat: find the mapping a proxy provider builds a proxy from"),
            ("6aeff178349cbbc89f1729d717a4eb8eba64a198", "cd1023ac150fd74dc96ad5701d9b10a56fbe5d20", "feat: clear every DNS answer and client state on request"),
            ("cd1023ac150fd74dc96ad5701d9b10a56fbe5d20", "edc32bd7e7ad1a5f74263595f93eace4342d9336", "feat: list use providers among a group's proxies by use-position"),
            ("edc32bd7e7ad1a5f74263595f93eace4342d9336", "3f27ef39f8c96bbfbc8b0b9bb10f5c9ef60149d8", "feat: support FlClash"),
        ]
        actual = list(rows)

        def git(*args, **kwargs):
            if args[1] == "log":
                return "\n".join("\0".join(row) for row in actual)
            if args[1] == "rev-list":
                return f"{args[-1]} {rows[0][1]}"
            return rows[0][2]

        with patch("prepare.run", side_effect=git):
            self.assertEqual(compatibility_base("unused", rows[0][0]), rows[-1][1])
            with self.assertRaises(ValueError):
                compatibility_base("unused", "unknown-later-tip")
            actual = rows[:-1]
            with self.assertRaises(ValueError):
                compatibility_base("unused", rows[0][0])
            for index, value in ((0, "unknown-commit"), (1, "unknown-parent"),
                                 (1, rows[1][1] + " extra-merge-parent"), (2, "feat: unreviewed change")):
                actual = list(rows)
                changed = list(actual[1])
                changed[index] = value
                actual[1] = tuple(changed)
                with self.assertRaises(ValueError):
                    compatibility_base("unused", rows[0][0])

    def test_old_single_and_reviewed_two_commit_stack_reject_unknown_layouts(self):
        tip = "8380d0e7462f061a964323e9bf3129a236fcc5d5"
        support = "86a42fd8986243306705a525067dbcaa67bf0bb3"
        baseline = "88dcbf7f1614a67c3b36b848ee3592dfa92ada36"
        commits = {
            "old": ("old parent", "feat: support FlClash"),
            support: (f"{support} {baseline}", "feat: support FlClash"),
            tip: (f"{tip} {support}", "feat: list use providers among a group's proxies by use-position"),
            "unknown": ("unknown old", "feat: unknown compatibility change"),
            "merge": ("merge old other", "feat: support FlClash"),
        }

        def git(*args, **kwargs):
            return commits[args[-1]][0 if args[1] == "rev-list" else 1]

        with patch("prepare.run", side_effect=git):
            self.assertEqual(compatibility_base("unused", "old"), "parent")
            self.assertEqual(compatibility_base("unused", tip), baseline)
            for revision in ("unknown", "merge"):
                with self.assertRaises(ValueError):
                    compatibility_base("unused", revision)
            commits[support] = (f"{support} wrong-baseline", "feat: support FlClash")
            with self.assertRaises(ValueError):
                compatibility_base("unused", tip)


def replay(repository, ref):
    paths = ["android", "lib/application.dart", "lib/common/constant.dart", "lib/common/request.dart", "lib/views/about.dart", "test/common"]
    archive = subprocess.check_output(["git", "-c", "core.autocrlf=false", "-C", str(repository),
                                       "archive", "--format=zip", ref, "--", *paths])
    with tempfile.TemporaryDirectory(prefix="flclash-overlay-") as directory:
        source = Path(directory)
        with zipfile.ZipFile(io.BytesIO(archive)) as files:
            files.extractall(source)
        subprocess.run(["git", "init", "--quiet", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "add", "."], check=True, capture_output=True)
        apply(source)
        verify(source)
        request = source / "lib/common/request.dart"
        clean_request = request.read_text(encoding="utf-8")
        mode = "true" if "Future<Map<String, dynamic>> latestRelease() async {" in clean_request else "false"
        self_test = (source / "test/common/fork_update_test.dart").read_text(encoding="utf-8")
        assert f"const hasReleaseRedirect = {mode};" in self_test
        request.write_text(clean_request.replace("globalState.packageInfo.buildNumber", "globalState.packageInfo.version"), encoding="utf-8")
        try:
            verify(source)
        except ValueError as error:
            assert "Android version codes" in str(error), error
        else:
            raise AssertionError("Accepted the upstream version comparison")
        request.write_text(clean_request, encoding="utf-8")
        app = source / "android/app/build.gradle.kts"
        clean = app.read_text(encoding="utf-8")
        for residual in ('import com.google.firebase.NewApi', 'configure<CrashlyticsExtension> {}',
                         'tasks.register("uploadCrashlyticsUnexpected")', 'implementation(libs.firebase.analytics)'):
            app.write_text(clean + "\n" + residual + "\n", encoding="utf-8")
            try:
                verify(source)
            except ValueError as error:
                assert "Firebase executable reference" in str(error), error
            else:
                raise AssertionError("Accepted a new Firebase entry: " + residual)
        app.write_text(clean, encoding="utf-8")
        native = source / "android/common/src/main/java/com/follow/clash/common/GlobalState.kt"
        native.write_text("import com.google.firebase.NewApi\n" + native.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            verify(source)
        except ValueError as error:
            assert "GlobalState.kt" in str(error), error
        else:
            raise AssertionError("Accepted a new native Firebase import")
        subprocess.run(["git", "-C", str(source), "restore", "."], check=True)
        (source / "test/common/fork_update_test.dart").unlink()
        if "import com.google.firebase.FirebaseApp" in native.read_text(encoding="utf-8"):
            common = source / "android/common/build.gradle.kts"
            before = common.read_text(encoding="utf-8")
            assert before.count("    implementation(libs.firebase.analytics)\n") == 1
            common.write_text(before.replace(
                "    implementation(libs.firebase.analytics)\n", "", 1), encoding="utf-8")
            expected = subprocess.CalledProcessError
        else:
            before = app.read_text(encoding="utf-8")
            assert before.count("dependencies {\n") == 1
            app.write_text(before.replace(
                "dependencies {\n", "dependencies {\n    implementation(libs.firebase.analytics)\n", 1), encoding="utf-8")
            expected = ValueError
        try:
            apply(source)
        except expected as error:
            if isinstance(error, subprocess.CalledProcessError):
                assert Path(error.cmd[-1]).name == "firebase-runtime.patch", error
            else:
                assert "Firebase executable reference" in str(error), error
        else:
            raise AssertionError("Accepted a partial Firebase removal or a residual SDK")
        print(ref + ": full overlay, update-code guard, five Firebase rejection cases and partial-removal rejection passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ref", action="append", default=[])
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    if not unittest.TextTestRunner().run(suite).wasSuccessful():
        raise SystemExit(1)
    for ref in args.ref:
        replay(args.repository, ref)
