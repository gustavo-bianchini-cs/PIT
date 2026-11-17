# Agenda Acadêmica

Aplicação web para estudantes organizarem trabalhos, provas e atividades de diferentes disciplinas em uma única lista, acompanhando prazos, prioridades e o que já foi concluído.

Projeto desenvolvido para a PIT — Projeto Integrador Transdisciplinar.
**Autor:** Gustavo Emanoel Bianchini — RGM 33636541

## Tecnologias

| Camada | Tecnologia |
| --- | --- |
| Back-end | Python 3 (biblioteca padrão, `http.server`) |
| Banco de dados | SQLite |
| Front-end | HTML, CSS e JavaScript (sem frameworks) |
| Plataforma | Web, responsiva (computador e celular) |
| Hospedagem | Render, com acesso por usuário e senha (`render.yaml`), ou execução local |
| Modo de codificação | Tradicional |

## Estrutura do repositório

```
versao-1/      primeira versão (v1.0)
versao-2/      versão atual, com melhorias e correções (v2.0, v2.1 e v2.2)
docs/          documentação, laudo de qualidade e evidências
CHANGELOG.md   o que mudou em cada versão
render.yaml    configuração de publicação da versão 2
```

As duas versões são independentes: cada pasta tem seu próprio servidor, banco de dados e testes.

## Executar

```bash
cd versao-2          # ou versao-1
python3 app.py
```

Depois, acesse `http://127.0.0.1:8000`. Não é preciso instalar pacotes (Python 3.10 ou superior).

## Testar

```bash
cd versao-2
python3 -W error::ResourceWarning -m unittest discover -s tests -v
```

## Documentação

- [Documentação do projeto](docs/DOCUMENTACAO_PROJETO.md)
- [Laudo de qualidade](docs/LAUDO_QUALIDADE.md)
- [Histórico de versões](CHANGELOG.md)
