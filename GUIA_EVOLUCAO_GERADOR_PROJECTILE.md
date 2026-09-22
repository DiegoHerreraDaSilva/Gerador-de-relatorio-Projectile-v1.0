# Guia de Evolução — Gerador de Relatórios Projectile v1.0

## 1. Objetivo deste documento

Este documento é o guia técnico para evoluir o projeto `Gerador-de-relatorio-projectile-v1.0` de uma aplicação funcional de geração de relatórios para uma plataforma mais robusta, auditável, escalável e preparada para análises históricas.

A evolução está dividida em dois grandes eixos:

1. **Refatoração e fortalecimento da aplicação atual**
   - separação de responsabilidades;
   - melhoria do acesso ao MySQL do Projectile;
   - validação de upload;
   - fortalecimento do gerador XLSX;
   - redução de acoplamento do chatbot/IA;
   - IDs estáveis;
   - auditoria;
   - testes de contrato/regressão;
   - melhorias de configuração, segurança e observabilidade.

2. **Criação de um segundo MySQL independente do Projectile**
   - armazenamento dos relatórios gerados;
   - versionamento;
   - snapshots imutáveis dos dados usados na geração;
   - histórico completo;
   - auditoria;
   - rastreabilidade de arquivos XLSX/PDF;
   - base para analytics e indicadores futuros.

A regra central da arquitetura proposta é:

```text
                         ┌─────────────────────┐
                         │      Frontend       │
                         │ React + TypeScript  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │       FastAPI       │
                         │ API / Services      │
                         └───────┬─────┬───────┘
                                 │     │
                   leitura       │     │ escrita
                                 │     │
                                 ▼     ▼
                    ┌──────────────┐  ┌─────────────────┐
                    │   Projectile │  │ Reports MySQL   │
                    │    MySQL     │  │ Histórico       │
                    │ fonte externa│  │ e analytics     │
                    └──────────────┘  └─────────────────┘
```

O banco do Projectile continua sendo tratado como **fonte operacional de origem**. O novo banco passa a ser o **sistema histórico da aplicação**.

---

# 2. Estado-alvo da aplicação

A aplicação deve evoluir para o seguinte fluxo:

```text
Projectile
   │
   │ consulta
   ▼
Ingestion / Repository
   │
   ▼
Normalização
   │
   ▼
Snapshot imutável
   │
   ├───────────────┐
   ▼               ▼
Report            Report Version
   │               │
   └───────┬───────┘
           ▼
      Generation
           │
      ┌────┴────┐
      ▼         ▼
    XLSX       PDF
      │         │
      └────┬────┘
           ▼
       Histórico
           │
           ▼
        Analytics
```

A aplicação não deve depender do estado atual do Projectile para reconstruir um relatório antigo.

Exemplo:

```text
10/09
Projectile:
Projeto A = 10h

         ↓ geração

Relatório v1:
Projeto A = 10h


12/09
Projectile:
Projeto A = 14h

         ↓ nova geração

Relatório v2:
Projeto A = 14h
```

O relatório de 10/09 continua mostrando 10h.

Isso só é possível se a aplicação armazenar o **snapshot utilizado naquela geração**.

---

# 3. Princípios arquiteturais

## 3.1. Separação dos bancos

Nunca transformar o banco histórico em uma extensão direta do banco do Projectile.

Evitar:

```text
Reports DB
   ↓
JOIN
   ↓
Projectile DB
```

Preferir:

```text
Projectile DB
   ↓
FastAPI
   ↓
normalização/snapshot
   ↓
Reports DB
```

Benefícios:

- menor acoplamento;
- histórico independente;
- possibilidade de trocar o sistema fonte;
- maior controle de performance;
- auditoria determinística;
- recuperação do relatório mesmo quando o Projectile estiver indisponível.

---

## 3.2. Backend como camada de integração

O frontend não deve conhecer:

- credenciais MySQL;
- estrutura interna do Projectile;
- estrutura interna do banco histórico;
- detalhes do XLSX;
- regras de persistência;
- regras de auditoria;
- lógica da IA.

O fluxo deve ser:

```text
React
  ↓
API
  ↓
Service
  ↓
Repository
  ↓
Database
```

---

## 3.3. Serviços devem representar regras de negócio

Evitar concentrar toda a aplicação em:

- `main.py`;
- `useReportStore.ts`;
- endpoints gigantes;
- funções utilitárias que conhecem tudo.

Uma função HTTP deve principalmente:

1. validar entrada;
2. chamar o serviço;
3. retornar resposta.

---

# 4. Refatoração do backend

## 4.1. Problema atual

O `main.py` cresceu muito e concentra responsabilidades diferentes.

Entre elas:

- endpoints;
- autenticação;
- upload;
- consultas ao Projectile;
- geração;
- gerenciamento;
- histórico;
- tratamento de erros;
- integração com IA.

Isso aumenta o custo de manutenção e o risco de regressões.

---

# 5. Estrutura de diretórios recomendada

Uma estrutura possível:

```text
backend/
├── app/
│   ├── main.py
│   │
│   ├── api/
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── reports.py
│   │   │   ├── projectile.py
│   │   │   ├── management.py
│   │   │   ├── history.py
│   │   │   ├── analytics.py
│   │   │   └── health.py
│   │   │
│   │   └── dependencies.py
│   │
│   ├── services/
│   │   ├── report_service.py
│   │   ├── report_generation_service.py
│   │   ├── projectile_service.py
│   │   ├── snapshot_service.py
│   │   ├── audit_service.py
│   │   ├── management_service.py
│   │   └── analytics_service.py
│   │
│   ├── repositories/
│   │   ├── projectile_repository.py
│   │   ├── report_repository.py
│   │   ├── version_repository.py
│   │   ├── generation_repository.py
│   │   ├── snapshot_repository.py
│   │   └── audit_repository.py
│   │
│   ├── db/
│   │   ├── projectile_db.py
│   │   ├── reports_db.py
│   │   ├── models/
│   │   └── migrations/
│   │
│   ├── schemas/
│   │   ├── report.py
│   │   ├── history.py
│   │   ├── generation.py
│   │   ├── analytics.py
│   │   └── common.py
│   │
│   ├── domain/
│   │   ├── report.py
│   │   ├── snapshot.py
│   │   └── audit.py
│   │
│   ├── integrations/
│   │   ├── projectile/
│   │   └── ai/
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── logging.py
│   │   └── errors.py
│   │
│   └── utils/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── regression/
│
└── alembic.ini
```

Não é necessário fazer toda essa reorganização de uma vez.

O ideal é migrar progressivamente.

---

# 6. Divisão recomendada do `main.py`

## Etapa 1

Criar:

```text
api/routers/
```

e mover os endpoints por domínio:

```text
auth.py
reports.py
projectile.py
management.py
history.py
analytics.py
health.py
```

No `main.py` deve sobrar principalmente:

```python
app = FastAPI()

app.include_router(auth_router)
app.include_router(reports_router)
app.include_router(projectile_router)
app.include_router(management_router)
app.include_router(history_router)
app.include_router(analytics_router)
app.include_router(health_router)
```

---

# 7. Separação Service / Repository

## Repository

Responsável apenas por acesso aos dados.

Exemplo conceitual:

```python
class ReportRepository:
    def create_report(self, report_data):
        ...

    def get_report(self, report_id):
        ...

    def list_reports(self, filters):
        ...
```

