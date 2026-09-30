# P1-018 early-exit bookkeeping correction

The original Windows PlayGodot run failed after a clean Godot exit because final bookkeeping received only one second, despite unused time in the existing eight-second cleanup budget. The reviewed two-file correction is now applied and passes 98 host controls, pinned Ruff, and four focused official-engine Windows rendered cases. A new remote Windows run remains required; this packet does not declare the CI failure closed.

Only these canonical files were written by runtime:

| File | SHA-256 |
| --- | --- |
| `automation/playgodot/src/cannonball_playgodot/launcher.py` | `a8ef90facf80600e58729cf74dc72c1878b7d97606b4ba0301a355745f530aef` |
| `automation/playgodot/tests/test_launcher.py` | `ececed27efd3c2e0330c5afa93596b0e96c9e0bf7654c8bf2394a99ebe4b8dd0` |

The final drain/bookkeeping deadline is `started + SHUTDOWN_TIMEOUT_SECONDS`. Early native exit leaves unused graceful/fallback reservations available within that same absolute eight-second deadline. The 5/1/1 native quit/terminate/kill limits, one-second session close limit, token/capability handling, ordinary connection close, fallback rejection, original exceptions, cancellation and repeated-stop result remain unchanged. Existing test ASTs are identical after removing the single newly added parametrized test. No RPC timeout, gameplay, C#, source asset or renderer setting was changed.

Lead separately updated `addons/playgodot/PROTOCOL.md` under its own recorded scope. The earlier obsolete one-second final-phase wording is retained in the original source snapshots. Runtime did not write that third path.

## Original standard CI evidence

Run `34709448118` is a pull-request run advertising head `568252ce674997d9d20a6959a557c7922e2fbe91`; all three runners actually checked out merge `edd29de73b0013953c29b324d749e948a7a128e4`. Fifteen retained relevant source files are byte-equal between the head and actual merge (`merge-binding02.json`).

| Platform | Actual result | Original API ZIP SHA-256 |
| --- | --- | --- |
| Windows, job103595382030 | 175 passed, 1 failed; 305.42s | `b84fb311e9c6aa0d2cddd0330d9540466b9b36b33d8aa951d7eb51f46e5c201d` |
| macOS, job103595381958 | 176 passed; 163.63s | `6566b91c97ad9da62494fba67427737dd03d084f0ff5367cc249aa869a7d5df9` |
| Linux, job103595382011 | 176 passed; 298.78s | `e2d57a75640b33ba8ccc8478a7a51e940a541153ec4f0a7c84d9d08e6f324444` |

These counts include host tests, not only rendered cases. All three original API ZIPs are retained with every one of their 321 members hash/CRC checked. The 54 retained native shutdown observations report exit0, EOF, no fallback and no shutdown diagnostics; some filenames are reused by tests, so this is not a per-launch total. The three intentional null-Callable connection-failure stderr lines are retained with their actual negative fixture results, separate from owned-process logs. No repeated-signal, leaked-object or crash error appeared in the inspected ordinary native logs.

The sole Windows failure is `test_endurance_sedan_inspection_and_selection_controls`, at async-context teardown. Its 25 functional observations, three actual F5 files and all four completed vehicle generations precede the failure. Native PID7488 acknowledged quit and exited0 in1.760842s. The retained observation starts writing at2.796074s, 1.034996s after its pre-bookkeeping snapshot: approximately35ms beyond the local one-second reservation, with over5s still available under the absolute cap. The observation is explicitly not an owner-success record; the job traceback records the owner failure.

The remote Windows renderer was ANGLE/D3D11 Microsoft Basic Render Driver. Mac used ANGLE Metal Apple Paravirtual device; Linux used llvmpipe. The approximately1.035s bookkeeping interval is measured; disk, antivirus, thread scheduling and GPU causes are not individually instrumented or asserted.

## Preserved schedule controls

`schedule03.py` drives the real Python event loop and bookkeeping worker with an isolated fake child; it launches no engine. The matched delays come from the Windows record. Original and candidate sources and all four outcomes remain separate.

| Case | Owner result | Actual elapsed |
| --- | --- | --- |
| Old code, matched early exit and1.034996s bookkeeping | Failure: bookkeeping timeout | 2.789633s |
| Candidate, identical schedule | Pass | 2.798670s |
| Candidate, early exit plus5.25s bookkeeping | Pass using unused reservation | 7.023662s |
| Candidate, work exceeding absolute deadline | Failure; late worker cannot change verdict | 8.012989s |

The last failed observation wakes about13ms after its eight-second deadline because of event-loop scheduling. The deadline itself is unchanged, and the success predicate rejects elapsed time above8s. It is not a successful overrun or increased acceptance bound. Late worker completion and repeated stop calls preserve each original result.

## Current focused integration

`integration07/application.json` binds the before/candidate bytes and exact two-file diff. `integration07/host08/` contains the 98-test canonical execution; `lint08/` contains Ruff; `native08/` contains the four current ordinary rendered cases. Tools were uv0.9.24 with the frozen lock, Python3.13.11, Ruff0.15.21 and official Godot4.7.1 `a13da4feb`.

The four native cases test ordinary close/reconnection and shutdown authorization, pending input/wait cleanup with and without response consumption, and the full sedan inspection/selection/F5 test. All four pass in25.93s on NVIDIA RTX3080Ti Compatibility. All four processes exit0 with EOF and clean logs; both resource cases release their one pending wait and held input. Their observations require the successful test/context return for owner acceptance. Local sedan records bind25 stages, four same-frame generations, three exact persisted clocks and seed20260714 under unchanged0.01s clock/0.25m stationary bounds.

The native command completed and rehashed all494 bound inputs unchanged at `2026-09-12T19:03:24.874145Z`. Subsequent lead M0 work regenerated the two Debug DLLs and updated PROTOCOL.md. `review10.json` records their tested and later hashes separately. The owned Python files and all other491 inputs remain exact. No original DLL-currentness claim is made after the lead rebuild. The four focused native PIDs are gone; the GPU lane was released.

Installed source34 GLB remains `f9a30e7b19ea799c526ce2b1788e646af3a8e4f2aa3b7e910340004b99bc8417`. These are runtime/automation checks, not final source35 art, physical assembly, package, performance or human acceptance. No local software-renderer reproduction is claimed.

## Frozen records and failures

`readback07.json` SHA `f6e588b5bc94ee808b9129a1e016bfe20dceee5b5e1faa7fb3e5e62c2806db37` contains the complete remote numeric and artifact readback. `review10.json` SHA `57a3308a75c562cfd0efdf6c473b1b59aac6062498ef7cf599944a227994b378` contains current focused integration results and exact post-run changes. `inventory13.json` inventories the complete retention packet, including original workflow ZIPs, source snapshots, native images and logs, commands, rejected controls and host fixtures. Its explicit omissions list hashes every driver shader-cache payload beneath the one declared isolated native08 profile path. No logs, commands, native images or negative results are omitted. The first full inventory11 retained these cache bytes, which ordinary non-extended Windows path enumeration had missed; its incorrect no-cache prose in HANDOFF11 is superseded here. Both earlier records remain immutable.

The missing-golden-fixture host attempt, reader06's mistaken all-logs-clean assumption, and finalizer09's rejection after the later root rebuild are preserved alongside their corrected outputs. None is omitted or represented as a passing test. Root owns full-front-door results, retention promotion, commits and the required new standard platform run.

The final inventory uses extended Windows paths for every read and discovers files beyond the usual260-character boundary. This corrects evidence-retention scope only; it changes no test, timeout, rendering result or canonical file.
