# Solutec - revisão de 18/11/2026

## Atualização 3.2 — exclusão e identidade visual

Criada a opção **Excluir máquina** para a matriz, na ficha e na conferência das máquinas sem cliente. A página mostra a identificação do equipamento e a quantidade de vínculos antes da confirmação pelo número do cadastro. A exclusão faz backup consistente antes de escrever, remove a ficha e os registros dos anexos, desvincula as OS e mantém seus itens, observações e clientes. Os arquivos físicos e o registro administrativo ficam preservados para recuperação. Falhas no backup impedem a exclusão; falhas durante a transação desfazem as mudanças.

A atualização apenas disponibiliza a função: a máquina #1 não foi excluída automaticamente e os arquivos originais de `seed/` continuam inalterados.

As quatro fotografias recebidas foram convertidas para WebP e incluídas no painel e na galeria. O login e a apresentação decorativa das fichas passaram a usar fotografias reais. Elas não foram atribuídas como fotos de máquinas de clientes.

O arquivo oficial da logo da Solutec não veio entre os anexos. Foi criada a tela **Identidade visual** para a matriz carregar, trocar ou remover a marca, que aparece no menu, login e cabeçalhos impressos. A logo é persistida no volume de dados e incluída no backup completo. Até o envio, a identificação em texto da Solutec é exibida; Bruthor continua identificado como fabricante.

**143 testes automatizados passaram** na versão 3.2. A nova cobertura verifica exclusão de órfãos e arquivados, confirmação, acesso administrativo, CSRF, preservação dos registros e arquivos, backup anterior, rollback em falhas, logo persistente, validação de upload, acesso à marca ativa, remoção e backup da identidade.

## Atualização 3.1 - OS e cabeçalhos

Criada a aba exclusiva **Ordens de serviço**, acessível no computador e no celular. Ela lista todas as OS da conta, com busca por número, cliente, equipamento, série, motor e descrição; período, paginação e filtro de vínculos pendentes. As OS antigas continuam visíveis, com acesso ao documento e à impressão/PDF.

O painel agora aponta seu indicador de OS para essa aba. O botão Nova OS leva à escolha do cliente e já abre a área do atendimento no cadastro escolhido.

CNPJ **45.154.368/0001-42** e telefone **(32) 9 9988-5977** adicionados à identificação do sistema e dos cabeçalhos das OS e fichas impressas. A matriz recebe esses dados por migração aplicada uma vez, com cópia anterior do banco. Outras revendas e os dados dos clientes são preservados.

**122 testes automatizados passaram** na versão 3.1, incluindo histórico, pesquisa, período, paginação, isolamento das revendas, cabeçalhos e idempotência da atualização institucional.

## Revisão visual 3.0

Nova direção visual em azul profundo e laranja, com tema escuro por padrão e opção de tema claro. A escolha fica salva no navegador. O painel ganhou uma imagem ilustrativa, números em destaque, indicadores de vínculo calculados a partir do cadastro real e atalhos redesenhados.

O inventário agora tem visualização em cards e em lista. A ficha da máquina recebeu uma capa, série em destaque e áreas mais definidas para proprietário, histórico e documentos. As adaptações também atingem login, clientes, formulários e conferência de cadastros.

Os 94 testes funcionais passaram novamente após a revisão. Também foram verificados por DOM a troca de tema, a preferência de visualização e a abertura/fechamento do menu. A inspeção visual usou renderização estática local; não representa uma validação interativa em navegador de produção.

Esta revisão altera apenas apresentação e preferências locais de visualização. O banco e os PDFs originais continuam preservados.

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

Há forte indício de cadastro antigo duplicado do equipamento da ficha #2, mas o proprietário do registro #1 não foi presumido. Consulte a ficha #1 para comparar com a #2. Após conferir os documentos, o administrador pode corrigir o proprietário, arquivar o cadastro ou usar Excluir máquina após conferir sua identidade. Arquivar é reversível e preserva os dados, documentos e OS.

## Outras pendências reais encontradas

| Identificador | Valor | Máquinas / proprietários |
| --- | --- | --- |
| Série | 24070253 | #5 Gilberto Fernandes de Carvalho; #14 Jaime Ferreira da Silva Neto |
| Motor | L810723226B | #5 Gilberto Fernandes de Carvalho; #14 Jaime Ferreira da Silva Neto |
| Motor | L820310658B | #9 Edmar Fialho; #10 Laudenir Monteiro dos Santos |

Somados aos identificadores das máquinas #1/#2, são cinco grupos repetidos, envolvendo seis máquinas. Os registros #5/#14 têm notas e datas diferentes; confira se é transferência ou erro antes de alterar. Não foi feita fusão automática.

Há quatro OS com cliente ausente: #1 aponta para o antigo cliente #5; #2, #3 e #4 apontam para o antigo cliente #1. A OS #4 também está vinculada à máquina #1. Agora essas OS podem ser abertas, impressas e consultadas pela matriz. A área **Conferir cadastros** permite ajustar o vínculo com confirmação e cópia anterior do banco.

Dois PDFs da máquina #8 estão no disco sem referência na tabela de anexos. Eles foram preservados e seguem no backup completo. Confira se são cópias antigas antes de criar novos vínculos.

A identificação da matriz foi atualizada na versão 3.1 com o CNPJ e o telefone fornecidos pelo usuário. Nenhum dado institucional das outras revendas foi substituído.

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

**143 testes automatizados passaram**, sem falhas. Cobrem páginas existentes, busca, cadastro/edição, valores inválidos, duplicidade, observações, upload/PDF, remoção de anexos, OS, isolamento das revendas, sessão, formulários, backup, arquivamento/restauração, migrações, banco novo, troca de proprietário, QR Code e senha administrativa.

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
