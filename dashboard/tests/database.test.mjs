import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PGlite } from '@electric-sql/pglite';

const db = new PGlite();
const admin = '00000000-0000-4000-8000-000000000001';
const outsider = '00000000-0000-4000-8000-000000000002';
const device = '00000000-0000-4000-8000-000000000003';
const secret = 'a'.repeat(64);
async function role(name, id = '') {
  await db.exec('reset role');
  await db.query("select set_config('request.jwt.claim.sub', $1, false)", [id]);
  await db.exec(`set role ${name}`);
}
before(async () => {
  await db.exec(`
    create role anon; create role authenticated; create role service_role bypassrls;
    create schema auth;
    create table auth.users (id uuid primary key, email text);
    create function auth.uid() returns uuid language sql stable as $$
      select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
    $$;
    grant usage on schema public, auth to anon, authenticated;
    insert into auth.users values ('${admin}', 'mentor@example.com'), ('${outsider}', 'other@example.com');
  `);
  for (const filename of ['0001_telemetry.sql', '0002_dashboard.sql', '0003_reliable_telemetry.sql', '0004_team_analysis.sql', '0005_multiclient_progress.sql', '0006_student_observability.sql']) {
    await db.exec(await readFile(new URL(`../../backend/supabase/migrations/${filename}`, import.meta.url), 'utf8'));
  }
  await db.query('insert into public.admins values ($1, $2)', [admin, 'mentor@example.com']);
});
after(async () => db.close());

test('anonymous skill can ingest, but cannot read student data or statistics', async () => {
  await role('anon');
  const { rows } = await db.query('select public.ingest($1, $2, $3, $4, $5) as result', [device, secret,
    { claude_name: 'Test Student', claude_email: 'student@example.com' },
    [{ prompt: 'Build a test app', project: 'test-app' }],
    { level: 3, summary: 'Checked the result', stage: 'Testing' },
  ]);
  assert.equal(rows[0].result.prompts, 1);
  await assert.rejects(db.query('select * from public.students'), /permission denied/);
  await assert.rejects(db.query('select public.dashboard_stats(30)'), /permission denied/);
  await assert.rejects(db.query('select public.ingest($1, $2)', [device, 'b'.repeat(64)]), /bad credentials/);
});
test('an authenticated non-admin cannot read students, prompts or summaries', async () => {
  await role('authenticated', outsider);
  for (const table of ['students', 'prompts', 'summaries', 'admins']) {
    const { rows } = await db.query(`select * from public.${table}`);
    assert.equal(rows.length, 0, table);
  }
  await assert.rejects(db.query('select public.dashboard_stats(30)'), /Administrator access required/);
  const { rows } = await db.query("update public.students set display_name = 'Unauthorized' returning id");
  assert.equal(rows.length, 0);
});
test('admin sees exact totals, level zero, unassessed students and zero-filled UTC days', async () => {
  await role('postgres');
  await db.query("insert into public.students (device_id, device_secret_hash, level, last_seen, first_seen) values ($1, 'test', 0, now() - interval '50 days', now() - interval '50 days'), ($2, 'test', null, now(), now())", ['00000000-0000-4000-8000-000000000004', '00000000-0000-4000-8000-000000000005']);
  await role('authenticated', admin);
  const { rows } = await db.query('select public.dashboard_stats(30) as stats');
  const s = rows[0].stats;
  assert.equal(s.students, 3); assert.equal(s.new_students, 2); assert.equal(s.active_students, 2);
  assert.equal(s.prompts, 1); assert.equal(s.summaries, 1); assert.equal(s.average_level, 1.5);
  assert.equal(s.unassessed, 1); assert.equal(s.activity.length, 30);
  assert.equal(s.activity.at(-1).prompts, 1); assert.equal(s.activity[0].prompts, 0);
  assert.equal(s.levels[0].count, 1); assert.equal(s.levels[3].count, 1);
  for (const days of [14, 90]) {
    const { rows } = await db.query('select public.dashboard_stats($1) as stats', [days]);
    assert.equal(rows[0].stats.activity.length, days);
  }
  await assert.rejects(db.query('select public.dashboard_stats(999)'), /Period must be/);
});
test('admin can change names and groups, but cannot overwrite telemetry fields', async () => {
  await role('authenticated', admin);
  const { rows } = await db.query("update public.students set display_name = 'Renamed', group_name = 'Group A' where device_id = $1 returning display_name", [device]);
  assert.equal(rows[0].display_name, 'Renamed');
  const stats = await db.query('select public.dashboard_stats(30) as stats');
  assert.deepEqual(stats.rows[0].stats.groups, ['Group A']);
  await assert.rejects(db.query('update public.students set level = 5'), /permission denied/);
  await assert.rejects(db.query('delete from public.students'), /permission denied/);
});
test('statistics include more than 1000 prompts and exclude old events from the selected period', async () => {
  await role('postgres');
  await db.query("insert into public.prompts (student_id, prompt, created_at) select id, 'batch test', now() from public.students cross join generate_series(1, 1200) where device_id = $1", [device]);
  await db.query("insert into public.prompts (student_id, prompt, created_at) select id, 'old prompt', now() - interval '50 days' from public.students where device_id = $1", [device]);
  await role('authenticated', admin);
  const recent = await db.query('select public.dashboard_stats(14) as stats');
  const all = await db.query('select public.dashboard_stats(90) as stats');
  assert.equal(recent.rows[0].stats.prompts, 1201);
  assert.equal(all.rows[0].stats.prompts, 1202);
  assert.equal(recent.rows[0].stats.activity.reduce((n, d) => n + d.prompts, 0), 1201);
});

