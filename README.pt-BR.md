# project-mcp

[![CI](https://github.com/jeffmodeler/project-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/jeffmodeler/project-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> 🇧🇷 Versão em português · 🇺🇸 [English version](README.md)

Servidor MCP (Model Context Protocol) que expõe arquivos do Microsoft Project
para clientes LLM como Claude Desktop e Claude Code. Lê cronogramas, recursos,
dependências, caminho crítico e variação de baseline — e adiciona camadas
de **AWP** (Advanced Work Packaging, CII) e **LPS** (Last Planner System, Lean)
para gerenciar pacotes de trabalho, restrições, compromissos semanais e PPC.
Tudo local, sem chamadas à nuvem e sem necessidade de licença do Microsoft Project.

## Por que existe

Fluxos de trabalho de construção, engenharia e BIM vivem dentro de cronogramas
do Microsoft Project. Este servidor permite que seu LLM:

- Inspecione um cronograma e responda perguntas sobre ele (prazos, caminho
  crítico, sobrealocação de recursos).
- Cruze dados de tarefas com quantitativos de modelos BIM ou com dados de
  custo de dashboards Power BI.
- Gere exportações JSON para automações downstream (dashboards, relatórios,
  pipelines ETL).

É **read-only por design**. Edições no cronograma permanecem onde devem estar:
no próprio Microsoft Project.

## Requisitos

- Python 3.11+
- Um cliente MCP compatível (Claude Desktop, Claude Code, etc.)
- Para `.xml` (MSPDI): nenhuma dependência extra
- Para `.mpp` (formato nativo do Microsoft Project): a dependência opcional
  `[mpp]` (requer JVM via pacote `mpxj`)

## Instalação

### Opção A — `uv` (recomendada)

```bash
git clone https://github.com/jeffmodeler/project-mcp.git
cd project-mcp
uv sync
```

### Opção B — `pip`

```bash
pip install git+https://github.com/jeffmodeler/project-mcp.git
```

Para suporte a `.mpp`:

```bash
uv sync --extra mpp
# ou
pip install "project-mcp[mpp] @ git+https://github.com/jeffmodeler/project-mcp.git"
```

## Integração com Claude Desktop

Adicione ao seu `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "project-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\caminho\\para\\project-mcp",
        "run",
        "project-mcp"
      ]
    }
  }
}
```

Reinicie o Claude Desktop. As 35 tools ficam disponíveis em qualquer conversa
(13 do núcleo MS Project + 10 AWP + 12 LPS).

## Tools disponíveis

| Tool | Finalidade |
|---|---|
| `load_project` | Carrega um `.xml` MSPDI ou `.mpp` na memória |
| `project_info` | Título, autor, janela do cronograma, moeda, contagens agregadas |
| `list_tasks` | Filtra tarefas por tipo, criticidade, substring no nome, top N |
| `get_task` | Registro completo de uma tarefa por UID, ID ou nome |
| `list_resources` | Recursos, opcionalmente filtrados por tipo ou sobrealocação |
| `get_resource_assignments` | Atribuições para um ou todos os recursos |
| `find_overallocated_resources` | Recursos marcados como sobrealocados |
| `get_critical_path` | Tarefas no caminho crítico, ordenadas por data de início |
| `get_predecessors_successors` | Rede de dependências de uma tarefa |
| `get_baseline_variance` | Comparação de datas e duração atual vs. baseline |
| `get_gantt_data` | Tarefas formatadas para bibliotecas de Gantt |
| `export_to_json` | Exportação completa do projeto para JSON (arquivo ou inline) |
| `generate_pbip_dashboard` | Gera um Power BI Project (.pbip) e abre no Power BI Desktop |

## Exportando `.mpp` para MSPDI XML

Se você não quer instalar Java para a dependência opcional `mpp`, exporte
seu cronograma do Microsoft Project como XML:

1. Abra o `.mpp` no Microsoft Project.
2. **Arquivo → Salvar como → Tipo de arquivo → Formato XML (\*.xml)**.
3. Aponte `load_project` para o `.xml` resultante.

O formato XML é o esquema oficial Microsoft Project Data Interchange (MSPDI)
e contém tarefas, recursos, atribuições, predecessores, baseline e a maior
parte dos metadados do projeto.

## Exemplos de prompts

Depois de carregar um projeto, pergunte ao Claude:

```
Carregue o projeto em C:\cronogramas\obra-acme.xml
Me dê o caminho crítico com duração total em dias.
Quais recursos estão sobrealocados e em quanto?
Liste as 5 tarefas com maior variação de baseline.
Exporte o projeto completo para C:\relatorios\obra-acme.json
```

## AWP — Advanced Work Packaging ✅

Metodologia do **Construction Industry Institute (CII)** que estrutura a
execução em pacotes de trabalho alinhados entre engenharia, compras e campo.

```
CWA (Construction Work Area) → CWP (Construction Work Package)
                                     ↓
                               IWP (Installation Work Package)
                    EWP (Engineering WP) + PWP (Procurement WP)
```

Foco: **path of construction** + **readiness** (nada começa no canteiro sem
materiais, documentação e acessos disponíveis).

### Tools AWP (10)

| Tool | Finalidade |
|---|---|
| `awp_list_cwa` | Lista Construction Work Areas |
| `awp_upsert_cwa` | Cria ou atualiza uma CWA |
| `awp_list_cwp` | Lista CWPs com `task_count`, `total_hours`, `any_critical` |
| `awp_upsert_cwp` | Cria ou atualiza um CWP (status: planned/ready/in-progress/complete/on-hold) |
| `awp_assign_task_to_cwp` | Vincula tarefa a um CWP (move de outro se necessário) |
| `awp_set_cwp_requirements` | Define requisitos do CWP (materiais, documentos, acessos) |
| `awp_readiness_check` | Verifica se um CWP está pronto — compara requisitos vs disponíveis |
| `awp_path_of_construction` | Sequencia CWPs por data de início com contagem de tarefas críticas |
| `awp_generate_iwps` | Quebra um CWP em IWPs limitados por horas de trabalho |
| `awp_export_wpr` | Gera Work Package Release — JSON auto-contido pro canteiro |

## LPS — Last Planner System ✅

Método de **Lean Construction** com 5 níveis de planejamento.

```
Master → Phase (pull plan) → Lookahead (N semanas, remove restrições)
                              → WWP (Weekly Work Plan) → Daily huddle
```

Métrica principal: **PPC** (Percent Plan Complete) — compromissos cumpridos /
compromissos assumidos.

### Tools LPS (12)

| Tool | Finalidade |
|---|---|
| `lps_list_phases` | Lista fases do projeto |
| `lps_upsert_phase` | Cria ou atualiza uma fase (PH-01, datas início/fim) |
| `lps_set_pull_plan` | Define sequência reversa (pull planning) com UIDs de tarefas |
| `lps_get_pull_plan` | Retorna pull plan de uma fase |
| `lps_register_constraint` | Registra restrição (material/document/labor/equipment/access/permit/…) |
| `lps_clear_constraint` | Marca restrição como resolvida |
| `lps_list_constraints` | Lista com filtros por task, status, tipo |
| `lps_lookahead` | Janela de N semanas com tarefas ready/blocked por restrições |
| `lps_add_commitment` | Adiciona compromisso a um Weekly Work Plan (ISO week `2026-W03`) |
| `lps_mark_complete` | Fecha compromisso com `actual_hours` ou `variance_reason` |
| `lps_get_wwp` | Lê WWP de uma semana |
| `lps_ppc` | Calcula PPC de uma semana ou série das últimas N semanas |

**Tipos de restrição aceitos**: `material`, `document`, `information`, `design`,
`labor`, `equipment`, `access`, `permit`, `prerequisite`, `other`.

**Razões de variance aceitas**: `weather`, `design_change`, `material_delay`,
`labor_unavailable`, `equipment_breakdown`, `rework`, `permit`,
`prerequisite_incomplete`, `scope_change`, `other`.

## Arquitetura sidecar

O `.mpp`/`.xml` permanece como fonte mestre das tarefas (read-only preservado).
Ao lado do arquivo do projeto, uma pasta `<nome>.awp/` guarda metadados que o
Project não representa bem:

```
C:\cronogramas\
├── obra-acme.mpp              ← fonte mestre (nunca modificada)
└── obra-acme.awp/             ← sidecar criado automaticamente
    ├── awp.json               ← CWA / CWP / IWP
    └── lps.json               ← phases, pull plans, constraints, WWPs
```

Cada tool de escrita atualiza `updated_at` (ISO 8601 UTC) no JSON.

## Exemplo de diálogo com AWP + LPS

```
Você: Carregue o cronograma em D:\obra\vila-idosos.mpp
Claude: [load_project]
        "342 tarefas, 28 recursos. Início 2025-01-15."

Você: Crie a CWA "Fundações" com id CWA-01 prioridade 1
Claude: [awp_upsert_cwa] "CWA-01 criada."

Você: Crie o CWP-01.01 "Fundação Bloco A" dentro da CWA-01 e
      associe as tarefas 145, 146, 147
Claude: [awp_upsert_cwp + awp_assign_task_to_cwp x3]
        "CWP-01.01 criado com 3 tarefas (total 240h, 1 crítica)."

Você: Define que esse CWP precisa de: aço CA-50, concreto fck25, AR-01
Claude: [awp_set_cwp_requirements] "Requisitos registrados."

Você: O CWP está ready? Chegou aço CA-50 e AR-01
Claude: [awp_readiness_check]
        "Não — falta: concreto fck25."

Você: Registra essa pendência como restrição material do CWP
Claude: [lps_register_constraint]
        "CST-3F2A4B91 registrada — material, responsável compras."

Você: Qual é o lookahead de 4 semanas?
Claude: [lps_lookahead(weeks=4)]
        "47 tarefas. 12 com restrições abertas. Críticas: 3."

Você: Chegou o concreto — limpa a restrição CST-3F2A4B91
Claude: [lps_clear_constraint] "Resolvida em 2025-02-03. CWP agora READY."

Você: Compromete a task 145 para o time-arq na semana 2025-W06, 40h
Claude: [lps_add_commitment] "Compromisso adicionado."

Você: No fim da semana: task 145 concluída em 42h
Claude: [lps_mark_complete] "Fechada."

Você: Calcula o PPC da semana
Claude: [lps_ppc(week='2025-W06')]
        "PPC 100% (1/1 entregue)."
```

## Desenvolvimento

```bash
uv sync --extra dev
uv run pytest -v
uv run ruff check src tests
```

## Licença

MIT — veja [LICENSE](LICENSE).
