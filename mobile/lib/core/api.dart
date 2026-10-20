import 'package:dio/dio.dart';

class ApiFailure implements Exception {
  const ApiFailure(this.message, {this.status, this.reason});
  final String message;
  final int? status;
  final String? reason;
  @override
  String toString() => message; // Never expose Dio request options or bodies.
}

class Api {
  Api(String baseUrl, {Dio? client}) : dio = client ?? Dio() {
    final uri = Uri.parse(baseUrl);
    if (!uri.hasScheme ||
        !['http', 'https'].contains(uri.scheme) ||
        uri.host.isEmpty) {
      throw const ApiFailure('API 주소 설정을 확인해 주세요.');
    }
    dio.options = BaseOptions(
      baseUrl: baseUrl.replaceAll(RegExp(r'/$'), ''),
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 15),
      sendTimeout: const Duration(seconds: 10),
      followRedirects: false,
    );
  }
  final Dio dio;
  Future<dynamic> send(
    String method,
    String path, {
    Object? data,
    Map<String, dynamic>? query,
    String? access,
  }) async {
    if (!path.startsWith('/') ||
        path.startsWith('//') ||
        path.contains('://')) {
      throw const ApiFailure('허용되지 않은 API 경로입니다.');
    }
    try {
      final response = await dio.request<dynamic>(
        path,
        data: data,
        queryParameters: query,
        options: Options(
          method: method,
          headers: access == null ? null : {'Authorization': 'Bearer $access'},
        ),
      );
      return response.data;
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      final body = e.response?.data;
      String? reason;
      if (body is Map && body['error'] is Map) {
        final details = body['error']['details'];
        if (details is Map && details['reason'] is String) {
          reason = details['reason'];
        }
      }
      throw ApiFailure(
        switch (status) {
          400 => '입력 내용을 확인해 주세요.',
          401 => '다시 로그인해 주세요.',
          403 =>
            reason == 'out_of_range'
                ? 'Spot에 더 가까이 이동해 주세요.'
                : '이 작업을 수행할 수 없습니다.',
          404 => '대상을 찾을 수 없습니다.',
          409 =>
            reason == 'encounter_expired'
                ? '발견 유효 시간이 지났습니다.'
                : '현재 출현 가능한 캐릭터가 없습니다.',
          _ => '연결 또는 처리 결과를 확인할 수 없습니다. 다시 확인해 주세요.',
        },
        status: status,
        reason: reason,
      );
    }
  }
}
