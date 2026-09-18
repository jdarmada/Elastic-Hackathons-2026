# 🤖 Using the Elastic Inference Service (EIS)

The **Elastic Inference Service (EIS)** lets you use AI models - LLMs for chat and embedding models for semantic and vector search - **without deploying a model, managing infrastructure, or bringing your own API keys**. The models are hosted by Elastic on **AWS Bedrock** (and other backends) and are billed per token as part of your Serverless project.

For this hack night, **EIS is the recommended way to add AI to your project** - it's the fastest path and requires zero setup.

---

## Benefits of EIS

- **No API keys to manage** - you don't need your own AWS Bedrock, OpenAI, or Anthropic account
- **No model deployment** - embedding models are ready the moment your project spins up
- **Already powering the starter project** - the World Cup Predictor agent's LLM runs on EIS
- **Bedrock under the hood** - Elastic Managed LLMs run on AWS Bedrock, so "use EIS" *is* "use Bedrock", minus the setup

---

## 1. LLM / chat - powers Agent Builder (zero setup)

On Elastic Cloud Serverless, **Agent Builder, the AI Assistant, and Search Playground all use Elastic Managed LLMs running on EIS by default**. There is nothing to configure - the LLM is already wired up.

- The **World Cup Predictor agent** you build in [starter_project.md](starter_project.md) already runs on this. You never add a connector or a key.
- To **see or switch the model**, use the model selector in the Agent Builder chat interface.
- To **set a default model** (Elastic 9.4+), search for **Model management** in Kibana's global search bar and pick from the **Default model** dropdown.


---

## 2. Semantic & vector search (zero setup)

Perfect for the **Soccer RAG Chatbot**, **semantic search**, and **Similar Player Finder** ideas in the [open challenge](open_challenge.md).

The simplest path is a `semantic_text` field. You don't even need to choose a model - on a current Serverless project, `semantic_text` automatically uses the deployment's default embedding model (a Jina embedding model served by EIS):

```
PUT wc_notes
{
  "mappings": {
    "properties": {
      "summary": { "type": "semantic_text" }
    }
  }
}
```

Index documents normally - Elasticsearch calls EIS to embed them at index time:

```
POST wc_notes/_doc
{
  "summary": "Brazil edged Morocco 1-0 in a tense Group C clash decided by a late header."
}
```

Then search with a natural-language `semantic` query - no keywords, no key, no model deployment:

```
GET wc_notes/_search
{
  "query": {
    "semantic": {
      "field": "summary",
      "query": "which teams won close low-scoring games"
    }
  }
}
```

**Want a specific model, or raw vectors for your own kNN search?** Create a `text_embedding` endpoint backed by EIS (`service: "elastic"`):

```
PUT _inference/text_embedding/wc-embeddings
{
  "service": "elastic",
  "service_settings": {
    "model_id": "<embedding-model-id>"
  }
}
```

> Check the [EIS docs](https://www.elastic.co/docs/explore-analyze/elastic-inference/eis) for the current list of available embedding model IDs.

Then point a `semantic_text` field at it with `"inference_id": "wc-embeddings"`, or generate vectors to store in a `dense_vector` field for [kNN search](https://www.elastic.co/docs/solutions/search/vector/knn).

---

## 3. Calling EIS from your own app / the API

Building something outside Agent Builder - a script, a backend, a custom chatbot? You talk to the **inference API** on your Elasticsearch endpoint directly. No connector, no keys of your own - auth is just your Elasticsearch API key, and the models (on Bedrock) are billed per token to your project.

You need two things from the Elastic Cloud console (**your project → Connection details**): your Elasticsearch endpoint URL and an API key.

### Chat completion (LLM)

Serverless projects come with **preconfigured EIS endpoints** (Elastic Managed LLMs on Bedrock) - nothing to create. To see every inference endpoint available to you and its ID, run this in Kibana's **Dev Tools Console**:

```
GET _inference
```

Grab the `inference_id` of a `chat_completion` endpoint from the list. The API is OpenAI-compatible and **streams** its response over the `/_stream` path:

```bash
curl "$ELASTICSEARCH_URL/_inference/chat_completion/<chat-inference-id>/_stream" \
  -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      { "role": "system", "content": "You are a football analyst." },
      { "role": "user", "content": "Who won the 2022 World Cup final?" }
    ]
  }'
```

Same call from Python with the official client:

```python
from elasticsearch import Elasticsearch

es = Elasticsearch(ELASTIC_ENDPOINT, api_key=ELASTIC_API_KEY)

resp = es.inference.chat_completion_unified(
    inference_id='<chat-inference-id>',
    messages=[
        {'role': 'system', 'content': 'You are a football analyst.'},
        {'role': 'user',   'content': 'Who won the 2022 World Cup final?'},
    ],
)
# response streams as SSE chunks - concatenate the delta.content fields
```

> Because the schema is OpenAI-compatible (`messages` with `system` / `user` / `assistant` roles), most OpenAI SDKs work too - just point their `base_url` at `<ELASTICSEARCH_URL>/_inference/chat_completion/<chat-inference-id>`.

**This is the core of a RAG app:** query Elasticsearch for relevant context, drop it into the `system`/`user` message, then call this endpoint for a grounded answer.

### Embeddings

The same client generates embeddings - handy for building your own vector search:

```python
resp = es.inference.inference(
    inference_id='wc-embeddings',
    task_type='text_embedding',
    input=['Lionel Messi', 'Kylian Mbappe', 'Erling Haaland'],
)
print(resp['text_embedding'][0]['embedding'][:5])
```

See the [chat completion API reference](https://www.elastic.co/docs/api/doc/elasticsearch-serverless/operation/operation-inference-chat-completion-unified) for the full request/response schema, including tool calling.

---

## Reference

- [Elastic Inference Service (EIS)](https://www.elastic.co/docs/explore-analyze/elastic-inference/eis)
- [Default inference endpoints](https://www.elastic.co/docs/explore-analyze/elastic-inference/inference-api)
- [Model configuration in Agent Builder](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/models)
- [Semantic search with `semantic_text`](https://www.elastic.co/docs/solutions/search/semantic-search/semantic-search-semantic-text)
- [Create an inference endpoint (API)](https://www.elastic.co/docs/api/doc/elasticsearch-serverless/operation/operation-inference-put)
- [Build AI agents with EIS (Elasticsearch Labs)](https://www.elastic.co/search-labs/blog/build-ai-agents-elastic-inference-service)
