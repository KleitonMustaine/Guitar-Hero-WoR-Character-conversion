"""GH:WoR (X360, .qb.xen) QB reader / writer.

  py wor_qb.py dump <file.qb> [filter]   -> text dump (checksums resolved with ghwor_keys.txt)

Binary layout (big-endian):
  header 28 bytes: 0, file size, 20 constant bytes
  section (top level item): type u32 (0x0020TT00), id, file id, value|pointer, 0
  struct: 0x00000100, pointer to first item | item: type (0x0001TT00, 0x00000100 flag for struct
          items), id, value|pointer, next pointer
  array: type (0x0001TT00), count, pointer to elements (count > 1 or pointer types) | inline value
Types (TT): 01 int, 02 float, 03 string, 04 wstring, 05 vec2, 06 vec3, 07 script, 0A struct,
            0C array, 0D qbkey, 1A qbkey-string, 1C qbkey-string-qs
"""
import struct, sys

INT, FLOAT, STR, WSTR, VEC2, VEC3, SCRIPT, STRUCT, ARRAY, KEY, KEYSTR, KEYQS = \
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x0A, 0x0C, 0x0D, 0x1A, 0x1C
NAMES = {INT: "int", FLOAT: "float", STR: "string", WSTR: "wstring", VEC2: "vec2", VEC3: "vec3",
         SCRIPT: "script", STRUCT: "struct", ARRAY: "array", KEY: "qbkey", KEYSTR: "qbstring", KEYQS: "qsstring"}
SIMPLE = (INT, FLOAT, KEY, KEYSTR, KEYQS)


class Item:
    """Generic node: kind (type byte), id (checksum or 0), value.
       value: int/float/checksum for simple types, bytes for strings, tuple for vectors,
              list[Item] for structs, (elemkind, list) for arrays, bytes for scripts."""
    def __init__(self, kind, id=0, value=None, flags=0):
        self.kind, self.id, self.value, self.flags = kind, id, value, flags

    def __repr__(self):
        return "Item(%s, %08X)" % (NAMES.get(self.kind, hex(self.kind)), self.id)


class QBFile:
    def __init__(self, data):
        self.d = data
        self.header = data[:28]
        self.sections = []
        self.end = 0
        o = 28
        while o < len(data):
            t, iid, fid, val, nxt = struct.unpack_from(">5I", data, o)
            kind = (t >> 8) & 0xFF
            it = Item(kind, iid, flags=t)
            it.file_id = fid
            o += 20
            if kind in SIMPLE:
                it.value = val
            elif kind == SCRIPT:
                # script: crc, uncompressed size, compressed size, data (padded to 4)
                crc, usz, csz = struct.unpack_from(">3I", data, val)
                n = csz if csz else usz
                end = val + 12 + n
                end = (end + 3) & ~3
                it.value = data[val:end]
                o = end
                self.sections.append(it); continue
            else:
                it.value, o = self.read_value(kind, val, top=True)
            self.sections.append(it)
            o = max(o, self.end)

    # each reader returns (value, end-of-data offset) and records self.end
    def read_value(self, kind, p, top=False):
        d = self.d
        if kind in (STR,):
            e = d.index(b"\0", p)
            self.end = (e + 1 + 3) & ~3
            return d[p:e], self.end
        if kind == WSTR:
            e = p
            while d[e:e + 2] != b"\0\0": e += 2
            self.end = (e + 2 + 3) & ~3
            return d[p:e], self.end
        if kind in (VEC2, VEC3):
            n = 2 if kind == VEC2 else 3
            hdr = struct.unpack_from(">I", d, p)[0]
            self.end = p + 4 + 4 * n
            return struct.unpack_from(">%df" % n, d, p + 4), self.end
        if kind == STRUCT:
            return self.read_struct(p)
        if kind == ARRAY:
            return self.read_array(p)
        raise ValueError("unknown value kind %X at %X" % (kind, p))

    def read_struct(self, p):
        d = self.d
        hdr, first = struct.unpack_from(">II", d, p)
        end = p + 8
        items = []
        q = first
        while q:
            t, iid, val, nxt = struct.unpack_from(">4I", d, q)
            kind = (t >> 8) & 0xFF
            it = Item(kind, iid, flags=t)
            end = max(end, q + 16)
            if kind in SIMPLE or kind == 0:
                it.value = val
            else:
                it.value, e = self.read_value(kind, val)
                end = max(end, e)
            items.append(it)
            q = nxt
        self.end = end
        return items, end

    def read_array(self, p):
        d = self.d
        t, count = struct.unpack_from(">II", d, p)
        kind = (t >> 8) & 0xFF
        end = p + 8
        if count == 0:
            self.end = p + 12
            return (kind, t, [], 0), self.end
        if kind in SIMPLE:
            if count == 1:
                self.end = p + 12
                return (kind, t, [struct.unpack_from(">I", d, p + 8)[0]], 1), self.end
            ptr = struct.unpack_from(">I", d, p + 8)[0]
            vals = list(struct.unpack_from(">%dI" % count, d, ptr))
            self.end = ptr + 4 * count
            return (kind, t, vals, 2), self.end
        # pointer elements
        if count == 1:
            ptrs = [struct.unpack_from(">I", d, p + 8)[0]]
            end = p + 12
            style = 1
        else:
            lp = struct.unpack_from(">I", d, p + 8)[0]
            ptrs = list(struct.unpack_from(">%dI" % count, d, lp))
            end = lp + 4 * count
            style = 2
        vals = []
        for q in ptrs:
            v, e = self.read_value(kind, q)
            end = max(end, e)
            vals.append(v)
        self.end = end
        return (kind, t, vals, style), end


