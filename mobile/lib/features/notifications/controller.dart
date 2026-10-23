import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../core/api.dart';
import '../../core/session.dart';

abstract class PushPlatform {
  Future<String> permission({bool request = false});
  Future<String?> token();
  Stream<String> get rotations;
  Stream<Map<String, dynamic>> get foreground;
  Stream<Map<String, dynamic>> get taps;
  Future<Map<String, dynamic>?> initialTap();
}

abstract class InstallationStore {
  Future<Map<String, dynamic>?> read();
  Future<void> write(Map<String, dynamic> value);
}

class SecureInstallationStore implements InstallationStore {
  static const storage = FlutterSecureStorage(
    iOptions: IOSOptions(
      accessibility: KeychainAccessibility.unlocked_this_device,
    ),
  );
  @override
  Future<Map<String, dynamic>?> read() async {
    final raw = await storage.read(key: 'chii.push.installation');
    return raw == null ? null : Map<String, dynamic>.from(jsonDecode(raw));
  }

  @override
  Future<void> write(Map<String, dynamic> value) =>
      storage.write(key: 'chii.push.installation', value: jsonEncode(value));
}

class PushController extends ChangeNotifier {
  PushController(this.session, this.platform, this.store, this.platformName) {
    session.addListener(sessionChanged);
    subscriptions.add(platform.rotations.listen((_) => synchronize()));
    subscriptions.add(
      platform.foreground.listen((data) {
        if (valid(data) && session.authenticated) {
          notice = 'テスト通知 / 테스트 알림을 받았습니다.';
          emit();
        }
      }),
    );
    subscriptions.add(platform.taps.listen(handleTap));
    platform.initialTap().then((data) {
      if (data != null) handleTap(data);
    }, onError: (Object _) {});
    sessionChanged();
  }
  final Session session;
  final PushPlatform platform;
  final InstallationStore store;
  final String platformName;
  final subscriptions = <StreamSubscription<dynamic>>[];
  Future<void> pending = Future.value();
  bool busy = false, disposed = false, closing = false;
  int epoch = 0;
  String? lastUser;
  String? notice;
  String permissionState = 'not_determined';
  bool pendingHome = false;
  int homeEvent = 0;
  final seen = <String>{};
  bool valid(Map<String, dynamic> data) =>
      data['version'] == '1' &&
      data['type'] == 'OPERATOR_TEST' &&
      data['destination'] == 'HOME' &&
      data['message_id'] is String &&
      RegExp(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
      ).hasMatch(data['message_id']);
  void handleTap(Map<String, dynamic> data) {
    if (!valid(data) || !seen.add(data['message_id'])) return;
    if (seen.length > 100) seen.remove(seen.first);
    pendingHome = true;
    if (session.authenticated) {
      pendingHome = false;
      homeEvent++;
    }
    emit();
  }

  void sessionChanged() {
    final id = session.authenticated ? session.user!['id'] as String : null;
    if (id == lastUser) return;
    lastUser = id;
    epoch++;
    notice = null;
    if (id != null) {
      if (pendingHome) {
        pendingHome = false;
        homeEvent++;
      }
      synchronize();
    }
    emit();
  }

  void emit() {
    if (!disposed) notifyListeners();
  }

  Future<Map<String, dynamic>> installation() async {
    final existing = await store.read();
    if (existing != null) return existing;
    final random = Random.secure();
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    final h = bytes.map((v) => v.toRadixString(16).padLeft(2, '0')).join();
    final value = <String, dynamic>{
      'id':
          '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}',
      'secret': base64UrlEncode(
        List<int>.generate(32, (_) => random.nextInt(256)),
      ).replaceAll('=', ''),
      'version': 0,
    };
    await store.write(value);
    return value;
  }

  bool current(int generation) =>
      !disposed && !closing && generation == epoch && session.authenticated;
  Future<void> synchronize({bool optIn = false, bool disable = false}) {
    final generation = epoch;
    pending = pending.then((_) async {
      if (!current(generation)) return;
      busy = true;
      emit();
      try {
        final record = await installation();
        if (!current(generation)) return;
        if (optIn || disable) {
          record['opt_in'] = optIn && !disable;
          await store.write(record);
        }
        permissionState = await platform.permission(request: optIn);
        if (!current(generation)) return;
        final allowed =
            record['opt_in'] == true &&
            !disable &&
            ['authorized', 'provisional'].contains(permissionState);
        final token = allowed ? await platform.token() : '';
        if (!current(generation)) return;
        if (allowed && token == null) {
          notice = '알림 등록 준비 중입니다. 잠시 후 다시 시도해 주세요.';
          return;
        }
        final path = '/notifications/devices/${record['id']}';
        // Resolve only for this active generation; no old request is automatically replayed.
        try {
          final resolved = await session.request(
            'POST',
            '$path/resolve',
            data: {'installation_secret': record['secret']},
          );
          if (!current(generation)) return;
          record['version'] = resolved['binding_version'];
        } on ApiFailure catch (e) {
          if (e.status != 404) rethrow;
          record['version'] = 0;
        }
        if (!current(generation)) return;
        final result = await session.request(
          'PUT',
          path,
          data: {
            'installation_secret': record['secret'],
            'binding_version': record['version'],
            'platform': platformName,
            'provider_token': token ?? '',
            'permission_state': permissionState,
            'enabled': allowed,
          },
        );
        if (!current(generation)) return;
        record['version'] = result['binding_version'];
        await store.write(record);
        notice = allowed ? '알림 등록을 완료했습니다.' : '알림을 비활성화했습니다.';
      } catch (_) {
        if (current(generation)) notice = '알림 등록 상태를 확인할 수 없습니다. 다시 시도해 주세요.';
      } finally {
        busy = false;
        emit();
      }
    });
    return pending;
  }

  Future<bool> logout() async {
    if (closing) return false;
    closing = true;
    epoch++;
    notice = null;
    emit();
    try {
      // Drain local registration work. A timed-out server operation is fenced by binding_version.
      await pending.timeout(const Duration(seconds: 20));
      final record = await store.read();
      if (record != null && session.authenticated) {
        final path = '/notifications/devices/${record['id']}';
        final resolved = await session.request(
          'POST',
          '$path/resolve',
          data: {'installation_secret': record['secret']},
        );
        await session.request(
          'DELETE',
          path,
          data: {
            'installation_secret': record['secret'],
            'binding_version': resolved['binding_version'],
          },
        );
      }
    } catch (_) {
      /* Offline logout must still clear the authentication state. */
    }
    try {
      return await session.logout();
    } finally {
      closing = false;
      emit();
    }
  }

  @override
  void dispose() {
    disposed = true;
    epoch++;
    session.removeListener(sessionChanged);
    for (final s in subscriptions) {
      s.cancel();
    }
    super.dispose();
  }
}
