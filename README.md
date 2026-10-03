# WoR Character Tools

Port **Guitar Hero World Tour: Definitive Edition** character mods to **Guitar Hero: Warriors of Rock** (Xbox 360 / Xenia). You can also edit the textures of the original characters.

- **Pure Python 3, no dependencies.**
- **Works on an extracted copy of the game.** Back it up first.
- **Tested in Xenia Canary.** A custom GHWT:DE character, with its own custom skeleton, shows up in *Select Rocker* with its own name and description. It also played a guitar song. Other instruments have not been tested yet.

> This repository contains **no game files**. You need your own copy of Guitar Hero: Warriors of Rock.

---

## What you need

| | |
|---|---|
| **Python 3.8+** | [python.org](https://www.python.org/). Use `py` on Windows and `python3` elsewhere. |
| **Guitar Hero: Warriors of Rock (X360)** | Extracted to a folder, e.g. with [extract-xiso](https://github.com/XboxDev/extract-xiso). |
| **[Xenia Canary](https://github.com/xenia-canary/xenia-canary)** | To play the extracted game. |
| **A GHWT:DE character mod** | A folder with `character.ini`, the `.skin.xen`/`.tex.xen` it uses and, optionally, custom skeleton `.ske.xen` files. |
| *(optional)* `ghwor_keys.txt` | From the [Guitar Hero SDK](https://gitgud.io/fretworks/guitar-hero-sdk) (`SDKCode/Checksums`). It only adds readable file names to listings. |

The tools find the game's `data` folder automatically when it sits next to them. Otherwise, point to it:

```bat
set WOR_DATA=D:\Games\Guitar Hero - Warriors of Rock\data
```

---

## Step by step: add a GHWT:DE character to WoR

### 1. Extract the game

```bat
extract-xiso -x "Guitar Hero Warriors of Rock.iso"
```

Run the extracted `default.xex` in Xenia once to check that the game itself works.

### 2. Get the tools

Download or clone this repository anywhere. A good place is next to the extracted game folder:

```
MyFolder\
  Guitar Hero - Warriors of Rock\   <- extracted game (has data\ and default.xex)
  wor-character-tools\              <- this repository
  MyCharacter\                      <- the GHWT:DE mod (character.ini, Content\..., Assets\...)
```

### 3. Port and install the character

```bat
cd wor-character-tools
py wor_port.py install ..\MyCharacter
```

The command does everything:
1. Reads `character.ini` for the name, description, gender, mesh and custom skeleton.
2. Converts the textures from the PC layout to the Xbox 360 one: tiled, byte-swapped, with mipmaps. No quality is lost. Textures bigger than 1024 px are scaled down by dropping their top mip level.
3. Converts the mesh from GHWT PC to WoR: vertex, UV and normal packing, plus materials.
4. Puts the files into the game and registers the character in the *Select Rocker* list.

The converted files are also saved in `wor_build\<name>\`.

Useful options:

```bat
py wor_port.py install ..\MyCharacter --name "Display Name" --blurb "Short description"
py wor_port.py install ..\MyCharacter --max-tex 2048          :: keep 2048 px textures (more memory)
py wor_port.py install ..\MyCharacter --replace Johnny_1      :: replace an existing rocker instead
```

### 4. Start with a new save (important!)

WoR copies the rocker profiles **into the save game** when the save is created. A save made before the install will not list the new character.

In Xenia, the save lives in:

```
xenia_canary\content\<profile id>\41560883\00000001\Progress
xenia_canary\content\<profile id>\41560883\Headers\00000001\Progress.header
```

Move both somewhere else as a backup, not just deleted. Then start the game and let it create a new save.

### 5. Play

Open **Select Rocker**. With the default settings, the new character sits between *Casey Lynch* and *Judy Nails*.

### Uninstall

```bat
py wor_port.py uninstall
```

This puts back every game file the tools changed. They keep a `.bak` copy of each file the first time they modify it.

---

## Limitations

- **One new rocker slot.** WoR does not accept extra profiles: adding one hangs the game at the title screen. The tools reuse the hidden, unused profile `GH_Rocker_Casey_Cut_Skin` and its body `Casey_Cut_Skin`. Installing another character overwrites that slot. Use `--replace <rocker>` for more characters, e.g. `Johnny_1`, `Axel_1`, `Judy_1`, `Lars_1`, `Pandora_1` or `Eddie_1`.
- **Menu photo and instruments come from the slot's profile** (Casey Lynch's).
- **Animations and the base material** come from a template rocker: `Johnny_1` for `Gender=Male` and `Casey_1` for female. Change it with `--template`.
- **Materials are simplified.** Every part becomes an opaque material with normal, diffuse and specular maps:
  - the biggest mesh (the body) gets the mod's normal map, if it has exactly one;
  - the other parts get a flat normal map;
  - transparency and alpha cut-outs are not converted yet.
- **Textures:** DXT1 and DXT5 are supported. Other formats stop the conversion with an error message.
- **No cloth physics** for the new character.
- **Skeletons:** WoR accepts GHWT custom skeletons as they are (same format). If the mod has no custom skeleton, the template's skeleton is used.

---

## Editing textures of the original characters

`wor_tex.py` works directly on the game's character archive (`data\pak\archive\cas_pieces`).

```bat
py wor_tex.py list                                     :: every .tex (names need ghwor_keys.txt)
py wor_tex.py gallery ..\gallery                       :: thumbnails of every texture + index.html
py wor_tex.py info johnny_1.tex                        :: textures inside a .tex
py wor_tex.py export johnny_1.tex ..\out               :: each texture as .dds (all mips) + .png
py wor_tex.py import johnny_1.tex 9A58372E jacket.png  :: put an edited texture back
py wor_tex.py restore johnny_1.tex                     :: undo the changes to one file
```

When importing, the image must have the same size as the original:
- **PNG:** works for DXT1/DXT5 textures. The tool compresses it and builds the mipmaps.
- **DDS:** must have the same format and the full mip chain. In Paint.NET or GIMP, tick "generate mipmaps".

---

## Tools

| File | What it does |
|---|---|
| `wor_port.py` | One-command port of a GHWT:DE character mod (`install` / `uninstall`). |
| `wor_tex.py` | `cas_pieces` archive: list, export, import and replace files, plus PC to X360 `.tex` conversion. |
| `wor_skin.py` | Reads `.skin` files from GHWT PC/DE and WoR X360. `dump` prints them; `obj` exports the geometry. |
| `wor_skinconv.py` | Writes WoR `.skin` files. `rebuild` re-writes a game skin as a self-test; `convert` turns a GHWT skin into a WoR one. |
| `wor_qb.py` | Reads and writes QB script files. `dump` prints them as text. |
| `wor_pak.py` | Reads and writes standard `.pak`/`.pab` pairs and updates `compress.toc.xen`. |
| `wor_install.py` | Install logic used by `wor_port.py`. |

Self-tests used during development:
- **Textures:** rebuilding original `.tex` files gives byte-identical results (19 of 19).
- **Meshes:** 303 of 304 original character `.skin` files rebuild byte-identically.
- **Scripts:** 1375 of 1383 original QB files rebuild byte-identically.
- **Paks:** `qb`/`qs` rebuild byte-identically.

---

## Technical notes

These are the findings the tools rely on. They should help anyone modding WoR.

### Archives

- **CHNK compression.** Paks in `data\compressed` and the `cas_pieces` archive use it:
  - each chunk is a 0x80-byte header followed by **raw deflate** (zlib, wbits = -15) holding up to 0x80000 bytes;
  - header fields: `"CHNK"`, 0x80, compressed size, offset of the next chunk (`FFFFFFFF` on the last), size of the next chunk's slot, uncompressed size, uncompressed offset;
  - each slot is `align(0x80 + csize, 0x800)`;
  - compressed paks on disc are padded to a multiple of 32 KB.
- **`cas_pieces.pak.xen`** is an index of 32-byte entries: type, offset, compressed size, uncompressed size, name key, chunk count, first slot size, 0x200. The `.pab` holds the data.
- **Standard paks** (`qb`, `qs`, ...):
  - each entry is 32 bytes: type, offset, size, 0, full-name key, short-name key, 0, 0;
  - in `.pak` + `.pab` pairs, offsets are relative to the start of the `.pab`; in single `.pak` files, they are relative to the entry itself;
  - files are 32-byte aligned and back to back;
  - a `.last` entry ends the index, with `ABABABAB` as its data.

### File keys

- **QBKey** = CRC-32 of the lower-case string, with **no final XOR**.
- **Game paths use backslashes**, e.g. `qbkey("models\gh_rockers\johnny\johnny_1.skin")` = `DA63ECC5`.
- **Keys can be extended.** With no final XOR, `qbkey(path + ".skin")` equals `qbkey(".skin", state = qbkey(path))`. That is how the game turns a script's `mesh = models\...\johnny_1` into archive keys. It also lets you add new file names without a name table.

### `compress.toc.xen`

- **Format:** a `TOC1` header followed by 24-byte entries: `qbkey(path relative to data\compressed)`, uncompressed size, **read size**, `0x30000 | chunk count`, first chunk slot, and an unknown value.
- **The game reads only *read size* bytes** of the listed files. A recompressed file that ends later decompresses garbage and the game hangs. `wor_pak.py` updates the entry automatically.

### `.tex` (X360)

- **Header:** magic `FACECAA7`, version 0x011C, texture count and offset of the entry table.
  - The hash area is `28 + 24 × next_pow2(count)` bytes, filled with 0xEF.
  - It is followed by the 0x28-byte entries, then one 0x34-byte D3D header per texture.
- **Each D3D header holds a Xenos fetch constant:** tiled bit, pitch, format, endian (8in16; 8in32 for A8R8G8B8), size and mip count.
- **Mips:**
  - level 0 starts at the base offset, the next levels follow at the mip offset;
  - each level is 32×32-block aligned, in 4 KB pages;
  - levels whose smaller side is 16 px or less share one 4 KB *packed mip tail* (the same rule as Xenia's `GetPackedMipOffset`).
- **Unused tile space is filled with `0xFACE`.**
- **The PC (GHWT) `.tex`** has the same dictionary, with a plain DDS file per texture.

### `.skin`

- **Common to both:** big-endian, material list v4, CScene, sectors, CGeoms, sMeshes and a disqualifier footer.
- **WoR:**
  - 144-byte sMeshes;
  - 32-byte skinned vertices: float position, two u16 weights, normal, tangent and bitangent packed 11:11:10, `BAADF00D`;
  - half-float UVs, with `0x10000` as the "1 compressed UV set" flag.
- **GHWT PC:**
  - 112-byte sMeshes;
  - 56-byte float vertices;
  - float UVs.
- **Skeletons** (`.ske`) are byte-compatible between GHWT PC and WoR.

### Scripts (`qb.pab`) and what hangs the game

WoR hangs at the title screen if any of these rules is broken:

1. The decompressed `qb.pab` grows past its original size.
2. The read size in `compress.toc.xen` does not cover the recompressed `qb.pab`.
3. There is a gap between two files inside `qb.pab`.
4. A 34th entry is added to `Preset_Musician_Profiles_GHRockers`, or other structural changes are made to the profiles.

Changing **values** in place is safe. That is all `wor_install.py` does.

### Profiles live in the save

The *Select Rocker* list comes from `CharacterProfileGetList(savegame)`, so preset profiles are copied into the save when it is created. The profile check `is_selectable_profile` only looks at the `selection_not_allowed` flag.

---

## Credits

- **Format references:** [Guitar Hero SDK](https://gitgud.io/fretworks/guitar-hero-sdk) 010 Editor templates and checksum lists, and [NXTools](https://gitgud.io/fretworks/nxtools) importers.
- **Xbox 360 texture tiling and packed mips:** [Xenia](https://github.com/xenia-project/xenia).
- **The GHWT:DE and Guitar Hero modding communities.**

