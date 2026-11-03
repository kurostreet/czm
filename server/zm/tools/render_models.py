#!/usr/bin/env python3
"""Pictures of the skins and knives for the player panel, drawn from the game's own models.

Runs on the game host after the content is in place (install_content.py calls it):

    python3 -I render_models.py GAME_DIR OUT_DIR [id ...]

Reads GoldSrc studio models (version 10) and draws each one in its idle pose with a small software
rasteriser, so the panel shows exactly what the player wears in the game. Plain Python, no
packages: the game host has none, and it runs at the lowest priority next to the game server.
Writes OUT_DIR/skins/<id>.png (320x480) and OUT_DIR/knives/<id>.png (480x360) with a transparent
background; a picture newer than its model and this script is kept.
"""
import array
import math
import os
import struct
import sys
import zlib

# panel id: the model it shows (the same files the game puts on, see survival.py CATALOG)
SKINS = {
    "sas": "models/player/sas/sas.mdl",
    "gsg9": "models/player/gsg9/gsg9.mdl",
    "gsg9_admin": "models/player/czm_gsg9_admin/czm_gsg9_admin.mdl",
    "gign": "models/player/gign/gign.mdl",
    "sas_custom": "models/player/czm_sas_custom/czm_sas_custom.mdl",
    "elite_arctic": "models/player/arctic/arctic.mdl",
    "leet": "models/player/leet/leet.mdl",
    "leet_pirate": "models/player/czm_leet_pirate/czm_leet_pirate.mdl",
    "professional": "models/player/czm_professional/czm_professional.mdl",
    "survivor": "models/player/czm_survivor/czm_survivor.mdl",
}
KNIVES = {
    "glass": "models/czm_survival/v_glass.mdl",
    "katana": "models/czm_survival/v_katana.mdl",
    "axe": "models/czm_survival/v_axe.mdl",
    "sickle": "models/czm_survival/v_sickle.mdl",
}
GLOW = {"survivor": (0, 136, 255)}  # the skins that shine in the game (survival.py "glow")
# what each skin holds in the picture: the weapon model and the upper body sequence of the game,
# the legs stand in idle1 as in the game (the Zombie Plague survivor carries the M249)
RIFLE, AK47, M249 = ("models/p_m4a1.mdl", "ref_aim_rifle"), ("models/p_ak47.mdl", "ref_aim_ak47"), ("models/p_m249.mdl", "ref_aim_m249")
WEAPON = {"sas": RIFLE, "gsg9": RIFLE, "gsg9_admin": RIFLE, "gign": RIFLE, "sas_custom": RIFLE,
          "elite_arctic": AK47, "leet": AK47, "leet_pirate": AK47, "professional": AK47, "survivor": M249}

SKIN_SIZE = (320, 480)
KNIFE_SIZE = (480, 360)
SS = 3  # supersampling per axis

NF_CHROME, NF_FULLBRIGHT, NF_ADDITIVE, NF_MASKED = 2, 4, 32, 64


