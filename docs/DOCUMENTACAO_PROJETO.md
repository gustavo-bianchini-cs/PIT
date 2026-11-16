# Documentação do projeto — Agenda Acadêmica

## 1. Identificação e objetivo

**Nome do sistema:** Agenda Acadêmica.  
**Objetivo:** ajudar estudantes a acompanhar prazos de trabalhos, provas e atividades em uma lista simples.  
**Público-alvo:** estudantes que precisam organizar tarefas de diferentes disciplinas.  
**Problema tratado:** prazos anotados em lugares diferentes podem ser esquecidos ou difíceis de acompanhar.

Esta documentação descreve a versão 1.0, implementada em 8 de novembro de 2026.

## 2. Escopo da versão

O sistema oferece:

1. Cadastro de tarefa com título, disciplina, data de entrega e observações opcionais.
2. Visualização da lista ordenada por estado e prazo.
3. Edição dos dados de uma tarefa.
4. Marcação como concluída e reabertura.
5. Exclusão com confirmação.
6. Filtros: todas, pendentes e concluídas.
7. Resumo com quantidades de tarefas totais, pendentes e concluídas.
8. Identificação de tarefas pendentes cujo prazo já passou.
9. Inclusão de dez tarefas iniciais relacionadas à entrega da PIT, apenas na primeira execução de um banco novo.

Não há autenticação nem compartilhamento entre pessoas. O servidor é destinado a uso local em um computador.

## 3. Requisitos funcionais

| Código | Requisito | Critério de aceitação |
| --- | --- | --- |
| RF01 | Cadastrar tarefa | Uma tarefa válida aparece na lista após salvar. |
| RF02 | Consultar tarefas | A lista é carregada a partir do banco ao abrir ou atualizar a página. |
| RF03 | Editar tarefa | Título, disciplina, prazo e observações podem ser alterados. |
| RF04 | Alterar estado | É possível concluir e reabrir uma tarefa. |
| RF05 | Excluir tarefa | A tarefa desaparece após confirmação e remoção no banco. |
| RF06 | Filtrar lista | O filtro selecionado mostra apenas os itens correspondentes. |
| RF07 | Exibir resumo | Os contadores refletem os registros carregados. |

## 4. Regras de negócio

- Título e disciplina são obrigatórios; espaços isolados não são aceitos.
- O título tem até 120 caracteres e a disciplina até 80.
- A data deve existir no calendário e usar o formato `AAAA-MM-DD`.
- Observações são opcionais e têm até 500 caracteres.
- Uma tarefa nova começa como pendente.
- Tarefa concluída permanece armazenada e pode ser reaberta.
- Uma tarefa pendente com data anterior à data local do navegador aparece como atrasada.
- A exclusão exige confirmação na interface.
- O plano inicial da PIT é incluído somente quando o arquivo de banco ainda não existe. Depois, as tarefas podem ser editadas ou excluídas normalmente.

## 5. Arquitetura e dados

**Interface:** HTML, CSS e JavaScript sem biblioteca externa.  
**Servidor:** Python 3 com a biblioteca padrão (`http.server`).  
**Banco de dados:** SQLite, criado no primeiro uso.  
**Hospedagem atual:** execução local em `127.0.0.1`.

O navegador envia requisições JSON para a API. O servidor valida os dados e executa comandos SQL parametrizados. A tabela `tasks` contém `id`, `title`, `subject`, `due_date`, `notes`, `completed`, `created_at` e `updated_at`.

| Método | Rota | Finalidade |
| --- | --- | --- |
| GET | `/api/tasks` | Listar tarefas. |
| POST | `/api/tasks` | Cadastrar tarefa. |
| PUT | `/api/tasks/{id}` | Editar dados ou estado. |
| DELETE | `/api/tasks/{id}` | Excluir tarefa. |
| GET | `/health` | Verificar se o servidor responde. |

## 6. Fluxo de uso

1. Na primeira execução de uma cópia nova, dez tarefas da PIT aparecem na lista; em usos seguintes, o sistema carrega apenas os registros existentes.
2. Clica em **Nova tarefa**, preenche os campos e salva.
3. A tarefa aparece na lista. Pode ser editada, concluída ou excluída.
4. O usuário escolhe um filtro para consultar tarefas pendentes ou concluídas.
5. Ao reabrir a página, os dados são lidos novamente do SQLite.

## 7. Verificação e limites

Os testes automatizados cobrem cadastro, consulta, edição, conclusão, reabertura, exclusão, gravação no banco, dados inválidos, tarefas inexistentes, resposta da página e inclusão do plano inicial em banco vazio. Os resultados e as correções observadas estão em `LAUDO_QUALIDADE.md`, com logs em `evidencias/`.

Próximas etapas: rodada de testes de uso com cinco colegas, correções a partir do retorno obtido e publicação da aplicação em um endereço externo.
