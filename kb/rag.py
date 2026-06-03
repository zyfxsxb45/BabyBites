"""
RAG 检索增强生成模块。

从 PDF/MD 标准文档中加载、切块、TF-IDF 向量化、检索。
基于 sklearn TfidfVectorizer，纯本地计算，无需下载模型。

用法：
    from kb.rag import RAGRetriever
    rag = RAGRetriever()
    rag.build_index()
    chunks = rag.search("6月龄辅食铁含量")
"""

import re
import pickle
from pathlib import Path
from typing import Optional


class RAGRetriever:
    """基于 TF-IDF 的文档检索器。

    文档来源：
      - 国内标准和指南/
      - 国外国际标准和指南/

    使用 sklearn TfidfVectorizer（纯本地，不联网，即刻可用）
    """

    SOURCE_DIRS = [
        Path("D:/课程文件/大二下/人工智能导论/AI系统实践/国内标准和指南"),
        Path("D:/课程文件/大二下/人工智能导论/AI系统实践/国外国际标准和指南"),
    ]

    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 80

    def __init__(self, persist_dir: str = None):
        if persist_dir is None:
            project_root = Path(__file__).parent.parent
            persist_dir = str(project_root / "data" / "rag_index")
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self._chunks: list[dict] = []       # [{text, filename, source}]
        self._vectorizer = None
        self._tfidf_matrix = None
        self._loaded = False

        # 尝试加载缓存
        self._load_cache()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    # ===== 构建索引 =====

    def build_index(self, force: bool = False) -> int:
        """扫描文档 → 提取 → 切块 → TF-IDF → 缓存"""
        if self._loaded and not force:
            return len(self._chunks)

        print("📄 扫描文档中...")
        chunks = []
        for source_dir in self.SOURCE_DIRS:
            if not source_dir.exists():
                continue

            for pdf_path in source_dir.rglob("*.pdf"):
                try:
                    texts = self._load_pdf(pdf_path)
                    for t in texts:
                        chunks.append({
                            "text": t,
                            "filename": pdf_path.name,
                            "source": str(pdf_path),
                        })
                except Exception as e:
                    print(f"  ⚠️ 跳过 {pdf_path.name}: {e}")

            for md_path in source_dir.rglob("*.md"):
                try:
                    text = md_path.read_text(encoding="utf-8", errors="replace")
                    for t in self._chunk_text(text):
                        chunks.append({
                            "text": t,
                            "filename": md_path.name,
                            "source": str(md_path),
                        })
                except Exception:
                    continue

        if not chunks:
            print("⚠️ 未找到任何文档")
            return 0

        print(f"  提取到 {len(chunks)} 个文本块，正在向量化...")

        # TF-IDF 向量化
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),     # 单字+双字组合，适合中文
            analyzer="char_wb",      # 字符级分析，适合中文
        )
        self._tfidf_matrix = self._vectorizer.fit_transform(
            [c["text"] for c in chunks]
        )
        self._chunks = chunks
        self._loaded = True

        # 缓存到磁盘
        self._save_cache()

        print(f"✓ RAG 索引完成：{len(chunks)} 个文本块")
        return len(chunks)

    # ===== 检索 =====

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """TF-IDF 检索最相关段落"""
        if not self._loaded:
            return []

        from sklearn.metrics.pairwise import cosine_similarity

        query_vec = self._vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self._tfidf_matrix)[0]

        # 取 top_k
        top_idx = scores.argsort()[-top_k:][::-1]

        results = []
        for idx in top_idx:
            score = float(scores[idx])
            if score < 0.01:
                continue
            results.append({
                "text": self._chunks[idx]["text"],
                "filename": self._chunks[idx]["filename"],
                "source": self._chunks[idx]["source"],
                "score": round(score, 3),
            })

        return results

    def search_formatted(self, query: str, top_k: int = 3) -> str:
        """格式化为 ChatAgent 可用的上下文字符串"""
        results = self.search(query, top_k)
        if not results:
            return ""

        lines = ["【标准/指南原文片段】"]
        for i, r in enumerate(results, 1):
            source = r["filename"].replace(".pdf", "").replace(".md", "")
            lines.append(f"\n--- {source} (相关度: {r['score']}) ---")
            lines.append(r["text"][:500])

        return "\n".join(lines)

    # ===== PDF 加载 =====

    def _load_pdf(self, path: Path) -> list[str]:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        full_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        return self._chunk_text(full_text) if full_text.strip() else []

    # ===== 切块 =====

    def _chunk_text(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        chunks = []
        start = 0
        while start < len(text):
            end = start + self.CHUNK_SIZE
            if end < len(text):
                for sep in ["\n\n", "\n", "。", ".", "；", ";"]:
                    pos = text.rfind(sep, start, end)
                    if pos > start + 100:
                        end = pos + 1
                        break
            chunk = text[start:end].strip()
            if len(chunk) >= 50:
                chunks.append(chunk)
            start = end - self.CHUNK_OVERLAP
        return chunks

    # ===== 缓存 =====

    def _save_cache(self):
        try:
            with open(self.persist_dir / "rag_cache.pkl", "wb") as f:
                pickle.dump({
                    "chunks": self._chunks,
                    "vectorizer": self._vectorizer,
                    "tfidf_matrix": self._tfidf_matrix,
                }, f)
        except Exception:
            pass

    def _load_cache(self):
        cache_file = self.persist_dir / "rag_cache.pkl"
        if not cache_file.exists():
            return
        try:
            with open(cache_file, "rb") as f:
                data = pickle.load(f)
                self._chunks = data["chunks"]
                self._vectorizer = data["vectorizer"]
                self._tfidf_matrix = data["tfidf_matrix"]
                self._loaded = len(self._chunks) > 0
                print(f"✓ 加载 RAG 缓存：{len(self._chunks)} 块")
        except Exception:
            self._loaded = False
