from . import server
import asyncio
import argparse

def main():
    """Main entry point for the Google Sheets MCP server."""
    parser = argparse.ArgumentParser(description='Generic Google Sheets MCP Server')
    parser.add_argument('--creds-file-path',
                        required=True,
                       help='OAuth 2.0 credentials file path')
    parser.add_argument('--token-path',
                        required=True,
                       help='File location to store and retrieve access and refresh tokens for application')
    
    args = parser.parse_args()
    asyncio.run(server.main(args.creds_file_path, args.token_path))

# Expose important items at package level
__all__ = ['main', 'server'] 