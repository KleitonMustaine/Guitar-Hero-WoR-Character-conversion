# Documentation

The documentation is written by AI (sorry for that) but it actually provides some good info at how it works, i plan to write a more comprehensive documentation on the process

## Installation

To get started, simply clone the repository:
```bash
git clone https://github.com/KleitonMustaine/Guitar-Hero-WoR-Character-conversion.git
```

### Building

Requires gcc. From the `repacker` folder:

```bash
gcc -O2 -Wall -I Includes UNCHNK.c libs/common.c libs/chnk.c libs/archive.c Includes/miniz.c -o unchnk.exe
```

### File names (optional)

To show file names instead of only checksums, place `ghwor_keys.txt` from the
[Guitar Hero SDK](https://gitgud.io/fretworks/guitar-hero-sdk) next to `unchnk.exe`

## Usage

1. Copy the archive you want to edit:

```bash
\data\pak\archive\cas_pieces.pak.xen
```

```bash
\data\pak\archive\cas_pieces.pab.xen
```
put them inside any folder you want

2. List the files inside it:

```bash
.\unchnk.exe l test\cas_pieces.pak.xen
```

3. Extract a file, by checksum or by part of its name (i will be using Johnny as an example):

```bash
.\unchnk.exe x test\cas_pieces.pak.xen test\cas_pieces.pab.xen 957706D4 johnny.ske
```

```bash
.\unchnk.exe x test\cas_pieces.pak.xen test\cas_pieces.pab.xen johnny_1.tex johnny.tex
```

4. Replace a file with your own (for example a GHWT:DE skeleton):

```bash
.\unchnk.exe r test\cas_pieces.pak.xen test\cas_pieces.pab.xen 957706D4 MyCharacter.ske.xen
```

5. Check that the replacement went in correctly:

```bash
.\unchnk.exe x test\cas_pieces.pak.xen test\cas_pieces.pab.xen 957706D4 check.ske
```
6. Then copy the edited ones into the game


### Modes

- `d <input.xen> <output>`: decompress a CHNK file
- `c <input> <output.xen>`: compress a file to CHNK
- `l <pak>`: list an archive index
- `x <pak> <pab> <crc|name> <out>`: extract a file from an archive
- `r <pak> <pab> <crc|name> <file>`: replace a file in an archive


## Contributing

Pull requests are always welcome!

If you have some insights or a better approach to this process, feel free to fork the repository and open a PR. I'd love to take a look at your improvements and see what you come up with.

## Credits

- **Format references:** [Guitar Hero SDK](https://gitgud.io/fretworks/guitar-hero-sdk) 010 Editor templates and checksum lists, and [NXTools](https://gitgud.io/fretworks/nxtools) importers.
- **The GHWT:DE and Guitar Hero modding communities.**
