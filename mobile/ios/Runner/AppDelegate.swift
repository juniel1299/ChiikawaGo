import Flutter
import UIKit
import GoogleMaps
import CoreLocation

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    if let key = Bundle.main.object(forInfoDictionaryKey: "GMSApiKey") as? String,
       !key.isEmpty, !key.hasPrefix("$(") { GMSServices.provideAPIKey(key) }
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    if let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "ChiiLocation") {
      FlutterMethodChannel(name: "chii/config", binaryMessenger: registrar.messenger())
        .setMethodCallHandler { call, result in
          if call.method == "mapsReady" {
            let key = Bundle.main.object(forInfoDictionaryKey: "GMSApiKey") as? String ?? ""
            result(!key.isEmpty && !key.hasPrefix("$("))
          } else { result(FlutterMethodNotImplemented) }
        }
      FlutterMethodChannel(name: "chii/location", binaryMessenger: registrar.messenger())
        .setMethodCallHandler { call, result in
          if call.method == "isRestricted" {
            result(CLLocationManager().authorizationStatus == .restricted)
          } else { result(FlutterMethodNotImplemented) }
        }
    }
  }
}
