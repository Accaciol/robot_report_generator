# Ruzy — alfa local com Selenium

Versão `0.2.0-alpha.1` · 17/11/2026 · branch `alpha/ruzy-local-2026-11-17`.
Complemento experimental do robot_report_generator, de Accaciol, base original `ba61a344dd324dab5ccb999e261f0abbf629d52d`. A versão 0.2 identifica o complemento; a versão do pacote original permanece 1.0.0. A primeira alfa com extensão permanece na branch `alpha/ruzy-review-2026-11-16`; a main não recebe alterações nem merge por esta entrega.

## Estado e funcionamento
Esta versão substitui a extensão por um serviço Python local e um navegador dedicado controlado pelo Selenium. O parser e o renderer originais continuam gerando a matriz e o relatório. Não há classificação por IA: falhas são candidatas à revisão humana.

O fluxo atual é **sintético**: abre um formulário por vez, preenche título e descrição, mostra evidências de imagem disponíveis e aguarda salvar ou descartar. Fechar ou navegar para outra página pausa a fila. As decisões são persistidas antes de avançar; tentativas vencidas/repetidas são rejeitadas. Os códigos `SIM` não são IDs Azure; nenhum card real ou anexo é enviado ao Azure.

- HTML avulso: botão cinza/desabilitado, sem mensagem de serviço ausente.
- Relatório aberto pela janela do serviço: botão habilitado após conexão; a configuração fica no painel local confiável.
- Exportação: nova cópia HTML com o consolidado original e a tabela de decisões, além de JSON. O HTML final funciona sem Python; não contém a sessão local nem reinicia uma fila.

Para manter o relatório isolado, esta alfa não procura serviços locais a partir de qualquer HTML avulso. O serviço abre sua própria janela com o relatório incorporado em sandbox; somente essa conexão habilita o botão. O arquivo original não é sobrescrito pela exportação.

## Instalação e uso
Requer Python 3.10+ e Edge ou Chrome instalado. No notebook, foi validado com Python 3.14, Chrome e Edge. O WebDriver correspondente precisa estar disponível; o Selenium Manager pode baixá-lo no primeiro uso. Políticas corporativas podem bloquear o WebDriver mesmo sem extensão; não contorná-las.

Na raiz do clone desta branch, em PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ruzy-dev.txt
.\.venv\Scripts\python.exe scripts/build_demo.py
.\.venv\Scripts\python.exe -m complemento.local_service --results-dir demo/results --browser edge
```

Para Chrome, substituir `--browser edge` por `--browser chrome`. O gerador executa três falhas intencionais, um caso aprovado e um ignorado: são a massa da demonstração. Para resultados próprios autorizados, trocar `demo/results` pelo diretório que contém `output.xml` e evidências. `--report` escolhe o HTML gerado; `--state-dir` escolhe o estado privado; `--port` muda a porta local (padrão 8877).

Na janela aberta, clicar no botão do relatório, informar um board e preparar. Iniciar a fila, revisar e salvar/descartar os formulários fictícios. Ao concluir, há tentativa de download automático do HTML; os botões de exportação permitem repetir o download. Ctrl+C encerra o serviço. Se a abertura do navegador falhar, a fila pausa; conferir driver/política/rede antes de retomar.

Configuração por execução: URL do board, tipo, estado, coluna de referência, área, iteração, responsável, prioridade e tags. São aceitos links HTTPS de `dev.azure.com` com organização/projeto e `_boards`; outros domínios aguardam validação. A URL não é acessada nesta alfa. Estado e coluna são campos diferentes; o mapeamento real continua pendente. A configuração fica congelada durante a fila.

O comando `ruzy-local` também fica disponível após instalar `pip install -e '.[ruzy]'`. `main.py` e `gui.py` originais ainda não incorporam o botão; usar o comando complementar acima.

## Testes e correções

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
$env:RUZY_SELENIUM_TESTS="1"
.\.venv\Scripts\python.exe -m unittest tests.test_selenium_local -v
```

