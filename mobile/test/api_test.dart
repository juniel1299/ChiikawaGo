import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:chii_mobile/core/api.dart';

class Adapter implements HttpClientAdapter {
  Adapter(this.handle);
  final ResponseBody Function(RequestOptions) handle;
  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async => handle(options);
  @override
  void close({bool force = false}) {}
}

void main() {
  test('safe errors never echo body headers or request URI', () async {
    final dio = Dio()
      ..httpClientAdapter = Adapter(
        (options) => ResponseBody.fromString(
          '{"private":"secret"}',
          500,
          headers: {
            Headers.contentTypeHeader: ['application/json'],
          },
        ),
      );
    final api = Api('https://example.invalid/api/v1', client: dio);
    try {
      await api.send(
        'POST',
        '/encounters',
        data: {'password': 'secret', 'latitude': 37.123456},
        access: 'private-token',
      );
      fail('expected failure');
    } on ApiFailure catch (e) {
      expect(e.toString(), isNot(contains('secret')));
      expect(e.toString(), isNot(contains('37.123456')));
      expect(e.toString(), isNot(contains('private-token')));
    }
  });
  test('external pagination URL cannot receive Authorization', () async {
    final dio = Dio()
      ..httpClientAdapter = Adapter((options) {
        fail('must not fetch');
      });
    await expectLater(
      Api(
        'https://example.invalid/api/v1',
        client: dio,
      ).send('GET', 'https://other.invalid', access: 'sensitive'),
      throwsA(isA<ApiFailure>()),
    );
  });
  for (final status in [200, 201]) {
    test('Encounter $status body is preserved', () async {
      final dio = Dio()
        ..httpClientAdapter = Adapter((options) {
          expect(options.followRedirects, false);
          return ResponseBody.fromString(
            '{"id":"e"}',
            status,
            headers: {
              Headers.contentTypeHeader: ['application/json'],
            },
          );
        });
      expect(
        await Api(
          'https://example.invalid/api/v1',
          client: dio,
        ).send('POST', '/encounters', data: {}),
        {'id': 'e'},
      );
    });
  }
}
