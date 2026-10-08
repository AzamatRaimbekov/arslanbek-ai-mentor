import { ArrowUpRight, Check, CheckCircle2, Circle, Compass, Flag, Lightbulb, ListChecks, Sparkles, Target, TriangleAlert, UserRound, Workflow } from 'lucide-react';
import { STAGES, clientName, type ProgressReport as Report } from './progress';
import { formatDate, type Student, type Summary } from './data';

const statuses = { in_progress: 'В работе', blocked: 'Нужна помощь', completed: 'Результат готов' };
const skills = { strength: 'Получается', developing: 'Развивается', needs_support: 'Нужна практика', unknown: 'Пока нет данных' };
function ActionList({ values, empty }: { values: string[]; empty: string }) {
  return values.length ? <ul className="report-list-text">{values.map((v, i) => <li key={i}>{v}</li>)}</ul> : <p className="report-empty-note">{empty}</p>;
}
function Details({ report: r }: { report: Report }) {
  return <>
    <section className="report-result"><h3><Flag size={16} />Что получилось</h3><p>{r.result}</p></section>
    <div className="report-contributions">
      <section><h3><UserRound size={17} />Сделал сотрудник</h3><ActionList values={r.learner_actions} empty="Самостоятельные действия пока не зафиксированы." /></section>
      <section><h3><Sparkles size={17} />Помог ИИ</h3><ActionList values={r.agent_actions} empty="Помощь агента не описана." /></section>
    </div>
    <section className="report-skills"><div className="report-section-heading"><h3><Compass size={17} />Навыки в этой задаче</h3><span>На основании действий, а не количества запросов</span></div>
      {r.skills.length ? <div className="skill-observation-grid">{r.skills.map((s, i) => <article className={`skill-observation skill-${s.status}`} key={i}>
        <span className="skill-observation-label">{skills[s.status] || 'Наблюдение'}</span><h4>{s.name}</h4><p>{s.evidence || 'Для оценки нужны дополнительные наблюдения.'}</p>
        {s.next_action && <div className="skill-exercise"><Lightbulb size={14} /><span>{s.next_action}</span></div>}
      </article>)}</div> : <p className="report-empty-note">Данных для наблюдений по навыкам пока недостаточно.</p>}
    </section>
    <section className="report-checks"><h3><ListChecks size={17} />Проверка результата</h3>{r.checks.length ? r.checks.map((c, i) => <div className={`report-check check-${c.status}`} key={i}>
      {c.status === 'passed' ? <CheckCircle2 size={18} /> : c.status === 'failed' ? <TriangleAlert size={18} /> : <Circle size={18} />}
      <div><b>{c.name}</b><p>{c.evidence || 'Подтверждение не передано.'}</p></div><span>{c.status === 'passed' ? 'Пройдено' : c.status === 'failed' ? 'Не пройдено' : 'Не проверено'}</span>
    </div>) : <p className="report-empty-note">Проверки не зафиксированы. Готовность результата не подтверждена.</p>}</section>
    {r.next_steps.length > 1 && <section className="report-followups"><h3>Дальнейшие действия</h3>{r.next_steps.slice(1).map((s, i) => <div key={i}><span>{String(i + 2).padStart(2, '0')}</span><div><b>{s.action}</b><p>Готово, когда: {s.done_when}</p><small>{s.owner === 'learner' ? 'Сотруднику' : 'Наставнику / ИИ'}</small></div></div>)}</section>}
    <footer className="report-confidence"><span><span className={`confidence-dot confidence-${r.confidence}`} />{r.confidence === 'high' ? 'Достаточно наблюдений' : r.confidence === 'medium' ? 'Часть навыков ещё нужно проверить' : 'Предварительные наблюдения'}</span>
      {r.limitations.length > 0 && <details><summary>Что пока неизвестно</summary><ActionList values={r.limitations} empty="" /></details>}
    </footer>
  </>;
}

