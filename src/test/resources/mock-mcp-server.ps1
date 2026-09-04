$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
while (($line = [Console]::In.ReadLine()) -ne $null) {
    try {
        $request = $line | ConvertFrom-Json
        if ($null -eq $request.id) { continue }
        $result = $null
        if ($request.method -eq 'initialize') {
            $result = [ordered]@{
                protocolVersion = $request.params.protocolVersion
                capabilities = @{ tools = @{ listChanged = $false } }
                serverInfo = @{ name = 'mock-stdio'; version = '1.0' }
            }
        } elseif ($request.method -eq 'tools/list') {
            $result = @{ tools = @(@{
                name = 'stdio_echo'
                description = 'Echo over stdio'
                inputSchema = @{ type = 'object' }
                annotations = @{ readOnlyHint = $true }
            }) }
        } elseif ($request.method -eq 'tools/call') {
            $result = @{ content = @(@{ type = 'text'; text = "stdio:$($env:STAR_MCP_TEST_ENV)" }); isError = $false }
        } else {
            $result = @{}
        }
        $response = [ordered]@{ jsonrpc = '2.0'; id = $request.id; result = $result }
        [Console]::Out.WriteLine(($response | ConvertTo-Json -Depth 20 -Compress))
        [Console]::Out.Flush()
    } catch {
        [Console]::Error.WriteLine($_.Exception.Message)
    }
}
