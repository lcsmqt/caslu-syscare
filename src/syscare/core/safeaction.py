"""Safe action pipeline: SCAN → ANALYZE → PREVIEW → CONFIRM → EXECUTE → VERIFY → LOG.

Every maintenance action that changes the system must be a SafeAction. The UI calls
`prepare()` (cheap, shows the preview), asks the user, then `commit()` in a worker.
`run_safe_action()` chains both for non-UI callers and tests. Nothing here raises.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from . import audit, privilege

log = logging.getLogger("syscare.safeaction")


class Risk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


RISK_LABEL = {Risk.LOW: "BAIXO", Risk.MEDIUM: "MÉDIO", Risk.HIGH: "ALTO"}


@dataclass
class Preview:
    title: str
    description: str
    risk: Risk = Risk.LOW
    needs_admin: bool = False
    impact: str = ""
    items: list[str] = field(default_factory=list)   # affected paths/entries/commands
    reversible: bool = False

    def as_text(self) -> str:
        lines = [self.description, ""]
        lines.append(f"Risco: {RISK_LABEL[self.risk]}")
        if self.impact:
            lines.append(f"Impacto: {self.impact}")
        lines.append("Reversível: " + ("sim" if self.reversible else "não"))
        if self.needs_admin:
            lines.append(f"{privilege.ADMIN_BADGE}: o Windows pedirá permissão (UAC).")
        if self.items:
            lines.append("")
            lines += [f"• {i}" for i in self.items[:15]]
            if len(self.items) > 15:
                lines.append(f"… e mais {len(self.items) - 15}")
        return "\n".join(lines)


@dataclass
class ActionResult:
    status: str            # success | warning | failed | cancelled | blocked
    message: str = ""
    output: str = ""
    verified: bool | None = None
    data: dict = field(default_factory=dict)


class SafeAction:
    name = "action"
    can_elevate = False    # True if execute() can request UAC itself

    def scan(self) -> Any:
        return None

    def analyze(self, scanned: Any) -> Any:
        return scanned

    def preview(self, analysis: Any) -> Preview:
        raise NotImplementedError

    def execute(self, analysis: Any) -> ActionResult:
        raise NotImplementedError

    def verify(self, analysis: Any, result: ActionResult) -> bool | None:
        return None

    def audit_target(self, analysis: Any) -> str:
        return self.name

    def previous_state(self, analysis: Any) -> Any:
        return None


def prepare(action: SafeAction) -> tuple[Any, Preview | None, ActionResult | None]:
    """SCAN → ANALYZE → PREVIEW. Returns (analysis, preview, error_result)."""
    try:
        analysis = action.analyze(action.scan())
        return analysis, action.preview(analysis), None
    except Exception as e:  # noqa: BLE001
        log.exception("prepare failed for %s", action.name)
        audit.record(action.name, "failed", details=f"prepare: {e}")
        return None, None, ActionResult("failed", "Não foi possível preparar a ação. Detalhes no log técnico.")


def commit(action: SafeAction, analysis: Any, preview: Preview) -> ActionResult:
    """EXECUTE → VERIFY → LOG (call only after explicit user confirmation)."""
    target = _safe(lambda: action.audit_target(analysis), action.name)
    previous = _safe(lambda: action.previous_state(analysis), None)
    if preview.needs_admin and not privilege.is_admin() and not action.can_elevate:
        res = ActionResult("blocked", f"{privilege.ADMIN_BADGE}. Execute o Observer como administrador.")
        audit.record(action.name, "blocked", target, previous, details=res.message)
        return res
    try:
        res = action.execute(analysis)
        try:
            res.verified = action.verify(analysis, res)
        except Exception:  # noqa: BLE001
            log.exception("verify failed for %s", action.name)
    except Exception as e:  # noqa: BLE001
        log.exception("execute failed for %s", action.name)
        res = ActionResult("failed", "A operação falhou. Detalhes no log técnico.", output=str(e))
    audit.record(action.name, res.status, target, previous, {"message": res.message, "verified": res.verified})
    return res


def run_safe_action(action: SafeAction, confirm: Callable[[Preview], bool]) -> ActionResult:
    analysis, preview, err = prepare(action)
    if err or preview is None:
        return err or ActionResult("failed", "Falha ao preparar a ação.")
    if not confirm(preview):
        audit.record(action.name, "cancelled", _safe(lambda: action.audit_target(analysis), action.name))
        return ActionResult("cancelled", "Cancelado pelo usuário.")
    return commit(action, analysis, preview)


def _safe(fn: Callable, default: Any) -> Any:
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default
