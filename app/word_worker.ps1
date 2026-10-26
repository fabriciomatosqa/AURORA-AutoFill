$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Web.Extensions
$references = @([System.Web.Script.Serialization.JavaScriptSerializer].Assembly.Location, 'System.dll')
$source = [IO.File]::ReadAllText($env:AURORA_UIA_SOURCE)
Add-Type -TypeDefinition $source -ReferencedAssemblies $references -Language CSharp
[AuroraWordWorker]::Run()