class Studio:
    """The parts of a studio model a still picture needs: bones, one pose, meshes, textures."""

    def __init__(self, path):
        d = open(path, "rb").read()
        if d[:4] != b"IDST" or struct.unpack_from("<i", d, 4)[0] != 10:
            raise ValueError("not a GoldSrc studio model")
        self.d = d
        nb, bi = struct.unpack_from("<2i", d, 140)
        self.bones = []
        for i in range(nb):
            o = bi + i * 112
            self.bones.append((struct.unpack_from("<i", d, o + 32)[0], struct.unpack_from("<6f", d, o + 64),
                               struct.unpack_from("<6f", d, o + 88), d[o:o + 32].split(b"\0")[0].decode("latin-1").lower()))
        ns, si = struct.unpack_from("<2i", d, 164)
        self.seqs = []
        for i in range(ns):
            o = si + i * 176
            label = d[o:o + 32].split(b"\0")[0].decode("latin-1").lower()
            blends, anim = struct.unpack_from("<2i", d, o + 120)
            self.seqs.append((label, anim, struct.unpack_from("<i", d, o + 156)[0], max(1, blends)))
        self.textures, self.skins = self._textures(d)
        if not self.textures:
            base = path[:-4]
            for t in (base + "T.mdl", base + "t.mdl", base + "T.MDL"):
                if os.path.exists(t):
                    td = open(t, "rb").read()
                    if td[:4] == b"IDST":
                        self.textures, self.skins = self._textures(td)
                    break

    @staticmethod
    def _textures(d):
        nt, ti = struct.unpack_from("<2i", d, 180)
        nref, nfam, ski = struct.unpack_from("<3i", d, 192)
        textures = []
        for i in range(nt):
            flags, w, h, idx = struct.unpack_from("<4i", d, ti + i * 80 + 64)
            textures.append((flags, w, h, d[idx:idx + w * h], d[idx + w * h:idx + w * h + 768]))
        skins = struct.unpack_from("<%dh" % nref, d, ski) if nref > 0 and nfam > 0 else ()
        return textures, skins

    def sequence(self, names, fallback=0):
        labels = [s[0] for s in self.seqs]
        for n in names:
            if n in labels:
                return labels.index(n)
        return fallback if self.seqs else None

    def _anim(self, seq, blend):
        """Where the bones' channels of that blend start, None for the rest pose."""
        if seq is None or self.seqs[seq][2] != 0:
            return None
        return self.seqs[seq][1] + min(blend, self.seqs[seq][3] - 1) * len(self.bones) * 12

    def _animvalue(self, p):
        """Frame 0 of a run-length coded channel."""
        d = self.d
        valid, total = d[p], d[p + 1]
        if total == 0 or valid == 0:
            return 0
        return struct.unpack_from("<h", d, p + 2)[0]

    def pose(self, seq, blend=0, gait=None, merge=None):
        """World matrices (3x4, row-major) of every bone at frame 0 of the sequence.

        As the game draws a player: with a gait sequence, the bones before "Bip01 Spine" (the legs)
        take it. merge {bone name: matrix} puts a weapon's bones on the player's (bone merge).
        """
        d = self.d
        split = 0
        if gait is not None:
            split = next((i for i, b in enumerate(self.bones) if b[3] == "bip01 spine"), 0)
        upper, legs = self._anim(seq, blend), self._anim(gait, 0)
        mats = []
        for b, (parent, value, scale, name) in enumerate(self.bones):
            if merge and name in merge:
                mats.append(merge[name])
                continue
            anim = legs if b < split else upper
            ch = list(value)
            if anim is not None:
                p = anim + b * 12
                offs = struct.unpack_from("<6H", d, p)
                for j in range(6):
                    if offs[j]:
                        ch[j] = value[j] + self._animvalue(p + offs[j]) * scale[j]
            m = _bone_matrix(ch)
            mats.append(_mat_mul(mats[parent], m) if 0 <= parent < len(mats) else m)
        return mats

    def triangles(self, mats):
        """[(texture, [(position, normal, s, t)] * 3)] of body 0."""
        d = self.d
        nbp, bpi = struct.unpack_from("<2i", d, 204)
        tris = []
        for i in range(nbp):
            nm, _base, mi = struct.unpack_from("<3i", d, bpi + i * 76 + 64)
            if nm <= 0:
                continue
            nmesh, meshi, nv, vinfo, vi, nn, ninfo, ni = struct.unpack_from("<8i", d, mi + 72)
            verts = [_xform(mats[d[vinfo + k]], struct.unpack_from("<3f", d, vi + 12 * k)) for k in range(nv)]
            norms = [_rotate(mats[d[ninfo + k]], struct.unpack_from("<3f", d, ni + 12 * k)) for k in range(nn)]
            for j in range(nmesh):
                _numtris, p, skinref = struct.unpack_from("<3i", d, meshi + 20 * j)
                tex = self.skins[skinref] if skinref < len(self.skins) else skinref
                while True:
                    n = struct.unpack_from("<h", d, p)[0]
                    p += 2
                    if n == 0:
                        break
                    fan, n = n < 0, abs(n)
                    cmd = [struct.unpack_from("<4h", d, p + 8 * k) for k in range(n)]
                    p += 8 * n
                    for a in range(n - 2):
                        if fan:
                            tri = (cmd[0], cmd[a + 1], cmd[a + 2])
                        elif a % 2:
                            tri = (cmd[a + 1], cmd[a], cmd[a + 2])
                        else:
                            tri = (cmd[a], cmd[a + 1], cmd[a + 2])
                        if all(v < nv and q < nn for v, q, _s, _t in tri):
                            tris.append((tex, [(verts[v], norms[q], s, t) for v, q, s, t in tri]))
        return tris


