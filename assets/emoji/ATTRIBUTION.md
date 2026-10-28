# Créditos do seletor de emojis

**Microsoft Fluent Emoji — arte 3D.** Copyright (c) Microsoft Corporation.
Distribuída sob a licença MIT, incluída integralmente em `LICENSE-Fluent.txt`.

Fonte: https://github.com/microsoft/fluentui-emoji

Revisão: `1ffb34c752ecf5d402f04cfb4b392c77f57c54bc`.

As imagens originais foram reduzidas para 96 px e agrupadas em um atlas PNG
transparente, sem alterar as formas ou as cores. `fluent-3d.json` identifica cada
arquivo de origem e seus checksums. `scripts/build_fluent_emoji.py` reproduz o
atlas a partir dessa revisão. Os recursos são incluídos no instalador e o seletor
funciona offline.

Os gráficos são usados no seletor; os comandos armazenam emojis Unicode,
mantendo a edição e a compatibilidade com os aplicativos de destino.
