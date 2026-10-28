"""
app.py - Flask API. Run with:  python app.py
"""
from flask import Flask, jsonify, request

from engine import SearchEngine

app = Flask(__name__)
engine = SearchEngine()


@app.after_request
def allow_frontend(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.get("/api/documents")
def list_documents():
    return jsonify([{"id": d["id"], "title": d["title"], "filename": d["filename"]}
                    for d in engine.docs])


@app.get("/api/documents/<int:doc_id>")
def get_document(doc_id):
    if doc_id < 0 or doc_id >= engine.n_docs:
        return jsonify({"error": "Document not found"}), 404
    return jsonify(engine.docs[doc_id])


@app.post("/api/boolean")
def boolean_search():
    data = request.get_json(force=True)
    try:
        return jsonify(engine.boolean_search(data.get("query", "")))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@app.post("/api/advanced")
def advanced_search():
    data = request.get_json(force=True)
    try:
        return jsonify(engine.advanced_search(
            data.get("query", ""),
            data.get("options", {}),
            data.get("relevant", []),
            data.get("nonrelevant", []),
        ))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@app.post("/api/click")
def click():
    data = request.get_json(force=True)
    engine.record_click(data.get("query", ""), data.get("doc_id"))
    return jsonify({"ok": True})


@app.get("/api/suggest")
def suggest():
    return jsonify(engine.suggestions(request.args.get("q", "")))


@app.get("/api/stats")
def stats():
    return jsonify(engine.stats())


if __name__ == "__main__":
    app.run(port=5000, debug=True)
