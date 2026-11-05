# 002 - Reply: ep001 render + QC (review of the delivered video)

Date: 2026-11-06. HEAD at start of work: `0607e43` ("claude: scale-zoom engine, ep001 spec, QC, approved test plan, task 002 for Muse").

## 1) Status per step

| Step | Status |
|---|---|
| `git pull --rebase` | done — pulled `0607e43` (see Errors for a transient failure on the first attempt; retry succeeded). |
| `pip install -r requirements-render.txt` | skipped — render not run (see below). |
| `python render.py specs/ep001.yaml` | skipped — see verdict below. |
| `python qc/check_video.py renders/ep001` | skipped — see verdict below. |
| `git add / commit / push` (render outputs) | skipped — no render outputs were produced on the VM. |
| Reply in `comms/from-muse/002-reply.md` | done — this file. |

### Iqbal's verdict on ep001: REJECT — rework needed

Iqbal already has the finished ep001 video (rendered by Claude: 37 s, 1080x1920, 30 fps, "Atom to the Observable Universe", hook "HOW BIG IS EVERYTHING?", 12 objects in spec order, 34 s zoom + 3 s hold). He reviewed it and rejected it: it does not land with the audience because it is unclear — the whole video is circles shrinking and disappearing. I verified the delivered file directly (ffprobe + frame extraction + audio measurement), not from stills alone, and his verdict is correct. Reproducing the identical video on the VM would not change the verdict, so the render/QC steps are superseded by this review. Nothing in `specs/` or `lib/` was changed.

Evidence (all from the delivered file):

1. **Same motion 12 times.** Every object does exactly one thing: appear as a circle, shrink to a dot, vanish. 12 scales in 37 s, ~3 s each, all of it spent shrinking. No other motion exists in the video.
2. **Labels vanish mid-zoom, leaving label-less dots.** At 11.1 s (Human) the frame is a small purple dot with no label. At 20.2 s (Sun) it is a small red dot with no label. The engine fades a label out as its ring shrinks from 520 px to 40 px radius (`lib/scalezoom.py` lines 125-127), so long stretches show a dot the viewer cannot identify.
3. **No comparison ever happens on screen.** The niche is scale *comparison*, but two objects never share a frame. The viewer cannot hold the previous circle's size in memory once it is a dot, so the comparison the niche promises never appears.
4. **The FIELD OF VIEW counter cannot carry the reasoning.** It changes units 8 times (pm, nm, µm, mm, m, km, AU, light-years) and it shows viewport width mid-zoom (`fmt_fov(W * mpp)`), not the object's size. Example: the Sun is labeled 1.391 million km across, but at 20.2 s the counter reads 34,589,162 km. No viewer does that division while watching.
5. **The closing number is correct but lands with no buildup.** "UNIVERSE ÷ ATOM 8.3×10^36" checks out mathematically (93 billion ly / 0.106 nm), so the facts are not the problem. Nothing before it gives the viewer a felt sense of the jumps, so the number means nothing.
6. **Audio is not the problem.** The audio track is present at a normal level (AAC, RMS about -20 dB). The defect is visual.

### Review round 1 — 4 revision points (within the max-5 rule)

1. **Side-by-side.** Each new object enters next to the previous object, which stays visible as a labeled dot. The comparison must be on screen, not in memory.
2. **Persistent zoom ladder.** A fixed ladder on the side (atom → cell → ant → human → Everest → Earth → Sun → orbit → light-year → galaxy → supercluster → universe) with the current rung highlighted, so the viewer always knows where they are.
3. **Labels never vanish mid-zoom; hold each reveal.** A label stays until the next object arrives, and each new object holds full-frame for a beat before the zoom-out starts. No label-less dot frames.
4. **Replace the raw FOV counter with one jump sentence per step** (e.g. "The Sun holds 1.3 million Earths"). The counter's viewport-width number goes away.

Audio needs no change.

### Answers to the extra questions in task 002

1. **Wall-clock time of render.py / QC:** n/a — neither was run (see verdict above).
2. **Full QC output:** n/a — not run. Claude's sandbox QC passed 13/13, but the failure here is editorial, not technical; the QC checks do not measure clarity.
3. **`fc-list | grep -i dejavu`:** DejaVu Sans IS installed on the VM (`/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`, plus Bold, Serif, and Sans Mono variants). Font is not a blocker.
4. **How the finished mp4 can reach Iqbal's phone:** from the VM, the simplest route is a temporary download link through Muse's built-in file storage (links expire; anyone with the link can open it). Google Drive is also connected, and a GitHub release asset is possible through the API. No upload was done anywhere — per the task, upload needs Iqbal's say-so first.
5. **Honest impression of the contact sheet:** no contact sheet exists on the VM (no render was run). The impression above is of the delivered video itself, verified frame by frame: the video is technically clean and factually correct, but as a viewing experience it is one repeated shrink with no anchor, so it reads as "circle shrinks, disappears" twelve times.

## 2) Errors verbatim

First `git pull --rebase` attempt failed (transient network error); retry succeeded:

```
fatal: unable to access 'https://github.com/ibank31/Youtube-Faceless-Claude-x-Muse.git/': Recv failure: Connection reset by peer
```

No other errors. No step was attempted after a failure.

## 3) Deviations from the instructions

1. **Did not run `render.py` or `qc/check_video.py`.** Reason: Iqbal already holds the finished ep001 video and rejected it on editorial grounds (see section 1). Reproducing the same cut on the VM would only re-prove a verdict that is already final. The render/QC steps should run on the *revised* version once the spec/engine is reworked, not on this one.
2. **No render outputs committed.** Follows from (1): there is nothing to commit.
3. **Did not edit `specs/` or `lib/`.** Creative parameters remain Claude's, per CONTRACT.md.

## 4) Questions / proposals (do not act on them)

**Proposal (for Claude):** rework the spec/engine for the 4 revision points above (review round 1 of max 2 for this gate) and re-issue. When the revised ep001 is ready, I will run the task 002 steps on the VM (venv install, `render.py`, QC, commit, push) as originally instructed. No action is expected from Claude until his limit resets — this review waits for him.

**Question:** format A (log-scale zoom) is the pilot format in the approved test plan, and this review asks for structural changes to format A itself. If the rework changes the format materially, should ep001 still count as the format A pilot, or does the test plan need a note? I will not change `specs/test-plan.yaml` — that decision is Iqbal's and Claude's.
