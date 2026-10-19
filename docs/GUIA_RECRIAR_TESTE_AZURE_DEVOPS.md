# Guia completo: configurar novamente o teste no Azure DevOps

Este roteiro refaz o teste de envio de resultados do Robot Framework desde a
criação de uma organização Azure DevOps até a confirmação dos dados no catálogo
do Robot Report Generator. O cenário documentado usa um computador Linux, com o
agente self-hosted e o servidor executando na mesma máquina.

> O Azure DevOps Services é acessado pela internet. O agente self-hosted roda
> localmente e busca os trabalhos na nuvem. Neste roteiro não é criada uma
> máquina virtual Azure. Para evitar custos, não crie recursos de computação no
> portal Azure para este teste. A disponibilidade da avaliação gratuita do
> Azure depende da conta e da elegibilidade; ela não é necessária para criar a
> organização do Azure DevOps.

## O que será necessário

- Uma conta Microsoft que consiga acessar [Azure DevOps](https://dev.azure.com/).
- O projeto Robot Report Generator clonado e executável localmente.
- Linux com `bash`, `curl`, `jq`, `tar`, Python 3 e Git.
- Conexão de rede para o agente acessar Azure DevOps.
- Uma porta local livre, aqui definida como `5001`.

O fluxo final será:

```text
Azure DevOps (organização, projeto e pipeline)
                │
                ▼
Agente self-hosted Linux no seu computador
                │ POST + consulta de status
                ▼
Robot Report Generator em 127.0.0.1:5001
                │
                ▼
SQLite temporário em /tmp
```

## 1. Criar ou acessar a organização

1. Acesse [https://dev.azure.com/](https://dev.azure.com/) e entre com a conta
   Microsoft que pretende usar.
2. Se o Azure DevOps oferecer criar uma organização, escolha essa opção.
   Informe um nome único, selecione a região disponível e conclua.
3. Se aparecer uma página de boas-vindas do portal Azure com opções de
   assinatura, volte a [https://dev.azure.com/](https://dev.azure.com/) e
   prossiga pelo Azure DevOps. O teste descrito neste guia não requer criar
   assinatura Azure nem recurso de nuvem.
4. Se a conta apresentar erro de locatário ou disser que o usuário não existe
   em “Microsoft Services”, saia da sessão Microsoft e tente entrar no Azure
   DevOps com a conta pessoal correta. Uma conta corporativa pode estar sujeita
   a políticas do locatário da organização.

## 2. Criar o projeto e inicializar o repositório

1. Na organização, crie um projeto com nome como
   `robot-report-generator-test`.
2. Defina a visibilidade como **Private** e o processo **Basic** (ou o padrão
   oferecido).
3. Abra **Repos → Files** e inicialize o repositório adicionando um README.
   Isso cria a branch `main`.
4. Confirme que os serviços **Repos** e **Pipelines** estão habilitados no
   projeto.

## 3. Preparar os arquivos da pipeline

Use um clone separado do repositório Azure DevOps para os arquivos de teste.
Assim, você não mistura o repositório de teste com alterações locais do projeto
principal.

No portal, em **Repos → Files**, copie a URL HTTPS de clone. No terminal:

```bash
mkdir -p ~/azure-test
cd ~/azure-test
git clone https://dev.azure.com/ORGANIZACAO/robot-report-generator-test/_git/robot-report-generator-test
cd robot-report-generator-test
```

Substitua `ORGANIZACAO` pelo nome real da organização. Se o Git solicitar
autenticação, use o método oferecido pelo Azure DevOps (por exemplo, Git
Credential Manager ou credenciais Git geradas pelo portal); não grave senhas
no repositório.

Copie os arquivos do projeto principal para o clone Azure. Ajuste os caminhos
se seus diretórios forem diferentes:

```bash
cp /caminho/para/robot_report_generator/azure-pipelines-test.yml ./azure-pipelines.yml
mkdir -p azure-pipelines results
cp /caminho/para/robot_report_generator/azure-pipelines/robot-report-import.yml azure-pipelines/
cp /caminho/para/robot_report_generator/example/output.xml results/output.xml
```

Edite `azure-pipelines.yml` e confirme os parâmetros abaixo. A porta precisa
ser a mesma usada pelo servidor; o `systemId` deve usar letras minúsculas,
números e hífens.

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

Faça commit e push:

```bash
git add azure-pipelines.yml azure-pipelines/robot-report-import.yml results/output.xml
git commit -m "ci: configurar teste de importação no Azure DevOps"
git push -u origin main
```

## 4. Criar o PAT para registrar o agente

O PAT serve somente para registrar o agente no pool. Ele não é o segredo que a
pipeline usará para enviar os resultados.

1. No Azure DevOps, abra **User settings → Personal access tokens** e crie um
   token com nome como `registro-agente-local`.
2. Selecione a organização correta, validade curta e escopo personalizado
   **Agent Pools: Read & manage**.
3. Crie o PAT e copie-o naquele momento para uso no comando interativo do
   agente. Não o salve no YAML, não o envie em mensagens e revogue-o quando não
   precisar mais registrar agentes.

## 5. Baixar, extrair e configurar o agente Linux

1. Abra **Organization settings → Agent pools → Default → Agents → New
   agent**. Selecione **Linux** e a arquitetura correspondente (normalmente
   x64), baixe o arquivo `.tar.gz` e anote onde o navegador o salvou.
2. No terminal, crie uma pasta própria para o agente e extraia o pacote. Troque
   o caminho pelo local real do arquivo baixado:

   ```bash
   mkdir -p ~/myagent
   tar -xzf ~/Downloads/vsts-agent-linux-x64-VERSAO.tar.gz -C ~/myagent
   cd ~/myagent
   ./config.sh
   ```

   Se não souber o caminho do pacote, localize-o, por exemplo, com:

   ```bash
   find ~/Downloads ~/Documents -maxdepth 6 -type f -name 'vsts-agent-linux-x64-*.tar.gz' -print 2>/dev/null
   ```

3. Responda ao assistente de configuração:

   - URL da organização: `https://dev.azure.com/NOME_DA_ORGANIZACAO`;
   - método de autenticação: `PAT`;
   - token: cole o PAT recém-criado;
   - pool: `Default`;
   - nome do agente: por exemplo, `robot-report-linux`;
   - diretório de trabalho: aceite `_work`.

4. Inicie o agente:

   ```bash
   ./run.sh
   ```

   Deixe esse terminal aberto durante o teste e aguarde a indicação de que o
   agente está escutando por trabalhos (`Listening for Jobs`). A pasta
   `~/myagent` deve conter arquivos como `config.sh` e `run.sh` após a extração.

## 6. Iniciar o servidor local

Abra outro terminal no clone principal do Robot Report Generator, não no clone
Azure que contém apenas os arquivos da pipeline. Escolha um banco isolado para
não alterar o catálogo de desenvolvimento.

```bash
cd /caminho/para/robot_report_generator
export ROBOT_REPORT_PORT=5001
export ROBOT_REPORT_DATABASE=/tmp/robot-report-azure-test.sqlite3
export ROBOT_REPORT_NO_BROWSER=1
export ROBOT_REPORT_INGEST_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf '%s\n' "$ROBOT_REPORT_INGEST_TOKEN"
python3 gui.py
```

Copie o valor impresso pelo `printf`: ele será usado como segredo da pipeline.
Não compartilhe esse valor. Deixe o terminal do servidor aberto durante o
teste. Se aparecer `Address already in use`, escolha outra porta livre e
atualize tanto `ROBOT_REPORT_PORT` quanto `serverUrl` no YAML.

As credenciais têm finalidades diferentes:

| Credencial | Para que serve |
|---|---|
| PAT `Agent Pools: Read & manage` | Registrar/configurar o agente no Azure DevOps. |
| `ROBOT_REPORT_INGEST_TOKEN` | Autorizar envio do ZIP e consultas de status da importação. Deve ser igual no servidor e na variável secreta da pipeline. |
| Token de sessão local mostrado na URL da interface | Abrir a interface web local. Não é usado pela pipeline. |

## 7. Criar a pipeline no portal

1. No projeto, abra **Pipelines → New pipeline**.
2. Selecione **Azure Repos Git** e o repositório criado.
3. Escolha **Existing Azure Pipelines YAML file**, branch `main` e
   `/azure-pipelines.yml`.
4. Salve. Se o portal solicitar, autorize o uso do pool `Default`.
5. Abra a pipeline em **Edit → Variables** e crie:

   - nome: `ROBOT_REPORT_INGEST_TOKEN`;
   - valor: o segredo impresso no terminal do servidor;
   - marque **Keep this value secret**;
   - deixe **Let users override this value** desmarcado.

6. Salve a pipeline e selecione **Run pipeline**. O agente local deve aceitar
   o trabalho, criar o ZIP, enviá-lo ao servidor e consultar o status até o
   processamento terminar.

## 8. Confirmar o resultado

Quando a execução terminar como **Succeeded**, abra no mesmo computador:

```text
http://127.0.0.1:5001/public
```

O sistema `robot-report-test` deve aparecer no catálogo. Para inspecionar os
dados em JSON, abra:

```text
http://127.0.0.1:5001/public/api/systems
```

Execute novamente a pipeline com o mesmo `results/output.xml`. O sistema deve
continuar com uma execução, pois o servidor deduplica resultados pelo conteúdo
do XML. Uma execução com XML diferente deve ser registrada como uma nova
execução.

## 9. Diagnóstico rápido

- **Não encontra agente no pool `Default`**: confirme que `./run.sh` está
  ativo, que a configuração terminou sem erro e que o agente aparece como
  online no pool `Default`.
- **HTTP 403 com “Acesso local não autorizado”**: confira se o segredo de
  ingestão configurado no processo `gui.py` é idêntico ao valor da variável
  secreta da pipeline. PAT e token de sessão não substituem esse segredo.
- **Servidor na porta 5000 já está em uso**: mantenha a porta `5001` em ambos
  os terminais/configurações, conforme os exemplos deste guia.
- **O arquivo compactado não é encontrado**: confirme que `results/output.xml`
  está no clone Azure e foi incluído no commit/push.
- **A pasta `~/myagent` está vazia**: provavelmente o pacote foi extraído em
  outro diretório. Localize o `.tar.gz` e extraia explicitamente com `-C
  ~/myagent`.
- **Comandos falham por caracteres estranhos**: digite apenas o comando; não
  copie os símbolos do prompt do terminal, como `` ou `~$`.

## 10. Encerrar ou repetir o teste

Para parar, pressione **Ctrl + C** separadamente no terminal do servidor e no
terminal do agente. Para uma nova sessão do agente, entre novamente em
`~/myagent` e execute `./run.sh`. Mantenha a variável secreta no Azure DevOps
enquanto continuar usando a integração. Revogue o PAT de registro quando não
for mais necessário.

O banco deste roteiro fica em `/tmp/robot-report-azure-test.sqlite3` e pode ser
removido quando não precisar mais dos dados do teste. A remoção é irreversível
para esse banco; confirme que não há resultados que queira preservar antes de
apagá-lo.
