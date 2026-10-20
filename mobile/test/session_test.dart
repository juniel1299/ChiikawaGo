import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:chii_mobile/core/session.dart';
import 'package:chii_mobile/core/api.dart';

import 'support.dart';

void main() {
  test('login persists only refresh and sends access in memory', () async {
    final store = MemoryStore();
    final session = Session(
      FakeApi((m, p, d, q, a) async {
        if (p == '/auth/token') {
          return {'access': 'access-memory', 'refresh': 'refresh-secure'};
        }
        expect(a, 'access-memory');
        return {'id': 'u'};
      }),
      store,
    );
    await session.login('e', 'p');
    expect(store.value, 'refresh-secure');
    expect(session.authenticated, true);
  });
  test('restore rotates before me', () async {
    final calls = <String>[];
    final store = MemoryStore()..value = 'old';
    final session = Session(
      FakeApi((m, p, d, q, a) async {
        calls.add(p);
        if (p.endsWith('/refresh')) return {'access': 'a', 'refresh': 'new'};
        return {'id': 'u'};
      }),
      store,
    );
    await session.restore();
    expect(calls, ['/auth/token/refresh', '/me']);
    expect(store.value, 'new');
    expect(session.authenticated, true);
  });
  test(
    'simultaneous 401s share one refresh including late old-token response',
    () async {
      final entered = Completer<void>(), release = Completer<void>();
      int refresh = 0;
      final store = MemoryStore()..value = 'r';
      final session = Session(
        FakeApi((m, p, d, q, a) async {
          if (p.endsWith('/refresh')) {
            refresh++;
            entered.complete();
            await release.future;
            return {'access': 'new', 'refresh': 'rotated'};
          }
          if (a != 'new') throw const ApiFailure('expired', status: 401);
          return {'ok': true};
        }),
        store,
      );
      final first = session.request('GET', '/a'),
          second = session.request('GET', '/b');
      await entered.future;
      release.complete();
      await Future.wait([first, second]);
      expect(refresh, 1);
      expect(store.value, 'rotated');
    },
  );
  test('second 401 fails without an infinite refresh loop', () async {
    int refresh = 0, requests = 0;
    final store = MemoryStore()..value = 'r';
    final session = Session(
      FakeApi((m, p, d, q, a) async {
        if (p.endsWith('/refresh')) {
          refresh++;
          return {'access': 'a', 'refresh': 'r2'};
        }
        requests++;
        throw const ApiFailure('401', status: 401);
      }),
      store,
    );
    await expectLater(
      session.request('GET', '/me'),
      throwsA(isA<ApiFailure>()),
    );
    expect(refresh, 1);
    expect(requests, 2);
    expect(store.value, null);
  });
  test(
    'lost refresh response clears ambiguous old token, never repeats',
    () async {
      int n = 0;
      final store = MemoryStore()..value = 'r';
      final session = Session(
        FakeApi((m, p, d, q, a) async {
          if (p.endsWith('/refresh')) {
            n++;
            throw const ApiFailure('timeout');
          }
          throw const ApiFailure('401', status: 401);
        }),
        store,
      );
      await expectLater(
        session.request('GET', '/me'),
        throwsA(isA<ApiFailure>()),
      );
      expect(n, 1);
      expect(store.value, null);
    },
  );
  test('secure storage failure does not authenticate', () async {
    final store = MemoryStore()..failWrite = true;
    final session = Session(
      FakeApi((m, p, d, q, a) async => {'access': 'a', 'refresh': 'r'}),
      store,
    );
    await expectLater(session.login('e', 'p'), throwsA(isA<ApiFailure>()));
    expect(session.authenticated, false);
    expect(store.value, null);
  });
  test(
    'logout waits for refresh then revokes rotated token without resurrection',
    () async {
      final entered = Completer<void>(), release = Completer<void>();
      Object? revoked;
      final store = MemoryStore()..value = 'r';
      final session = Session(
        FakeApi((m, p, d, q, a) async {
          if (p.endsWith('/refresh')) {
            entered.complete();
            await release.future;
            return {'access': 'a', 'refresh': 'new'};
          }
          if (p.endsWith('/logout')) {
            revoked = d;
            return null;
          }
          throw const ApiFailure('401', status: 401);
        }),
        store,
      );
      final request = expectLater(
        session.request('GET', '/me'),
        throwsA(isA<ApiFailure>()),
      );
      await entered.future;
      final logout = session.logout();
      release.complete();
      await request;
      expect(await logout, true);
      expect(revoked, {'refresh': 'new'});
      expect(store.value, null);
      expect(session.authenticated, false);
    },
  );
  test('logout racing login revokes its result and keeps signed out', () async {
    final entered = Completer<void>(), release = Completer<void>();
    final store = MemoryStore();
    final session = Session(
      FakeApi((m, p, d, q, a) async {
        if (p == '/auth/token') {
          entered.complete();
          await release.future;
          return {'access': 'a', 'refresh': 'r'};
        }
        return null;
      }),
      store,
    );
    final login = expectLater(
      session.login('e', 'p'),
      throwsA(isA<ApiFailure>()),
    );
    await entered.future;
    final logout = session.logout();
    release.complete();
    await login;
    await logout;
    expect(session.authenticated, false);
    expect(store.value, null);
  });
  test(
    'offline logout clears local state but reports unconfirmed revocation',
    () async {
      final store = MemoryStore()..value = 'r';
      final session = Session(
        FakeApi((m, p, d, q, a) async => throw const ApiFailure('offline')),
        store,
      )..user = {'id': 'u'};
      expect(await session.logout(), false);
      expect(store.value, null);
      expect(session.authenticated, false);
    },
  );
}
