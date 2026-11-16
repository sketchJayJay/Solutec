# Solutec - revisão de 16/11/2026

## Resultado

Layout renovado em azul, branco e laranja, com navegação lateral no computador, menu e atalhos inferiores no celular. Painel com indicadores, busca, filtros e acesso rápido aos registros que precisam de conferência. A ficha da máquina separa identificação, proprietário, histórico e anexos.

Os dados originais não foram excluídos nem tiveram a propriedade alterada. A cópia enviada tinha 20 clientes, 21 máquinas, 6 OS, 10 anexos registrados e 12 PDFs no disco. Essas informações correspondem ao arquivo recebido, não ao banco de um servidor ao qual não houve acesso.

## Máquina extra identificada

| Campo | Cadastro #1 | Cadastro #2 |
| --- | --- | --- |
| Cliente | Antigo ID #1, ausente no banco | Sebastião Claudio dos Santos, cliente #7 |
| Máquina | TRATOR 354-4x4,35hp | Trator Bruthor 354 - 4x4 |
| Série | 25030713 | 25030713 |
| Motor | L820310661B | L820310661B |
| NF | Não informada | 125 |
| Entrega | 14/11/2025 | 20/07/2025 |

O cadastro #1 é a máquina que aumentava o total sem aparecer na listagem. O contador usava a tabela de máquinas, enquanto a lista exigia que o cliente existisse (`INNER JOIN`). Agora a lista usa o vínculo opcional e mostra a pendência.

Há forte indício de cadastro antigo duplicado do equipamento da ficha #2, mas o proprietário do registro #1 não foi presumido. Consulte a ficha #1 para comparar com a #2. Após conferir os documentos, o administrador pode corrigir o proprietário ou arquivar o cadastro com motivo e confirmação do número. Arquivar é reversível e preserva os dados, documentos e OS.

## Outras pendências reais encontradas

| Identificador | Valor | Máquinas / proprietários |
| --- | --- | --- |
| Série | 24070253 | #5 Gilberto Fernandes de Carvalho; #14 Jaime Ferreira da Silva Neto |
| Motor | L810723226B | #5 Gilberto Fernandes de Carvalho; #14 Jaime Ferreira da Silva Neto |
| Motor | L820310658B | #9 Edmar Fialho; #10 Laudenir Monteiro dos Santos |

Somados aos identificadores das máquinas #1/#2, são cinco grupos repetidos, envolvendo seis máquinas. Os registros #5/#14 têm notas e datas diferentes; confira se é transferência ou erro antes de alterar. Não foi feita fusão automática.

Há quatro OS com cliente ausente: #1 aponta para o antigo cliente #5; #2, #3 e #4 apontam para o antigo cliente #1. A OS #4 também está vinculada à máquina #1. Agora essas OS podem ser abertas, impressas e consultadas pela matriz. A área **Conferir cadastros** permite ajustar o vínculo com confirmação e cópia anterior do banco.

Dois PDFs da máquina #8 estão no disco sem referência na tabela de anexos. Eles foram preservados e seguem no backup completo. Confira se são cópias antigas antes de criar novos vínculos.

Os dados institucionais da matriz usados na impressão ainda contêm campos de exemplo (CNPJ e telefone). Substitua pelos dados reais antes de emitir documentos oficiais; nenhum dado fiscal foi inventado nesta revisão.

## Correções e melhorias entregues

- A máquina sem cliente ficou visível, com o antigo ID e as fichas de identificadores coincidentes.
- Filtros: todas, a conferir, sem proprietário e arquivadas; busca por nome, proprietário, modelo, série, motor e NF.
- Busca sem depender de acentos e ordenação por ID nos bancos antigos que não têm data de cadastro.
- Impede novos números de série ou motor repetidos na mesma revenda, normalizando espaços, sinais e maiúsculas. Mantém a possibilidade de editar os registros legados sem apagar seus identificadores.
- Valida cliente e revenda no servidor; impede cadastrar OS com máquina de outro cliente.
- Valida datas e horímetro, aceita vírgula decimal e preserva zero.
- Corrige a incompatibilidade entre `obs` e `obs_text` em bancos novos e antigos.
- Corrige a abertura dos PDFs antigos: sete nomes tinham diferenças na codificação de acentos entre banco e disco. Os dez PDFs registrados foram abertos nos testes.
- PDFs aparecem como documentos, com abertura e download, em vez de miniaturas de imagem quebradas.
- Upload com nome seguro, identificação única, checagem básica de formato, limite de dez arquivos e 25 MB por envio. Se um arquivo for inválido, as observações não são gravadas parcialmente.
- Revendas só acessam seus próprios clientes, máquinas, OS e anexos. A URL de um PDF também exige autorização.
- Formulários protegidos contra envio sem token; sessão renovada no login e redirecionamentos externos rejeitados.
- Corrige o WhatsApp de números brasileiros com DDD 55.
- Remove o botão de exclusão duplicado no painel do cliente.
- O último item digitado na OS é salvo mesmo sem clicar em Adicionar; Enter adiciona o item.
- Arquivamento e restauração de máquinas, registro das alterações administrativas e backup completo pela matriz.
- Exclusão de cliente trata explicitamente dependências em bancos legados, guardando cópia anterior. Arquivos removidos da ficha continuam preservados para recuperação.
- Alterações de proprietário preservam os vínculos das OS históricas; as divergências ficam disponíveis para conferência.
- QR Code de acesso gerado pelo próprio sistema, sem depender de um serviço externo.
- Impressão com a logo original recortada, aproveitamento melhor do espaço e datas legíveis.
- Chave de sessão local persistente e criação atômica; senha do administrador não muda em atualizações. Banco novo exige senha inicial definida, sem senha padrão pública.
- Docker/Gunicorn com preparação anterior aos workers, health check e volume `/data` preservado.

## Validação

**94 testes automatizados passaram**, sem falhas. Cobrem páginas existentes, busca, cadastro/edição, valores inválidos, duplicidade, observações, upload/PDF, remoção de anexos, OS, isolamento das revendas, sessão, formulários, backup, arquivamento/restauração, migrações, banco novo, troca de proprietário, QR Code e senha administrativa.

Também foi iniciado o Gunicorn com dois workers e `--preload`: health, login, CSS e JavaScript responderam HTTP 200. A ficha da máquina e a OS usadas na revisão foram renderizadas em A4 com uma página cada.

A revisão visual estática foi feita localmente. A navegação visual interativa no navegador não pôde ser concluída por restrição do ambiente. Não foi feito deploy nem acesso ao banco de produção. Confira as telas no domínio definitivo após a atualização.

A verificação SQLite de integridade estrutural retornou `ok`. Os cinco vínculos legados inválidos (uma máquina e quatro OS) foram preservados e sinalizados; testes passando não significam que essas pendências cadastrais foram apagadas.

Para repetir os testes no pacote completo:

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q
```

Os testes usam cópias temporárias. Não usam o banco de produção.

## Pacotes e instalação

O repositório `sketchJayJay/Solutec` foi identificado como público. Nenhum banco ou documento de cliente foi enviado a ele. O pacote `Solutec_GitHub_Coolify.zip` contém somente o código; o pacote completo mantém a cópia recebida para implantação privada e preservação. Veja `DEPLOY_COOLIFY.md`.
