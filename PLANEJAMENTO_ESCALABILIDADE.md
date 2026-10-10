# Planejamento de escalabilidade e acompanhamento histórico

**Estado:** propostas para implementação futura. **Objetivo:** acompanhar meses ou anos de execuções sem exigir que o navegador carregue todo o histórico e todas as evidências de uma vez.

**Pré-requisito atendido:** a geração individual identifica `output.xml` já processado e mantém uma única entrada por execução no histórico. A interface local atualiza um HTML por pasta de origem. A futura migração de dados deve preservar essas regras.

## Situação atual

- O relatório de um sistema limita o histórico a 30 execuções (`core/history_manager.py`); o catálogo mantém resumos sem limite (`core/catalog.py`).
- O consolidado gera o HTML completo de cada sistema e o incorpora em um único arquivo (`core/catalog_report.py` e `templates/catalog_template.html`). O template individual serializa o histórico duas vezes.
- O HTML pode incorporar evidências em Base64. Na cópia local analisada, `output.xml` tem cerca de 22 MB e `relatorio.html`, cerca de 176 MB; esses números são uma amostra, não uma meta de desempenho.
- O catálogo preserva as evidências completas apenas da execução mais recente de cada sistema. As demais ficam como resumos de testes e métricas.

## Etapa 1 — Medir e reduzir o tamanho atual

1. Criar bases de referência com diferentes números de sistemas, execuções, testes e evidências. Registrar tempo e memória de importação, geração e abertura do relatório, além do tamanho final do HTML.
2. Medir separadamente o peso de evidências Base64, dados históricos, scripts e HTML repetido. Eliminar a segunda serialização do histórico no template.
3. Reduzir a quantidade de pontos enviados aos gráficos conforme a largura e o período selecionado, preservando os dados originais para consulta.

**Concluído quando:** houver uma linha de base reproduzível e as melhorias puderem ser comparadas com ela sem perda de dados ou recursos do relatório.

## Etapa 2 — Acompanhamento de longos períodos

1. Oferecer filtros de 7, 30, 90 e 365 dias e intervalo personalizado, por sistema e por teste.
2. Calcular séries diárias e mensais de taxa de sucesso, falhas, duração mediana e testes instáveis. Mostrar o número de execuções em cada período para dar contexto às taxas.
3. Definir como tratar dias sem execução, mudanças no identificador de testes e datas sem fuso horário. Manter a comparação entre execuções individuais.

**Concluído quando:** seja possível identificar tendências anuais e investigar o teste e a execução que explicam uma mudança nos indicadores.

## Etapa 3 — Armazenamento e retenção

1. Para uso local, avaliar uma migração dos JSONs para SQLite com tabelas para sistemas, execuções e resultados por teste, índices por sistema/data/teste e migração reversível dos dados existentes.
2. Definir retenção configurável: métricas por longo prazo, XML e evidências completas por prazo ou volume, e resumos agregados permanentes. Não apagar evidências antes de validar a política e fornecer exportação ou backup.
3. Separar evidências do histórico analítico e evitar copiá-las integralmente a cada atualização do catálogo.

**Concluído quando:** consultas por período não exigirem ler todo o histórico, e a política de retenção for explícita, testada e documentada.

## Etapa 4 — Consulta, distribuição e containerização (Docker)

1. Carregar sistemas, períodos e detalhes sob demanda na interface, com paginação. Manter a exportação de HTML portátil para um recorte escolhido.
2. Disponibilizar a aplicação empacotada em container Docker (`Dockerfile` e `docker-compose.yml`), permitindo executar tanto a interface web (Flask) quanto os scripts de geração em lote de relatórios sem dependência do ambiente hospedeiro ou de nuvem proprietária (Azure).
3. Considerar PostgreSQL somente se houver uso simultâneo por equipes, serviço hospedado ou volume que exceda as metas medidas com SQLite. Nessa situação, o container do banco pode ser orquestrado diretamente via compose.

**Concluído quando:** a aplicação puder ser inicializada de forma reproduzível via Docker, a interface continuar responsiva com a maior base de referência e o HTML exportado abrir sem carregar dados fora do período selecionado.

## Ordem de decisão

Implementar e medir cada etapa antes de avançar. Preservar os comandos atuais de geração individual e do catálogo durante a transição. A escolha de banco, prazos de retenção e metas numéricas de desempenho depende da linha de base da Etapa 1 e do volume real de uso.
