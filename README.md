[![CI](https://github.com/MINE-DD/PRAG-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/MINE-DD/PRAG-AI/actions/workflows/ci.yml)

[![codecov](https://codecov.io/gh/MINE-DD/PRAG-AI/branch/main/graph/badge.svg)](https://codecov.io/gh/MINE-DD/PRAG-AI)

# PRAG-AI — Chat with your research papers

PRAG-AI lets you ask questions to a collection of academic PDF papers and get answers grounded in the text, with citations. Everything runs on your own computer — your papers never leave your machine.

**What's in this repository:**
- A **backend** (Python) that converts PDFs, stores them as searchable data, and runs queries
- A **database** (Qdrant) that holds the indexed content
- A **web interface** already hosted at [https://mine-dd.github.io/PRAG-AI](https://mine-dd.github.io/PRAG-AI) — no installation needed for this part

The backend and database run on your laptop inside Docker. The web interface connects to them over your local network.

---

## What you need to install

| Tool | What it does | Download |
|---|---|---|
| **Git** | Downloads this repository | [git-scm.com](https://git-scm.com) |
| **Docker Desktop** | Runs the backend and database | [docker.com](https://www.docker.com/products/docker-desktop/) |
| **Ollama** | Runs the AI models locally | [ollama.com](https://ollama.com) |

> No programming knowledge required. You only need a terminal for the two setup commands below.

---

## Step 1 — Download this repository

Open a terminal and run:

```bash
git clone https://github.com/mine-dd/PRAG-AI.git
cd PRAG-AI
```

---

## Step 2 — Start the backend

Make sure Docker Desktop is open and running, then:

```bash
docker compose up -d
```

This starts two things in the background:
- **Backend** — handles PDF conversion, indexing, and answering queries
- **Qdrant** — stores the indexed content of your papers

That's it. You can verify everything is running at [http://localhost:8000/health](http://localhost:8000/health) — you should see a short status message in your browser.

To stop the services at any time:

```bash
docker compose down
```

Your data is kept in the `./data/` folder and is never deleted when you stop or restart.

---

## Step 3 — Open the web interface

Go to: **[https://mine-dd.github.io/PRAG-AI](https://mine-dd.github.io/PRAG-AI)**

The first time, click **⚙ Settings** at the bottom of the left panel. The backend URL should already be set to `http://localhost:8000` — just click **Save & connect**. The dot next to the URL should turn green.

> If you prefer to run the interface locally instead of using the hosted version:
> ```bash
> cd frontend-web
> python3 -m http.server 3000
> ```
> Then open [http://localhost:3000](http://localhost:3000).

---

## Step 4 — Download AI models

Make sure Ollama is running (you should see the Ollama icon in your menu bar on Mac, or run `ollama serve` on Linux/Windows).

In the Settings panel, scroll to **Ollama Models** and you will see a **Pull model** section. Select a model from the dropdown and click **Pull** to download it:

- For **embedding** (indexing your papers): `nomic-embed-text` is a good default
- For **generation** (answering your questions): `llama3.2` is a good starting point

Once downloaded, select the model in the **Embedding model** and **Generation model** dropdowns and click **Save & connect**.

> Smaller models download faster and use less memory. Larger models give better answers but require more RAM (8 GB+ recommended for 7B models).

---

## How to use it

### 1. Convert your PDFs

Go to the **PDF Management** tab.

1. Enter a folder name (e.g. `climate-papers`)
2. Select one or more PDF files
3. Click **Convert** next to each file — this extracts the text so the AI can read it

Conversion takes a few seconds to a minute per paper depending on length.

---

### 2. Create a collection

Go to the **Collections** tab.

1. Enter a **name** for your collection (e.g. `Climate Papers 2024`)
2. Choose **Hybrid** search (recommended — combines keyword and semantic matching)
3. Optionally select a folder under **Ingest from directory** to add all its papers at once
4. Click **Create**

To add more papers to an existing collection later, click **+ Add files** on the collection card.

---

### 3. Ask questions

Go to the **RAG Query** tab.

1. Select a collection from the left panel
2. Type your question
3. Click **Ask**

You get a written answer, the passages used to generate it, and citations in APA or BibTeX format.

---

### 4. Other features

- **Explore Paper** — browse individual papers, view metadata and extracted text
- **Compare** — run a side-by-side comparison of multiple papers on a topic
- **Cloud models** — in Settings you can switch to Anthropic (Claude) or Google (Gemini) for better answers; note that your queries and relevant text excerpts will be sent to their servers

---

## Updating to a new version

```bash
git pull
docker compose up -d --build
```

Your data in `./data/` is never affected by updates.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Backend dot is red | Make sure Docker Desktop is running, then `docker compose up -d` |
| Ollama dot is red | Start Ollama (menu bar icon or `ollama serve` in terminal) |
| Model list is empty in Settings | Ollama is running but has no models yet — use the Pull section to download one |
| PDF conversion fails | Check logs with `docker compose logs backend` |
| Can't connect from the hosted interface | Confirm the backend URL in Settings is exactly `http://localhost:8000` |
