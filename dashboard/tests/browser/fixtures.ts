import { readFileSync } from 'node:fs';
import type { ProgressReport } from '../../src/progress';
import type { Student, Prompt, Summary, Stats } from '../../src/data';

// Synthetic records are used only by Playwright HTTP routes. Never import from src.
export function createFixtures() {
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
const progress: ProgressReport = JSON.parse(readFileSync(new URL('../../../skills/arslanbek-ai-mentor/references/progress-example.json', import.meta.url), 'utf8'));
const fixtureNow = Date.now();
const ago = (days: number) => new Date(fixtureNow - days * 86400000).toISOString();
const students: Student[] = people.map(([name, slug, group, level, stage], i) => ({
  id: `fixture-${i + 1}`, device_id: `00000000-0000-4000-8000-${String(i + 1).padStart(12, '0')}`,
  display_name: name, claude_name: name, claude_email: `${slug}@example.com`, claude_org: 'Учебная группа',
  git_name: name, git_email: `${slug}@example.com`, os_user: slug, hostname: `${slug}-laptop`,
  os: i % 3 === 0 ? 'Windows 11' : i % 3 === 1 ? 'macOS 15.6' : 'Ubuntu 24.04',
  group_name: group || null, level, stage, summary: level === null ? null : 'Работает над собственным проектом. Формулирует задачи с контекстом, проверяет результат и задаёт вопросы по реализации.',
  profile_md: level === null ? null : '# Профиль ученика\n\n## Что уже знает\nФормулирует задачу, работает с Git, проверяет изменения в браузере.\n\n## Что даётся тяжело\nДекомпозиция больших задач и обработка ошибок.\n\n## Цели\nЗапустить первую версию своего продукта и показать её пользователям.\n\n## Как удобно работать\nКороткими шагами, с примерами и разбором результата.',
  ...(i === 0 ? { progress_report: progress, last_client: 'codex', last_summary_at: ago(0) } : {}),
  prompt_count: 0, first_seen: ago(44 - i * 2), last_seen: ago(i < 5 ? (i + 1) / 240 : i < 14 ? (i - 3) / 2 : i),
}));
const promptExamples = [
  'Хочу добавить корзину в интернет-магазин. Товары должны сохраняться после перезагрузки страницы. Давай сначала разберём, где лучше хранить состояние.',
  'Я проверила изменения в браузере. Когда удаляю последний товар, сумма не обнуляется. Объясни, почему это происходит, и помоги найти причину.',
  'Давай разобьём задачу на небольшие шаги. Готово, когда пользователь может добавить товар, изменить количество и оформить заказ.',
  'Как протестировать этот сценарий? Хочу проверить и успешный ответ, и ситуацию, когда сервер недоступен.',
  'Объясни, пожалуйста, чем отличается состояние компонента от данных в базе. Покажи на примере моего проекта.',
];
const prompts: Prompt[] = students.flatMap((s, i) => Array.from({ length: s.level === null ? 2 : 28 + i * 7 }, (_, j) => ({
  id: i * 1000 + j, student_id: s.id, session_id: `session-${i}-${Math.floor(j / 5)}`,
  project: ['shop-app', 'my-saas', 'landing-page', 'telegram-bot'][i % 4],
  prompt: promptExamples[j % promptExamples.length],
  created_at: new Date(new Date(s.last_seen).getTime() - j * 5 * 3600000).toISOString(),
}))).sort((a, b) => b.created_at.localeCompare(a.created_at));
students.forEach(s => { s.prompt_count = prompts.filter(p => p.student_id === s.id).length; });
const summaries: Summary[] = students.flatMap((s, i) => s.level === null ? [] : Array.from({ length: 3 }, (_, j) => ({
  id: i * 10 + j, student_id: s.id, session_id: `session-${i}-${j}`, project: ['shop-app', 'my-saas', 'landing-page', 'telegram-bot'][i % 4],
  ...(i === 0 && j === 0 ? { progress_report: progress, client: 'codex', model: 'test-model' } : {}),
  level: Math.max(0, s.level! - Math.floor(j / 2)), stage: s.stage,
  summary: s.summary, strengths: 'Задаёт уточняющие вопросы. Самостоятельно проверяет результат в браузере.',
  struggles: 'Пока сложно заранее продумать неуспешные сценарии и разделить большую задачу на шаги.',
  next_step: 'Перед следующей задачей записать три проверяемых критерия готовности.',
  created_at: new Date(new Date(s.last_seen).getTime() - j * 3 * 86400000).toISOString(),
}))).sort((a, b) => b.created_at.localeCompare(a.created_at));


function stats(days: number): Stats {
  const start = new Date(); start.setUTCHours(0, 0, 0, 0); start.setUTCDate(start.getUTCDate() - days + 1);
  const assessed = students.filter(s => s.level !== null);
  return {
    students: students.length, new_students: students.filter(s => new Date(s.first_seen) >= start).length,
    active_students: students.filter(s => new Date(s.last_seen) >= start).length,
    prompts: prompts.filter(p => new Date(p.created_at) >= start).length,
    summaries: summaries.filter(s => new Date(s.created_at) >= start).length,
    average_level: Math.round(assessed.reduce((a, s) => a + s.level!, 0) / assessed.length * 10) / 10,
    unassessed: students.length - assessed.length,
    groups: [...new Set(students.map(s => s.group_name).filter((g): g is string => !!g))].sort(),
    levels: Array.from({ length: 6 }, (_, level) => ({ level, count: students.filter(s => s.level === level).length })),
    activity: Array.from({ length: days }, (_, i) => {
      const date = new Date(start.getTime() + i * 86400000).toISOString().slice(0, 10);
      return { date, prompts: prompts.filter(p => p.created_at.startsWith(date)).length };
    }),
  };
}

return { students, prompts, summaries, stats };
}
