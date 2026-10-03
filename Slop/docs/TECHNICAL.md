# Technical notes: porting GHWT:DE characters to Guitar Hero: Warriors of Rock

This document explains three things:
- **How the port works,** and why it is possible at all.
- **How each piece was figured out.**
- **The exact skeleton and mesh formats.** These are what you need to write your own tools, for example a Blender exporter or importer.

Everything here was verified against the Xbox 360 release of Warriors of Rock (title ID `41560883`) and a GHWT:DE character mod, running in Xenia Canary. Most claims are backed by byte-exact rebuild tests. Inferred or partially understood points are marked as such.

Conventions:
- All multi-byte values are **big-endian** unless stated otherwise.
- "WT" means the PC files used by Guitar Hero World Tour: Definitive Edition, which is GHWT PC.
- "WoR" means the Xbox 360 files of Warriors of Rock.

---

## 1. Why this is possible

GHWT (2008), GH5, Band Hero and WoR (2010) all run on successive versions of the same Neversoft engine. The asset formats are the same families, and almost every difference falls into one of two kinds:

1. **Platform packing (PC vs Xbox 360).**
   - WT PC keeps vertices as plain floats. WoR on the Xbox 360 packs normals into 32 bits and stores UVs as half floats.
   - PC textures are plain DDS files. On the 360 they are tiled for the Xenos GPU and byte-swapped.
2. **Versioned struct sizes.** The WT submesh record is 112 bytes, the WoR one is 144 bytes. The fields are mostly the same; a few are new or reordered.

What did *not* change between the games is what makes characters portable:
- **The character skeleton.** The `.ske` format and the bone list (names, order, hierarchy) are the same. Section 3 covers this.
- **The skinning model.** Vertices are stored in model space at bind pose, and each vertex refers to bones **by index into the skeleton** with up to 3 weights.
- **The material and texture-dictionary concepts.** Materials reference textures by checksum, and `.tex` files are dictionaries keyed by those checksums.

Converting a character is therefore mostly **repacking**. Nothing needs to be re-rigged or re-weighted.

---

## 2. How it was figured out (discovery log)

The order matters, because each step validated the tools used in the next one.

1. **Archives and compression.** The character data lives in `data/pak/archive/cas_pieces.pak.xen` (an index) and `.pab.xen` (the data).
   - The data started with `CHNK`. A raw-deflate decode (zlib, `wbits = -15`) of the bytes after a 0x80-byte header produced exactly the uncompressed size given in the index. That confirmed the compression.
   - Type fields were matched by QBKey against extension strings: `.tex`, `.skin`, `.ske`, and so on.
2. **Textures, and the first proof of life.**
   - `.tex` files start with `FACECAA7`. Each texture has a 0x34-byte D3D header containing an Xenos fetch constant: format, endianness, tiling and size.
   - Untiling with the standard `XGAddress2DTiledOffset` formula and swapping bytes in 16-bit units gave correct images. The packed mip tail follows Xenia's `GetPackedMipOffset`.
   - Painting one face texture solid green and seeing it green in game confirmed that the archive can be edited and that the game does no integrity checks on it.
3. **Names.** The GH SDK's `ghwor_keys.txt` resolves 100% of the `cas_pieces` checksums. That identified Johnny Napalm's files: `johnny_1.skin/.tex/.clt` and `gh_rocker_johnny_1.ske`.
4. **Meshes.**
   - The GH SDK 010 Editor templates (`Skin.bt`, `sMesh_WOR.bt`, …) and the NXTools importers describe both the WT and the WoR `.skin` layouts.
   - A reader for both formats (`wor_skin.py`) was checked by software-rendering both models.
   - The differences turned out to be the vertex and UV packing and the size of the submesh record.
5. **Skeletons.** The WT mod's `Thyeen.ske.xen` and WoR's `gh_rocker_johnny_1.ske.xen` have the **same size (14592 bytes) and the same header**. Only the transform data differs (section 3).
   - Injecting the WT skeleton over Johnny's did not crash the game.
   - Johnny's arms stretched into spikes: his A-pose mesh was being driven by a T-pose skeleton. That proved the game reads the bind pose from the `.ske` file.
