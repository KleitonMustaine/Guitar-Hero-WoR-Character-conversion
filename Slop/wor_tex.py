"""Guitar Hero: Warriors of Rock (X360) - CAS texture tool.

Works on data/pak/archive/<name>.pak.xen (index) + <name>.pab.xen (CHNK-compressed blobs).

  py wor_tex.py list     [--archive cas_pieces] [--type tex]
  py wor_tex.py info     <file_crc>
  py wor_tex.py export   <file_crc> <outdir>            -> one .dds per texture (+ .png preview)
  py wor_tex.py gallery  <outdir>                       -> small PNG of every DXT1/DXT5 + index.html
  py wor_tex.py fill     <file_crc> <tex_crc|all> R G B -> proof of life: solid colour (DXT1/DXT5)
  py wor_tex.py import   <file_crc> <tex_crc> <in.dds|in.png>
                         DDS: same format/size/mips as the original. PNG: same size; DXT1/DXT5 only,
                         compressed and mipmapped by the tool
  py wor_tex.py restore  [name]                         -> put back the .bak copies (all, or one file)
  py wor_tex.py replace  <name|crc> <file>              -> replace any archive file (skin/ske/tex/...)
  py wor_tex.py convert-pc-tex <pc.tex.xen> <out.tex> [--max 1024]
                         GHWT PC/DE texture dictionary -> X360 WoR layout (tiled, swapped); mips
                         above --max are dropped (the smaller mips are reused, no recompression)

file_crc = name checksum from the archive index (e.g. F2280EFC); tex_crc = texture checksum inside the .tex.
"""
import os, re, sys, glob, struct, zlib, shutil

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_data():
    """The extracted game's 'data' folder: $WOR_DATA, or searched next to the tools / current folder."""
    if os.environ.get("WOR_DATA"):
        return os.environ["WOR_DATA"]
    for base in dict.fromkeys((os.getcwd(), HERE, os.path.dirname(HERE))):
        for cand in [base] + glob.glob(os.path.join(base, "*")) + glob.glob(os.path.join(base, "*", "*")):
            if os.path.isfile(os.path.join(cand, "data", "pak", "archive", "cas_pieces.pak.xen")):
                return os.path.join(cand, "data")
            if os.path.isfile(os.path.join(cand, "pak", "archive", "cas_pieces.pak.xen")):
                return cand
    return None


def _find_keys():
    """ghwor_keys.txt from the Guitar Hero SDK (optional, only used to show file names)."""
    if os.environ.get("WOR_KEYS"):
        return os.environ["WOR_KEYS"]
    for base in dict.fromkeys((HERE, os.getcwd(), os.path.dirname(HERE))):
        hits = glob.glob(os.path.join(base, "**", "ghwor_keys.txt"), recursive=True)
        if hits:
            return hits[0]
    return ""


DATA = _find_data() or os.path.join(os.getcwd(), "data")
ARCH = os.path.join(DATA, "pak", "archive")


def require_data():
    if not os.path.isfile(os.path.join(ARCH, "cas_pieces.pak.xen")):
        raise SystemExit("Game data not found. Set WOR_DATA to the extracted game's 'data' folder, e.g.\n"
                         '  set WOR_DATA=C:\\games\\Guitar Hero - Warriors of Rock\\data')

TYPES = {0x8BFA5E8E: "tex", 0x64112E85: "skin", 0xDAD5E950: "img", 0x4AE71C19: "clt",
         0x7330095C: "ske", 0x4BC1E85E: "mqb", 0x2CB3EF3B: "last"}
TYPE_TEX, TYPE_LAST = 0x8BFA5E8E, 0x2CB3EF3B
CHUNK = 0x80000
ALIGN = 0x800

# xenos format -> (name, block dim, bytes per block, dds fourcc or None)
XFMT = {0x12: ("DXT1", 4, 8, b"DXT1"), 0x13: ("DXT3", 4, 16, b"DXT3"), 0x14: ("DXT5", 4, 16, b"DXT5"),
        0x31: ("DXN", 4, 16, b"ATI2"), 0x3B: ("DXT5A", 4, 8, b"ATI1"),
        0x06: ("A8R8G8B8", 1, 4, None), 0x03: ("A1R5G5B5", 1, 2, None), 0x04: ("R5G6B5", 1, 2, None),
        0x0F: ("A4R4G4B4", 1, 2, None), 0x02: ("L8", 1, 1, None)}


KEYS_FILE = None
_keys = None


def name_of(crc):
    """File name for a checksum, from the GH SDK's ghwor_keys.txt (empty if unknown)."""
    global _keys, KEYS_FILE
    if _keys is None:
        _keys = {}
        KEYS_FILE = _find_keys()
        if KEYS_FILE and os.path.exists(KEYS_FILE):
            for line in open(KEYS_FILE, encoding="utf-8", errors="replace"):
                p = line.rstrip("\n").split(" ", 1)
                if len(p) == 2:
                    _keys[int(p[0], 16)] = p[1].replace("c:/gh6_burn/data/", "")
    return _keys.get(crc, "")


