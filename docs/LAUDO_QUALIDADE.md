# Laudo de qualidade — Agenda Acadêmica

**Responsável:** Gustavo Emanoel Bianchini — RGM 33636541
**Versões avaliadas:** 1.0 (pasta `versao-1`), 2.0, 2.1 e 2.2 (pasta `versao-2`)
**Datas das verificações:** 08/11/2026 (versão 1.0), 16/11/2026 (testes com os colegas na versão 1.0 e reteste na versão 2.0) e 17/11/2026 (versão 2.2)
**Ambiente:** macOS, Python 3.13, SQLite integrado ao Python, Google Chrome (computador 1366×900 e celular 390×844), Node.js para verificação de sintaxe.

## 1. Metodologia

1. **Testes automatizados de integração** (`unittest`): sobem o servidor com um banco temporário e chamam a API como o navegador faria.
2. **Roteiro de uso na interface:** cadastro, edição, conclusão, exclusão, filtros, fechamento do formulário, datas no passado e servidor desligado, executados no Google Chrome com registro do que aparece na tela.
3. **Verificação de rede e inicialização:** acesso pelo IP do computador na rede Wi-Fi (como um celular faria) e execução com a porta já ocupada.
4. **Testes com cinco colegas** (16/11/2026, versão 1.0 rodando no computador do desenvolvedor), cada um em uma área: João Felipe Santos da Silva (cadastro e formulário), Kawan Schultz Bueno (edição e prazos), Cesar Alexandrini (filtros, exclusão e dados salvos), Maria Julia Collodel e Silva (celular e rede) e Arthur Sestrem (mensagens de erro). Os relatos estão no formulário da atividade (seção "Testes da Solução"). Para registrar cada ponto com precisão, o desenvolvedor executou roteiros nas mesmas cinco áreas e anotou o resultado em `evidencias/sessoes_teste_v1_2026-11-16.txt`.

Cada problema recebeu uma severidade: **alta** (impede o uso ou a publicação), **média** (pode causar perda de dados ou confusão) ou **baixa** (incômodo, com contorno simples).

## 2. Resultado da versão 1.0

| Verificação | Resultado |
| --- | --- |
| Cadastro, consulta, edição, conclusão, reabertura e exclusão | Aprovado |
| Persistência no SQLite | Aprovado |
| Rejeição de dados inválidos (HTTP 400) e tarefa inexistente (HTTP 404) | Aprovado |
| Testes automatizados | 4 de 4 aprovados (`evidencias/testes_2026-11-08.txt`) |
| Uso pela interface e pela rede | 6 problemas encontrados (ocorrências 03 a 08) nos testes de João Felipe, Kawan, Maria Julia e Arthur; Cesar não encontrou erros nas funções que testou |

## 3. Ocorrências e correções

### Corrigidas durante o desenvolvimento da versão 1.0

| Nº | Problema | Correção | Evidência |
| --- | --- | --- | --- |
| 01 | Conexão SQLite não era fechada (`ResourceWarning: unclosed database`). | A função `connect` confirma ou desfaz a transação e fecha a conexão em `finally`. | `evidencias/ocorrencia_01.txt`, `evidencias/testes_2026-11-08.txt` |
| 02 | A aplicação abria sem nenhum registro, dificultando a demonstração. | Plano inicial com dez tarefas da PIT, criado apenas em banco novo. | `evidencias/plano_pit_2026-11-08.txt` |

### Encontradas na versão 1.0 e corrigidas na versão 2.0

| Nº | Problema (versão 1.0) | Relatado por | Severidade | Correção (versão 2.0) | Onde no código |
| --- | --- | --- | --- | --- | --- |
| 03 | Ao clicar fora do formulário ou apertar Esc, a janela fechava e **o texto digitado era perdido** sem aviso. | João Felipe Santos da Silva | Média | O formulário guarda uma "foto" dos campos ao abrir; se algo mudou, pergunta "Descartar as alterações que ainda não foram salvas?". Clicar e arrastar a seleção de texto para fora também não fecha mais a janela. | `app.js`: `hasUnsavedChanges`, `closeForm`, eventos `pointerdown` e `cancel` |
| 04 | Com o servidor desligado, a mensagem era **"Failed to fetch"**, técnica e em inglês. | Arthur Sestrem | Baixa | `api()` captura a falha de conexão e mostra: "Sem conexão com o servidor. Verifique se a Agenda Acadêmica está em execução e tente novamente." | `app.js`: `api`, `OFFLINE_MESSAGE` |
| 05 | Com o formulário aberto, as mensagens de erro apareciam **atrás do fundo escurecido** e ficavam ilegíveis (ex.: título só com espaços). | Arthur Sestrem | Média | Os erros passaram a ser mostrados dentro do próprio formulário, em destaque. | `index.html`: `#form-error`; `app.js`: `showFormError` |
| 06 | Datas de entrega no passado eram aceitas **sem nenhum aviso**. | Kawan Schultz Bueno | Baixa | Ao salvar uma tarefa pendente com data passada, o sistema pede confirmação. | `app.js`: evento `submit` do formulário |
| 07 | O servidor aceitava conexões **somente do próprio computador** (`127.0.0.1` fixo): não abria no celular nem podia ser publicado. | Maria Julia Collodel e Silva | Alta | Variável `HOST` (`0.0.0.0` libera a rede), aviso no terminal com o endereço para o celular e `render.yaml` para hospedagem. | `app.py`: `main`, `local_network_address`; `render.yaml` |
| 08 | Ao abrir a aplicação com ela já aberta (porta 8000 ocupada), o terminal mostrava um **traceback do Python** (`OSError: [Errno 48] Address already in use`). | Arthur Sestrem | Baixa | `create_server` trata o erro e orienta: "A porta 8000 já está em uso... PORT=8001 python3 app.py". `PORT` inválida também tem mensagem própria. | `app.py`: `create_server`, `main` |

