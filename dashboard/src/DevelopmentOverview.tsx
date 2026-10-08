import { BrainCircuit, ArrowUpRight, CheckCircle2, Compass, Layers, Sparkles } from 'lucide-react';
import { useId, useRef, useState } from 'react';
import CompetencyMatrix from './CompetencyMatrix';
import { formatDate, formatNumber } from './data';
import { COMPETENCIES, actorName, skillState, stateName, tagName, type CompetencyId, type StudentObservability } from './observability';
import { clientName } from './progress';

export default function DevelopmentOverview({ data, onTag, onSummary }: { data: StudentObservability; onTag: (tag: string) => void; onSummary: (id: number) => void }) {
  const [selected, setSelected] = useState<CompetencyId>('prompt_engineering');
  const detailId = useId();
  const detailRef = useRef<HTMLElement>(null);
  const definition = COMPETENCIES.find(c => c.id === selected)!;
  const stat = data.skills.find(s => s.competency_id === selected);
  const evidence = data.evidence.filter(e => e.competency_id === selected);
  return <div className="development-overview">
    <header className="observability-heading"><div><span className="report-eyebrow"><BrainCircuit size={16} />РАЗВИТИЕ В ДЕЙСТВИЯХ</span><h2>Что ученик осваивает</h2><p>За {data.days} дней. Навык подтверждает наблюдаемое действие; запрос к ИИ сам по себе этого не доказывает.</p></div></header>
    <div className="development-metrics">{[
      ['Дней с промптами', data.metrics.active_days], ['Задач отмечено готовыми', data.metrics.completed_tasks], ['Срезов наставника', data.metrics.summaries], ['Промптов в периоде', data.metrics.prompts],
    ].map(([label, value]) => <div key={String(label)}><b>{formatNumber(Number(value))}</b><span>{label}</span></div>)}</div>
    <CompetencyMatrix skills={data.skills} selected={selected} detailId={detailId} onSelect={id => { setSelected(id); detailRef.current?.scrollIntoView({ block: 'start', behavior: 'instant' }); }} />
    <section id={detailId} ref={detailRef} className="competency-detail" aria-live="polite"><div className="competency-title"><div><span className="competency-detail-label">ВЫБРАННОЕ НАПРАВЛЕНИЕ</span><h3>{definition.label}</h3><span className={`competency-state state-${skillState(stat)}`}>{stateName(skillState(stat))}</span></div>{stat && <div className="competency-detail-counts"><span><b>{stat.tasks}</b>Задач</span><span><b>{stat.independent_tasks}</b>Самостоятельных</span></div>}</div>
      <div className="competency-probe"><Sparkles size={18} /><div><b>Как проверить понимание</b><p>{stat?.next_action || definition.probe}</p></div></div>
      {evidence.length ? <div className="evidence-timeline">{evidence.map((e, index) => <article key={`${e.summary_id}-${index}`}><span className="evidence-dot" /><div className="evidence-meta"><time>{formatDate(e.created_at, true)}</time><span>{actorName(e.actor)}</span><span>{e.source === 'legacy_report' ? 'Ранний срез наставника' : 'Наблюдение наставника'}</span></div><h4>{e.task}</h4><p>{e.evidence || 'Конкретное подтверждение не передано.'}</p><button className="text-button" onClick={() => onSummary(e.summary_id)}>Открыть исходную сводку <ArrowUpRight size={14} /></button></article>)}</div> : <p className="report-empty-note">За этот период нет подтверждений. Это не означает, что ученик не владеет навыком.</p>}
      {evidence.length === 8 && <p className="observability-note">Показаны 8 последних наблюдений по направлению. Счётчики учитывают весь выбранный период.</p>}
    </section>
    <section className="observability-section"><h3><Compass size={17} />Направления работы</h3>{data.directions.length ? <div className="topic-tags">{data.directions.map(d => <span key={d.direction}>{d.direction}<b>{d.count} срезов</b></span>)}</div> : <p className="report-empty-note">Направления появятся после структурированной сводки.</p>}</section>
    <section className="observability-section"><h3><Layers size={17} />О чём ученик спрашивает</h3><p className="observability-note">Теги определяются по словам в промпте. Один запрос может иметь несколько тегов; теги не являются оценкой навыка. Нажмите тег для просмотра запросов.</p>
      {data.tags.length ? <div className="topic-tags">{data.tags.map(t => <button key={t.tag} onClick={() => onTag(t.tag)}>{tagName(t.tag)}<b>{t.count}</b><ArrowUpRight size={13} /></button>)}</div> : <p className="report-empty-note">Теги появятся с запросами обновлённого скилла.</p>}
      <div className="observation-coverage"><CheckCircle2 size={15} /><span>Метаданные есть у {data.metrics.tagged_prompts} из {data.metrics.prompts} промптов. {data.clients.map(c => `${clientName(c.client)}: ${c.count}`).join(' · ')}</span></div>
    </section>
  </div>;
}

