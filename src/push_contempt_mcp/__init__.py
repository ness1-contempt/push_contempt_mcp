from push_contempt_mcp.server import mcp


def main() -> None:
    """Entry point: avvia il server su stdio (usato da Claude Code / Claude Desktop)."""
    mcp.run()


__all__ = ["main", "mcp"]
