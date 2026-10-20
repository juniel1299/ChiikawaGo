"""Run Dart application flows against an isolated real Django/PostGIS stack."""
import os
import pathlib
import secrets
import shutil
import subprocess
import time
import urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
env = os.environ.copy()
env['CHII_TEST_PASSWORD'] = secrets.token_urlsafe(32)
env['CHII_BACKEND_INTEGRATION'] = '1'
flutter = env.get('FLUTTER_BIN') or shutil.which('flutter')
if not flutter:
    raise SystemExit('Set FLUTTER_BIN or add the pinned Flutter SDK to PATH')
compose = ['docker', 'compose', '-f', str(root / 'tool/compose.integration.yaml')]
def run(args):
    subprocess.run(args, cwd=root, env=env, check=True)
try:
    run(compose + ['up', '-d', '--wait'])
    run(compose + ['exec', '-T', 'api', 'python', 'manage.py', 'migrate', '--noinput'])
    run(compose + ['exec', '-T', 'api', 'python', '/mobile-tool/seed_integration.py'])
    for _ in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:18081/ready', timeout=2) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(1)
    else:
        raise RuntimeError('Isolated API readiness timed out')
    run([flutter, 'test', 'test/backend_flow_test.dart'])
finally:
    # Only the dedicated test project and its anonymous database volume are removed.
    subprocess.run(compose + ['down', '-v'], cwd=root, env=env, check=False)
