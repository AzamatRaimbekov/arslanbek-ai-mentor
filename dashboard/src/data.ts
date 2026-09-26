import { createClient } from '@supabase/supabase-js';

export const LEVELS = ['Знакомство', 'Заказчик', 'Постановщик', 'Контролёр', 'Архитектор', 'Автор'];
export const PAGE_SIZE = 8;
export interface Student {
  id: string; device_id: string; display_name: string | null; group_name: string | null;
  claude_name: string | null; claude_email: string | null; claude_org: string | null;
  git_name: string | null; git_email: string | null; os_user: string | null;
  hostname: string | null; os: string | null; level: number | null;
  stage: string | null; summary: string | null; profile_md: string | null;
  prompt_count: number; first_seen: string; last_seen: string;
}
export interface Prompt { id: number; student_id: string; session_id: string | null; project: string | null; prompt: string; created_at: string; received_at?: string }
export interface Summary { id: number; student_id: string; session_id: string | null; project: string | null; level: number | null; stage: string | null; summary: string | null; strengths: string | null; struggles: string | null; next_step: string | null; created_at: string }
export interface Stats {
  students: number; new_students: number; active_students: number; prompts: number;
  summaries: number; average_level: number | null; unassessed: number; groups: string[];
  levels: { level: number; count: number }[]; activity: { date: string; prompts: number }[];
}
export interface Filters { search: string; group: string; level: string; status: string; sort: string }
export const initialFilters: Filters = { search: '', group: '', level: '', status: '', sort: 'last_seen' };

const url = import.meta.env.VITE_SUPABASE_URL?.trim();
const key = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim();
export const supabase = url && key ? createClient(url, key) : null;
export const demo = !supabase;
export const nameOf = (s: Student) => s.display_name || s.claude_name || s.git_name || s.os_user || 'Без имени';
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

