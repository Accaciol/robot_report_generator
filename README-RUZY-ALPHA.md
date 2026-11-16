# Ruzy — versão alfa para avaliação

Versão: `0.1.0-alpha.1` · 16/11/2026. Complemento experimental do robot_report_generator, de Accaciol. Base de referência: `ba61a344dd324dab5ccb999e261f0abbf629d52d`.

## Objetivo e estado
Preparar candidatos a bug a partir dos resultados Robot já extraídos e conduzir a revisão humana de um formulário por vez. Esta alfa demonstra o fluxo com formulários internos à extensão e identificadores fictícios `SIM`. Não acessa o Azure, não cria cards reais e não coleta credenciais ou cookies.

O botão é gerado pelo comando complementar; os comandos e interfaces originais `main.py` e `gui.py` ainda não incluem esse botão. Não há classificador por IA: testes com status FAIL viram candidatos, cuja qualificação cabe ao analista.

## Funcionalidades
- Reutilização do parser e renderer existentes, com matriz de falhas e referências às evidências disponíveis.
- Botão no relatório HTML para configurar destino, preparar candidatos e iniciar a revisão sequencial.
- Configuração de URL do board, tipo, estado, coluna de referência e campos opcionais. O destino não é consultado nesta alfa; coluna e estado ainda exigem validação real.
- Fila persistida localmente no perfil, com salvar, descartar, pausar e retomar. Fechar o formulário não equivale a descartá-lo.
- Exportação do resultado em HTML e JSON, com decisões e códigos simulados; não sobrescreve o relatório original.
- Extensões Edge e Chrome geradas da mesma fonte.

## Ambiente e execução
Executar na raiz do repositório, com Python e ambiente virtual. O conjunto completo de dependências utilizado no desenvolvimento está em `requirements-ruzy-dev.txt`; versões de Python observadas nas validações: 3.14.4 no ambiente inicial e 3.14.7 no desktop. Node é necessário somente para os testes JavaScript; não para carregar a extensão.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ruzy-dev.txt
.\.venv\Scripts\python.exe scripts/build_demo.py
.\.venv\Scripts\python.exe scripts/build_extensions.py
```

O gerador de demonstração executa cinco casos sintéticos: três falhas intencionais, um aprovado e um ignorado. As falhas são a entrada esperada para a demonstração.

Carregar `extensions/edge` ou `extensions/chrome` no navegador correspondente, com acesso a URLs de arquivos, conforme [instalação](INSTALAR-RUZY.md). Depois abrir `demo/relatorio-demo.html`. A instalação local depende da política da organização. No desktop avaliado, o Edge bloqueou a instalação sem pacote; a distribuição autorizada permanece em decisão. Não contornar essa política.

Para gerar um relatório complementar a partir de resultados autorizados:

```powershell
.\.venv\Scripts\python.exe complemento/generate_report.py --results-dir CAMINHO_DOS_RESULTADOS --report relatorio-ruzy.html
```

## Testes e evidências
Comandos na raiz, após instalar as dependências:

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
node --test tests/queue.test.mjs
```

O teste de navegador `tests/browser_demo.py` requer Playwright, navegador instalado e permissão para carregar a extensão. Não é executado pela suíte unittest padrão.

| Verificação | Resultado registrado | Limite |
|---|---|---|
| Base original com reparos | Desktop Windows/Python 3.14.7: 54 testes em 12,364 s, OK, dois opcionais ignorados (52 aprovados) | Resultado informado pelo executor em 16/11; não valida Azure |
| Catálogo | Desktop: 16 testes em 4,342 s, OK | Inclui concorrência e preservação dos dados |
| Complemento Python | Três testes aprovados | Matriz e tratamento de entradas |
| Fila JavaScript | Sete testes aprovados na validação inicial | Node indisponível no desktop corporativo |
| Fluxo no navegador | Demonstração sintética validada anteriormente em Edge e Chrome | Não comprova instalação corporativa nem integração Azure |

O layout desta entrega usa a base na raiz, sem a cópia `base/robot_report_generator` utilizada no ambiente de desenvolvimento. Em 16/11, a verificação adicional deste layout no notebook concluiu 57 testes Python em 18,327 s, OK com dois opcionais ignorados (55 aprovados: 52 da base e três do complemento), além de sete testes JavaScript aprovados. A geração da demonstração com três candidatos e a construção dos pacotes Edge/Chrome também concluíram. Não houve novo teste de interface de navegador nesta preparação.

## Falhas identificadas e reparos
**BASE-WIN-001 — trava do catálogo.** O segundo escritor tentava ler um byte já bloqueado no Windows, causando `PermissionError` antes do tratamento de concorrência. Em `core/catalog.py`, a inicialização passou a consultar o tamanho com `os.fstat()` em vez de ler o byte. Permanecem a aquisição não bloqueante, a rejeição concorrente e a liberação em `finally`. O teste existente verifica rejeição sem alteração do catálogo; foi acrescentado teste de reutilização após exceção em `tests/test_catalog.py`. Reteste isolado, catálogo e suíte completa aprovados no desktop.

**BASE-WIN-002 — comparação de caminhos no teste.** A API normalizava o caminho para o nome completo, enquanto `test_folder_navigation_and_validation` esperava o nome curto Windows 8.3. O esperado passou a usar `self.base.resolve()` em `tests/test_web_app.py`. A aplicação não foi alterada por esse reparo. Reteste da suíte completa aprovado no desktop.

Mensagens de XML inválido, histórico corrompido e `OSError: disco cheio` aparecem nos testes negativos intencionais. Avaliar o resumo final do executor; essas mensagens isoladas não significam falha da suíte.

## Dados e limitações
Usar somente massa sintética para demonstração. Relatórios e exportações podem conter informações e evidências sensíveis: não versionar resultados corporativos, credenciais, sessões ou preferências reais. Dados da fila ficam no perfil local e podem ser removidos conforme o guia de instalação. A visualização de evidência não comprova anexação ao Azure.

## Pendências para a próxima versão
1. Definir distribuição autorizada da extensão ou revisar a estratégia de integração.
2. Confirmar domínio Azure, projeto, permissões, campos obrigatórios e relação estado/coluna.
3. Implementar preenchimento e anexação reais, confirmação inequívoca de salvamento e captura correlacionada de ID/URL.
4. Integrar o botão ao fluxo original efetivamente usado pela equipe e validar retomada, duplicidade e falhas no ambiente real.
5. Obter revisão e aceite do analista antes de promover a versão.

Esta branch é uma alfa para revisão, sem merge automático e sem declaração de integração real concluída. A ferramenta original e sua autoria permanecem preservadas; fontes adicionais estão em `complemento/`, `extension/`, `extensions/`, scripts e testes correspondentes.