export default function ProgressReport({ report: r, client, model, date, compact = false }: { report: Report; client?: string | null; model?: string | null; date?: string | null; compact?: boolean }) {
  const next = r.next_steps[0];
  return <article className={`work-report${compact ? ' work-report-compact' : ''}`}>
    <header className="report-heading"><div className="report-eyebrow"><Workflow size={15} />{compact ? 'СВОДКА РАБОТЫ' : 'КАРТА ПРОГРЕССА'}</div><span className={`work-status work-status-${r.status}`}>{r.status === 'completed' && <Check size={13} />}{statuses[r.status]}</span></header>
    <h2 className="report-task">{r.task}</h2><p className="report-goal">{r.goal}</p>
    <div className="report-tags">{r.directions.map((d, i) => <span key={i}>{d}</span>)}<span className="source-tag">{clientName(client)}{model ? ` · ${model}` : ''}</span>{date && <time>{formatDate(date, true)}</time>}</div>
    <ol className="task-stages" aria-label="Текущий этап задачи">{STAGES.map(([key, title], i) => <li key={key} className={r.stage === key ? 'current' : ''} aria-current={r.stage === key ? 'step' : undefined}><span>{i + 1}</span><b>{title}</b></li>)}</ol>
    <div className={`report-focus${r.blockers.length ? ' with-blocker' : ''}`}>
      <section className="current-action"><div className="action-label"><Target size={17} />Что требуется сейчас<span>{next.owner === 'learner' ? 'Сотруднику' : 'Наставнику / ИИ'}</span></div><h3>{next.action}</h3><div className="done-when"><CheckCircle2 size={15} /><p><b>Готово, когда</b>{next.done_when}</p></div></section>
      {r.blockers.length > 0 && <section className="current-blocker"><h3><TriangleAlert size={17} />Что мешает</h3><ActionList values={r.blockers} empty="" /></section>}
    </div>
    {compact ? <details className="report-expand"><summary>Навыки, действия и проверка результата <ArrowUpRight size={15} /></summary><Details report={r} /></details> : <Details report={r} />}
  </article>;
}

// Render older text profiles as readable sections; never execute embedded HTML.
export function ProfileNotes({ text }: { text: string }) {
  const sections: { title: string; lines: string[] }[] = [];
  for (const line of text.split('\n')) {
    if (/^#{1,6}\s/.test(line)) sections.push({ title: line.replace(/^#{1,6}\s+/, ''), lines: [] });
    else if (line.trim()) {
      if (!sections.length) sections.push({ title: 'Наблюдения наставника', lines: [] });
      sections[sections.length - 1].lines.push(line.replace(/^\s*[-*+]\s+/, '').replace(/\*\*([^*]+)\*\*/g, '$1'));
    }
  }
  return <div className="profile-notes">{sections.filter(s => s.lines.length).map((s, i) => <section key={i}><h4>{s.title}</h4>{s.lines.map((line, n) => <p key={n}>{line}</p>)}</section>)}</div>;
}

export function LegacyProgress({ student, summary }: { student: Student; summary: Summary | null }) {
  return <article className="work-report legacy-progress"><header className="report-heading"><div className="report-eyebrow"><Workflow size={15} />ТЕКУЩАЯ РАБОТА</div><span className="source-tag">{summary ? clientName(summary.client) : 'Ожидаем сводку'}</span></header>
    <h2 className="report-task">{summary?.stage || student.stage || 'Познакомимся с задачей'}</h2>
    <p className="report-goal">{summary?.summary || student.summary || 'После первой задачи наставник опишет результат и ближайший шаг.'}</p>
    <section className="current-action legacy-action"><div className="action-label"><Target size={17} />Что требуется сейчас</div><h3>{summary?.next_step || 'Наставнику нужно зафиксировать текущую задачу и следующий шаг.'}</h3></section>
    {(summary?.strengths || summary?.struggles) && <div className="report-contributions"><section><h3><Compass size={17} />Что получается</h3><p>{summary.strengths || 'Пока нет наблюдений.'}</p></section><section><h3><Lightbulb size={17} />Где нужна помощь</h3><p>{summary.struggles || 'Трудности не описаны.'}</p></section></div>}
    <footer className="report-confidence">{summary && <span>Последняя сводка: {formatDate(summary.created_at, true)}</span>}<p>Это прежний формат сводки. Обновлённый скилл добавит этап задачи, подтверждения навыков и критерии готовности.</p></footer>
  </article>;
}