const people = [
  ['Айдана Абдылдаева', 'aidana', 'Поток 04', 3, 'Интернет-магазин · разработка'],
  ['Тимур Асанов', 'timur', 'Поток 04', 4, 'SaaS-платформа · архитектура'],
  ['Алина Ким', 'alina', 'Поток 03', 2, 'Первый проект · лендинг'],
  ['Бекзат Токтогулов', 'bekzat', 'Поток 04', 2, 'Telegram-бот · интеграции'],
  ['Мария Соколова', 'maria', 'Поток 03', 5, 'AI-агент · автоматизация'],
  ['Данияр Осмонов', 'daniyar', 'Поток 04', 1, 'Первый проект · идея'],
  ['София Ли', 'sofia', 'Поток 03', 3, 'Мобильное приложение · тесты'],
  ['Нурлан Ибраев', 'nurlan', 'Поток 04', 0, 'Знакомство с инструментами'],
  ['Азамат Усенов', 'azamat', 'Поток 03', 3, 'CRM · разработка'],
  ['Элина Мамбетова', 'elina', 'Поток 04', 2, 'Портфолио · дизайн'],
  ['Руслан Алиев', 'ruslan', 'Поток 03', 4, 'Аналитика · интеграции'],
  ['Анна Петрова', 'anna', 'Поток 04', 1, 'Первый проект · лендинг'],
  ['Эмир Садыков', 'emir', 'Поток 03', 2, 'Telegram-бот · разработка'],
  ['Диана Жумабаева', 'diana', 'Поток 04', 3, 'Сервис записи · тесты'],
  ['Артём Иванов', 'artem', 'Поток 03', 2, 'Каталог · разработка'],
  ['Мээрим Акматова', 'meerim', '', null, 'Первый запуск'],
  ['Ильяс Беков', 'ilyas', 'Поток 04', 1, 'Первый проект · идея'],
  ['Полина Орлова', 'polina', '', null, 'Первый запуск'],
] as const;
const demoNow = Date.now();
const ago = (days: number) => new Date(demoNow - days * 86400000).toISOString();
const demoStudents: Student[] = people.map(([name, slug, group, level, stage], i) => ({
  id: `demo-${i + 1}`, device_id: `00000000-0000-4000-8000-${String(i + 1).padStart(12, '0')}`,
  display_name: name, claude_name: name, claude_email: `${slug}@example.com`, claude_org: 'Учебная группа',
  git_name: name, git_email: `${slug}@example.com`, os_user: slug, hostname: `${slug}-laptop`,
  os: i % 3 === 0 ? 'Windows 11' : i % 3 === 1 ? 'macOS 15.6' : 'Ubuntu 24.04',
  group_name: group || null, level, stage, summary: level === null ? null : 'Работает над собственным проектом. Формулирует задачи с контекстом, проверяет результат и задаёт вопросы по реализации.',
  profile_md: level === null ? null : '# Профиль ученика\n\n## Что уже знает\nФормулирует задачу, работает с Git, проверяет изменения в браузере.\n\n## Что даётся тяжело\nДекомпозиция больших задач и обработка ошибок.\n\n## Цели\nЗапустить первую версию своего продукта и показать её пользователям.\n\n## Как удобно работать\nКороткими шагами, с примерами и разбором результата.',
  prompt_count: 0, first_seen: ago(44 - i * 2), last_seen: ago(i < 5 ? (i + 1) / 240 : i < 14 ? (i - 3) / 2 : i),
}));
const promptExamples = [
  'Хочу добавить корзину в интернет-магазин. Товары должны сохраняться после перезагрузки страницы. Давай сначала разберём, где лучше хранить состояние.',
  'Я проверила изменения в браузере. Когда удаляю последний товар, сумма не обнуляется. Объясни, почему это происходит, и помоги найти причину.',
  'Давай разобьём задачу на небольшие шаги. Готово, когда пользователь может добавить товар, изменить количество и оформить заказ.',
  'Как протестировать этот сценарий? Хочу проверить и успешный ответ, и ситуацию, когда сервер недоступен.',
  'Объясни, пожалуйста, чем отличается состояние компонента от данных в базе. Покажи на примере моего проекта.',
];
const demoPrompts: Prompt[] = demoStudents.flatMap((s, i) => Array.from({ length: s.level === null ? 2 : 28 + i * 7 }, (_, j) => ({
  id: i * 1000 + j, student_id: s.id, session_id: `session-${i}-${Math.floor(j / 5)}`,
  project: ['shop-app', 'my-saas', 'landing-page', 'telegram-bot'][i % 4],
  prompt: promptExamples[j % promptExamples.length],
  created_at: new Date(new Date(s.last_seen).getTime() - j * 5 * 3600000).toISOString(),
}))).sort((a, b) => b.created_at.localeCompare(a.created_at));
demoStudents.forEach(s => { s.prompt_count = demoPrompts.filter(p => p.student_id === s.id).length; });
const demoSummaries: Summary[] = demoStudents.flatMap((s, i) => s.level === null ? [] : Array.from({ length: 3 }, (_, j) => ({
  id: i * 10 + j, student_id: s.id, session_id: `session-${i}-${j}`, project: ['shop-app', 'my-saas', 'landing-page', 'telegram-bot'][i % 4],
  level: Math.max(0, s.level! - Math.floor(j / 2)), stage: s.stage,
  summary: s.summary, strengths: 'Задаёт уточняющие вопросы. Самостоятельно проверяет результат в браузере.',
  struggles: 'Пока сложно заранее продумать неуспешные сценарии и разделить большую задачу на шаги.',
  next_step: 'Перед следующей задачей записать три проверяемых критерия готовности.',
  created_at: new Date(new Date(s.last_seen).getTime() - j * 3 * 86400000).toISOString(),
}))).sort((a, b) => b.created_at.localeCompare(a.created_at));

function fail(error: { message: string } | null) { if (error) throw new Error(error.message); }
const STUDENT_COLUMNS = 'id,device_id,display_name,group_name,claude_name,claude_email,claude_org,git_name,git_email,os_user,hostname,os,level,stage,summary,prompt_count,first_seen,last_seen';

