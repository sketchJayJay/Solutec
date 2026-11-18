# Solutec 3.3 no Coolify

## Escolha do pacote

- **Solutec_GitHub_Coolify.zip**: somente o código, sem banco, PDFs ou dados de clientes. É o pacote para enviar a um repositório público ou atualizar uma instalação que já tem seu volume de dados.
- **solutec.zip**: pacote completo, com a cópia dos dados e anexos recebidos. Use em um repositório **privado** ou em instalação direta. A pasta `seed/` contém dados de clientes; não a envie a um repositório público. O `.gitignore` exclui essa pasta de commits feitos por Git, mas não controla o envio manual de arquivos pela página do GitHub.

Os dados do pacote completo são uma fotografia do ZIP enviado, não uma leitura do servidor em produção.

## Atualizar uma instalação existente

1. Antes da atualização, baixe o backup completo no menu do sistema. Se estiver na versão anterior, faça uma cópia consistente do banco e dos anexos do volume atual.
2. Envie os arquivos do pacote de código à raiz do repositório, mantendo `Dockerfile`, `app.py`, `maintenance.py`, `requirements.txt`, `static/` e `templates/`.
3. No Coolify use **Build Pack: Dockerfile**, porta interna **8000**.
4. Mantenha o mesmo volume persistente montado em **`/data`** e os mesmos caminhos já usados. Não recrie ou remova o volume.
5. Preserve a `SECRET_KEY` atual e mantenha `RESET_ADMIN_PASSWORD=false`.
6. Faça o redeploy e consulte `/health`. Confira os totais, abra um PDF e revise `Conferir cadastros`.

A atualização usa migrações aditivas. Antes da primeira migração, guarda uma cópia consistente do banco em `/data/backups`. Não exclui nem atribui automaticamente a máquina sem proprietário.

## Primeira instalação

1. Para trazer os dados existentes automaticamente, use o pacote completo em um repositório **privado**. O banco e os anexos de `seed/` só serão copiados se o destino estiver vazio. Se enviar por Git, a pasta é ignorada por padrão; somente após confirmar que o repositório é privado, inclua-a explicitamente com `git add -f seed`.
2. Crie a aplicação com Dockerfile e o volume persistente `/data` **antes do primeiro deploy**.
3. Configure:

| Variável | Valor / finalidade |
| --- | --- |
| `SECRET_KEY` | Chave longa e aleatória. Guarde e mantenha nas próximas atualizações. |
| `COOKIE_SECURE` | `true` no domínio HTTPS. |
| `PORT` | `8000` |
| `SOLUTEC_DATA_DIR` | `/data` |
| `SOLUTEC_UPLOAD_DIR` | `/data/uploads` |
| `ADMIN_EMAIL` | Login inicial. Padrão: `solutec.divinomg@gmail.com`. Não configura envio de e-mail. |
| `ADMIN_PASSWORD` | Necessária para iniciar um banco vazio ou redefinir a senha explicitamente. |
| `RESET_ADMIN_PASSWORD` | `false` normalmente. |

Se o banco do pacote já contém administrador, o login e a senha existentes são preservados. Para redefinir: informe a nova `ADMIN_PASSWORD`, use `RESET_ADMIN_PASSWORD=true` por um deploy e depois retorne a `false`.

Não há configuração SMTP, servidor de e-mail ou senha de e-mail neste sistema. `ADMIN_EMAIL` é apenas o identificador do login.

Se usar o pacote sem dados em uma primeira instalação, o sistema inicia vazio. Ele não contém a cópia dos clientes e não substitui uma migração dos dados anteriores.

## Persistência

- `/data/solutec.db`: banco em uso.
- `/data/uploads`: documentos e fotos, incluindo os nomes antigos.
- `/data/uploads/company_brand`: logos enviados pela administração; a seleção ativa fica no banco e acompanha o backup.
- `/data/backups`: cópias anteriores a migração, edição administrativa ou exclusão.
- `/data/.session-key`: chave local de sessão gerada somente quando `SECRET_KEY` não foi configurada.
- Uma instância da aplicação, com dois workers do Gunicorn. Não escale para múltiplas réplicas com volumes separados.
- `--preload` executa a preparação do banco uma vez antes dos workers.
- O health check verifica se o banco pode ser lido. Não mostra dados do cadastro.

## Uso local

Python 3.12 ou superior:

```bash
pip install -r requirements.txt
```

No PowerShell, para acesso local por HTTP:

```powershell
$env:COOKIE_SECURE="false"
$env:PORT="8000"
python app.py
```

Abra `http://127.0.0.1:8000`. Se estiver usando o pacote sem banco, defina também `ADMIN_PASSWORD` antes de iniciar. Os dados locais ficam em `data/` por padrão.

## Backup e restauração

O menu **Baixar backup completo** exporta SQLite por sua API de backup, incluindo as páginas que ainda estejam no WAL, junto com os anexos. Não copie apenas o arquivo `.db` enquanto a aplicação estiver escrevendo.

Para restaurar, pare a aplicação, preserve uma cópia do volume atual e restaure `solutec.db` e `uploads/` no mesmo volume. Preserve a chave de sessão. Uma restauração substitui a base inteira; para corrigir um cadastro isolado, use as telas de edição e conferência.

## Atualização 3.1

Ao iniciar esta versão, a identificação da Solutec Matriz é atualizada para CNPJ `45.154.368/0001-42` e telefone `(32) 9 9988-5977`. A alteração é registrada uma única vez, com cópia anterior do banco. Ela não altera a identificação das outras revendas, senhas, clientes, máquinas ou OS.

A aba **Ordens de serviço** está disponível no menu lateral e no atalho **OS** do celular. Não há variável nova de ambiente para esta atualização.

## Atualização 3.2

Não exige novas variáveis de ambiente. Mantenha o volume `/data` e a `SECRET_KEY`. A tabela institucional é criada de forma aditiva; nenhuma máquina é removida no deploy. A exclusão depende da ação explícita da matriz na ficha, com confirmação e cópia anterior do banco.

Depois de atualizar, use **Identidade visual** para carregar a logo oficial. As quatro fotos fornecidas já estão no código. Os logos enviados depois ficam no volume persistente e são incluídos no backup completo.

## Atualização 3.3

Mantenha o volume e as variáveis existentes. A primeira inicialização adiciona `machines.cover_image`, com cópia anterior consistente do banco. O campo guarda apenas a escolha de apresentação. As máquinas antigas recebem a referência visual na renderização, sem atualização dos seus modelos ou anexos.

Após atualizar, abra **Máquinas** e confira as fotografias nos cards. Use **Trocar foto** para mudar cada capa. A escolha e as fotos próprias ficam no volume persistente e acompanham o backup completo.
