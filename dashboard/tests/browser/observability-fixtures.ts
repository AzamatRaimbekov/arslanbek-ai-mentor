import type { createFixtures } from './fixtures';
import type { SecurityAlert } from '../../src/data';
import type { StudentObservability } from '../../src/observability';

export function observationFixtures(base: ReturnType<typeof createFixtures>) {
  base.prompts.forEach((p, index) => { p.observability = { version: 1, tags: ['frontend', index % 2 ? 'testing' : 'intent:learn'], tag_source: 'keyword_rules', privacy_signals: [] }; });
  const student = base.students[0];
  const episodes = base.summaries.filter(s => s.student_id === student.id).slice(0, 2);
  const alerts: SecurityAlert[] = [{ id: 2001, student_id: student.id, prompt_id: base.prompts.find(p => p.student_id === student.id)!.id, category: 'api_key', severity: 'critical', occurrences: 1, status: 'open', created_at: new Date().toISOString(), reviewed_at: null, student, prompt: { project: 'shop-app', client: 'codex', model: 'test-model', created_at: new Date().toISOString() } }];
  return {
    alerts,
    snapshot(id: string, days: number): StudentObservability {
      const prompts = base.prompts.filter(p => p.student_id === id);
      const first = id === student.id;
      return {
        days, period_start: new Date(Date.now() - days * 86400000).toISOString(), generated_at: new Date().toISOString(),
        metrics: { prompts: prompts.length, tagged_prompts: prompts.length, summaries: 3, completed_tasks: 1, active_days: 6, projects: 1, open_alerts: first ? alerts.filter(a => a.status === 'open').length : 0 },
        skills: first ? [{ competency_id: 'prompt_engineering', observations: 2, tasks: 2, independent_tasks: 2, latest_state: 'demonstrated', last_observed: episodes[0].created_at, next_action: 'Сформулировать критерии новой задачи самостоятельно' }] : [],
        evidence: first ? episodes.map((s, i) => ({ competency_id: 'prompt_engineering', state: 'demonstrated', actor: 'learner', evidence_type: 'learner_explanation', evidence: i ? 'Объяснил критерии проверки ошибки' : 'Самостоятельно сформулировал цель корзины', next_action: 'Проверить на следующей задаче', summary_id: s.id, created_at: s.created_at, task: i ? 'Проверка ошибок корзины' : 'Добавление корзины', goal: i ? 'Проверить ошибку' : 'Добавить товар', project: 'shop-app', confidence: 'high', source: 'structured_report' })) : [],
        tags: [{ tag: 'frontend', count: prompts.length }, { tag: 'testing', count: prompts.filter(p => p.observability?.tags.includes('testing')).length }],
        directions: [{ direction: 'Frontend', count: 3 }], clients: [{ client: 'codex', count: prompts.length }],
        tools: [{ kind: 'mcp', tool_id: 'docs-search', action: 'used', actor: 'agent', source: 'tool_hook', count: 2, last_used: new Date().toISOString() }],
        tool_events: [{ id: 10, kind: 'mcp', tool_id: 'docs-search', action: 'used', actor: 'agent', source: 'tool_hook', project: 'shop-app', created_at: new Date().toISOString() }],
        environment: { version: 1, client: 'codex', tools: [{ kind: 'skill', tool_id: 'example-skill', scope: 'project' }], harness: ['project_instructions', 'test_configuration', 'app_hooks'], truncated: false, coverage: 'selected_app_and_project' },
        environment_updated_at: new Date().toISOString(), activity: [],
      };
    },
  };
}
