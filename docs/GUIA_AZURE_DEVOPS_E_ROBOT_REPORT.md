# Guia do Azure DevOps e Robot Report Generator

Este guia explica como as partes do teste de integração se conectam: Azure DevOps, agente `myagent`, pipeline, Robot Framework e Robot Report Generator.

## 1. Visão geral do fluxo

```text
Testes Robot Framework
        ↓
output.xml e evidências
        ↓
Pipeline do Azure DevOps
        ↓
Agente self-hosted (myagent)
        ↓ ZIP
Robot Report Generator
        ↓
Banco SQLite e arquivos de execução
        ↓
Catálogo e relatórios HTML
```

O Azure DevOps organiza e agenda o trabalho. O agente executa os passos definidos pela pipeline. O servidor Robot Report Generator recebe e importa os resultados.

## 2. Função do agente `myagent`

O agente é um programa instalado em uma máquina que conecta essa máquina ao Azure DevOps. Quando uma pipeline precisa rodar, o agente busca o trabalho e executa os comandos definidos no YAML.

No teste documentado, o agente era **self-hosted Linux** e estava na mesma máquina que o servidor de relatórios. O comando `./run.sh` mantém o agente disponível. A mensagem `Listening for Jobs` indica que ele está aguardando trabalho.

A pasta `~/myagent` contém o programa do agente. Os arquivos temporários da pipeline costumam ficar na área de trabalho configurada pelo agente, como `_work`. Essa pasta não é necessariamente onde o servidor guarda o catálogo ou os relatórios.

## 3. Função da pipeline

O YAML define os passos executados pelo Azure DevOps. O template [`infra/azure-pipelines/robot-report-import.yml`](../infra/azure-pipelines/robot-report-import.yml) recebe parâmetros e:

1. Localiza a pasta de resultados, que deve conter `output.xml`.
2. Compacta os resultados em um ZIP.
3. Envia o ZIP ao servidor.
4. Consulta o servidor até a importação terminar.
5. Informa sucesso ou erro à pipeline.

A pipeline precisa conhecer o caminho dos resultados, a URL do servidor e a identificação do sistema. Ela não hospeda o servidor de relatórios.

## 4. Papel do `output.xml`

O Robot Framework gera `output.xml` ao executar os testes. O arquivo contém a estrutura das suítes e testes, os resultados, mensagens e tempos. O ZIP também pode conter evidências, como imagens.

O servidor recebe o ZIP, valida e extrai os arquivos, lê o XML e registra os resultados. O gerador produz o relatório HTML a partir dos dados importados.

## 5. Credenciais e tokens

Há três credenciais distintas neste fluxo:

| Credencial | Uso |
|---|---|
| **PAT do Azure DevOps** | Registrar/configurar o agente no pool do Azure DevOps. O guia recomenda validade curta e o escopo `Agent Pools: Read & manage`. |
| **`ROBOT_REPORT_INGEST_TOKEN`** | Autorizar a pipeline a enviar a importação e consultar o processamento na API do servidor. |
| **Token de sessão** | Acessar a interface administrativa local. A URL da interface pode conter esse token. |

O token de ingestão precisa estar configurado no processo do servidor e como **variável secreta** da pipeline. Não o coloque no YAML versionado nem o compartilhe em capturas, mensagens ou logs.

O PAT não substitui o token de ingestão. Cada credencial autoriza uma parte diferente do fluxo.

## 6. Onde o servidor roda e o que significa `127.0.0.1`

O servidor pode rodar na mesma máquina do agente ou em outra máquina acessível pela rede.

No teste documentado, agente e servidor estavam na mesma máquina, então a pipeline usou `http://127.0.0.1:5001`. `127.0.0.1` significa **esta própria máquina**. Se o agente estiver em outra máquina, esse endereço apontará para o agente, e não para o servidor de relatórios.

Para uma arquitetura remota, a URL do servidor precisa estar acessível ao agente. A documentação indica HTTPS para esse cenário e ressalta que o teste local não validou a implantação de produção.

A aplicação pode ser executada localmente com `python gui.py`. O terminal mostra a URL da interface administrativa. O catálogo compartilhado fica em `/public`.

## 7. O que o teste comprovou

O teste ponta a ponta documentado confirmou que:

- o agente recebeu a pipeline;
- o ZIP foi enviado;
- o servidor importou os resultados para o SQLite;
- o catálogo foi atualizado;
- reenviar o mesmo `output.xml` não criou uma execução duplicada.

O teste usou HTTP, um agente self-hosted Linux e loopback (`127.0.0.1`). Portanto, não comprova que a instalação está pronta para uso remoto ou produção. A equipe ainda precisa definir hospedagem, acesso de rede, HTTPS, gestão de segredos e operação.

## 8. Armazenamento e acesso aos dados

O histórico e as métricas ficam no banco SQLite. Os arquivos da execução mais recente, incluindo evidências, ficam no diretório de artefatos junto ao banco. Os resumos históricos continuam disponíveis mesmo quando os artefatos de uma execução anterior são removidos.

