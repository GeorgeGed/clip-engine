-- The control plane's tables. Postgres, so it drops into Supabase as-is.
--
-- The agent (worker/agent.py) never touches these directly — it goes through
-- the six HTTP calls in worker/backend.py. This file is here so the website
-- can be built against a schema rather than against a guess.

create table if not exists job (
  id          uuid primary key default gen_random_uuid(),
  name        text not null unique,          -- jobs/<name>; every path is keyed on it
  url         text not null,                 -- the VOD, or a path on the worker's disk
  channel     text not null,
  -- NEVER NULL, and not defaulted. The build refuses to start without a
  -- rights basis, and a viewer's chat message is their words on screen.
  rights      text not null check (rights in ('explicit','affiliate','client_owned')),
  note        text not null default '',
  state       text not null default 'queued',
  owner       uuid references auth.users,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),

  -- THE LEASE. A worker that dies mid-job must not strand it. The claim sets
  -- these; a heartbeat extends lease_until; anything past its lease with no
  -- heartbeat goes back to 'queued'. A thread flag cannot survive a crash,
  -- a power cut, or a Mac going to sleep, and all three happen.
  claimed_by  text,
  lease_until timestamptz,
  attempts    int not null default 0
);

create table if not exists stage (
  job_id   uuid not null references job(id) on delete cascade,
  key      text not null,
  state    text not null default 'pending',  -- pending|running|done|failed
  started  timestamptz,
  ended    timestamptz,
  code     int,
  progress jsonb not null default '{}',      -- {line, done, total}
  primary key (job_id, key)
);

create table if not exists clip (
  job_id    uuid not null references job(id) on delete cascade,
  idx       int  not null,                   -- the candidate number, 01..50
  url       text not null,                   -- where the mp4 landed
  meta      jsonb not null default '{}',     -- bytes, seconds, qc_ok
  created_at timestamptz not null default now(),
  primary key (job_id, idx)
);

create table if not exists worker (
  name       text primary key,
  health     jsonb not null default '{}',    -- {resolve, notes, host, platform}
  seen_at    timestamptz not null default now()
);

create index if not exists job_claimable on job (state, created_at)
  where state = 'queued';

-- ONE JOB AT A TIME, PER WORKER, ENFORCED BY THE DATABASE.
--
-- Resolve is one GUI app with one timeline, so two jobs on one Mac is not
-- slower, it is wrong. `for update skip locked` is what makes two agents
-- racing for the same row impossible without either of them waiting.
create or replace function claim_job(w text, needs_resolve boolean,
                                     lease_seconds int default 900)
returns setof job language plpgsql as $$
begin
  return query
  with reclaimed as (
    update job set state = 'queued', claimed_by = null, lease_until = null
     where state like 'running%' and lease_until < now()
     returning id
  ), picked as (
    select j.id from job j
     where j.state = 'queued'
       and (needs_resolve or true)
     order by j.created_at
     for update skip locked
     limit 1
  )
  update job j
     set state = 'running:' || w, claimed_by = w, attempts = j.attempts + 1,
         lease_until = now() + make_interval(secs => lease_seconds),
         updated_at = now()
   from picked p where j.id = p.id
  returning j.*;
end $$;

alter table job    enable row level security;
alter table stage  enable row level security;
alter table clip   enable row level security;
-- Policies are deliberately not written here: who may see which job is a
-- product decision, and a permissive default committed to a repo is how
-- that decision gets made by accident.
