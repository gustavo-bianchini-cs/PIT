# Laudo de qualidade — Agenda Acadêmica

**Responsável:** Gustavo Emanoel Bianchini — RGM 33636541
**Versões avaliadas:** 1.0 (pasta `versao-1`), 2.0 e 2.1 (pasta `versao-2`)
**Datas das verificações:** 08/11/2026 (versão 1.0) e 16/11/2026 (versão 1.0 e reteste na versão 2.0)
**Ambiente:** macOS, Python 3.13, SQLite integrado ao Python, Google Chrome (computador 1366×900 e celular 390×844), Node.js para verificação de sintaxe.

## 1. Metodologia

1. **Testes automatizados de integração** (`unittest`): sobem o servidor com um banco temporário e chamam a API como o navegador faria.
2. **Roteiro de uso na interface:** cadastro, edição, conclusão, exclusão, filtros, fechamento do formulário, datas no passado e servidor desligado, executados no Google Chrome com registro do que aparece na tela.
3. **Verificação de rede e inicialização:** acesso pelo IP do computador na rede Wi-Fi (como um celular faria) e execução com a porta já ocupada.
4. **Sessões de teste de uso (usuários fictícios 1 a 5):** cinco sessões na versão 1.0, cada uma em uma área (cadastro e formulário; edição e prazos; filtros, exclusão e dados salvos; celular e rede; mensagens de erro). Registro em `evidencias/sessoes_teste_v1_2026-11-16.txt` e no formulário da atividade (seção "Testes da Solução").

Cada problema recebeu uma severidade: **alta** (impede o uso ou a publicação), **média** (pode causar perda de dados ou confusão) ou **baixa** (incômodo, com contorno simples).

## 2. Resultado da versão 1.0

| Verificação | Resultado |
| --- | --- |
| Cadastro, consulta, edição, conclusão, reabertura e exclusão | Aprovado |
| Persistência no SQLite | Aprovado |
| Rejeição de dados inválidos (HTTP 400) e tarefa inexistente (HTTP 404) | Aprovado |
| Testes automatizados | 4 de 4 aprovados (`evidencias/testes_2026-11-08.txt`) |
| Uso pela interface e pela rede | 6 problemas encontrados (ocorrências 03 a 08) nas sessões dos usuários fictícios 1, 2, 4 e 5; a sessão 3 não encontrou erros |

## 3. Ocorrências e correções

### Corrigidas durante o desenvolvimento da versão 1.0

| Nº | Problema | Correção | Evidência |
| --- | --- | --- | --- |
| 01 | Conexão SQLite não era fechada (`ResourceWarning: unclosed database`). | A função `connect` confirma ou desfaz a transação e fecha a conexão em `finally`. | `evidencias/ocorrencia_01.txt`, `evidencias/testes_2026-11-08.txt` |
| 02 | A aplicação abria sem nenhum registro, dificultando a demonstração. | Plano inicial com dez tarefas da PIT, criado apenas em banco novo. | `evidencias/plano_pit_2026-11-08.txt` |

### Encontradas na versão 1.0 e corrigidas na versão 2.0

| Nº | Problema (versão 1.0) | Encontrado por | Severidade | Correção (versão 2.0) | Onde no código |
| --- | --- | --- | --- | --- | --- |
| 03 | Ao clicar fora do formulário ou apertar Esc, a janela fechava e **o texto digitado era perdido** sem aviso. | Usuário fictício 1 | Média | O formulário guarda uma "foto" dos campos ao abrir; se algo mudou, pergunta "Descartar as alterações que ainda não foram salvas?". Clicar e arrastar a seleção de texto para fora também não fecha mais a janela. | `app.js`: `hasUnsavedChanges`, `closeForm`, eventos `pointerdown` e `cancel` |
| 04 | Com o servidor desligado, a mensagem era **"Failed to fetch"**, técnica e em inglês. | Usuário fictício 5 | Baixa | `api()` captura a falha de conexão e mostra: "Sem conexão com o servidor. Verifique se a Agenda Acadêmica está em execução e tente novamente." | `app.js`: `api`, `OFFLINE_MESSAGE` |
| 05 | Com o formulário aberto, as mensagens de erro apareciam **atrás do fundo escurecido** e ficavam ilegíveis (ex.: título só com espaços). | Usuário fictício 5 | Média | Os erros passaram a ser mostrados dentro do próprio formulário, em destaque. | `index.html`: `#form-error`; `app.js`: `showFormError` |
| 06 | Datas de entrega no passado eram aceitas **sem nenhum aviso**. | Usuário fictício 2 | Baixa | Ao salvar uma tarefa pendente com data passada, o sistema pede confirmação. | `app.js`: evento `submit` do formulário |
| 07 | O servidor aceitava conexões **somente do próprio computador** (`127.0.0.1` fixo): não abria no celular nem podia ser publicado. | Usuário fictício 4 | Alta | Variável `HOST` (`0.0.0.0` libera a rede), aviso no terminal com o endereço para o celular e `render.yaml` para hospedagem. | `app.py`: `main`, `local_network_address`; `render.yaml` |
| 08 | Com a porta 8000 ocupada, o terminal mostrava um **traceback do Python** (`OSError: [Errno 48] Address already in use`). | Usuário fictício 5 | Baixa | `create_server` trata o erro e orienta: "A porta 8000 já está em uso... PORT=8001 python3 app.py". `PORT` inválida também tem mensagem própria. | `app.py`: `create_server`, `main` |

