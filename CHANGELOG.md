# Histórico de versões

## 2.1 — 16/11/2026

### Correção
- Na publicação, qualquer pessoa com o link podia ver e alterar a lista. Agora, com a variável `AGENDA_SENHA` definida na hospedagem, o navegador pede usuário e senha antes de abrir a agenda. Rodando no próprio computador, nada muda.
- A rota `/health` continua aberta para a verificação automática da hospedagem.
- Testes automatizados: de 9 para 11.

### Ajustes de publicação (depois da tag v2.1)
- Na hospedagem, o terminal mostrava endereços internos do servidor (127.0.0.1 e o IP da rede do Render), que não abrem no navegador. Agora mostra o link público e avisa quando `AGENDA_SENHA` não está definida.
- O servidor passou a responder a requisições HEAD (antes: erro 501 nas verificações automáticas da hospedagem).
- Espaços e aspas colados junto com a senha no painel da hospedagem são ignorados, e cada login recusado é registrado no log com o motivo (usuário recebido e tamanho da senha, nunca o conteúdo).
- Testes automatizados: 15.

## 2.0 — 16/11/2026

### Novas funcionalidades
- Campo de busca por título, disciplina ou observação (ignora maiúsculas e acentos).
- Prioridade da tarefa (baixa, média ou alta), exibida na lista e usada na ordenação.
- Filtro "Atrasadas" e cartão com a quantidade de tarefas atrasadas.
- Prazo relativo na lista: vence hoje, vence amanhã, faltam N dias, atrasada há N dias.
- Ordenação por prazo, prioridade ou disciplina.
- Exportação da lista para planilha CSV (separador `;` e acentos corretos no Excel).
- Sugestão das disciplinas já cadastradas no formulário.
- Contador de caracteres no campo de observações.
- Tarefas concluídas continuam mostrando o prazo original.

### Correções
- O formulário era fechado ao clicar fora ou apertar Esc e o texto digitado era perdido. Agora há confirmação antes de descartar.
- Com o servidor desligado, a mensagem exibida era "Failed to fetch". Agora a mensagem é em português e explica o que fazer.
- Mensagens de erro ficavam atrás do fundo escurecido do formulário. Agora aparecem dentro dele.
- Datas de entrega no passado eram aceitas sem aviso. Agora o sistema pede confirmação.
- O servidor só aceitava conexões do próprio computador. Agora a variável `HOST` permite o acesso pelo celular e a publicação em hospedagem (`render.yaml`).
- Porta ocupada mostrava um erro técnico do Python. Agora aparece uma orientação em português.

### Técnico
- Migração automática do banco da versão 1.0 (coluna `priority`).
- Comandos SQL com parâmetros nomeados.
- Testes automatizados: de 4 para 9.

## 1.0 — 08/11/2026

- Cadastro, edição, conclusão, reabertura e exclusão de tarefas.
- Filtros: todas, pendentes e concluídas; resumo com totais.
- Identificação de tarefas atrasadas.
- Persistência em SQLite e plano inicial com as etapas da PIT.
- 4 testes automatizados de integração.
