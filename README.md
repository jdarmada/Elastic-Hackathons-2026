# Elastic Hackathons (World Cup Data)


## Quick Start - One Script

Everything - data ingest **and** Agent Builder setup - runs from a single script:

```bash
pip install -r requirements.txt
export ELASTIC_ENDPOINT="https://your-project.es.region.aws.elastic.cloud"
export ELASTIC_API_KEY="your-elastic-api-key"
python setup_hacknight.py
```

The script:

1. Fetches **live 2026 World Cup data** from [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json)
2. Ingests it into the **`wc2026_matches`** index (structured match data - same schema as the notebook)
3. Generates a **natural-language story for every match** and ingests them into **`wc2026_match_stories`** - a `semantic_text` index embedded automatically by EIS, ready for **vector search**
4. Creates **four Agent Builder tools** via the Kibana API - team form, team stats, upcoming fixtures, and **`search_match_stories`, a hybrid search tool** (BM25 + semantic vector search fused with RRF)
5. Creates the **World Cup 2026 Predictor** agent wired to all four tools

Then open **Kibana → Agents** and ask: *"Find the most dramatic comebacks of the tournament so far"*.

> Credentials: Copy your credentials into .env


## Public Soccer Datasets

These are publicly available soccer datasets for player performance analysis, match data, and event-level analytics. You are not restricted to these, feel free to use any dataset you find.

| Dataset | Description | Data Type |
|---------|-------------|-----------|
| **[FIFA World Cup 2026 Player Performance Dataset](https://www.kaggle.com/datasets/rauffauzanrambe/fifa-world-cup-2026-player-performance-dataset)** | Simulated/player performance dataset for the FIFA World Cup 2026. Includes player statistics, match performance metrics, team information, and tournament-related data suitable for machine learning and analytics. | Player & Match Statistics |
| **[openfootball/worldcup.json](https://github.com/openfootball/worldcup.json)** | Open-source JSON dataset containing historical FIFA World Cup tournaments, including teams, fixtures, match results, venues, and tournament structure in an easy-to-use format. | Historical Match Results |
| **[StatsBomb Open Data](https://github.com/statsbomb/open-data)** | One of the most comprehensive free football analytics datasets available. Provides detailed event-level data (passes, shots, dribbles, pressures, tackles, etc.), lineups, matches, competitions, and 360° data for selected competitions. Widely used in football analytics research and visualization. :contentReference[oaicite:0]{index=0} | Event-Level Match Data |


## Resources

Handy documentation and references for building tonight.

### Getting started
- [Elasticsearch quickstart](https://www.elastic.co/docs/solutions/search/get-started) - your first index and query
- [Connecting to Elasticsearch](https://www.elastic.co/docs/reference/elasticsearch/clients) - endpoints, API keys, and client setup

### Agent Builder
- [Agent Builder overview](https://www.elastic.co/docs/explore-analyze/ai-features/elastic-agent-builder)
- [Building custom tools](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/tools/custom-tools)
- [Building custom agents](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/custom-agents)
- [Expose agents over MCP](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/mcp-server) - connect to Claude Desktop or your own app

### Search & querying
- [ES|QL reference](https://www.elastic.co/docs/explore-analyze/query-filter/languages/esql) - the query language the starter tools use
- [Query DSL](https://www.elastic.co/docs/explore-analyze/query-filter/languages/querydsl) - full-text, filters, and boolean queries
- [Aggregations](https://www.elastic.co/docs/explore-analyze/query-filter/aggregations) - stats, terms, and metrics for dashboards
- [Search relevance & autocomplete](https://www.elastic.co/docs/solutions/search/full-text) - for player/team search experiences

### Vector & semantic search (great for RAG and "similar player" ideas)
- [Semantic search with `semantic_text`](https://www.elastic.co/docs/solutions/search/semantic-search/semantic-search-semantic-text) - the fastest path to semantic search
- [kNN / dense vector search](https://www.elastic.co/docs/solutions/search/vector/knn)
- [Bringing your own embeddings](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/dense-vector)

### Ingesting data
- [Python Elasticsearch client](https://www.elastic.co/docs/reference/elasticsearch/clients/python) - what the notebook uses
- [Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk) - efficient batch indexing
- [Upload a file in Kibana](https://www.elastic.co/docs/manage-data/ingest/upload-data-files) - no-code CSV/JSON ingest




