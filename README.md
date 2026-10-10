# Gerador de Relatório Customizado — Robot Framework

Gerador de relatórios HTML modernos, interativos e standalone (com CSS, JavaScript e evidências embutidos em Base64) a partir das saídas `output.xml` do **Robot Framework** (BDD + BrowserLibrary / SeleniumLibrary).

## Estrutura do Projeto
```
robot_report_generator/
├── pyproject.toml              # Metadados do pacote e entrypoints CLI (robot-report / robot-report-gui)
├── requirements.txt            # Dependências mínimas de produção
├── main.py                     # Orquestrador de linha de comando (CLI)
├── gui.py                      # Inicialização da interface web local (Flask)
├── models.py                   # Dataclasses tipadas (Status, SuiteResult, TestResult, ...)
├── core/
│   ├── xml_parser.py           # output.xml -> dataclasses (Robot Framework Visitor)
│   ├── sqlite_store.py        # Persistência transacional do histórico SQLite
│   ├── database_admin.py      # Backup completo, restauração e limpeza de artefatos
│   ├── import_service.py      # Ingestão segura de ZIPs e pastas
│   ├── report_renderer.py      # Renderização HTML standalone (Jinja2 + Base64 com cache)
│   ├── web_app.py              # Rotas, autenticação e respostas HTTP da interface local
│   ├── web_services.py         # Validação de pedidos e operações de catálogo/histórico
│   ├── web_jobs.py             # Coordenação da fila e execução de cada item
│   └── web/                    # HTML, CSS e JavaScript da interface
├── templates/
│   ├── report_template.html    # Estrutura principal do relatório
│   ├── _report_styles.html     # Estilos do relatório
│   ├── _report_body.html       # Abas executiva / técnica / versões / falhas
│   └── _report_scripts.html    # Interações do relatório
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
- `robot-report-gui`: Inicia o servidor local e abre a interface no navegador.

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
python main.py --results-dir caminho/para/results --database robot-results/report_history.sqlite3 --report relatorio.html
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
| `--database` | `robot-results/report_history.sqlite3` | Banco SQLite do histórico e catálogo. |
| `--report` | `relatorio.html` | Caminho do arquivo HTML final gerado. |
| `--title` | `"Relatório de Execução — Testes BDD"` | Título exibido no cabeçalho e na aba do navegador. |
| `--fail-on-error` | `False` | **Ideal para CI/CD**: encerra o processo com código de saída `1` se houver testes com falha. |
| `--no-history` | `False` | Gera o relatório sem persistir nem atualizar o arquivo de histórico. |
| `--no-embed-artifacts`| `False` | Não converte imagens em Base64, referenciando-as pelo caminho local relativo. |

Gerar novamente a partir do mesmo `output.xml` não adiciona uma versão repetida ao
histórico. A CLI substitui o HTML quando recebe o mesmo caminho em `--report`.
Execuções são identificadas pelo conteúdo de `output.xml`; importar novamente o mesmo resultado não cria duplicatas.

### 2. Via interface web local

Com as dependências instaladas, execute:

```bash
python gui.py
# ou
robot-report-gui
```

O navegador abre automaticamente. Se isso não acontecer, copie o endereço completo
exibido no terminal (incluindo `#token=...`). Esse endereço abre a interface
administrativa local e contém a chave de acesso à sessão; não o compartilhe. O link
público de consulta é `/public` no mesmo servidor e não exige token.

1. Selecione um ZIP de resultados e clique em **Enviar e analisar ZIP**. O arquivo pode conter `output.xml` na raiz ou dentro de uma única pasta; a interface valida os caminhos internos e apresenta os totais encontrados.
2. Selecione um sistema existente ou informe identificador e nome para um novo. Informe a versão do produto. A data e hora são sugeridas pelo XML e podem ser editadas; preencha manualmente quando o XML não as trouxer.
3. Clique em **Importar execução**. Métricas e snapshots ficam no SQLite. O ZIP original e os arquivos extraídos são preservados apenas para a execução cronologicamente mais recente de cada sistema; execuções anteriores continuam disponíveis no histórico.
4. Acompanhe a importação e abra o **link fixo**. A página pública permite selecionar sistemas e renderiza os dados atuais do SQLite no template existente; não é criado um HTML a cada ZIP. A versão do produto continua no campo de metadados existente.
   A visão geral compara os sistemas e exibe uma linha histórica de aprovação por sistema. Ao selecionar um sistema, o link mostra o relatório completo.