def align(v, a):
    return (v + a - 1) & ~(a - 1)


def log2_ceil(v):
    return (v - 1).bit_length() if v > 1 else 0


# ---------------------------------------------------------------- archive (CHNK)

def unchnk(buf):
    pos, out = 0, bytearray()
    while True:
        magic, hsz, csz, nxt = struct.unpack_from(">4sIII", buf, pos)
        if magic != b"CHNK":
            raise ValueError("bad CHNK at 0x%X" % pos)
        out += zlib.decompressobj(-15).decompress(buf[pos + hsz:pos + hsz + csz])
        if nxt == 0xFFFFFFFF:
            return bytes(out)
        pos += nxt


def chnk_parts(buf):
    """{uncompressed offset: (raw deflate bytes, uncompressed size)} of a CHNK stream"""
    pos, res = 0, {}
    while True:
        magic, hsz, csz, nxt, _, usz, uoff = struct.unpack_from(">4s6I", buf, pos)
        res[uoff] = (buf[pos + hsz:pos + hsz + csz], usz)
        if nxt == 0xFFFFFFFF:
            return res
        pos += nxt


def mkchnk(data, reuse=None):
    """reuse: (original uncompressed data, chnk_parts of the original) -> chunks whose bytes did
    not change keep the original compressed bytes (smaller than our zlib output, byte-identical)"""
    parts = []
    for uoff in range(0, max(len(data), 1), CHUNK):
        piece = data[uoff:uoff + CHUNK]
        if reuse and uoff in reuse[1] and reuse[0][uoff:uoff + CHUNK] == piece and reuse[1][uoff][1] == len(piece):
            comp = reuse[1][uoff][0]
        else:
            c = zlib.compressobj(9, zlib.DEFLATED, -15)
            comp = c.compress(piece) + c.flush()
        parts.append((uoff, len(piece), comp, align(0x80 + len(comp), ALIGN)))
    out = bytearray()
    for i, (uoff, usz, comp, slot) in enumerate(parts):
        last = i == len(parts) - 1
        hdr = struct.pack(">4s7I", b"CHNK", 0x80, len(comp), 0xFFFFFFFF if last else slot,
                          0 if last else parts[i + 1][3], usz, uoff, 0)
        out += hdr.ljust(0x80, b"\0") + comp
        out += b"\0" * (slot - 0x80 - len(comp))
    return bytes(out), len(parts), parts[0][3]


class Archive:
    def __init__(self, name="cas_pieces", pak=None, pab=None):
        if not pak:
            require_data()
        self.pak = pak or os.path.join(ARCH, name + ".pak.xen")
        self.pab = pab or os.path.join(ARCH, name + ".pab.xen")
        raw = open(self.pak, "rb").read()
        self.ents = []
        for i in range(0, len(raw), 32):
            e = list(struct.unpack_from(">8I", raw, i))
            if not any(e):
                break
            self.ents.append(e)
        self.index_size = len(raw)

    def find(self, crc, typ=TYPE_TEX):
        """crc = hex checksum, or a (part of a) file name from the dictionary, e.g. johnny_1"""
        if isinstance(crc, str) and not re.fullmatch(r"(0x)?[0-9a-fA-F]{8}", crc):
            hits = [e for e in self.ents if e[0] == typ and crc.lower() in name_of(e[4]).lower()]
            if len(hits) != 1:
                for e in hits[:20]:
                    print("  %08X %s" % (e[4], name_of(e[4])))
                raise SystemExit("%d files match '%s' - be more specific" % (len(hits), crc))
            return hits[0]
        crc = int(crc, 16) if isinstance(crc, str) else crc
        for e in self.ents:
            if e[4] == crc and e[0] != TYPE_LAST:
                return e
        raise SystemExit("file %08X not in archive" % crc)

    def read(self, e):
        with open(self.pab, "rb") as f:
            f.seek(e[1])
            return unchnk(f.read(e[2]))

    def backup(self):
        for p in (self.pak, self.pab):
            if not os.path.exists(p + ".bak"):
                print("backup ->", p + ".bak")
                shutil.copyfile(p, p + ".bak")

    def add(self, typ, crc, data):
        """Add a new file (or replace it if the checksum already exists)."""
        for e in self.ents:
            if e[4] == crc and e[0] == typ:
                return self.write(e, data)
        if 32 * (len(self.ents) + 1) > self.index_size:
            raise SystemExit("archive index is full")
        e = [typ, 0, 0, 0, crc, 0, 0, 0x200]
        last = next(i for i, x in enumerate(self.ents) if x[0] == TYPE_LAST)
        self.ents.insert(last, e)
        e[2] = 0  # forces append
        self.write(e, data)

    def write(self, e, data):
        self.backup()
        blob, nchunks, first = mkchnk(data)
        with open(self.pab, "r+b") as f:
            if len(blob) <= e[2]:
                f.seek(e[1]); f.write(blob + b"\0" * (e[2] - len(blob)))
                where = "in place"
            else:
                f.seek(0, 2); end = align(f.tell(), ALIGN)
                f.seek(end); f.write(blob)
                e[1] = end
                for l in self.ents:
                    if l[0] == TYPE_LAST:
                        l[1] = end + len(blob)
                where = "appended at 0x%X" % end
        e[2], e[3], e[5], e[6] = len(blob), len(data), nchunks, first
        raw = b"".join(struct.pack(">8I", *x) for x in self.ents).ljust(self.index_size, b"\0")
        open(self.pak, "wb").write(raw)
        print("wrote %08X: %d bytes compressed (%s)" % (e[4], len(blob), where))


