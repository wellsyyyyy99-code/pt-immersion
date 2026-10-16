# Português SP: your immersion machine 🇧🇷

**What this does:** every Sunday you paste one block of text into GitHub. About 5 minutes later, a robot has turned it into:

- 🎧 **Podcast episodes** on your phone: 4 scene episodes for the train, a drill episode for the gym, and a weekly mix.
- 🃏 **An Anki flashcard deck** with native-sounding audio. About 80 cards a week, which is 20 a day Mon–Thu.

Week 1 and a "sound rules" pack are **already included**, so you can start on Monday.

Total setup: about 45 minutes, once. After that, about 15 minutes every Sunday.

---

## Part A: Put it on GitHub (about 20 min, once)

1. **Make a free account** at github.com.
2. Click **+ → New repository**. Name it `pt-immersion`, choose **Public**, and click **Create repository**.
   *(It has to be public for the free podcast hosting. It only contains study audio.)*
3. On the empty repo page, click **"uploading an existing file"**. Unzip the folder I gave you and drag **everything inside it** into the browser window, then click **Commit changes**.
4. **Check the robot file uploaded.** You should see a `.github` folder in the file list. If you don't (Macs hide folders starting with a dot):
   - Click **Add file → Create new file**
   - In the name box, type: `.github/workflows/build.yml`
   - Open `workflow-copy.yml`, copy everything, paste it in, then click **Commit changes**.
5. **Turn on the free hosting:** go to **Settings → Pages**. Under "Source", choose **GitHub Actions**.
6. **Run it for the first time:** go to the **Actions** tab, click **Build immersion pack** on the left, then **Run workflow → Run workflow**.
   Wait about 5–8 minutes for a ✅ green tick.
7. **Open your page:** `https://YOUR-USERNAME.github.io/pt-immersion/`
   It shows your **podcast feed link** and your **Anki deck downloads**. Bookmark it.

> ❌ **Red X instead?** Click the failed run and look for the line starting with ❌. Common fixes:
> - It fails at "Save built files": go to **Settings → Actions → General → Workflow permissions**, choose **Read and write**, save, and run again.
> - It fails at "Build audio": the voice service hiccupped. Just run it again.

---

## Part B: Phone podcast app (5 min, once)

Copy the feed link from your page (it ends in `/feed.xml`).

- **Android: AntennaPod** (free): tap **+ → Add podcast by RSS address** and paste the link.
- **iPhone: Apple Podcasts**: **Library → ⋯ (top right) → Follow a Show by URL**. Or use **Pocket Casts**: **Search** and paste the link.

Then, in the show's settings:

- **Sort: oldest first**, so the scenes play in order.
- **Auto-download: ON**, so episodes are on your phone before the train. The signal is patchy, but downloads work offline.

New episodes appear by themselves every week.

---

## Part C: Anki flashcards (15 min, once)

1. Install **Anki** on your computer (free, from apps.ankiweb.net) and make a free **AnkiWeb** account for syncing.
2. On your phone: **AnkiDroid** (free) on Android. On iPhone, AnkiMobile is paid, but the free option is reviewing in your browser at **ankiweb.net**.
3. Download `week-00.apkg` and `week-01.apkg` from your page. In Anki desktop, go to **File → Import**. Then click **Sync**.
4. **One-time settings:** click the ⚙️ next to "Português SP", then **Options**:
   - Turn on **FSRS**, the smart scheduler, and set **Desired retention: 0.90**.
   - **New cards/day: 20**. **Maximum reviews/day: 300**.

**Two card types:**

- 🎧 **Listen:** you hear the audio and work out what it means. The back shows the spelling, the purple "as-heard" spelling, and the English.
- 🗣️ **Say it:** you see the English and **say the Portuguese out loud** before flipping.

---

## Part D: Every Sunday (about 15 min)

1. **Claude:** make a Project called **Portuguese Coach** (one time). Paste everything from `prompts/master_prompt.txt` into the Project's instructions. Each Sunday, open it and send:

   > Generate week 2. My mistake log this week: [paste]. Gabriela's notes: [paste].

   Claude replies with a block of JSON (text starting with `{`).
2. **GitHub:** open the `packs` folder, click **Add file → Create new file**, and name it `week-02.json` (then `week-03.json` and so on). Paste Claude's reply and click **Commit changes**.
3. **Wait about 5 minutes.** The robot builds everything by itself. Your podcast app gets the new episodes. Download `week-02.apkg` from your page, then **File → Import** in Anki and **Sync**.

> 💡 Ask Gabriela to read the scenes now and then. If she says "nobody says that", tell Claude and it'll fix it next week.

---

## What each file is (you won't need to touch most of them)

| File | What it is |
|---|---|
| `packs/` | Your weekly content (week-00 = sound rules, week-01 is ready to go) |
| `build.py` | The robot's instructions: text → audio → flashcards → podcast |
| `.github/workflows/build.yml` | Tells GitHub to run the robot whenever you add a pack |
| `prompts/master_prompt.txt` | What you paste into your Claude Project |
| `docs/` | Created by the robot: audio, decks and feed. Don't edit. |

## Rebuilding / changing things

- **Fix a typo in a week that's already built:** go to **Actions → Build immersion pack → Run workflow**, set **force to 1**, and run. It rebuilds everything, which takes longer.
- **Different voices:** edit the `VOICES` list near the top of `build.py`.

## Prefer to skip GitHub? (run it on your own computer)

Install Python and ffmpeg, then run:

```
pip install -r requirements.txt
python build.py
```

The MP3s land in `docs/audio`; copy them to your phone. The decks land in `docs/decks`. You lose the auto-updating podcast, but everything else works.