### Encontrada na publicação da versão 2.0 e corrigida na versão 2.1

| Nº | Problema | Encontrado em | Severidade | Correção (versão 2.1) | Onde no código |
| --- | --- | --- | --- | --- | --- |
| 09 | Publicada no Render, a agenda ficou **aberta para qualquer pessoa com o link**, que podia ver e alterar a mesma lista. | Publicação (Render) | Alta | Com `AGENDA_SENHA` definida, todas as páginas e a API pedem usuário e senha (HTTP 401 sem credenciais); `/health` continua aberta para a hospedagem. Execução local sem mudança. | `app.py`: `authorized`, `login_required`, `main` |

Evidência: `evidencias/v2.1_senha_2026-11-16.txt` e `evidencias/testes_v2.1_2026-11-16.txt` (14 de 14 testes aprovados). Na mesma publicação também foram ajustados a mensagem do terminal, que mostrava endereços internos do servidor, e o suporte a requisições HEAD (antes, erro 501).

## 4. Melhorias incluídas na versão 2.0

| Melhoria | Motivo |
| --- | --- |
| Busca por título, disciplina ou observação, sem diferenciar acentos | Falta apontada pelo usuário fictício 1: não havia como procurar uma tarefa. |
| Prioridade baixa, média ou alta | Falta apontada pelo usuário fictício 1: tarefas com o mesmo prazo não tinham como ser diferenciadas. |
| Filtro e contador de atrasadas | Falta apontada pelo usuário fictício 2: as atrasadas só eram identificadas lendo item por item. |
| Prazo relativo ("Vence hoje", "Faltam 3 dias") | Era preciso comparar mentalmente a data com o dia de hoje. |
| Ordenação por prazo, prioridade ou disciplina | Falta apontada pelo usuário fictício 3: a ordem era fixa. |
| Exportar planilha (CSV para Excel) | Falta apontada pelo usuário fictício 3: não havia como levar a lista para fora do sistema. |
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

## 6. Evidências

| Arquivo | Conteúdo |
| --- | --- |
| `evidencias/sessoes_teste_v1_2026-11-16.txt` | Registro das cinco sessões de teste da versão 1.0 (usuários fictícios 1 a 5). |
| `evidencias/v1_interface_2026-11-16.txt` | Ocorrências 03, 04 e 06 reproduzidas na versão 1.0. |
| `evidencias/v1_rede_e_porta_2026-11-16.txt` | Ocorrências 07 e 08 reproduzidas na versão 1.0. |
| `capturas/v1_tela_inicial.png` | Tela da versão 1.0. |
| `capturas/v1_celular.png` | Versão 1.0 em tela de celular (sessão do usuário fictício 4). |
| `capturas/v1_erro_titulo_espacos.png` | Mensagem de erro do título atrás do fundo escuro (sessão do usuário fictício 5, ocorrência 05). |
| `capturas/v1_erro_servidor_desligado.png` | Mensagem "Failed to fetch" atrás do fundo escuro (ocorrências 04 e 05). |
| `capturas/v2_tela_inicial.png` | Tela da versão 2.0 com prioridade, atrasadas e prazo relativo. |
| `capturas/v2_busca.png` | Busca "calculo" encontrando tarefas de "Cálculo I". |
| `capturas/v2_formulario.png` | Formulário mantido aberto após clicar fora (ocorrência 03). |
| `capturas/v2_erro_servidor_desligado.png` | Mensagem em português dentro do formulário (ocorrências 04 e 05). |
| `capturas/v2_celular.png` | Versão 2.0 no celular. |

## 7. Limitações conhecidas

- A senha da versão publicada é uma só, compartilhada por quem tem acesso: todos com a senha veem a mesma lista. Não há contas individuais.
- No plano gratuito do Render o disco é temporário; quando o serviço reinicia, o banco volta ao plano inicial.
- A data de "hoje" é a do navegador; um relógio errado no aparelho altera o cálculo de atrasadas.
