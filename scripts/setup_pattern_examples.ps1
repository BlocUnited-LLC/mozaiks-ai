# setup_pattern_examples.ps1
# Creates the pattern_examples folder structure and moves existing .md files

$patternsDir = "c:\Users\mbari\OneDrive\Desktop\BlocUnited\BlocUnited Code\MozaiksAI\docs\patterns"

# Pattern mapping: folder name -> original .md filename
$patterns = @{
    "1_context_aware_routing" = "context-aware-routing.md"
    "2_escalation" = "escalation.md"
    "3_feedback_loop" = "Feedback-Loop.md"
    "4_hierarchical" = "Hierarchical.md"
    "5_organic" = "Organic.md"
    "6_pipeline" = "Pipeline-Sequential.md"
    "7_redundant" = "Redundant.md"
    "8_star" = "Star.md"
    "9_triage_with_tasks" = "Triage-with-Task.md"
}

# JSON templates
$agentsTemplate = @'
{
  "$schema": "../schemas/agents.schema.json",
  "pattern_id": {PATTERN_ID},
  "pattern_name": "{PATTERN_NAME}",
  "agents": [
    {
      "name": "example_agent",
      "role": "worker",
      "description": "Agent description for Organic pattern LLM selection",
      "system_message": "You are an agent that...",
      "tools": [],
      "after_work": "user"
    }
  ]
}
'@

$contextVariablesTemplate = @'
{
  "$schema": "../schemas/context_variables.schema.json",
  "pattern_id": {PATTERN_ID},
  "pattern_name": "{PATTERN_NAME}",
  "context_variables": [
    {
      "name": "task_started",
      "type": "boolean",
      "default": false,
      "description": "Whether the workflow has been initiated"
    }
  ]
}
'@

$handoffsTemplate = @'
{
  "$schema": "../schemas/handoffs.schema.json",
  "pattern_id": {PATTERN_ID},
  "pattern_name": "{PATTERN_NAME}",
  "entry_agent": "example_agent",
  "exit_target": "user",
  "handoffs": [
    {
      "source_agent": "example_agent",
      "target": "user",
      "type": "after_work",
      "condition": null,
      "available": null
    }
  ]
}
'@

$toolsTemplate = @'
{
  "$schema": "../schemas/tools.schema.json",
  "pattern_id": {PATTERN_ID},
  "pattern_name": "{PATTERN_NAME}",
  "tools": [
    {
      "name": "example_tool",
      "description": "Tool description",
      "owner_agent": "example_agent",
      "parameters": {
        "type": "object",
        "properties": {},
        "required": []
      },
      "returns": {
        "type": "reply_result",
        "target": "user",
        "context_updates": {}
      }
    }
  ]
}
'@

Write-Host "Setting up pattern examples structure..." -ForegroundColor Cyan
Write-Host ""

foreach ($folder in $patterns.Keys | Sort-Object) {
    $mdFile = $patterns[$folder]
    $folderPath = Join-Path $patternsDir $folder
    $patternId = [int]$folder.Split("_")[0]
    $patternName = ($folder -replace "^\d+_", "") -replace "_", " "
    $patternName = (Get-Culture).TextInfo.ToTitleCase($patternName)
    
    Write-Host "Creating: $folder" -ForegroundColor Green
    
    # Create folder
    if (-not (Test-Path $folderPath)) {
        New-Item -ItemType Directory -Path $folderPath -Force | Out-Null
    }
    
    # Move the .md file if it exists at the root
    $sourceMd = Join-Path $patternsDir $mdFile
    $destMd = Join-Path $folderPath "example.md"
    
    if (Test-Path $sourceMd) {
        Move-Item -Path $sourceMd -Destination $destMd -Force
        Write-Host "  Moved: $mdFile -> $folder/example.md" -ForegroundColor Yellow
    } elseif (Test-Path $destMd) {
        Write-Host "  Already exists: $folder/example.md" -ForegroundColor DarkGray
    } else {
        Write-Host "  Warning: $mdFile not found" -ForegroundColor Red
    }
    
    # Create JSON files with pattern-specific values
    $agentsJson = $agentsTemplate -replace "\{PATTERN_ID\}", $patternId -replace "\{PATTERN_NAME\}", $patternName
    $contextJson = $contextVariablesTemplate -replace "\{PATTERN_ID\}", $patternId -replace "\{PATTERN_NAME\}", $patternName
    $handoffsJson = $handoffsTemplate -replace "\{PATTERN_ID\}", $patternId -replace "\{PATTERN_NAME\}", $patternName
    $toolsJson = $toolsTemplate -replace "\{PATTERN_ID\}", $patternId -replace "\{PATTERN_NAME\}", $patternName
    
    # Write JSON files
    $agentsPath = Join-Path $folderPath "agents.json"
    $contextPath = Join-Path $folderPath "context_variables.json"
    $handoffsPath = Join-Path $folderPath "handoffs.json"
    $toolsPath = Join-Path $folderPath "tools.json"
    
    if (-not (Test-Path $agentsPath)) {
        Set-Content -Path $agentsPath -Value $agentsJson -Encoding UTF8
        Write-Host "  Created: agents.json" -ForegroundColor DarkGreen
    }
    
    if (-not (Test-Path $contextPath)) {
        Set-Content -Path $contextPath -Value $contextJson -Encoding UTF8
        Write-Host "  Created: context_variables.json" -ForegroundColor DarkGreen
    }
    
    if (-not (Test-Path $handoffsPath)) {
        Set-Content -Path $handoffsPath -Value $handoffsJson -Encoding UTF8
        Write-Host "  Created: handoffs.json" -ForegroundColor DarkGreen
    }
    
    if (-not (Test-Path $toolsPath)) {
        Set-Content -Path $toolsPath -Value $toolsJson -Encoding UTF8
        Write-Host "  Created: tools.json" -ForegroundColor DarkGreen
    }
    
    Write-Host ""
}

Write-Host "Done! Pattern examples structure created." -ForegroundColor Cyan
Write-Host ""
Write-Host "Structure:" -ForegroundColor White
Get-ChildItem -Path $patternsDir -Directory | ForEach-Object {
    Write-Host "  $($_.Name)/" -ForegroundColor Yellow
    Get-ChildItem -Path $_.FullName | ForEach-Object {
        Write-Host "    $($_.Name)" -ForegroundColor Gray
    }
}
