"""Neversoft .skin reader for GH:WT (PC/GHWT:DE) and GH:WoR (X360). Both are big-endian.

  py wor_skin.py dump <file.skin.xen> [--verts]     -> materials, sectors, meshes summary
  py wor_skin.py obj  <file.skin.xen> <out.obj>     -> geometry as OBJ (sanity check in Blender)

Layout from the GH SDK templates (Skin.bt, SceneHeader.bt, CSector.bt, CGeom.bt, sMesh*.bt)
and NXTools (fmt_ghscene_import / fmt_ghwtscene_import / fmt_ghworscene_import).
"""
import struct, sys, math


class R:
    def __init__(self, d, o=0):
        self.d, self.o = d, o

    def u8(self): v = self.d[self.o]; self.o += 1; return v
    def u16(self): v = struct.unpack_from(">H", self.d, self.o)[0]; self.o += 2; return v
    def u32(self): v = struct.unpack_from(">I", self.d, self.o)[0]; self.o += 4; return v
    def i32(self): v = struct.unpack_from(">i", self.d, self.o)[0]; self.o += 4; return v
    def f32(self): v = struct.unpack_from(">f", self.d, self.o)[0]; self.o += 4; return v
    def f16(self):
        h = self.u16()
        return struct.unpack("<e", struct.pack("<H", h))[0]
    def vec(self, n): return tuple(self.f32() for _ in range(n))
    def skip(self, n): self.o += n


class Material:
    pass


class Mesh:
    pass


