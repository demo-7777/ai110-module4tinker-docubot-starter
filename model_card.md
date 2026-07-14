# DocuBot Model Card

This model card is a short reflection on your DocuBot system. Fill it out after you have implemented retrieval and experimented with all three modes:

1. Naive LLM over full docs  
2. Retrieval only  
3. RAG (retrieval plus LLM)

Use clear, honest descriptions. It is fine if your system is imperfect.

---

## 1. System Overview

**What is DocuBot trying to do?**  
Describe the overall goal in 2 to 3 sentences.

> DocuBot answers developer questions about a specific codebase by reading the local `docs/` folder. Its goal is to give grounded, reliable answers based on the project's own documentation instead of the model's general knowledge. It also knows when to refuse rather than guess.

**What inputs does DocuBot take?**  
For example: user question, docs in folder, environment variables.

> A user question (typed or from `dataset.py` samples), the `.md`/`.txt` files in the `docs/` folder, and the `GEMINI_API_KEY` environment variable (only needed for the LLM modes).

**What outputs does DocuBot produce?**

> Depending on the mode: a naive LLM answer (mode 1), the raw retrieved snippets with their filenames (mode 2), or a grounded LLM answer that cites which files it used and refuses with "I do not know based on the docs I have" when evidence is missing (mode 3).

---

## 2. Retrieval Design

**How does your retrieval system work?**  
Describe your choices for indexing and scoring.

- How do you turn documents into an index?
- How do you score relevance for a query?
- How do you choose top snippets?

> `build_index` creates a tiny inverted index mapping each lowercase word to the filenames it appears in. For retrieval, each document is split into small snippets (paragraphs, split on blank lines by `split_into_snippets`). `score_document` counts how many *meaningful* query words (query tokens minus a stopword list) appear in a snippet. `retrieve` scores every snippet, keeps only those scoring at least `min_score=1`, sorts by score descending, and returns the top 3.

**What tradeoffs did you make?**  
For example: speed vs precision, simplicity vs accuracy.

> The scoring is raw term frequency, which is simple and fast but biased toward snippets that repeat a query word many times rather than the snippet that actually answers the question. Paragraph-level snippets improved precision over whole-file retrieval, but there is no notion of synonyms, phrases, or word importance (no TF-IDF). Stopword filtering makes the refusal guardrail work but is a hand-maintained list.

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**  
Briefly describe how each mode behaves.

- Naive LLM mode: Calls the LLM with only the bare question — the docs are deliberately **not** sent (see `naive_answer_over_full_docs`). The model answers from general training knowledge.
- Retrieval only mode: Does **not** call the LLM at all. Returns the retrieved snippets and filenames directly.
- RAG mode: First runs retrieval, then calls the LLM with only the retrieved snippets and strict grounding rules. If retrieval returns nothing, it refuses without calling the LLM.

**What instructions do you give the LLM to keep it grounded?**  
Summarize the rules from your prompt. For example: only use snippets, say "I do not know" when needed, cite files.

> The RAG prompt tells the model to answer using **only** the provided snippets, to invent no new functions/endpoints/values, to reply exactly "I do not know based on the docs I have." when the snippets are insufficient, and to briefly mention which files it relied on.

---

## 4. Experiments and Comparisons

Run the **same set of queries** in all three modes. Fill in the table with short notes.

You can reuse or adapt the queries from `dataset.py`.

| Query | Naive LLM: helpful or harmful? | Retrieval only: helpful or harmful? | RAG: helpful or harmful? | Notes |
|------|---------------------------------|--------------------------------------|---------------------------|-------|
| Where is the auth token generated? | Harmful — confident but generic; listed Auth0/Firebase/PyJWT, never named `generate_access_token`/`auth_utils.py` | Helpful — returned correct AUTH.md paragraphs (accurate source) | Failed — refused ("I do not know") because the answering sentence was not in the top-3 snippets | Retrieval surfaced token-dense paragraphs, not the one naming the function |
| How do I connect to the database? | Harmful — returned an essentially empty answer | Helpful — returned DATABASE.md + SETUP.md snippets with `DATABASE_URL` details | Failed — refused despite correct files being nearby | Same frequency-bias issue as above |
| Which endpoint lists all users? | Harmful — guessed `GET /users`, cited GitHub/Slack/WordPress, missed the admin-only `GET /api/users` | Helpful — returned the correct API_REFERENCE.md snippets | Refused | Naive sounds authoritative but is wrong for this codebase |
| Is there any mention of payment processing in these docs? | Harmful — complained the docs weren't attached (it never receives them) and offered to search | Correct refusal — retrieved nothing (guardrail) | Correct refusal — "I do not know based on these docs." | The one case where refusal is the right answer, and both grounded paths get it right |

