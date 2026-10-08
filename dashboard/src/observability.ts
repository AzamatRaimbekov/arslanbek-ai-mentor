export const COMPETENCIES = [
  { id: 'prompt_engineering', label: 'Промпт-инжиниринг', short: 'Промпты', code: 'Pr', probe: 'Попросите ученика самому сформулировать цель, ограничения и проверяемый результат новой задачи.' },
  { id: 'context_engineering', label: 'Контекст-инжиниринг', short: 'Контекст', code: 'Cx', probe: 'Попросите выбрать нужные файлы и объяснить, что включить в контекст, что исключить и как проверить актуальность.' },
  { id: 'harness', label: 'Харнес: рабочая среда агента', short: 'Харнес', code: 'Hr', probe: 'Попросите объяснить роль инструкций проекта, хуков и проверок, затем самостоятельно настроить один элемент.' },
  { id: 'skill_authoring', label: 'Создание и применение скиллов', short: 'Скиллы', code: 'Sk', probe: 'Попросите самостоятельно описать область скилла и проверить его на новом примере.' },
  { id: 'plugin_authoring', label: 'Плагины и MCP', short: 'Плагины', code: 'Pl', probe: 'Попросите объяснить инструменты и разрешения плагина, затем проверить одну интеграцию.' },
  { id: 'frontend', label: 'Frontend', short: 'Frontend', code: 'Fe', probe: 'Попросите самостоятельно проверить интерфейс и объяснить состояние компонента и обработку ошибки.' },
  { id: 'backend', label: 'Backend', short: 'Backend', code: 'Be', probe: 'Попросите объяснить путь запроса, валидацию входа и проверить неуспешный сценарий API.' },
  { id: 'databases', label: 'Базы данных', short: 'Базы', code: 'Db', probe: 'Попросите объяснить схему и самостоятельно написать запрос или проверить миграцию.' },
  { id: 'testing', label: 'Проверка и тестирование', short: 'Тесты', code: 'Ts', probe: 'Попросите выбрать пограничный сценарий, предсказать результат и самостоятельно выполнить проверку.' },
  { id: 'devops', label: 'DevOps и публикация', short: 'DevOps', code: 'Op', probe: 'Попросите объяснить конфигурацию окружения, проверку готовности и порядок отката.' },
  { id: 'security', label: 'Защита данных', short: 'Защита', code: 'Sec', probe: 'Попросите распознать секреты и объяснить, какие сведения нельзя передавать модели и как их заменить.' },
] as const;
export type CompetencyId = typeof COMPETENCIES[number]['id'];
export type Actor = 'learner' | 'agent' | 'together' | 'unknown';
export const actorName = (actor: string) => ({ learner: 'Ученик самостоятельно', agent: 'Выполнил агент', together: 'Совместно с агентом', unknown: 'Вклад ученика не уточнён' }[actor] || 'Источник не уточнён');
export const tagName = (tag: string) => COMPETENCIES.find(c => c.id === tag)?.short || ({ 'intent:debug': 'Исправление ошибки', 'intent:learn': 'Объяснение', 'intent:plan': 'Планирование', 'intent:build': 'Создание', 'intent:review': 'Проверка работы' }[tag] || tag);
export const privacyName = (category: string) => ({ api_key: 'Признаки API-ключа или токена', private_key: 'Приватный ключ', credential: 'Пароль или реквизиты доступа', personal_contact: 'Контактные данные', financial_id: 'Возможный платёжный идентификатор', confidential_marker: 'Метка конфиденциального документа' }[category] || 'Сигнал защиты данных');
export interface LearningEvidence {
  competency_id: CompetencyId; state: 'unknown' | 'practiced' | 'demonstrated' | 'needs_practice';
  actor: Actor; evidence_type: 'learner_action' | 'learner_explanation' | 'artifact_check' | 'mentor_observation';
  evidence: string; next_action: string;
}
export interface Evidence extends LearningEvidence { summary_id: number; created_at: string; task: string; goal: string; project: string; confidence: string; source: string }
export interface Tool { kind: 'skill' | 'plugin' | 'mcp' | 'harness' | 'tool'; tool_id: string; action: 'used' | 'created' | 'configured'; actor: Actor; evidence?: string; source?: string; count?: number; last_used?: string }
export interface Environment { version: 1; client: string; tools: { kind: Tool['kind']; tool_id: string; scope: string }[]; harness: string[]; truncated: boolean; coverage: string }
export interface Observation { version: 1; tags: string[]; tag_source: 'keyword_rules'; privacy_signals: { category: string; severity: string; count: number }[] }
export interface SkillStats { competency_id: CompetencyId; observations: number; tasks: number; independent_tasks: number; latest_state: LearningEvidence['state']; last_observed: string; next_action: string }
export interface StudentObservability {
  days: number; period_start: string; generated_at: string;
  metrics: { prompts: number; tagged_prompts: number; summaries: number; completed_tasks: number; active_days: number; projects: number; open_alerts: number };
  skills: SkillStats[]; evidence: Evidence[]; tags: { tag: string; count: number }[];
  directions: { direction: string; count: number }[]; clients: { client: string; count: number }[];
  tools: Tool[]; tool_events: (Tool & { id: number; created_at: string; project: string })[];
  environment: Environment | null; environment_updated_at: string | null;
  activity: { date: string; prompts: number }[] | null;
}
export const skillState = (s?: SkillStats) => !s ? 'unknown' : s.latest_state === 'needs_practice' ? 'needs_practice' : s.independent_tasks >= 2 ? 'repeated' : s.independent_tasks === 1 ? 'demonstrated' : 'practiced';
export const stateName = (value: string) => ({ unknown: 'Нет наблюдений', needs_practice: 'Нужна практика', repeated: 'Повторно подтверждено', demonstrated: 'Есть самостоятельный пример', practiced: 'Практикуется' }[value] || 'Наблюдение');
