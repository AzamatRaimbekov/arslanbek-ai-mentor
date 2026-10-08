"""Configure the explicitly selected Railway project without printing secrets.

Run from the repository: python3 backend/railway/configure.py
Requires an authenticated Railway CLI and existing services/public domains.
Secrets remain in backend/.env.railway.json (0600, ignored by Git and uploads).
"""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
PROJECT = json.loads((Path(__file__).with_name('project.json')).read_text())
STATE = ROOT / 'backend/.env.railway.json'


def private_file(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(content)
    path.chmod(0o600)


def railway(args, data=None):
    result = subprocess.run(['railway', *args], cwd=ROOT, input=None if data is None else json.dumps(data),
                            text=True, capture_output=True, timeout=120)
    if result.returncode:
        # CLI errors may contain submitted variables; never print their raw contents.
        raise RuntimeError(f'Railway command failed: {args[0]} (exit {result.returncode})')
    return json.loads(result.stdout)


def dotenv(path):
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def signed_key(secret, role):
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
    now = int(time.time())
    header = encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = encode(json.dumps({'role': role, 'iss': 'supabase', 'iat': now, 'exp': now + 10 * 365 * 86400}, separators=(',', ':')).encode())
    body = f'{header}.{payload}'
    return f'{body}.{encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())}'


def set_variables(service, variables):
    data = {'input': {'projectId': PROJECT['projectId'], 'environmentId': PROJECT['environmentId'],
                     'serviceId': PROJECT['services'][service], 'variables': variables, 'skipDeploys': True}}
    result = railway(['api', 'mutation SetVariables($input:VariableCollectionUpsertInput!){variableCollectionUpsert(input:$input)}', '--variables', '@-'], data)
    if result.get('errors') or result.get('data', result).get('variableCollectionUpsert') is not True:
        raise RuntimeError(f'Could not configure {service}')
    print(f'Configured {service}: {len(variables)} variables (values hidden).', flush=True)


def domains(service):
    result = railway(['domain', 'list', '--service', PROJECT['services'][service], '--project', PROJECT['projectId'], '--environment', PROJECT['environmentId'], '--json'])
    def collect(value):
        if isinstance(value, dict):
            if isinstance(value.get('domain'), str) and value['domain'].endswith('.up.railway.app'):
                yield value['domain'].removeprefix('https://')
            for nested in value.values():
                yield from collect(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from collect(nested)
    matches = list(dict.fromkeys(collect(result)))
    if len(matches) != 1:
        raise RuntimeError(f'Expected one public domain for {service}')
    return 'https://' + matches[0]


def set_healthcheck(service, path):
    variables = {'serviceId': PROJECT['services'][service], 'environmentId': PROJECT['environmentId'],
                 'input': {'healthcheckPath': path, 'healthcheckTimeout': 300, 'restartPolicyType': 'ON_FAILURE', 'restartPolicyMaxRetries': 10}}
    result = railway(['api', 'mutation Health($serviceId:String!,$environmentId:String!,$input:ServiceInstanceUpdateInput!){serviceInstanceUpdate(serviceId:$serviceId,environmentId:$environmentId,input:$input)}', '--variables', '@-'], variables)
    if result.get('errors') or result.get('data', result).get('serviceInstanceUpdate') is not True:
        raise RuntimeError(f'Could not configure healthcheck for {service}')
    print(f'Healthcheck configured: {service} {path}', flush=True)


def main():
    local = dotenv(ROOT / 'backend/.env.local')
    if STATE.exists():
        state = json.loads(STATE.read_text())
    else:
        state = {'JWT_SECRET': secrets.token_hex(32), 'AUTH_DB_PASSWORD': secrets.token_hex(32),
                 'REST_DB_PASSWORD': secrets.token_hex(32), 'ADMIN_PASSWORD': secrets.token_urlsafe(30),
                 'ADMIN_EMAIL': local.get('ADMIN_EMAIL') or 'a.raimbekov@mdigital.kg', 'projectId': PROJECT['projectId']}
        state['ANON_KEY'] = signed_key(state['JWT_SECRET'], 'anon')
        state['SERVICE_ROLE_KEY'] = signed_key(state['JWT_SECRET'], 'service_role')
        private_file(STATE, json.dumps(state, indent=2) + '\n')
    if state['projectId'] != PROJECT['projectId']:
        raise RuntimeError('Secret state belongs to another project')
    api, frontend = domains('backend'), domains('frontend')
    state.update(API_URL=api, FRONTEND_URL=frontend)
    private_file(STATE, json.dumps(state, indent=2) + '\n')
    common = {'PORT': '8080'}
    backend = {**common, 'DATABASE_URL': '${{Postgres.DATABASE_URL}}',
               'AUTH_URL': 'http://${{auth.RAILWAY_PRIVATE_DOMAIN}}:9999',
               'REST_URL': 'http://${{rest.RAILWAY_PRIVATE_DOMAIN}}:3000',
               'REST_HEALTH_URL': 'http://${{rest.RAILWAY_PRIVATE_DOMAIN}}:3001',
               'AUTH_DB_PASSWORD': state['AUTH_DB_PASSWORD'], 'REST_DB_PASSWORD': state['REST_DB_PASSWORD'],
               'SUPABASE_ANON_KEY': state['ANON_KEY'], 'SUPABASE_SERVICE_ROLE_KEY': state['SERVICE_ROLE_KEY'],
               'ALLOWED_ORIGINS': frontend, 'BOOTSTRAP_ADMIN_EMAIL': state['ADMIN_EMAIL'],
               'BOOTSTRAP_ADMIN_PASSWORD': state['ADMIN_PASSWORD'], 'AI_ANALYSIS_ENABLED': 'false'}
    database = '@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}'
    auth = {'PORT': '9999', 'GOTRUE_API_PORT': '9999', 'GOTRUE_API_HOST': '::',
            'API_EXTERNAL_URL': api + '/auth/v1', 'GOTRUE_SITE_URL': frontend,
            'GOTRUE_URI_ALLOW_LIST': frontend, 'GOTRUE_DB_DRIVER': 'postgres',
            'GOTRUE_DB_DATABASE_URL': 'postgresql://supabase_auth_admin:' + state['AUTH_DB_PASSWORD'] + database,
            'GOTRUE_JWT_SECRET': state['JWT_SECRET'], 'GOTRUE_JWT_ADMIN_ROLES': 'service_role',
            'GOTRUE_JWT_AUD': 'authenticated', 'GOTRUE_JWT_DEFAULT_GROUP_NAME': 'authenticated',
            'GOTRUE_JWT_EXP': '3600', 'GOTRUE_DISABLE_SIGNUP': 'true', 'GOTRUE_EXTERNAL_EMAIL_ENABLED': 'true',
            'GOTRUE_EXTERNAL_PHONE_ENABLED': 'false', 'GOTRUE_EXTERNAL_ANONYMOUS_USERS_ENABLED': 'false',
            'GOTRUE_MAILER_AUTOCONFIRM': 'false', 'GOTRUE_PASSWORD_MIN_LENGTH': '12',
            'GOTRUE_SECURITY_REFRESH_TOKEN_ROTATION_ENABLED': 'true', 'GOTRUE_SECURITY_REFRESH_TOKEN_REUSE_INTERVAL': '10',
            'GOTRUE_DB_MAX_POOL_SIZE': '5'}
    rest = {'PORT': '3001', 'PGRST_SERVER_PORT': '3000', 'PGRST_SERVER_HOST': '*6',
            'PGRST_ADMIN_SERVER_PORT': '3001', 'PGRST_ADMIN_SERVER_HOST': '*6', 'PGRST_DB_URI': 'postgresql://authenticator:' + state['REST_DB_PASSWORD'] + database,
            'PGRST_DB_SCHEMAS': 'public', 'PGRST_DB_ANON_ROLE': 'anon', 'PGRST_DB_POOL': '5',
            'PGRST_JWT_SECRET': state['JWT_SECRET'], 'PGRST_DB_MAX_ROWS': '1000', 'PGRST_OPENAPI_MODE': 'disabled'}
    for service, variables in [('backend', backend), ('auth', auth), ('rest', rest),
                               ('frontend', {**common, 'VITE_SUPABASE_URL': api, 'VITE_SUPABASE_ANON_KEY': state['ANON_KEY']})]:
        set_variables(service, variables)
    for service, path in [('backend', '/healthz'), ('frontend', '/healthz'), ('auth', '/health'), ('rest', '/ready')]:
        set_healthcheck(service, path)
    private_file(ROOT / 'dashboard/.env.local', f'VITE_SUPABASE_URL={api}\nVITE_SUPABASE_ANON_KEY={state["ANON_KEY"]}\n')
    (ROOT / 'skills/arslanbek-ai-mentor/telemetry.conf').write_text(
        '# Public production endpoint. No service-role or private keys belong here.\n'
        f'SUPABASE_URL={api}\nSUPABASE_ANON_KEY={state["ANON_KEY"]}\n')
    private_file(ROOT / 'backend/.env.railway-login.txt', f'Кабинет: {frontend}\nEmail: {state["ADMIN_EMAIL"]}\nПароль: {state["ADMIN_PASSWORD"]}\n')
    print(f'Frontend: {frontend}\nBackend: {api}\nCredentials: backend/.env.railway-login.txt')
    print('Mode: skill summaries. Server AI analysis is disabled; no provider key is uploaded.')


if __name__ == '__main__':
    main()
