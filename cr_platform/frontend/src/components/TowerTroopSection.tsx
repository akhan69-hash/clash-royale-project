import Collapsible from './Collapsible'
import CardImage from './CardImage'

/**
 * Real feedback (2026-08-23): "there should be a collapsible tab on decks
 * shown that will show the tower, maybe cannonier or tower princess or
 * ducchess, real stat." Backed by real per-match King Tower Troop data
 * (team_tower_troop, tracked since 2026-08-01) -- see
 * scripts/retrain_from_collected.py's _typical_tower_troop and
 * battle_collector.py's get_player_deck_history. `d.typical_tower_troop` is
 * the troop most often actually played with this exact deck across its
 * tracked real games, with `tower_troop_rate_pct` (how often) and
 * `tower_troop_win_rate_pct` (that troop's own real win rate in this deck) --
 * None (component renders nothing) until 5+ tracked sightings exist, same
 * reliability floor as the Evolution/Hero typical-card fields.
 *
 * One shared component instead of re-copy-pasting this block into every
 * deck-card renderer (Top Decks, counter decks, My Decks, Arena decks,
 * Favorites) -- real feedback elsewhere in the same batch: "i do not want
 * repeated features."
 */
export default function TowerTroopSection({ d }: { d: any }) {
  if (!d?.typical_tower_troop) return null
  return (
    <Collapsible title={`🏰 Tower Troop: ${d.typical_tower_troop}`} compact>
      <div className="flex items-center gap-2 text-[10px] text-text-muted">
        <CardImage name={d.typical_tower_troop} imageUrl={d.tower_troop_image_url} size="xs" showName={false} />
        <span>
          Used in {d.tower_troop_rate_pct}% of this deck's tracked real games
          {d.tower_troop_win_rate_pct != null && (
            <> · <span className="text-text-secondary font-medium">{d.tower_troop_win_rate_pct}% WR</span> with it</>
          )}
        </span>
      </div>
    </Collapsible>
  )
}
