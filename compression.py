"""
compression.py
Dictionary compression + postings compression (WSM: "dictionary compression
for faster and memory saving").

1. CompressedDictionary : "dictionary as a string" + blocking (k terms per block)
2. vbyte / gap encoding : compress the postings lists (doc ids)
"""


# ---------------------------------------------------------------
# 1. Dictionary as a string with blocking
# ---------------------------------------------------------------
class CompressedDictionary:
    """
    All terms are glued into ONE long string, each term preceded by one
    character that stores its length:

        "\x05index\x08positionall..."

    Instead of keeping a pointer for every term, we keep a pointer only for
    every k-th term (a "block"). Lookup = binary search over the blocks,
    then a short linear scan inside one block.
    The position of a term in the sorted list is its term id.
    """

    def __init__(self, sorted_terms, k=4):
        self.k = k
        self.n = len(sorted_terms)
        self.text = ""
        self.block_pointers = []          # one pointer per block
        for i, term in enumerate(sorted_terms):
            if i % k == 0:
                self.block_pointers.append(len(self.text))
            self.text += chr(len(term)) + term

    def _read_term(self, pos):
        length = ord(self.text[pos])
        term = self.text[pos + 1: pos + 1 + length]
        return term, pos + 1 + length      # term and pointer to the next one

    def lookup(self, term):
        """Return term id, or -1 if the term is not in the dictionary."""
        lo, hi, block = 0, len(self.block_pointers) - 1, 0
        # binary search: last block whose first term is <= term
        while lo <= hi:
            mid = (lo + hi) // 2
            first_term, _ = self._read_term(self.block_pointers[mid])
            if first_term <= term:
                block = mid
                lo = mid + 1
            else:
                hi = mid - 1
        # linear scan inside the block
        pos = self.block_pointers[block]
        for j in range(self.k):
            term_id = block * self.k + j
            if term_id >= self.n:
                break
            t, pos = self._read_term(pos)
            if t == term:
                return term_id
        return -1

    def size_in_bytes(self):
        # the string + a 4 byte pointer per block
        return len(self.text) + 4 * len(self.block_pointers)


# ---------------------------------------------------------------
# 2. Variable byte encoding of gaps
# ---------------------------------------------------------------
def vbyte_encode_number(n):
    pieces = []
    while True:
        pieces.insert(0, n % 128)
        if n < 128:
            break
        n = n // 128
    pieces[-1] += 128                 # last byte gets the "end" bit
    return bytes(pieces)


def encode_postings(doc_ids):
    """[3, 7, 20] -> gaps [3, 4, 13] -> vbyte bytes"""
    result = b""
    previous = 0
    for doc_id in sorted(doc_ids):
        result += vbyte_encode_number(doc_id - previous)
        previous = doc_id
    return result


def decode_postings(data):
    """bytes -> gaps -> doc ids"""
    doc_ids, n, total = [], 0, 0
    for byte in data:
        if byte < 128:
            n = 128 * n + byte
        else:
            n = 128 * n + (byte - 128)
            total += n                # gap -> real doc id
            doc_ids.append(total)
            n = 0
    return doc_ids
