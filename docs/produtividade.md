# Produtividade avançada — AURORA AutoFill

## Formulários

Tokens salvos como texto no editor. O valor do usuário só existe na execução e
não é gravado no corpo do comando.

| Sintaxe | Uso |
| --- | --- |
| `{{campo:Nome}}` | Campo livre |
| `{{campo:Nome|Joana}}` | Campo com valor inicial |
| `{{escolha:Status|Aberto|Concluído}}` | Lista obrigatória |

Até 12 campos diferentes por comando e 12 opções por lista. Campos repetidos
com a mesma definição compartilham a resposta. Campos inconsistentes e
respostas muito grandes são rejeitados.

O diálogo aparece no momento de escolher o modelo. Se for cancelado,
nenhuma substituição do atalho digitado é tentada. O resultado é montado
na memória; o valor preenchido não fica no banco nem nos relatórios.

Em Windows, o sistema tenta reconectar-se ao mesmo campo de destino e só
executa substituição automática após comprovar a presença do atalho.
Quando não é possível, oferece resultado copiado para Ctrl+V. No Linux,
a colagem manual evita apagar texto incerto em outros aplicativos.

## Pesquisa global e sugestões

O painel lateral contém **Pesquisa global**, que também é aberta por
`Ctrl+Shift+Espaço` quando o listener de teclado global está funcionando.
A busca alcança título, atalho e conteúdo das pastas.

**Sugestões flutuantes** devem ser habilitadas conscientemente em Configurações:
elas são opt-in, porque apps de expansão não conseguem distinguir todos os
campos sensíveis. Após `/` e mais dois caracteres, mostram até cinco opções.
O balão é somente informativo: pressione `Ctrl+Shift+Espaço` para pesquisar
e escolher, sem que o balão intercepte teclas.

## Variáveis avançadas

A versão anterior continua aceitando as variáveis `{{data}}`, `{{hora}}`,
`{{data_hora}}`, `{{clipboard}}`, `{{area_transferencia}}` e `{{cursor}}`.

- `{{data:+7}}`: daqui a sete dias.
- `{{data:-30}}`: trinta dias atrás.
- `{{data_formato:%d/%m/%Y}}`: dia/mês/ano; outros formatos seguros
  do strftime permitidos.
- `{{calculo:12.5*3}}`: 37.5, limitado à aritmética simples; nomes,
  arquivos, funções e execução de código são proibidos.

As variáveis são avaliadas por uso; datas usam o horário do computador.

## Etapas por teclado

```text
{{campo:Nome}}{{tab}}{{campo:Email}}{{tab}}Pendente{{espera:200}}{{enter}}
```

- `{{tab}}` navega para o próximo campo.
- `{{enter}}` envia Enter.
- `{{espera:200}}` aguarda 200 ms. Intervalo permitido 50–2000 ms.
- São permitidas até 20 etapas por execução e no máximo 5000 ms de espera.

Uma confirmação explica os efeitos antes da sequência. No Windows o mecanismo
requer a janela do destino e, no primeiro trecho de um atalho digitado, um
intervalo de texto verificável. A cada próxima etapa confirma que continua
no mesmo aplicativo; cancela se houver mudança. Não há cliques por coordenadas.

O mecanismo é experimental, não garante um aplicativo de destino específico
e não deve ser empregado em campos sensíveis, envios irreversíveis ou processos
que não admitem revisão. Em Linux são oferecidas alternativas de copiar texto,
não um fluxo de pressionamentos cegos.

## Estatísticas de uso

Tabela `usage_daily(day, snippet_id, shortcut, uses)` no banco do usuário.
Somente sucessos confirmados pelo mecanismo tradicional contam. Indicadores:
dia, mês, ano, total, evolução mensal por 12 meses e modelos mais utilizados.

Limpar métricas não apaga comandos. Excluir um modelo não armazena conteúdo
capturado; o histórico agregado pode manter o atalho usado naquele momento.
Não há envio de estatísticas por rede.

## Busca FTS5

Índice de texto completo SQLite sobre título, atalho e texto simples. Triggers
mantêm o índice com inclusões, alterações e exclusões; migração constrói índice
uma vez para bases existentes. Com SQLite sem FTS5, e quando não houver
resultado indexado, o código volta à pesquisa `LIKE` anterior.

A busca por prefixo de palavra é acelerada; busca de trechos no meio da palavra
permanece compatível pelo fallback. Resultados preservam ordem personalizada.

## Regressões prioritárias

1. Abrir e fechar formulários sem apagar o texto do aplicativo externo.
2. Confirmar foco e atalho antes de substituição em Windows.
3. Testar Ctrl+Shift+Espaço, sugestões desligadas/ligadas e pesquisa por acento.
4. Validar data na virada do mês/ano e cálculos inválidos.
5. Comprovar interrupção quando o aplicativo muda durante a sequência.
6. Verificar contadores de sucesso, exclusão e limpeza, sem conteúdo de teclas.
7. Testar migração de banco antigo e restauração de backup completo.
