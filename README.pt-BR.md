# WoR Character Tools

Porte mods de personagem do **Guitar Hero World Tour: Definitive Edition** para o **Guitar Hero: Warriors of Rock** (Xbox 360 / Xenia). Também dá para editar as texturas dos personagens originais.

*[Read in English](README.md)*

- **Python 3 puro, sem dependências.**
- **Funciona sobre uma cópia extraída do jogo.** Faça backup antes.
- **Testado no Xenia Canary.** Um personagem do GHWT:DE, com esqueleto customizado, aparece no *Select Rocker* com nome e descrição próprios. Ele também já tocou uma música na guitarra. Os outros instrumentos ainda não foram testados.

> Este repositório **não contém nenhum arquivo do jogo**. Você precisa da sua própria cópia do Guitar Hero: Warriors of Rock.

---

## O que você precisa

| | |
|---|---|
| **Python 3.8+** | [python.org](https://www.python.org/). Use `py` no Windows e `python3` nos outros sistemas. |
| **Guitar Hero: Warriors of Rock (X360)** | Extraído numa pasta, por exemplo com o [extract-xiso](https://github.com/XboxDev/extract-xiso). |
| **[Xenia Canary](https://github.com/xenia-canary/xenia-canary)** | Para jogar o jogo extraído. |
| **Um mod de personagem do GHWT:DE** | Pasta com o `character.ini`, os `.skin.xen`/`.tex.xen` que ele usa e, se houver, os `.ske.xen` do esqueleto customizado. |
| *(opcional)* `ghwor_keys.txt` | Vem do [Guitar Hero SDK](https://gitgud.io/fretworks/guitar-hero-sdk) (`SDKCode/Checksums`). Serve só para mostrar nomes legíveis nas listagens. |

As ferramentas acham a pasta `data` do jogo sozinhas se ela estiver ao lado delas. Se não estiver, aponte manualmente:

```bat
set WOR_DATA=D:\Jogos\Guitar Hero - Warriors of Rock\data
```

---

## Passo a passo: colocar um personagem do GHWT:DE no WoR

### 1. Extraia o jogo

```bat
extract-xiso -x "Guitar Hero Warriors of Rock.iso"
```

Abra uma vez o `default.xex` extraído no Xenia, para confirmar que o jogo em si funciona.

### 2. Baixe as ferramentas

Baixe ou clone este repositório em qualquer lugar. Ao lado da pasta do jogo é um bom lugar:

```
MinhaPasta\
  Guitar Hero - Warriors of Rock\   <- jogo extraído (tem data\ e default.xex)
  wor-character-tools\              <- este repositório
  MeuPersonagem\                    <- o mod do GHWT:DE (character.ini, Content\..., Assets\...)
```

### 3. Porte e instale o personagem

```bat
cd wor-character-tools
py wor_port.py install ..\MeuPersonagem
```

O comando faz tudo:
1. Lê o `character.ini`: nome, descrição, gênero, malha e esqueleto customizado.
2. Converte as texturas do formato de PC para o do Xbox 360 (tiling, troca de bytes, mipmaps), sem perder qualidade. Texturas maiores que 1024 px são reduzidas descartando o primeiro nível de mip.
3. Converte a malha do GHWT PC para o WoR: vértices, UVs, normais e materiais.
4. Grava os arquivos no jogo e registra o personagem na lista do *Select Rocker*.

Os arquivos convertidos também ficam salvos em `wor_build\<nome>\`.

Opções úteis:

```bat
py wor_port.py install ..\MeuPersonagem --name "Nome na Tela" --blurb "Descrição curta"
py wor_port.py install ..\MeuPersonagem --max-tex 2048          :: mantém texturas de 2048 px (usa mais memória)
py wor_port.py install ..\MeuPersonagem --replace Johnny_1      :: substitui um roqueiro existente
```

### 4. Comece com um save novo (importante!)

O WoR copia os perfis dos roqueiros **para dentro do save** quando o save é criado. Um save feito antes da instalação não vai mostrar o personagem novo.

No Xenia, o save fica em:

```
xenia_canary\content\<id do perfil>\41560883\00000001\Progress
xenia_canary\content\<id do perfil>\41560883\Headers\00000001\Progress.header
```

Mova os dois para outro lugar, como backup, em vez de só apagar. Depois abra o jogo e deixe ele criar um save novo.

### 5. Jogue

Abra o **Select Rocker**. Com as opções padrão, o personagem novo fica entre *Casey Lynch* e *Judy Nails*.

### Desinstalar

```bat
py wor_port.py uninstall
```

Isso devolve todos os arquivos do jogo que as ferramentas modificaram. Na primeira modificação de cada arquivo, elas guardam uma cópia `.bak` dele.

---

## Limitações

- **Uma vaga de personagem novo.** O WoR não aceita perfis extras: acrescentar um trava o jogo na tela de título. As ferramentas reaproveitam o perfil escondido e sem uso `GH_Rocker_Casey_Cut_Skin` e o corpo dele, `Casey_Cut_Skin`. Instalar outro personagem sobrescreve essa vaga. Para ter mais personagens, use `--replace <roqueiro>`, por exemplo `Johnny_1`, `Axel_1`, `Judy_1`, `Lars_1`, `Pandora_1` ou `Eddie_1`.
- **A foto do menu e os instrumentos vêm do perfil reaproveitado** (os da Casey Lynch).
- **As animações e o material base** vêm de um roqueiro modelo: `Johnny_1` para `Gender=Male` e `Casey_1` para feminino. Dá para trocar com `--template`.
- **Os materiais são simplificados.** Cada parte vira um material opaco com normal, difusa e specular:
  - a maior malha (o corpo) recebe a normal map do mod, se houver exatamente uma;
  - as outras partes recebem uma normal neutra;
  - transparência e recortes por alpha ainda não são convertidos.
- **Texturas:** DXT1 e DXT5 são suportadas. Outros formatos interrompem a conversão com uma mensagem de erro.
- **Sem física de roupa (cloth)** no personagem novo.
- **Esqueletos:** o WoR aceita os esqueletos customizados do GHWT como estão, porque o formato é o mesmo. Se o mod não tiver esqueleto customizado, é usado o do modelo.

---

## Editar texturas dos personagens originais

O `wor_tex.py` trabalha direto no archive de personagens do jogo (`data\pak\archive\cas_pieces`).

```bat
py wor_tex.py list                                      :: todos os .tex (nomes precisam do ghwor_keys.txt)
py wor_tex.py gallery ..\galeria                        :: miniaturas de todas as texturas + index.html
py wor_tex.py info johnny_1.tex                         :: texturas dentro de um .tex
py wor_tex.py export johnny_1.tex ..\saida              :: cada textura em .dds (todos os mips) + .png
py wor_tex.py import johnny_1.tex 9A58372E jaqueta.png  :: devolve uma textura editada
py wor_tex.py restore johnny_1.tex                      :: desfaz as mudanças de um arquivo
```

Na importação, a imagem precisa ter o mesmo tamanho da original:
- **PNG:** serve para texturas DXT1/DXT5. A ferramenta comprime e gera os mipmaps.
- **DDS:** precisa ter o mesmo formato e todos os mipmaps. No Paint.NET ou no GIMP, marque "gerar mipmaps".

---

## Ferramentas

| Arquivo | O que faz |
|---|---|
| `wor_port.py` | Porte de um mod de personagem do GHWT:DE em um comando (`install` / `uninstall`). |
| `wor_tex.py` | Archive `cas_pieces`: listar, exportar, importar e substituir arquivos, mais a conversão de `.tex` de PC para X360. |
| `wor_skin.py` | Lê `.skin` do GHWT PC/DE e do WoR X360. `dump` mostra o conteúdo; `obj` exporta a geometria. |
| `wor_skinconv.py` | Grava `.skin` do WoR. `rebuild` regrava um skin do jogo como autoteste; `convert` transforma um skin do GHWT em skin do WoR. |
| `wor_qb.py` | Lê e grava scripts QB. `dump` mostra o conteúdo em texto. |
| `wor_pak.py` | Lê e grava paks `.pak`/`.pab` e atualiza o `compress.toc.xen`. |
| `wor_install.py` | Lógica de instalação usada pelo `wor_port.py`. |

Autotestes usados no desenvolvimento:
- **Texturas:** reconstruir `.tex` originais gera arquivos byte a byte idênticos (19 de 19).
- **Malhas:** 303 de 304 `.skin` de personagem originais se reconstroem byte a byte.
- **Scripts:** 1375 de 1383 arquivos QB originais se reconstroem byte a byte.
- **Paks:** `qb`/`qs` se reconstroem byte a byte.

---

## Notas técnicas

Estas são as descobertas em que as ferramentas se baseiam. Devem ajudar quem for modificar o WoR.

### Archives

- **Compressão CHNK.** É usada pelos paks de `data\compressed` e pelo archive `cas_pieces`:
  - cada chunk tem um cabeçalho de 0x80 bytes seguido de **deflate puro** (zlib, wbits = -15), com até 0x80000 bytes;
  - campos do cabeçalho: `"CHNK"`, 0x80, tamanho comprimido, offset do próximo chunk (`FFFFFFFF` no último), tamanho do slot do próximo chunk, tamanho descomprimido, offset descomprimido;
  - cada slot mede `align(0x80 + csize, 0x800)`;
  - os paks comprimidos em disco são completados até um múltiplo de 32 KB.
- **`cas_pieces.pak.xen`** é um índice de entradas de 32 bytes: tipo, offset, tamanho comprimido, tamanho descomprimido, chave do nome, número de chunks, tamanho do primeiro slot, 0x200. O `.pab` guarda os dados.
- **Paks padrão** (`qb`, `qs`, ...):
  - cada entrada tem 32 bytes: tipo, offset, tamanho, 0, chave do nome completo, chave do nome curto, 0, 0;
  - nos pares `.pak` + `.pab`, os offsets são relativos ao início do `.pab`; nos `.pak` sozinhos, à própria entrada;
  - os arquivos ficam alinhados em 32 bytes, colados uns nos outros;
  - uma entrada `.last` fecha o índice, com `ABABABAB` como dados.

### Chaves de arquivo

- **QBKey** = CRC-32 do texto em minúsculas, **sem XOR final**.
- **Os caminhos do jogo usam barra invertida**, por exemplo `qbkey("models\gh_rockers\johnny\johnny_1.skin")` = `DA63ECC5`.
- **As chaves podem ser estendidas.** Sem o XOR final, `qbkey(caminho + ".skin")` é igual a `qbkey(".skin", estado = qbkey(caminho))`. É assim que o jogo transforma o `mesh = models\...\johnny_1` de um script em chaves do archive. Isso também permite criar nomes de arquivo novos sem tabela de nomes.

### `compress.toc.xen`

- **Formato:** um cabeçalho `TOC1` seguido de entradas de 24 bytes: `qbkey(caminho relativo a data\compressed)`, tamanho descomprimido, **tamanho de leitura**, `0x30000 | número de chunks`, slot do primeiro chunk e um valor desconhecido.
- **O jogo lê só o *tamanho de leitura*** dos arquivos listados. Um arquivo recomprimido que termine depois disso é descomprimido com lixo, e o jogo trava. O `wor_pak.py` atualiza a entrada sozinho.

### `.tex` (X360)

- **Cabeçalho:** magic `FACECAA7`, versão 0x011C, número de texturas e offset da tabela de entradas.
  - A área de hash tem `28 + 24 × próxima_potência_de_2(número)` bytes, preenchida com 0xEF.
  - Depois vêm as entradas de 0x28 bytes e, em seguida, um cabeçalho D3D de 0x34 bytes por textura.
- **Cada cabeçalho D3D tem um fetch constant do Xenos:** bit de tiling, pitch, formato, endian (8in16; 8in32 no A8R8G8B8), tamanho e número de mips.
- **Mips:**
  - o nível 0 começa no offset base, e os níveis seguintes no offset de mips;
  - cada nível é alinhado a 32×32 blocos, em páginas de 4 KB;
  - os níveis cujo menor lado tem 16 px ou menos dividem um único *packed mip tail* de 4 KB (a mesma regra do `GetPackedMipOffset` do Xenia).
- **O espaço livre dos tiles é preenchido com `0xFACE`.**
- **O `.tex` de PC (GHWT)** usa o mesmo dicionário, com um arquivo DDS comum por textura.

### `.skin`

- **Em comum:** big-endian, lista de materiais v4, CScene, setores, CGeoms, sMeshes e um rodapé de disqualifiers.
- **WoR:**
  - sMeshes de 144 bytes;
  - vértices com peso de 32 bytes: posição em float, dois pesos em u16, normal, tangente e bitangente empacotadas em 11:11:10, `BAADF00D`;
  - UVs em half-float, com `0x10000` como flag de "1 conjunto de UV comprimido".
- **GHWT PC:**
  - sMeshes de 112 bytes;
  - vértices de 56 bytes em float;
  - UVs em float.
- **Os esqueletos** (`.ske`) são compatíveis byte a byte entre GHWT PC e WoR.

### Scripts (`qb.pab`) e o que trava o jogo

O WoR trava na tela de título se alguma destas regras for quebrada:

1. O `qb.pab` descomprimido cresce além do tamanho original.
2. O tamanho de leitura no `compress.toc.xen` não cobre o `qb.pab` recomprimido.
3. Fica um buraco entre dois arquivos dentro do `qb.pab`.
4. Uma 34ª entrada é acrescentada a `Preset_Musician_Profiles_GHRockers`, ou os perfis sofrem outras mudanças de estrutura.

Trocar **valores** no lugar é seguro. É só isso que o `wor_install.py` faz.

### Os perfis ficam no save

A lista do *Select Rocker* vem de `CharacterProfileGetList(savegame)`, então os perfis predefinidos são copiados para o save quando ele é criado. A checagem de perfil `is_selectable_profile` só olha a flag `selection_not_allowed`.

---

## Créditos

- **Referência dos formatos:** templates do 010 Editor e listas de checksums do [Guitar Hero SDK](https://gitgud.io/fretworks/guitar-hero-sdk), e os importadores do [NXTools](https://gitgud.io/fretworks/nxtools).
- **Tiling de texturas e packed mips do Xbox 360:** [Xenia](https://github.com/xenia-project/xenia).
- **As comunidades de modding do GHWT:DE e do Guitar Hero.**

Guitar Hero é marca registrada da Activision. Este é um projeto de fã não oficial, sem ligação com a Activision ou a Neversoft.
