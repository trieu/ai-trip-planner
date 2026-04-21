# Local Guide RAG Demo (Updated 2026)

This AI Trip Planner includes an optional Retrieval-Augmented Generation (RAG) feature that powers the `SmartTripPlanner` with curated, real-world local experiences.

## What is RAG?

RAG (Retrieval-Augmented Generation) combines:
1. **Retrieval**: Search a database for relevant information.
2. **Augmentation**: Add that information to the LLM's context.
3. **Generation**: LLM generates responses using both its knowledge and the retrieved data.

## How to Enable RAG

### 1. Set the Feature Flag

Copy `sample.env` to `.env`. Configure the following variables:

```bash
# Enable RAG feature (1 for true, 0 for false)
ENABLE_RAG=1

# Your Google Gemini API Key for the main LLM and Embeddings
GOOGLE_GEMINI_API_KEY="your_api_key_here"

# Set the models to match the application defaults
LLM_MODEL_NAME=gemini-2.5-flash-lite
EMBEDDING_MODEL_NAME=models/text-embedding-004
```


### 2. Restart the Server

```bash
uvicorn main:app --reload --port 8000
```


On startup, the app will:
* Load curated local experiences from your data source.
* [cite_start]Create vector embeddings using `models/text-embedding-004`[cite: 2].
* Index them into an in-memory vector store for semantic search.

## What Happens Behind the Scenes

### With ENABLE_RAG=1 (Semantic Search)

1. **User Request**: "Tokyo with food, anime interests".
2. [cite_start]**Create Query Embedding**: Uses `GoogleGenerativeAIEmbeddings`[cite: 2].
3. **Search Vector Store**: Finds top similar local experiences.
4. [cite_start]**Inject Context**: The retrieved data is passed to the `journey_plan_node`[cite: 2].
5. [cite_start]**LLM Generation**: The Gemini model synthesizes the plan using the RAG context[cite: 2].

### With ENABLE_RAG=0 (Default Behavior)

[cite_start]The `SmartTripPlanner` falls back to its core nodes (`research`, `budget`) and general LLM knowledge[cite: 2].

## Observability & Tracing

When RAG is enabled and your `PHOENIX_COLLECTOR_ENDPOINT` is set to `http://localhost:6006/v1/traces`, you can monitor:

* **Retrieval Spans**: See the exact query used to fetch local data.
* **Retrieved Documents**: View the content passed to the Gemini model.
* **Latency**: Track how long the embedding and retrieval process takes.

## Common Issues & Solutions

* **"No embeddings created"**: Ensure `ENABLE_RAG=1` and `GOOGLE_GEMINI_API_KEY` is set in `.env`.
* **"Empty retrieval results"**: Verify your destination and interests match the tags in your local guides database.
* [cite_start]**"Tracing not showing"**: Ensure the `PHOENIX_COLLECTOR_ENDPOINT` in your `.env` matches your local Phoenix instance[cite: 2].