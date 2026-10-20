import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:chii_mobile/main.dart';
import 'package:chii_mobile/core/api.dart';
import 'package:chii_mobile/core/session.dart';

import 'support.dart';

Future<void> form(WidgetTester t) async {
  await t.enterText(
    find.byKey(const ValueKey('signup_email')),
    'new@example.com',
  );
  await t.enterText(find.byKey(const ValueKey('signup_display_name')), 'New');
  await t.enterText(
    find.byKey(const ValueKey('signup_password')),
    'Walking-park-42!',
  );
  await t.enterText(
    find.byKey(const ValueKey('signup_confirmation')),
    'Walking-park-42!',
  );
}

void main() {
  testWidgets('login signup loading success returns email but does not login', (
    t,
  ) async {
    final pending = Completer<dynamic>();
    final store = MemoryStore();
    var calls = 0;
    final session = Session(
      FakeApi((m, p, d, q, a) {
        expect(p, '/auth/register');
        calls++;
        return pending.future;
      }),
      store,
    );
    await t.pumpWidget(MaterialApp(home: Login(session: session)));
    await t.tap(find.text('회원가입'));
    await t.pumpAndSettle();
    await form(t);
    await t.ensureVisible(find.text('가입하기'));
    await t.tap(find.text('가입하기'));
    await t.pump();
    expect(t.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull);
    expect(calls, 1);
    pending.complete({'email': 'new@example.com'});
    await t.pumpAndSettle();
    expect(find.text('로그인'), findsOneWidget);
    expect(find.text('new@example.com'), findsOneWidget);
    expect(session.authenticated, false);
    expect(store.value, isNull);
    expect(
      t.widget<TextField>(find.byType(TextField).last).controller!.text,
      isEmpty,
    );
  });
  testWidgets('required errors are shown without API request', (t) async {
    await t.pumpWidget(
      MaterialApp(
        home: Login(
          session: Session(
            FakeApi((m, p, d, q, a) async => fail('no request')),
            MemoryStore(),
          ),
        ),
      ),
    );
    await t.tap(find.text('회원가입'));
    await t.pumpAndSettle();
    await t.ensureVisible(find.text('가입하기'));
    await t.tap(find.text('가입하기'));
    await t.pumpAndSettle();
    expect(find.text('올바른 이메일을 입력해 주세요.'), findsOneWidget);
  });
  testWidgets('duplicate error clears passwords and offers login', (t) async {
    await t.pumpWidget(
      MaterialApp(
        home: Login(
          session: Session(
            FakeApi(
              (m, p, d, q, a) async => throw const ApiFailure(
                '입력 오류',
                status: 400,
                fields: {'email': '이미 사용 중인 이메일입니다.'},
              ),
            ),
            MemoryStore(),
          ),
        ),
      ),
    );
    await t.tap(find.text('회원가입'));
    await t.pumpAndSettle();
    await form(t);
    await t.ensureVisible(find.text('가입하기'));
    await t.tap(find.text('가입하기'));
    await t.pumpAndSettle();
    expect(find.text('이미 사용 중인 이메일입니다.'), findsOneWidget);
    expect(
      t
          .widget<TextField>(find.byKey(const ValueKey('signup_password')))
          .controller!
          .text,
      isEmpty,
    );
    await t.ensureVisible(find.text('이미 계정이 있어요 · 로그인으로'));
    await t.tap(find.text('이미 계정이 있어요 · 로그인으로'));
    await t.pumpAndSettle();
    expect(find.text('new@example.com'), findsOneWidget);
  });
}
