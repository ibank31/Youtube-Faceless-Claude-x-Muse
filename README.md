# Youtube-Faceless-Claude-x-Muse

Faceless YouTube Shorts channel, produced 100% with Python code (no generative AI, no Blender).
Read CONTRACT.md first.

Status: niche chosen by data = cosmic / real-data scale comparison (see research/analysis/2026-11-05-review.md).
Pilot episode ep001 built; see comms/to-muse/ for the current task.

    research/   niche research (scripts, frozen criteria, results, analysis)
    specs/      episode specs (*.yaml) and the approved test plan
    lib/        rendering engine (pycairo + numpy + ffmpeg)
    qc/         objective QC for rendered videos
    comms/      to-muse/ (tasks from Claude), from-muse/ (replies)
    renders/    outputs (videos are git-ignored; QC reports and contact sheets are kept)

Render: python render.py specs/ep001.yaml   |   QC: python qc/check_video.py renders/ep001
