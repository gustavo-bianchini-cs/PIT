# Agenda Acadêmica — versão 2.1

Segunda versão da Agenda Acadêmica (2.0, com o ajuste 2.1 para a publicação), com novas funcionalidades e correções feitas a partir dos testes da versão 1.0. A lista completa de mudanças está em [`../CHANGELOG.md`](../CHANGELOG.md) e os detalhes de cada correção em [`../docs/LAUDO_QUALIDADE.md`](../docs/LAUDO_QUALIDADE.md).

## Como executar

Requisito: Python 3.10 ou superior. Não é necessário instalar pacotes.

```bash
cd versao-2
python3 app.py
```

Acesse `http://127.0.0.1:8000`. Para encerrar, pressione `Ctrl+C`.

### Abrir no celular (mesma rede Wi-Fi)

```bash
HOST=0.0.0.0 python3 app.py
```

O terminal mostra o endereço para digitar no celular, por exemplo `http://192.168.0.10:8000`.

### Variáveis de ambiente

| Variável | Padrão | Uso |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | `0.0.0.0` libera o acesso pela rede e é usado na hospedagem. |
| `PORT` | `8000` | Porta do servidor. |
| `AGENDA_DB_PATH` | `data/agenda.db` | Arquivo do banco SQLite. |
| `AGENDA_SENHA` | vazio | Se definida, o navegador pede usuário e senha para abrir a agenda. Usada na hospedagem. |
| `AGENDA_USUARIO` | `avaliador` | Usuário pedido junto com a senha. |

Um banco criado pela versão 1.0 pode ser usado diretamente: na primeira execução, a coluna de prioridade é adicionada e as tarefas existentes recebem prioridade média.

## Como testar

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -v
```

## O que mudou em relação à versão 1.0

- Busca por título, disciplina ou observação, sem diferenciar acentos.
- Prioridade (baixa, média, alta) com migração automática do banco.
- Filtro e contador de tarefas atrasadas.
- Prazo relativo: "Vence hoje", "Vence amanhã", "Faltam 3 dias", "Atrasada há 2 dias".
- Ordenação por prazo, prioridade ou disciplina.
- Exportação da lista para planilha (CSV compatível com o Excel).
- Sugestão das disciplinas já cadastradas e contador de caracteres nas observações.
- 2.1: acesso protegido por usuário e senha na versão publicada (`AGENDA_SENHA`).
- Correções: confirmação antes de descartar o formulário, mensagens de erro em português e visíveis dentro do formulário, aviso de data no passado, acesso pela rede/hospedagem e aviso de porta ocupada.
