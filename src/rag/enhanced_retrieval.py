"""Enhanced RAG retrieval system with improved efficiency."""

# 配置环境变量以避免tokenizers警告
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from sentence_transformers import CrossEncoder
import re
from collections import defaultdict

logger = logging.getLogger(__name__)

# Performance timing flag - can be enabled via environment variable
ENABLE_TIMING = os.getenv("PRTS_ENABLE_TIMING", "true").lower() == "true"


def _log_timing(step_name: str, elapsed: float, extra_info: str = ""):
    """Log timing information for a processing step."""
    if ENABLE_TIMING:
        info = f" | {extra_info}" if extra_info else ""
        print(f"[TIMING] {step_name}: {elapsed*1000:.1f}ms{info}")

from langchain_core.documents import Document


@dataclass
class RetrievalConfig:
    """Configuration for enhanced retrieval."""
    # Embedding settings
    embedding_model: str = os.getenv('EMBED_MODEL_NAME', 'BAAI/bge-large-zh-v1.5')  # 默认使用中文优化模型
    
    # Retrieval parameters - optimized for speed and conciseness
    initial_k: int = 4   # Reduced from 8 for faster retrieval
    final_k: int = 2     # Reduced from 4 for more focused context
    similarity_threshold: float = 0.7
    
    # Reranking settings
    use_reranking: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    # Query enhancement - disable rewrite for speed
    enable_query_expansion: bool = True
    enable_query_rewrite: bool = False  # Disabled for faster queries
    
    # Context building - reduced for concise responses
    max_context_length: int = 4000  # Reduced from 8000
    enable_deduplication: bool = True
    similarity_dedup_threshold: float = 0.85


class QueryEnhancer:
    """Enhance user queries for better retrieval."""
    
    def __init__(self):
        # Technical term mappings for query expansion
        self.tech_synonyms = {
            "api": ["API", "接口", "应用程序接口"],
            "database": ["DB", "数据库", "存储"],
            "function": ["函数", "方法", "method"],
            "class": ["类", "对象", "object"],
            "bug": ["错误", "问题", "issue", "故障"],
            "performance": ["性能", "效率", "速度", "优化"],
            "config": ["配置", "设置", "参数", "configuration"],
            "deploy": ["部署", "发布", "deployment"],
            "test": ["测试", "检验", "验证", "testing"],
            "debug": ["调试", "排错", "troubleshoot"]
        }
    
    def expand_query(self, query: str) -> str:
        """Expand query with technical synonyms."""
        if not query:
            return query
            
        expanded_terms = []
        query_lower = query.lower()
        
        for term, synonyms in self.tech_synonyms.items():
            if term in query_lower:
                # Add synonyms to enhance matching
                expanded_terms.extend([syn for syn in synonyms if syn not in query])
        
        if expanded_terms:
            return f"{query} {' '.join(expanded_terms[:3])}"  # Limit to avoid noise
        return query
    
    def rewrite_query(self, query: str) -> List[str]:
        """Generate alternative query formulations."""
        queries = [query]
        
        # If query is a question, try statement form
        if query.strip().endswith('?'):
            statement = query.rstrip('?').replace('如何', '').replace('怎么', '')
            if statement != query:
                queries.append(statement.strip())
        
        # If query contains "如何/怎么", generate direct form
        if any(word in query for word in ['如何', '怎么', 'how to']):
            direct_form = re.sub(r'(如何|怎么|how to)\s*', '', query, flags=re.IGNORECASE)
            if direct_form.strip():
                queries.append(direct_form.strip())
        
        # Extract key technical terms for focused search
        tech_terms = []
        for word in query.split():
            if len(word) > 2 and (word.isalpha() or word in self.tech_synonyms):
                tech_terms.append(word)
        
        if len(tech_terms) >= 2:
            queries.append(' '.join(tech_terms))
        
        return list(set(queries))  # Remove duplicates


