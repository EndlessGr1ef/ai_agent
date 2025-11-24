import os
import sys
import argparse
import re
from typing import Dict, List, Tuple
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 解决HuggingFace tokenizers警告
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['TRANSFORMERS_NO_ADVISORY_WARNINGS'] = '1'

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
import chromadb
from chromadb.config import Settings


def smart_chunk_arknights_docs(docs, chunk_size: int, chunk_overlap: int):
    """为明日方舟文档优化的智能分块策略"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    
    # 针对中文和结构化内容的分隔符
    arknights_separators = [
        "\n## ",  # 二级标题
        "\n### ",  # 三级标题  
        "\n\n",  # 双换行
        "\n技能",  # 技能部分
        "\n天赋",  # 天赋部分
        "\n特性",  # 特性部分
        "\n基础信息",  # 基础信息部分
        "。\n",  # 中文句号
        "\n",     # 单换行
        "。",     # 中文句号
        r"\. ",    # 英文句号
        " ",      # 空格
        ""
    ]
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=arknights_separators,
        keep_separator=True  # 保持分隔符以维持上下文
    )
    
    return splitter.split_documents(docs)


def _extract_rarity(content_lower: str) -> str:
    """提取干员稀有度"""
    rarity_patterns = {
        "6星": ["6星", "6☆", "6★", "六星"],
        "5星": ["5星", "5☆", "5★", "五星"],
        "4星": ["4星", "4☆", "4★", "四星"],
        "3星": ["3星", "3☆", "3★", "三星"],
        "2星": ["2星", "2☆", "2★", "二星"],
        "1星": ["1星", "1☆", "1★", "一星"]
    }
    
    for rarity, patterns in rarity_patterns.items():
        for pattern in patterns:
            if pattern.lower() in content_lower:
                return rarity
    return "未知"


def _extract_operator_class(content_lower: str) -> str:
    """提取干员职业"""
    class_patterns = {
        "先锋": ["先锋", "vanguard"],
        "近卫": ["近卫", "guard"],
        "重装": ["重装", "defender"],
        "狙击": ["狙击", "sniper"],
        "术师": ["术师", "caster"],
        "医疗": ["医疗", "medic"],
        "辅助": ["辅助", "supporter"],
        "特种": ["特种", "specialist"]
    }
    
    for op_class, patterns in class_patterns.items():
        for pattern in patterns:
            if pattern.lower() in content_lower:
                return op_class
    return "未知"


def build_embeddings(model_name: str | None = None) -> HuggingFaceEmbeddings:
    if not model_name:
        # 优先选择中文优化模型，回退到通用模型
        model_name = os.getenv("EMBED_MODEL_NAME", "BAAI/bge-large-zh-v1.5")
    
    print(f"📊 使用嵌入模型: {model_name}")
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={'device': 'cpu'},  # 可根据需要改为'cuda'
        encode_kwargs={'normalize_embeddings': True}  # 正则化嵌入向量
    )


def create_chroma_client(host: str, port: int) -> chromadb.HttpClient:
    settings = Settings(allow_reset=True, anonymized_telemetry=False)
    return chromadb.HttpClient(host=host, port=port, settings=settings)


def classify_by_path(file_path: str) -> Dict[str, str]:
    """根据文件路径进行目录分类（明日方舟优化版）"""
    path = Path(file_path)
    path_parts = path.parts

    # 初始化分类
    category = "Arknights"
    subcategory = "Operator"
    topic = path.stem  # 文件名作为主题（干员名称）

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

    # 规刱2: 文件名关键词分类（明日方舟专用）
    filename = path.name.lower()
    if subcategory == "Operator":  # 进一步细分干员类型
        # 根据干员名称特征判断类型（可以根据实际数据调整）
        if any(char in filename for char in ['银灰', '陈', '博士', 'dr.']):
            subcategory = "Special_Operator"
        elif any(char in filename for char in ['阿米娅', '波卢']):
            subcategory = "Collaboration_Operator"
    
    # 技术文档备用分类
    if category == "Arknights" and any(keyword in filename for keyword in ['tech', '技术', '文档']):
        category = "Technical"
        subcategory = "Documentation"

    return {
        "category": category,
        "subcategory": subcategory or "General",
        "topic": topic,
        "source_type": "markdown"
    }


def classify_by_content(content: str, file_path: str) -> Dict[str, any]:
    """根据文档内容进行主题分类（明日方舟优化版）"""
    content_lower = content.lower()

    # 明日方舟主题关键词映射
    topic_keywords = {
        # 干员相关
        "Operator_Info": ["干员", "operator", "稀有度", "rarity", "职业", "class", "分支", "branch"],
        "Operator_Skills": ["技能", "skill", "天赋", "talent", "特性", "trait"],
        "Operator_Stats": ["攻击力", "attack", "生命值", "hp", "防御力", "defense", "法术抗性", "res"],
        
        # 职业分类
        "Vanguard": ["先锋", "vanguard", "尖兵", "冲锋手", "战术家", "执旗手", "情报官", "策士"],
        "Guard": ["近卫", "guard", "强攻手", "斗士", "术战者", "教官", "领主", "剑豪"],
        "Defender": ["重装", "defender", "铁卫", "守护者", "不屈者", "驭法铁卫"],
        "Sniper": ["狙击", "sniper", "速射手", "重射手", "炮手", "神射手"],
        "Caster": ["术师", "caster", "中坚术师", "扩散术师", "驭械术师"],
        "Medic": ["医疗", "medic", "医师", "群愈师", "疗养师"],
        "Supporter": ["辅助", "supporter", "凝滞师", "削弱者", "吐游者"],
        "Specialist": ["特种", "specialist", "处决者", "推击手", "伏击客"],
        
        # 游戏机制
        "Game_Mechanics": ["部署费用", "cost", "再部署时间", "redeploy", "攻击间隔", "interval"],
        "Combat_System": ["阻挡", "block", "攻击范围", "range", "伤害类型", "damage"],
        
        # 技术文档备用
        "Technical": ["api", "database", "rag", "embedding", "vector", "retrieval"]
    }

    # 明日方舟元素识别
    game_elements = {
        "Rarity": ["一星", "二星", "三星", "四星", "五星", "六星", "1★", "2★", "3★", "4★", "5★", "6★"],
        "Faction": ["罗德岛", "rhodes island", "企鹅物流", "penguin logistics", "黑钢", "blacksteel"],
        "Nation": ["炎国", "yan", "维多利亚", "victoria", "乌萨斯", "ursus", "哥伦比亚", "columbia"],
        "Element": ["物理", "physical", "法术", "arts", "真伤", "true damage"],
        "Position": ["远程位", "ranged", "近战位", "melee"],
        # 技术类型备用
        "Tech_Language": ["python", "go", "javascript", "api", "database"]
    }

    # 匹配主题
    detected_topics = []
    for topic, keywords in topic_keywords.items():
        if any(keyword in content_lower for keyword in keywords):
            detected_topics.append(topic)

    # 匹配游戏元素
    detected_elements = []
    for element, keywords in game_elements.items():
        if any(keyword in content_lower for keyword in keywords):
            detected_elements.append(element)

    # 从文件路径补充信息
    path_classification = classify_by_path(file_path)

    return {
        "topics": detected_topics if detected_topics else ["General"],
        "game_elements": detected_elements if detected_elements else [],
        "content_type": "operator_profile" if any(word in content_lower for word in ["干员", "operator"]) else
                        "skill_info" if any(word in content_lower for word in ["技能", "skill", "天赋"]) else
                        "game_guide" if any(word in content_lower for word in ["攻略", "指南", "guide"]) else
                        "reference",
        "rarity": _extract_rarity(content_lower),
        "operator_class": _extract_operator_class(content_lower)
    }


def classify_arknights_content(content: str, file_path: str = "") -> Dict[str, any]:
    """明日方舟内容分类的主入口函数"""
    # 结合路径和内容分类
    path_classification = classify_by_path(file_path) if file_path else {}
    content_classification = classify_by_content(content, file_path)
    
    # 合并分类结果
    return {
        **path_classification,
        **content_classification,
        "confidence": calculate_classification_confidence(content, content_classification)
    }


def calculate_classification_confidence(content: str, classification: Dict[str, any]) -> float:
    """计算分类置信度"""
    confidence_score = 0.0
    content_lower = content.lower()
    
    # 基于关键词匹配度计算置信度
    if classification.get("rarity") != "Unknown":
        confidence_score += 0.3
    if classification.get("operator_class") != "未知":
        confidence_score += 0.3
    if classification.get("topics") and len(classification["topics"]) > 0:
        confidence_score += 0.2
    if classification.get("game_elements") and len(classification["game_elements"]) > 0:
        confidence_score += 0.2
    
    return min(confidence_score, 1.0)

def _extract_rarity(content: str) -> str:
    """提取干员稀有度"""
    rarity_patterns = {
        "6": ["6★", "六星", "6星"],
        "5": ["5★", "五星", "5星"],
        "4": ["4★", "四星", "4星"],
        "3": ["3★", "三星", "3星"],
        "2": ["2★", "二星", "2星"],
        "1": ["1★", "一星", "1星"]
    }
    
    for rarity, patterns in rarity_patterns.items():
        if any(pattern in content for pattern in patterns):
            return rarity
    return "Unknown"

def _extract_operator_class(content: str) -> str:
    """提取干员职业"""
    class_patterns = {
        "先锋": ["先锋", "vanguard"],
        "近卫": ["近卫", "guard"],
        "重装": ["重装", "defender"],
        "狙击": ["狙击", "sniper"],
        "术师": ["术师", "caster"],
        "医疗": ["医疗", "medic"],
        "辅助": ["辅助", "supporter"],
        "特种": ["特种", "specialist"]
    }
    
    for op_class, patterns in class_patterns.items():
        if any(pattern in content for pattern in patterns):
            return op_class
    return "Unknown"


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

        # 内容分类（针对明日方舟优化）
        "topics": ", ".join(content_meta["topics"]) if isinstance(content_meta["topics"], list) else content_meta["topics"],
        "game_elements": ", ".join(content_meta["game_elements"]) if isinstance(content_meta["game_elements"], list) and content_meta["game_elements"] else "",
        "content_type": content_meta["content_type"],
        "rarity": content_meta["rarity"],
        "operator_class": content_meta["operator_class"],

        # 系统信息
        "source": original_path,
        "file_name": os.path.basename(original_path),
        "ingested_at": "2024-11-10"
    }

    # 更新文档的metadata
    doc.metadata = enriched_metadata
    return doc


def ingest_markdown(docs_dir: str, collection_name: str, host: str, port: int,
                    chunk_size: int = 1500, chunk_overlap: int = 300,
                    embed_model_name: str | None = None, enable_auto_classification: bool = True,
                    use_smart_chunking: bool = True) -> int:
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

    # 智能分块：为明日方舟干员信息优化
    if use_smart_chunking:
        chunks = smart_chunk_arknights_docs(docs, chunk_size, chunk_overlap)
    else:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, 
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", r"\. ", " ", ""]  # 中文优化分隔符
        )
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
    parser.add_argument("--embed-model", type=str, default=os.getenv("EMBED_MODEL_NAME", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"), help="Embedding model name")
    parser.add_argument("--chunk-size", type=int, default=1500, help="Chunk size for splitting")
    parser.add_argument("--chunk-overlap", type=int, default=300, help="Chunk overlap for splitting")
    parser.add_argument("--disable-smart-chunking", action="store_true", help="Disable smart chunking for Arknights content")
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
            use_smart_chunking=not args.disable_smart_chunking,
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