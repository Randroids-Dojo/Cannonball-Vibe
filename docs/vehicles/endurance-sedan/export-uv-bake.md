# Evaluated UV bake

On 2026-09-11 the production33 two-export gate rejected different GLB bytes.
Five retained exports, including two with Blender restricted to one thread,
have identical JSON, positions, normals, indices, materials and embedded images.
Only evaluated UV floats differ. The maximum deviation from the reviewed
production33 export is 0.0000019073486328125 UV units. This observation does not
establish a specific internal Blender bug or justify ignoring a failed byte check.

`data/assets/vehicles/endurance-sedan.uv-bake.json` now retains the evaluated UV
coordinates of the reviewed production34 export, whose SHA-256 is
`f9a30e7b19ea799c526ce2b1788e646af3a8e4f2aa3b7e910340004b99bc8417`.
Its source SHA-256 is
`0b4220d5c3f0024054de17a3c36add3388a4f52be2046cc2b837f3bac9edf793`;
the bake SHA-256 is
`c1f17f39d4d49bac0e66fbc2c9964c60e1ab300b9b74470e610eebff250020ee`.
This new bake was explicitly prepared after the revision17 restraint correction.
The preceding production33 failure, original bake and reviewed export remain
retained as history. A production33 bake cannot accept this revised source.
The bake is an offline input and does not change the editable Blender scene,
quantize geometry, coarsen UVs or add a runtime dependency.

The exporter retains a `.pre-uv-bake.glb` diagnostic, then checks the source,
complete GLB JSON/layout and every non-UV byte against the bake. Each referenced
UV accessor must use the declared noninterleaved FLOAT VEC2 layout, have finite
values and avoid every other accessor/image range. Payload lengths and hashes
are checked. A component may differ from its baked value by at most 0.00001 UV
units; a larger change is rejected. Only those UV bytes are replaced, and the
complete resulting GLB must equal the reviewed reference hash. Two complete
export/import/release-pack comparisons remain required after this step.

The bake preserves the original reviewed coordinates instead of choosing a
coarser rounding grid. At the ordinary 0.25 m texture repeat, the accepted bound
corresponds to 2.5 micrometers of surface texture displacement; it is a UV error
bound, not permission to move geometry. Actual measured drift remains separately
recorded in each export inventory.

After editing the source, prepare a new bake explicitly using the exporter:

```powershell
& $sedanBlender --background reports/p1-018/edited.blend --python-exit-code 1 `
  --python tools/vehicles/validate_and_export_endurance_sedan.py -- `
  --source reports/p1-018/edited.blend `
  --output reports/p1-018/edited-export/endurance-sedan.glb `
  --inventory reports/p1-018/edited-export/blender.json `
  --prepare-uv-bake reports/p1-018/edited-export/endurance-sedan.uv-bake.json
```

An existing bake is never overwritten by this operation. Review the source and
export, promote their matching new bake through the owned asset process, and
rerun the asset and affected visual/runtime gates. A stale bake cannot be updated
implicitly by export or validation. Historical failures and the five-export
comparison are retained with P1-018 evidence; human approvals remain open.
