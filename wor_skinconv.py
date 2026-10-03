"""Build GH:WoR (X360) .skin files.

  py wor_skinconv.py rebuild <wor.skin.xen> <out>        -> parse + re-write a WoR skin (self-test)
  py wor_skinconv.py convert <wt.skin.xen> <template_wor.skin.xen> <out> [--normal CRC] [--flatnormal CRC]
        GHWT PC/DE skin -> WoR. The WoR template (e.g. johnny_1.skin) gives the sector list,
        a known-good material to clone and the constant blocks.
        (wor_port.py does all of this automatically.)

Layout (offsets relative to the CScene start unless noted), as found in johnny_1.skin:
  0x00 file header (dq offset, FAAABACA x7) | 0x80 material list | align 128 | CScene:
  header 0x90 | sectors 96*n | CGeoms 0x60 per geometry sector | Lst::Head pad | sMesh 144*n |
  0xEA*4n | mesh indices u32*n | 0xFF*4n | 0xAA to align 32 |
  per mesh: UV block (32 const + stride*verts) | faces (32 const + u16*n) | 0xEE to 4 KB |
            vertex block (CAFEBAB4*4, 0, n1, n2, n3, groups) | ... | 0 to align 32 | footer
"""
import struct, sys, math
import wor_skin as S

FOOTER_EMPTY = bytes.fromhex("021400fe00000000000000140000000000000000000000000000000000000000")


def align(v, a):
    return (v + a - 1) & ~(a - 1)


def pack_vec(v):
    x = int(round(max(-1, min(1, v[0])) * 1023)) & 0x7FF
    y = int(round(max(-1, min(1, v[1])) * 1023)) & 0x7FF
    z = int(round(max(-1, min(1, v[2])) * 511)) & 0x3FF
    return x | (y << 11) | (z << 22)


def norm(v):
    l = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / l for c in v)


class WMesh:
    """One WoR sMesh: raw 144-byte record (kept for unknown fields) + geometry blocks."""
    def __init__(self):
        self.rec = None          # bytearray(144)
        self.uv_hdr = None       # 32 bytes
        self.uv = b""            # stride * verts
        self.face_hdr = None     # 32 bytes
        self.indices = []        # u16
        self.vcounts = (0, 0, 0)
        self.groups = []         # [(header16 bytes, vertex bytes)]
        self.verts = 0


def parse_wor(data):
    sk = S.Skin(data)
    if not sk.wor:
        raise SystemExit("not a WoR skin")
    s = sk.scene
    model = {"head": data[:0x80], "mat": data[sk.core:sk.core + sk.matlist_size],
             "scene_hdr": bytearray(data[s:s + 0x90]),
             "sectors": [data[sk.off_sector + 96 * i: sk.off_sector + 96 * (i + 1)] for i in range(sk.sector_count)],
             "bigpad": data[sk.off_bigpad:sk.off_smesh], "meshes": []}
    ngeo = sum(1 for x in sk.sectors if not x["flags"] & 0x20)
    model["cgeoms"] = [data[sk.off_cgeom + 0x60 * i: sk.off_cgeom + 0x60 * (i + 1)] for i in range(ngeo)]
    for m in sk.meshes:
        w = WMesh()
        w.rec = bytearray(data[m.off:m.off + 144])
        w.uv_hdr = data[m.off_uv:m.off_uv + 32]
        w.uv = data[m.off_uv + 32:m.off_uv + 32 + m.uv_stride * m.vertex_count]
        w.face_hdr = data[m.off_face:m.off_face + 32]
        w.indices = list(struct.unpack_from(">%dH" % m.face_count, data, m.off_face + 32))
        r = S.R(data, m.off_vert + 20)
        w.vcounts = (r.u32(), r.u32(), r.u32())
        for _ in range(sum(w.vcounts)):
            gh = data[r.o:r.o + 16]; n = struct.unpack_from(">I", gh)[0]; r.skip(16)
            w.groups.append((gh, data[r.o:r.o + 32 * n])); r.skip(32 * n)
        w.verts = m.vertex_count
        model["meshes"].append(w)
    fo = sk.core + sk.dq_off
    model["footer"] = data[fo:]
    model["order"] = list(struct.unpack_from(">%dI" % len(sk.meshes), data, sk.off_mesh_indices))
    return model


