-- Supabase schema for public fan voting.
-- Run this in Supabase SQL Editor.

create table if not exists fan_votes (
    id uuid primary key default gen_random_uuid(),
    favorite_team text not null,
    surprise_team text,
    top_scorer text,
    group_of_death text,
    confidence integer check (confidence >= 1 and confidence <= 10),
    user_country text,
    display_name text,
    created_at timestamp with time zone default now()
);

alter table fan_votes enable row level security;

-- Anyone can insert a vote. Keep the table anonymous, no sensitive data.
drop policy if exists "Public can insert fan votes" on fan_votes;
create policy "Public can insert fan votes"
on fan_votes
for insert
to anon, authenticated
with check (true);

-- Anyone can read aggregated/public vote data through the app.
drop policy if exists "Public can read fan votes" on fan_votes;
create policy "Public can read fan votes"
on fan_votes
for select
to anon, authenticated
using (true);

create index if not exists fan_votes_created_at_idx on fan_votes(created_at desc);
create index if not exists fan_votes_favorite_team_idx on fan_votes(favorite_team);
