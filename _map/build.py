#!/usr/bin/env python3
"""Draw the "Places I've Been" map into a page of the site, or refresh the one that is there.

Usage (from the repo root; -I keeps Python from loading code next to the data):

    python3 -I _map/build.py                 the main page, index.html
    python3 -I _map/build.py some/page.html  another page that has the BEGIN/END map comments (a path from the repo root)

What it reads, all in this folder:
  cities.json   one entry per place: {"name", "cc", "lat", "lon", "note"?, "photo", "photo_w", "photo_h"} in any order;
                the page lists them by name, A to Z. "note" is a few words shown after the name on the photo card
                ("ICML 2026"). "cc" is the two-letter code of the country whose flag follows the name on the card.
                "photo" is a path from the page's folder ("photos/seoul.jpg"); make the file with add_photo.py,
                which also prints its width and height. Use the city's general coordinates, not the photo's own.
  data/         Natural Earth land polygons (public domain): 1:110m for the light outline that sits inside the page,
                1:50m for the detailed one. Coastlines only, no borders and no names. And the flags of flag-icons 7.6.0
                (MIT; its LICENSE travels with the files).

What it writes:
  in the page   the three parts between the "BEGIN map ..." and "END map ..." comments: the styles, the section and
                the script. Everything else in the page is left alone, so the page can be edited by hand; do not edit
                between the comments, change this file instead. Running it twice with nothing changed leaves the
                page byte for byte the same.
  next to the page   land-fine.txt (the detailed outline, fetched when the map nears the screen) and flags/ (the
                flags in use, with the LICENSE). Photos are not copied: photos/ next to the page is where they live.

About the map:
- It is centered on the Pacific (150 E in the middle), so Korea and North America face each other.
- Its shape is Miller's rectangular projection: every meridian is upright, so no region leans, at the price
  of a far north that looks a little larger than it is.
- Each city is a dot on the map and a name under it; pointing at or tapping either shows a photo card.
- Regions with two or more cities get a view of their own: a button next to the heading, or a click on
  that part of the map, glides the map in; another click on the map (or "World") glides back out.
  There is no free zoom or drag, so the map never fights page scrolling.

History: this is references/trial-map/build_map.py (2026-11-15 to 17, not in the repo) without its trial-only parts
(sample cities, placeholder images, building a whole copy of the main page). The page's menu entry, its noscript rule
and the numbers that fit the left column to eight menu items are part of the page itself now.
"""
import json
import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True   # no __pycache__ folder in the repo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CITIES = HERE / "cities.json"
LAND110 = HERE / "data" / "ne_110m_land.geojson"
LAND50 = HERE / "data" / "ne_50m_land.geojson"


