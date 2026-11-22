"""Offline corpus.

Purpose: the pipeline, the trace and the UI must be demoable with no network and
no API key (a venue wifi failure is a real risk on competition day). The texts
below are synthetic but shaped like the real thing: every quote used as evidence
is a verbatim substring of the body, except the one deliberately fuzzy quote on
mock-rag-04, which must land on level B.

Do not "improve" these numbers. The critic loop and the evidence ladder are only
meaningful because the data is deterministic.
"""

from __future__ import annotations

import re

from schema import Claim, Evidence, EvidenceLevel, ExtractedField, Metric, Paper, PaperStatus

# --------------------------------------------------------------------------- corpus

PAPERS: dict[str, dict] = {
    "mock-rag-01": {
        "title": "Adaptive Semantic Chunking for Retrieval-Augmented Generation",
        "year": 2025,
        "venue": "ACL",
        "authors": ["Y. Chen", "L. Zhao"],
        "abstract": (
            "Retrieval-augmented generation still depends on how documents are cut into chunks. "
            "Fixed token windows ignore sentence semantics and break arguments across boundaries. "
            "We study whether semantic chunking improves downstream answer quality."
        ),
        "pages": [
            "Abstract. Retrieval-augmented generation still depends on how documents are cut into chunks. "
            "Fixed token windows ignore sentence semantics and break arguments across boundaries. "
            "We study whether semantic chunking improves downstream answer quality. "
            "1 Introduction. Prior work treats chunk size as a hyperparameter. "
            "We argue that the boundary placement matters more than the size.",
            "2 Method. We propose AS-Cut, a semantic chunker that splits documents at embedding "
            "discontinuity points instead of fixed token windows. Consecutive sentences are embedded "
            "with a frozen encoder, and a chunk boundary is placed where cosine similarity between "
            "neighbouring sentences falls below a learned threshold. The threshold is tuned on a "
            "held-out split of each corpus.",
            "3 Experiments. We evaluate on NaturalQuestions and HotpotQA with the same retriever and "
            "reader. The baseline is fixed 512-token chunking with 64-token overlap. "
            "4 Results. AS-Cut reaches 46.2 EM on NaturalQuestions and 58.9 F1 on HotpotQA, "
            "outperforming the fixed 512-token baseline by 3.1 EM. "
            "Gains are largest on multi-sentence questions.",
        ],
    },
    "mock-rag-02": {
        "title": "Two-Stage Reranking with Distilled Cross-Encoders",
        "year": 2024,
        "venue": "EMNLP",
        "authors": ["M. Rossi", "T. Nakamura"],
        "abstract": (
            "Reranking is the quality bottleneck of two-stage retrieval, yet cross-encoders are too "
            "slow for full corpora. We distil a cross-encoder into a compact student and apply it "
            "only to the top candidates."
        ),
        "pages": [
            "Abstract. Reranking is the quality bottleneck of two-stage retrieval, yet cross-encoders "
            "are too slow for full corpora. We distil a cross-encoder into a compact student and "
            "apply it only to the top candidates. "
            "1 Introduction. Two-stage retrieval has become the default for open-domain QA.",
            "2 Method. Our pipeline retrieves 200 candidates with BM25, then reranks the top 50 with "
            "a distilled cross-encoder trained on teacher scores. The student keeps 97% of the "
            "teacher's nDCG while running 6x faster.",
            "3 Experiments. We report nDCG@10 on the BEIR benchmark and MRR@10 on MS MARCO. The "
            "baseline is BM25 with a single-stage bi-encoder reranker. "
            "4 Results. The distilled reranker reaches 52.1 nDCG@10 on BEIR and 38.4 MRR@10 on "
            "MS MARCO, a 4.6 point gain over the bi-encoder baseline.",
        ],
    },
    "mock-rag-03": {
        "title": "Tree-Organized Retrieval over Recursive Summaries",
        "year": 2024,
        "venue": "ICLR",
        "authors": ["S. Patel", "H. Kim"],
        "abstract": (
            "Long documents defeat flat retrieval because a single embedding cannot represent a whole "
            "section. We build a tree of recursive summaries and retrieve at multiple levels of "
            "abstraction."
        ),
        "pages": [
            "Abstract. Long documents defeat flat retrieval because a single embedding cannot represent "
            "a whole section. We build a tree of recursive summaries and retrieve at multiple levels "
            "of abstraction. "
            "1 Introduction. Section-level questions are poorly served by chunk retrieval.",
            "2 Method. Documents are clustered recursively and each cluster is summarised by the "
            "model, producing a tree whose leaves are sentences and whose root is a document summary. "
            "Retrieval traverses the tree and collapses matched nodes.",
            "3 Experiments. We evaluate on QASPER and NarrativeQA using the same reader. "
            "4 Results. On QASPER and NarrativeQA the tree retriever reaches 55.7 F1, against 49.2 F1 "
            "for flat chunk retrieval. The gain comes from questions whose evidence spans several sections.",
        ],
    },
    "mock-rag-04": {
        "title": "Hybrid Sparse-Dense Retrieval for Scientific Question Answering",
        "year": 2025,
        "venue": "NAACL",
        "authors": ["R. Gupta", "A. Lindqvist"],
        "abstract": (
            "Dense retrievers generalise well but miss exact terminology in scientific text. We combine "
            "sparse and dense scores with learned fusion weights."
        ),
        "pages": [
            "Abstract. Dense retrievers generalise well but miss exact terminology in scientific text. "
            "We combine sparse and dense scores with learned fusion weights. "
            "1 Introduction. Scientific questions often depend on a single technical term.",
            "2 Method. Sparse BM25 scores and dense DPR scores are normalised and combined by learned "
            "fusion weights trained on domain pairs. A single weight vector is shared across query types.",
            "3 Experiments. We use SciQA and BioASQ with the official splits. "
            "4 Results. On SciQA and BioASQ the hybrid retriever reaches 61.3 accuracy, compared with "
            "54.8 for dense-only DPR. Exact-terminology questions improve the most.",
        ],
    },
    "mock-rag-05": {
        "title": "Query Rewriting for Multi-Hop Retrieval",
        "year": 2025,
        "venue": "ACL Findings",
        "authors": ["J. Silva", "W. Zhang"],
        "abstract": (
            "Multi-hop questions fail in one retrieval round because the second hop depends on the "
            "first answer. We rewrite the query after each hop."
        ),
        "pages": [
            "Abstract. Multi-hop questions fail in one retrieval round because the second hop depends "
            "on the first answer. We rewrite the query after each hop. "
            "1 Introduction. Single-round retrieval cannot bridge two linked facts.",
            "2 Method. After each retrieval round the model rewrites the query conditioned on the "
            "passages already read, then retrieves again. The loop stops when the reader's answer "
            "confidence exceeds a threshold.",
            "3 Experiments. We evaluate on HotpotQA and MuSiQue with a fixed reader. "
            "4 Results. On HotpotQA and MuSiQue iterative rewriting reaches 51.8 EM and 34.5 EM "
            "respectively, against 42.0 and 25.9 for single-round retrieval.",
        ],
    },
}

