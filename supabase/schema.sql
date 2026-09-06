-- Royale IQ: real battle storage, Postgres/Supabase schema.
--
-- Replaces data/collected_battles.csv as the source of truth for
-- services/battle_collector.py. This is the ROOT CAUSE fix for four real
-- production incidents this session (see the clash_royale_search_oom_incident
-- memory file): every incident traced back to _load_cache() loading the
-- ENTIRE, ever-growing CSV into Python memory on first use each process
-- restart. A real database means queries are answered by Postgres's own
-- indexed lookups -- memory usage stops scaling with total historical row
-- count, which is the property that actually matters.
--
-- Column names and semantics match collected_battles.csv exactly (see
-- battle_collector.py's FIELDNAMES) so the migration script's mapping is a
-- straight 1:1 copy, not a redesign -- minimizes risk of subtly changing
-- what a "battle" means partway through 4M+ existing real rows.
--
-- Card lists (team_cards, team_evolved_cards, etc.) become real text[]
-- arrays instead of semicolon-joined strings -- lets Postgres index/query
-- "decks containing card X" directly (see the GIN index below) instead of
-- every caller doing `str(field).split(";")` in Python first.

create table if not exists battles (
  id bigserial primary key,
  battle_time timestamptz,
  game_mode text,
  team_tag text not null,
  team_name text,
  team_cards text[] not null,
  team_crowns smallint,
  team_trophies integer,
  team_avg_level real,
  opponent_tag text not null,
  opponent_name text,
  opponent_cards text[] not null,
  opponent_crowns smallint,
  opponent_trophies integer,
  opponent_avg_level real,
  result text,
  collected_at timestamptz not null,
  -- Real per-match Evolution/Hero slot usage (added 2026-07-31 in the CSV
  -- era) -- blank/empty array for older battles predating that tracking.
  team_evolved_cards text[] not null default '{}',
  team_hero_cards text[] not null default '{}',
  opponent_evolved_cards text[] not null default '{}',
  opponent_hero_cards text[] not null default '{}',
  -- Real per-match King Tower Troop + elixir-leaked (added 2026-08-01).
  team_tower_troop text,
  opponent_tower_troop text,
  team_elixir_leaked real,
  opponent_elixir_leaked real,
  -- Dual-capable cards (Knight/Musketeer/Wizard/Valkyrie) confirmed active
  -- but Evolution-vs-Hero undeterminable from real match data (see
  -- card_service.split_evolution_hero_cards's docstring).
  team_ambiguous_cards text[] not null default '{}',
  opponent_ambiguous_cards text[] not null default '{}',

  -- Matches battle_collector.py's existing _dedup_key exactly (battle_time,
  -- team_tag, opponent_tag) -- a real duplicate insert is silently ignored
  -- via ON CONFLICT DO NOTHING at the application layer, same effect as the
  -- CSV era's in-memory `keys` set, but enforced by the database itself
  -- instead of a Python set that only existed for one process's lifetime.
  constraint battles_dedup_key unique (battle_time, team_tag, opponent_tag)
);

-- Every "get this player's battles/deck history" query filters by tag --
-- this is the single most important index for the app's actual query
-- pattern (see battle_collector.py's by_team_tag grouping).
create index if not exists idx_battles_team_tag on battles (team_tag);
create index if not exists idx_battles_opponent_tag on battles (opponent_tag);

-- Player search (search_players) matches on team_name/team_tag AND
-- opponent_name/opponent_tag prefixes and substrings -- trigram indexes make
-- ILIKE '%query%' fast instead of a sequential scan, which is what CSV
-- streaming always was. Real production bug (2026-09-01): team_tag/
-- team_name had no index at all for weeks -- searches against the app's
-- own real query (which unions both sides) still did a full sequential scan
-- on that half no matter how the query itself was written, measured at
-- 9-19 seconds against 1M+ rows. Added to match the opponent side.
create extension if not exists pg_trgm;
create index if not exists idx_battles_opponent_name_trgm
  on battles using gin (opponent_name gin_trgm_ops);
create index if not exists idx_battles_opponent_tag_trgm
  on battles using gin (opponent_tag gin_trgm_ops);
create index if not exists idx_battles_team_name_trgm
  on battles using gin (team_name gin_trgm_ops);
create index if not exists idx_battles_team_tag_trgm
  on battles using gin (team_tag gin_trgm_ops);

-- Deck archetype / "decks containing card X" queries (retrain_from_collected.py,
-- meta.py's card+variant filter) -- GIN array index makes `team_cards @>
-- ARRAY['Hog Rider']`-style containment queries fast.
create index if not exists idx_battles_team_cards_gin on battles using gin (team_cards);
create index if not exists idx_battles_opponent_cards_gin on battles using gin (opponent_cards);

-- collected_at drives every "since TOWER_TROOP_TRACKING_ADDED_AT" /
-- "last 7 days" style query throughout the retrain pipeline.
create index if not exists idx_battles_collected_at on battles (collected_at);
