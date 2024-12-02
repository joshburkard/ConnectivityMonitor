#region get current path of the started script file
    switch ( $ExecutionContext.Host.Name ) {
        "ConsoleHost" { Write-Verbose "Runbook is executed from PowerShell Console"; if ( [boolean]$MyInvocation.ScriptName ) { if ( ( $MyInvocation.ScriptName ).EndsWith( ".psm1" ) ) { $CurrentFile = [System.IO.FileInfo]$Script:MyInvocation.ScriptName } else { $CurrentFile = [System.IO.FileInfo]$MyInvocation.ScriptName } } elseif ( [boolean]$MyInvocation.MyCommand ) { if ( [boolean]$MyInvocation.MyCommand.Source ) { if ( ( $MyInvocation.MyCommand.Source ).EndsWith( ".psm1" ) ) { $CurrentFile = [System.IO.FileInfo]$Script:MyInvocation.MyCommand.Source } else { $CurrentFile = [System.IO.FileInfo]$MyInvocation.MyCommand.Source } } else { $CurrentFile = [System.IO.FileInfo]$MyInvocation.MyCommand.Path } } }
        "Visual Studio Code Host" { Write-Verbose 'Runbook is executed from Visual Studio Code'; If ( [boolean]( $psEditor.GetEditorContext().CurrentFile.Path ) ) { Write-Verbose "c"; $CurrentFile = [System.IO.FileInfo]$psEditor.GetEditorContext().CurrentFile.Path } else { if ( ( [System.IO.FileInfo]$MyInvocation.ScriptName ).Extension -eq '.psm1' ) { Write-Verbose "d1"; $PSCallStack = Get-PSCallStack; $CurrentFile =[System.IO.FileInfo] @( $PSCallStack | Where-Object { $_.ScriptName -match '.ps1'} )[0].ScriptName } else { Write-Verbose "d2";  $CurrentFile = [System.IO.FileInfo]$MyInvocation.scriptname } } }
        "Windows PowerShell ISE Host" { Write-Verbose 'Runbook is executed from ISE'; Write-Verbose "  CurrentFile"; $CurrentFile = [System.IO.FileInfo]( $psISE.CurrentFile.FullPath ) }
    }

    $CurrentPath = $CurrentFile.Directory.FullName
#endregion get current path of the started script file

$SourcePath = Join-Path -Path $CurrentPath -ChildPath 'custom_components'
$SourcePathParts = $SourcePath.Split('\').Count
$ComponentName = ( Get-ChildItem -Path $SourcePath -Directory ).Name
$DestinationPath = Join-Path -Path $CurrentPath -ChildPath '\all-files'
if ( -not ( Test-Path -Path $DestinationPath ) ) {
    [void]( New-Item -Path $DestinationPath -ItemType Directory )
}
$json = Get-Content -Path ( Join-Path -Path $CurrentPath -ChildPath "\custom_components\${ComponentName}\manifest.json" )  | ConvertFrom-Json
$DestinationFile = Join-Path -Path $DestinationPath -ChildPath "all-files-$( $json.version ).txt"

$files = Get-ChildItem -Path $SourcePath -Recurse -File

$Content = ''
foreach ( $File in $files ) {
    $Content += "# " + ( $File.FullName.Split('\')[ ( $SourcePathParts -1 ).. ( $File.FullName.Split('\').Count -1 ) ] -join '\' ) + [System.Environment]::NewLine + [System.Environment]::NewLine

    $FileContent = Get-Content -Path $File.FullName -Raw
    $Content += $FileContent + [System.Environment]::NewLine + [System.Environment]::NewLine
}

$Content | Out-File -FilePath $DestinationFile -Encoding utf8
