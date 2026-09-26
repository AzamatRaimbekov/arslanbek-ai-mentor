-- Сбор данных arslanbek-ai-mentor: промпты и срезы по ученикам.
--
-- Модель доступа:
--   * клиенты (скил на машинах учеников) ходят с публичным anon-ключом и могут
--     ТОЛЬКО вызвать public.ingest(...). Прямого доступа к таблицам у них нет;
--   * каждое устройство при первом обращении регистрирует device_id + секрет,
--     дальше без секрета писать от его имени нельзя;
--   * читать данные могут только вошедшие пользователи из public.admins.
--
-- Первый админ (после регистрации в Supabase Auth):
--   insert into public.admins (user_id, email)
--   select id, email from auth.users where email = 'you@example.com';

-- ── таблицы ────────────────────────────────────────────────────────────────

create table public.students (
  id                 uuid primary key default gen_random_uuid(),
  device_id          uuid not null unique,
  device_secret_hash text not null,
  -- что скил узнал о человеке сам
  claude_email       text,
  claude_name        text,
  claude_org         text,
  git_email          text,
  git_name           text,
  os_user            text,
  hostname           text,
  os                 text,
  -- что задаёт админ в дашборде
  display_name       text,
  group_name         text,
  -- последний срез от наставника
  level              smallint check (level between 0 and 5),
  stage              text,
  summary            text,
  profile_md         text,
  prompt_count       integer not null default 0,
  first_seen         timestamptz not null default now(),
  last_seen          timestamptz not null default now()
);

create table public.prompts (
  id          bigint generated always as identity primary key,
  student_id  uuid not null references public.students (id) on delete cascade,
  session_id  text,
  project     text,
  prompt      text not null,
  created_at  timestamptz not null default now(),  -- время на машине ученика
  received_at timestamptz not null default now()
);
create index prompts_student_created_idx on public.prompts (student_id, created_at desc);
create index prompts_created_idx on public.prompts (created_at desc);

create table public.summaries (
  id          bigint generated always as identity primary key,
  student_id  uuid not null references public.students (id) on delete cascade,
  session_id  text,
  project     text,
  level       smallint check (level between 0 and 5),
  stage       text,
  summary     text,
  strengths   text,
  struggles   text,
  next_step   text,
  created_at  timestamptz not null default now()
);
create index summaries_student_created_idx on public.summaries (student_id, created_at desc);

create table public.admins (
  user_id uuid primary key references auth.users (id) on delete cascade,
  email   text
);

-- ── доступ ─────────────────────────────────────────────────────────────────

create function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.admins where user_id = auth.uid());
$$;

alter table public.students  enable row level security;
alter table public.prompts   enable row level security;
alter table public.summaries enable row level security;
alter table public.admins    enable row level security;

create policy admin_read on public.students  for select to authenticated using (public.is_admin());
create policy admin_edit on public.students  for update to authenticated using (public.is_admin()) with check (public.is_admin());
create policy admin_read on public.prompts   for select to authenticated using (public.is_admin());
create policy admin_read on public.summaries for select to authenticated using (public.is_admin());
create policy admin_read on public.admins    for select to authenticated using (public.is_admin());

-- админ правит только имя и группу, остальное пишет скил
revoke update on public.students from authenticated;
grant  update (display_name, group_name) on public.students to authenticated;

-- ── приём данных ───────────────────────────────────────────────────────────

-- p_identity: {claude_email, claude_name, claude_org, git_email, git_name, os_user, hostname, os}
-- p_prompts:  [{session_id, project, prompt, ts}]  — не больше 200 за раз
-- p_summary:  {session_id, project, level, stage, summary, strengths, struggles, next_step, profile_md} или null
create function public.ingest(
  p_device   uuid,
  p_secret   text,
  p_identity jsonb default '{}'::jsonb,
  p_prompts  jsonb default '[]'::jsonb,
  p_summary  jsonb default null
) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_hash    text := encode(sha256(convert_to(coalesce(p_secret, ''), 'UTF8')), 'hex');
  v_student public.students%rowtype;
  v_count   integer := 0;
  v_level   smallint;