FIELDS: dict[str, dict] = {
    "mock-rag-01": dict(
        task="开放域问答（检索增强生成）",
        method="AS-Cut：按句向量不连续点做语义分块",
        dataset="NaturalQuestions, HotpotQA",
        metrics=[Metric(name="EM", value="46.2 (NQ)"), Metric(name="F1", value="58.9 (HotpotQA)")],
        baseline="固定 512-token 分块 + 64 token 重叠",
        limitation="阈值需按语料调参，跨领域迁移未验证",
    ),
    "mock-rag-02": dict(
        task="两阶段检索重排",
        method="蒸馏交叉编码器，仅对 top-50 候选重排",
        dataset="BEIR, MS MARCO",
        metrics=[Metric(name="nDCG@10", value="52.1 (BEIR)"), Metric(name="MRR@10", value="38.4 (MS MARCO)")],
        baseline="BM25 + 单阶段 bi-encoder 重排",
        limitation="学生模型保留 97% 教师效果，长文档未覆盖",
    ),
    "mock-rag-03": dict(
        task="长文档 / 章节级问答",
        method="递归聚类 + 摘要树，多层级检索",
        dataset="QASPER, NarrativeQA",
        metrics=[Metric(name="F1", value="55.7")],
        baseline="扁平 chunk 检索",
        limitation="摘要树构建成本高，更新文档需重建",
    ),
    "mock-rag-04": dict(
        task="科学问答检索",
        method="稀疏-稠密混合打分 + 学习式融合权重",
        dataset="SciQA, BioASQ",
        metrics=[Metric(name="Accuracy", value="61.3")],
        baseline="纯稠密检索（DPR）",
        limitation="融合权重按领域成对训练，跨领域需重训",
    ),
    "mock-rag-05": dict(
        task="多跳问答检索",
        method="每跳后按已读段落改写查询，迭代检索",
        dataset="HotpotQA, MuSiQue",
        metrics=[Metric(name="EM", value="51.8 (HotpotQA)"), Metric(name="EM", value="34.5 (MuSiQue)")],
        baseline="原始查询单轮检索",
        limitation="跳数上限固定为 3，更长链条未验证",
    ),
}