## Service

Responsável pelas regras:

```python
class ReportService:
    def create_report_from_projectile(...):
        projectile_data = self.projectile_service.fetch(...)
        snapshot = self.snapshot_service.create(projectile_data)

        report = self.repository.create(...)
        version = self.version_repository.create(...)
        self.snapshot_repository.save(snapshot)

        return report
```

---

# 8. Banco do Projectile

## 8.1. Conexão atual

A conexão persistente protegida por lock solucionou o problema de concorrência que causava erros como:

```text
read of closed file
```

Entretanto, esse desenho pode serializar chamadas ao banco.

Em termos conceituais:

```text
Request A ───────┐
                 │
                 ▼
             [LOCK]
                 │
Projectile DB ◄──┤
                 │
             [UNLOCK]
                 │
Request B ───────┘
```

Isso funciona, mas limita concorrência.

---

# 9. Evolução para pool de conexões

A solução desejada:

```text
             ┌───────────────┐
Request A ──►│               │
Request B ──►│ Connection    │──► Projectile
Request C ──►│ Pool          │
Request D ──►│               │
             └───────────────┘
```

O pool deve:

- abrir algumas conexões;
- reaproveitar conexões;
- detectar conexões inválidas;
- recriar conexões quando necessário;
- limitar o número máximo;
- devolver a conexão ao pool após a operação.

## Ordem de implementação

1. encapsular criação da conexão;
2. criar interface única para aquisição;
3. eliminar uso direto da conexão global;
4. adicionar pool;
5. adicionar testes de concorrência;
6. medir novamente o tempo das queries.

---

# 10. Configuração do `_SYS_CLIENT_ID`

Evitar:

```python
_SYS_CLIENT_ID = "0"
```

Preferir:

```env
PROJECTILE_SYS_CLIENT_ID=0
```

e:

```python
class Settings:
    projectile_sys_client_id: str
```

Também centralizar:

- host;
- port;
- database;
- user;
- timeout;
- pool size;
- SSL;
- reports database;
- paths de arquivos.

---

# 11. Arquivo de configuração

Criar algo semelhante a:

```text
core/config.py
```

Exemplo conceitual:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    projectile_db_host: str
    projectile_db_port: int = 3306
    projectile_db_name: str
    projectile_db_user: str
    projectile_db_password: str
    projectile_sys_client_id: str

    reports_db_host: str
    reports_db_port: int = 3306
    reports_db_name: str
    reports_db_user: str
    reports_db_password: str

    upload_max_bytes: int = 20 * 1024 * 1024

    class Config:
        env_file = ".env"
```

Nunca colocar senha diretamente no código.

---

# 12. Segurança do upload

## Problema

Ler o arquivo inteiro antes de verificar tamanho pode permitir consumo desnecessário de memória.

Evitar:

```python
content = await file.read()

if len(content) > MAX_SIZE:
    ...
```

Preferir:

```text
Request
   ↓
Content-Length / limite de stream
   ↓
leitura em chunks
   ↓
arquivo temporário
   ↓
processamento
```

Além disso:

- limitar tamanho máximo;
- validar extensão;
- validar MIME quando possível;
- não confiar somente na extensão;
- usar diretório temporário;
- remover temporários;
- impedir path traversal;
- gerar nomes internos;
- impedir sobrescrita arbitrária.

---

# 13. Validação de XLSX

O arquivo deve ser validado antes de chegar ao parser.

Verificações:

```text
Arquivo recebido
   ├── tamanho
   ├── extensão
   ├── MIME
   ├── ZIP válido
   ├── estrutura XLSX
   └── workbook esperado
```

Em caso de erro, retornar uma mensagem específica.

Exemplo:

```json
{
  "code": "INVALID_XLSX",
  "message": "O arquivo não possui a estrutura XLSX esperada."
}
```

---

# 14. Parser

O parser deve manter uma responsabilidade muito clara:

```text
XLSX / Projectile
      ↓
estrutura normalizada
```

Modelo:

```text
Package
  └── Group
       └── Activity
            └── Hours
```

O parser não deve:

- gravar banco;
- autenticar usuário;
- gerar PDF;
- controlar UI;
- executar IA.

---

# 15. Contrato interno do parser

Definir DTOs/schema explícitos.

Exemplo:

```python
@dataclass
class Activity:
    id: str
    name: str
    hours: Decimal
```

e:

```python
@dataclass
class Group:
    id: str
    name: str
    activities: list[Activity]
```

Isso evita que mudanças no parser quebrem silenciosamente o restante da aplicação.

---

# 16. Gerador XLSX

O gerador atual utiliza manipulação direta do XML dentro do ZIP do XLSX para preservar:

- drawings;
- imagens;
- mídia;
- estrutura do template;
- formatação específica.

Essa decisão deve ser preservada enquanto o template depender desses elementos.

Não substituir automaticamente por:

```python
openpyxl.save(...)
```

sem testes, pois isso pode alterar ou remover elementos do arquivo original.

---

# 17. Template Contract

Criar um contrato explícito do template.

Documentar:

```text
Nome esperado do arquivo
Sheets obrigatórias
Cells obrigatórias
Ranges
Drawing relationships
Media
Assinaturas
XMLs modificados
Placeholders
```

Exemplo:

```yaml
template:
  file: report_template.xlsx

sheets:
  - name: "Relatório"
    required: true

cells:
  employee_name: "B3"
  competence: "B4"
  total_hours: "F20"
