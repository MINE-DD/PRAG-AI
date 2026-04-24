# PRAG Tech Stack and Toolchain

## Backend

| Tool | Version | Role | License | Docs |
|------|---------|------|---------|------|
| Python | 3.11+ | Core runtime | — | [docs.python.org](https://docs.python.org/) |
| FastAPI | 0.135.1 | REST API + SSE | MIT | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/) |
| Pydantic | 2.12.5 | Data models | MIT | [docs.pydantic.dev](https://docs.pydantic.dev/) |
| pydantic-settings | 2.13.1 | Configuration management | MIT | [docs.pydantic.dev/…/pydantic_settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| uvicorn | 0.41.0 | ASGI server | BSD | [uvicorn.org](https://www.uvicorn.org/) |
| click | 8.3.1 | CLI framework | BSD | [click.palletsprojects.com](https://click.palletsprojects.com/) |
| httpx | 0.28.1 | Async HTTP client (OllamaAdapter / GROBID / ZoteroClient) | BSD | [python-httpx.org](https://www.python-httpx.org/) |
| structlog | 25.5.0 | Structured logging + processor chain sanitization filtering | MIT | [structlog.org](https://www.structlog.org/) |
| Ollama (app) | 0.17.7 | LLM + Embedding inference server | MIT | [ollama.com](https://ollama.com/) |
| ollama (Python client) | 0.6.1 | Python SDK for Ollama API | MIT | [pypi.org/project/ollama](https://pypi.org/project/ollama/) |

> - **Atomic file writes**: Self-implemented (temp file + `os.replace()`, ~10 lines of code), ensuring safe writes to metadata.json as source-of-truth.
> - **Ingestor task registry**: Self-implemented (`dict[str, asyncio.Task]` mapping), tracking background parsing tasks and preventing duplicate parsing.

## PDF Parsing

| Tool | Version | Role | License | Integration | Docs |
|------|---------|------|---------|-------------|------|
| pdfplumber | 0.11.9 | Quick preview/metadata extraction (replaces PyMuPDF4LLM) | MIT | Python library | [github.com/jsvine/pdfplumber](https://github.com/jsvine/pdfplumber) |
| MinerU | 2.7.6 | Primary parsing engine (formulas/tables/layout) | Apache 2.0 | **HTTP service** (Docker, GPU) | [github.com/opendatalab/MinerU](https://github.com/opendatalab/MinerU) |
| GROBID | 0.8.2 | Reference structuring | Apache 2.0 | **HTTP service** (Docker) | [grobid.readthedocs.io](https://grobid.readthedocs.io/) |

> **MinerU deployment:** Docker image `mineru:latest` with `docker compose --profile api up`. Exposes FastAPI at port 8000. Requires Volta+ GPU with 8GB+ VRAM. See [Docker deployment guide](https://opendatalab.github.io/MinerU/quick_start/docker_deployment/).
> **GROBID deployment:** Docker image `grobid/grobid:0.8.2-full` (CRF + Deep Learning), migrated to OpenJDK 21.
> **PyMuPDF4LLM removed:** AGPL v3 license risk + C++ native deps fail on aarch64/Docker. Replaced by pdfplumber (pure Python, MIT).

## RAG Pipeline

| Tool | Version | Role | Docs |
|------|---------|------|------|
| qdrant-client | 1.17.0 | Vector store + native hybrid search (embedded mode, no Port abstraction) | [python-client.qdrant.tech](https://python-client.qdrant.tech/) |
| Qdrant (engine) | 1.17.0 | Vector database (RocksDB removed, replaced with gridstore) | [qdrant.tech/documentation](https://qdrant.tech/documentation/) |
| Qwen3-Embedding-0.6B | 600M | **Default embedding model** (100+ languages, 32K context, adjustable dimensions 32-1024, MTEB #1) | [Ollama](https://ollama.com/library/qwen3-embedding) / [GitHub](https://github.com/QwenLM/Qwen3-Embedding) |
| Qwen3-Embedding-4B/8B | 4B/8B | Optional larger embedding models for high-end hardware | Same as above |
| bge-reranker-base | — | Optional cross-encoder reranking (Phase 2: upgrade to bge-reranker-v2-m3) | [HuggingFace](https://huggingface.co/BAAI/bge-reranker-base) |

> **Token counting**: chunker.py requires "500 token" chunk size. Candidates: `tiktoken` (0.12.0) for exact counting, or character approximation (1 token ≈ 4 characters in English).

## Frontend

| Tool | Version | Role | Docs |
|------|---------|------|------|
| React | 19.2.4 | UI framework | [react.dev](https://react.dev) |
| TypeScript | — | Type safety | [typescriptlang.org](https://www.typescriptlang.org/) |
| Vite | 7.3.1 | Build/HMR | [vite.dev](https://vite.dev) |
| Zustand | 5.0.11 | UI state management | [github.com/pmndrs/zustand](https://github.com/pmndrs/zustand) |
| @tanstack/react-query | 5.90.21 | Server state management + parsing progress polling (complementary to Zustand) | [tanstack.com/query](https://tanstack.com/query/latest) |
| Tailwind CSS | 4.2.1 | Styling (CSS-first configuration, no config file needed) | [tailwindcss.com](https://tailwindcss.com) |
| Radix UI | 1.4.3 (unified package `radix-ui`) | Unstyled component primitives | [radix-ui.com/primitives](https://www.radix-ui.com/primitives) |
| react-pdf (wojtekmaj) | 10.4.1 | PDF rendering (based on PDF.js, requires custom UI) | [npmjs.com/package/react-pdf](https://www.npmjs.com/package/react-pdf) |
| react-markdown | 10.1.0 | Markdown rendering | [github.com/remarkjs/react-markdown](https://github.com/remarkjs/react-markdown) |
| remark-math | 6.0.0 | LaTeX formula support | [github.com/remarkjs/remark-math](https://github.com/remarkjs/remark-math) |
| rehype-katex | 7.0.1 | KaTeX rendering | [github.com/remarkjs/remark-math](https://github.com/remarkjs/remark-math) |
| sonner | 2.0.7 | Toast notifications (REST API errors → user messages) | [sonner.emilkowal.ski](https://sonner.emilkowal.ski) |
| react-dropzone | 15.0.0 | Drag-and-drop upload | [react-dropzone.js.org](https://react-dropzone.js.org) |
| Lucide React | 0.577.0 | Icons | [lucide.dev](https://lucide.dev/guide/packages/lucide-react) |
| React Router | 7.13.1 | Routing (two pages) | [reactrouter.com](https://reactrouter.com) |

> - **SSE client**: Native `fetch()` + `ReadableStream`, with event parsing implemented in the `useSSE.ts` hook. Zero dependencies; POST response streaming requires no auto-reconnect.
> - **PDF UI component layer**: Self-implemented — react-pdf has no built-in UI; requires custom page navigation, zoom controls, continuous scrolling, and citation highlight overlays.

## Development Tools

| Tool | Version | Role | Docs |
|------|---------|------|------|
| uv | 0.10.9 | Python package management | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |
| ruff | 0.15.5 | Python lint + format | [docs.astral.sh/ruff](https://docs.astral.sh/ruff/) |
| pyright | 1.1.408 | Python type checking (works with Pydantic/Protocol) | [github.com/microsoft/pyright](https://github.com/microsoft/pyright) |
| pytest | 9.0.2 | Python testing | [docs.pytest.org](https://docs.pytest.org/) |
| pytest-asyncio | 1.3.0 | Async test support | [pytest-asyncio.readthedocs.io](https://pytest-asyncio.readthedocs.io/) |
| pytest-cov | — | Test coverage | [pypi.org/project/pytest-cov](https://pypi.org/project/pytest-cov/) |
| pre-commit | 4.5.1 | Code quality hooks (ruff + biome + pyright) | [pre-commit.com](https://pre-commit.com/) |
| pnpm | 10.31.0 | Node package management | [pnpm.io](https://pnpm.io) |
| Vitest | 4.0.18 | Frontend testing | [vitest.dev](https://vitest.dev) |
| @testing-library/react | 16.3.2 | Frontend component testing (rendering + interaction) | [testing-library.com](https://testing-library.com/docs/react-testing-library/intro/) |
| Playwright | 1.58.2 | E2E testing (Phase 2) | [playwright.dev](https://playwright.dev) |
| Biome | 2.4.6 | Frontend lint + format | [biomejs.dev](https://biomejs.dev) |
| openapi-typescript | 7.13.0 | Auto-generate TypeScript types from FastAPI OpenAPI schema | [openapi-ts.dev](https://openapi-ts.dev/) |
| Makefile | — | Unified dev commands (dev / test / lint / build / setup) | — |
| devcontainer | — | Unified development environment (MinerU has complex dependency chains) | [containers.dev](https://containers.dev/) |
