"""Install bundled skills offline and optional skills for the selected native client."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import skill_dependencies as dependencies

SKILL = Path(__file__).resolve().parents[1]
STACK = {
    'agent-browser':'vercel-labs/agent-browser',
    'stitch-generate-design':'google-labs-code/stitch-skills',
    'taste-design':'google-labs-code/stitch-skills',
    'stitch-manage-design-system':'google-labs-code/stitch-skills',
    'stitch-react-native':'google-labs-code/stitch-skills',
    'ui-ux-pro-max':'nextlevelbuilder/ui-ux-pro-max-skill',
    'shadcn-ui':'google-labs-code/stitch-skills',
    'deploy-to-vercel':'vercel-labs/agent-skills',
    'accessibility':'addyosmani/web-quality-skills',
    'indexion-readme':'trkbt10/indexion-skills',
    'om-root-cause':'open-mercato/skills',
    'harness-creator':'walkinglabs/learn-harness-engineering',
    'eval-harness':'affaan-m/ecc',
    'test-harness':'zernie/vigiles',
    'multi-stage-dockerfile':'github/awesome-copilot',
    'docker-patterns':'affaan-m/ecc',
    'docker-compose-orchestration':'manutej/luxor-claude-marketplace',
    'vercel-react-native-skills':'vercel-labs/agent-skills',
    'react-native-best-practices':'callstackincubator/agent-skills',
    'eas-app-stores':'expo/skills',
}
MARKETS = {'claude-plugins-official':'anthropics/claude-plugins-official',
           'thedotmack':'thedotmack/claude-mem','ecc':'affaan-m/ecc','ralph-marketplace':'snarktank/ralph'}
PLUGINS = ['superpowers@claude-plugins-official','claude-mem@thedotmack','frontend-design@claude-plugins-official',
           'vercel@claude-plugins-official','ecc@ecc','ralph-skills@ralph-marketplace','claude-code-setup@claude-plugins-official']


def run(command, environment=None):
    try:
        return subprocess.run(command,env=environment,capture_output=True,timeout=180).returncode == 0
    except (OSError,subprocess.TimeoutExpired):
        return False


def add_skill(source, name, client, target, dry_run=False):
    if client not in dependencies.NATIVE:
        return {'name':name,'status':'unsupported','reason':'MCP hosts read bundled skills; external installation is native only'}
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',source) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',name):
        raise ValueError('Use a repository owner/name and a plain skill name')
    if dependencies.usable(target / name,name):
        return {'name':name,'status':'existing'}
    if (target / name).exists() or (target / name).is_symlink():
        return {'name':name,'status':'blocked','reason':'Existing directory or symbolic link preserved'}
    if dry_run:
        return {'name':name,'status':'planned','client':client}
    if target.resolve() != dependencies.destination(client).resolve():
        return {'name':name,'status':'blocked','reason':'For custom skill directories use skill-installer with the explicit destination'}
    command = shutil.which('npx') or shutil.which('npx.cmd')
    if not command:
        return {'name':name,'status':'blocked','reason':'Extra online skills require Node/npm; the bundled core works without them'}
    ok = run([command,'-y','skills','add',source,'--skill',name,'--global','--yes','--copy','--agent',client])
    return {'name':name,'status':'installed' if ok and dependencies.usable(target / name,name) else 'failed'}


def add_plugins(client, home, dry_run=False):
    if client != 'claude-code':
        return [{'name':'claude-plugins','status':'unsupported','reason':'Claude plugins belong to Claude Code; this client uses bundled skills'}]
    command = shutil.which('claude') or shutil.which('claude.exe') or shutil.which('claude.cmd')
    if not command and not dry_run:
        return [{'name':'claude-plugins','status':'blocked','reason':'Claude Code CLI unavailable'}]
    registry_path = home / 'plugins/installed_plugins.json'
    registry = registry_path.read_text(encoding='utf-8') if registry_path.exists() else ''
    ruflo = bool(shutil.which('ruflo') or (Path.cwd() / '.claude-flow').exists() or (Path.cwd() / '.ruflo').exists())
    environment = {**os.environ,'CLAUDE_CONFIG_DIR':str(home)}
    results = []
    if not dry_run:
        for market, source in MARKETS.items():
            if ruflo and market in ('thedotmack','ecc'):
                continue
            known = home / 'plugins/known_marketplaces.json'
            if not known.exists() or market not in known.read_text(encoding='utf-8'):
                run([command,'plugin','marketplace','add',source],environment)
    for plugin in PLUGINS:
        if ruflo and plugin.split('@')[0] in ('claude-mem','ecc'):
            results.append({'name':plugin,'status':'skipped','reason':'Existing Ruflo manages these hooks'})
        elif plugin in registry:
            results.append({'name':plugin,'status':'existing'})
        elif dry_run:
            results.append({'name':plugin,'status':'planned'})
        else:
            ok = run([command,'plugin','install',plugin],environment)
            current = registry_path.read_text(encoding='utf-8') if registry_path.exists() else ''
            results.append({'name':plugin,'status':'installed' if ok and plugin in current else 'failed'})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client',choices=dependencies.CLIENTS)
    parser.add_argument('--skills-home',type=Path)
    parser.add_argument('--claude-home',type=Path,default=Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude'))
    parser.add_argument('--with-stack',action='store_true')
    parser.add_argument('--with-plugins',action='store_true')
    parser.add_argument('--add',help='Repository owner/name for one task skill')
    parser.add_argument('--skill',help='Exact task skill name')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--quiet',action='store_true')
    parser.add_argument('--once',action='store_true',help='Compatibility flag: bundled setup is always idempotent')
    args = parser.parse_args()
    if bool(args.add) != bool(args.skill):
        parser.error('--add and --skill must be provided together')
    pointer = SKILL / '.arslanbek-client.json'
    saved = json.loads(pointer.read_text()).get('client') if pointer.exists() else None
    client = args.client or os.environ.get('ARSLANBEK_CLIENT') or saved or 'claude-code'
    try:
        result = dependencies.ensure(SKILL,client,native_home=args.claude_home if client == 'claude-code' else None,
                                     skills_home=args.skills_home,dry_run=args.dry_run)
        extras = []
        target = dependencies.destination(client,args.claude_home if client == 'claude-code' else None,args.skills_home)
        for name, source in (STACK.items() if args.with_stack else []):
            extras.append(add_skill(source,name,client,target,args.dry_run))
        if args.add:
            extras.append(add_skill(args.add,args.skill,client,target,args.dry_run))
        if args.with_plugins:
            extras += add_plugins(client,args.claude_home,args.dry_run)
        result['extras'] = extras
        result['ready'] = result['ready'] and all(item['status'] in ('installed','existing','skipped') for item in extras)
        result['status'] = 'ready' if result['ready'] else 'planned' if args.dry_run else 'not_ready'
    except (OSError,ValueError,TypeError) as error:
        result = {'client':client,'ready':False,'status':'not_ready','error':str(error) if isinstance(error,ValueError) else type(error).__name__}
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=None if args.quiet else 2))
    return 0 if result['ready'] or args.dry_run and result.get('status') == 'planned' else 1


if __name__ == '__main__':
    raise SystemExit(main())
