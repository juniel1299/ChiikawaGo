import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:chii_mobile/main.dart';
import 'package:chii_mobile/core/session.dart';
import 'package:chii_mobile/core/location.dart';

import 'support.dart';

void main() {
  testWidgets(
    'Riverpod auth state switches user scope and clears it on logout',
    (tester) async {
      final session = Session(
        FakeApi((m, p, d, q, a) async {
          if (p == '/auth/token') return {'access': 'a', 'refresh': 'r'};
          if (p == '/me') return {'id': 'user'};
          return null;
        }),
        MemoryStore(),
      );
      await tester.pumpWidget(
        ProviderScope(
          overrides: [sessionProvider.overrideWithValue(session)],
          child: const ChiiApp(),
        ),
      );
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(TextField).first,
        'user@example.invalid',
      );
      await tester.enterText(find.byType(TextField).last, 'test');
      await tester.tap(find.text('로그인'));
      await tester.pumpAndSettle();
      expect(find.text('현재 위치로 새로 찾기'), findsOneWidget);
      await tester.tap(find.byTooltip('로그아웃'));
      await tester.pumpAndSettle();
      expect(find.text('로그인'), findsOneWidget);
      expect(find.text('현재 위치로 새로 찾기'), findsNothing);
    },
  );

  testWidgets('login error is safe and password is cleared', (tester) async {
    final session = Session(
      FakeApi((m, p, d, q, a) async => throw StateError('private')),
      MemoryStore(),
    );
    await tester.pumpWidget(MaterialApp(home: Login(session: session)));
    await tester.enterText(find.byType(TextField).first, 'u@example.invalid');
    await tester.enterText(find.byType(TextField).last, 'private');
    await tester.tap(find.text('로그인'));
    await tester.pumpAndSettle();
    expect(find.textContaining('private'), findsNothing);
    expect(find.textContaining('작업을 완료'), findsOneWidget);
  });
  testWidgets('denied location does not block collection navigation', (
    tester,
  ) async {
    final session = Session(
      FakeApi((m, p, d, q, a) async => page([])),
      MemoryStore(),
    )..user = {'id': 'u'};
    await tester.pumpWidget(
      MaterialApp(
        home: Home(
          session: session,
          location: FakeLocation(
            () async => throw const LocationIssue('denied', '권한 거부'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('현재 위치로 새로 찾기'));
    await tester.pumpAndSettle();
    expect(find.text('권한 거부'), findsOneWidget);
    await tester.tap(find.text('컬렉션'));
    await tester.pumpAndSettle();
    expect(find.text('아직 획득한 캐릭터가 없습니다.'), findsOneWidget);
  });
}
