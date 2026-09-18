# Hack Night Starter Project - World Cup Predictor Agent

Predict 2026 World Cup matches using live data from the tournament happening right now. You'll build a **World Cup Predictor agent** that you can ask things like:

> *"Predict the upcoming Brazil vs Scotland match"*
> *"Compare France and Argentina based on their 2026 results so far"*
> *"When does England play next and what's their form?"*

The agent pulls live stats from Elasticsearch, reasons over them, and gives you a structured prediction with scoreline, key factors, and confidence level. It can also answer fuzzy, descriptive questions like *"find the most dramatic comebacks"* using **hybrid search** (lexical + semantic vector search) over natural-language match stories.

### ⚡ Option 0 - One script does everything (recommended)

```bash
pip install -r requirements.txt
export ELASTIC_ENDPOINT="https://your-project.es.region.aws.elastic.cloud"
export ELASTIC_API_KEY="your-elastic-api-key"
python setup_hacknight.py
```

This ingests both indices (`wc2026_matches` and `wc2026_match_stories`), creates all four Agent Builder tools via the Kibana API, and creates the agent. Open **Kibana → Agents** and start chatting. Use `--data-only` or `--agent-only` to run just one half.

Prefer to build it step by step? The project has two parts:

- **Part 1 - Notebook (or the script):** fetch live 2026 match data from a public API and ingest it into Elasticsearch
- **Part 2 - Agent Builder:** build a conversational AI agent on top of that data inside Kibana — no extra code, LLM included

Run the notebook (or script) first to populate the indices, then move to Agent Builder.

---

### Teams in the Dataset

All 48 qualified nations from the 2026 World Cup - including `Brazil`, `Germany`, `France`, `Argentina`, `Spain`, `England`, `USA`, `Mexico`, `Canada`, `Morocco`, `Japan`, `Portugal`, and more.

The index includes both completed results and upcoming fixtures, so the agent can answer questions about form, schedules, and predictions.

---

### Prerequisites

