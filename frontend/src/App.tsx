import { useCallback, useEffect, useState } from "react";
import { BookOpen, Leaf, Shield, Sparkles } from "lucide-react";

type Tab = "pathway" | "scriptures" | "eco";

const SESSION_WARNING_MS = 60_000;
const STORED_CONVERSATION_HISTORY = 2;
const PREVIOUS_CONVERSATION_LIMIT = 1;

interface ScriptureVerse {
  id: string;
  faith: string;
  source: string;
  chapter: string;
  verse: string;
  translation: string;
  context: string;
  keywords: string[];
  originalText?: string;
}

interface AuditScores {
  scores: Record<string, number>;
  passed: boolean;
  rationale: string;
  judgeModel?: string;
}

interface CompressionMetrics {
  compressedPrompt?: string;
  compressedQuestion?: string;
  originTokens?: number;
  compressedTokens?: number;
  compressionRatio?: string;
  enabled?: boolean;
  method?: string;
}

interface QueryResult {
  moralPathway?: string | null;
  userMessage?: string;
  failureReason?: string;
  citations?: ScriptureVerse[];
  plannerReasoning?: string;
  historySummary?: string;
  toneMsg?: string;
  confidence?: number;
  topRetrievalScore?: number;
  contextThreshold?: number;
  cacheHit?: boolean;
  compressedQuery?: string;
  compressionMetrics?: CompressionMetrics;
  powerMetrics?: { energyMWh: number; co2Kg: number; cpuWatts: number; gpuWatts: number; hardwareLevel: string };
  ecoBreakdown?: Array<{ stage: string; energyWh: number; co2Kg: number; durationMs: number }>;
  auditScores?: AuditScores;
  status?: string;
  hitl?: { workflowRunId: string; draftPathway: string };
  quantizedMetrics?: Record<string, unknown>;
  synthesisEngine?: string;
  executionPlan?: string[];
}

interface QuestionHistoryItem {
  id: string;
  question: string;
  response: string;
  timestamp: string;
}

interface GuidanceSection {
  label?: string;
  text: string;
}

const GUIDANCE_LABELS: Record<string, string> = {
  "one line summary": "One-line summary",
  "one-line summary": "One-line summary",
  summary: "One-line summary",
  reflection: "Reflection",
  judgment: "Judgment",
  judgement: "Judgment",
  "next step": "Next step",
  action: "Next step",
  "scripture grounding": "Scripture grounding",
  grounding: "Scripture grounding",
};

function decodeBase64Url(value: string): string {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
  return atob(padded);
}

function getJwtExpiryMs(jwtToken: string | null): number | null {
  if (!jwtToken) return null;
  try {
    const [, payload] = jwtToken.split(".");
    if (!payload) return null;
    const decoded = JSON.parse(decodeBase64Url(payload)) as { exp?: number };
    return typeof decoded.exp === "number" ? decoded.exp * 1000 : null;
  } catch {
    return null;
  }
}

function resultStatusTitle(status?: string): string {
  if (status === "retrieval_unavailable") return "Scripture Retrieval Service Unavailable";
  if (status === "insufficient_context") return "No Relevant Scripture Context";
  if (status === "quality_threshold_not_met") return "Quality Threshold Not Met";
  return "Workflow Notice";
}

function formatMetricValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "n/a";
  if (typeof value === "number") return Number.isInteger(value) ? value.toString() : value.toFixed(2);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function guidanceSections(pathway?: string | null): GuidanceSection[] {
  if (!pathway) return [];
  const cleaned = pathway
    .replace(/\*\*/g, "")
    .replace(/^#+\s*/gm, "")
    .trim();

  const labelPattern = Object.keys(GUIDANCE_LABELS)
    .sort((a, b) => b.length - a.length)
    .map((label) => label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");

  const sections: GuidanceSection[] = [];
  let pendingLabel: string | null = null;
  const lines = cleaned
    .replace(new RegExp(`\\b(${labelPattern})\\s*:\\s*`, "gi"), "\n$1: ")
    .replace(/\s+(?=\d+[.)]\s+)/g, "\n")
    .split(/\n+/)
    .map((line) =>
      line
        .replace(/^[\s*\-•]*(?:\d+[.)]\s*)?/, "")
        .trim(),
    )
    .filter(Boolean);

  for (const line of lines) {
    const match = line.match(/^([A-Za-z][A-Za-z -]{1,32}):\s*(.*)$/);
    if (match) {
      const label = GUIDANCE_LABELS[match[1].trim().toLowerCase()];
      if (label) {
        const text = match[2].trim();
        if (text) {
          sections.push({ label, text });
          pendingLabel = null;
        } else {
          pendingLabel = label;
        }
        continue;
      }
    }

    if (pendingLabel) {
      sections.push({ label: pendingLabel, text: line });
      pendingLabel = null;
    } else {
      sections.push({ text: line });
    }
  }

  return sections;
}

