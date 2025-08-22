# TGW (Text Generation Web UI) — OpenAI‑style API Cheatsheet

> **Scope:** You said you’ll load/select the model manually in TGW. This guide covers everything else needed to call TGW’s OpenAI-compatible API from Cursor.

---

## 0) TGW startup (one-time settings you run in TGW)
Enable the OpenAI bridge and listen on all interfaces:
```
--api --extensions openai --host 0.0.0.0
```
Default ports:
- Web UI (optional): **7860**
- TGW REST API: **5000**
- **OpenAI-compatible API**: **5001** → base URL is `http://<tgw-host>:5001/v1`

**Auth:** TGW expects a token; use `Authorization: Bearer local` (or set your own).

> **Note:** You’re loading the model yourself in TGW, so the client just uses whatever model TGW reports/has loaded. Always use an ID from `/v1/models`.

---

## 1) Quick terminal checks (handy inside Cursor’s terminal)
List models TGW currently knows (and which ID to use):
```bash
curl -s http://192.168.73.140:5001/v1/models   -H "Authorization: Bearer local" | jq .
```

Minimal chat test:
```bash
curl -s http://192.168.73.140:5001/v1/chat/completions   -H "Authorization: Bearer local" -H "Content-Type: application/json"   -d '{
    "model": "REPLACE_WITH_ID_FROM_/v1/models",
    "messages": [{"role":"user","content":"ping"}],
    "max_tokens": 8
  }'
```

> If you pass an unknown model name, TGW may try to hot-load or just use the currently loaded model. Use the exact `id` from `/v1/models`.

---

## 2) Node/TypeScript via official OpenAI SDK (simple & ergonomic)
Install:
```bash
npm i openai
```

Create **`tgw.ts`**:
```ts
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://192.168.73.140:5001/v1", // TGW OpenAI bridge
  apiKey: "local",                           // TGW expects a token; "local" is fine by default
});

export const TGW_MODEL =
  process.env.TGW_MODEL || "REPLACE_WITH_ID_FROM_/v1/models";

export async function classifyBatch(batch: Array<{source_id: string; polarity: "pos" | "neg"; prompt: string;}>) {
  const system =
    "You are a classifier that outputs ONLY valid JSON. No Markdown. No commentary.";
  const user = JSON.stringify({ batch });

  const resp = await client.chat.completions.create({
    model: TGW_MODEL,
    messages: [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
    temperature: 0,
    max_tokens: 512,
    // Enforce JSON if supported by your TGW build:
    response_format: { type: "json_object" },
    // You can pass llama.cpp extras as well (may need `as any`):
    // ...( { seed: 0, top_k: 40, grammar: GBNF_STRING } as any ),
  } as any);

  const content = resp.choices[0]?.message?.content ?? "{}";
  return JSON.parse(content);
}
```

Usage:
```ts
import { classifyBatch, TGW_MODEL } from "./tgw";

(async () => {
  const out = await classifyBatch([
    { source_id: "item123", polarity: "pos", prompt: "masterpiece, cinematic lighting, portrait of a woman, octane render, 35mm f/1.8" }
  ]);
  console.log(out);
})();
```

**Notes**
- Put your model ID into `.env` as `TGW_MODEL=...` for easy switching.
- If `response_format` isn’t honored by your TGW build, see §4 “Hard‑enforce JSON”.

---

## 3) Node/TypeScript via `axios` (full control)
Install:
```bash
npm i axios
```

Create **`tgw-axios.ts`**:
```ts
import axios from "axios";

const BASE = "http://192.168.73.140:5001/v1";
const HEADERS = {
  "Authorization": "Bearer local",
  "Content-Type": "application/json",
};
const MODEL = process.env.TGW_MODEL || "REPLACE_WITH_ID_FROM_/v1/models";

export async function chat(body: any, timeoutMs = 120_000) {
  const { data } = await axios.post(`${BASE}/chat/completions`, body, {
    headers: HEADERS,
    timeout: timeoutMs, // local inference can be slow; don’t use tiny timeouts
    validateStatus: s => s < 500, // surface 4xx as responses instead of throwing
  });
  return data;
}

// Example JSON-only call
(async () => {
  const body = {
    model: MODEL,
    messages: [
      { role: "system", content: "Only valid JSON. No prose." },
      { role: "user", content: JSON.stringify({
          batch: [{ source_id: "item123", polarity: "pos",
                    prompt: "masterpiece, cinematic lighting" }]
      })},
    ],
    max_tokens: 512,
    temperature: 0,
    response_format: { type: "json_object" },
    // llama.cpp extras are fine to include here too:
    // seed: 0, top_k: 40, grammar: GBNF_STRING
  };

  const resp = await chat(body);
  const json = JSON.parse(resp.choices[0].message.content);
  console.log(json);
})();
```
- Adjust `BASE` to your TGW host/IP.
- Bump `timeoutMs` if first token is slow on your hardware.

