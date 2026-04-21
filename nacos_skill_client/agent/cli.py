"""Nacos-Agent CLI — 命令行对话工具。

交互式 CLI，连接到 nacos-skill-client API 与 Agent 对话。

用法::

    nacos-agent                    # 使用默认配置启动
    nacos-agent --api-url http://10.0.0.1:8002
    nacos-agent --model gpt-4o
    echo "hello" | nacos-agent     # stdin 模式

支持命令：
    /quit or /exit     — 退出
    /clear             — 清空对话历史
    /tools             — 查看可用工具
    /reload            — 重新加载工具
    /help              — 显示帮助
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from urllib.parse import urljoin


class NacosAgentCLI:
    """Nacos-Agent 交互式 CLI。"""

    PROMPT = "\U0001F33A \u27A1 "  # 🌼 ➡
    HELP_TEXT = (
        "\n\U00002B50 Available commands:\n"
        "  /quit, /exit          Exit\n"
        "  /clear                Clear conversation history\n"
        "  /tools                Show available tools\n"
        "  /reload               Reload tools from Nacos\n"
        "  /config               Show current config\n"
        "  /help                 Show this help\n\n"
        "Examples:\n"
        "  Ask anything: 北京天气怎么样？\n"
        "  Multi-turn:    那明天呢？（自动携带上下文）\n"
    )

    def __init__(self, api_url: str = "http://127.0.0.1:8002", timeout: int = 120):
        """
        Args:
            api_url: nacos-skill-client API 地址
            timeout: 请求超时秒数
        """
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.thread_id = "cli-session"
        self.message_count = 0

    def run(self) -> None:
        """运行交互式 CLI 循环。"""
        print("\U0001F527 Connected to", self.api_url)
        print("Type your message or /help for commands.")
        print()

        while True:
            try:
                user_input = input(self.PROMPT)
            except (EOFError, KeyboardInterrupt):
                print("\U0001F44B Goodbye!")
                break

            if not user_input.strip():
                continue

            if user_input.startswith("/"):
                self._handle_command(user_input)
            else:
                self._send_message(user_input)

    def _handle_command(self, cmd: str) -> None:
        """处理 CLI 命令。"""
        parts = cmd.strip().split(None, 1)
        command = parts[0].lower()

        if command in ("/quit", "/exit"):
            print("\U0001F44B Goodbye!")
            sys.exit(0)

        elif command == "/clear":
            self.thread_id = f"cli-session-{int(time.time())}"
            self.message_count = 0
            print("\U0001F5D1 Conversation history cleared.")

        elif command == "/tools":
            self._show_tools()

        elif command == "/reload":
            self._reload_tools()

        elif command in ("/help", "/h"):
            print(self.HELP_TEXT)

        elif command == "/config":
            print(f"  API URL : {self.api_url}")
            print(f"  Thread  : {self.thread_id}")
            print(f"  Messages: {self.message_count}")

        else:
            print(f"\u26A0 Unknown command: {command}. Type /help for available commands.")

    def _send_message(self, message: str) -> None:
        """发送消息到 Agent。"""
        import requests

        self.message_count += 1

        try:
            resp = requests.post(
                urljoin(self.api_url, "/api/v1/chat"),
                json={"message": message, "thread_id": self.thread_id},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            self._print_response(data)

            if "thread_id" in data:
                self.thread_id = data["thread_id"]

        except requests.ConnectionError:
            print("\u274C Cannot connect to server. Is it running?")
        except requests.Timeout:
            print(f"\u274C Request timed out after {self.timeout}s")
        except requests.HTTPError as e:
            print(f"\u274C Server error: {e}")
        except Exception as e:
            print(f"\u274C Error: {e}")

    def _print_response(self, data: dict) -> None:
        """格式化输出 Agent 响应。"""
        answer = data.get("answer", "(no answer)")
        print(f"\n{answer}")

        tool_used = data.get("tool_used")
        if tool_used:
            print(f"\U0001F527 Used tool: {tool_used}")

        took_ms = data.get("took_ms", 0)
        if took_ms > 0:
            print(f"\U0001FAC1 Took {took_ms:.0f}ms")

        steps = data.get("thinking_steps")
        if steps and len(steps) > 1:
            print(f"\U0001F4DA Steps: {len(steps)}")

    def _show_tools(self) -> None:
        """显示可用工具列表。"""
        import requests

        try:
            resp = requests.get(
                urljoin(self.api_url, "/api/v1/skills/tools"),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            tools = data.get("tools", [])
            total = data.get("total", 0)

            if not tools:
                print("\u274E No tools loaded.")
                return

            print(f"\U0001F4D1 {total} tool(s) available:")
            for tool in tools:
                name = tool.get("name", "?")
                desc = tool.get("description", "")
                print(f"  \U0001F50D {name}: {desc}")

        except requests.ConnectionError:
            print("\u274C Cannot connect to server.")
        except Exception as e:
            print(f"\u274C Error: {e}")

    def _reload_tools(self) -> None:
        """重新加载工具。"""
        import requests

        try:
            resp = requests.post(
                urljoin(self.api_url, "/api/v1/skills/tools/reload"),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == "ok":
                loaded = data.get("loaded", 0)
                time_ms = data.get("time_ms", 0)
                print(f"\u2705 Reloaded {loaded} tool(s) in {time_ms:.0f}ms")
            else:
                print(f"\u26A0 Reload: {data.get('status', 'unknown')}")

        except requests.ConnectionError:
            print("\u274C Cannot connect to server.")
        except Exception as e:
            print(f"\u274C Error: {e}")


def main() -> None:
    """CLI 入口函数。"""
    parser = argparse.ArgumentParser(
        description="Nacos-Agent CLI — 交互式对话工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8002",
        help="nacos-skill-client API URL (default: http://127.0.0.1:8002)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Request timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--single",
        type=str,
        help="Send a single message and exit (non-interactive mode)",
    )

    args = parser.parse_args()

    cli = NacosAgentCLI(api_url=args.api_url, timeout=args.timeout)

    if args.single:
        cli.message_count = 1
        print(cli.PROMPT, args.single, flush=True)
        cli._send_message(args.single)
        print()
    else:
        cli.run()


if __name__ == "__main__":
    main()
