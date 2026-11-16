# Laudo de qualidade — Agenda Acadêmica

**Data das verificações:** 8 de novembro de 2026.  
**Versão avaliada:** 1.0 (pasta `versao-1`).  
**Ambiente:** Python 3.13, Node.js 25, SQLite integrado ao Python, macOS.

## Verificações realizadas

| Verificação | Procedimento | Resultado | Evidência |
| --- | --- | --- | --- |
| Fluxo de tarefas | Teste de integração cria, consulta, edita, conclui, reabre e exclui uma tarefa. | Aprovado. | `evidencias/testes_2026-11-08.txt` |
| Persistência | O teste lê a tarefa em uma nova conexão com o banco. | Aprovado. | `evidencias/testes_2026-11-08.txt` |
| Validação | Envio de título vazio, disciplina vazia, data inexistente, estado inválido e observação acima do limite. | Todos rejeitados com erro HTTP 400. | `evidencias/testes_2026-11-08.txt` |
| Recurso inexistente | Edição e exclusão de tarefa não cadastrada. | Erro HTTP 404. | `evidencias/testes_2026-11-08.txt` |
| Plano inicial da PIT | Inclusão em banco vazio e repetição da chamada. | Dez tarefas específicas são criadas uma vez; segunda chamada não duplica. | `evidencias/testes_2026-11-08.txt`, `evidencias/plano_pit_2026-11-08.txt` |
| Disponibilidade local | Requisições à página inicial, `/health` e `/api/tasks` no servidor iniciado localmente. | HTTP 200; `/health` retornou `{"status":"ok"}`. | Execução local em 8/11/2026; fluxo também coberto pelo teste automatizado. |
| Sintaxe | `node --check app.js` e `python3 -m py_compile app.py`. | Aprovado. | `evidencias/sintaxe_2026-11-08.txt` |

O comando registrado para os testes foi `python3 -W error::ResourceWarning -m unittest discover -s tests -v`. Resultado final após a inclusão do plano: **4 testes concluídos, 0 falhas e 0 erros**.

## Ocorrência e correção

**Ocorrência 01 — conexão SQLite não fechada explicitamente.** Na primeira execução dos testes, apareceu `ResourceWarning: unclosed database`. O bloco `with sqlite3.Connection` concluía a transação, mas não encerrava a conexão. A função de acesso ao banco foi ajustada para confirmar ou desfazer a transação e fechar a conexão em `finally`. Os testes foram executados novamente com avisos de recurso tratados como erro e passaram sem esse aviso. Evidência: transcrição do aviso em `evidencias/ocorrencia_01.txt`, código em `app.py` e saída final em `evidencias/testes_2026-11-08.txt`.

**Ocorrência 02 — aplicativo aberto sem registros.** Na primeira execução a lista aparecia vazia, o que dificultava a demonstração. Foram incluídas dez tarefas específicas da PIT, ligadas aos documentos existentes e às etapas futuras. A rotina cria o plano somente em um banco novo e preserva dados já cadastrados. Evidência: `evidencias/plano_pit_2026-11-08.txt` e o teste `test_project_plan_only_populates_an_empty_database` em `evidencias/testes_2026-11-08.txt`.

## Próximas etapas

Realizar a rodada de testes de uso com cinco colegas, registrar o que funcionou e o que precisa ser corrigido e aplicar as correções pertinentes em uma nova versão.
