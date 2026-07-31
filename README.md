# Processamento batch de clubes

[![CI](https://github.com/Ernanidacosta/desafio-big-data/actions/workflows/ci.yml/badge.svg)](https://github.com/Ernanidacosta/desafio-big-data/actions/workflows/ci.yml)

## Objetivo

Ler um arquivo JSONL de clubes e gerar dois CSVs normalizados — um de
clubes e um de jogadores — aplicando o filtro de campeonato (Série A e
Série B) e tratando dados ausentes ou inválidos por registro.

## Requisitos

- Python 3.9+ (apenas biblioteca padrão).
- Dependências de desenvolvimento fixadas em `requirements-dev.txt`.

A CI verifica Python 3.9, 3.12 e 3.14.

Para preparar as ferramentas locais:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

## Como executar

```bash
python3 main.py <entrada.jsonl>
```

Exemplo:

```bash
python3 main.py sample_clubes.jsonl
```

### --output-dir

Diretório onde os arquivos gerados são gravados. Padrão: diretório atual.
É criado se não existir.

```bash
python3 main.py sample_clubes.jsonl --output-dir out
```

## Arquivos gerados

Gravados no diretório de saída:

- `clubs.csv` — um clube por linha.
  Cabeçalho: `Id do Clube, Nome, Campeonato, Data de Fundação, Cidade,
  Estado, País, Estádio, Presidente, Apelido, Cores`.
- `players.csv` — um jogador por linha, ligado ao clube por `Id do Clube`.
  Cabeçalho: `Id do Clube, Id do Jogador, Nome, Idade, Gols,
  Data de Estreia, Posição, Número da Camisa`.
- `processing.log` — log da execução (também impresso no terminal).

## Estratégia de streaming

A entrada é JSONL estrito: exatamente um objeto JSON por linha. O arquivo
é lido linha a linha (`json.loads` por linha), mantendo apenas um registro
em memória por vez. Não há recuperação de objetos distribuídos em várias
linhas, o que mantém o leitor simples e permite processar arquivos grandes
sem carregá-los inteiros.

Os CSVs são escritos com `csv.DictWriter`, que cuida do escapamento de
vírgulas e aspas nos valores.

## Tratamento de dados inválidos

A recuperação é por registro; um problema em um registro não interrompe os
demais.

- Linha vazia: ignorada.
- Linha com byte UTF-8 inválido: descartada, com WARNING e contador no resumo.
- JSON inválido: descarta apenas aquela linha.
- Constante fora do padrão JSON, como `NaN`: descarta apenas aquela linha.
- JSON válido que não seja objeto: descarta apenas aquela linha.
- Clube de campeonato fora de Série A/B: ignorado (clube e jogadores).
- Campo ausente ou nulo: vira vazio (zeros são preservados).
- Data fora do formato literal `YYYY-MM-DD` ou calendário inválido: campo
  vazio, sem descartar o registro.
- `colors` não é lista: vira vazio.
- `players` não é lista: o clube permanece, sem jogadores.
- Item de `players` que não seja objeto: apenas o item é ignorado.
- Valor Unicode que não possa ser codificado em UTF-8: descarta apenas o
  clube ou jogador afetado.

`club_id` e `player_id` não são obrigatórios — se ausentes, ficam vazios.

Os CSVs são construídos em um diretório temporário dentro da saída e
substituem os resultados anteriores somente depois que o processamento
termina com sucesso.

## Logging

Log simultâneo no terminal e em `processing.log`, formato
`data | nível | mensagem`. Registra início e fim da execução, caminhos de
entrada e saída, WARNING para dados inválidos, INFO para clubes ignorados
por campeonato, progresso a cada 100 mil linhas e um resumo final com os
contadores, incluindo a quantidade de bytes UTF-8 inválidos. Registros
exportados não são logados individualmente.

## Testes

```bash
.venv/bin/pytest -q
```

Sem dependências externas:

```bash
python3 -m unittest discover -s tests -q
```

Os testes cobrem o comportamento observável pela interface pública
(processar um JSONL e inspecionar os CSVs): datas válidas/inválidas,
nulos e zeros, junção de `colors`, filtro de campeonato, isolamento de
JSON malformado, clube sem jogadores, `players`/itens inválidos, ordem
dos cabeçalhos, escapamento de CSV, UTF-8 inválido, inteiros JSON excessivos,
constantes fora do padrão JSON e Unicode não codificável.

## Biblioteca padrão

O projeto usa apenas a biblioteca padrão do Python (`json`, `csv`,
`argparse`, `logging`, `pathlib`, `datetime`, `re`, `tempfile`,
`unicodedata`). O volume de dados e as transformações não justificam
dependências externas como pandas; isso mantém o setup trivial e a execução
portável.
