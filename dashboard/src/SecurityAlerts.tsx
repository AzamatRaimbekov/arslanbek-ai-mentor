import { useEffect, useState } from 'react';
import { ShieldAlert, CheckCircle2, TriangleAlert } from 'lucide-react';
import { getAlerts, reviewAlert, formatDate, nameOf, type SecurityAlert } from './data';
import { privacyName } from './observability';
import { clientName } from './progress';
import { Empty, ErrorBox, Pagination } from './ui';

export default function SecurityAlerts({ studentId = null, refresh = 0, onStudent, onReviewed }: { studentId?: string | null; refresh?: number; onStudent?: (id: string) => void; onReviewed?: () => void }) {
  const [rows, setRows] = useState<SecurityAlert[]>([]); const [count, setCount] = useState(0);
  const [page, setPage] = useState(0); const [open, setOpen] = useState(true);
  const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  const [retry, setRetry] = useState(0); const [busy, setBusy] = useState<number | null>(null);
  useEffect(() => {
    let alive = true; setLoading(true); setError('');
    getAlerts(studentId, page, open).then(result => { if (alive) { setRows(result.rows); setCount(result.count); } }).catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [studentId, page, open, refresh, retry]);
  async function review(id: number, status: 'reviewed' | 'false_positive') {
    setBusy(id); setError('');
    try { await reviewAlert(id, status); setRetry(v => v + 1); onReviewed?.(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }
  return <section className="security-panel"><header className="observability-heading"><span className="report-eyebrow"><ShieldAlert size={16} />ЗАЩИТА КОНФИДЕНЦИАЛЬНЫХ ДАННЫХ</span><h2>Сигналы для проверки</h2><p>В промпте или доступном событии инструмента обнаружены признаки секрета или конфиденциального материала. Передача конкретному сервису не подтверждена. Локальное обезличивание очищает отчёт школе и не перехватывает весь трафик приложения.</p></header>
    <div className="alert-filter"><label>Показывать<select aria-label="Фильтр сигналов" value={open ? 'open' : 'all'} onChange={e => { setOpen(e.target.value === 'open'); setPage(0); }}><option value="open">Требуют проверки</option><option value="all">Все сигналы</option></select></label><span>{count} записей</span></div>
    {error && <ErrorBox error={error} retry={() => setRetry(v => v + 1)} />}
    {loading ? <div className="loading">Загружаем сигналы…</div> : !error && (rows.length ? <div className="security-alert-list">{rows.map(alert => <article key={alert.id} className={`security-alert severity-${alert.severity}`}>
      <div className="security-alert-top"><span>{alert.severity === 'critical' ? <ShieldAlert size={18} /> : <TriangleAlert size={18} />}{privacyName(alert.category)}</span><time>{formatDate(alert.created_at, true)}</time></div>
      {!studentId && alert.student && <button className="text-button" onClick={() => onStudent?.(alert.student_id)}>{nameOf(alert.student)}</button>}
      <p>{alert.occurrences} совпадений · {alert.tool ? `Событие инструмента ${alert.tool.tool_id}` : 'Промпт'} · {clientName(alert.prompt?.client || alert.tool?.client)}{alert.prompt?.model ? ` · ${alert.prompt.model}` : ''} · {alert.prompt?.project || alert.tool?.project || 'Проект не передан'}</p>
      <small>Значения и фрагменты секрета не сохраняются в сигнале. Проверьте ситуацию с учеником. При подтверждённом секрете замените ключ или пароль у его владельца.</small>
      {alert.status === 'open' ? <div className="security-alert-actions"><button className="button" disabled={busy === alert.id} onClick={() => review(alert.id, 'reviewed')}><CheckCircle2 size={15} />Проверено преподавателем</button><button className="text-button" disabled={busy === alert.id} onClick={() => review(alert.id, 'false_positive')}>Ложное срабатывание</button></div> : <p className="alert-reviewed">{alert.status === 'false_positive' ? 'Отмечено как ложное срабатывание' : 'Проверено преподавателем'}{alert.reviewed_at && ` · ${formatDate(alert.reviewed_at, true)}`}</p>}
    </article>)}</div> : <Empty title="Сигналов для проверки нет">Это означает отсутствие поступивших сигналов. Полнота распознавания и всех каналов передачи не гарантируется.</Empty>)}
    <Pagination page={page} count={count} size={20} onChange={setPage} />
  </section>;
}
