import { useEffect, useState, type FormEvent } from 'react';
import type { Session } from '@supabase/supabase-js';
import { LayoutDashboard, Users, MessageSquare, Settings, ChevronDown, ChevronRight, ArrowUpRight, Download, Search, SlidersHorizontal, RefreshCw, Sparkles, BookOpen, ShieldCheck, LogOut, ArrowRight, CalendarDays, CircleHelp, PanelLeftClose, Menu, Database, Check, ExternalLink, Activity, GraduationCap } from 'lucide-react';
import { supabase, demo, getStats, getStudents, getHistory, exportStudents, initialFilters, LEVELS, PAGE_SIZE, nameOf, emailOf, isActive, formatNumber, relativeDate, type Stats, type Student, type Prompt, type Filters } from './data';
import { Avatar, LevelBadge, ErrorBox, Empty, Pagination, ActivityChart, LevelsChart, LevelGuide } from './ui';
import StudentDetail, { PromptCard } from './StudentDetail';

const nav = [
  { id: 'overview', name: 'Обзор', icon: LayoutDashboard },
  { id: 'students', name: 'Ученики', icon: Users },
  { id: 'prompts', name: 'История промптов', icon: MessageSquare },
  { id: 'settings', name: 'Подключение', icon: Settings },
];

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(demo);
  const [admin, setAdmin] = useState(demo);
  const [authError, setAuthError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!supabase) return;
    const { data } = supabase.auth.onAuthStateChange((_event, value) => { setSession(value); setAuthReady(true); });
    return () => data.subscription.unsubscribe();
  }, []);
  useEffect(() => {
    if (!supabase || !session) { setAdmin(demo); return; }
    let alive = true; setAuthError(''); setAdmin(false);
    supabase.rpc('is_admin').then(({ data, error }) => {
      if (!alive) return;
      if (error) setAuthError('Не удалось проверить доступ. Проверьте подключение и миграции базы.');
      else if (!data) setAuthError('У этого аккаунта нет доступа к кабинету наставника. Добавьте пользователя в таблицу admins.');
      else setAdmin(true);
    });
    return () => { alive = false; };
  }, [session, attempt]);
  if (!authReady) return <div className="auth-screen"><div className="loading">Проверяем сессию…</div></div>;
  if (!demo && !session) return <Login />;
  if (!admin) return <div className="auth-screen"><div className="auth-card"><Brand /><h1>{authError ? 'Доступ к кабинету' : 'Проверяем доступ…'}</h1>{authError && <><ErrorBox error={authError} retry={() => setAttempt(v => v + 1)} /><button className="button" onClick={() => supabase?.auth.signOut()}>Выйти из аккаунта</button></>}</div></div>;
  return <Dashboard email={session?.user.email} />;
}

function Brand() {
  return <div className="brand"><span className="brand-mark">a<span>.</span></span><div>arslanbek<span>AI MENTOR</span></div></div>;
}
function Login() {
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false); const [error, setError] = useState('');
  async function submit(e: FormEvent) {
    e.preventDefault(); setLoading(true); setError('');
    try { const { error } = await supabase!.auth.signInWithPassword({ email, password }); if (error) setError('Не удалось войти. Проверьте email, пароль и подключение к базе.'); }
    catch { setError('Нет соединения с сервером. Попробуйте ещё раз.'); } finally { setLoading(false); }
  }
  return <div className="auth-screen"><div className="auth-card"><Brand /><span className="eyebrow">КАБИНЕТ НАСТАВНИКА</span><h1>Весь прогресс.<br />В одном месте.</h1><p>Войдите, чтобы видеть, как ваши ученики учатся создавать с ИИ.</p><form onSubmit={submit}><label>Email<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} placeholder="mentor@example.com" /></label><label>Пароль<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="Ваш пароль" /></label>{error && <ErrorBox error={error} />}<button className="button primary" disabled={loading}>{loading ? 'Входим…' : 'Войти в кабинет'}<ArrowRight size={17} /></button></form><div className="auth-foot"><ShieldCheck size={16} /> Доступ только для администраторов школы</div></div></div>;
}

