#!/usr/bin/env python3
"""
Português SP immersion builder.

Reads packs/week-XX.json and produces, in docs/:
  audio/   Scene episodes, a Drill episode and a Weekly Mix per week (MP3)
  decks/   One Anki deck per week (.apkg, audio included)
  feed.xml A private podcast feed for your phone
  index.html  A simple page with the feed link and deck downloads

Only weeks that haven't been built yet are processed (set FORCE=1 to rebuild all).
DRY_RUN=1 replaces text-to-speech with beeps, for testing without internet.
"""
import asyncio, hashlib, json, os, re, shutil, sys, time, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydub import AudioSegment
import genanki
from feedgen.feed import FeedGenerator

ROOT = Path(__file__).parent
PACKS, DOCS = ROOT / "packs", ROOT / "docs"
AUDIO, DECKS = DOCS / "audio", DOCS / "decks"
CACHE, MEDIA = ROOT / ".tts_cache", ROOT / ".anki_media"
DRY = os.getenv("DRY_RUN") == "1"
FORCE = os.getenv("FORCE") == "1" or "--force" in sys.argv

# ---- Voices (edge-tts). One voice per character; pitch shifts separate characters sharing a voice.
VOICES = {
    "george":   ("pt-BR-AntonioNeural",   "+0Hz"),
    "gabi":     ("pt-BR-FranciscaNeural", "+0Hz"),
    "gabriela": ("pt-BR-FranciscaNeural", "+0Hz"),
    "mãe":      ("pt-BR-ThalitaNeural",   "+0Hz"),
    "mae":      ("pt-BR-ThalitaNeural",   "+0Hz"),
    "pai":      ("pt-BR-AntonioNeural",   "-12Hz"),
    "irmão":    ("pt-BR-AntonioNeural",   "+10Hz"),
    "irmao":    ("pt-BR-AntonioNeural",   "+10Hz"),
    "narrador": ("pt-BR-FranciscaNeural", "+0Hz"),
}
EXTRA = [("pt-BR-FranciscaNeural", "-8Hz"), ("pt-BR-AntonioNeural", "+5Hz"), ("pt-BR-ThalitaNeural", "+8Hz")]
SAFE_FALLBACK = {"F": "pt-BR-FranciscaNeural", "M": "pt-BR-AntonioNeural"}
EN_VOICE = ("en-GB-RyanNeural", "+0Hz")
SLOW = "-25%"
_extra_map = {}


def voice_for(speaker):
    key = speaker.strip().lower()
    if key in VOICES:
        return VOICES[key]
    if key not in _extra_map:
        _extra_map[key] = EXTRA[len(_extra_map) % len(EXTRA)]
    return _extra_map[key]


# ---- Text-to-speech with a disk cache -------------------------------------------------
async def _edge(text, voice, rate, pitch, out):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(out))


def tts_path(text, voice, pitch="+0Hz", rate="+0%"):
    key = hashlib.sha1(f"{text}|{voice}|{rate}|{pitch}".encode()).hexdigest()[:16]
    path = CACHE / f"ptsp_{key}.mp3"
    if path.exists() and path.stat().st_size > 0:
        return path
    CACHE.mkdir(exist_ok=True)
    if DRY:
        from pydub.generators import Sine
        dur = 400 + 55 * len(text) * (1.3 if rate == SLOW else 1)
        Sine(330 if voice.startswith("en") else 520).to_audio_segment(duration=dur).apply_gain(-18).export(path, format="mp3")
        return path
    v, last = voice, None
    for attempt in range(4):
        try:
            asyncio.run(_edge(text, v, rate, pitch, path))
            if path.exists() and path.stat().st_size > 0:
                return path
        except Exception as e:  # network hiccup or voice not available
            last = e
        if attempt == 1 and v.startswith("pt-BR") and v not in SAFE_FALLBACK.values():
            v = SAFE_FALLBACK["F"]  # e.g. a voice Microsoft removed
        time.sleep(2 + attempt * 2)
    raise RuntimeError(f"TTS failed for {text!r} ({voice}): {last}")


def tts(*a, **k):
    return AudioSegment.from_file(tts_path(*a, **k))


def sil(ms):
    return AudioSegment.silent(duration=int(ms))


def en(text):
    return tts(text, *EN_VOICE)


def line_audio(line, rate="+0%"):
    v, p = voice_for(line["speaker"])
    return tts(line["pt"], v, p, rate)


