# Resultados de entrada

A pasta `current/` contém somente os resultados da execução mais recente.
Para substituir o conteúdo anterior, execute na raiz do projeto:

```bash
python scripts/update_robot_results.py /caminho/para/resultados
git add -A robot-results/current
git commit -m "Atualiza resultados do Robot"
git push
```

A origem precisa conter `output.xml`. As evidências são copiadas preservando os
caminhos relativos. `log.html` e `report.html` da raiz da origem não são copiados,
pois o gerador não precisa deles. O script não faz commit nem push automaticamente.

Arquivos antigos são removidos da pasta atual, mas continuam no histórico do Git.
Não coloque outras informações em `current/`: seu conteúdo será substituído.
