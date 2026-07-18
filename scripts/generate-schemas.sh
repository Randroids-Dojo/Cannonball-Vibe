#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

flatc --csharp --gen-object-api -o src/Cannonball.Core/Content/Generated schemas/route_graph.fbs
flatc --python --gen-object-api -o tools/map_pipeline/src schemas/route_graph.fbs
flatc --csharp --gen-object-api -o src/Cannonball.Core/Content/Generated \
  -I schemas schemas/route_chunk.fbs
flatc --python --gen-object-api -o tools/map_pipeline/src \
  -I schemas schemas/route_chunk.fbs

# NuGet's newest C# runtime is 25.2.10. The generated wire code is compatible;
# normalize only flatc's compile-time version assertion until NuGet catches up.
while IFS= read -r generated_file; do
  perl -pi -e 's/FLATBUFFERS_[0-9_]+/FLATBUFFERS_25_2_10/g' "$generated_file"
done < <(rg -l 'FLATBUFFERS_[0-9_]+' src/Cannonball.Core/Content/Generated)

# The released C# verifier narrows absolute vtable positions to Int16. Route
# roots legitimately exceed that range, so generated verification uses the
# compatible in-repo verifier until the upstream runtime fixes the narrowing.
while IFS= read -r generated_file; do
  perl -pi -e \
    's/Google\.FlatBuffers\.Verifier/Cannonball.Core.Content.FlatBufferVerifier/g' \
    "$generated_file"
done < <(rg -l 'Google\.FlatBuffers\.Verifier' src/Cannonball.Core/Content/Generated)
