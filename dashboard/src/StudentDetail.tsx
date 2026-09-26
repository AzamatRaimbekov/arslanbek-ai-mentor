import { useEffect, useState } from 'react';
import { Mail, Monitor, CalendarDays, Save, MessageSquare, Sparkles, ArrowRight } from 'lucide-react';
import { getStudent, getHistory, saveStudent, nameOf, emailOf, formatDate, formatNumber, demo, type Student, type Prompt, type Summary } from './data';
import { Modal, Avatar, LevelBadge, Empty, ErrorBox, Pagination } from './ui';

export function PromptCard({ prompt, onStudent }: { prompt: Prompt; onStudent?: (id: string) => void }) {
  return <article className="history-card"><div className="history-meta"><span><MessageSquare size={14} />{prompt.project || 'Без проекта'}</span><time>{formatDate(prompt.created_at, true)}</time></div><p className="prompt-text">{prompt.prompt}</p><div className="history-bottom"><span title={prompt.session_id || ''}>Сессия: {prompt.session_id || 'не передана'}</span>{onStudent && <button className="text-button" onClick={() => onStudent(prompt.student_id)}>Карточка ученика <ArrowRight size={14} /></button>}</div></article>;
}
function SummaryCard({ summary: s }: { summary: Summary }) {
  return <article className="history-card"><div className="history-meta"><LevelBadge level={s.level} /><time>{formatDate(s.created_at, true)}</time></div><h3>{s.stage || 'Срез наставника'}</h3><p>{s.summary || 'Описание не передано'}</p>{[['Получается', s.strengths], ['Зоны роста', s.struggles], ['Следующий шаг', s.next_step]].map(([title, text]) => text && <div className="summary-section" key={title}><b>{title}</b><p>{text}</p></div>)}<div className="history-bottom">{s.project || 'Без проекта'} · {s.session_id || 'Сессия не передана'}</div></article>;
}
export default function StudentDetail({ id, onClose, onSaved }: { id: string; onClose: () => void; onSaved: () => void }) {
  const [student, setStudent] = useState<Student | null>(null);
  const [tab, setTab] = useState('overview');
  const [error, setError] = useState('');
  const [name, setName] = useState(''); const [group, setGroup] = useState('');
  const [saving, setSaving] = useState(false); const [saved, setSaved] = useState(false);
  const [prompts, setPrompts] = useState<Prompt[]>([]); const [summaries, setSummaries] = useState<Summary[]>([]);
  const [count, setCount] = useState(0); const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true); const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    setError('');
    getStudent(id).then(s => { if (alive) { setStudent(s); setName(s.display_name || ''); setGroup(s.group_name || ''); } }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [id, retry]);
  useEffect(() => {
    if (tab === 'overview') return;
    let alive = true; setLoading(true); setError('');
    const task = tab === 'prompts' ? getHistory('prompts', id, page).then(r => { if (alive) { setPrompts(r.rows); setCount(r.count); } }) : getHistory('summaries', id, page).then(r => { if (alive) { setSummaries(r.rows); setCount(r.count); } });
    task.catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [id, tab, page, retry]);
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
      <div className="tabs" role="tablist" aria-label="Данные ученика">{[['overview', 'Профиль'], ['prompts', 'Промпты'], ['summaries', 'Прогресс']].map(([key, label]) => <button role="tab" aria-selected={tab === key} key={key} className={tab === key ? 'selected' : ''} onClick={() => { setTab(key); setPage(0); setError(''); }}>{label}</button>)}</div>
      <div className="detail-body" role="tabpanel">
        {tab === 'overview' ? <>
          <section className="insight"><div><Sparkles size={17} /><h3>Последний срез наставника</h3></div><strong>{student.stage || 'Этап пока не определён'}</strong><p>{student.summary || 'Наставник ещё не отправил оценку прогресса.'}</p></section>
          <form onSubmit={save} className="edit-form"><h3>Данные для школы</h3><div className="form-grid"><label>Имя в дашборде<input maxLength={200} value={name} onChange={e => { setName(e.target.value); setSaved(false); }} placeholder={student.claude_name || student.git_name || 'Имя ученика'} /></label><label>Группа<input maxLength={200} value={group} onChange={e => { setGroup(e.target.value); setSaved(false); }} placeholder="Например, Поток 04" /></label></div><div className="save-row"><span role="status">{saved ? demo ? 'Сохранено в демо до перезагрузки' : 'Изменения сохранены' : 'Имя и группу видят только администраторы'}</span><button className="button primary" disabled={saving}><Save size={15} />{saving ? 'Сохраняем…' : 'Сохранить'}</button></div></form>
          <section><h3 className="section-label"><Monitor size={17} /> Аккаунт и устройство</h3><dl className="metadata">{[
            ['Имя Claude', student.claude_name], ['Email Claude', student.claude_email], ['Организация', student.claude_org], ['Имя Git', student.git_name], ['Email Git', student.git_email], ['Пользователь ОС', student.os_user], ['Компьютер', student.hostname], ['Операционная система', student.os], ['ID устройства', student.device_id], ['ID записи', student.id], ['Первое появление', formatDate(student.first_seen, true)], ['Последняя активность', formatDate(student.last_seen, true)],
          ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || 'Не передано'}</dd></div>)}</dl></section>
          <section><h3 className="section-label"><Mail size={17} /> Профиль от наставника</h3>{student.profile_md ? <pre className="profile-text">{student.profile_md}</pre> : <p className="muted">Профиль ещё не передан.</p>}</section>
        </> : loading ? <div className="loading">Загружаем историю…</div> : !error && <>
          {tab === 'prompts' ? prompts.length ? prompts.map(p => <PromptCard key={p.id} prompt={p} />) : <Empty title="Промптов пока нет" /> : summaries.length ? summaries.map(s => <SummaryCard key={s.id} summary={s} />) : <Empty title="Оценок пока нет">Наставник отправит первый срез после нескольких промптов.</Empty>}
          <Pagination page={page} count={count} size={20} onChange={setPage} />
        </>}
      </div><div className="detail-footer"><CalendarDays size={14} /> Одна запись соответствует одному устройству ученика</div>
    </>}
  </Modal>;
}
