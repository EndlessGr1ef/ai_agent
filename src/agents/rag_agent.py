"""RAG agent implementation."""

import os
from typing import List

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from agents.base_agent import BaseAgent


class RagAgent(BaseAgent):
    """RAG-enabled agent for retrieval-based conversations."""

    def __init__(
        self,
        llm: ChatOpenAI,
        retriever,
        system_prompt: str = "You are a helpful assistant for software development.",
        compressor=None,
        enable_compression: bool = False
    ):
        """Initialize the RAG agent.

        Args:
            llm: The language model to use
            retriever: The retriever to use for document retrieval
            system_prompt: The system prompt to use
            compressor: The context compressor instance
            enable_compression: Whether to enable context compression
        """
        super().__init__(llm, system_prompt, compressor, enable_compression)
        self.retriever = retriever

    def _retrieve_and_build_context(self, user_input: str) -> str:
        """Retrieve relevant documents and build context.

        Args:
            user_input: The user query

        Returns:
            The built context string
        """
        # Retrieve relevant documents
        retrieved = self.retriever.invoke(user_input)
        context_parts = []
        for i, doc in enumerate(retrieved, 1):
            src = (doc.metadata or {}).get("source", "unknown")
            context_parts.append(f"[Chunk {i}] source: {src}\n{doc.page_content}")
        context = "\n\n".join(context_parts)

        # Build prompt with context
        prompt_with_context = (
            f"Question:\n{user_input}\n\nContext:\n{context}\n\n"
            f"Instructions: Answer based on the context above. "
            f"If not enough information, say you don't know."
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

                # Add user input to message list
                messages.append(HumanMessage(content=prompt_with_context))

                # Process the request
                assistant_msg = self._process_streaming(messages, max_tokens)
                messages.append(AIMessage(content=assistant_msg))

                # Check if context compression is needed
                compression_counter = self._handle_compression(messages, compression_counter)

                # Display token usage statistics after each turn
                self._print_token_stats(messages, max_tokens)

            except Exception as e:
                self._handle_error(e, messages)
                continue

    def run(self):
        """Run the RAG agent (alias for chat_loop)."""
        self.chat_loop()
