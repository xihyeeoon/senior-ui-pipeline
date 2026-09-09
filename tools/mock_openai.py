import json, time, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs", "mock_requests.jsonl")

FAKE = {
  "get_web_page_components": {"components": ["Card", "Icon Button", "Text"]},
  "get_library_components": {"components": ["cards", "icon buttons", "text fields"]},
  "analyze_components": {"bad_component_design": [{
      "bad_design_code_filename": "example1.tsx",
      "bad_design_code": "<MOCK bad code>",
      "detailed_reference_from_guidelines": "MOCK guideline reference",
      "suggestion_fix_code": "<MOCK fixed code>"}]},
  "repair_to_full_code": {"repaired_code": "// MOCK repaired file\nexport default function Component(){return null}"},
}
# analysis_groups reuses the name analyze_components but expects bad_property_design
PROP = {"bad_property_design": [{
      "bad_design_code_filename": "example1.tsx",
      "bad_design_code": "<MOCK bad property>",
      "detailed_reference_from_guidelines": "MOCK property guideline",
      "suggestion_fix_code": "<MOCK property fix>"}]}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        fns = body.get("functions")
        fname = fns[0]["name"] if fns else None
        props = (fns[0].get("parameters", {}).get("properties", {}) if fns else {})
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "path": self.path, "model": body.get("model"),
                "function": fname, "schema_top_keys": list(props),
                "n_messages": len(body.get("messages", [])),
                "prompt_chars": sum(len(str(m.get("content",""))) for m in body.get("messages",[])),
                "first_user_msg_head": next((str(m.get("content",""))[:300] for m in body.get("messages",[]) if m.get("role")=="user"), ""),
            }, ensure_ascii=False) + "\n")

        if fname == "analyze_components" and "bad_property_design" in props:
            payload = json.dumps(PROP)
        elif fname:
            payload = json.dumps(FAKE.get(fname, {"components": []}))
        else:
            payload = "// MOCK repaired full code\nexport default function Component(){ return <div/> }"

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        def chunk(delta):
            d = {"id":"m","object":"chat.completion.chunk","created":int(time.time()),
                 "model":body.get("model","mock"),"choices":[{"index":0,"delta":delta,"finish_reason":None}]}
            self.wfile.write(b"data: " + json.dumps(d).encode() + b"\n\n"); self.wfile.flush()
        if fname:
            chunk({"role":"assistant","function_call":{"name":fname,"arguments":""}})
            for i in range(0, len(payload), 200):
                chunk({"function_call":{"arguments":payload[i:i+200]}})
        else:
            chunk({"role":"assistant","content":""})
            for i in range(0, len(payload), 200):
                chunk({"content":payload[i:i+200]})
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()

ThreadingHTTPServer(("127.0.0.1", 8099), H).serve_forever()
