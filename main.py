import os
import sys
import argparse
from typing import List, Dict

from dotenv import load_dotenv

try:
    # OpenAI Python SDK (>= 1.x)
    from openai import OpenAI
except Exception as e:
    print("[Error] 'openai' package not found. Please install: pip install -r requirements.txt")
    raise


def require_api_key() -> str:
    """Ensure OPENAI_API_KEY is set; return its value or exit."""
    load_dotenv()  # Load .env
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print(
            "[Error] OPENAI_API_KEY not found.\n"
            "Please create a .env file at project root and set:\n"
            "OPENAI_API_KEY=your_api_key\n"
        )
        sys.exit(1)
    return api_key


def chat_once(client: OpenAI, model: str, prompt: str, system_prompt: str = "You are a helpful assistant.", timeout: int = 300) -> str:
    """Execute a single-turn chat and return assistant text."""
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
        extra_body={"reasoning_split": True},
        timeout=timeout,
    )
    return resp.choices[0].message.content


def chat_loop(client: OpenAI, model: str, system_prompt: str = "You are a helpful assistant.", timeout: int = 30) -> None:
    """Interactive multi-turn session. Type /exit or /quit to leave."""
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    print("\n===== AI Agent (interactive) =====")
    print("Tip: type /exit or /quit to exit; type /reset to reset the conversation.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[Info] Exited.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"/exit", "/quit"}:
            print("[Info] Bye!")
            break
        if user_input.lower() == "/reset":
            messages = [{"role": "system", "content": system_prompt}]
            print("[Info] Conversation reset.")
            continue

        messages.append({"role": "user", "content": user_input})
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                extra_body={"reasoning_split": True},
                timeout=timeout,
            )
            assistant_msg = resp.choices[0].message.content
        except Exception as e:
            print(f"[Error] Request failed: {e}")
            continue

        print(f"Assistant: {assistant_msg}\n")
        messages.append({"role": "assistant", "content": assistant_msg})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple OpenAI-compatible test agent")
    parser.add_argument("-p", "--prompt", type=str, help="User prompt for single-turn chat")
    parser.add_argument(
        "-s",
        "--system",
        type=str,
        default=os.getenv("OPENAI_SYSTEM_PROMPT", "You are a helpful assistant."),
        help="System prompt (default from env OPENAI_SYSTEM_PROMPT or a fixed string)",
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default=os.getenv("OPENAI_MODEL", "MiniMax-M2"),
        help="Model name (default from env OPENAI_MODEL or 'MiniMax-M2')",
    )
    parser.add_argument(
        "-u",
        "--base-url",
        type=str,
        default=os.getenv("OPENAI_BASE_URL", "https://api.minimax.io/v1"),
        help="Custom OpenAI-compatible API base_url (default from env OPENAI_BASE_URL or 'https://api.minimax.io/v1')",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=300,
        help="Request timeout in seconds (default: 300)",
    )
    return parser.parse_args()


def main() -> None:
    # Ensure API key exists
    api_key = require_api_key()

    args = parse_args()
    model = args.model
    system_prompt = args.system
    base_url = args.base_url
    timeout = args.timeout

    # Initialize client with custom base_url and API key
    client = OpenAI(api_key=api_key, base_url=base_url)

    if args.prompt:
        # Single-turn mode
        try:
            answer = chat_once(client, model, prompt=args.prompt, system_prompt=system_prompt, timeout=timeout)
        except Exception as e:
            print(f"[Error] Request failed: {e}")
            sys.exit(2)
        print("Assistant:")
        print(answer)
    else:
        # Interactive mode
        chat_loop(client, model, system_prompt, timeout)


if __name__ == "__main__":
    main()