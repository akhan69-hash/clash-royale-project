# Clash Royale Deck Builder & Analytics

A Streamlit-powered deck builder and data analysis tool using real per-level card stats.

## Project Structure

```
clash_royale_project/
├── app.py                  # Main Streamlit app (deck builder)
├── requirements.txt        # Python dependencies
├── README.md
├── data/
│   └── clash_royale_master_stats.csv   # Per-level stats for all cards
├── pages/                  # Additional Streamlit pages (coming soon)
│   └── (placeholder)
└── utils/
    ├── data_loader.py      # CSV loading + card data access
    └── deck_analysis.py    # Deck metrics + synergy analysis
```

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the app**
   ```bash
   streamlit run app.py
   ```

3. **Open in browser** — Streamlit will auto-open `http://localhost:8501`

## Features (Phase 1)

- **Deck Builder** — pick 8 cards, set levels, get instant analysis
- **Card Stats Viewer** — see any stat plotted across all 18 levels
- **Card Compare** — side-by-side comparison of two cards at chosen levels

## Roadmap

### Phase 2 — Data Analysis (Jupyter)
- [ ] Win rate by card (from Season 18 match dataset)
- [ ] Card synergy co-occurrence matrix
- [ ] Deck archetype clustering (K-means)
- [ ] Elixir efficiency model

### Phase 3 — Advanced Features
- [ ] Official API integration (live player data)
- [ ] Counter deck suggester
- [ ] Meta tracker (live usage + win rates)
- [ ] Player collection builder (input tag → see buildable decks)

## Data

Stats sourced manually from in-game data across 130 cards, levels 1–18.
Columns include: Hitpoints, Damage, DPS, Crown Tower Damage, Charge Damage,
Shield Hitpoints, Death Damage, Heal values, Spawn Damage, Jump Damage, and more.
