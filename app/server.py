"""Local web app for the AI Due Diligence demo (stdlib only).

    python3 app/server.py          -> http://localhost:8501
"""
import csv
import datetime as dt
import io
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW_LOG = os.path.join(HERE, "review_log.json")
STATE = {}


def load_reviews():
    if os.path.exists(REVIEW_LOG):
        return json.load(open(REVIEW_LOG))
    return {"latest": {}, "audit": []}


def save_reviews(r):
    json.dump(r, open(REVIEW_LOG, "w"), indent=2)


def run_analysis():
    t0 = time.time()
    kb, findings, entities = engine.analyse()
    STATE.update(kb=kb, findings=findings, entities=entities,
                 runtime=round(time.time() - t0, 2),
                 run_at=dt.datetime.now().strftime("%d %b %Y %H:%M:%S"))


def payload():
    kb = STATE["kb"]
    return {
        "run_at": STATE["run_at"], "runtime": STATE["runtime"], "today": str(engine.today()),
        "docs": [{"file": d["file"], "counterparty": d["counterparty"], "kind": d["kind"],
                  "title": d["doc_title"], "pages": d["pages"], "clauses": len(d["clauses"]),
                  "terms": engine.key_terms(d)} for d in kb],
        "findings": STATE["findings"],
        "entities": STATE["entities"],
        "evaluation": engine.evaluate(STATE["findings"]),
        "requests": engine.info_requests(STATE["findings"]),
        "reviews": load_reviews(),
        "llm": STATE["findings"][0].get("llm_note", "") if STATE["findings"] else "",
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", code=200, extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, default=str)
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            return self._send(open(os.path.join(HERE, "index.html"), encoding="utf-8").read(), "text/html")
        if u.path == "/api/data":
            return self._send(payload())
        if u.path == "/api/search":
            return self._send(engine.search(STATE["kb"], q.get("q", [""])[0]))
        if u.path == "/api/doc":
            f = q.get("file", [""])[0]
            d = next((d for d in STATE["kb"] if d["file"] == f), None)
            return self._send({"file": d["file"], "title": d["doc_title"], "clauses": d["clauses"]} if d else {}, code=200 if d else 404)
        if u.path == "/api/pdf":
            f = os.path.basename(q.get("file", [""])[0])
            p = os.path.join(engine.CONTRACTS, f)
            if os.path.exists(p):
                return self._send(open(p, "rb").read(), "application/pdf")
            return self._send({"error": "not found"}, code=404)
        if u.path == "/export/register.csv":
            buf = io.StringIO()
            cols = ["id", "severity", "confidence", "method", "counterparty", "file", "clause", "page",
                    "clause_type", "issue", "data_check", "workstreams", "review_status", "reviewer_note"]
            w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            rv = load_reviews()["latest"]
            for f in STATE["findings"]:
                w.writerow({**f, "workstreams": "; ".join(f["workstreams"]),
                            "review_status": rv.get(f["id"], {}).get("status", "Pending"),
                            "reviewer_note": rv.get(f["id"], {}).get("note", "")})
            return self._send(buf.getvalue(), "text/csv",
                              extra={"Content-Disposition": "attachment; filename=risk_register.csv"})
        if u.path == "/export/memo.md":
            memo = engine.ic_memo(STATE["findings"], STATE["entities"], load_reviews()["latest"])
            return self._send(memo, "text/markdown; charset=utf-8",
                              extra={"Content-Disposition": "attachment; filename=draft_findings_memo.md"})
        if u.path == "/api/memo":
            return self._send({"memo": engine.ic_memo(STATE["findings"], STATE["entities"], load_reviews()["latest"])})
        return self._send({"error": "not found"}, code=404)

    def do_POST(self):
        u = urlparse(self.path)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        if u.path == "/api/review":
            r = load_reviews()
            entry = {"finding": body["id"], "status": body["status"], "note": body.get("note", ""),
                     "reviewer": body.get("reviewer", "Analyst"),
                     "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            r["latest"][body["id"]] = entry
            r["audit"].append(entry)
            save_reviews(r)
            return self._send(r)
        if u.path == "/api/rerun":
            run_analysis()
            return self._send({"ok": True, "runtime": STATE["runtime"]})
        if u.path == "/api/reset_reviews":
            save_reviews({"latest": {}, "audit": []})
            return self._send({"ok": True})
        return self._send({"error": "not found"}, code=404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8501))
    run_analysis()
    print(f"Analysed {len(STATE['kb'])} documents -> {len(STATE['findings'])} findings in {STATE['runtime']}s")
    print(f"Open http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
