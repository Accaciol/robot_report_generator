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
│   ├── history_manager.py      # Persistência e rotação de history.json
│   ├── report_renderer.py      # Renderização HTML standalone (Jinja2 + Base64 com cache)
│   ├── web_app.py              # Rotas e proteção da interface local
│   ├── web_jobs.py             # Fila e cancelamento de subprocessos
│   └── web/                    # HTML, CSS e JavaScript da interface
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

### 2. Via interface web local

Com as dependências instaladas, execute:

```bash
python gui.py
# ou
robot-report-gui
```

O navegador abre automaticamente. Se isso não acontecer, copie o endereço completo
exibido no terminal (incluindo `#token=...`). O servidor usa uma porta disponível
em `127.0.0.1` e aceita somente conexões locais autenticadas. Não compartilhe esse
endereço: ele contém a chave de acesso à sessão.

1. Clique em **Adicionar pasta**. Navegue pelas pastas ou cole um caminho e clique
   em **Ir**. A seleção é liberada quando a pasta contém `output.xml`.
2. Adicione quantas pastas precisar e escolha a pasta dos relatórios. Por padrão,
   o destino é sua pasta pessoal, e o histórico é `~/robot-report-history.json`.
   Você pode informar um histórico existente para preservar suas comparações.
3. Clique em **Gerar relatórios**. A fila é processada sequencialmente; uma falha
   fica registrada e não impede os próximos itens. Cada HTML recebe um nome único.
4. Use **Abrir** ou **Baixar** em cada item concluído. Os arquivos permanecem no
   destino escolhido depois que o servidor é encerrado.
5. **Cancelar** interrompe o item ativo e os pendentes, aguardando o processo sair
   antes de permitir uma nova execução. Relatórios já concluídos são preservados.
6. Use **Encerrar** ou `Ctrl+C` no terminal para desligar o servidor. Fechar a aba
   não interrompe a fila. Encerrar durante uma execução cancela os itens restantes.

A interface usa HTML, CSS e JavaScript locais, sem precisar de internet. O Python
continua necessário para gerar os relatórios; não há upload nem hospedagem externa.
O relatório gerado mantém seu comportamento anterior, incluindo o Chart.js via CDN
quando o arquivo opcional não foi instalado em `assets/`.

As opções ficam bloqueadas durante o processamento. A fila e os logs pertencem à
sessão atual; o histórico JSON e os relatórios ficam gravados no disco. O navegador
de pastas inicia na pasta pessoal e respeita as permissões do usuário do sistema.

---

## Sistemas, histórico e Azure Pipelines

O relatório consolidado tem um seletor de sistemas. Cada sistema possui seu próprio
histórico, gráficos, comparações e evidências. O usuário final baixa um único HTML
pelo artefato `robot-report` da pipeline e seleciona o sistema no cabeçalho.

### Importar resultados

Execute na raiz do projeto:

```bash
python scripts/update_robot_results.py /caminho/resultados-pagamentos \
  --system pagamentos --name "Pagamentos"
python scripts/update_robot_results.py /caminho/resultados-cadastro \
  --system cadastro --name "Cadastro de clientes"
```

`--system` é obrigatório e aceita letras minúsculas, números e hífens, por exemplo
`portal-cliente`. `--name` define ou atualiza o nome exibido; nas próximas importações
pode ser omitido. Um sistema novo sem nome usa seu identificador como nome.

Cada origem precisa conter `output.xml` e as evidências referenciadas por caminhos
relativos. O script valida o XML e prepara a cópia antes de substituir dados.
Reimportar o mesmo XML no mesmo sistema não duplica a execução. Um XML alterado
recebe outro identificador, mesmo se as métricas forem iguais.

A base fica em `robot-results/systems/<sistema>/`:

- `system.json`: identificação e vínculo com a execução que tem evidências.
- `history.json`: métricas e snapshots dos testes, sem limite automático de execuções.
- `current/`: XML e evidências completos somente da execução mais recente.

Resultados antigos importados posteriormente entram na ordem cronológica, sem
substituir os outputs mais recentes. Empates de data são ordenados pelo identificador
completo da execução. Execuções sem data usam `1970-01-01` para ordenação determinística.
`log.html` e `report.html` da raiz da origem não são copiados. Cada atualização
substitui apenas os arquivos do sistema informado.

### Listar e remover uma execução incorreta

```bash
python scripts/update_robot_results.py --list
python scripts/update_robot_results.py --list --system pagamentos
python scripts/update_robot_results.py --system pagamentos --remove ID_COMPLETO_DA_EXECUCAO
```

