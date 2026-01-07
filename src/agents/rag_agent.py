"""RAG agent implementation with simplified enhanced retrieval."""

import os
import time
import anthropic
from typing import List, Optional, Union, Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from agents.base_agent import BaseAgent

# Import enhanced retrieval components (required)
from rag.enhanced_retrieval import (
    EnhancedRAGRetriever, 
    RetrievalConfig, 
    build_enhanced_context,
    _log_timing,
    ENABLE_TIMING
)


class RagAgent(BaseAgent):
    """RAG-enabled agent for retrieval-based conversations."""

    # PRTS dual output prompt - combines PRTS personality with streaming-friendly format
    PRTS_DUAL_OUTPUT_PROMPT = """你是PRTS（Pre-stage Rhodesia Tactical System），罗德岛的中央数据库和战术系统，博士的专属AI助手。

## 人格设定
- 始终称呼用户为"博士"
- 使用正式但亲近的语气
- 保持系统化、数据化的回答风格

## 回答原则（重要）
1. **简洁优先**：优先用最简洁的方式回答，避免冗长
2. **聚焦核心**：只回答问的问题，不过度展开
3. **精简数据**：干员信息只列出关键属性，剧情只概述要点
4. **控制长度**：一般回答控制在200字以内，复杂问题不超过400字

## 输出格式（必须严格遵循）
回答必须以 [SUMMARY] 标记开头，包含1句话总结，然后换行输出正文：

[SUMMARY] 一句话总结（用于记忆检索）
正文内容...

## 正文格式
- 使用状态指示器：[INFO]、[STATUS]、[WARN]
- 使用结构化格式：【标题】内容
- 结尾询问是否需要更多信息

## 示例
[SUMMARY] 博士查询阿米娅的职业信息
[INFO] 检索干员档案: 阿米娅

【阿米娅】5★术师
• 类型: 术战者（近卫形态可造成法术伤害）
• 定位: 罗德岛领袖，核心输出干员

[STATUS] 查询完成
需要了解更多详情吗，博士？"""

    def __init__(
        self,
        llm: Union[ChatOpenAI, anthropic.Anthropic],
        retriever,
        system_prompt: str = None,  # Default to dual output prompt
        compressor=None,
        enable_compression: bool = False,
        session_id: Optional[str] = None,
        memory_manager=None,
        memory_k: int = 5,
        use_dual_output: bool = True,  # New parameter to control dual output
        use_anthropic_sdk: bool = False,
        # Simplified retrieval configuration
        retrieval_config: Optional[RetrievalConfig] = None
    ):
        """Initialize the RAG agent with enhanced retrieval only.

        Args:
            llm: The language model to use (ChatOpenAI or Anthropic client)
            retriever: The base retriever to use (will be wrapped with EnhancedRAGRetriever)
            system_prompt: The system prompt to use (defaults to PRTS dual output prompt)
            compressor: The context compressor instance
            enable_compression: Whether to enable context compression
            session_id: Optional session ID for memory persistence
            memory_manager: Optional MemoryManager instance
            memory_k: Number of memories to retrieve (default: 5)
            use_dual_output: Whether to use dual output prompt for summary extraction (default: True)
            use_anthropic_sdk: Whether to use Anthropic SDK
            retrieval_config: Configuration for enhanced retrieval system
        """
        # Default to PRTS dual output prompt (combines PRTS personality with JSON format)
        if system_prompt is None:
            # Check environment variable first, fallback to PRTS dual output prompt
            env_prompt = os.getenv("OPENAI_SYSTEM_PROMPT")
            if env_prompt:
                # User specified custom prompt via environment
                system_prompt = env_prompt
            else:
                # Use PRTS dual output prompt by default
                system_prompt = self.PRTS_DUAL_OUTPUT_PROMPT

        super().__init__(
            llm,
            system_prompt,
            compressor,
            enable_compression,
            session_id,
            memory_manager,
            memory_k,
            use_anthropic_sdk
        )
        
        # Setup enhanced retrieval system (always enabled)
        self.use_enhanced_retrieval = True
        self.retrieval_config = retrieval_config or RetrievalConfig()
        self.enhanced_retriever = EnhancedRAGRetriever(retriever, self.retrieval_config)
        self.retriever = self.enhanced_retriever
        print("[INFO] 增强检索系统: 已启用")
        
        self.use_dual_output = use_dual_output

    def _retrieve_and_build_context(self, user_input: str) -> str:
        """Retrieve relevant documents and build enhanced context.

        Args:
            user_input: The user query

        Returns:
            The built context string with enhanced formatting
        """
        try:
            # Always use enhanced retriever (timing is handled inside retrieve())
            retrieved = self.enhanced_retriever.retrieve(user_input)
            
            # Build enhanced context with PRTS-style formatting
            step_start = time.time()
            context = build_enhanced_context(
                user_input, 
                retrieved, 
                max_length=self.retrieval_config.max_context_length
            )
            _log_timing("上下文构建", time.time() - step_start, f"{len(context)} 字符")
            
            # Add PRTS-style instructions
            prompt_with_context = (
                f"{context}\n\n"
                f"[PRTS指令] 基于上述罗德岛数据库检索结果回答博士的问题。"
                f"在回答中引用具体的档案来源。"
                f"如果信息不足，使用[WARN]明确说明缺失内容。"
            )
                
        except Exception as e:
            print(f"[ERROR] 检索失败: {e}")
            # Fallback to basic context
            prompt_with_context = (
                f"[QUERY] 博士查询: {user_input}\n\n"
                f"[WARN] 罗德岛数据库检索遇到问题，请基于已知信息回答。"
            )

        return prompt_with_context

    def chat_loop(self):
        """Run the interactive RAG chat loop."""
        messages: List = [SystemMessage(content=self.system_prompt)]
        max_tokens = 80000  # Default max tokens for display

        # PRTS style welcome message
        print("\n" + "="*60)
        print("[PRTS] 罗德岛战术终端系统 v2.0")
        print("[INFO] 系统初始化完成")
        print("[INFO] 数据库连接: 就绪")
        print("[INFO] 博士权限验证: 通过")
        print("="*60)
        print("[PRTS]$ 输入 /exit 或 /quit 退出 | /reset 清空上下文")

        if self.enable_compression and self.compressor:
            print("[INFO] 上下文压缩: 已启用")
            max_tokens = self.compressor.max_tokens
        print()

        compression_counter = 0
        turn_counter = 0  # Turn counter for memory

        # Load session history if session_id is provided
        if self.session_id and self.memory_manager:
            try:
                history = self.memory_manager.get_session_history(self.session_id, limit=10)
                for user_msg, assistant_msg in history:
                    messages.append(HumanMessage(content=user_msg))
                    messages.append(AIMessage(content=assistant_msg))
                    turn_counter += 1
                if history:
                    print(f"[INFO] 已加载 {len(history)} 条历史会话记录 (会话: {self.session_id})")
            except Exception as e:
                self.output_formatter.print_error(f"Failed to load session history: {e}")

        while True:
            try:
                user_input = input("博士: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n[STATUS] 会话终止")
                if compression_counter > 0:
                    print(f"[INFO] 压缩次数: {compression_counter}")
                self._print_token_stats(messages, max_tokens)
                break

            if not user_input:
                continue
            if user_input.lower() in {"/exit", "/quit"}:
                print("[STATUS] 再见，博士。期待您的下次访问。")
                if compression_counter > 0:
                    print(f"[INFO] 压缩次数: {compression_counter}")
                self._print_token_stats(messages, max_tokens)
                break
            if user_input.lower() == "/reset":
                messages = [SystemMessage(content=self.system_prompt)]
                compression_counter = 0
                os.system("clear")
                print("\n[PRTS] 罗德岛战术终端系统")
                print("[INFO] 上下文已清空")
                continue

            # RAG query
            try:
                # Retrieve relevant documents and build context
                prompt_with_context = self._retrieve_and_build_context(user_input)

                # Retrieve relevant memories if enabled
                if self.session_id and self.memory_manager:
                    relevant_memories = self._retrieve_memories(user_input)
                    if relevant_memories:
                        # Combine RAG context with memory context
                        prompt_with_context = (
                            f"[相关历史记忆]\n{relevant_memories}\n\n"
                            f"{prompt_with_context}"
                        )

                # Add user input to message list
                messages.append(HumanMessage(content=prompt_with_context))

                # Process the request with timing
                llm_start = time.time()
                raw_response = self._process_streaming(messages, max_tokens)
                _log_timing("LLM生成", time.time() - llm_start, f"{len(raw_response)} 字符")

                # Parse dual output if enabled
                if self.use_dual_output:
                    full_answer, summary_text = self._parse_dual_output(raw_response)
                    assistant_msg = full_answer
                else:
                    assistant_msg = raw_response
                    summary_text = None

                messages.append(AIMessage(content=assistant_msg))
                turn_counter += 1

                # Save the conversation turn to memory with extracted summary and content if available
                if self.session_id and self.memory_manager:
                    if self.use_dual_output and summary_text:
                        self._save_conversation_turn(
                            user_input,
                            raw_response,
                            turn_counter,
                            summary=summary_text,
                            content=full_answer
                        )
                    else:
                        self._save_conversation_turn(user_input, assistant_msg, turn_counter)

                # Check if context compression is needed
                compression_counter = self._handle_compression(messages, compression_counter)

                # Display token usage statistics after each turn
                self._print_token_stats(messages, max_tokens)

            except Exception as e:
                self._handle_error(e, messages)
                continue

    def get_retrieval_stats(self) -> Dict[str, Any]:
        """Get retrieval performance statistics."""
        if self.enhanced_retriever:
            return self.enhanced_retriever.get_stats()
        return {"enhanced_retrieval": False}
    
    def run(self):
        """Run the RAG agent (alias for chat_loop)."""
        try:
            self.chat_loop()
        finally:
            # Print retrieval statistics on exit (PRTS style)
            if self.use_enhanced_retrieval:
                stats = self.get_retrieval_stats()
                print(f"\n[STATUS] 会话统计")
                print(f"  查询次数: {stats.get('total_queries', 0)}")
                print(f"  平均检索文档: {stats.get('avg_final_results', 0):.1f}")
                print(f"  重排序: {'启用' if stats.get('reranking_enabled', False) else '禁用'}")
