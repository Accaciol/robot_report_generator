# Planejamento de escalabilidade e acompanhamento histórico

Este documento registra a proposta original de evolução e serve como lista de
decisões para reavaliação. Parte da arquitetura descrita já foi implementada;
portanto, confirme o código e o README antes de tratar qualquer item abaixo
como trabalho pendente. O objetivo continua sendo acompanhar períodos longos
sem exigir que o navegador carregue todas as evidências de uma vez.

## Situação atual

- A interface web, CLI e scripts de catálogo mantêm sistemas, execuções, métricas, snapshots e artefatos em SQLite (`core/sqlite_store.py`). JSON é aceito apenas como entrada para migração de catálogos antigos.
- A visão pública carrega sistemas e tendências a partir das APIs públicas da aplicação; o relatório detalhado é renderizado com o template comum.
- O HTML pode incorporar evidências em Base64. Na cópia local analisada, `output.xml` tem cerca de 22 MB e `relatorio.html`, cerca de 176 MB; esses números são uma amostra, não uma meta de desempenho.
- Evidências completas podem aumentar bastante o HTML quando incorporadas. Confirmar a política atual de retenção no SQLite antes de alterações nessa área.

## Estado das propostas

- **Armazenamento SQLite para a interface web:** implementado em `core/sqlite_store.py`; retenção, volume e plano de consulta ainda precisam ser medidos com bases representativas.
- **Página pública com dados atuais do banco:** implementada; consultar `core/web_app.py` e `core/web/static/public_catalog.js`.
- **Medição de desempenho, limites históricos e retenção de evidências:** permanecem como decisões e trabalho futuro, conforme os critérios abaixo.

## Etapa 1 — Medir e reduzir o tamanho atual

1. Criar bases de referência com diferentes números de sistemas, execuções, testes e evidências. Registrar tempo e memória de importação, geração e abertura do relatório, além do tamanho final do HTML.
2. Medir separadamente o peso de evidências Base64, dados históricos, scripts e HTML repetido. Remover serializações duplicadas que forem confirmadas pela medição.
3. Reduzir a quantidade de pontos enviados aos gráficos conforme a largura e o período selecionado, preservando os dados originais para consulta.

**Concluído quando:** houver uma linha de base reproduzível e as melhorias puderem ser comparadas com ela sem perda de dados ou recursos do relatório.

## Etapa 2 — Acompanhamento de longos períodos

1. Oferecer filtros de 7, 30, 90 e 365 dias e intervalo personalizado, por sistema e por teste.
2. Calcular séries diárias e mensais de taxa de sucesso, falhas, duração mediana e testes instáveis. Mostrar o número de execuções em cada período para dar contexto às taxas.
3. Definir como tratar dias sem execução, mudanças no identificador de testes e datas sem fuso horário. Manter a comparação entre execuções individuais.

**Concluído quando:** seja possível identificar tendências anuais e investigar o teste e a execução que explicam uma mudança nos indicadores.

## Etapa 3 — Armazenamento e retenção

1. Avaliar a migração dos fluxos JSON restantes para SQLite somente se eles ainda forem necessários e após definir compatibilidade e migração reversível dos dados existentes.
2. Definir retenção configurável: métricas por longo prazo, XML e evidências completas por prazo ou volume, e resumos agregados permanentes. Não apagar evidências antes de validar a política e fornecer exportação ou backup.
3. Separar evidências do histórico analítico e evitar copiá-las integralmente a cada atualização do catálogo.

**Concluído quando:** consultas por período não exigirem ler todo o histórico, e a política de retenção for explícita, testada e documentada.

## Etapa 4 — Consulta, distribuição e containerização (Docker)

1. Carregar sistemas, períodos e detalhes sob demanda na interface, com paginação. Manter a exportação de HTML portátil para um recorte escolhido.
2. Manter a aplicação empacotada em container Docker (`Dockerfile` e `docker-compose.yml`) e verificar a execução reproduzível da interface web e dos comandos em lote. A publicação opcional no Azure continua isolada em `core/azure_publish.py`.
3. Considerar PostgreSQL somente se houver uso simultâneo por equipes, serviço hospedado ou volume que exceda as metas medidas com SQLite. Nessa situação, o container do banco pode ser orquestrado diretamente via compose.

**Concluído quando:** a aplicação puder ser inicializada de forma reproduzível via Docker, a interface continuar responsiva com a maior base de referência e o HTML exportado abrir sem carregar dados fora do período selecionado.

## Ordem de decisão

Implementar e medir cada etapa antes de avançar. Preservar os comandos atuais de geração individual e do catálogo durante a transição. A escolha de banco, prazos de retenção e metas numéricas de desempenho depende da linha de base da Etapa 1 e do volume real de uso.