# ---- Validation -------------------------------------------------------------------------
def validate(pack, name):
    errs = []
    if not isinstance(pack.get("week"), int):
        errs.append('"week" must be a number')
    for i, s in enumerate(pack.get("scenes", [])):
        for f in ("title", "lines"):
            if f not in s:
                errs.append(f"scene {i+1}: missing {f!r}")
        for j, l in enumerate(s.get("lines", [])):
            for f in ("speaker", "pt", "en"):
                if not l.get(f):
                    errs.append(f"scene {i+1} line {j+1}: missing {f!r}")
        for j, c in enumerate(s.get("chunks", [])):
            for f in ("pt", "en"):
                if not c.get(f):
                    errs.append(f"scene {i+1} chunk {j+1}: missing {f!r}")
    for j, d in enumerate(pack.get("drills", [])):
        if not d.get("en") or not d.get("pt"):
            errs.append(f"drill {j+1}: needs 'en' and 'pt'")
    if errs:
        sys.exit(f"\n❌ {name} has problems:\n  - " + "\n  - ".join(errs))


def slug(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:40]


# ---- Episodes ---------------------------------------------------------------------------
def scene_episode(scene, num):
    lines = scene["lines"]
    full = sum((line_audio(l) + sil(450) for l in lines), sil(0))
    ep = en(f"Scene {num}. {scene['title']}.") + sil(900)
    ep += en("First, just listen.") + sil(500) + full + sil(1200)
    ep += en("Again. Follow the transcript.") + sil(500) + full + sil(1500)
    ep += en("Now shadow. Each line slow, then normal speed. Repeat in the gap.") + sil(900)
    for l in lines:
        s, n = line_audio(l, SLOW), line_audio(l)
        ep += s + sil(len(s) * 1.1 + 500) + n + sil(len(n) * 1.1 + 600)
    ep += sil(800) + en("Last time. Full speed, no transcript.") + sil(600) + full
    return ep


def drill_episode(pack):
    g = VOICES["george"]
    ep = en(f"Week {pack['week']} drills. Say the Portuguese before you hear it.") + sil(1000)
    for d in pack["drills"]:
        ep += en(d["en"]) + sil(3200 + 25 * len(d["pt"])) + tts(d["pt"], *g) + sil(1000) + tts(d["pt"], *g) + sil(1600)
    return ep


def mix_episode(pack):
    ep = en(f"Week {pack['week']} mix. All scenes, full speed.") + sil(900)
    for i, s in enumerate(pack["scenes"]):
        ep += en(s["title"]) + sil(600) + sum((line_audio(l) + sil(400) for l in s["lines"]), sil(0)) + sil(1500)
    return ep


def export(seg, path, title):
    seg.set_channels(1).export(path, format="mp3", bitrate="64k", tags={"title": title, "album": "Português SP"})


# ---- Anki -------------------------------------------------------------------------------
CSS = """.card{font-family:Arial,sans-serif;font-size:22px;text-align:center;color:#222;background:#fff}
.pt{font-size:28px;font-weight:bold;margin:10px}.heard{color:#7a4bb3;font-style:italic;margin:6px}
.en{font-size:22px;margin:8px}.note{font-size:16px;color:#666;margin-top:12px}.hint{font-size:15px;color:#999;margin-top:14px}
.nightMode .card,.night_mode .card{background:#1e1e1e;color:#eee}.nightMode .heard{color:#c9a7f0}"""
MODEL = genanki.Model(
    1607392319, "PT-SP Listen + Say",
    fields=[{"name": n} for n in ("PT", "Heard", "EN", "Note", "Audio", "AudioSlow", "SayEN")],
    templates=[
        {"name": "1 Listen",
         "qfmt": '{{Audio}}<div class="hint">🎧 What does this mean?</div>',
         "afmt": '{{FrontSide}}<hr id="answer"><div class="pt">{{PT}}</div><div class="heard">{{Heard}}</div>'
                 '<div class="en">{{EN}}</div><div class="note">{{Note}}</div>{{AudioSlow}}'},
        {"name": "2 Say it",
         "qfmt": '{{#SayEN}}<div class="en">{{SayEN}}</div><div class="hint">🗣️ Say it out loud first</div>{{/SayEN}}',
         "afmt": '{{FrontSide}}<hr id="answer"><div class="pt">{{PT}}</div><div class="heard">{{Heard}}</div>'
                 '{{Audio}}<div class="note">{{Note}}</div>'},
    ],
    css=CSS,
)


class StableNote(genanki.Note):
    @property
    def guid(self):
        return genanki.guid_for(self.fields[0], self.fields[6] != "")


