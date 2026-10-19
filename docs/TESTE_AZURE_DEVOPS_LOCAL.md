# Resultado do teste local com Azure DevOps

Este documento registra o que foi exercitado no teste ponta a ponta. Para
recriar o ambiente, use o [guia completo do Azure DevOps](GUIA_RECRIAR_TESTE_AZURE_DEVOPS.md).

## Topologia usada

```text
Azure DevOps Services
        │ agenda a pipeline
        ▼
Agente self-hosted Linux ── HTTP loopback ──► Robot Report Generator
                                              127.0.0.1:5001
                                                     │
                                                     ▼
                                           SQLite temporário em /tmp
```

O agente e o servidor estavam na mesma máquina. O teste usou Azure DevOps
Services, um agente self-hosted Linux, `127.0.0.1:5001`, HTTP e banco SQLite
temporário. Não foi criada VM Azure nem servidor remoto.

## O que foi validado

- A pipeline compactou `output.xml` e as evidências em ZIP.
- O agente enviou o pacote com o token de ingestão.
- O servidor aceitou e processou o ZIP, registrando os dados no SQLite.
- O sistema apareceu no catálogo em `/public`.
- O reenvio do mesmo XML não criou uma segunda execução.

Esse resultado confirma o fluxo funcional nessa topologia local. Ele não valida
HTTPS, acesso entre máquinas, implantação de produção, disponibilidade ou
controles de rede. Se o agente e o servidor estiverem em hosts diferentes,
`127.0.0.1` não serve: o agente precisa alcançar o servidor por uma URL HTTPS.

## Diagnóstico rápido

- **Agente não encontrado:** iniciar `./run.sh` e aguardar `Listening for Jobs`.
- **Porta ocupada:** escolher uma porta livre e alterar tanto
  `ROBOT_REPORT_PORT` quanto `serverUrl` na pipeline.
- **HTTP 403:** conferir se `ROBOT_REPORT_INGEST_TOKEN` coincide no servidor e
  na variável secreta da pipeline. PAT e token da interface têm outros usos.
- **Sem dados no catálogo:** consultar o estado da importação e abrir
  `/public/api/systems`.