# ---------------------------------------------------------------- writer

class Writer:
    def __init__(self):
        self.b = bytearray()

    def pos(self): return len(self.b)
    def u32(self, v): self.b += struct.pack(">I", v & 0xFFFFFFFF)
    def patch(self, at, v): struct.pack_into(">I", self.b, at, v)

    def value(self, kind, v):
        """write data for a pointer-type value at current position, return its offset"""
        p = self.pos()
        if kind == STR:
            self.b += v + b"\0"; self.pad()
        elif kind == WSTR:
            self.b += v + b"\0\0"; self.pad()
        elif kind in (VEC2, VEC3):
            self.u32(0x00010000); self.b += struct.pack(">%df" % len(v), *v)
        elif kind == STRUCT:
            self.struct(v)
        elif kind == ARRAY:
            self.array(v)
        else:
            raise ValueError(kind)
        return p

    def pad(self):
        while len(self.b) % 4: self.b += b"\0"

    def struct(self, items):
        p = self.pos()
        self.u32(0x00000100); self.u32(p + 8 if items else 0)
        for i, it in enumerate(items):
            at = self.pos()
            self.u32(it.flags); self.u32(it.id); self.u32(0); self.u32(0)
            if it.kind in SIMPLE or it.kind == 0:
                self.patch(at + 8, it.value)
            else:
                self.patch(at + 8, self.value(it.kind, it.value))
            if i + 1 < len(items):
                self.patch(at + 12, self.pos())

    def array(self, arr):
        kind, t, vals, style = arr
        p = self.pos()
        self.u32(t); self.u32(len(vals))
        if not vals:
            self.u32(0); return
        if kind in SIMPLE:
            if style == 1:
                self.u32(vals[0])
            else:
                self.u32(self.pos() + 4)
                for v in vals: self.u32(v)
            return
        if style == 1:
            at = self.pos(); self.u32(0)
            self.patch(at, self.value(kind, vals[0]))
            return
        self.u32(self.pos() + 4)
        lst = self.pos()
        for _ in vals: self.u32(0)
        for i, v in enumerate(vals):
            self.patch(lst + 4 * i, self.value(kind, v))


def write_qb(qb):
    w = Writer()
    w.b += qb.header
    for it in qb.sections:
        at = w.pos()
        w.u32(it.flags); w.u32(it.id); w.u32(it.file_id); w.u32(0); w.u32(0)
        if it.kind in SIMPLE:
            w.patch(at + 12, it.value)
        elif it.kind == SCRIPT:
            w.patch(at + 12, w.pos()); w.b += it.value
        else:
            w.patch(at + 12, w.value(it.kind, it.value))
    w.patch(4, len(w.b))
    return bytes(w.b)


# ---------------------------------------------------------------- text dump

_keys = None
def kn(c):
    global _keys
    if _keys is None:
        import wor_tex
        wor_tex.name_of(0)       # loads ghwor_keys.txt if it can be found
        _keys = wor_tex._keys
    return _keys.get(c, "#%08X" % c)


def fmt_value(kind, v, ind):
    if kind == INT: return str(struct.unpack(">i", struct.pack(">I", v))[0])
    if kind == FLOAT: return "%g" % struct.unpack(">f", struct.pack(">I", v))[0]
    if kind in (KEY, KEYSTR, KEYQS): return kn(v)
    if kind == STR: return '"%s"' % v.decode("latin-1")
    if kind == WSTR: return 'W"%s"' % v.decode("utf-16-be", "replace")
    if kind in (VEC2, VEC3): return "(" + ", ".join("%g" % x for x in v) + ")"
    if kind == STRUCT:
        s = "{\n"
        for it in v:
            s += "  " * (ind + 1) + ("%s = " % kn(it.id) if it.id else "") + fmt_value(it.kind, it.value, ind + 1) + "\n"
        return s + "  " * ind + "}"
    if kind == ARRAY:
        ek, t, vals, style = v
        return "[" + ", ".join(fmt_value(ek, x, ind + 1) for x in vals) + "]"
    if kind == 0: return "<flag>"
    return "<%X>" % kind


def dump(qb, flt=None):
    for it in qb.sections:
        if it.kind == SCRIPT:
            txt = "script %s (%d bytes)" % (kn(it.id), len(it.value))
        else:
            txt = "%s %s = %s" % (NAMES.get(it.kind, hex(it.kind)), kn(it.id), fmt_value(it.kind, it.value, 0))
        if flt is None or flt.lower() in txt.lower():
            print(txt)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "dump":
        dump(QBFile(open(a[1], "rb").read()), a[2] if len(a) > 2 else None)
    else:
        print(__doc__)