# Claims derived from the full text: (claim text, verbatim quote, section)
BODY_CLAIMS: dict[str, list[tuple[str, str, str]]] = {
    "mock-rag-01": [
        ("AS-Cut 在 NaturalQuestions 上达到 46.2 EM", "AS-Cut reaches 46.2 EM on NaturalQuestions", "Results"),
        ("在嵌入不连续点切分，而不是固定 token 窗口",
         "splits documents at embedding discontinuity points instead of fixed token windows", "Method"),
        ("比固定 512-token 基线高 3.1 EM", "outperforming the fixed 512-token baseline by 3.1 EM", "Results"),
    ],
    "mock-rag-02": [
        ("蒸馏后学生模型保留 97% 的教师 nDCG", "The student keeps 97% of the teacher's nDCG", "Method"),
        ("BEIR 上 nDCG@10 达 52.1", "The distilled reranker reaches 52.1 nDCG@10 on BEIR", "Results"),
        ("比 bi-encoder 基线高 4.6 分", "a 4.6 point gain over the bi-encoder baseline", "Results"),
        # deliberately unfindable: a plausible sentence that is NOT in the paper.
        # Must stay level C after the critic retry, and must not enter the table.
        ("蒸馏重排在所有基准上都达到当前最优",
         "the distilled reranker achieves state-of-the-art on every benchmark", "Results"),
    ],
    "mock-rag-03": [
        ("QASPER 与 NarrativeQA 上 F1 达 55.7", "the tree retriever reaches 55.7 F1", "Results"),
        ("扁平检索为 49.2 F1", "against 49.2 F1 for flat chunk retrieval", "Results"),
        ("收益来自证据跨越多段的问题",
         "The gain comes from questions whose evidence spans several sections.", "Results"),
    ],
    "mock-rag-04": [
        ("混合检索在 SciQA 与 BioASQ 上准确率 61.3", "the hybrid retriever reaches 61.3 accuracy", "Results"),
        ("纯稠密 DPR 为 54.8", "compared with 54.8 for dense-only DPR", "Results"),
        # deliberately fuzzy: "weight" vs "weights" -> level B, not A
        ("稀疏与稠密分数按学习到的融合权重合并",
         "combined by learned fusion weight trained on domain pairs", "Method"),
    ],
    "mock-rag-05": [
        ("HotpotQA 上 EM 51.8", "iterative rewriting reaches 51.8 EM and 34.5 EM", "Results"),
        ("单轮检索为 42.0 / 25.9 EM", "against 42.0 and 25.9 for single-round retrieval", "Results"),
        ("每轮检索后依据已读段落改写查询",
         "the model rewrites the query conditioned on the passages already read", "Method"),
    ],
}