```

---

# 18. Testes de regressão do XLSX

Criar testes que comparem o arquivo gerado com um artefato esperado.

Testar:

- workbook abre normalmente;
- sheets continuam presentes;
- imagens continuam presentes;
- drawings continuam presentes;
- células esperadas foram alteradas;
- conteúdo não relacionado permanece;
- links/relações continuam válidos;
- arquivo final não fica corrompido.

Além disso, manter um:

```text
tests/fixtures/
└── template_reference.xlsx
```

---

# 19. Estratégia de comparação do XLSX

Não comparar apenas bytes do arquivo inteiro, pois ZIP interno pode ter pequenas diferenças.

Comparar estruturalmente:

```text
workbook.xml
worksheets/*.xml
drawings/*
media/*
_rels/*
```

A ideia é validar o que importa para o contrato.

---

# 20. Configuração do gerador

Evitar valores mágicos dentro do código:

```python
SIGNATURE_START_ROW = 35
...
```

Centralizar em configuração de template:

```python
TemplateConfig(
    signature_start_row=35,
    signature_column="B",
    ...
)
```

---

# 21. Dados gerenciados em JSON

O arquivo JSON de management começou a atuar como um pequeno banco de dados.

Antes de migrar imediatamente para outra infraestrutura, melhorar:

- schema;
- versionamento;
- validação;
- locking quando necessário;
- backup;
- testes.

Quando a aplicação precisar de:

- histórico;
- filtros complexos;
- concorrência;
- auditoria;
- relacionamentos;

migrar para o banco histórico.

A nova base pode absorver gradualmente essa responsabilidade.

---

# 22. Chatbot / IA

## Problema

A IA não deve receber estado ilimitado da aplicação.

Riscos:

- payload crescente;
- custo;
- latência;
- contexto inconsistente;
- exposição desnecessária de dados;
- comportamento menos determinístico.

---

# 23. Limitar histórico da IA

Enviar apenas:

- contexto relevante;
- últimas mensagens necessárias;
- estado resumido;
- IDs/objetos realmente utilizados.

Estratégia:

```text
Histórico completo
       ↓
resumo persistente
       ↓
últimas N mensagens
       ↓
estado mínimo necessário
```

---

# 24. Comandos determinísticos

Nem tudo precisa passar pela IA.

Exemplo:

```text
"abrir histórico"
"listar relatórios"
"gerar PDF"
"cancelar"
"voltar"
```

Podem ser tratados diretamente:

```python
if command == "open_history":
    ...
```

A IA deve ser usada quando houver interpretação necessária.

---

# 25. Stable IDs

Evitar operações baseadas somente em:

```text
nome
```

ou:

```text
"Projeto XYZ"
```

Usar IDs estáveis.

Exemplo:

```json
{
  "report_id": "019...",
  "package_id": "019...",
  "activity_id": "019..."
}
```

O nome pode mudar:

```text
"Engenharia"
→
"Engenharia Automotiva"
```

O ID continua igual.

---

# 26. IDs recomendados

Para o banco histórico, usar UUID ou ULID.

ULID é interessante para sistemas em que:

- há muitos registros;
- ordenação temporal importa;
- queremos IDs únicos e ordenáveis.

Exemplo:

```text
01K6...
```

Não usar nomes humanos como chave primária.

---

# 27. Auditoria

Criar uma trilha de auditoria.

Registrar:

```text
quem
quando
o quê
qual entidade
qual operação
antes
depois
origem
```

Exemplo:

```json
{
  "action": "REPORT_UPDATED",
  "entity_type": "report",
  "entity_id": "...",
  "before": {...},
  "after": {...},
  "source": "ui"
}
```

Fontes possíveis:

```text
ui
api
ai
system
import
```

---

# 28. Não sobrescrever histórico

Evitar:

```text
UPDATE relatório
```

como único mecanismo.

Para informações relevantes, usar:

```text
Report
   ├── Version 1
   ├── Version 2
   ├── Version 3
   └── Version N
```

A versão anterior não desaparece.

---

# 29. Segundo MySQL — objetivo

Criar um banco independente:

```text
reports_db
```

Ele será responsável por:

- relatórios;
- versões;
- snapshots;
- gerações;
- arquivos;
- auditoria;
- dados normalizados;
- analytics.

Ele não deve substituir o banco operacional do Projectile.

---

# 30. Criando o segundo banco

Exemplo:

```sql
CREATE DATABASE reports_db
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

Criar usuário separado:

```sql
CREATE USER 'reports_app'@'%' IDENTIFIED BY 'SENHA_FORTE';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX
ON reports_db.*
TO 'reports_app'@'%';
```

As permissões devem ser ajustadas ao ambiente de produção.

---

# 31. Conexão do novo banco

Criar:

```text
db/reports_db.py
```

Não reutilizar a conexão do Projectile.

Conceito:

```python
class ReportsDatabase:
    ...
```

O projeto passa a ter duas dependências explícitas:

```text
ProjectileDatabase
ReportsDatabase
```

---

# 32. Migrations com Alembic

Usar Alembic desde o início.

Fluxo:

```bash
alembic init migrations
```

Depois:

```bash
alembic revision --autogenerate -m "create reports tables"
```

Aplicação:

```bash
alembic upgrade head
```

Rollback:

```bash
alembic downgrade -1
```

Nunca depender de criação manual de tabelas em produção.

---

# 33. Modelo principal do banco

Uma proposta inicial:

```text
reports
report_versions
report_source_snapshots
report_packages
report_groups
report_activities
report_generation
report_artifacts
audit_log
```

Opcionalmente:

```text
employees
clients
projects
```

dependendo do quanto desses dados precisam ser mantidos como dimensões próprias.

---

# 34. Tabela `reports`

Representa o relatório lógico.

Campos sugeridos:

```text
id
employee_id
employee_name_snapshot
competence
status
current_version_id
created_by
created_at
updated_at
```

Exemplo:

```sql
CREATE TABLE reports (
    id CHAR(26) PRIMARY KEY,
    employee_id VARCHAR(100) NULL,
    employee_name_snapshot VARCHAR(255) NOT NULL,
    competence DATE NOT NULL,
    status VARCHAR(30) NOT NULL,
    current_version_id CHAR(26) NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL
);
```

O nome armazenado como snapshot evita depender do estado atual do Projectile para exibir um relatório antigo.

---

# 35. Competência

Definir uma regra única.

Opções:

```text
2026-09-01
```

ou:

```text
2026-09
```

Recomendação de banco:

```text
competence_month DATE
```

normalizando para o primeiro dia do mês.

Exemplo:

```text
2026-09-01
```

---

# 36. Status do relatório

Usar enum lógico:

```text
draft
generated
approved
cancelled
archived
```

Não espalhar strings diferentes no código.

Centralizar constantes.

---

# 37. Tabela `report_versions`

Cada alteração relevante gera uma nova versão.

Campos:

```text
id
report_id
version_number
source_snapshot_id
created_by
created_from
change_summary
state_json
created_at
```

Exemplo:

```sql
CREATE TABLE report_versions (
    id CHAR(26) PRIMARY KEY,
    report_id CHAR(26) NOT NULL,
    version_number INT NOT NULL,
    source_snapshot_id CHAR(26) NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_from VARCHAR(30) NOT NULL,
    change_summary TEXT NULL,
    state_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL,

    UNIQUE (report_id, version_number)
);
```

---

# 38. Por que `state_json`

Mesmo mantendo tabelas normalizadas, o snapshot completo em JSON pode ser útil para:

- reconstruir contexto;
- debugging;
- auditoria;
- exportação;
- reprodução de uma geração.

Mas o JSON não deve substituir completamente as tabelas estruturadas.

A arquitetura pode usar:

```text
Relacional = consulta
JSON       = snapshot/reprodução
```

---

# 39. Tabela `report_source_snapshots`

Essa é uma das tabelas mais importantes do projeto.

Ela registra exatamente os dados recebidos do Projectile.

Campos sugeridos:

```text
id
source_system
source_query
source_filters_json
captured_at
source_reference
data_json
data_hash
schema_version
```

Exemplo:

```sql
CREATE TABLE report_source_snapshots (
    id CHAR(26) PRIMARY KEY,
    source_system VARCHAR(50) NOT NULL,
    source_query TEXT NULL,
    source_filters_json JSON NULL,
    captured_at DATETIME(6) NOT NULL,
    source_reference VARCHAR(255) NULL,
    data_json JSON NOT NULL,
    data_hash CHAR(64) NOT NULL,
    schema_version VARCHAR(30) NOT NULL
);
```

---

# 40. Hash do snapshot

Calcular um hash SHA-256 do conteúdo normalizado.

Exemplo conceitual:

```python
digest = hashlib.sha256(
    canonical_json.encode("utf-8")
).hexdigest()
```

Objetivos:

- detectar alterações;
- comprovar que duas versões possuem o mesmo snapshot;
- evitar armazenamentos duplicados quando desejado;
- facilitar auditoria.

---

# 41. Canonical JSON

O JSON utilizado no hash deve ser determinístico.

Por exemplo:

```python
json.dumps(
    data,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":")
)
```

Assim, mudanças irrelevantes de espaço não alteram o hash.

---

# 42. Dados normalizados do relatório

Criar tabelas:

```text
report_packages
report_groups
report_activities
```

Essas tabelas permitem analytics eficientes.

---

# 43. `report_packages`

Campos:

```text
id
report_version_id
source_id
name
position
created_at
```

---

# 44. `report_groups`

Campos:

```text
id
report_package_id
source_id
name
position
created_at
```

---

# 45. `report_activities`

Campos:

```text
id
report_group_id
source_id
name
hours
position
created_at
```

---

# 46. Versão e relacionamento

A hierarquia recomendada:

```text
Report
  │
  └── Version
        │
        ├── Package
        │      │
        │      └── Group
        │             │
        │             └── Activity
        │
        └── Source Snapshot
```

Dessa forma, a mesma atividade pode existir em versões diferentes sem que uma atualização altere versões antigas.

---

# 47. Histórico de geração

Criar `report_generation`.

Cada tentativa de geração deve ser registrada.

Campos:

```text
id
report_id
report_version_id
requested_by
started_at
finished_at
duration_ms
status
error_code
error_message
```

Status:

```text
started
success
failed
cancelled
```

---

# 48. Artifacts

Separar a execução do arquivo produzido.

Criar:

```text
report_artifacts
```

Campos:

```text
id
generation_id
artifact_type
storage_type
storage_path
file_name
mime_type
file_size
sha256
created_at
```

Tipos:

```text
xlsx
pdf
json
```

Storage:

```text
filesystem
object_storage
database
```

Recomendação:

**não guardar arquivos grandes diretamente em BLOB no MySQL sem necessidade.**

Guardar:

```text
metadados + hash + caminho
```

e deixar o arquivo em storage apropriado.

---

# 49. Exemplo de fluxo de geração

Quando o usuário clicar em:

```text
Gerar relatório
```

Executar:

```text
1. autenticar usuário
2. validar parâmetros
3. consultar Projectile
4. normalizar dados
5. criar snapshot
6. calcular hash
7. criar report
8. criar report_version
9. persistir packages/groups/activities
10. criar generation
11. gerar XLSX
12. validar XLSX
13. salvar artifact
14. finalizar generation
15. registrar audit
16. retornar resultado
```

---

# 50. Transações

O banco histórico deve usar transações cuidadosamente.

Por exemplo:

```text
BEGIN

insert report
insert snapshot
insert version
insert packages
insert groups
insert activities
insert generation

COMMIT
```

A geração do arquivo pode ocorrer fora da mesma transação quando necessário.

Uma estratégia segura:

```text
Transaction A:
  persistir estado + generation=started
  COMMIT

Gerar arquivo

Transaction B:
  generation=success/failed
  salvar artifact
  COMMIT
```

Isso evita manter uma transação aberta durante todo o processamento do XLSX.

---

# 51. Falha durante geração

Exemplo:

```text
generation = started
        ↓
XLSX falha
        ↓
generation = failed
error_message = ...
```

Nunca deixar uma geração "started" para sempre.

Criar rotina de reconciliação para detectar execuções antigas sem conclusão.

---

# 52. Idempotência

O endpoint de geração deve evitar duplicações acidentais.

O usuário pode clicar duas vezes:

```text
Gerar
Gerar
```

sem querer criar duas versões.

Usar um:

```text
idempotency_key
```

por requisição quando fizer sentido.

Exemplo:

```text
POST /reports/{id}/generate
Idempotency-Key: abc123
```

A aplicação registra a chave e a geração correspondente.

---

# 53. APIs de histórico

Criar endpoints semelhantes a:

```text
GET /reports
GET /reports/{report_id}
GET /reports/{report_id}/versions
GET /reports/{report_id}/versions/{version_id}
GET /reports/{report_id}/generations
GET /reports/{report_id}/artifacts
GET /reports/{report_id}/audit
```

Também:

```text
GET /history
```

com filtros.

---

# 54. Filtros de histórico

Começar com:

```text
employee
competence
status
created_by
date_from
date_to
```

Depois:

```text
client
project
activity
generation_status
```

Nunca montar SQL por concatenação de string.

Usar query parameters validados.

---

# 55. Paginação

Nenhuma API de histórico deve retornar milhares de relatórios de uma vez.

Usar:

```text
page
page_size
```

ou cursor pagination.

Exemplo:

```text
GET /history?page=1&page_size=50
```

Definir limite:

```text
page_size <= 100
```

---

# 56. API de analytics

Começar com agregações SQL.

Exemplos:

```text
total de relatórios
total de horas
relatórios por mês
horas por cliente
horas por projeto
horas por atividade
tempo médio de geração
taxa de falhas
```

Exemplo:

```text
GET /analytics/summary
GET /analytics/hours-by-client
GET /analytics/hours-by-activity
GET /analytics/generation-performance
```

---

# 57. Não criar Data Warehouse ainda

A primeira versão não precisa de:

```text
ETL
Data Warehouse
OLAP
BI separado
```

O MySQL histórico pode atender o começo.

Porém, já estruturar os dados para permitir evolução futura.

---

# 58. Modelo futuro de analytics

Quando o volume aumentar:

```text
dim_date
dim_employee
dim_client
dim_project
dim_activity
```

e fatos:

```text
fact_report_hours
fact_report_generation
```

Exemplo:

```text
fact_report_hours
-----------------
date_id
employee_id
client_id
project_id
activity_id
report_version_id
hours
```

---

# 59. Frontend — `useReportStore.ts`

O store atual também está grande.

Evitar um único Zustand store responsável por tudo.

Separar conceitualmente:

```text
authStore
reportStore
historyStore
managementStore
chatStore
uiStore
```

Não é obrigatório fazer toda a divisão em uma única etapa.

---

# 60. Estado servidor x estado UI

Nem tudo precisa ficar no Zustand.

## Estado do servidor

Exemplo:

```text
reports
history
analytics
management data
```

Pode ser buscado e cacheado por camada própria de data fetching.

## Estado da interface

Exemplo:

```text
modal aberto
filtro ativo
aba selecionada
input temporário
```

Pode ficar no Zustand.

Objetivo:

```text
Server State ≠ UI State
```

---

# 61. Frontend — IDs

A interface deve trabalhar com:

```text
reportId
versionId
generationId
artifactId
```

e não com:

```text
reportName
employeeName
```

como identificação primária.

---

# 62. Tela de histórico

Criar uma área:

```text
Histórico de Relatórios
```

Tabela:

```text
Data
Funcionário
Competência
Versão
Status
Criado por
Última geração
Ações
```

Ações:

```text
Visualizar
Baixar XLSX
Baixar PDF
Ver versões
Ver auditoria
```

---

# 63. Tela de versões

Exemplo:

```text
Relatório #01K...
─────────────────────────────

v3   21/09/2026   Usuário X
     14:33
     Alteração: ajuste de atividades

v2   20/09/2026   Usuário X
     17:10
     Alteração: dados importados

v1   20/09/2026   Sistema
     16:50
     Criação inicial
```

Não exibir somente a versão atual.

---

# 64. Tela de auditoria

Mostrar:

```text
Data/hora
Usuário
Ação
Entidade
Origem
Resumo
```

Opcionalmente permitir:

```text
Ver antes
Ver depois
```

---

# 65. Download de artifacts

O frontend não deve montar caminhos de arquivo.

Exemplo:

```text
GET /artifacts/{artifact_id}/download
```

O backend valida autorização e retorna o arquivo.

---

# 66. Autorização

A aplicação deve definir claramente:

```text
admin
manager
user
```

ou os papéis existentes no sistema.

Controlar:

- quem pode gerar;
- quem pode visualizar;
- quem pode baixar;
- quem pode alterar;
- quem pode consultar analytics;
- quem pode ver auditoria.

---

# 67. Audit trail da IA

Quando a IA executar uma operação:

```text
source = ai
```

Registrar também:

```text
intent
operation
input
result
user
timestamp
```

Não é necessário armazenar segredos ou credenciais.

---

# 68. Operações da IA

O ideal é:

```text
LLM
 ↓
structured operation
 ↓
validator
 ↓
service
 ↓
database
```

Não:

```text
LLM
 ↓
SQL arbitrário
```

Nem:

```text
LLM
 ↓
edição direta do arquivo
```

---

# 69. Validação das operações da IA

Exemplo:

```json
{
  "operation": "update_activity_hours",
  "report_id": "...",
  "activity_id": "...",
  "hours": 8.5
}
```

O backend valida:

```text
report existe?
usuário tem acesso?
activity pertence ao report?
hours é válida?
operação é permitida?
```

Só então executa.

---

# 70. Observabilidade

Adicionar logs estruturados.

Cada request pode possuir:

```text
request_id
user_id
route
duration_ms
status_code
```

Para geração:

```text
generation_id
report_id
version_id
duration_ms
status
```

---

# 71. Métricas

Começar com:

```text
projectile_query_duration_ms
report_generation_duration_ms
xlsx_generation_duration_ms
pdf_generation_duration_ms
database_query_duration_ms
api_error_count
generation_failure_count
```

Isso permitirá saber onde o sistema está lento.

---

# 72. Performance do Projectile

A otimização que reduziu uma consulta de aproximadamente dezenas de segundos para cerca de 0,4–0,45 s mostra que os filtros corretos, especialmente pelo `sysClientId`, têm impacto significativo.

Esse ganho deve ser protegido com testes/performance checks.

Não assumir que uma alteração futura manterá o mesmo desempenho.

---

# 73. Performance tests

Criar queries representativas:

```text
consulta pequena
consulta média
consulta grande
múltiplos usuários
```

Registrar:

```text
p50
p95
p99
```

Pode começar apenas com:

```text
tempo total
```

e evoluir depois.

---

# 74. Índices no banco histórico

Criar índices para filtros reais.

Exemplo:

```sql
CREATE INDEX idx_reports_competence
ON reports (competence);

CREATE INDEX idx_reports_employee
ON reports (employee_id);

CREATE INDEX idx_generations_report
ON report_generation (report_id);

CREATE INDEX idx_versions_report
ON report_versions (report_id, version_number);
```

Não criar dezenas de índices sem observar consultas reais.

---

# 75. Integridade referencial

Sempre que possível, usar foreign keys:

```text
report_versions.report_id
    → reports.id
```

```text
report_packages.report_version_id
    → report_versions.id
```

```text
report_groups.report_package_id
    → report_packages.id
```

etc.

Isso evita registros órfãos.

---

# 76. Soft delete

Não apagar histórico por padrão.

Quando algo precisar desaparecer da interface, considerar:

```text
archived_at
```

ou:

```text
deleted_at
```

O dado continua disponível para auditoria, conforme as regras do sistema.

---

# 77. Retenção

Definir política:

```text
Quanto tempo manter snapshots?
Quanto tempo manter arquivos?
Quanto tempo manter logs?
```

Exemplo inicial:

```text
dados históricos: indefinido
artifacts antigos: política configurável
logs técnicos: período menor
```

A política real deve ser decidida conforme os requisitos da empresa.

---

# 78. Backup

O segundo MySQL passa a ser crítico.

Implementar:

```text
backup diário
backup incremental/binlog quando aplicável
teste de restauração
```

Também testar:

```text
restore completo
restore de tabela
recuperação após corrupção
```

Backup que nunca foi restaurado em teste não deve ser considerado plenamente validado.

---

# 79. Ambiente de desenvolvimento

Criar pelo menos:

```text
.env
.env.example
```

Exemplo:

```env
PROJECTILE_DB_HOST=
PROJECTILE_DB_PORT=3306
PROJECTILE_DB_NAME=
PROJECTILE_DB_USER=
PROJECTILE_DB_PASSWORD=
PROJECTILE_SYS_CLIENT_ID=

REPORTS_DB_HOST=
REPORTS_DB_PORT=3306
REPORTS_DB_NAME=reports_db
REPORTS_DB_USER=
REPORTS_DB_PASSWORD=
```

Nunca versionar:

```text
.env
```

---

# 80. Docker opcional

Para desenvolvimento, pode ser útil:

```text
docker-compose.yml
```

com:

```text
reports-mysql
backend
frontend
```

O Projectile pode continuar externo.

Exemplo:

```text
┌──────────────┐
│ FastAPI      │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ reports-mysql│
└──────────────┘

Projectile → servidor externo
```

---

# 81. Migração incremental

Não tentar refatorar tudo simultaneamente.

Recomendação:

```text
Fase 1 — Fundação
Fase 2 — Novo banco
Fase 3 — Persistência
Fase 4 — Histórico
Fase 5 — Auditoria
Fase 6 — Refatoração
Fase 7 — Analytics
Fase 8 — Hardening
```

---

# 82. Fase 1 — Fundação

Objetivos:

- configuração central;
- `.env`;
- estrutura de logging;
- IDs estáveis;
- tratamento padronizado de erros;
- testes de regressão existentes.

Checklist:

```text
[ ] core/config.py
[ ] core/logging.py
[ ] core/errors.py
[ ] request_id
[ ] erro JSON padronizado
[ ] .env.example
```

---

# 83. Fase 2 — Segundo MySQL

Criar:

```text
reports_db.py
```

Depois:

```text
Alembic
```

Primeira migration:

```text
reports
```

Segunda:

```text
report_source_snapshots
```

Terceira:

```text
report_versions
```

Quarta:

```text
report_packages
report_groups
report_activities
```

Quinta:

```text
report_generation
report_artifacts
```

Sexta:

```text
audit_log
```

Não precisa fazer todas em uma migration gigante.

---

# 84. Fase 3 — Persistência do relatório

Implementar:

```text
Generate Report
      ↓
Projectile
      ↓
Snapshot
      ↓
Reports DB
      ↓
XLSX
```

Critério de conclusão:

> Ao gerar um relatório, consigo abrir o banco e encontrar o estado estruturado que originou aquele arquivo.

---

# 85. Fase 4 — Histórico

Implementar:

```text
Report
Version
Generation
Artifact
```

Critério de conclusão:

```text
Relatório
 ├── v1
 │    └── XLSX
 ├── v2
 │    └── XLSX
 └── v3
      ├── XLSX
      └── PDF
```

---

# 86. Fase 5 — Auditoria

Registrar:

```text
create
update
generate
download
archive
ai_operation
```

Critério de conclusão:

> Consigo responder quem fez uma alteração, quando fez e qual versão foi afetada.

---

# 87. Fase 6 — Refatoração do backend

Depois que a persistência estiver funcionando, separar:

```text
routers
services
repositories
schemas
integrations
```

Isso reduz o risco de tentar redesenhar arquitetura enquanto o domínio ainda está mudando.

---

# 88. Fase 7 — Frontend histórico

Adicionar:

```text
histórico
versões
artifacts
auditoria
filtros
paginação
```

Critério de conclusão:

> O usuário consegue encontrar um relatório antigo sem consultar o Projectile.

---

# 89. Fase 8 — Analytics

Começar simples:

```text
KPI total de relatórios
KPI total de horas
horas por competência
horas por cliente
horas por atividade
gerações por status
tempo médio de geração
```

Depois evoluir.

---

# 90. Fase 9 — Hardening

Revisar:

```text
segurança
uploads
auth
autorização
rate limit
logs
timeouts
pool
backup
migrations
recovery
```

---

# 91. Testes recomendados

## Unitários

Testar:

```text
parser
normalização
hash
versionamento
regras de negócio
validação
chat_ops
```

## Integração

Testar:

```text
Projectile repository
Reports repository
migrations
services
API
```

## Contrato

Testar:

```text
API schemas
template XLSX
snapshot schema
AI operations
```

## Regressão

Testar:

```text
casos antigos
templates reais
relatórios conhecidos
```

---

# 92. Teste crítico: reprodução

Criar um teste em que:

```text
snapshot antigo
      ↓
gera novamente
      ↓
resultado equivalente
```

Objetivo:

```text
snapshot
   ↓
parser/normalização
   ↓
generator
```

deve ser reproduzível.

Isso é extremamente importante para auditoria.

---

# 93. Teste de imutabilidade

Depois de criar:

```text
v1
```

executar:

```text
criar v2
```

e verificar:

```text
v1 != alterada
```

O teste deve detectar qualquer UPDATE acidental nos registros da versão anterior.

---

# 94. Teste de concorrência

Simular:

```text
10 requisições simultâneas
```

e validar:

- conexão;
- pool;
- geração;
- IDs;
- versionamento;
- arquivos;
- banco.

Garantir que duas execuções não obtenham:

```text
version_number = 5
```

simultaneamente para o mesmo relatório.

Isso deve ser protegido por transação + constraint.

---

# 95. Concorrência de versão

Não confiar somente em:

```python
version = last_version + 1
```

sem proteção.

Uma abordagem:

```text
transaction
   ↓
lock do relatório
   ↓
buscar versão máxima
   ↓
incrementar
   ↓
insert
   ↓
commit
```

Além disso:

```sql
UNIQUE(report_id, version_number)
```

funciona como segunda barreira.

---

# 96. Tratamento de erros

Criar códigos internos:

```text
PROJECTILE_CONNECTION_ERROR
PROJECTILE_QUERY_ERROR
INVALID_XLSX
TEMPLATE_INVALID
REPORT_NOT_FOUND
VERSION_NOT_FOUND
GENERATION_FAILED
ARTIFACT_NOT_FOUND
UNAUTHORIZED
FORBIDDEN
VALIDATION_ERROR
```

Isso facilita frontend, logs e suporte.

---

# 97. Erros no frontend

O frontend deve transformar:

```json
{
  "code": "GENERATION_FAILED",
  "message": "..."
}
```

em uma mensagem adequada para o usuário.

Não exibir stack trace.

---

# 98. Health checks

Criar:

```text
GET /health
GET /health/projectile
GET /health/reports-db
```

Exemplo:

```json
{
  "status": "ok",
  "projectile_db": "ok",
  "reports_db": "ok"
}
```

O endpoint público pode ser simplificado, enquanto endpoints internos podem fornecer mais detalhes.

---

# 99. Readiness

Separar:

```text
liveness
readiness
```

Liveness:

```text
aplicação está viva
```

Readiness:

```text
aplicação consegue atender requisições
```

---

# 100. Cache

O cache atual deve ser revisto após a criação do banco histórico.

Uma regra simples:

```text
cache = otimização
database = fonte persistente
```

Nunca usar cache como armazenamento histórico.

Definir:

```text
TTL
invalidation
scope
```

---

# 101. Snapshot versus cache

São conceitos diferentes.

## Cache

```text
pode desaparecer
```

## Snapshot

```text
deve permanecer
```

Exemplo:

```text
cache:
"consulta Projectile de hoje"

snapshot:
"dados usados para gerar relatório v7"
```

Nunca tratar snapshot como cache.

---

# 102. Arquivos físicos

Estrutura recomendada:

```text
storage/
  reports/
    YYYY/
      MM/
        report-id/
          v1/
            report.xlsx
            report.pdf
          v2/
            report.xlsx
```

Mesmo nesse caso, o MySQL guarda:

```text
artifact_id
path
hash
size
mime
```

---

# 103. Hash do arquivo

Após gerar:

```python
sha256(file_bytes)
```

Guardar:

```text
artifact.sha256
```

Benefícios:

- detectar corrupção;
- verificar integridade;
- identificar duplicatas;
- auditoria.

---

# 104. Storage abstraction

Não acoplar o serviço a `open()` diretamente.

Criar:

```python
class ArtifactStorage:
    def save(...)
    def open(...)
    def delete(...)
```

Implementação inicial:

```text
LocalFilesystemStorage
```

Futura:

```text
S3Storage
```

Isso facilita migração para cloud/object storage.

---

# 105. Relatório como agregado

Uma forma útil de pensar o domínio:

```text
Report
 ├── Versions
 ├── Current Version
 ├── Generations
 ├── Artifacts
 └── Audit events
```

O serviço de relatório coordena esse agregado.

---

# 106. Eventual event-driven

Não é necessário implementar agora.

No futuro, eventos como:

```text
ReportCreated
ReportVersionCreated
ReportGenerated
ReportGenerationFailed
ArtifactCreated
```

podem alimentar:

```text
analytics
notificações
integrações
```

Primeiro estabilizar o fluxo transacional.

---

# 107. Analytics de negócio

Com o banco histórico, será possível responder perguntas como:

```text
Quantos relatórios foram gerados por mês?

Quantas horas foram registradas?

Quais atividades concentram mais horas?

Como as horas variaram entre competências?

Quantas gerações falharam?

Quanto tempo o gerador leva?

Quais usuários geram mais relatórios?

Quantas versões cada relatório possui?
```

Essas consultas devem usar dados históricos próprios, sem depender do estado atual do Projectile.

---

# 108. Analytics técnico

Também será possível medir:

```text
tempo de consulta Projectile
tempo de parsing
tempo de geração XLSX
tempo de geração PDF
tempo total
taxa de erro
tamanho médio dos artifacts
```

Exemplo:

```text
generation
├── projectile_ms
├── parser_ms
├── generator_ms
├── storage_ms
└── total_ms
```

Pode ser adicionado posteriormente à tabela `report_generation`.

---

# 109. Snapshot completo versus snapshot mínimo

Há duas estratégias.

## Snapshot completo

Guardar todos os dados usados.

Vantagens:

- reprodução;
- auditoria;
- debugging.

Desvantagens:

- mais espaço.

## Snapshot mínimo

Guardar apenas os campos essenciais.

Vantagens:

- menor custo.

Desvantagens:

- pode ser impossível reproduzir exatamente.

Para esse projeto, a primeira versão deve preferir o **snapshot suficientemente completo para reprodução**.

---

# 110. Versionamento do schema do snapshot

Adicionar:

```text
schema_version
```

Exemplo:

```text
1.0
```

ou:

```text
2026-09
```

Quando a estrutura mudar:

```text
schema_version = 2
```

Isso evita interpretar JSON antigo como se fosse novo.

---

# 111. Compatibilidade futura

Criar funções:

```text
snapshot_v1_to_domain()
snapshot_v2_to_domain()
```

quando necessário.

Assim registros antigos continuam utilizáveis.

---

# 112. Migration do JSON de management

Quando o novo banco estiver estável:

```text
management.json
       ↓
import script
       ↓
reports_db
```

O script deve:

1. validar JSON;
2. criar IDs;
3. inserir registros;
4. produzir relatório de erros;
5. permitir reexecução;
6. não duplicar registros.

---

# 113. Import idempotente

O script de migração deve poder ser executado mais de uma vez.

Usar:

```text
external_id
```

ou algum identificador determinístico.

Exemplo:

```text
source = management_json
source_key = employee:123
```

E criar:

```sql
UNIQUE(source, source_key)
```

quando fizer sentido.

---

# 114. Estratégia de branches

Uma forma segura:

```text
main
develop

feature/reports-db
feature/report-history
feature/audit-log
feature/api-refactor
feature/frontend-history
feature/analytics
```

Cada grande etapa em branch própria.

---

# 115. Commits

Evitar:

```text
"fiz tudo"
```

Preferir:

```text
feat(db): add reports database connection
feat(db): add initial reports migration
feat(reports): persist source snapshot
feat(reports): add report versions
feat(audit): record report generation
refactor(api): split report routes
test(generator): add template regression coverage
```

Isso facilita rollback e revisão.

---

# 116. Ordem prática de implementação

Esta é a ordem sugerida para reduzir risco:

```text
1. Configuração central
2. Tratamento de erros
3. IDs estáveis
4. Segundo MySQL
5. Alembic
6. Tabela reports
7. Snapshot
8. Version
9. Estrutura Package/Group/Activity
10. Generation
11. Artifact
12. Persistência durante geração
13. Histórico API
14. Histórico frontend
15. Audit log
16. Refatoração do main.py
17. Refatoração do store
18. Pool Projectile
19. Upload hardening
20. XLSX contract tests
21. IA determinística + IDs
22. Analytics
23. Observabilidade
24. Backup/restore
```

---

# 117. Primeiro MVP recomendado

Antes de construir toda a arquitetura, criar este MVP:

```text
[Gerar Relatório]
       ↓
Projectile
       ↓
Snapshot
       ↓
Reports DB
       ↓
Report v1
       ↓
XLSX
       ↓
Artifact
```

Depois:

```text
[Histórico]
       ↓
lista v1
       ↓
download
```

Isso já muda o projeto de:

```text
gerador
```

para:

```text
sistema de relatórios persistente
```

---

# 118. Definition of Done — banco

Considerar o segundo banco pronto quando:

```text
[ ] banco separado existe
[ ] usuário separado existe
[ ] conexão separada existe
[ ] Alembic configurado
[ ] migrations funcionando
[ ] reports criados
[ ] versions criadas
[ ] snapshots criados
[ ] activities persistidas
[ ] generation registrada
[ ] artifacts registrados
[ ] índices criados
[ ] foreign keys criadas
[ ] backup configurado
```

---

# 119. Definition of Done — histórico

```text
[ ] relatório antigo pode ser listado
[ ] versão antiga pode ser aberta
[ ] snapshot permanece inalterado
[ ] arquivo pode ser baixado
[ ] geração pode ser consultada
[ ] erro de geração fica registrado
[ ] usuário que gerou fica registrado
```

---

# 120. Definition of Done — auditoria

```text
[ ] create registrado
[ ] update registrado
[ ] generate registrado
[ ] download registrado
[ ] AI operation registrada
[ ] before/after disponível quando aplicável
[ ] timestamp confiável
[ ] usuário identificado
```

---

# 121. Definition of Done — arquitetura

```text
[ ] main.py não concentra domínio
[ ] routers separados
[ ] services separados
[ ] repositories separados
[ ] Projectile isolado
[ ] Reports DB isolado
[ ] IA isolada
[ ] storage isolado
[ ] configuração centralizada
```

---

# 122. Definition of Done — qualidade

```text
[ ] unit tests
[ ] integration tests
[ ] regression tests
[ ] contract tests
[ ] XLSX fixture tests
[ ] concurrency tests
[ ] migration tests
[ ] health checks
```

---

# 123. Definition of Done — segurança

```text
[ ] secrets fora do Git
[ ] upload limitado
[ ] validação de XLSX
[ ] autorização por recurso
[ ] downloads autorizados
[ ] rate limiting mantido
[ ] cookies seguros
[ ] logs sem segredos
[ ] SQL parametrizado
```

---

# 124. Roadmap futuro

Depois dessa etapa, a plataforma poderá evoluir para:

```text
V1
├── geração
├── histórico
├── snapshots
└── artifacts

V2
├── auditoria completa
├── analytics
├── dashboards
└── performance monitoring

V3
├── object storage
├── filas de geração
├── processamento assíncrono
└── notificações

V4
├── data warehouse
├── BI
├── previsões
└── integrações externas
```

---

# 125. Quando usar fila assíncrona

Se a geração ficar pesada:

```text
POST /generate
       ↓
job criado
       ↓
queue
       ↓
worker
       ↓
XLSX/PDF
```

O frontend consulta:

```text
GET /generations/{id}
```

Status:

```text
queued
running
success
failed
```

Não implementar essa complexidade antes de haver necessidade real.

---

# 126. Quando separar analytics do banco operacional

Quando houver:

- muitas consultas analíticas;
- milhões de linhas;
- consultas pesadas;
- dashboards frequentes;
- necessidade de histórico muito grande;
- necessidade de integração com BI.

A partir daí:

```text
Reports MySQL
      ↓
ETL/ELT
      ↓
Data Warehouse
      ↓
BI
```

Até lá, manter uma única base histórica simplifica o projeto.

---

# 127. Possível schema final

```text
reports
├── id
├── employee_id
├── employee_name_snapshot
├── competence
├── status
├── current_version_id
├── created_by
├── created_at
└── updated_at

report_versions
├── id
├── report_id
├── version_number
├── source_snapshot_id
├── created_by
├── created_from
├── change_summary
├── state_json
└── created_at

report_source_snapshots
├── id
├── source_system
├── source_query
├── source_filters_json
├── captured_at
├── source_reference
├── data_json
├── data_hash
└── schema_version

report_packages
├── id
├── report_version_id
├── source_id
├── name
└── position

report_groups
├── id
├── report_package_id
├── source_id
├── name
└── position

report_activities
├── id
├── report_group_id
├── source_id
├── name
├── hours
└── position

report_generation
├── id
├── report_id
├── report_version_id
├── requested_by
├── started_at
├── finished_at
├── duration_ms
├── status
├── error_code
└── error_message

report_artifacts
├── id
├── generation_id
├── artifact_type
├── storage_type
├── storage_path
├── file_name
├── mime_type
├── file_size
├── sha256
└── created_at

audit_log
├── id
├── actor_id
├── action
├── entity_type
├── entity_id
├── source
├── before_json
├── after_json
├── metadata_json
└── created_at
```

---

# 128. Exemplo de fluxo completo

```text
USUÁRIO
  │
  │ clica em "Gerar"
  ▼
FRONTEND
  │
  │ POST /reports/generate
  ▼
FASTAPI
  │
  ├── autentica
  ├── valida parâmetros
  │
  ▼
REPORT SERVICE
  │
  ├── chama Projectile Service
  │          │
  │          ▼
  │      Projectile DB
  │          │
  │          ▼
  │      dados brutos
  │
  ├── normaliza
  │
  ├── cria snapshot
  │
  ├── calcula SHA-256
  │
  ├── cria report/version
  │
  ├── persiste estrutura
  │
  ├── registra generation=started
  │
  ▼
GENERATOR
  │
  ├── gera XLSX
  ├── valida XLSX
  │
  ▼
STORAGE
  │
  ├── salva arquivo
  ├── calcula hash
  │
  ▼
REPORT DB
  │
  ├── cria artifact
  ├── generation=success
  └── audit
  │
  ▼
FASTAPI
  │
  ▼
FRONTEND
  │
  ▼
Relatório gerado + ID + artifact
```

---

# 129. O que não fazer

## Não

```text
misturar as duas bases
```

## Não

```text
armazenar apenas o XLSX
```

## Não

```text
usar nome como ID
```

## Não

```text
deixar o LLM escrever SQL
```

## Não

```text
regravar versões antigas
```

## Não

```text
reescrever o template XLSX inteiro sem testes
```

## Não

```text
guardar senha no código
```

## Não

```text
retornar todo o histórico em uma chamada
```

## Não

```text
usar cache como histórico
```

## Não

```text
criar data warehouse antes de estabilizar o domínio
```

---

# 130. Resultado esperado da evolução

Ao finalizar o roadmap, o sistema terá uma arquitetura próxima desta:

```text
                         ┌──────────────────────┐
                         │      React/Vite      │
                         │                      │
                         │ Reports              │
                         │ History              │
                         │ Versions             │
                         │ Analytics             │
                         │ Chat                 │
                         └───────────┬──────────┘
                                     │
                                     ▼
                         ┌──────────────────────┐
                         │       FastAPI        │
                         │                      │
                         │ Routers              │
                         │ Services             │
                         │ Repositories         │
                         │ Integrations         │
                         └───────┬───────┬──────┘
                                 │       │
                  read-only      │       │ read/write
                                 ▼       ▼
                       ┌────────────┐ ┌───────────────┐
                       │ Projectile │ │ Reports MySQL │
                       │   MySQL    │ │               │
                       │            │ │ Histórico     │
                       └────────────┘ │ Snapshots     │
                                      │ Versions      │
                                      │ Audit         │
                                      │ Analytics     │
                                      └───────┬───────┘
                                              │
                                              ▼
                                      ┌──────────────┐
                                      │   Storage    │
                                      │ XLSX / PDF   │
                                      └──────────────┘
```

---

# 131. Prioridade final

Se houver pouco tempo, a ordem de prioridade deve ser:

```text
P0 — Persistência correta
    segundo MySQL
    snapshot
    versionamento
    generation
    artifact

P1 — Confiabilidade
    migrations
    testes
    integridade
    auditoria
    erros

P2 — Arquitetura
    routers
    services
    repositories
    configuração

P3 — Segurança e performance
    upload
    pool
    autorização
    observabilidade

P4 — Produto
    histórico UI
    analytics
    melhorias de IA

P5 — Escala
    fila
    object storage
    warehouse
```

---

# 132. Estratégia recomendada para implementação solo

Não tentar desenvolver todas as tabelas, APIs e telas em paralelo.

Trabalhar verticalmente.

## Vertical Slice 1

```text
Generate
 → Projectile
 → snapshot
 → reports DB
 → XLSX
```

## Vertical Slice 2

```text
History
 → list
 → details
 → download
```

## Vertical Slice 3

```text
Versions
 → v1
 → v2
 → diff
```

## Vertical Slice 4

```text
Audit
```

## Vertical Slice 5

```text
Analytics
```

Só depois reorganizar os módulos restantes.

Essa abordagem reduz o risco de terminar uma grande refatoração sem possuir uma funcionalidade completa utilizável.

---

# 133. Checklist executável

## Fundação

- [ ] Criar `core/config.py`
- [ ] Criar `.env.example`
- [ ] Centralizar variáveis
- [ ] Criar códigos de erro
- [ ] Padronizar respostas de erro
- [ ] Adicionar request ID

## Banco Projectile

- [ ] Encapsular conexão
- [ ] Configurar pool
- [ ] Tornar `sysClientId` configurável
- [ ] Testar concorrência
- [ ] Medir performance

## Banco Reports

- [ ] Criar MySQL
- [ ] Criar usuário
- [ ] Configurar conexão
- [ ] Instalar/configurar Alembic
- [ ] Criar `reports`
- [ ] Criar `report_versions`
- [ ] Criar snapshots
- [ ] Criar packages/groups/activities
- [ ] Criar generation
- [ ] Criar artifacts
- [ ] Criar audit

## Geração

- [ ] Criar snapshot antes da geração
- [ ] Persistir versão
- [ ] Registrar generation
- [ ] Gerar XLSX
- [ ] Validar XLSX
- [ ] Salvar artifact
- [ ] Calcular SHA-256
- [ ] Finalizar generation

## Histórico

- [ ] GET reports
- [ ] GET report
- [ ] GET versions
- [ ] GET generations
- [ ] GET artifacts
- [ ] Download seguro
- [ ] Paginação
- [ ] Filtros

## Frontend

- [ ] `historyStore`
- [ ] Tela de histórico
- [ ] Tela de versões
- [ ] Tela de auditoria
- [ ] Download
- [ ] Estados loading/error/empty

## IA

- [ ] Limitar contexto
- [ ] Operações estruturadas
- [ ] Stable IDs
- [ ] Validar cada operação
- [ ] Auditar operações

## XLSX

- [ ] Template fixture
- [ ] Contract tests
- [ ] Regression tests
- [ ] Validar drawings/media
- [ ] Validar workbook final

## Segurança

- [ ] Limite de upload
- [ ] Streaming/chunks
- [ ] Validação de XLSX
- [ ] Secrets fora do código
- [ ] Autorização por recurso
- [ ] Download autorizado
- [ ] Logs sem credenciais

## Analytics

- [ ] Summary
- [ ] Horas por competência
- [ ] Horas por cliente
- [ ] Horas por atividade
- [ ] Geração por status
- [ ] Tempo de geração

## Operação

- [ ] Health checks
- [ ] Logs estruturados
- [ ] Métricas
- [ ] Backup
- [ ] Restore testado
- [ ] Política de retenção

---

# 134. Meta arquitetural

A meta não é apenas "adicionar um banco".

A meta é transformar:

```text
Aplicação que gera arquivo
```

em:

```text
Plataforma de geração, versionamento, rastreabilidade e análise de relatórios
```

O segundo MySQL é a peça que permite essa evolução porque ele passa a guardar a história do sistema sem depender da mutabilidade do Projectile.

O princípio mais importante para preservar durante toda a implementação é:

```text
Projectile = fonte operacional
Reports DB = histórico oficial da aplicação
XLSX/PDF = artifacts derivados
Snapshot = estado que permite explicar/reproduzir a geração
Audit = prova do que aconteceu
```

Essa separação mantém o sistema compreensível e cria uma base sólida para as próximas evoluções.
