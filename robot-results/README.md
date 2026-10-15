# Banco de resultados

O histórico da aplicação fica no banco SQLite `report_history.sqlite3`. O
caminho padrão é este diretório; configure `ROBOT_REPORT_DATABASE` ou passe
`--database` para usar outro local. Arquivos de execuções atuais ficam na pasta
`executions/`, ao lado do banco.

Use `scripts/update_robot_results.py` para importar, listar ou remover execuções:

```bash
python scripts/update_robot_results.py /caminho/resultados \
  --system portal --name "Portal" --version 1.2
python scripts/update_robot_results.py --list
python scripts/update_robot_results.py --system portal --remove ID_COMPLETO
```

Para converter um catálogo antigo que contenha `systems/<id>/system.json`,
`history.json` e opcionalmente `current/output.xml`, execute:

```bash
python scripts/migrate_json_catalog.py /caminho/catalogo-antigo
```

Para importar apenas um arquivo JSON de histórico:

```bash
python scripts/migrate_json_catalog.py --history-json /caminho/history.json \
  --system portal --name "Portal"
```

A migração importa resumos e a execução atual para SQLite e preserva os arquivos
JSON e evidências originais. Faça um backup do catálogo antigo antes de migrar.
Relatórios HTML exportados são cópias estáticas e não são atualizados quando o
banco muda; gere-os novamente quando necessário.
