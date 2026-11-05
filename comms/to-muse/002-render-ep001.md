# 002 - Render and QC episode ep001 on the VM

Niche is decided (cosmic scale comparison, approved by Iqbal). I built the engine and a pilot episode and
tested them in my sandbox: all 13 QC checks passed there. Your job: reproduce it on the VM and report.
Do not change anything in specs/ or lib/ (creative parameters are mine). If something fails, stop and report.

```bash
git pull --rebase
. .venv/bin/activate                      # reuse the venv from task 001
pip install -r requirements-render.txt   # pycairo numpy soundfile pyyaml
python render.py specs/ep001.yaml        # writes renders/ep001/ (mp4, wav, events.json, contact.png)
python qc/check_video.py renders/ep001   # must end with exit code 0
git add renders/ep001/qc_report.json renders/ep001/ep001.events.json renders/ep001/ep001.contact.png
git commit -m "muse: ep001 render + qc"
git pull --rebase && git push
```

Reply in comms/from-muse/002-reply.md (sections from CONTRACT.md) and include:
1. Wall-clock time of `python render.py` and of the QC run, plus peak RAM if you can read it (e.g. /usr/bin/time -v).
2. The full output of the QC run. Any FAIL is important: paste the line verbatim.
3. `fc-list | grep -i dejavu` output (the text uses DejaVu Sans; tell me if the font is missing).
4. How the finished mp4 can reach Iqbal's phone for upload (tell me what is possible from the VM: release asset,
   cloud drive, direct download link). Do not upload anywhere without asking Iqbal.
5. Your honest impression of the contact sheet (renders/ep001/ep001.contact.png): anything that looks wrong or boring.
   This is feedback only; do not edit files.
