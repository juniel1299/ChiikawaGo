import 'package:flutter/foundation.dart';

import '../core/api.dart';
import '../core/location.dart';
import '../core/session.dart';

String safeMessage(Object e) => e is ApiFailure
    ? e.message
    : e is LocationIssue
    ? e.message
    : '작업을 완료하지 못했습니다. 다시 시도해 주세요.';

class Nearby extends ChangeNotifier {
  Nearby(this.session, this.location);
  final Session session;
  final LocationSource location;
  Fix? fix;
  List<Map<String, dynamic>> spots = [];
  String? error;
  bool busy = false, more = false, disposed = false;
  int _version = 0, _page = 0;
  void _emit() {
    if (!disposed) notifyListeners();
  }

  // On resume invalidate stale results without initiating an API request.
  void invalidate() {
    _version++;
    busy = false;
    fix = null;
    spots = [];
    more = false;
    _emit();
  }

  Future<void> refresh({bool requestPermission = true}) async {
    final version = ++_version;
    busy = true;
    error = null;
    fix = null;
    spots = [];
    _page = 0;
    more = false;
    _emit();
    try {
      final point = await location.current(
        requestPermission: requestPermission,
      );
      if (version != _version || disposed) return;
      final result = await session.request(
        'GET',
        '/spots/nearby',
        query: {...point.query, 'radius_m': 1000, 'page': 1},
      );
      if (version != _version || disposed) return;
      fix = point;
      spots = _rows(result);
      _page = 1;
      more = result['next'] != null;
    } catch (e) {
      if (version == _version) error = safeMessage(e);
    } finally {
      if (version == _version) {
        busy = false;
        _emit();
      }
    }
  }

  Future<void> next() async {
    if (busy || !more || fix == null) return;
    final version = _version;
    busy = true;
    error = null;
    _emit();
    try {
      final result = await session.request(
        'GET',
        '/spots/nearby',
        query: {...fix!.query, 'radius_m': 1000, 'page': _page + 1},
      );
      if (version != _version || disposed) return;
      spots = [...spots, ..._rows(result)];
      _page++;
      more = result['next'] != null;
    } catch (e) {
      if (version == _version) error = safeMessage(e);
    } finally {
      if (version == _version) {
        busy = false;
        _emit();
      }
    }
  }

  @override
  void dispose() {
    disposed = true;
    _version++;
    super.dispose();
  }
}

List<Map<String, dynamic>> _rows(dynamic result) => (result['results'] as List)
    .map((e) => Map<String, dynamic>.from(e))
    .toList();

class Encounters extends ChangeNotifier {
  Encounters(this.session, this.location);
  final Session session;
  final LocationSource location;
  Map<String, dynamic>? encounter, capture;
  bool busy = false, _disposed = false;
  String? error;
  void _emit() {
    if (!_disposed) notifyListeners();
  }

  Future<void> create(String spotId) async {
    if (busy) return;
    busy = true;
    error = null;
    encounter = null;
    capture = null;
    _emit();
    try {
      // Intentionally acquire a new fix, never the Nearby query or map camera.
      final point = await location.current();
      encounter = Map<String, dynamic>.from(
        await session.request(
          'POST',
          '/encounters',
          data: {'spot_id': spotId, ...point.query},
        ),
      );
    } catch (e) {
      error = safeMessage(e);
    } finally {
      busy = false;
      _emit();
    }
  }

  Future<void> reload() async {
    if (busy || encounter == null) return;
    busy = true;
    error = null;
    _emit();
    try {
      encounter = Map<String, dynamic>.from(
        await session.request('GET', '/encounters/${encounter!['id']}'),
      );
    } catch (e) {
      error = safeMessage(e);
    } finally {
      busy = false;
      _emit();
    }
  }

  Future<bool> catchEncounter() async {
    if (busy || encounter == null) return false;
    busy = true;
    error = null;
    _emit();
    try {
      capture = Map<String, dynamic>.from(
        await session.request(
          'POST',
          '/encounters/${encounter!['id']}/capture',
          data: <String, dynamic>{},
        ),
      );
      encounter = {...encounter!, 'status': 'captured'};
      return true;
    } catch (e) {
      error = safeMessage(e);
      return false;
    } finally {
      busy = false;
      _emit();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

class Collection extends ChangeNotifier {
  Collection(this.session);
  final Session session;
  List<Map<String, dynamic>> items = [];
  bool busy = false, more = false, _disposed = false;
  String? error;
  int _page = 0, _version = 0;
  void _emit() {
    if (!_disposed) notifyListeners();
  }

  Future<void> load({bool reset = false}) async {
    if (busy && !reset) return;
    if (!reset && _page > 0 && !more) return;
    if (reset) {
      _version++;
      _page = 0;
      items = [];
      more = false;
    }
    final version = _version;
    busy = true;
    error = null;
    _emit();
    try {
      final result = await session.request(
        'GET',
        '/collection',
        query: {'page': _page + 1},
      );
      if (version != _version || _disposed) return;
      items = [...items, ..._rows(result)];
      _page++;
      more = result['next'] != null;
    } catch (e) {
      if (version == _version) error = safeMessage(e);
    } finally {
      if (version == _version) {
        busy = false;
        _emit();
      }
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _version++;
    super.dispose();
  }
}
