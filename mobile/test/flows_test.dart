import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:chii_mobile/core/session.dart';
import 'package:chii_mobile/core/api.dart';
import 'package:chii_mobile/core/location.dart';
import 'package:chii_mobile/features/flows.dart';

import 'support.dart';

void main() {
  Fix point(double x) => Fix(x, 127, 10, DateTime.now());
  test('stale Nearby result cannot replace refreshed query', () async {
    final old = Completer<dynamic>();
    int calls = 0;
    final session = Session(
      FakeApi((m, p, d, q, a) async {
        calls++;
        return calls == 1
            ? old.future
            : page([
                {'id': 'new'},
              ]);
      }),
      MemoryStore(),
    );
    final nearby = Nearby(session, FakeLocation(() async => point(37)));
    final first = nearby.refresh();
    await Future<void>.delayed(Duration.zero);
    await nearby.refresh();
    old.complete(
      page([
        {'id': 'old'},
      ]),
    );
    await first;
    expect(nearby.spots.single['id'], 'new');
  });
  test(
    'pagination retains fix, ignores next host, reset acquires new fix',
    () async {
      final queries = <Map<String, dynamic>>[];
      int n = 0;
      final session = Session(
        FakeApi((m, p, d, q, a) async {
          expect(p, '/spots/nearby');
          queries.add({...q!});
          return page([
            {'id': '$n'},
          ], more: true);
        }),
        MemoryStore(),
      );
      final location = FakeLocation(() async => point(37.0 + (n++)));
      final nearby = Nearby(session, location);
      await nearby.refresh();
      await nearby.next();
      await nearby.refresh();
      expect(queries[0]['latitude'], queries[1]['latitude']);
      expect(queries[1]['page'], 2);
      expect(queries[2]['page'], 1);
      expect(location.calls, 2);
    },
  );
  for (final code in [
    'denied',
    'permanently_denied',
    'restricted',
    'disabled',
    'timeout',
    'error',
    'stale',
  ]) {
    test('location $code prevents Nearby request', () async {
      var requests = 0;
      final session = Session(
        FakeApi((m, p, d, q, a) async {
          requests++;
          return null;
        }),
        MemoryStore(),
      );
      final nearby = Nearby(
        session,
        FakeLocation(() async => throw LocationIssue(code, code)),
      );
      await nearby.refresh();
      expect(nearby.error, code);
      expect(requests, 0);
    });
  }
  test('approximate location is retained for UI guidance', () async {
    final session = Session(
      FakeApi((m, p, d, q, a) async => page([])),
      MemoryStore(),
    );
    final nearby = Nearby(
      session,
      FakeLocation(
        () async => Fix(37, 127, 500, DateTime.now(), approximate: true),
      ),
    );
    await nearby.refresh();
    expect(nearby.fix!.approximate, true);
  });
  test(
    'Encounter obtains a new fix and Capture retries same ID without location',
    () async {
      final bodies = <Object?>[];
      final paths = <String>[];
      int captures = 0;
      final session = Session(
        FakeApi((m, p, d, q, a) async {
          paths.add(p);
          bodies.add(d);
          if (p == '/encounters') return {'id': 'enc', 'status': 'active'};
          if (p.endsWith('/capture')) {
            if (captures++ == 0) throw const ApiFailure('lost');
            return {'id': 'result', 'status': 'captured'};
          }
          return page([]);
        }),
        MemoryStore(),
      );
      final location = FakeLocation(() async => point(38));
      final flow = Encounters(session, location);
      await flow.create('spot');
      expect((bodies.first as Map)['latitude'], 38);
      expect(location.calls, 1);
      expect(await flow.catchEncounter(), false);
      expect(await flow.catchEncounter(), true);
      expect(paths.sublist(1), [
        '/encounters/enc/capture',
        '/encounters/enc/capture',
      ]);
      expect(bodies.last, {});
      expect(location.calls, 1);
    },
  );
  test('duplicate Capture tap starts only one request', () async {
    final done = Completer<dynamic>();
    int n = 0;
    final flow = Encounters(
      Session(
        FakeApi((m, p, d, q, a) async {
          n++;
          return done.future;
        }),
        MemoryStore(),
      ),
      FakeLocation(() async => point(37)),
    )..encounter = {'id': 'e'};
    final first = flow.catchEncounter();
    expect(await flow.catchEncounter(), false);
    done.complete({'id': 'r'});
    expect(await first, true);
    expect(n, 1);
  });
  test('Encounter timeout is not automatically retried', () async {
    int n = 0;
    final flow = Encounters(
      Session(
        FakeApi((m, p, d, q, a) async {
          n++;
          throw const ApiFailure('lost');
        }),
        MemoryStore(),
      ),
      FakeLocation(() async => point(37)),
    );
    await flow.create('s');
    expect(n, 1);
    expect(flow.encounter, null);
  });
  test('Collection appends pages and resets after Capture', () async {
    final session = Session(
      FakeApi(
        (m, p, d, q, a) async => page([
          {'id': '${q!['page']}'},
        ], more: q['page'] == 1),
      ),
      MemoryStore(),
    );
    final flow = Collection(session);
    await flow.load(reset: true);
    await flow.load();
    expect(flow.items.length, 2);
    await flow.load(reset: true);
    expect(flow.items.length, 1);
  });
}