PAGE = (ROOT / sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "index.html"

# -I leaves this script's folder out of the import path; the shared drawing code sits next to this file
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mapgeo import Frame, W, load_rings, miller  # noqa: E402

FRAME = Frame(miller, 82.0)   # the map's shape, cropped at 82 N
H = FRAME.h

CENTER = 150.0    # the meridian in the middle of the map
FINE_FILE = "land-fine.txt"
MAX_ZOOM = 5.0    # a region view never enlarges more than this
PAD = 0.22        # room around a region's cities, as a share of their spread

# the regions that can have a closer view, in button order. "Pacific" (Hawaii, Guam and the like) is mostly open sea,
# because its islands lie thousands of kilometers apart; the user asked for it anyway (2026-11-16)
REGION_ORDER = ["East Asia", "Southeast Asia", "South Asia", "Middle East", "Europe", "Africa", "North America", "Latin America", "Oceania", "Pacific"]


def region_of(lon, lat):
    """A rough region for a city, only used to group dots into map views. The cuts are simple lines of
    longitude and latitude, chosen so that each view stays small enough to pull crowded dots apart."""
    if lon < -30:
        if lon < -140 and lat < 30:
            return "Pacific"            # Hawaii and the islands east of the date line: too far from the mainland to share its view
        return "North America" if lat >= 13 else "Latin America"
    if lon < 60:
        if lat >= 35.5 and lon < 45:
            return "Europe"
        return "Middle East" if lon >= 32 and lat >= 12 else "Africa"
    if lon >= 110 and lat < -10:
        return "Oceania"
    if lon >= 130 and lat < 21.5:
        return "Pacific"                # Guam and the other islands of the western Pacific: not Southeast Asia
    if lon < 92:
        return "South Asia"
    return "Southeast Asia" if lat < 21.5 else "East Asia"


def num(v):
    return str(int(v)) if v == int(v) else f"{v:.2f}".rstrip("0").rstrip(".")


def region_views(points):
    """One view per region with at least two cities: [label, x, y, width] in drawing units, same shape as the map."""
    groups = {}
    for (x, y), region in points:
        groups.setdefault(region, []).append((x, y))
    views = []
    for label in REGION_ORDER:
        pts = groups.get(label, [])
        if len(pts) < 2:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        # wide enough for the cities plus some room, in the map's own shape, and never closer than MAX_ZOOM
        w = max((max(xs) - min(xs)) * (1 + 2 * PAD), (max(ys) - min(ys)) * (1 + 2 * PAD) * W / H, W / MAX_ZOOM)
        w = min(w, W)
        h = w * H / W
        x = min(max(cx - w / 2, 0), W - w)
        y = min(max(cy - h / 2, 0), H - h)
        views.append((label, round(x, 1), round(y, 1), round(w, 1)))
    return views


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def photo_for(city):
    """The city's photo path as the page uses it. The file itself lives next to the page; it is not copied."""
    rel = city.get("photo", "")
    if rel and not (PAGE.parent / rel).is_file():
        sys.exit(f'{city["name"]}: {rel} is missing next to {PAGE.relative_to(ROOT)} (make it with _map/add_photo.py)')
    return rel


# flag-icons 7.6.0, the 4:3 flags (MIT license, github.com/lipis/flag-icons), downloaded with the user's OK on 2026-11-16.
# pictures, not flag emoji: those print as two letters ("FR") in Chrome and Edge on Windows. after a trial with flags
# on the card and in the name list, the user chose the card only
FLAG_SOURCE = HERE / "data" / "flag-icons-7.6.0"


def flag_for(city):
    """The path of the city's country flag as the page will use it, or nothing. The flag is copied next to the page,
    together with the flag set's license, which has to travel with the files."""
    cc = city.get("cc", "")
    source = FLAG_SOURCE / f"{cc}.svg"
    if not re.fullmatch(r"[a-z]{2}", cc) or not source.is_file():
        return ""
    target = PAGE.parent / "flags" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    shutil.copyfile(source.parent / "LICENSE", target.parent / "LICENSE")
    return f"flags/{source.name}"


def build_section(cities):
    # the light outline goes into the page; the detailed one into a file the page fetches when the map nears the screen
    coarse, _, coarse_points = FRAME.land(load_rings(LAND110), CENTER, 0.5, 1.5, 0)
    # islands down to 0.25 units squared are kept in the detailed outline, so that Guam (about 0.35) is drawn under its dot
    fine, _, fine_points = FRAME.land(load_rings(LAND50), CENTER, 0.22, 0.25, 1)
    (PAGE.parent / FINE_FILE).write_text(fine + "\n", encoding="utf-8")
    pins, names, placed = [], [], []
    for i, c in enumerate(cities):
        x, y = FRAME.place(c["lon"], c["lat"], CENTER)
        placed.append(((x, y), region_of(c["lon"], c["lat"])))
        photo = photo_for(c)
        flag = flag_for(c)
        ratio = min(max(c["photo_w"] / c["photo_h"], 0.7), 1.6) if c.get("photo_w") and c.get("photo_h") else 1.5
        pins.append(
            f'            <i class="pin" aria-hidden="true" style="left:{num(round(x / W * 100, 2))}%;top:{num(round(y / H * 100, 2))}%"'
            f' data-x="{num(round(x, 1))}" data-y="{num(round(y, 1))}" data-name="{esc(c["name"])}" data-note="{esc(c.get("note", ""))}" data-photo="{esc(photo)}" data-ratio="{num(round(ratio, 2))}"'
            + (f' data-flag="{esc(flag)}"' if flag else "") + "></i>"
        )
        # a name never breaks inside, and the dot between names stays at the end of a line, not the start of the next
        sep = "&nbsp;&middot;" if i < len(cities) - 1 else ""
        names.append(f'<span class="pi"><button class="pname" type="button">{esc(c["name"])}</button>{sep}</span>')
    views = region_views(placed)
    buttons = [f'            <button type="button" role="radio" aria-checked="true" tabindex="0" data-view="0,0,{num(W)}">World</button>']
    buttons += [
        f'            <button type="button" role="radio" aria-checked="false" tabindex="-1" data-view="{num(x)},{num(y)},{num(w)}">{esc(label)}</button>'
        for label, x, y, w in views
    ]
    section = f'''      <section class="sec" id="places">
        <div class="sec-h">
          <h2>Places I've Been</h2>
          <div class="views" role="radiogroup" aria-label="Map view">
{chr(10).join(buttons)}
          </div>
        </div>
        <div class="mapbox" id="map" data-w="{num(W)}" data-h="{H}">
          <div class="mapclip" style="aspect-ratio: {num(W)} / {H}">
            <div class="mapfade"><svg class="map" viewBox="0 0 {num(W)} {H}" aria-hidden="true" data-fine="{FINE_FILE}"><path class="land" fill-rule="evenodd" d="{coarse}"/></svg></div>
{chr(10).join(pins)}
          </div>
          <figure class="pcard" id="pcard" aria-hidden="true"><div class="pc-photo"></div><figcaption><span class="pc-name"></span><span class="pc-note"></span></figcaption></figure>
        </div>
        <p class="places">{" ".join(names)}</p>
      </section>

'''
    info = {
        "coarse": f"{coarse_points} points, {len(coarse) / 1024:.0f}KB in the page", "fine": f"{fine_points} points, {len(fine) / 1024:.0f}KB in {FINE_FILE}",
        "size": f"{num(W)}x{H}",
        "views": ", ".join(f"{label} x{W / w:.1f}" for label, _, _, w in views) or "none",
    }
    return section, info


STYLES = '''
    /* places: a quiet world map. coastlines only (no borders, no names), one gray. each city is a dot on the map and a name under it;
       pointing at or tapping either one shows that city's photo in a small card. regions with several cities have a closer view */
    /* the buttons end where the heading's rule ends, like the publication filter */
    .views { display: flex; gap: 2px; }
    .views button { display: inline-flex; align-items: center; height: 28px; padding: 0 10px; border: 0; border-radius: 8px; background: none; color: var(--text-3); font: inherit; font-size: 13px; font-weight: 500; cursor: pointer; transition: background .15s, color .15s; }
    .views button:hover { color: var(--text); }
    .views button[aria-checked="true"] { background: var(--pick); color: var(--text); }
    .mapbox { position: relative; margin: 4px 0 0; -webkit-tap-highlight-color: transparent; }
    /* the map moves inside this frame. the land's edges fade out so a closer view does not end in a hard cut;
       the dots sit outside that fade, so a city near the edge (Rio de Janeiro) keeps a full-strength dot */
    .mapclip { position: relative; overflow: hidden; }
    .mapfade {
      position: absolute; inset: 0; overflow: hidden;
      -webkit-mask-image: linear-gradient(to right, transparent, #000 5%, #000 95%, transparent), linear-gradient(to bottom, transparent, #000 7%, #000 93%, transparent);
      -webkit-mask-composite: source-in;
      mask-image: linear-gradient(to right, transparent, #000 5%, #000 95%, transparent), linear-gradient(to bottom, transparent, #000 7%, #000 93%, transparent);
      mask-composite: intersect;
    }
    .map { display: block; width: 100%; height: 100%; transform-origin: 0 0; transition: transform .6s cubic-bezier(.3, 0, .15, 1); }
    /* the hairline in the fill's own color closes the seam where two pieces of land meet at the date line */
    .map .land { fill: var(--line); stroke: var(--line); stroke-width: .6px; vector-effect: non-scaling-stroke; }
    /* a dot keeps its size at every view: only its position follows the map, with the same timing as the map's own move */
    /* 4px dots with a 1.5px ring in the page's color (5px and 2px until 2026-11-17): cities a little over 4px apart on the
       world map, such as Seattle and Vancouver, show as two dots */
    .pin { position: absolute; width: 4px; height: 4px; margin: -2px 0 0 -2px; border-radius: 50%; background: var(--text); box-shadow: 0 0 0 1.5px var(--bg); pointer-events: none; transition: left .6s cubic-bezier(.3, 0, .15, 1), top .6s cubic-bezier(.3, 0, .15, 1), transform .15s; }
    .pin.on { z-index: 2; transform: scale(1.9); }
    .pcard { position: absolute; z-index: 3; width: 196px; margin: 0; padding: 6px 6px 8px; border-radius: 14px; background: var(--bg); box-shadow: 0 0 0 1px var(--line-2), 0 10px 30px rgba(0, 0, 0, .1); pointer-events: none; opacity: 0; visibility: hidden; transform: translateY(-4px); transition: opacity .15s, transform .15s, visibility .15s; }
    .pcard.up { transform: translateY(4px); }
    .pcard.show { opacity: 1; visibility: visible; transform: none; }
    /* an upright photo gets a narrower card, so the card is not much taller than a wide one */
    .pcard.tall { width: 168px; }
    .pc-photo { position: relative; aspect-ratio: var(--shape, 1.5); border-radius: 9px; overflow: hidden; background: var(--surface); }
    .pc-photo img { position: absolute; inset: 0; display: block; width: 100%; height: 100%; object-fit: cover; opacity: 0; transition: opacity .2s; }
    .pc-photo img.ready { opacity: 1; }
    /* the name and its note each stay in one piece; when both do not fit on a line, the whole note moves to the next */
    .pcard figcaption { display: flex; flex-wrap: wrap; column-gap: 6px; margin: 7px 4px 0; font-size: 12.5px; line-height: 1.35; font-weight: 500; color: var(--text); }
    .pc-name, .pc-note { white-space: nowrap; }
    .pc-note { font-weight: 400; color: var(--text-3); }
    /* the flag of the city's country, right after its name. the hairline keeps a white stripe from dissolving into the card.
       the flag is fetched the first time a card needs it and fades in when it has arrived */
    .pc-name .flag { display: inline-block; width: 1.04em; height: .78em; margin-left: .4em; vertical-align: -.03em; border-radius: 2px; box-shadow: 0 0 0 1px var(--line-2); opacity: 0; transition: opacity .15s; }
    .pc-name .flag.ready { opacity: 1; }
    .places { margin: 16px 0 0; font-size: 13.5px; line-height: 1.8; color: var(--text-3); }
    .places .pi { white-space: nowrap; }
    .pname { all: unset; cursor: pointer; color: var(--text-2); border-radius: 4px; text-decoration: underline; text-decoration-color: transparent; text-decoration-thickness: 1px; text-underline-offset: 3px; transition: color .15s, text-decoration-color .15s; -webkit-tap-highlight-color: transparent; }
    .pname.off { color: var(--text-3); }
    .pname.on { color: var(--text); text-decoration-color: currentColor; }
    .pname:focus-visible { outline: 2px solid var(--text); outline-offset: 2px; }
    @media (pointer: coarse) {
      .places { line-height: 2.3; }
      .views button { position: relative; }
      .views button::after { content: ""; position: absolute; inset: -8px -1px; }
    }
    @media (max-width: 560px) {
      .views { width: 100%; flex-wrap: wrap; }
    }
'''

SCRIPT = r'''      // places. a dot on the map and its name in the list are one city: pointing at either (mouse), moving to the name with
      // the keyboard, or tapping shows the photo card, and a click or tap keeps it open until the next click elsewhere.
      // the map has a few fixed views (the world and each region with several cities); it glides between them and is never dragged
      (() => {
        const box = $("#map"), card = $("#pcard");
        if (!box) return;
        const clip = $(".mapclip", box), land = $(".map", box), slot = $(".pc-photo", card);
        const capName = $(".pc-name", card), capNote = $(".pc-note", card);
        const pins = $$(".pin", box), names = $$(".pname"), tabs = $$(".views button");
        const W = +box.dataset.w, H = +box.dataset.h;
        const at = pins.map(p => [+p.dataset.x, +p.dataset.y]);
        const views = tabs.map(b => b.dataset.view.split(",").map(Number));   // [x, y, width] in drawing units; the first is the world
        let view = 0, active = -1, pinned = false, closedByPress = false;
        const shots = [];   // one picture element per city, made the first time the city is shown
        const flags = {};   // one flag picture per country, made the first time a card needs it
        // the page carries a light outline of the land; the detailed one is fetched when the map comes near the screen,
        // so a closer view has a natural coastline. if that fails, the light outline simply stays
        if (land.dataset.fine && "IntersectionObserver" in window) {
          const near = new IntersectionObserver(entries => {
            if (!entries.some(e => e.isIntersecting)) return;
            near.disconnect();
            fetch(land.dataset.fine).then(r => r.ok ? r.text() : Promise.reject())
              .then(d => { if (/^M[\d.\s-]/.test(d)) $(".land", land).setAttribute("d", d.trim()); })
              .catch(() => {});
          }, { rootMargin: "800px" });
          near.observe(box);
        }

        // where a city sits in the frame at a given view, in percent
        const spot = (i, k = view) => {
          const [x, y, w] = views[k];
          return [(at[i][0] - x) / w * 100, (at[i][1] - y) / (w * H / W) * 100];
        };
        const inView = (i, k = view) => { const [l, t] = spot(i, k); return l >= 0 && l <= 100 && t >= 0 && t <= 100; };

        function hide() {
          if (active < 0) return;
          pins[active].classList.remove("on");
          names[active].classList.remove("on");
          card.classList.remove("show");
          active = -1;
        }
        // on a wide map the card opens beside its dot and stays inside the map, so it never covers the view buttons above
        // or the names below. a narrow map is too small for that: there the card opens above the dot, clear of the names
        function place(i) {
          const [x, y] = spot(i), bw = box.clientWidth, bh = box.clientHeight, cw = card.offsetWidth, ch = card.offsetHeight;
          const px = bw * x / 100, py = bh * y / 100;
          if (bw >= 480) {
            const left = px + 14 + cw <= bw ? px + 14 : px - 14 - cw;
            card.style.left = Math.max(0, Math.min(bw - cw, left)) + "px";
            card.style.top = Math.max(0, Math.min(bh - ch, py - ch / 2)) + "px";
            card.style.bottom = "auto";
            card.classList.remove("up");
          } else {
            card.style.left = Math.max(0, Math.min(bw - cw, px - cw / 2)) + "px";
            card.style.top = "auto";
            card.style.bottom = `calc(${100 - y}% + 14px)`;
            card.classList.add("up");
          }
        }
        function show(i) {
          if (active === i) return;
          hide();
          active = i;
          pins[i].classList.add("on");
          names[i].classList.add("on");
          capName.textContent = pins[i].dataset.name;
          const flag = pins[i].dataset.flag;
          if (flag) {
            if (!flags[flag]) {
              const f = flags[flag] = new Image();
              f.className = "flag";
              f.alt = "";
              f.addEventListener("load", () => f.classList.add("ready"));
              f.addEventListener("error", () => { if (flags[flag] === f) delete flags[flag]; });   // try again next time
              f.src = flag;
            }
            capName.appendChild(flags[flag]);
          }
          capNote.textContent = pins[i].dataset.note;
          // the picture takes the photo's own shape; an upright one gets the narrower card
          card.style.setProperty("--shape", pins[i].dataset.ratio);
          card.classList.toggle("tall", +pins[i].dataset.ratio < 1);
          // the photo is fetched the first time its city is shown, so the page itself stays light. every city has a
          // picture element of its own: one shared element kept showing the last city's photo until the new one came in.
          // until its photo arrives the frame is plain gray, then the photo fades in; later visits show it at once
          const src = pins[i].dataset.photo;
          slot.hidden = !src;   // a city without a photo shows its name only
          if (src && !shots[i]) {
            const shot = shots[i] = new Image();
            shot.alt = "";
            shot.decoding = "sync";   // a photo already fetched appears in the same frame as its caption
            shot.addEventListener("load", () => shot.classList.add("ready"));
            shot.addEventListener("error", () => { if (shots[i] === shot) shots[i] = null; });   // try again next time
            shot.src = src;
          }
          if (src && slot.firstChild !== shots[i]) { slot.textContent = ""; slot.appendChild(shots[i]); }
          place(i);
          card.classList.add("show");
        }
        function setView(k) {
          view = k;
          const [x, y, w] = views[k], s = W / w;
          land.style.transform = `translate(${-x / W * s * 100}%, ${-y / H * s * 100}%) scale(${s})`;
          pins.forEach((p, i) => { const [l, t] = spot(i); p.style.left = l + "%"; p.style.top = t + "%"; });
          tabs.forEach((b, j) => { b.setAttribute("aria-checked", j === k); b.tabIndex = j === k ? 0 : -1; });
          names.forEach((n, i) => n.classList.toggle("off", !inView(i)));
          box.style.cursor = "";   // the next pointer move sets it again for the new view
          if (active >= 0) { if (inView(active)) place(active); else { pinned = false; hide(); } }
        }
        // a click keeps a city's card open; a city outside the current view brings the whole world back first
        const toggle = i => {
          if (pinned && active === i) { pinned = false; hide(); return; }
          if (!inView(i)) setView(0);
          pinned = true;
          show(i);
        };

        // on the map the dot nearest to the pointer wins, so cities that sit close together can still be told apart
        const coarse = matchMedia("(pointer: coarse)");
        function nearest(e) {
          const reach = coarse.matches ? 24 : 14;
          let best = -1, bestD = reach * reach;
          pins.forEach((pin, i) => {
            if (!inView(i)) return;
            const r = pin.getBoundingClientRect();
            const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
            const d = dx * dx + dy * dy;
            if (d < bestD) { bestD = d; best = i; }
          });
          return best;
        }
        // which region's view holds this point of the world map (0 when none does)
        function regionAt(e) {
          const r = clip.getBoundingClientRect();
          const mx = (e.clientX - r.left) / r.width * W, my = (e.clientY - r.top) / r.height * H;
          const k = views.findIndex((v, j) => j > 0 && mx >= v[0] && mx <= v[0] + v[2] && my >= v[1] && my <= v[1] + v[2] * H / W);
          return Math.max(k, 0);
        }
        box.addEventListener("pointermove", e => {
          if (e.pointerType !== "mouse") return;
          const i = nearest(e);
          box.style.cursor = i >= 0 ? "pointer" : view > 0 ? "zoom-out" : regionAt(e) ? "zoom-in" : "";
          if (pinned) return;
          if (i >= 0) show(i); else hide();
        });
        box.addEventListener("pointerleave", e => { if (e.pointerType === "mouse" && !pinned) hide(); });
        box.addEventListener("click", e => {
          const i = nearest(e);
          if (i >= 0) return toggle(i);
          if (closedByPress) return;          // this press only closed an open card
          if (view > 0) return setView(0);
          const k = regionAt(e);
          if (k) setView(k);
        });
        names.forEach((el, i) => {
          el.addEventListener("pointerenter", e => { if (e.pointerType === "mouse" && !pinned && inView(i)) show(i); });
          el.addEventListener("pointerleave", e => { if (e.pointerType === "mouse" && !pinned) hide(); });
          el.addEventListener("focus", () => { if (!pinned && inView(i) && el.matches(":focus-visible")) show(i); });
          el.addEventListener("blur", () => { if (!pinned) hide(); });
          el.addEventListener("click", () => toggle(i));
        });
        tabs.forEach((b, j) => {
          b.addEventListener("click", () => setView(j));
          b.addEventListener("keydown", e => {
            const d = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
            if (!d) return;
            e.preventDefault();
            const n = (j + d + tabs.length) % tabs.length;
            setView(n);
            tabs[n].focus();
          });
        });
        addEventListener("pointerdown", e => {
          closedByPress = false;
          if (!pinned || e.target.closest(".pname")) return;
          if (!box.contains(e.target) || nearest(e) < 0) { pinned = false; hide(); closedByPress = box.contains(e.target); }
        });
        addEventListener("keydown", e => {
          if (e.key === "Escape" && active >= 0) { pinned = false; hide(); }
        });
      })();

'''


NOTE = "written by _map/build.py from _map/cities.json; what is between this and the END comment is replaced on the next run"
MARKS = {
    "styles": (f"    /* BEGIN map styles, {NOTE} */", "    /* END map styles */"),
    "section": (f"      <!-- BEGIN map section, {NOTE} -->", "      <!-- END map section -->"),
    "script": (f"      // BEGIN map script, {NOTE}", "      // END map script"),
}


def replace(page, key, body):
    """Swap what is between this part's two comments (and bring the BEGIN comment itself up to date)."""
    begin, end = MARKS[key]
    lines = page.split("\n")
    a = [i for i, line in enumerate(lines) if line.startswith(begin.split(",")[0])]
    z = [i for i, line in enumerate(lines) if line == end]
    if len(a) != 1 or len(z) != 1 or a[0] >= z[0]:
        sys.exit(f"{PAGE.relative_to(ROOT)}: the BEGIN/END comments of the map {key} are missing or out of order")
    return "\n".join(lines[: a[0]] + [begin] + body.split("\n") + lines[z[0]:])


def main():
    cities = json.loads(CITIES.read_text(encoding="utf-8"))
    cities.sort(key=lambda c: c["name"].casefold())   # the names under the map run A to Z (the user's choice, 2026-11-16)
    section, info = build_section(cities)             # also writes land-fine.txt and flags/ next to the page
    parts = {"styles": STYLES.strip("\n"), "section": section.rstrip("\n"), "script": SCRIPT.rstrip("\n")}
    old = PAGE.read_text(encoding="utf-8")
    page = old
    for key, body in parts.items():
        page = replace(page, key, body)
    if page != old:
        PAGE.write_text(page, encoding="utf-8")
    flags = page.count(' data-flag="')
    print(f'{PAGE.relative_to(ROOT)}: {"updated" if page != old else "no change"} | {len(cities)} cities | views: {info["views"]}')
    print(f'light outline: {info["coarse"]} | detailed: {info["fine"]} | cities with a flag: {flags}')


if __name__ == "__main__":
    main()
