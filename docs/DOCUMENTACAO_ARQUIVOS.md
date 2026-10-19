# Guia dos arquivos do projeto

Este documento descreve os arquivos versionados do Robot Report Generator e a
responsabilidade de cada um. Arquivos gerados durante a execução, como banco
SQLite, relatórios exportados, uploads temporários e `pipeline-state/`, não são
código-fonte e ficam fora do Git.

## Arquivos da raiz

| Arquivo | Responsabilidade |
|---|---|
| `AGENTS.md` | Orientações de estrutura, estilo, comandos e testes para quem trabalha no repositório. |
| `.gitignore` | Impede que bancos, resultados e outros arquivos locais sejam adicionados por engano ao Git. |
| `.dockerignore` | Define o que não deve ser enviado ao contexto durante a construção da imagem Docker. |
| `Dockerfile` | Instala as dependências e monta a imagem da aplicação web. |
| `docker-compose.yml` | Define o serviço web, a porta local e o volume persistente de dados. |
| `README.md` | Apresenta o projeto, instalação, uso da CLI, interface e Docker. |
| `docs/PLANEJAMENTO_ESCALABILIDADE.md` | Registra etapas e critérios para evolução da arquitetura. |
| `docs/TESTE_AZURE_DEVOPS_LOCAL.md` | Passo a passo para configurar o agente Linux e testar a ingestão de resultados via Azure DevOps. |
| `docs/GUIA_RECRIAR_TESTE_AZURE_DEVOPS.md` | Roteiro completo para recriar a organização, o projeto, o agente Linux e a pipeline de teste Azure DevOps. |
| `docs/SEGURANCA_ARQUITETURA.md` | Descreve os fluxos de dados, autenticação, limites de ingestão, armazenamento e pontos de atenção para revisão de segurança. |
| `docs/DOCUMENTACAO_ARQUIVOS.md` | Este inventário e mapa de responsabilidades dos arquivos. |
| `main.py` | Entrada da CLI: importa resultados, gera HTML/PDF/JSON e chama os serviços do catálogo. |
| `gui.py` | Inicializa o servidor Flask, define a origem local e anuncia o endereço da interface. |
| `models.py` | Define os modelos compartilhados de testes, suítes, métricas, histórico e relatório. |
| `pyproject.toml` | Metadados do pacote, dependências, comandos instalados e configuração do pytest. |
| `requirements.txt` | Dependências mínimas para executar a aplicação. |

## Pacote `core/`

| Arquivo | Responsabilidade |
|---|---|
| `core/__init__.py` | Marca `core` como pacote Python. |
| `core/xml_parser.py` | Lê `output.xml` do Robot Framework e converte suítes, testes, mensagens, artefatos e metadados para os modelos do projeto. |
| `core/history_manager.py` | Funções auxiliares para snapshots, detecção de testes instáveis, comparação entre execuções e normalização de datas. A persistência fica em `sqlite_store.py`. |
| `core/catalog.py` | Fachada de compatibilidade para operações de catálogo, com persistência SQLite e leitura de históricos JSON legados para migração. |
| `core/catalog_overview.py` | Calcula métricas agregadas e tendências por período para os sistemas do catálogo. |
| `core/catalog_report.py` | Renderiza um relatório consolidado ou uma cópia estática do catálogo. |
| `core/sqlite_store.py` | Mantém esquema, migrações, conexões, histórico, snapshots e artefatos no SQLite. |
| `core/database_admin.py` | Cria e restaura pacotes completos de backup e localiza arquivos de artefatos sem referência no banco. |
| `core/import_service.py` | Valida e extrai ZIPs, cria uploads temporários e encaminha execuções confirmadas ao armazenamento. |
| `core/report_renderer.py` | Monta o HTML detalhado com Jinja2 e inclui as evidências quando necessário. |
| `core/pdf_summary.py` | Gera resumos executivos e relatórios customizados em PDF (mono e multi-sistemas com seções selecionáveis) via ReportLab. |
| `core/azure_publish.py` | Publica opcionalmente o catálogo estático usando Azure Static Web Apps CLI. |
| `core/web_app.py` | Cria a aplicação Flask, define rotas HTTP, controla acesso local e conecta as interfaces aos serviços. |
| `core/web_services.py` | Valida caminhos e solicitações e oferece operações independentes de Flask para catálogo e histórico. |
| `core/web_jobs.py` | Executa importações em processos sequenciais, acompanha logs e erros e permite cancelamento. |

## Interface web: `core/web/`

