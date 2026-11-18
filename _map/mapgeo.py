"""Drawing code for the map: projections, re-centering on another meridian, simplifying, path data.

Used by build.py. Everything is in "drawing units": the world is W units wide and H units tall, y grows downward.
(The comparison sheets that also used it, for map styles and projections, are not in the repo.)
"""
import json
import math

# Equal Earth projection (Savric, Patterson, Jenny 2018): equal-area, with a calm, familiar shape
A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
M = math.sqrt(3) / 2


def project(lon, lat):
    lam, phi = math.radians(lon), math.radians(lat)
    t = math.asin(M * math.sin(phi))
    t2 = t * t
    t6 = t2 * t2 * t2
    return lam * math.cos(t) / (M * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2))), t * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))


W = 1000.0
LAT_TOP, LAT_BOTTOM = 84.0, -57.0   # crop: no land of interest beyond these; Antarctica is left out
X_MAX = project(180, 0)[0]
S = W / (2 * X_MAX)
Y_TOP = project(0, LAT_TOP)[1]
H = round((Y_TOP - project(0, LAT_BOTTOM)[1]) * S)


def wrap(lon):
    return (lon + 180.0) % 360.0 - 180.0


def to_xy(lon, lat, center=0.0):
    """Drawing units for a place; center is the meridian in the middle of the map."""
    x, y = project(wrap(lon - center) if center else lon, lat)
    return (x + X_MAX) * S, (Y_TOP - y) * S


def load_rings(path):
    """Every land ring of a Natural Earth GeoJSON file as (lon, lat) points, Antarctica left out."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rings = []
    for feature in data["features"]:
        geom = feature["geometry"]
        polygons = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for polygon in polygons:
            for ring in polygon:
                pts = [(float(p[0]), float(p[1])) for p in ring]
                if len(pts) > 1 and pts[0] == pts[-1]:
                    pts.pop()
                if len(pts) >= 3 and max(lat for _, lat in pts) >= LAT_BOTTOM:
                    rings.append(pts)
    return rings


def clip_band(poly, lo, hi):
    """Keep the part of a polygon, given as (x, lat) points, with lo <= x <= hi (Sutherland-Hodgman)."""
    def cut(points, edge, keep_right):
        out = []
        for i, a in enumerate(points):
            b = points[(i + 1) % len(points)]
            a_in = a[0] >= edge if keep_right else a[0] <= edge
            b_in = b[0] >= edge if keep_right else b[0] <= edge
            if a_in:
                out.append(a)
            if a_in != b_in:
                t = (edge - a[0]) / (b[0] - a[0])
                out.append((edge, a[1] + t * (b[1] - a[1])))
        return out
    part = cut(poly, lo, True)
    return cut(part, hi, False) if part else []


def recenter(ring, center):
    """The ring in longitudes measured from a new middle meridian; a ring that crosses the new edge is cut in two."""
    if not center:
        return [ring]
    line, prev, acc = [], None, 0.0
    for lon, lat in ring:
        x = wrap(lon - center)
        if prev is None:
            acc = x
        else:
            d = x - prev
            acc += d - 360 if d > 180 else d + 360 if d < -180 else d
        prev = x
        line.append((acc, lat))
    pieces = []
    for k in (-1, 0, 1):
        lo, hi = -180 + 360 * k, 180 + 360 * k
        if max(p[0] for p in line) <= lo or min(p[0] for p in line) >= hi:
            continue
        piece = clip_band(line, lo, hi)
        if len(piece) >= 3:
            pieces.append([(x - 360 * k, lat) for x, lat in piece])
    return pieces


def simplify(points, eps):
    """Douglas-Peucker on an open line."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = points[a], points[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        best, idx = 0.0, -1
        for i in range(a + 1, b):
            px, py = points[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / norm if norm else math.hypot(px - ax, py - ay)
            if d > best:
                best, idx = d, i
        if best > eps:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(points, keep) if k]


def area(ring):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def fmt(v, dec):
    """A number for path data: fixed decimals, no trailing zeros, no leading zero before the point."""
    s = f"{v:.{dec}f}"
    if dec:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    return s.replace("0.", ".", 1) if s.startswith("0.") else s.replace("-0.", "-.", 1) if s.startswith("-0.") else s


