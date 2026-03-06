# PRAG-v2 — Personal RAG for Academic Papers

PRAG-v2 is a local tool that lets you chat with your academic PDF papers using AI. You upload PDFs, convert them, and then ask questions across your library — all privately on your own machine.

**How it works at a glance:**

```
Your browser (GitHub Pages)
        │  HTTP requests
        ▼
FastAPI backend ── Qdrant vector DB    (both run in Docker on your laptop)
        │
        ▼
Ollama (also on your laptop, runs the AI models)
```

The web interface is hosted on GitHub Pages so you don't need to run anything extra, but **all your data and AI processing stay on your machine**.

---

## What you need

| Tool | Purpose | Install |
|---|---|---|
| **Git** | Download the repo | [git-scm.com](https://git-scm.com) |
| **Docker Desktop** | Runs the backend and database | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| **Ollama** | Runs the AI models locally | [ollama.com](https://ollama.com) |

No Python installation needed to use the app — only if you want to run the tests.

---

## Step 1 — Install Ollama and download models

1. Install Ollama from [ollama.com](https://ollama.com) and make sure it is running (you should see the Ollama icon in your menu bar on Mac, or run `ollama serve` on Linux/Windows).

2. Open a terminal and pull the two models PRAG-v2 uses by default:

```bash
# Embedding model — converts text into vectors for search
ollama pull nomic-embed-text

# Language model — generates answers to your questions
ollama pull llama3.2
```

> You can use different models later from the Settings panel. These are just the defaults.

---

## Step 2 — Download the repository

```bash
git clone https://github.com/mine-dd/PRAG-AI.git
cd PRAG-AI
```

---

## Step 3 — Configure environment variables

Copy the example environment file and edit it if needed:

```bash
cp .env.example .env
```

Open `.env` in any text editor. The defaults work for most setups — you only need to change anything if:
- Ollama is running on a non-standard port
- You want to use optional API keys (Anthropic, Google)

```env
# Optional API keys — leave blank if you don't have them
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
```

---

## Step 4 — Start the backend with Docker

Make sure Docker Desktop is running, then:

```bash
docker compose up -d
```

This starts two services:
- **Backend** — the FastAPI server that handles all logic (port 8000)
- **Qdrant** — the vector database that stores your paper embeddings (port 6333)

Both ports are bound to `127.0.0.1` (your machine only) — they are **not accessible from other devices on your network**.

To check that everything started correctly:

```bash
docker compose ps
```

Both services should show `Up` or `healthy`. You can also visit [http://localhost:8000/health](http://localhost:8000/health) in your browser — you should see a JSON response confirming the backend, Qdrant, and Ollama are all reachable.

To stop the services:

```bash
docker compose down
```

Your data is stored in the `./data/` folder and is preserved between restarts.

---

## Step 5 — Open the web interface

Go to: **[https://mine-dd.github.io/PRAG-AI](https://mine-dd.github.io/PRAG-AI)**

The first time you open it you need to connect it to your local backend (see Settings below).

> **Alternatively**, if you prefer to run the frontend locally instead of using GitHub Pages:
> ```bash
> cd frontend-web
> python3 -m http.server 3000
> ```
> Then open [http://localhost:3000](http://localhost:3000).

---

## Step 6 — Configure Settings

Click the **⚙ Settings** button at the bottom of the sidebar.

| Setting | What it does | Default |
|---|---|---|
| **Backend URL** | Address of your local backend | `http://localhost:8000` |
| **Preprocessed directory** | Server-side path where converted files are stored | `/data/preprocessed` |
| **Embedding model** | Ollama model used to index papers | `nomic-embed-text:latest` |
| **Generation model** | Ollama model used to answer questions | `llama3.2:latest` |

The Settings panel automatically fetches your available Ollama models and preselects the ones currently configured — just confirm they look right and click **Save & connect**.

The sidebar shows three status dots that tell you if each service is reachable:
- **Backend** — your FastAPI server
- **Qdrant** — your vector database
- **Ollama** — your local AI models

All three should be green before you start.

---

## Workflow — from PDFs to answers

### 1. Upload and convert PDFs

Go to the **PDF Management** tab.

1. Type a folder name (e.g. `climate-papers`) in the **Directory name** field.
2. Click the file input and select one or more PDF files.
3. Click **Convert** next to each file to convert it to markdown — this is the step that extracts text for the AI. A green **Converted** badge appears when done.

> Conversion can take from a few seconds to a minute depending on the paper length and which model backend is used.

To remove a file, click **Delete** next to it. To remove an entire folder and all its contents, click **Delete folder** on the folder header.

---

### 2. Create a collection and add papers

Go to the **Collections** tab.

1. Fill in a **Collection ID** (e.g. `climate-2024`) — this is the internal name, no spaces.
2. Optionally add a **Display name** (e.g. `Climate Papers 2024`).
3. Choose a **Search type**:
   - **Dense** — pure vector search, good general default
   - **Hybrid** — vector + keyword search, better for technical terminology
4. Optionally pick a directory from **Ingest from directory** — this will add all converted papers from that folder in one step.
5. Click **Create** (or **Create & Ingest** if you selected a directory).

To add more papers to an existing collection later, click **+ Add files** on the collection card. A file picker will expand with:
- A **folder filter** and a **search box** to narrow down papers
- **Check all / Uncheck all** buttons
- A per-file **✓ / ✗** status as ingestion runs

---

### 3. Ask questions (RAG Query)

Go to the **RAG Query** tab.

1. Select a collection from the sidebar picker or the in-tab dropdown.
2. Type your question in the text box.
3. Adjust options if needed (number of results, max tokens, hybrid search).
4. Click **Ask**.

The answer appears with:
- The **generated response** from the language model
- **Retrieved passages** (collapsed by default) showing which chunks were used
- **Citations** in APA or BibTeX format

---

### 4. Explore a paper

Go to the **Explore Paper** tab to browse individual papers in a collection — view metadata, abstract, and chunk count, or download the converted markdown.

---

### 5. Compare papers

Go to the **Compare** tab to run a side-by-side comparison of multiple papers on a specific aspect (methodology, results, limitations, etc.).

---

## Keeping data across updates

All your data lives in the `./data/` folder:

```
data/
├── pdf_input/       ← your original PDFs (organised by folder)
├── preprocessed/    ← converted markdown files
├── collections/     ← Qdrant vector data
└── qdrant/          ← Qdrant internal storage
```

This folder is a Docker volume mount, so it persists across `docker compose down` / `up` cycles and Docker image rebuilds.

---

## Updating to a new version

```bash
git pull
docker compose up -d --build
```

The `--build` flag rebuilds the backend image with any new code. Your data in `./data/` is untouched.

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| Backend dot is red | Docker containers not running | Run `docker compose up -d` |
| Ollama dot is red | Ollama not running | Start Ollama (menu bar icon or `ollama serve`) |
| "Cannot reach Ollama" in Settings | Model list can't load | Make sure Ollama is running before opening Settings |
| Conversion fails | Model backend error | Check `docker compose logs backend` for details |
| Frontend can't reach backend from GitHub Pages | Mixed content or wrong URL | Confirm backend URL is `http://localhost:8000` in Settings |
