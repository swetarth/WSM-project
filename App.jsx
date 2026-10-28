import { useState } from "react";
import ResultCard from "./ResultCard.jsx";

async function post(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Something went wrong");
  return data;
}

export default function App() {
  const [tab, setTab] = useState("basic");

  // ---- basic (boolean) ----
  const [boolQuery, setBoolQuery] = useState("");

  // ---- advanced ----
  const [advQuery, setAdvQuery] = useState("");
  const [options, setOptions] = useState({
    soundex: false,
    thesaurus: true,
    query_log: false,
    pseudo_feedback: false,
    click_feedback: false,
    feedback_method: "rocchio",
  });
  const [marks, setMarks] = useState({}); // {docId: "relevant" | "nonrelevant"}

  // ---- shared ----
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [stats, setStats] = useState(null);
  const [openDoc, setOpenDoc] = useState(null);
  const [lastQuery, setLastQuery] = useState("");

  const toggle = (name) => setOptions({ ...options, [name]: !options[name] });

  async function runBoolean(e) {
    e.preventDefault();
    setError("");
    try {
      setData(await post("/api/boolean", { query: boolQuery }));
      setLastQuery(boolQuery);
    } catch (err) {
      setData(null);
      setError(err.message);
    }
  }

  async function runAdvanced(e, useMarks = false) {
    if (e) e.preventDefault();
    setError("");
    const m = useMarks ? marks : {};
    if (!useMarks) setMarks({});
    try {
      const result = await post("/api/advanced", {
        query: advQuery,
        options,
        relevant: Object.keys(m).filter((id) => m[id] === "relevant").map(Number),
        nonrelevant: Object.keys(m).filter((id) => m[id] === "nonrelevant").map(Number),
      });
      setData(result);
      setLastQuery(advQuery);
    } catch (err) {
      setData(null);
      setError(err.message);
    }
  }

  function mark(id, kind) {
    setMarks({ ...marks, [id]: marks[id] === kind ? undefined : kind });
  }

  async function openDocument(result) {
    const res = await fetch("/api/documents/" + result.id);
    setOpenDoc(await res.json());
    // a click is "indirect relevance feedback"
    post("/api/click", { query: lastQuery, doc_id: result.id });
  }

  async function showStats() {
    setTab("stats");
    setStats(await (await fetch("/api/stats")).json());
  }

  function switchTab(name) {
    setTab(name);
    setData(null);
    setError("");
  }

  const hasMarks = Object.values(marks).some(Boolean);

  return (
    <div className="page">
      <header>
        <h1>Mini Search Engine</h1>
        <p>15 documents on information retrieval, searched with the methods from WSM.</p>
      </header>

      <nav className="tabs">
        <button className={tab === "basic" ? "active" : ""} onClick={() => switchTab("basic")}>
          Basic search
        </button>
        <button className={tab === "advanced" ? "active" : ""} onClick={() => switchTab("advanced")}>
          Advanced search
        </button>
        <button className={tab === "stats" ? "active" : ""} onClick={showStats}>
          Index and compression
        </button>
      </nav>

      {tab === "basic" && (
        <form onSubmit={runBoolean} className="box">
          <label>Boolean query</label>
          <div className="row">
            <input
              value={boolQuery}
              onChange={(e) => setBoolQuery(e.target.value)}
              placeholder='query AND (expansion OR feedback) NOT thesaurus'
            />
            <button type="submit">Search</button>
          </div>
          <small>
            Use AND, OR, NOT and brackets. Put words in quotes for a phrase: "relevance feedback".
            Upper or lower case both work.
          </small>
        </form>
      )}

      {tab === "advanced" && (
        <form onSubmit={runAdvanced} className="box">
          <label>Ranked query</label>
          <div className="row">
            <input
              value={advQuery}
              onChange={(e) => setAdvQuery(e.target.value)}
              placeholder='search recall  or  "query expansion"'
            />
            <button type="submit">Search</button>
          </div>
          <div className="options">
            <label><input type="checkbox" checked={options.soundex} onChange={() => toggle("soundex")} /> Soundex (sounds-like words)</label>
            <label><input type="checkbox" checked={options.thesaurus} onChange={() => toggle("thesaurus")} /> Thesaurus expansion</label>
            <label><input type="checkbox" checked={options.query_log} onChange={() => toggle("query_log")} /> Query log expansion</label>
            <label><input type="checkbox" checked={options.pseudo_feedback} onChange={() => toggle("pseudo_feedback")} /> Pseudo relevance feedback</label>
            <label><input type="checkbox" checked={options.click_feedback} onChange={() => toggle("click_feedback")} /> Use past clicks (indirect feedback)</label>
            <label>
              Feedback method{" "}
              <select
                value={options.feedback_method}
                onChange={(e) => setOptions({ ...options, feedback_method: e.target.value })}
              >
                <option value="rocchio">Rocchio</option>
                <option value="probabilistic">Probabilistic</option>
              </select>
            </label>
          </div>
          <small>
            Put a phrase in quotes to filter by it. After searching, mark results as relevant or not relevant
            and press "Search again with my feedback".
          </small>
        </form>
      )}

      {error && <div className="error">{error}</div>}

      {data && (
        <section>
          <p className="summary">
            {data.total} result{data.total === 1 ? "" : "s"}
            {data.mode === "advanced" && data.total > 10 ? " (top 10 shown)" : ""}
          </p>

          {(data.info.steps.length > 0 || Object.keys(data.info.expanded_terms).length > 0) && (
            <div className="info">
              {data.info.steps.map((s, i) => <div key={i}>{s}</div>)}
              {Object.keys(data.info.expanded_terms).length > 0 && (
                <div className="chips">
                  Added terms:
                  {Object.entries(data.info.expanded_terms).map(([term, why]) => (
                    <span key={term} className="chip" title={why}>{term}</span>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === "advanced" && hasMarks && (
            <button className="again" onClick={() => runAdvanced(null, true)}>
              Search again with my feedback
            </button>
          )}

          {data.results.map((r) => (
            <ResultCard
              key={r.id}
              result={r}
              mark={marks[r.id]}
              onMark={mark}
              onOpen={openDocument}
              showFeedback={tab === "advanced"}
            />
          ))}

          {data.suggestions.length > 0 && (
            <div className="suggest">
              Others searched:
              {data.suggestions.map((s) => (
                <button key={s} onClick={() => setAdvQuery(s)}>{s}</button>
              ))}
            </div>
          )}
        </section>
      )}

      {tab === "stats" && stats && (
        <section className="stats">
          <p>
            {stats.documents} documents, {stats.terms} distinct terms, {stats.postings} postings,{" "}
            {stats.biwords} biwords.
          </p>
          <table>
            <thead>
              <tr><th></th><th>Before</th><th>After</th><th>Saved</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>Dictionary (string + blocks of {stats.dictionary.block_size})</td>
                <td>{stats.dictionary.fixed_width_bytes} B</td>
                <td>{stats.dictionary.compressed_bytes} B</td>
                <td>{stats.dictionary.saving_percent}%</td>
              </tr>
              <tr>
                <td>Postings (gaps + variable byte)</td>
                <td>{stats.postings_size.raw_bytes} B</td>
                <td>{stats.postings_size.compressed_bytes} B</td>
                <td>{stats.postings_size.saving_percent}%</td>
              </tr>
            </tbody>
          </table>
        </section>
      )}

      {openDoc && (
        <div className="modal" onClick={() => setOpenDoc(null)}>
          <div className="modal-body" onClick={(e) => e.stopPropagation()}>
            <h2>{openDoc.title}</h2>
            <p>{openDoc.text}</p>
            <button onClick={() => setOpenDoc(null)}>Close</button>
          </div>
        </div>
      )}
    </div>
  );
}