def _bone_matrix(ch):
    # AngleQuaternion of the Half-Life SDK, then the matrix with the position
    sy, cy = math.sin(ch[5] * 0.5), math.cos(ch[5] * 0.5)
    sp, cp = math.sin(ch[4] * 0.5), math.cos(ch[4] * 0.5)
    sr, cr = math.sin(ch[3] * 0.5), math.cos(ch[3] * 0.5)
    x = sr * cp * cy - cr * sp * sy
    y = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy
    w = cr * cp * cy + sr * sp * sy
    return (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y), ch[0],
            2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x), ch[1],
            2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y), ch[2])


def _mat_mul(a, b):
    out = []
    for r in range(3):
        a0, a1, a2, a3 = a[4 * r:4 * r + 4]
        out += [a0 * b[0] + a1 * b[4] + a2 * b[8], a0 * b[1] + a1 * b[5] + a2 * b[9],
                a0 * b[2] + a1 * b[6] + a2 * b[10], a0 * b[3] + a1 * b[7] + a2 * b[11] + a3]
    return tuple(out)


def _xform(m, v):
    x, y, z = v
    return (m[0] * x + m[1] * y + m[2] * z + m[3], m[4] * x + m[5] * y + m[6] * z + m[7],
            m[8] * x + m[9] * y + m[10] * z + m[11])


def _rotate(m, v):
    x, y, z = v
    return (m[0] * x + m[1] * y + m[2] * z, m[4] * x + m[5] * y + m[6] * z, m[8] * x + m[9] * y + m[10] * z)


