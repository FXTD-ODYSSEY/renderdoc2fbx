set exporter=%APPDATA%\qrenderdoc\extensions
if not exist "%exporter%" mkdir "%exporter%"
xcopy "%~dp0timmyliang\*" "%exporter%" /i /e /Y /C
