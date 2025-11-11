"""Chat agent implementation."""

from typing import List

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from agents.base_agent import BaseAgent


class ChatAgent(BaseAgent):
    """Chat-only agent for interactive conversations."""

    def __init__(
        self,
        llm: ChatOpenAI,
        system_prompt: str = "You are a helpful assistant for software development.",
        compressor=None,
        enable_compression: bool = False
    ):
        """Initialize the chat agent.

        Args:
            llm: The language model to use
            system_prompt: The system prompt to use
            compressor: The context compressor instance
            enable_compression: Whether to enable context compression
        """
        super().__init__(llm, system_prompt, compressor, enable_compression)

    def chat_loop(self):
        """Run the interactive chat loop."""
        messages: List = [SystemMessage(content=self.system_prompt)]
        max_tokens = 80000  # Default max tokens for display

        print("\n===== LangChain OpenAI-compatible Test Agent (interactive) =====")
        print("Tip: type /exit or /quit to exit; type /reset to reset the conversation.")

        if self.enable_compression and self.compressor:
            print("✓ Context compression enabled")
            max_tokens = self.compressor.max_tokens
        print()

        compression_counter = 0  # Compression counter

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
                print("[Info] Conversation reset.")
                continue

            messages.append(HumanMessage(content=user_input))

            # Check if context compression is needed
            compression_counter = self._handle_compression(messages, compression_counter)

            # Process the request
            try:
                assistant_msg = self._process_streaming(messages, max_tokens)
                messages.append(AIMessage(content=assistant_msg))

                # Display token usage statistics after each turn
                self._print_token_stats(messages, max_tokens)

            except Exception as e:
                self._handle_error(e, messages)
                continue

    def run(self):
        """Run the chat agent (alias for chat_loop)."""
        self.chat_loop()
