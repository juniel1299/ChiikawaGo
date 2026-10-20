import 'package:flutter/foundation.dart';

import '../core/api.dart';

/// Screen-scoped state. Passwords exist only as submit arguments, never fields.
class Signup extends ChangeNotifier {
  Signup(this.api);
  final Api api;
  bool busy = false;
  bool _disposed = false;
  Map<String, String> errors = {};
  String? message;

  Future<String?> submit({
    required String email,
    required String displayName,
    required String password,
    required String confirmation,
  }) async {
    if (busy || _disposed) return null;
    errors = {};
    message = null;
    email = email.trim();
    displayName = displayName.trim();
    if (!RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(email) ||
        email.length > 254) {
      errors['email'] = '올바른 이메일을 입력해 주세요.';
    }
    if (displayName.isEmpty || displayName.length > 80) {
      errors['display_name'] = '표시 이름을 1~80자로 입력해 주세요.';
    }
    if (password.length < 8 || password.length > 128) {
      errors['password'] = '비밀번호는 8~128자로 입력해 주세요.';
    }
    if (password != confirmation) errors['confirmation'] = '비밀번호가 일치하지 않습니다.';
    if (errors.isNotEmpty) {
      notifyListeners();
      return null;
    }
    busy = true;
    notifyListeners();
    try {
      final result = await api.send(
        'POST',
        '/auth/register',
        data: {
          'email': email,
          'display_name': displayName,
          'password': password,
        },
      );
      return result['email'] as String;
    } on ApiFailure catch (e) {
      if (_disposed) return null;
      errors = Map.of(e.fields);
      message = errors.remove('non_field_errors') ?? errors.remove('detail');
      message ??= e.status == 400
          ? e.message
          : '가입 결과를 확인할 수 없습니다. 이미 가입됐다면 로그인해 주세요. 다시 시도할 수도 있습니다.';
    } catch (_) {
      if (!_disposed) message = '가입 결과를 확인할 수 없습니다. 로그인하거나 다시 시도해 주세요.';
    } finally {
      busy = false;
      if (!_disposed) notifyListeners();
    }
    return null;
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
