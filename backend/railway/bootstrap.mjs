import pg from 'pg';
import { readFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';

export async function bootstrap(env) {
  for (const key of ['DATABASE_URL', 'AUTH_DB_PASSWORD', 'REST_DB_PASSWORD', 'AUTH_URL', 'SUPABASE_SERVICE_ROLE_KEY']) {
    if (!env[key]) throw new Error(`Missing ${key}`);
  }
  const db = new pg.Client({ connectionString: env.DATABASE_URL, connectionTimeoutMillis: 10000 });
  await db.connect();
  try {
    await db.query('select pg_advisory_lock(728310024)');
    await db.query(`
      do $$ begin
        if not exists(select from pg_roles where rolname='anon') then create role anon nologin; end if;
        if not exists(select from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
        if not exists(select from pg_roles where rolname='service_role') then create role service_role nologin bypassrls; end if;
        if not exists(select from pg_roles where rolname='authenticator') then create role authenticator login noinherit; end if;
        if not exists(select from pg_roles where rolname='supabase_auth_admin') then create role supabase_auth_admin login noinherit; end if;
      end $$;
      grant anon, authenticated, service_role to authenticator;
      create schema if not exists auth authorization supabase_auth_admin;
      create schema if not exists extensions;
      create extension if not exists pgcrypto with schema extensions;
      grant usage on schema public, auth, extensions to anon, authenticated, service_role;
      grant usage on schema public, extensions to supabase_auth_admin;
      alter role supabase_auth_admin set search_path = auth, public, extensions;
      revoke create on schema public from public;
      create or replace function auth.uid() returns uuid language sql stable as $$
        select coalesce(nullif(current_setting('request.jwt.claim.sub',true),''),
          nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid;
      $$;
      -- GoTrue's first migration replaces this helper under its own database role.
      alter function auth.uid() owner to supabase_auth_admin;
      grant execute on function auth.uid() to anon, authenticated, service_role;
      create schema if not exists mentor_deploy;
      revoke all on schema mentor_deploy from public;
      create table if not exists mentor_deploy.migrations(name text primary key, checksum text not null, applied_at timestamptz not null default now());
    `);
    await db.query(`alter role authenticator password ${pg.escapeLiteral(env.REST_DB_PASSWORD)}`);
    await db.query(`alter role supabase_auth_admin password ${pg.escapeLiteral(env.AUTH_DB_PASSWORD)}`);
    console.info('Database roles ready; waiting for authentication migrations.');
    let authReady = false;
    for (let attempt = 0; attempt < 90; attempt++) {
      const result = await db.query("select to_regclass('auth.users') is not null as ready");
      if (result.rows[0].ready) {
        try { authReady = (await fetch(`${env.AUTH_URL}/health`, { signal: AbortSignal.timeout(3000) })).ok; } catch { /* Service is starting. */ }
        if (authReady) break;
      }
      await delay(2000);
    }
    if (!authReady) throw new Error('Authentication service not ready');
    const directory = new URL('../supabase/migrations/', import.meta.url);
    for (const name of (await readdir(directory)).filter(n => /^\d+_.+\.sql$/.test(n)).sort()) {
      const sql = await readFile(new URL(name, directory), 'utf8');
      const checksum = createHash('sha256').update(sql).digest('hex');
      const existing = await db.query('select checksum from mentor_deploy.migrations where name=$1', [name]);
      if (existing.rowCount) {
        if (existing.rows[0].checksum !== checksum) throw new Error(`Applied migration changed: ${name}`);
        continue;
      }
      await db.query('begin');
      try {
        await db.query(sql);
        await db.query('insert into mentor_deploy.migrations(name,checksum) values($1,$2)', [name, checksum]);
        await db.query('commit');
        console.info(`Applied migration ${name}`);
      } catch (error) { await db.query('rollback'); throw error; }
    }
    if (env.BOOTSTRAP_ADMIN_EMAIL) {
      const existing = await db.query('select id from auth.users where lower(email)=lower($1)', [env.BOOTSTRAP_ADMIN_EMAIL]);
      let id = existing.rows[0]?.id;
      if (!id) {
        if (!env.BOOTSTRAP_ADMIN_PASSWORD || env.BOOTSTRAP_ADMIN_PASSWORD.length < 20) throw new Error('Initial administrator password missing');
        const response = await fetch(`${env.AUTH_URL}/admin/users`, {
          method: 'POST', signal: AbortSignal.timeout(20000),
          headers: { Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: env.BOOTSTRAP_ADMIN_EMAIL, password: env.BOOTSTRAP_ADMIN_PASSWORD, email_confirm: true }),
        });
        if (!response.ok) throw new Error(`Administrator creation returned ${response.status}`);
        id = (await response.json()).id;
        if (!id) throw new Error('Administrator creation returned no ID');
      }
      await db.query('insert into public.admins(user_id,email) values($1,$2) on conflict(user_id) do nothing', [id, env.BOOTSTRAP_ADMIN_EMAIL]);
    }
    await db.query("notify pgrst, 'reload schema'");
    console.info('Application migrations and administrator ready.');
  } finally {
    await db.end();
  }
}
