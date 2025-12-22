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
from langchain_chroma import Chroma
import chromadb
from chromadb.config import Settings

# 导入我们统一的嵌入模型配置
from src.config import get_global_embeddings
from src.config.llm_config import create_chroma_client


def detect_content_type(content: str, file_path: str) -> str:
    """
    检测文档内容类型: operator(干员) / story(剧情) / general(通用)

    检测优先级:
    1. YAML头中的 content_type 字段
    2. 文件路径特征
    3. 内容关键词
    """
    content_lower = content.lower()

    # 1. 优先检查YAML头中的 content_type
    if 'content_type: story' in content_lower:
        return 'story'
    if 'content_type: character' in content_lower or 'content_category: character' in content_lower:
        return 'operator'

    # 2. 检查文件路径
    if file_path:
        path_lower = file_path.lower()
        if '干员' in path_lower or '/operator' in path_lower:
            return 'operator'
        if '剧情' in path_lower or 'story' in path_lower:
            return 'story'
        if '主线剧情一览' in file_path or '活动剧情一览' in file_path:
            return 'story'

    # 3. 回退到内容关键词检测
    # 剧情特征：对话格式、登场角色列表
    story_indicators = [
        'dialogue_count:', 'narration_count:', 'characters:',
        '## 剧情内容', '行动前', '行动后'
    ]
    story_score = sum(1 for ind in story_indicators if ind in content)

    # 干员特征：技能、天赋、属性
    operator_indicators = [
        '## 天赋', '## 技能', '## 属性', '## 干员信息',
        '精英化', '攻击力', '防御力', '法术抗性'
    ]
    operator_score = sum(1 for ind in operator_indicators if ind in content)

    if story_score > operator_score:
        return 'story'
    elif operator_score > 0:
        return 'operator'

    return 'general'


def smart_chunk_arknights_docs(docs, chunk_size: int, chunk_overlap: int):
    """为明日方舟干员文档优化的智能分块策略"""
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


