import { createClient } from '@supabase/supabase-js';
import type { ProgressReport } from './progress';
import type { Observation, StudentObservability } from './observability';

export const LEVELS = ['Знакомство', 'Заказчик', 'Постановщик', 'Контролёр', 'Архитектор', 'Автор'];
export const PAGE_SIZE = 8;
export interface Student {
  id: string; device_id: string; display_name: string | null; group_name: string | null;
  claude_name: string | null; claude_email: string | null; claude_org: string | null;
  git_name: string | null; git_email: string | null; os_user: string | null;
  hostname: string | null; os: string | null; level: number | null;
  stage: string | null; summary: string | null; profile_md: string | null;
  prompt_count: number; first_seen: string; last_seen: string;
  last_event_at?: string | null; last_summary_at?: string | null; skill_version?: string | null;
  progress_report?: ProgressReport | null; last_client?: string | null;
  analysis_allowed?: boolean; consent_version?: number | null;
}
export interface Prompt { id: number; student_id: string; session_id: string | null; project: string | null; prompt: string; created_at: string; received_at?: string; client?: string; model?: string | null; observability?: Observation | null }
export interface Summary { id: number; student_id: string; session_id: string | null; project: string | null; level: number | null; stage: string | null; summary: string | null; strengths: string | null; struggles: string | null; next_step: string | null; created_at: string; client?: string; model?: string | null; progress_report?: ProgressReport | null }
export type StudentName = Pick<Student, 'display_name' | 'claude_name' | 'git_name' | 'os_user'>;
export interface SummaryEntry extends Summary { student: StudentName | null }
export interface Stats {
  students: number; new_students: number; active_students: number; prompts: number;
  summaries: number; average_level: number | null; unassessed: number; groups: string[];
  levels: { level: number; count: number }[]; activity: { date: string; prompts: number }[];
}
export interface Filters { search: string; group: string; level: string; status: string; sort: string }
export const initialFilters: Filters = { search: '', group: '', level: '', status: '', sort: 'last_seen' };

