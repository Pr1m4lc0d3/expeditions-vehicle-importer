
# Diagnosing a vehicle

Almost nothing in this part of the game reports an error, so debugging is
reading artefacts rather than reading messages. Three of them matter, and the
first rule is about keeping them alive.

> **⛔ The evidence is destroyed at every launch**
>    `base\logs\*` and `base\ssl_crash_dump\*` are cleared when the game starts.
> If something fails, **quit and do not relaunch** before looking. Restarting
> to "try it again" wipes the only record of what happened the first time.

> This costs people the same evening twice: once to the bug, once to losing
> the evidence of it.

## The three artefacts

| artefact | what it gives you |
|---|---|
| `base\ssl_crash_dump\ssl_dump_*.json` | `callstack[0]` names the exact script function, class and arguments |
| `base\logs\LegacyLog.txt` | often 0 bytes while running; written on exit |
| `base\CrashScreenshot.jpg` | the screen it died on |

### The dump is the good one

Each dump has `callstack`, `globals` and `objects`. The callstack reads like
this, innermost first:

```
ZonePropertyInventoryStorage.InitZoneInventory()          <- died here
ZonePropertyGenerator.GenerateInventory(slotModifiers=null, createdForZoneId=null)
PopupBaseBuildingUiController.CreateModuleLir(building)
PopupBaseBuildingUiController.CreateListData()
PopupBaseBuildingUiController.Show(withFade=true)
```

That is a complete diagnosis with argument values attached, and it took one
read. Note what it also tells you: nothing in that stack is a vehicle, so a
vehicle theory was wrong no matter how plausible it sounded.

> **ℹ `objects` holds the game's live data**
>    **measured**     A dump carried **74,695 loaded objects**, including every stock module and
> its field values. The game ships its own content compiled, so those values
> appear in no pak and cannot be grepped — the dump is the only readable copy.

> This is how you compare your thing against the game's equivalent when the
> game's equivalent is not a file.

### Zero frames means it was not a script

A dump with an empty callstack is a **native** crash, not a script one, and
`dxdiag.txt` appearing beside it means the game's own reporter fired rather than
Windows. `Get-WinEvent -LogName Application -Id 1000,1001` tells you whether the
OS saw a fault at all; if it did not, the game caught it internally.

## Reading the log

When it does have content, go to the end first. `Failed to load texture` should
be zero, and `Unknown wheels type` should be absent. Most of the rest is noise
the stock game produces too.

> **⚠ A clean log proves nothing on its own**
>    If you are comparing against a mod that works, check it is mentioned in the
> log **at all**. A short launch-and-quit may never have loaded it, and its
> silence then means nothing. Four conclusions were once built on a log whose
> quietness only meant the session was 35 seconds long.

## Discipline that saves time

**Verify the artefact you are actually running.** Hash the installed pak against
your build before reasoning about it. A conclusion drawn from a stale file is
worse than no conclusion, and building a pak to `out.pak.new` and then
installing the old one is an easy mistake to make twice.

**A field differing from a working example is a lead, not a cause.** Name the
mechanism, or say you do not know yet. Two plausible differences in one
investigation turned out to be nothing: a capacity of `0` that the stock module
also had, and missing schema members that the working modules also omitted. The
one that mattered survived because it was the only difference that held across
*every* working example.

**A zero result is a claim.** Run a positive control before citing one. A search
that returns nothing may be a search that was not looking in the right place —
or a tool that silently skipped the folder your answer was in.

**Three failed fixes is an architecture question.** Not a fourth attempt.