def build_deck(pack, out_path):
    w = pack["week"]
    deck = genanki.Deck(2059400110 + w, f"Português SP::Week {w:02d}")
    MEDIA.mkdir(exist_ok=True)
    media, seen = [], set()

    def add(pt, heard, en_, note, speaker, production):
        if pt in seen and not production:
            return
        seen.add(pt)
        v, p = voice_for(speaker)
        a, s = tts_path(pt, v, p), tts_path(pt, v, p, SLOW)
        for f in (a, s):
            dst = MEDIA / f.name
            if not dst.exists():
                shutil.copy(f, dst)
            media.append(str(dst))
        deck.add_note(StableNote(model=MODEL, tags=[f"week{w:02d}"], fields=[
            pt, heard or "", en_, note or "", f"[sound:{a.name}]", f"[sound:{s.name}]", en_ if production else ""]))

    for s in pack["scenes"]:
        for c in s.get("chunks", []):
            add(c["pt"], c.get("heard"), c["en"], c.get("note"), "george", True)
        for l in s["lines"]:
            add(l["pt"], l.get("heard"), l["en"], f"{s['title']} — {l['speaker']}", l["speaker"], False)
    pkg = genanki.Package(deck)
    pkg.media_files = sorted(set(media))
    pkg.write_to_file(out_path)
    return len(deck.notes)


# ---- Transcripts ---------------------------------------------------------------------
TCSS = """:root{--bg:#fff;--fg:#1b1b1b;--muted:#666;--heard:#7a4bb3;--card:#f5f5f7;--line:#e2e2e2}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#eee;--muted:#aaa;--heard:#c9a7f0;--card:#1e1e1e;--line:#333}}
body{font-family:Arial,sans-serif;background:var(--bg);color:var(--fg);max-width:720px;margin:0 auto;padding:1em;line-height:1.45}
h2{margin-top:1.6em;border-bottom:2px solid var(--line);padding-bottom:.2em}.ln{background:var(--card);border-radius:10px;padding:.6em .8em;margin:.5em 0}
.sp{font-size:.8em;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}.pt{font-size:1.15em;font-weight:bold}
.heard{color:var(--heard);font-style:italic}.en{color:var(--muted)}a{color:var(--heard)}
details{margin:.4em 0}summary{cursor:pointer;color:var(--muted)}"""


def esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_transcript(pack):
    w = pack["week"]
    (DOCS / "transcripts").mkdir(exist_ok=True)
    eps = episodes_for(pack)
    body = [f'<p><a href="../index.html">← All weeks</a></p><h1>Week {w:02d} transcripts</h1>'
            '<p class="en">Purple = how it actually sounds. Tap "English" to check meaning.</p>']
    for i, s in enumerate(pack["scenes"]):
        body.append(f'<h2 id="s{i+1}">Scene {i+1}: {esc(s["title"])}</h2>'
                    f'<p><a href="../audio/{eps[i][0]}">▶ Play episode</a></p>')
        for l in s["lines"]:
            body.append(f'<div class="ln"><div class="sp">{esc(l["speaker"])}</div><div class="pt">{esc(l["pt"])}</div>'
                        f'<div class="heard">{esc(l.get("heard"))}</div>'
                        f'<details><summary>English</summary><div class="en">{esc(l["en"])}</div></details></div>')
        if s.get("chunks"):
            body.append("<h3>Key phrases</h3><ul>" + "".join(
                f'<li><b>{esc(c["pt"])}</b> <span class="heard">({esc(c.get("heard"))})</span> = {esc(c["en"])}</li>'
                for c in s["chunks"]) + "</ul>")
    if pack.get("drills"):
        body.append('<h2>Drills</h2><details><summary>Show all answers</summary><ol>' + "".join(
            f'<li>{esc(d["en"])} → <b>{esc(d["pt"])}</b></li>' for d in pack["drills"]) + "</ol></details>")
    (DOCS / "transcripts" / f"week-{w:02d}.html").write_text(
        f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>Week {w:02d}</title><style>{TCSS}</style>' + "".join(body), encoding="utf-8")


# ---- Feed + index -----------------------------------------------------------------------
def base_url():
    if os.getenv("PAGES_URL"):
        return os.getenv("PAGES_URL").rstrip("/") + "/"
    repo = os.getenv("GITHUB_REPOSITORY")
    if repo:
        owner, name = repo.split("/")
        return f"https://{owner.lower()}.github.io/{name}/"
    return "http://localhost:8000/"


def episodes_for(pack):
    w = pack["week"]
    eps = [(f"w{w:02d}-s{i+1}-{slug(s['title'])}.mp3", f"W{w:02d} · Scene {i+1}: {s['title']}")
           for i, s in enumerate(pack["scenes"])]
    if pack.get("drills"):
        eps.append((f"w{w:02d}-drills.mp3", f"W{w:02d} · Drills (gym)"))
    if len(pack["scenes"]) > 1:
        eps.append((f"w{w:02d}-mix.mp3", f"W{w:02d} · Weekly mix"))
    return eps


def write_feed_and_index(packs):
    url = base_url()
    fg = FeedGenerator()
    fg.load_extension("podcast")
    fg.title("Português SP — George")
    fg.link(href=url, rel="alternate")
    fg.description("Private São Paulo Portuguese immersion feed")
    fg.language("pt-BR")
    fg.podcast.itunes_category("Education", "Language Learning")
    fg.podcast.itunes_block(True)
    fg.podcast.itunes_explicit("no")
    now = datetime.now(timezone.utc)
    rows, decks, trans = [], [], []
    for pack in packs:
        w = pack["week"]
        monday = datetime(2026, 10, 19, 6, tzinfo=timezone.utc) + timedelta(days=7 * (w - 1))
        start = min(monday - timedelta(days=2), now - timedelta(hours=1))
        for k, (fname, title) in enumerate(episodes_for(pack)):
            f = AUDIO / fname
            if not f.exists():
                continue
            fe = fg.add_entry()
            fe.id(url + "audio/" + fname)
            fe.title(title)
            fe.description(f"Transcript: {url}transcripts/week-{w:02d}.html")
            fe.enclosure(url + "audio/" + fname, str(f.stat().st_size), "audio/mpeg")
            fe.pubDate(start + timedelta(minutes=k))
            rows.append(f'<li><a href="audio/{fname}">{title}</a></li>')
        write_transcript(pack)
        trans.append(f'<li><a href="transcripts/week-{w:02d}.html">Week {w:02d} transcripts</a></li>')
        d = DECKS / f"week-{w:02d}.apkg"
        if d.exists():
            decks.append(f'<li><a href="decks/{d.name}">Week {w:02d} Anki deck</a></li>')
    fg.rss_file(str(DOCS / "feed.xml"), pretty=True)
    (DOCS / "index.html").write_text(f"""<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Português SP</title>
<style>body{{font-family:Arial,sans-serif;max-width:680px;margin:2em auto;padding:0 1em;line-height:1.5}}
code{{background:#eee;padding:2px 6px;border-radius:4px;word-break:break-all}}</style>
<h1>Português SP 🇧🇷</h1><p>Podcast feed (add this URL in your podcast app):<br><code>{url}feed.xml</code></p>
<h2>📖 Transcripts</h2><ul>{''.join(reversed(trans))}</ul><h2>Anki decks</h2><ul>{''.join(decks)}</ul><h2>Episodes</h2><ul>{''.join(reversed(rows))}</ul>""", encoding="utf-8")
    (DOCS / ".nojekyll").write_text("")


# ---- Main -------------------------------------------------------------------------------
def main():
    AUDIO.mkdir(parents=True, exist_ok=True)
    DECKS.mkdir(parents=True, exist_ok=True)
    packs = []
    for p in sorted(PACKS.glob("*.json")):
        try:
            pack = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.exit(f"\n❌ {p.name} isn't valid JSON: {e}\nTip: make sure you copied Claude's whole reply, from the first {{ to the last }}.")
        validate(pack, p.name)
        packs.append(pack)
    packs.sort(key=lambda x: x["week"])

    for pack in packs:
        w = pack["week"]
        deck_path = DECKS / f"week-{w:02d}.apkg"
        eps = episodes_for(pack)
        if not FORCE and deck_path.exists() and all((AUDIO / f).exists() for f, _ in eps):
            print(f"✓ Week {w:02d} already built — skipping")
            continue
        print(f"▶ Building week {w:02d}")
        for i, s in enumerate(pack["scenes"]):
            fname, title = eps[i]
            export(scene_episode(s, i + 1), AUDIO / fname, title)
            print(f"   🎧 {fname}")
        for fname, title in eps[len(pack["scenes"]):]:
            seg = drill_episode(pack) if fname.endswith("drills.mp3") else mix_episode(pack)
            export(seg, AUDIO / fname, title)
            print(f"   🎧 {fname}")
        n = build_deck(pack, deck_path)
        print(f"   🃏 {deck_path.name} ({n} notes)")

    write_feed_and_index(packs)
    print(f"\n✅ Done. Feed: {base_url()}feed.xml")


if __name__ == "__main__":
    main()