| Arquivo | Responsabilidade |
|---|---|
| `core/web/templates/index.html` | Estrutura da interface local para envio de ZIP, acompanhamento, manutenção e histórico. |
| `core/web/static/app.js` | Interações da interface local, chamadas à API, importação, filtros e ações de manutenção. |
| `core/web/static/app.css` | Estilos da interface local. |
| `core/web/templates/public_catalog.html` | Página pública de seleção de sistemas e visão geral. |
| `core/web/static/public_catalog.js` | Carrega o catálogo público, desenha tendências e incorpora o relatório do sistema selecionado. |
| `core/web/static/public_catalog.css` | Estilos responsivos e temas claro/escuro do catálogo público. |

## Relatórios e recursos

| Arquivo | Responsabilidade |
|---|---|
| `templates/__init__.py` | Marca `templates` como pacote Python para distribuição. |
| `templates/report_template.html` | Documento-base do relatório standalone; inclui os fragmentos de estilo, corpo e scripts. |
| `templates/_report_styles.html` | Estilos do relatório detalhado. |
| `templates/_report_body.html` | Conteúdo e estrutura das abas executiva, técnica, versões e falhas. |
| `templates/_report_scripts.html` | Gráficos, filtros e interações do relatório detalhado. |
| `templates/catalog_template.html` | Página de catálogo que seleciona ou incorpora relatórios por sistema. |
| `assets/__init__.py` | Marca `assets` como pacote Python para distribuição. |
| `assets/chart.umd.min.js` | Arquivo opcional esperado para uso offline. Não há uma cópia de Chart.js versionada atualmente; sem ela, o relatório usa o CDN. |

## Dados de exemplo e manutenção do catálogo

| Arquivo | Responsabilidade |
|---|---|
| `example/output.xml` | Exemplo de saída do Robot Framework usado na documentação e em testes. |
| `example/history.json` | Histórico JSON de exemplo para compatibilidade com o formato antigo. |
| `example/login.robot` | Exemplo de suíte Robot Framework. |
| `robot-results/README.md` | Orientações sobre os dados e arquivos mantidos no diretório `robot-results/`. |
| `scripts/update_robot_results.py` | Comando auxiliar para listar, importar ou remover execuções do catálogo SQLite. |
| `scripts/migrate_json_catalog.py` | Migra catálogos JSON antigos ou históricos isolados para SQLite, preservando os arquivos de origem. |

## Testes

Os arquivos em `tests/` verificam componentes isolados e integrações. Os testes
de navegador são opcionais e dependem de Playwright e Chromium.

| Arquivo | Cobertura principal |
|---|---|
| `tests/__init__.py` | Marca `tests` como pacote Python. |
| `tests/test_xml_parser.py` | Extração de métricas, metadados e estrutura de testes do XML. |
| `tests/test_history_manager.py` | Persistência JSON, snapshots, comparações e identificação de flakiness. |
| `tests/test_catalog.py` | Catálogo de arquivos legado, importação e remoção. |
| `tests/test_catalog_browser.py` | Comportamento do catálogo em navegador; execução opt-in. |
| `tests/test_cli.py` | Argumentos, códigos de saída e fluxos da CLI. |
| `tests/test_multi_app.py` | Isolamento e operações com múltiplos sistemas. |
| `tests/test_pdf_summary.py` | Geração do resumo PDF. |
| `tests/test_report_renderer.py` | Conteúdo, fragmentos e renderização do relatório HTML. |
| `tests/test_sqlite_store.py` | Persistência, deduplicação e gestão de artefatos no SQLite. |
| `tests/test_update_robot_results.py` | Comando auxiliar de manutenção do catálogo. |
| `tests/test_web_app.py` | Rotas, sessão, permissões e interface local. |
| `tests/test_web_imports.py` | Validação, prévia e submissão de ZIPs pela interface. |
| `tests/test_web_services.py` | Validação e operações sem dependência de requisições Flask. |

## Fluxo de dados

`output.xml` → `xml_parser.py` → `models.py` → `import_service.py` →
`sqlite_store.py` → `report_renderer.py` → templates de relatório.

`web_app.py` recebe requisições e delega regras a `web_services.py`,
`database_admin.py`, `import_service.py` e `web_jobs.py`. A CLI em `main.py`
reutiliza o parser, o armazenamento e os renderizadores.

## Armazenamento atual e compatibilidade

O SQLite é o armazenamento persistente da interface web, CLI e scripts de
catálogo. JSON permanece somente como formato de entrada para migrar históricos
antigos e como fixture de exemplo/teste; a aplicação não grava histórico em
arquivos JSON.