class Skin:
    def __init__(self, data):
        self.data = data
        r = R(data)
        self.dq_off = r.u32()
        self.wor = data[0x20] == 0
        self.core = 0x80 if self.wor else 0x20
        self.read_materials()
        self.read_scene()

    # -- materials -------------------------------------------------------
    def read_materials(self):
        r = R(self.data, self.core)
        self.mat_version, _, count = r.u8(), r.u8(), r.u16()
        self.matlist_size = r.u32()
        rel = r.u32()
        self.materials = []
        o = self.core + rel
        for _ in range(count):
            m = Material(); m.off = o
            mr = R(self.data, o)
            m.checksum, m.name = mr.u32(), mr.u32()
            mr.o = o + 0x70
            m.template = mr.u32(); mr.u32()
            m.vs_count, m.vs_ptr, m.ps_count, m.ps_ptr = mr.u32(), mr.u32(), mr.u32(), mr.u32()
            m.tex_count, m.tex_ptr = mr.u32(), mr.u32()
            mr.u32(); m.size = mr.u32(); mr.u32(); m.flags = mr.u32(); mr.u32()
            m.draw_order, m.blend = mr.i32(), mr.u32()
            mr.o = o + m.tex_ptr
            m.textures = [mr.u32() for _ in range(m.tex_count)]
            self.materials.append(m)
            o += (m.size + 15) & ~15
        o = self.core + self.matlist_size
        if struct.unpack_from(">I", self.data, o)[0] == 0xBABEFACE:
            pad = struct.unpack_from(">I", self.data, o + 4)[0]
            o += 8 + pad - 4  # SDK: padding[padding_count-4], then pre_scene_int
            o += 4
        else:
            o = (o + 127) & ~127
        self.scene = o

    # -- scene -----------------------------------------------------------
    def read_scene(self):
        s = self.scene
        r = R(self.data, s)
        self.bbox = (r.vec(4), r.vec(4)); self.sphere = r.vec(4)
        self.unk_a, self.unk_b = r.u16(), r.u16()
        r.skip(8); self.footer_off = r.u32(); r.u32(); r.u32()
        self.off_mesh_indices = s + r.u32()
        self.smesh_count = r.u32()
        r.u32(); r.skip(16); r.u32(); r.u32()
        self.sector_count = r.u32()
        self.off_sector = s + r.u32(); self.off_cgeom = s + r.u32(); r.u32()
        self.off_bigpad = s + r.u32(); self.off_smesh = s + r.u32()
        r.skip(8); self.off_eapad = s + r.u32()

        self.sectors = []
        r.o = self.off_sector
        for _ in range(self.sector_count):
            r.u32(); cs, fl, lg = r.u32(), r.u32(), r.u32(); r.skip(48)
            sph = r.vec(4); r.skip(16)
            self.sectors.append({"checksum": cs, "flags": fl, "sphere": sph})
        r.o = self.off_cgeom
        for sec in self.sectors:
            if sec["flags"] & 0x20:
                sec["first"], sec["count"] = 0, 0; continue
            r.u32(); r.skip(8); r.u32(); r.vec(8); r.skip(24)
            sec["first"], sec["count"] = r.u32(), r.i32(); r.skip(16)

        msize = 144 if self.wor else 112
        self.meshes = []
        for sec in self.sectors:
            for i in range(max(sec["count"], 0)):
                m = self.read_smesh(self.off_smesh + msize * (sec["first"] + i))
                m.sector = sec["checksum"]
                self.meshes.append(m)

    def read_smesh(self, o):
        s, r, m = self.scene, R(self.data, o), Mesh()
        m.off = o
        m.sphere = r.vec(4)
        if self.wor:
            peek = struct.unpack_from(">I", self.data, r.o)[0]
            if peek == 0: r.skip(8)
            m.off_uv = s + r.u32(); m.uv_stride = r.u8(); m.uv_bool = r.u8(); m.uv_count = r.u16()
            if peek != 0: r.skip(8)
            r.u32(); m.flags = r.u32(); r.skip(8)
            m.off_face = s + r.u32(); r.skip(8); m.face_block_len = r.u32()
            r.u32(); r.u32(); r.u16(); r.u16(); r.u32()
            m.material = r.u32(); r.skip(16)
            m.face_type = r.u32()
            vs = r.i32(); m.off_vert = s + vs if vs >= 0 else -1
            r.skip(14); m.face_count, m.vertex_count = r.u16(), r.u16()
            r.u16(); r.u16(); m.single_bone = r.u8(); r.u8(); m.unk_flags = r.u32()
        else:
            m.off_uv = s + r.u32(); r.skip(8); m.uv_length = r.u32(); r.u32()
            m.flags = r.u32(); r.u8(); r.u8(); m.uv_bool = r.u8(); m.uv_stride = r.u8()
            r.u16(); r.u16(); r.u32(); m.material = r.u32(); r.u32(); r.u32(); r.u32()
            m.face_count, m.vertex_count = r.u16(), r.u16(); r.skip(8); m.unk_flags = r.u32(); r.u32()
            m.off_face = s + r.u32()
            vs = r.i32(); m.off_vert = s + vs if vs >= 0 else -1
            r.u32(); m.face_type = r.u32()
            m.single_bone = 255
        return m

    # -- geometry --------------------------------------------------------
    def vertices(self, m):
        """[(pos, normal, (w0,w1,w2), bones[4])] in file order, plus groups summary."""
        out, groups = [], []
        if m.off_vert < 0:
            return out, groups
        r = R(self.data, m.off_vert + 16)
        r.u32()
        counts = (r.u32(), r.u32(), r.u32())
        for _ in range(sum(counts)):
            n = r.u32(); bones = [r.u8() for _ in range(4)]; r.u32(); r.u32()
            groups.append((n, bones))
            for _ in range(n):
                if not self.wor:
                    x1, x2, x3 = r.vec(4), r.vec(4), r.vec(4)
                    a, b = r.f32(), r.f32()
                    pos, nrm = (x1[0], x2[0], x3[0]), (x1[1], x2[1], x3[1])
                else:
                    pos = r.vec(3); b = r.u16() / 65535.0; a = r.u16() / 65535.0
                    nrm = unpack_normal(r.u32()); r.skip(12)
                d = 1.0 - (a + b)
                out.append((pos, nrm, (a + d, b + d, d), bones))
        return out, (counts, groups)

    def uvs(self, m):
        """UV set 0 per vertex (u, v)."""
        out = []
        if m.off_uv < 0:
            return out
        compressed = self.wor
        nuv = uv_set_count(m.flags)
        skip = 0
        if not (m.flags & 0x80):  # unweighted: position etc. live here
            skip = 6 * 2 if compressed else 12
        for i in range(m.vertex_count):
            r = R(self.data, m.off_uv + 32 + m.uv_stride * i)
            out.append(None if nuv == 0 else None)
        return out

    def faces(self, m):
        r = R(self.data, m.off_face)
        r.skip(12); r.u32(); fa, fb, fc = r.u32(), r.u32(), r.u32(); guessed = r.u32()
        idx = [r.u16() for _ in range(m.face_count)]
        tris = []
        if m.face_type == 4:  # triangle list
            tris = [tuple(idx[i:i + 3]) for i in range(0, len(idx) - 2, 3)]
        else:  # strips separated by 0x7FFF
            strip = []
            for v in idx + [0x7FFF]:
                if v == 0x7FFF:
                    for f in range(2, len(strip)):
                        t = (strip[f - 2], strip[f - 1], strip[f]) if f % 2 == 0 else (strip[f - 2], strip[f], strip[f - 1])
                        if len(set(t)) == 3: tris.append(t)
                    strip = []
                else:
                    strip.append(v)
        return tris, (fa, fb, fc, guessed)


