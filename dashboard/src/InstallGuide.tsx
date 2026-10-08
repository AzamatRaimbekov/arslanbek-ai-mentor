import { useEffect, useState, type ReactNode } from 'react';
import { ArrowDown, ArrowRight, BookOpen, Check, CheckCircle2, ChevronRight, Copy, Download, ExternalLink, FolderOpen, GraduationCap, MessageSquare, Monitor, ShieldCheck, Sparkles } from 'lucide-react';
import './install-guide.css';

type Client = 'claude-code' | 'claude-desktop' | 'codex' | 'mcp';
const clients: { id: Client; label: string; note: string }[] = [
  { id: 'claude-code', label: 'Claude Code', note: 'Обычная установка скилла' },
  { id: 'claude-desktop', label: 'Claude Desktop', note: 'Обычный чат · расширение' },
  { id: 'codex', label: 'Codex', note: 'Установка с помощью агента' },
  { id: 'mcp', label: 'Другое приложение', note: 'С поддержкой локального MCP' },
];
const downloadFile = (client: Client) => client === 'claude-desktop' ? 'arslanbek-claude-desktop.mcpb' : client === 'codex' ? 'arslanbek-codex.zip' : 'arslanbek-ai-mentor.zip';
const STATUS_PROMPT = 'Проверь статус отправки данных Arslanbek. Покажи время последней успешной доставки и есть ли записи, ожидающие отправки. Если подключение не работает, помоги исправить причину.';

function DownloadLink({ children = 'Скачать скилл', secondary = false, client = 'claude-code' }: { children?: ReactNode; secondary?: boolean; client?: Client }) {
  return <a className={`guide-button ${secondary ? 'guide-button-light' : 'guide-button-primary'}`} href={`/downloads/${downloadFile(client)}`} download={downloadFile(client)}><Download size={18} />{children}</a>;
}

function CopyBlock({ text, label }: { text: string; label: string }) {
  const [status, setStatus] = useState<'idle' | 'copied' | 'failed'>('idle');
  useEffect(() => { setStatus('idle'); }, [text]);
  useEffect(() => {
    if (status === 'idle') return;
    const timer = setTimeout(() => setStatus('idle'), 5000);
    return () => clearTimeout(timer);
  }, [status]);
  async function copy() {
    try { await navigator.clipboard.writeText(text); setStatus('copied'); }
    catch { setStatus('failed'); }
  }
  return <div className="guide-copy-block">
    <div className="guide-copy-heading"><span>{label}</span><button type="button" onClick={copy} aria-label={`Скопировать: ${label}`}>{status === 'copied' ? <Check size={15} /> : <Copy size={15} />}{status === 'copied' ? 'Скопировано' : 'Скопировать'}</button></div>
    <pre>{text}</pre>
    <span className={status === 'failed' ? 'guide-copy-error' : 'sr-only'} role="status">{status === 'copied' ? 'Текст скопирован. Вставьте его в своё приложение.' : status === 'failed' ? 'Браузер не разрешил копирование. Выделите текст выше и скопируйте его вручную.' : ''}</span>
  </div>;
}

function Step({ number, title, children }: { number: number; title: string; children: ReactNode }) {
  return <section className="guide-step"><span className="guide-step-number" aria-hidden="true">{String(number).padStart(2, '0')}</span><div className="guide-step-body"><h3>{title}</h3>{children}</div></section>;
}

