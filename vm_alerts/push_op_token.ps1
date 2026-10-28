# Run on the GROKBOTS host (as Administrator). Copies the host's machine env var OP_SERVICE_ACCOUNT_TOKEN into the
# eugene-alerts VM as /etc/eugene-alerts/op.env (root:root 600) over SSH stdin. Never printed, never written on the host.
param([string]$Ip = ((Get-VMNetworkAdapter -VMName eugene-alerts).IPAddresses | ? { $_ -match '^\d+\.' } | select -First 1))
$t = [Environment]::GetEnvironmentVariable('OP_SERVICE_ACCOUNT_TOKEN','Machine'); if (-not $t) { throw 'OP_SERVICE_ACCOUNT_TOKEN not set on host' }
$ssh = 'C:\GrokBots\tools\OpenSSH-Win64\ssh.exe'; $k = 'C:\GrokBots\eugene-alerts-vm\ssh'
("OP_SERVICE_ACCOUNT_TOKEN=" + $t + "`n") | & $ssh -i "$k\id_ed25519" -o UserKnownHostsFile="$k\known_hosts" -o BatchMode=yes "alerts@$Ip" "sudo install -m 600 -o root -g root /dev/stdin /etc/eugene-alerts/op.env && echo token-installed"
Remove-Variable t