export async function getStats(days: number): Promise<Stats> {
  if (supabase) {
    const { data, error } = await supabase.rpc('dashboard_stats', { p_days: days }); fail(error); return data as Stats;
  }
  const start = new Date(); start.setUTCHours(0, 0, 0, 0); start.setUTCDate(start.getUTCDate() - days + 1);
  const assessed = demoStudents.filter(s => s.level !== null);
  return {
    students: demoStudents.length, new_students: demoStudents.filter(s => new Date(s.first_seen) >= start).length,
    active_students: demoStudents.filter(s => new Date(s.last_seen) >= start).length,
    prompts: demoPrompts.filter(p => new Date(p.created_at) >= start).length,
    summaries: demoSummaries.filter(s => new Date(s.created_at) >= start).length,
    average_level: Math.round(assessed.reduce((a, s) => a + s.level!, 0) / assessed.length * 10) / 10,
    unassessed: demoStudents.length - assessed.length,
    groups: [...new Set(demoStudents.map(s => s.group_name).filter((g): g is string => !!g))].sort(),
    levels: LEVELS.map((_, level) => ({ level, count: demoStudents.filter(s => s.level === level).length })),
    activity: Array.from({ length: days }, (_, i) => {
      const date = new Date(start.getTime() + i * 86400000).toISOString().slice(0, 10);
      return { date, prompts: demoPrompts.filter(p => p.created_at.startsWith(date)).length };
    }),
  };
}

export async function getStudents(filters: Filters, page: number, size = PAGE_SIZE): Promise<{ rows: Student[]; count: number }> {
  if (supabase) {
    let query = supabase.from('students').select(STUDENT_COLUMNS, { count: 'exact' });
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
  const search = filters.search.toLowerCase().trim();
  const rows = demoStudents.filter(s =>
    (!search || [nameOf(s), s.claude_name, s.claude_email, s.git_name, s.git_email, s.hostname, s.os_user].some(v => v?.toLowerCase().includes(search))) &&
    (!filters.group || (filters.group === '__none' ? !s.group_name : s.group_name === filters.group)) &&
    (!filters.level || (filters.level === 'none' ? s.level === null : s.level === Number(filters.level))) &&
    (!filters.status || (filters.status === 'active' ? isActive(s) : !isActive(s)))
  ).sort((a, b) => {
    if (filters.sort === 'level') return (b.level ?? -1) - (a.level ?? -1);
    if (filters.sort === 'prompt_count') return b.prompt_count - a.prompt_count;
    return (filters.sort === 'first_seen' ? b.first_seen.localeCompare(a.first_seen) : b.last_seen.localeCompare(a.last_seen)) || a.id.localeCompare(b.id);
  });
  return { rows: rows.slice(page * size, (page + 1) * size), count: rows.length };
}
export async function getStudent(id: string): Promise<Student> {
  if (!supabase) return { ...demoStudents.find(s => s.id === id)! };
  const { data, error } = await supabase.from('students').select(`${STUDENT_COLUMNS},profile_md`).eq('id', id).single();
  fail(error); return data as Student;
}
export async function saveStudent(id: string, display_name: string, group_name: string) {
  const values = { display_name: display_name.trim() || null, group_name: group_name.trim() || null };
  if (!supabase) { Object.assign(demoStudents.find(s => s.id === id)!, values); return; }
  const { error } = await supabase.from('students').update(values).eq('id', id).select('id').single(); fail(error);
}
export async function getHistory<T extends 'prompts' | 'summaries'>(kind: T, studentId: string | null, page = 0): Promise<{ rows: (T extends 'prompts' ? Prompt : Summary)[]; count: number }> {
  if (supabase) {
    let query = supabase.from(kind).select('*', { count: 'exact' });
    if (studentId) query = query.eq('student_id', studentId);
    const { data, error, count } = await query.order('created_at', { ascending: false }).order('id', { ascending: false }).range(page * 20, page * 20 + 19);
    fail(error); return { rows: data as (T extends 'prompts' ? Prompt : Summary)[], count: count ?? 0 };
  }
  const rows = (kind === 'prompts' ? demoPrompts : demoSummaries).filter(p => !studentId || p.student_id === studentId);
  return { rows: rows.slice(page * 20, page * 20 + 20) as (T extends 'prompts' ? Prompt : Summary)[], count: rows.length };
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
  a.download = `arslanbek-students${demo ? '-demo' : ''}-${new Date().toISOString().slice(0, 10)}.csv`; a.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
