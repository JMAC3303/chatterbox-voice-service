-- ============================================================================
-- City Center Voice Service — shared-DB schema (project tsnbktwryvnbmgsvzxdt).
-- Apply centrally. Tables are read by the LDOS Admin-CMS "Voice Service" page
-- to manage the Atlantic server and track usage across the whole tech stack.
-- ============================================================================

-- --- Registered voices (zero-shot reference samples) -----------------------
-- One row per cloned/registered voice. The sample lives (private) in the
-- voice-samples bucket; voice_id is that storage path.
create table if not exists public.voice_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  voice_id text not null,               -- storage path in voice-samples
  display_name text,
  app text,                             -- which LDOS app registered it
  created_at timestamptz not null default now(),
  unique (user_id, voice_id)
);
alter table public.voice_profiles enable row level security;
create policy "voice_profiles_owner_all" on public.voice_profiles
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- --- Usage log (append-only) -----------------------------------------------
-- One row per synthesis/clone call. Powers the Admin-CMS usage dashboard and
-- per-app / per-tenant cost tracking. Written server-side by the voice service
-- (service role); never written by clients.
create table if not exists public.voice_usage (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  app text,                             -- X-Client-App header (prayer-life, speak-life, …)
  operation text not null,              -- 'tts' | 'clone'
  characters integer not null default 0,
  audio_seconds numeric,
  cache_hit boolean not null default false,
  model_variant text,                   -- turbo | original | multilingual
  latency_ms integer,
  created_at timestamptz not null default now()
);
alter table public.voice_usage enable row level security;
-- No client policies: inserts are service-role only; the Admin-CMS reads via a
-- service-role backend, not the browser.

create index if not exists voice_usage_created_at_idx on public.voice_usage (created_at desc);
create index if not exists voice_usage_app_idx on public.voice_usage (app, created_at desc);
create index if not exists voice_usage_user_idx on public.voice_usage (user_id, created_at desc);

-- --- Service config (single row) -------------------------------------------
-- Lets the Admin-CMS manage the Atlantic deployment without a redeploy:
-- default model, per-app enablement, rate/char caps, and a maintenance flag.
create table if not exists public.voice_service_config (
  id integer primary key default 1 check (id = 1),
  default_variant text not null default 'turbo',
  max_tts_chars integer not null default 2000,
  daily_char_budget_per_user integer not null default 200000,
  enabled_apps text[] not null default array['prayer-life']::text[],
  maintenance_mode boolean not null default false,
  atlantic_endpoint text,               -- informational; the live host URL
  updated_at timestamptz not null default now(),
  updated_by uuid
);
alter table public.voice_service_config enable row level security;

-- Platform-admin predicate. Other ecosystem migrations (Music LIFE Daily
-- phase-1, Speak LIFE bucket-2) also define one; whichever lands first wins,
-- so this only creates it when the shared DB doesn't have it yet. Fallback
-- definition: super_admin via JWT app_metadata (what the Admin-CMS server
-- middleware reads) or via public.user_roles when that table exists.
do $$
begin
  if not exists (
    select 1 from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname = 'is_platform_admin'
  ) then
    execute $fn$
      create function public.is_platform_admin()
      returns boolean
      language plpgsql stable security definer
      set search_path = public, pg_catalog
      as $body$
      begin
        if coalesce((auth.jwt() -> 'app_metadata' ->> 'role') = 'super_admin', false) then
          return true;
        end if;
        if to_regclass('public.user_roles') is not null then
          return exists (
            select 1 from public.user_roles
            where user_id = auth.uid() and role = 'super_admin'
          );
        end if;
        return false;
      end;
      $body$
    $fn$;
    execute 'grant execute on function public.is_platform_admin() to authenticated';
  end if;
end $$;

-- Read/write only by platform admins (the Admin-CMS edits this row through
-- its service-role backend, which bypasses RLS; this policy is the
-- defense-in-depth path for direct client access).
create policy "voice_config_admin_all" on public.voice_service_config
  for all using (public.is_platform_admin()) with check (public.is_platform_admin());

insert into public.voice_service_config (id) values (1)
  on conflict (id) do nothing;
