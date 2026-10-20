import 'package:chii_mobile/core/api.dart';
import 'package:chii_mobile/core/session.dart';
import 'package:chii_mobile/core/location.dart';

typedef Handler = Future<dynamic> Function(
  String method,
  String path,
  Object? data,
  Map<String, dynamic>? query,
  String? access,
);

class FakeApi extends Api {
  FakeApi(this.handler) : super('https://example.invalid/api/v1');
  final Handler handler;
  @override
  Future<dynamic> send(
    String method,
    String path, {
    Object? data,
    Map<String, dynamic>? query,
    String? access,
  }) => handler(method, path, data, query, access);
}

class MemoryStore implements RefreshStore {
  String? value;
  bool failWrite = false;
  @override
  Future<String?> read() async => value;
  @override
  Future<void> write(String v) async {
    if (failWrite) throw StateError('unavailable');
    value = v;
  }

  @override
  Future<void> clear() async {
    value = null;
  }
}

class FakeLocation implements LocationSource {
  FakeLocation(this.obtain);
  final Future<Fix> Function() obtain;
  int calls = 0;
  @override
  Future<Fix> current({bool requestPermission = true}) {
    calls++;
    return obtain();
  }

  @override
  Future<void> openSettings() async {}
}

Map<String, dynamic> page(
  List<Map<String, dynamic>> rows, {
  bool more = false,
}) => {
  'count': rows.length,
  'next': more ? 'https://untrusted.invalid/?page=2' : null,
  'previous': null,
  'results': rows,
};
