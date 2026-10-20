import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:chii_mobile/core/api.dart';
import 'package:chii_mobile/features/signup.dart';

import 'support.dart';
import 'api_test.dart' show Adapter;

Future<String?> submit(
  Signup state, {
  String email = 'new@example.com',
  String name = 'New',
  String password = 'Walking-park-42!',
  String confirmation = 'Walking-park-42!',
}) => state.submit(
  email: email,
  displayName: name,
  password: password,
  confirmation: confirmation,
);

void main() {
  test('register sends only server fields without authorization or token operations', () async {
    final state = Signup(
      FakeApi((m, p, d, q, a) async {
        expect(m, 'POST');
        expect(p, '/auth/register');
        expect(a, isNull);
        expect(d, {
          'email': 'new@example.com',
          'display_name': 'New',
          'password': 'Walking-park-42!',
        });
        return {'email': 'new@example.com'};
      }),
    );
    expect(await submit(state), 'new@example.com');
    expect(state.busy, false);
  });
  for (final entry in ['email', 'password', 'confirmation', 'display_name']) {
    test('invalid $entry prevents request', () async {
      final state = Signup(
        FakeApi((m, p, d, q, a) async => fail('no request')),
      );
      await submit(
        state,
        email: entry == 'email' ? 'bad' : 'new@example.com',
        name: entry == 'display_name' ? '' : 'New',
        password: entry == 'password' ? '1111' : 'Walking-park-42!',
        confirmation: entry == 'confirmation'
            ? 'different'
            : 'Walking-park-42!',
      );
      expect(state.errors, contains(entry));
    });
  }
  test('duplicate submission does not send another request', () async {
    final pending = Completer<dynamic>();
    var calls = 0;
    final state = Signup(
      FakeApi((m, p, d, q, a) {
        calls++;
        return pending.future;
      }),
    );
    final first = submit(state);
    expect(state.busy, true);
    expect(await submit(state), isNull);
    expect(calls, 1);
    pending.complete({'email': 'new@example.com'});
    await first;
  });
  for (final field in ['email', 'password', 'non_field_errors']) {
    test(
      'actual error envelope maps $field without leaking password',
      () async {
        final message = field == 'email'
            ? '이미 사용 중인 이메일입니다.'
            : '서버 검증 오류 Walking-park-42!';
        final dio = Dio()
          ..httpClientAdapter = Adapter(
            (o) => ResponseBody.fromString(
              jsonEncode({
                'error': {
                  'code': 'validation_error',
                  'message': '요청을 처리할 수 없습니다.',
                  'details': {
                    field: [message],
                  },
                },
              }),
              400,
              headers: {
                Headers.contentTypeHeader: ['application/json'],
              },
            ),
          );
        final state = Signup(
          Api('https://example.invalid/api/v1', client: dio),
        );
        expect(await submit(state), isNull);
        final text = field == 'non_field_errors'
            ? state.message
            : state.errors[field];
        expect(text, isNotNull);
        expect(text, isNot(contains('Walking-park-42!')));
        if (field == 'email') expect(text, contains('이미 사용'));
      },
    );
  }
  for (final type in [
    DioExceptionType.connectionTimeout,
    DioExceptionType.connectionError,
  ]) {
    test('$type is ambiguous and never automatically retried', () async {
      var calls = 0;
      final dio = Dio()
        ..httpClientAdapter = Adapter((o) {
          calls++;
          throw DioException(requestOptions: o, type: type, error: 'private');
        });
      final state = Signup(Api('https://example.invalid/api/v1', client: dio));
      await submit(state);
      expect(calls, 1);
      expect(state.message, contains('가입 결과'));
      expect(state.message, isNot(contains('private')));
      expect(state.busy, false);
    });
  }
  test('500 raw response is not displayed', () async {
    final dio = Dio()
      ..httpClientAdapter = Adapter(
        (o) => ResponseBody.fromString(
          '{"error":{"message":"private","details":{"password":["private"]}}}',
          500,
          headers: {
            Headers.contentTypeHeader: ['application/json'],
          },
        ),
      );
    final state = Signup(Api('https://example.invalid/api/v1', client: dio));
    await submit(state);
    expect(state.errors, isEmpty);
    expect(state.message, isNot(contains('private')));
  });
  test('disposed signup safely ignores in-flight failure', () async {
    final pending = Completer<dynamic>();
    final state = Signup(FakeApi((m, p, d, q, a) => pending.future));
    final task = submit(state);
    state.dispose();
    pending.completeError(const ApiFailure('error'));
    expect(await task, isNull);
  });
}
