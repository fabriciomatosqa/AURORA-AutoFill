# UI Automation bridge. Requests/responses stay in anonymous pipes.
# Reads focused text and selects verified ranges; never types or edits text.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class AuroraFocusedWindow {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@

function Test-FocusScope($focused, $request) {
    if ($null -eq $focused) { return $false }
    if (-not $request.window) { return $focused.Current.ProcessId -eq $request.process }
    if ([AuroraFocusedWindow]::GetForegroundWindow().ToInt64() -ne [long]$request.window) {
        return $false
    }
    # Teams hosts its editor in a separate WebView process. Prove the focused
    # element belongs to this HWND tree instead of requiring the host's PID.
    $ancestor = $focused
    for ($depth = 0; $depth -lt 40 -and $null -ne $ancestor; $depth++) {
        $handle = [long]$ancestor.Current.NativeWindowHandle
        if ($handle -ne 0 -and ($handle -eq [long]$request.window -or
                                $handle -eq [long]$request.control)) { return $true }
        $ancestor = [System.Windows.Automation.TreeWalker]::RawViewWalker.GetParent($ancestor)
    }
    return $false
}

function Get-PositionRange($document, [string]$text, [int]$offset) {
    $endpoint = [System.Windows.Automation.Text.TextPatternRangeEndpoint]
    $range = $document.Clone()
    if ($offset -eq 0) {
        $range.MoveEndpointByRange($endpoint::End, $document, $endpoint::Start)
    } elseif ($offset -eq $text.Length) {
        $range.MoveEndpointByRange($endpoint::Start, $document, $endpoint::End)
    } else {
        # Find the exact prefix rather than counting UIA Character units:
        # providers differ for emoji, combining marks and paragraph breaks.
        $prefix = $text.Substring(0, $offset)
        $range = $document.FindText($prefix, $false, $false)
        if ($null -eq $range -or $range.GetText(65535) -cne $prefix -or
            $range.CompareEndpoints($endpoint::Start, $document, $endpoint::Start) -ne 0) {
            throw 'range unavailable'
        }
        $range.MoveEndpointByRange($endpoint::Start, $range, $endpoint::End)
    }
    return $range
}

function Read-FocusedText($request) {
    $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
    if ($null -eq $focused -or -not (Test-FocusScope $focused $request)) {
        return @{ status = 'changed' }
    }
    if ($focused.Current.IsPassword) { return @{ status = 'unsupported' } }
    $focusedId = [string]::Join(',', $focused.GetRuntimeId())
    $element = $focused
    $pattern = $null
    for ($depth = 0; $depth -lt 8 -and $null -ne $element; $depth++) {
        if ($element.Current.IsPassword) {
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
    $identity = @([string]$focused.Current.ProcessId, $focusedId, $providerId)
    if ($request.action -eq 'select') {
        if ($request.text -cne $text -or
            [string]::Join('|', @($request.identity)) -cne [string]::Join('|', $identity) -or
            $request.selection_start -ne $beforeStart.Length -or
            $request.selection_end -ne $beforeEnd.Length -or
            $request.start -lt 0 -or $request.end -lt $request.start -or
            $request.end -gt $text.Length) { return @{ status = 'changed' } }
        $startRange = Get-PositionRange $document $text $request.start
        $endRange = Get-PositionRange $document $text $request.end
        $endpoint = [System.Windows.Automation.Text.TextPatternRangeEndpoint]
        $startRange.MoveEndpointByRange($endpoint::End, $endRange, $endpoint::Start)
        if ($startRange.GetText(65535) -cne $text.Substring($request.start, $request.end - $request.start)) {
            return @{ status = 'changed' }
        }
        $nowFocused = [System.Windows.Automation.AutomationElement]::FocusedElement
        if (-not (Test-FocusScope $nowFocused $request) -or
            [string]::Join(',', $nowFocused.GetRuntimeId()) -cne $focusedId -or
            $document.GetText(65535) -cne $text) { return @{ status = 'changed' } }
        # TextPatternRange.Select() retorna antes de o Teams/WebView refletir
        # a seleção em GetSelection(). Responder com um ACK explícito evita
        # confundir o estado anterior com uma seleção recusada. A GUI deverá
        # consultar e comprovar o intervalo exato antes de executar Ctrl+V.
        $startRange.Select()
        return @{ status = 'selection_requested'; window = [string]$request.window;
                  control = [string]$request.control; identity = $identity }
    }
    return @{ status = 'ok'; text = $text; start = $beforeStart.Length; end = $beforeEnd.Length;
        identity = $identity; window = [string]$request.window; control = [string]$request.control }
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