export function ToolObservations({ data }: { data: StudentObservability }) {
  const harnessNames: Record<string, string> = { project_instructions: 'Инструкции проекта', version_control: 'Контроль версий', ci_configuration: 'Конфигурация CI', test_configuration: 'Конфигурация тестов', app_hooks: 'Хуки приложения' };
  const kindNames: Record<string, string> = { skill: 'Скилл', plugin: 'Плагин', mcp: 'MCP', harness: 'Харнес', tool: 'Инструмент' };
  const actionNames: Record<string, string> = { used: 'Применение', created: 'Создание', configured: 'Настройка' };
  return <div className="tool-observations"><header className="observability-heading"><span className="report-eyebrow"><Layers size={16} />РАБОЧАЯ СРЕДА</span><h2>Инструменты и способы работы</h2><p>Установлено, применялось и создано — разные наблюдения. Наличие инструмента не подтверждает владение им.</p></header>
    <section className="observability-section"><h3>Элементы харнеса</h3><p className="observability-note">Харнес — инструкции, инструменты и проверки вокруг агента. Видно наличие конфигурации; её качество и использование требуют отдельного подтверждения.</p>
      {data.environment ? <><div className="topic-tags">{data.environment.harness.map(h => <span key={h}>{harnessNames[h] || h}</span>)}</div>{!data.environment.harness.length && <p className="report-empty-note">В проверенных местах элементы не обнаружены. Это не проверка всей среды.</p>}<small className="muted">{clientName(data.environment.client)} · {data.environment_updated_at && formatDate(data.environment_updated_at, true)} · {data.environment.coverage === 'project_only' ? 'Только текущий проект' : 'Выбранное приложение и текущий проект'}</small></> : <p className="report-empty-note">Снимка среды пока нет. Нужен запрос из обновлённого скилла.</p>}
    </section>
    <section className="observability-section"><h3>Наблюдаемое применение и создание</h3>{data.tools.length ? <div className="tool-observation-list">{data.tools.map((tool, index) => <article key={index}><span className="tool-kind">{kindNames[tool.kind]}</span><div><b>{tool.tool_id}</b><p>{actionNames[tool.action]} · {actorName(tool.actor)} · {tool.source === 'tool_hook' ? 'Событие приложения' : 'Сводка наставника'}</p></div><span>{tool.count} событий</span></article>)}</div> : <p className="report-empty-note">События применения пока не поступили. В приложениях без хуков они зависят от вызовов и сводок агента.</p>}
      {data.tools.length === 100 && <p className="observability-note">Показаны последние 100 комбинаций инструментов и действий.</p>}
    </section>
    <section className="observability-section"><h3>Доступно в среде</h3>{data.environment?.tools.length ? <div className="topic-tags">{data.environment.tools.map((tool, index) => <span key={index}>{kindNames[tool.kind]}: {tool.tool_id}<b>{tool.scope === 'project' ? 'Проект' : 'Приложение'}</b></span>)}</div> : <p className="report-empty-note">Список установленных инструментов не передан или в проверенных местах ничего не найдено.</p>}{data.environment?.truncated && <p className="observability-note">Список ограничен 64 элементами. Это не полный перечень установок.</p>}</section>
    {data.tool_events.length > 0 && <section className="observability-section"><h3>Последние события</h3><div className="tool-event-timeline">{data.tool_events.map(event => <article key={event.id}><time>{formatDate(event.created_at, true)}</time><b>{event.tool_id}</b><span>{actionNames[event.action]} · {actorName(event.actor)}</span>{event.evidence && <p>{event.evidence}</p>}</article>)}</div><p className="observability-note">Показано до 50 последних событий; команды, аргументы и результаты инструментов не передаются.</p></section>}
  </div>;
}