---

## 4) Hard‑enforce JSON (optional, for llama.cpp)
If the model sometimes adds prose, constrain output with a grammar (GBNF). Save a grammar that matches your schema (e.g., **`cls.gbnf`**) and send it as `"grammar": "<stringified gbnf>"` in the request body. TGW forwards unknown fields to llama.cpp when the **`llama.cpp`** loader is used.

> Tips: Keep `temperature: 0` and consider `seed: 0` for determinism.

**Example GBNF outline** (adapt to your exact schema):
```gbnf
ws        ::= " " | "\n" | "\r" | "\t"
quote     ::= """
string    ::= quote ( "\\" ["\\/bfnrt] | "\\u" hex hex hex hex | ~["\\] )* quote
hex       ::= [0-9a-fA-F]

root      ::= "{" ws? ""results"" ws? ":" ws? "[" ws? result (ws? "," ws? result)* ws? "]" ws? "}"
result    ::= "{" ws?
              ""source_id"" ws? ":" ws? string ws? "," ws?
              ""polarity""  ws? ":" ws? ( ""pos"" | ""neg"" ) ws? "," ws?
              ""phrases""   ws? ":" ws? "[" ws? phrase (ws? "," ws? phrase)* ws? "]"
              ws? "}"
phrase    ::= "{" ws?
              ""text""     ws? ":" ws? string ws? "," ws?
              ""category"" ws? ":" ws? category
              ws? "}"
category  ::= ""subjects"" | ""styles"" | ""aesthetics"" | ""techniques"" | ""quality_boosters"" | ""negatives"" | ""modifiers""
```
When inlining in JSON, escape newlines/quotes as shown.

---

## 5) Streaming (Server‑Sent Events)
Set `"stream": true` and read SSE chunks. Example with native `fetch` in Node 18+:

```ts
const res = await fetch("http://192.168.73.140:5001/v1/chat/completions", {
  method: "POST",
  headers: { "Authorization": "Bearer local", "Content-Type": "application/json" },
  body: JSON.stringify({
    model: process.env.TGW_MODEL || "REPLACE_WITH_ID_FROM_/v1/models",
    messages: [{ role: "user", content: "stream please" }],
    stream: true,
    max_tokens: 128,
  }),
});

if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
const reader = res.body.getReader();
const decoder = new TextDecoder();

let buf = "";
for (;;) {
  const { value, done } = await reader.read();
  if (done) break;
  buf += decoder.decode(value, { stream: true });
  for (const line of buf.split("\n")) {
    if (line.startsWith("data: ")) {
      const payload = line.slice(6);
      if (payload === "[DONE]") { /* flush/end */ break; }
      try {
        const delta = JSON.parse(payload);
        process.stdout.write(delta.choices?.[0]?.delta?.content ?? "");
      } catch { /* ignore partials */ }
    }
  }
}
```

---

## 6) Timeouts, retries, and other gotchas
- **Timeouts:** Set generous HTTP timeouts (60–120s) for first tokens on local models.
- **Max tokens:** If you see `"finish_reason": "length"`, raise `max_tokens` or trim verbosity.
- **Unknown model name:** TGW may hot‑load or stick to the currently loaded model. Use an `id` from `/v1/models`.
- **Ports:** OpenAI route is **5001**. If you see 404s, ensure `--extensions openai` is enabled and port 5001 is reachable.
- **CORS:** If calling from a browser, add a reverse proxy that injects permissive CORS headers.

---

## 7) Copy‑paste one‑liners (keep in your repo for quick debugging)
```bash
# List models
curl -s http://192.168.73.140:5001/v1/models -H "Authorization: Bearer local" | jq -r '.data[].id'

# Simple chat
ID="REPLACE_WITH_ID_FROM_/v1/models"
curl -s http://192.168.73.140:5001/v1/chat/completions   -H "Authorization: Bearer local" -H "Content-Type: application/json"   -d '{"model":"'"$ID"'","messages":[{"role":"user","content":"hi"}], "max_tokens":16}'
```