function Dashboard({ email }: { email?: string }) {
  const [page, setPage] = useState('overview'); const [days, setDays] = useState(30);
  const [stats, setStats] = useState<Stats | null>(null); const [statsError, setStatsError] = useState('');
  const [refresh, setRefresh] = useState(0); const [refreshing, setRefreshing] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [selected, setSelected] = useState<string | null>(null); const [guide, setGuide] = useState(false);
  const [mobileNav, setMobileNav] = useState(false); const [toast, setToast] = useState('');
  const [filters, setFilters] = useState<Filters>(initialFilters);
  useEffect(() => {
    let alive = true; setRefreshing(true); setStatsError('');
    getStats(days).then(data => { if (alive) { setStats(data); setLastUpdate(new Date()); } }).catch(e => { if (alive) { setStats(null); setStatsError(e.message); } }).finally(() => { if (alive) setRefreshing(false); });
    return () => { alive = false; };
  }, [days, refresh]);
  useEffect(() => { const timer = setInterval(() => { if (document.visibilityState === 'visible') setRefresh(v => v + 1); }, 60000); return () => clearInterval(timer); }, []);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(''), 4500); return () => clearTimeout(timer); }, [toast]);
  function navigate(id: string) { setPage(id); setMobileNav(false); }
  async function logout() { const { error } = await supabase!.auth.signOut(); if (error) setToast('Не удалось выйти. Попробуйте ещё раз.'); }
  return <div className="app-shell">
    {mobileNav && <button className="nav-scrim" aria-label="Закрыть меню" onClick={() => setMobileNav(false)} />}
    <aside className={`sidebar ${mobileNav ? 'open' : ''}`}><Brand /><div className="workspace"><span className="workspace-icon"><GraduationCap size={19} /></span><div><b>Школа Arslanbek</b><span>Кабинет наставника</span></div><ShieldCheck size={15} /></div><span className="nav-label">РАБОЧЕЕ ПРОСТРАНСТВО</span><nav aria-label="Основная навигация">{nav.map(({ id, name, icon: Icon }) => <button key={id} className={`nav-item ${page === id ? 'active' : ''}`} onClick={() => navigate(id)} aria-current={page === id ? 'page' : undefined}><Icon size={19} /><span>{name}</span>{id === 'students' && stats && <b>{stats.students}</b>}</button>)}</nav><div className="sidebar-bottom"><div className="mentor-note"><div className="note-symbol"><Sparkles size={19} /></div><h3>Учить создавать,<br />а не копировать.</h3><p>Помогайте ученикам становиться самостоятельнее с каждым шагом.</p><button onClick={() => setGuide(true)}>О шкале прогресса <ArrowUpRight size={15} /></button></div><button className="help-button" onClick={() => navigate('settings')}><CircleHelp size={18} />Как подключить скилл <ArrowUpRight size={15} /></button><div className="sidebar-account"><Avatar name="Арсланбек Наставник" small /><div><b>Наставник</b><span title={email}>{email || 'Демонстрационный кабинет'}</span></div>{demo ? <span className="account-dot" /> : <button className="icon-button" aria-label="Выйти из аккаунта" onClick={logout}><LogOut size={17} /></button>}</div></div></aside>
    <div className="main-shell"><header className="topbar"><div><button className="icon-button mobile-menu" aria-label="Открыть меню" onClick={() => setMobileNav(true)}><Menu size={20} /></button><PanelLeftClose className="desktop-panel-icon" size={18} /><span className="top-divider" /><span>Рабочее пространство</span><ChevronRight size={14} /><b>{nav.find(n => n.id === page)?.name}</b></div><div className="topbar-right"><span className="connection-state"><i className={demo ? 'demo-dot' : ''} />{demo ? 'Демо-режим' : 'Supabase подключён'}</span><button className="icon-button" aria-label="Обновить данные" disabled={refreshing} onClick={() => setRefresh(v => v + 1)}><RefreshCw size={17} className={refreshing ? 'spin' : ''} /></button><Avatar name="Арсланбек Наставник" small /></div></header>
      <main>
        {demo && <div className="demo-banner"><span><Sparkles size={14} />Вы смотрите демонстрационные данные. Подключите базу, чтобы увидеть своих учеников.</span><button onClick={() => navigate('settings')}>Подключить <ArrowRight size={14} /></button></div>}
        <div className="page-heading"><div><span className="eyebrow">ARS LAN BEK / MENTOR SPACE</span><h1>{page === 'overview' ? 'Каждый ученик — на виду' : page === 'students' ? 'Ваши ученики' : page === 'prompts' ? 'История промптов' : 'Всё начинается с подключения'}<span className="heading-dot">.</span></h1><p>{page === 'overview' ? 'Наблюдайте за прогрессом. Замечайте трудности. Помогайте расти.' : page === 'students' ? 'Люди, их проекты и путь к самостоятельной работе с ИИ.' : page === 'prompts' ? 'Посмотрите, какие задачи ученики решают вместе с наставником.' : 'Соедините скилл, базу данных и кабинет наставника.'}</p></div>{page === 'overview' && <label className="period-select"><CalendarDays size={16} /><select aria-label="Период статистики" value={days} onChange={e => setDays(Number(e.target.value))}><option value={14}>Последние 14 дней</option><option value={30}>Последние 30 дней</option><option value={90}>Последние 90 дней</option></select><ChevronDown size={14} /></label>}</div>
        {statsError && page !== 'settings' && <ErrorBox error={`Не удалось загрузить статистику: ${statsError}`} retry={() => setRefresh(v => v + 1)} />}
        {page === 'overview' && (stats ? <><div className={`metrics-grid ${refreshing ? 'refreshing' : ''}`}><Metric label="Всего учеников" value={formatNumber(stats.students)} icon={<Users size={19} />} note={<><span className="metric-tag">+{stats.new_students}</span>новых за {days} дней</>} /><Metric label="Активные ученики" value={formatNumber(stats.active_students)} icon={<Activity size={19} />} note={<><span className="green-dot" />за последние {days} дней</>} /><Metric label="Промптов отправлено" value={formatNumber(stats.prompts)} icon={<MessageSquare size={19} />} note={<>за последние {days} дней</>} /><Metric label="Средний уровень ИИ" value={stats.average_level === null ? '—' : String(stats.average_level).replace('.', ',')} icon={<Sparkles size={19} />} suffix="/ 5" note={<>по последней оценке наставника</>} /></div><div className="charts-grid"><ActivityChart stats={stats} days={days} /><LevelsChart stats={stats} onGuide={() => setGuide(true)} /></div></> : !statsError && <div className="metrics-skeleton" aria-label="Загрузка статистики">{[0, 1, 2, 3].map(i => <div key={i} />)}</div>)}
        {(page === 'overview' || page === 'students') && <StudentTable filters={filters} setFilters={setFilters} groups={stats?.groups || []} refresh={refresh} onSelect={setSelected} notify={setToast} />}
        {page === 'prompts' && <PromptFeed refresh={refresh} onSelect={setSelected} />}
        {page === 'settings' && <Setup />}
        <footer className="page-footer"><span><ShieldCheck size={14} /> Только данные, переданные с согласия ученика</span><span>{lastUpdate ? `Обновлено в ${lastUpdate.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}` : 'Ожидаем данные'}<i />Автообновление · 1 мин.</span></footer>
      </main>
    </div>
    {selected && <StudentDetail key={selected} id={selected} onClose={() => setSelected(null)} onSaved={() => setRefresh(v => v + 1)} />}
    {guide && <LevelGuide onClose={() => setGuide(false)} />}
    {toast && <div className="toast" role="status"><Check size={17} />{toast}</div>}
  </div>;
}

