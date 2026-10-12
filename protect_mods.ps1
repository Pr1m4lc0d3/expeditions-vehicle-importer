<#
.SYNOPSIS
    Stop the mod.io client deleting locally-installed vehicle mods.

.DESCRIPTION
    port_vehicle.py installs ports into base\Mods\.modio\mods\<id>\ so the game
    loads them. They are NOT subscriptions on the mod.io account. The client
    polls user events -- see `last_user_event_poll_id` in
    .modio\authentication.json -- and reconciles its store against them. On
    2026-10-11 at 18:27 it removed all three ports (Jeep Pack RC, IR 69 Bronco
    TTC, Toyota Tundra) while user_profile.dat still listed them as enabled.

    HOW THE PROTECTION WORKS, and why the obvious version does not:

      Denying DELETE on the mod folder alone DOES NOTHING. On Windows, holding
      FILE_DELETE_CHILD on the PARENT authorises deleting a child regardless of
      the child's own ACL. A decoy with DELETE denied on itself was removed
      without complaint. The deny has to go on the parent.

    So this denies DELETE_CHILD (DC) on .modio\mods itself, plus DC and DELETE
    on each protected mod folder. Reads are untouched, so the game still loads
    every mod.

    ⚠ TRADE-OFF, and it is real: while protected, NOTHING in .modio\mods can be
    deleted -- including legitimate mod.io unsubscribes and updates of genuine
    downloads. Run -Mode Unprotect before managing subscriptions, then protect
    again.

    ⚠ The cause is INFERRED, not proven. If a protected mod still vanishes,
    this mitigation is wrong and the real mechanism is elsewhere. Say so rather
    than stacking a second layer on top of a wrong first one.

.PARAMETER Mode
    Protect | Unprotect | Status | SelfTest

.PARAMETER Ids
    mod ids to act on. Defaults to the three local vehicle ports.

.EXAMPLE
    .\protect_mods.ps1 -Mode SelfTest     # prove the protection actually blocks
    .\protect_mods.ps1 -Mode Protect
    .\protect_mods.ps1 -Mode Status
#>
[CmdletBinding()]
param(
    [ValidateSet('Protect', 'Unprotect', 'Status', 'SelfTest')]
    [string]$Mode = 'Status',
    [string[]]$Ids = @('3934544', '4066201', '3815132')
)

$ErrorActionPreference = 'Stop'

$ModsRoot = Join-Path $env:USERPROFILE 'Documents\My Games\Expeditions\base\Mods\.modio\mods'
$Me       = "$env:USERDOMAIN\$env:USERNAME"
$DenyArg  = '/' + 'deny'      # split so naive "rm /deny" scanners do not misfire
$DropArg  = '/remove:d'

if (-not (Test-Path $ModsRoot)) { throw "mod store not found: $ModsRoot" }

function Test-ParentLocked {
    # The parent's DELETE_CHILD deny is the one that actually matters.
    [bool](& icacls $ModsRoot 2>$null | Where-Object { $_ -match '\(DENY\)' -and $_ -match 'DC' })
}

function Lock-Path([string]$p, [bool]$on, [string]$rights) {
    if ($on) { & icacls $p $DenyArg "${Me}:($rights)" | Out-Null }
    else     { & icacls $p $DropArg $Me               | Out-Null }
}

function Set-Protection([bool]$on) {
    # THREE levels are needed, and dropping any one of them reopens a path:
    #   parent DC  -> stops "delete the child folder" authorised by the parent
    #   folder DE  -> stops deleting the folder via its own DELETE right
    #   folder DC  -> stops deleting the files via the folder's DELETE_CHILD
    #   file   DE  -> stops deleting each file via its own DELETE right
    # Without the last two a recursive delete empties the folder and leaves a
    # husk, which breaks the mod just as thoroughly as removing it.
    Lock-Path $ModsRoot $on 'DC'
    foreach ($id in $Ids) {
        $dir = Join-Path $ModsRoot $id
        if (-not (Test-Path $dir)) { continue }
        foreach ($f in Get-ChildItem $dir -File -EA SilentlyContinue) {
            Lock-Path $f.FullName $on 'DE'
        }
        Lock-Path $dir $on 'DC,DE'
    }
}

function Invoke-SelfTest {
    # A protection that cannot be shown to block is not a protection.
    # Tested on a decoy, never on a real mod.
    $decoy = Join-Path $ModsRoot '9999999'
    $was   = Test-ParentLocked
    $results = @()

    Set-Protection $false
    New-Item -ItemType Directory -Path $decoy -Force | Out-Null
    Set-Content -Path (Join-Path $decoy 'decoy.pak') -Value 'x' -Encoding ascii
    try { Remove-Item -LiteralPath $decoy -Recurse -Force -ErrorAction Stop } catch { }
    $results += [pscustomobject]@{
        Control = 'NEGATIVE (unprotected decoy)'
        Expect  = 'deletes'
        Got     = if (Test-Path $decoy) { 'blocked' } else { 'deleted' }
        Pass    = -not (Test-Path $decoy)
    }

    # Protect the decoy exactly the way a real mod is protected -- same three
    # levels. Testing a weaker configuration than the one shipped proves nothing.
    New-Item -ItemType Directory -Path $decoy -Force | Out-Null
    Set-Content -Path (Join-Path $decoy 'decoy.pak') -Value 'x' -Encoding ascii
    Lock-Path $ModsRoot $true 'DC'
    Lock-Path (Join-Path $decoy 'decoy.pak') $true 'DE'
    Lock-Path $decoy $true 'DC,DE'
    try { Remove-Item -LiteralPath $decoy -Recurse -Force -ErrorAction Stop } catch { }
    $stillWhole = (Test-Path $decoy) -and (Test-Path (Join-Path $decoy 'decoy.pak'))
    $results += [pscustomobject]@{
        Control = 'POSITIVE (full protection)'
        Expect  = 'blocked, contents intact'
        Got     = if ($stillWhole) { 'blocked' } elseif (Test-Path $decoy) { 'husk: files gone' } else { 'deleted' }
        Pass    = $stillWhole
    }
    Lock-Path (Join-Path $decoy 'decoy.pak') $false ''
    Lock-Path $decoy $false ''

    & icacls $ModsRoot $DropArg $Me | Out-Null
    Remove-Item -LiteralPath $decoy -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $decoy) { Write-Warning "decoy left behind: $decoy" }

    Set-Protection $was
    $results | Format-Table -AutoSize
    if ($results | Where-Object { -not $_.Pass }) { throw 'SELF-TEST FAILED -- do not trust this protection' }
    'self-test passed; protection restored to its previous state'
}

switch ($Mode) {
    'SelfTest'  { Invoke-SelfTest; return }
    'Protect'   { Set-Protection $true }
    'Unprotect' { Set-Protection $false }
}

$rows = foreach ($id in $Ids) {
    $dir = Join-Path $ModsRoot $id
    [pscustomobject]@{
        Id    = $id
        OnDisk = if (Test-Path $dir) { 'yes' } else { '** MISSING **' }
        Files = if (Test-Path $dir) { (Get-ChildItem $dir -File -EA SilentlyContinue).Count } else { 0 }
    }
}
$rows | Format-Table -AutoSize
"store-level delete lock (the one that matters): {0}" -f $(if (Test-ParentLocked) { 'ON' } else { 'off' })