def write_wor(model):
    out = bytearray(model["head"])
    mat = model["mat"]
    out += mat
    out += b"\0" * (align(len(out), 128) - len(out))
    s = len(out)
    meshes, nsec, ngeo = model["meshes"], len(model["sectors"]), len(model["cgeoms"])
    n = len(meshes)
    hdr = bytearray(model["scene_hdr"])
    o_sec = 0x90
    o_geo = o_sec + 96 * nsec
    o_big = o_geo + 0x60 * ngeo
    o_sm = o_big + len(model["bigpad"])
    o_ea = o_sm + 144 * n
    o_idx = o_ea + 4 * n
    o_ff = o_idx + 4 * n
    o_data = align(o_ff + 4 * n, 32)
    scene = bytearray(hdr)
    for sec in model["sectors"]: scene += sec
    for g in model["cgeoms"]: scene += g
    scene += model["bigpad"]
    recs_at = len(scene); scene += b"\0" * (144 * n)
    scene += b"\xEA" * (4 * n)
    order = model.get("order") if len(model.get("order") or []) == n else list(range(n))
    scene += b"".join(struct.pack(">I", i) for i in order)  # draw order
    scene += b"\xFF" * (4 * n)
    scene += b"\xAA" * (o_data - len(scene))
    for i, m in enumerate(meshes):
        rec = m.rec
        uv_at = len(scene)
        scene += m.uv_hdr + m.uv
        face_at = len(scene)
        scene += m.face_hdr + struct.pack(">%dH" % len(m.indices), *m.indices)
        scene += b"\xEE" * (align(len(scene), 0x1000) - len(scene))
        vert_at = len(scene)
        scene += b"\xCA\xFE\xBA\xB4" * 4 + struct.pack(">4I", 0, *m.vcounts)
        for gh, vb in m.groups:
            scene += gh + vb
        struct.pack_into(">I", rec, 0x18, uv_at)
        struct.pack_into(">H", rec, 0x1E, m.verts)
        struct.pack_into(">I", rec, 0x30, face_at)
        struct.pack_into(">I", rec, 0x3C, 2 * len(m.indices))
        struct.pack_into(">I", rec, 0x68, vert_at)
        struct.pack_into(">HH", rec, 0x7A, len(m.indices), m.verts)
        scene[recs_at + 144 * i: recs_at + 144 * (i + 1)] = rec
    geom_end_rel_core = s + len(scene) - 0x80
    scene += b"\0" * (align(s + len(scene), 32) - (s + len(scene)))
    footer_rel_core = s + len(scene) - 0x80
    # scene header pointers
    struct.pack_into(">I", scene, 0x3C, geom_end_rel_core)
    struct.pack_into(">II", scene, 0x48, o_idx, n)
    struct.pack_into(">I", scene, 0x50, o_ff)
    struct.pack_into(">II", scene, 0x6C, nsec, o_sec)
    struct.pack_into(">I", scene, 0x74, o_geo)
    struct.pack_into(">II", scene, 0x7C, o_big, o_sm)
    struct.pack_into(">I", scene, 0x8C, o_ea)
    out += scene + model["footer"]
    struct.pack_into(">I", out, 0, footer_rel_core)
    return bytes(out)


# ---------------------------------------------------------------- WT -> WoR

def read_wt(data):
    """GHWT PC skin -> list of meshes with full vertex data."""
    sk = S.Skin(data)
    if sk.wor:
        raise SystemExit("input is already a WoR skin")
    res = []
    for m in sk.meshes:
        r = S.R(data, m.off_vert + 20)
        counts = (r.u32(), r.u32(), r.u32())
        groups = []
        for _ in range(sum(counts)):
            n = r.u32(); bones = bytes(r.u8() for _ in range(4)); r.u32(); r.u32()
            vs = []
            for _ in range(n):
                x1, x2, x3 = r.vec(4), r.vec(4), r.vec(4); a, b = r.f32(), r.f32()
                vs.append(((x1[0], x2[0], x3[0]), (x1[1], x2[1], x3[1]), (x1[2], x2[2], x3[2]),
                           (x1[3], x2[3], x3[3]), a, b))
            groups.append((bones, vs))
        nuv = S.uv_set_count(m.flags)
        has_col = bool(m.flags & 0x10)
        uvs = []
        for i in range(m.vertex_count):
            r = S.R(data, m.off_uv + 32 + m.uv_stride * i)
            col = data[r.o:r.o + 4] if has_col else b"\xff\xff\xff\xff"
            if has_col: r.skip(4)
            uvs.append((col, r.f32(), r.f32()))
        tris_raw = list(struct.unpack_from(">%dH" % m.face_count, data, m.off_face + 32))
        res.append({"material": m.material, "sphere": m.sphere, "counts": counts, "groups": groups,
                    "uvs": uvs, "indices": tris_raw, "face_type": m.face_type, "verts": m.vertex_count})
    return sk, res


def half(f):
    return struct.unpack(">H", struct.pack(">e", f))[0]


def build_mesh(src, tmpl_rec, uv_hdr, face_hdr):
    w = WMesh()
    w.rec = bytearray(tmpl_rec)
    struct.pack_into(">4f", w.rec, 0, *src["sphere"])
    struct.pack_into(">BB", w.rec, 0x1C, 8, 0)               # uv stride: ARGB color + half2 uv
    struct.pack_into(">I", w.rec, 0x24, 0x000105FE)           # weights | color | 1 uv set (compressed) | tangents
    w.uv_hdr, w.face_hdr = uv_hdr, face_hdr
    w.uv = b"".join(col + struct.pack(">HH", half(u), half(v)) for col, u, v in src["uvs"])
    w.indices = src["indices"]
    w.vcounts = src["counts"]
    maxbone = 0
    for bones, vs in src["groups"]:
        maxbone = max([maxbone] + list(bones))
        gh = struct.pack(">I4sII", len(vs), bones, len(vs), 0xFACEF000)
        vb = bytearray()
        for pos, nrm, tan, bit, a, b in vs:
            vb += struct.pack(">3fHHIII4s", *pos,
                              int(round(max(0, min(1, b)) * 65535)), int(round(max(0, min(1, a)) * 65535)),
                              pack_vec(norm(nrm)), pack_vec(norm(tan)), pack_vec(norm(bit)), b"\xBA\xAD\xF0\x0D")
        w.groups.append((gh, bytes(vb)))
    w.verts = src["verts"]
    w.rec[0x84] = maxbone
    struct.pack_into(">I", w.rec, 0x50, src["material"])
    struct.pack_into(">I", w.rec, 0x64, 4)
    return w


