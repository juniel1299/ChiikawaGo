package dev.chiiworld.mobile

import android.content.pm.PackageManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        if (android.os.Build.VERSION.SDK_INT >= 26) {
            getSystemService(android.app.NotificationManager::class.java).createNotificationChannel(
                android.app.NotificationChannel("operator_test", "운영자 테스트", android.app.NotificationManager.IMPORTANCE_DEFAULT)
            )
        }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "chii/config")
            .setMethodCallHandler { call, result ->
                if (call.method == "mapsReady") {
                    val info = packageManager.getApplicationInfo(packageName, PackageManager.GET_META_DATA)
                    result.success(!info.metaData.getString("com.google.android.geo.API_KEY").isNullOrBlank())
                } else result.notImplemented()
            }
    }
}