6. **Texture converter.** PC DDS data was tiled and byte-swapped into a WoR `.tex`. To validate the generator, original WoR `.tex` files were rebuilt from their own decoded pixels: **19 of 19 came out byte-identical**, which also fixed the header and padding rules.
7. **Mesh writer.** A WoR `.skin` writer was validated the same way: **303 of 304 original character skins rebuild byte-identically.** Only then was the WT→WoR conversion written. Johnny's converted skin, texture and skeleton were then replaced: the character worked, animated and played.
8. **A new character instead of a replacement.** This needed edits to the QB scripts.
   - **Script tooling first.** A QB reader and writer (1375 of 1383 files byte-identical) and a pak writer (byte-identical) were built.
   - **Bisection in Xenia.** Every attempt to change `qb.pab` hung at the title screen, so the problem was narrowed down one variable at a time:

     | Test | Change | Result |
     |---|---|---|
     | C | game scripts original, `cas_pieces` modified | boots |
     | B | original content, one 512 KB chunk recompressed | boots, once `compress.toc.xen` was fixed |
     | D | one padding byte changed | boots, so there is no content hash |
     | F | one value changed (4 bytes) | boots |
     | A/E | entry replaced, file shrank, gap left before the next file | hangs |
     | G | entry replaced with the same size (padding item) | boots |
     | H | profiles file grown by a dummy global | boots |
     | I | 34th rocker profile appended | hangs |

   - **The conclusion** was to change **values only**. The hidden, unused rocker `GH_Rocker_Casey_Cut_Skin` and its full-body piece `Casey_Cut_Skin` are repointed at the new files.
9. **Profiles live in the save.** Reading the decompressed menu scripts showed that *Select Rocker* uses `CharacterProfileGetList(savegame)`. Preset profiles are copied into the save when it is created, so a new save is needed. With a fresh save, the character appeared.

---

## 3. Skeletons (`.ske`)

### 3.1 Format

A `.ske` file is a fixed table of **128 bone slots**, stored as parallel arrays. Both games use exactly the same layout, 14592 bytes:

| Offset | Size | Content |
|---|---|---|
| 0x00 | 2 | `0x0001` (constant) |
| 0x02 | 2 | `0x0030` (constant) |
| 0x04 | 4 | `0x39000080`; the low byte, 0x80 = 128, is the bone count |
| 0x08 | 8 | zero |
| 0x10 | 8×4 | absolute offsets of the eight arrays below |
| 0x30 | 0x50 | zero |
| 0x0080 | 128 × 16 | **translation**, `float x, y, z, w (=1)`: local, relative to the parent |
| 0x0880 | 128 × 16 | **rotation**, quaternion `x, y, z, w`: local (see the conjugate note) |
| 0x1080 | 128 × 64 | **matrix**, 4×4 float: inverse bind pose in world space |
| 0x3080 | 128 × 4 | bone name (QBKey) |
| 0x3280 | 128 × 4 | parent bone name (QBKey; 0 for the root) |
| 0x3480 | 128 × 4 | mirror bone name (QBKey; the left/right counterpart) |
| 0x3680 | 128 × 4 | mirror bone index (`int32`, -1 = none) |
| 0x3880 | 128 × 1 | bone type (byte) |

The offsets in the header point exactly to these positions in both games.

### 3.2 Semantics (verified numerically)

- **Coordinate system:**
  - **Y is up**, units are **meters**, and the character faces **+Z**;
  - the character's **left** side is **+X**;
  - for example, Johnny's pelvis is at (0, 1.027, 0) and his head at (0, 1.646, -0.008), with `BONE_KNEE_L` at x = +0.107.
