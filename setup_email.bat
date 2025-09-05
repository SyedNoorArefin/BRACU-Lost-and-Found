@echo off
echo Setting up email environment variables for BRACU Lost and Found Portal...
echo.

set MAIL_USERNAME=braculostandfound6@gmail.com
set MAIL_PASSWORD=onrwqfkyeemrevsi
set MAIL_SERVER=smtp.gmail.com
set MAIL_PORT=587
set MAIL_USE_TLS=true
set MAIL_DEFAULT_SENDER=BRACU Lost and Found Portal ^<braculostandfound6@gmail.com^>

echo Environment variables set for current session:
echo MAIL_USERNAME: %MAIL_USERNAME%
echo MAIL_PASSWORD: [HIDDEN]
echo MAIL_SERVER: %MAIL_SERVER%
echo MAIL_PORT: %MAIL_PORT%
echo MAIL_USE_TLS: %MAIL_USE_TLS%
echo MAIL_DEFAULT_SENDER: %MAIL_DEFAULT_SENDER%
echo.
echo Email configuration complete! You can now run your Flask application.
echo.
pause

