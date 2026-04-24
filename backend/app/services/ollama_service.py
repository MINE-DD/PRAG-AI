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
        chat_history: list[dict] | None = None,
    ) -> str:
        """Generate text response from LLM"""
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        if chat_history:
            messages.extend(chat_history)

        messages.append({"role": "user", "content": prompt})

        opts: dict = {"temperature": temperature}
        if max_tokens is not None:
            opts["num_predict"] = max_tokens

        response = self.client.chat(
            model=self.model,
            messages=messages,
            options=opts,
        )

        return response["message"]["content"]

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
