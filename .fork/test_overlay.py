import argparse
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from overlay import apply, replace_literal, verify


class LiteralTest(unittest.TestCase):
    def test_layout_does_not_matter_and_replacement_is_idempotent(self):
        for layout in ("openUrl('old')", "Link(url: 'old', label: 'name')"):
            result = replace_literal(layout, "'old'", "'new'")
            self.assertEqual(replace_literal(result, "'old'", "'new'"), result)

    def test_missing_or_duplicate_values_stop_the_build(self):
        for text in ("", "old old", "old new", "new new"):
            with self.assertRaises(ValueError):
                replace_literal(text, "old", "new")
        self.assertEqual(replace_literal("unrelated", "old", "new", optional=True), "unrelated")


def replay(repository, ref):
    paths = ["android", "lib/common/constant.dart", "lib/common/request.dart", "lib/views/about.dart"]
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
        print(ref + ": full overlay and five Firebase rejection cases passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ref", action="append", default=[])
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LiteralTest)
    if not unittest.TextTestRunner().run(suite).wasSuccessful():
        raise SystemExit(1)
    for ref in args.ref:
        replay(args.repository, ref)
