# Hack Night Open Challenge


## Example Projects

| Project | Description | Elasticsearch Features |
|--------|-------------|-------------------------|
| **Player Search Engine** | Search players by name, country, club, position, or tournament statistics with instant filtering and autocomplete. | Full-text search, autocomplete, aggregations |
| **Similar Player Finder** | Find players with similar playing styles using performance statistics or embeddings. | Vector search, kNN, dense vectors |
| **Soccer RAG Chatbot** | Ask natural language questions like *"Who scored the most goals in the 2018 World Cup?"* or *"Show all matches Messi played against France."* | Elasticsearch + LLM + semantic search |
| **Team Performance Explorer** | Compare national teams across tournaments using advanced statistics and historical trends. | Aggregations |
| **AI Match Summary Generator** | Generate natural-language summaries of matches from event data using an LLM with Elasticsearch as the retrieval layer. | Semantic search, vector search, RAG |

> **Need an LLM, semantic search, or embeddings?** Don't wire up your own API keys - use the **Elastic Inference Service (EIS)**. Its LLM and embedding models are hosted on AWS Bedrock and ready with zero setup. The [EIS guide](eis_guide.md) shows how to use it for chat, semantic search, and dense-vector embeddings - everything the RAG, similarity, and summary ideas above need.

## Stretch Ideas

- Build a **player similarity search** using vector embeddings.
- Create an **interactive World Cup timeline** showing every tournament, champion, and memorable match.
- Compare **playing styles** between teams using passing networks and event data.
- Build a **fantasy football assistant** that recommends players based on historical performance.
- Create a **natural language search experience** where users ask soccer questions and Elasticsearch retrieves the relevant matches, events, and player statistics.

---

## Example: Ingesting the Kaggle Dataset

Here's a complete, runnable example that pulls the [FIFA World Cup 2026 Player Performance Dataset](https://www.kaggle.com/datasets/rauffauzanrambe/fifa-world-cup-2026-player-performance-dataset) from Kaggle and indexes it into Elasticsearch. This is just one dataset - the same pattern works for any CSV-based source.

Run it in a Jupyter/Colab notebook or as a plain Python script. If you don't want to ingest CSVs programmatically, you can also use the `upload file` option within the Elasticsearch UI.

### 1. Install dependencies

```bash
pip install elasticsearch pandas kagglehub
```

### 2. Get your Kaggle API token

Kaggle downloads require authentication:

1. Go to [kaggle.com](https://www.kaggle.com) → your account → **Settings**
2. Under **API**, click **Create New Token** - this downloads `kaggle.json`
3. Place it at `~/.kaggle/kaggle.json` (Linux/Mac) or `%USERPROFILE%\.kaggle\kaggle.json` (Windows)

> In Google Colab, upload `kaggle.json` and run:
> ```python
> import os, shutil
> os.makedirs('/root/.kaggle', exist_ok=True)
> shutil.copy('kaggle.json', '/root/.kaggle/kaggle.json')
> os.chmod('/root/.kaggle/kaggle.json', 0o600)
> ```

### 3. Download the dataset

```python
import kagglehub, glob, os

# Downloads to a local cache and returns the folder path
path = kagglehub.dataset_download('rauffauzanrambe/fifa-world-cup-2026-player-performance-dataset')

csv_files = glob.glob(os.path.join(path, '*.csv'))
print('Downloaded files:')
for f in csv_files:
    print(' ', os.path.basename(f))
```

### 4. Load and inspect the CSV

```python
import pandas as pd

# Use the first CSV in the dataset (or pick a specific file from the list above)
df = pd.read_csv(csv_files[0])

print(f'{len(df)} rows, {len(df.columns)} columns')
print('Columns:', list(df.columns))
df.head()
```

### 5. Connect to Elastic Serverless

```python
from elasticsearch import Elasticsearch, helpers

# 🔑 Fill these in - Elastic Cloud Console → Your Project → Connection Details
ELASTIC_ENDPOINT = 'https://your-project.es.region.aws.elastic.cloud'
ELASTIC_API_KEY  = 'your-elastic-api-key'

es = Elasticsearch(ELASTIC_ENDPOINT, api_key=ELASTIC_API_KEY)
print(f'✅ Connected to Elasticsearch {es.info()["version"]["number"]}')
```

### 6. Bulk-index into Elasticsearch

We let Elasticsearch infer the field types automatically (dynamic mapping), which is fine for exploration. Define an explicit mapping later if you want `keyword` fields for exact filtering or `dense_vector` fields for similarity search.

```python
INDEX = 'wc2026_players'

# Recreate the index each run so there are no duplicates
if es.indices.exists(index=INDEX):
    es.indices.delete(index=INDEX)
es.indices.create(index=INDEX)

# Clean NaNs (Elasticsearch can't index NaN) and turn each row into a document
records = df.where(pd.notnull(df), None).to_dict(orient='records')
actions = [{'_index': INDEX, '_source': r} for r in records]

success, errors = helpers.bulk(es, actions)
es.indices.refresh(index=INDEX)
print(f'✅ Indexed {success} documents ({len(errors)} errors)')
```

### 7. Verify

```python
resp = es.search(index=INDEX, size=3)
print(f"Total documents: {resp['hits']['total']['value']}\n")
for hit in resp['hits']['hits']:
    print(hit['_source'])
```

That's it - you now have a `wc2026_players` index you can search, aggregate, or layer AI on top of. From here, add an explicit mapping for the fields you care about, wire up autocomplete, or add semantic search, embeddings, and an LLM chatbot with the [EIS guide](eis_guide.md) - everything the **Similar Player Finder**, **Soccer RAG Chatbot**, and **AI Match Summary Generator** ideas above need.
