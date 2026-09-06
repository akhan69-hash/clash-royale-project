"""
Clash Royale Card Stats Auto-Scraper
=====================================
Runs LOCALLY on your machine (not in the cloud).
Scrapes per-level stats from the Clash Royale wiki and cross-checks
against your local CSV, updating it with any new or changed stats.

Usage:
    python scrape_card_stats.py                          # scrape + update CSV
    python scrape_card_stats.py --card "Knight"          # single card
    python scrape_card_stats.py --report-only            # just show diff
    python scrape_card_stats.py --schedule 3600          # run every hour

Requirements:
    pip install httpx beautifulsoup4 lxml schedule pandas
"""

import csv
import json
import time
import argparse
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Windows consoles default to cp1252, which can't encode the emoji this
# script prints (warnings/checkmarks) -- reconfigure so it doesn't crash
# mid-run on Windows regardless of the terminal's codepage.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import httpx
    from bs4 import BeautifulSoup
    import pandas as pd
    import schedule
except ImportError:
    print("Installing dependencies...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "httpx", "beautifulsoup4", "lxml", "schedule", "pandas"])
    import httpx
    from bs4 import BeautifulSoup
    import pandas as pd
    import schedule


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

CSV_PATH = Path(__file__).parent.parent / "data" / "clash_royale_master_stats.csv"
LOG_PATH = Path(__file__).parent / "scrape_log.json"

# Rough per-rarity level offset, used only to align the wiki's relative-level
# text with our CSV's absolute Level column for this standalone QA script.
# The app itself (utils/data_loader.py, cr_platform/backend) derives this
# per-card from the live API's own maxLevel instead of a hardcoded table --
# see api_level_to_csv_level() -- since this table goes stale on balance
# patches. Fine here since a human reviews --report-only output before
# anything gets applied.
RARITY_MAX_LEVEL = {
    'Common': 16, 'Rare': 14, 'Epic': 11, 'Legendary': 8, 'Champion': 6
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
}

# Map our CSV unit names → wiki page names
WIKI_NAME_MAP = {
    "Archer": "Archers",
    "Barbarian": "Barbarians",
    "Bat": "Bats",
    "Elite Barbarian": "Elite Barbarians",
    "Guard": "Guards",
    "Minion": "Minions",
    "Skeleton": "Skeletons",
    "Spear Goblin": "Spear Goblins",
    "Goblins": "Goblins",
    "Ram (Ram Rider)": "Ram_Rider",
    "Rider (Ram Rider)": "Ram_Rider",
    "Rascal Boy": "Rascals",
    "Rascal Girl": "Rascals",
}


# ─────────────────────────────────────────────────────────────────────────────
# WIKI SCRAPER
# ─────────────────────────────────────────────────────────────────────────────

class WikiScraper:
    WIKI_BASE = "https://clashroyale.fandom.com/wiki"

    def __init__(self):
        self.client = httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True)

    def get_card_page(self, card_name: str) -> Optional[BeautifulSoup]:
        """Fetch a card's wiki page."""
        wiki_name = WIKI_NAME_MAP.get(card_name, card_name.replace(" ", "_"))
        url = f"{self.WIKI_BASE}/{wiki_name}"
        try:
            resp = self.client.get(url)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, 'lxml')
            elif resp.status_code == 404:
                # Try alternate URL formats
                alt_url = f"{self.WIKI_BASE}/{card_name.replace(' ', '%20')}"
                resp2 = self.client.get(alt_url)
                if resp2.status_code == 200:
                    return BeautifulSoup(resp2.text, 'lxml')
            print(f"  ⚠️ {card_name}: HTTP {resp.status_code}")
            return None
        except Exception as e:
            print(f"  ⚠️ {card_name}: {e}")
            return None

    def parse_stats_table(self, soup: BeautifulSoup, card_name: str) -> list[dict]:
        """
        Extract per-level stats from the wiki page.
        The wiki uses tables with class 'wikitable' containing level stats.
        """
        stats = []

        # Find stats tables — wiki has a table with "Statistics" heading
        tables = soup.find_all('table', class_=['wikitable', 'article-table'])

        for table in tables:
            headers = []
            rows = table.find_all('tr')
            if not rows:
                continue

            # Parse header row
            header_row = rows[0]
            for th in header_row.find_all(['th', 'td']):
                text = th.get_text(strip=True).lower()
                headers.append(text)

            # Check if this looks like a stats table
            stat_keywords = {'level', 'hitpoints', 'damage', 'dps', 'health'}
            if not any(kw in ' '.join(headers) for kw in stat_keywords):
                continue

            # Parse data rows
            for row in rows[1:]:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue

                row_data = {}
                for i, cell in enumerate(cells):
                    if i >= len(headers):
                        break
                    text = cell.get_text(strip=True).replace(',', '').replace('−', '-')
                    header = headers[i]

                    if 'level' in header:
                        row_data['level'] = self._parse_num(text)
                    elif 'hitpoint' in header or 'health' in header or 'hp' in header:
                        row_data['hitpoints'] = self._parse_num(text)
                    elif 'damage per second' in header or 'dps' in header:
                        row_data['dps'] = self._parse_num(text)
                    elif 'damage' in header and 'crown' not in header and 'building' not in header:
                        row_data['damage'] = self._parse_num(text)
                    elif 'crown' in header:
                        row_data['crown_tower_damage'] = self._parse_num(text)

                if row_data.get('level') is not None:
                    stats.append(row_data)

        return stats

    def _parse_num(self, text: str) -> Optional[float]:
        """Parse a number from text, handling k/m suffixes."""
        text = text.strip().replace(',', '').replace(' ', '')
        if not text or text in ('—', '-', 'N/A', '?'):
            return None
        try:
            if text.endswith('k'):
                return float(text[:-1]) * 1000
            return float(text)
        except ValueError:
            return None

    def close(self):
        self.client.close()


