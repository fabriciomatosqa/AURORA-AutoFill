# Revisão do ciclo 0.6.1

Revisão de confiabilidade, interface e distribuição iniciada em 16/10/2026.

## Problemas encontrados e corrigidos

| Área | Problema | Correção |
| --- | --- | --- |
| Atualizações | A consulta ignorava versões de teste; artifacts do Actions não apareciam no app. | Descoberta de Releases e Pre-releases, versões únicas por compilação/tentativa e publicação após aprovação Windows/Linux. |
| Atualizações | Comparação reconhecia somente versões X.Y.Z. | Comparação SemVer, incluindo números de desenvolvimento e promoção para estável. |
| Atualizações | Lançamento incompleto podia esconder outro já pronto. | Oferta exige instalador e manifesto compatíveis; versões sem assets são ignoradas. |
| Instalação | Origem, tamanho, cancelamento e alteração posterior do arquivo exigiam mais proteção. | HTTPS e repositório oficial, limites de tamanho, SHA256, cancelamento sem Content-Length e nova conferência local antes de executar. |
| Encerramento | Fechar durante consulta/download podia destruir uma thread ativa. | Cancelamento e saída adiada até o término da operação, com interface responsiva. |
| Dados | JSON perdia pastas vazias e invertia a ordem. | Exportação/importação preservam pastas, formatação e ordem; nomes acentuados distintos permanecem separados. |
| Exportação | Falha durante escrita podia destruir uma exportação anterior. | Gravação temporária e substituição após conclusão. |
| Restauração | Estrutura incompatível ou preferências inválidas podiam falhar depois de trocar o banco. | Validação e migração do arquivo temporário; preferências normalizadas; recuperação do banco anterior em falha. |
| Desfazer | Estado antigo podia sobreviver à restauração de backup. | A restauração limpa a fila de operações; falhas ao desfazer mantêm a opção até o prazo expirar. |
| Desfazer | Um comando poderia ter a pasta removida antes de ser recuperado. | Recuperação da pasta original quando necessário. |
| Configurações | Falha ao salvar podia deixar controles divergindo do valor persistido. | Controles retornam aos valores anteriores, incluindo volume e prévia de áudio. |
| Inicialização | Política de acesso ao registro podia impedir a abertura da janela. | Falha de leitura da inicialização automática não impede abrir o aplicativo. |
| Execução | Duas cópias podiam processar o mesmo teclado. | Uma instância por pasta de dados, com liberação ao encerrar. |
| Aparência | Corpo/viewport de configurações herdavam fundo preto nativo. | Superfícies azuis explícitas, checkboxes e divisores consistentes com o tema. |
| Menus | Área externa aos cantos arredondados podia ficar preta. | Popup sem moldura/sombra nativa e fundo transparente nos cantos. |
| Áudio | Som precisava se aproximar de uma gota; o cache podia manter áudio antigo. | Glube original de 0,32 s, volume independente e cache por conteúdo. |
| Versões | Aplicativo, instalador e tag podiam divergir. | Base centralizada e metadados gerados antes dos testes/empacotamento. |

## Validação executada

- 167 testes automatizados aprovados no Windows com Python 3.14 e PySide6 6.12, em perfis temporários.
- Capturas das telas inicial, editor e configurações no tamanho normal e no tamanho mínimo; verificação visual do menu de pastas.
- Teste de pixels da central sob paleta nativa escura, confirmando o fundo azul.
- Regressões para consentimento, cancelamento, backup antes da instalação, recusa de arquivo modificado e fechamento durante atualização.
- Regressões da expansão, foco, Unicode, cursor, área de transferência, pastas, ordenação e recuperação mantidas.

O pipeline também executa esses testes em Windows/Linux, verifica recursos e dados dos pacotes, abre os executáveis congelados em perfis temporários e verifica o caminho público de atualização após publicar os arquivos. O resultado de cada compilação pode ser consultado no GitHub Actions.

## Validação manual restante

- Primeira instalação sobre a v0.6.0: precisa ocorrer pelo novo instalador, porque o atualizador antigo só procura versões estáveis.
- Avaliar o som em **Configurações → Ouvir gota de confirmação**, no volume habitual do computador.
- Testar a expansão nos aplicativos efetivamente utilizados, especialmente Word, Teams e editores de navegador.
- Na próxima compilação publicada, validar o fluxo completo de atualização no Windows instalado, incluindo o assistente e a reabertura do aplicativo.

Estas compilações permanecem identificadas como versões de teste. Formulários dinâmicos continuam fora do escopo e não foram implementados.
