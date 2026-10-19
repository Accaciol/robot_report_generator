# Robot Report Generator: revisão de segurança

**Público:** equipe de Segurança  
**Objetivo:** revisar os fluxos implementados, delimitar o que o teste local comprovou e alinhar decisões antes de uma implantação remota.

---

## 1. Robot Report Generator: revisão de segurança

### Dados de testes, ingestão por pipeline e publicação dos relatórios

Revisão técnica para alinhamento da equipe de Segurança. O material descreve controles registrados no projeto; não representa auditoria nem declaração de conformidade.

**Referências:** `docs/SEGURANCA_ARQUITETURA.md`, `docs/TESTE_AZURE_DEVOPS_LOCAL.md`.

---

## 2. O que a equipe precisa decidir

- Quais resultados, mensagens de teste e metadados podem ser expostos pelo catálogo público?
- Onde ficará o serviço que recebe os ZIPs e quais agentes terão acesso a ele?
- Quais controles de produção devem ser definidos para rede, TLS, autenticação, operação e retenção?

O teste ponta a ponta validou o fluxo funcional em loopback. Ele não validou a implantação remota.

**Referência:** `docs/SEGURANCA_ARQUITETURA.md`, “Cenário testado e diferença para produção”.

---

## 3. Fluxo de dados e fronteiras

```text
Azure DevOps
    │ pipeline compacta os resultados
    ▼
Agente self-hosted ── bearer token ──► API Flask
                                          │ valida ZIP e metadados
                                          ▼
                                     staging / fila
                                          │ parser Robot Framework
                                  ┌───────┴────────┐
                                  ▼                ▼
                              SQLite       artefatos em disco
                                  └───────┬────────┘
                                          ▼
                              catálogo público / relatório
```

Entradas também podem vir da interface administrativa local ou da CLI. O servidor importa XML e evidências e gera as visualizações a partir do catálogo.

**Referências:** `docs/SEGURANCA_ARQUITETURA.md`, “Fluxos de entrada e processamento”; `docs/DOCUMENTACAO_ARQUIVOS.md`, “Fluxo de dados”.

---

## 4. Dados processados e persistidos

| Dado | Uso / localização descritos |
|---|---|
| `output.xml` | Suítes, resultados, mensagens, tempos, metadados e data da execução |
| Evidências | ZIP original e resultados da execução mais recente em `executions/` |
| Metadados | ID, nome e versão do sistema |
| Histórico e snapshots | SQLite definido por `ROBOT_REPORT_DATABASE` |
| Upload pendente | Diretório `.pending-*`; expira após 30 minutos e é limpo por operações do serviço |

O identificador da execução usa SHA-256 do `output.xml`; reenvios do mesmo XML não criam duplicatas. Ao entrar uma execução mais recente, os artefatos anteriores são removidos, mas o resumo permanece no histórico.

**Referência:** `docs/SEGURANCA_ARQUITETURA.md`, “Dados e armazenamento”.

---

## 5. Credenciais e controle de acesso

| Credencial | Escopo descrito |
|---|---|
| PAT Azure DevOps | Registro do agente no pool; o guia recomenda validade curta e escopo `Agent Pools: Read & manage` |
| `ROBOT_REPORT_INGEST_TOKEN` | Bearer token para enviar importações e consultar seu estado |
| Token de sessão | Acesso administrativo local; URL e token devem ser tratados como credenciais |

As credenciais têm usos separados. O token de ingestão deve ficar em variável secreta no Azure DevOps, nunca no YAML. As rotas administrativas exigem as verificações de sessão/origem descritas no projeto.

**Referências:** `docs/SEGURANCA_ARQUITETURA.md`, “Autenticação, autorização e exposição”; `docs/TESTE_AZURE_DEVOPS_LOCAL.md`, “Credenciais”.

---

## 6. Catálogo público: decisão de exposição

`/public`, `/public/api/*` e `/public/reports/*` permitem leitura sem login. O conteúdo pode incluir nomes, versões, métricas, histórico, mensagens de falha e informações ambientais presentes no XML.

- Qualquer pessoa com acesso de rede à URL pode consultar os relatórios.
- A API pública de PDF também aceita geração e download.
- As rotas de mudança de estado continuam protegidas por autenticação.

**Decisão necessária:** classificar os dados de entrada e confirmar se o conteúdo completo pode ser público para a rede onde o serviço ficará acessível.

**Referência:** `docs/SEGURANCA_ARQUITETURA.md`, “Catálogo público”.

---

## 7. Controles de entrada de arquivos

- ZIP recebido: limite padrão de **500 MiB**.
- Conteúdo extraído: limite padrão de **1 GiB** e **10.000 membros**.
- Rejeita caminhos absolutos, traversal (`..`), nomes duplicados, links e tipos não regulares.
- O nome enviado pelo cliente não define o destino; o servidor usa caminhos de staging.
- Valida IDs, nome e versão; permite uma importação ativa por vez e remove a pasta temporária após o processamento.

Os limites podem ser ajustados por variáveis de ambiente documentadas. A configuração efetiva deve ser conferida no ambiente implantado.

**Referência:** `docs/SEGURANCA_ARQUITETURA.md`, “Validação de arquivos e execução”.

---

## 8. O que o teste Azure comprovou

**Topologia exercitada:** Azure DevOps Services → agente self-hosted Linux → servidor na mesma máquina, usando `127.0.0.1:5001`, HTTP e SQLite temporário em `/tmp`.

O teste confirmou envio do ZIP, processamento, atualização do catálogo e deduplicação ao reenviar o mesmo XML.

**Não comprovou:** conectividade remota, TLS, proxy reverso, controles de rede de produção, operação de segredos em produção ou isolamento entre clientes. `127.0.0.1` só aponta para a própria máquina; um agente hospedado pela Microsoft não alcança por esse endereço um servidor externo.

**Referências:** `docs/TESTE_AZURE_DEVOPS_LOCAL.md`, “Topologia do teste”; `docs/SEGURANCA_ARQUITETURA.md`, “Cenário testado e diferença para produção”.

---

## 9. Cabeçalhos e limites dos controles HTTP

O projeto configura `Cache-Control: no-store`, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, Content Security Policy e sandbox para páginas de relatório embutidas.

Esses cabeçalhos reduzem algumas classes de exposição no navegador. Não substituem HTTPS, autenticação, autorização ou controles de rede.

O guia registra que `gui.py` usa o servidor de desenvolvimento Werkzeug. `infra/docker-compose.yml` publica a porta 5000 e escuta em `0.0.0.0`; o alcance depende do host, firewall e publicação de rede.

**Referência:** `docs/SEGURANCA_ARQUITETURA.md`, “Cenário testado e diferença para produção” e “Controles HTTP observados”.

---

## 10. Perguntas para fechar a revisão

1. Qual classificação se aplica a XMLs, mensagens de falha e evidências?
2. O catálogo público é aceitável para essa classificação e para a rede planejada?
3. Qual topologia aprovada atende agentes remotos, com HTTPS e controles de rede definidos?
4. Quem administra e rotaciona o token de ingestão e os tokens de acesso ao agente?
5. Quais são os requisitos de retenção, recuperação dos dados e remoção de artefatos?
6. Quais controles de operação e isolamento devem existir antes de produção?

**Resultado esperado da reunião:** decisões registradas, responsáveis definidos e pendências de produção priorizadas.

**Referências:** `docs/SEGURANCA_ARQUITETURA.md`; `docs/TESTE_AZURE_DEVOPS_LOCAL.md`.
