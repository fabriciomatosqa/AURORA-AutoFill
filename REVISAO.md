# Revisão do ciclo 0.6.1

Revisão de confiabilidade, interface e distribuição iniciada em 16/10/2026.

## Teams para Windows, cursor, áudio e ícones — 16/10/2026

- Chromium/WebView consulta o editor por UI Automation também para comandos sem marcador. A validação aceita o processo filho do editor somente quando sua árvore pertence à janela em primeiro plano; mantém a identidade do campo e a conferência do texto/seleção antes de colar.
- A seleção do atalho é confirmada por UIA antes de enviar Ctrl+V nesses editores. Não há reenvio automático de colagem. O prazo de confirmação tolera processamento assíncrono do destino.
- O marcador `{{cursor}}` usa posição direta: seleção nativa recolhida no ponto exato ou intervalo UIA. Não percorre o conteúdo com setas. Prefixos são conferidos com coordenadas UTF-16 e tratamento de CRLF, acentos e emojis.
- O arquivo Water Droplet 2, de floraphonic, fornecido pelo usuário substitui o efeito sintético. Toca ao salvar e após uma expansão confirmada, respeitando o volume e a opção de som. Origem e licença atualizadas.
- Botões de configurações, edição, pastas, importação/exportação, backup e atualização usam SVG com cores explícitas e nomes acessíveis.
- 201 testes locais aprovados, além do teste real da ponte UIA em uma janela Windows com dados sintéticos: seleção exata do atalho, início/meio/fim do texto, Unicode e rejeição de estado antigo. Capturas do editor e das configurações revisadas.
- O teste real do UIA integra o pipeline Windows. O Teams instalado do usuário não foi acessado: a validação final no Teams para Windows depende do teste da nova compilação nesse ambiente. O Teams no navegador não foi relatado como afetado.

## Atualização silenciosa — 16/10/2026

- O botão **Atualizar agora** autoriza download, verificação, backup e instalação; o aplicativo novo não solicita uma segunda confirmação de instalação. Cancelar o download, inclusive quando a conclusão já está enfileirada, impede iniciar o instalador.
- No Windows, a atualização acontece sem o assistente de “Avançar” e o AURORA reabre automaticamente. A primeira instalação manual mantém o assistente; uma instalação silenciosa comum não abre o aplicativo.
- O novo instalador identifica a chamada feita pela versão `0.6.1-161026` já instalada e executa a atualização automaticamente, mostrando apenas o progresso. Essa versão antiga ainda pode mostrar sua confirmação de instalação dentro do aplicativo durante a transição. O aplicativo novo usa o modo totalmente silencioso.
- AppId, diretório de instalação, dados e preferências são mantidos. Falhas de backup ou integridade mantêm o programa aberto; edições pendentes ainda podem interromper a atualização para evitar descarte sem aviso.
- Rodapé simplificado para **V&lt;versão&gt;**, sem a palavra “Versão”; o número completo com data é preservado.
- 197 testes locais aprovados. O pipeline Windows também instala e atualiza o pacote real em um runner descartável, verificando substituição dos arquivos, reabertura, compatibilidade com a chamada antiga e preservação de dados sintéticos. A limpeza do perfil temporário aguarda por até cinco segundos a liberação de arquivos pelo Windows, sem repetir nem ignorar as verificações. Esse teste recusa execução no computador do usuário.

## Teste de atualização com data — 16/10/2026

- Formato público alterado para `0.6.1-161026`, exibindo dia, mês e ano da publicação. Datas seguem o horário de Brasília; atualizações adicionais no mesmo dia recebem `.2`, `.3` etc.
- A versão instalada `0.6.1-dev.22.1` não considera um sufixo numérico mais recente que `dev`. Uma publicação de transição `0.6.1-update.20261016` oferece os mesmos bytes dos instaladores com nomes e checksums compatíveis. Depois de instalar, o programa exibe a versão com data solicitada.
- O atualizador novo considera data e referência de transição a mesma versão, evitando oferecer a mesma instalação novamente. Compara as datas pelo calendário, incluindo viradas de mês/ano e dias com zero à esquerda.
- 193 testes locais aprovados, incluindo calendário, revisões, arquivos de transição, consentimento e ausência de oferta repetida. O pipeline também executa o código exato do atualizador antigo, obtido do commit `583ff467efc40c2b6ebfe1fcfa2b7ce216c60730`, para descobrir, baixar e conferir o SHA256 dos dois instaladores sem executá-los.
- A instalação pelo assistente e a reabertura no computador do usuário continuam sendo a parte manual deste teste remoto. Os testes automatizados não instalam sobre o perfil pessoal.

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

- 172 testes automatizados aprovados no Windows com Python 3.14 e PySide6 6.12, em perfis temporários.
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
