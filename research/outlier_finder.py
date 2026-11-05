#!/usr/bin/env python3
"""Phase 1 niche gap finder.
Reads research/niches.yaml + research/criteria.yaml, queries YouTube Data API v3 and writes
research/results/<UTC date>/{videos.csv, niche_scores.csv, SUMMARY.md, run_meta.json}.
API key comes ONLY from env var YOUTUBE_API_KEY. Never put it in the repo.

Usage:
  python research/outlier_finder.py --dry-run      # print planned quota, no API calls
  python research/outlier_finder.py                # real run (default quota budget 9000 of 10000/day)

Two samples per query: order=viewCount (finds winners) and order=date (random-ish recent
uploads, used for a base rate). The base rate is the only guard against survivorship bias;
this tool measures whether gaps EXIST, it does not predict the chance of going viral.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import statistics
import sys
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
API = "https://www.googleapis.com/youtube/v3"
COST = {"search": 100, "videos": 1, "channels": 1}
ORDERS = ("viewCount", "date")


class QuotaExceeded(Exception):
    pass


class Quota:
    def __init__(self, budget):
        self.budget, self.used = budget, 0

    def spend(self, kind):
        c = COST[kind]
        if self.used + c > self.budget:
            raise QuotaExceeded(f"quota budget {self.budget} reached")
        self.used += c


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def parse_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_dur(s):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return None
    d, h, mi, sec = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + sec


def chunked(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def api_get(endpoint, params, kind, quota, key, cache_dir):
    ck = hashlib.sha256(json.dumps([endpoint, params, utcnow().date().isoformat()],
                                   sort_keys=True).encode()).hexdigest()[:24]
    cp = cache_dir / f"{endpoint}_{ck}.json"
    if cp.exists():
        return json.loads(cp.read_text())
    quota.spend(kind)
    r = requests.get(f"{API}/{endpoint}", params={**params, "key": key}, timeout=30)
    if r.status_code != 200:
        try:
            reason = r.json()["error"]["errors"][0].get("reason", "")
        except Exception:  # noqa: BLE001
            reason = r.text[:200]
        if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise QuotaExceeded(reason)
        raise RuntimeError(f"{endpoint} HTTP {r.status_code}: {reason}")
    data = r.json()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(data))
    return data


def score_niche(rows, crit, codeability):
    small, hit, newd = crit["small_channel_subs"], crit["hit_views"], crit["new_channel_days"]
    rules = crit["pass_rules"]
    small_hits = {r["channel_id"] for r in rows if r["channel_subs"] < small and r["views"] >= hit}
    new_hits = {r["channel_id"] for r in rows if r["channel_age_days"] <= newd and r["views"] >= hit}
    sample = [r for r in rows if "date" in r["via"].split("|") and r["channel_subs"] < small]
    base_rate = (sum(1 for r in sample if r["views"] >= crit["base_rate_views"]) / len(sample)) if sample else None
    checks = {
        "codeability": codeability >= rules["min_codeability"],
        "small_channel_hits": len(small_hits) >= rules["min_small_channel_hits"],
        "new_channel_hits": len(new_hits) >= rules["min_new_channel_hits"],
        "base_rate_sample": len(sample) >= rules["min_base_rate_sample"],
        "base_rate": base_rate is not None and base_rate >= rules["min_base_rate"],
    }
    return {
        "videos": len(rows),
        "distinct_channels": len({r["channel_id"] for r in rows}),
        "small_channel_hits": len(small_hits),
        "new_channel_hits": len(new_hits),
        "base_rate_sample": len(sample),
        "base_rate": None if base_rate is None else round(base_rate, 4),
        "median_views_date_sample": int(statistics.median([r["views"] for r in sample])) if sample else None,
        "codeability": codeability,
        "passed": all(checks.values()),
        "failed_checks": ",".join(k for k, v in checks.items() if not v),
    }


def write_outputs(outdir, rows, scores, labels, crit, quota, notes):
    outdir.mkdir(parents=True, exist_ok=True)
    if rows:
        with open(outdir / "videos.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    ranked = sorted(scores.items(), key=lambda kv: (
        not kv[1]["passed"], -(kv[1]["base_rate"] or 0), -kv[1]["small_channel_hits"]))
    with open(outdir / "niche_scores.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["niche"] + list(next(iter(scores.values())).keys()) if scores else ["niche"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for nid, s in ranked:
            w.writerow({"niche": nid, **s})
    lines = [f"# Niche scan {utcnow().date()}", "",
             f"Quota used: {quota.used}. Criteria frozen in research/criteria.yaml.", ""]
    lines += [f"NOTE: {n}" for n in notes] + [""] if notes else []
    lines += ["| niche | pass | small hits | new hits | base rate (n) | failed |", "|---|---|---|---|---|---|"]
    for nid, s in ranked:
        br = "n/a" if s["base_rate"] is None else f"{s['base_rate']:.1%}"
        lines.append(f"| {labels[nid]} | {'YES' if s['passed'] else 'no'} | {s['small_channel_hits']} | "
                     f"{s['new_channel_hits']} | {br} ({s['base_rate_sample']}) | {s['failed_checks'] or '-'} |")
    lines += ["", "Caveat: viewCount-ordered search only shows winners (survivorship bias). The base rate",
              "column (date-ordered sample) is the only failure-aware signal. This ranks niches by evidence",
              "that a gap exists; it does not predict the probability of any single video going viral."]
    (outdir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (outdir / "run_meta.json").write_text(json.dumps({
        "generated_at_utc": utcnow().isoformat(timespec="seconds"), "quota_used": quota.used,
        "criteria": crit, "notes": notes}, indent=2))


def run(args):
    niches = yaml.safe_load((HERE / "niches.yaml").read_text())["niches"]
    crit = yaml.safe_load((HERE / "criteria.yaml").read_text())
    n_search = sum(len(n["queries"]) for n in niches) * len(ORDERS)
    est = n_search * COST["search"]
    print(f"Planned: {len(niches)} niches, {n_search} searches, ~{est} quota units "
          f"(+ ~{n_search} for details). Budget: {args.budget}.")
    if args.dry_run:
        return 0
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        print("ERROR: set YOUTUBE_API_KEY in the environment.", file=sys.stderr)
        return 2
    quota, cache = Quota(args.budget), HERE / "cache"
    after = (utcnow() - dt.timedelta(days=crit["window_days"])).strftime("%Y-%m-%dT00:00:00Z")
    notes, found = [], {}  # found[(niche, video_id)] = set(orders)
    vdata, cdata = {}, {}
    try:
        for n in niches:
            for q in n["queries"]:
                for order in ORDERS:
                    data = api_get("search", {"part": "id", "type": "video", "videoDuration": "short",
                                              "order": order, "q": q, "maxResults": 50,
                                              "publishedAfter": after, "relevanceLanguage": "en"},
                                   "search", quota, key, cache)
                    for it in data.get("items", []):
                        found.setdefault((n["id"], it["id"]["videoId"]), set()).add(order)
        for ids in chunked({v for _, v in found}, 50):
            for it in api_get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids)},
                              "videos", quota, key, cache).get("items", []):
                vdata[it["id"]] = it
        cids = {v["snippet"]["channelId"] for v in vdata.values()}
        for ids in chunked(cids, 50):
            for it in api_get("channels", {"part": "snippet,statistics", "id": ",".join(ids)},
                              "channels", quota, key, cache).get("items", []):
                cdata[it["id"]] = it
    except QuotaExceeded as e:
        notes.append(f"STOPPED EARLY, results are partial: {e}. Re-run tomorrow; cache is reused.")
        print(notes[-1], file=sys.stderr)
    now, by_niche = utcnow(), {n["id"]: [] for n in niches}
    for (nid, vid), via in found.items():
        v = vdata.get(vid)
        ch = cdata.get(v["snippet"]["channelId"]) if v else None
        if not v or not ch:
            continue
        dur = parse_dur(v["contentDetails"].get("duration"))
        cs = ch.get("statistics", {})
        if not dur or dur > crit["max_short_seconds"] or cs.get("hiddenSubscriberCount"):
            continue
        views, subs = int(v.get("statistics", {}).get("viewCount", 0)), int(cs.get("subscriberCount", 0))
        by_niche[nid].append({
            "niche": nid, "video_id": vid, "url": f"https://youtube.com/shorts/{vid}",
            "title": v["snippet"]["title"], "channel_id": v["snippet"]["channelId"],
            "channel_subs": subs, "channel_age_days": (now - parse_ts(ch["snippet"]["publishedAt"])).days,
            "published_at": v["snippet"]["publishedAt"], "duration_s": dur, "views": views,
            "likes": int(v.get("statistics", {}).get("likeCount", 0)),
            "views_per_sub": round(views / max(subs, 100), 2), "via": "|".join(sorted(via)),
        })
    labels = {n["id"]: n["label"] for n in niches}
    scores = {n["id"]: score_niche(by_niche[n["id"]], crit, n["codeability"]) for n in niches}
    rows = [r for n in niches for r in by_niche[n["id"]]]
    outdir = HERE / "results" / now.date().isoformat()
    write_outputs(outdir, rows, scores, labels, crit, quota, notes)
    print(f"Done. Quota used: {quota.used}. Output: {outdir}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--budget", type=int, default=9000)
    sys.exit(run(ap.parse_args()))
