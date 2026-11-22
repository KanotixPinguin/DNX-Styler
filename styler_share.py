#!/usr/bin/env python3
# DNX Styler - Teilen-Dienst v2
# Speichert eigene Styler-Einstellungen fuer ALLE Besucher dieses OpenWebRX.
# v2: /dnx/styler/std = Startzustand fuer neue Besucher (Wasserfall/Spektrum an-aus,
#     beide Paletten und das Aussehen). Wer selbst etwas einstellt, behaelt seine Wahl.
# Nur Standardbibliothek, keine IPs im Log, keine Schluessel fuer Dritte.
#   Start:  python3 styler_share.py
#   Stop:   pkill -f styler_share.py
#   Test:   curl -s http://127.0.0.1:8098/dnx/styler/state
import argparse, json, math, os, re, sqlite3, sys, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

BASIS = os.environ.get("DNX_SHARE_DIR", os.path.expanduser("~/.dnx"))
DB = os.path.join(BASIS, "styler_share.db")
LOG = os.path.join(BASIS, "styler_share.log")
MAXBODY = 16384
MAXEINTRAEGE = 200

# SSE sendet lediglich "Standard hat sich geaendert"; der Inhalt wird wie
# bisher ueber GET geholt. Lange Verbindungen haben eine feste Obergrenze.
STANDARD_SIGNAL = threading.Condition()
STANDARD_VERSION = 0
STANDARD_STREAMS = threading.BoundedSemaphore(256)


def standard_geaendert():
    global STANDARD_VERSION
    with STANDARD_SIGNAL:
        STANDARD_VERSION += 1
        STANDARD_SIGNAL.notify_all()

FARBE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
GRAD = re.compile(r"^linear-gradient\([0-9a-zA-Z .,%#()\-]{5,400}\)$")
KENNUNG = re.compile(r"^[A-Za-z0-9_:.\-]{1,40}$")
# v6 [S-METER-ALLE]: erlaubte S-Meter-Modelle und LCD-Farben des Stylers.
SM_MODELLE = ("neu", "georg1", "georg2", "alan48")
SM_LCD_FARBEN = ("orange", "gelb", "gruen", "blau", "tuerkis", "rot", "weiss")
SCHLUESSEL = ("name", "preset", "bg", "panel", "accent", "btn", "text", "btntext",
              "radius", "glow", "fx", "sound", "hover", "pitch", "rh", "pal",
              "stan", "stf", "staus", "stx", "sty",
              "mt", "mt_seite", "mt_abstand", "mt_ticks", "mt_schrift", "mt_min", "mt_scroller", "mt_bg", "mt_fg",
              "wf", "fft", "wf_an", "fft_an", "m3d", "m3d_flip")
GRENZEN = {"radius": (0, 40), "glow": (0, 20), "fx": (0, 100), "sound": (0, 100),
           "hover": (0, 100), "pitch": (200, 4000), "rh": (0, 1),
           "stan": (0, 1), "stf": (0, 1), "staus": (0, 1), "stx": (-4000, 4000), "sty": (-3000, 3000),
           "mt": (0, 1), "mt_seite": (0, 1), "mt_abstand": (1, 60), "mt_ticks": (0, 1),
           "mt_schrift": (10, 18), "mt_min": (0, 720), "mt_scroller": (0, 1), "mt_bg": (0, 100), "mt_fg": (0, 100),
           "wf_an": (0, 1), "fft_an": (0, 1), "m3d_flip": (0, 1)}


def jetzt():
    return time.strftime("%Y-%m-%d %H:%M")


def jetzt_standard():
    # Jeder Speichervorgang ist eine neue Revision, selbst wenn zweimal in
    # derselben Minute dieselben Werte veroeffentlicht werden. Andere Clients
    # erkennen so den neuen Standard ohne sich gegenseitig zu ueberschreiben.
    ns = time.time_ns()
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ns // 1_000_000_000)) + ".%09d" % (ns % 1_000_000_000)


def log(*teile):
    try:
        os.makedirs(BASIS, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(str(t) for t in teile)))
    except Exception:
        pass


