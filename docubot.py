"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import glob


# Common words that carry little meaning for retrieval. Ignoring them keeps a
# query like "Is there any mention of payment processing?" from matching docs
# on filler words alone, which is what powers the refusal guardrail.
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "am",
    "do", "does", "did", "how", "what", "which", "where", "when", "who",
    "why", "to", "of", "in", "on", "for", "and", "or", "any", "there",
    "this", "that", "these", "those", "i", "you", "it", "with", "as",
    "at", "by", "from", "into", "about", "can", "could", "should", "would",
    "my", "me", "we", "us", "our", "your", "mention", "docs",
}


def tokenize(text):
    """
    Split text into lowercase word tokens, stripping surrounding punctuation.
    Keeps things simple: whitespace split, then trim non-alphanumeric edges.
    """
    tokens = []
    for raw in text.lower().split():
        word = raw.strip(".,:;!?()[]{}<>\"'`/\\|#*")
        if word:
            tokens.append(word)
    return tokens


def query_terms(query):
    """
    Meaningful query words: tokens minus stopwords. These are the words we
    actually score against, so filler words cannot create false matches.
    """
    return {word for word in tokenize(query) if word not in STOPWORDS}


def split_into_snippets(text):
    """
    Break a document into smaller pieces so retrieval can return precise
    sections instead of whole files. We split on blank lines (paragraphs),
    trim whitespace, and drop empty pieces.
    """
    snippets = []
    for block in text.split("\n\n"):
        block = block.strip()
        if block:
            snippets.append(block)
    return snippets


class DocuBot:
    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)

        # Build a retrieval index (implemented in Phase 1)
        self.index = self.build_index(self.documents)

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def build_index(self, documents):
        """
        TODO (Phase 1):
        Build a tiny inverted index mapping lowercase words to the documents
        they appear in.

        Example structure:
        {
            "token": ["AUTH.md", "API_REFERENCE.md"],
            "database": ["DATABASE.md"]
        }

        Keep this simple: split on whitespace, lowercase tokens,
        ignore punctuation if needed.
        """
        index = {}
        for filename, text in documents:
            for word in set(tokenize(text)):
                index.setdefault(word, [])
                if filename not in index[word]:
                    index[word].append(filename)
        return index

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def score_document(self, query, text):
        """
        TODO (Phase 1):
        Return a simple relevance score for how well the text matches the query.

        Suggested baseline:
        - Convert query into lowercase words
        - Count how many appear in the text
        - Return the count as the score
        """
        query_words = query_terms(query)
        text_words = tokenize(text)

        score = 0
        for word in text_words:
            if word in query_words:
                score += 1
        return score

    def retrieve(self, query, top_k=3, min_score=1):
        """
        Select the top_k most relevant snippets for a query.

        Documents are split into small snippets (paragraphs), each snippet is
        scored, and only snippets scoring at least min_score are kept. If none
        clear that bar we return an empty list, which the answer methods turn
        into an "I do not know" refusal (the guardrail).

        Returns a list of (filename, snippet_text) sorted by score descending.
        """
        scored = []
        for filename, text in self.documents:
            for snippet in split_into_snippets(text):
                score = self.score_document(query, snippet)
                if score >= min_score:
                    scored.append((score, filename, snippet))

        scored.sort(key=lambda item: item[0], reverse=True)

        results = [(filename, snippet) for _, filename, snippet in scored]
        return results[:top_k]

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
