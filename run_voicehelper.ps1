$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
python -m pip install -r requirements.txt
python voicehelper.py
