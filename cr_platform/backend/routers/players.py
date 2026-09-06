import itertools
import pandas as pd
from fastapi import APIRouter, HTTPException, Header
import httpx
import os
from services.card_service import (
    get_card_at_relative_level, get_card_image_url, get_max_level, get_rarity_map, normalize_card_name,
    get_unlocked_slots, split_evolution_hero_cards, get_evolution_hero_map,
)
from services.battle_collector import save_battles, get_player_deck_history, get_likely_variant_for_card, search_players
from utils.data_loader import api_level_to_csv_level as api_to_absolute
from routers.synergy import get_synergy_score
from routers.meta import _load_card_stats_df, _strategy_fields, _load_deck_estimate_lookup
from routers.decks import MIN_USES_FOR_CARD_STAT

router = APIRouter()
CR_API_BASE = "https://api.clashroyale.com/v1"


def get_api_key(authorization: str = Header(None)) -> str:
    # Try header first, then env. A caller-supplied header with an empty
    # token ("Bearer " with nothing after it) falls through to the server
    # key too, same as no header at all -- otherwise a stray empty client
    # key would silently shadow the real, working server-side one.
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    key = os.getenv("CR_API_KEY", "")
    if not key:
        raise HTTPException(status_code=401, detail="CR API key required. Set CR_API_KEY env or pass Authorization header.")
    return key


@router.get("/search")
def search_players_endpoint(q: str = "", limit: int = 8):
    """Search-ahead over everyone this app has ever seen (as a directly
    looked-up player or a real opponent) by name or partial tag -- real
    feedback (2026-08-21): "why not try to use search queries... might help
    the player not to type the whole thing in." Registered ABOVE the
    /{tag} catch-all route below (route order matters in FastAPI/Starlette:
    a literal path segment must be registered before a path-parameter route
    that would otherwise swallow it -- a GET to /search would incorrectly
    match /{tag} with tag="search" if this were declared after it)."""
    return {"results": search_players(q, limit)}


