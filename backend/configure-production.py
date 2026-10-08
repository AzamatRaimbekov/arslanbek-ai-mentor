#!/usr/bin/env python3
"""Validate deployment settings and copy ONLY public connection values to clients."""
import argparse
import base64
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


def read_env(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def validate(values):
    errors = []
    for field in ['SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_PROJECT_REF', 'ADMIN_EMAIL']:
        if not values.get(field):
            errors.append(f'Missing {field}')
    url = urlparse(values.get('SUPABASE_URL', ''))
    if url.scheme != 'https' or not url.hostname or url.path not in ('', '/') or url.query or url.fragment or url.username:
        errors.append('SUPABASE_URL must be an HTTPS project origin')
    ref = values.get('SUPABASE_PROJECT_REF', '')
    if not re.fullmatch(r'[a-z0-9]{20}', ref):
        errors.append('SUPABASE_PROJECT_REF must be the 20-character project reference')
    if url.hostname and url.hostname.endswith('.supabase.co') and url.hostname != f'{ref}.supabase.co':
        errors.append('Project reference and URL refer to different projects')
    key = values.get('SUPABASE_ANON_KEY', '')
    if key.startswith('eyJ'):
        try:
            payload = json.loads(base64.urlsafe_b64decode(key.split('.')[1] + '==='))
            if payload.get('role') != 'anon':
                errors.append('Client JWT must have the anon role, never service_role')
            if payload.get('ref') and payload['ref'] != ref:
                errors.append('Public key belongs to a different project')
        except (ValueError, IndexError):
            errors.append('Invalid public JWT key')
    elif not re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]+', key):
        errors.append('Expected a public anon JWT or sb_publishable key')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', values.get('ADMIN_EMAIL', '')):
        errors.append('ADMIN_EMAIL must be an email address')
    return errors


def write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as out:
        os.chmod(path, 0o600)
        out.write(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=ROOT / 'backend/.env.local')
    parser.add_argument('--write', action='store_true', help='Write public dashboard and skill configuration after validation')
    args = parser.parse_args()
    if not args.env_file.is_file():
        parser.exit(1, 'Create backend/.env.local from backend/.env.example. Values are never printed.\n')
    values = read_env(args.env_file)
    errors = validate(values)
    if errors:
        parser.exit(1, '\n'.join(errors) + '\n')
    print('Public project settings: valid. No network requests made.')
    print('AI server configuration:', 'present' if values.get('OPENAI_API_KEY') and values.get('AI_MODEL') else 'missing OPENAI_API_KEY / AI_MODEL')
    if args.write:
        url = values['SUPABASE_URL'].rstrip('/')
        key = values['SUPABASE_ANON_KEY']
        write_private(ROOT / 'dashboard/.env.local', f'VITE_SUPABASE_URL={url}\nVITE_SUPABASE_ANON_KEY={key}\n')
        # These values are public and must travel with the school skill release.
        (ROOT / 'skills/arslanbek-ai-mentor/telemetry.conf').write_text(
            '# Public school endpoint. Never place secret/service_role keys here.\n'
            f'SUPABASE_URL={url}\nSUPABASE_ANON_KEY={key}\n')
        print('Updated dashboard/.env.local and skill telemetry.conf with public values only.')
        print('Migrations, administrator enrollment, server secrets and deployment still need verification.')


if __name__ == '__main__':
    main()
