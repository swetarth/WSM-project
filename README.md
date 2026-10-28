# Mini Search Engine (WSM project)

Python (Flask) backend + React (Vite) frontend. The 15 sample documents live in
`search-engine/backend/documents/`. Add `.txt` files there with the first line as
the title, then restart the backend.

## Run it

Install the frontend and backend dependencies from the project root:

    npm install
    python -m pip install -r requirements.txt

Start the backend in one terminal:

    python app.py            # http://127.0.0.1:5000

Start the frontend in another terminal:

    npm run dev              # open the address it prints (http://localhost:5173)

## Syllabus topic -> where it is in the code

| Topic | File / function |
|---|---|
| Lowercasing | `engine.py` tokenize() |
| Inverted index, positions | `engine.py` build_index() |
| Boolean search (AND OR NOT, brackets) | `engine.py` BooleanParser |
| Biword + phrase search | `engine.py` phrase_docs() |
| Soundex | `engine.py` soundex(), advanced_search() step 2 |
| Thesaurus (manual) | `thesaurus.json`, advanced_search() step 3 |
| Dictionary compression | `compression.py` CompressedDictionary |
| Postings compression | `compression.py` encode_postings() |
| Ranking and score | `engine.py` rank() (tf-idf cosine) |
| Rocchio relevance feedback | `engine.py` rocchio() |
| Probabilistic relevance feedback | `engine.py` probabilistic() |
| Pseudo relevance feedback | advanced_search() step 5 |
| Indirect feedback (clicks) | record_click(), "Use past clicks" |
| Query log mining | mine_query_log(), suggestions() |

## Try these

- Basic: `query AND (expansion OR feedback) NOT thesaurus`, `"inverted index construction"`
- Advanced: `Rupert` with Soundex (finds the Robert document), `relevence feedbak` with Soundex,
  `search recall` with Thesaurus + Pseudo feedback, then mark results and search again.
- Click a result title a few times for `rocchio`, then search `rocchio` with "Use past clicks".
