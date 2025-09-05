# PowerShell script to set up email environment variables for BRACU Lost and Found Portal
# Run this script in PowerShell as Administrator or in your user session

Write-Host "Setting up email environment variables for BRACU Lost and Found Portal..." -ForegroundColor Green

# Set environment variables for the current session
$env:MAIL_USERNAME = "braculostandfound6@gmail.com"
$env:MAIL_PASSWORD = "onrwqfkyeemrevsi"
$env:MAIL_SERVER = "smtp.gmail.com"
$env:MAIL_PORT = "587"
$env:MAIL_USE_TLS = "true"
$env:MAIL_DEFAULT_SENDER = "BRACU Lost and Found Portal <braculostandfound6@gmail.com>"

Write-Host "Environment variables set for current session:" -ForegroundColor Yellow
Write-Host "MAIL_USERNAME: $env:MAIL_USERNAME" -ForegroundColor Cyan
Write-Host "MAIL_PASSWORD: [HIDDEN]" -ForegroundColor Cyan
Write-Host "MAIL_SERVER: $env:MAIL_SERVER" -ForegroundColor Cyan
Write-Host "MAIL_PORT: $env:MAIL_PORT" -ForegroundColor Cyan
Write-Host "MAIL_USE_TLS: $env:MAIL_USE_TLS" -ForegroundColor Cyan
Write-Host "MAIL_DEFAULT_SENDER: $env:MAIL_DEFAULT_SENDER" -ForegroundColor Cyan

Write-Host "`nTo make these permanent, run the following commands:" -ForegroundColor Yellow
Write-Host "[System.Environment]::SetEnvironmentVariable('MAIL_USERNAME', 'braculostandfound6@gmail.com', 'User')" -ForegroundColor White
Write-Host "[System.Environment]::SetEnvironmentVariable('MAIL_PASSWORD', 'onrwqfkyeemrevsi', 'User')" -ForegroundColor White
Write-Host "[System.Environment]::SetEnvironmentVariable('MAIL_SERVER', 'smtp.gmail.com', 'User')" -ForegroundColor White
Write-Host "[System.Environment]::SetEnvironmentVariable('MAIL_PORT', '587', 'User')" -ForegroundColor White
Write-Host "[System.Environment]::SetEnvironmentVariable('MAIL_USE_TLS', 'true', 'User')" -ForegroundColor White
Write-Host "[System.Environment]::SetEnvironmentVariable('MAIL_DEFAULT_SENDER', 'BRACU Lost and Found Portal <braculostandfound6@gmail.com>', 'User')" -ForegroundColor White

Write-Host "`nEmail configuration complete! You can now run your Flask application." -ForegroundColor Green

