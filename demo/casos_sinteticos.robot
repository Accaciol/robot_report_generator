*** Settings ***
Documentation    Casos fictícios para validar Ruzy. Sem acesso a sistemas externos.

*** Test Cases ***
Login apresenta erro após credenciais válidas
    [Tags]    login    regressao
    Log    *HTML* <img src="evidencia.png">
    Fail    Resultado esperado: painel inicial. Resultado obtido: mensagem de erro.

Cadastro com massa já utilizada
    [Tags]    massa
    Fail    Registro fictício já cadastrado. Conferir se há defeito ou problema na massa.

Consulta excede o tempo de resposta
    [Tags]    consulta    ambiente
    Log    *HTML* <img src="evidencia.png">
    Fail    Timeout de exemplo. A causa deve ser revisada pelo analista.

Cenário que passou não gera formulário
    Log    Execução fictícia aprovada.

Cenário ignorado não gera formulário
    Skip    Cenário fictício fora do recorte.
