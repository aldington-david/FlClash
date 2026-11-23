import 'dart:convert';

import 'package:fl_clash/enum/enum.dart';
import 'package:fl_clash/models/models.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:prism_ui/prism_ui.dart';

void expectForkDefaults(Config config) {
  expect(config.vpnProps.systemProxy, false);
  expect(config.vpnProps.allowBypass, false);
  expect(config.vpnProps.ipv6, true);
  expect(config.vpnProps.dnsHijacking, true);
  expect(config.patchClashConfig.tun.congestionController, 'bbr3');
  expect(config.patchClashConfig.ipv6, true);
  expect(config.patchClashConfig.geoAutoUpdate, true);
  expect(config.patchClashConfig.generalOverrideJson, {
    'unified-delay': true,
    'tcp-concurrent': true,
    'ipv6': true,
    'geodata-loader': 'memconservative',
  });
  expect(config.themeProps.themeMode, ThemeMode.dark);
  expect(config.themeProps.colorStyle, ColorStyle.soft);
  expect(config.patchClashConfig.allowLan, false);
  expect(config.networkProps.bypassPrivateRoute, true);
  expect(config.appSettingProps.autoRun, false);
  expect(config.appSettingProps.hidden, false);
  expect(config.appSettingProps.showNotificationStopAction, true);
  expect(config.appSettingProps.autoCheckUpdate, true);
}

void main() {
  test('new remote subscriptions update every six hours', () {
    final profile = Profile.normal(url: 'https://example.invalid/profile.yaml');
    expect(profile.type, ProfileType.url);
    expect(profile.autoUpdate, true);
    expect(profile.autoUpdateDuration, const Duration(hours: 6));
    expect(profile.autoUpdateDuration.inMinutes, 360);
    expect(profile.autoUpdateDuration.inMilliseconds, 21600000);
    expect(profile.toJson()['autoUpdateDuration'], 21600000000);
    expect(Profile.normal().autoUpdateDuration, const Duration(days: 1));
    final custom = Profile.custom();
    expect(custom.autoUpdate, false);
    expect(custom.autoUpdateDuration, const Duration(days: 1));
  });

  test('saved subscription schedules survive backup decoding', () {
    for (final enabled in [true, false]) {
      final saved = Profile(
        id: 1,
        type: ProfileType.url,
        url: 'https://example.invalid/profile.yaml',
        autoUpdate: enabled,
        autoUpdateDuration: const Duration(hours: 12),
      );
      final restored = Profile.fromJson(
        jsonDecode(jsonEncode(saved)) as Map<String, Object?>,
      );
      expect(restored, saved);
    }
  });

  test('new and missing configuration fields use approved defaults', () {
    expectForkDefaults(Config.realFromJson(null));
    expectForkDefaults(Config.fromJson({}));
    expectForkDefaults(
      Config.fromJson({
        'vpnProps': <String, Object?>{},
        'themeProps': <String, Object?>{},
        'patchClashConfig': <String, Object?>{},
      }),
    );
  });

  test('saved settings and deliberately empty overrides survive decoding', () {
    const saved = Config(
      vpnProps: VpnProps(
        systemProxy: true,
        allowBypass: true,
        ipv6: false,
        dnsHijacking: false,
      ),
      themeProps: ThemeProps(
        themeMode: ThemeMode.light,
        colorStyle: ColorStyle.vivid,
      ),
      patchClashConfig: PatchClashConfig(
        ipv6: false,
        geoAutoUpdate: false,
        tun: Tun(congestionController: 'reno'),
        generalOverrideKeys: {},
      ),
    );
    final restored = Config.realFromJson(
      jsonDecode(jsonEncode(saved)) as Map<String, Object?>,
    );
    expect(restored, saved);
    expect(restored.patchClashConfig.generalOverrideJson, isEmpty);
  });

  test('legacy explicit theme and congestion choices keep their meaning', () {
    for (final variant in [
      'content',
      'fidelity',
      'vibrant',
      'expressive',
      'rainbow',
      'fruitSalad',
    ]) {
      expect(
        ThemeProps.fromJson({'schemeVariant': variant}).colorStyle,
        ColorStyle.vivid,
      );
    }
    expect(
      ThemeProps.fromJson({'schemeVariant': 'content', 'colorStyle': 'tinted'})
          .colorStyle,
      ColorStyle.tinted,
    );
    final oldBbr = PatchClashConfig.fromJson({
      'tun': {'congestion-controller': 'bbr3'},
    });
    expect(
      oldBbr.tunOverrideKeys,
      contains(TunOverrideKey.congestionController),
    );
    expect(oldBbr.tunOverride.congestionController, 'bbr3');
    for (final tun in [
      <String, Object?>{},
      {'congestion-controller': 'cubic'},
    ]) {
      expect(
        PatchClashConfig.fromJson({'tun': tun}).tunOverrideKeys,
        isNot(contains(TunOverrideKey.congestionController)),
      );
    }
    expect(const ProfileTun().congestionController, 'cubic');
  });
}
