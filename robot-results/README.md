# Resultados por sistema

O catálogo versionado fica em `systems/<identificador>/`, com `system.json`,
`history.json` e os outputs mais recentes em `current/`. O histórico de resumos
não tem limite automático; os outputs antigos são substituídos por sistema.

Na raiz do projeto:

```bash
python scripts/update_robot_results.py /caminho/resultados --system portal --name "Portal"
python scripts/update_robot_results.py --list --system portal
python scripts/update_robot_results.py --system portal --remove ID_COMPLETO_DA_EXECUCAO
python main.py --catalog-dir robot-results/systems --report relatorio.html
git add -A robot-results/systems
git commit -m "Atualiza resultados dos sistemas"
git push
```

A origem precisa conter `output.xml` e suas evidências por caminhos relativos.
Use a listagem para obter o ID completo antes de remover uma execução. Remover a
execução atual apaga também seus outputs; a anterior fica disponível como resumo.
HTMLs já baixados não são alterados. Nenhum comando faz commit ou push automaticamente.

A pasta `robot-results/current/` é legada e não alimenta mais a pipeline. Para migrar,
importe-a com `--system`. Para incluir também um histórico antigo, use
`--migrate-history /caminho/history.json` na importação para um sistema novo.

Consulte o [README principal](../README.md#sistemas-histórico-e-azure-pipelines)
para migração, retenção e cadastro da pipeline. Excluir outputs atuais não remove
suas versões antigas do histórico do Git.