export default function InstallGuide() {
  const [client, setClient] = useState<Client>('claude-code');
  const [os, setOs] = useState('mac');
  useEffect(() => {
    document.title = 'Установить Arslanbek — инструкция для учеников';
    document.querySelector('meta[name="description"]')?.setAttribute('content', 'Скачайте скилл Arslanbek и установите его по пошаговой инструкции для Claude Code, Codex и приложений с MCP.');
  }, []);
  const selected = clients.find(item => item.id === client)!;
  const skillHome = client === 'claude-code' ? '~/.claude' : client === 'codex' ? '~/.agents' : '~/.arslanbek/mcp';
  const firstPrompt = `${client === 'claude-code' ? '/arslanbek-ai-mentor\n\n' : client === 'codex' ? '$arslanbek-ai-mentor\n\n' : 'Используй Arslanbek для моей задачи.\n\n'}Меня зовут [ваше имя], мой email — [ваш email]. Я учусь в школе Arslanbek. Сохрани эти сведения в моём профиле ученика.\n\nМоя задача: [что вы хотите сделать]. Помоги мне разобраться и выполнить её по шагам.`;
  const installerPrompt = `Установи школьный скилл Arslanbek из этой распакованной папки. Выполни python3 install.py --client ${client}. На Windows вместо python3 используй runtime/windows-x64/python.exe или runtime/windows-arm64/python.exe внутри папки скилла; на macOS/Linux проверь Python 3.10+. Сохрани мой личный профиль, уроки и существующие настройки. Покажи результат установки и следующие действия в приложении.`;
  const updatePrompt = `Обнови школьный скилл Arslanbek из этой распакованной папки. Выполни python3 install.py --client ${client} --setup-only. На Windows вместо python3 используй Python из папки runtime пакета для своей архитектуры. Сохрани мой личный профиль, уроки, существующие настройки и прежний выбор передачи данных. Проверь результат обновления.`;

  return <div className="install-guide">
    <a className="guide-skip" href="#instructions">Перейти к инструкции</a>
    <header className="guide-header"><div className="guide-container guide-header-inner">
      <a className="brand guide-brand" href="/install" aria-label="Arslanbek — установка скилла"><span className="brand-mark">a<span>.</span></span><div>arslanbek<span>AI MENTOR</span></div></a>
      <nav aria-label="Навигация по инструкции"><a href="#faq">Помощь</a><a className="guide-mentor-link" href="/">Кабинет наставника <ArrowRight size={15} /></a></nav>
    </div></header>

    <main className="guide-container guide-main">
      <section className="guide-hero" aria-labelledby="guide-title">
        <div className="guide-hero-content">
          <span className="guide-eyebrow"><GraduationCap size={16} /> ДЛЯ УЧЕНИКОВ ШКОЛЫ ARSLANBEK</span>
          <h1 id="guide-title">Установите Arslanbek<span>.</span><br />Начните создавать.</h1>
          <p>Ваш наставник по работе с ИИ — прямо в привычном приложении. Поможет разобраться в задаче, проверить решение и увидеть следующий шаг.</p>
          <div className="guide-hero-actions"><DownloadLink client={client} /><a className="guide-button guide-button-light" href="#instructions">Как установить <ArrowDown size={17} /></a></div>
          <div className="guide-download-note"><CheckCircle2 size={15} /> {client === 'claude-desktop' ? 'Расширение Claude Desktop' : 'ZIP со скиллом'} · адрес школы уже настроен</div>
        </div>
        <div className="guide-hero-card">
          <div className="guide-hero-card-top"><span className="guide-spark"><Sparkles size={23} /></span><span>ОДИН СКИЛЛ<br /><b>Поддержка на каждом шаге</b></span></div>
          <div className="guide-benefit"><span><MessageSquare size={19} /></span><div><b>Объясняет понятно</b><p>Связывает решение с вашей задачей.</p></div></div>
          <div className="guide-benefit"><span><BookOpen size={19} /></span><div><b>Помогает учиться</b><p>Замечает навыки и трудности по ходу работы.</p></div></div>
          <div className="guide-benefit"><span><GraduationCap size={19} /></span><div><b>Держит наставника в курсе</b><p>Передаёт школе промпты и сводки прогресса.</p></div></div>
          <div className="guide-hero-card-foot"><ShieldCheck size={15} /> Школьный пакет для участников по договору</div>
        </div>
      </section>

      <ol className="guide-flow" aria-label="Порядок установки">
        <li><span>1</span><div><b>Скачайте</b><small>{client === 'claude-desktop' ? 'Расширение для Claude' : 'И распакуйте архив'}</small></div><ChevronRight size={19} /></li>
        <li><span>2</span><div><b>Установите</b><small>В своё приложение</small></div><ChevronRight size={19} /></li>
        <li><span>3</span><div><b>Начните работу</b><small>Познакомьтесь с наставником</small></div><CheckCircle2 size={19} /></li>
      </ol>

      <section id="instructions" className="guide-instructions" aria-labelledby="instructions-title">
        <div className="guide-section-heading"><span className="guide-eyebrow">ПОШАГОВАЯ ИНСТРУКЦИЯ</span><h2 id="instructions-title">В каком приложении вы работаете?</h2><p>Выберите его — ниже появятся нужные шаги.</p></div>
        <div className="guide-client-picker" role="group" aria-label="Приложение для установки">{clients.map(item => <button type="button" key={item.id} aria-pressed={client === item.id} aria-controls="client-instructions" onClick={() => setClient(item.id)}><span className="guide-client-icon">{item.id === 'claude-code' ? <Sparkles size={21} /> : item.id === 'codex' ? <Monitor size={21} /> : <FolderOpen size={21} />}</span><span><b>{item.label}</b><small>{item.note}</small></span><span className="guide-client-check">{client === item.id && <Check size={14} />}</span></button>)}</div>

        <div className="guide-instruction-layout">
          <div id="client-instructions" className="guide-steps" key={client}>
            <Step number={1} title={client === 'claude-desktop' ? 'Скачайте расширение' : 'Скачайте и распакуйте архив'}>
              <p>{client === 'claude-desktop' ? <>Скачайте <code>{downloadFile(client)}</code>. Этот файл устанавливается прямо в Claude, распаковывать его не нужно.</> : <>Нажмите «Скачать скилл» и полностью распакуйте файл <code>{downloadFile(client)}</code>. Откройте полученную папку.</>}</p>
              {client !== 'claude-desktop' && <div className="guide-archive"><FolderOpen size={20} /><div><b>Что должно быть внутри</b><p>Папка <code>arslanbek-ai-mentor</code>, файл <code>install.py</code> и инструкция <code>START_HERE.txt</code>.</p></div></div>}
              <DownloadLink client={client} secondary />
            </Step>
            <Step number={2} title={client === 'claude-desktop' ? 'Добавьте расширение в Claude' : client === 'claude-code' ? 'Добавьте папку в Claude Code' : client === 'codex' ? 'Поручите установку Codex' : 'Подключите скилл к своему приложению'}>
              {client === 'claude-desktop' ? <><p>В Claude откройте <b>Settings → Extensions → Advanced settings → Install Extension</b> и выберите скачанный файл. Подтвердите установку расширения.</p><p>Claude сам подготовит среду и запустит подключение. Терминал, ручной запуск скриптов и отдельная установка Python не нужны. При первом запуске нужен интернет.</p><p>Используйте актуальный Claude Desktop с поддержкой MCPB 0.4/UV. Если приложение сообщает о неподдерживаемом формате, сначала обновите его.</p></> : client === 'claude-code' ? <>
                <p>Поместите папку <code>arslanbek-ai-mentor</code> из архива в папку личных скиллов Claude Code. Переносите папку целиком, вместе со всеми файлами.</p>
                <CopyBlock label="Куда поместить папку" text="~/.claude/skills/" />
                <p>Если папки <code>skills</code> ещё нет, создайте её. После установки файл скилла должен находиться по этому адресу:</p>
                <pre className="guide-file-path">~/.claude/skills/arslanbek-ai-mentor/SKILL.md</pre>
                <label className="guide-os-label">Ваш компьютер<select aria-label="Ваш компьютер" value={os} onChange={e => setOs(e.target.value)}><option value="mac">macOS</option><option value="linux">Linux</option><option value="windows">Windows</option></select></label>
                <p className="guide-small">{os === 'mac' ? <>В Finder нажмите <kbd>⌘</kbd> + <kbd>Shift</kbd> + <kbd>G</kbd>, вставьте <code>~/.claude/</code> и откройте или создайте папку <code>skills</code>.</> : os === 'linux' ? <>В файловом менеджере откройте домашнюю папку и включите показ скрытых файлов. Откройте <code>.claude</code>, затем папку <code>skills</code>.</> : <>В Проводнике откройте <code>%USERPROFILE%\.claude\skills</code>. Скопируйте туда папку скилла. Для вкладки Code в Claude Desktop используется та же папка. В WSL скилл устанавливается отдельно в домашнюю папку WSL.</>}</p>
                <div className="guide-tip"><CheckCircle2 size={17} /><p>Это обычная установка скилла. Подключение отчётов произойдёт при первом использовании.</p></div>
                <details className="guide-details"><summary>Можно поручить установку агенту</summary><p>Откройте распакованную папку в Claude Code или сообщите ему полный путь к ней. Затем отправьте:</p><CopyBlock label="Сообщение для установки" text="Установи школьный скилл Arslanbek из этой распакованной папки как обычный скилл в ~/.claude/skills/arslanbek-ai-mentor. На Windows вместо python3 используй runtime/windows-x64/python.exe или runtime/windows-arm64/python.exe внутри папки скилла; на macOS/Linux проверь Python 3.10+. Если Arslanbek уже установлен, сохрани мой личный профиль, уроки и прежний выбор передачи данных." /></details>
              </> : <>
                {client === 'codex' && <p>Можно просто поместить папку скилла в <code>~/.agents/skills/</code>, на Windows — <code>%USERPROFILE%\.agents\skills</code>, затем вызвать <code>$arslanbek-ai-mentor</code>. Агент подключит отчёты сам. Ниже — альтернативная установка с его помощью.</p>}
                <p>Откройте распакованную папку в {client === 'codex' ? 'Codex' : 'приложении с агентом'} или сообщите агенту полный путь к ней. Скопируйте сообщение ниже и отправьте ему:</p>
                <CopyBlock label="Сообщение для установки" text={installerPrompt} />
                <p>{client === 'codex' ? <>Агент установит скилл в <code>~/.agents/skills/arslanbek-ai-mentor</code> и настроит подключение школы.</> : <>После установки агент создаст файл <code>mcp.json</code>. Добавьте это подключение в настройки MCP своего приложения, а установленный <code>SKILL.md</code> — в его инструкции.</>}</p>
                {client === 'mcp' && <div className="guide-tip"><Monitor size={17} /><p><b>MCP</b> — подключение инструментов к вашему ИИ-приложению. Для этого пакета требуется поддержка локального MCP. Модель может быть любой, в том числе DeepSeek.</p></div>}
              </>}
            </Step>
            <Step number={3} title="Начните новую сессию и представьтесь">
              <p>Откройте свой рабочий проект и начните новую сессию {selected.label === 'Другое приложение' ? 'в приложении' : selected.label}. Скопируйте сообщение, замените поля в квадратных скобках и отправьте:</p>
              <CopyBlock label="Первое сообщение наставнику" text={firstPrompt} />
              {client === 'codex' && <div className="guide-tip guide-tip-amber"><ShieldCheck size={17} /><p>Для автоматической передачи запросов Codex требует один раз просмотреть и доверить хуки Arslanbek — действия, которые запускаются при событиях сессии. В CLI откройте <code>/hooks</code>. Это настройка самого Codex. <a href="https://learn.chatgpt.com/docs/hooks" target="_blank" rel="noreferrer">Официальная инструкция <ExternalLink size={12} /></a></p></div>}
              <p>{client === 'claude-code' ? 'Наставник подключит отчёты школы при загрузке скилла. Автоматическая отправка запросов через хуки начнётся со следующей сессии; в первой сессии текущие запросы и сводки передаёт сам агент.' : client === 'codex' ? 'После установки и доверия хукам новые запросы передаются автоматически. Сводку по выполненной задаче составляет агент в вашей рабочей сессии.' : <>Попросите агента вызвать <code>arslanbek_status</code>. Текущие запросы он передаёт через <code>arslanbek_record_prompt</code>, сводки — через <code>arslanbek_submit_progress</code>. В приложении без хуков полнота передачи зависит от вызова инструментов агентом.</>}</p>
            </Step>
            <Step number={4} title="Проверьте, что подключение работает">
              <p>Отправьте наставнику короткую задачу, а после её выполнения попросите проверить доставку:</p>
              <CopyBlock label="Проверка подключения" text={STATUS_PROMPT} />
              <p>Подтверждение — время <b>последней успешной доставки</b>. После первой успешной передачи школа увидит вашу запись в кабинете; сводка появится после содержательной работы над задачей.</p>
              <div className="guide-tip"><CheckCircle2 size={17} /><p>Дальше работайте в своём приложении. Промпты и сводки поступают наставнику по ходу работы.</p></div>
            </Step>
          </div>

          <aside className="guide-aside" aria-label="Перед установкой">
            <section className="guide-side-card"><span className="guide-side-icon"><CheckCircle2 size={21} /></span><h3>Что нужно заранее</h3><ul><li>Установленное приложение: {selected.label === 'Другое приложение' ? 'с поддержкой локального MCP' : selected.label}.</li><li>{client === 'claude-desktop' ? 'Актуальный Claude Desktop с поддержкой MCPB 0.4/UV.' : 'В Windows Python уже внутри пакета. Для macOS/Linux нужен Python 3.10+.'}</li><li>Интернет для доставки отчётов.</li></ul><p>Нативные Windows-приложения работают без WSL. Вкладка Code в Claude Desktop использует вариант Claude Code; обычный чат — расширение Claude Desktop.</p><a href={client === 'claude-desktop' ? 'https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop' : client === 'codex' ? 'https://learn.chatgpt.com/docs/build-skills' : client === 'claude-code' ? 'https://code.claude.com/docs/en/skills' : 'https://modelcontextprotocol.io/docs/getting-started/intro'} target="_blank" rel="noreferrer">Документация {client === 'mcp' ? 'MCP' : selected.label} <ExternalLink size={13} /></a></section>
            <section className="guide-side-card guide-school-note"><ShieldCheck size={21} /><h3>Подключение школы</h3><p>Этот пакет предназначен ученикам после оформления договора со школой. Передача промптов и сводок подключается при первом использовании скилла.</p><p>Адрес школы уже указан в пакете. Вводить ключи или пароль кабинета наставника не требуется.</p><a href="#reporting">Какие данные передаются <ArrowDown size={13} /></a></section>
          </aside>
        </div>
      </section>

      <section id="reporting" className="guide-reporting" aria-labelledby="reporting-title">
        <div><span className="guide-eyebrow"><ShieldCheck size={15} /> ПОНЯТНОЕ ПОДКЛЮЧЕНИЕ</span><h2 id="reporting-title">Как наставник видит ваш прогресс</h2><p>Данные доступны администраторам школы. Сводку составляет агент, с которым вы работаете.</p></div>
        <div className="guide-reporting-body"><ul><li><b>Промпты и проекты.</b> Тексты запросов, псевдонимы проектов и сессий. В Codex и Claude Code после подключения работают хуки. В обычном чате Claude Desktop и других MCP-приложениях отправляются только сообщения, для которых агент вызвал инструмент; полного журнала всех сообщений нет.</li><li><b>Рабочие инструменты и защита данных.</b> Теги запросов, названия доступных и применённых скиллов, плагинов и MCP, наличие инструкций, хуков и проверок проекта. Признаки чувствительных данных проверяются локально; школе передаются категории и количество совпадений. Команды, аргументы, результаты инструментов и фрагменты секретов в эти метаданные не входят.</li><li><b>Сводки работы.</b> Задача, результат, проверки, трудности, наблюдения по навыкам и следующий шаг.</li><li><b>Профиль и устройство.</b> Учебные наблюдения и псевдоним участника. В обновлённом скилле имена, email, телефоны и сведения об устройстве заменяются локально перед отправкой в школу.</li></ul><p>Таблица обратных замен остаётся на компьютере. Типовые ключи и пароли удаляются без восстановления. Очистка отчёта школе не изменяет исходные сообщения, которые ваше приложение отправляет своей ИИ-модели. Произвольные личные сведения в свободном тексте автоматическое распознавание может пропустить.</p><p>История до подключения, ответы агента и исходные файлы проектов не загружаются. Ранее сохранённое отключение передачи сохраняется при обновлении.</p><details className="guide-details"><summary>Как остановить передачу данных</summary><p>{client === 'claude-desktop' ? 'Выключите передачу в настройках расширения. Новые события и доставка очереди остановятся.' : 'Попросите агента выполнить эту команду для выбранного приложения. Сбор остановится, а неотправленная очередь очистится.'}</p>{client === 'claude-desktop' ? <p>Откройте настройки расширения Arslanbek и выключите «Передавать учебные данные школе», либо отключите расширение целиком.</p> : <CopyBlock label="Сообщение для отключения" text={`Отключи отправку данных Arslanbek для ${selected.label}. Выполни python3 ${skillHome}/skills/arslanbek-ai-mentor/scripts/telemetry.py consent no, используя Python из папки runtime установленного скилла на Windows. Проверь статус.`} />}<p>Уже доставленные записи автоматически не удаляются. По ним обратитесь к наставнику школы.</p></details></div>
      </section>

      <section id="faq" className="guide-faq" aria-labelledby="faq-title">
        <div className="guide-section-heading"><span className="guide-eyebrow">ЕСЛИ НУЖНА ПОМОЩЬ</span><h2 id="faq-title">Ответы на частые вопросы</h2></div>
        <div className="guide-faq-list">
          <details><summary>Скилл уже установлен. Как обновить?</summary><div><p>{client === 'claude-desktop' ? 'Скачайте свежее расширение.' : <>Скачайте и распакуйте свежий архив. Откройте полученную папку в своём приложении и отправьте агенту сообщение ниже. Оно относится к выбранному выше приложению: {selected.label}.</>}</p>{client === 'claude-desktop' ? <p>Установите новый файл .mcpb через настройки расширений Claude.</p> : <CopyBlock label="Сообщение для обновления" text={updatePrompt} />}<p>Установщик сохранит личный профиль, уроки, настройки и прежний выбор передачи данных.</p></div></details>
          <details><summary>Приложение не видит Arslanbek</summary><div><p>Начните новую сессию или перезапустите приложение. Для Claude Code проверьте адрес <code>~/.claude/skills/arslanbek-ai-mentor/SKILL.md</code>, для Codex — <code>~/.agents/skills/arslanbek-ai-mentor/SKILL.md</code>. Файл должен лежать прямо в папке скилла. Если после распаковки появилась ещё одна папка с тем же именем, перенесите внутреннюю папку.</p><p>В приложении с MCP проверьте подключение из <code>mcp.json</code> и наличие текста <code>SKILL.md</code> в инструкциях агента.</p></div></details>
          <details><summary>Наставник пока не видит мои данные</summary><div><p>Скачивание само по себе не создаёт запись. Скилл должен запуститься и успешно передать данные. Попросите агента проверить статус подключения по сообщению в шаге 4. В Codex также проверьте доверие хукам.</p><p>Если сети не было, события остаются в очереди. Повторная отправка происходит при следующем запросе, сводке или запуске сессии. Пустая очередь без времени успешной доставки ещё не подтверждает подключение.</p></div></details>
          <details><summary>Можно установить в ChatGPT, Claude в браузере или DeepSeek?</summary><div><p>Эта инструкция рассчитана на приложения, которые работают с локальными файлами и выполняют команды или поддерживают локальный MCP. В обычном браузерном чате без этих интеграций данный пакет автоматически данные не передаёт.</p><p>DeepSeek можно использовать как модель в совместимом приложении. Выберите выше «Другое приложение» и следуйте инструкции для MCP.</p></div></details>
          <details><summary>Нужно ли регистрироваться на этом сайте?</summary><div><p>Для скачивания и установки вход на этот сайт не требуется. В первом сообщении представьтесь наставнику и укажите свой email. Кабинет с данными предназначен администраторам школы.</p></div></details>
        </div>
      </section>

      <section className="guide-final-cta"><div><span className="guide-eyebrow">ВАШ СЛЕДУЮЩИЙ ШАГ</span><h2>Начните с первой задачи.</h2><p>Скачайте скилл, установите его и познакомьтесь с наставником.</p></div><DownloadLink client={client} /></section>
    </main>
    <footer className="guide-footer"><div className="guide-container"><span>Arslanbek · AI Mentor</span><span>Инструкция для учеников школы</span><a href="#guide-title">Наверх <ArrowRight size={14} /></a></div></footer>
  </div>;
}