- **Each bone points along its own local +X axis.** For example, the knee's translation is (0.417, 0, 0), which is the thigh length.
- **Rotation:** the root has quaternion (-0.5, -0.5, -0.5, 0.5), which turns the X-forward bone convention into the Y-up model space.
- **The stored matrix is the inverse of the bind-pose world matrix.** To see this, build each bone's local matrix from its translation `t` and the **conjugate** of its stored quaternion, `q* = (-x, -y, -z, w)`:

  ```
  local_i = [ R(q*_i) | t_i ]          (column-vector convention)
  world_i = world_parent(i) · local_i
  matrix_i (stored, row-major, transposed) = inverse(world_i)
  ```

  This was checked on all 92 deforming bones of Johnny's skeleton, with a maximum error of **0.00000**. A writer must keep the three representations consistent.

### 3.3 Bone list

- **The bone names and order are the standard Neversoft GH rig.** Slots 0–91 are the deforming body. Slot 0 is `control_root`, then come `bone_pelvis`, `Bone_Stomach_Lower`, `Bone_Stomach_Upper`, `Bone_Chest`, `Bone_Neck`, `Bone_Head`, the collars, the arms, the hands and fingers, the legs and the face bones. The remaining slots are control, cloth and accessory bones.
- **The type byte groups bones by role.** Values seen: 0 for 48 bones (body), 7, 8 (fingers), 9 (face), 5 and 10. The role of each type is inferred, not confirmed.
- **The mirror name and index pair each left bone with its right counterpart.** They are probably used for mirrored animations.

### 3.4 Why GHWT:DE skeletons work in WoR unchanged

Comparing the WT mod's skeleton with Johnny's, slot by slot:
- **Header and offsets:** identical.
- **Names, mirror names, mirror indices and types of all 128 slots:** identical.
- **Parents:** identical except one. `Bone_Tongue` has `Bone_Head` as its parent in WoR and `BONE_JAW` in the WT file. This is harmless.
- **Translations, rotations and matrices:** different. That is the custom proportions, plus a T-pose instead of an A-pose.

What follows from that:
1. **Meshes reference bones by slot index** (section 4.6), so a mesh made for one skeleton works with any skeleton that has the same bone order. Both games use the same order.
2. **Animations are applied per bone.** They are mostly local rotations, so a skeleton with other lengths or another rest pose still animates correctly. That is how GHWT:DE handles custom skeletons too.
3. **The game takes the bind pose from the `.ske` itself.** This was proven by the stretched-arms test: an A-pose mesh on a T-pose skeleton. So the mesh and its skeleton only have to agree with each other, and a WT mesh plus its WT skeleton is a matching pair.

### 3.5 Writing a skeleton from Blender

Start from an existing `.ske` as a template. Keep the name, parent, mirror, mirror-index and type arrays, and rewrite only the transforms. For each bone *i*, in slot order:

1. **Take the Blender armature bone's rest matrix in armature space** and convert it to GH space (section 4.9). The bone must point along its local **+X**. Blender bones point along local +Y, so add a fixed axis swap for every bone.
2. **Build the local matrix:** `local_i = inverse(world_parent) · world_i`.
3. **Write the translation:** `t_i = local_i.translation`, with `w = 1`.
4. **Write the rotation:** take the rotation part of `local_i` as a quaternion `q`, then store its **conjugate** `(-x, -y, -z, w)`.
5. **Write the matrix:** `inverse(world_i)`, transposed to row-major.

Then rebuild the world matrices from what you wrote and check that they match `inverse(stored matrix)`. That catches convention errors immediately.

The drummer skeleton (`gh_drummer_*`) is a second skeleton with the same layout, used for the drum animations. GHWT:DE mods ship `<name>_Drummer.ske.xen`. If you only have one skeleton, use it for both.

---

## 4. Meshes (`.skin`)

### 4.1 File layout

