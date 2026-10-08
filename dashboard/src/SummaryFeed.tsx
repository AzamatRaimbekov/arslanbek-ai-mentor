import { useEffect, useState } from 'react';
import { ArrowUpRight, BookOpen } from 'lucide-react';
import { getSummaryFeed, nameOf, formatNumber, type SummaryEntry } from './data';
import { Empty, ErrorBox, Pagination } from './ui';
import { SummaryCard } from './StudentDetail';

export default function SummaryFeed({ refresh, onSelect }: { refresh: number; onSelect: (id: string) => void }) {
  const [rows, setRows] = useState<SummaryEntry[]>([]);
  const [page, setPage] = useState(0);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError('');
    getSummaryFeed(page).then(result => {
      if (alive) { setRows(result.rows); setCount(result.count); }
    }).catch(e => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [page, refresh, retry]);
  return <section className="card feed-card">
    <div className="card-heading"><div><h2>Сводки скилла <span className="count-pill">{formatNumber(count)}</span></h2><p>Что делали, что получилось, где возникли трудности и какой следующий шаг. Сводку пишет наставник в сессии участника.</p></div><BookOpen size={21} /></div>
    {error ? <ErrorBox error={error} retry={() => setRetry(v => v + 1)} /> : loading ? <div className="loading">Загружаем сводки…</div> : <div className="feed-list">
      {rows.length ? rows.map(row => <div key={row.id} className="summary-feed-entry">
        <button className="text-button" onClick={() => onSelect(row.student_id)}>{row.student ? nameOf(row.student) : 'Открыть участника'} <ArrowUpRight size={14} /></button>
        <SummaryCard summary={row} />
      </div>) : <Empty title="Сводок пока нет">После согласия участника скилл отправит сводку по завершённой задаче или после нескольких промптов.</Empty>}
    </div>}
    <Pagination page={page} count={count} size={20} onChange={setPage} />
  </section>;
}
