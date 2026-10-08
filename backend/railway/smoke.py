"""Read-only production checks; --delivery additionally sends and removes synthetic data.

Reads local deployment credentials without printing them. Database cleanup uses the
private Railway network through SSH. Never enables collection for a real participant.
"""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
MARKER = 'arslanbek-deployment-smoke'


def main(delivery=False):
    state = json.loads((ROOT / 'backend/.env.railway.json').read_text())
    project = json.loads((ROOT / 'backend/railway/project.json').read_text())
    def request(path, body=None, token=None):
        headers = {'apikey': state['ANON_KEY'], 'Content-Type': 'application/json',
                   'Authorization': 'Bearer ' + (token or state['ANON_KEY'])}
        req = urllib.request.Request(state['API_URL'] + path, headers=headers,
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.load(error)
            except (ValueError, OSError):
                return error.code, None

    status, health = request('/healthz')
    assert status == 200 and health['status'] == 'ok' and not health['analysis_configured'], 'Backend is not healthy in summaries mode'
    status, login = request('/auth/v1/token?grant_type=password', {'email': state['ADMIN_EMAIL'], 'password': state['ADMIN_PASSWORD']})
    assert status == 200 and login.get('access_token'), f'Administrator login failed: HTTP {status}'
    token = login['access_token']
    status, role = request('/rest/v1/rpc/is_admin', {}, token)
    assert status == 200 and role is True, f'Administrator role failed: HTTP {status}'
    assert request('/rest/v1/students?select=id')[0] in (401, 403), 'Anonymous access must be denied'
    assert request('/functions/v1/analyze-team', {'days': 30}, token)[0] == 404, 'Server AI must be disabled'
    print('PASS: healthy backend, administrator login, anonymous access denied, server AI disabled.', flush=True)
    # The database rejects a null device before any INSERT: verify the public
    # collection key and RPC route without registering a synthetic participant.
    status, probe = request('/rest/v1/rpc/ingest', {'p_device': None, 'p_secret': '', 'p_identity': {}, 'p_prompts': [], 'p_summary': None})
    assert status in (400, 401, 403) and isinstance(probe, dict) and probe.get('code') == '28000', f'Collection route validation failed: HTTP {status}'
    print('PASS: public collection key reaches ingest; invalid probe rejected before data creation.', flush=True)
    status, summaries = request('/rest/v1/summaries?select=*,student:students(display_name,claude_name,git_name,os_user)&limit=1', token=token)
    assert status == 200 and isinstance(summaries, list), 'Summary feed query failed'
    status, stats = request('/rest/v1/rpc/dashboard_stats', {'p_days': 30}, token)
    assert status == 200, 'Dashboard statistics unavailable'
    print(f"PASS: summary feed and dashboard statistics; participants={stats['students']}, summaries={stats['summaries']}.")
    for table, columns in (('students', 'id,progress_report,last_client'), ('summaries', 'id,progress_report,client,model'), ('prompts', 'id,client,model')):
        status, rows = request(f'/rest/v1/{table}?select={columns}&limit=1', token=token)
        assert status == 200 and isinstance(rows, list), f'Multiclient schema unavailable: {table}'
    print('PASS: structured progress and application/model fields available to the administrator.', flush=True)
    for table in ('security_alerts', 'tool_events'):
        status, rows = request(f'/rest/v1/{table}?select=id&limit=1', token=token)
        assert status == 200 and isinstance(rows, list), f'Observation schema unavailable: {table}'
        assert request(f'/rest/v1/{table}?select=id&limit=1')[0] in (401, 403), 'Anonymous observation access must be denied'
    status, alerts = request('/rest/v1/rpc/security_alert_counts', {}, token)
    assert status == 200 and isinstance(alerts.get('open'), int), 'Alert counts unavailable'
    status, people = request('/rest/v1/students?select=id&limit=1', token=token)
    if people:
        status, snapshot = request('/rest/v1/rpc/student_observability', {'p_student': people[0]['id'], 'p_days': 30}, token)
        assert status == 200 and all(k in snapshot for k in ('metrics', 'skills', 'evidence', 'tags', 'tools')), 'Student development unavailable'
    print('PASS: observation schema, alert counts, student development and anonymous isolation; no data changed.', flush=True)
    if not delivery:
        return

    def database(device='check'):
        result = subprocess.run(['railway', 'ssh', '--project', project['projectId'], '--environment', project['environmentId'],
                                 '--service', project['services']['backend'], '--', 'node', 'railway/smoke-db.mjs', device],
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, 'Test cleanup database operation failed through Railway SSH'
    database()

    spec = importlib.util.spec_from_file_location('telemetry', ROOT / 'skills/arslanbek-ai-mentor/scripts/telemetry.py')
    telemetry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(telemetry)
    with tempfile.TemporaryDirectory(prefix='arslanbek-smoke-') as folder:
        base = Path(folder)
        for key, filename in {'STATE': '.', 'QUEUE': 'queue', 'SESSIONS': 'sessions', 'LOCK': 'flush.lock',
                              'CONSENT': 'consent.json', 'DELIVERY': 'delivery.json', 'REVOKE': 'revoke-pending.json'}.items():
            setattr(telemetry, key, base / filename)
        telemetry.config = lambda: (state['API_URL'], state['ANON_KEY'], False)
        telemetry.spawn_flush = lambda: None
        telemetry.profile_md = lambda: ''
        telemetry.identity = lambda: {'git_name': 'Проверка подключения (автотест)', 'hostname': MARKER, 'analysis_allowed': False,
                                      'consent_version': 3, 'skill_version': telemetry.SKILL_VERSION}
        telemetry.private_write(telemetry.CONSENT, {'answer': 'yes', 'version': 3, 'analysis_allowed': False})
        device = telemetry.device()['device_id']
        try:
            summary = 'Техническая проверка доставки сводки. Это синтетическая запись, не оценка участника.'
            with contextlib.redirect_stdout(io.StringIO()):
                telemetry.cmd_summary(argparse.Namespace(level=None, session='deployment-smoke', stage='Проверка доставки', summary=summary,
                                                        strengths='', struggles='', next='Удалить тестовую запись после проверки.'))
            assert telemetry.flush() == 1, 'Skill summary was not acknowledged by production'
            assert not list(telemetry.QUEUE.glob('*.json')), 'Skill queue was not cleared after acknowledgement'
            status, students = request(f'/rest/v1/students?select=id&device_id=eq.{device}', token=token)
            assert status == 200 and len(students) == 1, 'Test device missing in admin data'
            student_id = students[0]['id']
            status, summaries = request(f'/rest/v1/summaries?select=*,student:students(display_name,git_name)&student_id=eq.{student_id}', token=token)
            assert status == 200 and len(summaries) == 1 and summaries[0]['summary'] == summary, 'Summary feed cannot read the delivered text'
            assert summaries[0]['student']['git_name'] == 'Проверка подключения (автотест)', 'Participant join failed'
            assert summaries[0]['level'] is None, 'Unknown level became a numeric score'
            print('PASS: real skill queue → server → saved summary → administrator feed.', flush=True)
        finally:
            database(device)
            print('Synthetic test device and its summary removed.', flush=True)
    status, stats = request('/rest/v1/rpc/dashboard_stats', {'p_days': 30}, token)
    assert status == 200, 'Dashboard statistics unavailable'
    print(f"PASS: dashboard statistics; participants={stats['students']}, summaries={stats['summaries']}.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery', action='store_true', help='Requires registered Railway SSH access; creates and removes a synthetic device')
    args = parser.parse_args()
    try:
        main(args.delivery)
    except Exception as error:
        print(f'FAIL: {error}' if isinstance(error, AssertionError) else f'FAIL: {type(error).__name__}; private details suppressed.')
        raise SystemExit(1)
