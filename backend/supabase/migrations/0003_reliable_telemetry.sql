-- Stable event IDs make retrying a batch safe after a lost HTTP response.
alter table public.prompts add column event_id uuid;
alter table public.summaries add column event_id uuid;
alter table public.summaries add column received_at timestamptz not null default now();
alter table public.students add column last_event_at timestamptz;
alter table public.students add column last_summary_at timestamptz;
alter table public.students add column skill_version text;
alter table public.students add column analysis_allowed boolean not null default false;
alter table public.students add column consent_version integer;
alter table public.students add column consented_at timestamptz;
create unique index prompts_event_id_idx on public.prompts(student_id, event_id);
create unique index summaries_event_id_idx on public.summaries(student_id, event_id);

create or replace function public.ingest(
  p_device uuid, p_secret text, p_identity jsonb default '{}'::jsonb,
  p_prompts jsonb default '[]'::jsonb, p_summary jsonb default null
) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_hash text := encode(sha256(convert_to(coalesce(p_secret, ''), 'UTF8')), 'hex');
  v_student public.students%rowtype;
  v_count integer := 0;
  v_summary_count integer := 0;
  v_level smallint;
  v_summary_at timestamptz;
  v_prompt_at timestamptz;
  v_fresh boolean := false;
begin
  if p_device is null or length(coalesce(p_secret, '')) < 32 then
    raise exception 'bad credentials' using errcode = '28000';
  end if;
  if jsonb_typeof(coalesce(p_identity, '{}'::jsonb)) <> 'object'
     or jsonb_typeof(coalesce(p_prompts, '[]'::jsonb)) <> 'array'
     or jsonb_array_length(coalesce(p_prompts, '[]'::jsonb)) > 200 then
    raise exception 'bad payload' using errcode = '22023';
  end if;
  insert into public.students(device_id, device_secret_hash) values(p_device, v_hash)
    on conflict(device_id) do nothing;
  select * into v_student from public.students where device_id = p_device for update;
  if v_student.device_secret_hash <> v_hash then
    raise exception 'bad credentials' using errcode = '28000';
  end if;

  with inserted as (
    insert into public.prompts(student_id, event_id, session_id, project, prompt, created_at)
    select v_student.id, nullif(e->>'event_id', '')::uuid,
      left(e->>'session_id', 100), left(e->>'project', 200), left(e->>'prompt', 20000),
      coalesce(least(nullif(e->>'ts', '')::timestamptz, now()), now())
    from jsonb_array_elements(coalesce(p_prompts, '[]'::jsonb)) e
    where coalesce(e->>'prompt', '') <> ''
    on conflict(student_id, event_id) do nothing
    returning created_at
  ) select count(*), max(created_at) into v_count, v_prompt_at from inserted;

  if p_summary is not null and jsonb_typeof(p_summary) = 'object' then
    v_level := nullif(p_summary->>'level', '')::smallint;
    if v_level is not null and (v_level < 0 or v_level > 5) then
      raise exception 'level must be 0..5' using errcode = '22023';
    end if;
    v_summary_at := coalesce(least(nullif(p_summary->>'ts', '')::timestamptz, now()), now());
    if v_level is not null or coalesce(p_summary->>'summary', '') <> '' then
      insert into public.summaries(student_id, event_id, session_id, project, level, stage, summary, strengths, struggles, next_step, created_at)
      values(v_student.id, nullif(p_summary->>'event_id', '')::uuid,
        left(p_summary->>'session_id', 100), left(p_summary->>'project', 200), v_level,
        left(p_summary->>'stage', 200), left(p_summary->>'summary', 5000),
        left(p_summary->>'strengths', 2000), left(p_summary->>'struggles', 2000),
        left(p_summary->>'next_step', 2000), v_summary_at)
      on conflict(student_id, event_id) do nothing;
      get diagnostics v_summary_count = row_count;
    end if;
    v_fresh := (v_student.last_summary_at is null or v_summary_at >= v_student.last_summary_at)
      and (v_summary_count > 0 or (v_level is null and coalesce(p_summary->>'summary', '') = ''
        and coalesce(p_summary->>'profile_md', '') <> ''));
  end if;

  update public.students set
    claude_email = coalesce(nullif(left(p_identity->>'claude_email', 200), ''), claude_email),
    claude_name = coalesce(nullif(left(p_identity->>'claude_name', 200), ''), claude_name),
    claude_org = coalesce(nullif(left(p_identity->>'claude_org', 200), ''), claude_org),
    git_email = coalesce(nullif(left(p_identity->>'git_email', 200), ''), git_email),
    git_name = coalesce(nullif(left(p_identity->>'git_name', 200), ''), git_name),
    os_user = coalesce(nullif(left(p_identity->>'os_user', 100), ''), os_user),
    hostname = coalesce(nullif(left(p_identity->>'hostname', 200), ''), hostname),
    os = coalesce(nullif(left(p_identity->>'os', 200), ''), os),
    skill_version = coalesce(nullif(left(p_identity->>'skill_version', 80), ''), skill_version),
    analysis_allowed = case when p_identity ? 'analysis_allowed' then
      coalesce((p_identity->>'analysis_allowed')::boolean, false)
      and coalesce((p_identity->>'consent_version')::integer, 0) >= 2 else analysis_allowed end,
    consent_version = coalesce((p_identity->>'consent_version')::integer, consent_version),
    consented_at = coalesce((p_identity->>'consented_at')::timestamptz, consented_at),
    level = case when v_fresh and v_summary_count > 0 then v_level else level end,
    stage = case when v_fresh then coalesce(nullif(left(p_summary->>'stage', 200), ''), stage) else stage end,
    summary = case when v_fresh then coalesce(nullif(left(p_summary->>'summary', 5000), ''), summary) else summary end,
    profile_md = case when v_fresh then coalesce(nullif(left(p_summary->>'profile_md', 50000), ''), profile_md) else profile_md end,
    last_summary_at = case when v_fresh and v_summary_count > 0 then v_summary_at else last_summary_at end,
    prompt_count = prompt_count + v_count,
    last_event_at = greatest(last_event_at, v_prompt_at, case when v_summary_count > 0 then v_summary_at end),
    last_seen = now()
  where id = v_student.id;
  return jsonb_build_object('ok', true, 'prompts', v_count, 'summaries', v_summary_count);
end;
$$;

-- Consent can be revoked without sending any identity or queued prompt data.
create function public.revoke_analysis_consent(p_device uuid, p_secret text) returns void
language plpgsql security definer set search_path = public as $$
begin
  update public.students set analysis_allowed = false
  where device_id = p_device and device_secret_hash = encode(sha256(convert_to(coalesce(p_secret, ''), 'UTF8')), 'hex');
end;
$$;
revoke all on function public.revoke_analysis_consent(uuid, text) from public;
grant execute on function public.revoke_analysis_consent(uuid, text) to anon, authenticated;
