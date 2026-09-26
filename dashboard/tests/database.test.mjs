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
    create role anon; create role authenticated;
    create schema auth;
    create table auth.users (id uuid primary key, email text);
    create function auth.uid() returns uuid language sql stable as $$
      select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
    $$;
    grant usage on schema public, auth to anon, authenticated;
    insert into auth.users values ('${admin}', 'mentor@example.com'), ('${outsider}', 'other@example.com');
  `);
  for (const filename of ['0001_telemetry.sql', '0002_dashboard.sql']) {
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