def _norm(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class Camera:
    """Eye and the direction back towards it; x right, y up, depth forward; focal 1 = 90 degrees."""

    def __init__(self, eye, back, focal=1.0):
        self.eye, self.back = eye, _norm(back)
        self.right = _norm(_cross((0.0, 0.0, 1.0), self.back))
        self.up = _cross(self.back, self.right)
        self.focal = focal

    def view(self, p):
        rel = (p[0] - self.eye[0], p[1] - self.eye[1], p[2] - self.eye[2])
        depth = -_dot(rel, self.back)
        if depth <= 0.5:
            return None
        return self.focal * _dot(rel, self.right) / depth, self.focal * _dot(rel, self.up) / depth, depth

    def normal(self, n):
        return _dot(n, self.right), _dot(n, self.up), _dot(n, self.back)


# camera space light: a key from the upper left, a warm rim behind on the left, a cool one on the right
KEY = _norm((-0.45, 0.6, 0.65))
RIM_WARM, WARM = _norm((-0.85, 0.2, -0.5)), (1.0, 0.62, 0.35)
RIM_COOL, COOL = _norm((0.85, 0.25, -0.45)), (0.5, 0.75, 1.0)


def _light(n):
    d = (_dot(n, KEY) + 0.5) / 1.5
    base = 0.5 + 0.78 * max(0.0, d)
    w = max(0.0, _dot(n, RIM_WARM)) ** 1.5 * 0.75
    c = max(0.0, _dot(n, RIM_COOL)) ** 1.5 * 0.9
    return base + w * WARM[0] + c * COOL[0], base + w * WARM[1] + c * COOL[1], base + w * WARM[2] + c * COOL[2]


def project(model, tris, cam):
    """Screen-ready triangles: (texture, [(x, y, q, s*q, t*q, r, g, b)] * 3) in view-plane units."""
    out = []
    textures = model.textures
    for tex, verts in tris:
        flags, tw, th = (textures[tex][:3] if 0 <= tex < len(textures) else (0, 1, 1))
        vs = []
        for pos, nrm, s, t in verts:
            v = cam.view(pos)
            if v is None:
                break
            n = cam.normal(nrm)
            if flags & NF_CHROME:
                s, t = (n[0] * 0.5 + 0.5) * tw, (0.5 - n[1] * 0.5) * th
            r, g, b = (1.0, 1.0, 1.0) if flags & NF_FULLBRIGHT else _light(n)
            q = 1.0 / v[2]
            vs.append((v[0], v[1], q, s * q, t * q, r, g, b))
        if len(vs) == 3:
            out.append((tex, vs))
    return out


def bounds(ptris):
    xs = [v[0] for _t, vs in ptris for v in vs]
    ys = [v[1] for _t, vs in ptris for v in vs]
    return min(xs), min(ys), max(xs), max(ys)


def raster(model, ptris, W, H, sc, ox, oy, clip=None):
    """Draws the triangles at X = ox + x*sc, Y = oy - y*sc; returns (rgb, alpha) of W x H."""
    N = W * H
    rgb = bytearray(N * 3)
    alpha = array.array("f", bytes(4 * N))
    zbuf = array.array("f", bytes(4 * N))
    cx0, cy0, cx1, cy1 = clip if clip else (0, 0, W - 1, H - 1)
    cx0, cy0, cx1, cy1 = max(0, cx0), max(0, cy0), min(W - 1, cx1), min(H - 1, cy1)
    textures = model.textures
    fallback = (0, 1, 1, b"\0", bytes((160, 160, 160)) * 256)
    opaque = [t for t in ptris if not (0 <= t[0] < len(textures) and textures[t[0]][0] & NF_ADDITIVE)]
    additive = [t for t in ptris if 0 <= t[0] < len(textures) and textures[t[0]][0] & NF_ADDITIVE]
    for add, group in ((False, opaque), (True, additive)):
        for tex, vs in group:
            flags, tw, th, pix, pal = textures[tex] if 0 <= tex < len(textures) else fallback
            if tw <= 0 or th <= 0 or len(pix) < tw * th:
                flags, tw, th, pix, pal = fallback
            masked = flags & NF_MASKED
            (x0, y0, q0, s0, t0, r0, g0, b0), (x1, y1, q1, s1, t1, r1, g1, b1), (x2, y2, q2, s2, t2, r2, g2, b2) = [
                (ox + v[0] * sc, oy - v[1] * sc) + v[2:] for v in vs]
            area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if area == 0:
                continue
            if area < 0:
                x1, y1, q1, s1, t1, r1, g1, b1, x2, y2, q2, s2, t2, r2, g2, b2 = \
                    x2, y2, q2, s2, t2, r2, g2, b2, x1, y1, q1, s1, t1, r1, g1, b1
                area = -area
            ia = 1.0 / area
            # edge functions: weight of v0 from the edge v1-v2, of v1 from v2-v0, of v2 from v0-v1
            A0, B0, C0 = -(y2 - y1), (x2 - x1), (y2 - y1) * x1 - (x2 - x1) * y1
            A1, B1, C1 = -(y0 - y2), (x0 - x2), (y0 - y2) * x2 - (x0 - x2) * y2
            A2, B2, C2 = -(y1 - y0), (x1 - x0), (y1 - y0) * x0 - (x1 - x0) * y0
            ya = max(cy0, int(math.floor(min(y0, y1, y2)))); yb = min(cy1, int(math.ceil(max(y0, y1, y2))))
            xa = max(cx0, int(math.floor(min(x0, x1, x2)))); xb = min(cx1, int(math.ceil(max(x0, x1, x2))))
            for y in range(ya, yb + 1):
                py = y + 0.5
                lo, hi = xa, xb
                e0, e1, e2 = B0 * py + C0, B1 * py + C1, B2 * py + C2
                empty = False
                for A, e in ((A0, e0), (A1, e1), (A2, e2)):
                    if A > 0:
                        lo = max(lo, math.ceil(-e / A - 0.5))
                    elif A < 0:
                        hi = min(hi, math.floor(-e / A - 0.5))
                    elif e < 0:
                        empty = True
                if empty or lo > hi:
                    continue
                row = y * W
                for x in range(lo, hi + 1):
                    px = x + 0.5
                    w0 = (A0 * px + e0) * ia
                    w1 = (A1 * px + e1) * ia
                    w2 = 1.0 - w0 - w1
                    q = w0 * q0 + w1 * q1 + w2 * q2
                    i = row + x
                    if q <= zbuf[i]:
                        continue
                    k = pix[(int((w0 * t0 + w1 * t1 + w2 * t2) / q) % th) * tw + int((w0 * s0 + w1 * s1 + w2 * s2) / q) % tw]
                    if masked and k == 255:
                        continue
                    r = pal[3 * k] * (w0 * r0 + w1 * r1 + w2 * r2)
                    g = pal[3 * k + 1] * (w0 * g0 + w1 * g1 + w2 * g2)
                    b = pal[3 * k + 2] * (w0 * b0 + w1 * b1 + w2 * b2)
                    j = 3 * i
                    if add:
                        if alpha[i] == 0.0:
                            r, g, b = r * 0.8, g * 0.8, b * 0.8
                        rgb[j] = min(255, rgb[j] + int(r)); rgb[j + 1] = min(255, rgb[j + 1] + int(g))
                        rgb[j + 2] = min(255, rgb[j + 2] + int(b))
                        alpha[i] = min(1.0, alpha[i] + max(r, g, b) / 255.0)
                    else:
                        zbuf[i] = q
                        rgb[j] = min(255, int(r)); rgb[j + 1] = min(255, int(g)); rgb[j + 2] = min(255, int(b))
                        alpha[i] = 1.0
    return rgb, alpha


def downsample(rgb, alpha, W, H, f):
    """Premultiplied RGBA floats of the (W/f) x (H/f) picture."""
    w, h = W // f, H // f
    out = array.array("f", bytes(16 * w * h))
    n = float(f * f)
    for y in range(h):
        for x in range(w):
            r = g = b = a = 0.0
            for sy in range(f):
                base = (y * f + sy) * W + x * f
                for sx in range(f):
                    i = base + sx
                    ai = alpha[i]
                    if ai:
                        a += ai; r += rgb[3 * i] * ai; g += rgb[3 * i + 1] * ai; b += rgb[3 * i + 2] * ai
            o = 4 * (y * w + x)
            out[o], out[o + 1], out[o + 2], out[o + 3] = r / n, g / n, b / n, a / n
    return out


def blur_alpha(px, w, h, radius, passes=3):
    a = array.array("f", px[3::4])
    for _ in range(passes):
        for horizontal in (True, False):
            src, a = a, array.array("f", bytes(4 * w * h))
            n, m = (w, h) if horizontal else (h, w)
            step = 1 if horizontal else w
            for line in range(m):
                start = line * (w if horizontal else 1)
                acc, win = 0.0, 2 * radius + 1
                vals = [src[start + k * step] for k in range(n)]
                for k in range(-radius, radius + 1):
                    acc += vals[min(max(k, 0), n - 1)]
                for k in range(n):
                    a[start + k * step] = acc / win
                    acc += vals[min(k + radius + 1, n - 1)] - vals[max(k - radius, 0)]
    return a


def under(px, layer_alpha, color, strength):
    """Puts a coloured layer (alpha per pixel) under the picture."""
    cr, cg, cb = color
    for i in range(len(layer_alpha)):
        la = min(1.0, layer_alpha[i] * strength)
        if la <= 0.0:
            continue
        o = 4 * i
        keep = 1.0 - px[o + 3]
        px[o] += cr * la * keep; px[o + 1] += cg * la * keep; px[o + 2] += cb * la * keep
        px[o + 3] += la * keep


def shadow(w, h, cx, cy, rx, ry):
    a = array.array("f", bytes(4 * w * h))
    for y in range(max(0, int(cy - ry)), min(h, int(cy + ry) + 1)):
        for x in range(max(0, int(cx - rx)), min(w, int(cx + rx) + 1)):
            d = ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2
            if d < 1.0:
                a[y * w + x] = (1.0 - d) ** 1.5 * 0.55
    return a


def write_png(path, px, w, h):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            o = 4 * (y * w + x)
            a = px[o + 3]
            if a <= 0.0:
                raw += b"\0\0\0\0"
                continue
            raw += bytes((min(255, int(px[o] / a + 0.5)), min(255, int(px[o + 1] / a + 0.5)),
                          min(255, int(px[o + 2] / a + 0.5)), min(255, int(a * 255 + 0.5))))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", w, h, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def render_skin(path, glow=None, weapon=None):
    model = Studio(path)
    if os.environ.get("CZM_RENDER_DEBUG"):
        print(path, [(q[0], q[3]) for q in model.seqs])
    idle = model.sequence(["idle1", "idle"])
    tris = None
    if weapon and os.path.exists(weapon[0]):
        aim = model.sequence([weapon[1]], None)
        if aim is not None:
            mats = model.pose(aim, model.seqs[aim][3] // 2, idle)  # the middle blend looks straight ahead
            tris = model.triangles(mats)
            gun = Studio(weapon[0])
            names = {b[3]: m for b, m in zip(model.bones, mats)}
            gun_tris = gun.triangles(gun.pose(0 if gun.seqs else None, merge=names))
            base = len(model.textures)
            tris += [(tex + base, v) for tex, v in gun_tris]
            model.textures = model.textures + gun.textures
    if tris is None:
        tris = model.triangles(model.pose(idle))
    pts = [v[0] for _t, vs in tris for v in vs]
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    center = [(lo[k] + hi[k]) / 2 for k in range(3)]
    yaw, pitch = math.radians(28), math.radians(6)
    back = (math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch))
    dist = (hi[2] - lo[2]) * 4.0
    cam = Camera([center[k] + back[k] * dist for k in range(3)], back, focal=4.0)
    ptris = project(model, tris, cam)
    w, h = SKIN_SIZE
    W, H = w * SS, h * SS
    x0, y0, x1, y1 = bounds(ptris)
    sc = min(W * 0.92 / (x1 - x0), H * 0.93 / (y1 - y0))
    ox = W / 2 - (x0 + x1) / 2 * sc
    oy = H * 0.965 + y0 * sc  # feet near the bottom, room for the shadow
    rgb, alpha = raster(model, ptris, W, H, sc, ox, oy)
    px = downsample(rgb, alpha, W, H, SS)
    if glow:
        under(px, blur_alpha(px, w, h, 5), glow, 1.6)
    under(px, shadow(w, h, w / 2, h * 0.965 - 2, w * 0.3, h * 0.03), (0, 0, 0), 1.0)
    return px, w, h


def render_knife(path):
    model = Studio(path)
    seq = model.sequence(["idle", "idle1"])
    tris = model.triangles(model.pose(seq))
    cam = Camera((0.0, 0.0, 0.0), (-1.0, 0.0, 0.0), focal=1.0)
    ptris = project(model, tris, cam)
    # what the player sees (90 degrees, 4:3), then the part with the knife, cut where the screen cuts it
    fw, fh = 320, 240
    rgb, alpha = raster(model, ptris, fw, fh, fw / 2, fw / 2, fh / 2)
    cols = [x for x in range(fw) if any(alpha[y * fw + x] for y in range(fh))]
    rows = [y for y in range(fh) if any(alpha[y * fw + x] for x in range(fw))]
    if not cols:
        raise ValueError("nothing in view")
    vx0, vx1 = (cols[0] - fw / 2) / (fw / 2), (cols[-1] + 1 - fw / 2) / (fw / 2)
    vy1, vy0 = (fh / 2 - rows[0]) / (fw / 2), (fh / 2 - rows[-1] - 1) / (fw / 2)
    edge_l, edge_r, edge_t, edge_b = cols[0] == 0, cols[-1] == fw - 1, rows[0] == 0, rows[-1] == fh - 1
    w, h = KNIFE_SIZE
    W, H = w * SS, h * SS
    m = 0.07
    sc = min(W * (1 - (0 if edge_l else m) - (0 if edge_r else m)) / (vx1 - vx0),
             H * (1 - (0 if edge_t else m) - (0 if edge_b else m)) / (vy1 - vy0))
    if edge_r and not edge_l:
        ox = W - vx1 * sc
    elif edge_l and not edge_r:
        ox = -vx0 * sc
    else:
        ox = W / 2 - (vx0 + vx1) / 2 * sc
    if edge_b and not edge_t:
        oy = H + vy0 * sc
    elif edge_t and not edge_b:
        oy = vy1 * sc
    else:
        oy = H / 2 + (vy0 + vy1) / 2 * sc
    clip = (int(ox - sc), int(oy - 0.75 * sc), int(ox + sc), int(oy + 0.75 * sc))
    rgb, alpha = raster(model, ptris, W, H, sc, ox, oy, clip)
    return downsample(rgb, alpha, W, H, SS), w, h


def main(game, out, only=()):
    try:
        os.nice(19)
    except (AttributeError, OSError):
        pass
    me = os.path.getmtime(os.path.abspath(__file__))
    done = 0
    for folder, table in (("skins", SKINS), ("knives", KNIVES)):
        os.makedirs(os.path.join(out, folder), mode=0o755, exist_ok=True)
        for pid, rel in table.items():
            if only and pid not in only:
                continue
            src = os.path.join(game, rel)
            dst = os.path.join(out, folder, pid + ".png")
            if not os.path.exists(src):
                print("render: no model for", pid)
                continue
            if not only and os.path.exists(dst) and os.path.getmtime(dst) >= max(me, os.path.getmtime(src)):
                continue
            try:
                if folder == "skins":
                    gun = WEAPON.get(pid)
                    px, w, h = render_skin(src, GLOW.get(pid), gun and (os.path.join(game, gun[0]), gun[1]))
                else:
                    px, w, h = render_knife(src)
                write_png(dst, px, w, h)
                done += 1
                print("render:", folder, pid)
            except Exception as e:  # one broken model must not stop the others
                print("render: failed", pid, type(e).__name__, e)
    return done


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], set(sys.argv[3:]))
