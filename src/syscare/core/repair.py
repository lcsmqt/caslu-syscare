"""Windows Repair Center: SFC, DISM and read-only CHKDSK modes.

Each command has an explanation, impact, risk and admin requirement shown BEFORE running.
Nothing runs without explicit confirmation (SafeAction pipeline). Destructive CHKDSK modes
(/f, /r, /x) are intentionally NOT exposed: they can require dismounting volumes/reboots.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from . import audit, privilege, winutil
from .safeaction import ActionResult, Preview, Risk, SafeAction

log = logging.getLogger("syscare.repair")

OK, WARNING, FAILED = "success", "warning", "failed"


@dataclass(frozen=True)
class RepairCommand:
    id: str
    title: str
    command: tuple[str, ...]
    explanation: str
    impact: str
    duration: str
    risk: Risk
    needs_admin: bool = True
    read_only: bool = True
    timeout: int = 7200


CATALOG: list[RepairCommand] = [
    RepairCommand("dism_check", "DISM — CheckHealth",
                  ("DISM", "/Online", "/Cleanup-Image", "/CheckHealth"),
                  "Consulta rapidamente se o Windows já marcou o repositório de componentes como corrompido. "
                  "Não faz varredura profunda.", "Somente leitura; não altera o sistema.", "segundos", Risk.LOW),
    RepairCommand("dism_scan", "DISM — ScanHealth",
                  ("DISM", "/Online", "/Cleanup-Image", "/ScanHealth"),
                  "Varredura completa do repositório de componentes do Windows para detectar corrupção.",
                  "Somente leitura; usa CPU/disco por alguns minutos.", "5–15 minutos", Risk.LOW),
    RepairCommand("sfc_verify", "SFC — verificar apenas",
                  ("sfc", "/verifyonly"),
                  "Verifica a integridade dos arquivos protegidos do Windows sem corrigir nada.",
                  "Somente leitura; usa disco/CPU.", "10–30 minutos", Risk.LOW),
    RepairCommand("chkdsk_ro", "CHKDSK — verificação somente leitura (C:)",
                  ("chkdsk", "C:"),
                  "Analisa o sistema de arquivos do volume C: sem corrigir nada.",
                  "Somente leitura; pode ser lento e reportar 'em uso'.", "5–20 minutos", Risk.LOW),
    RepairCommand("chkdsk_scan", "CHKDSK /scan — verificação online (C:)",
                  ("chkdsk", "C:", "/scan"),
                  "Verificação online do NTFS com o volume montado; pode corrigir problemas leves de metadados.",
                  "Pode corrigir erros do sistema de arquivos; sem reinicialização.", "5–30 minutos", Risk.MEDIUM,
                  read_only=False),
    RepairCommand("sfc_scannow", "SFC — verificar e reparar",
                  ("sfc", "/scannow"),
                  "Verifica os arquivos protegidos do Windows e substitui os corrompidos por cópias em cache.",
                  "Altera arquivos de sistema (somente os corrompidos). Recomendável ter backup/ponto de restauração.",
                  "10–30 minutos", Risk.MEDIUM, read_only=False),
    RepairCommand("dism_restore", "DISM — RestoreHealth",
                  ("DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"),
                  "Repara o repositório de componentes do Windows, baixando arquivos bons do Windows Update se "
                  "necessário.", "Altera componentes do sistema e usa a internet (Windows Update). "
                  "Não interrompa durante a execução.", "10–40 minutos", Risk.MEDIUM, read_only=False),
]
BY_ID = {c.id: c for c in CATALOG}


# ------------------------------------------------------------------ result classification (pure)
def _has(text: str, *patterns: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def classify_result(cmd_id: str, returncode: int | None, output: str) -> tuple[str, str]:
    """Return (status, summary) from exit code and (en/pt-BR) output text."""
    t = output or ""
    if cmd_id.startswith("sfc"):
        if _has(t, r"did not find any integrity violations", r"não encontrou nenhuma viola"):
            return OK, "Nenhuma violação de integridade encontrada."
        if _has(t, r"found corrupt files and successfully repaired", r"encontrou arquivos corrompidos e os reparou",
                r"successfully repaired them"):
            return WARNING, "Arquivos corrompidos foram encontrados e reparados. Reinicie o computador."
        if _has(t, r"found corrupt files but was unable to fix", r"não pôde reparar", r"não foi possível reparar"):
            return FAILED, "Arquivos corrompidos foram encontrados e não puderam ser reparados. " \
                           "Execute DISM RestoreHealth e repita o SFC."
        if _has(t, r"found integrity violations", r"encontrou viola"):
            return WARNING, "Violações de integridade encontradas. Use 'SFC — verificar e reparar'."
        if _has(t, r"system repair pending", r"reparo do sistema pendente", r"reinicialização pendente"):
            return WARNING, "Há um reparo/reinicialização pendente. Reinicie o Windows e tente novamente."
        if _has(t, r"must be an administrator", r"deve ser um administrador", r"administrador"):
            return FAILED, "É necessário executar como administrador."
    elif cmd_id.startswith("dism"):
        if _has(t, r"no component store corruption detected", r"nenhuma corrup"):
            return OK, "Nenhuma corrupção do repositório de componentes detectada."
        if _has(t, r"component store is repairable", r"repositório de componentes pode ser reparado"):
            return WARNING, "O repositório de componentes está corrompido, mas é reparável (DISM RestoreHealth)."
        if _has(t, r"restore operation completed successfully", r"operação de restauração foi concluída"):
            return OK, "Restauração concluída com êxito."
        if _has(t, r"error: 740", r"elevated", r"elevad"):
            return FAILED, "É necessário executar como administrador."
        if _has(t, r"source files could not be found", r"arquivos de origem não puderam"):
            return FAILED, "Arquivos de origem não encontrados. Verifique a conexão com a internet/Windows Update."
        if _has(t, r"operation completed successfully", r"operação foi concluída com êxito"):
            return OK, "Operação concluída com êxito."
    elif cmd_id.startswith("chkdsk"):
        if _has(t, r"found no problems", r"não encontrou problemas", r"não foram encontrados problemas"):
            return OK, "Nenhum problema encontrado no sistema de arquivos."
        if _has(t, r"errors found", r"foram encontrados erros", r"corrupt"):
            return WARNING, "Foram encontrados erros no sistema de arquivos. Faça backup antes de reparar."
        if _has(t, r"access denied", r"acesso negado", r"privilége", r"privileg"):
            return FAILED, "Acesso negado: execute como administrador."
    if returncode == 0:
        return OK, "Comando concluído (código 0)."
    if returncode is None:
        return FAILED, "O comando não pôde ser executado."
    return FAILED, f"O comando terminou com código {returncode}."


# ------------------------------------------------------------------ SafeAction
class RepairAction(SafeAction):
    can_elevate = True

    def __init__(self, cmd: RepairCommand):
        self.cmd = cmd
        self.name = f"repair:{cmd.id}"

    def preview(self, analysis) -> Preview:
        c = self.cmd
        return Preview(
            title=c.title,
            description=f"{c.explanation}\n\nComando: {' '.join(c.command)}\nDuração estimada: {c.duration}",
            risk=c.risk, needs_admin=c.needs_admin, impact=c.impact,
            reversible=c.read_only, items=[" ".join(c.command)])

    def audit_target(self, analysis) -> str:
        return " ".join(self.cmd.command)

    def execute(self, analysis) -> ActionResult:
        c = self.cmd
        if not winutil.IS_WINDOWS:
            return ActionResult(FAILED, "Ferramentas de reparo só existem no Windows.")
        if c.needs_admin and not privilege.is_admin():
            r = privilege.run_elevated(list(c.command), c.timeout)
        else:
            r = winutil.run(list(c.command), c.timeout)
        if r.timed_out:
            return ActionResult(FAILED, "Tempo esgotado. A operação pode ainda estar em andamento no Windows.",
                                r.text)
        if r.error and not r.text:
            return ActionResult(FAILED, r.error)
        status, summary = classify_result(c.id, r.returncode, r.text)
        return ActionResult(status, summary, r.text, data={"returncode": r.returncode, "command": list(c.command)})


def recent_results(limit: int = 20) -> list[dict]:
    """Repair outcomes from the audit trail (for the maintenance report)."""
    return [e for e in audit.read(500) if str(e.get("action", "")).startswith("repair:")][-limit:]
