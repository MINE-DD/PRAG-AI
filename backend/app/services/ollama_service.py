import ollama
from typing import Optional


class OllamaService:
    """Service for interacting with Ollama LLMs"""

    def __init__(self, url: str, model: str = "llama3", embedding_model: str = "nomic-embed-text"):
        self.url = url
        self.model = model
        self.embedding_model = embedding_model
        self.client = ollama.Client(host=url)

    def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for a single text"""
        response = self.client.embeddings(
            model=self.embedding_model,
            prompt=text
        )
        return response["embedding"]

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts"""
        embeddings = []
        for text in texts:
            embedding = self.generate_embedding(text)
            embeddings.append(embedding)
        return embeddings

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        chat_history: Optional[list[dict]] = None
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

    def check_health(self) -> bool:
        """Check if Ollama is accessible"""
        try:
            self.client.list()
            return True
        except Exception:
            return False
