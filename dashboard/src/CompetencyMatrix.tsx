import { ArrowUpRight, Blocks, BrainCircuit, Braces, Code2, Database, FlaskConical, Layers3, MessageSquareText, Puzzle, Rocket, ShieldCheck, Workflow, type LucideIcon } from 'lucide-react';
import { COMPETENCIES, skillState, stateName, type CompetencyId, type SkillStats } from './observability';
import './competency-matrix.css';

const groups: { title: string; note: string; ids: CompetencyId[] }[] = [
  { title: 'Работа с ИИ', note: 'Задачи, контекст и управление агентом', ids: ['prompt_engineering', 'context_engineering', 'harness'] },
  { title: 'Инструменты и автоматизация', note: 'Создание собственных способов работы', ids: ['skill_authoring', 'plugin_authoring'] },
  { title: 'Разработка продукта', note: 'От интерфейса до проверки и публикации', ids: ['frontend', 'backend', 'databases', 'testing', 'devops', 'security'] },
];
const icons: Record<CompetencyId, LucideIcon> = { prompt_engineering: MessageSquareText, context_engineering: Layers3, harness: Workflow, skill_authoring: Blocks, plugin_authoring: Puzzle, frontend: Code2, backend: Braces, databases: Database, testing: FlaskConical, devops: Rocket, security: ShieldCheck };
const titles: Record<CompetencyId, string> = { prompt_engineering: 'Промпт-инжиниринг', context_engineering: 'Контекст-инжиниринг', harness: 'Харнес агента', skill_authoring: 'Создание скиллов', plugin_authoring: 'Плагины и MCP', frontend: 'Frontend', backend: 'Backend', databases: 'Базы данных', testing: 'Тестирование', devops: 'DevOps', security: 'Защита данных' };
const states = ['repeated', 'demonstrated', 'practiced', 'needs_practice', 'unknown'] as const;

export default function CompetencyMatrix({ skills, selected, detailId, onSelect }: { skills: SkillStats[]; selected: CompetencyId; detailId: string; onSelect: (id: CompetencyId) => void }) {
  const entries = COMPETENCIES.map(c => ({ ...c, stat: skills.find(s => s.competency_id === c.id), state: skillState(skills.find(s => s.competency_id === c.id)) }));
  const observed = entries.filter(c => c.state !== 'unknown').length;
  const independent = entries.filter(c => c.state === 'demonstrated' || c.state === 'repeated').length;
  const practice = entries.filter(c => c.state === 'needs_practice').length;
  return <section className="learning-map" aria-label="Матрица компетенций">
    <header className="matrix-heading">
      <div className="matrix-heading-icon"><BrainCircuit size={26} aria-hidden="true" /></div>
      <div><span className="matrix-eyebrow">МАТРИЦА КОМПЕТЕНЦИЙ</span><h3>Карта навыков</h3><p>Выберите направление — ниже откроются действия и подтверждения.</p></div>
      <span className="matrix-total">11 направлений</span>
    </header>
    <div className="matrix-summary">
      <div><b>{observed}<span> / 11</span></b><span>С наблюдениями</span></div>
      <div><b>{independent}</b><span>С самостоятельными примерами</span></div>
      <div><b>{practice}</b><span>Требуют практики</span></div>
    </div>
    <div className="matrix-coverage" aria-hidden="true">{states.map(state => {
      const count = entries.filter(c => c.state === state).length;
      return count > 0 && <span key={state} className={`coverage-${state}`} style={{ flex: count }} />;
    })}</div>
    <div className="knowledge-network" role="group" aria-label="Направления развития ученика">
      {groups.map((group, index) => <section className="matrix-group" key={group.title} aria-labelledby={`${detailId}-group-${index}`}>
        <div className="matrix-group-heading"><h4 id={`${detailId}-group-${index}`}>{group.title}</h4><span>{group.note}</span></div>
        <div className={`matrix-grid${group.ids.length === 2 ? ' matrix-grid-pair' : ''}`}>
          {group.ids.map(id => {
            const c = entries.find(entry => entry.id === id)!;
            const Icon = icons[id];
            return <button type="button" key={id} className={`knowledge-node knowledge-${c.state}${selected === id ? ' is-selected' : ''}`} aria-label={`${c.label}: ${stateName(c.state)}`} aria-pressed={selected === id} aria-controls={detailId} onClick={() => onSelect(id)}>
              <span className="matrix-node-heading"><span className="matrix-node-icon"><Icon size={20} aria-hidden="true" /></span><span className="matrix-node-title">{titles[id]}</span><ArrowUpRight className="matrix-node-arrow" size={17} aria-hidden="true" /></span>
              <span className={`matrix-node-state state-${c.state}`}><i aria-hidden="true" />{stateName(c.state)}</span>
              <span className="matrix-node-footer">{c.stat ? <><span>Наблюдений <b>{c.stat.observations}</b></span><span>Самост. задач <b>{c.stat.independent_tasks}</b></span></> : <span>Ожидает первого наблюдения</span>}</span>
            </button>;
          })}
        </div>
      </section>)}
    </div>
    <div className="knowledge-legend">{states.map(state => <span key={state}><i className={`knowledge-dot knowledge-${state}`} />{stateName(state)}</span>)}</div>
    <p className="matrix-footnote">Цвета отражают наблюдения наставника. Повторное подтверждение — самостоятельные действия в разных задачах; окончательную оценку даёт преподаватель.</p>
  </section>;
}
