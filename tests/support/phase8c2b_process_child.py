"""Synthetic inherited-stdio peer for bounded process lifecycle tests only."""

from __future__ import annotations

import hashlib
import json
import sys
import time


request = json.loads(sys.stdin.readline())
request_id = request.get("request_id", "")
mode = request_id[0] if request_id else "0"
if mode in {"2", "3"}:
    time.sleep(60)
if mode == "4":
    sys.stderr.write("x" * 5000)
if mode == "a":
    sys.stderr.write("bounded synthetic diagnostic")
if mode == "5":
    raise SystemExit(9)
if mode == "7":
    sys.stdout.write("x" * (129 * 1024))
    raise SystemExit(0)
if mode == "6":
    print("not-json")
    raise SystemExit(0)

projection = request["projection"]
candidate = json.dumps(
    {
        "schema_id": "aia-teaching-claim-candidate/v1",
        "projection_id": projection["projection_id"],
        "context_fingerprint": projection["context_fingerprint"],
        "envelope_id": projection["envelope_id"],
        "goal": projection["goal"],
        "ordered_permission_refs": [projection["slots"][0]["permission_ref"]],
    },
    separators=(",", ":"),
)
encoded = candidate.encode("utf-8")
receipt = {
    "schema_id": "aia-harness-publication-model-receipt/v1",
    "request_id": request_id if mode != "8" else "88888888-8888-4888-8888-888888888889",
    "request_digest": request["request_digest"] if mode != "9" else "sha256:" + "9" * 64,
    "status": "CANDIDATE",
    "executor_version": "aia-phase8c2b-executor/1",
    "runtime_version": "0.1.3-alpha.1",
    "provider_id": "deepseek-official",
    "model_id": "deepseek-v4-flash",
    "model_request_count": 1,
    "raw_byte_count": len(encoded),
    "raw_digest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    "raw_precheck": "SAFE",
    "finish_category": "STOP",
    "duration_bucket": "LT_1S",
    "failure_code": None,
    "raw_candidate": candidate,
}
print(json.dumps(receipt, separators=(",", ":")))