```
0x00   u32  footer offset (relative to the core start)
0x04   7 × u32  0xFAAABACA
-----  WT: core starts at 0x20.   WoR: 0x20..0x7F are zero, core starts at 0x80
core:  material list  (header 0x10 bytes + materials)
       WT: 0xBABEFACE, pad count, padding        WoR: zero-pad to 128-byte alignment
CScene (all offsets below are relative to the CScene start unless noted):
       scene header           0x90 bytes
       CSector × n            96 bytes each
       CGeom × (sectors with geometry)   0x60 bytes each
       Lst::Head area         (runtime; copy from a template)
       sMesh × m              WT 112 bytes, WoR 144 bytes
       0xEA × 4m              (runtime pointer slots)
       u32 × m                mesh draw order (0..m-1 is fine)
       0xFF × 4m, then 0xAA up to 32-byte alignment
       per sMesh: UV block, face block, 0xEE padding up to 4 KB alignment, vertex block
       zero up to 32-byte alignment
footer (disqualifiers; WoR "empty": 02 14 00 FE, count 0, …, 32 bytes)
```

The WoR layout rules come from `johnny_1.skin` and were confirmed by rebuilding 303 of 304 character skins:
- The **first UV block** starts at the first 32-byte boundary after the `0xFF` area.
- **Each sMesh's data** is UV block, then face block, then `0xEE` padding up to the next **4 KB boundary relative to the CScene start**, then the vertex block.
- **The next mesh's UV block** follows the previous vertex block directly.

### 4.2 Material list (version 4, the same in both games)

The list header is 16 bytes:
- `u8 version (4)`, `u8 0x10`, `u16 count`;
- `u32 list size` (header plus materials);
- `u32 0x10`;
- `u32 0xFFFFFFFF`.

Each material:

| Offset | Content |
|---|---|
| 0x00 | material checksum, referenced by the sMesh |
| 0x04 | name checksum |
| 0x70 | **template checksum.** The shader comes from `data/compressed/FXFILES/MaterialLibrary.bin.xen`. |
| 0x78 / 0x7C | vertex-shader property count / offset (relative to the material) |
| 0x80 / 0x84 | pixel-shader property count / offset |
| 0x88 / 0x8C | texture count / offset of the texture checksum list |
| 0x94 | material size |
| 0x9C | flags |
| 0xA4, 0xA8 | draw order, blend mode (0 opaque, 3 blend, …) |
| 0xB8 | alpha cut-off |

- **Johnny's skins** mostly use template `852105C8`, with textures **[normal, diffuse, specular]** and 7 pixel-shader properties.
- **The WT mod used** template `67AA2AE2`. It also exists in WoR's material library, but its WoR property layout was not verified, so the converter clones a WoR material instead (section 5).
- **Global default textures exist** for any material slot: `DEC273CB` is black (no specular), `D729D3B1` and `E7A5C290` are white. All are 32×32 and live in `global_model_tex`.

### 4.3 CScene header (0x90 bytes, WoR)

| Offset | Content |
|---|---|
| 0x00 / 0x10 | bounding box min / max (`vec4`) |
| 0x20 | bounding sphere (`x y z r`) |
| 0x30 | `u16 14`, `u16 144` (constants; 144 is the sMesh size) |
| 0x3C | end of geometry data, relative to the core (before the final padding) |
| 0x44 | `0xFFFFFFFF` |
| 0x48 / 0x4C | mesh-order list offset / sMesh count |
| 0x50 | `0xFF` area offset |
| 0x6C / 0x70 | sector count / sector list offset (0x90) |
| 0x74 | CGeom list offset |
| 0x78 | `0xFFFFFFFF` |
| 0x7C / 0x80 | Lst::Head area offset / sMesh list offset |
| 0x8C | `0xEA` area offset |

- **CSector (96 bytes):** 0, checksum, flags (`0x20` = no geometry), light group, `FF×8`, zero ×40, bounding sphere, zero ×16.
- **CGeom (0x60 bytes):** block length, 0, 0, `0x100`, bounding box (2 × `vec4`), zero ×24, first sMesh index, sMesh count, zero ×12, `DEADDEAD`.

Johnny has 4 sectors, and only the first has geometry. The converter keeps his sector list and puts every mesh in the first one.

### 4.4 sMesh record (WoR, 144 bytes)

