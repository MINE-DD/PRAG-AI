"""HuggingFace Transformers LLM and multimodal service.

Provides text generation, dense embeddings, and vision-language model (VLM)
inference using locally loaded HuggingFace models. All models are lazily
loaded on first use and cached for subsequent calls.

Install optional dependencies before use:
    uv sync --extra huggingface
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import PIL.Image

logger = logging.getLogger(__name__)


class HuggingFaceService:
    """LLM, embedding, and multimodal service via HuggingFace Transformers.

    All three capabilities (text generation, embeddings, VLM) share a single
    service instance. Models are loaded lazily on first use and kept in memory.

    Args:
        model_id: HuggingFace model ID for text generation.
        embedding_model_id: HuggingFace model ID for dense embeddings.
        vlm_model_id: HuggingFace model ID for vision-language inference.
            Required only when calling ``generate_multimodal`` or
            ``extract_from_image``.
    """

    def __init__(
        self,
        model_id: str = "Qwen/Qwen2.5-3B-Instruct",
        embedding_model_id: str = "sentence-transformers/all-MiniLM-L6-v2",
        vlm_model_id: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.embedding_model_id = embedding_model_id
        self.vlm_model_id = vlm_model_id

        # Lazy-loaded — populated on first use
        self._text_pipe = None
        self._embed_tokenizer = None
        self._embed_model = None
        self._vlm_pipe = None

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_device() -> str:
        """Return the best available device: CUDA > MPS (Apple Silicon) > CPU."""
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _get_text_pipe(self):
        if self._text_pipe is None:
            from transformers import pipeline

            logger.info("Loading text-generation model: %s", self.model_id)
            self._text_pipe = pipeline(
                "text-generation",
                model=self.model_id,
                device=self._get_device(),
                torch_dtype="auto",
            )
        return self._text_pipe

    def _get_embed_model(self):
        if self._embed_model is None:
            from transformers import AutoModel, AutoTokenizer

            logger.info("Loading embedding model: %s", self.embedding_model_id)
            self._embed_tokenizer = AutoTokenizer.from_pretrained(
                self.embedding_model_id
            )
            self._embed_model = AutoModel.from_pretrained(
                self.embedding_model_id,
                torch_dtype="auto",
            ).to(self._get_device())
            self._embed_model.eval()
        return self._embed_tokenizer, self._embed_model

    def _get_vlm_pipe(self):
        if self._vlm_pipe is None:
            if not self.vlm_model_id:
                raise ValueError(
                    "vlm_model_id is not set. Pass a VLM model ID to HuggingFaceService "
                    "to use multimodal capabilities."
                )
            from transformers import pipeline

            logger.info("Loading vision-language model: %s", self.vlm_model_id)
            self._vlm_pipe = pipeline(
                "image-text-to-text",
                model=self.vlm_model_id,
                device=self._get_device(),
                torch_dtype="auto",
            )
        return self._vlm_pipe

    @staticmethod
    def _mean_pool(token_embeddings, attention_mask) -> list[float]:
        """Mean-pool token embeddings, ignoring padding tokens, then L2-normalise."""
        import torch
        import torch.nn.functional as F

        mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        pooled = torch.sum(token_embeddings * mask, 1) / torch.clamp(
            mask.sum(1), min=1e-9
        )
        normalised = F.normalize(pooled, p=2, dim=1)
        return normalised[0].cpu().tolist()

    # ──────────────────────────────────────────────────────────────────────
    # Text interface — mirrors OllamaService
    # ──────────────────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        """Generate a text response from the loaded instruction-tuned model.

        Args:
            prompt: User message.
            system: Optional system prompt.
            temperature: Sampling temperature (0 = greedy).
            max_tokens: Maximum new tokens to generate.

        Returns:
            Generated text string.
        """
        pipe = self._get_text_pipe()
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        result = pipe(
            messages,
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
        )
        generated = result[0]["generated_text"]
        # Pipeline returns the full conversation list; take the last assistant turn.
        if isinstance(generated, list):
            return str(generated[-1]["content"])
        return str(generated)

    def generate_embedding(self, text: str) -> list[float]:
        """Generate a dense embedding vector for *text* via mean pooling.

        Args:
            text: Input text to embed.

        Returns:
            L2-normalised embedding as a list of floats.
        """
        import torch

        tokenizer, model = self._get_embed_model()
        encoded = tokenizer(text, padding=True, truncation=True, return_tensors="pt")
        device = next(model.parameters()).device
        encoded = {k: v.to(device) for k, v in encoded.items()}

        with torch.no_grad():
            outputs = model(**encoded)

        return self._mean_pool(outputs.last_hidden_state, encoded["attention_mask"])

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input strings.

        Returns:
            List of embedding vectors.
        """
        return [self.generate_embedding(t) for t in texts]

    def check_health(self) -> bool:
        """Return True if the text model loads without error."""
        try:
            self._get_text_pipe()
            return True
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────────────
    # Multimodal interface — VLM
    # ──────────────────────────────────────────────────────────────────────

    def generate_multimodal(
        self,
        prompt: str,
        images: list[PIL.Image.Image],
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        """Generate a response from a VLM given text and one or more images.

        Args:
            prompt: User text prompt.
            images: List of PIL Image objects to include in the request.
            system: Optional system prompt.
            max_tokens: Maximum tokens to generate.

        Returns:
            Generated text response.
        """
        pipe = self._get_vlm_pipe()

        content: list[dict] = [{"type": "image", "image": img} for img in images]
        content.append({"type": "text", "text": prompt})

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})

        result = pipe(messages, max_new_tokens=max_tokens)
        generated = result[0]["generated_text"]
        if isinstance(generated, list):
            return str(generated[-1]["content"])
        return str(generated)

    def extract_from_image(
        self,
        image: PIL.Image.Image,
        prompt: str = (
            "Extract all text content from this image exactly as it appears. "
            "Preserve headings, paragraphs, lists, and tables using Markdown formatting. "
            "Do not add commentary — output only the extracted content."
        ),
    ) -> str:
        """Run OCR-like text extraction on a single image using the VLM.

        Suitable for scanned PDFs, figures with embedded text, or any image
        where layout-based converters (Docling, PyMuPDF) are insufficient.

        Args:
            image: PIL Image to extract text from.
            prompt: Extraction instruction prompt for the VLM.

        Returns:
            Extracted text in Markdown format.
        """
        return self.generate_multimodal(prompt=prompt, images=[image])
