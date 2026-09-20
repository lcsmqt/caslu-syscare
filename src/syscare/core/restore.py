"""Safety Center: System Restore points and the operation risk guide."""
from __future__ import annotations

import logging

from . import privilege, winutil
from .safeaction import ActionResult, Preview, Risk, SafeAction

log = logging.getLogger("syscare.restore")

LIST_PS = ("Get-ComputerRestorePoint | Select-Object SequenceNumber,Description,RestorePointType,"
           "@{n='Created';e={[Management.ManagementDateTimeConverter]::ToDateTime($_.CreationTime).ToString('yyyy-MM-dd HH:mm')}}")

RISK_GUIDE = [
    ("Ler informações (hardware, SMART, segurança, logs)", "LOW", "Somente leitura."),
    ("Verificações somente leitura (SFC /verifyonly, DISM CheckHealth/ScanHealth, CHKDSK)", "LOW", "Usa CPU/disco; não altera o sistema."),
    ("Encerrar programas desnecessários", "MEDIUM", "Trabalho não salvo é perdido; processos críticos são protegidos."),
    ("Desativar item de inicialização / alterar serviço de terceiros", "MEDIUM", "Reversível pelo Desfazer; o programa pode deixar de iniciar."),
    ("Limpar arquivos temporários", "MEDIUM", "Não vai para a Lixeira; somente pastas temporárias e com prévia."),
    ("SFC /scannow, DISM RestoreHealth, CHKDSK /scan", "MEDIUM", "Altera arquivos/metadados do sistema; recomenda-se ponto de restauração."),
    ("Apagar arquivos escolhidos pelo usuário (duplicados, grandes)", "HIGH", "Irreversível; sempre seleção manual."),
]


def parse_points(raw) -> list[dict]:
    out = []
    for p in winutil.ensure_list(raw):
        out.append({"id": p.get("SequenceNumber"), "description": winutil.val(p.get("Description")),
                    "created": winutil.val(p.get("Created")), "type": winutil.val(p.get("RestorePointType"))})
    return sorted(out, key=lambda x: str(x["created"]), reverse=True)


def list_points() -> dict:
    if not winutil.IS_WINDOWS:
        return {"points": [], "message": "Pontos de restauração disponíveis apenas no Windows."}
    raw = winutil.ps_json(LIST_PS, 30)
    if raw is None:
        return {"points": [], "message": "Não foi possível consultar a Proteção do Sistema (pode exigir administrador)."}
    pts = parse_points(raw)
    msg = "" if pts else ("Nenhum ponto de restauração encontrado. A Proteção do Sistema pode estar desativada "
                          "(Propriedades do Sistema › Proteção do Sistema).")
    return {"points": pts, "message": msg}


class RestorePointAction(SafeAction):
    name = "restore_point"
    can_elevate = True

    def __init__(self, description: str | None = None):
        if description is None:
            from .. import APP_NAME
            description = APP_NAME
        self.description = description

    def preview(self, analysis) -> Preview:
        return Preview(
            title="Criar ponto de restauração",
            description=("Cria um ponto de restauração do sistema antes de manutenção. Se a Proteção do Sistema estiver "
                         "desativada ou já houver um ponto nas últimas 24 h, o Windows pode não criar um novo."),
            risk=Risk.LOW, needs_admin=True, reversible=True,
            impact="Usa um pouco de espaço em disco; não altera seus arquivos.", items=[self.description])

    def scan(self):
        return len(list_points()["points"])

    def execute(self, analysis) -> ActionResult:
        if not winutil.IS_WINDOWS:
            return ActionResult("failed", "Pontos de restauração só existem no Windows.")
        cmd = ["powershell", "-NoProfile", "-Command",
               f"Checkpoint-Computer -Description '{self.description}' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop"]
        r = winutil.run(cmd, 180) if privilege.is_admin() else privilege.run_elevated(cmd, 300)
        if not r.ok:
            return ActionResult("failed", r.error or "O Windows não conseguiu criar o ponto de restauração.", r.text)
        return ActionResult("success", "Ponto de restauração solicitado.", r.text)

    def verify(self, analysis, result):
        if result.status != "success":
            return None
        after = len(list_points()["points"])
        ok = after > (analysis or 0)
        if not ok:
            result.status = "warning"
            result.message = ("O Windows não criou um novo ponto (limite de 1 por 24 h ou Proteção do Sistema "
                              "desativada).")
        return ok
