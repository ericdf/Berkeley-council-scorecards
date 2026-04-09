"""
LDA topic modeling on Berkeley City Council captioner transcripts.

Usage:
    python topic_model.py [--topics N] [--words W]

Defaults: 10 topics, 15 top words each.
"""

import argparse
import glob
import os
import re

import pandas as pd
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TEXT_DIR = os.path.join(os.path.dirname(__file__), "text")

# Words to strip beyond sklearn's built-in English stopwords.
# These are high-frequency meeting artifacts that swamp real topics.
EXTRA_STOPWORDS = [
    "councilmember", "council", "mayor", "city", "berkeley",
    "meeting", "thank", "yes", "okay", "right", "going", "know",
    "think", "just", "like", "said", "say", "want", "make",
    "need", "come", "good", "one", "also", "well", "back",
    "item", "public", "comment", "motion", "second", "vote",
    "aye", "nay", "abstain", "present", "absent", "call",
    "order", "recess", "adjourn", "clerk", "captioner", "certified",
    "realtime", "reporter", "information", "provided", "certify",
    "text", "created", "following",
    "boardroom", "zoom",
]


# ---------------------------------------------------------------------------
# Load documents
# ---------------------------------------------------------------------------
def load_docs(text_dir):
    paths = sorted(glob.glob(os.path.join(text_dir, "*.txt")))
    docs, names = [], []
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as f:
            raw = f.read()
        # Normalize Unicode ligatures before anything else (ﬁ ﬂ etc.)
        raw = raw.replace("\ufb01", "fi").replace("\ufb02", "fl")
        # Strip per-page boilerplate inserted by the captioning service
        raw = re.sub(
            r"This information provided by a Certifi?ed Realtime Reporter\..*?"
            r"we did not create it\.",
            " ", raw, flags=re.IGNORECASE | re.DOTALL,
        )
        # Strip page-feed characters pdftotext inserts between pages
        raw = re.sub(r"\f", "\n", raw)
        # Normalize "Boardroom:" speaker label (Zoom-sourced transcripts)
        # — treat it the same as ">>" by just removing the label prefix
        raw = re.sub(r"^Boardroom\s*:\s*", "", raw, flags=re.MULTILINE)
        # Lowercase, drop punctuation/digits, collapse whitespace
        cleaned = re.sub(r"[^a-zA-Z\s]", " ", raw.lower())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        docs.append(cleaned)
        names.append(os.path.basename(p))
    return docs, names


# ---------------------------------------------------------------------------
# Vectorize
# ---------------------------------------------------------------------------
def build_vectorizer(extra_stopwords):
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    stopwords = list(ENGLISH_STOP_WORDS) + extra_stopwords
    return CountVectorizer(
        max_df=0.90,      # ignore terms in >90% of docs
        min_df=2,         # ignore terms in <2 docs
        max_features=5000,
        stop_words=stopwords,
        ngram_range=(1, 2),  # unigrams + bigrams
    )


# ---------------------------------------------------------------------------
# Display results
# ---------------------------------------------------------------------------
def print_topics(model, vectorizer, n_words):
    feature_names = vectorizer.get_feature_names_out()
    for i, comp in enumerate(model.components_):
        top_idx = comp.argsort()[-n_words:][::-1]
        words = ", ".join(feature_names[j] for j in top_idx)
        print(f"  Topic {i+1:2d}: {words}")


def print_doc_topics(doc_topic_matrix, names, top_n=3):
    print("\nTop topics per meeting:")
    for name, row in zip(names, doc_topic_matrix):
        top = row.argsort()[-top_n:][::-1]
        summary = "  |  ".join(
            f"T{t+1}({row[t]:.2f})" for t in top
        )
        label = name.replace(" Captioning.txt", "").replace(" Captioning", "")
        print(f"  {label:<55} {summary}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topics", type=int, default=10)
    parser.add_argument("--words", type=int, default=15)
    args = parser.parse_args()

    print(f"Loading documents from {TEXT_DIR} ...")
    docs, names = load_docs(TEXT_DIR)
    print(f"  {len(docs)} documents loaded.")

    print("Vectorizing ...")
    vec = build_vectorizer(EXTRA_STOPWORDS)
    dtm = vec.fit_transform(docs)
    print(f"  Vocabulary size: {len(vec.get_feature_names_out())}")

    print(f"Fitting LDA ({args.topics} topics) ...")
    lda = LatentDirichletAllocation(
        n_components=args.topics,
        random_state=42,
        max_iter=30,
        learning_method="batch",
    )
    doc_topic = lda.fit_transform(dtm)
    print(f"  Perplexity: {lda.perplexity(dtm):.1f}\n")

    print("=" * 70)
    print(f"TOP {args.words} WORDS PER TOPIC")
    print("=" * 70)
    print_topics(lda, vec, args.words)

    print_doc_topics(doc_topic, names)


if __name__ == "__main__":
    main()
