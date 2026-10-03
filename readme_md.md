# wor_tex.py: GH:WoR (X360) character textures

Requires only Python 3 (no dependencies). Run from inside `tools\`.

```
py wor_tex.py list                              # cas_pieces .tex (checksum, size)
py wor_tex.py info    F2280EFC                  # textures inside a .tex
py wor_tex.py export  F2280EFC ..\out           # .dds (with all mips) + .png of each texture
py wor_tex.py gallery ..\gallery                # thumbnails of everything + index.html (to find characters)
py wor_tex.py fill    F2280EFC 4E065537 0 255 0 # proof of concept: solid color (DXT1/DXT5); "all" = all
py wor_tex.py import  F2280EFC 4E065537 new.dds
py wor_tex.py restore                           # restores .baks (created on 1st write)
py wor_tex.py restore gh_rocker_johnny_1.ske    # restores only one file
py wor_tex.py replace gh_rocker_johnny_1.ske.xen ..\Thyeen\Assets\Thyeen.ske.xen   # replaces any file
py wor_tex.py convert-pc-tex Thyeen.tex.xen output.tex [--max 1024]   # GHWT PC/DE .tex -> 360
```

### Meshes (`wor_skin.py`, `wor_skinconv.py`)

```
py wor_skin.py dump file.skin.xen [--verts]          # reads WT (PC/DE) or WoR .skin
py wor_skinconv.py rebuild johnny_1.skin.xen output.skin  # selftest: rewrites a WoR .skin
py wor_skinconv.py convert Thyeen.skin.xen johnny_1.skin.xen output.skin --normal 3CECC64E --flatnormal ACF1131D
```

`convert` uses a WoR `.skin` as a template (sectors, material to clone, constant blocks).
Materials become copies of the first opaque material of the template (`852105C8`: normal, diffuse, specular).
For the neutral normal, generate the `.tex` with `convert-pc-tex ... --flat-normal` (checksum `ACF1131D`).

### New character (`wor_newchar.py`)

```
py wor_newchar.py Thyeen "Thyeen" ..\out\thyeen\thyeen_wor.skin ..\out\thyeen\thyeen_x360.tex ..\Thyeen\Assets\Thyeen.ske.xen ..\Thyeen\Assets\Thyeen_Drummer.ske.xen
```

The command adds the files to `cas_pieces` and modifies three places:
- **`CAS_Full_Body`:** gets the `<Id>_1` part, cloned from Johnny and without cloth.
- **Profile list:** gets the `GH_Rocker_<Id>` profile.
- **`qs.pak`:** gets the name displayed on screen.

Backups are saved as `qb.pak.xen.bak`, `qb.pab.xen.bak`, and `qs.pak.xen.bak` (in `data\compressed\PAK`).

Naming convention: file checksums use **backslashes**, for example
`qbkey("models\gh_rockers\johnny\johnny_1.skin") = DA63ECC5`. In QB, `mesh` stores the path without the extension.

Support tools:
- **`wor_qb.py`:** reads and writes QB (`dump`).
- **`wor_pak.py`:** reads and writes standard paks, `.pak` + `.pab` or just `.pak`.

Names come from the GH SDK's `ghwor_keys.txt`: a piece of the unique name is enough (`johnny_1.tex`).
The `convert-pc-tex` generates files byte-by-byte identical to the originals (tested by rebuilding 19 game `.tex` files).

`--archive <name>` replaces the pair `data\pak\archive\<name>.pak.xen/.pab.xen` (default: `cas_pieces`).

**DDS for import:** same format (DXT1/DXT5/ATI2), same dimensions, and **with full mipmaps**
(same number of levels as the original; see `info`). In Paint.NET, use "Generate mip maps"; in GIMP, use "Generate mipmaps".

## Formats (verified in this dump)

### `cas_pieces.pak.xen` (index) + `.pab.xen` (data) file
32-byte entries in big-endian, terminated by zeros. The last entry has type `.last`, with an offset at the end of the `.pab`.

| off | field |
|---|---|
| 0x00 | type (QBKey of the extension: `.tex` 8BFA5E8E, `.skin` 64112E85, `.img` DAD5E950, `.clt` 4AE71C19, `.ske` 7330095C, `.mqb` 4BC1E85E) |
| 0x04 | offset in .pab |
| 0x08 | compressed size (sum of chunk slots, aligned to 0x800) |
| 0x0C | uncompressed size |
| 0x10 | file name checksum (paths do not appear as text in QBs) |
| 0x14 | number of chunks |
| 0x18 | 1st chunk slot size |
| 0x1C | 0x200 (always) |

Currently there are 6800 entries: 2691 .img, 1954 .skin, 1698 .tex, 283 .clt, 88 .ske and 85 .mqb.

### CHNK (also used in the `.pak.xen`/`.pab.xen` of `data\compressed\`)
It is a sequence of chunks. Each one has a 0x80 byte header followed by **raw deflate** (zlib wbits=-15) and stores up to 0x80000 uncompressed bytes.
Header: `"CHNK"`, 0x80, csize, relative offset of the next chunk (FFFFFFFF in the last one), next chunk's slot, usize, uncompressed offset, 0.
Each chunk's slot is `align(0x80 + csize, 0x800)`.

### `.tex` (texture dictionary)
Starts with the magic `FACECAA7`, followed by u16 version (0x011C), u16 count, and u32 offset of the entry table. Each entry has 0x28 bytes:
`0A 28 02 kind | crc | w h d | w h d | levels bpp fmt 0 | mipOffset | d3dHeaderOffset | ? | baseOffset`.
- `kind`: 0 = diffuse, 1 = normal (DXN), 3 = spec(?), 5 = cubemap (unsupported).
- The D3D header has 0x34 bytes. At +0x1C is the **Xenos fetch constant**: tiled = bit 31 of dword0, pitch = bits 22–30 of dword0 (×32 texels), format = bits 0–5 of dword1, endian = bits 6–7 of dword1, packed mips = bit 11 of dword5.
- Formats seen: DXT1 (0x12), DXT5 (0x14), DXN/BC5 (0x31), A1R5G5B5 (0x03), A8R8G8B8 (0x06, endian 8in32). All are tiled and the rest use endian 8in16.
- Mips: level 0 is at `baseOffset`; the following levels are in sequence starting from `mipOffset`, each with pitch and height aligned to 32 blocks and size aligned to 4 KB.
  Levels with the smallest side ≤16 texels are packed into a single tile (*packed mip tail*); offsets follow Xenia's `GetPackedMipOffset`.