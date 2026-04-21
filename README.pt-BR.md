# project-mcp

[![CI](https://github.com/jeffmodeler/project-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/jeffmodeler/project-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> 🇧🇷 Versão em português · 🇺🇸 [English version](README.md)

Servidor MCP (Model Context Protocol) que expõe arquivos do Microsoft Project
para clientes LLM como Claude Desktop e Claude Code. Lê cronogramas, recursos,
dependências, dados de caminho crítico e variação de baseline — tudo local,
sem chamadas à nuvem e sem necessidade de licença do Microsoft Project.

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

Reinicie o Claude Desktop. As 13 tools ficam disponíveis em qualquer conversa.

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

## Roadmap — AWP e LPS

Próximas metodologias planejadas, ambas expostas como **tools MCP consumidas
via chat** (sem GUI própria — o Claude interpreta pedidos em linguagem natural
e chama as tools).

### AWP — Advanced Work Packaging

Metodologia do **Construction Industry Institute (CII)** que estrutura a
execução em pacotes de trabalho alinhados entre engenharia, compras e campo:

```
CWA (Construction Work Area) → CWP (Construction Work Package)
                                     ↓
                               IWP (Installation Work Package)
                    EWP (Engineering WP) + PWP (Procurement WP)
```

Foco: **path of construction** + **readiness** (nada começa no canteiro sem
materiais, documentação e acessos disponíveis).

#### Tools AWP planejadas

| Tool | Finalidade |
|---|---|
| `awp_list_cwa` | Lista Construction Work Areas (via WBS ou sidecar) |
| `awp_list_cwp` | Lista CWPs com tarefas associadas e status |
| `awp_assign_task_to_cwp` | Vincula tarefa a um CWP (grava no sidecar JSON) |
| `awp_path_of_construction` | Sequencia CWPs por dependências (caminho crítico de pacotes) |
| `awp_readiness_check` | Verifica se um CWP tem tudo pronto: materiais, docs, acesso |
| `awp_generate_iwp` | Quebra um CWP em IWPs por restrição de duração/tamanho |
| `awp_export_wpr` | Gera Work Package Release — pacote pronto para o canteiro |

### LPS — Last Planner System

Método de **Lean Construction** com 5 níveis de planejamento:

```
Master → Phase (pull plan) → Lookahead (6 semanas, remove restrições)
                              → WWP (Weekly Work Plan) → Daily huddle
```

Métricas principais: **PPC** (Percent Plan Complete), motivos de não-cumprimento,
variance.

#### Tools LPS planejadas

| Tool | Finalidade |
|---|---|
| `lps_phase_pull_plan_get` | Lê pull plan da fase |
| `lps_phase_pull_plan_set` | Grava sequência reversa de uma fase (pull planning) |
| `lps_lookahead` | Janela de N semanas à frente com restrições |
| `lps_register_constraint` | Adiciona restrição a uma tarefa (tipo, responsável, prazo) |
| `lps_clear_constraint` | Remove restrição quando resolvida |
| `lps_weekly_work_plan` | Compromissos da semana + status |
| `lps_mark_complete` | Fecha tarefa do WWP (alimenta PPC) |
| `lps_ppc` | Calcula PPC por semana/equipe + motivos de variance |

### Arquitetura prevista

**Abordagem sidecar** — o `.mpp` permanece como fonte mestre de tarefas
(read-only preservado). Ao lado de cada projeto, uma pasta `<nome>.awp/`
guarda metadados que o Project não representa bem:

```
C:\cronogramas\
├── obra-acme.mpp              ← fonte mestre (não modificado)
└── obra-acme.awp/             ← sidecar criado pelo project-mcp
    ├── cwa-cwp.json           ← hierarquia AWP
    ├── constraints.json       ← restrições LPS
    ├── wwp.json               ← weekly work plans + compromissos
    └── ppc-history.json       ← histórico de PPC semanal
```

### Exemplo de diálogo com AWP/LPS

```
Você: "Carrega o cronograma em D:\obra\vila-idosos.mpp"
Claude: [load_project]
        "342 tarefas, 28 recursos. Início 2025-01-15."

Você: "Qual é o lookahead de 4 semanas e quais tarefas têm restrições?"
Claude: [lps_lookahead(weeks=4)]
        "47 tarefas nas próximas 4 semanas. 12 com restrições abertas:
         - #145 'Forma P2' falta aço CA-50
         - #167 'Revestimento sala 3' falta projeto executivo..."

Você: "Chegou o aço, remove essa restrição"
Claude: [lps_clear_constraint(task=145, id='material-aco')]
        "Restrição removida. Task #145 agora está READY."

Você: "Calcula o PPC da semana passada"
Claude: [lps_ppc(week='2025-04-14')]
        "PPC = 73% (11 de 15 tarefas cumpridas).
         Motivos das 4 falhas: chuva (2), retrabalho (1), material (1)."
```

### Status

- 🚧 **Em design** — especificação sendo escrita
- ⏳ **Não implementado ainda** — as tools acima não existem no código
- 📖 **Documentado aqui** como referência para contribuidores e usuários

Abra uma issue em [Issues](https://github.com/jeffmodeler/project-mcp/issues)
para discutir prioridades ou contribuir com a implementação.

## Desenvolvimento

```bash
uv sync --extra dev
uv run pytest -v
uv run ruff check src tests
```

## Licença

MIT — veja [LICENSE](LICENSE).