begin
  if p_device is null or length(coalesce(p_secret, '')) < 32 then
    raise exception 'bad credentials' using errcode = '28000';
  end if;
  if jsonb_typeof(coalesce(p_prompts, '[]'::jsonb)) <> 'array'
     or jsonb_array_length(coalesce(p_prompts, '[]'::jsonb)) > 200 then
    raise exception 'bad prompts batch' using errcode = '22023';
  end if;

  -- регистрация при первом обращении, дальше — сверка секрета
  insert into public.students (device_id, device_secret_hash)
  values (p_device, v_hash)
  on conflict (device_id) do nothing;

  select * into v_student from public.students where device_id = p_device for update;
  if v_student.device_secret_hash <> v_hash then
    raise exception 'bad credentials' using errcode = '28000';
  end if;

  if p_prompts is not null and jsonb_array_length(p_prompts) > 0 then
    insert into public.prompts (student_id, session_id, project, prompt, created_at)
    select v_student.id,
           left(e->>'session_id', 100),
           left(e->>'project', 200),
           left(e->>'prompt', 20000),
           coalesce(least((e->>'ts')::timestamptz, now()), now())
    from jsonb_array_elements(p_prompts) e
    where coalesce(e->>'prompt', '') <> '';
    get diagnostics v_count = row_count;
  end if;

  if p_summary is not null and jsonb_typeof(p_summary) = 'object' then
    v_level := nullif(p_summary->>'level', '')::smallint;
    if v_level is not null and (v_level < 0 or v_level > 5) then
      raise exception 'level must be 0..5' using errcode = '22023';
    end if;
    if v_level is not null or coalesce(p_summary->>'summary', '') <> '' then
      insert into public.summaries (student_id, session_id, project, level, stage, summary, strengths, struggles, next_step)
      values (v_student.id,
              left(p_summary->>'session_id', 100),
              left(p_summary->>'project', 200),
              v_level,
              left(p_summary->>'stage', 200),
              left(p_summary->>'summary', 5000),
              left(p_summary->>'strengths', 2000),
              left(p_summary->>'struggles', 2000),
              left(p_summary->>'next_step', 2000));
    end if;
  end if;

  update public.students set
    claude_email = coalesce(nullif(left(p_identity->>'claude_email', 200), ''), claude_email),
    claude_name  = coalesce(nullif(left(p_identity->>'claude_name', 200), ''), claude_name),
    claude_org   = coalesce(nullif(left(p_identity->>'claude_org', 200), ''), claude_org),
    git_email    = coalesce(nullif(left(p_identity->>'git_email', 200), ''), git_email),
    git_name     = coalesce(nullif(left(p_identity->>'git_name', 200), ''), git_name),
    os_user      = coalesce(nullif(left(p_identity->>'os_user', 100), ''), os_user),
    hostname     = coalesce(nullif(left(p_identity->>'hostname', 200), ''), hostname),
    os           = coalesce(nullif(left(p_identity->>'os', 200), ''), os),
    level        = coalesce(v_level, level),
    stage        = coalesce(nullif(left(p_summary->>'stage', 200), ''), stage),
    summary      = coalesce(nullif(left(p_summary->>'summary', 5000), ''), summary),
    profile_md   = coalesce(nullif(left(p_summary->>'profile_md', 50000), ''), profile_md),
    prompt_count = prompt_count + v_count,
    last_seen    = now()
  where id = v_student.id;

  return jsonb_build_object('ok', true, 'prompts', v_count);
end;
$$;

revoke all on function public.ingest(uuid, text, jsonb, jsonb, jsonb) from public;
grant execute on function public.ingest(uuid, text, jsonb, jsonb, jsonb) to anon, authenticated;
revoke all on function public.is_admin() from public;
grant execute on function public.is_admin() to authenticated;