function Metric({ label, value, icon, note, suffix }: { label: string; value: string; icon: React.ReactNode; note: React.ReactNode; suffix?: string }) {
  return <section className="metric card"><div className="metric-label"><span>{label}</span><span className="metric-icon">{icon}</span></div><div className="metric-value">{value}{suffix && <small>{suffix}</small>}</div><div className="metric-note">{note}</div></section>;
}

function StudentTable({ filters, setFilters, groups, refresh, onSelect, notify }: { filters: Filters; setFilters: (f: Filters) => void; groups: string[]; refresh: number; onSelect: (id: string) => void; notify: (s: string) => void }) {
  const [rows, setRows] = useState<Student[]>([]); const [count, setCount] = useState(0); const [page, setPage] = useState(0);
  const [search, setSearch] = useState(filters.search); const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  const [exporting, setExporting] = useState(false); const [more, setMore] = useState(false); const [retry, setRetry] = useState(0);
  useEffect(() => { const timeout = setTimeout(() => { if (filters.search !== search) { setFilters({ ...filters, search }); setPage(0); } }, 250); return () => clearTimeout(timeout); }, [search, filters, setFilters]);
  useEffect(() => {
    let alive = true; setLoading(true); setError('');
    getStudents(filters, page).then(r => { if (alive) { if (page > 0 && page * PAGE_SIZE >= r.count) { setPage(0); return; } setRows(r.rows); setCount(r.count); } }).catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [filters, page, refresh, retry]);
  function update(key: keyof Filters, value: string) { setFilters({ ...filters, [key]: value }); setPage(0); }
  async function download() { setExporting(true); try { await exportStudents(filters); notify('CSV с текущей выборкой готов'); } catch (e) { setError(`Не удалось выгрузить CSV: ${(e as Error).message}`); } finally { setExporting(false); } }
  const filtered = filters.search || filters.group || filters.level || filters.status;
  return <section className="card students-card"><div className="card-heading students-heading"><div className="students-title"><h2>Ученики</h2><span className="count-pill">{count}</span><span className="muted">Один скилл. Разные пути.</span></div><button className="button export-button" onClick={download} disabled={exporting || loading}><Download size={15} />{exporting ? 'Выгружаем…' : 'Экспорт CSV'}</button></div><div className="table-toolbar"><label className="search-field"><Search size={17} /><input aria-label="Поиск учеников" placeholder="Поиск по имени или email…" value={search} onChange={e => setSearch(e.target.value)} /><kbd>⌕</kbd></label><div className="filter-controls"><select aria-label="Фильтр по группе" value={filters.group} onChange={e => update('group', e.target.value)}><option value="">Все группы</option>{groups.map(g => <option key={g}>{g}</option>)}<option value="__none">Без группы</option></select><select aria-label="Фильтр по уровню" value={filters.level} onChange={e => update('level', e.target.value)}><option value="">Все уровни</option>{LEVELS.map((l, i) => <option key={l} value={String(i)}>{i} · {l}</option>)}<option value="none">Без оценки</option></select><button className={`button filter-button ${more ? 'pressed' : ''}`} aria-expanded={more} onClick={() => setMore(v => !v)}><SlidersHorizontal size={16} /><span>Фильтры</span>{filters.status && <i className="dot purple" />}</button></div></div>
    {more && <div className="extra-filters"><label>Активность<select aria-label="Фильтр по активности" value={filters.status} onChange={e => update('status', e.target.value)}><option value="">Любая</option><option value="active">Были за последние 7 дней</option><option value="inactive">Не были больше 7 дней</option></select></label><label>Сортировка<select aria-label="Сортировка учеников" value={filters.sort} onChange={e => update('sort', e.target.value)}><option value="last_seen">Сначала активные</option><option value="first_seen">Сначала новые</option><option value="prompt_count">По числу промптов</option><option value="level">По уровню ИИ</option></select></label>{filtered && <button className="text-button" onClick={() => { setFilters(initialFilters); setSearch(''); setPage(0); }}>Сбросить фильтры</button>}</div>}
    {error ? <ErrorBox error={error} retry={() => setRetry(v => v + 1)} /> : <div className={`table-scroll ${loading ? 'table-loading' : ''}`} aria-busy={loading}><table><thead><tr><th>Ученик</th><th>Группа</th><th>Уровень ИИ <button className="sort-button" aria-label="Сортировать по уровню" onClick={() => update('sort', 'level')}>↕</button></th><th>Промпты <button className="sort-button" aria-label="Сортировать по числу промптов" onClick={() => update('sort', 'prompt_count')}>↕</button></th><th>Последняя активность</th><th><span className="sr-only">Открыть</span></th></tr></thead><tbody>{rows.map(s => <tr key={s.id}><td><button className="student-button" onClick={() => onSelect(s.id)}><Avatar name={nameOf(s)} /><span><b>{nameOf(s)}</b><small>{emailOf(s)}</small></span></button></td><td><span className={`group-badge ${!s.group_name ? 'no-group' : ''}`}>{s.group_name || 'Без группы'}</span></td><td><LevelBadge level={s.level} /></td><td className="prompt-count">{formatNumber(s.prompt_count)}</td><td><span className="last-seen"><i className={`dot ${isActive(s) ? 'green' : 'gray'}`} />{relativeDate(s.last_seen)}</span></td><td><button className="icon-button row-arrow" aria-label={`Открыть профиль: ${nameOf(s)}`} onClick={() => onSelect(s.id)}><ArrowUpRight size={17} /></button></td></tr>)}</tbody></table>{!rows.length && (loading ? <div className="loading">Загружаем учеников…</div> : <Empty title={filtered ? 'Ученики не найдены' : 'Первые ученики скоро появятся'}>{filtered ? 'Попробуйте изменить запрос или сбросить фильтры.' : 'Записи появятся после согласия ученика и первой отправки данных скиллом.'}</Empty>)}</div>}
    <Pagination page={page} count={count} size={PAGE_SIZE} onChange={setPage} />
    <div className="table-footnote"><span className="dot green" /> Активность — за последние 7 дней. Один ученик на нескольких устройствах может иметь несколько записей.</div>
  </section>;
}

function PromptFeed({ refresh, onSelect }: { refresh: number; onSelect: (id: string) => void }) {
  const [rows, setRows] = useState<Prompt[]>([]); const [page, setPage] = useState(0); const [count, setCount] = useState(0);
  const [error, setError] = useState(''); const [loading, setLoading] = useState(true); const [retry, setRetry] = useState(0);
  useEffect(() => { let alive = true; setLoading(true); setError(''); getHistory('prompts', null, page).then(r => { if (alive) { setRows(r.rows); setCount(r.count); } }).catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setLoading(false); }); return () => { alive = false; }; }, [page, refresh, retry]);
  return <section className="card feed-card"><div className="card-heading"><div><h2>Что спрашивают ученики <span className="count-pill">{formatNumber(count)}</span></h2><p>Последние сообщения из всех проектов</p></div><MessageSquare size={21} /></div>{error ? <ErrorBox error={error} retry={() => setRetry(v => v + 1)} /> : loading ? <div className="loading">Загружаем промпты…</div> : <div className="feed-list">{rows.length ? rows.map(p => <PromptCard key={p.id} prompt={p} onStudent={onSelect} />) : <Empty title="Промптов пока нет" />}</div>}<Pagination page={page} count={count} size={20} onChange={setPage} /></section>;
}