A suíte padrão cobre a base, a matriz, a fila e o serviço. Os testes de navegador são opcionais; o segundo comando abre Chrome em modo headless (usar `RUZY_TEST_BROWSER=edge` para Edge) e usa somente páginas sintéticas locais. Imagens de conferência ficam em `test-results/`, fora do Git.

Resultados de 17/11: suíte padrão de 68 testes, 65 aprovados e três opcionais ignorados; teste Selenium executado separadamente e aprovado em Chrome (14,897 s) e Edge (23,503 s). O cenário de navegador verifica botão avulso inativo, ativação pelo serviço, preenchimento, salvar/descarte sequenciais, fechamento e retomada, título revisado e HTML final portátil sem token. O Azure real e o ambiente corporativo não foram validados nesta migração. `pip check` sem incompatibilidades. Construção do wheel concluída e conteúdo conferido, incluindo interface e comando `ruzy-local`.

Reparos da base preservados da primeira alfa:
- **BASE-WIN-001:** `Catalog._writer()` consultava um byte já bloqueado no Windows. A inicialização usa `os.fstat()` sem ler esse byte, preservando rejeição concorrente e liberação em `finally`. Teste adicional cobre reutilização após exceção.
- **BASE-WIN-002:** o teste de navegação comparava nomes curto e completo da mesma pasta. O esperado usa `self.base.resolve()`, sem alterar a navegação da aplicação.
- A base reparada teve reteste corporativo em 16/11: 54 testes em 12,364 s, OK com dois opcionais ignorados. Isso não constitui aceite da integração Azure.

Mensagens de XML inválido, histórico corrompido e disco cheio fazem parte dos testes negativos. A fila local também verifica que falha de gravação não avança o candidato.

## Dados e segurança
Serviço ligado somente em `127.0.0.1`, com sessão temporária, validação de Host/Origin, sem CORS aberto. O relatório fica em iframe sandbox sem acesso de mesma origem e nunca recebe o token da API. A comunicação do iframe transporta somente disponibilidade/pedido para mostrar configuração; os comandos exigem confirmação no painel confiável. Conteúdo de resultados é escapado na exportação.

Selenium usa um perfil dedicado. A alfa não lê cookies do perfil pessoal, não solicita credenciais Azure e não utiliza PyAutoGUI; esse apoio só será adicionado se houver necessidade concreta.

Estado em `.ruzy-state/<report_id>.json`, com configuração e decisões, sem cópias das imagens. Reiniciar interrompido pausa a fila e invalida a tentativa anterior. Arquivo corrompido ou incompatível gera erro, sem reset silencioso. Executar somente uma instância por diretório de estado; não há coordenação entre vários processos. Exportar antes de remover o estado; removê-lo perde a memória de decisões. Não versionar estado, sessões, evidências corporativas ou exportações reais. Os HTMLs mantêm as evidências e exigem guarda privada conforme seu conteúdo.

## Mudanças e próximos passos
Foram removidos fontes e pacotes da extensão, testes Node e HTML pré-gerado; a demonstração passa a ser gerada por comando. Não é preciso instalar Node ou extensão para esta versão. O histórico anterior permanece na primeira branch.

A base local está pronta para avaliação sintética. Ainda faltam: inspecionar o Azure autorizado, implementar o adaptador real com campos/seletores e login humano, confirmar salvamento e ID correlacionados, anexar evidências, mapear coluna/estado e integrar ao fluxo original. O suporte Edge também precisa de validação no ambiente corporativo. Não inferir que um clique em Salvar ou um número na URL prova a criação de um bug.

Referências: [Selenium: esperas explícitas](https://www.selenium.dev/documentation/webdriver/waits/) e [Microsoft: WebDriver para Edge e políticas](https://learn.microsoft.com/en-us/microsoft-edge/webdriver-chromium/).
