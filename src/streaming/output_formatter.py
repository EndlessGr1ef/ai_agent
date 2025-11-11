"""Output formatting utilities."""

class OutputFormatter:
    """Format and display thinking and answer content."""

    def __init__(self):
        """Initialize the output formatter."""
        self.reasoning_displayed = False
        self.answer_displayed = False

    def reset(self):
        """Reset for new output."""
        self.reasoning_displayed = False
        self.answer_displayed = False

    def print_assistant_header(self):
        """Print the 'Assistant:' header."""
        print("Assistant:")

    def print_thinking(self, thinking_content: str):
        """Print thinking content with formatting.

        Args:
            thinking_content: The thinking content to print
        """
        if not self.reasoning_displayed:
            # First thinking output
            print()
            self.reasoning_displayed = True

        print(f"[thinking] {thinking_content}", end="", flush=True)

    def print_answer(self, answer_content: str):
        """Print answer content with formatting.

        Args:
            answer_content: The answer content to print
        """
        if not self.answer_displayed:
            # First answer output
            print()
            print("[answers] ", end="", flush=True)
            self.answer_displayed = True

        print(answer_content, end="", flush=True)

    def print_empty_line(self):
        """Print an empty line."""
        print()

    def print_error(self, error_msg: str):
        """Print an error message.

        Args:
            error_msg: The error message to print
        """
        print()
        print(f"[Error] {error_msg}")

    def print_hint(self, hint_msg: str):
        """Print a hint message.

        Args:
            hint_msg: The hint message to print
        """
        print(f"[Hint] {hint_msg}")