### Encontrada na publicação da versão 2.0 e corrigida na versão 2.1

| Nº | Problema | Encontrado em | Severidade | Correção (versão 2.1) | Onde no código |
| --- | --- | --- | --- | --- | --- |
| 09 | Publicada no Render, a agenda ficou **aberta para qualquer pessoa com o link**, que podia ver e alterar a mesma lista. | Publicação (Render) | Alta | Com `AGENDA_SENHA` definida, todas as páginas e a API pedem usuário e senha (HTTP 401 sem credenciais); `/health` continua aberta para a hospedagem. Execução local sem mudança. | `app.py`: `authorized`, `login_required`, `main` |

Evidência: `evidencias/v2.1_senha_2026-11-16.txt` e `evidencias/testes_v2.1_2026-11-16.txt` (15 de 15 testes aprovados). Na mesma publicação também foram ajustados a mensagem do terminal, que mostrava endereços internos do servidor, o suporte a requisições HEAD (antes, erro 501) e o registro do motivo de logins recusados, que facilitou conferir a senha cadastrada no painel.

## 4. Melhorias incluídas na versão 2.0

| Melhoria | Motivo |
| --- | --- |
| Busca por título, disciplina ou observação, sem diferenciar acentos | Falta apontada por João Felipe: não havia como procurar uma tarefa. |
| Prioridade baixa, média ou alta | Falta apontada por João Felipe: tarefas com o mesmo prazo não tinham como ser diferenciadas. |
| Filtro e contador de atrasadas | Falta apontada por Kawan: as atrasadas só eram identificadas lendo item por item. |
| Prazo relativo ("Vence hoje", "Faltam 3 dias") | Era preciso comparar mentalmente a data com o dia de hoje. |
| Ordenação por prazo, prioridade ou disciplina | Falta apontada por Cesar: a ordem era fixa. |
| Exportar planilha (CSV para Excel) | Falta apontada por Cesar: não havia como levar a lista para fora do sistema. |
| Sugestão de disciplinas e contador de caracteres | Evita a mesma disciplina escrita de formas diferentes e mostra o limite de 500 caracteres. |

A prioridade exigiu uma nova coluna no banco. A função `migrate` adiciona a coluna em bancos criados pela versão 1.0, mantendo as tarefas existentes com prioridade média (`evidencias/v2_rede_e_porta_2026-11-16.txt`, item 3).

## 5. Reteste na versão 2.0

| Verificação | Resultado | Evidência |
| --- | --- | --- |
| Testes automatizados | **9 de 9 aprovados** (eram 4; novos: prioridade, ordenação, exportação CSV, migração do banco 1.0 e porta ocupada) | `evidencias/testes_v2_2026-11-16.txt` |
| Ocorrências 03, 04, 05 e 06 na interface | Corrigidas | `evidencias/v2_interface_2026-11-16.txt`, `capturas/v2_formulario.png`, `capturas/v2_erro_servidor_desligado.png` |
| Ocorrências 07 e 08 | Corrigidas | `evidencias/v2_rede_e_porta_2026-11-16.txt` |
| Busca, filtro de atrasadas, ordenação e exportação | Funcionando | `evidencias/v2_interface_2026-11-16.txt`, `capturas/v2_busca.png` |
| Layout no celular (390 px) | Sem rolagem horizontal | `capturas/v2_celular.png` |
| Sintaxe | Aprovado | `evidencias/sintaxe_v2_2026-11-16.txt` |

Comando dos testes: `python3 -W error::ResourceWarning -m unittest discover -s tests -v` (dentro de `versao-2`).

## 6. Versão 2.2 — cores por prazo (sugestão de Cesar Alexandrini)

No teste da versão 1.0, Cesar sugeriu marcar cada tarefa com uma cor conforme o tempo que falta: verde com folga, amarelo a 6 horas, laranja a 1 hora e vermelho quando o prazo chega. Como a tarefa só guardava a data, a contagem em horas exigiu um **horário de entrega** opcional.

