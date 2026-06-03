#!/usr/bin/env python3
"""
RAG 索引构建脚本。

扫描所有标准/指南 PDF，提取文本 → 切块 → 向量化 → 存入 ChromaDB。

用法：
    python scripts/build_rag.py          # 首次构建
    python scripts/build_rag.py --force  # 强制重建
"""

import sys, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from kb.rag import RAGRetriever


def main():
    parser = argparse.ArgumentParser(description="构建 RAG 知识库索引")
    parser.add_argument("--force", action="store_true", help="强制重建索引")
    args = parser.parse_args()

    print("📚 RAG 索引构建")
    print(f"  文档目录: {RAGRetriever.SOURCE_DIRS}")
    print()

    # 初始化
    rag = RAGRetriever()

    if rag.is_loaded and not args.force:
        print(f"✅ 索引已存在（{rag.chunk_count} 个文本块）")
        print("   使用 --force 强制重建")
        return

    # 构建
    print("扫描文档中...")
    count = rag.build_index(force=args.force)
    print(f"\n✅ 完成：{count} 个文本块已索引")
    print(f"   持久化目录：{rag.persist_dir}")


if __name__ == "__main__":
    main()