test('event retries do not inflate counts and old summaries cannot overwrite newer observations', async () => {
  await role('anon');
  const event = '00000000-0000-4000-8000-000000000101';
  const summary = { event_id: '00000000-0000-4000-8000-000000000102', level: 4, summary: 'New evidence', ts: new Date().toISOString() };
  const args = [device, secret, { analysis_allowed: true, consent_version: 2, consented_at: new Date().toISOString() }, [{ event_id: event, prompt: 'Idempotent event' }], summary];
  const first = await db.query('select public.ingest($1,$2,$3,$4,$5) as r', args);
  const retry = await db.query('select public.ingest($1,$2,$3,$4,$5) as r', args);
  assert.equal(first.rows[0].r.prompts, 1); assert.equal(first.rows[0].r.summaries, 1);
  assert.equal(retry.rows[0].r.prompts, 0); assert.equal(retry.rows[0].r.summaries, 0);
  await db.query('select public.ingest($1,$2,$3,$4,$5)', [device, secret, {}, [], { event_id: '00000000-0000-4000-8000-000000000103', level: 1, summary: 'Old evidence', ts: '2020-01-01T00:00:00Z' }]);
  await role('authenticated', admin);
  const { rows } = await db.query('select level,summary from public.students where device_id=$1', [device]);
  assert.equal(rows[0].level, 4); assert.equal(rows[0].summary, 'New evidence');
});

test('analysis snapshot has exact totals, bounded samples, no account fields and excludes non-consenting devices', async () => {
  await role('authenticated', admin);
  const { rows } = await db.query('select public.team_analysis_snapshot(30,null) as s');
  const s = rows[0].s;
  assert.equal(s.total_devices, 3); assert.equal(s.eligible_devices, 1); assert.equal(s.excluded_without_analysis_consent, 2);
  assert.equal(s.students[0].metrics.prompts, 1202);
  assert.equal(s.students[0].prompts.length, 8);
  assert.ok(s.students[0].summaries.length <= 5);
  assert.equal(JSON.stringify(s).includes('student@example.com'), false);
  assert.equal(JSON.stringify(s).includes('device_secret_hash'), false);
  await role('authenticated', outsider);
  await assert.rejects(db.query('select public.team_analysis_snapshot(30,null)'), /Administrator access required/);
  await assert.rejects(db.query('select public.begin_team_analysis(30,null)'), /Administrator access required/);
});

