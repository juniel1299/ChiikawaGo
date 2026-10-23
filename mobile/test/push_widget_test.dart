import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:chii_mobile/main.dart';
import 'package:chii_mobile/core/session.dart';
import 'package:chii_mobile/core/location.dart';
import 'package:chii_mobile/features/notifications/controller.dart';

import 'push_test.dart' show PlatformFake, InstallMemory;
import 'support.dart';

void main() {
  testWidgets('opt in and HOME tap return from collection', (tester) async {
    var version = 0;
    final platform = PlatformFake();
    final session = Session(
      FakeApi((m, p, d, q, a) async {
        if (p == '/collection') return page([]);
        if (p.endsWith('/resolve')) return {'binding_version': version};
        return {'binding_version': ++version};
      }),
      MemoryStore(),
    )..user = {'id': 'A'};
    final push = PushController(session, platform, InstallMemory(), 'ios');
    await tester.pumpWidget(
      MaterialApp(
        home: Home(
          session: session,
          push: push,
          location: FakeLocation(() async => Fix(37, 127, 5, DateTime.now())),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('알림 설정'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('알림 켜기 / 등록 갱신'));
    await tester.pumpAndSettle();
    expect(platform.requests, 1);
    await tester.tap(find.text('컬렉션'));
    await tester.pumpAndSettle();
    push.handleTap({
      'version': '1',
      'type': 'OPERATOR_TEST',
      'destination': 'HOME',
      'message_id': '00000000-0000-4000-8000-000000000002',
    });
    await tester.pumpAndSettle();
    expect(find.text('현재 위치로 새로 찾기'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    push.dispose();
    session.dispose();
    platform.close();
  });
}
