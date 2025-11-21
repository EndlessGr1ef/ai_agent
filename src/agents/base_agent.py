"""Base agent class with common functionality."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
import re

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from streaming.processor import StreamProcessor
from streaming.output_formatter import OutputFormatter
from utils.token_counter import count_tokens_in_messages


class BaseAgent(ABC):
    """Base agent class with common functionality for all agents."""

    # JSON-format system prompt for structured response with summary and content
    DUAL_OUTPUT_SYSTEM_PROMPT = """你是一个专业的AI助手。请直接、精准地回答用户的问题。

回答原则：
1. **聚焦问题**：只回答用户问的内容，不展开无关信息
2. **简洁明确**：优先用最简洁的方式表达核心答案
3. **按需详细**：只在用户明确需要或问题复杂时提供详细说明
4. **去除冗余**：不要客套话、不要重复用户的问题、不要过度总结

回答要求：
- 如果问题简单：直接给出1-2句话的答案
- 如果问题复杂：先给核心答案，再简要说明原因/步骤
- 只在涉及多个要点时使用列表，避免强制分点

请按照以下JSON格式返回答案，确保输出有效的JSON格式：

```json
{
  "summary": "用1-3句话总结本次回答的核心内容，便于记忆检索",
  "content": "完整的回答内容，包括核心信息和详细说明"
}
```"""

    def __init__(
        self,
        llm: ChatOpenAI,
        system_prompt: str = "You are a helpful assistant for software development.",
        compressor=None,
        enable_compression: bool = False,
        session_id: Optional[str] = None,
        memory_manager=None,
        memory_k: int = 5
    ):
        """Initialize the base agent.

        Args:
            llm: The language model to use
            system_prompt: The system prompt to use
            compressor: The context compressor instance
            enable_compression: Whether to enable context compression
            session_id: Optional session ID for memory persistence
            memory_manager: Optional MemoryManager instance
            memory_k: Number of memories to retrieve (default: 5)
        """
        self.llm = llm
        self.system_prompt = system_prompt
        self.compressor = compressor
        self.enable_compression = enable_compression
        self.session_id = session_id
        self.memory_manager = memory_manager
        self.memory_k = memory_k
        self.stream_processor = StreamProcessor()
        self.output_formatter = OutputFormatter()

    def _count_tokens(self, messages: List) -> int:
        """Count tokens in messages.

        Args:
            messages: List of messages

        Returns:
            Total token count
        """
        return count_tokens_in_messages(messages)

    def _parse_dual_output(self, response_text: str) -> Tuple[str, str]:
        """Parse LLM response JSON into full answer and summary.

        Args:
            response_text: Raw response from LLM

        Returns:
            Tuple of (full_answer, summary)
        """
        import json

        try:
            # Try to extract JSON from markdown code blocks first
            json_match = re.search(r'```(?:json)?\n?({.*?})\n?```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON directly in the response
                json_match = re.search(r'({.*})', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    # No JSON found, use fallback
                    return response_text, self._extract_fallback_summary(response_text)

            # Parse the JSON
            try:
                parsed = json.loads(json_str)
                summary = parsed.get('summary', '')
                content = parsed.get('content', '')

                # Validate that we got meaningful content
                if summary and content:
                    return content, summary
                elif content:
                    return content, self._extract_fallback_summary(content)
                else:
                    return response_text, self._extract_fallback_summary(response_text)

            except json.JSONDecodeError as e:
                print(f"\n[Warning] JSON parsing failed: {e}")
                return response_text, self._extract_fallback_summary(response_text)

        except Exception as e:
            # If parsing fails, return full response as both
            print(f"\n[Warning] Failed to parse dual output: {e}")
            return response_text, self._extract_fallback_summary(response_text)

    def _extract_fallback_summary(self, text: str) -> str:
        """Extract summary using fallback method if parsing fails.

        Args:
            text: Response text to extract summary from

        Returns:
            Extracted summary
        """
        # Extract first meaningful sentence
        sentences = re.split(r'[。！？\n]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return text[:100] + "..." if len(text) > 100 else text

        # Try each sentence until we find a meaningful one
        for sentence in sentences:
            first_sentence = sentence.strip()

            # Remove common filler phrases
            filler_phrases = [
                '很高兴为您服务', '请问有什么可以帮助您的', '我会尽力帮您',
                '当然可以', '让我来帮您', '根据我的理解', '一般来说',
                '通常情况下', '简单来说', '换句话说'
            ]

            cleaned_sentence = first_sentence
            for phrase in filler_phrases:
                cleaned_sentence = cleaned_sentence.replace(phrase, '')

            cleaned_sentence = cleaned_sentence.strip()

            # If the cleaned sentence has meaningful content, use it
            if len(cleaned_sentence) >= 10:  # At least 10 characters
                # Truncate if too long
                if len(cleaned_sentence) > 150:
                    cleaned_sentence = cleaned_sentence[:150] + "..."

                return cleaned_sentence

        # If all sentences are filtered out, use the original text
        return sentences[0][:100] + "..." if len(sentences[0]) > 100 else sentences[0]

    def _handle_compression(
        self,
        messages: List,
        compression_counter: int
    ) -> int:
        """Handle context compression if enabled.

        Args:
            messages: List of messages
            compression_counter: Current compression count

        Returns:
            Updated compression count
        """
        if not self.enable_compression or not self.compressor or len(messages) <= 5:
            return compression_counter

        if len(messages) > 10:
            try:
                compressed_messages = self.compressor.compress(messages)
                if len(compressed_messages) < len(messages):
                    messages.clear()
                    messages.extend(compressed_messages)
                    compression_counter += 1
                    stats = self.compressor.get_stats()
                    print(
                        f"\n[🗜️  Context compressed] "
                        f"Messages: {stats['original_count']}→{stats['compressed_count']} "
                        f"({stats['compression_ratio']:.1%} reduction)"
                    )
            except Exception as e:
                print(f"\n[⚠️  Compression failed] {e}")

        return compression_counter

    def _process_streaming(
        self,
        messages: List,
        max_tokens: int = 80000
    ) -> str:
        """Process streaming response and extract complete content.

        Args:
            messages: List of messages to send
            max_tokens: Maximum token limit for display

        Returns:
            The complete assistant response
        """
        self.stream_processor.reset()
        self.output_formatter.reset()
        self.output_formatter.print_assistant_header()

        full_response = []
        show_timer = True  # Always show timer during streaming

        for chunk in self.llm.stream(messages):
            if chunk.content:
                thinking_content, answer_content = self.stream_processor.process_chunk(chunk.content)

                if thinking_content:
                    self.output_formatter.print_thinking(thinking_content)

                if answer_content:
                    self.output_formatter.print_answer(answer_content)
                    full_response.append(answer_content)

        self.output_formatter.clear_status_bar()
        self.output_formatter.print_empty_line()
        self.output_formatter.print_call_duration()
        return "".join(full_response)

    def _handle_error(
        self,
        e: Exception,
        messages: List
    ) -> bool:
        """Handle errors during request processing.

        Args:
            e: The exception that occurred
            messages: List of messages

        Returns:
            True if error was handled, False otherwise
        """
        # Stop timer if error occurs
        self.output_formatter.status_bar.stop_timer()

        self.output_formatter.print_error(f"Request failed: {e}")

        if "token" in str(e).lower() and "limit" in str(e).lower():
            self.output_formatter.print_hint(
                "Consider enabling context compression with --enable-compression"
            )

        if messages and isinstance(messages[-1], HumanMessage):
            messages.pop()

        return True

    def _print_token_stats(self, messages: List, max_tokens: int = 80000):
        """Print token usage statistics.

        Args:
            messages: List of messages
            max_tokens: Maximum token limit
        """
        current_tokens = self._count_tokens(messages)
        used_percent = current_tokens / max_tokens * 100
        print(f"[Info] Total tokens: {current_tokens:,} / {max_tokens:,} ({used_percent:.1f}% of limit)")

    def _retrieve_memories(self, query: str) -> str:
        """Retrieve relevant memories and format as context.

        Args:
            query: Query text for semantic search

        Returns:
            Formatted memory context string
        """
        if not self.session_id or not self.memory_manager:
            return ""

        memories = self.memory_manager.retrieve_relevant_memories(
            session_id=self.session_id,
            query=query,
            k=self.memory_k
        )

        if not memories:
            return ""

        return "\n".join(memories)

    def _save_conversation_turn(
        self,
        user_msg: str,
        assistant_msg: str,
        turn_id: int,
        summary: str = None,
        content: str = None
    ):
        """Save a conversation turn to memory with separate summary and content.

        Args:
            user_msg: User message content
            assistant_msg: Assistant response content (full response)
            turn_id: Turn number in the conversation
            summary: Optional pre-extracted summary for memory storage
            content: Optional separate content for memory storage
        """
        if self.session_id and self.memory_manager:
            try:
                self.memory_manager.save_turn(
                    session_id=self.session_id,
                    user_msg=user_msg,
                    assistant_msg=assistant_msg,
                    turn_id=turn_id,
                    assistant_summary=summary,
                    assistant_content=content
                )
            except Exception as e:
                self.output_formatter.print_error(f"Failed to save memory: {e}")

    @abstractmethod
    def run(self):
        """Run the agent (must be implemented by subclasses)."""
        pass

    @abstractmethod
    def chat_loop(self):
        """Run the chat loop (must be implemented by subclasses)."""
        pass
