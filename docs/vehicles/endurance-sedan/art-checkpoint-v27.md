# P1-018 fresh Blender construction checkpoint v27

The current editable surface prototype is
`reports/p1-018/fresh-construction26-pilot05/fresh05/source.blend`, SHA-256
`db7a04ce82561985c7955adc5e54aaf7d6e568f753e636f44c16a6a658bbbb73`.
Blender 5.1.2 `ec6e62d40fa9` constructed it from an empty scene using the
frozen `snapshot08` Python modules and specification. The build loaded no old
Blender scene. Its 1,102 complete raw mesh fields and modifier states matched
after saving, reopening and exercising the hidden instrument drivers.
It contains 148,820 LOD0 triangles against the unchanged 150,000 ceiling.
Derived LOD1/2 are intentionally absent from this surface prototype.

The [five-part retention index](../../../data/assets/vehicles/endurance-sedan-review/art-checkpoint-v27/index.json)
retains 2,734 new files in 532,230,984 archive bytes: construction inputs,
editable sources, complete local component proofs, actual Blender images,
failed attempts and recoveries, and independent review records. Every archive
was written twice and compared directly byte for byte. Both copies were read
for every member's SHA-256 and CRC. Two unchanged historical payloads are
referenced through the retained v26 inventory. This is review archive
reproducibility, not final shipping GLB reproducibility.

The fresh source incorporates the main radiator field correction, formed
charge-cooler assemblies, 24-vent rotors, six curved cooling pipes and four
static label patches. The pipe packet checks all 6,015 unrelated pairs,
12 complete post-Boolean ports and 696 affected opening pairs. The minimum
reported closed-hood gap to a changed hot pipe is 5.151792 mm. Those component
certificates have their own exact source/correspondence bindings; they do not
approve the whole final source. The fresh05 native control and lighting checks
exercise 109 and 12 states respectively and pass. The first two invocations
failed to write because the lead omitted the new output directory; the same
checks passed after creating it, without a source or validator change.

The new 2048 x 512 static label atlas is generated from the actual native Bfont
cap triangles. Four labels decrease from 1,216 to 48 triangles. Their complete
receiver fit passes; independent matched images show preserved placement and
crisper close text. The PNG is 24,347 bytes; RGBA8 with mipmaps costs
5,592,406 bytes. Existing Bfont provenance and the human rights review remain
applicable. No external font or image was introduced.

A separate nine-part label/receiver prototype exported twice using the pinned
glTF options produces identical 198,156-byte GLBs, SHA-256
`36613e9ef0ff897a2c9d3c4c9459d03bfaf31d5c8628ac1f54c314583144e509`.
An isolated clean official Godot import preserves the embedded PNG, standard
alpha material, four semantic meshes and the exact decoded base RGBA bytes.
The diagnostic hash API initially failed to parse; the retained recovery uses
native HashingContext without changing the asset or import settings. This
small compatibility-renderer import is not a full Forward+ sedan playtest.

The roof lip and creases, broad center fascia, forked upper bumper reflection,
brake edge/caliper finish and lower-LOD appearance remain open. The archives
include rejected roof, fascia and LOD attempts. Newer joined-roof, brake-edge
and protected-LOD proposals are outside this checkpoint until separately
verified. The installed production34 asset and Hero GT are unchanged.

To inspect this checkpoint, extract the five archives into the worktree root,
preserving their relative paths, then open the source above with:

```powershell
& 'C:\Program Files\Blender\blender-5.1.2-windows-x64\blender.exe' `
  'C:\Dev\Cannonball-Vibe-sedan\reports\p1-018\fresh-construction26-pilot05\fresh05\source.blend'
```

Select `RigControls` and edit its custom properties for source inspection.
Reset controls before export. To rebuild into a distinct new output path:

```powershell
& 'C:\Program Files\Blender\blender-5.1.2-windows-x64\blender.exe' `
  --background --factory-startup --python-exit-code 1 `
  --python reports/p1-018/fresh-construction26-pilot05/snapshot08/tools/vehicles/create_endurance_sedan.py `
  -- --output reports/p1-018/checkpoint27-rebuild/source.blend --stage production --surface-preview
```

Use the retained preparation12 input hashes and reopened.json evidence to
identify the exact construction. Rebuilding editable content does not promise
byte-identical .blend serialization. Final shipping exports must still be
built twice and compared, reopened and cleanly imported into the actual game.
Full source QA, chosen LODs, runtime footage, reference performance and all
declared platform evidence remain required. P1-018 stays in progress, with
human visual, rights, driving-feel, calibration and usability gates open.

The full Windows `scripts/check.sh` front door passes all13 steps for the
bound checkpoint working inputs. Its completed doctor, build, test and
official-engine logs are retained in [frontdoor-index.json](../../../data/assets/vehicles/endurance-sedan-review/art-checkpoint-v27/frontdoor-index.json).
This verifies the repository checkpoint; final sedan art and other-platform
evidence remain separate requirements.
