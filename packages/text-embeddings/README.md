# nolemy-text-embeddings

Reusable text embedding contracts and an optional FastEmbed provider. The package has no Vault Graph dependency or cache policy. Install `nolemy-text-embeddings[fastembed]` to use the default provider.

```python
from pathlib import Path

from text_embeddings import EmbeddingInput, EmbeddingModelSpec, FastEmbedTextEmbeddings

spec = EmbeddingModelSpec("my-model", "revision", 384, "cosine-v1")
embeddings = FastEmbedTextEmbeddings(model_spec=spec, model_path=Path("/local/pinned-model"))
vectors = embeddings.embed((EmbeddingInput("item-1", "example"),))
```

The default FastEmbed backend requires an existing local model directory and loads when a nonempty batch is embedded. Supply `backend_factory` to use a separately configured backend or a deterministic test backend. The caller is responsible for ensuring that `model_path` matches the declared `model_version`.