function Setup() {
  return <div className="setup-grid"><section className="card setup-card"><span className="setup-symbol"><Database size={26} /></span><h2>{demo ? 'Подключите свою школу' : 'База данных подключена'}</h2><p>{demo ? 'Сейчас кабинет показывает пример работы. Для настоящих данных используйте тот же проект Supabase, в который скилл отправляет отчёты.' : 'Кабинет читает данные из вашего проекта Supabase. Доступ к записям проверяется базой для каждого запроса.'}</p><ol className="setup-steps"><li><b>Подготовьте базу</b><p>В SQL Editor проекта Supabase последовательно выполните файлы из <code>backend/supabase/migrations</code>: <code>0001_telemetry.sql</code> и <code>0002_dashboard.sql</code>. Если первый уже применён, повторять его не нужно.</p></li><li><b>Добавьте администратора</b><p>Создайте пользователя с email и паролем в Authentication → Users, затем добавьте его ID в таблицу <code>public.admins</code>.</p><pre>insert into public.admins (user_id, email){'\n'}select id, email from auth.users{'\n'}where email = 'your-email@example.com';</pre></li><li><b>Укажите подключение дашборду</b><p>Скопируйте <code>dashboard/.env.example</code> в <code>dashboard/.env.local</code> и заполните URL проекта и публичный anon / publishable ключ.</p><pre>VITE_SUPABASE_URL=https://PROJECT.supabase.co{'\n'}VITE_SUPABASE_ANON_KEY=PUBLIC_KEY</pre><p>Перезапустите приложение. Для публикации задайте эти переменные перед сборкой.</p></li><li><b>Подключите скилл к той же базе</b><p>В <code>skills/arslanbek-ai-mentor/telemetry.conf</code> заполните <code>SUPABASE_URL</code> и <code>SUPABASE_ANON_KEY</code>. Убедитесь, что ученики получили обновлённый конфиг и установили хуки скилла.</p></li></ol><a className="button" href="https://supabase.com/dashboard" target="_blank" rel="noreferrer">Открыть Supabase <ExternalLink size={15} /></a></section><div><section className="card setup-side"><ShieldCheck size={23} /><h3>Доступ под контролем</h3><p>Просматривать данные могут только вошедшие пользователи из таблицы администраторов.</p><p>В браузере используется публичный ключ. Ключ <code>service_role</code> здесь не нужен и не должен попадать в настройки приложения.</p></section><section className="card setup-side"><BookOpen size={23} /><h3>Какие данные появятся</h3><ul><li>Имя и email из Claude и Git</li><li>Устройство и операционная система</li><li>Промпты, проекты и сессии</li><li>Уровень ИИ, сильные стороны и трудности</li><li>Профиль и следующий шаг обучения</li></ul><p>Данные поступают только после согласия ученика. Список скачиваний скилла отдельно не собирается.</p></section></div></div>;
}
