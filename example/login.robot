*** Settings ***
Documentation    Feature: Login do usuário

*** Test Cases ***
Login com credenciais válidas
    [Documentation]    Scenario: usuário acessa o sistema com sucesso
    [Tags]    smoke
    Given o usuário está na página de login
    When o usuário informa credenciais válidas
    Then o usuário vê o dashboard

Login com credenciais inválidas
    [Documentation]    Scenario: usuário tenta logar com senha errada
    [Tags]    regression
    Given o usuário está na página de login
    When o usuário informa uma senha incorreta
    Then o sistema deve rejeitar o login

*** Keywords ***
o usuário está na página de login
    Log    Navegando até /login

o usuário informa credenciais válidas
    Log    Preenchendo usuário e senha válidos

o usuário vê o dashboard
    Log    Validando elemento do dashboard

o usuário informa uma senha incorreta
    Log    Preenchendo senha incorreta

o sistema deve rejeitar o login
    Fail    Elemento 'mensagem-erro' não encontrado na página (timeout 5s)
