"""Output formatting utilities."""

import sys
import time
from datetime import datetime

class StatusBar:
    """Simple status bar for displaying thinking tokens and elapsed time."""

    def __init__(self):
        self.current_message = ""
        self.token_count = 0
        self.start_time = None
        self.timer_active = False

    def start_timer(self):
        """Start the elapsed time timer."""
        self.start_time = time.time()
        self.timer_active = True

    def stop_timer(self):
        """Stop the elapsed time timer."""
        self.timer_active = False
        self.start_time = None

    def _format_duration(self, seconds: float) -> str:
        """Format elapsed time in seconds to human readable format.

        Args:
            seconds: Elapsed time in seconds

        Returns:
            Formatted duration string
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    def update(self, message: str, thinking_tokens: int = None, show_timer: bool = False):
        """Update status bar with new message and token count.

        Args:
            message: Status message to display
            thinking_tokens: Number of thinking tokens
            show_timer: Whether to show elapsed time
        """
        if thinking_tokens is not None:
            self.token_count = thinking_tokens

        # Build status components
        components = []

        # Add thinking tokens if available
        if self.token_count > 0:
            components.append(f"思考: {self.token_count} tokens")

        # Add elapsed time if requested and timer is active
        if show_timer and self.timer_active and self.start_time is not None:
            elapsed = time.time() - self.start_time
            components.append(f"⏱ {self._format_duration(elapsed)}")

        # Add custom message
        if message:
            components.append(message)

        # Combine components
        status = " | ".join(components)

        # Use ANSI escape sequences to move cursor to line start and clear
        sys.stdout.write(f"\r\033[K{status}")
        sys.stdout.flush()

    def clear(self):
        """Clear the status bar."""
        sys.stdout.write(f"\r\033[K")
        sys.stdout.flush()

class OutputFormatter:
    """Enhanced output formatter with thinking process display control."""

    def __init__(self, prts_mode: bool = True):
        """Initialize the output formatter.
        
        Args:
            prts_mode: Whether to use PRTS terminal style output (default: True)
        """
        self.reasoning_displayed = False
        self.answer_displayed = False

        # PRTS mode control - default enabled
        self.prts_mode = prts_mode

        # Thinking process display control - always hidden (removed toggle functionality)
        self.show_thinking = False  # Default: always hide thinking process
        self.thinking_cache = ""    # Not used anymore

        # Status bar for thinking tokens
        self.status_bar = StatusBar()

        # Thinking content styling - kept for potential future use
        self.thinking_style = {
            "prefix": "🤔 [thinking] ",
            "color": "\033[90m",      # Dark gray (ANSI 90)
            "italic": "\033[3m",      # Italic (ANSI 3)
            "reset": "\033[0m"        # Reset
        }

    def reset(self):
        """Reset for new output."""
        self.reasoning_displayed = False
        self.answer_displayed = False
        self.thinking_cache = ""  # Clear thinking cache

    def print_assistant_header(self):
        """Print the assistant header (PRTS style or standard)."""
        if self.prts_mode:
            print("[PRTS]$")
        else:
            print("Assistant:")
        # Start timer when assistant begins responding
        self.status_bar.start_timer()

    def print_call_duration(self):
        """Print the final call duration."""
        if self.status_bar.timer_active and self.status_bar.start_time is not None:
            elapsed = time.time() - self.status_bar.start_time
            self.status_bar.stop_timer()
            duration_str = self.status_bar._format_duration(elapsed)
            if self.prts_mode:
                print(f"\n[STATUS] 响应完成 | 耗时: {duration_str}")
            else:
                print(f"\n[Info] Call duration: {duration_str}")

    def print_thinking(self, thinking_content: str):
        """Print thinking content with formatting.

        Args:
            thinking_content: The thinking content to print
        """
        if not self.reasoning_displayed:
            # First thinking output
            print()
            self.reasoning_displayed = True

        # Cache thinking content when hidden
        if not self.show_thinking:
            self.thinking_cache += thinking_content
            return

        # Display thinking content with styling
        styled_thinking = (
            f"{self.thinking_style['prefix']}"
            f"{self.thinking_style['color']}"
            f"{self.thinking_style['italic']}"
            f"{thinking_content}"
            f"{self.thinking_style['reset']}"
        )
        print(styled_thinking, end="", flush=True)

    def print_answer(self, answer_content: str):
        """Print answer content with formatting.

        Args:
            answer_content: The answer content to print
        """
        # Filter out content that shouldn't appear in streaming output
        lines = answer_content.split('\n')
        filtered_lines = []

        for line in lines:
            # Skip [SUMMARY] lines - these are for memory extraction, not display
            if line.strip().startswith('[SUMMARY]'):
                continue
            # Skip status bar artifacts
            if ('思考:' in line and 'tokens' in line and '⏱' in line) or \
               (line.strip().startswith('⏱') and 's |' in line):
                continue
            # Skip JSON format artifacts
            if line.strip() in ['```json', '```', '{', '}']:
                continue
            if line.strip().startswith('"summary"') or line.strip().startswith('"content"'):
                continue
            filtered_lines.append(line)

        filtered_content = '\n'.join(filtered_lines)
        
        # Skip if no content after filtering
        if not filtered_content.strip():
            return

        # Only show [answers] label if thinking process is being displayed
        if self.show_thinking and not self.answer_displayed:
            print()
            print("[answers] ", end="", flush=True)
            self.answer_displayed = True
        elif not self.show_thinking and not self.answer_displayed:
            self.answer_displayed = True

        print(filtered_content, end="", flush=True)

    def print_empty_line(self):
        """Print an empty line."""
        print()

    def print_error(self, error_msg: str):
        """Print an error message.

        Args:
            error_msg: The error message to print
        """
        print()
        if self.prts_mode:
            print(f"[ERROR] {error_msg}")
        else:
            print(f"[Error] {error_msg}")

    def print_hint(self, hint_msg: str):
        """Print a hint message.

        Args:
            hint_msg: The hint message to print
        """
        if self.prts_mode:
            print(f"[INFO] {hint_msg}")
        else:
            print(f"[Hint] {hint_msg}")

    def update_thinking_tokens(self, thinking_tokens: int, show_timer: bool = True):
        """Update thinking tokens in status bar with optional timer.

        Args:
            thinking_tokens: Number of thinking tokens
            show_timer: Whether to show elapsed time
        """
        self.status_bar.update("正在思考...", thinking_tokens=thinking_tokens, show_timer=show_timer)

    def clear_status_bar(self):
        """Clear the status bar."""
        self.status_bar.clear()
