import ollama


class OllamaService:
    """Service for interacting with Ollama LLMs"""

    def __init__(
        self, url: str, model: str = "llama3", embedding_model: str = "nomic-embed-text"
    ):
        self.url = url
        self.model = model
        self.embedding_model = embedding_model
        self.client = ollama.Client(host=url)

    def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        response = self.client.embed(
            model=self.embedding_model, input=text, truncate=True
        )
        return list(response.embeddings[0])

    def generate_embeddings_batch(
        self, texts: list[str], batch_size: int = 32
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Uses the embed() batch API so the server handles all texts in one
        round-trip per batch, with truncate=True to avoid context-length errors.
        """
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            response = self.client.embed(
                model=self.embedding_model,
                input=texts[start : start + batch_size],
                truncate=True,
            )
            embeddings.extend(list(e) for e in response.embeddings)
        return embeddings

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        num_context_tokens: int | None = None,
        chat_history: list[dict] | None = None,
    ) -> tuple[str, dict]:
        """Generate text response from LLM.

        Returns (content, usage) where usage = {prompt_tokens, completion_tokens}.
        """
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        if chat_history:
            messages.extend(chat_history)

        messages.append({"role": "user", "content": prompt})

        opts: dict = {"temperature": temperature}
        if max_tokens is not None:
            opts["num_predict"] = max_tokens
        if num_context_tokens is not None:
            opts["num_ctx"] = num_context_tokens

        response = self.client.chat(
            model=self.model,
            messages=messages,
            options=opts,
        )

        NO_LLM_TOKENS_IN_RESPONSE = "OOPS! It seems like the LLM refused to generate any tokens as a response to this question =("
        content = response.message.content
        text = content if content and content.strip() else NO_LLM_TOKENS_IN_RESPONSE
        usage = {
            "prompt_tokens": response.prompt_eval_count,
            "completion_tokens": response.eval_count,
            "total_tokens": (response.prompt_eval_count or 0) + (response.eval_count or 0),
            "model": response.model,
            "created_at": str(response.created_at) if response.created_at else None,
            "done_reason": response.done_reason,
            "total_duration_ms": round(response.total_duration / 1e6) if response.total_duration else None,
            "load_duration_ms": round(response.load_duration / 1e6) if response.load_duration else None,
            "prompt_eval_duration_ms": round(response.prompt_eval_duration / 1e6) if response.prompt_eval_duration else None,
            "eval_duration_ms": round(response.eval_duration / 1e6) if response.eval_duration else None,
        }
        return text, usage

    def get_llm_context_length(self) -> int:
        """Return the max context length for the LLM model from Ollama metadata.

        Ollama stores this as '{architecture}.context_length' (e.g. 'llama.context_length',
        'gemma4.context_length'). Falls back to 4096 if unavailable.
        """
        try:
            info = self.client.show(self.model)
            modelinfo = info.modelinfo or {}
            architecture = modelinfo.get("general.architecture", "")
            if architecture:
                key = f"{architecture}.context_length"
                if key in modelinfo:
                    return int(modelinfo[key])
            # Fallback: scan for any *.context_length key
            for key, value in modelinfo.items():
                if key.endswith(".context_length") and value:
                    return int(value)
        except Exception:
            pass
        return 4096

    def get_embedding_context_length(self) -> int:
        """Return the max token context length for the embedding model.

        Queries Ollama's model metadata and looks for any key ending in
        '.context_length' (e.g. 'bert.context_length', 'llama.context_length').
        Falls back to 512 if the information is unavailable.
        """
        try:
            info = self.client.show(self.embedding_model)
            modelinfo = info.modelinfo or {}
            for key, value in modelinfo.items():
                if key.endswith(".context_length"):
                    return int(value)
        except Exception:
            pass
        return 512

    def check_health(self) -> bool:
        """Check if Ollama is accessible"""
        try:
            self.client.list()
            return True
        except Exception:
            return False
