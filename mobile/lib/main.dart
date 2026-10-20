import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import 'core/api.dart';
import 'core/session.dart';
import 'core/location.dart';
import 'features/flows.dart';
import 'features/signup_screen.dart';

const apiUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000/api/v1',
);
const mapsEnabled = bool.fromEnvironment('MAPS_ENABLED', defaultValue: false);
final sessionProvider = Provider<Session>((ref) {
  final session = Session(Api(apiUrl), const SecureRefreshStore());
  ref.onDispose(session.dispose);
  return session;
});
final locationProvider = Provider<LocationSource>((ref) => DeviceLocation());

final mapAvailabilityProvider = FutureProvider<bool>((ref) async {
  if (!mapsEnabled) return false;
  try {
    return await const MethodChannel('chii/config')
            .invokeMethod<bool>('mapsReady') ??
        false;
  } catch (_) {
    return false;
  }
});

typedef AuthView = ({
  bool authenticated,
  bool busy,
  int generation,
  String? userId,
});
final authViewProvider = NotifierProvider<AuthController, AuthView>(
  AuthController.new,
);

class AuthController extends Notifier<AuthView> {
  @override
  AuthView build() {
    final session = ref.watch(sessionProvider);
    AuthView snapshot() => (
      authenticated: session.authenticated,
      busy: session.busy,
      generation: session.generation,
      userId: session.user?['id'] as String?,
    );
    void changed() {
      state = snapshot();
    }

    session.addListener(changed);
    ref.onDispose(() => session.removeListener(changed));
    return snapshot();
  }
}

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  if (kReleaseMode && Uri.parse(apiUrl).scheme != 'https') {
    runApp(
      const MaterialApp(
        home: Scaffold(body: Center(child: Text('HTTPS API 설정이 필요합니다.'))),
      ),
    );
    return;
  }
  runApp(const ProviderScope(child: ChiiApp()));
}

class ChiiApp extends ConsumerStatefulWidget {
  const ChiiApp({super.key});
  @override
  ConsumerState<ChiiApp> createState() => _ChiiAppState();
}

class _ChiiAppState extends ConsumerState<ChiiApp> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(sessionProvider).restore());
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    final auth = ref.watch(authViewProvider);
    return MaterialApp(
      title: 'CHII WORLD',
      theme: ThemeData(
        colorSchemeSeed: const Color(0xff638c76),
        useMaterial3: true,
      ),
      home: auth.authenticated
          ? Home(
              key: ValueKey('${session.generation}:${session.user!['id']}'),
              session: session,
              mapReady: ref.watch(mapAvailabilityProvider).value ?? false,
              location: ref.read(locationProvider),
            )
          : Login(session: session),
    );
  }
}

class Login extends StatefulWidget {
  const Login({super.key, required this.session});
  final Session session;
  @override
  State<Login> createState() => _LoginState();
}

class _LoginState extends State<Login> {
  final email = TextEditingController(), password = TextEditingController();
  String? error;
  @override
  void dispose() {
    email.dispose();
    password.dispose();
    super.dispose();
  }

  Future<void> submit() async {
    setState(() => error = null);
    try {
      await widget.session.login(email.text.trim(), password.text);
    } catch (e) {
      if (mounted) setState(() => error = safeMessage(e));
    } finally {
      if (mounted) password.clear();
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('CHII WORLD')),
    body: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.all(24),
          children: [
            const Text('주변에서 발견하고, 나만의 컬렉션으로', style: TextStyle(fontSize: 24)),
            const SizedBox(height: 24),
            TextField(
              controller: email,
              keyboardType: TextInputType.emailAddress,
              autocorrect: false,
              decoration: const InputDecoration(labelText: '이메일'),
            ),
            TextField(
              controller: password,
              obscureText: true,
              enableSuggestions: false,
              autocorrect: false,
              decoration: const InputDecoration(labelText: '비밀번호'),
              onSubmitted: (_) {
                if (!widget.session.busy) submit();
              },
            ),
            if (error != null)
              Text(error!, style: const TextStyle(color: Colors.red)),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: widget.session.busy ? null : submit,
              child: Text(widget.session.busy ? '확인 중…' : '로그인'),
            ),
            TextButton(
              onPressed: widget.session.busy
                  ? null
                  : () async {
                      password.clear();
                      final registeredEmail = await Navigator.push<String>(
                        context,
                        MaterialPageRoute(
                          builder: (_) => SignupScreen(api: widget.session.api),
                        ),
                      );
                      if (!mounted) return;
                      if (registeredEmail != null) {
                        setState(() {
                          email.text = registeredEmail;
                          error = null;
                        });
                      }
                    },
              child: const Text('회원가입'),
            ),
            const Text('위치 권한은 주변 탐색을 사용할 때 요청합니다.'),
          ],
        ),
      ),
    ),
  );
}

