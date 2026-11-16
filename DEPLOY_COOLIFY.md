# Solutec no Coolify

## Deploy pelo GitHub
1. Envie o conteúdo desta pasta para a raiz de um repositório GitHub.
2. No Coolify, crie um recurso **Public Repository** (ou Private Repository) e selecione o repositório.
3. Build Pack: **Dockerfile**. Porta interna: **8000**.
4. Em Storage / Persistent Volumes, crie um volume persistente montado em `/data`.
5. Configure as variáveis de ambiente:
   - `SECRET_KEY`: string longa e aleatória (não reutilize a senha do administrador).
   - `COOKIE_SECURE`: `true`.
   - `PORT`: `8000`.
   - `SOLUTEC_DATA_DIR`: `/data`.
   - `SOLUTEC_UPLOAD_DIR`: `/data/uploads`.
   - `ADMIN_EMAIL`: e-mail inicial da matriz, usado somente se o banco ainda não tiver usuário administrador.
   - `ADMIN_PASSWORD`: senha inicial.
   - `RESET_ADMIN_PASSWORD`: opcional, `true` somente no primeiro deploy para redefinir a senha do administrador existente; depois altere para `false` ou remova.
6. Gere o domínio HTTPS no Coolify e faça o deploy.

## Persistência e migração
- Banco SQLite e anexos ficam em `/data`, que precisa ser um volume persistente.
- Na primeira inicialização, o banco e os anexos existentes no pacote são copiados para o volume vazio.
- Nos próximos deploys, os dados do volume são preservados.
- Não remova o volume `/data` ao atualizar/recriar o serviço.
- Este pacote mantém SQLite para simplificar a migração e preservar os dados atuais. Use apenas uma instância/replica da aplicação.

## Login
O banco incluído já possui um administrador cadastrado. Para definir uma senha nova na primeira implantação, configure `ADMIN_PASSWORD` e `RESET_ADMIN_PASSWORD=true` no Coolify, faça o primeiro deploy e depois mude `RESET_ADMIN_PASSWORD` para `false` ou remova a variável. Assim a senha não será sobrescrita em deploys futuros.
