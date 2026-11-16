# Demonstração Ruzy — escolha Edge ou Chrome

Esta versão funciona inteiramente com formulários fictícios. Não acessa o Azure e não cria cards reais.

## Edge
1. Extraia o pacote para uma pasta fixa; não mova essa pasta depois da instalação.
2. Abra `edge://extensions` e ative **Modo do desenvolvedor**.
3. Use **Carregar sem compactação** e selecione `extensions/edge`, a pasta que contém o manifest.json.
4. Nos detalhes da extensão Ruzy, habilite **Permitir acesso a URLs de arquivos**.

## Chrome
1. Extraia o pacote para uma pasta fixa; não mova essa pasta depois da instalação.
2. Abra `chrome://extensions` e ative **Modo do desenvolvedor**.
3. Use **Carregar sem compactação** e selecione `extensions/chrome`, a pasta que contém o manifest.json.
4. Nos detalhes da extensão Ruzy, habilite **Permitir acesso a URLs de arquivos**.

Instale apenas a opção correspondente ao navegador em que abrirá o relatório. O navegador usado pelo Robot para executar os testes pode ser outro. Se os dois navegadores forem usados, cada um terá sua instalação, preferências e fila independentes.

Se a política da empresa impedir extensões ou modo de desenvolvedor, não contorne essa política; registre a restrição para decidir a distribuição com a equipe.

## Experimentar sem instalar Python
1. Abra `demo/relatorio-demo.html` no navegador escolhido. Recarregue se ele já estava aberto antes da instalação.
2. No fim do relatório, em **Ruzy · demonstração local**, clique **Configurar e preparar bugs**.
3. Pode manter o board fictício preenchido. Ou informe o link de destino para testar a configuração; ele não será acessado nesta versão.
4. Informe tipo, estado inicial, coluna desejada e demais campos necessários. A coluna é uma referência: seu mapeamento com o estado ainda precisa ser validado no Azure.
5. Marque **Lembrar** somente se quiser guardar as preferências neste perfil de navegador.
6. Confirme a preparação e clique **Iniciar abertura de cards simulados**.
7. Salve o primeiro formulário, descarte o segundo e salve o terceiro. O próximo abre na mesma aba, apenas depois da decisão.
8. Confira os códigos SIM no relatório. Ao concluir, uma nova cópia HTML é baixada automaticamente; JSON e nova exportação HTML também estão disponíveis por botão.

Se fechar o formulário sem decidir, volte ao relatório e use **Retomar fila simulada**. Fechar a aba não conta como descarte. Se o relatório de origem for fechado, reabra o mesmo arquivo e retome. Não navegue manualmente para outras páginas na aba do formulário; feche-a para pausar e retome pelo relatório.

Se o navegador impedir o download automático, use **Exportar relatório HTML** ou **Exportar decisões JSON**. A cópia original não é sobrescrita. O relatório exportado é somente um resultado: abri-lo não inicia outra fila.

## Limpar dados
Exporte o resultado, feche a aba do formulário e clique **Limpar dados desta execução**. Isso remove a fila e as decisões. Para apagar preferências, prepare uma execução sem marcar **Lembrar**; também é possível remover os dados ao desinstalar a extensão. Nada é sincronizado com uma conta ou servidor pelo Ruzy.

## O que ainda falta no trabalho
Confirmar endereço/versão Azure, permissão de instalação, campos reais, estado/coluna, preenchimento, envio de anexos e detecção do ID após salvar. A pré-visualização da evidência nesta demonstração não comprova anexação ao Azure.

## Referências
[Instalação de extensão local no Edge](https://learn.microsoft.com/en-us/microsoft-edge/extensions/getting-started/extension-sideloading).
[Modo de desenvolvimento do Chrome](https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world#load-unpacked).
