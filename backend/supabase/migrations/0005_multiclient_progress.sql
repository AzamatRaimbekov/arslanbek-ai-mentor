-- Keep older clients and their text summaries working; add structured progress.
alter table public.prompts add column client text not null default 'claude-code';
alter table public.prompts add column model text;
alter table public.summaries add column client text not null default 'claude-code';
alter table public.summaries add column model text;
alter table public.summaries add column progress_report jsonb;
alter table public.students add column progress_report jsonb;
alter table public.students add column last_client text;

create function public.validate_progress_report(p jsonb) returns void
language plpgsql immutable set search_path=public as $$
declare k text; e jsonb;
begin
  if jsonb_typeof(p) <> 'object' or octet_length(p::text) > 65000 or coalesce(p->>'version','') <> '1' or jsonb_typeof(p->'version') <> 'number'
     or not p ?& array['version','task','goal','stage','status','directions','learner_actions','agent_actions','result','skills','checks','blockers','next_steps','confidence','limitations'] then
    raise exception 'invalid progress report' using errcode='22023';
  end if;
  foreach k in array array['task','goal','stage','status','result','confidence'] loop
    if jsonb_typeof(p->k) <> 'string' or length(p->>k) > 5000 then
      raise exception 'invalid progress text' using errcode='22023';
    end if;
  end loop;
  if btrim(p->>'task')='' or btrim(p->>'result')=''
     or p->>'stage' not in ('discovery','planning','building','checking','delivery')
     or p->>'status' not in ('in_progress','blocked','completed')
     or p->>'confidence' not in ('low','medium','high') then
    raise exception 'invalid progress state' using errcode='22023';
  end if;
  foreach k in array array['directions','learner_actions','agent_actions','skills','checks','blockers','next_steps','limitations'] loop
    if jsonb_typeof(p->k) <> 'array' then raise exception 'invalid progress list' using errcode='22023'; end if;
    if jsonb_array_length(p->k) > 12 then raise exception 'progress list too long' using errcode='22023'; end if;
  end loop;
  foreach k in array array['directions','learner_actions','agent_actions','blockers','limitations'] loop
    for e in select value from jsonb_array_elements(p->k) loop
      if jsonb_typeof(e) <> 'string' or length(e#>>'{}') > 2000 then raise exception 'invalid progress list item' using errcode='22023'; end if;
    end loop;
  end loop;
  for e in select value from jsonb_array_elements(p->'skills') loop
    if jsonb_typeof(e) <> 'object' or not e ?& array['name','status','evidence','next_action']
       or jsonb_typeof(e->'name') <> 'string' or jsonb_typeof(e->'evidence') <> 'string' or jsonb_typeof(e->'next_action') <> 'string'
       or coalesce(e->>'status','') not in ('strength','developing','needs_support','unknown')
       or (e->>'status' <> 'unknown' and btrim(e->>'evidence')='') then
      raise exception 'invalid skill observation' using errcode='22023';
    end if;
  end loop;
  for e in select value from jsonb_array_elements(p->'checks') loop
    if jsonb_typeof(e) <> 'object' or not e ?& array['name','status','evidence']
       or jsonb_typeof(e->'name') <> 'string' or jsonb_typeof(e->'evidence') <> 'string'
       or coalesce(e->>'status','') not in ('passed','failed','not_run') then
      raise exception 'invalid progress check' using errcode='22023';
    end if;
  end loop;
  if jsonb_array_length(p->'next_steps') not between 1 and 5 then raise exception 'next step required' using errcode='22023'; end if;
  for e in select value from jsonb_array_elements(p->'next_steps') loop
    if jsonb_typeof(e) <> 'object' or not e ?& array['action','done_when','owner']
       or jsonb_typeof(e->'action') <> 'string' or jsonb_typeof(e->'done_when') <> 'string'
       or btrim(e->>'action')='' or btrim(e->>'done_when')=''
       or coalesce(e->>'owner','') not in ('learner','mentor') then
      raise exception 'invalid next step' using errcode='22023';
    end if;
  end loop;
end;
$$;
revoke all on function public.validate_progress_report(jsonb) from public;

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
  if p_summary ? 'report' and p_summary->'report' <> 'null'::jsonb then
    perform public.validate_progress_report(p_summary->'report');
  end if;
  insert into public.students(device_id, device_secret_hash) values(p_device, v_hash)
    on conflict(device_id) do nothing;
  select * into v_student from public.students where device_id = p_device for update;
  if v_student.device_secret_hash <> v_hash then
    raise exception 'bad credentials' using errcode = '28000';
  end if;

  with inserted as (
    insert into public.prompts(student_id, event_id, session_id, project, prompt, created_at, client, model)
    select v_student.id, nullif(e->>'event_id', '')::uuid,
      left(e->>'session_id', 100), left(e->>'project', 200), left(e->>'prompt', 20000),
      coalesce(least(nullif(e->>'ts', '')::timestamptz, now()), now()),
      coalesce(nullif(left(e->>'client', 80), ''), 'claude-code'), nullif(left(e->>'model', 120), '')
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
      insert into public.summaries(student_id, event_id, session_id, project, level, stage, summary, strengths, struggles, next_step, created_at, client, model, progress_report)
      values(v_student.id, nullif(p_summary->>'event_id', '')::uuid,
        left(p_summary->>'session_id', 100), left(p_summary->>'project', 200), v_level,
        left(p_summary->>'stage', 200), left(p_summary->>'summary', 5000),
        left(p_summary->>'strengths', 2000), left(p_summary->>'struggles', 2000),
        left(p_summary->>'next_step', 2000), v_summary_at,
        coalesce(nullif(left(p_summary->>'client', 80), ''), 'claude-code'),
        nullif(left(p_summary->>'model', 120), ''), nullif(p_summary->'report', 'null'::jsonb))
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
    progress_report = case when v_fresh and v_summary_count > 0 then nullif(p_summary->'report', 'null'::jsonb) else progress_report end,
    last_client = case when v_fresh and v_summary_count > 0 then coalesce(nullif(left(p_summary->>'client', 80), ''), 'claude-code') else last_client end,
    last_summary_at = case when v_fresh and v_summary_count > 0 then v_summary_at else last_summary_at end,
    prompt_count = prompt_count + v_count,
    last_event_at = greatest(last_event_at, v_prompt_at, case when v_summary_count > 0 then v_summary_at end),
    last_seen = now()
  where id = v_student.id;
  return jsonb_build_object('ok', true, 'prompts', v_count, 'summaries', v_summary_count);
end;
$$;