test('analysis jobs are rate limited and cannot be forged or altered by browser users', async () => {
  await role('authenticated', admin);
  const { rows } = await db.query('select public.begin_team_analysis(30,null) as r');
  assert.ok(rows[0].r.id);
  await assert.rejects(db.query('select public.begin_team_analysis(30,null)'), /Wait two minutes/);
  await assert.rejects(db.query("update public.team_reports set status='complete'"), /permission denied/);
  await role('authenticated', outsider);
  const hidden = await db.query('select * from public.team_reports');
  assert.equal(hidden.rows.length, 0);
  await role('anon');
  await assert.rejects(db.query('select * from public.team_reports'), /permission denied/);
  await db.query('select public.revoke_analysis_consent($1,$2)', [device, secret]);
  await role('authenticated', admin);
  const after = await db.query('select public.team_analysis_snapshot(30,null) as s');
  assert.equal(after.rows[0].s.eligible_devices, 0);
});

test('unknown current assessment remains unknown, and profile sync does not masquerade as a new assessment', async () => {
  await role('anon');
  await db.query('select public.ingest($1,$2,$3,$4,$5)', [device, secret, {}, [], { event_id: '00000000-0000-4000-8000-000000000104', level: null, summary: 'Insufficient evidence in this session' }]);
  await role('authenticated', admin);
  const before = await db.query('select level,last_summary_at from public.students where device_id=$1', [device]);
  assert.equal(before.rows[0].level, null);
  await role('anon');
  await db.query('select public.ingest($1,$2,$3,$4,$5)', [device, secret, {}, [], { event_id: '00000000-0000-4000-8000-000000000105', profile_md: 'Updated profile only' }]);
  await role('authenticated', admin);
  const after = await db.query('select level,last_summary_at,profile_md from public.students where device_id=$1', [device]);
  assert.equal(after.rows[0].last_summary_at.getTime(), before.rows[0].last_summary_at.getTime());
  assert.equal(after.rows[0].profile_md, 'Updated profile only');
});


test('structured progress preserves provider, evidence, retry safety and latest report ordering', async () => {
  const d = '00000000-0000-4000-8000-000000000301';
  const report = JSON.parse(await readFile(new URL('../../skills/arslanbek-ai-mentor/references/progress-example.json', import.meta.url), 'utf8'));
  const summary = {event_id: '00000000-0000-4000-8000-000000000302', summary: report.result, report, client: 'codex', model: 'test-model', ts: new Date().toISOString()};
  await role('anon');
  await db.query('select public.ingest($1,$2,$3,$4,$5)', [d, secret, {}, [{prompt: 'Check cart', client: 'codex'}], summary]);
  const retry = await db.query('select public.ingest($1,$2,$3,$4,$5) as result', [d, secret, {}, [], summary]);
  assert.equal(retry.rows[0].result.summaries, 0);
  await db.query('select public.ingest($1,$2,$3,$4,$5)', [d, secret, {}, [], {...summary, event_id: '00000000-0000-4000-8000-000000000303', ts: '2020-01-01', client: 'mcp', report: {...report, task: 'Outdated'}}]);
  await role('authenticated', admin);
  const student = (await db.query('select id,progress_report,last_client,level from public.students where device_id=$1', [d])).rows[0];
  assert.deepEqual(student.progress_report, report);
  assert.equal(student.last_client, 'codex');
  assert.equal(student.level, null);
  const summaries = (await db.query('select client,model,progress_report from public.summaries where student_id=$1 order by created_at desc', [student.id])).rows;
  assert.equal(summaries.length, 2);
  assert.equal(summaries[0].model, 'test-model');
  assert.deepEqual(summaries[0].progress_report.next_steps, report.next_steps);
  await role('authenticated', outsider);
  assert.equal((await db.query('select progress_report from public.students where id=$1', [student.id])).rows.length, 0);
  await role('anon');
  for (const bad of [{}, {...report, skills: 'text'}, {...report, next_steps: []}, {...report, version: null}, {...report, skills: [{name: 'Skill', status: 'strength', evidence: '', next_action: ''}]}]) {
    await assert.rejects(db.query('select public.ingest($1,$2,$3,$4,$5)', [d, secret, {}, [], {...summary, report: bad}]), /progress|skill|next step/);
  }
});
