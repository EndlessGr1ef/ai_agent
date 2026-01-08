"""Base agent class with common functionality."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Union
import re
import json
import anthropic

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from streaming.processor import StreamProcessor
from streaming.output_formatter import OutputFormatter
from utils.token_counter import count_tokens_in_messages
from utils import ToolRegistry, build_markdown_create_tool, build_web_search_tool


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
        llm: Union[ChatOpenAI, anthropic.Anthropic],
        system_prompt: str = "You are a helpful assistant for software development.",
        compressor=None,
        enable_compression: bool = False,
        session_id: Optional[str] = None,
        memory_manager=None,
        memory_k: int = 5,
        use_anthropic_sdk: bool = False
    ):
        """Initialize the base agent.

        Args:
            llm: The language model to use (ChatOpenAI or Anthropic client)
            system_prompt: The system prompt to use
            compressor: The context compressor instance
            enable_compression: Whether to enable context compression
            session_id: Optional session ID for memory persistence
            memory_manager: Optional MemoryManager instance
            memory_k: Number of memories to retrieve (default: 5)
            use_anthropic_sdk: Whether the llm is an Anthropic client
        """
        self.llm = llm
        self.system_prompt = system_prompt
        self.compressor = compressor
        self.enable_compression = enable_compression
        self.session_id = session_id
        self.memory_manager = memory_manager
        self.memory_k = memory_k
        self.use_anthropic_sdk = use_anthropic_sdk or isinstance(llm, anthropic.Anthropic)
        self.stream_processor = StreamProcessor()
        self.output_formatter = OutputFormatter()
        
        # Initialize tool registry and register built-in tools
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(build_markdown_create_tool())
        self.tool_registry.register(build_web_search_tool())

    def _try_handle_command(self, user_input: str) -> bool:
        """
        Handle explicit command forms like '/write'.
        Returns True if handled.
        """
        if user_input.startswith('/write '):
            # Parse format: /write <path.md> <<<\n<content>\n>>>
            try:
                parts = user_input[len('/write '):]
                if '<<<' in parts and '>>>' in parts:
                    filename, content_block = parts.split('<<<', 1)
                    content = content_block.rsplit('>>>', 1)[0]
                    filename = filename.strip()
                else:
                    # Simple one-line placeholder: /write <path.md> <content>
                    tokens = parts.split(' ', 1)
                    filename = tokens[0].strip()
                    content = tokens[1].strip() if len(tokens) > 1 else ''

                tool = self.tool_registry.get('markdown_create')
                result = tool.execute({'path': filename, 'content': content})
                if result.ok:
                    self.output_formatter.print_hint(result.message)
                else:
                    self.output_formatter.print_error(result.message)
                return True
            except Exception as e:
                self.output_formatter.print_error(f"/write command failed: {e}")
                return True
        return False

    def _classify_intent(self, user_input: str) -> dict:
        """Use LLM to classify intent and proposed tool with arguments. Returns dict or {}."""
        sys = SystemMessage(content=(
            "You are an intent classifier. Read the user's input and decide if it matches one of tools: "
            "markdown_create (create a markdown file), web_search (search the web). "
            "Return ONLY JSON with fields: intent, tool_name, arguments (object), confidence (0-1). "
            "If no suitable tool, return intent='chat', tool_name='', arguments={}, confidence=0."
        ))
        hm = HumanMessage(content=user_input)
        try:
            # Note: For intent classification, we always use the LLM invoke method
            # This is separate from the main streaming chat loop
            if self.use_anthropic_sdk:
                # Basic implementation for Anthropic intent classification if needed
                # For now, we assume LLM is compatible with invoke() or similar
                # If using raw Anthropic client, this might need adjustment
                pass
            
            resp = self.llm.invoke([sys, hm])
            content = getattr(resp, 'content', '')
            content = content.strip()
            # Extract JSON from possible code fences
            if content.startswith('```'):
                content = content.strip('`')
            # Try to find first JSON object
            match = None
            for m in re.finditer(r'\{[\s\S]*\}', content):
                match = m
                break
            if match:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def _route_and_execute_tool(self, route: dict) -> Optional[str]:
        """
        Execute tool based on route. Returns a short summary string or None if not executed.
        """
        name = route.get('tool_name')
        args = route.get('arguments') or {}
        if not name:
            return None
        tool = self.tool_registry.get(name)
        if not tool:
            return None
        result = tool.execute(args if isinstance(args, dict) else {})
        if result.ok:
            self.output_formatter.print_hint(result.message)
            # Build a short summary to insert into conversation
            if name == 'markdown_create':
                p = (result.data or {}).get('path', '')
                return f"[TOOL_RESULT: markdown_create] File created at: {p}"
            if name == 'web_search':
                items = (result.data or {}).get('results', [])
                lines = [f"- {it.get('title','')} ({it.get('url','')})" for it in items]
                return "[TOOL_RESULT: web_search]\n" + "\n".join(lines)
            return f"[TOOL_RESULT: {name}] {result.message}"
        else:
            self.output_formatter.print_error(result.message)
            return f"[TOOL_RESULT: {name}] {result.message}"

    def _count_tokens(self, messages: List) -> int:
        """Count tokens in messages.

        Args:
            messages: List of messages

        Returns:
            Total token count
        """
        return count_tokens_in_messages(messages)

    def _parse_dual_output(self, response_text: str) -> Tuple[str, str]:
        """Parse LLM response into full answer and summary.
        
        Supports two formats:
        1. Tag format: [SUMMARY] summary text\\ncontent...
        2. JSON format: {"summary": "...", "content": "..."}

        Args:
            response_text: Raw response from LLM

        Returns:
            Tuple of (full_answer, summary)
        """
        import json

        # First try tag format: [SUMMARY] xxx\n content...
        summary_match = re.search(r'\[SUMMARY\]\s*(.+?)(?:\n|$)', response_text)
        if summary_match:
            summary = summary_match.group(1).strip()
            # Content is everything after the summary line
            content_start = summary_match.end()
            content = response_text[content_start:].strip()
            if content:
                return content, summary
        
        # Fallback to JSON format
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

            except json.JSONDecodeError:
                return response_text, self._extract_fallback_summary(response_text)

        except Exception:
            # If parsing fails, return full response as both
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
        max_tokens: int = 80000,
        temperature: float = 1.0
    ) -> str:
        """Process streaming response and extract complete content.

        Args:
            messages: List of messages to send (LangChain format for OpenAI, Anthropic format for Anthropic)
            max_tokens: Maximum token limit for display
            temperature: Sampling temperature

        Returns:
            The complete assistant response
        """
        self.stream_processor.reset()
        self.output_formatter.reset()
        self.output_formatter.print_assistant_header()

        full_response = []
        show_timer = True  # Always show timer during streaming

        if self.use_anthropic_sdk:
            # Use Anthropic SDK streaming
            full_response = self._process_anthropic_streaming(messages, temperature)
        else:
            # Use OpenAI-compatible streaming (original implementation)
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

    def _process_anthropic_streaming(
        self,
        messages: List,
        temperature: float = 1.0
    ) -> List[str]:
        """Process streaming response using Anthropic SDK.

        Args:
            messages: List of messages in LangChain format
            temperature: Sampling temperature

        Returns:
            List of response text chunks
        """
        import anthropic
        import os

        # Convert LangChain messages to Anthropic format
        anthropic_messages = []
        system_prompt = self.system_prompt

        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_prompt = msg.content
            elif isinstance(msg, HumanMessage):
                anthropic_messages.append({
                    "role": "user",
                    "content": [{"type": "text", "text": msg.content}]
                })
            elif isinstance(msg, AIMessage):
                anthropic_messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": msg.content}]
                })

        full_response = []

        # Get model from environment
        # Available models (via Anthropic-compatible API):
        # - MiniMax-M2.1: faster (~60 tps), recommended (default)
        # - MiniMax-M2: stable, has deep thinking
        # - MiniMax-M2.1-lightning: fastest (~100 tps) but requires Coding Plan subscription
        model_name = os.getenv("OPENAI_MODEL", "MiniMax-M2.1")
        
        # Create stream using Anthropic SDK
        stream = self.llm.messages.create(
            model=model_name,
            max_tokens=1500,  # Reduced from 4000 for faster, more concise responses
            system=system_prompt,
            messages=anthropic_messages,
            temperature=temperature,
            stream=True,
        )

        for chunk in stream:
            # Handle content block start (for tracking thinking vs text blocks)
            if chunk.type == "content_block_start":
                if hasattr(chunk, "content_block") and chunk.content_block:
                    block_type = getattr(chunk.content_block, "type", "")
                    # Could add logic here to track block state if needed
                    pass
            
            # Handle content deltas (main content)
            elif chunk.type == "content_block_delta":
                if hasattr(chunk, "delta") and chunk.delta:
                    delta_type = getattr(chunk.delta, "type", "")
                    
                    if delta_type == "thinking_delta":
                        # Handle thinking content - just track, don't display
                        thinking_text = getattr(chunk.delta, 'thinking', '')
                        if thinking_text:
                            # Silently accumulate thinking (not displayed to user)
                            pass
                            
                    elif delta_type == "text_delta":
                        # Handle text content - display to user
                        text_content = getattr(chunk.delta, 'text', '')
                        if text_content:
                            # Process and display answer content
                            _, answer_content = self.stream_processor.process_chunk(text_content)
                            if answer_content:
                                self.output_formatter.print_answer(answer_content)
                                full_response.append(answer_content)

        return full_response

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
        print(f"[STATUS] Token使用: {current_tokens:,} / {max_tokens:,} ({used_percent:.1f}%)")

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
