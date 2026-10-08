import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { PGlite } from '@electric-sql/pglite';

const db = new PGlite();
const admin = randomUUID(), other = randomUUID(), device = randomUUID(), secret = 'x'.repeat(64);
let student;
const example = JSON.parse(await readFile(new URL('../../skills/arslanbek-ai-mentor/references/progress-example.json', import.meta.url)));
async function role(name, id = '') { await db.exec('reset role'); await db.query("select set_config('request.jwt.claim.sub',$1,false)",[id]); await db.exec(`set role ${name}`); }
const observation = { version: 1, tags: ['backend','intent:learn'], tag_source: 'keyword_rules', privacy_signals: [{ category: 'api_key', severity: 'critical', count: 1 }] };
async function ingest(prompts = [], summary = null, identity = {}) { return (await db.query('select public.ingest($1,$2,$3,$4,$5) as r',[device,secret,identity,prompts,summary])).rows[0].r; }
function report(goal, extras = {}) { return { ...structuredClone(example), goal, learning_evidence: [{ competency_id: 'prompt_engineering', state: 'demonstrated', actor: 'learner', evidence_type: 'learner_explanation', evidence: 'Ученик объяснил цель и проверяемый результат', next_action: 'Повторить на новой задаче' }], ...extras }; }
before(async () => {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls; create schema auth; create table auth.users(id uuid primary key,email text); create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$; grant usage on schema public,auth to anon,authenticated;`);
  await db.query('insert into auth.users values($1,$2),($3,$4)',[admin,'mentor@example.test',other,'other@example.test']);
  for (const file of ['0001_telemetry.sql','0002_dashboard.sql','0003_reliable_telemetry.sql','0004_team_analysis.sql','0005_multiclient_progress.sql','0006_student_observability.sql']) await db.exec(await readFile(new URL('../../backend/supabase/migrations/'+file,import.meta.url),'utf8'));
  await db.query('insert into public.admins values($1,$2)',[admin,'mentor@example.test']);
  await role('anon'); await ingest(); await role('postgres'); student=(await db.query('select id from public.students where device_id=$1',[device])).rows[0].id;
});
after(async () => db.close());

test('v1 ingestion remains compatible; observation metadata creates one alert and retries cannot rewrite it', async () => {
  await role('anon');
  await ingest([{event_id:randomUUID(),prompt:'Old client without metadata'}],{event_id:randomUUID(),summary:'Old summary'});
  const event={event_id:randomUUID(),prompt:'Explain backend. [SECRET_REMOVED]',observability:observation};
  assert.equal((await ingest([event])).prompts,1);
  assert.equal((await ingest([{...event,observability:{...observation,privacy_signals:[]}}])).prompts,0);
  await role('authenticated',admin);
  const alert=(await db.query('select * from public.security_alerts')).rows;
  assert.equal(alert.length,1); assert.equal(alert[0].category,'api_key');
  const stored=(await db.query('select observability from public.prompts where event_id=$1',[event.event_id])).rows[0].observability;
  assert.equal(stored.privacy_signals.length,1);
  assert.equal(JSON.stringify(alert).includes('SECRET_REMOVED'),false);
});
test('skill development uses independent evidence across distinct tasks, not repeated reports or agent work', async () => {
  await role('anon');
  for (const goal of ['Goal A','Goal A','Goal B']) { const r=report(goal); await ingest([],{event_id:randomUUID(),summary:r.result,report:r}); }
  const invalid=report('Agent task'); invalid.learning_evidence[0].actor='agent';
  await assert.rejects(ingest([],{event_id:randomUUID(),summary:invalid.result,report:invalid}),/observed learner actions/);
  await role('authenticated',admin);
  const data=(await db.query('select public.student_observability($1,30) as r',[student])).rows[0].r;
  assert.equal(data.skills[0].independent_tasks,2); assert.equal(data.skills[0].tasks,3);
  assert.equal(data.evidence.length,3);
  await assert.rejects(db.query('select public.student_observability($1,999)',[student]),/Period must/);
});
test('tool hooks and mentor creation reports retain source and actor; duplicates do not inflate usage', async () => {
  await role('anon');
  const event={event_id:randomUUID(),tool_id:'mcp__docs__search',kind:'mcp',action:'used',actor:'agent',source:'tool_hook',client:'codex'};
  await ingest([],null,{tool_event:event}); await ingest([],null,{tool_event:event});
  await assert.rejects(ingest([],null,{tool_event:{...event,tool_input:'private source'}}),/invalid tool event/);
  const r=report('Create a reusable skill',{tool_usage:[{kind:'skill',tool_id:'test-skill',action:'created',actor:'together',evidence:'Проверен SKILL.md на тестовом запросе'}]});
  const summary={event_id:randomUUID(),summary:r.result,report:r}; await ingest([],summary); await ingest([],summary);
  await role('authenticated',admin);
  const events=(await db.query('select * from public.tool_events')).rows;
  assert.equal(events.length,2); assert.equal(events.find(e=>e.source==='tool_hook').actor,'agent');
  assert.equal(events.find(e=>e.action==='created').actor,'together');
});
test('metadata validation is atomic and cannot store secret values in alert or environment fields', async () => {
  await role('anon');
  const before=(await ingest()).prompts;
  for (const obs of [{}, {...observation,privacy_signals:[{...observation.privacy_signals[0],value:'a-secret'}]}, {...observation,tags:['uncontrolled-tag']}]) {
    await assert.rejects(ingest([{event_id:randomUUID(),prompt:'Malformed metadata',observability:obs}]),/invalid/);
  }
  await assert.rejects(ingest([],null,{environment:{version:1,client:'codex',tools:[],harness:[],truncated:false,coverage:'project_only',credentials:'secret'}}),/invalid environment/);
  assert.equal(before,0);
  await role('authenticated',admin);
  assert.equal((await db.query("select count(*)::int n from public.prompts where prompt='Malformed metadata'")).rows[0].n,0);
});
test('only administrators can read observations or review alerts; review retains an audit record', async () => {
  await role('authenticated',other);
  assert.equal((await db.query('select * from public.security_alerts')).rows.length,0);
  assert.equal((await db.query('select * from public.tool_events')).rows.length,0);
  await assert.rejects(db.query('select public.student_observability($1,30)',[student]),/Administrator/);
  await assert.rejects(db.query("select public.review_security_alert(1,'reviewed')"),/Administrator/);
  await role('anon'); await assert.rejects(db.query('select public.ingest_v5($1,$2)',[device,secret]),/permission denied/);
  await role('authenticated',admin);
  const id=(await db.query('select id from public.security_alerts limit 1')).rows[0].id;
  await assert.rejects(db.query("update public.security_alerts set status='reviewed'"),/permission denied/);
  await db.query("select public.review_security_alert($1,'false_positive')",[id]);
  const alert=(await db.query('select * from public.security_alerts where id=$1',[id])).rows[0];
  assert.equal(alert.reviewed_by,admin); assert.ok(alert.reviewed_at);
  assert.equal((await db.query('select public.security_alert_counts() r')).rows[0].r.open,0);
});
test('aggregates include more than 1000 events while evidence and tool history stay bounded', async () => {
  await role('anon');
  for(let i=0;i<6;i++) await ingest(Array.from({length:200},()=>({event_id:randomUUID(),prompt:'Build backend',observability:{...observation,privacy_signals:[]}})));
  for(let i=0;i<12;i++) { const r=report('Extra goal '+i); await ingest([],{event_id:randomUUID(),summary:r.result,report:r}); }
  await role('authenticated',admin);
  const data=(await db.query('select public.student_observability($1,30) r',[student])).rows[0].r;
  assert.equal(data.metrics.prompts,1202); assert.equal(data.tags.find(t=>t.tag==='backend').count,1201);
  assert.equal(data.skills[0].tasks,16); assert.equal(data.evidence.length,8);
  assert.equal(data.skills[0].independent_tasks,15);
});

test('sensitive tool signals retain the tool source, contain no content and stay idempotent', async () => {
  await role('anon');
  const event={event_id:randomUUID(),tool_id:'Read',kind:'tool',action:'used',actor:'agent',source:'tool_hook',client:'claude-code',privacy_signals:[{category:'private_key',severity:'critical',count:1}]};
  await ingest([],null,{tool_event:event}); await ingest([],null,{tool_event:event});
  await role('authenticated',admin);
  const alerts=(await db.query('select * from public.security_alerts where tool_event_id is not null')).rows;
  assert.equal(alerts.length,1); assert.equal(alerts[0].prompt_id,null); assert.equal(alerts[0].category,'private_key');
  assert.equal((await db.query('select public.security_alert_counts() r')).rows[0].r.open,1);
});