def ring_path(ring, dec):
    """One closed ring as compact path data: absolute start, then relative steps."""
    pts = []
    for x, y in ring:
        p = (round(x, dec), round(y, dec))
        if not pts or p != pts[-1]:
            pts.append(p)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    if len(pts) < 3:
        return ""
    out = [f"M{fmt(pts[0][0], dec)} {fmt(pts[0][1], dec)}l"]
    first = True
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        for v in (x1 - x0, y1 - y0):
            s = fmt(v, dec)
            out.append(s if first or s.startswith("-") else " " + s)
            first = False
    return "".join(out) + "z"


def land(rings, center, tolerance, min_area, dec):
    """Projected, simplified land: the path data, the rings in drawing units, and the point count.

    tolerance and min_area are in drawing units (and units squared); dec is the number of decimals kept.
    """
    parts, shapes, points = [], [], 0
    for ring in rings:
        for piece in recenter(ring, center):
            xy = [((x + X_MAX) * S, (Y_TOP - y) * S) for x, y in (project(lon, lat) for lon, lat in piece)]
            if area(xy) < min_area:
                continue
            # simplify the closed ring as two open halves so the start point is not special
            half = len(xy) // 2
            simple = simplify(xy[: half + 1], tolerance)[:-1] + simplify(xy[half:] + xy[:1], tolerance)[:-1]
            d = ring_path(simple, dec)
            if d:
                parts.append(d)
                shapes.append(simple)
                points += len(simple)
    return "".join(parts), shapes, points


# ---- more than one map shape ----------------------------------------------------------------------------
# The functions above are the Equal Earth map as first built. A Frame does the same job for any projection:
# it fits the projection to a drawing W units wide, cropped between two latitudes.

def equal_earth(lam, phi):
    t = math.asin(M * math.sin(phi))
    t2 = t * t
    t6 = t2 * t2 * t2
    return lam * math.cos(t) / (M * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2))), t * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))


def miller(lam, phi):
    """Rectangular: every meridian upright, the far north stretched only a little."""
    return lam, 1.25 * math.log(math.tan(math.pi / 4 + 0.4 * phi))


def equirectangular(lam, phi):
    return lam, phi


def mercator(lam, phi):
    return lam, math.log(math.tan(math.pi / 4 + phi / 2))


class Frame:
    """A projection (a function of longitude and latitude in radians) fitted to the drawing."""

    def __init__(self, proj, lat_top, lat_bottom=LAT_BOTTOM):
        self.proj = proj
        self.x_max = proj(math.pi, 0)[0]
        self.s = W / (2 * self.x_max)
        self.y_top = proj(0, math.radians(lat_top))[1]
        self.h = round((self.y_top - proj(0, math.radians(lat_bottom))[1]) * self.s)

    def xy(self, lon, lat):
        """Drawing units for a longitude already measured from the map's middle meridian."""
        x, y = self.proj(math.radians(lon), math.radians(min(lat, 89.0)))
        return (x + self.x_max) * self.s, (self.y_top - y) * self.s

    def place(self, lon, lat, center=0.0):
        """Drawing units for a place; center is the meridian in the middle of the map."""
        return self.xy(wrap(lon - center) if center else lon, lat)

    def land(self, rings, center=0.0, tolerance=0.22, min_area=0.5, dec=1):
        """Projected, simplified land: the path data, the rings in drawing units, and the point count."""
        parts, shapes, points = [], [], 0
        for ring in rings:
            for piece in recenter(ring, center):
                pts = [self.xy(lon, lat) for lon, lat in piece]
                if area(pts) < min_area:
                    continue
                # simplify the closed ring as two open halves so the start point is not special
                half = len(pts) // 2
                simple = simplify(pts[: half + 1], tolerance)[:-1] + simplify(pts[half:] + pts[:1], tolerance)[:-1]
                d = ring_path(simple, dec)
                if d:
                    parts.append(d)
                    shapes.append(simple)
                    points += len(simple)
        return "".join(parts), shapes, points
