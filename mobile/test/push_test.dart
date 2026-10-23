import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:chii_mobile/core/api.dart';
import 'package:chii_mobile/core/session.dart';
import 'package:chii_mobile/features/notifications/controller.dart';

import 'support.dart';

class InstallMemory implements InstallationStore {
  Map<String, dynamic>? value;
  @override
  Future<Map<String, dynamic>?> read() async =>
      value == null ? null : Map.of(value!);
  @override
  Future<void> write(Map<String, dynamic> v) async {
    value = Map.of(v);
  }
}

class PlatformFake implements PushPlatform {
  String state = 'authorized';
  int requests = 0, tokens = 0;
  final rotation = StreamController<String>.broadcast();
  final foregroundEvents = StreamController<Map<String, dynamic>>.broadcast();
  final tapEvents = StreamController<Map<String, dynamic>>.broadcast();
  @override
  Future<String> permission({bool request = false}) async {
    if (request) requests++;
    return state;
  }

  @override
  Future<String?> token() async {
    tokens++;
    return 'synthetic-provider';
  }

  @override
  Stream<String> get rotations => rotation.stream;
  @override
  Stream<Map<String, dynamic>> get foreground => foregroundEvents.stream;
  @override
  Stream<Map<String, dynamic>> get taps => tapEvents.stream;
  @override
  Future<Map<String, dynamic>?> initialTap() async => null;
  void close() {
    rotation.close();
    foregroundEvents.close();
    tapEvents.close();
  }
}

void main() {
  late Session session;
  late PushController push;
  late InstallMemory store;
  late PlatformFake platform;
  late List<Map<String, dynamic>> writes;
  late int version;
  Future<dynamic> normal(
    String method,
    String path,
    Object? data,
    Map<String, dynamic>? query,
    String? access,
  ) async {
    if (path == '/collection') return page([]);
    if (path.endsWith('/resolve')) return {'binding_version': version};
    if (method == 'PUT') {
      writes.add(Map<String, dynamic>.from(data as Map));
      expect(data['binding_version'], version);
      return {'binding_version': ++version};
    }
    if (method == 'DELETE') {
      version++;
      return null;
    }
    return null;
  }

  setUp(() {
    writes = [];
    version = 0;
    store = InstallMemory();
    platform = PlatformFake();
    session = Session(FakeApi(normal), MemoryStore())..user = {'id': 'A'};
    push = PushController(session, platform, store, 'ios');
  });
  tearDown(() {
    push.dispose();
    session.dispose();
    platform.close();
  });
  test('bootstrap persists ownership proof, opt in is explicit, secret never returned', () async {
    await push.pending;
    expect(writes.single['enabled'], false);
    expect(platform.tokens, 0);
    final identity = Map.of(store.value!);
    expect(identity['secret'], matches(RegExp(r'^[A-Za-z0-9_-]{43}$')));
    await push.synchronize(optIn: true);
    expect(writes.last['enabled'], true);
    expect(platform.requests, 1);
    expect(store.value!['id'], identity['id']);
    expect(store.value!['secret'], identity['secret']);
    expect(store.value!['version'], 2);
  });
  test(
    'denied permission registers disabled and never asks for provider token',
    () async {
      await push.pending;
      platform.state = 'denied';
      await push.synchronize(optIn: true);
      expect(writes.last['enabled'], false);
      expect(platform.tokens, 0);
    },
  );
  test('explicit disable survives resume', () async {
    await push.pending;
    await push.synchronize(optIn: true);
    await push.synchronize(disable: true);
    await push.synchronize();
    expect(writes.last['enabled'], false);
    expect(store.value!['opt_in'], false);
  });
  test('rotations synchronize using latest server version', () async {
    await push.pending;
    await push.synchronize(optIn: true);
    platform.rotation.add('new');
    await Future<void>.delayed(Duration.zero);
    await push.pending;
    expect(store.value!['version'], 3);
  });
  test('logout clears auth but preserves installation proof', () async {
    await push.pending;
    final proof = store.value!['secret'];
    expect(await push.logout(), true);
    expect(session.authenticated, false);
    expect(store.value!['secret'], proof);
  });
  test(
    'old generation response cannot persist version or UI after account switch',
    () async {
      await push.pending;
      final entered = Completer<void>(), response = Completer<dynamic>();
      final other = Session(
        FakeApi((m, p, d, q, a) async {
          if (p.endsWith('/resolve')) return {'binding_version': 0};
          entered.complete();
          return response.future;
        }),
        MemoryStore(),
      )..user = {'id': 'A'};
      final memory = InstallMemory();
      final controller = PushController(other, platform, memory, 'ios');
      await entered.future;
      other.user = null;
      other.notifyListeners();
      response.complete({'binding_version': 999});
      await controller.pending;
      expect(memory.value!['version'], 0);
      expect(controller.notice, null);
      controller.dispose();
      other.dispose();
    },
  );
  test(
    'offline registration does not leak error details or retry indefinitely',
    () async {
      await push.pending;
      final other = Session(
        FakeApi((m, p, d, q, a) async {
          throw const ApiFailure('private-provider-secret');
        }),
        MemoryStore(),
      )..user = {'id': 'A'};
      final controller = PushController(
        other,
        platform,
        InstallMemory(),
        'ios',
      );
      await controller.pending;
      expect(controller.notice, isNot(contains('private-provider-secret')));
      expect(other.authenticated, true);
      expect(await controller.logout(), true);
      controller.dispose();
      other.dispose();
    },
  );
  test(
    'only supported HOME payload routes once; login gates pending tap',
    () async {
      await push.pending;
      final data = {
        'version': '1',
        'type': 'OPERATOR_TEST',
        'destination': 'HOME',
        'message_id': '00000000-0000-4000-8000-000000000001',
      };
      push.handleTap({...data, 'destination': 'https://unsafe.invalid'});
      expect(push.homeEvent, 0);
      session.user = null;
      session.notifyListeners();
      push.handleTap(data);
      expect(push.pendingHome, true);
      expect(push.homeEvent, 0);
      session.user = {'id': 'B'};
      session.notifyListeners();
      await push.pending;
      expect(push.homeEvent, 1);
      push.handleTap(data);
      expect(push.homeEvent, 1);
    },
  );
}
