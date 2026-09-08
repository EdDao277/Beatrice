# Starts collection only when explicitly executed. Backend owns credentials and pacing.
$ErrorActionPreference = 'Stop'
$collectionEndpoint = 'http://127.0.0.1:8080/api/collection'
try {
    $collectionState = Invoke-RestMethod -Method Post -Uri $collectionEndpoint
    Write-Host 'Collection started. Closing this terminal does not cancel the backend job.'
    while ($collectionState.running) {
        Start-Sleep -Seconds 5
        $collectionState = Invoke-RestMethod -Uri $collectionEndpoint
        Write-Host $collectionState.message
    }
    if ($null -eq $collectionState.report) { throw $collectionState.message }
    $collectionState.report | Format-List
    if ($collectionState.report.status -eq 'BUDGET_REACHED') {
        Write-Host 'Match budget reached. Run this command again later to continue.'
    }
} catch {
    Write-Error 'Collection could not finish. Ensure the updated backend is running with the local profile; inspect GET /api/collection for status. No retry was started automatically.'
    exit 1
}