| Offset | Type | Content |
|---|---|---|
| 0x00 | 4 × f32 | bounding sphere `x y z r` |
| 0x10 | 8 | zero |
| 0x18 | u32 | UV block offset |
| 0x1C | u8, u8, u16 | UV stride, 0, vertex count |
| 0x20 | u32 | 0 |
| 0x24 | u32 | **mesh flags** (4.7) |
| 0x28 | 2 × u32 | vertex-layout descriptor (inferred), then `0x00FFEDBE`. The first value is `0x111` in 91% of 3546 character meshes, with `0x221`, `0x2111`, `0x211` and `0x121` in the rest. Copy it from a template mesh with the same flags. |
| 0x30 | u32 | face block offset |
| 0x34 | 8 | `FF` |
| 0x3C | u32 | index data length in bytes (= 2 × index count) |
| 0x44 | u32, u16, u16 | `0x102`, 2, `0x40` (the same in all 3546 meshes checked) |
| 0x50 | u32 | material checksum |
| 0x54 | 8 | `FF` |
| 0x64 | u32 | face type: **4 = triangle list**. All 3546 WoR character meshes use 4; other games use strips with `0x7FFF` separators. |
| 0x68 | i32 | vertex block offset (-1 = unskinned) |
| 0x7A | u16 | **index count** |
| 0x7C | u16 | vertex count |
| 0x82 | u8 | single bone (`0xFF` = skinned) |
| 0x84 | u8 | highest bone index used by the mesh |
| 0x85 | u8 | `0x1E` (the same in all 3546 meshes checked) |

Offsets are relative to the CScene start. Counts are u16, so each sMesh is limited to 65535 vertices and 65535 indices. A 11 066-vertex body mesh works fine. Split bigger meshes.

The WT sMesh is 112 bytes with the same information in a different order: sphere, UV offset, `FF×8`, UV length, flags, stride, material, `0xFF`, index count, vertex count, face offset, vertex offset, face type. See `read_smesh()` in `wor_skin.py`.

### 4.5 UV block

- **32-byte header,** then one record of `stride` bytes per vertex, **in vertex-block order** (4.6).
- **WoR header:** 32 bytes that **do not depend on the mesh data.** The same value appears in meshes with very different counts, and it changes from file to file. It looks like memory left over from Neversoft's exporter. The converter copies the header of the template's first mesh into every mesh, and the game accepts it.
- **WoR record:** `[ARGB colour (4 bytes) if flags & 0x10]`, then `half u, half v` per UV set.
  - Johnny uses stride 4 (one half-float UV) or 8 (colour + UV).
- **WT PC record:** `[colour 4]` then `float u, float v` per set. The mod has 2 sets, so stride 20.
- **Unskinned meshes** (vertex block offset -1) store position, normal and so on in the UV block instead. The converter does not handle that case, because characters are skinned.
- **V-flip for Blender:** `blender_v = 1 - v`.

### 4.6 Vertex block ("submesh cafe") and bone weights

```
16 bytes  CAFEBAB4 × 4
u32       0
u32 n1, n2, n3     number of groups with 1, 2 and 3 weights
groups, in that order (all 1-weight groups, then 2-weight, then 3-weight):
    u32  vertex count
    u8   bone index[4]          slot 4 is never used (max 3 influences)
    u32  vertex count (again)
    u32  0xFACEF000 (WoR; WT has other values here)
    vertices × count
```

**Vertex order is the order of the vertices across all groups.** Face indices and UV records both use this order. To build one, sort the vertices by their bone set and cut them into groups.

**WoR vertex (32 bytes):**

| Offset | Content |
|---|---|
| 0x00 | position `f32 x, y, z` (model space, bind pose, GH axes) |
| 0x0C | `u16 w1`, `u16 w0` (**note the order**), each weight × 65535 |
| 0x10 | normal, packed 11:11:10 |
| 0x14 | tangent, packed 11:11:10 |
| 0x18 | bitangent, packed 11:11:10 |
| 0x1C | `BA AD F0 0D` |