@router.get("/{tag}")
async def get_player(tag: str, authorization: str = Header(None)):
    api_key = get_api_key(authorization)
    tag = tag.lstrip("#").upper()

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{CR_API_BASE}/players/%23{tag}",
            headers={"Authorization": f"Bearer {api_key}"}
        )

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Player #{tag} not found")
    if resp.status_code == 403:
        raise HTTPException(status_code=403, detail="Invalid API key or IP not whitelisted")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="CR API error")

    data = resp.json()
    rarity_map = get_rarity_map()

    # Enrich current deck with our stats. The CR API reports each card's level
    # relative to that card's own maxLevel, and includes maxLevel directly on
    # each deck entry -- prefer that real per-card value over our rarity-based
    # table, same as pages/4_Live_API.py in the Streamlit app.
    #
    # CORRECTED 2026-08-06: `currentDeck` DOES carry a real `evolutionLevel`
    # field per card (an earlier claim that it never does was wrong), BUT
    # directly re-verified against a real account (2026-08-06) that this
    # field is NOT "is this card actively Evolution/Hero-slotted in this
    # deck build" -- it's identical, card-for-card, to that same card's
    # SHARD-OWNERSHIP level on the player's owned-collection entry (e.g. a
    # deck can show 6 different cards all with a truthy evolutionLevel,
    # which is impossible for real gameplay -- max is ~2-3 special slots).
    # A same-session fix that applied split_evolution_hero_cards() to
    # currentDeck was wrong for this reason and has been reverted here.
    # The only honest source for "what's actually evolved/hero'd in this
    # exact deck" is this player's own real, tracked battle history for the
    # exact same 8 cards (get_player_deck_history) -- prefer whichever real,
    # tracked variant they've played most, and if there's no tracked match
    # yet, leave evolved/hero unset rather than guessing.
    own_deck_history = get_player_deck_history(tag)
    current_deck_cards_sorted = tuple(sorted(
        normalize_card_name(c.get("name", "")) for c in data.get("currentDeck", [])
    ))
    matching_variants = [
        d for d in own_deck_history
        if d["variant_known"] and tuple(sorted(d["cards"])) == current_deck_cards_sorted
    ]
    best_variant = max(matching_variants, key=lambda d: d["times_played"], default=None)
    evolved_in_deck = set(best_variant["evolved_cards"]) if best_variant else set()
    hero_in_deck = set(best_variant["hero_cards"]) if best_variant else set()
    ambiguous_in_deck = set(best_variant["ambiguous_cards"]) if best_variant else set()
    deck = []
    for card in data.get("currentDeck", []):
        name = normalize_card_name(card.get("name", ""))
        api_level = card.get("level", 1)
        rarity = card.get("rarity", rarity_map.get(name, "Rare")).title()
        max_lvl = card.get("maxLevel") or get_max_level(name, rarity)
        abs_level = api_to_absolute(api_level, max_lvl)
        relative = api_level  # API already returns relative level

        local_stats = get_card_at_relative_level(name, relative)
        deck.append({
            "name": name,
            "api_level": api_level,
            "relative_level": relative,
            "absolute_level": abs_level,
            "max_level": max_lvl,
            "rarity": rarity,
            "elixir_cost": card.get("elixirCost"),
            "image_url": get_card_image_url(name),
            "is_evolved": name in evolved_in_deck,
            "is_hero": name in hero_in_deck,
            # True for dual-capable cards (Knight/Musketeer/Wizard/Valkyrie)
            # confirmed actively evolved-or-hero'd in real tracked battles
            # with this exact deck, but where which of the two systems can't
            # be determined -- see split_evolution_hero_cards's docstring.
            "is_ambiguous": name in ambiguous_in_deck,
            "stats": local_stats,
        })

    # Enrich cards collection
    evo_hero_map = get_evolution_hero_map()
    cards_enriched = []
    for card in data.get("cards", []):
        name = normalize_card_name(card.get("name", ""))
        api_level = card.get("level", 1)
        rarity = card.get("rarity", rarity_map.get(name, "Rare")).title()
        max_lvl = card.get("maxLevel") or get_max_level(name, rarity)
        # Real Evolution/Hero shard ownership -- the API reports this on the
        # OWNED collection entry too (not just battlelog), as evolutionLevel/
        # maxEvolutionLevel (shards invested / shards needed for max tier),
        # cross-referenced against card_reference.csv's has_evolution/has_hero
        # to know which system(s) this card's shards apply to. For the small
        # set of dual-capable cards (Knight, Musketeer, Wizard, Valkyrie),
        # the API doesn't expose which pool this specific number belongs to,
        # so both are shown together rather than guessing one.
        has_evo, has_hero = evo_hero_map.get(name, (False, False))
        shard_level = card.get("evolutionLevel")
        shard_max = card.get("maxEvolutionLevel")
        owns_evo_shards = has_evo and bool(shard_level)
        owns_hero = has_hero and bool(shard_level)

        # For the 4 dual-capable cards where the static API field is
        # genuinely ambiguous (both true above), see if this player's own
        # tracked real battle history has evidence of which pool it's
        # actually in -- see get_likely_variant_for_card's docstring for why
        # this is evidence-based, not a repeat of the disproven guess.
        likely = get_likely_variant_for_card(tag, name) if (owns_evo_shards and owns_hero) else None

        cards_enriched.append({
            "name": name,
            "api_level": api_level,
            "absolute_level": api_to_absolute(api_level, max_lvl),
            "max_level": max_lvl,
            "levels_to_max": max_lvl - api_level,
            "pct_to_max": round(api_level / max_lvl * 100, 1),
            # Real owned copy count -- real feedback (2026-08-27): "the
            # collections should include the number of upgrades on the card
            # like 100/1000 for lets say valkyrie." The API gives us real
            # owned copies (`count`) directly; it does NOT give a "copies
            # needed for next level" figure anywhere (confirmed via a fresh
            # raw API dump) -- that's static game-balance data this app
            # doesn't have a verified, current table for yet (the real
            # numbers keep changing -- Level 15/16 were both new economy
            # reworks in the last year), so only the real owned count is
            # shown for now rather than guessing the "/1000" target.
            "count": card.get("count"),
            "rarity": rarity,
            "image_url": get_card_image_url(name),
            "has_evolution": has_evo,
            "has_hero": has_hero,
            "owns_evolution_shards": owns_evo_shards,
            "owns_hero_unlock": owns_hero,
            "shard_level": shard_level,
            "shard_max": shard_max,
            "likely_variant": likely["likely_variant"] if likely else None,
            "likely_variant_confidence": likely["likely_variant_confidence"] if likely else None,
        })

    # Tower Troops (King Tower skin) -- a separate field the API never mixes into
    # currentDeck/cards, so it was previously missing from the app entirely.
    def _enrich_tower_troop(card: dict) -> dict:
        name = normalize_card_name(card.get("name", ""))
        api_level = card.get("level", 1)
        rarity = card.get("rarity", rarity_map.get(name, "Common")).title()
        max_lvl = card.get("maxLevel") or get_max_level(name, rarity)
        return {
            "name": name,
            "api_level": api_level,
            "absolute_level": api_to_absolute(api_level, max_lvl),
            "max_level": max_lvl,
            "rarity": rarity,
            "image_url": get_card_image_url(name),
        }

    current_tower_troop = next(
        (_enrich_tower_troop(c) for c in data.get("currentDeckSupportCards", [])), None
    )
    tower_troops = [_enrich_tower_troop(c) for c in data.get("supportCards", [])]

    wins = data.get("wins", 0)
    losses = data.get("losses", 0)
    total = wins + losses

    return {
        "tag": f"#{tag}",
        "name": data.get("name"),
        "trophies": data.get("trophies"),
        "best_trophies": data.get("bestTrophies"),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
        "three_crown_wins": data.get("threeCrownWins"),
        "king_level": data.get("expLevel"),
        "clan": data.get("clan", {}).get("name"),
        "unlocked_slots": get_unlocked_slots(data.get("bestTrophies")),
        "current_deck": deck,
        # Whether the is_evolved/is_hero flags above came from a real,
        # tracked match with this exact deck (see comment above) -- false
        # means no such match exists yet, so every is_evolved/is_hero on
        # this deck is honestly false rather than guessed.
        "current_deck_variant_known": best_variant is not None,
        "cards": cards_enriched,
        "current_tower_troop": current_tower_troop,
        "tower_troops": tower_troops,
        "favourite_card": data.get("currentFavouriteCard", {}).get("name"),
        # Real global Path of Legends rank -- confirmed via direct API test
        # (2026-08-01): only populated when a player actually places on the
        # global leaderboard that season, null otherwise (there's no browsable
        # "world" player leaderboard in the API, see rankings.py's docstring --
        # this is the honest substitute: the player's own real rank, if any).
        "global_rank": (data.get("currentPathOfLegendSeasonResult") or {}).get("rank"),
        "best_global_rank": (data.get("bestPathOfLegendSeasonResult") or {}).get("rank"),
        # Real per-season fields -- distinct from `trophies` (that's
        # lifetime/current-arena trophies, unaffected by season resets).
        # Real feedback (2026-08-26): "Add your season level on Player
        # feature." leagueStatistics.currentSeason is the classic seasonal
        # trophy count (resets each season, real Supercell field, confirmed
        # via a direct API response check). Path of Legend's leagueNumber is
        # its own separate real ladder (1-10) -- global_rank above is the
        # PLACEMENT within it, this is which league tier the player is in.
        "season_trophies": (data.get("leagueStatistics") or {}).get("currentSeason", {}).get("trophies"),
        "season_best_trophies": (data.get("leagueStatistics") or {}).get("currentSeason", {}).get("bestTrophies"),
        "path_of_legend_league": (data.get("currentPathOfLegendSeasonResult") or {}).get("leagueNumber"),
        # Newer "Seasonal Arena" trophy road (separate from the classic arena
        # ladder) -- lives under the real `progress` map, keyed by a dynamic
        # per-season id ("seasonal-trophy-road-202608"); picking the
        # lexicographically-latest such key is the current season's entry
        # since that id embeds year+month. `arena.name` is the real,
        # official name Supercell gives this season's arena tier.
        "seasonal_arena": _current_seasonal_arena(data.get("progress") or {}),
    }


