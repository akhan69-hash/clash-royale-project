"""
Loss-pattern classification for the Personal Coaching Hub -- the one
genuinely new piece of logic in that feature (everything else composes
already-shipped endpoints). Deliberately built from data that's actually
real and already fetched (a player's real recent battle history from
GET /players/{tag}/battles) plus the curated role taxonomy and hard-counter
table already used throughout the app -- no invented heuristics, no replay
data (the official API doesn't expose that; see cr_platform/backend/routers/
coaching.py's docstring for the full explanation of what coaching features
are and aren't achievable from real data).
"""
from collections import Counter

from utils.counter_suggester import HARD_COUNTERS, archetype_label as _archetype_label


def classify_losses(your_deck: list[str], losses: list[list[str]]) -> dict:
    """your_deck: the player's own 8-card deck. losses: a list of opponent
    decks from real battles the player lost. Returns frequency-ranked
    archetypes they lose to and specific recurring hard-counter matchups --
    both derived purely from real match-summary data + existing curated
    tables, safe to call with zero losses (empty result, not an error)."""
    archetype_counts = Counter()
    hard_counter_counts = Counter()

    for opponent_deck in losses:
        archetype_counts[_archetype_label(opponent_deck)] += 1
        for opp_card in opponent_deck:
            for beaten in HARD_COUNTERS.get(opp_card, []):
                if beaten in your_deck:
                    hard_counter_counts[(opp_card, beaten)] += 1

    total = len(losses)
    top_archetypes = [
        {"archetype": a, "count": c, "pct": round(c / total * 100, 1) if total else 0}
        for a, c in archetype_counts.most_common(8)
    ]
    top_hard_counters = [
        {"opponent_card": oc, "your_card": yc, "count": c}
        for (oc, yc), c in hard_counter_counts.most_common(8)
    ]
    return {
        "total_losses": total,
        "top_archetypes": top_archetypes,
        "top_hard_counters": top_hard_counters,
    }
