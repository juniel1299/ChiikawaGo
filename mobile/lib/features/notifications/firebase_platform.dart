import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import 'controller.dart';

const pushEnabled = bool.fromEnvironment('PUSH_ENABLED', defaultValue: false);
Future<bool> initializePush() async {
  if (!pushEnabled) return false;
  try {
    // Use native environment-specific resources, including terminated app delivery.
    await Firebase.initializeApp();
    // Token generation begins only after the user opts in.
    await FirebaseMessaging.instance.setAutoInitEnabled(false);
    await FirebaseMessaging.instance
        .setForegroundNotificationPresentationOptions(
          alert: false,
          badge: false,
          sound: false,
        );
    return true;
  } catch (_) {
    return false;
  }
}

class FirebasePushPlatform implements PushPlatform {
  final messaging = FirebaseMessaging.instance;
  String? registeredId;
  @override
  Future<String> permission({bool request = false}) async {
    final settings = request
        ? await messaging.requestPermission(
            alert: true,
            badge: true,
            sound: true,
          )
        : await messaging.getNotificationSettings();
    return switch (settings.authorizationStatus) {
      AuthorizationStatus.authorized => 'authorized',
      AuthorizationStatus.provisional => 'provisional',
      AuthorizationStatus.denied => 'denied',
      _ => 'not_determined',
    };
  }

  @override
  Future<String?> token() async {
    if (Platform.isIOS && await messaging.getAPNSToken() == null) return null;
    if (registeredId != null) return registeredId;
    final received = messaging.onRegistered.first.timeout(
      const Duration(seconds: 15),
    );
    // Attach error handlers to both futures before either can fail.
    final results = await Future.wait<Object?>([
      received,
      messaging.register(),
    ]);
    return registeredId = results.first as String;
  }

  @override
  Stream<String> get rotations => messaging.onRegistered.map((id) {
    registeredId = id;
    return id;
  }).distinct();
  @override
  Stream<Map<String, dynamic>> get foreground =>
      FirebaseMessaging.onMessage.map((m) => m.data);
  @override
  Stream<Map<String, dynamic>> get taps =>
      FirebaseMessaging.onMessageOpenedApp.map((m) => m.data);
  @override
  Future<Map<String, dynamic>?> initialTap() async =>
      (await messaging.getInitialMessage())?.data;
}
