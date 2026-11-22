-- Fintwin production schema for Supabase Postgres.
create extension if not exists pgcrypto;

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '', organization text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table public.projects (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null, activity_type text not null, description text, stage text,
  base_config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table public.products (
  id uuid primary key default gen_random_uuid(), project_id uuid not null references public.projects(id) on delete cascade,
  name text not null, sku text, category text, price_dzd numeric(14,2), cost_dzd numeric(14,2),
  stock integer, monthly_sales integer, metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create table public.simulation_runs (
  id uuid primary key default gen_random_uuid(), project_id uuid not null references public.projects(id) on delete cascade,
  parent_run_id uuid references public.simulation_runs(id) on delete set null, scenario_name text not null,
  input_config jsonb not null, result jsonb not null, provider text not null, model text not null,
  created_at timestamptz not null default now()
);
create table public.persona_results (
  id uuid primary key default gen_random_uuid(), run_id uuid not null references public.simulation_runs(id) on delete cascade,
  persona_index integer not null, attributes jsonb not null, purchase_probability numeric(7,6) not null,
  decision text not null, payment_method text, objections jsonb not null default '[]'::jsonb,
  unique(run_id, persona_index)
);
create table public.llm_usage (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
  run_id uuid references public.simulation_runs(id) on delete set null, provider text not null, model text not null,
  status text not null, input_tokens integer not null default 0, output_tokens integer not null default 0,
  estimated_cost_usd numeric(14,8) not null default 0, latency_ms integer not null default 0,
  created_at timestamptz not null default now()
);

create index projects_owner_id_idx on public.projects(owner_id);
create index products_project_id_idx on public.products(project_id);
create index simulation_runs_project_id_idx on public.simulation_runs(project_id, created_at desc);
create index persona_results_run_id_idx on public.persona_results(run_id);
create index llm_usage_owner_id_idx on public.llm_usage(owner_id, created_at desc);

alter table public.profiles enable row level security;
alter table public.projects enable row level security;
alter table public.products enable row level security;
alter table public.simulation_runs enable row level security;
alter table public.persona_results enable row level security;
alter table public.llm_usage enable row level security;

revoke all on public.profiles, public.projects, public.products, public.simulation_runs, public.persona_results, public.llm_usage from anon;
grant select, insert, update, delete on public.profiles, public.projects, public.products, public.simulation_runs, public.persona_results, public.llm_usage to authenticated;

create policy "profiles_select_own" on public.profiles for select to authenticated using ((select auth.uid()) = id);
create policy "profiles_insert_own" on public.profiles for insert to authenticated with check ((select auth.uid()) = id);
create policy "profiles_update_own" on public.profiles for update to authenticated using ((select auth.uid()) = id) with check ((select auth.uid()) = id);
create policy "projects_select_own" on public.projects for select to authenticated using ((select auth.uid()) = owner_id);
create policy "projects_insert_own" on public.projects for insert to authenticated with check ((select auth.uid()) = owner_id);
create policy "projects_update_own" on public.projects for update to authenticated using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
create policy "projects_delete_own" on public.projects for delete to authenticated using ((select auth.uid()) = owner_id);
create policy "products_owner_access" on public.products for all to authenticated
using (exists (select 1 from public.projects p where p.id = project_id and p.owner_id = (select auth.uid())))
with check (exists (select 1 from public.projects p where p.id = project_id and p.owner_id = (select auth.uid())));
create policy "runs_owner_access" on public.simulation_runs for all to authenticated
using (exists (select 1 from public.projects p where p.id = project_id and p.owner_id = (select auth.uid())))
with check (exists (select 1 from public.projects p where p.id = project_id and p.owner_id = (select auth.uid())));
create policy "persona_owner_access" on public.persona_results for all to authenticated
using (exists (select 1 from public.simulation_runs r join public.projects p on p.id = r.project_id where r.id = run_id and p.owner_id = (select auth.uid())))
with check (exists (select 1 from public.simulation_runs r join public.projects p on p.id = r.project_id where r.id = run_id and p.owner_id = (select auth.uid())));
create policy "usage_select_own" on public.llm_usage for select to authenticated using ((select auth.uid()) = owner_id);
create policy "usage_insert_own" on public.llm_usage for insert to authenticated with check ((select auth.uid()) = owner_id);