5. Consulte **Visão geral** para comparar sistemas e períodos. A área de histórico permite remover uma execução.
6. Use **Encerrar** ou `Ctrl+C` no terminal para desligar o servidor. Fechar a aba não interrompe a fila.

O SQLite é compartilhado entre a interface local e a CLI. A base começa vazia; arquivos de histórico JSON antigos são preservados, sem migração automática. O caminho padrão é `robot-results/report_history.sqlite3` e pode ser alterado por `--database` ou `ROBOT_REPORT_DATABASE`. O limite padrão do ZIP é 500 MiB; o conteúdo expandido é limitado a 1 GiB e 10.000 arquivos. Os limites de upload e expansão podem ser configurados por `ROBOT_REPORT_MAX_UPLOAD_BYTES` e `ROBOT_REPORT_MAX_UNPACKED_BYTES`.

A interface usa HTML, CSS e JavaScript locais, sem precisar de internet. O ZIP é
enviado ao servidor que executa a aplicação; não há envio a um serviço de terceiros.
O Python continua necessário para importar os resultados e renderizar a página quando
ela é aberta. O relatório mantém o comportamento visual anterior, incluindo o Chart.js
via CDN quando o arquivo opcional não foi instalado em `assets/`.

As opções ficam bloqueadas durante o processamento. A fila e os logs pertencem à
sessão atual. Em **Logs da geração**, a aba **Log completo** mostra a importação mais
recente; **Erros** reúne falhas da sessão com pasta, motivo e detalhes do processo.
Até 50 erros ficam em memória enquanto o servidor estiver aberto.
O histórico SQLite e os dados da execução mais recente ficam gravados no disco. O processamento local respeita as permissões do usuário do sistema. O link `/public` não exige login e expõe o conteúdo completo dos relatórios; compartilhe-o somente se esses dados puderem ser públicos.

---

## Executando com Docker

Você pode executar tanto a interface web (Flask) quanto os comandos CLI de geração sem precisar configurar o ambiente Python localmente.

### 1. Subindo a Interface Web com Docker Compose
Para iniciar a aplicação em container:
```bash
docker compose up -d --build
```
Acesse a aplicação em seu navegador através do endereço exibido nos logs (ou `http://localhost:5000`). Para visualizar o link com o token de sessão gerado:
```bash
docker compose logs -f
```
O histórico SQLite e os arquivos da execução mais recente ficam no volume Docker `robot-report-data`. O link fixo do catálogo é `http://localhost:5000/public`; ele lê o banco e exibe a execução mais recente de cada sistema sem salvar relatórios HTML. Para usuários externos, mantenha o container em um servidor acessível, configure DNS e HTTPS em um proxy reverso e compartilhe `https://seu-dominio/public`. A interface de importação continua restrita ao endereço local configurado. O conteúdo completo do relatório é público nesse link.

### 2. Construindo a Imagem Manualmente
```bash
docker build -t robot-report-generator .
```

### 3. Rodando o CLI via Container
Para gerar um relatório pontual usando uma pasta de resultados da sua máquina hospedeira:
```bash
docker run --rm \
  -v "$(pwd)/example:/app/example" \
  -v "$(pwd)/output:/app/output" \
  robot-report-generator \
  main.py --results-dir /app/example --report /app/output/relatorio.html --no-history
```

---

## Sistemas e histórico

A CLI importa pastas ou ZIPs diretamente para o mesmo SQLite usado pela interface:

