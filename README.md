# Caslu SysCare

Aplicativo desktop de diagnóstico e suporte de TI para Windows. Identifica programas desnecessários que consomem recursos e reúne, numa só interface, as ferramentas que um técnico usa no atendimento: saúde do hardware, inicialização, rede, disco, segurança e relatório para o cliente.

Foco em Windows 10/11. Linux serve para desenvolvimento e testes.

## Problema

Em visitas de suporte, o técnico precisa cruzar Gerenciador de Tarefas, inicialização, Event Viewer, SMART, Windows Update e inventário de software. Ferramentas comerciais são pesadas ou cobram por máquina. O Caslu SysCare concentra o diagnóstico local, explica o que encontrou e só altera o sistema depois de confirmação.

## Funcionalidades

- **Saúde:** nota 0–100 com categorias explicadas; hardware (CPU, RAM, GPU, placa-mãe, BIOS); discos SMART/NVMe (Saudável / Atenção / Crítico / Desconhecido); bateria; desempenho amostrado; estabilidade e BSOD.
- **Processos:** detecta atualizadores, launchers, bloatware de fabricante, telemetria e adware; estima RAM recuperável.
- **Inicialização:** lista o que abre com o Windows, classifica impacto e desativa com desfazer.
- **Windows:** Update (somente leitura), reparo SFC/DISM/CHKDSK em modos seguros, serviços de terceiros, drivers com códigos de erro, software instalado (CSV) e logs recentes.
- **Segurança:** Defender, firewall, UAC, Secure Boot, TPM e BitLocker — consulta, sem alteração automática.
- **Rede:** interfaces, ping, DNS, teste de portas e portas em escuta com o processo dono.
- **Disco:** uso por partição, limpeza de temporários com prévia e maiores arquivos.
- **Técnico:** relatório HTML imprimível (PDF pelo navegador) e JSON; comparação antes/depois; histórico de atendimentos; caixa de ferramentas do Windows.
- **Auditoria:** cada ação vai para `audit.jsonl`. Modo portátil com o arquivo `syscare.portable` ao lado do executável.

SMART detalhado é opcional: usa `smartctl` (smartmontools) se estiver instalado. Não há telemetria nem chamadas de rede além de ping/DNS/portas disparados pelo usuário.

## Segurança das ações

Nada é encerrado ou alterado sem confirmação na interface. Processos críticos do sistema estão protegidos e não podem ser encerrados pelo app. Mudanças reversíveis ficam em `%APPDATA%\CasluSysCare\undo_log.json`. Reparo do Windows cria ponto de restauração antes de executar; se a criação falhar, a operação é abortada.

## Tecnologias

- **Python 3.10+** — lógica de diagnóstico isolada da interface (`src/syscare/core/`)
- **PySide6** — interface desktop
- **psutil** — processos, memória, serviços e métricas
- **PowerShell / CIM** — coletores Windows (um comando por área; parsers testados com fixtures)
- **pytest** — testes sem tocar no host (dados isolados; APIs Windows simuladas)
- **GitHub Actions** — testes em Ubuntu e Windows; geração do `.exe`

Dependências de runtime: somente `PySide6` e `psutil`.

## Instalação

**Windows (PowerShell), na raiz do projeto:**

```powershell
git clone https://github.com/lcsmqt/caslu-syscare.git
cd caslu-syscare
.\scripts\setup-dev.ps1    # cria .venv e instala em modo editável
.\scripts\test.ps1         # pytest (UI em offscreen)
.\scripts\run.ps1          # abre o aplicativo
```

Atalho sem PowerShell: duplo clique em `setup-dev.cmd`, depois `scripts\test.ps1` e `scripts\run.ps1`.

**Linux / macOS (desenvolvimento):**

```bash
git clone https://github.com/lcsmqt/caslu-syscare.git
cd caslu-syscare
chmod +x scripts/*.sh
./scripts/setup-dev.sh
./scripts/test.sh
./scripts/run.sh
```

### Manual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
syscare                    # ou: python -m syscare
$env:QT_QPA_PLATFORM="offscreen"; python -m pytest -q
```

## Gerar executável (Windows)

```powershell
.\build_exe.ps1
```

Saída: `dist\CasluSysCare.exe`. O workflow de CI também gera o artefato a cada push.

## Personalizar regras

Edite `src/syscare/core/knowledge.py` para incluir novos programas (regex, motivo e risco) e a lista de processos protegidos.

## Licença

MIT — Copyright (c) 2026 Lucas Mesquita / Caslu Soluções.
