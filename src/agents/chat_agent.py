"""Chat agent implementation."""

import re
import json
import anthropic

from typing import List, Optional, Union

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from agents.base_agent import BaseAgent
from streaming.output_formatter import OutputFormatter
from utils import ToolRegistry, build_markdown_create_tool, build_web_search_tool


class ChatAgent(BaseAgent):
    """Chat-only agent for interactive conversations."""

    def __init__(
        self,
        llm: Union[ChatOpenAI, anthropic.Anthropic],
        system_prompt: str = None,  # Default to dual output prompt
        compressor=None,
        enable_compression: bool = False,
        session_id: Optional[str] = None,
        memory_manager=None,
        memory_k: int = 5,
        use_dual_output: bool = True,  # New parameter to control dual output
        use_anthropic_sdk: bool = False
    ):
        """Initialize the chat agent.

        Args:
            llm: The language model to use (ChatOpenAI or Anthropic client)
            system_prompt: The system prompt to use (defaults to dual output if use_dual_output=True)
            compressor: The context compressor instance
            enable_compression: Whether to enable context compression
            session_id: Optional session ID for memory persistence
            memory_manager: Optional MemoryManager instance
            memory_k: Number of memories to retrieve (default: 5)
            use_dual_output: Whether to use dual output prompt for summary extraction (default: True)
            use_anthropic_sdk: Whether to use Anthropic SDK
        """
        # Use dual output prompt by default if not specified
        if system_prompt is None and use_dual_output:
            system_prompt = self.DUAL_OUTPUT_SYSTEM_PROMPT
        elif system_prompt is None:
            system_prompt = "You are a helpful assistant."

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
        # Initialize tool registry and register built-in tools
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(build_markdown_create_tool())
        self.tool_registry.register(build_web_search_tool())
        self.output_formatter: OutputFormatter = self.output_formatter
        self.use_dual_output = use_dual_output

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
        turn_counter = 0  # Turn counter for memory

        # Keyboard listener removed - no longer needed

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
                # Keyboard listener removed
                if compression_counter > 0:
                    print(f"[Info] Total compressions performed: {compression_counter}")
                self._print_token_stats(messages, max_tokens)
                break
            except UnicodeDecodeError:
                print("\n[Warning] Input encoding error. Please try again.")
                continue

            if not user_input:
                continue
            if user_input.lower() in {"/exit", "/quit"}:
                print("[Info] Bye!")
                # Keyboard listener removed
                if compression_counter > 0:
                    print(f"[Info] Total compressions performed: {compression_counter}")
                self._print_token_stats(messages, max_tokens)
                break
            if user_input.lower() == "/reset":
                messages = [SystemMessage(content=self.system_prompt)]
                compression_counter = 0
                print("[Info] Conversation reset.")
                continue

            # 1) Try explicit command handling
            if self._try_handle_command(user_input):
                # command handled: do not send to LLM
                continue

            # 2) Intent classification and tool routing
            route = self._classify_intent(user_input)
            summary = None
            if route and route.get('tool_name'):
                # append user first for context
                messages.append(HumanMessage(content=user_input))
                summary = self._route_and_execute_tool(route)
                if summary:
                    messages.append(AIMessage(content=summary))
            else:
                messages.append(HumanMessage(content=user_input))

            # Retrieve relevant memories before processing
            original_user_input = user_input
            if self.session_id and self.memory_manager and not summary:
                relevant_memories = self._retrieve_memories(user_input)
                if relevant_memories:
                    # Inject memories into the user message
                    enhanced_input = f"[相关历史记忆]\n{relevant_memories}\n\n[当前问题]\n{user_input}"
                    # Replace the last user message with enhanced version
                    if messages and isinstance(messages[-1], HumanMessage):
                        messages[-1] = HumanMessage(content=enhanced_input)

            # Check if context compression is needed
            compression_counter = self._handle_compression(messages, compression_counter)

            # Process the request
            try:
                # Get raw response from LLM (timer will be started automatically)
                raw_response = self._process_streaming(messages, max_tokens)

                # Get token statistics from stream processor
                token_stats = self.stream_processor.get_stats()

                # Parse dual output if enabled
                full_answer, summary_text = self._parse_dual_output(raw_response)

                # Use the full answer for display and history
                assistant_msg = full_answer
                messages.append(AIMessage(content=assistant_msg))
                turn_counter += 1

                # Save the conversation turn to memory with extracted summary and content
                if self.session_id and self.memory_manager and not summary:
                    self._save_conversation_turn(
                        original_user_input,
                        assistant_msg,
                        turn_counter,
                        summary=summary_text,
                        content=full_answer
                    )

                # Clear status bar
                self.output_formatter.clear_status_bar()

                # Display token usage statistics after each turn
                self._print_token_stats(messages, max_tokens)

            except Exception as e:
                self._handle_error(e, messages)
                continue

    def run(self):
        """Run the chat agent (alias for chat_loop)."""
        self.chat_loop()
