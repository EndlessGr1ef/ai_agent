"""Base agent class with common functionality."""

from abc import ABC, abstractmethod
from typing import List, Optional

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from streaming.processor import StreamProcessor
from streaming.output_formatter import OutputFormatter
from utils.token_counter import count_tokens_in_messages


class BaseAgent(ABC):
    """Base agent class with common functionality for all agents."""

    def __init__(
        self,
        llm: ChatOpenAI,
        system_prompt: str = "You are a helpful assistant for software development.",
        compressor=None,
        enable_compression: bool = False
    ):
        """Initialize the base agent.

        Args:
            llm: The language model to use
            system_prompt: The system prompt to use
            compressor: The context compressor instance
            enable_compression: Whether to enable context compression
        """
        self.llm = llm
        self.system_prompt = system_prompt
        self.compressor = compressor
        self.enable_compression = enable_compression
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

        for chunk in self.llm.stream(messages):
            if chunk.content:
                thinking_content, answer_content = self.stream_processor.process_chunk(chunk.content)

                if thinking_content:
                    self.output_formatter.print_thinking(thinking_content)

                if answer_content:
                    self.output_formatter.print_answer(answer_content)
                    full_response.append(answer_content)

        self.output_formatter.print_empty_line()
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

    @abstractmethod
    def run(self):
        """Run the agent (must be implemented by subclasses)."""
        pass

    @abstractmethod
    def chat_loop(self):
        """Run the chat loop (must be implemented by subclasses)."""
        pass
