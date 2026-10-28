"""
engine.py  -  a small search engine for the WSM course.

Everything is kept in plain Python dicts / lists so it is easy to read.

Features (search for the heading to find the code):
  * lowercasing + tokenizing                  -> tokenize()
  * inverted index with positions             -> build_index()
  * biword index, phrase search               -> phrase_docs()
  * boolean search (AND OR NOT, brackets)     -> BooleanParser
  * soundex                                   -> soundex()
  * thesaurus (manual) query expansion        -> advanced_search()
  * dictionary + postings compression         -> compression.py
  * tf-idf cosine ranking with scores         -> rank()
  * Rocchio + probabilistic relevance feedback-> rocchio(), probabilistic()
  * pseudo relevance feedback                 -> advanced_search()
  * indirect feedback (clicks)                -> record_click()
  * query log mining                          -> mine_query_log()
"""
import json
import math
import os
import re
from collections import Counter, defaultdict

from compression import CompressedDictionary, encode_postings, decode_postings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "documents")
if not os.path.isdir(DOCS_DIR):
    DOCS_DIR = os.path.join(BASE_DIR, "search-engine", "backend", "documents")
LOG_FILE = os.path.join(BASE_DIR, "query_log.json")
CLICK_FILE = os.path.join(BASE_DIR, "clicks.json")
THESAURUS_FILE = os.path.join(BASE_DIR, "thesaurus.json")

SEED_QUERIES = [
    "relevance feedback rocchio", "query expansion thesaurus",
    "query expansion synonyms", "relevance feedback precision recall",
    "soundex phonetic names", "phrase search positional index",
    "dictionary compression blocking", "query log suggestions",
    "pseudo relevance feedback", "thesaurus expansion recall",
]


# ------------------------------------------------------------------
# Text processing
# ------------------------------------------------------------------
def tokenize(text):
    """LOWERCASING happens here: 'Search' and 'search' become the same token."""
    return re.findall(r"[a-z0-9]+", text.lower())


def soundex(word):
    """First letter + 3 digits. Robert -> R163, Rupert -> R163."""
    word = word.upper()
    codes = {}
    for letters, digit in [("BFPV", "1"), ("CGJKQSXZ", "2"), ("DT", "3"),
                           ("L", "4"), ("MN", "5"), ("R", "6")]:
        for ch in letters:
            codes[ch] = digit
    result = word[0]
    last = codes.get(word[0], "")
    for ch in word[1:]:
        code = codes.get(ch, "")
        if code and code != last:
            result += code
        if ch not in "HW":          # H and W do not break a run of same codes
            last = code
    return (result + "000")[:4]


# ------------------------------------------------------------------
# Boolean query parser:   OR  <  AND  <  NOT  <  ( ) / "phrase" / word
# ------------------------------------------------------------------
class BooleanParser:
    def __init__(self, engine, query):
        self.engine = engine
        self.tokens = re.findall(r'"[^"]*"|\(|\)|[^\s()"]+', query)
        self.pos = 0
        self.terms = []        # positive terms (used for scoring)
        self.notes = []        # explanation shown in the UI
        self.negated = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self):
        token = self.peek()
        self.pos += 1
        return token

    def parse(self):
        if not self.tokens:
            raise ValueError("Please type a query")
        result = self.parse_or()
        if self.pos < len(self.tokens):
            raise ValueError("Unexpected ')' in query")
        return result

    def parse_or(self):
        result = self.parse_and()
        while self.peek() and self.peek().upper() == "OR":
            self.next()
            result = result | self.parse_and()
        return result

    def parse_and(self):
        result = self.parse_not()
        # a missing operator between two terms means AND
        while self.peek() and self.peek() != ")" and self.peek().upper() != "OR":
            if self.peek().upper() == "AND":
                self.next()
            result = result & self.parse_not()
        return result

    def parse_not(self):
        if self.peek() and self.peek().upper() == "NOT":
            self.next()
            self.negated += 1
            inner = self.parse_not()
            self.negated -= 1
            return set(range(self.engine.n_docs)) - inner
        return self.parse_atom()

    def parse_atom(self):
        token = self.next()
        if token is None:
            raise ValueError("The query ended unexpectedly (missing a term?)")
        if token == "(":
            result = self.parse_or()
            if self.next() != ")":
                raise ValueError("Missing closing bracket ')'")
            return result
        if token == ")":
            raise ValueError("Unexpected ')' in query")

        if token.startswith('"'):                       # phrase search
            words = tokenize(token)
            docs, method = self.engine.phrase_docs(words)
            self.notes.append(f'Phrase "{" ".join(words)}" answered with the {method}')
            if not self.negated:
                self.terms.extend(words)
            return docs

        words = tokenize(token)                         # normal word
        if not words:
            return set()
        word = words[0]
        if token != word:
            self.notes.append(f"Lowercased '{token}' -> '{word}'")
        if not self.negated:
            self.terms.append(word)
        return self.engine.term_docs(word)


