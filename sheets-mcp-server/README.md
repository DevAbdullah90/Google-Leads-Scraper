# Google Sheets MCP Server

A Model Context Protocol (MCP) server that provides comprehensive Google Sheets integration. This server enables you to create, read, update, and manage Google Sheets spreadsheets programmatically.

## 🎯 Purpose

This server enables you to:
- **Create** new Google Sheets spreadsheets with custom sheet names
- **Read** data from any range in a spreadsheet
- **Write** data to specific ranges
- **Append** new rows to existing data
- **Clear** ranges of data
- **Get** spreadsheet information and metadata
- **Batch update** multiple ranges efficiently

## 🛠️ Available Tools

### Core Operations

- **create-spreadsheet**
  - Creates a new Google Sheets spreadsheet
  - Input: `title` (required), `sheet_names` (optional array)
  - Returns: Spreadsheet ID, URL, and created sheet names

- **read-range**
  - Reads data from a specific range
  - Input: `spreadsheet_id`, `range_name` (e.g., 'Sheet1!A1:C10')
  - Returns: 2D array of cell values

- **write-range**
  - Writes data to a specific range (overwrites existing data)
  - Input: `spreadsheet_id`, `range_name`, `values` (2D array)
  - Returns: Update statistics

- **append-rows**
  - Appends rows to the end of a range
  - Input: `spreadsheet_id`, `range_name`, `values` (2D array)
  - Returns: Update statistics

- **clear-range**
  - Clears all data from a specified range
  - Input: `spreadsheet_id`, `range_name`
  - Returns: Confirmation of cleared range

- **get-spreadsheet-info**
  - Gets metadata about a spreadsheet
  - Input: `spreadsheet_id`
  - Returns: Title, URL, sheet information, dimensions

- **batch-update**
  - Performs multiple range updates in a single request
  - Input: `spreadsheet_id`, `updates` (array of range/values pairs)
  - Returns: Total update statistics

### Prompts

- **manage-sheets**: General Google Sheets management prompt for AI assistants

## 🚀 Setup

### 1. Google Sheets API Setup