def _current_seasonal_arena(progress: dict) -> dict | None:
    keys = sorted(k for k in progress if k.startswith("seasonal-trophy-road-"))
    if not keys:
        return None
    entry = progress[keys[-1]]
    return {
        "name": (entry.get("arena") or {}).get("name"),
        "trophies": entry.get("trophies"),
        "best_trophies": entry.get("bestTrophies"),
    }


def _avg_absolute_level(raw_cards: list[dict]) -> float | None:
    """Average real absolute card level for one side of a battle -- a much
    more reliable signal of account maturity than current trophies, since
    trophies swing with season resets / deliberate trophy-dropping while
    unlocked card levels only ever go up. Used to sanity-check the arena
    breakdown (see utils/arena_data.py and the Arena tab caveat)."""
    rarity_map = get_rarity_map()
    levels = []
    for c in raw_cards:
        name = normalize_card_name(c.get("name", ""))
        max_lvl = get_max_level(name, rarity_map.get(name, "Common"))
        levels.append(api_to_absolute(c.get("level", 1), max_lvl))
    return round(sum(levels) / len(levels), 2) if levels else None


def _tower_troop_name(side: dict) -> str | None:
    """Real King Tower Troop actually used in this specific battle -- the
    battlelog's supportCards field (confirmed via direct API inspection
    2026-08-01), distinct from a player's owned supportCards list."""
    support = side.get("supportCards") or []
    if not support:
        return None
    return normalize_card_name(support[0].get("name", "")) or None


