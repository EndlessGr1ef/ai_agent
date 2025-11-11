import os
import sys
import argparse
import re
from typing import Dict, List, Tuple
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
import chromadb
from chromadb.config import Settings


def build_embeddings(model_name: str | None = None) -> HuggingFaceEmbeddings:
    if not model_name:
        model_name = os.getenv("EMBED_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
    return HuggingFaceEmbeddings(model_name=model_name)


def create_chroma_client(host: str, port: int) -> chromadb.HttpClient:
    settings = Settings(allow_reset=True, anonymized_telemetry=False)
    return chromadb.HttpClient(host=host, port=port, settings=settings)


def classify_by_path(file_path: str) -> Dict[str, str]:
    """根据文件路径进行目录分类"""
    path = Path(file_path)
    path_parts = path.parts

    # 初始化分类
    category = "Other"
    subcategory = None
    topic = path.stem  # 文件名作为主题

    # 规则1: 直接子目录分类
    if len(path_parts) > 1:
        immediate_parent = path_parts[-2].lower()

        if any(keyword in immediate_parent for keyword in ['ai', 'ml', 'rag', 'agent', 'transformer']):
            category = "AI/RAG"
            if 'rag' in immediate_parent:
                subcategory = "RAG"
            elif 'agent' in immediate_parent:
                subcategory = "Agent"
            elif 'transformer' in immediate_parent:
                subcategory = "Transformer"
        elif any(keyword in immediate_parent for keyword in ['backend', 'server', 'api', 'go', 'python', 'java']):
            category = "Backend"
            if 'go' in immediate_parent or 'golang' in immediate_parent:
                subcategory = "Go"
            elif 'python' in immediate_parent:
                subcategory = "Python"
            elif 'api' in immediate_parent:
                subcategory = "API"
        elif any(keyword in immediate_parent for keyword in ['frontend', 'web', 'react', 'vue']):
            category = "Frontend"
            subcategory = "Web"
        elif any(keyword in immediate_parent for keyword in ['docs', 'doc', 'documentation']):
            category = "Documentation"
            subcategory = "Technical"

    # 规则2: 文件名关键词分类
    filename = path.name.lower()
    if not subcategory:  # 如果没有通过目录设置subcategory
        if any(keyword in filename for keyword in ['rag', 'retrieval']):
            subcategory = "RAG"
            category = "AI/RAG"
        elif any(keyword in filename for keyword in ['agent', 'ai agent']):
            subcategory = "Agent"
            category = "AI/RAG"
        elif any(keyword in filename for keyword in ['transformer', 'bert', 'gpt']):
            subcategory = "Transformer"
            category = "AI/RAG"
        elif any(keyword in filename for keyword in ['tech', '技术', '项目']):
            subcategory = "Project"
            category = "Documentation"

    return {
        "category": category,
        "subcategory": subcategory or "General",
        "topic": topic,
        "source_type": "markdown"
    }


def classify_by_content(content: str, file_path: str) -> Dict[str, any]:
    """根据文档内容进行主题分类"""
    content_lower = content.lower()

    # 主题关键词映射
    topic_keywords = {
        "RAG": ["retrieval augmented", "rag", "retrieval", "vector database", "embedding", "similarity search", "retrieval-based"],
        "Agent": ["ai agent", "autonomous agent", "multi-agent", "agent framework", "langgraph", "crewai", "autogpt"],
        "Transformer": ["transformer", "attention", "bert", "gpt", "encoder-decoder", "self-attention", "multi-head attention"],
        "Machine Learning": ["machine learning", "deep learning", "neural network", "training", "model", "algorithm", "supervised", "unsupervised"],
        "Backend": ["api", "rest", "server", "backend", "database", "gorm", "gin", "fastapi", "flask", "spring"],
        "Frontend": ["react", "vue", "angular", "javascript", "typescript", "frontend", "ui", "ux", "component"],
        "DevOps": ["docker", "kubernetes", "ci/cd", "deployment", "devops", "infrastructure", "terraform", "ansible"],
        "Database": ["database", "sql", "nosql", "mongodb", "postgresql", "mysql", "redis", "elasticsearch"],
        "Documentation": ["documentation", "docs", "readme", "tutorial", "guide", "manual", "api reference", "getting started"]
    }

    # 编程语言识别
    language_keywords = {
        "Python": ["python", "django", "flask", "fastapi", "pytorch", "tensorflow", "pandas", "numpy"],
        "Go": ["golang", " go ", "goroutine", "gorm", "gin", "echo", "fiber"],
        "Java": ["java", "spring", "springboot", "maven", "gradle", "hibernate", "jpa"],
        "JavaScript": ["javascript", "nodejs", "node.js", "express", "npm", "react", "vue", "angular"],
        "TypeScript": ["typescript", "ts", "tsx", "jsx"],
    }

    # 匹配主题
    detected_topics = []
    for topic, keywords in topic_keywords.items():
        if any(keyword in content_lower for keyword in keywords):
            detected_topics.append(topic)

    # 匹配编程语言
    detected_languages = []
    for lang, keywords in language_keywords.items():
        if any(keyword in content_lower for keyword in keywords):
            detected_languages.append(lang)

    # 从文件路径补充信息
    path_classification = classify_by_path(file_path)

    return {
        "topics": detected_topics if detected_topics else ["Other"],
        "languages": detected_languages if detected_languages else [],
        "content_type": "tutorial" if any(word in content_lower for word in ["tutorial", "guide", "教程", "指南"]) else
                        "reference" if any(word in content_lower for word in ["api", "reference", "文档", "reference"]) else
                        "project",
        "complexity": "advanced" if any(word in content_lower for word in ["advanced", "complex", "高级", "复杂"]) else
                      "intermediate" if any(word in content_lower for word in ["intermediate", "中级"]) else
                      "beginner"
    }


def enrich_metadata(doc, original_path: str):
    """为文档添加丰富的metadata"""
    # 基础路径分类
    path_meta = classify_by_path(original_path)

    # 内容分类
    content_meta = classify_by_content(doc.page_content, original_path)

    # 合并metadata
    enriched_metadata = {
        # 路径分类
        "category": path_meta["category"],
        "subcategory": path_meta["subcategory"],
        "topic": path_meta["topic"],
        "source_type": path_meta["source_type"],

        # 内容分类（列表转换为逗号分隔的字符串）
        "topics": ", ".join(content_meta["topics"]) if isinstance(content_meta["topics"], list) else content_meta["topics"],
        "languages": ", ".join(content_meta["languages"]) if isinstance(content_meta["languages"], list) and content_meta["languages"] else "",
        "content_type": content_meta["content_type"],
        "complexity": content_meta["complexity"],

        # 系统信息
        "source": original_path,
        "file_name": os.path.basename(original_path),
        "ingested_at": "2024-11-10"
    }

    # 更新文档的metadata
    doc.metadata = enriched_metadata
    return doc


def ingest_markdown(docs_dir: str, collection_name: str, host: str, port: int,
                    chunk_size: int = 1000, chunk_overlap: int = 200,
                    embed_model_name: str | None = None, enable_auto_classification: bool = True) -> int:
    """
    Ingest markdown files into Chroma with automatic classification.

    Args:
        docs_dir: Directory containing markdown files
        collection_name: Chroma collection name
        host: Chroma server host
        port: Chroma server port
        chunk_size: Size of text chunks
        chunk_overlap: Overlap between chunks
        embed_model_name: Embedding model to use
        enable_auto_classification: Whether to enable automatic classification

    Returns:
        Number of chunks ingested
    """
    loader = DirectoryLoader(
        docs_dir,
        glob="**/*.md",
        loader_cls=TextLoader,
        show_progress=True,
        loader_kwargs={"encoding": "utf-8"},
    )
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_documents(docs)

    # If no chunks are produced (empty directory or no markdown files), return early
    if not chunks:
        return 0

    # Enrich chunks with metadata
    print(f"[Info] Enriching {len(chunks)} chunks with metadata...")
    enriched_chunks = []
    for chunk in chunks:
        # 获取原始文件路径
        original_path = chunk.metadata.get('source', 'unknown')

        # 丰富metadata
        enriched_chunk = enrich_metadata(chunk, original_path)
        enriched_chunks.append(enriched_chunk)

    embeddings = build_embeddings(embed_model_name)
    client = create_chroma_client(host, port)

    # 创建带有分类信息的collection metadata
    # 注意：ChromaDB只支持简单类型(str, int, float, bool)，不支持嵌套字典
    collection_metadata = {
        "description": "Auto-classified knowledge base",
        "version": "1.0",
        "auto_classification": str(enable_auto_classification).lower(),
        "ingestion_date": "2024-11-10"
    }

    _vs = Chroma.from_documents(
        documents=enriched_chunks,
        embedding=embeddings,
        collection_name=collection_name,
        client=client,
        collection_metadata=collection_metadata,
    )

    # Print classification summary
    print_classification_summary(enriched_chunks)

    return len(enriched_chunks)


def print_classification_summary(chunks):
    """打印分类汇总信息"""
    from collections import Counter

    categories = Counter()
    subcategories = Counter()
    topics = Counter()
    languages = Counter()

    for chunk in chunks:
        meta = chunk.metadata
        categories[meta.get('category', 'Unknown')] += 1
        subcategories[meta.get('subcategory', 'Unknown')] += 1
        topics[meta.get('topic', 'Unknown')] += 1
        if meta.get('languages'):
            # languages现在是逗号分隔的字符串，需要先分割
            lang_list = meta['languages'].split(', ') if meta['languages'] else []
            for lang in lang_list:
                if lang:  # 确保不是空字符串
                    languages[lang] += 1

    print("\n" + "="*60)
    print("分类汇总 (Classification Summary)")
    print("="*60)

    print("\n【主要分类 Category】")
    for cat, count in categories.most_common():
        print(f"  • {cat}: {count} chunks")

    print("\n【子分类 Subcategory】")
    for sub, count in subcategories.most_common(10):
        print(f"  • {sub}: {count} chunks")

    print("\n【主题 Topic (Top 10)】")
    for topic, count in topics.most_common(10):
        print(f"  • {topic}: {count} chunks")

    if languages:
        print("\n【编程语言 Languages】")
        for lang, count in languages.most_common():
            print(f"  • {lang}: {count} chunks")

    print("="*60 + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest markdown into Chroma collection with automatic classification")
    # Default to a local 'docs' directory next to this script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_docs_dir = os.path.join(base_dir, "docs")
    parser.add_argument("--docs-dir", type=str, default=default_docs_dir, help="Directory to recursively read *.md files")
    parser.add_argument("--collection", type=str, default=os.getenv("CHROMA_COLLECTION", "md_docs"), help="Chroma collection name")
    parser.add_argument("--chroma-host", type=str, default=os.getenv("CHROMA_HOST", "localhost"), help="Chroma server host")
    parser.add_argument("--chroma-port", type=int, default=int(os.getenv("CHROMA_PORT", "9000")), help="Chroma server port")
    parser.add_argument("--embed-model", type=str, default=os.getenv("EMBED_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"), help="Embedding model name")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Chunk size for splitting")
    parser.add_argument("--chunk-overlap", type=int, default=200, help="Chunk overlap for splitting")
    parser.add_argument("--no-classification", action="store_true", help="Disable automatic classification")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        # Ensure the docs directory exists
        os.makedirs(args.docs_dir, exist_ok=True)

        print(f"\n{'='*60}")
        print("ChromaDB 自动分类入库工具")
        print("Automatic Classification Ingestion Tool")
        print(f"{'='*60}\n")

        count = ingest_markdown(
            docs_dir=args.docs_dir,
            collection_name=args.collection,
            host=args.chroma_host,
            port=args.chroma_port,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            embed_model_name=args.embed_model,
            enable_auto_classification=not args.no_classification,
        )
        if count == 0:
            print(f"[Info] No markdown files found in '{args.docs_dir}'. Nothing ingested.")
        else:
            print(f"\n[Info] Successfully ingested {count} chunks into collection '{args.collection}'.")
            print(f"[Info] You can now query with category filters!")
    except Exception as e:
        print(f"[Error] Ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()