```bash
python scripts/update_robot_results.py /caminho/resultados.zip \
  --system pagamentos --name "Pagamentos" --version 2.4.1
python scripts/update_robot_results.py --list
python scripts/update_robot_results.py --list --system pagamentos
python scripts/update_robot_results.py --system pagamentos --remove ID_COMPLETO_DA_EXECUCAO
```

O banco padrão fica em `robot-results/report_history.sqlite3`; use `--database` ou `ROBOT_REPORT_DATABASE` para escolher outro arquivo. A base inicia vazia e não importa automaticamente os arquivos JSON antigos; eles permanecem intactos.

Cada importação registra métricas e snapshots no SQLite. O ZIP original e os resultados extraídos ficam arquivados somente para a execução mais recente por data e hora; execuções antigas permanecem consultáveis no histórico. O mesmo XML não é duplicado no mesmo sistema.

### Backup, manutenção e estrutura do banco

Na interface local, use **Baixar backup completo** para salvar um pacote ZIP com o banco SQLite e os artefatos da execução atual. **Restaurar backup** valida o SQLite e substitui o histórico e os artefatos atuais; faça isso somente quando não houver importações pendentes. Para inspeção, o pacote pode ser extraído e `report_history.sqlite3` aberto no DB Browser for SQLite.

O painel de histórico permite filtrar por data, versão e resultado e remover execuções. A seção de manutenção também procura diretórios de artefatos sem registro no banco; a remoção exige confirmação e não toca em uploads pendentes. O catálogo identifica cada sistema pelo par nome/ID, evitando confusão quando há nomes repetidos.

As tabelas centrais são `systems`, `executions` e `test_snapshots`. Alterações de esquema devem avançar `PRAGMA user_version` e incluir uma migração incremental em `SQLiteStore._initialize`; não apague nem recrie o banco para atualizar a aplicação. A API local documentada no código inclui `/api/database/backup`, `/api/database/restore`, `/api/artifacts/orphans` e `/api/artifacts/cleanup`.

Para gerar o relatório consolidado do banco:

```bash
python main.py --catalog-report --database robot-results/report_history.sqlite3 --report relatorio.html
```

Também é possível gerar um site estático por sistema com `--site-dir /tmp/robot-report-site`. A geração do catálogo não grava no banco. Os arquivos do Azure Static Web Apps são opcionais e podem ser publicados localmente com `ROBOT_REPORT_SWA_TOKEN`; isso não depende de Azure DevOps.

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

5. **Visibilidade das execuções**:
   - No controle **Execuções visíveis**, desmarque uma execução para ocultá-la em todas as abas, seletores, gráficos e comparações.
   - A comparação usa a execução visível anterior. **Mostrar todas** restaura as execuções sem alterar o histórico salvo.
   - Se todas forem ocultadas, o relatório exibe um estado vazio com a opção de restaurar.
   - A preferência fica salva por relatório no navegador quando o armazenamento está disponível; na visualização isolada da interface local, vale enquanto a página estiver aberta. O arquivo HTML original não é modificado.

6. **Modo Escuro (Dark Mode)**:
   - Alternador de tema no cabeçalho com detecção automática da preferência do sistema operacional e persistência via `localStorage`.

---

## Executando os Testes Automatizados

A base conta com suíte de testes unitários e de integração:

```bash
# Após instalar as dependências do projeto:
python3 -m unittest discover -s tests -v

# Ou com pytest (se instalado):
pytest -v
```

Os testes de navegador são opcionais e requerem Playwright e Chromium:

```bash
pip install playwright
python -m playwright install chromium
ROBOT_REPORT_BROWSER_TESTS=1 python -m unittest tests.test_catalog_browser -v
```

Por padrão esses testes bloqueiam o CDN para verificar a consulta sem internet.
Para validar também os gráficos, defina `ROBOT_REPORT_CHART_JS` com o caminho de
um arquivo Chart.js 4 UMD local. `ROBOT_REPORT_BROWSER` permite informar o caminho
de um Chrome/Chromium já instalado. A suíte padrão não precisa dessas dependências.
