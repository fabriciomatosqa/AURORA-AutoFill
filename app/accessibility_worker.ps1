# Bootstrap only. Compile once during warm-up; all requests run in typed C#.
# The isolated MTA process can be killed if a UI Automation provider hangs.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, WindowsBase, System.Web.Extensions
$references = @(
    [System.Windows.Automation.AutomationElement].Assembly.Location,
    [System.Windows.Automation.Text.TextPatternRangeEndpoint].Assembly.Location,
    [System.Windows.Point].Assembly.Location,
    [System.Web.Script.Serialization.JavaScriptSerializer].Assembly.Location,
    'System.dll'
)
$source = [IO.File]::ReadAllText($env:AURORA_UIA_SOURCE)
Add-Type -TypeDefinition $source -ReferencedAssemblies $references -Language CSharp
[AuroraAccessibilityWorker]::Run()