# ---------------------------------------------------------------- .tex dictionary

class Tex:
    def __init__(self, data, w, h, levels, xfmt, endian, pitch_tex, base, mips, crc, tiled, kind):
        self.w, self.h, self.levels, self.xfmt, self.endian = w, h, levels, xfmt, endian
        self.pitch_tex, self.base, self.mips, self.crc, self.tiled, self.kind = pitch_tex, base, mips, crc, tiled, kind
        self.name, self.bw, self.bpb, self.fourcc = XFMT.get(xfmt, ("fmt%02X" % xfmt, 1, 4, None))

    def blocks(self, n):
        return max((n + self.bw - 1) // self.bw, 1)

    def layout(self):
        """[(level_w, level_h, byte_offset, pitch_blocks, x_blk, y_blk)] following the Xenos mip rules."""
        l2w, l2h = log2_ceil(self.w), log2_ceil(self.h)
        l2s = min(l2w, l2h)
        pbase = l2s - 4 if l2s > 4 else 0
        out, cur, tail = [], self.mips, None
        for lv in range(self.levels):
            if lv == 0:
                lw, lh = self.w, self.h
                pitch = self.pitch_tex // self.bw
            else:
                lw, lh = max((1 << l2w) >> lv, 1), max((1 << l2h) >> lv, 1)
                pitch = align(self.blocks(lw), 32)
            if lv >= pbase and l2s <= 4 + lv:  # packed mip tail
                if tail is None:
                    tail = (self.base if lv == 0 else cur, pitch)
                pm = lv - pbase
                if pm < 3:
                    x, y = (0, 16 >> pm) if l2w > l2h else (16 >> pm, 0)
                elif l2w > l2h:
                    x, y = (1 << (l2w - pbase)) >> (pm - 2), 0
                else:
                    x, y = 0, (1 << (l2h - pbase)) >> (pm - 2)
                out.append((lw, lh, tail[0], tail[1], x // self.bw, y // self.bw))
                continue
            off = self.base if lv == 0 else cur
            out.append((lw, lh, off, pitch, 0, 0))
            if lv > 0:
                cur += align(pitch * align(self.blocks(lh), 32) * self.bpb, 4096)
        return out

    def _addr(self, lvl):
        lw, lh, off, pitch, xb, yb = lvl
        bw, bh = self.blocks(lw), self.blocks(lh)
        lb = self.bpb.bit_length() - 1
        for y in range(bh):
            for x in range(bw):
                if self.tiled:
                    idx = tiled_offset(x + xb, y + yb, pitch, lb)
                else:
                    idx = (y + yb) * pitch + x + xb
                yield off + idx * self.bpb

    def get_level(self, buf, lv):
        """Linear, little-endian (PC/DDS order) bytes of one mip level."""
        out = bytearray()
        for a in self._addr(self.layout()[lv]):
            out += buf[a:a + self.bpb]
        return swap(bytes(out), self.endian)

    def put_level(self, buf, lv, linear):
        linear = swap(linear, self.endian)
        for i, a in enumerate(self._addr(self.layout()[lv])):
            buf[a:a + self.bpb] = linear[i * self.bpb:(i + 1) * self.bpb]

    def level_size(self, lv):
        lw, lh = self.layout()[lv][:2]
        return self.blocks(lw) * self.blocks(lh) * self.bpb


def tiled_offset(x, y, width, log_bpb):
    """XGAddress2DTiledOffset: element index of block (x, y) in a tiled surface of `width` blocks."""
    aw = (width + 31) & ~31
    macro = ((x >> 5) + (y >> 5) * (aw >> 5)) << (log_bpb + 7)
    micro = ((x & 7) + ((y & 6) << 2)) << log_bpb
    off = macro + ((micro & ~15) << 1) + (micro & 15) + ((y & 8) << (3 + log_bpb)) + ((y & 1) << 4)
    return (((off & ~511) << 3) + ((off & 448) << 2) + (off & 63) + ((y & 16) << 7)
            + (((((y & 8) >> 2) + (x >> 3)) & 3) << 6)) >> log_bpb


def swap(b, endian):
    if endian == 1:  # 8in16
        a = bytearray(b); a[0::2], a[1::2] = b[1::2], b[0::2]; return bytes(a)
    if endian == 2:  # 8in32
        a = bytearray(b)
        a[0::4], a[1::4], a[2::4], a[3::4] = b[3::4], b[2::4], b[1::4], b[0::4]
        return bytes(a)
    return b


def parse_tex(data):
    magic, ver, cnt, meta = struct.unpack_from(">IHHI", data, 0)
    if magic != 0xFACECAA7:
        raise ValueError("not a .tex dictionary")
    out = []
    for k in range(cnt):
        o = meta + k * 0x28
        _, _, _, kind, crc, w, h, _, _, _, _, levels, bpp, fmt, _, mips, hdr, _, base = \
            struct.unpack_from(">BBBBIHHHHHHBBBBIIII", data, o)
        fc = struct.unpack_from(">6I", data, hdr + 0x1C)
        out.append(Tex(data, w, h, levels, fc[1] & 0x3F, (fc[1] >> 6) & 3, ((fc[0] >> 22) & 0x1FF) * 32,
                       base, mips, crc, fc[0] >> 31, kind))
    return out


# ---------------------------------------------------------------- DDS / PNG

def dds_bytes(t, levels):
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000
    if t.fourcc:
        pf = struct.pack("<II4s5I", 32, 0x4, t.fourcc, 0, 0, 0, 0, 0)
    else:
        masks = {"A8R8G8B8": (0x41, 32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000),
                 "A1R5G5B5": (0x41, 16, 0x7C00, 0x3E0, 0x1F, 0x8000),
                 "R5G6B5": (0x40, 16, 0xF800, 0x7E0, 0x1F, 0),
                 "A4R4G4B4": (0x41, 16, 0xF00, 0xF0, 0xF, 0xF000),
                 "L8": (0x20000, 8, 0xFF, 0, 0, 0)}[t.name]
        pf = struct.pack("<II4s5I", 32, masks[0], b"\0\0\0\0", *masks[1:])
    hdr = struct.pack("<4sIIIIIII44x", b"DDS ", 124, flags, t.h, t.w, t.level_size(0), 1, len(levels))
    caps = struct.pack("<IIII4x", 0x1000 | 0x8 | 0x400000, 0, 0, 0)
    return hdr + pf + caps + b"".join(levels)


def read_dds(path, t):
    d = open(path, "rb").read()
    if d[:4] != b"DDS ":
        raise SystemExit("not a DDS file")
    h, w, _, _, mipcount = struct.unpack_from("<IIIII", d, 12)
    fourcc = d[84:88]
    if (w, h) != (t.w, t.h):
        raise SystemExit("DDS is %dx%d, original is %dx%d - must match" % (w, h, t.w, t.h))
    if t.fourcc and fourcc != t.fourcc and not (t.fourcc == b"ATI2" and fourcc == b"BC5U"):
        raise SystemExit("DDS format %r, original needs %r" % (fourcc, t.fourcc))
    pos = 128 + (20 if fourcc == b"DX10" else 0)
    levels = []
    for lv in range(t.levels):
        n = t.level_size(lv)
        if pos + n > len(d):
            raise SystemExit("DDS has only %d mip levels, need %d (save with mipmaps)" % (lv, t.levels))
        levels.append(d[pos:pos + n]); pos += n
    return levels


def read_png(path):
    """Minimal PNG reader: 8-bit RGB/RGBA/grey/palette, non-interlaced -> (w, h, RGBA bytes)."""
    d = open(path, "rb").read()
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("not a PNG file")
    pos, idat, pal, trns = 8, b"", None, b""
    while pos < len(d):
        n, tag = struct.unpack_from(">I4s", d, pos)
        body = d[pos + 8:pos + 8 + n]; pos += 12 + n
        if tag == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", body)
        elif tag == b"PLTE": pal = body
        elif tag == b"tRNS": trns = body
        elif tag == b"IDAT": idat += body
    if depth != 8 or inter:
        raise SystemExit("PNG must be 8 bits per channel and not interlaced")
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw, stride = zlib.decompress(idat), w * ch
    rows, prev = [], bytearray(stride)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - ch] if i >= ch else 0
            b = prev[i]; c = prev[i - ch] if i >= ch else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(bytes(line)); prev = line
    px = bytearray()
    for line in rows:
        if ctype == 6: px += line; continue
        for x in range(w):
            if ctype == 2: px += line[x * 3:x * 3 + 3] + b"\xff"
            elif ctype == 0: px += bytes((line[x],) * 3) + b"\xff"
            elif ctype == 4: px += bytes((line[2 * x],) * 3) + bytes((line[2 * x + 1],))
            else:
                i = line[x]; px += pal[i * 3:i * 3 + 3] + bytes((trns[i] if i < len(trns) else 255,))
    return w, h, bytes(px)


def downsample(w, h, px):
    nw, nh = max(w // 2, 1), max(h // 2, 1)
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        for x in range(nw):
            for c in range(4):
                s = 0
                for dy in (0, 1):
                    for dx in (0, 1):
                        sx, sy = min(2 * x + dx, w - 1), min(2 * y + dy, h - 1)
                        s += px[(sy * w + sx) * 4 + c]
                out[(y * nw + x) * 4 + c] = (s + 2) // 4
    return nw, nh, bytes(out)


def encode_dxt(name, w, h, px):
    """Simple DXT1/DXT5 encoder (bounding-box endpoints, nearest index)."""
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            blk = []
            for i in range(16):
                x, y = min(bx + i % 4, w - 1), min(by + i // 4, h - 1)
                o = (y * w + x) * 4
                blk.append(px[o:o + 4])
            if name == "DXT5":
                al = [p[3] for p in blk]
                a0, a1 = max(al), min(al)
                if a0 == a1:
                    out += bytes((a0, a1)) + b"\0" * 6
                else:
                    pal = [a0, a1] + [((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)]
                    bits = 0
                    for i, a in enumerate(al):
                        bits |= min(range(8), key=lambda k: abs(pal[k] - a)) << (3 * i)
                    out += bytes((a0, a1)) + bits.to_bytes(6, "little")
            lo = [min(p[c] for p in blk) for c in range(3)]
            hi = [max(p[c] for p in blk) for c in range(3)]
            inset = [(hi[c] - lo[c]) >> 4 for c in range(3)]
            lo = [lo[c] + inset[c] for c in range(3)]; hi = [hi[c] - inset[c] for c in range(3)]
            def q(c): return ((c[0] >> 3) << 11) | ((c[1] >> 2) << 5) | (c[2] >> 3)
            v0, v1 = q(hi), q(lo)
            if v0 < v1: v0, v1 = v1, v0
            if v0 == v1:
                out += struct.pack("<HHI", v0, v1, 0); continue
            p0, p1 = c565(v0), c565(v1)
            pal = [p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)),
                   tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))]
            idx = 0
            for i, p in enumerate(blk):
                k = min(range(4), key=lambda k: (pal[k][0] - p[0]) ** 2 + (pal[k][1] - p[1]) ** 2 + (pal[k][2] - p[2]) ** 2)
                idx |= k << (2 * i)
            out += struct.pack("<HHI", v0, v1, idx)
    return bytes(out)


def png_levels(path, t):
    if t.name not in ("DXT1", "DXT5"):
        raise SystemExit("PNG import only for DXT1/DXT5 (this one is %s) - use a DDS" % t.name)
    w, h, px = read_png(path)
    if (w, h) != (t.w, t.h):
        raise SystemExit("PNG is %dx%d, original is %dx%d - must match" % (w, h, t.w, t.h))
    levels = []
    for lv in range(t.levels):
        if lv:
            w, h, px = downsample(w, h, px)
        levels.append(encode_dxt(t.name, w, h, px))
    return levels


def c565(v):
    return ((v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)


def decode(t, lv, lin):
    """RGBA bytes for a preview (DXT1/DXT5/DXN/A8R8G8B8/A1R5G5B5)."""
    lw, lh = t.layout()[lv][:2]
    bw = t.blocks(lw)
    W, H = bw * t.bw, t.blocks(lh) * t.bw
    px = bytearray(W * H * 4)
    if t.bw == 1:
        for i in range(lw * lh):
            if t.name == "A8R8G8B8":
                b, g, r, a = lin[i * 4:i * 4 + 4]
            elif t.name == "A1R5G5B5":
                v = struct.unpack_from("<H", lin, i * 2)[0]
                r, g, b, a = ((v >> 10) & 31) * 8, ((v >> 5) & 31) * 8, (v & 31) * 8, 255 if v >> 15 else 0
            else:
                r = g = b = lin[i * t.bpb]; a = 255
            px[i * 4:i * 4 + 4] = bytes((r, g, b, a))
        return lw, lh, bytes(px)
    for bi in range(len(lin) // t.bpb):
        bx, by = (bi % bw) * 4, (bi // bw) * 4
        blk = lin[bi * t.bpb:(bi + 1) * t.bpb]
        alpha = [255] * 16
        if t.name == "DXN":
            def bc4(s):
                a0, a1 = s[0], s[1]
                pal = [a0, a1] + ([((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)] if a0 > a1 else
                                  [((4 - i) * a0 + (i + 1) * a1) // 5 for i in range(4)] + [0, 255])
                bits = int.from_bytes(s[2:8], "little")
                return [pal[(bits >> (3 * i)) & 7] for i in range(16)]
            rr, gg = bc4(blk[:8]), bc4(blk[8:])
            cols = [(rr[i], gg[i], 255) for i in range(16)]
        else:
            if t.name == "DXT5":
                a0, a1 = blk[0], blk[1]
                pal = [a0, a1] + ([((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)] if a0 > a1 else
                                  [((4 - i) * a0 + (i + 1) * a1) // 5 for i in range(4)] + [0, 255])
                bits = int.from_bytes(blk[2:8], "little")
                alpha = [pal[(bits >> (3 * i)) & 7] for i in range(16)]
                blk = blk[8:]
            v0, v1, idx = struct.unpack_from("<HHI", blk)
            p0, p1 = c565(v0), c565(v1)
            if v0 > v1 or t.name == "DXT5":
                pal = [p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)),
                       tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))]
            else:
                pal = [p0, p1, tuple((a + b) // 2 for a, b in zip(p0, p1)), (0, 0, 0)]
            cols = [pal[(idx >> (2 * i)) & 3] for i in range(16)]
            if t.name == "DXT1" and v0 <= v1:
                alpha = [0 if (idx >> (2 * i)) & 3 == 3 else 255 for i in range(16)]
        for i in range(16):
            o = ((by + i // 4) * W + bx + i % 4) * 4
            px[o:o + 4] = bytes((*cols[i], alpha[i]))
    rows = b"".join(px[y * W * 4:y * W * 4 + lw * 4] for y in range(min(lh, H)))
    return lw, min(lh, H), rows


def write_png(path, w, h, rgba):
    raw = b"".join(b"\0" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    def chunk(tag, d):
        return struct.pack(">I", len(d)) + tag + d + struct.pack(">I", zlib.crc32(tag + d))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- commands

def cmd_list(a, typ="tex"):
    for e in a.ents:
        if TYPES.get(e[0]) == typ or typ == "all":
            print("%08X  %-4s  %8d  %s" % (e[4], TYPES.get(e[0], "?"), e[3], name_of(e[4])))


def cmd_info(a, crc):
    data = a.read(a.find(crc))
    for i, t in enumerate(parse_tex(data)):
        print("%2d  %08X  %4dx%-4d  %-9s levels=%d tiled=%d endian=%d kind=%d base=0x%X mips=0x%X" % (
            i, t.crc, t.w, t.h, t.name, t.levels, t.tiled, t.endian, t.kind, t.base, t.mips))


def usable(t):
    return t.kind != 5 and t.xfmt in XFMT  # kind 5 = cube map, not handled


def cmd_export(a, crc, outdir):
    os.makedirs(outdir, exist_ok=True)
    data = a.read(a.find(crc))
    open(os.path.join(outdir, "%s.tex" % crc.upper()), "wb").write(data)
    for t in parse_tex(data):
        if not usable(t):
            print("skip %08X (%s kind=%d)" % (t.crc, t.name, t.kind)); continue
        levels = [t.get_level(data, lv) for lv in range(t.levels)]
        base = os.path.join(outdir, "%08X_%s" % (t.crc, t.name))
        open(base + ".dds", "wb").write(dds_bytes(t, levels))
        write_png(base + ".png", *decode(t, 0, levels[0]))
        print("exported", base + ".dds")


def cmd_gallery(a, outdir, maxdim=64):
    os.makedirs(outdir, exist_ok=True)
    html = ["<html><body style='background:#222;color:#ddd;font:12px monospace'>"]
    texs = [e for e in a.ents if e[0] == TYPE_TEX]
    for n, e in enumerate(texs):
        try:
            data = a.read(e); ts = parse_tex(data)
        except Exception as ex:
            print("skip %08X: %s" % (e[4], ex)); continue
        cells = []
        for t in ts:
            if not usable(t) or t.name not in ("DXT1", "DXT5"):
                continue
            lv = next((i for i, l in enumerate(t.layout()) if max(l[0], l[1]) <= maxdim), t.levels - 1)
            fn = "%08X_%08X.png" % (e[4], t.crc)
            write_png(os.path.join(outdir, fn), *decode(t, lv, t.get_level(data, lv)))
            cells.append("<img src='%s' title='%08X %dx%d %s'>" % (fn, t.crc, t.w, t.h, t.name))
        if cells:
            html.append("<div><b>%08X</b> %s</div>" % (e[4], " ".join(cells)))
        if n % 100 == 0:
            print("%d/%d" % (n, len(texs)), flush=True)
    open(os.path.join(outdir, "index.html"), "w").write("\n".join(html + ["</body></html>"]))
    print("done ->", os.path.join(outdir, "index.html"))


def solid_block(t, r, g, b):
    v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    col = struct.pack("<HHI", v, v, 0)
    return (b"\xff\xff" + b"\0" * 6 + col) if t.name == "DXT5" else col


def cmd_fill(a, crc, which, r, g, b):
    e = a.find(crc)
    data = bytearray(a.read(e))
    n = 0
    for t in parse_tex(data):
        if which.lower() != "all" and t.crc != int(which, 16):
            continue
        if not usable(t) or t.name not in ("DXT1", "DXT5"):
            print("skip %08X (%s)" % (t.crc, t.name)); continue
        blk = solid_block(t, r, g, b)
        for lv in range(t.levels):
            t.put_level(data, lv, blk * (t.level_size(lv) // t.bpb))
        n += 1
    if not n:
        raise SystemExit("no matching DXT1/DXT5 texture")
    a.write(e, bytes(data))


def cmd_import(a, crc, which, path):
    e = a.find(crc)
    data = bytearray(a.read(e))
    t = next((t for t in parse_tex(data) if t.crc == int(which, 16)), None)
    if t is None or not usable(t):
        raise SystemExit("texture %s not found / not supported" % which)
    levels = png_levels(path, t) if path.lower().endswith(".png") else read_dds(path, t)
    for lv, lin in enumerate(levels):
        t.put_level(data, lv, lin)
    a.write(e, bytes(data))


def cmd_restore(a, which=None):
    if which is None:
        for p in (a.pak, a.pab):
            if os.path.exists(p + ".bak"):
                shutil.copyfile(p + ".bak", p); print("restored", p)
        return
    # one file: take its original bytes from the .bak archive
    e = find_any(a, which)
    orig = Archive.__new__(Archive)
    orig.pak, orig.pab = a.pak + ".bak", a.pab + ".bak"
    if not os.path.exists(orig.pab):
        raise SystemExit("no backup yet - nothing was modified")
    Archive.__init__(orig, None, orig.pak, orig.pab)
    a.write(e, orig.read(orig.find(e[4])))


def find_any(a, which):
    """Entry by checksum or by (unique) name substring, any file type."""
    if re.fullmatch(r"(0x)?[0-9a-fA-F]{8}", which):
        return a.find(which)
    hits = [e for e in a.ents if e[0] != TYPE_LAST and which.lower() in name_of(e[4]).lower()]
    exact = [e for e in hits if name_of(e[4]).lower().endswith(which.lower())]
    if len(exact) == 1:
        return exact[0]
    if len(hits) != 1:
        for e in hits[:20]:
            print("  %08X %s" % (e[4], name_of(e[4])))
        raise SystemExit("%d files match '%s' - be more specific" % (len(hits), which))
    return hits[0]


def cmd_replace(a, which, path):
    e = find_any(a, which)
    print("replacing %s with %s" % (name_of(e[4]), path))
    a.write(e, open(path, "rb").read())


# ---------------------------------------------------------------- PC (GHWT:DE) .tex -> X360 .tex

D3D_HDR = bytes.fromhex("00200003 00000001 00000000 00000000 00000000 ffff0000 ffff0000")
PC_FMT = {b"DXT1": (0x12, 1, 4), b"DXT5": (0x14, 5, 8)}  # fourcc -> (xenos fmt, entry fmt byte, bpp)


def build_x360_tex(textures):
    """textures: [(crc, kind, w, h, fourcc, [linear little-endian level data...])] -> X360 .tex bytes"""
    cnt = len(textures)
    buckets = 1 << log2_ceil(max(cnt, 1))
    meta = 0x1C + 28 + 24 * buckets  # 0x1C header + hash area (filled with 0xEF, used at runtime)
    hdr0 = meta + cnt * 0x28
    end_hdrs = hdr0 + cnt * 0x34
    out = bytearray(b"\xEF" * end_hdrs)
    struct.pack_into(">IHHIIiII", out, 0, 0xFACECAA7, 0x011C, cnt, meta, end_hdrs, -1,
                     log2_ceil(buckets) + 1, 0x1C)
    cur = align(end_hdrs, 0x1000)
    for k, tx in enumerate(textures):
        crc, kind, w, h, fourcc, levels = tx[:6]
        xfmt, fmtbyte, bpp = PC_FMT[fourcc]
        if len(tx) > 6:
            fmtbyte = tx[6]  # keep the source entry's format byte (DXT1 with alpha uses 2)
        n = len(levels)
        pitch_tex = max(align(w, 128), 128)
        base_size = align((pitch_tex // 4) * align(max(h // 4, 1), 32) * (8 if bpp == 4 else 16), 4096)
        base = cur
        t = Tex(None, w, h, n, xfmt, 1, pitch_tex, base, base + base_size, crc, 1, kind)
        lay = t.layout()
        mip_end = base + base_size
        for lv in range(1, n):
            lw, lh, off, pitch, xb, yb = lay[lv]
            if min(log2_ceil(w), log2_ceil(h)) <= 4 + lv:  # packed mip tail: one 4 KB tile
                mip_end = off + 0x1000
                break
            mip_end = off + align(pitch * align(t.blocks(lh), 32) * t.bpb, 4096)
        size = mip_end - base
        cur = align(mip_end, 0x1000)
        out += b"\0" * (base - len(out))
        out += b"\xCE\xFA" * ((cur - base) // 2)  # unused tile space is 0xFACE-filled, like the originals
        for lv, lin in enumerate(levels):
            t.put_level(out, lv, lin)
        hdr = hdr0 + k * 0x34
        struct.pack_into(">BBBBIHHHHHHBBBBIIII", out, meta + k * 0x28, 0x0A, 0x28, 0x02, kind, crc,
                         w, h, 1, w, h, 1, n, bpp, fmtbyte, 0,
                         base + base_size, hdr, size, base)
        fetch = struct.pack(">6I", 0x80000002 | ((pitch_tex // 32) << 22), xfmt | (1 << 6),
                            (w - 1) | ((h - 1) << 13), 0x00000D10, (n - 1) << 6, 0x00000A00)
        out[hdr:hdr + 0x34] = D3D_HDR + fetch
    return bytes(out)


def read_pc_tex(data, max_size):
    """GHWT PC .tex (DDS inside) -> list for build_x360_tex, dropping mips above max_size."""
    magic, ver, cnt, meta = struct.unpack_from(">IHHI", data, 0)
    if magic != 0xFACECAA7:
        raise SystemExit("not a .tex dictionary")
    res = []
    for k in range(cnt):
        _, _, _, kind, crc = struct.unpack_from(">BBBBI", data, meta + k * 0x28)
        fmtbyte = data[meta + k * 0x28 + 0x16]
        off, size = struct.unpack_from(">II", data, meta + k * 0x28 + 0x1C)  # PC: DDS offset, DDS size
        d = data[off:off + size]
        h, w, _, _, mips = struct.unpack_from("<IIIII", d, 12)
        fourcc = d[84:88]
        if fourcc not in PC_FMT:
            raise SystemExit("texture %08X: format %r not supported yet" % (crc, fourcc))
        bpb = 8 if fourcc == b"DXT1" else 16
        pos, levels, lw, lh = 128, [], w, h
        for lv in range(max(mips, 1)):
            n = max(lw // 4, 1) * max(lh // 4, 1) * bpb
            levels.append(d[pos:pos + n]); pos += n
            lw, lh = max(lw // 2, 1), max(lh // 2, 1)
        while max(w, h) > max_size and len(levels) > 1:
            levels.pop(0); w, h = max(w // 2, 1), max(h // 2, 1)
        print("  %08X kind=%d %4dx%-4d %s levels=%d" % (crc, kind, w, h, fourcc.decode(), len(levels)))
        res.append((crc, kind, w, h, fourcc, levels, fmtbyte))
    return res


def qbkey(s, state=0xFFFFFFFF):
    """Neversoft QBKey: CRC-32 of the lower-case string, no final XOR. Because there is no final XOR,
    qbkey(path + ext) == qbkey(ext, state=qbkey(path)): the game derives file keys this way
    (QB 'mesh' = qbkey of the path, archive file = that + ".skin" / ".tex")."""
    c = state
    for ch in s.lower().encode():
        c ^= ch
        for _ in range(8):
            c = (c >> 1) ^ (0xEDB88320 if c & 1 else 0)
    return c


FLAT_NORMAL = qbkey("tex/wor_tools_flat_normal")


def flat_normal_texture():
    """64x64 DXT1 normal map pointing straight out (128,128,255), 6 levels."""
    blk = struct.pack("<HHI", (16 << 11) | (32 << 5) | 31, (16 << 11) | (32 << 5) | 31, 0)
    levels = [blk * (max(s // 4, 1) ** 2) for s in (64, 32, 16, 8, 4, 2)]
    return (FLAT_NORMAL, 1, 64, 64, b"DXT1", levels, 1)


def cmd_convert_pc_tex(src, dst, max_size=1024, add_flat=False):
    tex = read_pc_tex(open(src, "rb").read(), max_size)
    if add_flat:
        tex.append(flat_normal_texture())
        print("  %08X flat normal map added (use it for materials without a normal map)" % FLAT_NORMAL)
    out = build_x360_tex(tex)
    open(dst, "wb").write(out)
    print("wrote %s (%d bytes)" % (dst, len(out)))
    # self-check: parse back and compare every level with the source
    for t, tx in zip(parse_tex(out), tex):
        crc, levels = tx[0], tx[5]
        for lv in range(len(levels)):
            if t.get_level(out, lv) != levels[lv]:
                raise SystemExit("self-check failed: %08X level %d" % (crc, lv))
    print("self-check ok: all levels read back identical")


def main(argv):
    archive = "cas_pieces"
    if "--archive" in argv:
        i = argv.index("--archive"); archive = argv[i + 1]; del argv[i:i + 2]
    if not argv:
        print(__doc__); return
    a = Archive(archive)
    c, args = argv[0], argv[1:]
    if c == "list": cmd_list(a, args[0] if args else "tex")
    elif c == "info": cmd_info(a, args[0])
    elif c == "export": cmd_export(a, args[0], args[1])
    elif c == "gallery": cmd_gallery(a, args[0])
    elif c == "fill": cmd_fill(a, args[0], args[1], *map(int, args[2:5]))
    elif c == "import": cmd_import(a, args[0], args[1], args[2])
    elif c == "restore": cmd_restore(a, args[0] if args else None)
    elif c == "replace": cmd_replace(a, args[0], args[1])
    elif c == "convert-pc-tex":
        mx = 1024
        if "--max" in args:
            i = args.index("--max"); mx = int(args[i + 1]); del args[i:i + 2]
        flat = "--flat-normal" in args
        if flat: args.remove("--flat-normal")
        cmd_convert_pc_tex(args[0], args[1], mx, flat)
    else: print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
