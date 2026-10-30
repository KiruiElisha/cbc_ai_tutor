# Signs one Windows file with the company's code-signing certificate, held by SSL.com eSigner.
#
# Tauri runs this for every binary it bundles (bundle.windows.signCommand), so the app exe, the
# setup.exe and the .msi are all signed. Windows 11 Smart App Control blocks unsigned installers
# outright, and SmartScreen warns about them; a signed, timestamped file passes both.
#
# The release workflow sets these from secrets and unpacks CodeSignTool into CODESIGNTOOL_DIR:
#   ESIGNER_USERNAME, ESIGNER_PASSWORD, ESIGNER_CREDENTIAL_ID, ESIGNER_TOTP_SECRET
param([Parameter(Mandatory = $true)][string]$File)

$ErrorActionPreference = "Stop"
$tool = Join-Path $env:CODESIGNTOOL_DIR "CodeSignTool.bat"
if (-not (Test-Path $tool)) { throw "CodeSignTool is not in CODESIGNTOOL_DIR ($env:CODESIGNTOOL_DIR)" }

# CodeSignTool resolves its jar and JDK relative to its own folder.
Push-Location $env:CODESIGNTOOL_DIR
try {
    $output = & $tool sign `
        "-username=$env:ESIGNER_USERNAME" `
        "-password=$env:ESIGNER_PASSWORD" `
        "-credential_id=$env:ESIGNER_CREDENTIAL_ID" `
        "-totp_secret=$env:ESIGNER_TOTP_SECRET" `
        "-input_file_path=$File" `
        "-override=true" 2>&1
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
# CodeSignTool can exit 0 after an error, so its output is checked as well.
if ($code -ne 0 -or ($output -match "Error")) {
    throw "Signing $File failed: $output"
}

$signature = Get-AuthenticodeSignature -FilePath $File
if ($signature.Status -ne "Valid") {
    throw "Signed $File, but Windows reads the signature as $($signature.Status)"
}
Write-Host "Signed $File by $($signature.SignerCertificate.Subject)"
