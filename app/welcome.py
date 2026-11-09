"""Textos educativos criados exclusivamente em perfis novos do AURORA AutoFill."""
from __future__ import annotations

from html import escape
import re


# (Nome do comando, atalho, texto com **ênfase** opcional.)
# Somente os quatro atalhos listados aqui são criados na primeira instalação.
# /ola é um exemplo didático, não um comando já cadastrado.
_TEMPLATES = (
    (
        "Boas-vindas",
        "/bemvindo",
        """👋 **Boas-vindas ao AURORA AutoFill!**

O AURORA transforma pequenos atalhos em textos completos: você prepara uma mensagem uma vez e a reutiliza nos aplicativos compatíveis.

✨ **Três coisas para experimentar:**
• Abra o comando /tutorial para aprender a criar e organizar seus textos.
• Abra /datahora para ver as datas preenchidas automaticamente.
• Crie um comando com o botão **+ Novo** e escolha seu próprio atalho.

🚀 **Pronto para usar:** nas novas instalações do Windows, o AURORA vem configurado para iniciar com o sistema, ficar minimizado na bandeja e mostrar sugestões enquanto você digita. Você pode desmarcar qualquer opção em **Configurações**.

💡 A expansão depende do campo de destino. Evite utilizar sugestões em senhas e informações sensíveis.

**Menos digitação, mais produtividade e mais tempo para você!** 🌌""",
    ),
    (
        "Atalhos e pastas",
        "/tutorial",
        """📖 **Primeiros passos com o AURORA AutoFill**

⌨️ **1. Crie um atalho**
Clique em **+ Novo**, informe um nome, um atalho começando com / e o texto que será inserido. O salvamento acontece automaticamente quando os campos estiverem completos.

Exemplo: crie /ola com a mensagem "Olá! Tudo bem?". Ao digitar /ola em um aplicativo compatível, o AURORA poderá inserir a mensagem.

✨ **2. Sugestões enquanto digita**
Digite / para visualizar seus comandos disponíveis. Use ↑/↓ para navegar, Enter ou Tab para inserir e Esc para fechar a lista. Em uma instalação nova, as sugestões já começam ativadas, mas podem ser desmarcadas em **Configurações → Produtividade**.

📁 **3. Organize seus textos**
Você também pode criar pastas para separar os comandos por assunto: Pessoal, Trabalho, Estudos ou qualquer outro. Esta pasta **Conheça o AURORA** já é um exemplo de organização.

⚡ **4. Explore os comandos dinâmicos**
No editor de um comando, clique em **Inserir comando dinâmico** para incluir datas, horas, cálculos, campos de formulário, listas de escolha, conteúdo da área de transferência e ações de teclado.

Clique no botão **?** ao lado desse menu. O guia apresenta cinco abas em ordem alfabética: **Área de transferência e cursor**, **Automações**, **Cálculos**, **Data e hora** e **Formulários interativos**. No final da aba **Data e hora**, você encontra uma tabela de códigos como %a, %A, %b e %B, com exemplos em português.

📊 **5. Insira tabelas, formas e gráficos**
Na faixa **FORMATAÇÃO**, à direita do grupo Parágrafo, abra o grupo **Inserir**. Use **Tabelas** para criar células editáveis, **Formas** para incluir figuras e **Gráficos** para montar colunas, linhas ou pizza com dados simples.

Tabelas continuam editáveis dentro do AURORA; as formas e os gráficos são salvos como imagens incorporadas. A colagem rica em outros programas depende de cada editor aceitar HTML ou imagens.

🔎 **6. Encontre seus comandos**
Use a busca na lateral ou a pesquisa global com **Ctrl + Shift + Espaço** para localizar e reutilizar seus comandos.

🛡️ **7. Proteja seus dados**
Em **Configurações → Segurança dos dados**, crie um backup completo e restaure quando precisar. Os backups são locais. Não existe conexão obrigatória com serviços em nuvem.

⚠️ Ações como Tab e Enter dependem da compatibilidade e do foco do aplicativo de destino. Não use comandos de expansão em campos de senha.

**Você pode criar pastas, atalhos e textos do seu jeito. Explore sem pressa!**""",
    ),
    (
        "Data e hora automáticas",
        "/datahora",
        """📅 **Datas e horários sem preencher manualmente**

Os comandos dinâmicos são atualizados **quando você usa o atalho**, não quando salva o texto.

📅 Data de hoje: {{data}}
🕒 Horário atual: {{hora}}
🗓️ Data e hora juntas: {{data_hora}}
⏩ Daqui a sete dias: {{data:+7}}
⏪ Ontem: {{data:-1}}

🌎 **Datas por extenso em português**
Hoje é {{data_formato:%A, %d de %B de %Y}}.
Dia da semana abreviado: {{data_formato:%a}}.
Mês por extenso: {{data_formato:%B}}.

No editor, clique no botão **?** → **Data e hora** e role até o final (ou use **Consultar códigos de formatação**) para descobrir o significado e os exemplos de %d, %m, %Y, %H, %M, %a, %A e muitos outros.

💡 Você também pode usar **Cálculos**, **Formulários interativos** e **Automações** pelo menu **Inserir comando dinâmico**. Consulte o guia antes de usar ações de teclado em outros aplicativos.""",
    ),
    (
        "Agradecimento e motivação",
        "/obrigado",
        """💜 **Obrigado por escolher o AURORA AutoFill!**

A ideia do AURORA é simples: escrever menos vezes as mesmas coisas e dedicar mais tempo ao que importa.

Comece com os comandos desta pasta, crie seus próprios atalhos e consulte o botão **?** do editor quando quiser explorar as funcionalidades dinâmicas.

Em **Configurações**, você pode escolher o tema, o comportamento de inicialização, as sugestões de comandos e a forma de proteger seus dados com backups locais.

🌌 **Que o AURORA AutoFill facilite sua rotina, um atalho de cada vez!** 🚀""",
    ),
)


def _render_model(body: str) -> tuple[str, str]:
    """Guarda texto puro para colagem e HTML básico para destinos compatíveis."""
    plain = re.sub(r"\*\*(.*?)\*\*", r"\1", body)
    plain = plain.replace("`", "")
    html = escape(body)
    html = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html)
    html = html.replace("`", "")
    html = "<html><body><p style='white-space:pre-wrap'>" + html.replace("\n", "<br/>") + "</p></body></html>"
    return plain, html


def initial_snippets() -> tuple[tuple[str, str, str, str], ...]:
    """Nome, atalho, conteúdo simples e HTML rico."""
    return tuple((title, shortcut, *_render_model(body))
                 for title, shortcut, body in _TEMPLATES)