class Home extends StatefulWidget {
  const Home({
    super.key,
    required this.session,
    required this.location,
    this.mapReady = false,
  });
  final Session session;
  final LocationSource location;
  final bool mapReady;
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> with WidgetsBindingObserver {
  late final nearby = Nearby(widget.session, widget.location);
  late final encounters = Encounters(widget.session, widget.location);
  late final collection = Collection(widget.session);
  int tab = 0;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    nearby.dispose();
    encounters.dispose();
    collection.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      nearby.invalidate();
      if (widget.location is DeviceLocation) {
        (widget.location as DeviceLocation).setForeground(false);
      }
    }
    if (state == AppLifecycleState.resumed) {
      if (widget.location is DeviceLocation) {
        (widget.location as DeviceLocation).setForeground(true);
      }
      nearby.invalidate();
      // Refresh permission/service/fix locally, without requesting permission or calling Nearby.
      widget.location
          .current(requestPermission: false)
          .then(
            (_) {},
            onError: (Object e) {
              if (mounted) setState(() => nearby.error = safeMessage(e));
            },
          );
      encounters.reload();
    }
  }

  Future<void> discover(Map<String, dynamic> spot) async {
    await encounters.create(spot['id']);
    if (mounted) setState(() => tab = 1);
  }

  Future<void> capture() async {
    if (await encounters.catchEncounter()) {
      await collection.load(reset: true);
    }
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: Listenable.merge([nearby, encounters, collection]),
    builder: (context, _) => Scaffold(
      appBar: AppBar(
        title: const Text('CHII WORLD'),
        actions: [
          IconButton(
            tooltip: '로그아웃',
            onPressed: () async {
              final messenger = ScaffoldMessenger.of(context);
              try {
                final revoked = await widget.session.logout();
                if (!revoked) {
                  messenger.showSnackBar(
                    const SnackBar(
                      content: Text('기기에서 로그아웃했습니다. 서버 토큰 폐기는 확인되지 않았습니다.'),
                    ),
                  );
                }
              } catch (_) {
                messenger.showSnackBar(
                  const SnackBar(content: Text('보안 저장소 정리를 확인해 주세요.')),
                );
              }
            },
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: switch (tab) {
        0 => nearbyView(),
        1 => encounterView(),
        _ => collectionView(),
      },
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (value) {
          setState(() => tab = value);
          if (value == 2 && collection.items.isEmpty) {
            collection.load(reset: true);
          }
        },
        destinations: const [
          NavigationDestination(icon: Icon(Icons.explore), label: '주변'),
          NavigationDestination(icon: Icon(Icons.auto_awesome), label: '발견'),
          NavigationDestination(
            icon: Icon(Icons.collections_bookmark),
            label: '컬렉션',
          ),
        ],
      ),
    ),
  );
  Widget nearbyView() => ListView(
    padding: const EdgeInsets.all(16),
    children: [
      const Text('내 주변 1km', style: TextStyle(fontSize: 24)),
      const Text('현재 위치로 장소를 찾습니다. 지도 이동만으로 검색되지는 않습니다.'),
      FilledButton(
        onPressed: nearby.busy ? null : () => nearby.refresh(),
        child: const Text('현재 위치로 새로 찾기'),
      ),
      if (nearby.busy) const LinearProgressIndicator(),
      if (nearby.error != null) ...[
        Text(nearby.error!),
        TextButton(
          onPressed: () => widget.location.openSettings(),
          child: const Text('앱 권한 설정'),
        ),
        if (widget.location is DeviceLocation)
          TextButton(
            onPressed: () =>
                (widget.location as DeviceLocation).openLocationSettings(),
            child: const Text('위치 서비스 설정'),
          ),
      ],
      if (nearby.fix != null) ...[
        Text(
          nearby.fix!.approximate
              ? '대략적 위치입니다. 발견하려면 정밀 위치가 필요할 수 있습니다.'
              : '위치 정확도 약 ${nearby.fix!.accuracy.round()}m',
        ),
        if (widget.mapReady)
          SizedBox(
            height: 260,
            child: GoogleMap(
              key: ValueKey(nearby.fix),
              initialCameraPosition: CameraPosition(
                target: LatLng(nearby.fix!.latitude, nearby.fix!.longitude),
                zoom: 15,
              ),
              myLocationEnabled: false,
              myLocationButtonEnabled: false,
              markers: {
                Marker(
                  markerId: const MarkerId('current'),
                  position: LatLng(nearby.fix!.latitude, nearby.fix!.longitude),
                  infoWindow: const InfoWindow(title: '조회 위치'),
                ),
                ...nearby.spots.map(
                  (s) => Marker(
                    markerId: MarkerId(s['id']),
                    position: LatLng(
                      (s['location']['latitude'] as num).toDouble(),
                      (s['location']['longitude'] as num).toDouble(),
                    ),
                    infoWindow: InfoWindow(title: s['name']),
                    onTap: () => showModalBottomSheet(
                      context: context,
                      builder: (c) => SafeArea(
                        child: ListTile(
                          title: Text(s['name']),
                          subtitle: Text(s['description']),
                          trailing: FilledButton(
                            onPressed: encounters.busy
                                ? null
                                : () {
                                    Navigator.pop(c);
                                    discover(s);
                                  },
                            child: const Text('발견'),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              },
            ),
          )
        else
          const Card(
            child: Padding(
              padding: EdgeInsets.all(20),
              child: Text('지도 키 설정 전입니다. 아래 목록으로 탐색할 수 있습니다.'),
            ),
          ),
        Text('불러온 장소 ${nearby.spots.length}개'),
        if (nearby.spots.isEmpty) const Text('주변에 등록된 장소가 없습니다.'),
      ],
      ...nearby.spots.map(
        (s) => Card(
          child: ListTile(
            title: Text(s['name']),
            subtitle: Text(
              '${(s['distance_m'] as num).round()}m · ${s['description']}',
            ),
            trailing: FilledButton(
              onPressed: encounters.busy ? null : () => discover(s),
              child: const Text('발견'),
            ),
          ),
        ),
      ),
      if (nearby.more)
        TextButton(
          onPressed: nearby.busy ? null : nearby.next,
          child: const Text('장소 더 보기'),
        ),
    ],
  );
  Widget encounterView() => ListView(
    padding: const EdgeInsets.all(24),
    children: [
      const Icon(Icons.auto_awesome, size: 96),
      const Text('새로운 발견', style: TextStyle(fontSize: 24)),
      if (encounters.busy) const LinearProgressIndicator(),
      if (encounters.error != null) Text(encounters.error!),
      if (encounters.encounter == null) const Text('주변 장소에서 발견을 시작해 주세요.'),
      if (encounters.encounter != null) ...[
        Text('상태: ${encounters.encounter!['status']}'),
        Text(
          '유효 시각: ${DateTime.parse(encounters.encounter!['expires_at']).toLocal()} (서버가 최종 판단)',
        ),
        const Text('캐릭터 정보는 포획 후 컬렉션에서 확인할 수 있습니다.'),
        FilledButton(
          onPressed: encounters.busy ? null : capture,
          child: Text(
            encounters.capture == null ? '포획 / 같은 결과 다시 확인' : '포획 결과 확인',
          ),
        ),
        TextButton(
          onPressed: encounters.busy ? null : encounters.reload,
          child: const Text('서버 상태 확인'),
        ),
        if (encounters.capture != null)
          const Text('컬렉션에 저장되었습니다. 중복 요청해도 한 번만 지급됩니다.'),
      ],
    ],
  );
  Widget collectionView() => ListView(
    padding: const EdgeInsets.all(16),
    children: [
      const Text('나의 컬렉션', style: TextStyle(fontSize: 24)),
      TextButton(
        onPressed: collection.busy ? null : () => collection.load(reset: true),
        child: const Text('컬렉션 새로고침'),
      ),
      if (collection.busy) const LinearProgressIndicator(),
      if (collection.error != null) Text(collection.error!),
      if (!collection.busy && collection.items.isEmpty)
        const Text('아직 획득한 캐릭터가 없습니다.'),
      ...collection.items.map(
        (item) => Card(
          child: ListTile(
            leading: const Icon(Icons.pets),
            title: Text(
              '${item['character']['name']} · ${item['character_variant']['name']}',
            ),
            subtitle: Text(
              '${item['character_variant']['rarity']} · ${item['captured_spot']['name']}\n${DateTime.parse(item['captured_at']).toLocal()}',
            ),
          ),
        ),
      ),
      if (collection.more)
        TextButton(
          onPressed: collection.busy ? null : () => collection.load(),
          child: const Text('컬렉션 더 보기'),
        ),
    ],
  );
}