**WT PC vertex (56 bytes):**
- three `vec4` that are columns: `(pos.x, n.x, t.x, b.x)`, `(pos.y, n.y, t.y, b.y)`, `(pos.z, n.z, t.z, b.z)`;
- then `f32 w0, f32 w1`.

**Weight semantics,** measured on both files:
- `w0` belongs to `bone[0]`, `w1` to `bone[1]`, and `w2 = 1 - w0 - w1` to `bone[2]`.
- Weights are **sorted in descending order**: `w0 ≥ w1 ≥ w2`.
- 1-weight groups have `w0 = 1`. 2-weight groups have `w0 + w1 = 1`.

> NXTools computes `(w0+d, w1+d, d)` with `d = 1 - w0 - w1`. That is only right for 1 and 2 weights. For 3-weight vertices it is wrong, because the weights add up to more than 1.

**Packed vectors (normal, tangent, bitangent):**

```
x = round(v.x * 1023) & 0x7FF        bits  0..10
y = round(v.y * 1023) & 0x7FF        bits 11..21
z = round(v.z *  511) & 0x3FF        bits 22..31
unpack: sign-extend each field, x/1023, y/1023, z/511
```

`pack(unpack(p)) == p` for all 25 512 normals and tangents in Johnny's skin. Some degenerate bitangents are stored as `0x3FF` / `0x401`, that is (±1, 0, 0).

### 4.7 Mesh flags (`sMesh + 0x24`)

The bits follow the SDK's `Common.bt`:

| Bit | Meaning |
|---|---|
| 0x80 | has weights (vertex block) |
| 0x10 | vertex colour in the UV block |
| 0x400 | 1 tangent |
| 0x10000 | 1 UV set, **compressed** (half float). WoR uses this. |
| 0x40000 | 2nd UV set, compressed. In 310 of 3546 WoR meshes (stride 12 with colour). |
| 0x20000 / 0x80000 | 1 / 2 UV sets, uncompressed (float). WT uses these. |
| 0x100, 0x40, 0x20, 0x08, 0x04, 0x02 | always set on character meshes (exact meaning unknown) |

Johnny uses `0x000105EE` (no colour, stride 4) and `0x000105FE` (colour, stride 8). WT uses `0x000A05FE`.

### 4.8 Face block

- **32-byte header,** then `u16` indices, as many as the index count.
- **WoR header:** 32 bytes with the same nature as the UV header. They are not tied to the mesh data, and copying a template's works.
- **WT header:** zero ×12, a number, the group counts n3, n2, n1 reversed, and the index count.
- **Face type 4:** plain triangles. The winding is kept as it is between WT and WoR.

### 4.9 Axes for Blender

GH is Y-up and Blender is Z-up. The conversion used by NXTools is a pure rotation, so face winding does not change:

```
GH → Blender:  (x, y, z) → (x, -z,  y)
Blender → GH:  (x, y, z) → (x,  z, -y)
```

Apply it to positions, normals, tangents and bitangents. For bone matrices, conjugate by the same rotation.

---

## 5. How the WT → WoR mesh converter works (`wor_skinconv.py`)

`convert_data(wt_skin, wor_template_skin, normal_map, flat_normal)`:

1. **Parse the WoR template** with the same parser used by the rebuild self-test. The template is the game's own skin of a rocker: `Johnny_1` for male characters, `Casey_1` for female ones. It provides the 32-byte UV and face headers, the sector list, the CGeom, the Lst::Head area, the scene header constants and a **known-good material**: the first opaque `852105C8` one.
2. **Parse the WT skin.** For every sMesh, read the material, bounding sphere, group counts, groups (bone indices plus vertices: position, normal, tangent, bitangent, w0, w1), UV records (colour plus the first UV set) and indices.
3. **Build the materials.** For each WT material, clone the template material's bytes and change only the checksum, the name and the three texture checksums:
   - **normal:** the mod's normal map for the material of the biggest mesh (the body), and a generated flat normal map (`ACF1131D`, 64×64 DXT1 (128, 128, 255)) for the rest;
   - **diffuse:** the WT diffuse;
   - **specular:** the WT specular, or `DEC273CB` (black) when there is none.