- **Elastic Serverless** project (sign up at [Elastic Cloud Serverless free-trial](https://www.elastic.co/cloud/cloud-trial-overview))

---

### Part 1 - Notebook

[world_cup_predictor.ipynb](world_cup_predictor.ipynb)

Run this first - it fetches live 2026 data and ingests it. All queries and analysis happen in Agent Builder (Part 2). The notebook's only job is to populate the index.

#### Option A - Google Colab (recommended, no install needed)

The fastest way to get started. Just a browser - no Python install required.

1. Download the notebook
2. Go to [colab.research.google.com](https://colab.research.google.com)
3. Click **File → Upload notebook** and upload `world_cup_predictor.ipynb`
4. Fill in your credentials in the Section 1 cell (see below)
5. Click **Runtime → Run all** to run every cell top to bottom

That's it. Colab handles all the dependencies automatically when the first cell runs `pip install`.

---

#### Option B - Run locally

If you'd prefer to run on your own machine:

**Requirements:** Python 3.9+ with pip installed. Check with `python --version` in a terminal.

```bash
# Install Jupyter and dependencies
pip install jupyter elasticsearch requests

# Launch Jupyter and open the notebook
jupyter notebook world_cup_predictor.ipynb
```

This opens a browser tab. Run cells one at a time with **Shift + Enter**, or run all at once via **Cell → Run All**.

---

#### Filling in your credentials

Whichever option you use, fill in these two values in the Section 1 cell before running:

```python
ELASTIC_ENDPOINT = "https://your-project.es.region.aws.elastic.cloud"
ELASTIC_API_KEY  = "your-elastic-api-key"
```

> **Finding your credentials:** Elastic Cloud Console → Your Project → Connection Details

#### What the notebook does

**Section 1 - Connect** to Elastic Serverless.

**Section 2 - Fetch live data** from [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) - a public domain GitHub repo updated daily with real 2026 results. No API key required. Both completed results and upcoming fixtures are fetched and printed so you can see what's in the data.

**Section 3 - Create index** `wc2026_matches` with explicit mappings, including a nested `goals` field capturing scorer name, minute, team, and goal type.

**Section 4 - Enrich and ingest** all matches. Computed fields added at ingest: `status` (played/upcoming), `winner`, `total_goals`, `team1_win`, `team2_win`, `stage`.

**Section 5 - Verify** with quick sense-check queries confirming the data landed correctly. This is the last step in the notebook - building the agent happens in Part 2.

**To refresh with latest results:** re-run cells 2-4. The index is dropped and recreated each time so there are no duplicates. Takes about 30 seconds.

#### Index schema - `wc2026_matches`

| Field | Type | Notes |
|---|---|---|
| `date` | date | Match date |
| `round` | keyword | e.g. `Matchday 1`, `Quarter-finals` |
| `group` | keyword | e.g. `Group A`, `Knockout` |
| `stage` | keyword | `group`, `round_of_32`, `round_of_16`, `quarter`, `semi`, `final` |
| `status` | keyword | `played` or `upcoming` |
| `team1` | keyword | |
| `team2` | keyword | |
| `score_ft1` | integer | Team 1 full-time goals (played only) |
| `score_ft2` | integer | Team 2 full-time goals (played only) |
| `total_goals` | integer | Computed at ingest |
| `winner` | keyword | Team name or `draw` (played only) |
| `team1_win` | boolean | |
| `team2_win` | boolean | |
| `goals` | nested | `scorer`, `minute`, `team`, `type` (`goal`/`penalty`/`own_goal`) |
| `stadium` | keyword | Host city/venue |

> The notebook populates `wc2026_matches` only. To also get the match-stories index below (needed for the hybrid search tool), run `python setup_hacknight.py --data-only` - it ingests both.

#### Index schema - `wc2026_match_stories` (semantic_text / vector search)

The setup script generates a natural-language story for every match - e.g. *"Brazil edged Morocco 2-1 in a tight, hard-fought contest in their group-stage match in Group C at MetLife Stadium... Brazil came from behind after trailing 0-1 at half-time."* - and indexes it twice:

| Field | Type | Notes |
|---|---|---|
| `match_id` | keyword | `date-team1-team2` |
| `date` | date | |
| `team1` / `team2` / `teams` | keyword | |
| `group` / `stage` / `status` / `stadium` | keyword | Same values as `wc2026_matches` |
| `story` | text | The description - powers **lexical (BM25)** search |
| `story_semantic` | semantic_text | Same text, **embedded automatically by EIS** at index time - powers **semantic vector** search |

Querying both fields and fusing the results with RRF is what makes the `search_match_stories` tool a true **hybrid search** - no model deployment, no API keys, embeddings courtesy of EIS on AWS Bedrock.

---

### Part 2 - Agent Builder

Everything for Part 2 lives in [agent_builder_guide.md](agent_builder_guide.md). It gives you two paths to the same result:

- **Fast path - Dev Tools Console:** the guide's *Quick Setup* section has the four API commands (three tools + one agent) ready to paste into Kibana's **Dev Tools Console** (hamburger menu → Management → Dev Tools). Paste each block, press play, and you're done - no Kibana endpoint to find, no auth headers, Dev Tools uses your current session.
- **Manual walkthrough:** the rest of the guide builds the same tools and agent field-by-field through the Agent Builder UI, if you want to understand each piece or tweak it.

Either way, once the three tools and the agent exist, open **Kibana → Agents** and the **World Cup 2026 Predictor** is ready to chat.

#### Navigate to Agent Builder

In your Elastic Serverless project, look for **Agents** in the main navigation. 

---

#### The Four Tools

| Tool ID | What it does |
|---|---|
| `get_team_form` | Full match-by-match results for a team in 2026 - scores, opponents, stage, outcome |
| `get_team_stats_2026` | Aggregated stats: wins, draws, losses, goals scored/conceded |
| `get_upcoming_fixtures` | Scheduled matches not yet played - lets the agent find real upcoming matchups |
| `search_match_stories` | **Hybrid search** (BM25 + semantic vector search fused with RRF) over natural-language match stories - answers fuzzy questions like "dramatic comebacks" or "tense low-scoring knockout games" |

See `agent_builder_guide.md` for the exact ES|QL query and parameter config for each tool.

---

#### The Custom Agent

| Field | Value |
|---|---|
| **Agent ID** | `wc2026_predictor` |
| **Display name** | World Cup 2026 Predictor |
| **Tools** | All four above |

**Custom instructions summary:** The agent is instructed to always check upcoming fixtures first to confirm a match is actually scheduled, then pull team stats and form, then produce a structured prediction with scoreline, key factors, and confidence level. Full instructions in `agent_builder_guide.md`.

---

#### Step 5 - Chat With Your Agent

Try these - all grounded in live 2026 data:

```
When do France and Argentina play and what's their form so far?
```
```
Compare Brazil and Morocco based on their 2026 results
```
```
Predict the Germany vs Ecuador match
```
```
How has England performed in the group stage?
```
```
Find the most dramatic comebacks of the tournament so far
```

Watch the **thinking trace** - you'll see the agent calling tools in sequence before forming its answer. The last prompt triggers the hybrid search tool - watch it retrieve match stories by meaning, not keywords.

---