def text(s, n):
    s = "" if s is None else str(s)
    s = re.sub(r"[^A-Za-z0-9 _.,:#()\-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()[:n]


def saeubern(roh):
    """Nur bekannte Felder, nur harmlose Werte - nichts wird ungeprueft gespeichert."""
    if not isinstance(roh, dict):
        return {}
    o = {}
    schluessel = list(SCHLUESSEL) + [x for x in roh.keys()
                                     if isinstance(x, str) and re.match(r"^t_[a-z0-9_]{1,20}$", x)]
    for k in schluessel:
        if k not in roh:
            continue
        v = roh[k]
        if isinstance(v, bool):
            v = int(v)
        if isinstance(v, int) or (isinstance(v, float) and v == int(v)):
            n = int(v)
            if k in GRENZEN:
                lo, hi = GRENZEN[k]
                n = max(lo, min(hi, n))
            o[k] = n
            continue
        v = str(v)
        if k in ("name", "preset"):
            t = text(v, 28)
            if t:
                o[k] = t
        elif k in ("wf", "fft") and KENNUNG.match(v):
            o[k] = v
        elif k == "m3d" and v in ("std", "3d", "both"):
            o[k] = v
        elif k.startswith("t_") and len(k) <= 24 and re.match(r"^t_[a-z0-9_]+$", k):
            o[k] = v
        elif FARBE.match(v):
            o[k] = v.lower()
        elif k == "pal" and GRAD.match(v):
            o[k] = v
    return o


def saeubern_std(roh):
    """Nur der Anzeige-Zustand: Paletten-Kennungen, an/aus und das Aussehen."""
    if not isinstance(roh, dict):
        return {}
    o = {}
    for k in ("wf", "fft"):
        v = roh.get(k)
        if isinstance(v, str) and KENNUNG.match(v):
            o[k] = v
    for k in ("wf_an", "fft_an"):
        v = roh.get(k)
        if isinstance(v, bool):
            o[k] = 1 if v else 0
        elif isinstance(v, int) and v in (0, 1):
            o[k] = v
    # v3: 3D-Wasserfall-Ansicht (2D / 3D / beide) mit weiterreichen,
    # damit neue Besucher sehen, dass etwas in 3D laeuft.
    m = roh.get("m3d")
    if isinstance(m, str) and m in ("std", "3d", "both"):
        o["m3d"] = m
    f = roh.get("m3d_flip")
    if isinstance(f, bool):
        o["m3d_flip"] = 1 if f else 0
    elif isinstance(f, int) and f in (0, 1):
        o["m3d_flip"] = f
    tools = roh.get("tools")
    if isinstance(tools, dict):
        tt = {}
        for k, v in tools.items():
            if not isinstance(k, str) or not re.match(r"^t_[a-z0-9_]{1,20}$", k):
                continue
            if isinstance(v, bool):
                tt[k] = 1 if v else 0
            elif isinstance(v, int) and v in (0, 1):
                tt[k] = v
            if len(tt) >= 40:
                break
        if tt:
            o["tools"] = tt
    # v4: Farben & Hintergruende - Wasserfall (2D), 3D-Wasserfall, Spektrum
    #     samt Hintergruenden und die beiden roten Ziehlinien.
    f = roh.get("farben")
    if isinstance(f, dict):
        ff = {}
        for k in ("wf", "cmap3d", "bg3d", "pal", "hg"):
            v = f.get(k)
            if isinstance(v, str) and (KENNUNG.match(v[:40]) or FARBE.match(v[:40])):
                ff[k] = v[:40]
        lf = f.get("linieFarbe")
        if isinstance(lf, str) and FARBE.match(lf):
            ff["linieFarbe"] = lf.lower()
        for k, lo, hi in (("linieDicke", 1, 8), ("fftH", 0, 800), ("topH", 0, 4000)):
            v = f.get(k)
            if isinstance(v, bool):
                continue
            if isinstance(v, int) or (isinstance(v, float) and v == int(v)):
                ff[k] = max(lo, min(hi, int(v)))
        if ff:
            o["farben"] = ff
    s = saeubern(roh.get("skin"))
    if s.get("accent"):
        o["skin"] = s
    eff = roh.get("effekte")
    if isinstance(eff, dict):
        ee = {}
        if eff.get("pfx") in ("keiner", "puls", "atmen", "blink", "strobe", "flacker",
                              "regenbogen", "farbe", "neon", "laufband", "ledlauf", "zittern", "pumpen", "herz", "blitz"):
            ee["pfx"] = eff["pfx"]
        if eff.get("smeter") in ("standard", "lauf", "farbstat", "leddb", "leds"):
            ee["smeter"] = eff["smeter"]
        # v6 [S-METER-ALLE]: S-Meter-Modell und LCD-Farbe mitnehmen, sonst
        #     kommt "S-Meter fuer alle uebernehmen" nie bei den anderen an.
        if eff.get("sm_modell") in SM_MODELLE:
            ee["sm_modell"] = eff["sm_modell"]
        if eff.get("sm_lcd") in SM_LCD_FARBEN:
            ee["sm_lcd"] = eff["sm_lcd"]
        if ee:
            o["effekte"] = ee
    seiten = roh.get("seiten")
    if isinstance(seiten, dict):
        ss = {k: seiten[k] for k in ("zeitachse", "pegel", "dmr") if seiten.get(k) in ("L", "R")}
        if ss:
            o["seiten"] = ss
    # Weitere Spektrum-Regler. Die Hoehe bleibt ausschliesslich fftH, damit
    # ein alter Spektrum-Regler die untere rote Linie nicht zurueckstellt.
    # v5: Pegel-Block (Offset / Range / Kontrast / Automatik) [DNX-PEGEL-1]
    pegel = roh.get("pegel")
    if isinstance(pegel, dict):
        pg = {}
        for k, lo, hi in (("boden", -150.0, 10.0), ("deckel", -140.0, 30.0), ("kontrast", 0.0, 100.0), ("offset", -12.0, 52.0), ("range", -60.0, 60.0)):
            v = pegel.get(k)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                continue
            pg[k] = max(lo, min(hi, float(v)))
        if "boden" in pg and "deckel" in pg and pg["deckel"] < pg["boden"] + 4.0:
            pg["deckel"] = min(30.0, pg["boden"] + 4.0)
        a = pegel.get("autoFit")
        if isinstance(a, bool):
            pg["autoFit"] = 1 if a else 0
        elif isinstance(a, int) and a in (0, 1):
            pg["autoFit"] = a
        # Abweichungen je Profil: Kennung -> eigener Satz
        pr = pegel.get("profile")
        if isinstance(pr, dict):
            pgs = {}
            for name, satz in pr.items():
                if not isinstance(name, str) or not re.match(r"^[A-Za-z0-9_.\-| ]{1,60}$", name):
                    continue
                if not isinstance(satz, dict):
                    continue
                ein = {}
                for k, lo, hi in (("boden", -150.0, 10.0), ("deckel", -140.0, 30.0), ("kontrast", 0.0, 100.0), ("offset", -12.0, 52.0), ("range", -60.0, 60.0)):
                    v = satz.get(k)
                    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                        continue
                    ein[k] = max(lo, min(hi, float(v)))
                if "boden" in ein and "deckel" in ein and ein["deckel"] < ein["boden"] + 4.0:
                    ein["deckel"] = min(30.0, ein["boden"] + 4.0)
                aa = satz.get("autoFit")
                if isinstance(aa, bool):
                    ein["autoFit"] = 1 if aa else 0
                elif isinstance(aa, int) and aa in (0, 1):
                    ein["autoFit"] = aa
                if ein:
                    pgs[name[:60]] = ein
                if len(pgs) >= 300:
                    break
            if pgs:
                pg["profile"] = pgs
        if pg:
            o["pegel"] = pg
    spektrum = roh.get("spektrum")
    if isinstance(spektrum, dict):
        grenzen = {"hell": (40, 200), "kont": (40, 220), "saett": (0, 250),
                   "hue": (-180, 180), "weich": (0, 6), "deck": (20, 100)}
        sp = {}
        for k, (lo, hi) in grenzen.items():
            v = spektrum.get(k)
            if not isinstance(v, bool) and isinstance(v, (int, float)) and (isinstance(v, int) or math.isfinite(v)):
                sp[k] = max(lo, min(hi, v))
        if sp:
            o["spektrum"] = sp
    return o


def std_lesen(c):
    r = c.execute("select ts, author, view from standard where id = 1").fetchone()
    if not r:
        return None
    try:
        v = json.loads(r[2])
    except Exception:
        v = {}
    return {"ts": r[0], "author": r[1], "view": v}


def db():
    os.makedirs(BASIS, exist_ok=True)
    c = sqlite3.connect(DB, timeout=5)
    c.execute("create table if not exists skins(id integer primary key autoincrement,"
              " name text not null, author text not null default '', ts text not null,"
              " token text not null, skin text not null)")
    c.execute("create table if not exists standard(id integer primary key check (id = 1),"
              " ts text not null, author text not null default '', token text not null,"
              " view text not null)")
    c.commit()
    return c


def zahlen(c):
    n, u = c.execute("select count(*), count(distinct author) from skins where author <> ''").fetchone()
    n2 = c.execute("select count(*) from skins").fetchone()[0]
    return int(n2), int(u)


def kurze_liste(c):
    r = c.execute("select id, name, author, ts from skins order by id desc limit 200").fetchall()
    return [{"id": int(a), "name": a2, "author": b, "ts": t} for a, a2, b, t in r]


class H(BaseHTTPRequestHandler):
    server_version = "dnx-styler-share/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        log("HTTP", fmt % args)          # bewusst ohne IP-Adresse

    def kopf(self, code=200, art="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", art)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")

    def senden(self, code, obj):
        b = obj if isinstance(obj, (bytes, bytearray)) else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.kopf(code, "text/html; charset=utf-8" if isinstance(obj, (bytes, bytearray)) else "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def koerper(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = 0
        if n <= 0 or n > MAXBODY:
            return None
        try:
            return json.loads(self.rfile.read(n).decode("utf-8", "replace"))
        except Exception:
            return None

    def do_OPTIONS(self):
        self.kopf(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def standard_stream(self):
        if not STANDARD_STREAMS.acquire(blocking=False):
            self.kopf(503)
            self.send_header("Retry-After", "30")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.close_connection = True
        try:
            self.connection.settimeout(10)
            self.kopf(200, "text/event-stream; charset=utf-8")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            with STANDARD_SIGNAL:
                zuletzt = STANDARD_VERSION
            self.wfile.write(b"retry: 3000\n: verbunden\n\n")
            self.wfile.flush()
            while True:
                with STANDARD_SIGNAL:
                    if zuletzt == STANDARD_VERSION:
                        STANDARD_SIGNAL.wait(timeout=10)
                    neu = STANDARD_VERSION
                if neu != zuletzt:
                    zuletzt = neu
                    data = ("event: standard\ndata: %d\n\n" % neu).encode("ascii")
                else:
                    data = b": keepalive\n\n"
                self.wfile.write(data)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            pass
        finally:
            STANDARD_STREAMS.release()

    def do_GET(self):
        u = urlsplit(self.path)
        p = u.path.rstrip("/") or "/"
        if p == "/dnx/styler/events":
            self.standard_stream()
            return
        if p == "/":
            c = db()
            n, m = zahlen(c)
            zeilen = "".join("<tr><td>%d</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                             % (e["id"], e["name"], e["author"] or "-", e["ts"]) for e in kurze_liste(c))
            c.close()
            html = ("<!doctype html><html lang='de'><meta charset='utf-8'><title>DNX Styler - Teilen</title>"
                    "<body style='background:#06130b;color:#e8f5ec;font:14px system-ui;padding:18px'>"
                    "<h2>DNX Styler - Teilen-Dienst</h2>"
                    "<p>Gespeicherte Einstellungen: <b>%d</b> (von %d Besuchern). "
                    "Dieser Dienst gehoert zum DNX Styler im OpenWebRX.</p>"
                    "<table style='border-collapse:collapse'><tr><th style='padding:4px 12px 4px 0'>Nr</th>"
                    "<th style='padding:4px 12px 4px 0'>Name</th><th style='padding:4px 12px 4px 0'>Besucher</th>"
                    "<th style='padding:4px 12px 4px 0'>Zeit</th></tr>%s</table>"
                    "<p style='color:#9fb8a8'>Schnittstelle: /dnx/styler/state, /dnx/styler/get?id=, "
                    "/dnx/styler/save (POST), /dnx/styler/del (POST), "
                    "/dnx/styler/std (GET/POST = Startzustand fuer alle)</p></body></html>" % (n, m, zeilen))
            self.senden(200, html.encode("utf-8"))
            return
        if p == "/dnx/styler/state":
            c = db()
            n, m = zahlen(c)
            l = kurze_liste(c)
            hatstd = std_lesen(c) is not None
            c.close()
            self.senden(200, {"ok": True, "count": n, "users": m, "list": l, "std": hatstd})
            return
        if p == "/dnx/styler/std":
            c = db()
            s = std_lesen(c)
            c.close()
            if not s:
                self.senden(200, {"ok": True, "std": None})
                return
            c2 = db()
            try:
                tr = c2.execute("select token from standard where id = 1").fetchone()
                tok = tr[0] if tr and tr[0] else ""
            except Exception:
                tok = ""
            finally:
                c2.close()
            self.senden(200, {"ok": True, "std": s["view"], "ts": s["ts"],
                              "author": s["author"], "token": tok})
            return
        if p == "/dnx/styler/get":
            q = parse_qs(u.query)
            try:
                i = int((q.get("id") or ["0"])[0])
            except Exception:
                i = 0
            c = db()
            r = c.execute("select id, name, author, ts, skin from skins where id = ?", (i,)).fetchone()
            c.close()
            if not r:
                self.senden(404, {"ok": False, "error": "unbekannte Nummer"})
                return
            self.senden(200, {"ok": True, "id": int(r[0]), "name": r[1], "author": r[2], "ts": r[3],
                              "skin": saeubern(json.loads(r[4]))})
            return
        self.senden(404, {"ok": False, "error": "unbekannter Pfad"})

    def do_POST(self):
        p = urlsplit(self.path).path.rstrip("/")
        d = self.koerper()
        if d is None:
            self.senden(400, {"ok": False, "error": "leere oder zu grosse Anfrage"})
            return
        if p == "/dnx/styler/save":
            skin = saeubern(d.get("skin"))
            name = text(d.get("name"), 28) or "Einstellung"
            autor = text(d.get("author"), 24)
            if not skin.get("accent"):
                self.senden(400, {"ok": False, "error": "Einstellung ohne Farbe"})
                return
            import secrets
            tok = secrets.token_hex(8)
            c = db()
            c.execute("insert into skins(name, author, ts, token, skin) values(?,?,?,?,?)",
                      (name, autor, jetzt(), tok, json.dumps(skin, ensure_ascii=False)))
            c.execute("delete from skins where id not in (select id from skins order by id desc limit ?)", (MAXEINTRAEGE,))
            c.commit()
            n, m = zahlen(c)
            l = kurze_liste(c)
            i = c.execute("select max(id) from skins").fetchone()[0]
            c.close()
            log("save", name, autor or "-")
            self.senden(200, {"ok": True, "id": int(i), "token": tok, "count": n, "users": m, "list": l})
            return
        if p == "/dnx/styler/del":
            try:
                i = int(d.get("id") or 0)
            except Exception:
                i = 0
            tok = str(d.get("token") or "")
            autor_del = text(d.get("author"), 24)
            c = db()
            if tok:
                c.execute("delete from skins where id = ? and token = ?", (i, tok))
            elif autor_del:
                c.execute("delete from skins where id = ? and author = ?", (i, autor_del))
            else:
                c.execute("delete from skins where id = ?", (i,))
            c.commit()
            n, m = zahlen(c)
            l = kurze_liste(c)
            c.close()
            log("del", i)
            self.senden(200, {"ok": True, "count": n, "users": m, "list": l})
            return
        if p == "/dnx/styler/std":
            view = saeubern_std(d.get("view"))
            autor = text(d.get("author"), 24)
            tok = text(d.get("token"), 32)
            if not view:
                self.senden(400, {"ok": False, "error": "Standard ohne Inhalt"})
                return
            import secrets
            c = db()
            r = c.execute("select token from standard where id = 1").fetchone()
            # Kein Token-Zwang mehr: der Standard darf jederzeit neu gesetzt werden.
            c.close()
            c = db()
            r = c.execute("select token from standard where id = 1").fetchone()
            revision = jetzt_standard()
            if r:
                c.execute("update standard set ts = ?, author = ?, view = ? where id = 1",
                          (revision, autor, json.dumps(view, ensure_ascii=False)))
                neu = r[0]
            else:
                neu = secrets.token_hex(8)
                c.execute("insert into standard(id, ts, author, token, view) values(1, ?, ?, ?, ?)",
                          (revision, autor, neu, json.dumps(view, ensure_ascii=False)))
            c.commit()
            c.close()
            # Erst nach erfolgreichem Commit veroeffentlichen.
            standard_geaendert()
            log("standard", autor or "-")
            # Der Sender merkt die gespeicherte Revision vor, ohne seine gerade
            # eingestellte Ansicht durch die eigene Veroeffentlichung zu resetten.
            self.senden(200, {"ok": True, "token": neu, "ts": revision, "std": view})
            return
        self.senden(404, {"ok": False, "error": "unbekannter Pfad"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8098)
    ap.add_argument("--daemon", action="store_true", help="im Hintergrund weiterlaufen")
    ap.add_argument("--std-reset", action="store_true", help="Standard fuer alle loeschen (Notfall)")
    a = ap.parse_args()
    if a.std_reset:
        c = db()
        c.execute("delete from standard where id = 1")
        c.commit()
        c.close()
        print("Standard fuer alle geloescht.")
        sys.exit(0)
    if a.daemon:
        pid = os.fork()
        if pid > 0:
            print("DNX Styler Teilen-Dienst gestartet (PID %d)" % pid)
            sys.exit(0)
        os.setsid()
        null = os.open(os.devnull, os.O_RDONLY)
        os.dup2(null, 0)
        aus = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        os.dup2(aus, 1)
        os.dup2(aus, 2)
        os.makedirs(BASIS, exist_ok=True)
    db().close()
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print("DNX Styler Teilen-Dienst laeuft auf http://%s:%d" % (a.host, a.port))
    print("Datenbank:", DB)
    print("Beenden mit Strg+C oder: pkill -f styler_share.py")
    log("start", "port", a.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
