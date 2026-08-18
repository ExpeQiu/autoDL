#!/usr/bin/env python3
"""MCP stdio 入口。仅暴露 agent_safe: true 的命令。"""

from autodl_cli.mcp_server import main

if __name__ == "__main__":
    main()
