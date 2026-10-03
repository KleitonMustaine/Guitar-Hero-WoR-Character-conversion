"""Port a Guitar Hero World Tour: Definitive Edition character mod to Guitar Hero: Warriors of Rock (X360).

  py wor_port.py install <mod folder> [options]
  py wor_port.py uninstall

<mod folder> is a GHWT:DE character mod: character.ini + the .skin.xen / .tex.xen it points to
(+ the custom skeleton .ske.xen files if it has one).

Options:
  --name "Text"        name shown in Select Rocker (default: [CharacterInfo] Name)
  --blurb "Text"       description (default: [CharacterInfo] Description)
  --replace Johnny_1   replace an existing rocker instead of adding one (Axel_1, Judy_1, ...)
  --template Johnny_1  rocker whose animations / material are used (default by Gender:
                       Johnny_1 for male, Casey_1 for female)
  --max-tex 1024       biggest texture size kept (default 1024; 2048 works but uses more memory)
  --normal CRC         normal map (texture checksum) for the body; default: the only normal map
                       in the .tex, if there is exactly one
  --out DIR            where the converted files are written (default: wor_build\\<name>)

Set WOR_DATA to the extracted game's data folder if it is not found automatically.
"""
import os, sys, glob, struct, configparser
import wor_tex as W, wor_skinconv as C, wor_install as I


def find_file(folder, name):
    """case-insensitive search for a file name anywhere in the mod folder"""
    name = name.lower()
    for path in glob.glob(os.path.join(folder, "**", "*"), recursive=True):
        if os.path.basename(path).lower() == name:
            return path
    return None


def read_mod(folder):
    ini_path = find_file(folder, "character.ini")
    if not ini_path:
        raise SystemExit("character.ini not found in %s" % folder)
    ini = configparser.ConfigParser(strict=False, interpolation=None)
    ini.optionxform = str
    ini.read(ini_path, encoding="utf-8-sig")
    ch = ini["CharacterInfo"] if ini.has_section("CharacterInfo") else {}
    mod = ini["ModInfo"] if ini.has_section("ModInfo") else {}
    mesh = ch.get("Mesh", "")
    base = os.path.basename(mesh.replace("\\", "/"))
    if base.lower().endswith(".skin"):
        base = base[:-5]
    skin = find_file(folder, base + ".skin.xen")
    tex = find_file(folder, base + ".tex.xen")
    if not skin or not tex:
        raise SystemExit("could not find %s.skin.xen / %s.tex.xen in %s" % (base, base, folder))
    ske = ske_d = None
    if ch.get("CustomSkeleton", "").strip().lower() in ("true", "1", "yes"):
        sk = ch.get("Skeleton") or os.path.basename(ch.get("SkeletonPath", "").replace("\\", "/")).replace(".ske", "")
        ske = find_file(folder, sk + ".ske.xen")
        ske_d = find_file(folder, sk + "_Drummer.ske.xen") or ske
        if not ske:
            raise SystemExit("CustomSkeleton=True but %s.ske.xen was not found" % sk)
    return {"id": mod.get("Name") or ch.get("Name") or base, "name": ch.get("Name") or mod.get("Name") or base,
            "blurb": ch.get("Description", ""), "gender": ch.get("Gender", "Male").strip().lower(),
            "skin": skin, "tex": tex, "ske": ske, "ske_drum": ske_d}


def opt(a, key, default=None):
    if key in a:
        i = a.index(key); v = a[i + 1]; del a[i:i + 2]; return v
    return default


def install(a):
    name, blurb = opt(a, "--name"), opt(a, "--blurb")
    replace, template = opt(a, "--replace"), opt(a, "--template")
    max_tex, normal, out = int(opt(a, "--max-tex", "1024")), opt(a, "--normal"), opt(a, "--out")
    if len(a) != 1:
        raise SystemExit(__doc__)
    m = read_mod(a[0])
    name = name or m["name"]
    blurb = m["blurb"] if blurb is None else blurb
    template = template or (replace if replace else I.TEMPLATES.get(m["gender"], "Johnny_1"))
    out = out or os.path.join("wor_build", "".join(c for c in m["id"] if c.isalnum() or c in "_-") or "character")
    os.makedirs(out, exist_ok=True)
    print("== %s  (%s, template %s)" % (name, m["gender"], template))
    print("   skin %s\n   tex  %s\n   ske  %s" % (m["skin"], m["tex"], m["ske"] or "(none - template skeleton)"))

    # 1) textures: PC dictionary -> X360 (tiled, byte-swapped) + flat normal map
    print("\n-- textures")
    texs = W.read_pc_tex(open(m["tex"], "rb").read(), max_tex)
    normals = [t[0] for t in texs if t[1] == 1]
    if normal is None and len(normals) == 1:
        normal = "%08X" % normals[0]
    texs.append(W.flat_normal_texture())
    tex_x360 = W.build_x360_tex(texs)
    open(os.path.join(out, "character.tex"), "wb").write(tex_x360)

    # 2) mesh: GHWT PC skin -> WoR, materials cloned from the template rocker
    print("\n-- mesh")
    skin_wor = C.convert_data(open(m["skin"], "rb").read(), I.template_skin(template),
                              int(normal, 16) if normal else None)
    open(os.path.join(out, "character.skin"), "wb").write(skin_wor)
    ske = open(m["ske"], "rb").read() if m["ske"] else None
    ske_d = open(m["ske_drum"], "rb").read() if m["ske_drum"] else None
    for data, fn in ((ske, "rocker.ske"), (ske_d, "drummer.ske")):
        if data:
            if len(data) != 14592:
                print("   warning: %s is %d bytes, WoR skeletons are 14592" % (fn, len(data)))
            open(os.path.join(out, fn), "wb").write(data)
    print("   converted files in %s" % out)

    # 3) game files
    print("\n-- install")
    if replace:
        I.install_replace(replace, skin_wor, tex_x360, ske, ske_d)
        print("\nDone: %s now looks like %s." % (replace, name))
    else:
        I.install_new(m["id"], name, blurb, skin_wor, tex_x360, ske, ske_d, template)
        print("\nDone: '%s' was added to Select Rocker." % name)
        print("IMPORTANT: rocker profiles are stored in the save game. Start the game with a NEW save\n"
              "(move Xenia's content\\<profile>\\41560883\\00000001\\Progress folder somewhere else first)\n"
              "or the new rocker will not be listed.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["install"]:
        install(a[1:])
    elif a[:1] == ["uninstall"]:
        I.uninstall()
    else:
        print(__doc__)
