# FlatBuffers C# large-root verifier audit

Date: 2026-07-17  
Task: P1-001  
Package: `Google.FlatBuffers` 25.2.10

## Finding

The representative schema-4 corridor root is approximately 246 KB. The
official C# verifier rejects it after converting an absolute vtable position to
`Int16`. The FlatBuffers wire format stores the signed table-to-vtable distance
as 32 bits, so a valid table located after byte 32,767 can trigger the failure.
The same narrowing remains in the verifier source at upstream tag v25.12.19.

Disabling writer vtable deduplication does not resolve the issue because the
failing value is the absolute vtable position, not only the table-to-vtable
distance. The writer therefore remains standard FlatBuffers.

## Resolution

Generated C# verification calls are normalized by `scripts/generate-schemas.sh`
to use `FlatBufferVerifier`. The local verifier preserves the package's
structural checks, limits, alignment checks, string terminator checks, and
generated schema callbacks. Its intentional behavioral difference is retaining
32-bit absolute positions during vtable lookup.

Small and large roots use the same structural verifier. Regression tests cover
a valid schema-4 root whose nested node vtable is located after byte 32,767,
plus rejection of corrupt root, nested-string, and optional-field offsets.
Runtime semantic validation remains unchanged and follows structural
verification.

## Revisit condition

Remove the compatibility verifier only after the pinned NuGet runtime includes
an upstream fix and the representative schema-4 root plus corruption tests pass
through the upstream verifier.

References:

- [Google.FlatBuffers NuGet package](https://www.nuget.org/packages/Google.FlatBuffers)
- [Google FlatBuffers repository](https://github.com/google/flatbuffers)
