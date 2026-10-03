"""GH:WoR (X360) standard .pak/.pab pair (e.g. data/compressed/PAK/qb.pak.xen + qb.pab.xen).

Both files are CHNK-compressed on disc. After decompression:
  pak = index of 32-byte entries (type, offset in pab, size, 0, full-name crc, short-name crc, 0, 0),
        ending with a '.last' entry, zero-padded to 4 KB
  pab = file data, each file 32-byte aligned (zero padding), '.last' data = ABABABAB, padded to 4 KB

  py wor_pak.py list <name>                    e.g. list qb
  py wor_pak.py extract <name> <outdir>
"""
import os, sys, struct
import wor_tex as W

PAKDIR = os.path.join(W.DATA, "compressed", "PAK")
TYPE_LAST = 0x2CB3EF3B


class Pak:
    def __init__(self, name, from_backup=False):
        """from_backup: start from the untouched .bak copies (if they exist)"""
        self.name = name
        self.pak_path = os.path.join(PAKDIR, name + ".pak.xen")
        self.pab_path = os.path.join(PAKDIR, name + ".pab.xen")
        # single-file paks keep the data inside the .pak, offsets relative to each entry
        self.single = not os.path.exists(self.pab_path)

        def src(p):
            return p + ".bak" if from_backup and os.path.exists(p + ".bak") else p
        pak = W.unchnk(open(src(self.pak_path), "rb").read())
        pab = pak if self.single else W.unchnk(open(src(self.pab_path), "rb").read())
        self.orig_sizes = (len(pak), len(pab))
        self.load(pak, pab)

    def load(self, pak, pab):
        self.entries = []   # [list of 8 fields, data]
        for i in range(0, len(pak), 32):
            e = list(struct.unpack_from(">8I", pak, i))
            base = i if self.single else 0
            if e[0] == TYPE_LAST:
                self.last = e
                break
            self.entries.append([e, pab[base + e[1]:base + e[1] + e[2]]])

    def find(self, part):
        hits = [x for x in self.entries if part.lower() in W.name_of(x[0][4]).lower()]
        if len(hits) != 1:
            raise SystemExit("%d files match '%s'" % (len(hits), part))
        return hits[0]

    def build(self):
        n = len(self.entries) + 1
        start = W.align(32 * n, 0x1000) if self.single else 0
        pab = bytearray()
        idx = bytearray()
        for k, (e, data) in enumerate(self.entries):
            # files must follow each other at the next 32-byte boundary: the game walks the pab
            # sequentially, a gap (e.g. left by a file that shrank) hangs it at the title screen
            pab += b"\0" * (W.align(len(pab), 32) - len(pab))
            e[1] = start + len(pab) - (32 * k if self.single else 0)
            e[2] = len(data)
            pab += data
            idx += struct.pack(">8I", *e)
        pab += b"\0" * (W.align(len(pab), 32) - len(pab))
        last = list(self.last)
        last[1] = start + len(pab) - (32 * (n - 1) if self.single else 0)
        last[2] = 4
        pab += b"\xAB\xAB\xAB\xAB"
        idx += struct.pack(">8I", *last)
        pab += b"\0" * (W.align(len(pab), 16) - len(pab))
        pab += b"\xAB" * (W.align(len(pab), 0x1000) - len(pab))
        idx += b"\0" * (W.align(len(idx), 0x1000) - len(idx))
        if self.single:
            return bytes(idx) + bytes(pab), None
        return bytes(idx), bytes(pab)

    def save(self, strict=True):
        """strict: refuse to grow the decompressed or compressed files. The game reserves fixed
        buffers for them - a bigger qb.pab hangs WoR on a black screen at boot."""
        pak, pab = self.build()
        out = []
        for path, data in ((self.pak_path, pak), (self.pab_path, pab)):
            if data is None:
                continue
            if not os.path.exists(path + ".bak"):
                import shutil
                shutil.copyfile(path, path + ".bak")
                print("backup ->", path + ".bak")
            orig = open(path + ".bak", "rb").read()
            orig_raw = W.unchnk(orig)
            blob, _, _ = W.mkchnk(data, (orig_raw, W.chnk_parts(orig)))
            # disc files are read in 32 KB blocks: originals are always padded past the last
            # chunk to the next 32 KB boundary (e.g. qb.pak 0x5451 bytes of data -> 0x8000)
            blob += b"\0" * (W.align(len(blob) + 1, 0x8000) - len(blob))
            print("  %s: decompressed 0x%X (original 0x%X), file 0x%X (original 0x%X)" % (
                os.path.basename(path), len(data), len(orig_raw), len(blob), len(orig)))
            if strict and (len(data) > len(orig_raw) or len(blob) > len(orig)):
                raise SystemExit("%s would grow past the original size - not written" % os.path.basename(path))
            out.append((path, blob))
        for path, blob in out:
            open(path, "wb").write(blob)
            update_toc(path, blob)
        print("wrote %s (%d files)" % (self.name, len(self.entries)))


TOC = os.path.join(W.DATA, "compressed", "compress.toc.xen")


def update_toc(path, blob):
    """data/compressed/compress.toc.xen ("TOC1") lists how many bytes the game reads for some
    compressed files: 24-byte entries (qbkey of the path relative to data/compressed, e.g.
    "pak\\qb.pab.xen", uncompressed size, read size, 0x30000|chunks, first chunk slot, ?).
    The game reads only 'read size' bytes - a file whose chunks end later decompresses garbage."""
    rel = os.path.relpath(path, os.path.join(W.DATA, "compressed"))
    key = W.qbkey(rel)
    toc = bytearray(open(TOC, "rb").read())
    cnt = struct.unpack_from(">I", toc, 4)[0]
    for k in range(cnt):
        o = 0x20 + 24 * k
        if struct.unpack_from(">I", toc, o)[0] != key:
            continue
        pos, n, raw = 0, 0, 0
        while True:
            _, hsz, csz, nxt, _, usz, _ = struct.unpack_from(">4s6I", blob, pos)
            n += 1; raw += usz
            if n == 1:
                first = nxt if nxt != 0xFFFFFFFF else W.align(hsz + csz, 0x800)
            if nxt == 0xFFFFFFFF:
                end = pos + hsz + csz
                break
            pos += nxt
        read = min(len(blob), W.align(end, 0x800) + 0x80)
        if not os.path.exists(TOC + ".bak"):
            import shutil
            shutil.copyfile(TOC, TOC + ".bak")
        struct.pack_into(">4I", toc, o + 4, raw, read, 0x30000 | n, first)
        open(TOC, "wb").write(toc)
        print("  compress.toc: %s read size 0x%X, %d chunks, first slot 0x%X" % (rel, read, n, first))
        return
    print("  compress.toc: no entry for %s" % rel)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "list":
        for e, d in Pak(a[1]).entries:
            print("%08X %7d %s" % (e[4], len(d), W.name_of(e[4])))
    elif a and a[0] == "extract":
        p = Pak(a[1]); os.makedirs(a[2], exist_ok=True)
        for e, d in p.entries:
            open(os.path.join(a[2], os.path.basename(W.name_of(e[4]) or "%08X" % e[4])), "wb").write(d)
    else:
        print(__doc__)
