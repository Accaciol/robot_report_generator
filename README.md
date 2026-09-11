# Gerador de Relatório Customizado — Robot Framework

Gerador de relatórios HTML modernos, interativos e standalone (com CSS, JavaScript e evidências embutidos em Base64) a partir das saídas `output.xml` do **Robot Framework** (BDD + BrowserLibrary / SeleniumLibrary).

## Estrutura do Projeto
```
robot_report_generator/
├── pyproject.toml              # Metadados do pacote e entrypoints CLI (robot-report / robot-report-gui)
├── requirements.txt            # Dependências mínimas de produção
├── main.py                     # Orquestrador de linha de comando (CLI)
├── gui.py                      # Interface desktop multiplataforma (Tkinter)
├── models.py                   # Dataclasses tipadas (Status, SuiteResult, TestResult, ...)
├── core/
│   ├── xml_parser.py           # output.xml -> dataclasses (Robot Framework Visitor)
│   ├── history_manager.py      # Persistência e rotação de history.json
│   └── report_renderer.py      # Renderização HTML standalone (Jinja2 + Base64 com cache)
├── templates/
│   └── report_template.html    # Template com abas executiva / técnica / versões / falhas
├── assets/
│   └── chart.umd.min.js        # (Opcional) Build UMD do Chart.js para relatório 100% offline
└── tests/                      # Suíte de testes automatizados (unittest / pytest)
    ├── test_xml_parser.py
    ├── test_history_manager.py
    ├── test_report_renderer.py
    └── test_cli.py
```

## Instalação

### Instalação como pacote CLI (Recomendado)
```bash
pip install -e .
```
Isso disponibiliza os comandos diretos no seu terminal:
- `robot-report`: Linha de comando para gerar relatórios.
- `robot-report-gui`: Abre a interface gráfica.

### Instalação tradicional via requirements
```bash
pip install -r requirements.txt
```

> **Dica para uso 100% offline**: O relatório utiliza o Chart.js para exibir gráficos de tendência. Caso haja conexão à internet, ele carrega automaticamente via CDN da JSDelivr. Se você deseja manter o relatório estritamente offline, baixe o arquivo `chart.umd.min.js` (Chart.js 4.x UMD) e salve-o na pasta `assets/chart.umd.min.js`.

---

## Como Usar

### 1. Via Linha de Comando (CLI)
Após executar seus testes com `robot`, gere o relatório apontando para a pasta de resultados:

```bash
python main.py --results-dir caminho/para/results --history history.json --report relatorio.html
```
ou, se instalado como pacote:
```bash
robot-report --results-dir caminho/para/results
```

#### Opções de Linha de Comando:
| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--output-xml` | `<results-dir>/output.xml` | Caminho explícito para o arquivo `output.xml`. |
| `--results-dir` | Diretório atual | Pasta com o `output.xml` e evidências (screenshots e vídeos). |
| `--history` | `history.json` | Arquivo para leitura e persistência do histórico de execuções. |
| `--report` | `relatorio.html` | Caminho do arquivo HTML final gerado. |
| `--title` | `"Relatório de Execução — Testes BDD"` | Título exibido no cabeçalho e na aba do navegador. |
| `--fail-on-error` | `False` | **Ideal para CI/CD**: encerra o processo com código de saída `1` se houver testes com falha. |
| `--no-history` | `False` | Gera o relatório sem persistir nem atualizar o arquivo de histórico. |
| `--no-embed-artifacts`| `False` | Não converte imagens em Base64, referenciando-as pelo caminho local relativo. |

### 2. Via Interface Gráfica (Desktop)
```bash
python gui.py
# ou
robot-report-gui
```
Recursos da interface:
- Multiplataforma (Windows, Linux e macOS).
- Permite enfileirar múltiplas pastas `results` para processamento sequencial.
- Botão **Cancelar** para interromper execuções longas.
- Botão **Abrir relatório** que abre o navegador padrão do sistema com segurança.
- Console de log integrado com autolimpeza de memória para execuções volumosas.

---

## Funcionalidades do Relatório HTML

O relatório gerado é um arquivo único, interativo e responsivo:

1. **Visão Executiva (PO / Gestão)**:
   - Cards com contagem de testes (Total, Pass, Fail, Skip, Taxa de Sucesso e Duração).
   - Gráfico de tendência histórica com histórico das últimas 30 execuções.
   - **⏱️ Painel de Testes Mais Lentos (Top 10)**: Identifica testes demorados e potenciais gargalos.
   - Resumo consolidado por Feature/Suíte.

2. **Visão Técnica (Dev / QA)**:
   - **🔍 Busca em Tempo Real**: Filtre testes por nome, tags ou documentação instantaneamente.
   - **Filtros por Status**: Botões rápidos para alternar entre `[Todos]`, `[Falhas (FAIL)]`, `[Passou (PASS)]` e `[Ignorado (SKIP)]`.
   - **🏷️ Painel de Tags**: Visualize a frequência de tags e filtre testes clicando na tag desejada.
   - Árvore de execução expansível com botões *Expandir tudo* / *Recolher tudo*.
   - Screenshots e vídeos sob demanda (carregados somente ao expandir o nó) com lightbox ampliado ao clicar.

3. **Resumo de Falhas**:
   - Cards detalhados com suíte, passo falho e mensagem de erro/stack trace.
   - **📋 Botão Copiar Erro**: Copia os detalhes da falha para a área de transferência com 1 clique (para abertura ágil de chamados no Jira/GitHub).

4. **Comparação de Versões**:
   - Compara a execução selecionada com a anterior, apontando testes adicionados, removidos, mantidos ou que sofreram regressão de status.

5. **Modo Escuro (Dark Mode)**:
   - Alternador de tema no cabeçalho com detecção automática da preferência do sistema operacional e persistência via `localStorage`.

---

## Executando os Testes Automatizados

A base conta com suíte de testes unitários e de integração:

```bash
# Execução nativa (sem dependências extras):
python3 -m unittest discover -s tests -v

# Ou com pytest (se instalado):
pytest -v
```