O catálogo em `/public` permite leitura sem login. Ele pode mostrar relatórios detalhados, mensagens de falha e informações ambientais presentes no XML. Qualquer pessoa com acesso de rede à URL poderá consultar esse conteúdo. Antes de publicar o serviço, confirme que esses dados podem ser expostos nesse alcance.

A interface administrativa é diferente do catálogo público. As operações administrativas exigem o token de sessão e as verificações descritas nos documentos de arquitetura.

## 9. Validação dos ZIPs e processamento

O servidor aplica limites e validações durante o recebimento e a extração. Os limites padrão documentados são 500 MiB para o ZIP, 1 GiB para o conteúdo extraído e 10.000 arquivos. O projeto também rejeita caminhos absolutos, caminhos com `..`, links e nomes duplicados.

A importação passa por uma fila sequencial: o servidor permite um trabalho ativo por vez. A fila fica na memória enquanto o servidor está ligado; o banco e os artefatos persistidos ficam no disco.

## 10. Sequência de verificação

1. **Confirme que o agente está ativo.** No terminal do `myagent`, procure `Listening for Jobs`.
2. **Confirme que o servidor está ativo.** No terminal do `gui.py`, verifique se iniciou e qual porta está usando.
3. **Compare os endereços.** A URL `serverUrl` da pipeline precisa apontar para a máquina e porta corretas do servidor.
4. **Confira os resultados.** O diretório indicado no YAML precisa conter `output.xml`.
5. **Confira o segredo sem revelá-lo.** A variável secreta da pipeline e `ROBOT_REPORT_INGEST_TOKEN` no servidor precisam ter o mesmo valor. Não copie o valor para o YAML.
6. **Execute a pipeline.** Depois de uma execução bem-sucedida, abra `/public` e procure o sistema importado.
7. **Revise a exposição antes do acesso remoto.** Defina quem pode alcançar o servidor e se o catálogo público pode apresentar esses resultados.

## 11. Documentação relacionada

- [Teste local da integração com Azure DevOps](TESTE_AZURE_DEVOPS_LOCAL.md)
- [Arquitetura e controles de segurança](SEGURANCA_ARQUITETURA.md)
- [Guia completo para recriar o teste Azure DevOps](GUIA_RECRIAR_TESTE_AZURE_DEVOPS.md)
- [Guia de arquivos do projeto](DOCUMENTACAO_ARQUIVOS.md)

## 12. Etapas, responsáveis, motivos e tecnologias

Esta tabela acompanha uma execução desde a preparação dos testes até a consulta do relatório. “Responsável” indica quem opera ou mantém a etapa. Algumas etapas são automáticas depois da configuração.