def smart_chunk_story_docs(docs, chunk_size: int, chunk_overlap: int):
    """为剧情文档优化的智能分块策略 - 保持对话连贯性"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    # 剧情文档分隔符 - 优先在对话边界分割
    story_separators = [
        "\n## ",       # 章节标题（如 "## 剧情内容"）
        "\n### ",      # 子章节
        "\n---\n",     # YAML分隔线
        "\n\n**",      # 新角色对话开始（**角色名**:）
        "\n\n*",       # 旁白段落开始（*旁白内容*）
        "\n\n",        # 段落分隔
        "\n",          # 单换行
        "。",          # 中文句号
        "！",          # 中文感叹号
        "？",          # 中文问号
        " ",           # 空格
        ""
    ]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=story_separators,
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


# 移除本地定义的build_embeddings和create_chroma_client函数，使用统一的导入版本


def _extract_story_metadata(content: str, file_path: str = "") -> Dict[str, any]:
    """
    从剧情文档提取元数据

    Args:
        content: 文档内容
        file_path: 文件路径

    Returns:
        Dict包含: story_type, chapter, characters, dialogue_count, narration_count
    """
    metadata = {
        "story_type": "general",
        "chapter": "",
        "characters": [],
        "dialogue_count": 0,
        "narration_count": 0
    }

    # 1. 从YAML头提取（剧情文档已有这些字段）
    # 提取 dialogue_count
    dialogue_match = re.search(r'dialogue_count:\s*(\d+)', content)
    if dialogue_match:
        metadata["dialogue_count"] = int(dialogue_match.group(1))

    # 提取 narration_count
    narration_match = re.search(r'narration_count:\s*(\d+)', content)
    if narration_match:
        metadata["narration_count"] = int(narration_match.group(1))

    # 提取 characters
    characters_match = re.search(r'characters:\s*(.+?)(?:\n|$)', content)
    if characters_match:
        chars_str = characters_match.group(1).strip()
        metadata["characters"] = [c.strip() for c in chars_str.split(',') if c.strip()]

    # 2. 从路径推断剧情类型和章节
    if file_path:
        path_parts = Path(file_path).parts

        # 查找剧情类型
        if '主线剧情一览' in path_parts:
            metadata["story_type"] = "mainline"
            # 章节名是主线剧情一览的下一级目录
            try:
                idx = path_parts.index('主线剧情一览')
                if idx + 1 < len(path_parts) - 1:  # 确保有下一级目录
                    metadata["chapter"] = path_parts[idx + 1]
            except (ValueError, IndexError):
                pass
        elif '活动剧情一览' in path_parts:
            metadata["story_type"] = "event"
            # 活动名是活动剧情一览的下一级目录
            try:
                idx = path_parts.index('活动剧情一览')
                if idx + 1 < len(path_parts) - 1:
                    metadata["chapter"] = path_parts[idx + 1]
            except (ValueError, IndexError):
                pass
        elif '干员密录' in str(file_path) or '悖论模拟' in str(file_path):
            metadata["story_type"] = "character"

    # 3. 如果没有从YAML提取到角色，尝试从对话中提取
    if not metadata["characters"]:
        # 匹配 **角色名**: 格式
        dialogue_pattern = re.findall(r'\*\*([^*]+)\*\*:', content)
        if dialogue_pattern:
            # 去重并保持顺序
            seen = set()
            unique_chars = []
            for char in dialogue_pattern:
                if char not in seen:
                    seen.add(char)
                    unique_chars.append(char)
            metadata["characters"] = unique_chars[:20]  # 最多保留20个角色

    return metadata


def classify_by_path(file_path: str) -> Dict[str, str]:
    """根据文件路径进行目录分类（支持干员和剧情）"""
    path = Path(file_path)
    path_parts = path.parts

    # 初始化分类
    category = "Arknights"
    subcategory = "General"
    topic = path.stem  # 文件名作为主题

    # 规则1: 明日方舟内容分类（优先检测）
    path_str = str(file_path)

    # 干员文档
    if '干员' in path_str or '/operator' in path_str.lower():
        subcategory = "Operator"
        topic = path.stem  # 干员名称

    # 主线剧情
    elif '主线剧情一览' in path_str:
        subcategory = "MainStory"
        # 提取章节名（主线剧情一览的下一级目录）
        try:
            idx = path_parts.index('主线剧情一览')
            if idx + 1 < len(path_parts) - 1:
                topic = path_parts[idx + 1]  # 章节名如"风暴瞭望"
        except (ValueError, IndexError):
            pass

    # 活动剧情
    elif '活动剧情一览' in path_str:
        subcategory = "EventStory"
        # 提取活动名
        try:
            idx = path_parts.index('活动剧情一览')
            if idx + 1 < len(path_parts) - 1:
                topic = path_parts[idx + 1]  # 活动名如"将进酒"
        except (ValueError, IndexError):
            pass

    # 其他剧情
    elif '剧情' in path_str or 'story' in path_str.lower():
        subcategory = "Story"

    # 规则2: 技术文档分类
    elif len(path_parts) > 1:
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

    return {
        "category": category,
        "subcategory": subcategory or "General",
        "topic": topic,
        "source_type": "markdown"
    }


def classify_by_content(content: str, file_path: str) -> Dict[str, any]:
    """根据文档内容进行主题分类（支持干员和剧情）"""
    content_lower = content.lower()

    # 首先检测内容类型
    doc_type = detect_content_type(content, file_path)

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

        # 剧情相关（新增）
        "Story_Mainline": ["主线", "mainline", "章节", "chapter"],
        "Story_Event": ["活动", "event", "限时"],
        "Story_Dialogue": ["对话", "dialogue", "台词"],
        "Story_Narration": ["旁白", "narration", "场景描述"],

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
        "Nation": ["炎国", "yan", "维多利亚", "victoria", "乌萨斯", "ursus", "哥伦比亚", "columbia",
                   "拉特兰", "laterano", "卡西米尔", "kazimierz", "莱塔尼亚", "leithanien"],
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

    # 根据文档类型确定 content_type
    if doc_type == "story":
        content_type_value = "story"
    elif doc_type == "operator":
        if any(word in content_lower for word in ["技能", "skill", "天赋"]):
            content_type_value = "skill_info"
        else:
            content_type_value = "operator_profile"
    else:
        content_type_value = "reference"

    return {
        "topics": detected_topics if detected_topics else ["General"],
        "game_elements": detected_elements if detected_elements else [],
        "content_type": content_type_value,
        "doc_type": doc_type,  # 新增：文档类型标识
        "rarity": _extract_rarity(content_lower) if doc_type == "operator" else "",
        "operator_class": _extract_operator_class(content_lower) if doc_type == "operator" else ""
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
    """为文档添加丰富的metadata（支持干员和剧情）"""
    # 基础路径分类
    path_meta = classify_by_path(original_path)

    # 内容分类
    content_meta = classify_by_content(doc.page_content, original_path)

    # 检测文档类型
    doc_type = content_meta.get("doc_type", "general")

    # 基础metadata（所有文档共有）
    enriched_metadata = {
        # 路径分类
        "category": path_meta["category"],
        "subcategory": path_meta["subcategory"],
        "topic": path_meta["topic"],
        "source_type": path_meta["source_type"],

        # 内容分类
        "topics": ", ".join(content_meta["topics"]) if isinstance(content_meta["topics"], list) else content_meta["topics"],
        "game_elements": ", ".join(content_meta["game_elements"]) if isinstance(content_meta["game_elements"], list) and content_meta["game_elements"] else "",
        "content_type": content_meta["content_type"],
        "doc_type": doc_type,

        # 系统信息
        "source": original_path,
        "file_name": os.path.basename(original_path),
        "ingested_at": "2024-11-10"
    }

    # 根据文档类型添加特定metadata
    if doc_type == "story":
        # 剧情文档特有字段
        story_meta = _extract_story_metadata(doc.page_content, original_path)
        enriched_metadata.update({
            "story_type": story_meta["story_type"],
            "chapter": story_meta["chapter"],
            "characters": ", ".join(story_meta["characters"]) if story_meta["characters"] else "",
            "dialogue_count": str(story_meta["dialogue_count"]),
            "narration_count": str(story_meta["narration_count"]),
            # 剧情文档不需要干员字段
            "rarity": "",
            "operator_class": ""
        })
    elif doc_type == "operator":
        # 干员文档特有字段
        enriched_metadata.update({
            "rarity": content_meta.get("rarity", ""),
            "operator_class": content_meta.get("operator_class", ""),
            # 干员文档不需要剧情字段
            "story_type": "",
            "chapter": "",
            "characters": "",
            "dialogue_count": "",
            "narration_count": ""
        })
    else:
        # 通用文档
        enriched_metadata.update({
            "rarity": content_meta.get("rarity", ""),
            "operator_class": content_meta.get("operator_class", ""),
            "story_type": "",
            "chapter": "",
            "characters": "",
            "dialogue_count": "",
            "narration_count": ""
        })

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
        use_smart_chunking: Whether to use smart chunking based on content type

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

    # If no docs loaded, return early
    if not docs:
        return 0

    # 智能分块：根据文档类型选择不同的分块策略
    if use_smart_chunking:
        # 按文档类型分类
        operator_docs = []
        story_docs = []
        general_docs = []

        for doc in docs:
            source_path = doc.metadata.get('source', '')
            doc_type = detect_content_type(doc.page_content, source_path)

            if doc_type == 'operator':
                operator_docs.append(doc)
            elif doc_type == 'story':
                story_docs.append(doc)
            else:
                general_docs.append(doc)

        print(f"[Info] Document type distribution:")
        print(f"  - Operator docs: {len(operator_docs)}")
        print(f"  - Story docs: {len(story_docs)}")
        print(f"  - General docs: {len(general_docs)}")

        # 对不同类型的文档使用不同的分块策略
        chunks = []

        if operator_docs:
            operator_chunks = smart_chunk_arknights_docs(operator_docs, chunk_size, chunk_overlap)
            chunks.extend(operator_chunks)
            print(f"[Info] Operator chunks: {len(operator_chunks)}")

        if story_docs:
            story_chunks = smart_chunk_story_docs(story_docs, chunk_size, chunk_overlap)
            chunks.extend(story_chunks)
            print(f"[Info] Story chunks: {len(story_chunks)}")

        if general_docs:
            # 通用文档使用默认分块
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=["\n\n", "\n", "。", r"\. ", " ", ""]
            )
            general_chunks = splitter.split_documents(general_docs)
            chunks.extend(general_chunks)
            print(f"[Info] General chunks: {len(general_chunks)}")

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

    embeddings = get_global_embeddings(model_name=embed_model_name)
    client = create_chroma_client(host, port)

    # 创建带有分类信息的collection metadata
    # 注意：ChromaDB只支持简单类型(str, int, float, bool)，不支持嵌套字典
    collection_metadata = {
        "description": "Auto-classified knowledge base",
        "version": "1.0",
        "auto_classification": str(enable_auto_classification).lower(),
        "ingestion_date": "2024-11-10"
    }

    # 批量处理避免 payload 过大
    batch_size = 500  # 每批处理500个chunks
    total_chunks = len(enriched_chunks)

    print(f"[Info] Ingesting {total_chunks} chunks in batches of {batch_size}...")

    for i in range(0, total_chunks, batch_size):
        batch = enriched_chunks[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total_chunks + batch_size - 1) // batch_size

        print(f"[Info] Processing batch {batch_num}/{total_batches} ({len(batch)} chunks)...")

        if i == 0:
            # 第一批：创建新的collection
            _vs = Chroma.from_documents(
                documents=batch,
                embedding=embeddings,
                collection_name=collection_name,
                client=client,
                collection_metadata=collection_metadata,
            )
        else:
            # 后续批次：添加到现有collection
            _vs.add_documents(documents=batch)

    # Print classification summary
    print_classification_summary(enriched_chunks)

    return len(enriched_chunks)


def print_classification_summary(chunks):
    """打印分类汇总信息（支持干员和剧情统计）"""
    from collections import Counter

    categories = Counter()
    subcategories = Counter()
    topics = Counter()
    doc_types = Counter()
    story_types = Counter()
    chapters = Counter()
    characters = Counter()
    operator_classes = Counter()

    for chunk in chunks:
        meta = chunk.metadata
        categories[meta.get('category', 'Unknown')] += 1
        subcategories[meta.get('subcategory', 'Unknown')] += 1
        topics[meta.get('topic', 'Unknown')] += 1
        doc_types[meta.get('doc_type', 'Unknown')] += 1

        # 剧情统计
        if meta.get('story_type'):
            story_types[meta.get('story_type')] += 1
        if meta.get('chapter'):
            chapters[meta.get('chapter')] += 1
        if meta.get('characters'):
            # characters是逗号分隔的字符串
            char_list = meta['characters'].split(', ') if meta['characters'] else []
            for char in char_list:
                if char.strip():
                    characters[char.strip()] += 1

        # 干员统计
        if meta.get('operator_class') and meta.get('operator_class') != 'Unknown':
            operator_classes[meta.get('operator_class')] += 1

    print("\n" + "="*60)
    print("分类汇总 (Classification Summary)")
    print("="*60)

    print("\n【文档类型 Doc Type】")
    for dtype, count in doc_types.most_common():
        print(f"  • {dtype}: {count} chunks")

    print("\n【主要分类 Category】")
    for cat, count in categories.most_common():
        print(f"  • {cat}: {count} chunks")

    print("\n【子分类 Subcategory】")
    for sub, count in subcategories.most_common(10):
        print(f"  • {sub}: {count} chunks")

    print("\n【主题/章节 Topic (Top 10)】")
    for topic, count in topics.most_common(10):
        print(f"  • {topic}: {count} chunks")

    # 剧情相关统计
    if story_types:
        print("\n【剧情类型 Story Type】")
        for stype, count in story_types.most_common():
            print(f"  • {stype}: {count} chunks")

    if chapters:
        print("\n【剧情章节 Chapters (Top 10)】")
        for chapter, count in chapters.most_common(10):
            print(f"  • {chapter}: {count} chunks")

    if characters:
        print("\n【登场角色 Characters (Top 15)】")
        for char, count in characters.most_common(15):
            print(f"  • {char}: {count} appearances")

    # 干员相关统计
    if operator_classes:
        print("\n【干员职业 Operator Class】")
        for op_class, count in operator_classes.most_common():
            print(f"  • {op_class}: {count} chunks")

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
    parser.add_argument("--embed-model", type=str, default=os.getenv("EMBED_MODEL_NAME", "BAAI/bge-large-zh-v1.5"), help="Embedding model name")
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