# Claims a model would produce from the abstract alone (no full text).
ABSTRACT_CLAIMS: dict[str, list[tuple[str, str, str]]] = {
    "mock-rag-01": [("固定窗口会忽略句子语义并切断论证",
                     "Fixed token windows ignore sentence semantics and break arguments across boundaries.", "Abstract")],
    "mock-rag-02": [("交叉编码器对全量语料太慢，故只用于 top 候选",
                     "cross-encoders are too slow for full corpora", "Abstract")],
    "mock-rag-03": [("长文档使扁平检索失效，因单个向量无法表示整节",
                     "a single embedding cannot represent a whole section", "Abstract")],
    "mock-rag-04": [("稠密检索在科学文本上漏掉精确术语",
                     "Dense retrievers generalise well but miss exact terminology in scientific text.", "Abstract")],
    "mock-rag-05": [("多跳问题的第二跳依赖第一个答案",
                     "the second hop depends on the first answer", "Abstract")],
}


# --------------------------------------------------------------------------- helpers

def make_paper(paper_id: str) -> Paper:
    d = PAPERS[paper_id]
    return Paper(
        paper_id=paper_id,
        title=d["title"],
        year=d["year"],
        venue=d["venue"],
        authors=list(d["authors"]),
        abstract=d["abstract"],
        url=f"https://arxiv.org/abs/{paper_id}",
        pdf_url=f"https://arxiv.org/pdf/{paper_id}.pdf",
        status=PaperStatus.PENDING,
    )


def search(_topic: str, limit: int) -> list[Paper]:
    return [make_paper(pid) for pid in list(PAPERS)[:limit]]


_SECTION_SPLIT = re.compile(
    r"(?<![A-Za-z])(?=(?:\d\.?\s*)?(?:Abstract|Introduction|Method|Experiments|Results|Conclusion)\.)"
)


def body_text(paper: Paper) -> list[str]:
    """Return the page list of a paper (mock: the synthetic full text).

    Section headings are re-flowed onto their own lines so parse_sections exercises
    the same code path it will use on a real PDF.
    """
    pages = []
    for raw in PAPERS[paper.paper_id]["pages"]:
        parts = [p.strip() for p in _SECTION_SPLIT.split(raw) if p.strip()]
        pages.append("\n".join(parts))
    return pages


def extract(paper: Paper, *, from_abstract: bool) -> tuple[ExtractedField, list[Claim]]:
    f = FIELDS[paper.paper_id]
    field = ExtractedField(
        paper_id=paper.paper_id,
        task=f["task"],
        method=f["method"],
        dataset=f["dataset"],
        metrics=[Metric(**m.model_dump()) for m in f["metrics"]],
        baseline=f["baseline"],
        limitation=f["limitation"],
        source="abstract" if from_abstract else "full_text",
    )
    field.complete = bool(field.method and field.dataset and field.metrics)

    raw = ABSTRACT_CLAIMS[paper.paper_id] if from_abstract else BODY_CLAIMS[paper.paper_id]
    claims: list[Claim] = []
    for i, (text, quote, section) in enumerate(raw):
        cid = f"{paper.paper_id}-c{i + 1}"
        claims.append(
            Claim(
                claim_id=cid,
                paper_id=paper.paper_id,
                text=text,
                section=section,
                evidence=Evidence(
                    evid_id=f"{cid}-e",
                    paper_id=paper.paper_id,
                    claim_id=cid,
                    quote=quote,
                    level=EvidenceLevel.C,
                ),
            )
        )
    return field, claims