const url = import.meta.env.VITE_SUPABASE_URL?.trim();
const key = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim();
function checkConfiguration() {
  if (!url || !key) return 'Для настоящих данных укажите URL проекта и публичный ключ Supabase в dashboard/.env.local.';
  try {
    const address = new URL(url);
    if (address.protocol !== 'https:' && !(address.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(address.hostname))) return 'Подключение к Supabase должно использовать HTTPS.';
  } catch { return 'Проверьте URL проекта Supabase.'; }
  if (key.startsWith('sb_secret_')) return 'В браузере нельзя использовать секретный ключ. Укажите anon / publishable key.';
  if (key.startsWith('eyJ')) {
    try { if (JSON.parse(atob(key.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).role === 'service_role') return 'Ключ service_role нельзя использовать в браузере. Укажите anon key.'; } catch { return 'Некорректный публичный ключ Supabase.'; }
  }
  return '';
}
export const configurationError = checkConfiguration();
export const supabase = !configurationError && url && key ? createClient(url, key) : null;
export const nameOf = (s: StudentName) => {
  const name = s.display_name || s.claude_name || s.git_name || s.os_user || 'Без имени';
  const pseudonym = name.match(/^\[(?:PERSON|USER|DEVICE)_([a-f0-9]{12})_[0-9]{4,8}\]$/);
  return pseudonym ? `Ученик ${pseudonym[1].slice(0, 6).toUpperCase()}` : name;
};
export const emailOf = (s: Student) => s.claude_email || s.git_email || 'Email не передан';
export const isActive = (s: Student) => Date.now() - new Date(s.last_seen).getTime() < 7 * 86400000;
export const formatNumber = (n: number) => new Intl.NumberFormat('ru-RU').format(n);
export function formatDate(value: string, time = false) {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', ...(time ? { hour: '2-digit', minute: '2-digit' } : {}) }).format(new Date(value));
}
export function relativeDate(value: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 1) return 'только что';
  if (minutes < 60) return `${minutes} мин. назад`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} ч. назад`;
  if (minutes < 2880) return 'вчера';
  return formatDate(value);
}

function fail(error: { message: string } | null) { if (error) throw new Error(error.message); }
const STUDENT_COLUMNS = 'id,device_id,display_name,group_name,claude_name,claude_email,claude_org,git_name,git_email,os_user,hostname,os,level,stage,summary,prompt_count,first_seen,last_seen,last_event_at,last_summary_at,skill_version,analysis_allowed,consent_version';

function requireSupabase() {
  if (!supabase) throw new Error(configurationError || 'База данных не подключена.');
  return supabase;
}

export async function getStats(days: number): Promise<Stats> {
  const { data, error } = await requireSupabase().rpc('dashboard_stats', { p_days: days });
  fail(error); return data as Stats;
}

export async function getStudents(filters: Filters, page: number, size = PAGE_SIZE): Promise<{ rows: Student[]; count: number }> {
  let query = requireSupabase().from('students').select(STUDENT_COLUMNS, { count: 'exact' });
  // Strip PostgREST filter syntax; wildcard characters are not user operators.
  const search = filters.search.replace(/[^\p{L}\p{N}\s@._+\-]/gu, '').replace(/_/g, '\\_').trim();
  if (search) query = query.or(['display_name', 'claude_name', 'claude_email', 'git_name', 'git_email', 'hostname', 'os_user'].map(f => `${f}.ilike.%${search}%`).join(','));
  if (filters.group === '__none') query = query.or('group_name.is.null,group_name.eq.');
  else if (filters.group) query = query.eq('group_name', filters.group);
  if (filters.level === 'none') query = query.is('level', null);
  else if (filters.level) query = query.eq('level', Number(filters.level));
  const cutoff = new Date(Date.now() - 7 * 86400000).toISOString();
  if (filters.status === 'active') query = query.gte('last_seen', cutoff);
  if (filters.status === 'inactive') query = query.lt('last_seen', cutoff);
  const sort = ['last_seen', 'first_seen', 'prompt_count', 'level'].includes(filters.sort) ? filters.sort : 'last_seen';
  const { data, error, count } = await query.order(sort, { ascending: false, nullsFirst: false }).order('id').range(page * size, (page + 1) * size - 1);
  fail(error); return { rows: data as Student[], count: count ?? 0 };
}
export async function getStudent(id: string): Promise<Student> {
  const { data, error } = await requireSupabase().from('students').select(`${STUDENT_COLUMNS},profile_md,progress_report,last_client`).eq('id', id).single();
  fail(error); return data as Student;
}
export async function getLatestSummary(id: string): Promise<Summary | null> {
  const { data, error } = await requireSupabase().from('summaries').select('*').eq('student_id', id)
    .order('created_at', { ascending: false }).order('id', { ascending: false }).limit(1);
  fail(error); return data?.[0] as Summary || null;
}
export async function saveStudent(id: string, display_name: string, group_name: string) {
  const values = { display_name: display_name.trim() || null, group_name: group_name.trim() || null };
  const { error } = await requireSupabase().from('students').update(values).eq('id', id).select('id').single(); fail(error);
}
export async function getHistory<T extends 'prompts' | 'summaries'>(kind: T, studentId: string | null, page = 0, options: { tag?: string; days?: number } = {}): Promise<{ rows: (T extends 'prompts' ? Prompt : Summary)[]; count: number }> {
  let query = requireSupabase().from(kind).select('*', { count: 'exact' });
  if (studentId) query = query.eq('student_id', studentId);
  if (kind === 'prompts' && options.tag) query = query.contains('observability', { tags: [options.tag] });
  if (options.days) { const start = new Date(); start.setUTCHours(0, 0, 0, 0); start.setUTCDate(start.getUTCDate() - options.days + 1); query = query.gte('created_at', start.toISOString()); }
  const { data, error, count } = await query.order('created_at', { ascending: false }).order('id', { ascending: false }).range(page * 20, page * 20 + 19);
  fail(error); return { rows: data as (T extends 'prompts' ? Prompt : Summary)[], count: count ?? 0 };
}
export async function getObservability(id: string, days: number): Promise<StudentObservability> {
  const { data, error } = await requireSupabase().rpc('student_observability', { p_student: id, p_days: days });
  fail(error); return data as StudentObservability;
}
export async function getSummary(id: number, studentId: string): Promise<Summary> {
  const { data, error } = await requireSupabase().from('summaries').select('*').eq('id', id).eq('student_id', studentId).single();
  fail(error); return data as Summary;
}
export interface SecurityAlert { id: number; student_id: string; prompt_id: number | null; tool_event_id?: number | null; category: string; severity: string; occurrences: number; status: string; created_at: string; reviewed_at: string | null; student?: StudentName | null; prompt?: { project: string; client: string; model: string; created_at: string } | null; tool?: { tool_id: string; client: string; project: string; created_at: string } | null }
export async function getAlerts(studentId: string | null, page = 0, onlyOpen = true): Promise<{ rows: SecurityAlert[]; count: number }> {
  let query = requireSupabase().from('security_alerts').select('*,student:students(display_name,claude_name,git_name,os_user),prompt:prompts(project,client,model,created_at),tool:tool_events(tool_id,client,project,created_at)', { count: 'exact' });
  if (studentId) query = query.eq('student_id', studentId);
  if (onlyOpen) query = query.eq('status', 'open');
  const { data, error, count } = await query.order('created_at', { ascending: false }).order('id', { ascending: false }).range(page * 20, page * 20 + 19);
  fail(error); return { rows: data as SecurityAlert[], count: count ?? 0 };
}
export async function getAlertCounts(): Promise<{ open: number; critical: number; latest_id: number }> {
  const { data, error } = await requireSupabase().rpc('security_alert_counts'); fail(error); return data;
}
export async function reviewAlert(id: number, status: 'reviewed' | 'false_positive') {
  const { error } = await requireSupabase().rpc('review_security_alert', { p_alert: id, p_status: status }); fail(error);
}
export async function getSummaryFeed(page = 0): Promise<{ rows: SummaryEntry[]; count: number }> {
  const { data, error, count } = await requireSupabase().from('summaries')
    .select('*,student:students(display_name,claude_name,git_name,os_user)', { count: 'exact' })
    .order('created_at', { ascending: false }).order('id', { ascending: false })
    .range(page * 20, page * 20 + 19);
  fail(error); return { rows: data as SummaryEntry[], count: count ?? 0 };
}
export async function exportStudents(filters: Filters) {
  const all: Student[] = [];
  for (let page = 0; ; page++) {
    const { rows, count } = await getStudents(filters, page, 500); all.push(...rows);
    if (all.length >= count || !rows.length) break;
  }
  const cell = (value: unknown) => {
    let text = String(value ?? '');
    if (/^[\s]*[=+@\-]/.test(text) || /^[\t\r\n]/.test(text)) text = `'${text}`;
    return `"${text.replace(/"/g, '""')}"`;
  };
  const rows = [['ID', 'Имя', 'Claude email', 'Git email', 'Группа', 'Уровень', 'Этап', 'Промпты', 'Первое появление', 'Последняя активность', 'Устройство', 'ОС'],
    ...all.map(s => [s.id, nameOf(s), s.claude_email, s.git_email, s.group_name, s.level, s.stage, s.prompt_count, s.first_seen, s.last_seen, s.hostname, s.os])];
  const blob = new Blob(['\uFEFF' + rows.map(r => r.map(cell).join(';')).join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const href = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = href;
  a.download = `arslanbek-students-${new Date().toISOString().slice(0, 10)}.csv`; a.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
