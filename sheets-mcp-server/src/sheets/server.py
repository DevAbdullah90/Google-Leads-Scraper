from typing import Any, Optional, List, Dict, Union
import argparse
import os
import asyncio
import logging
import json
from datetime import datetime, timezone

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SHEETS_PROMPTS = """You are a Google Sheets assistant.
You can create, read, update and manage Google Sheets spreadsheets.
You have the following tools available:
- Create spreadsheet (create-spreadsheet)
- Read range (read-range)
- Write range (write-range)
- Append rows (append-rows)
- Clear range (clear-range)
- Get spreadsheet info (get-spreadsheet-info)
Always confirm before making destructive changes to important data.
"""

# Define available prompts
PROMPTS = {
    "manage-sheets": types.Prompt(
        name="manage-sheets",
        description="Act as a Google Sheets management assistant",
        arguments=None,
    ),
}


class GoogleSheetsService:
    def __init__(self,
                 creds_file_path: str,
                 token_path: str,
                 scopes: list[str] = ['https://www.googleapis.com/auth/spreadsheets']):
        logger.info(f"Initializing GoogleSheetsService with creds file: {creds_file_path}")
        self.creds_file_path = creds_file_path
        self.token_path = token_path
        self.scopes = scopes
        self.token = self._get_token()
        logger.info("Token retrieved successfully")
        self.service = self._get_service()
        logger.info("Google Sheets service initialized")

    def _get_token(self) -> Credentials:
        """Get or refresh Google API token"""
        # First check if the credentials file is a service account
        try:
            if os.path.exists(self.creds_file_path):
                with open(self.creds_file_path, 'r') as f:
                    creds_data = json.load(f)
                if creds_data.get('type') == 'service_account':
                    logger.info('Loading service account credentials')
                    return service_account.Credentials.from_service_account_info(
                        creds_data, scopes=self.scopes
                    )
        except Exception as e:
            logger.warning(f'Failed to check/load service account credentials: {e}')

        token = None
    
        if os.path.exists(self.token_path):
            logger.info('Loading token from file')
            logger.info(f'Token path: {self.token_path}')
            logger.info(f'Scopes: {self.scopes}')
            token = Credentials.from_authorized_user_file(self.token_path, self.scopes)

        if not token or not token.valid:
            if token and token.expired and token.refresh_token:
                logger.info('Refreshing token')
                token.refresh(Request())
            else:
                logger.info('Fetching new token')
                flow = InstalledAppFlow.from_client_secrets_file(self.creds_file_path, self.scopes)
                token = flow.run_local_server(port=0)

            with open(self.token_path, 'w') as token_file:
                token_file.write(token.to_json())
                logger.info(f'Token saved to {self.token_path}')
        
        return token

    def _get_service(self) -> Any:
        """Initialize Google Sheets API service"""
        try:
            service = build('sheets', 'v4', credentials=self.token)
            return service
        except HttpError as error:
            logger.error(f'An error occurred building Sheets service: {error}')
            raise ValueError(f'An error occurred: {error}')

    async def create_spreadsheet(self, title: str, sheet_names: Optional[List[str]] = None) -> dict:
        """Create a new spreadsheet"""
        try:
            if sheet_names is None:
                sheet_names = ["Sheet1"]
                
            sheets = []
            for i, sheet_name in enumerate(sheet_names):
                sheets.append({
                    'properties': {
                        'title': sheet_name,
                        'sheetId': i,
                        'gridProperties': {
                            'rowCount': 1000,
                            'columnCount': 26
                        }
                    }
                })

            spreadsheet_body = {
                'properties': {
                    'title': title
                },
                'sheets': sheets
            }
            
            result = await asyncio.to_thread(
                self.service.spreadsheets().create(body=spreadsheet_body).execute
            )
            
            spreadsheet_id = result['spreadsheetId']
            
            logger.info(f"Created spreadsheet: {spreadsheet_id}")
            
            return {
                "status": "success",
                "spreadsheet_id": spreadsheet_id,
                "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
                "title": title,
                "sheets": sheet_names
            }
            
        except HttpError as error:
            logger.error(f"Error creating spreadsheet: {error}")
            return {"status": "error", "error_message": str(error)}

    async def read_range(self, spreadsheet_id: str, range_name: str) -> Union[List[List[str]], str]:
        """Read data from a specific range in the spreadsheet"""
        try:
            result = await asyncio.to_thread(
                self.service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name
                ).execute
            )

            values = result.get('values', [])
            logger.info(f"Read {len(values)} rows from {range_name}")
            return values

        except HttpError as error:
            logger.error(f"Error reading range {range_name}: {error}")
            return f"An HttpError occurred: {str(error)}"

    async def write_range(self, spreadsheet_id: str, range_name: str, values: List[List[str]]) -> dict:
        """Write data to a specific range in the spreadsheet"""
        try:
            body = {
                'values': values
            }

            result = await asyncio.to_thread(
                self.service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption='RAW',
                    body=body
                ).execute
            )

            logger.info(f"Updated range {range_name}")
            return {
                "status": "success",
                "updated_range": result.get('updatedRange', ''),
                "updated_rows": result.get('updatedRows', 0),
                "updated_columns": result.get('updatedColumns', 0),
                "updated_cells": result.get('updatedCells', 0)
            }

        except HttpError as error:
            logger.error(f"Error updating range {range_name}: {error}")
            return {"status": "error", "error_message": str(error)}

    async def append_rows(self, spreadsheet_id: str, range_name: str, values: List[List[str]]) -> dict:
        """Append rows to the end of a range"""
        try:
            body = {
                'values': values
            }

            result = await asyncio.to_thread(
                self.service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption='RAW',
                    body=body
                ).execute
            )

            logger.info(f"Appended {len(values)} rows to {range_name}")
            return {
                "status": "success",
                "updated_range": result.get('updates', {}).get('updatedRange', ''),
                "updated_rows": result.get('updates', {}).get('updatedRows', 0),
                "updated_columns": result.get('updates', {}).get('updatedColumns', 0),
                "updated_cells": result.get('updates', {}).get('updatedCells', 0)
            }

        except HttpError as error:
            logger.error(f"Error appending to range {range_name}: {error}")
            return {"status": "error", "error_message": str(error)}

    async def clear_range(self, spreadsheet_id: str, range_name: str) -> dict:
        """Clear data from a specific range"""
        try:
            result = await asyncio.to_thread(
                self.service.spreadsheets().values().clear(
                    spreadsheetId=spreadsheet_id,
                    range=range_name
                ).execute
            )

            logger.info(f"Cleared range {range_name}")
            return {
                "status": "success",
                "cleared_range": result.get('clearedRange', '')
            }

        except HttpError as error:
            logger.error(f"Error clearing range {range_name}: {error}")
            return {"status": "error", "error_message": str(error)}

    async def get_spreadsheet_info(self, spreadsheet_id: str) -> Union[dict, str]:
        """Get information about a spreadsheet"""
        try:
            result = await asyncio.to_thread(
                self.service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id,
                    fields='properties,sheets.properties'
                ).execute
            )

            spreadsheet_info = {
                "spreadsheet_id": spreadsheet_id,
                "title": result['properties']['title'],
                "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
                "sheets": []
            }

            for sheet in result.get('sheets', []):
                sheet_props = sheet['properties']
                spreadsheet_info["sheets"].append({
                    "sheet_id": sheet_props['sheetId'],
                    "title": sheet_props['title'],
                    "row_count": sheet_props['gridProperties']['rowCount'],
                    "column_count": sheet_props['gridProperties']['columnCount']
                })

            logger.info(f"Retrieved info for spreadsheet: {spreadsheet_info['title']}")
            return spreadsheet_info

        except HttpError as error:
            logger.error(f"Error getting spreadsheet info: {error}")
            return f"An HttpError occurred: {str(error)}"

    async def batch_update(self, spreadsheet_id: str, updates: List[dict]) -> dict:
        """Perform multiple updates in a single request"""
        try:
            body = {
                'valueInputOption': 'RAW',
                'data': updates
            }

            result = await asyncio.to_thread(
                self.service.spreadsheets().values().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body=body
                ).execute
            )

            logger.info(f"Performed {len(updates)} batch updates")
            return {
                "status": "success",
                "total_updated_rows": result.get('totalUpdatedRows', 0),
                "total_updated_columns": result.get('totalUpdatedColumns', 0),
                "total_updated_cells": result.get('totalUpdatedCells', 0),
                "total_updated_sheets": result.get('totalUpdatedSheets', 0)
            }

        except HttpError as error:
            logger.error(f"Error performing batch update: {error}")
            return {"status": "error", "error_message": str(error)}


