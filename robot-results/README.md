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

Relatórios HTML exportados são cópias estáticas e não são atualizados quando o
banco muda; gere-os novamente quando necessário.
