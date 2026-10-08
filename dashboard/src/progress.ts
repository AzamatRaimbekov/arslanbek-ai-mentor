export const STAGES = [
  ['discovery', 'Понять задачу'], ['planning', 'Составить план'], ['building', 'Создать'],
  ['checking', 'Проверить'], ['delivery', 'Передать результат'],
] as const;
import type { LearningEvidence, Tool } from './observability';
export interface ProgressReport {
  version: 1; task: string; goal: string; stage: typeof STAGES[number][0];
  status: 'in_progress' | 'blocked' | 'completed'; directions: string[];
  learner_actions: string[]; agent_actions: string[]; result: string;
  skills: { name: string; status: 'strength' | 'developing' | 'needs_support' | 'unknown'; evidence: string; next_action: string }[];
  checks: { name: string; status: 'passed' | 'failed' | 'not_run'; evidence: string }[];
  blockers: string[]; next_steps: { action: string; done_when: string; owner: 'learner' | 'mentor' }[];
  confidence: 'low' | 'medium' | 'high'; limitations: string[];
  learning_evidence?: LearningEvidence[]; tool_usage?: Tool[];
}
export function isProgressReport(value: unknown): value is ProgressReport {
  if (!value || typeof value !== 'object') return false;
  const r = value as Record<string, unknown>;
  const strings = (v: unknown) => Array.isArray(v) && v.every(x => typeof x === 'string');
  const records = (v: unknown, keys: string[]) => Array.isArray(v) && v.every(x => x && keys.every(k => typeof x[k] === 'string'));
  return r.version === 1 && ['task', 'goal', 'result'].every(k => typeof r[k] === 'string')
    && STAGES.some(([key]) => key === r.stage) && ['in_progress', 'blocked', 'completed'].includes(String(r.status))
    && ['low', 'medium', 'high'].includes(String(r.confidence))
    && ['directions', 'learner_actions', 'agent_actions', 'blockers', 'limitations'].every(k => strings(r[k]))
    && records(r.skills, ['name', 'status', 'evidence', 'next_action']) && records(r.checks, ['name', 'status', 'evidence'])
    && records(r.next_steps, ['action', 'done_when', 'owner']) && (r.next_steps as unknown[]).length > 0;
}
export const clientName = (value?: string | null) => ({ 'claude-code': 'Claude Code', 'claude-desktop': 'Claude Desktop', codex: 'Codex', mcp: 'MCP-приложение' }[value || ''] || value || 'Приложение не передано');
