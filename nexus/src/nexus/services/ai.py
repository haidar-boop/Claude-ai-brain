"""AI assistant service: chat, document actions, and semantic file search.

The provider abstraction is delegated to **AIForge** (the framework at this
repository's root), so Nexus supports Claude and any other AIForge provider
through one interface, with the API key read from the environment and never
stored. AIForge's ``fake`` provider is the default, so the assistant works
with zero cost and no key until the user opts into a real provider -- every
test here runs against it.

On top of that this service adds the things a productivity app needs:
- persisted chat sessions with bounded history sent as context,
- one-shot document actions (summarize, explain code, rewrite, draft email),
- semantic search over the user's indexed files via the local vector store,
  so "find my notes about onboarding" works without any content leaving the
  machine (the default embedder is offline and deterministic).

AIForge is imported lazily inside the constructor: importing this module
never requires it, and a missing install surfaces as a clear
:class:`~nexus.core.errors.AIError` pointing at how to install it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from nexus.ai.embeddings import Embedder, HashingEmbedder, VectorStore
from nexus.core.config import AIConfig
from nexus.core.errors import AIError, NotFoundError, ValidationError
from nexus.core.events import EventBus
from nexus.core.logging import get_logger
from nexus.db.database import Database
from nexus.db.models import ChatMessage, ChatSession

__all__ = ["AIService", "ChatMessageDTO", "ChatSessionDTO", "FileMatch"]

_logger = get_logger("services.ai")

_SUMMARIZE_SYSTEM = "You summarize documents faithfully and concisely. Preserve key facts."
_EXPLAIN_SYSTEM = "You explain code clearly for a competent developer: what it does and why."
_REWRITE_SYSTEM = "You rewrite text in the requested style while preserving meaning."
_EMAIL_SYSTEM = "You draft clear, professional emails. Return only the email, no preamble."


@dataclass(frozen=True, slots=True)
class ChatMessageDTO:
    """A single persisted chat message."""

    id: int
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ChatSessionDTO:
    """A chat session with its message history."""

    id: int
    title: str
    provider: str
    model: str | None
    messages: tuple[ChatMessageDTO, ...]


@dataclass(frozen=True, slots=True)
class FileMatch:
    """A semantic-search match against an indexed file."""

    file_id: int
    score: float
    snippet: str


class AIService:
    """Chat, document actions, and semantic search backed by AIForge."""

    def __init__(
        self,
        database: Database,
        config: AIConfig | None = None,
        events: EventBus | None = None,
        *,
        embedder: Embedder | None = None,
    ) -> None:
        self._db = database
        self._config = config or AIConfig()
        self._events = events or EventBus()
        self._embedder = embedder or HashingEmbedder(self._config.embedding_dimensions)
        self._vectors = VectorStore(database, self._embedder)
        self._forge = self._build_forge()

    def _build_forge(self) -> Any:
        """Construct an AIForge facade, or raise a clear AIError if missing."""
        try:
            from aiforge import AIForge
            from aiforge.config.schema import AIForgeConfig, EngineConfig
        except ImportError as exc:  # pragma: no cover - exercised only without aiforge
            raise AIError(
                "the 'aiforge' package is required for the AI assistant; install it "
                "from the repository root with `pip install -e .`"
            ) from exc
        config = AIForgeConfig(engine=EngineConfig(default_provider=self._config.default_provider))
        return AIForge(config=config)

    # -- one-shot document actions ---------------------------------------

    def summarize(self, text: str, *, model: str | None = None) -> str:
        """Return a concise summary of *text*."""
        return self._run(_SUMMARIZE_SYSTEM, f"Summarize the following:\n\n{text}", model)

    def explain_code(self, code: str, *, model: str | None = None) -> str:
        """Explain what *code* does and why."""
        return self._run(_EXPLAIN_SYSTEM, f"Explain this code:\n\n{code}", model)

    def rewrite(
        self, text: str, *, style: str = "clear and concise", model: str | None = None
    ) -> str:
        """Rewrite *text* in the requested *style*."""
        return self._run(_REWRITE_SYSTEM, f"Rewrite this in a {style} style:\n\n{text}", model)

    def generate_email(self, intent: str, *, model: str | None = None) -> str:
        """Draft an email fulfilling *intent* (e.g. 'decline a meeting politely')."""
        return self._run(_EMAIL_SYSTEM, f"Write an email to: {intent}", model)

    # -- chat -------------------------------------------------------------

    def create_session(
        self, title: str = "New chat", *, model: str | None = None
    ) -> ChatSessionDTO:
        """Start a new chat session."""
        with self._db.session() as session:
            chat = ChatSession(
                title=title.strip() or "New chat",
                provider=self._config.default_provider,
                model=model or self._config.default_model,
            )
            session.add(chat)
            session.flush()
            dto = self._session_dto(chat)
        self._events.publish("chat.session_created", session_id=dto.id)
        return dto

    def list_sessions(self) -> list[ChatSessionDTO]:
        """List chat sessions, most recently updated first."""
        with self._db.session() as session:
            chats = session.scalars(
                select(ChatSession).order_by(ChatSession.updated_at.desc())
            ).all()
            return [self._session_dto(chat) for chat in chats]

    def get_session(self, session_id: int) -> ChatSessionDTO:
        """Return a chat session with its full message history."""
        with self._db.session() as session:
            chat = session.get(ChatSession, session_id)
            if chat is None:
                raise NotFoundError("chat session", session_id)
            return self._session_dto(chat)

    def delete_session(self, session_id: int) -> None:
        """Delete a chat session and its messages."""
        with self._db.session() as session:
            chat = session.get(ChatSession, session_id)
            if chat is None:
                raise NotFoundError("chat session", session_id)
            session.delete(chat)
        self._events.publish("chat.session_deleted", session_id=session_id)

    def send_message(self, session_id: int, content: str) -> ChatMessageDTO:
        """Append a user message, get the assistant's reply, persist both.

        Only the most recent ``max_history_messages`` turns are sent as
        context, so a long conversation doesn't grow the prompt (and the
        cost) without bound. Returns the assistant's message.
        """
        text = content.strip()
        if not text:
            raise ValidationError("message content must not be empty")
        with self._db.session() as session:
            chat = session.get(ChatSession, session_id)
            if chat is None:
                raise NotFoundError("chat session", session_id)
            session.add(ChatMessage(session_id=session_id, role="user", content=text))
            session.flush()
            history = self._recent_history(session, session_id)
            model = chat.model

        prompt = _render_conversation(history)
        reply = self._run(
            "You are a helpful assistant inside a personal productivity app.", prompt, model
        )

        with self._db.session() as session:
            message = ChatMessage(session_id=session_id, role="assistant", content=reply)
            session.add(message)
            session.flush()
            dto = ChatMessageDTO(id=message.id, role="assistant", content=reply)
        self._events.publish("chat.message_sent", session_id=session_id)
        return dto

    # -- semantic file search --------------------------------------------

    def index_file_text(self, file_id: int, text: str, *, snippet: str = "") -> None:
        """Embed and store a file's text for later semantic search."""
        self._vectors.upsert("file", file_id, text, snippet=snippet or text[:200])

    def remove_file_index(self, file_id: int) -> None:
        """Drop a file's stored embedding."""
        self._vectors.remove("file", file_id)

    def semantic_search(self, query: str, *, limit: int = 10) -> list[FileMatch]:
        """Return indexed files most semantically similar to *query*."""
        hits = self._vectors.search(query, source_type="file", limit=limit)
        return [FileMatch(file_id=h.source_id, score=h.score, snippet=h.snippet) for h in hits]

    def reindex_all_files(self) -> int:
        """Embed every file already indexed by the Files service; return count.

        A convenience for building the semantic index from the file index in
        one pass (e.g. after a bulk import), using each file's stored text.
        Files with no extractable text are skipped.
        """
        from nexus.db.models import FileEntry

        with self._db.session() as session:
            payload = [
                (e.id, e.text_content, e.name) for e in session.scalars(select(FileEntry)).all()
            ]
        count = 0
        for file_id, text, name in payload:
            if text.strip():
                self._vectors.upsert("file", file_id, text, snippet=name)
                count += 1
        return count

    # -- internals --------------------------------------------------------

    def _run(self, system: str, prompt: str, model: str | None) -> str:
        try:
            response = self._forge.run(prompt, system=system, model=model)
        except Exception as exc:
            raise AIError(f"AI request failed: {exc}") from exc
        return str(response.text)

    def _recent_history(self, session: Any, session_id: int) -> list[tuple[str, str]]:
        from nexus.db.models import ChatMessage as Msg

        messages = session.scalars(
            select(Msg)
            .where(Msg.session_id == session_id)
            .order_by(Msg.created_at.desc())
            .limit(self._config.max_history_messages)
        ).all()
        return [(m.role, m.content) for m in reversed(messages)]

    def _session_dto(self, chat: ChatSession) -> ChatSessionDTO:
        return ChatSessionDTO(
            id=chat.id,
            title=chat.title,
            provider=chat.provider,
            model=chat.model,
            messages=tuple(
                ChatMessageDTO(id=m.id, role=m.role, content=m.content) for m in chat.messages
            ),
        )


def _render_conversation(history: list[tuple[str, str]]) -> str:
    """Render recent turns as a single prompt for a stateless provider call."""
    lines = [f"{role.capitalize()}: {content}" for role, content in history]
    lines.append("Assistant:")
    return "\n".join(lines)
