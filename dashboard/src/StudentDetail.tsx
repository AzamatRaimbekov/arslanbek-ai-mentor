import { useEffect, useState } from 'react';
import { Mail, Monitor, CalendarDays, Save, MessageSquare, ArrowRight } from 'lucide-react';
import { getStudent, getLatestSummary, getHistory, getObservability, getSummary, saveStudent, nameOf, emailOf, formatDate, formatNumber, type Student, type Prompt, type Summary } from './data';
import ProgressReport, { ProfileNotes, LegacyProgress } from './ProgressReport';
import { isProgressReport, clientName } from './progress';
import { Modal, Avatar, LevelBadge, Empty, ErrorBox, Pagination } from './ui';
import DevelopmentOverview, { ToolObservations } from './DevelopmentOverview';
import SecurityAlerts from './SecurityAlerts';
import { COMPETENCIES, tagName, privacyName, type StudentObservability } from './observability';
import './observability.css';

export function PromptCard({ prompt, onStudent }: { prompt: Prompt; onStudent?: (id: string) => void }) {
  return <article className="history-card"><div className="history-meta"><span><MessageSquare size={14} />{prompt.project || 'Без проекта'}</span><span>{clientName(prompt.client)}{prompt.model ? ` · ${prompt.model}` : ''}</span><time>{formatDate(prompt.created_at, true)}</time></div><div className="prompt-tags">{prompt.observability ? prompt.observability.tags.map(tag => <span key={tag}>{tagName(tag)}</span>) : <span className="muted">Теги не переданы</span>}</div><p className="prompt-text">{prompt.prompt}</p>{prompt.observability?.privacy_signals.length ? <details className="prompt-privacy"><summary>Признаки чувствительных данных · {prompt.observability.privacy_signals.length} категорий</summary>{prompt.observability.privacy_signals.map(signal => <p key={signal.category}>{privacyName(signal.category)}: {signal.count} совпадений. Значения скрыты.</p>)}</details> : null}<div className="history-bottom"><span title={prompt.session_id || ''}>Сессия: {prompt.session_id || 'не передана'}</span>{onStudent && <button className="text-button" onClick={() => onStudent(prompt.student_id)}>Карточка ученика <ArrowRight size={14} /></button>}</div></article>;
}
export function SummaryCard({ summary: s }: { summary: Summary }) {
  if (isProgressReport(s.progress_report)) return <ProgressReport report={s.progress_report} client={s.client} model={s.model} date={s.created_at} compact />;
  return <article className="history-card"><div className="history-meta"><LevelBadge level={s.level} /><time>{formatDate(s.created_at, true)}</time></div><h3>{s.stage || 'Срез наставника'}</h3><p>{s.summary || 'Описание не передано'}</p>{[['Получается', s.strengths], ['Зоны роста', s.struggles], ['Следующий шаг', s.next_step]].map(([title, text]) => text && <div className="summary-section" key={title}><b>{title}</b><p>{text}</p></div>)}<div className="history-bottom">{clientName(s.client)} · {s.project || 'Без проекта'} · {s.session_id || 'Сессия не передана'}</div></article>;
}
export default function StudentDetail({ id, onClose, onSaved }: { id: string; onClose: () => void; onSaved: () => void }) {
  const [student, setStudent] = useState<Student | null>(null);
  const [latest, setLatest] = useState<Summary | null>(null);
  const [tab, setTab] = useState('development');
  const [days, setDays] = useState(30); const [tag, setTag] = useState('');
  const [insights, setInsights] = useState<StudentObservability | null>(null); const [insightError, setInsightError] = useState('');
  const [focusedSummary, setFocusedSummary] = useState<Summary | null>(null);
  const [error, setError] = useState('');
  const [name, setName] = useState(''); const [group, setGroup] = useState('');
  const [saving, setSaving] = useState(false); const [saved, setSaved] = useState(false);
  const [prompts, setPrompts] = useState<Prompt[]>([]); const [summaries, setSummaries] = useState<Summary[]>([]);
  const [count, setCount] = useState(0); const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true); const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    setError('');
    Promise.all([getStudent(id), getLatestSummary(id)]).then(([s, last]) => { if (alive) { setLatest(last); setStudent(s); setName(s.display_name || ''); setGroup(s.group_name || ''); } }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [id, retry]);
  useEffect(() => {
    let alive = true; setInsights(null); setInsightError('');
    getObservability(id, days).then(data => { if (alive) setInsights(data); }).catch(e => { if (alive) setInsightError(e.message); });
    return () => { alive = false; };
  }, [id, days, retry]);
  useEffect(() => {
    if (tab !== 'prompts' && tab !== 'summaries') return;
    let alive = true; setLoading(true); setError('');
    const task = tab === 'prompts' ? getHistory('prompts', id, page, { tag, days }).then(r => { if (alive) { setPrompts(r.rows); setCount(r.count); } }) : getHistory('summaries', id, page, { days }).then(r => { if (alive) { setSummaries(r.rows); setCount(r.count); } });
    task.catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [id, tab, page, retry, tag, days]);
  async function openSummary(summaryId: number) {
    try { setFocusedSummary(await getSummary(summaryId, id)); } catch (e) { setError((e as Error).message); }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setSaved(false); setError('');
    try { await saveStudent(id, name, group); setStudent(await getStudent(id)); setSaved(true); onSaved(); }
    catch (e) { setError((e as Error).message); } finally { setSaving(false); }
  }
  return <Modal title="Карточка ученика" onClose={onClose} wide>
    {error && <ErrorBox error={error} retry={() => setRetry(r => r + 1)} />}
    {!student ? !error && <div className="loading">Загружаем профиль…</div> : <>
      <div className="student-hero"><Avatar name={nameOf(student)} /><div><h2>{nameOf(student)}</h2><p>{emailOf(student)}</p><LevelBadge level={student.level} /></div></div>
      <div className="student-mini-stats"><div><b>{formatNumber(student.prompt_count)}</b><span>промптов за всё время</span></div><div><b>{formatDate(student.first_seen)}</b><span>первое появление</span></div><div><b>{formatDate(student.last_seen)}</b><span>последняя активность</span></div></div>
      <div className="student-period"><label>Период наблюдений<select aria-label="Период развития ученика" value={days} onChange={e => { setDays(Number(e.target.value)); setPage(0); }}><option value={14}>14 дней</option><option value={30}>30 дней</option><option value={90}>90 дней</option></select></label>{insights && <span>{insights.metrics.open_alerts ? `${insights.metrics.open_alerts} сигналов требуют проверки` : 'Открытых сигналов нет'}</span>}</div>
      <div className="tabs student-tabs" role="tablist" aria-label="Данные ученика">{[['development', 'Развитие'], ['tools', 'Инструменты'], ['prompts', 'Промпты'], ['summaries', 'Прогресс'], ['security', 'Защита данных'], ['overview', 'Профиль']].map(([key, label]) => <button role="tab" aria-selected={tab === key} key={key} className={tab === key ? 'selected' : ''} onClick={() => { setTab(key); setPage(0); setError(''); }}>{label}</button>)}</div>
      <div className="detail-body" role="tabpanel">
        {tab === 'development' || tab === 'tools' ? <>
          {insightError ? <ErrorBox error={`Наблюдения пока недоступны: ${insightError}`} retry={() => setRetry(v => v + 1)} /> : !insights ? <div className="loading">Собираем историю развития…</div> : tab === 'tools' ? <ToolObservations data={insights} /> : <DevelopmentOverview data={insights} onTag={value => { setTag(value); setTab('prompts'); setPage(0); }} onSummary={openSummary} />}
          {tab === 'development' && <><h3 className="current-work-heading">Последняя задача</h3>{isProgressReport(student.progress_report) ? <ProgressReport report={student.progress_report} client={student.last_client} date={student.last_summary_at} /> : <LegacyProgress student={student} summary={latest} />}</>}
          {focusedSummary && <section className="focused-summary"><h3>Исходная сводка наблюдения</h3><SummaryCard summary={focusedSummary} /><button className="text-button" onClick={() => setFocusedSummary(null)}>Скрыть исходную сводку</button></section>}
        </> : tab === 'security' ? <SecurityAlerts studentId={id} refresh={retry} onReviewed={() => { setRetry(v => v + 1); onSaved(); }} /> : tab === 'overview' ? <>
          {isProgressReport(student.progress_report) ? <ProgressReport report={student.progress_report} client={student.last_client} date={student.last_summary_at} /> : <LegacyProgress student={student} summary={latest} />}
          <form onSubmit={save} className="edit-form"><h3>Данные для школы</h3><div className="form-grid"><label>Имя в дашборде<input maxLength={200} value={name} onChange={e => { setName(e.target.value); setSaved(false); }} placeholder={student.claude_name || student.git_name || 'Имя ученика'} /></label><label>Группа<input maxLength={200} value={group} onChange={e => { setGroup(e.target.value); setSaved(false); }} placeholder="Например, Поток 04" /></label></div><div className="save-row"><span role="status">{saved ? 'Изменения сохранены' : 'Имя и группу видят только администраторы'}</span><button className="button primary" disabled={saving}><Save size={15} />{saving ? 'Сохраняем…' : 'Сохранить'}</button></div></form>
          <details className="detail-settings"><summary>Аккаунт и устройство</summary><section><h3 className="section-label"><Monitor size={17} /> Аккаунт и устройство</h3><dl className="metadata">{[
            ['Имя Claude', student.claude_name], ['Email Claude', student.claude_email], ['Организация', student.claude_org], ['Имя Git', student.git_name], ['Email Git', student.git_email], ['Пользователь ОС', student.os_user], ['Компьютер', student.hostname], ['Операционная система', student.os], ['Версия скилла', student.skill_version], ['Допуск к ИИ-анализу', student.analysis_allowed === undefined ? 'Не передан' : student.analysis_allowed ? 'Есть согласие' : 'Нет согласия'], ['Последний срез', student.last_summary_at ? formatDate(student.last_summary_at, true) : null], ['ID устройства', student.device_id], ['ID записи', student.id], ['Первое появление', formatDate(student.first_seen, true)], ['Последняя активность', formatDate(student.last_seen, true)],
          ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || 'Не передано'}</dd></div>)}</dl></section></details>
          <section><h3 className="section-label"><Mail size={17} /> Заметки наставника</h3>{student.profile_md ? <ProfileNotes text={student.profile_md} /> : <p className="muted">Профиль ещё не передан.</p>}</section>
        </> : <>
          {tab === 'prompts' && <div className="prompt-filter"><label>Тег запроса<select aria-label="Тег промптов ученика" value={tag} onChange={e => { setTag(e.target.value); setPage(0); }}><option value="">Все теги</option>{[...COMPETENCIES.map(c => c.id), 'intent:debug', 'intent:learn', 'intent:plan', 'intent:build', 'intent:review'].map(value => <option key={value} value={value}>{tagName(value)}</option>)}</select></label><small>По словам в тексте; оценка навыка находится в карте развития.</small></div>}
          {loading ? <div className="loading">Загружаем историю…</div> : !error && <>
          {tab === 'prompts' ? prompts.length ? prompts.map(p => <PromptCard key={p.id} prompt={p} />) : <Empty title="Промптов пока нет" /> : summaries.length ? summaries.map(s => <SummaryCard key={s.id} summary={s} />) : <Empty title="Оценок пока нет">Наставник отправит первый срез после нескольких промптов.</Empty>}
          <Pagination page={page} count={count} size={20} onChange={setPage} />
        </>}</>}
      </div><div className="detail-footer"><CalendarDays size={14} /> Одна запись соответствует одному устройству ученика</div>
    </>}
  </Modal>;
}
