"""Install converted characters into GH:WoR (X360). Used by wor_port.py.

Two ways to get a character into the game:

  install_new()      the character gets its own entry in Select Rocker. WoR does not accept extra
                     rocker profiles, so the hidden, unused profile GH_Rocker_Casey_Cut_Skin and its
                     full-body piece Casey_Cut_Skin are repointed at the new files (one free slot).
  install_replace()  an existing rocker (e.g. Johnny_1) uses the new files instead of its own.

Rules learned the hard way (each one hangs WoR at the title screen when broken):
  - data/compressed/compress.toc.xen read sizes must cover a recompressed qb.pab (wor_pak does it)
  - files inside qb.pab must be back to back at 32-byte boundaries, and it must not grow
  - no extra profiles; structural QB edits are risky -> only VALUES are changed here
  - preset profiles are copied into the save game: a new save is needed to see the new rocker
"""
import os, shutil
import wor_tex as W, wor_qb as Q, wor_pak as P

K = W.qbkey
TYPE_SKIN, TYPE_TEX, TYPE_SKE = 0x64112E85, 0x8BFA5E8E, 0x7330095C
TEMPLATES = {"male": "Johnny_1", "female": "Casey_1"}
BODY_SLOT, PROFILE_SLOT = "Casey_Cut_Skin", "GH_Rocker_Casey_Cut_Skin"


def item(items, name):
    return next((i for i in items if i.id == K(name)), None)


def full_body(qb, desc):
    arr = next(s for s in qb.sections if s.id == K("CAS_Full_Body")).value[2]
    return next(el for el in arr if item(el, "desc_id").value == K(desc))


def original_body(desc):
    """Full-body entry of a rocker as shipped (from the qb.pak backup if there is one)."""
    qbpak = P.Pak("qb", from_backup=True)
    return full_body(Q.QBFile(qbpak.find("car_rocker_full_body.qb")[1]), desc)


def template_skin(desc):
    """The game's own .skin of a rocker (material/layout template for wor_skinconv)."""
    arc = W.Archive()
    key = K(".skin", item(original_body(desc), "mesh").value)
    orig = W.Archive(None, arc.pak + ".bak", arc.pab + ".bak") if os.path.exists(arc.pab + ".bak") else arc
    return orig.read(orig.find(key))


def install_new(cid, display, blurb, skin, tex, ske=None, ske_drum=None, template="Johnny_1"):
    """skin/tex/ske = file contents (bytes). Without ske the template's skeletons are used."""
    low = "".join(c for c in cid.lower() if c.isalnum() or c == "_")
    mesh_path = "models\\gh_rockers\\%s\\%s_1" % (low, low)
    ske_path = "skeletons\\gh_rocker_%s_1" % low
    sked_path = "skeletons\\gh_drummer_%s_1" % low

    arc = W.Archive()
    files = [(TYPE_SKIN, mesh_path + ".skin", skin), (TYPE_TEX, mesh_path + ".tex", tex)]
    if ske:
        files += [(TYPE_SKE, ske_path + ".ske", ske), (TYPE_SKE, sked_path + ".ske", ske_drum or ske)]
    for typ, path, data in files:
        print("cas_pieces: + %s" % path)
        arc.add(typ, K(path), data)

    qbpak = P.Pak("qb", from_backup=True)
    ent = qbpak.find("car_rocker_full_body.qb")
    qb = Q.QBFile(ent[1])
    tmpl, body = full_body(qb, template), full_body(qb, BODY_SLOT)
    item(body, "mesh").value = K(mesh_path)
    for key in ("skeleton_id", "anim_struct", "guitar_offset", "body_skeleton", "body_skeleton2"):
        item(body, key).value = item(tmpl, key).value
    if ske:
        item(body, "body_skeleton").value = K(ske_path)
        item(body, "body_skeleton2").value = K(sked_path)
    [i for i in body if i.id == 0][0].value = [i for i in tmpl if i.id == 0][0].value  # common settings
    out = Q.write_qb(qb)
    assert len(out) == len(ent[1]) and Q.write_qb(Q.QBFile(out)) == out
    ent[1] = out
    print("qb: full-body piece %s -> %s (animations of %s)" % (BODY_SLOT, mesh_path, template))

    ent = qbpak.find("guitar_band_ghrocker_profiles.qb")
    qb = Q.QBFile(ent[1])
    prof = next(el for el in next(s for s in qb.sections if s.id == K("Preset_Musician_Profiles_GHRockers")).value[2]
                if item(el, "name").value == K(PROFILE_SLOT))
    for i in prof:  # selection_not_allowed hides it from Select Rocker: swap for an unused flag
        if i.id == 0 and i.value == K("selection_not_allowed"):
            i.value = K("wor_tools_selectable")
    out = Q.write_qb(qb)
    assert len(out) == len(ent[1]) and Q.write_qb(Q.QBFile(out)) == out
    ent[1] = out
    print("qb: profile %s made selectable" % PROFILE_SLOT)
    qbpak.save()

    qspak = P.Pak("qs", from_backup=True)
    ent = qspak.find("guitar_band_ghrocker_profiles.qs")
    texts = {item(prof, "fullname").value: "\\L" + display}
    if blurb:
        texts[item(prof, "blurb").value] = blurb
    lines = ent[1].decode("utf-16").split("\n")
    for n, line in enumerate(lines):
        for key, txt in texts.items():
            if line.startswith("%08x " % key):
                lines[n] = '%08x "%s"' % (key, txt.replace('"', "'"))
    ent[1] = "\n".join(lines).encode("utf-16")
    qspak.save()
    print('qs: name "%s"%s' % (display, ', description "%s"' % blurb if blurb else ""))


def install_replace(target, skin, tex, ske=None, ske_drum=None):
    """Overwrite the files of an existing rocker, e.g. target='Johnny_1'. No script changes."""
    body = original_body(target)
    mesh = item(body, "mesh").value
    arc = W.Archive()
    files = [(K(".skin", mesh), skin, "skin"), (K(".tex", mesh), tex, "tex")]
    if ske:
        files += [(K(".ske", item(body, "body_skeleton").value), ske, "ske (rocker)"),
                  (K(".ske", item(body, "body_skeleton2").value), ske_drum or ske, "ske (drummer)")]
    for key, data, what in files:
        print("cas_pieces: %s %s replaced" % (target, what))
        arc.write(arc.find(key), data)


def uninstall():
    """Put every file this toolkit modified back to the original (from the .bak copies)."""
    arc = W.Archive()
    paths = [arc.pak, arc.pab, P.TOC]
    for n in ("qb", "qs"):
        paths +=[os.path.join(P.PAKDIR, n + ".pak.xen"), os.path.join(P.PAKDIR, n + ".pab.xen")]
    for p in paths:
        if os.path.exists(p + ".bak"):
            shutil.copyfile(p + ".bak", p)
            print("restored", os.path.relpath(p, W.DATA))
