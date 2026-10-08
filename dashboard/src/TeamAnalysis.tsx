import { useEffect, useState } from 'react';
import { Sparkles, RefreshCw, FileText, ShieldCheck, ArrowUpRight, Clock, Database } from 'lucide-react';
import { supabase, formatDate, formatNumber } from './data';
import { Empty, ErrorBox, Modal, Pagination } from './ui';

type Finding = { kind: 'observation' | 'interpretation'; statement: string; evidence_refs: string[]; uncertainty: string };
type Evidence = { ref: string; source_type: string; created_at: string; text?: string; summary?: string; strengths?: string; struggles?: string; next_step?: string; level?: number | null; truncated: boolean };
type Member = { student_id: string; display_name: string; group_name: string | null; metrics: { ref: string; prompts: number; sessions: number; projects: number; active_days: number; summaries: number }; prompts: Evidence[]; summaries: Evidence[] };
type Snapshot = { period_start: string; period_end: string; total_devices: number; eligible_devices: number; excluded_without_analysis_consent: number; students: Member[] };
type ReportBody = { team_findings: Finding[]; members: { student_id: string; status: string; findings: Finding[]; next_step: string }[]; recommendations: { action: string; evidence_refs: string[] }[]; limitations: string[] };
type Report = { id: string; created_at: string; completed_at: string | null; status: string; days: number; group_name: string | null; model: string | null; prompt_version: string | null; error: string | null; input_snapshot: Snapshot; report: ReportBody | null };

