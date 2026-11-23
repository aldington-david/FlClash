import 'dart:ffi' show Abi;

import 'package:fl_clash/common/app_update.dart';
import 'package:fl_clash/common/release_asset.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('fork packaging and updates keep the installed arm64 naming contract', () {
    final asset = selfUpdateAssetFor(
      Abi.androidArm64,
      windowsInstalled: false,
    )!;
    for (final tag in [
      'v0.9.4-anytls-v1.19.34-r5',
      'v0.9.4-anytls-v1.19.35-r5',
      'v0.9.4-anytls-v1.19.35-r6',
    ]) {
      final version = tag.substring(1);
      final name = 'FlClash-$version-android-arm64-v8a.apk';
      expect(updateAssetName(tag, asset), name);
      expect(
        releaseAssetName(
          line: ReleaseLine.dev,
          version: version,
          os: ReleaseOs.android,
          arch: ReleaseArch.arm64,
          extension: 'apk',
        ),
        name,
      );
      expect(updateChecksumsName(tag), 'SHA256SUMS');
      expect(releaseChecksumsName(ReleaseLine.dev, version), 'SHA256SUMS');
      expect(
        releaseAssetUri(tag, name).toString(),
        'https://github.com/aldington-david/FlClash/releases/download/$tag/$name',
      );
      final digest = 'a' * 64;
      expect(releaseChecksum('$digest  $name\n', name), digest);
      expect(releaseChecksum('$digest  other.apk\n', name), isNull);
    }
  });

  test('fork naming accepts only the published version layout', () {
    for (final version in [
      '0.9.4-anytls-v1.19.34-r5-extra',
      '0.9.4-anytls-v1.19.34-rx',
      '0.9.4-anytls-v1.19.34-r5/other',
    ]) {
      expect(
        () => releaseAssetName(
          line: ReleaseLine.dev,
          version: version,
          os: ReleaseOs.android,
          arch: ReleaseArch.arm64,
          extension: 'apk',
        ),
        throwsArgumentError,
      );
      expect(
        () => releaseChecksumsName(ReleaseLine.dev, version),
        throwsArgumentError,
      );
    }
  });
}
