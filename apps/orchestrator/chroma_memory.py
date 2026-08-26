"""Persistent Vanna 2.0 ChromaDB memory for domain training and SQL retrieval."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from django.apps import apps
from django.conf import settings as django_settings
from django.db import connection
from django.utils import timezone


def _stable_id(*parts: Any) -> str:
    value = "|".join(str(part) for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _collection_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value or "glis-analytics").strip(".-")
    value = value or "glis-analytics"
    if len(value) < 3:
        value = f"glis-{value}"
    return value[:120]


class OllamaEmbeddingFunction:
    """ChromaDB embedding function backed by the configured local Ollama server."""

    def __init__(self, *, host: str, model: str, timeout: int = 120):
        try:
            import ollama
        except ImportError as exc:
            raise RuntimeError("Install the Ollama Python package from requirements.txt.") from exc
        self.host = host
        self.model = model
        self.timeout = timeout
        self.client = ollama.Client(host=host, timeout=timeout)

    def __call__(self, input):  # Chroma requires this exact parameter name.
        texts = [input] if isinstance(input, str) else list(input)
        try:
            response = self.client.embed(model=self.model, input=texts)
        except Exception as exc:
            raise RuntimeError(
                f"Ollama embedding model '{self.model}' is unavailable. "
                f"Run: ollama pull {self.model}"
            ) from exc
        embeddings = response.get("embeddings") if hasattr(response, "get") else None
        if not embeddings or len(embeddings) != len(texts):
            raise RuntimeError(f"Ollama embedding model '{self.model}' returned no embeddings.")
        return embeddings

    def embed_documents(self, input):
        return self(input)

    def embed_query(self, input):
        return self(input)

    def default_space(self):
        return "cosine"

    def supported_spaces(self):
        return ["cosine", "l2", "ip"]

    @staticmethod
    def name() -> str:
        return "glis_ollama_embedding"

    def get_config(self) -> dict[str, Any]:
        return {"host": self.host, "model": self.model, "timeout": self.timeout}

    @staticmethod
    def build_from_config(config: dict[str, Any]):
        return OllamaEmbeddingFunction(
            host=config["host"],
            model=config["model"],
            timeout=int(config.get("timeout", 120)),
        )


class ChromaDomainMemory:
    """Synchronize Admin training into Chroma and retrieve relevant SQL context."""

    MANAGED_BY = "glis-domain-sync"

    def __init__(self, *, domain, vanna_settings):
        try:
            import chromadb
            from chromadb.config import Settings
            from vanna.integrations.chromadb import ChromaAgentMemory
        except ImportError as exc:
            raise RuntimeError(
                "ChromaDB dependencies are missing. Run: pip install -r requirements.txt"
            ) from exc

        self.domain = domain
        self.settings = vanna_settings
        persist_directory = Path(
            getattr(
                django_settings,
                "CHROMA_PERSIST_DIRECTORY",
                django_settings.BASE_DIR / "data" / "chroma",
            )
        )
        persist_directory.mkdir(parents=True, exist_ok=True)
        host = vanna_settings.endpoint or getattr(
            django_settings, "OLLAMA_HOST", "http://127.0.0.1:11434"
        )
        embed_model = getattr(django_settings, "OLLAMA_EMBED_MODEL", "nomic-embed-text")
        embedding = OllamaEmbeddingFunction(
            host=host,
            model=embed_model,
            timeout=vanna_settings.timeout_seconds,
        )
        client = chromadb.PersistentClient(
            path=str(persist_directory),
            settings=Settings(anonymized_telemetry=False, allow_reset=False),
        )
        collection_name = _collection_name(domain.collection_name or domain.slug)
        self.collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding,
            metadata={"description": f"GLIS Vanna memory for {domain.slug}"},
        )
        # Use Vanna's ChromaAgentMemory as the AgentMemory implementation while
        # retaining deterministic IDs for Admin-managed training documents.
        self.agent_memory = ChromaAgentMemory(
            persist_directory=str(persist_directory),
            collection_name=collection_name,
            embedding_function=embedding,
        )
        self.agent_memory._client = client
        self.agent_memory._collection = self.collection
        self.collection_name = collection_name

    def _model_ddl(self, table_name: str) -> str:
        model = next(
            (model for model in apps.get_models() if model._meta.db_table == table_name),
            None,
        )
        if model is None:
            return f"TABLE {table_name}: use only columns documented in approved Admin training."
        columns = []
        for field in model._meta.fields:
            column = field.column
            data_type = field.db_type(connection) or field.get_internal_type()
            details = [f"{column} {data_type}"]
            if not field.null:
                details.append("NOT NULL")
            if field.primary_key:
                details.append("PRIMARY KEY")
            if getattr(field, "remote_field", None) and field.remote_field.model:
                details.append(f"REFERENCES {field.remote_field.model._meta.db_table}(id)")
            columns.append(" ".join(details))
        return f"CREATE TABLE {table_name} (\n  " + ",\n  ".join(columns) + "\n);"

    def _training_documents(self) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []

        def add(source_type: str, source_id: Any, content: str):
            content = str(content or "").strip()
            if not content:
                return
            doc_id = _stable_id(self.domain.slug, source_type, source_id)
            documents.append(
                {
                    "id": doc_id,
                    "document": content,
                    "metadata": {
                        "content": content,
                        "source_type": source_type,
                        "source_id": str(source_id),
                        "managed_by": self.MANAGED_BY,
                        "fingerprint": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                        "updated_at": timezone.now().isoformat(),
                        "is_text_memory": True,
                    },
                }
            )

        add("domain", self.domain.pk, f"DOMAIN {self.domain.name}: {self.domain.description}\n{self.domain.schema_context}")
        for table_name in self.domain.allowed_tables:
            add("ddl", table_name, self._model_ddl(table_name))
        for item in self.domain.business_rules.filter(is_active=True):
            add(
                "business_rule",
                item.pk,
                f"BUSINESS RULE {item.name}: {item.rule_text}\nSQL GUIDANCE: {item.sql_guidance}",
            )
        for item in self.domain.training_prompts.filter(is_active=True):
            add(
                "training_prompt",
                item.pk,
                f"{item.prompt_type.upper()} PROMPT {item.name} v{item.version}: {item.content}",
            )
        for item in self.domain.training_candidates.filter(status__in=["approved", "trained"]):
            if item.kind == "question_sql":
                content = f"APPROVED EXAMPLE\nQUESTION: {item.question}\nSQL: {item.sql}"
            else:
                content = f"APPROVED {item.kind.upper()}: {item.content or item.sql}"
            add("training_candidate", item.pk, content)
        for item in self.domain.table_policies.all():
            add(
                "table_policy",
                item.pk,
                f"TABLE POLICY: {item.table_name}; access={item.access}; roles={item.allowed_roles}",
            )
        for item in self.domain.column_policies.all():
            add(
                "column_policy",
                item.pk,
                f"COLUMN POLICY: {item.table_name}.{item.column_name}; "
                f"sensitivity={item.sensitivity}; access={item.default_access}",
            )
        for item in self.domain.row_policies.filter(is_active=True):
            add(
                "row_policy",
                item.pk,
                f"ROW POLICY {item.name}: table={item.table_name}; "
                f"predicate={item.predicate_template}; roles={item.allowed_roles}",
            )
        return documents

    def sync_from_admin(self) -> int:
        documents = self._training_documents()
        current = self.collection.get(where={"managed_by": self.MANAGED_BY}, include=["metadatas"])
        existing = {
            item_id: (metadata or {}).get("fingerprint")
            for item_id, metadata in zip(current.get("ids", []), current.get("metadatas", []))
        }
        desired_ids = {item["id"] for item in documents}
        stale_ids = [item_id for item_id in existing if item_id not in desired_ids]
        if stale_ids:
            self.collection.delete(ids=stale_ids)
        changed = [
            item for item in documents if existing.get(item["id"]) != item["metadata"]["fingerprint"]
        ]
        if changed:
            self.collection.upsert(
                ids=[item["id"] for item in changed],
                documents=[item["document"] for item in changed],
                metadatas=[item["metadata"] for item in changed],
            )
        trained_candidates = {
            int(item["metadata"]["source_id"]): item["id"]
            for item in documents
            if item["metadata"]["source_type"] == "training_candidate"
            and item["metadata"]["source_id"].isdigit()
        }
        for candidate in self.domain.training_candidates.filter(
            pk__in=trained_candidates, status="approved"
        ):
            candidate.status = "trained"
            candidate.external_training_id = trained_candidates[candidate.pk]
            candidate.save(update_fields=["status", "external_training_id", "updated_at"])
        return len(changed)

    def retrieve(self, question: str) -> list[dict[str, Any]]:
        count = self.collection.count()
        if count == 0:
            return []
        limit = min(max(int(self.settings.chroma_top_k), 1), count)
        result = self.collection.query(
            query_texts=[question],
            n_results=limit,
            include=["documents", "metadatas", "distances"],
        )
        output = []
        for document, metadata, distance in zip(
            result.get("documents", [[]])[0],
            result.get("metadatas", [[]])[0],
            result.get("distances", [[]])[0],
        ):
            output.append(
                {
                    "content": document,
                    "source_type": (metadata or {}).get("source_type", "memory"),
                    "distance": float(distance),
                }
            )
        return output

    def remember_success(self, *, question: str, sql: str, summary: str) -> None:
        if not self.settings.chroma_auto_train_successful_queries:
            return
        content = f"SUCCESSFUL EXAMPLE\nQUESTION: {question}\nSQL: {sql}\nSUMMARY: {summary}"
        item_id = _stable_id(self.domain.slug, "successful_query", question, sql)
        self.collection.upsert(
            ids=[item_id],
            documents=[content],
            metadatas=[
                {
                    "content": content,
                    "source_type": "successful_query",
                    "source_id": item_id,
                    "managed_by": "glis-query-memory",
                    "fingerprint": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "updated_at": timezone.now().isoformat(),
                    "is_text_memory": True,
                    "question": question,
                    "tool_name": "run_sql",
                    "args_json": json.dumps({"sql": sql}),
                    "success": True,
                }
            ],
        )
