# Automação de Relatório de Horas

Aplicação web local que converte o export de horas do **Projectile** (`.xlsx`) no
relatório final de horas da empresa, já formatado — mesma logo, mesmas caixas de
assinatura, mesmas fórmulas — sem precisar montar isso manualmente todo mês.

Fluxo: **importar o export do Projectile → revisar/editar os dados → gerar o
relatório final em `.xlsx`**.

## O que o app faz

- Lê o `.xlsx` exportado do Projectile e agrupa as linhas por atividade
  (a partir da coluna `Observação`, no formato `Prefixo-Descrição do trabalho` ou
  `Prefixo_Descrição do trabalho`).
- Mostra os dados extraídos numa tela de revisão, onde é possível editar horas,
  performance, nome do arquivo etc. antes de gerar o relatório.
- Gera o `.xlsx` final preservando 100% do layout do template original (logo,
  caixas de assinatura, fórmulas de soma/performance) — o arquivo não é recriado
  do zero, apenas os dados são injetados nele.
- Sinaliza, num banner de aviso (não bloqueia a geração), linhas do export que
  parecem um apontamento incompleto ou mal formatado, para corrigir na origem.
- Calcula automaticamente a tabela auxiliar "Week/AK/Days/Hours per week" do
  relatório: dias úteis por semana do mês do relatório, descontando feriados
  nacionais (fixos e móveis — Carnaval, Sexta-feira Santa, Corpus Christi etc.).

### Dois modos de geração

- **Relatório único**: todas as linhas do export viram um único `.xlsx`.
- **Múltiplos relatórios**: um `.xlsx` separado por *Pacote de Trabalho*
  (identificado a partir do 2º segmento do texto, ex: em
  `"1546.6.4-002 Legislation Package - Sangam - Cabina Bruta - resto"` o pacote
  é **Sangam**). Nesse modo o download vem como um `.zip` com um relatório por
  pacote.

## Formato esperado do export do Projectile

A planilha precisa ter, entre outras, as colunas `Hs` e `Observação`
(o cabeçalho pode estar em qualquer linha — o parser procura a linha que começa
com `Dados, Horário, Hs`). Colunas usadas:

| Coluna              | Uso                                                              |
|---------------------|-------------------------------------------------------------------|
| `Dados`              | data do apontamento (usada só para diferenciar apontamento real de linha de subtotal) |
| `Hs`                 | horas do apontamento (aceita `,` ou `.` como separador decimal)  |
| `Observação`         | `Prefixo-Descrição` ou `Prefixo_Descrição` — o prefixo antes do `-`/`_` agrupa as linhas |
| `Projeto`            | nome do projeto (modo relatório único)                           |
| `Pacote de Trabalho` | usado para separar por projeto no modo múltiplos relatórios      |

## Rodando localmente

Requer Python 3.11+.

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8010
```

Depois abra `http://localhost:8010` no navegador.

## Estrutura do projeto

```
app/
  main.py       # API FastAPI (/parse, /generate) + serve o front-end estático
  parser.py     # lê o export do Projectile e agrupa em pacotes/grupos/atividades
  generator.py  # gera o .xlsx final editando o XML da planilha diretamente
web/
  index.html    # tela única (upload → revisão → geração)
  app.js        # toda a lógica do front-end (sem framework, sem build)
templates/
  relatorio_final_template.xlsx  # template oficial usado como base do relatório gerado
```

> `templates/exemplo_projectile.xlsx` (export real usado como referência durante o
> desenvolvimento) fica de fora do repositório — contém dados reais de colaboradores
> e de projeto do cliente. Fica só localmente, listado no `.gitignore`.

## Detalhe técnico: por que `generator.py` não usa `openpyxl.save()`

O `openpyxl` descarta desenhos (logo, caixas de assinatura) ao salvar um
arquivo. Para preservar o template original 100% intacto, `generator.py` copia
o `.xlsx` byte-a-byte e substitui apenas o XML da planilha de dados
(`xl/worksheets/sheet1.xml`), mantendo `xl/drawings`, `xl/media` e todo o resto
do arquivo sem alteração.
