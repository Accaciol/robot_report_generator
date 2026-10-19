# Teste local da integração com Azure DevOps

Este guia registra o teste ponta a ponta realizado com uma pipeline do Azure
DevOps, um agente self-hosted Linux e o servidor do Robot Report Generator
rodando na mesma máquina. A pipeline enviou um ZIP com `output.xml`, aguardou o
processamento, atualizou o catálogo SQLite e confirmou a deduplicação ao enviar
novamente o mesmo XML.

## Topologia do teste

```text
Azure DevOps Services
        │ agenda a pipeline
        ▼
Agente self-hosted Linux ── HTTP local ──► Robot Report Generator
       (Default pool)                    127.0.0.1:5001
                                                │
                                                ▼
                                  SQLite temporário em /tmp
```

O agente e o servidor ficaram na mesma máquina. Por isso, a pipeline pôde usar
`127.0.0.1`; não foi necessário criar VM nem expor o servidor à internet. Se o
servidor estiver em Docker, publique a porta para o host. Para agentes em outra
máquina ou agentes hospedados pela Microsoft, `127.0.0.1` aponta para o agente,
e será necessário usar um endereço de servidor acessível por ele, com HTTPS.

## 1. Organização, projeto e repositório

1. Entre em [Azure DevOps](https://dev.azure.com/) e crie uma organização e um
   projeto privado para o teste.
2. Em **Repos → Files**, inicialize o repositório com um README. O teste usou a
   branch `main`.
3. Clone o repositório Azure DevOps em uma pasta separada do checkout de
   desenvolvimento. O checkout de desenvolvimento pode ter outro `origin` e
   alterações locais não relacionadas.
4. No clone de teste, inclua:

   - `azure-pipelines.yml` na raiz;
   - `azure-pipelines/robot-report-import.yml`;
   - `results/output.xml`, copiado de `example/output.xml`.

5. Faça commit e push dos três itens para `main`.

O arquivo raiz usado no teste foi:

```yaml
trigger: none
pr: none

pool:
  name: Default

steps:
  - template: azure-pipelines/robot-report-import.yml
    parameters:
      resultsDirectory: '$(Build.SourcesDirectory)/results'
      serverUrl: 'http://127.0.0.1:5001'
      systemId: 'robot-report-test'
      systemName: 'Robot Report Test'
      systemVersion: '$(Build.BuildNumber)'
      failOnImportError: true
```

Use a mesma porta no servidor e em `serverUrl`. Neste teste a porta `5000` já
estava ocupada, então ambos foram configurados para `5001`. O template compacta
o diretório, envia o ZIP, consulta o status da importação e falha o passo se o
envio ou o processamento falhar.

## 2. Instalar e iniciar o agente Linux

1. Em **Organization settings → Agent pools → Default → Agents → New agent**,
   selecione Linux x64 e baixe o pacote.
2. Extraia o pacote em uma pasta dedicada no host. Por exemplo:

   ```bash
   mkdir -p ~/myagent
   tar -xzf /caminho/para/vsts-agent-linux-x64-ARQUIVO.tar.gz -C ~/myagent
   cd ~/myagent
   ./config.sh
   ```

   `~` representa a pasta pessoal do usuário. Use o caminho real onde o
   arquivo `.tar.gz` foi baixado.

3. Na configuração interativa, informe:

   - URL: `https://dev.azure.com/NOME_DA_ORGANIZACAO`;
   - autenticação: `PAT`;
   - pool: `Default`;
   - nome do agente: um nome identificável, por exemplo `robot-report-linux`;
   - diretório de trabalho: aceite `_work`.

4. Para registrar o agente, crie um PAT com validade curta e somente o escopo
   **Agent Pools: Read & manage**. O PAT é diferente do segredo de ingestão da
   API. Não o coloque no YAML nem compartilhe em logs.
5. Inicie o agente no terminal:

   ```bash
   ./run.sh
   ```

   Deixe esse terminal aberto. A mensagem `Listening for Jobs` indica que ele
   está disponível. Se uma pipeline disser que não encontrou agente no pool,
   confirme que o `./run.sh` continua ativo e que o agente está no pool `Default`.

## 3. Iniciar o servidor com um banco isolado

No checkout do Robot Report Generator, abra outro terminal. Não use o checkout
Azure do teste para iniciar o servidor se ele contiver apenas os arquivos
mínimos da pipeline.

Defina uma porta fixa, um banco temporário e um segredo de ingestão novo:

```bash
export ROBOT_REPORT_PORT=5001
export ROBOT_REPORT_DATABASE=/tmp/robot-report-azure-test.sqlite3
export ROBOT_REPORT_NO_BROWSER=1
export ROBOT_REPORT_INGEST_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf '%s\n' "$ROBOT_REPORT_INGEST_TOKEN"
python3 gui.py
```

Copie o valor exibido por `printf` diretamente para a variável secreta do
Azure DevOps. Não o envie em mensagens, capturas ou logs. Mantenha o terminal do
servidor aberto. O banco em `/tmp` mantém os dados deste teste separados do
catálogo normal.

Há três credenciais diferentes neste fluxo:

| Credencial | Uso |
|---|---|
| PAT com `Agent Pools: Read & manage` | Registrar o agente no Azure DevOps. |
| `ROBOT_REPORT_INGEST_TOKEN` | Autenticar o envio e a consulta de status da API. O mesmo valor deve estar no processo do servidor e na variável secreta da pipeline. |
| `SESSION_TOKEN` mostrado na URL da interface local | Acessar a interface web local. Não é usado pela pipeline. |

## 4. Criar e configurar a pipeline

1. Em **Pipelines → New pipeline**, selecione **Azure Repos Git**, o repositório
   de teste e **Existing Azure Pipelines YAML file**.
2. Escolha a branch `main` e o arquivo `/azure-pipelines.yml`, salve e autorize
   o uso do pool `Default`, se solicitado.
3. Em **Pipelines → pipeline → Edit → Variables**, crie a variável
   `ROBOT_REPORT_INGEST_TOKEN` com o valor exibido pelo servidor. Marque
   **Keep this value secret** e deixe **Let users override this value**
   desmarcado.
4. Execute a pipeline manualmente. O agente deve pegar o trabalho, compactar
   `results/`, enviar o ZIP e aguardar a conclusão da importação.

## 5. Validar a importação e a deduplicação

Após uma execução **Succeeded**, confira o catálogo em:

```text
http://127.0.0.1:5001/public
```

Para conferir os dados diretamente, abra:

```text
http://127.0.0.1:5001/public/api/systems
```

O sistema `robot-report-test` deve aparecer. Execute a mesma pipeline novamente
com o mesmo `output.xml`; o campo `executions` deve continuar em `1`. Esse é o
comportamento esperado porque a importação deduplica pelo conteúdo do XML.

## Solução de problemas observados

- **`No agent found in pool Default`**: o agente ainda não estava configurado ou
  o `./run.sh` não estava aberto. Inicie-o e aguarde `Listening for Jobs`.
- **`Port 5000 is in use`**: escolha uma porta livre, como `5001`, configure
  `ROBOT_REPORT_PORT` e atualize `serverUrl` no YAML para a mesma porta.
- **HTTP 403 na ingestão**: verifique se `ROBOT_REPORT_INGEST_TOKEN` é
  exatamente igual no servidor e na variável secreta da pipeline. PAT e token
  de sessão não servem para a ingestão.
- **Pasta do agente aparentemente vazia**: `~/myagent` fica diretamente na
  pasta pessoal. Não confunda com outra pasta `myagent` criada dentro da pasta
  do clone Azure.
- **Prompt do terminal**: digite apenas os comandos, sem copiar o prefixo visual
  do shell (por exemplo, `` ou `~$`).

## Encerrar o ambiente

Pressione **Ctrl + C** no terminal do `gui.py` e, separadamente, no terminal do
`./run.sh`. A pipeline e o projeto Azure podem permanecer para testes futuros.
Após confirmar o registro, o PAT pode ser revogado; o segredo de ingestão deve
continuar configurado enquanto a pipeline for usada.