# ------------------------------------------------------------------
# The search engine
# ------------------------------------------------------------------
class SearchEngine:
    def __init__(self):
        self.load_documents()
        self.build_index()
        self.load_thesaurus()
        self.load_logs()

    # ---------------- loading ----------------
    def load_documents(self):
        self.docs = []
        for filename in sorted(os.listdir(DOCS_DIR)):
            if not filename.endswith(".txt"):
                continue
            with open(os.path.join(DOCS_DIR, filename), encoding="utf-8") as f:
                lines = f.read().strip().split("\n", 1)
            self.docs.append({
                "id": len(self.docs),
                "filename": filename,
                "title": lines[0].strip(),
                "text": lines[1].strip() if len(lines) > 1 else "",
            })
        self.n_docs = len(self.docs)

    def load_thesaurus(self):
        """Manual thesaurus: every word in a group is a synonym of the others."""
        self.thesaurus = defaultdict(list)
        with open(THESAURUS_FILE, encoding="utf-8") as f:
            groups = json.load(f)["groups"]
        for group in groups:
            for word in group:
                for other in group:
                    if other != word:
                        self.thesaurus[word].append(other)

    def load_logs(self):
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE) as f:
                self.query_log = json.load(f)
        else:
            self.query_log = list(SEED_QUERIES)
            self.save(LOG_FILE, self.query_log)
        if os.path.exists(CLICK_FILE):
            with open(CLICK_FILE) as f:
                self.clicks = json.load(f)
        else:
            self.clicks = {}          # {"normalized query": {"doc id": count}}

    @staticmethod
    def save(path, data):
        with open(path, "w") as f:
            json.dump(data, f)

    # ---------------- indexing ----------------
    def build_index(self):
        positional = defaultdict(lambda: defaultdict(list))   # term -> doc -> [positions]
        self.biword = defaultdict(set)                         # "w1 w2" -> {docs}
        for doc in self.docs:
            tokens = tokenize(doc["title"] + " " + doc["text"])
            for position, term in enumerate(tokens):
                positional[term][doc["id"]].append(position)
            for i in range(len(tokens) - 1):
                self.biword[tokens[i] + " " + tokens[i + 1]].add(doc["id"])
        self.positional = {t: dict(d) for t, d in positional.items()}

        # compressed dictionary + compressed postings (doc ids only)
        self.terms = sorted(self.positional)
        self.dictionary = CompressedDictionary(self.terms, k=4)
        self.postings = [encode_postings(self.positional[t].keys()) for t in self.terms]

        # soundex index: code -> terms
        self.soundex_index = defaultdict(list)
        for term in self.terms:
            if term.isalpha():
                self.soundex_index[soundex(term)].append(term)

        # tf-idf vectors (lnc.ltc style, length normalised)
        self.idf = {t: math.log10(self.n_docs / len(d)) for t, d in self.positional.items()}
        self.doc_vectors = []
        for doc in self.docs:
            counts = Counter(tokenize(doc["title"] + " " + doc["text"]))
            vec = {t: (1 + math.log10(c)) * self.idf[t] for t, c in counts.items()}
            self.doc_vectors.append(self.normalize(vec))

    @staticmethod
    def normalize(vec):
        length = math.sqrt(sum(w * w for w in vec.values()))
        if length == 0:
            return vec
        return {t: w / length for t, w in vec.items()}

    # ---------------- lookups ----------------
    def term_docs(self, term):
        """Docs containing a term: dictionary lookup -> decode compressed postings."""
        term_id = self.dictionary.lookup(term)
        if term_id == -1:
            return set()
        return set(decode_postings(self.postings[term_id]))

    def phrase_docs(self, words):
        """Returns (docs, method_used)."""
        if not words:
            return set(), "empty phrase"
        if len(words) == 1:
            return self.term_docs(words[0]), "inverted index"
        if len(words) == 2:
            return set(self.biword.get(" ".join(words), set())), "biword index"
        docs = self.term_docs(words[0])
        for word in words[1:]:
            docs = docs & self.term_docs(word)
        matched = set()
        for doc_id in docs:
            for start in self.positional[words[0]][doc_id]:
                if all(start + i in self.positional[w][doc_id]
                       for i, w in enumerate(words) if i > 0):
                    matched.add(doc_id)
                    break
        return matched, "positional index"

    # ---------------- ranking ----------------
    def query_vector(self, weights):
        vec = {t: w * self.idf[t] for t, w in weights.items() if t in self.idf}
        return self.normalize(vec)

    def rank(self, vec, allowed=None):
        """Cosine score of every allowed doc. Returns [(doc_id, score)] best first."""
        candidates = range(self.n_docs) if allowed is None else allowed
        scored = []
        for doc_id in candidates:
            dv = self.doc_vectors[doc_id]
            scored.append((doc_id, sum(w * dv.get(t, 0.0) for t, w in vec.items())))
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored

    def snippet(self, doc_id, terms):
        sentences = re.split(r"(?<=[.!?])\s+", self.docs[doc_id]["text"])
        for sentence in sentences:
            if any(t in tokenize(sentence) for t in terms):
                return sentence
        return sentences[0]

    def format_results(self, ranked, terms, limit=None):
        results = []
        for doc_id, score in ranked[:limit]:
            doc = self.docs[doc_id]
            results.append({
                "id": doc_id,
                "title": doc["title"],
                "filename": doc["filename"],
                "score": round(score, 4),
                "snippet": self.snippet(doc_id, terms),
            })
        return results

    # ---------------- 1) basic boolean search ----------------
    def boolean_search(self, query):
        parser = BooleanParser(self, query)
        matched = parser.parse()
        counts = Counter(parser.terms)
        vec = self.query_vector({t: 1 + math.log10(c) for t, c in counts.items()})
        ranked = self.rank(vec, allowed=matched)
        return {
            "mode": "boolean",
            "total": len(ranked),
            "results": self.format_results(ranked, list(counts)),
            "info": {"steps": parser.notes, "expanded_terms": {}},
            "suggestions": [],
        }

    # ---------------- relevance feedback ----------------
    def rocchio(self, qvec, relevant, nonrelevant, alpha=1.0, beta=0.75, gamma=0.15, n_new=6):
        """q_new = alpha*q + beta*mean(relevant docs) - gamma*mean(non-relevant docs)"""
        new = defaultdict(float)
        for t, w in qvec.items():
            new[t] += alpha * w
        for doc_id in relevant:
            for t, w in self.doc_vectors[doc_id].items():
                new[t] += beta * w / len(relevant)
        for doc_id in nonrelevant:
            for t, w in self.doc_vectors[doc_id].items():
                new[t] -= gamma * w / len(nonrelevant)
        new = {t: w for t, w in new.items() if w > 0}       # drop negative weights
        added = sorted((t for t in new if t not in qvec), key=lambda t: -new[t])[:n_new]
        keep = set(qvec) | set(added)
        return self.normalize({t: w for t, w in new.items() if t in keep}), added

    def probabilistic(self, qvec, relevant, n_new=6):
        """
        Binary independence model feedback.
        p = P(term in doc | relevant)      u = P(term in doc | non-relevant)
        term weight c = log( p(1-u) / (u(1-p)) )
        """
        R, N = len(relevant), self.n_docs
        c = {}
        for t in {t for d in relevant for t in self.doc_vectors[d]}:
            vr = sum(1 for d in relevant if t in self.doc_vectors[d])
            df = len(self.positional[t])
            p = (vr + 0.5) / (R + 1)
            u = (df - vr + 0.5) / (N - R + 1)
            weight = math.log10((p * (1 - u)) / (u * (1 - p)))
            if weight > 0:
                c[t] = weight
        added = sorted((t for t in c if t not in qvec), key=lambda t: -c[t])[:n_new]
        new = dict(qvec)
        top = max(c.values()) if c else 1
        for t in added:
            new[t] = 0.5 * c[t] / top
        return self.normalize(new), added

    # ---------------- query log mining + indirect feedback ----------------
    @staticmethod
    def normalize_query(query):
        return " ".join(tokenize(query))

    def log_query(self, query):
        self.query_log.append(query)
        self.save(LOG_FILE, self.query_log)

    def mine_query_log(self, words, top=3):
        """Terms that often appear in the same past query as the user's words."""
        together = Counter()
        for past in self.query_log:
            past_terms = tokenize(past)
            if any(w in past_terms for w in words):
                for t in past_terms:
                    if t not in words and t in self.idf:
                        together[t] += 1
        return [t for t, _ in together.most_common(top)]

    def suggestions(self, query, top=5):
        words = set(tokenize(query))
        current = self.normalize_query(query)
        found = Counter()
        for past in self.query_log:
            key = self.normalize_query(past)
            if key != current and words & set(key.split()):
                found[key] += 1
        return [q for q, _ in found.most_common(top)]

    def record_click(self, query, doc_id):
        key = self.normalize_query(query)
        counts = self.clicks.setdefault(key, {})
        counts[str(doc_id)] = counts.get(str(doc_id), 0) + 1
        self.save(CLICK_FILE, self.clicks)

    # ---------------- 2) advanced search ----------------
    def advanced_search(self, query, options, relevant_ids=None, nonrelevant_ids=None):
        relevant_ids = list(relevant_ids or [])
        nonrelevant_ids = list(nonrelevant_ids or [])
        steps = []
        expanded = {}                         # term -> reason (shown in the UI)

        # 1. split phrases from normal words, lowercase everything
        phrases = re.findall(r'"([^"]*)"', query)
        words = tokenize(re.sub(r'"[^"]*"', " ", query))
        if not words and not phrases:
            raise ValueError("Please type a query")
        if query != query.lower():
            steps.append("Lowercased the query")
        base = Counter(words)
        allowed = None
        for phrase in phrases:
            p_words = tokenize(phrase)
            docs, method = self.phrase_docs(p_words)
            allowed = docs if allowed is None else allowed & docs
            base.update(p_words)
            steps.append(f'Phrase "{" ".join(p_words)}": {len(docs)} doc(s) via {method}')
        weights = {t: 1 + math.log10(c) for t, c in base.items()}

        # 2. soundex: add words that sound like the query words
        if options.get("soundex"):
            for w in words:
                if not w.isalpha():
                    continue
                similar = [t for t in self.soundex_index.get(soundex(w), []) if t != w][:5]
                boost = 0.4 if w in self.idf else 1.0   # unknown word = probably misspelt
                for t in similar:
                    if t not in weights:
                        weights[t], expanded[t] = boost, f"soundex of '{w}' ({soundex(w)})"

        # 3. thesaurus
        if options.get("thesaurus"):
            for w in words:
                for syn in self.thesaurus.get(w, []):
                    if syn in self.idf and syn not in weights:
                        weights[syn], expanded[syn] = 0.5, f"thesaurus synonym of '{w}'"

        # 4. query log mining
        if options.get("query_log"):
            for t in self.mine_query_log(words):
                if t not in weights:
                    weights[t], expanded[t] = 0.3, "often searched together (query log)"

        qvec = self.query_vector(weights)
        ranked = self.rank(qvec, allowed)

        # 5. which documents are "relevant" for feedback?
        source = ""
        if relevant_ids or nonrelevant_ids:
            source = "the documents you marked"
        elif options.get("click_feedback"):
            clicked = self.clicks.get(self.normalize_query(query), {})
            relevant_ids = [int(d) for d, _ in sorted(clicked.items(), key=lambda x: -x[1])][:3]
            if relevant_ids:
                source = "past clicks (indirect feedback)"
        if not source and options.get("pseudo_feedback"):
            relevant_ids = [d for d, s in ranked[:3] if s > 0]
            source = "top 3 results assumed relevant (pseudo feedback)"

        # 6. apply feedback and rank again
        if relevant_ids or nonrelevant_ids:
            method = options.get("feedback_method", "rocchio")
            if method == "probabilistic" and relevant_ids:
                qvec, added = self.probabilistic(qvec, relevant_ids)
            else:
                qvec, added = self.rocchio(qvec, relevant_ids, nonrelevant_ids)
                method = "rocchio"
            for t in added:
                expanded[t] = f"{method} feedback"
            steps.append(f"Feedback from {source}: re-ranked with {method}, added {len(added)} term(s)")
            ranked = self.rank(qvec, allowed)

        ranked = [(d, s) for d, s in ranked if s > 0]
        self.log_query(query)
        return {
            "mode": "advanced",
            "total": len(ranked),
            "results": self.format_results(ranked, list(weights), limit=10),
            "info": {"steps": steps, "expanded_terms": expanded},
            "suggestions": self.suggestions(query),
        }

    # ---------------- index statistics (compression) ----------------
    def stats(self):
        longest = max(len(t) for t in self.terms)
        fixed_width = len(self.terms) * longest
        compressed_dict = self.dictionary.size_in_bytes()
        n_postings = sum(len(d) for d in self.positional.values())
        raw_postings = 4 * n_postings                      # 4 byte int per doc id
        compressed_postings = sum(len(p) for p in self.postings)
        return {
            "documents": self.n_docs,
            "terms": len(self.terms),
            "postings": n_postings,
            "biwords": len(self.biword),
            "dictionary": {
                "fixed_width_bytes": fixed_width,
                "compressed_bytes": compressed_dict,
                "block_size": self.dictionary.k,
                "saving_percent": round(100 * (1 - compressed_dict / fixed_width), 1),
            },
            "postings_size": {
                "raw_bytes": raw_postings,
                "compressed_bytes": compressed_postings,
                "saving_percent": round(100 * (1 - compressed_postings / raw_postings), 1),
            },
        }
