# Auto-install Python script
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AUTOMATIC PYTHON INSTALLATION" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python already installed
Write-Host "Checking for existing Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Python already installed: $pythonVersion" -ForegroundColor Green
        Write-Host ""
        Write-Host "You can now run: ЗАПУСК.cmd" -ForegroundColor Green
        pause
        exit 0
    }
} catch {}

# Try winget
Write-Host "Trying to install via winget..." -ForegroundColor Yellow
try {
    winget --version | Out-Null
    Write-Host "winget found! Installing Python 3.12..." -ForegroundColor Green
    winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    
    Write-Host ""
    Write-Host "Python installed successfully!" -ForegroundColor Green
    python --version
    Write-Host ""
    Write-Host "Now run: ЗАПУСК.cmd" -ForegroundColor Green
    pause
    exit 0
} catch {
    Write-Host "winget not available, trying direct download..." -ForegroundColor Yellow
}

# Download and install Python
Write-Host "Downloading Python 3.12.0..." -ForegroundColor Yellow
$installerPath = "$env:TEMP\python-3.12.0-amd64.exe"
$url = "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe"

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $installerPath -UseBasicParsing
    
    Write-Host "Download complete! Installing..." -ForegroundColor Green
    Write-Host "This may take a minute..." -ForegroundColor Yellow
    
    # Install with options: Add to PATH, install for all users
    Start-Process -FilePath $installerPath -ArgumentList "/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_test=0" -Wait
    
    # Clean up
    Remove-Item $installerPath -ErrorAction SilentlyContinue
    
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  Python installed successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    
    # Test installation
    python --version
    
    Write-Host ""
    Write-Host "Now you can run: ЗАПУСК.cmd" -ForegroundColor Green
    Write-Host ""
    
} catch {
    Write-Host ""
    Write-Host "Failed to install Python automatically." -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install manually from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host ""
}

pause