1. [Create a Google Cloud project](https://console.cloud.google.com/projectcreate) or use an existing one
2. [Enable the Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com)
3. [Configure an OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)
   - Select "External" for testing purposes
   - Add your email as a test user
4. Add OAuth scope: `https://www.googleapis.com/auth/spreadsheets`
5. [Create OAuth 2.0 Client ID credentials](https://console.cloud.google.com/apis/credentials/oauthclient)
   - Choose "Desktop Application"
6. Download the credentials JSON file
7. Save it securely and note the file path

### 2. Installation

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
cd sheets-mcp-server
uv sync
```

### 3. Authentication

On first run, the server will launch a browser for OAuth authentication.
Access tokens will be saved to the specified `--token-path` for future use.

## 💼 Usage

### Standalone Usage

```bash
uv run sheets \
  --creds-file-path /path/to/your/credentials.json \
  --token-path /path/to/your/tokens.json
```

### Integration with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "google-sheets": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/sheets-mcp-server",
        "run",
        "sheets",
        "--creds-file-path",
        "/path/to/your/credentials.json",
        "--token-path",
        "/path/to/your/tokens.json"
      ]
    }
  }
}
```

### Integration with Other MCP Clients

This server follows the standard MCP protocol and can be integrated with any MCP-compatible client.

## 📋 Usage Examples

### Creating a New Spreadsheet
```json
{
  "tool": "create-spreadsheet",
  "arguments": {
    "title": "My Data Analysis",
    "sheet_names": ["Data", "Analysis", "Charts"]
  }
}
```

### Reading Data
```json
{
  "tool": "read-range",
  "arguments": {
    "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    "range_name": "Sheet1!A1:E10"
  }
}
```

### Writing Data
```json
{
  "tool": "write-range",
  "arguments": {
    "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    "range_name": "Sheet1!A1:C3",
    "values": [
      ["Name", "Age", "City"],
      ["Alice", "30", "New York"],
      ["Bob", "25", "San Francisco"]
    ]
  }
}
```

### Appending New Data
```json
{
  "tool": "append-rows",
  "arguments": {
    "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    "range_name": "Sheet1!A:C",
    "values": [
      ["Charlie", "35", "Chicago"],
      ["Diana", "28", "Boston"]
    ]
  }
}
```

### Batch Updates
```json
{
  "tool": "batch-update",
  "arguments": {
    "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    "updates": [
      {
        "range": "Sheet1!A1:B2",
        "values": [["Header1", "Header2"], ["Data1", "Data2"]]
      },
      {
        "range": "Sheet1!D1:E2",
        "values": [["Header3", "Header4"], ["Data3", "Data4"]]
      }
    ]
  }
}
```

## 🧪 Testing

### With MCP Inspector

Test the server using [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector):

```bash
npx @modelcontextprotocol/inspector uv run sheets \
  --creds-file-path /path/to/credentials.json \
  --token-path /path/to/tokens.json
```

### Manual Testing

1. **Create a test spreadsheet**
2. **Read some data** to verify connectivity
3. **Write test data** to ensure write permissions work
4. **Try different range formats** (A1 notation, named ranges, etc.)

## 📊 Common Use Cases

### Data Analysis Workflows
```
1. Create spreadsheet for analysis
2. Import raw data via append-rows
3. Read data for processing
4. Write calculated results back
5. Generate reports and summaries
```

### Content Management
```
1. Create content tracking spreadsheet
2. Append new content entries
3. Update status and metadata
4. Generate content reports
```

### Project Management
```
1. Create project tracking sheet
2. Add tasks and milestones
3. Update progress and status
4. Generate project dashboards
```

### Data Synchronization
```
1. Read data from external systems
2. Transform and validate data
3. Write to Google Sheets for sharing
4. Keep data synchronized across platforms
```

## 🔧 Advanced Features

### Range Formats Supported
- **A1 notation**: `Sheet1!A1:C10`
- **Named ranges**: `MyNamedRange`
- **Entire columns**: `Sheet1!A:C`
- **Entire rows**: `Sheet1!1:5`
- **Open-ended ranges**: `Sheet1!A1:C`

### Error Handling
The server includes comprehensive error handling for:
- Authentication failures and token refresh
- Network timeouts and connectivity issues
- Invalid spreadsheet IDs or range names
- Permission errors
- API quota limits
- Malformed data inputs

### Performance Considerations
- Uses `asyncio.to_thread` for non-blocking API calls
- Supports batch operations for efficiency
- Handles Google Sheets API rate limits gracefully
- Optimized for both small and large data operations

## 🔒 Security & Permissions

### Required OAuth Scopes
- `https://www.googleapis.com/auth/spreadsheets` - Full access to Google Sheets

### Security Best Practices
- Store credentials securely
- Use environment variables for sensitive paths
- Implement proper access controls
- Regularly rotate access tokens
- Monitor API usage and quotas

## 🤝 Contributing & Extending

This server is designed to be easily extensible. Common enhancements:

### Additional Features
- **Formatting operations** (bold, colors, borders)
- **Formula support** for calculated cells
- **Chart creation** and management
- **Conditional formatting** rules
- **Data validation** constraints
- **Pivot tables** and summaries

### Integration Enhancements
- **Database connectors** for data import/export
- **CSV/Excel file** import/export
- **Real-time collaboration** features
- **Webhook notifications** for changes
- **Advanced search** and filtering

### Performance Optimizations
- **Caching strategies** for frequently accessed data
- **Streaming support** for large datasets
- **Parallel processing** for bulk operations
- **Connection pooling** for high-throughput scenarios

## 📚 API Reference

### Google Sheets API Limits
- **100 requests per 100 seconds per user**
- **1000 requests per 100 seconds** (total quota)
- **Maximum 10 million cells** per spreadsheet
- **Maximum 200 sheets** per spreadsheet

### Response Formats
All tools return structured responses with:
- **Status indicators** (success/error)
- **Detailed error messages** when applicable
- **Update statistics** for write operations
- **Structured data** for read operations

## 🆘 Troubleshooting

### Common Issues

1. **Authentication Errors**
   - Verify credentials file path
   - Check OAuth consent screen configuration
   - Ensure correct scopes are configured

2. **Permission Errors**
   - Verify spreadsheet sharing permissions
   - Check if spreadsheet exists
   - Ensure account has edit access

3. **Range Errors**
   - Validate A1 notation format
   - Check sheet names for typos
   - Verify range bounds

4. **Quota Exceeded**
   - Implement request throttling
   - Use batch operations when possible
   - Monitor usage in Google Cloud Console

---

**Ready to supercharge your Google Sheets workflows with automated operations!** 🚀