**What patterns did you notice?**  

- When does naive LLM look impressive but untrustworthy?  
- When is retrieval only clearly better?  
- When is RAG clearly better than both?

> Naive mode is fluent and authoritative-sounding on every question, but it answers about *generic* systems (Auth0, GitHub's API) and never about this codebase — impressive tone, wrong specifics. Retrieval only is clearly better whenever the answer is a known fact in a doc: it returns the exact, correct source, though the output is raw text with no synthesis and can be hard to read. RAG is best when retrieval hands it the *right* snippet — it then answers in plain language, cites files, and refuses the trap questions. Its correct refusal on the payment question is the standout win over naive mode.

---

## 5. Failure Cases and Guardrails

**Describe at least two concrete failure cases you observed.**  
For each one, say:

- What was the question?  
- What did the system do?  
- What should have happened instead?

> **Failure case 1 (RAG under-answers):** "Where is the auth token generated?" RAG replied "I do not know based on the docs I have," even though AUTH.md explicitly says tokens are created by `generate_access_token` in `auth_utils.py`. It should have answered and cited AUTH.md. Cause: retrieval scores by raw term frequency, so token-heavy paragraphs (validation steps, overview) outrank the single sentence that actually answers the question, and it never reaches the LLM.

> **Failure case 2 (Naive over-answers / hallucinates):** "Which endpoint lists all users?" Naive mode confidently answered `GET /users` with examples from GitHub, Slack, and WordPress. The real answer is the admin-only `GET /api/users` in this project. It should have said it lacked the project's docs instead of guessing.

**When should DocuBot say "I do not know based on the docs I have"?**  
Give at least two specific situations.

> (1) When the question is about something genuinely absent from the docs, e.g. payment processing, rate limiting, or deployment. (2) When retrieval returns no snippet that meaningfully matches the query (score below `min_score`), so there is no evidence to reason from.

**What guardrails did you implement?**  
Examples: refusal rules, thresholds, limits on snippets, safe defaults.

> Stopword filtering so filler words cannot create false matches; a `min_score` threshold in `retrieve` that returns an empty list when nothing meaningful matches; empty retrieval short-circuits to an "I do not know" refusal without calling the LLM; a top_k limit so only the 3 best snippets are sent; and an explicit prompt rule requiring the exact refusal phrase when evidence is insufficient.

---

## 6. Limitations and Future Improvements

**Current limitations**  
List at least three limitations of your DocuBot system.

1. Scoring is raw term frequency, so the most *repetitive* snippet beats the most *relevant* one — this makes RAG refuse answerable questions.
2. No understanding of synonyms, phrases, or multi-word concepts; matching is single-word overlap only.
3. Paragraph splitting is naive (blank lines); a long table or list counts as one snippet and can crowd out better matches, and the stopword list is hand-maintained.

**Future improvements**  
List two or three changes that would most improve reliability or usefulness.

1. Use TF-IDF (or embeddings) so rare, meaningful words like `generate_access_token` outweigh common ones like `token`.
2. Increase `top_k` or add a small overlap/context window so the answering sentence is less likely to be cut off.
3. Return snippets with their section headings for context, and add a confidence threshold that distinguishes "weak match" from "no match."

---

## 7. Responsible Use

**Where could this system cause real world harm if used carelessly?**  
Think about wrong answers, missing information, or over trusting the LLM.

> If developers trusted naive-mode answers, they could implement the wrong auth flow or call endpoints that do not exist in this codebase. Over-trusting RAG is safer but not risk-free: a refusal can be mistaken for "the feature doesn't exist" when it is really a retrieval miss, and a confidently cited answer could still rest on an incomplete snippet.

**What instructions would you give real developers who want to use DocuBot safely?**  
Write 2 to 4 short bullet points.

- Treat answers as pointers into the docs, then open the cited file and verify.
- Trust the cited-source answers (mode 3) over naive answers (mode 1); never rely on mode 1 for codebase specifics.
- Read a refusal as "not found in the retrieved snippets," not as proof the information does not exist — rephrase or check the docs directly.

---