| Item | Como ficou | Onde no código |
| --- | --- | --- |
| Horário de entrega | Campo opcional no formulário; sem horário, o prazo vale até 23:59 do dia. O servidor aceita só `HH:MM` (24 h) ou vazio. | `index.html`: `#due-time`; `app.py`: `validate_task` |
| Cores | Verde: mais de 6 horas; amarelo: menos de 6 horas; laranja: menos de 1 hora; vermelho: prazo encerrado. Tarefas concluídas ficam sem cor. A legenda aparece acima da lista. | `app.js`: `deadline`, `urgency`; `styles.css` |
| Texto do prazo | Na reta final mostra o tempo restante ("Faltam 35 min · até 13:31") e, depois do horário, "Prazo encerrado hoje às 10:56". | `app.js`: `dueInfo`, `timeLeft` |
| Atualização | A lista é redesenhada a cada minuto, então a cor muda sem recarregar a página. | `app.js`: `setInterval` |
| Atrasadas e ordenação | Passam a considerar data **e** horário; no mesmo dia, a tarefa com horário mais cedo vem antes. | `app.js`: `isOverdue`, `compareTasks`; `app.py`: `ORDER_BY` |
| Banco | Nova coluna `due_time`. A função `migrate` a adiciona em bancos das versões 1.0 e 2.1, sem perder tarefas. | `app.py`: `migrate` |
| Planilha | Nova coluna "Horário". | `app.py`: `tasks_to_csv` |

| Reteste (17/11/2026) | Resultado | Evidência |
| --- | --- | --- |
| Testes automatizados | **18 de 18 aprovados** (novos: horário válido e inválido, ordenação por horário, migração do banco 2.1) | `evidencias/testes_v2.2_2026-11-17.txt` |
| Cores no navegador (tarefas com prazo em −2 h, +35 min, +3 h e +3 dias) | Vermelho, laranja, amarelo e verde, na ordem certa | `evidencias/v2.2_interface_2026-11-17.txt`, `capturas/v2.2_cores_prazo.png` |
| Horário já passado ao salvar | Pede confirmação, como a data passada | `evidencias/v2.2_interface_2026-11-17.txt` |
| Mudar só o horário e clicar fora | Pergunta antes de descartar (a correção da ocorrência 03 continua valendo) | `capturas/v2.2_formulario_horario.png` |
| Celular (390 px) | Data, horário e prioridade empilhados; sem rolagem horizontal | `evidencias/v2.2_interface_2026-11-17.txt` |

## 7. Evidências

| Arquivo | Conteúdo |
| --- | --- |
| `evidencias/sessoes_teste_v1_2026-11-16.txt` | Roteiros executados pelo desenvolvedor na versão 1.0, nas mesmas cinco áreas dos testes com os colegas. |
| `evidencias/v1_interface_2026-11-16.txt` | Ocorrências 03, 04 e 06 reproduzidas na versão 1.0. |
| `evidencias/v1_rede_e_porta_2026-11-16.txt` | Ocorrências 07 e 08 reproduzidas na versão 1.0. |
| `capturas/v1_tela_inicial.png` | Tela da versão 1.0. |
| `capturas/v1_celular.png` | Versão 1.0 em tela de celular (área do teste de Maria Julia). |
| `capturas/v1_erro_titulo_espacos.png` | Mensagem de erro do título atrás do fundo escuro (ocorrência 05, relatada por Arthur). |
| `capturas/v1_erro_servidor_desligado.png` | Mensagem "Failed to fetch" atrás do fundo escuro (ocorrências 04 e 05). |
| `capturas/v2_tela_inicial.png` | Tela da versão 2.0 com prioridade, atrasadas e prazo relativo. |
| `capturas/v2_busca.png` | Busca "calculo" encontrando tarefas de "Cálculo I". |
| `capturas/v2_formulario.png` | Formulário mantido aberto após clicar fora (ocorrência 03). |
| `capturas/v2_erro_servidor_desligado.png` | Mensagem em português dentro do formulário (ocorrências 04 e 05). |
| `capturas/v2_celular.png` | Versão 2.0 no celular. |
| `capturas/v2.2_cores_prazo.png` | Versão 2.2: tarefas em vermelho, laranja, amarelo e verde, com a legenda. |
| `capturas/v2.2_formulario_horario.png` | Versão 2.2: formulário com o campo de horário. |

## 8. Limitações conhecidas

- A senha da versão publicada é uma só, compartilhada por quem tem acesso: todos com a senha veem a mesma lista. Não há contas individuais.
- No plano gratuito do Render o disco é temporário; quando o serviço reinicia, o banco volta ao plano inicial.
- A data e a hora de "agora" são as do aparelho; um relógio errado altera as cores e o cálculo de atrasadas.