# ─────────────────────────────────────────────────────────────────────────────
# DATA COMPARISON
# ─────────────────────────────────────────────────────────────────────────────

def compare_stats(card_name: str, scraped: list[dict], csv_df: pd.DataFrame, rarity: str) -> list[dict]:
    """
    Compare scraped stats against local CSV.
    Returns list of differences found.
    """
    diffs = []
    max_lvl = RARITY_MAX_LEVEL.get(rarity, 14)
    offset = 18 - max_lvl

    card_rows = csv_df[csv_df['Unit'] == card_name].copy()

    for scraped_row in scraped:
        wiki_rel = scraped_row.get('level')
        if wiki_rel is None:
            continue

        abs_level = int(wiki_rel) + offset
        csv_row = card_rows[card_rows['Level'] == abs_level]

        if csv_row.empty:
            diffs.append({
                'type': 'missing_level',
                'card': card_name,
                'relative_level': int(wiki_rel),
                'absolute_level': abs_level,
                'wiki_data': scraped_row
            })
            continue

        csv_r = csv_row.iloc[0]

        for stat, col in [('hitpoints', 'Hitpoints'), ('damage', 'Damage'), ('dps', 'DPS')]:
            wiki_val = scraped_row.get(stat)
            csv_val = csv_r.get(col)

            if wiki_val is None:
                continue

            try:
                csv_num = float(str(csv_val).replace(',', '')) if pd.notna(csv_val) and str(csv_val) not in ('', 'NaN') else None
            except:
                csv_num = None

            if csv_num is None:
                diffs.append({
                    'type': 'missing_stat',
                    'card': card_name,
                    'relative_level': int(wiki_rel),
                    'absolute_level': abs_level,
                    'stat': col,
                    'wiki_value': wiki_val,
                    'csv_value': None
                })
            elif abs(csv_num - wiki_val) > 1:  # tolerance of 1 for rounding
                diffs.append({
                    'type': 'value_mismatch',
                    'card': card_name,
                    'relative_level': int(wiki_rel),
                    'absolute_level': abs_level,
                    'stat': col,
                    'wiki_value': wiki_val,
                    'csv_value': csv_num,
                    'diff': wiki_val - csv_num
                })

    return diffs