| Etapa | O que ocorre | Responsável | Por que existe | Tecnologia usada |
|---|---|---|---|---|
| 1. Preparar os testes | A equipe mantém os casos de teste e configura o comando que os executa. | Equipe de QA/Desenvolvimento | Definir o comportamento do produto que será verificado. | Robot Framework e arquivos `.robot` |
| 2. Executar os testes | A pipeline chama o Robot Framework no agente e o teste é executado contra o ambiente configurado. | Pipeline do Azure DevOps; agente executa | Automatizar a validação em cada execução solicitada. | Azure Pipelines, agente self-hosted Linux e Robot Framework |
| 3. Gerar resultados | O Robot Framework grava `output.xml` e, conforme os testes, evidências como screenshots. | Robot Framework, durante a execução | Registrar resultados, mensagens, tempos e dados necessários ao relatório. | XML e arquivos de evidência |
| 4. Selecionar a pasta de resultados | O YAML informa ao template onde estão os resultados. | Responsável pelo repositório/pipeline | Permitir que a etapa de envio encontre os arquivos corretos produzidos na etapa anterior. | YAML do Azure Pipelines, variáveis como `Build.SourcesDirectory` |
| 5. Compactar os resultados | O template reúne a pasta em um ZIP para envio. | Template da pipeline | Transportar XML e evidências como um pacote único. | Azure Pipelines e ferramenta de compactação usada pelo template |
| 6. Obter um agente disponível | O Azure DevOps agenda o job no pool; o agente ativo recebe o trabalho. | Azure DevOps administra a fila; administrador mantém o agente | Fornecer uma máquina que execute os comandos da pipeline. | Azure DevOps Agent, pool `Default` no teste documentado |
| 7. Autorizar a chamada | A pipeline envia o bearer token junto da requisição. O servidor compara com `ROBOT_REPORT_INGEST_TOKEN`. | Administrador do servidor configura o segredo; administrador da pipeline mantém a variável secreta | Restringir quem pode enviar resultados à API de ingestão. | HTTPS em implantação remota, HTTP loopback no teste; bearer token e variável secreta Azure DevOps |
| 8. Receber a importação | A API recebe o ZIP e os metadados, como ID, nome e versão do sistema. | Serviço Robot Report Generator | Criar uma entrada de importação identificável e retornar um ID para acompanhamento. | Flask, HTTP e endpoint `POST /api/automation/imports` |
| 9. Verificar o pacote | O servidor valida metadados, limites e estrutura do ZIP antes de processá-lo. | Serviço Robot Report Generator | Reduzir risco de arquivos inválidos, caminhos maliciosos ou pacotes excessivos. | Python, validação de ZIP e limites configuráveis |
| 10. Extrair em staging | Arquivos aprovados são colocados em uma pasta temporária controlada pelo servidor. | Serviço Robot Report Generator | Evitar que nomes do arquivo enviado determinem diretamente os caminhos finais. | Python, sistema de arquivos e diretório de staging |
| 11. Enfileirar e acompanhar | Se não houver importação ativa, o servidor enfileira o trabalho; a pipeline consulta o estado até concluir ou falhar. | Servidor processa; pipeline acompanha | Separar o recebimento da duração do processamento e dar retorno ao job. | Fila sequencial em memória, Flask, `POST /api/automation/imports` e `GET /api/automation/imports/{id}` |
| 12. Interpretar o XML | O parser lê `output.xml`, estrutura as suítes e testes e calcula métricas. | Robot Report Generator | Converter a saída Robot em dados que o catálogo e os relatórios possam usar. | Python, parser XML do projeto e modelos de dados |
| 13. Registrar histórico | O servidor registra execução, métricas e snapshots; compara o hash do XML para evitar duplicatas idênticas no mesmo sistema. | Robot Report Generator | Preservar a evolução das execuções e evitar registrar novamente o mesmo resultado. | SQLite, SHA-256 e `core/sqlite_store.py` |
| 14. Guardar artefatos | O ZIP original e os resultados da execução mais recente são salvos junto à área de dados. | Serviço Robot Report Generator; administrador define o local e protege o host | Permitir acesso às evidências da execução atual e apoiar a geração de relatórios. | Sistema de arquivos e diretório `executions/` ao lado do SQLite |
| 15. Encerrar a importação | O servidor atualiza o estado do trabalho e remove os arquivos temporários de processamento conforme o fluxo. | Serviço Robot Report Generator | Liberar a pipeline e reduzir o acúmulo de dados temporários. | Worker/fila em memória e sistema de arquivos |
| 16. Exibir o catálogo | A página consulta os sistemas e as métricas disponíveis. | Serviço serve os dados; usuário escolhe o sistema | Permitir encontrar sistemas e acompanhar a visão geral das execuções. | Flask, API pública, HTML, CSS e JavaScript |
| 17. Renderizar o relatório detalhado | Ao escolher um sistema, o servidor carrega os dados e gera a página HTML detalhada. | Robot Report Generator | Apresentar métricas, testes, falhas e evidências para análise. | Python, SQLite, Jinja2, HTML e iframe no catálogo |
| 18. Consultar o resultado | A equipe abre o catálogo e analisa a execução e o histórico. | Usuário do relatório; equipe decide o tratamento das falhas | Usar os resultados para acompanhar qualidade e investigar problemas. | Navegador, endpoint `/public` e relatórios HTML |

### Responsabilidades operacionais contínuas

| Atividade | Responsável principal | Motivo | Tecnologia / configuração |
|---|---|---|---|
| Manter o agente disponível | Administrador da máquina/agente | Permitir que o Azure DevOps encontre um executor no pool. | Serviço ou processo do Azure DevOps Agent; `./run.sh` no teste interativo |
| Manter o servidor disponível | Administrador da aplicação/host | Receber as importações e servir os relatórios. | `gui.py`/Flask no teste; topologia de produção ainda precisa ser definida |
| Gerir PAT e token de ingestão | Administradores Azure DevOps e do servidor, cada um no seu escopo | Permitir registro do agente e autenticação da API sem expor segredos no código. | PAT, variável secreta e variável de ambiente `ROBOT_REPORT_INGEST_TOKEN` |
| Definir exposição de dados | Segurança, proprietário dos dados e responsável pela aplicação | Decidir se XML, mensagens, evidências e relatórios podem ser consultados sem login na rede planejada. | Configuração de rede e rotas públicas `/public` |
| Proteger e manter dados | Administrador do host e proprietário operacional | Definir retenção, recuperação e acesso ao banco e aos artefatos. | SQLite, diretório de artefatos e permissões do sistema operacional |

### Limite entre o que é automático e o que depende de pessoas

- **Automático após configuração:** agendamento e execução do job, compactação, envio, validação, processamento, persistência e atualização do catálogo.
- **Responsabilidade das equipes:** escrever e manter os testes, apontar a pasta correta, manter agente e servidor, proteger credenciais, aprovar acesso aos dados e definir operação de produção.
- **Ponto específico do teste:** agente e servidor estavam na mesma máquina; `127.0.0.1:5001` e HTTP serviram ao cenário local. Uma implantação remota precisa de endereço alcançável, HTTPS e desenho operacional aprovado.
