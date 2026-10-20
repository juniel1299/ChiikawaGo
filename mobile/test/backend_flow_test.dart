import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:chii_mobile/core/api.dart';
import 'package:chii_mobile/core/session.dart';
import 'package:chii_mobile/core/location.dart';
import 'package:chii_mobile/features/flows.dart';

import 'support.dart';

void main() {
  test(
    'real Django/PostGIS login → Nearby → Encounter → Capture → Collection',
    () async {
      final store = MemoryStore();
      final session = Session(Api('http://127.0.0.1:18081/api/v1'), store);
      await session.login(
        'mobile@example.invalid',
        Platform.environment['CHII_TEST_PASSWORD']!,
      );
      expect(session.authenticated, true);
      final location = FakeLocation(
        () async => Fix(37, 127, 5, DateTime.now()),
      );
      final nearby = Nearby(session, location);
      await nearby.refresh();
      expect(nearby.error, isNull);
      expect(nearby.spots, isNotEmpty);
      final flow = Encounters(session, location);
      await flow.create(nearby.spots.first['id']);
      expect(flow.error, isNull);
      expect(flow.encounter!['status'], 'active');
      expect(await flow.catchEncounter(), true);
      final first = flow.capture;
      expect(await flow.catchEncounter(), true);
      expect(flow.capture, first);
      final collection = Collection(session);
      await collection.load(reset: true);
      expect(collection.error, isNull);
      expect(collection.items.length, 1);
      expect(collection.items.single['encounter_id'], flow.encounter!['id']);
      final restored = Session(Api('http://127.0.0.1:18081/api/v1'), store);
      await restored.restore();
      expect(restored.authenticated, true);
      expect(await restored.logout(), true);
      expect(store.value, null);
    },
    skip: Platform.environment['CHII_BACKEND_INTEGRATION'] != '1',
  );
}