def apply_updates(df: pd.DataFrame, diffs: list[dict]) -> tuple[pd.DataFrame, int]:
    """Apply scraped data to update the CSV dataframe."""
    updated = 0

    for diff in diffs:
        if diff['type'] not in ('missing_stat', 'value_mismatch'):
            continue

        card = diff['card']
        abs_level = diff['absolute_level']
        stat = diff['stat']
        value = diff['wiki_value']

        mask = (df['Unit'] == card) & (df['Level'].astype(str) == str(abs_level))
        if mask.any():
            df.loc[mask, stat] = value
            updated += 1

    return df, updated


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SCRAPE LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run_scrape(card_filter: Optional[str] = None, report_only: bool = False,
               csv_path: Path = CSV_PATH) -> dict:
    """Main scraping function."""

    print(f"\n{'='*60}")
    print(f"Clash Royale Stats Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # Load CSV
    if not csv_path.exists():
        print(f"❌ CSV not found: {csv_path}")
        return {}

    df = pd.read_csv(csv_path, low_memory=False)
    df['Level'] = pd.to_numeric(df['Level'], errors='coerce')
    print(f"Loaded {len(df)} rows from {csv_path.name}")

    # Get cards to scrape
    playable_types = ['Troop', 'Spell', 'Building', 'Champion', 'Tower Troop']
    sub_units = {
        "Ram (Ram Rider)", "Rider (Ram Rider)", "Rascal Boy", "Rascal Girl",
        "Phoenix Egg", "Lava Pups", "Elixir Golemite", "Elixir Blob",
        "Golemite", "Bush Goblin", "Cursed Hog", "Goblin Brawler",
        "Monster (Goblinstein)", "Guardian (Little Prince)", "Goblin Machine Rocket"
    }

    all_units = df[
        (df['Type'].isin(playable_types)) & (~df['Unit'].isin(sub_units))
    ]['Unit'].unique()

    if card_filter:
        cards_to_scrape = [c for c in all_units if card_filter.lower() in c.lower()]
    else:
        cards_to_scrape = list(all_units)

    print(f"Scraping {len(cards_to_scrape)} cards...\n")

    scraper = WikiScraper()
    all_diffs = []
    scraped_count = 0
    error_count = 0

    for i, card in enumerate(cards_to_scrape):
        print(f"[{i+1}/{len(cards_to_scrape)}] {card}...", end=' ')

        # Get rarity from CSV
        card_rows = df[df['Unit'] == card]
        rarity = card_rows['rarity'].iloc[0] if not card_rows.empty and 'rarity' in card_rows.columns else 'Rare'
        rarity = str(rarity).title() if pd.notna(rarity) else 'Rare'

        # Scrape wiki
        soup = scraper.get_card_page(card)
        if soup is None:
            print("❌ (wiki page not found)")
            error_count += 1
            continue

        stats = scraper.parse_stats_table(soup, card)
        if not stats:
            print("⚠️ (no stats table found)")
            error_count += 1
            continue

        # Compare
        diffs = compare_stats(card, stats, df, rarity)
        all_diffs.extend(diffs)
        scraped_count += 1

        if diffs:
            mismatches = [d for d in diffs if d['type'] == 'value_mismatch']
            missing = [d for d in diffs if d['type'] == 'missing_stat']
            print(f"✓ ({len(diffs)} issues: {len(mismatches)} mismatches, {len(missing)} missing)")
        else:
            print("✓ (all match)")

        # Rate limit — be polite to the wiki
        time.sleep(0.5)

    scraper.close()

    # Report
    print(f"\n{'─'*60}")
    print(f"RESULTS: {scraped_count} scraped, {error_count} errors, {len(all_diffs)} total differences")

    if all_diffs:
        mismatches = [d for d in all_diffs if d['type'] == 'value_mismatch']
        missing = [d for d in all_diffs if d['type'] == 'missing_stat']
        print(f"  Value mismatches: {len(mismatches)}")
        print(f"  Missing stats:    {len(missing)}")

        if mismatches:
            print("\nTop mismatches:")
            for d in mismatches[:10]:
                print(f"  {d['card']} lvl{d['relative_level']} {d['stat']}: "
                      f"wiki={d['wiki_value']}, csv={d['csv_value']} (diff={d.get('diff',0):+.0f})")

    # Apply updates
    if not report_only and all_diffs:
        print(f"\nApplying {len(all_diffs)} updates to CSV...")
        df, updated = apply_updates(df, all_diffs)
        df.to_csv(csv_path, index=False)
        print(f"✓ Updated {updated} values in {csv_path.name}")

        # Save log
        log = {
            'timestamp': datetime.now().isoformat(),
            'cards_scraped': scraped_count,
            'errors': error_count,
            'updates_applied': updated,
            'diffs': all_diffs[:50]  # save first 50 for review
        }
        LOG_PATH.write_text(json.dumps(log, indent=2))
        print(f"✓ Log saved to {LOG_PATH.name}")
    elif report_only:
        print("\n(Report only — no changes made. Run without --report-only to apply.)")

    return {'scraped': scraped_count, 'errors': error_count, 'diffs': len(all_diffs)}


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────────────────────────────────────

def run_scheduled(interval_seconds: int):
    """Run the scraper on a schedule."""
    print(f"Scheduling scrape every {interval_seconds} seconds...")
    schedule.every(interval_seconds).seconds.do(run_scrape)
    run_scrape()  # Run immediately first
    while True:
        schedule.run_pending()
        time.sleep(60)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CR Card Stats Auto-Scraper")
    parser.add_argument('--card', help='Scrape a single card only')
    parser.add_argument('--report-only', action='store_true',
                        help='Show differences without modifying CSV')
    parser.add_argument('--schedule', type=int, metavar='SECONDS',
                        help='Run continuously every N seconds (e.g. 3600 for hourly)')
    parser.add_argument('--csv', default=str(CSV_PATH),
                        help='Path to your CSV file')
    args = parser.parse_args()

    csv_path = Path(args.csv)

    if args.schedule:
        run_scheduled(args.schedule)
    else:
        run_scrape(
            card_filter=args.card,
            report_only=args.report_only,
            csv_path=csv_path
        )
