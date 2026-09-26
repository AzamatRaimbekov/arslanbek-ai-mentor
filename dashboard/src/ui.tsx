import { useEffect, useRef, type ReactNode } from 'react';
import { X, ArrowUpRight, Inbox, ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react';
import { LEVELS, type Stats, formatNumber, formatDate } from './data';

export function LevelBadge({ level }: { level: number | null }) {
  return <span className={`level-badge level-${level ?? 'none'}`}>{level === null ? 'Нет оценки' : <><b>{level}</b>{LEVELS[level]}</>}</span>;
}
export function Avatar({ name, small = false }: { name: string; small?: boolean }) {
  const color = [...name].reduce((a, c) => a + c.charCodeAt(0), 0) % 6;
  return <span className={`avatar avatar-${color} ${small ? 'small' : ''}`} aria-hidden="true">{name.split(' ').slice(0, 2).map(s => s[0]).join('')}</span>;
}
export function Empty({ title = 'Пока здесь пусто', children }: { title?: string; children?: ReactNode }) {
  return <div className="empty"><span className="empty-icon"><Inbox size={24} /></span><h3>{title}</h3><p>{children || 'Данные появятся после первых сессий с наставником.'}</p></div>;
}
export function ErrorBox({ error, retry }: { error: string; retry?: () => void }) {
  return <div className="error-box" role="alert"><AlertCircle size={18} /><span>{error}</span>{retry && <button onClick={retry}>Повторить</button>}</div>;
}
export function Pagination({ page, count, size, onChange }: { page: number; count: number; size: number; onChange: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / size));
  return <div className="pagination"><span>{count ? `${page * size + 1}–${Math.min((page + 1) * size, count)} из ${formatNumber(count)}` : '0 записей'}</span><div><button className="icon-button" aria-label="Предыдущая страница" disabled={!page} onClick={() => onChange(page - 1)}><ChevronLeft size={17} /></button><span>Страница {page + 1} из {pages}</span><button className="icon-button" aria-label="Следующая страница" disabled={page >= pages - 1} onClick={() => onChange(page + 1)}><ChevronRight size={17} /></button></div></div>;
}
export function Modal({ title, children, onClose, wide = false }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const el = dialog.current!; el.showModal(); const previous = document.body.style.overflow; document.body.style.overflow = 'hidden'; return () => { el.close(); document.body.style.overflow = previous; }; }, []);
  return <dialog ref={dialog} className={`modal ${wide ? 'drawer' : ''}`} aria-label={title} onCancel={e => { e.preventDefault(); onClose(); }} onClick={e => { if (e.target === e.currentTarget) onClose(); }}><div className="modal-content"><div className="modal-heading"><span>{title}</span><button className="icon-button" aria-label="Закрыть" onClick={onClose}><X size={20} /></button></div>{children}</div></dialog>;
}
export function ActivityChart({ stats, days }: { stats: Stats; days: number }) {
  const values = stats.activity;
  const max = Math.max(4, ...values.map(d => d.prompts));
  const ceiling = Math.ceil(max / 4) * 4;
  const width = 660, height = 156, left = 0, bottom = 172;
  const points = values.map((v, i) => [left + i * width / Math.max(1, values.length - 1), bottom - v.prompts / ceiling * height]);
  const path = points.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${y}`).join(' ');
  return <section className="card activity-card"><div className="card-heading"><div><h2>Активность учеников</h2><p>Количество промптов за последние {days} дней</p></div><span className="chart-legend"><i />Промпты</span></div><div className="chart-container"><div className="chart-axis">{[4, 3, 2, 1, 0].map(v => <span key={v}>{formatNumber(ceiling * v / 4)}</span>)}</div><div className="chart-main"><svg className="activity-chart" viewBox="0 0 660 185" role="img" aria-label={`График активности: ${formatNumber(stats.prompts)} промптов за ${days} дней`} preserveAspectRatio="none"><defs><linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#8672ed" stopOpacity=".21" /><stop offset="100%" stopColor="#8672ed" stopOpacity=".015" /></linearGradient></defs>{[0, 1, 2, 3, 4].map(i => <line key={i} x1="0" x2="660" y1={bottom - i * height / 4} y2={bottom - i * height / 4} stroke="#ececf2" strokeDasharray="4 5" />)}<path d={`${path} L${width},${bottom} L0,${bottom} Z`} fill="url(#chart-fill)" /><path d={path} stroke="#8873e8" strokeWidth="2.5" fill="none" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />{points.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="5" className="chart-point"><title>{formatDate(values[i].date)}: {values[i].prompts} промптов</title></circle>)}</svg><div className="chart-dates">{[0, Math.floor((values.length - 1) / 3), Math.floor((values.length - 1) * 2 / 3), values.length - 1].map(i => <span key={i}>{formatDate(values[i].date)}</span>)}</div></div></div><div className="chart-note"><span className="dot purple" />Каждый вопрос — ещё один шаг к самостоятельности<span>UTC</span></div></section>;
}
export function LevelsChart({ stats, onGuide }: { stats: Stats; onGuide: () => void }) {
  const assessed = stats.students - stats.unassessed;
  return <section className="card levels-card"><div className="card-heading"><div><h2>Уровни владения ИИ</h2><p>От первых шагов до своих агентов</p></div><button className="icon-button" aria-label="О шкале уровней" onClick={onGuide}><ArrowUpRight size={18} /></button></div><div className="levels-list">{stats.levels.map(v => <div className="level-row" key={v.level}><span className={`level-number level-${v.level}`}>{v.level}</span><span>{LEVELS[v.level]}</span><div className="level-track"><i className={`level-fill fill-${v.level}`} style={{ width: `${assessed ? v.count / assessed * 100 : 0}%` }} /></div><b>{v.count}</b></div>)}</div><div className="levels-footer"><span>Ещё без оценки</span><b>{stats.unassessed} чел.</b></div></section>;
}
export function LevelGuide({ onClose }: { onClose: () => void }) {
  const descriptions = ['Первые сессии: знакомится с возможностями агента.', 'Просит сделать задачу, пока редко проверяет результат.', 'Даёт контекст и формулирует проверяемые критерии готовности.', 'Сам проверяет изменения, запускает тесты и объясняет решения.', 'Планирует архитектуру и выбирает инструменты под задачу.', 'Создаёт скиллы, агентов и автоматизации, помогает другим.'];
  return <Modal title="Как устроена шкала уровней" onClose={onClose}><div className="guide"><p>Наставник оценивает устойчивые навыки по действиям ученика, а не по одному удачному промпту.</p>{LEVELS.map((name, i) => <div className="guide-row" key={name}><span className={`level-number level-${i}`}>{i}</span><div><h3>{name}</h3><p>{descriptions[i]}</p></div></div>)}</div></Modal>;
}