4. **Build each WoR sMesh,** starting from the template's first sMesh record:
   - **record fields:** the sphere, the flags `0x000105FE`, UV stride 8, the material checksum, face type 4 and the highest bone index at 0x84;
   - **UV records:** `colour + half(u) + half(v)`; only UV set 0 is kept;
   - **vertex groups:** the same groups and bone indices, with every vertex re-encoded as the 32-byte WoR vertex: `u16(w1), u16(w0)`, normalised vectors packed 11:11:10, `BAADF00D`;
   - **indices:** copied unchanged.
5. **Scene:** the bounding box and sphere come from the WT scene, the CGeom holds all meshes (first index 0) and the footer is the empty WoR footer.
6. **Write** with the same writer that rebuilds original skins byte-identically (`write_wor()`). That writer computes every offset, alignment and padding area from section 4.1.

The skeleton is copied as it is. The textures are converted separately (`wor_tex.py`):
- **For each DDS mip level:** tile it, swap the bytes in 16-bit units, then write the X360 header and entries.
- **Mips above `--max-tex`** are dropped, and the smaller ones are reused without recompressing.

---

## 6. Writing a Blender exporter: checklist

The simplest route that is guaranteed to load is to **generate the same structure the converter generates.** Reuse a game skin as the template for the constant blocks, the sectors and the material, and fill in your own meshes.

1. **One sMesh per material** (Blender: split the object by material). Triangulate it. Keep each sMesh under 65535 vertices and indices.
2. **Positions and vectors:**
   - convert to GH axes (4.9), in meters, at the rest pose of the armature you export with the `.ske`;
   - compute tangents with `mesh.calc_tangents()` and the bitangent as `sign × cross(n, t)`;
   - normalise everything before packing.
3. **Weights:**
   - map vertex groups to skeleton **slot indices** by bone name (QBKey of the name);
   - keep the 3 largest weights, normalise them, sort them in descending order;
   - drop zero weights, so the vertex lands in a 1-, 2- or 3-weight group.
4. **Groups:**
   - bucket the vertices by `(weight count, bone indices)`;
   - write all 1-weight groups first, then 2-weight, then 3-weight;
   - **this defines the vertex order**, so remap the face indices and write the UV records in the same order.
5. **Vertices shared between faces must be split** wherever the UV (or normal) differs, as in any game exporter.
6. **UVs:** half floats, with `v = 1 - blender_v`. The colour is ARGB; write `FFFFFFFF` if you have none and set flag `0x10`, or drop it and use stride 4 with flags `0x000105EE`.
7. **Bounding sphere per mesh and box/sphere for the scene.** Rough values are fine (a centre and a radius that contain the vertices).
8. **Highest bone index used** goes in `sMesh + 0x84`.
9. **Validate before testing in the game:**
   - `py wor_skin.py dump out.skin --verts` (it should parse, with sensible positions, normals and weights);
   - `py wor_skin.py obj out.skin out.obj` (open it in Blender);
   - `py wor_skinconv.py rebuild out.skin x.skin` (it must say *identical*: your layout is self-consistent).

**Importer:** `wor_skin.py` already reads both formats. For an importer, the same steps run backwards. Use the weight semantics from section 4.6, not NXTools' 3-weight formula.

---

## 7. Getting the files into the game (summary)

See the README for usage. These are the constraints any tool must respect:
- **File keys:** `qbkey(path + ".skin" / ".tex" / ".ske")`, with backslashes in the path. A script's `mesh` value is `qbkey(path)`, and the game extends it with the extension (QBKey has no final XOR).
- **`cas_pieces`:** new files can be added (the index had room for about 90 more entries), and nothing is checksummed.
- **`qb.pab` (scripts):**
  - files back to back at 32-byte boundaries;
  - no growth of the decompressed size;
  - update `compress.toc.xen` (read size) when recompressing;
  - **no extra rocker profiles**;
  - change values only.
- **New save:** rocker profiles are copied into it, so one is needed after an install.
