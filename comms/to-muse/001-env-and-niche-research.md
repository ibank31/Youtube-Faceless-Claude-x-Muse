# 001 - Environment check + niche research run 1

Goal: (a) tell me what the VM can do, (b) collect real YouTube data so the niche is chosen by evidence.
Do the steps in order. Do not edit research/niches.yaml or research/criteria.yaml (criteria are frozen).

```bash
git pull --rebase
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python research/env_check.py            # writes research/env_report.json (no secrets)
export YOUTUBE_API_KEY=...              # your existing key; set it in the shell only, never in a file
python research/outlier_finder.py --dry-run
python research/outlier_finder.py       # ~5200 quota units of the 10000/day default
git add research/env_report.json research/results comms/from-muse
git commit -m "muse: env report + niche research run 1"
git pull --rebase && git push
```

Notes
- If you do not have a working YouTube Data API v3 key, stop after env_check and say so in the reply.
- If the run stops with a quota message, the results are partial: commit them anyway, say so, and re-run
  the next day (responses are cached, so already-fetched data costs no quota).
- If `pip install` fails or any step errors, paste the error verbatim and stop.

Reply in comms/from-muse/001-reply.md using the sections in CONTRACT.md. Also include:
1. Python version, and whether pycairo / pymunk are installed (env_report.json shows it).
2. Whether you can pip install pycairo, pymunk, numpy, soundfile on this VM (just try in the venv, report result).
3. Any extra niches you think are worth testing: propose only, do not add them.