@router.get("/{tag}/battles")
async def get_battles(tag: str, authorization: str = Header(None)):
    api_key = get_api_key(authorization)
    tag = tag.lstrip("#").upper()

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{CR_API_BASE}/players/%23{tag}/battlelog",
            headers={"Authorization": f"Bearer {api_key}"}
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Could not fetch battle log")

    battles = resp.json()
    results = []
    for b in battles[:25]:
        team = b.get("team", [{}])[0]
        opponent = b.get("opponent", [{}])[0]
        team_crowns = team.get("crowns", 0)
        opp_crowns = opponent.get("crowns", 0)
        your_evolved, your_hero, your_ambiguous = split_evolution_hero_cards(team.get("cards", []))
        opponent_evolved, opponent_hero, opponent_ambiguous = split_evolution_hero_cards(opponent.get("cards", []))
        results.append({
            "type": b.get("type", ""),
            "battle_time": b.get("battleTime", ""),
            "result": "Win" if team_crowns > opp_crowns else ("Loss" if team_crowns < opp_crowns else "Draw"),
            "crowns": f"{team_crowns}-{opp_crowns}",
            "your_trophies": team.get("startingTrophies"),
            # Real bug found 2026-08-27: search_players() could never find a
            # player by name if they'd only ever been looked up directly --
            # their own real name was never captured anywhere (only
            # opponents' names, from the OTHER side of a battle). The
            # battlelog's own "team" entry already carries the looked-up
            # player's real name for free (no extra API call) -- save_battles
            # below now writes it into team_name so it becomes searchable
            # the first time this player is looked up, not only once someone
            # else's battle happens to mention them.
            "your_name": team.get("name"),
            "opponent_name": opponent.get("name"),
            "opponent_tag": opponent.get("tag"),
            "opponent_trophies": opponent.get("startingTrophies"),
            "your_deck": [normalize_card_name(c.get("name", "")) for c in team.get("cards", [])],
            "opponent_deck": [normalize_card_name(c.get("name", "")) for c in opponent.get("cards", [])],
            "your_avg_level": _avg_absolute_level(team.get("cards", [])),
            "opponent_avg_level": _avg_absolute_level(opponent.get("cards", [])),
            # Real per-match Evolution/Hero slot usage -- evolutionLevel > 0 on a
            # card entry means it was actively slotted in THIS battle (not just
            # shard-owned); see services/card_service.split_evolution_hero_cards.
            # "ambiguous" = confirmed active but the API gives no way to tell
            # Evolution from Hero for that specific card (Knight/Musketeer/
            # Wizard/Valkyrie only -- the only cards capable of both).
            "your_evolved": your_evolved,
            "your_hero": your_hero,
            "your_ambiguous": your_ambiguous,
            "opponent_evolved": opponent_evolved,
            "opponent_hero": opponent_hero,
            "opponent_ambiguous": opponent_ambiguous,
            # Real per-battle Tower Troop + elixir-leaked (confirmed real fields
            # via direct API inspection 2026-08-01 -- supportCards[0] is the
            # actual King Tower Troop used in THIS match; elixirLeaked is a
            # real per-side aggregate, unlike card placement/live trades which
            # still aren't exposed anywhere in this API).
            "your_tower_troop": _tower_troop_name(team),
            "opponent_tower_troop": _tower_troop_name(opponent),
            "your_elixir_leaked": team.get("elixirLeaked"),
            "opponent_elixir_leaked": opponent.get("elixirLeaked"),
            # Real per-battle tower HP -- there's no separate "tower level" field in the
            # API anymore (Supercell decoupled it from a flat stat in the May 2026 rework),
            # so this is the raw, real value rather than an invented level number.
            "your_king_tower_hp": team.get("kingTowerHitPoints"),
            "your_princess_towers_hp": team.get("princessTowersHitPoints"),
            "opponent_king_tower_hp": opponent.get("kingTowerHitPoints"),
            "opponent_princess_towers_hp": opponent.get("princessTowersHitPoints"),
        })

    new_count = save_battles(tag, results)
    return {"battles": results, "count": len(results), "newly_collected": new_count}


