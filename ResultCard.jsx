// One search result: title, score, snippet and feedback buttons.
export default function ResultCard({ result, mark, onMark, onOpen, showFeedback }) {
  return (
    <div className={"result " + (mark || "")}>
      <div className="result-top">
        <button className="title" onClick={() => onOpen(result)}>
          {result.title}
        </button>
        <span className="score" title="cosine tf-idf score">
          score {result.score.toFixed(4)}
        </span>
      </div>
      <p className="snippet">{result.snippet}</p>
      <div className="result-bottom">
        <span className="file">{result.filename}</span>
        {showFeedback && (
          <span className="feedback">
            <button
              className={mark === "relevant" ? "on" : ""}
              onClick={() => onMark(result.id, "relevant")}
            >
              Relevant
            </button>
            <button
              className={mark === "nonrelevant" ? "on" : ""}
              onClick={() => onMark(result.id, "nonrelevant")}
            >
              Not relevant
            </button>
          </span>
        )}
      </div>
    </div>
  );
}
