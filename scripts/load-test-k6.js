import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

const baseUrl = (__ENV.BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const users = Number(__ENV.USERS || 3);
const duration = __ENV.DURATION || "1m";
const p95Ms = Number(__ENV.P95_MS || 60000);
const queryText = __ENV.QUERY || "How can I resolve a disagreement with a close friend honestly and compassionately?";
const preSynthesisVerification = String(__ENV.PRE_SYNTHESIS || "false").toLowerCase() === "true";
const loginEmail = __ENV.ANAYAA_LOAD_TEST_EMAIL || "codex.test@example.com";
const loginPassword = __ENV.ANAYAA_LOAD_TEST_PASSWORD || "";

const queryLatency = new Trend("anayaa_query_latency_ms", true);
const queryErrors = new Counter("anayaa_query_errors");

export const options = {
  scenarios: {
    steady_guidance_requests: {
      executor: "constant-vus",
      vus: users,
      duration,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    anayaa_query_errors: ["count<1"],
    anayaa_query_latency_ms: [`p(95)<${p95Ms}`],
  },
};

let token = null;

function login() {
  if (!loginPassword) {
    throw new Error("ANAYAA_LOAD_TEST_PASSWORD must be set for load tests.");
  }
  const response = http.post(
    `${baseUrl}/api/auth/login`,
    JSON.stringify({ email: loginEmail, password: loginPassword }),
    { headers: { "Content-Type": "application/json" }, tags: { endpoint: "login" } },
  );

  const ok = check(response, {
    "login returned 200": (res) => res.status === 200,
    "login returned token": (res) => Boolean(res.json("token")),
  });
  if (!ok) {
    queryErrors.add(1);
    return null;
  }
  return response.json("token");
}

export default function () {
  if (!token) {
    token = login();
  }
  if (!token) {
    sleep(1);
    return;
  }

  const startedAt = Date.now();
  const response = http.post(
    `${baseUrl}/api/query`,
    JSON.stringify({
      query: queryText,
      preSynthesisVerification,
    }),
    {
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      timeout: __ENV.TIMEOUT || "120s",
      tags: { endpoint: "query" },
    },
  );
  queryLatency.add(Date.now() - startedAt);

  const ok = check(response, {
    "query returned supported status": (res) => [200, 403, 429, 503].includes(res.status),
    "query did not return server error": (res) => res.status < 500 || res.status === 503,
    "query response is JSON": (res) => String(res.headers["Content-Type"] || "").includes("application/json"),
  });
  if (!ok || response.status >= 500) {
    queryErrors.add(1);
  }

  sleep(Number(__ENV.SLEEP_SECONDS || 1));
}
