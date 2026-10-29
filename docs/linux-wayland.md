# Expansão de atalhos no Ubuntu 26.04 / GNOME Wayland

O AURORA AutoFill usa **evdev** (eventos do teclado físico do Linux) para
reconhecer sequências como \`/bemvindo\` e **uinput** para enviar a substituição
pelo teclado virtual. Funciona com Wayland nativo quando o usuário explicitamente
autoriza os dispositivos. Não usa XWayland, não exige executar o aplicativo como
root e não desativa a segurança global do GNOME.

## Antes de autorizar: privacidade e limitações

O acesso ao grupo \`input\` **permite ler eventos de teclados e outros dispositivos
de entrada**, inclusive enquanto outros aplicativos estão em primeiro plano.
É uma permissão poderosa concedida à conta inteira (não apenas ao AURORA).
Conceda somente em máquina pessoal confiável. O AURORA mantém apenas um pequeno
buffer volátil dos caracteres recentes para comparar atalhos, sem salvar as teclas
nem transmiti-las. Você pode pausar a captura no botão de estado.

O mecanismo Wayland não consegue inspecionar com segurança o conteúdo do campo
ou verificar por UIA como no Windows. A expansão é **melhor esforço**, adequada
a campos comuns de texto; ela não pode garantir substituição em todos os editores
nem detectar com segurança campos de senha, sessão bloqueada, outros layouts
selecionados em tempo real ou ambientes isolados (Flatpak/Snap).

A implementação nesta versão não suporta \`{{cursor}}\` em aplicativos externos
Wayland. Se o comando possuir esse marcador, o AURORA o mantém sem alterar o
destino. O texto HTML, imagens e formatação dependem do aplicativo receptor.

## 1. Instalação e permissão (uma única vez)

Instale o pacote Linux AURORA atualizado (DEB do GitHub Releases) e rode
**no Terminal do próprio Ubuntu**, com sua conta normal:

\`\`\`bash
# Crie um ponto de restauração/snapshot da VM antes de mudar permissões.
sudo usermod -aG input "$USER"
printf '%s\n' 'KERNEL=="uinput", GROUP="input", MODE="0660"' \
  | sudo tee /etc/udev/rules.d/70-aurora-uinput.rules
sudo modprobe uinput
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=misc
\`\`\`

**Encerre completamente a sessão e faça login novamente** para aplicar a
associação ao grupo. Não execute o AURORA com \`sudo\` (isso pode danificar
a propriedade do banco de dados pessoal e expor a sessão).

Diagnóstico:

\`\`\`bash
echo "$XDG_SESSION_TYPE"         # wayland
id -nG                         # deve incluir input
ls -l /dev/uinput
ls -l /dev/input/event*
\`\`\`

Reabra o AURORA. O topo deverá indicar **Atalhos ativos**. Se não funcionar,
clique no indicador **Atalhos indisponíveis** para ver o motivo técnico e
tentar novamente. A inicialização nunca deve fingir que os atalhos estão
ativos se a permissão ou o dispositivo não estiver acessível.

## 2. Teclado e layout

Por padrão, o AURORA procura o primeiro layout definido pelo GNOME em
\`org.gnome.desktop.input-sources sources\` e interpreta os códigos físicos via
\`libxkbcommon\`, sem usar a tradução de teclas do XWayland.

Se seu layout padrão for diferente do layout ativo, inicie o AURORA com
\`AURORA_WAYLAND_LAYOUT=br aurora-autofill\` ou \`=us\` para diagnóstico.
A mudança de layout em tempo real ainda não é detectada. Caracteres gerados por
IME e teclados virtuais não são eventos físicos evdev e não expandem.

## 3. Revogar acesso

Se não quiser mais conceder essas permissões:

\`\`\`bash
sudo gpasswd -d "$USER" input
sudo rm /etc/udev/rules.d/70-aurora-uinput.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=misc
\`\`\`

Saia da sessão e faça login novamente. Assim o grupo adicional é revogado e o
dispositivo uinput retorna às regras padrão do sistema.

## 4. Funcionamento em outros sistemas

- **Windows:** mantém monitor anterior (pynput/SendInput/UIA/Word).
- **Linux X11:** mantém monitor anterior (pynput/Xorg) sem exigir evdev/uinput.
- **GNOME Wayland:** novo backend evdev/uinput apenas com acesso explícito.
- **Sem permissões:** o aplicativo abre para editar comandos normalmente,
  enquanto o indicador informa que os atalhos estão indisponíveis.

O CI usa testes unitários simulados e não substitui um teste real do
GNOME Wayland na sua máquina virtual. Evite usar atalhos de expansão em
campos sensíveis e confira o resultado antes de enviar informações.