function responseText(result?: QueryResult | null): string {
  return result?.moralPathway || result?.hitl?.draftPathway || result?.userMessage || result?.failureReason || "";
}

function conversationHistoryKey(userEmail: string): string {
  return `anayaa_question_history:${userEmail}`;
}

function loadConversationHistory(userEmail: string): QuestionHistoryItem[] {
  if (!userEmail) return [];
  try {
    const raw = localStorage.getItem(conversationHistoryKey(userEmail));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item.question === "string" && typeof item.response === "string" && typeof item.timestamp === "string")
      .slice(0, STORED_CONVERSATION_HISTORY);
  } catch {
    return [];
  }
}

function saveConversationHistory(userEmail: string, items: QuestionHistoryItem[]): void {
  if (!userEmail) return;
  localStorage.setItem(conversationHistoryKey(userEmail), JSON.stringify(items.slice(0, STORED_CONVERSATION_HISTORY)));
}

export default function App() {
  const savedEmail = localStorage.getItem("anayaa_email") || "";
  const [token, setToken] = useState<string | null>(localStorage.getItem("anayaa_jwt"));
  const [email, setEmail] = useState(savedEmail);
  const [loginEmail, setLoginEmail] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("pathway");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [questionHistory, setQuestionHistory] = useState<QuestionHistoryItem[]>(() => loadConversationHistory(savedEmail));
  const [scriptures, setScriptures] = useState<ScriptureVerse[]>([]);
  const [dailyEco, setDailyEco] = useState({ totalEnergyWh: 0, totalCo2Kg: 0, queryCount: 0 });
  const [systemStatus, setSystemStatus] = useState<{ verseCount?: number; corpusSource?: string }>({});
  const [showSessionWarning, setShowSessionWarning] = useState(false);
  const [secondsUntilExpiry, setSecondsUntilExpiry] = useState(0);
  const [refreshingSession, setRefreshingSession] = useState(false);

  const authHeaders = useCallback(
    () => ({
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    }),
    [token]
  );

  const fetchDailyEco = useCallback(async () => {
    if (!token) return;
    const res = await fetch("/api/eco/daily", { headers: authHeaders() });
    if (res.ok) {
      const data = await res.json();
      setDailyEco({
        totalEnergyWh: data.totalEnergyWh || 0,
        totalCo2Kg: data.totalCo2Kg || 0,
        queryCount: data.queryCount || 0,
      });
    }
  }, [token, authHeaders]);

  useEffect(() => {
    if (!token) return;
    fetch("/api/system/scriptures", { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => setScriptures(d.scriptures || []));
    fetch("/api/system/status", { headers: authHeaders() })
      .then((r) => r.json())
      .then(setSystemStatus);
    fetchDailyEco();
  }, [token, authHeaders, fetchDailyEco]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: loginEmail }),
    });
    const data = await res.json();
    if (!res.ok) {
      setError(data.detail || "Login failed");
      return;
    }
    localStorage.setItem("anayaa_jwt", data.token);
    localStorage.setItem("anayaa_email", data.email);
    setToken(data.token);
    setEmail(data.email);
    setLoginEmail(data.email);
    setQuery("");
    setResult(null);
    setQuestionHistory(loadConversationHistory(data.email));
    setShowSessionWarning(false);
  };

  const handleLogout = () => {
    localStorage.removeItem("anayaa_jwt");
    localStorage.removeItem("anayaa_email");
    setToken(null);
    setEmail("");
    setQuery("");
    setResult(null);
    setQuestionHistory([]);
    setShowSessionWarning(false);
    setSecondsUntilExpiry(0);
  };

  const handleContinueSession = async () => {
    if (!email) {
      handleLogout();
      return;
    }
    setRefreshingSession(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || "Could not refresh session. Please log in again.");
        handleLogout();
        return;
      }
      localStorage.setItem("anayaa_jwt", data.token);
      localStorage.setItem("anayaa_email", data.email);
      setToken(data.token);
      setEmail(data.email);
      setQuestionHistory(loadConversationHistory(data.email));
      setShowSessionWarning(false);
      setSecondsUntilExpiry(0);
    } catch {
      setError("Could not refresh session. Please log in again.");
      handleLogout();
    } finally {
      setRefreshingSession(false);
    }
  };

  useEffect(() => {
    if (!token) return;

    const updateSessionWarning = () => {
      const expiresAt = getJwtExpiryMs(token);
      if (!expiresAt) {
        handleLogout();
        return;
      }

      const remainingMs = expiresAt - Date.now();
      if (remainingMs <= 0) {
        handleLogout();
        return;
      }

      setSecondsUntilExpiry(Math.ceil(remainingMs / 1000));
      setShowSessionWarning(remainingMs <= SESSION_WARNING_MS);
    };

    updateSessionWarning();
    const timer = window.setInterval(updateSessionWarning, 1000);
    return () => window.clearInterval(timer);
  }, [token]);

  const handleQuery = async () => {
    if (!token || !query.trim()) return;
    const submittedQuestion = query.trim();
    setLoading(true);
    setError(null);
    setResult(null);
    setCurrentConversationId(null);
    try {
      const res = await fetch("/api/query", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          query: query.trim(),
          previousContext: questionHistory[0]
            ? {
                question: questionHistory[0].question,
                response: questionHistory[0].response,
              }
            : undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        const response = data.userMessage || data.error || data.detail || "Query failed";
        setError(response);
        setCurrentConversationId(recordConversation(submittedQuestion, response));
        if (data.status && data.status !== "service_unavailable") {
          setResult(data);
        }
        return;
      }
      setResult(data);
      setCurrentConversationId(recordConversation(submittedQuestion, responseText(data) || "No response text returned."));
      fetchDailyEco();
    } catch {
      const response = "Could not reach edge server.";
      setError(response);
      setCurrentConversationId(recordConversation(submittedQuestion, response));
    } finally {
      setLoading(false);
    }
  };

  const recordConversation = (question: string, response: string) => {
    const item = {
      id: `${Date.now()}`,
      question,
      response,
      timestamp: new Date().toISOString(),
    };
    setQuestionHistory((items) => {
      const next = [item, ...items].slice(0, STORED_CONVERSATION_HISTORY);
      saveConversationHistory(email, next);
      return next;
    });
    return item.id;
  };

  const handleAskAnotherQuestion = () => {
    setQuery("");
    setResult(null);
    setError(null);
    setCurrentConversationId(null);
    setActiveTab("pathway");
  };

  const handleQueryChange = (value: string) => {
    setQuery(value);
    if (result) {
      setResult(null);
      setCurrentConversationId(null);
    }
    if (error) {
      setError(null);
    }
  };

  const currentPathway = result?.moralPathway || result?.hitl?.draftPathway || "";
  const currentGuidanceSections = guidanceSections(currentPathway);
  const mainSummary = currentGuidanceSections.find((section) => section.label === "One-line summary") || currentGuidanceSections[0];
  const summaryDetails = currentGuidanceSections.filter((section) => section !== mainSummary);
  const previousConversations = questionHistory
    .filter((item) => item.id !== currentConversationId)
    .slice(0, PREVIOUS_CONVERSATION_LIMIT);
  const canSubmitQuery = query.trim().length > 0 && !result;

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <form onSubmit={handleLogin} className="bg-white p-8 rounded-3xl shadow-sm border border-[#D9D2C5] w-full max-w-md">
          <h1 className="text-2xl italic mb-2">Anayaa.AI</h1>
          <p className="text-sm text-stone-500 mb-6">Dharma-driven eco-conscious edge guidance</p>
          <input
            type="email"
            required
            value={loginEmail}
            onChange={(e) => setLoginEmail(e.target.value)}
            placeholder="your@email.com"
            className="w-full border border-[#D9D2C5] rounded-xl px-4 py-3 mb-4"
          />
          {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
          <button type="submit" className="w-full bg-[#5A5A40] text-white rounded-xl py-3">
            Enter Edge Node
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex">
      {showSessionWarning && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-6">
          <div className="w-full max-w-md rounded-3xl border border-[#D9D2C5] bg-white p-6 shadow-xl">
            <h2 className="text-xl italic text-[#5A5A40]">Session expiring soon</h2>
            <p className="mt-3 text-sm text-stone-600">
              Your session will expire in {secondsUntilExpiry} seconds. Continue to refresh your session, or cancel to log out.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={handleLogout}
                className="rounded-xl border border-[#D9D2C5] px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
              >
                Cancel
              </button>
              <button
                onClick={handleContinueSession}
                disabled={refreshingSession}
                className="rounded-xl bg-[#5A5A40] px-4 py-2 text-sm text-white disabled:opacity-60"
              >
                {refreshingSession ? "Continuing..." : "Continue"}
              </button>
            </div>
          </div>
        </div>
      )}
      <aside className="w-72 bg-[#F5F2ED] border-r border-[#D9D2C5] p-6 flex flex-col">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl italic text-[#5A5A40]">Anayaa.AI</h1>
            <p className="text-xs text-stone-500 mt-1">{email}</p>
          </div>
          <button onClick={handleLogout} className="text-xs text-stone-500 underline">
            Log out
          </button>
        </div>
        <nav className="mt-6 space-y-2">
          {(["pathway", "scriptures", "eco"] as Tab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`w-full text-left px-3 py-2 rounded-xl text-sm capitalize ${
                activeTab === tab ? "bg-white shadow-sm" : "hover:bg-white/50"
              }`}
            >
              {tab === "pathway" ? "Active Pathway" : tab === "eco" ? "Eco Audit" : "Scripture Center"}
            </button>
          ))}
        </nav>
        <div className="mt-auto pt-4 border-t border-[#D9D2C5] text-xs space-y-1">
          <p className="flex items-center gap-1 font-bold uppercase text-stone-500">
            <Leaf className="w-3 h-3 text-emerald-600" /> CodeCarbon Audit
          </p>
          <div className="flex justify-between font-mono">
            <span>Today CO₂</span>
            <span className="text-emerald-700">{dailyEco.totalCo2Kg.toFixed(8)} kg</span>
          </div>
          <div className="flex justify-between font-mono">
            <span>Today Energy</span>
            <span>{dailyEco.totalEnergyWh.toFixed(3)} Wh</span>
          </div>
          <div className="flex justify-between font-mono">
            <span>Queries</span>
            <span>{dailyEco.queryCount}</span>
          </div>
          <p className="text-[10px] text-stone-400 mt-2">
            Corpus: {systemStatus.verseCount ?? "—"} verses (google_studio seed)
          </p>
        </div>
      </aside>

      <main className="flex-1 p-8 bg-[#FBF9F6] overflow-y-auto">
        {activeTab === "pathway" && (
          <div className="grid max-w-6xl gap-6">
            <div className="space-y-6">
              <section className="rounded-2xl border border-[#D9D2C5] bg-white p-5">
                <label htmlFor="dilemma-query" className="block font-mono text-xs font-bold uppercase tracking-wider text-[#5A5A40]">
                  Share your moral dilemma
                </label>
                <p className="mt-2 text-sm text-stone-500">
                  Describe the situation you want guidance on, including the choice or conflict you are weighing.
                </p>
                <textarea
                  id="dilemma-query"
                  value={query}
                  onChange={(e) => handleQueryChange(e.target.value)}
                  rows={4}
                  placeholder="Example: I need to be honest with a close friend, but I am worried the truth will hurt them. How can I respond with compassion and integrity?"
                  className="mt-4 w-full resize-none rounded-xl border border-[#D9D2C5] bg-[#FBF9F6] p-4 text-sm outline-none focus:border-[#5A5A40]"
                />
                <div className="mt-4 flex flex-wrap items-center gap-3">
                    <button
                      onClick={handleQuery}
                      disabled={loading || !canSubmitQuery}
                      className="flex items-center gap-2 rounded-xl bg-[#5A5A40] px-5 py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                    <Sparkles className="h-4 w-4" />
                    {loading ? "Processing..." : "Submit"}
                  </button>
                  {result && (
                    <button
                      onClick={handleAskAnotherQuestion}
                      className="rounded-xl border border-[#D9D2C5] px-5 py-3 text-sm font-bold text-stone-600 hover:bg-[#FBF9F6]"
                    >
                      Ask another question
                    </button>
                  )}
                  <span className="font-mono text-xs uppercase tracking-wider text-stone-400">
                    Local scripture retrieval + synthesis
                  </span>
                </div>
              </section>
              {error && <p className="text-red-600">{error}</p>}

              {result && (
                <div className="space-y-5">
                  {(["retrieval_unavailable", "insufficient_context", "quality_threshold_not_met"].includes(result.status || "")) && result.userMessage && (
                    <section className="rounded-2xl border border-amber-200 bg-amber-50 p-6">
                      <h3 className="mb-2 font-bold text-amber-900">
                        {resultStatusTitle(result.status)}
                      </h3>
                      <p className="text-sm text-amber-900">{result.userMessage}</p>
                      {result.status === "insufficient_context" && result.topRetrievalScore !== undefined && (
                        <p className="mt-3 font-mono text-xs text-amber-800">
                          Top retrieval score: {result.topRetrievalScore} (minimum required: {result.contextThreshold ?? "—"})
                        </p>
                      )}
                    </section>
                  )}

                  {currentPathway && result.status !== "insufficient_context" && result.status !== "quality_threshold_not_met" && (
                    <section className="relative rounded-2xl border-2 border-[#5A5A40] bg-white p-6 shadow-sm">
                      <div className="absolute left-1/2 top-0 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#5A5A40] px-4 py-1 font-mono text-[10px] font-bold uppercase tracking-wider text-white">
                        Answer
                      </div>
                      <p className="mt-2 flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-[#5A5A40]">
                        <Sparkles className="h-3 w-3" /> Scripture-grounded guidance
                      </p>
                      <h2 className="mt-3 text-2xl italic text-stone-800">A clear path forward</h2>
                      <div className="mt-5">
                        <div className="rounded-xl border border-[#D9D2C5] bg-[#FBF9F6] p-4">
                          <h3 className="border-b border-[#D9D2C5] pb-3 font-mono text-xs font-bold uppercase tracking-wider text-stone-700">
                            Summary
                          </h3>
                          <div className="mt-4 text-stone-800">
                            {mainSummary && (
                              <p className="text-base leading-7">{mainSummary.text}</p>
                            )}
                            {summaryDetails.length > 0 && (
                              <div className="mt-5 divide-y divide-[#E5DED2]">
                                {summaryDetails.map((section, index) => (
                                  <div key={`${section.label || "detail"}-${section.text}-${index}`} className="py-3 first:pt-0 last:pb-0">
                                    {section.label && (
                                      <p className="text-sm font-semibold text-[#5A5A40]">
                                        {section.label}
                                      </p>
                                    )}
                                    <p className="mt-1 text-sm leading-6">{section.text}</p>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </section>
                  )}

                {result.citations && result.citations.length > 0 && (
                  <section className="bg-white rounded-3xl p-6 border border-[#D9D2C5]">
                    <h3 className="font-bold mb-3 flex items-center gap-2">
                      <BookOpen className="w-4 h-4" /> Scripture Evidence
                    </h3>
                    {result.citations.map((c) => (
                      <div key={c.id} className="mb-4 pb-4 border-b border-stone-100 last:border-0">
                        <p className="text-xs font-bold text-[#5A5A40]">
                          {c.faith} — {c.source} {c.chapter}:{c.verse}
                        </p>
                        <p className="text-sm italic mt-1">"{c.translation}"</p>
                      </div>
                    ))}
                  </section>
                )}

              </div>
            )}

              {previousConversations.length > 0 && (
                <section className="bg-white rounded-3xl p-6 border border-[#D9D2C5]">
                  <h3 className="font-bold mb-4">Previous Conversation</h3>
                  <div className="space-y-4">
                    {previousConversations.map((item) => {
                      const responseSections = guidanceSections(item.response);
                      const historyMainSummary = responseSections.find((section) => section.label === "One-line summary") || responseSections[0];
                      const historyDetails = responseSections.filter((section) => section !== historyMainSummary);
                      return (
                        <article key={item.id} className="rounded-xl border border-[#D9D2C5] bg-[#FBF9F6] p-4">
                          <p className="font-mono text-[10px] uppercase tracking-wider text-stone-400">
                            {new Date(item.timestamp).toLocaleString()}
                          </p>
                          <div className="mt-3">
                            <p className="font-mono text-xs font-bold uppercase tracking-wider text-[#5A5A40]">Question</p>
                            <p className="mt-2 text-sm leading-6 text-stone-800">{item.question}</p>
                          </div>
                          <div className="mt-4">
                            <p className="font-mono text-xs font-bold uppercase tracking-wider text-[#5A5A40]">Response</p>
                            <div className="mt-2 text-sm leading-6 text-stone-800">
                              {historyMainSummary && <p>{historyMainSummary.text}</p>}
                              {historyDetails.length > 0 && (
                                <div className="mt-3 divide-y divide-[#E5DED2]">
                                  {historyDetails.map((section, index) => (
                                    <div key={`${item.id}-response-${index}`} className="py-2 first:pt-0 last:pb-0">
                                      {section.label && (
                                        <p className="text-sm font-semibold text-[#5A5A40]">
                                          {section.label}
                                        </p>
                                      )}
                                      <p className="mt-1">{section.text}</p>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </section>
              )}
            </div>
          </div>
        )}

        {activeTab === "scriptures" && (
          <div className="grid gap-4 md:grid-cols-2">
            {scriptures.map((s) => (
              <div key={s.id} className="bg-white rounded-2xl p-4 border border-[#D9D2C5]">
                <p className="text-xs font-bold text-[#5A5A40]">{s.faith} — {s.source}</p>
                <p className="text-sm font-semibold">{s.chapter} {s.verse}</p>
                <p className="text-sm italic mt-2">"{s.translation}"</p>
              </div>
            ))}
          </div>
        )}

        {activeTab === "eco" && (
          <div className="max-w-3xl space-y-5">
            <section className="bg-white rounded-3xl p-8 border border-[#D9D2C5]">
              <h2 className="text-xl italic mb-4">Daily Cumulative Eco Audit</h2>
              <div className="space-y-3 font-mono text-sm">
                <div className="flex justify-between"><span>Total Energy</span><span>{dailyEco.totalEnergyWh.toFixed(4)} Wh</span></div>
                <div className="flex justify-between"><span>Total CO₂</span><span>{dailyEco.totalCo2Kg.toFixed(8)} kg</span></div>
                <div className="flex justify-between"><span>Queries Today</span><span>{dailyEco.queryCount}</span></div>
              </div>
            </section>

            {result?.powerMetrics && (
              <section className="bg-white rounded-3xl p-6 border border-[#D9D2C5]">
                <h3 className="font-bold mb-2 flex items-center gap-2">
                  <Leaf className="w-4 h-4 text-emerald-600" /> Per-Request Eco Metrics
                </h3>
                <div className="grid grid-cols-2 gap-2 text-sm font-mono">
                  <span>Energy</span><span>{(result.powerMetrics.energyMWh / 1000).toFixed(6)} Wh</span>
                  <span>CO₂</span><span>{result.powerMetrics.co2Kg.toFixed(8)} kg</span>
                  <span>CPU/GPU</span><span>{result.powerMetrics.cpuWatts}W / {result.powerMetrics.gpuWatts}W</span>
                  <span>Cache</span><span>{result.cacheHit ? "HIT" : "MISS"}</span>
                </div>
                {result.ecoBreakdown && (
                  <table className="w-full mt-4 text-xs">
                    <thead><tr><th className="text-left">Stage</th><th>Wh</th><th>CO₂ kg</th></tr></thead>
                    <tbody>
                      {result.ecoBreakdown.map((s) => (
                        <tr key={s.stage}><td>{s.stage}</td><td>{s.energyWh.toFixed(6)}</td><td>{s.co2Kg.toFixed(8)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>
            )}

            {result?.auditScores && (
              <section className="bg-white rounded-3xl p-6 border border-[#D9D2C5]">
                <h3 className="font-bold mb-2 flex items-center gap-2">
                  <Shield className="w-4 h-4" /> G-Eval Audit
                </h3>
                <p className={`text-sm font-bold ${result.auditScores.passed ? "text-emerald-700" : "text-amber-700"}`}>
                  {result.auditScores.passed ? "PASSED" : "NEEDS REVIEW"}
                </p>
                <div className="grid grid-cols-2 gap-2 mt-2 text-sm">
                  {Object.entries(result.auditScores.scores).map(([k, v]) => (
                    <div key={k} className="flex justify-between"><span>{k}</span><span>{v}/5</span></div>
                  ))}
                </div>
                <p className="text-xs text-stone-500 mt-2">{result.auditScores.rationale}</p>
              </section>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
