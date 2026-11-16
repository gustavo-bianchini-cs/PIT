# Agenda Acadêmica — versão 1.0

Aplicação web para organizar trabalhos, provas e outras tarefas de estudo. Permite cadastrar, editar, concluir, reabrir, excluir e filtrar tarefas. Os dados são salvos em SQLite.

## Como executar

Requisito: Python 3.10 ou superior. Não é necessário instalar pacotes.

1. Abra um terminal nesta pasta (`versao-1`).
2. Execute `python3 app.py`.
3. Acesse `http://127.0.0.1:8000` no navegador.
4. Para encerrar, pressione `Ctrl+C` no terminal.

O banco de dados é criado automaticamente em `data/agenda.db`. Na primeira execução, ele recebe dez tarefas com as etapas da PIT (quatro concluídas e seis pendentes). Elas podem ser editadas ou excluídas e não são recriadas depois. Para usar outra porta, defina a variável `PORT`. Para usar outro arquivo de banco, defina `AGENDA_DB_PATH`.

## Como testar

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -v
```

Os testes usam um banco temporário e não alteram as tarefas cadastradas.

## Arquivos

- `app.py`: servidor HTTP, validação dos dados e acesso ao SQLite.
- `index.html`, `styles.css`, `app.js`: interface para computador e celular.
- `tests/test_app.py`: testes de integração da API.
