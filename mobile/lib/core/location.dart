import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

class LocationIssue implements Exception {
  const LocationIssue(this.code, this.message);
  final String code;
  final String message;
  @override
  String toString() => message;
}

class Fix {
  const Fix(
    this.latitude,
    this.longitude,
    this.accuracy,
    this.at, {
    this.approximate = false,
  });
  final double latitude, longitude, accuracy;
  final DateTime at;
  final bool approximate;
  Map<String, dynamic> get query => {
    'latitude': latitude,
    'longitude': longitude,
  };
}

abstract class LocationSource {
  Future<Fix> current({bool requestPermission = true});
  Future<void> openSettings();
}

class DeviceLocation implements LocationSource {
  static const _channel = MethodChannel('chii/location');
  bool _foreground = true;
  int _version = 0;
  void setForeground(bool active) {
    _foreground = active;
    _version++;
  }

  @override
  Future<Fix> current({bool requestPermission = true}) async {
    final version = _version;
    if (!_foreground) {
      throw const LocationIssue('inactive', '앱을 연 상태에서 위치를 확인해 주세요.');
    }
    try {
      if (defaultTargetPlatform == TargetPlatform.iOS) {
        final restricted = await _channel.invokeMethod<bool>('isRestricted');
        if (restricted == true) {
          throw const LocationIssue('restricted', '기기 정책으로 위치 사용이 제한됩니다.');
        }
      }
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw const LocationIssue(
          'disabled',
          '위치 서비스가 꺼져 있습니다. 기기 설정에서 켜 주세요.',
        );
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied && requestPermission) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.deniedForever) {
        throw const LocationIssue(
          'permanently_denied',
          '위치 권한이 차단되었습니다. 앱 설정에서 허용해 주세요.',
        );
      }
      if (permission == LocationPermission.denied) {
        throw const LocationIssue('denied', '주변 장소를 찾으려면 위치 권한이 필요합니다.');
      }
      if (permission == LocationPermission.unableToDetermine) {
        throw const LocationIssue(
          'restricted',
          '위치 권한 상태를 확인할 수 없습니다. 기기 제한을 확인해 주세요.',
        );
      }
      final accuracyStatus = await Geolocator.getLocationAccuracy();
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 15),
        ),
      );
      if (!_foreground || version != _version) {
        throw const LocationIssue('inactive', '위치 확인이 중단되었습니다. 다시 시도해 주세요.');
      }
      if (DateTime.now().difference(position.timestamp).abs() >
          const Duration(seconds: 15)) {
        throw const LocationIssue('stale', '최신 위치를 얻지 못했습니다. 다시 시도해 주세요.');
      }
      return Fix(
        position.latitude,
        position.longitude,
        position.accuracy,
        position.timestamp,
        approximate: accuracyStatus == LocationAccuracyStatus.reduced,
      );
    } on LocationIssue {
      rethrow;
    } on TimeoutException {
      throw const LocationIssue('timeout', '위치 확인 시간이 초과되었습니다. 다시 시도해 주세요.');
    } catch (_) {
      throw const LocationIssue('error', '위치를 확인하지 못했습니다. 권한과 GPS를 확인해 주세요.');
    }
  }

  @override
  Future<void> openSettings() async {
    await Geolocator.openAppSettings();
  }

  Future<void> openLocationSettings() async {
    await Geolocator.openLocationSettings();
  }
}
