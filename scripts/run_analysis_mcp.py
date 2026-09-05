#!/usr/bin/env python3
"""Run the Trading Analysis MCP over Streamable HTTP."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from trading_analysis_mcp.server import main


if __name__ == "__main__":
    main()