@router.get("/{tag}/decks")
def player_decks(tag: str):
    """Real, EXACT decks THIS specific player has actually used, across every
    battle they've been looked up or crawled for -- not just their single
    currently-equipped deck (see get_player() above) and not capped at the
    live API's 25-battle window like /battles. Players run multiple decks;
    each real deck here carries its own real win rate, cycle cost, and the
    exact cards that were really Evolution/Hero-slotted for THAT specific
    group of real games (see battle_collector.get_player_deck_history) --
    a deck played with Hero Knight and the same deck played with Regular
    Knight are two separate entries, not blended. Requires having looked
    this player up (or the crawler having reached them) at least once
    already -- returns an empty list otherwise, not an error, since 'no
    data collected yet' is a normal, honest state."""
    tag = tag.lstrip("#").upper()
    decks = get_player_deck_history(tag)
    if not decks:
        return {"decks": [], "note": "No collected battles for this player yet -- look them up via Player Lookup first."}

    # Real synergy score (average of all 28 real pairwise synergy lookups,
    # same computation Analytics' Top Decks "Best Synergy" sort uses -- see
    # meta.py's top_decks) and MVP card (the deck's highest real overall win
    # rate card, same definition as decks.py's counter-deck mvp_card) for each
    # of THIS player's own decks -- a much smaller list than the app-wide
    # top-decks table, so computing both eagerly for every deck is cheap.
    card_stats_df = _load_card_stats_df()
    card_win_rates = {}
    if card_stats_df is not None:
        reliable = card_stats_df[card_stats_df["times_used"] >= MIN_USES_FOR_CARD_STAT]
        card_win_rates = dict(zip(reliable["card_name"], reliable["win_rate"]))

    deck_estimates = _load_deck_estimate_lookup()
    for d in decks:
        cards = d["cards"]
        pair_scores = [get_synergy_score(a, b) for a, b in itertools.combinations(cards, 2)]
        d["synergy_score"] = round(sum(pair_scores) / len(pair_scores), 2) if pair_scores else None
        cards_detail = [
            {"name": name, "win_rate": round(card_win_rates[name] * 100, 1) if name in card_win_rates else None}
            for name in cards
        ]
        mvp = max((cd for cd in cards_detail if cd["win_rate"] is not None),
                  key=lambda cd: cd["win_rate"], default=None)
        d["cards_detail"] = cards_detail
        d["mvp_card"] = mvp["name"] if mvp else None

        # Reliability: a player's own exact deck can easily have fewer real
        # games than even the app-wide meta tables (it's one person's
        # history) -- same real-strategy-pooled + model-estimated numbers
        # shown alongside real win rate everywhere else, so a small personal
        # sample isn't the only signal here either.
        d.update(_strategy_fields(cards))
        deck_key = ";".join(sorted(cards))
        estimate = deck_estimates.get(deck_key)
        d["estimated_win_rate"] = round(float(estimate) * 100, 2) if estimate is not None and pd.notna(estimate) else None
        if d.get("typical_tower_troop"):
            d["tower_troop_image_url"] = get_card_image_url(d["typical_tower_troop"])

    return {"decks": decks}
