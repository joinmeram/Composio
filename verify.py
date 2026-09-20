"""
Human verification pass.

Takes a random (or specified) sample of already-researched apps, and records
a human's independent judgement against the same evidence the agent cited
(plus a fresh look at the docs). This produces the accuracy numbers used in
the case study -- both the raw "did the agent's fields match reality" rate,
and the before/after effect of the validation/repair loop in orchestrate.py.

Usage:
    python -m src.verify --sample 15 --seed 42   # pick a sample to review
    python -m src.verify --record salesforce --field auth_methods --correct true --note "..."
"""

import argparse
import json
import os
import random

from app_list import APPS
from orchestrate import slug, load_checkpoint, RESULTS_DIR

VERIFICATION_LOG = os.path.join(os.path.dirname(__file__), "verification", "human_review.json")


def load_log():
    if os.path.exists(VERIFICATION_LOG):
        with open(VERIFICATION_LOG) as f:
            return json.load(f)
    return {}


def save_log(log):
    os.makedirs(os.path.dirname(VERIFICATION_LOG), exist_ok=True)
    with open(VERIFICATION_LOG, "w") as f:
        json.dump(log, f, indent=2)


def sample_apps(n, seed=42):
    random.seed(seed)
    researched = [a for a, c, h in APPS if load_checkpoint(a) is not None]
    return random.sample(researched, min(n, len(researched)))


def record(app, field, correct, note=""):
    log = load_log()
    log.setdefault(app, {})[field] = {"correct": correct, "note": note}
    save_log(log)


def summarize():
    log = load_log()
    total, correct = 0, 0
    per_field = {}
    for app, fields in log.items():
        for field, v in fields.items():
            total += 1
            correct += int(v["correct"])
            per_field.setdefault(field, [0, 0])
            per_field[field][1] += 1
            per_field[field][0] += int(v["correct"])
    print(f"Overall: {correct}/{total} = {correct/total:.0%}" if total else "No records yet.")
    for field, (c, t) in per_field.items():
        print(f"  {field}: {c}/{t} = {c/t:.0%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--record", type=str)
    parser.add_argument("--field", type=str)
    parser.add_argument("--correct", type=str, choices=["true", "false"])
    parser.add_argument("--note", type=str, default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    if args.sample:
        for a in sample_apps(args.sample, args.seed):
            print(a)
    elif args.record:
        record(args.record, args.field, args.correct == "true", args.note)
    elif args.summary:
        summarize()
