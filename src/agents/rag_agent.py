"""RAG agent implementation."""

import os
from typing import List, Optional

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
        enable_compression: bool = False,
        session_id: Optional[str] = None,
        memory_manager=None,
        memory_k: int = 5
    ):
        """Initialize the RAG agent.

        Args:
            llm: The language model to use
            retriever: The retriever to use for document retrieval
            system_prompt: The system prompt to use
            compressor: The context compressor instance
            enable_compression: Whether to enable context compression
            session_id: Optional session ID for memory persistence
            memory_manager: Optional MemoryManager instance
            memory_k: Number of memories to retrieve (default: 5)
        """
        super().__init__(llm, system_prompt, compressor, enable_compression, session_id, memory_manager, memory_k)
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
                assistant_msg = self._process_streaming(messages, max_tokens)
                messages.append(AIMessage(content=assistant_msg))
                turn_counter += 1

                # Save the conversation turn to memory
                if self.session_id and self.memory_manager:
                    self._save_conversation_turn(user_input, assistant_msg, turn_counter)

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