def clone_material(tmpl, checksum, name, textures):
    m = bytearray(tmpl)
    struct.pack_into(">II", m, 0, checksum, name)
    tex_count, tex_ptr = struct.unpack_from(">II", m, 0x88)
    if tex_count != len(textures):
        raise SystemExit("template material has %d textures, need %d" % (tex_count, len(textures)))
    for i, t in enumerate(textures):
        struct.pack_into(">I", m, tex_ptr + 4 * i, t)
    return bytes(m)


def convert(wt_path, tmpl_path, out_path, normal_map=None, flat_normal=None, spec_default=0xDEC273CB):
    out = convert_data(open(wt_path, "rb").read(), open(tmpl_path, "rb").read(), normal_map, flat_normal,
                       spec_default)
    open(out_path, "wb").write(out)
    print("wrote %s (%d bytes)" % (out_path, len(out)))
    return out


def convert_data(wt_data, tmpl_data, normal_map=None, flat_normal=None, spec_default=0xDEC273CB):
    """GHWT PC skin bytes + WoR template skin bytes -> WoR skin bytes.
    normal_map goes to the material of the biggest mesh (the body), the others get flat_normal
    (default: the flat normal map that 'wor_tex.py convert-pc-tex --flat-normal' adds)."""
    if flat_normal is None:
        import wor_tex
        flat_normal = wor_tex.FLAT_NORMAL
    tmpl = parse_wor(tmpl_data)
    tsk = S.Skin(tmpl_data)
    wsk, meshes = read_wt(wt_data)
    # template material: first opaque 852105C8 one (normal, diffuse, spec)
    tm = next(m for m in tsk.materials if m.template == 0x852105C8 and m.blend == 0)
    tm_raw = tmpl_data[tm.off:tm.off + ((tm.size + 15) & ~15)]
    body_mat = max(meshes, key=lambda m: m["verts"])["material"] if meshes else None
    mats = []
    for m in wsk.materials:
        diffuse = m.textures[0]
        spec = m.textures[2] if len(m.textures) > 2 and m.textures[2] != 0xD729D3B1 else spec_default
        nrm = normal_map if (normal_map and m.checksum == body_mat) else flat_normal
        mats.append(clone_material(tm_raw, m.checksum, m.name, [nrm, diffuse, spec]))
        print("  material %08X: normal=%08X diffuse=%08X spec=%08X" % (m.checksum, nrm, diffuse, spec))
    body = b"".join(mats)
    head = bytes(tmpl["mat"][:16])
    matlist = bytearray(head) + body
    struct.pack_into(">HI", matlist, 2, len(mats), len(matlist))
    model = dict(tmpl)
    model["mat"] = bytes(matlist)
    t0 = tmpl["meshes"][0]
    model["meshes"] = [build_mesh(m, t0.rec, t0.uv_hdr, t0.face_hdr) for m in meshes]
    # scene bounds from the WT file
    hdr = bytearray(tmpl["scene_hdr"])
    hdr[0:0x30] = wt_data[wsk.scene:wsk.scene + 0x30]
    model["scene_hdr"] = hdr
    geo = bytearray(tmpl["cgeoms"][0])
    geo[0x10:0x30] = wt_data[wsk.scene:wsk.scene + 0x20]
    struct.pack_into(">Ii", geo, 0x48, 0, len(meshes))
    model["cgeoms"] = [bytes(geo)]
    model["footer"] = FOOTER_EMPTY
    model["order"] = None
    return write_wor(model)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "rebuild":
        src = open(a[1], "rb").read()
        out = write_wor(parse_wor(src))
        open(a[2], "wb").write(out)
        same = out == src
        print("identical" if same else "DIFFERENT (len %X vs %X)" % (len(out), len(src)))
        if not same:
            for i in range(min(len(out), len(src))):
                if out[i] != src[i]:
                    print("first diff at 0x%X: ours %s orig %s" % (i, out[i:i + 16].hex(" "), src[i:i + 16].hex(" ")))
                    break
    elif a[0] == "convert":
        def opt(k):
            if k in a:
                i = a.index(k); v = int(a[i + 1], 16); del a[i:i + 2]; return v
        nm, fl = opt("--normal"), opt("--flatnormal")
        convert(a[1], a[2], a[3], nm, fl)
