import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:chii_mobile/core/location.dart';

class PlatformLocation extends GeolocatorPlatform {
  bool enabled = true;
  LocationPermission permission = LocationPermission.whileInUse;
  LocationAccuracyStatus accuracy = LocationAccuracyStatus.precise;
  Object? failure;
  int requests = 0;
  DateTime time = DateTime.now();
  @override
  Future<bool> isLocationServiceEnabled() async => enabled;
  @override
  Future<LocationPermission> checkPermission() async => permission;
  @override
  Future<LocationPermission> requestPermission() async {
    requests++;
    return permission;
  }

  @override
  Future<LocationAccuracyStatus> getLocationAccuracy() async => accuracy;
  @override
  Future<Position> getCurrentPosition({
    LocationSettings? locationSettings,
  }) async {
    expect(locationSettings!.timeLimit, const Duration(seconds: 15));
    if (failure != null) throw failure!;
    return Position(
      longitude: 127,
      latitude: 37,
      timestamp: time,
      accuracy: 10,
      altitude: 0,
      altitudeAccuracy: 0,
      heading: 0,
      headingAccuracy: 0,
      speed: 0,
      speedAccuracy: 0,
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late GeolocatorPlatform original;
  late PlatformLocation fake;
  setUp(() {
    original = GeolocatorPlatform.instance;
    fake = PlatformLocation();
    GeolocatorPlatform.instance = fake;
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
  });
  tearDown(() {
    GeolocatorPlatform.instance = original;
    debugDefaultTargetPlatformOverride = null;
  });
  Matcher issue(String code) =>
      isA<LocationIssue>().having((e) => e.code, 'code', code);
  test('OS service disabled is distinct from denied', () async {
    fake.enabled = false;
    await expectLater(DeviceLocation().current(), throwsA(issue('disabled')));
    expect(fake.requests, 0);
  });
  test('permission denied requests only on explicit action', () async {
    fake.permission = LocationPermission.denied;
    await expectLater(
      DeviceLocation().current(requestPermission: false),
      throwsA(issue('denied')),
    );
    expect(fake.requests, 0);
    await expectLater(DeviceLocation().current(), throwsA(issue('denied')));
    expect(fake.requests, 1);
  });
  test('permanently denied does not prompt again', () async {
    fake.permission = LocationPermission.deniedForever;
    await expectLater(
      DeviceLocation().current(),
      throwsA(issue('permanently_denied')),
    );
    expect(fake.requests, 0);
  });
  test('iOS restricted status comes from native channel', () async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    const channel = MethodChannel('chii/location');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async => true);
    await expectLater(DeviceLocation().current(), throwsA(issue('restricted')));
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });
  test('reduced accuracy is preserved', () async {
    fake.accuracy = LocationAccuracyStatus.reduced;
    expect((await DeviceLocation().current()).approximate, true);
  });
  test('timeout is sanitized separately', () async {
    fake.failure = TimeoutException('sensitive');
    await expectLater(DeviceLocation().current(), throwsA(issue('timeout')));
  });
  test('plugin error is sanitized', () async {
    fake.failure = StateError('private coordinate');
    await expectLater(DeviceLocation().current(), throwsA(issue('error')));
  });
  test('stale fixes are rejected', () async {
    fake.time = DateTime.now().subtract(const Duration(minutes: 1));
    await expectLater(DeviceLocation().current(), throwsA(issue('stale')));
  });
}