def uv_set_count(flags):
    n = 0
    for bit in range(16, 24, 2):  # 1..4 uv set flags (compressed / not)
        if flags & (3 << bit): n += 1
    return n


def unpack_normal(p):
    # THAW/X360 packed normal: 11:11:10 signed (x, y, z)
    x = p & 0x7FF; y = (p >> 11) & 0x7FF; z = (p >> 22) & 0x3FF
    x = (x - 0x800 if x & 0x400 else x) / 1023.0
    y = (y - 0x800 if y & 0x400 else y) / 1023.0
    z = (z - 0x400 if z & 0x200 else z) / 511.0
    return (x, y, z)


def name(crc):
    try:
        import wor_tex
        return wor_tex.name_of(crc) or "%08X" % crc
    except Exception:
        return "%08X" % crc


def dump(path, verts=False):
    sk = Skin(open(path, "rb").read())
    print("%s: %s, core=0x%X scene=0x%X, %d materials (v%d), %d sectors, %d meshes, unk_a=%d unk_b=%d" % (
        path, "WoR" if sk.wor else "WT", sk.core, sk.scene, len(sk.materials), sk.mat_version,
        sk.sector_count, len(sk.meshes), sk.unk_a, sk.unk_b))
    for m in sk.materials:
        print("  MAT %08X tmpl=%08X vs=%d ps=%d tex=[%s] blend=%d size=0x%X" % (
            m.checksum, m.template, m.vs_count, m.ps_count, " ".join("%08X" % t for t in m.textures), m.blend, m.size))
    tv = tf = 0
    for i, m in enumerate(sk.meshes):
        v, (counts, groups) = sk.vertices(m) if m.off_vert >= 0 else ([], ((0, 0, 0), []))
        tris, fh = sk.faces(m)
        bones = sorted({b for _, bs in groups for b in bs})
        tv += m.vertex_count; tf += len(tris)
        print("  MESH %2d sec=%08X mat=%08X flags=%08X stride=%d verts=%d idx=%d type=%d tris=%d groups=%s maxbone=%s single=%d" % (
            i, m.sector, m.material, m.flags, m.uv_stride, m.vertex_count, m.face_count, m.face_type, len(tris),
            counts, max(bones) if bones else "-", m.single_bone))
        if verts and v:
            for p, n, w, b in v[:3]:
                print("      pos=(%.3f %.3f %.3f) n=(%.2f %.2f %.2f) w=(%.2f %.2f %.2f) bones=%s" % (*p, *n, *w, b))
    print("  total verts=%d tris=%d" % (tv, tf))
    return sk


def to_obj(path, out):
    sk = Skin(open(path, "rb").read())
    base = 1
    with open(out, "w") as f:
        for i, m in enumerate(sk.meshes):
            v, _ = sk.vertices(m)
            if not v:
                continue
            tris, _ = sk.faces(m)
            f.write("o mesh%02d_%08X\n" % (i, m.material))
            for p, n, w, b in v:
                f.write("v %f %f %f\n" % p)
            for t in tris:
                if max(t) < len(v):
                    f.write("f %d %d %d\n" % tuple(base + x for x in t))
            base += len(v)
    print("wrote", out)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "dump":
        dump(a[1], "--verts" in a)
    elif a[0] == "obj":
        to_obj(a[1], a[2])
