"""Local observations, using synthetic projects only."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'skills/arslanbek-ai-mentor/scripts/observability.py'
spec = importlib.util.spec_from_file_location('observation_test', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ObservationTest(unittest.TestCase):
    def test_tags_describe_topic_and_intent_without_inventing_proficiency(self):
        tags = module.tags('Объясни, почему FastAPI сервер не работает; давай проверим SQL и pytest')
        self.assertTrue({'backend', 'databases', 'testing', 'intent:debug', 'intent:learn'} <= set(tags))
        self.assertEqual(module.tags('Привет, спасибо'), [])

    def test_signals_only_contain_categories_counts_and_severity(self):
        key = 'sk-' + 'b' * 32
        signals = module.privacy_signals(f'пароль=private-password {key}. Конфиденциально: customer@example.test')
        for raw in ('private-password', key, 'customer@example.test'):
            self.assertNotIn(raw, json.dumps(signals))
        self.assertTrue({'api_key', 'credential', 'confidential_marker'} <= {s['category'] for s in signals})
        self.assertFalse(any(s['category'] == 'credential' for s in module.privacy_signals('password=YOUR_PASSWORD password=${LOCAL_SECRET}')))

    def test_inventory_names_without_config_values_or_other_app_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / 'user'; project = Path(folder) / 'project'
            (home / '.claude/skills/example-skill').mkdir(parents=True)
            (home / '.claude/skills/example-skill/SKILL.md').write_text('PRIVATE FILE CONTENT')
            (home / '.claude/settings.json').write_text(json.dumps({'enabledPlugins': {'example-plugin@school': True}, 'hooks': {'Stop': []}, 'env': {'SECRET': 'never-transmit'}}))
            (home / '.claude.json').write_text(json.dumps({'mcpServers': {'docs': {'command': 'private-command', 'env': {'TOKEN': 'never-transmit'}}}}))
            (project / '.git').mkdir(parents=True)
            (project / 'CLAUDE.md').write_text('PRIVATE INSTRUCTIONS')
            (project / 'package.json').write_text(json.dumps({'scripts': {'test': 'private-test-command'}}))
            value = module.environment(project, 'claude-code', home=home)
            self.assertTrue({'example-skill', 'example-plugin@school', 'docs'} <= {t['tool_id'] for t in value['tools']})
            self.assertTrue({'project_instructions', 'version_control', 'test_configuration'} <= set(value['harness']))
            for raw in ('PRIVATE', 'never-transmit', 'private-command', 'private-test-command', str(home)):
                self.assertNotIn(raw, json.dumps(value))
            self.assertEqual(module.environment(project, 'claude-desktop', home=home)['tools'], [])

    def test_tool_metadata_discards_arguments_and_results_and_skips_self_hooks(self):
        value = module.tool_event({'tool_name': 'Skill', 'tool_input': {'skill': 'test-skill', 'password': 'sensitive-password'}, 'tool_response': {'output': 'sk-' + 'a' * 32}})
        self.assertEqual(value['tool_id'], 'test-skill')
        self.assertNotIn('sensitive-password', json.dumps(value))
        self.assertNotIn('tool_input', value); self.assertNotIn('tool_response', value)
        self.assertTrue(value['privacy_signals'])
        self.assertIsNone(module.tool_event({'tool_name': 'mcp__arslanbek__arslanbek_capture_tool'}))


if __name__ == '__main__':
    unittest.main()
