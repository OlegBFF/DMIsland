# Скачивает официальный установщик Python 3.12 с python.org, проверяет подпись Python Software Foundation и ставит его
# для текущего пользователя (без прав администратора, с добавлением в PATH, лаунчером py и tcl/tk для окна лаунчера).
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ver = '3.12.8'
$url = "https://www.python.org/ftp/python/$ver/python-$ver-amd64.exe"
$file = Join-Path $env:TEMP "python-$ver-amd64.exe"
try {
    Write-Host "Скачиваю Python $ver ..."
    Invoke-WebRequest -Uri $url -OutFile $file -UseBasicParsing
    $sig = Get-AuthenticodeSignature $file
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        Remove-Item $file -Force -ErrorAction SilentlyContinue
        Write-Host 'Подпись установщика не совпала с Python Software Foundation — установка отменена.'
        exit 2
    }
    Write-Host 'Подпись проверена. Устанавливаю (1–2 минуты) ...'
    $p = Start-Process -FilePath $file -Wait -PassThru -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=1',
        'Include_launcher=1', 'Include_tcltk=1', 'Include_test=0', 'Include_doc=0', 'Shortcuts=0'
    Remove-Item $file -Force -ErrorAction SilentlyContinue
    exit $p.ExitCode
} catch {
    Write-Host "Не удалось скачать или установить Python: $($_.Exception.Message)"
    exit 1
}
