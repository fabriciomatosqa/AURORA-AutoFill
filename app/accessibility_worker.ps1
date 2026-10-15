# Read-only UI Automation bridge. Requests/responses stay in anonymous pipes.
# No selection, keystrokes, clipboard access, logs, or document modification.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

function Read-FocusedText($request) {
    $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
    if ($null -eq $focused -or $focused.Current.ProcessId -ne $request.process) {
        return @{ status = 'changed' }
    }
    if ($focused.Current.IsPassword) { return @{ status = 'unsupported' } }
    $focusedId = [string]::Join(',', $focused.GetRuntimeId())
    $element = $focused
    $pattern = $null
    for ($depth = 0; $depth -lt 8 -and $null -ne $element; $depth++) {
        if ($element.Current.ProcessId -ne $request.process -or $element.Current.IsPassword) {
            return @{ status = 'unsupported' }
        }
        $candidatePattern = $null
        if ($element.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$candidatePattern)) {
            $pattern = [System.Windows.Automation.TextPattern]$candidatePattern
            break
        }
        $element = [System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($element)
    }
    if ($null -eq $pattern) { return @{ status = 'unsupported' } }
    $providerId = [string]::Join(',', $element.GetRuntimeId())
    $ranges = @($pattern.GetSelection())
    if ($ranges.Count -ne 1) { return @{ status = 'unsupported' } }
    $selection = $ranges[0]
    $document = $pattern.DocumentRange
    $text = $document.GetText(65535)
    if ($text.Length -gt 65534) { return @{ status = 'too_large' } }
    $startPrefix = $document.Clone()
    $endPrefix = $document.Clone()
    $startPrefix.MoveEndpointByRange([System.Windows.Automation.Text.TextPatternRangeEndpoint]::End,
        $selection, [System.Windows.Automation.Text.TextPatternRangeEndpoint]::Start)
    $endPrefix.MoveEndpointByRange([System.Windows.Automation.Text.TextPatternRangeEndpoint]::End,
        $selection, [System.Windows.Automation.Text.TextPatternRangeEndpoint]::End)
    $beforeStart = $startPrefix.GetText(65535)
    $beforeEnd = $endPrefix.GetText(65535)
    if (-not $text.StartsWith($beforeStart, [StringComparison]::Ordinal) -or
        -not $text.StartsWith($beforeEnd, [StringComparison]::Ordinal) -or
        $beforeStart.Length -gt $beforeEnd.Length -or
        $selection.GetText(65535) -cne $text.Substring($beforeStart.Length, $beforeEnd.Length - $beforeStart.Length)) {
        return @{ status = 'changed' }
    }
    $again = @($pattern.GetSelection())
    $nowFocused = [System.Windows.Automation.AutomationElement]::FocusedElement
    if ($again.Count -ne 1 -or $null -eq $nowFocused -or
        [string]::Join(',', $nowFocused.GetRuntimeId()) -cne $focusedId -or
        $document.GetText(65535) -cne $text -or
        $selection.CompareEndpoints([System.Windows.Automation.Text.TextPatternRangeEndpoint]::Start,
            $again[0], [System.Windows.Automation.Text.TextPatternRangeEndpoint]::Start) -ne 0 -or
        $selection.CompareEndpoints([System.Windows.Automation.Text.TextPatternRangeEndpoint]::End,
            $again[0], [System.Windows.Automation.Text.TextPatternRangeEndpoint]::End) -ne 0) {
        return @{ status = 'changed' }
    }
    return @{ status = 'ok'; text = $text; start = $beforeStart.Length; end = $beforeEnd.Length;
        identity = @([string]$request.process, $focusedId, $providerId) }
}

[Console]::WriteLine('{"ready":true}')
while ($null -ne ($line = [Console]::ReadLine())) {
    try {
        $request = $line | ConvertFrom-Json
        $response = Read-FocusedText $request
    } catch {
        # Exceptions may include provider details; never export their text.
        $response = @{ status = 'unavailable' }
    }
    [Console]::WriteLine(($response | ConvertTo-Json -Compress -Depth 4))
}
