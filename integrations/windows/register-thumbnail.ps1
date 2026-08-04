param([Parameter(Mandatory=$true)][string]$DllPath)
$resolved = (Resolve-Path -LiteralPath $DllPath).Path
$clsid = '{A11A6D5E-8D61-4AE5-8D44-64C66F7E6B4A}'
$thumbnail = '{E357FCCD-A995-4576-B01F-234630154E96}'
$previewClsid = '{C747A1CC-95B3-49F0-A066-2D4E3DF98AA1}'
$preview = '{8895B1C6-B41F-4C1C-A562-0D564250836F}'
$root = 'HKCU:\Software\Classes'
New-Item -Force "$root\CLSID\$clsid\InprocServer32" | Out-Null
Set-Item -LiteralPath "$root\CLSID\$clsid\InprocServer32" -Value $resolved
New-ItemProperty -Force "$root\CLSID\$clsid\InprocServer32" -Name ThreadingModel -Value Both | Out-Null
New-Item -Force "$root\.wimf\shellex\$thumbnail" | Out-Null
Set-Item -LiteralPath "$root\.wimf\shellex\$thumbnail" -Value $clsid
New-Item -Force "$root\CLSID\$previewClsid\InprocServer32" | Out-Null
Set-Item -LiteralPath "$root\CLSID\$previewClsid\InprocServer32" -Value $resolved
New-ItemProperty -Force "$root\CLSID\$previewClsid\InprocServer32" -Name ThreadingModel -Value Apartment | Out-Null
New-Item -Force "$root\.wimf\shellex\$preview" | Out-Null
Set-Item -LiteralPath "$root\.wimf\shellex\$preview" -Value $previewClsid
Write-Host 'WIMF Explorer thumbnail and preview providers registered for the current user.'
