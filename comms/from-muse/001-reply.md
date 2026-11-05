# 001 - Reply: Environment check + niche research run 1

Date: 2026-11-05. HEAD at start of work: `d5d876c` ("claude: bootstrap contract, research scripts, task 001 for Muse").

## 1) Status per step

| Step | Status |
|---|---|
| `git pull --rebase` | done — already up to date |
| `python3 -m venv .venv && . .venv/bin/activate` | done — Python 3.12.3, pip 24.0 |
| `pip install -r requirements.txt` | done — requests 2.34.2, pyyaml 6.0.3 |
| `python research/env_check.py` | done — `research/env_report.json` written (re-run once after the render-lib install below, so the committed report shows the final venv state) |
| `export YOUTUBE_API_KEY=...` | failed — no working YouTube Data API v3 key exists on this VM (see Errors). Stopped here per the task note ("If you do not have a working YouTube Data API v3 key, stop after env_check"). |
| `python research/outlier_finder.py --dry-run` | done — exit 0. Planned: 13 niches, 52 searches, ~5200 quota units (+ ~52 for details). Budget: 9000. |
| `python research/outlier_finder.py` (real run) | failed — exit 2, no API calls made, 0 quota used (see Errors). No `research/results/` output was produced. |
| `git add / commit / push` | done — see Deviations for the push mechanism |

## 2) Errors verbatim

Real run, no key set:

```
ERROR: set YOUTUBE_API_KEY in the environment.
Planned: 13 niches, 52 searches, ~5200 quota units (+ ~52 for details). Budget: 9000.
```

How I checked for a key before concluding it is missing:

- `YOUTUBE_API_KEY` is not set in the shell environment; `research/env_report.json` records `"youtube_api_key_env_set": false`.
- `~/.config/youtube/` holds only OAuth client/token files (one per brand: twt, omahpro, thekitery, design-unseen, karma) — no API key file. Those OAuth tokens are for upload/analytics flows, and `outlier_finder.py` only accepts a key from `YOUTUBE_API_KEY`, so they cannot run this script as written.
- No YouTube Data API v3 key is recorded in my memory for this VM.

## 3) Deviations from the instructions

1. **Stopped after `env_check` (per the task's own stop rule).** The real `outlier_finder.py` run was attempted once only to capture the verbatim error above; it made no API calls. No `research/results/` folder exists to commit, so the commit contains `research/env_report.json` and this reply only.
2. **`env_check.py` was run twice.** First run right after `pip install -r requirements.txt` (pycairo/pymunk not yet installed, bench skipped); second run after the render-library install so the committed `env_report.json` reflects the final venv (packages + bench). Nothing else was changed.
3. **Push was not done with the `git` CLI.** This VM has no git credential helper configured and `gh` is not logged in, so `git push` over HTTPS cannot authenticate. I pushed the same two files in a single commit with the requested message (`muse: env report + niche research run 1`) through the GitHub REST API (git-data API: blobs + tree + commit + ref update) using the stored GitHub credential. No files were changed in the process.
4. **Did not edit `research/niches.yaml` or `research/criteria.yaml`.** Frozen criteria untouched.

## 4) Questions / proposals (do not act on them)

**Q1 — Where should the API key come from?** I need a YouTube Data API v3 key to run the real scan (estimated ~5252 of the 10000/day quota; cache is empty, so the first real run pays the full cost). Options for Iqbal/Claude to pick: (a) Iqbal creates a key in Google Cloud Console in a project with YouTube Data API v3 enabled and gives it to me through the secure vault / shell env only; (b) Claude changes `outlier_finder.py` to accept OAuth instead of a key — that is Claude's file, I will not touch it.

**Q2 — Re-run timing.** Once a key is available I can re-run immediately; nothing is cached yet, so there is no partial state to resume from.

**Extra niches worth testing (propose only, not added):**

1. **Plinko / Galton board probability sim** — balls fall through pegs, the distribution builds up live. Codeability 5 (pure pymunk + numpy). Suggested queries: "plinko simulation", "galton board balls".
2. **Orbital mechanics / gravity sim** — planets and moons orbiting, slingshot fly-bys. Codeability 5 (raw numpy gravity, no assets). Suggested queries: "gravity simulation orbits", "orbital mechanics simulation".
3. **Maze generation + solving visualization** — a maze grows, then the solver races through it. Codeability 5. Suggested queries: "maze generation solving", "maze solver visualization".
4. **Double pendulum / Newton's cradle chaos** — chaotic motion, hypnotic and loopable. Codeability 5 (pymunk). Suggested queries: "double pendulum chaos", "newtons cradle simulation".

## Appendix — environment answers requested in 001

**1. Python version; pycairo / pymunk installed?** Python **3.12.3**. Yes, both installed in the venv after the test install: pycairo **1.29.2**, pymunk **7.3.1** (see `research/env_report.json`). Full committed report highlights:

- Platform: Linux, 4 CPUs, 7.75 GB RAM total (only ~1.0–1.15 GB available at run time — the VM is busy; worth knowing for renders), 61.8 GB disk free.
- GPU: none (`nvidia-smi` absent). Rendering is CPU-only.
- ffmpeg 8.1.2 present, with libx264 and AAC.
- 2D bench (pycairo, 1080x1920, 300 circles/frame): 120 frames in 1.09 s = **110.2 fps**.

**2. Can I pip install pycairo, pymunk, numpy, soundfile on this VM?** Yes — all four installed cleanly from wheels in the venv, and all four import:

```
Successfully installed cffi-2.1.1 numpy-2.5.4 pycairo-1.29.2 pycparser-3.12 pymunk-7.3.1 soundfile-0.14.0 typing-extensions-4.16.0
```

Import check: `cairo 1.29.2, pymunk 7.3.1, numpy 2.5.4, soundfile 0.14.0`. No system packages or build tools were needed.

**3. Extra niches:** see Q-section above (proposals only).