export default function TeamAnalysis({ groups, onStudent }: { groups: string[]; onStudent: (id: string) => void }) {
  const [days, setDays] = useState(30); const [group, setGroup] = useState('');
  const [reports, setReports] = useState<Report[]>([]); const [selected, setSelected] = useState<Report | null>(null);
  const [page, setPage] = useState(0); const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false); const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(''); const [refresh, setRefresh] = useState(0); const [source, setSource] = useState<{ name: string; evidence: Evidence | Member['metrics'] } | null>(null);
  useEffect(() => {
    if (!supabase) return;
    let alive = true; setLoading(true);
    supabase.from('team_reports').select('id,created_at,completed_at,status,days,group_name,model,error', { count: 'exact' }).order('created_at', { ascending: false }).range(page * 20, page * 20 + 19).then(({ data, error, count }) => {
      if (!alive) return;
      if (error) setError('Не удалось загрузить отчёты. Проверьте, что применена миграция 0004_team_analysis.sql.');
      else { setReports(data as Report[]); setCount(count ?? 0); }
      setLoading(false);
    });
    return () => { alive = false; };
  }, [refresh, page]);

  async function openReport(id: string) {
    setError(''); setLoading(true);
    try {
      const { data, error } = await supabase!.from('team_reports').select('*').eq('id', id).single();
      if (error) throw error;
      setSelected(data as Report);
    } catch { setError('Не удалось открыть отчёт. Попробуйте обновить историю.'); }
    finally { setLoading(false); }
  }
  async function generate() {
    if (!supabase) return;
    setGenerating(true); setError('');
    try {
      const { data, error } = await supabase.functions.invoke('analyze-team', { body: { days, group: group || null } });
      if (error) {
        let message = 'ИИ-анализ недоступен. Проверьте публикацию функции и серверные секреты.';
        if (error.context instanceof Response) { try { message = (await error.context.json()).error || message; } catch { /* keep safe fallback */ } }
        throw new Error(message);
      }
      if (!data?.id) throw new Error('Сервер не вернул идентификатор отчёта. Обновите историю перед повторным запуском.');
      await openReport(data.id);
    } catch (e) { setError((e as Error).message); }
    finally { setGenerating(false); setPage(0); setRefresh(v => v + 1); }
  }
  function showSource(ref: string) {
    for (const member of selected?.input_snapshot.students || []) {
      const evidence = member.metrics.ref === ref ? member.metrics : [...member.prompts, ...member.summaries].find(s => s.ref === ref);
      if (evidence) { setSource({ name: member.display_name, evidence }); return; }
    }
  }
  const refs = (values: string[]) => <div className="evidence-links">{values.map(ref => <button key={ref} onClick={() => showSource(ref)}><FileText size={12} />{ref.startsWith('metrics:') ? 'Счётчики' : ref.replace('prompt:', 'Промпт #').replace('summary:', 'Срез #')}</button>)}</div>;
  const findings = (values: Finding[]) => values.map((f, i) => <article className="finding" key={i}><span className={`finding-kind ${f.kind}`}>{f.kind === 'observation' ? 'Наблюдение ИИ' : 'Интерпретация ИИ'}</span><p>{f.statement}</p>{refs(f.evidence_refs)}<p className="finding-uncertainty">Предел вывода: {f.uncertainty}</p></article>);
  const snapshot = selected?.input_snapshot;
  return <div className="analysis-space">
    <section className="card analysis-controls"><div><span className="setup-symbol"><Sparkles size={23} /></span><h2>Что происходит в команде</h2><p>ИИ читает выборку промптов и срезов. Каждый вывод можно сверить с источником.</p></div><div className="analysis-form"><label>Период<select aria-label="Период анализа" value={days} onChange={e => setDays(Number(e.target.value))} disabled={generating}>{[14, 30, 90].map(d => <option key={d} value={d}>{d} дней</option>)}</select></label><label>Группа<select aria-label="Группа для анализа" value={group} onChange={e => setGroup(e.target.value)} disabled={generating}><option value="">Вся команда</option>{groups.map(g => <option key={g}>{g}</option>)}</select></label><button className="button primary" onClick={generate} disabled={generating || !supabase}><Sparkles size={16} />{generating ? 'Анализируем факты…' : 'Сформировать отчёт'}</button></div><div className="analysis-disclosure"><ShieldCheck size={15} /><span>Внешний ИИ получает отрывки только от участников с согласием на анализ. Запуск расходует API-бюджет школы; отчёт сохраняется в истории.</span></div></section>
    {error && <ErrorBox error={error} />}
    <div className="analysis-layout"><section className="card analysis-history"><div className="card-heading"><h2>История отчётов</h2><button className="icon-button" aria-label="Обновить историю отчётов" onClick={() => setRefresh(v => v + 1)} disabled={loading || !supabase}><RefreshCw size={15} /></button></div>{reports.length ? <div className="report-list">{reports.map(r => <button className={r.id === selected?.id ? 'selected' : ''} key={r.id} onClick={() => openReport(r.id)} disabled={loading}><span><FileText size={16} /><b>{r.group_name || 'Вся команда'}</b></span><small>{formatDate(r.created_at, true)} · {r.days} дней</small><span className={`report-status status-${r.status}`}>{r.status === 'complete' ? 'Готов' : r.status === 'insufficient_data' ? 'Нет данных' : r.status === 'failed' ? 'Ошибка' : 'В обработке'}</span></button>)}</div> : <Empty title={loading ? 'Загружаем историю…' : 'Отчётов ещё нет'}>Выберите период и сформируйте первый анализ.</Empty>}{count > 20 && <Pagination page={page} count={count} size={20} onChange={setPage} />}</section>
    <section className="card analysis-result">{!selected ? <Empty title="Факты прежде выводов">Откройте отчёт из истории или создайте новый. Объём промптов сам по себе не измеряет продуктивность человека.</Empty> : <>
      <div className="analysis-result-heading"><span className="eyebrow">ОТЧЁТ НАСТАВНИКА</span><h2>{selected.group_name || 'Вся команда'} · {selected.days} дней</h2><p>{formatDate(selected.created_at, true)} · {selected.model || 'Без вызова ИИ'} · {selected.prompt_version || '—'}</p></div>
      {snapshot && <><div className="analysis-coverage"><div><b>{snapshot.eligible_devices} / {snapshot.total_devices}</b><span>устройств допущено к анализу</span></div><div><b>{snapshot.excluded_without_analysis_consent}</b><span>без согласия на ИИ-анализ</span></div><div><b>{formatNumber(snapshot.students.reduce((a, s) => a + s.metrics.prompts, 0))}</b><span>промптов за период</span></div></div><p className="analysis-method"><Database size={14} />Точные счётчики и выборка до 8 промптов и 5 срезов на устройство. Срезы — оценки наставника, а не независимая проверка результата.</p></>}
      {selected.status === 'running' && <div className="analysis-pending"><Clock size={18} /><p>Отчёт ещё не завершён. Обновите историю через минуту. Если прошло больше пяти минут, проверьте логи серверной функции.</p><button className="button" onClick={() => openReport(selected.id)}>Проверить результат</button></div>}
      {selected.status === 'failed' && <ErrorBox error={selected.error || 'Не удалось сформировать отчёт.'} />}
      {selected.report && <div className="analysis-body"><h3>Наблюдения о команде</h3>{selected.report.team_findings.length ? findings(selected.report.team_findings) : <p className="muted">Недостаточно оснований для общего вывода о команде.</p>}
        <h3>По участникам</h3>{selected.report.members.map(m => { const person = snapshot?.students.find(s => s.student_id === m.student_id); return <section className="member-analysis" key={m.student_id}><div className="member-analysis-heading"><button onClick={() => onStudent(m.student_id)}>{person?.display_name || 'Участник'}<ArrowUpRight size={15} /></button><span>{m.status === 'insufficient_data' ? 'Недостаточно данных' : 'Есть наблюдения'}</span></div>{person && <p className="member-coverage">Прочитано {person.prompts.length} из {person.metrics.prompts} промптов, {person.summaries.length} из {person.metrics.summaries} срезов · {person.metrics.active_days} дней с промптами</p>}{findings(m.findings)}<div className="next-step"><b>Следующий шаг</b><p>{m.next_step}</p></div></section>; })}
        {!!selected.report.recommendations.length && <><h3>Что сделать наставнику</h3>{selected.report.recommendations.map((r, i) => <div className="finding" key={i}><p>{r.action}</p>{refs(r.evidence_refs)}</div>)}</>}
        <div className="analysis-limitations"><h3>Чего этот отчёт не доказывает</h3><ul><li>ИИ-выводы требуют проверки наставником. Ссылка на источник не гарантирует правильную интерпретацию.</li><li>Отсутствие событий не означает отсутствие работы. Записи устройств не всегда равны числу людей.</li>{selected.report.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></div>
      </div>}
    </>}</section></div>
    {source && <Modal title={`Источник · ${source.name}`} onClose={() => setSource(null)}><div className="source-content">{'source_type' in source.evidence ? <><span className="finding-kind">{source.evidence.source_type === 'student_prompt' ? 'Текст промпта' : 'Оценка наставника'}</span><p className="muted">{formatDate(source.evidence.created_at, true)}</p>{source.evidence.truncated && <p className="muted">В отчёт попал сокращённый отрывок.</p>}<pre>{source.evidence.text || [source.evidence.summary, source.evidence.strengths && `Получается: ${source.evidence.strengths}`, source.evidence.struggles && `Трудности: ${source.evidence.struggles}`, source.evidence.next_step && `Следующий шаг: ${source.evidence.next_step}`].filter(Boolean).join('\n\n')}</pre></> : <dl className="metadata">{[['Промпты', source.evidence.prompts], ['Сессии', source.evidence.sessions], ['Проекты', source.evidence.projects], ['Дни с промптами', source.evidence.active_days], ['Срезы', source.evidence.summaries]].map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>}</div></Modal>}
  </div>;
}