async def main(creds_file_path: str, token_path: str):
    
    sheets_service = GoogleSheetsService(creds_file_path, token_path)
    server = Server("google-sheets")

    @server.list_prompts()
    async def list_prompts() -> list[types.Prompt]:
        return list(PROMPTS.values())

    @server.get_prompt()
    async def get_prompt(
        name: str, arguments: dict[str, str] | None = None
    ) -> types.GetPromptResult:
        if name not in PROMPTS:
            raise ValueError(f"Prompt not found: {name}")

        if name == "manage-sheets":
            return types.GetPromptResult(
                messages=[
                    types.PromptMessage(
                        role="user",
                        content=types.TextContent(
                            type="text",
                            text=SHEETS_PROMPTS,
                        )
                    )
                ]
            )

        raise ValueError("Prompt implementation not found")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="create-spreadsheet",
                description="Create a new Google Sheets spreadsheet",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Title for the spreadsheet",
                        },
                        "sheet_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Names of sheets to create (optional, defaults to ['Sheet1'])",
                        },
                    },
                    "required": ["title"],
                },
            ),
            types.Tool(
                name="read-range",
                description="Read data from a specific range in a spreadsheet",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "Google Sheets spreadsheet ID",
                        },
                        "range_name": {
                            "type": "string",
                            "description": "Range to read (e.g., 'Sheet1!A1:C10', 'Sheet1!A:A')",
                        },
                    },
                    "required": ["spreadsheet_id", "range_name"],
                },
            ),
            types.Tool(
                name="write-range",
                description="Write data to a specific range in a spreadsheet",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "Google Sheets spreadsheet ID",
                        },
                        "range_name": {
                            "type": "string",
                            "description": "Range to write to (e.g., 'Sheet1!A1:C3')",
                        },
                        "values": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "description": "2D array of values to write",
                        },
                    },
                    "required": ["spreadsheet_id", "range_name", "values"],
                },
            ),
            types.Tool(
                name="append-rows",
                description="Append rows to the end of a range in a spreadsheet",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "Google Sheets spreadsheet ID",
                        },
                        "range_name": {
                            "type": "string",
                            "description": "Range to append to (e.g., 'Sheet1!A:C')",
                        },
                        "values": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "description": "2D array of values to append",
                        },
                    },
                    "required": ["spreadsheet_id", "range_name", "values"],
                },
            ),
            types.Tool(
                name="clear-range",
                description="Clear data from a specific range in a spreadsheet",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "Google Sheets spreadsheet ID",
                        },
                        "range_name": {
                            "type": "string",
                            "description": "Range to clear (e.g., 'Sheet1!A1:C10')",
                        },
                    },
                    "required": ["spreadsheet_id", "range_name"],
                },
            ),
            types.Tool(
                name="get-spreadsheet-info",
                description="Get information about a spreadsheet (title, sheets, dimensions)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "Google Sheets spreadsheet ID",
                        },
                    },
                    "required": ["spreadsheet_id"],
                },
            ),
            types.Tool(
                name="batch-update",
                description="Perform multiple range updates in a single request",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "Google Sheets spreadsheet ID",
                        },
                        "updates": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "range": {"type": "string"},
                                    "values": {
                                        "type": "array",
                                        "items": {
                                            "type": "array",
                                            "items": {"type": "string"}
                                        }
                                    }
                                },
                                "required": ["range", "values"]
                            },
                            "description": "Array of range updates",
                        },
                    },
                    "required": ["spreadsheet_id", "updates"],
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:

        if name == "create-spreadsheet":
            title = arguments.get("title")
            sheet_names = arguments.get("sheet_names")
            if not title:
                raise ValueError("Missing title parameter")
                
            result = await sheets_service.create_spreadsheet(title, sheet_names)
            
            if result["status"] == "success":
                response_text = f"Created spreadsheet successfully!\nTitle: {result['title']}\nID: {result['spreadsheet_id']}\nURL: {result['url']}\nSheets: {', '.join(result['sheets'])}"
            else:
                response_text = f"Failed to create spreadsheet: {result['error_message']}"
            return [types.TextContent(type="text", text=response_text)]

        if name == "read-range":
            spreadsheet_id = arguments.get("spreadsheet_id")
            range_name = arguments.get("range_name")
            if not spreadsheet_id or not range_name:
                raise ValueError("Missing spreadsheet_id or range_name parameter")
                
            result = await sheets_service.read_range(spreadsheet_id, range_name)
            return [types.TextContent(type="text", text=str(result), artifact={"type": "json", "data": result})]

        if name == "write-range":
            spreadsheet_id = arguments.get("spreadsheet_id")
            range_name = arguments.get("range_name")
            values = arguments.get("values")
            if not spreadsheet_id or not range_name or not values:
                raise ValueError("Missing required parameters")
                
            result = await sheets_service.write_range(spreadsheet_id, range_name, values)
            
            if result["status"] == "success":
                response_text = f"Updated range successfully!\nRange: {result['updated_range']}\nRows: {result['updated_rows']}\nColumns: {result['updated_columns']}\nCells: {result['updated_cells']}"
            else:
                response_text = f"Failed to update range: {result['error_message']}"
            return [types.TextContent(type="text", text=response_text)]

        if name == "append-rows":
            spreadsheet_id = arguments.get("spreadsheet_id")
            range_name = arguments.get("range_name")
            values = arguments.get("values")
            if not spreadsheet_id or not range_name or not values:
                raise ValueError("Missing required parameters")
                
            result = await sheets_service.append_rows(spreadsheet_id, range_name, values)
            
            if result["status"] == "success":
                response_text = f"Appended rows successfully!\nRange: {result['updated_range']}\nRows: {result['updated_rows']}\nColumns: {result['updated_columns']}\nCells: {result['updated_cells']}"
            else:
                response_text = f"Failed to append rows: {result['error_message']}"
            return [types.TextContent(type="text", text=response_text)]

        if name == "clear-range":
            spreadsheet_id = arguments.get("spreadsheet_id")
            range_name = arguments.get("range_name")
            if not spreadsheet_id or not range_name:
                raise ValueError("Missing spreadsheet_id or range_name parameter")
                
            result = await sheets_service.clear_range(spreadsheet_id, range_name)
            
            if result["status"] == "success":
                response_text = f"Cleared range successfully: {result['cleared_range']}"
            else:
                response_text = f"Failed to clear range: {result['error_message']}"
            return [types.TextContent(type="text", text=response_text)]

        if name == "get-spreadsheet-info":
            spreadsheet_id = arguments.get("spreadsheet_id")
            if not spreadsheet_id:
                raise ValueError("Missing spreadsheet_id parameter")
                
            result = await sheets_service.get_spreadsheet_info(spreadsheet_id)
            return [types.TextContent(type="text", text=str(result), artifact={"type": "json", "data": result})]

        if name == "batch-update":
            spreadsheet_id = arguments.get("spreadsheet_id")
            updates = arguments.get("updates")
            if not spreadsheet_id or not updates:
                raise ValueError("Missing spreadsheet_id or updates parameter")
                
            result = await sheets_service.batch_update(spreadsheet_id, updates)
            
            if result["status"] == "success":
                response_text = f"Batch update successful!\nRows: {result['total_updated_rows']}\nColumns: {result['total_updated_columns']}\nCells: {result['total_updated_cells']}\nSheets: {result['total_updated_sheets']}"
            else:
                response_text = f"Failed to perform batch update: {result['error_message']}"
            return [types.TextContent(type="text", text=response_text)]

        else:
            logger.error(f"Unknown tool: {name}")
            raise ValueError(f"Unknown tool: {name}")

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        try:
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="google-sheets",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
        except Exception as e:
            logger.error(f"Server error: {str(e)}")
            # Don't re-raise to prevent ungraceful shutdown

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Google Sheets MCP Server')
    parser.add_argument('--creds-file-path',
                        required=True,
                       help='OAuth 2.0 credentials file path')
    parser.add_argument('--token-path',
                        required=True,
                       help='File location to store and retrieve access and refresh tokens for application')
    
    args = parser.parse_args()
    asyncio.run(main(args.creds_file_path, args.token_path)) 