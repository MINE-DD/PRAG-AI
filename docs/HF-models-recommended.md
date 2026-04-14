# HuggingFace Model Recommendations

Reference guide for selecting models to use with `HuggingFaceService` and `HuggingFaceVLMConverter`.

---

## Text Generation

Models for `hf_model` / `HuggingFaceService(model_id=...)`.

| Model | Size | Notes |
|---|---|---|
| `Qwen/Qwen2.5-3B-Instruct` | 3B | **Recommended default.** Fast on Apple Silicon and low-VRAM GPUs. |
| `Qwen/Qwen2.5-7B-Instruct` | 7B | Higher quality; needs ≥16GB VRAM (or 24GB unified memory). |
| `mistralai/Mistral-7B-Instruct-v0.3` | 7B | Strong general-purpose, Apache 2.0 licence. |
| `meta-llama/Llama-3.2-3B-Instruct` | 3B | Fast, compact; requires HF token (accept Meta licence). |
| `meta-llama/Llama-3.1-8B-Instruct` | 8B | Higher quality; requires HF token. |
| `google/gemma-2-9b-it` | 9B | Competitive quality; requires HF token (accept Google licence). |

---

## Embeddings

Models for `hf_embedding_model` / `HuggingFaceService(embedding_model_id=...)`.

| Model | Dimensions | Notes |
|---|---|---|
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | **Recommended default.** Fast, small, widely used. |
| `sentence-transformers/all-mpnet-base-v2` | 768 | Better quality, heavier. Same dimensions as Ollama `nomic-embed-text`. |
| `BAAI/bge-small-en-v1.5` | 384 | High performance for retrieval tasks. |
| `BAAI/bge-base-en-v1.5` | 768 | Stronger version of the above. |
| `thenlper/gte-large` | 1024 | High quality; larger vectors mean larger Qdrant collections. |

> **Important:** The embedding model determines the vector dimension stored in Qdrant.
> Changing it on an existing collection requires re-ingesting all papers.
> The Qdrant `get_vector_size()` check will catch mismatches at ingest time.

---

## Vision-Language Models (VLM)

Models for `hf_vlm_model` / `HuggingFaceService(vlm_model_id=...)` and `HuggingFaceVLMConverter`.

| Model | Size | Notes |
|---|---|---|
| `Qwen/Qwen2-VL-2B-Instruct` | 2B | **Recommended default.** Fast on Apple Silicon and low-VRAM GPUs. |
| `Qwen/Qwen2-VL-7B-Instruct` | 7B | Higher quality OCR; needs ≥16GB VRAM. |
| `llava-hf/llava-1.5-7b-hf` | 7B | Solid general-purpose VLM. |
| `llava-hf/llava-1.5-13b-hf` | 13B | Higher quality, needs ~26GB VRAM. |
| `microsoft/Phi-3.5-vision-instruct` | 4B | Compact multimodal from Microsoft, permissive licence. |
| `google/paligemma-3b-mix-224` | 3B | Requires HF token (accept Google licence). |

### Specialised OCR models

For pure OCR (no conversational interface needed):

| Model | Notes |
|---|---|
| `microsoft/trocr-base-printed` | Fast printed-text OCR via `image-to-text` pipeline. |
| `microsoft/trocr-large-printed` | Higher accuracy printed OCR. |
| `microsoft/trocr-base-handwritten` | Handwritten text recognition. |
| `naver-clova-ix/donut-base` | Document understanding without OCR; structured extraction. |

---

## Hardware Guidance

| Setup | Recommended configuration |
|---|---|
| GPU ≥ 24GB VRAM | Any 7B model in bfloat16 (`torch_dtype="auto"`) |
| GPU 8–16GB VRAM | 3B models, or 7B with 4-bit quantisation (`load_in_4bit=True` via bitsandbytes) |
| CPU only | 3B models only; inference will be slow (minutes per query) |

> `device_map="auto"` in `HuggingFaceService` automatically distributes across all available GPUs and falls back to CPU.

---

## Switching backends in `config.yaml`

```yaml
models:
  embedding: nomic-embed-text:latest   # still used by Ollama embeddings
  llm:
    type: huggingface                  # options: local | anthropic | google | huggingface
    hf_model: Qwen/Qwen2.5-7B-Instruct
    hf_embedding_model: sentence-transformers/all-MiniLM-L6-v2
```

Or override per-deployment via environment variables:

```bash
HF_TEXT_MODEL=Qwen/Qwen2.5-3B-Instruct
HF_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
HF_VLM_MODEL=Qwen/Qwen2-VL-2B-Instruct
```
