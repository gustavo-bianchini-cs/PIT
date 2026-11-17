# Histórico de versões

## 2.3 — 17/11/2026

### Nova funcionalidade (agenda separada por pessoa, pedido dos testes da versão 1.0)
- Tela de entrada com três opções: **Entrar**, **Criar conta** (nome, usuário, senha e pergunta secreta com resposta) e **Esqueci minha senha**.
- Cada conta vê, altera e exporta somente as próprias tarefas.
- Recuperação de senha: a pessoa informa o usuário, responde à pergunta secreta que ela mesma criou e escolhe uma nova senha. Maiúsculas, acentos e espaços a mais não contam na resposta.
- Nome da pessoa e botão "Sair" no topo da agenda.

### Segurança
- Senhas e respostas secretas guardadas só como hash PBKDF2-SHA256 (600 mil iterações, sal aleatório por registro).
- Sessão em cookie `HttpOnly` e `SameSite=Lax` (o JavaScript da página não lê o cookie; outros sites não fazem pedidos com ele), válida por 7 dias; o banco guarda só o hash do token.
- Depois de 5 tentativas erradas de senha ou de resposta secreta, o usuário fica bloqueado por 15 minutos.
- Trocar a senha pela pergunta secreta encerra a sessão em todos os outros aparelhos.
- A mesma mensagem ("Usuário ou senha incorretos.") para usuário inexistente e senha errada.

### Mudanças
- A senha única da versão 2.1 (janela do navegador) foi substituída pelas contas. Na hospedagem, `AGENDA_USUARIO` e `AGENDA_SENHA` passam a criar a conta do avaliador a cada inicialização; o endereço e a senha de acesso continuam os mesmos.
- Tarefas que já existiam (plano inicial e bancos das versões anteriores) passam para a primeira conta criada, ou para a conta do avaliador na hospedagem.

### Técnico
- Tabelas `users` e `sessions`; coluna `user_id` em `tasks`, adicionada automaticamente em bancos antigos.
- Testes automatizados: de 18 para 23.

## 2.2 — 17/11/2026

### Nova funcionalidade (sugestão de Cesar Alexandrini nos testes da versão 1.0)
- Horário de entrega opcional no formulário. Sem horário, o prazo vale até 23:59 do dia.
- Cor de cada tarefa pendente conforme o tempo que falta: verde (mais de 6 horas), amarelo (menos de 6 horas), laranja (menos de 1 hora) e vermelho (prazo encerrado), com legenda acima da lista.
- Na reta final, o prazo mostra o tempo restante ("Faltam 35 min · até 13:31").
- A lista é atualizada a cada minuto, então a cor muda sem recarregar a página.
- Atrasadas, ordenação e o aviso de prazo já passado passam a considerar data e horário.
- Planilha exportada com a coluna "Horário".

### Técnico
- Nova coluna `due_time`, adicionada automaticamente em bancos das versões 1.0 e 2.1.
- Ícone da aba do navegador.
- Testes automatizados: de 15 para 18.

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
