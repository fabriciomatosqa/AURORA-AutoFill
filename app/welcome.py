"""Textos educativos mostrados exclusivamente em perfis novos do AURORA AutoFill."""
from __future__ import annotations

from html import escape
import re


# (Nome do comando, atalho, texto com **ênfase** opcional.)
# Os atalhos no tutorial são hipotéticos; /ola não é um comando predefinido.
_TEMPLATES = (
    (
        "Boas-vindas",
        "/bemvindo",
        """Olá! 👋 Seja muito bem-vindo ao **AURORA AutoFill**!

Estamos felizes em ter você por aqui! ✨

Com o AURORA AutoFill, suas tarefas do dia a dia ficarão mais simples, rápidas e práticas.

Imagine escrever textos inteiros digitando apenas algumas letras. É exatamente isso que o AURORA AutoFill faz por você!

**Menos digitação, mais produtividade e mais tempo para o que realmente importa!** 🚀""",
    ),
    (
        "Atalhos e pastas",
        "/tutorial",
        """✨ **Você sabia que pode escrever textos completos usando apenas pequenos atalhos?**

Com o **AURORA AutoFill**, é muito fácil!

⌨️ **Como funcionam os atalhos?**

Imagine que você cadastrou o atalho `/ola` com a mensagem:

"Olá! Tudo bem com você? Espero que esteja tendo um ótimo dia!"

Agora, sempre que você digitar `/ola` em um campo de texto compatível, o AURORA AutoFill poderá substituí-lo automaticamente pela mensagem completa.

Você pode criar quantos atalhos precisar, personalizar suas mensagens e editar tudo quando quiser!

📁 **Organize seus textos com pastas!**

Para facilitar ainda mais sua rotina, o AURORA AutoFill permite criar pastas para organizar seus atalhos por assunto, categoria ou preferência.

Por exemplo:

• 📁 Pessoal — mensagens para amigos e familiares.
• 📁 Estudos — anotações e textos utilizados nos estudos.
• 📁 Dia a dia — mensagens e informações que você utiliza frequentemente.

Assim como esta pasta **Conheça o AURORA**, você pode criar suas próprias pastas e manter tudo organizado e fácil de encontrar!

💡 **Uma dica especial:** comece criando alguns atalhos para as mensagens que você mais digita. Aos poucos, você perceberá quanto tempo consegue economizar!

🚀 **Você cria uma vez, organiza do seu jeito e ganha tempo todos os dias!**""",
    ),
    (
        "Data e hora automáticas",
        "/datahora",
        """📅 **Que tal deixar o AURORA AutoFill cuidar da data e da hora para você?**

Além de expandir textos, o AURORA AutoFill permite utilizar informações dinâmicas, como a data e a hora atuais.

Assim, você não precisa atualizar essas informações manualmente toda vez que utilizar um texto.

Por exemplo:

📅 Data: {{data}}
🕒 Hora: {{hora}}

Esses valores são preenchidos automaticamente no momento da utilização do atalho. Você também pode utilizar {{data_hora}} em seus próprios textos.

✨ **Pequenos recursos que fazem uma grande diferença na sua rotina!**""",
    ),
    (
        "Agradecimento e motivação",
        "/obrigado",
        """💜 **Obrigado por escolher o AURORA AutoFill!**

É uma alegria saber que nosso programa fará parte do seu dia a dia.

O AURORA AutoFill foi criado com um propósito simples: facilitar sua vida, economizar seu tempo e tornar suas atividades mais práticas.

Lembre-se: produtividade não significa fazer mais coisas o tempo todo, mas encontrar maneiras inteligentes de fazer o que realmente importa.

Cada segundo economizado é uma oportunidade de dedicar mais tempo a você, aos seus sonhos e às pessoas que ama.

🌌 **Que o AURORA AutoFill seja uma pequena ferramenta para grandes conquistas!**

Obrigado por fazer parte dessa jornada! 🚀""",
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
