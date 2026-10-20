import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api.dart';

abstract class RefreshStore {
  Future<String?> read();
  Future<void> write(String value);
  Future<void> clear();
}

class SecureRefreshStore implements RefreshStore {
  const SecureRefreshStore();
  static const _storage = FlutterSecureStorage(
    iOptions: IOSOptions(
      accessibility: KeychainAccessibility.unlocked_this_device,
    ),
  );
  static const _key = 'chii.refresh';
  @override
  Future<String?> read() => _storage.read(key: _key);
  @override
  Future<void> write(String value) => _storage.write(key: _key, value: value);
  @override
  Future<void> clear() => _storage.delete(key: _key);
}

class Session extends ChangeNotifier {
  Session(this.api, this.store);
  final Api api;
  final RefreshStore store;
  String? _access;
  Map<String, dynamic>? user;
  bool busy = false;
  bool _closing = false;
  int generation = 0;
  Future<void>? _refreshing;
  Future<void>? _login;
  String? _latestRefresh;
  bool get authenticated => user != null && !_closing;

  Future<void> restore() async {
    busy = true;
    notifyListeners();
    try {
      if (await store.read() != null) {
        await _refresh();
        user = Map<String, dynamic>.from(await request('GET', '/me'));
      }
    } catch (_) {
      _access = null;
      user = null;
      // Refresh ambiguity is handled inside _doRefresh; never infer success.
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<void> login(String email, String password) {
    if (busy || _closing) return Future.value();
    return _login = _doLogin(email, password).whenComplete(() => _login = null);
  }

  Future<void> _doLogin(String email, String password) async {
    if (busy || _closing) return;
    busy = true;
    notifyListeners();
    try {
      await _refreshing;
      generation++;
      user = null;
      _access = null;
      await store.clear();
      final pair = await api.send(
        'POST',
        '/auth/token',
        data: {'email': email, 'password': password},
      );
      await _savePair(pair);
      user = Map<String, dynamic>.from(await request('GET', '/me'));
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<void> _savePair(dynamic pair) async {
    if (pair is! Map ||
        pair['access'] is! String ||
        pair['refresh'] is! String) {
      throw const ApiFailure('인증 응답을 확인할 수 없습니다.');
    }
    _latestRefresh = pair['refresh'];
    try {
      await store.write(pair['refresh']);
    } catch (_) {
      _access = null;
      throw const ApiFailure('보안 저장소에 로그인 정보를 저장하지 못했습니다.');
    }
    if (!_closing) _access = pair['access'];
  }

  Future<void> _refresh() {
    if (_closing) return Future.error(const ApiFailure('로그아웃 중입니다.'));
    return _refreshing ??= _doRefresh().whenComplete(() {
      _refreshing = null;
    });
  }

  Future<void> _doRefresh() async {
    final refresh = await store.read();
    if (refresh == null) throw const ApiFailure('다시 로그인해 주세요.', status: 401);
    try {
      final pair = await api.send(
        'POST',
        '/auth/token/refresh',
        data: {'refresh': refresh},
      );
      await _savePair(pair);
    } catch (_) {
      // Rotation may have committed before a lost response. Never replay the old refresh.
      _access = null;
      user = null;
      generation++;
      await store.clear();
      notifyListeners();
      rethrow;
    }
  }

  Future<dynamic> request(
    String method,
    String path, {
    Object? data,
    Map<String, dynamic>? query,
  }) async {
    if (_closing) throw const ApiFailure('로그아웃 중입니다.');
    final epoch = generation;
    final sentAccess = _access;
    try {
      final result = await api.send(
        method,
        path,
        data: data,
        query: query,
        access: sentAccess,
      );
      if (generation != epoch || _closing) {
        throw const ApiFailure('세션이 변경되었습니다.');
      }
      return result;
    } on ApiFailure catch (e) {
      if (e.status != 401 || generation != epoch || _closing) rethrow;
      if (_access == sentAccess) await _refresh();
      if (generation != epoch || _closing) {
        throw const ApiFailure('다시 로그인해 주세요.');
      }
      // Exactly one retry; no recursive interceptor.
      try {
        final result = await api.send(
          method,
          path,
          data: data,
          query: query,
          access: _access,
        );
        if (generation != epoch || _closing) {
          throw const ApiFailure("세션이 변경되었습니다.");
        }
        return result;
      } on ApiFailure catch (retryError) {
        if (retryError.status == 401) {
          _access = null;
          user = null;
          generation++;
          await store.clear();
          notifyListeners();
        }
        rethrow;
      }
    }
  }

  Future<bool> logout() async {
    if (_closing) return false;
    _closing = true;
    generation++;
    user = null;
    _access = null;
    notifyListeners();
    bool revoked = false;
    try {
      try {
        await _login;
        await _refreshing;
      } catch (_) {
        /* Still clear local credentials. */
      }
      final refresh = _latestRefresh ?? await store.read();
      if (refresh != null) {
        try {
          await api.send('POST', '/auth/logout', data: {'refresh': refresh});
          revoked = true;
        } on ApiFailure catch (e) {
          revoked = e.status == 401;
        }
      } else {
        revoked = true;
      }
    } finally {
      try {
        await store.clear();
      } finally {
        _latestRefresh = null;
        _access = null;
        _closing = false;
        notifyListeners();
      }
    }
    return revoked;
  }
}
