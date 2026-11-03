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

OAuth exige registro de um aplicativo no Google e na Microsoft. NÃO é possível
concluir a integração com as contas apenas escrevendo o código, sem client IDs
e autorização da aplicação junto aos provedores. IDs de cliente são públicos,
mas client secrets e refresh tokens jamais entram no GitHub, logs ou backup.

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