class ContentDeduplicator:
    """Remove similar/duplicate content from retrieved documents."""
    
    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
        self.embeddings_cache = {}
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate semantic similarity between two texts."""
        # Simple approach using word overlap for now
        # Can be enhanced with embeddings
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def deduplicate(self, documents: List[Document]) -> List[Document]:
        """Remove similar documents based on content similarity."""
        if len(documents) <= 1:
            return documents
        
        unique_docs = []
        for i, doc in enumerate(documents):
            is_duplicate = False
            
            for existing_doc in unique_docs:
                similarity = self.calculate_similarity(doc.page_content, existing_doc.page_content)
                if similarity > self.similarity_threshold:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_docs.append(doc)
        
        return unique_docs


class DocumentReranker:
    """Rerank retrieved documents based on query relevance."""
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        try:
            self.reranker = CrossEncoder(model_name)
            self.available = True
        except Exception as e:
            print(f"Warning: Could not load reranker model {model_name}: {e}")
            self.available = False
    
    def rerank(self, query: str, documents: List[Document], top_k: int = 4) -> List[Document]:
        """Rerank documents based on query-document relevance."""
        if not self.available or len(documents) <= top_k:
            return documents[:top_k]
        
        try:
            # Prepare query-document pairs
            pairs = [(query, doc.page_content[:1000]) for doc in documents]  # Limit content length
            
            # Get relevance scores
            scores = self.reranker.predict(pairs)
            
            # Sort documents by score (descending)
            scored_docs = list(zip(documents, scores))
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            
            # Return top-k reranked documents
            return [doc for doc, _ in scored_docs[:top_k]]
            
        except Exception as e:
            print(f"Warning: Reranking failed: {e}")
            return documents[:top_k]


class EnhancedRAGRetriever:
    """Enhanced RAG retriever with query enhancement and reranking."""
    
    def __init__(self, base_retriever, config: RetrievalConfig = None):
        self.base_retriever = base_retriever
        self.config = config or RetrievalConfig()
        
        # Copy search_kwargs from base retriever if it exists
        if hasattr(base_retriever, 'search_kwargs'):
            self.search_kwargs = base_retriever.search_kwargs.copy()
        else:
            self.search_kwargs = {"k": self.config.k}
        
        # Initialize components
        self.query_enhancer = QueryEnhancer()
        self.deduplicator = ContentDeduplicator(self.config.similarity_dedup_threshold)
        self.reranker = DocumentReranker(self.config.reranker_model) if self.config.use_reranking else None
        
        # Metrics tracking
        self.retrieval_stats = {
            "total_queries": 0,
            "avg_initial_results": 0,
            "avg_final_results": 0,
            "reranking_enabled": self.config.use_reranking
        }
    
    def retrieve(self, query: str, **kwargs) -> List[Document]:
        """Enhanced retrieval with query processing and reranking."""
        total_start = time.time()
        self.retrieval_stats["total_queries"] += 1
        
        # Step 1: Query enhancement
        step_start = time.time()
        enhanced_queries = self._enhance_query(query)
        _log_timing("查询增强", time.time() - step_start, f"生成 {len(enhanced_queries)} 个查询变体")
        
        # Step 2: Retrieve from multiple query variants
        step_start = time.time()
        all_documents = []
        for enhanced_query in enhanced_queries:
            docs = self._retrieve_base(enhanced_query, **kwargs)
            all_documents.extend(docs)
        _log_timing("向量检索", time.time() - step_start, f"检索到 {len(all_documents)} 条文档")
        
        initial_count = len(all_documents)
        self.retrieval_stats["avg_initial_results"] = (
            (self.retrieval_stats["avg_initial_results"] * (self.retrieval_stats["total_queries"] - 1) + initial_count) 
            / self.retrieval_stats["total_queries"]
        )
        
        # Step 3: Deduplication
        if self.config.enable_deduplication:
            step_start = time.time()
            before_dedup = len(all_documents)
            all_documents = self.deduplicator.deduplicate(all_documents)
            _log_timing("去重处理", time.time() - step_start, f"{before_dedup} → {len(all_documents)} 条")
        
        # Step 4: Reranking
        if self.reranker:
            step_start = time.time()
            all_documents = self.reranker.rerank(query, all_documents, self.config.final_k)
            _log_timing("重排序", time.time() - step_start, f"保留 top-{self.config.final_k}")
        else:
            all_documents = all_documents[:self.config.final_k]
        
        final_count = len(all_documents)
        self.retrieval_stats["avg_final_results"] = (
            (self.retrieval_stats["avg_final_results"] * (self.retrieval_stats["total_queries"] - 1) + final_count) 
            / self.retrieval_stats["total_queries"]
        )
        
        _log_timing("检索总耗时", time.time() - total_start, f"最终 {final_count} 条文档")
        return all_documents
    
    def get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
        """LangChain-compatible method for document retrieval."""
        return self.retrieve(query, **kwargs)
    
    def _enhance_query(self, query: str) -> List[str]:
        """Apply query enhancement techniques."""
        queries = [query]  # Always include original
        
        if self.config.enable_query_expansion:
            expanded = self.query_enhancer.expand_query(query)
            if expanded != query:
                queries.append(expanded)
        
        if self.config.enable_query_rewrite:
            rewritten = self.query_enhancer.rewrite_query(query)
            queries.extend([q for q in rewritten if q not in queries])
        
        return queries[:3]  # Limit to prevent too many queries
    
    def _retrieve_base(self, query: str, **kwargs) -> List[Document]:
        """Retrieve using base retriever."""
        # Update search kwargs with initial_k
        search_kwargs = kwargs.copy()
        search_kwargs['k'] = self.config.initial_k
        
        try:
            # Try different methods based on retriever type
            if hasattr(self.base_retriever, 'get_relevant_documents'):
                # LangChain retriever
                original_k = getattr(self.base_retriever, 'k', None)
                if hasattr(self.base_retriever, 'k'):
                    self.base_retriever.k = self.config.initial_k
                try:
                    results = self.base_retriever.get_relevant_documents(query)
                finally:
                    if original_k is not None:
                        self.base_retriever.k = original_k
                return results
            elif hasattr(self.base_retriever, 'invoke'):
                # Runnable interface
                return self.base_retriever.invoke(query)
            else:
                # Fallback: assume it's callable
                return self.base_retriever(query)
        except Exception as e:
            logger.error(f"Error in base retriever: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get retrieval statistics."""
        return self.retrieval_stats.copy()


