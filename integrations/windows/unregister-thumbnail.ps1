$clsid = '{A11A6D5E-8D61-4AE5-8D44-64C66F7E6B4A}'
$thumbnail = '{E357FCCD-A995-4576-B01F-234630154E96}'
$previewClsid = '{C747A1CC-95B3-49F0-A066-2D4E3DF98AA1}'
$preview = '{8895B1C6-B41F-4C1C-A562-0D564250836F}'
$root = 'HKCU:\Software\Classes'
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$root\.wimf\shellex\$thumbnail"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$root\CLSID\$clsid"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$root\.wimf\shellex\$preview"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$root\CLSID\$previewClsid"
Write-Host 'WIMF Explorer thumbnail and preview providers unregistered.'
