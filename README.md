# Robot Report Generator

Aplicação Python para importar resultados do Robot Framework (`output.xml`),
manter histórico em SQLite e consultar relatórios HTML e PDF. Pode ser usada
pela interface web ou pela CLI; pipelines do Azure DevOps podem enviar os
resultados ao servidor por uma API autenticada.

## Requisitos e instalação

- Python 3.9 ou posterior.
- Dependências instaladas no ambiente em que a aplicação será executada.

```bash
python -m pip install -e .
```

Para instalar também as dependências de desenvolvimento:

```bash
python -m pip install -e '.[dev]'
```

## Usar a interface web

```bash
python gui.py
```

Abra o endereço mostrado no terminal. Ele contém o token da sessão; trate-o
como credencial e não o compartilhe. Na interface, envie um ZIP com
`output.xml` e evidências, selecione ou crie um sistema e importe a execução.
O catálogo de consulta fica em `/public`; ele não exige autenticação e mostra
os dados completos do relatório.

## Usar a CLI

Gerar um relatório HTML a partir de uma pasta:

```bash
python main.py --results-dir example --report /tmp/relatorio.html --no-history
```

Importar os resultados para o histórico e gerar o relatório:

```bash
python main.py --results-dir caminho/para/resultados \
  --system-id pagamentos --system-name "Pagamentos"
```

É possível usar `--zip` ou `--output-xml` como entrada. `python main.py --help`
lista as opções. O banco padrão fica em
`robot-results/report_history.sqlite3`; use `--database` ou
`ROBOT_REPORT_DATABASE` para alterar o caminho.
Por padrão, a CLI grava o HTML em `local-data/reports/relatorio.html`. Para
entrada sem argumentos, prefere `output.xml` recém-gerado na raiz e usa
`local-data/input/output.xml` como cópia local. O diretório
`local-data/` reúne dados locais e saídas geradas e não é versionado.

## Exportar PDF

A exportação PDF é suportada pela interface web, pela CLI e pela biblioteca
ReportLab. Pela interface, abra `/public` e escolha **Exportar PDF**. Pela CLI:

```bash
python main.py --pdf relatorio.pdf
python main.py --pdf relatorio.pdf \
  --pdf-systems pagamentos,portal \
  --pdf-sections executive,suites,failures \
  --pdf-title "Relatório de homologação"
```

As seções disponíveis são `executive`, `distribution`, `suites`, `failures`,
`history` e `slowest`.

## Azure DevOps

A pipeline usa um agente para compactar e enviar os resultados. Configure
`ROBOT_REPORT_INGEST_TOKEN` no servidor e como variável secreta na pipeline. O
PAT do agente e o token da interface têm finalidades diferentes.

- [Roteiro para recriar o teste](docs/GUIA_RECRIAR_TESTE_AZURE_DEVOPS.md)
- [Resultado e limites do teste local](docs/TESTE_AZURE_DEVOPS_LOCAL.md)
- [Etapas do fluxo e responsabilidades](docs/GUIA_AZURE_DEVOPS_E_ROBOT_REPORT.md)

O teste realizado usou agente self-hosted e servidor na mesma máquina. Para
agentes remotos, configure um endereço HTTPS alcançável pelo agente; o teste
local não demonstra uma implantação de produção.

## Docker

Para iniciar a interface com Docker Compose:

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

Abra `http://localhost:5000`. Configure HTTPS e controles de rede antes de
permitir acesso remoto.

## Dados e documentação

O SQLite mantém o histórico e as métricas. Os artefatos completos ficam no
disco junto à área de dados, e o projeto conserva os artefatos da execução mais
recente de cada sistema. Históricos antigos em JSON não são mais importados;
novas execuções devem ser registradas no SQLite a partir dos resultados do Robot.

## Organização do código

- `core/`: regras de negócio, importação, armazenamento SQLite, geração de relatórios e rotas da API.
- `frontend/`: páginas, CSS, JavaScript e templates HTML dos relatórios.
- `infra/`: Docker Compose, Dockerfile e pipelines do Azure DevOps.
- `tests/`: testes unitários e de integração; os testes com navegador são opt-in.

- [Arquitetura e segurança](docs/SEGURANCA_ARQUITETURA.md)
- [Inventário dos arquivos](docs/DOCUMENTACAO_ARQUIVOS.md)
- [Planejamento de escalabilidade](docs/PLANEJAMENTO_ESCALABILIDADE.md)
- [Apresentação de segurança em formato Markdown](docs/APRESENTACAO_SEGURANCA.md)

## Desenvolvimento

```bash
python -m unittest discover -s tests -v
```

Os testes de navegador são opcionais e requerem Playwright e Chromium.
