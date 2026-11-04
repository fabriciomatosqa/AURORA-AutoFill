# Backup em nuvem — versão de validação

O AURORA AutoFill mantém todos os dados e backups locais sem exigir conta ou
conexão. A opção Configurações → Segurança dos dados → Backup em nuvem
é inteiramente voluntária e não altera atalhos, banco nem atualização online.

## O que funciona nesta versão

- Conectar uma conta Google Drive ou OneDrive pelo navegador externo (OAuth 2.0 + PKCE).
- Autorização limitada ao espaço do aplicativo:
  - Google Drive: appDataFolder, oculto na interface comum.
  - OneDrive: me/drive/special/approot, pasta Apps/<nome da aplicação>, visível.
- Gerar cópia consistente usando o ZIP completo dos backups locais.
- Enviar cópia nova somente ao clicar em Enviar backup completo.
- Listar backups; baixar e validar antes de propor restauração.
- Restaurar somente após duas confirmações, criando backup de segurança local.
- Desconectar do dispositivo removendo autorização do cofre local, sem excluir a nuvem.

Não há sincronização entre PCs, agendamento automático, exclusão remota,
backup em segundo plano ou criptografia de ponta a ponta dos ZIPs. O tráfego
usa HTTPS; arquivos na nuvem seguem a proteção do respectivo provedor.

## Pré-requisitos reais

O cliente público do Google Drive já está incluído em
`assets/cloud-oauth-clients.json` para validação com as contas cadastradas em
**Público-alvo → Usuários de teste** no projeto AURORA AutoFill do Google Cloud.
Não é necessário configurar variáveis de ambiente no computador do usuário.
Enquanto o projeto estiver em **Testando**, apenas essas contas podem conectar,
e a autorização expira após sete dias, exigindo nova conexão. A validação com
conta real (login, envio e recuperação de um ZIP) deve preceder a liberação
do backup ao público. Não confundir a publicação de um instalador com a
publicação do cliente OAuth em produção no Google Cloud.

### Conexão do usuário: somente login e autorização

O usuário abre Backup em nuvem → Google Drive → Conectar minha conta, faz login
no navegador e autoriza. Não importa JSON, não configura client IDs ou segredos
e não precisa de acesso ao Google Cloud. O instalador fornece a configuração
Desktop registrada pelo responsável do projeto. Os backups permanecem na conta
de cada usuário; a autorização pessoal fica somente no cofre do sistema.

### Configuração única do projeto para os instaladores

O responsável cadastra em GitHub → Settings → Secrets and variables → Actions
um **repository secret** chamado `AURORA_GOOGLE_DESKTOP_CLIENT_SECRET`.
O valor é somente o campo `client_secret` do cliente **AURORA AutoFill Desktop**
cujo ID já está em `assets/cloud-oauth-clients.json`, não o arquivo JSON inteiro.
Esse valor é obtido no Google Cloud uma única vez pelo responsável e não deve
ser solicitado aos usuários finais.

A compilação gera `app/_cloud_oauth.py`, ignorado pelo Git, e o PyInstaller
inclui o registro no executável. O valor não é impresso pelo preparador nem
publicado no código-fonte do repositório. Como todo cliente OAuth Desktop é
público, o registro compartilhado incluído no aplicativo pode ser extraído do
instalador; ele não substitui PKCE nem dá acesso à conta de ninguém. Tokens de
usuários, chaves de serviço e credenciais de clientes web não entram na build.

PRs recebem uma configuração sintética marcada como teste, sem acesso ao secret
real. Essa configuração não é aceita na autenticação normal nem no teste de
um pacote de distribuição. Builds de distribuição sem o repository secret
falham antes da geração dos instaladores. O teste executado dentro do binário
compilado exige a configuração embutida e não aceita o cofre local como prova.
Isso impede publicar outra versão que exija arquivos dos usuários.

Para quem já conectou o piloto, a autorização e a configuração local existentes
continuam funcionando. O registro embutido tem prioridade, permitindo atualizar
a configuração do projeto sem pedir nova importação aos usuários.

O OneDrive ainda não possui cliente registrado nesta distribuição e permanece
indisponível até a configuração do seu próprio ID Microsoft.

OAuth exige registro de um aplicativo no Google e na Microsoft. NÃO é possível
concluir a integração com as contas apenas escrevendo o código, sem client IDs
e autorização da aplicação junto aos provedores. IDs de cliente são públicos,
mas o valor de configuração Desktop não entra no Git público, logs ou backup.
Refresh tokens pessoais ficam exclusivamente no cofre do sistema.

1. Google Cloud: habilite Google Drive API, configure tela de consentimento
   e crie cliente OAuth tipo Aplicativo para computador, autorizando apenas
   o escopo https://www.googleapis.com/auth/drive.appdata. Em modo Teste,
   cadastre os usuários de teste.
2. Microsoft Entra: registre AURORA AutoFill com contas pessoais Microsoft,
   plataforma Aplicativos móveis e desktop e redirect URI
   http://localhost/callback (porta dinâmica); habilite cliente público e a
   permissão delegada Files.ReadWrite.AppFolder e offline_access.
3. Configure os IDs públicos em assets/cloud-oauth-clients.json na build,
   ou use as variáveis de ambiente AURORA_GOOGLE_CLIENT_ID e
   AURORA_MICROSOFT_CLIENT_ID antes de abrir o programa.
4. Instale requirements.txt. O cofre do Windows Credential Manager ou
   Secret Service do Linux precisa estar funcional. Nunca armazenar
   tokens de atualização em texto puro.

Cada client ID identifica seu próprio espaço da aplicação. Se usar outro
client ID em outro computador, o provedor poderá mostrar uma pasta diferente.

## Teste seguro

1. Faça backup local e mantenha cópia externa.
2. Abra Backup em nuvem, selecione o provedor e conecte a conta.
3. Envie um novo backup e confirme que aparece na lista.
4. Baixe o backup e escolha NÃO na pergunta de restauração. Confirme
   que o banco local não foi alterado.
5. Teste a restauração somente em perfil descartável, após copiar o
   backup local de produção para fora do computador.

## Limites

- Limite de 120 MiB por arquivo nesta etapa experimental.
- Download salvo como nova cópia no diretório local de backups.
- read_backup valida o ZIP antes de apresentar opção de restauração.
- Credenciais ficam no cofre do sistema via keyring, fora do banco e do ZIP.
- Se o cofre estiver ausente, a conexão é recusada com aviso.
- Desconectar localmente não revoga o acesso no painel do provedor.
- No Google OAuth em modo Teste, a autorização pode vencer e exigir login.
- CI não comprova conexão real com conta Google ou Microsoft sem os
  registros OAuth. Não substituir testes práticos por simulações.

## Documentação oficial

Google: https://developers.google.com/workspace/drive/api/guides/appdata
Google OAuth: https://developers.google.com/identity/protocols/oauth2/native-app
OneDrive: https://learn.microsoft.com/graph/onedrive-sharepoint-appfolder
Microsoft OAuth: https://learn.microsoft.com/entra/identity-platform/scenario-desktop-app-registration
