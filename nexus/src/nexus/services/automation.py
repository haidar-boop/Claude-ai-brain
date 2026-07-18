"""Automation service: persist workflow rules and load them into the engine.

This is the storage-and-wiring layer over :mod:`nexus.automation.rules`. It
saves rules (trigger + conditions + actions) as rows in ``workflow_rules``,
with the conditions and actions serialized to JSON, and can load the enabled
ones into a live :class:`~nexus.automation.rules.RuleEngine`. A UI or the
REST API drives this to let users build workflows; the engine then runs them
against the event bus at runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select

from nexus.automation.rules import ActionSpec, Condition, Rule, RuleEngine
from nexus.core.errors import NotFoundError, ValidationError
from nexus.core.events import EventBus
from nexus.core.logging import get_logger
from nexus.db.database import Database
from nexus.db.models import WorkflowRule

__all__ = ["AutomationService", "WorkflowRuleDTO"]

_logger = get_logger("services.automation")


@dataclass(frozen=True, slots=True)
class WorkflowRuleDTO:
    """A detached view of a stored workflow rule."""

    id: int
    name: str
    trigger: str
    conditions: tuple[Condition, ...]
    actions: tuple[ActionSpec, ...]
    enabled: bool

    def to_rule(self) -> Rule:
        """Convert to a runtime :class:`~nexus.automation.rules.Rule`."""
        return Rule(
            name=self.name,
            trigger=self.trigger,
            conditions=self.conditions,
            actions=self.actions,
            enabled=self.enabled,
        )


class AutomationService:
    """Create, store, and load rule-based workflows."""

    def __init__(self, database: Database, events: EventBus | None = None) -> None:
        self._db = database
        self._events = events or EventBus()

    def create_rule(
        self,
        name: str,
        trigger: str,
        *,
        conditions: list[Condition] | None = None,
        actions: list[ActionSpec] | None = None,
        enabled: bool = True,
    ) -> WorkflowRuleDTO:
        """Persist a new workflow rule."""
        clean = name.strip()
        if not clean:
            raise ValidationError("rule name must not be empty")
        if not trigger.strip():
            raise ValidationError("rule trigger must not be empty")
        with self._db.session() as session:
            if session.scalar(select(WorkflowRule).where(WorkflowRule.name == clean)) is not None:
                raise ValidationError(f"a rule named {clean!r} already exists")
            rule = WorkflowRule(
                name=clean,
                trigger=trigger.strip(),
                conditions_json=json.dumps([c.to_dict() for c in (conditions or [])]),
                actions_json=json.dumps([a.to_dict() for a in (actions or [])]),
                enabled=enabled,
            )
            session.add(rule)
            session.flush()
            dto = _rule_dto(rule)
        self._events.publish("automation.rule_created", rule_id=dto.id, name=dto.name)
        return dto

    def list_rules(self, *, enabled_only: bool = False) -> list[WorkflowRuleDTO]:
        with self._db.session() as session:
            stmt = select(WorkflowRule).order_by(WorkflowRule.name)
            if enabled_only:
                stmt = stmt.where(WorkflowRule.enabled.is_(True))
            return [_rule_dto(r) for r in session.scalars(stmt)]

    def get_rule(self, rule_id: int) -> WorkflowRuleDTO:
        with self._db.session() as session:
            rule = session.get(WorkflowRule, rule_id)
            if rule is None:
                raise NotFoundError("workflow rule", rule_id)
            return _rule_dto(rule)

    def set_enabled(self, rule_id: int, enabled: bool) -> WorkflowRuleDTO:
        with self._db.session() as session:
            rule = session.get(WorkflowRule, rule_id)
            if rule is None:
                raise NotFoundError("workflow rule", rule_id)
            rule.enabled = enabled
            session.flush()
            dto = _rule_dto(rule)
        self._events.publish("automation.rule_toggled", rule_id=rule_id, enabled=enabled)
        return dto

    def delete_rule(self, rule_id: int) -> None:
        with self._db.session() as session:
            rule = session.get(WorkflowRule, rule_id)
            if rule is None:
                raise NotFoundError("workflow rule", rule_id)
            session.delete(rule)
        self._events.publish("automation.rule_deleted", rule_id=rule_id)

    def load_into(self, engine: RuleEngine) -> int:
        """Load every enabled stored rule into *engine*; return how many.

        Called at startup (and after edits) to make the persisted workflows
        live. Only enabled rules are loaded, so toggling a rule off and
        reloading removes it from the running engine.
        """
        engine.clear()
        rules = self.list_rules(enabled_only=True)
        for dto in rules:
            engine.add_rule(dto.to_rule())
        _logger.info("loaded %d workflow rule(s) into the engine", len(rules))
        return len(rules)


def _rule_dto(rule: WorkflowRule) -> WorkflowRuleDTO:
    conditions = tuple(Condition.from_dict(c) for c in json.loads(rule.conditions_json))
    actions = tuple(ActionSpec.from_dict(a) for a in json.loads(rule.actions_json))
    return WorkflowRuleDTO(
        id=rule.id,
        name=rule.name,
        trigger=rule.trigger,
        conditions=conditions,
        actions=actions,
        enabled=rule.enabled,
    )
