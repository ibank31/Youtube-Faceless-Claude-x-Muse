# Working contract: Claude x Muse

Roles
- Claude = director + code author. Owns every creative decision (niche, concept, beats, parameters) and the Python library.
- Muse = operator of the VM. Runs scripts, renders, reports. Does NOT change creative parameters.
- Iqbal = owner. Final say; relays between us when needed.

Hard rules
1. No generative AI content. Every frame and sound is produced by Python code. $0 budget, no paid assets.
2. No Blender. Rendering must take minutes, not hours.
3. Niche is chosen by data (research/), against criteria frozen BEFORE the run (research/criteria.yaml).
4. Secrets (API keys) live only in VM environment variables. Never commit them, never paste them in replies.

Write ownership (disjoint paths, so no merge conflicts)
- Claude writes: CONTRACT.md, README.md, comms/to-muse/, specs/, lib/, qc/, research/*.py|yaml
- Muse writes: comms/from-muse/, research/env_report.json, research/results/, renders/ (renders are git-ignored)
- Always `git pull --rebase` before work and before push.

Message protocol
- Claude -> Muse: comms/to-muse/NNN-title.md (numbered, one task per file).
- Muse -> Claude: comms/from-muse/NNN-reply.md with the same number. Required sections:
  1) Status per step (done / failed / skipped)  2) Errors verbatim (code block)
  3) Deviations from the instructions, if any  4) Questions / proposals (do not act on them)
- If something fails: stop, report, wait. Do not improvise fixes to creative parameters.

Review limits (applies from the production phase)
- Max 5 numbered revision points per round, max 2 rounds per gate. Gates: animatic -> motion proof -> final.
