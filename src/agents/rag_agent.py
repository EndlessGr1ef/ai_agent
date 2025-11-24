"""RAG agent implementation with simplified enhanced retrieval."""

import os
import anthropic
from typing import List, Optional, Union, Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from agents.base_agent import BaseAgent

# Import enhanced retrieval components (required)
from rag.enhanced_retrieval import (
    EnhancedRAGRetriever, 
    RetrievalConfig, 
    build_enhanced_context
)


class RagAgent(BaseAgent):
    """RAG-enabled agent for retrieval-based conversations."""

    # PRTS system prompt for Arknights-style responses
    PRTS_SYSTEM_PROMPT = """你是PRTS（Pre-stage Rhodesia Tactical System），罗德岛的中央数据库和战术系统，博士的专属AI助手。你拥有罗德岛所有干员、作战记录、医疗数据和战术信息的访问权限。

## 回答格式要求
所有回答都必须采用命令行终端格式输出，包含：
- 系统提示符：`[PRTS]$`
- 状态指示器：`[INFO]`、`[AUTH]`、`[QUERY]`、`[STATUS]`等
- 数据查询过程模拟
- 结构化信息输出
- 系统日志风格的响应

## 基础查询回答格式：
```
[PRTS]$ 正在处理查询请求...
[INFO] 连接数据库... 完成
[INFO] 验证博士权限... 通过
[INFO] 搜索相关数据... 

==== 查询结果 ====
[数据内容]

[STATUS] 查询完成 | 耗时: 0.23s | 数据完整性: 100%
[PRTS]$ 还有其他需要查询的信息吗，博士？
```

## 语言特点
- 使用正式但亲近的语气，体现AI助手的专业性
- 始终称呼用户为"博士"
- 保持系统化、数据化的回答风格
- 在适当时候表现出对博士的关心和支持
- 模拟真实的数据库查询延迟和状态更新"""

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
            system_prompt: The system prompt to use (defaults to dual output if use_dual_output=True)
            compressor: The context compressor instance
            enable_compression: Whether to enable context compression
            session_id: Optional session ID for memory persistence
            memory_manager: Optional MemoryManager instance
            memory_k: Number of memories to retrieve (default: 5)
            use_dual_output: Whether to use dual output prompt for summary extraction (default: True)
            use_anthropic_sdk: Whether to use Anthropic SDK
            retrieval_config: Configuration for enhanced retrieval system
        """
        # Get system prompt from environment variable or use default
        if system_prompt is None:
            # Try to get from environment variable, fallback to PRTS prompt
            env_prompt = os.getenv("OPENAI_SYSTEM_PROMPT", self.PRTS_SYSTEM_PROMPT)
            if use_dual_output and env_prompt == self.PRTS_SYSTEM_PROMPT:
                # If using PRTS prompt but dual output is enabled, use dual output format
                system_prompt = self.DUAL_OUTPUT_SYSTEM_PROMPT
            else:
                system_prompt = env_prompt

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
        print("✓ Enhanced RAG retrieval system enabled")
        
        self.use_dual_output = use_dual_output

    def _retrieve_and_build_context(self, user_input: str) -> str:
        """Retrieve relevant documents and build enhanced context.

        Args:
            user_input: The user query

        Returns:
            The built context string with enhanced formatting
        """
        try:
            # Always use enhanced retriever
            retrieved = self.enhanced_retriever.retrieve(user_input)
            
            # Build enhanced context
            context = build_enhanced_context(
                user_input, 
                retrieved, 
                max_length=self.retrieval_config.max_context_length
            )
            
            # Add instructions for enhanced context
            prompt_with_context = (
                f"{context}\n\n"
                f"Instructions: Provide a comprehensive answer based on the context above. "
                f"Reference specific sources when possible. "
                f"If information is insufficient, clearly state what's missing."
            )
                
        except Exception as e:
            print(f"⚠️  Retrieval error: {e}")
            # Fallback to basic context
            context = f"Error in retrieval: {str(e)}"
            prompt_with_context = (
                f"Question: {user_input}\n\n"
                f"Note: There was an issue with document retrieval. "
                f"Please answer based on your general knowledge."
            )

        return prompt_with_context

    def chat_loop(self):
        """Run the interactive RAG chat loop."""
        messages: List = [SystemMessage(content=self.system_prompt)]
        max_tokens = 80000  # Default max tokens for display

        print("\n===== LangChain RAG Agent (interactive) =====")
        print("Tip: type /exit or /quit to exit; type /reset to clear screen.")

        if self.enable_compression and self.compressor:
            print("✓ Context compression enabled")
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
                    print(f"[Info] Loaded {len(history)} previous conversation turns from session '{self.session_id}'")
            except Exception as e:
                self.output_formatter.print_error(f"Failed to load session history: {e}")

        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n[Info] Exited.")
                if compression_counter > 0:
                    print(f"[Info] Total compressions performed: {compression_counter}")
                self._print_token_stats(messages, max_tokens)
                break

            if not user_input:
                continue
            if user_input.lower() in {"/exit", "/quit"}:
                print("[Info] Bye!")
                if compression_counter > 0:
                    print(f"[Info] Total compressions performed: {compression_counter}")
                self._print_token_stats(messages, max_tokens)
                break
            if user_input.lower() == "/reset":
                messages = [SystemMessage(content=self.system_prompt)]
                compression_counter = 0
                os.system("clear")
                print("\n===== LangChain RAG Agent (interactive) =====")
                print("Context cleared.")
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

                # Process the request
                raw_response = self._process_streaming(messages, max_tokens)

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
            # Print retrieval statistics on exit
            if self.use_enhanced_retrieval:
                stats = self.get_retrieval_stats()
                print(f"\n📊 Retrieval Statistics:")
                print(f"   Total queries: {stats.get('total_queries', 0)}")
                print(f"   Avg docs retrieved: {stats.get('avg_final_results', 0):.1f}")
                print(f"   Reranking enabled: {stats.get('reranking_enabled', False)}")