def _format_arknights_doc(doc: Document, index: int) -> str:
    """Format Arknights document with specialized template.
    
    Args:
        doc: The document to format
        index: Document index number
        
    Returns:
        Formatted document string
    """
    metadata = doc.metadata
    doc_type = metadata.get('doc_type', 'general')
    content = doc.page_content.strip()
    
    if doc_type == 'operator':
        # Operator document format
        rarity = metadata.get('rarity', '')
        op_class = metadata.get('operator_class', '')
        topic = metadata.get('topic', '')
        
        header_parts = [f"【干员档案 #{index}】"]
        if topic:
            header_parts.append(f"代号: {topic}")
        if rarity:
            header_parts.append(f"稀有度: {rarity}")
        if op_class:
            header_parts.append(f"职业: {op_class}")
            
        header = " | ".join(header_parts)
        return f"{header}\n{content}\n"
        
    elif doc_type == 'story':
        # Story document format
        story_type = metadata.get('story_type', '')
        chapter = metadata.get('chapter', '')
        characters = metadata.get('characters', '')
        topic = metadata.get('topic', '')
        
        header_parts = [f"【剧情档案 #{index}】"]
        if topic:
            header_parts.append(f"标题: {topic}")
        if story_type:
            type_map = {'mainline': '主线', 'event': '活动', 'character': '干员密录'}
            header_parts.append(f"类型: {type_map.get(story_type, story_type)}")
        if chapter:
            header_parts.append(f"章节: {chapter}")
        if characters:
            header_parts.append(f"登场角色: {characters[:50]}")
            
        header = " | ".join(header_parts)
        return f"{header}\n{content}\n"
    
    else:
        # General document format
        source = metadata.get('source', 'unknown')
        category = metadata.get('category', 'general')
        return f"[档案 #{index}] {category} | 来源: {source}\n{content}\n"


def build_enhanced_context(query: str, documents: List[Document], max_length: int = 8000) -> str:
    """Build intelligently structured context from retrieved documents.
    
    Includes specialized formatting for Arknights content (operators and stories).
    """
    if not documents:
        return "[WARN] 罗德岛数据库中未找到相关记录。"
    
    context_parts = []
    current_length = 0
    
    # PRTS-style header
    header = f"[QUERY] 博士查询: {query}\n\n==== 罗德岛数据库检索结果 ====\n"
    context_parts.append(header)
    current_length += len(header)
    
    # Count document types for summary
    operator_count = sum(1 for d in documents if d.metadata.get('doc_type') == 'operator')
    story_count = sum(1 for d in documents if d.metadata.get('doc_type') == 'story')
    
    if operator_count > 0 or story_count > 0:
        summary = f"[INFO] 找到 {len(documents)} 条相关记录"
        if operator_count > 0:
            summary += f" (干员: {operator_count})"
        if story_count > 0:
            summary += f" (剧情: {story_count})"
        context_parts.append(summary + "\n")
        current_length += len(summary) + 1
    
    # Process documents with Arknights-specific formatting
    for i, doc in enumerate(documents, 1):
        formatted_doc = _format_arknights_doc(doc, i)
        
        # Truncate if needed to fit max length
        available_space = max_length - current_length - 100  # Buffer
        if available_space <= 0:
            context_parts.append(f"\n[WARN] 已截断，还有 {len(documents) - i + 1} 条记录未显示")
            break
            
        if len(formatted_doc) > available_space:
            formatted_doc = formatted_doc[:available_space] + "...\n"
        
        context_parts.append(formatted_doc)
        current_length += len(formatted_doc)
    
    context_parts.append("\n==== 检索结束 ====")
    
    return "\n".join(context_parts)