Copie o ID completo mostrado pela listagem. A remoção exclui a execução da base e
recalcula a evolução no próximo relatório. Caso ela possua os outputs atuais, esses
arquivos também são apagados. A execução anterior continua disponível como resumo;
suas evidências antigas não podem ser recuperadas automaticamente. Remover a última
execução mantém o sistema cadastrado, mostrando um estado vazio.

O HTML é uma cópia de consulta: remoções persistentes são feitas pelo mantenedor,
com o comando acima e um novo commit. HTMLs já baixados não mudam. A opção **Execuções
visíveis** apenas oculta resultados na visualização. No consolidado, essa preferência
é mantida por sistema enquanto a página estiver aberta, inclusive ao trocar de sistema.

### Gerar e publicar

```bash
python main.py --catalog-dir robot-results/systems --report relatorio.html
# Após importar ou remover, inclua também as exclusões no commit:
git add -A robot-results/systems
git commit -m "Atualiza histórico dos sistemas"
git push
```

A geração é somente leitura: não acrescenta execuções nem altera a base.
`--catalog-dir` não pode ser combinado com `--results-dir`, `--output-xml` ou
`--no-embed-artifacts`. As opções `--title`, `--issue-url` e `--fail-on-error`
continuam disponíveis. Neste modo, `--history` e `--no-history` não controlam a base:
o histórico é sempre lido do catálogo, sem gravação.

No Azure DevOps Services, cadastre **Pipelines → New pipeline → Existing Azure
Pipelines YAML file**, selecionando `/azure-pipelines.yml`. Faça commit dos arquivos
da implementação também no primeiro envio. Mudanças em `robot-results/systems/`
na branch `main`, inclusive remoções, disparam a geração. Ajuste a branch no YAML
se necessário. Mudanças somente no gerador podem ser validadas executando manualmente.

A pipeline publica o consolidado e não faz commits automáticos. Testes Robot com
status FAIL aparecem no relatório, sem falhar a pipeline por padrão. O uso opcional
de `--fail-on-error` retorna código 1 quando a execução mais recente de algum sistema
tem falhas, mas ainda gera o HTML. Catálogo inválido ou XML atual alterado fora do
importador interrompe a geração. Um catálogo vazio gera um HTML com estado vazio.

Configure a limpeza dos builds e artefatos em **Project settings → Pipelines →
Settings**, conforme a [retenção do Azure](https://learn.microsoft.com/en-us/azure/devops/pipelines/policies/retention?view=azure-devops).
Artefatos de builds diferentes não se sobrescrevem. Os resumos sem limite e as versões
antigas de imagens no Git continuam ocupando espaço; excluir arquivos da pasta atual
não apaga o histórico do repositório.

### Migrar a entrada anterior

A migração é explícita e requer um identificador de sistema ainda não cadastrado:

```bash
python scripts/update_robot_results.py robot-results/current \
  --system sistema-legado --name "Sistema legado" \
  --migrate-history /caminho/history.json
```

Se não há histórico legado, importe a pasta antiga normalmente com `--system`.
A migração não apaga os arquivos de origem; após conferir o HTML, remova a pasta
legada do repositório se não precisar mais dela. O histórico antigo recebe IDs
estáveis próprios. Uma entrada legada só é associada ao XML quando data até segundos,
métricas e snapshots correspondem; entradas ambíguas são preservadas para revisão
manual pela listagem e remoção por ID.

Para trabalhar com outra base, use `--catalog-dir /caminho/systems` nos comandos de
gerenciamento e geração. A origem dos outputs deve estar fora dessa base. Use os
comandos para atualizar o catálogo, evitando editar seus JSONs manualmente. Escritas
simultâneas são bloqueadas. Uma interrupção na troca de diretórios mantém um backup
local legível, recuperado na próxima atualização; não remova arquivos `.backup`
manualmente. Arquivos transitórios do catálogo padrão são ignorados pelo Git.

A CLI de sistema único (`--results-dir`) e a interface local continuam funcionando
como antes. O gerenciamento de múltiplos sistemas nesta versão é feito pela CLI.

Referências: [gatilhos por branch/caminho](https://learn.microsoft.com/en-us/azure/devops/pipelines/yaml-schema/trigger?view=azure-pipelines)
e [publicação de artefatos](https://learn.microsoft.com/en-us/azure/devops/pipelines/artifacts/pipeline-artifacts?view=azure-devops).

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

5. **Visibilidade das execuções**:
   - No controle **Execuções visíveis**, desmarque uma execução para ocultá-la em todas as abas, seletores, gráficos e comparações.
   - A comparação usa a execução visível anterior. **Mostrar todas** restaura as execuções sem alterar o histórico JSON.
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
