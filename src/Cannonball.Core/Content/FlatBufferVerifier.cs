using Google.FlatBuffers;

namespace Cannonball.Core.Content;

public delegate bool FlatBufferVerifyTableAction(
    FlatBufferVerifier verifier,
    uint tablePosition);

/// <summary>
/// Structurally verifies generated FlatBuffer tables without narrowing absolute
/// vtable positions to 16 bits.
/// </summary>
public sealed class FlatBufferVerifier
{
    private readonly ByteBuffer _buffer;
    private readonly Options _options;
    private int _depth;
    private int _tableCount;

    public FlatBufferVerifier(ByteBuffer buffer, Options? options = null)
    {
        _buffer = buffer ?? throw new ArgumentNullException(nameof(buffer));
        _options = options ?? new Options();
    }

    public bool VerifyBuffer(
        string? identifier,
        bool sizePrefixed,
        FlatBufferVerifyTableAction verifyTable)
    {
        ArgumentNullException.ThrowIfNull(verifyTable);
        _depth = 0;
        _tableCount = 0;
        var start = (uint)_buffer.Position;
        if (sizePrefixed)
        {
            if (!CheckScalar(start, sizeof(uint)))
            {
                return false;
            }
            start += sizeof(uint);
            if (_buffer.GetUint(_buffer.Position) != _buffer.Length - start)
            {
                return false;
            }
        }
        if (identifier is not null && !BufferHasIdentifier(start, identifier))
        {
            return false;
        }
        return TryGetIndirectOffset(start, out var root) && verifyTable(this, root);
    }

    public bool VerifyTableStart(uint tablePosition)
    {
        _depth++;
        _tableCount++;
        if (_depth > _options.maxDepth || _tableCount > _options.maxTables ||
            !TryGetTable(tablePosition, out var table))
        {
            return false;
        }
        return CheckElement(table.VtablePosition, table.VtableBytes) &&
            CheckElement(tablePosition, table.TableBytes);
    }

    public bool VerifyTableEnd(uint tablePosition)
    {
        _ = tablePosition;
        _depth--;
        return true;
    }

    public bool VerifyField(
        uint tablePosition,
        short offsetId,
        ulong elementSize,
        ulong alignment,
        bool required)
    {
        var lookup = GetFieldPosition(tablePosition, offsetId, out var fieldPosition);
        if (lookup != FieldLookup.Found)
        {
            return lookup == FieldLookup.Missing && !required;
        }
        return CheckAlignment(fieldPosition, alignment) &&
            CheckElement(fieldPosition, elementSize);
    }

    public bool VerifyString(uint tablePosition, short offsetId, bool required)
    {
        var lookup = GetFieldPosition(tablePosition, offsetId, out var fieldPosition);
        if (lookup != FieldLookup.Found)
        {
            return lookup == FieldLookup.Missing && !required;
        }
        return TryGetIndirectOffset(fieldPosition, out var stringPosition) &&
            CheckVectorOrString(stringPosition, sizeof(byte), checkTerminator: true);
    }

    public bool VerifyVectorOfData(
        uint tablePosition,
        short offsetId,
        ulong elementSize,
        bool required)
    {
        var lookup = GetFieldPosition(tablePosition, offsetId, out var fieldPosition);
        if (lookup != FieldLookup.Found)
        {
            return lookup == FieldLookup.Missing && !required;
        }
        return TryGetIndirectOffset(fieldPosition, out var vectorPosition) &&
            CheckVectorOrString(vectorPosition, elementSize, checkTerminator: false);
    }

    public bool VerifyVectorOfStrings(uint tablePosition, short offsetId, bool required) =>
        VerifyVectorOfObjects(tablePosition, offsetId, VerifyStringObject, required);

    public bool VerifyVectorOfTables(
        uint tablePosition,
        short offsetId,
        FlatBufferVerifyTableAction verifyTable,
        bool required) =>
        VerifyVectorOfObjects(tablePosition, offsetId, verifyTable, required);

    public bool VerifyTable(
        uint tablePosition,
        short offsetId,
        FlatBufferVerifyTableAction verifyTable,
        bool required)
    {
        var lookup = GetFieldPosition(tablePosition, offsetId, out var fieldPosition);
        if (lookup != FieldLookup.Found)
        {
            return lookup == FieldLookup.Missing && !required;
        }
        return TryGetIndirectOffset(fieldPosition, out var childPosition) &&
            verifyTable(this, childPosition);
    }

    private bool VerifyVectorOfObjects(
        uint tablePosition,
        short offsetId,
        FlatBufferVerifyTableAction verifyObject,
        bool required)
    {
        var lookup = GetFieldPosition(tablePosition, offsetId, out var fieldPosition);
        if (lookup != FieldLookup.Found)
        {
            return lookup == FieldLookup.Missing && !required;
        }
        if (!TryGetIndirectOffset(fieldPosition, out var vectorPosition) ||
            !TryGetVector(
                vectorPosition,
                sizeof(uint),
                out var dataPosition,
                out _,
                out var count))
        {
            return false;
        }
        for (uint index = 0; index < count; index++)
        {
            var elementPosition = (ulong)dataPosition + index * sizeof(uint);
            if (elementPosition > uint.MaxValue ||
                !TryGetIndirectOffset((uint)elementPosition, out var objectPosition) ||
                !verifyObject(this, objectPosition))
            {
                return false;
            }
        }
        return true;
    }

    private bool VerifyStringObject(FlatBufferVerifier verifier, uint stringPosition) =>
        verifier.CheckVectorOrString(stringPosition, sizeof(byte), checkTerminator: true);

    private bool BufferHasIdentifier(uint start, string identifier)
    {
        if (identifier.Length != 4 || !CheckElement((ulong)start + sizeof(uint), 4))
        {
            return false;
        }
        for (var index = 0; index < identifier.Length; index++)
        {
            if (_buffer.Get((int)(start + sizeof(uint) + index)) != (byte)identifier[index])
            {
                return false;
            }
        }
        return true;
    }

    private bool TryGetTable(uint tablePosition, out TableEnvelope table)
    {
        table = default;
        if (!CheckScalar(tablePosition, sizeof(int)))
        {
            return false;
        }
        var vtablePosition = (long)tablePosition - _buffer.GetInt((int)tablePosition);
        if (vtablePosition < 0 || vtablePosition > uint.MaxValue ||
            !CheckElement((ulong)vtablePosition, 2 * sizeof(ushort)))
        {
            return false;
        }
        var vtableBytes = _buffer.GetUshort((int)vtablePosition);
        var tableBytes = _buffer.GetUshort((int)vtablePosition + sizeof(ushort));
        if (vtableBytes < 2 * sizeof(ushort) || vtableBytes % sizeof(ushort) != 0 ||
            tableBytes < sizeof(int))
        {
            return false;
        }
        table = new TableEnvelope((uint)vtablePosition, vtableBytes, tableBytes);
        return true;
    }

    private FieldLookup GetFieldPosition(
        uint tablePosition,
        short offsetId,
        out uint fieldPosition)
    {
        fieldPosition = 0;
        if (offsetId < 2 * sizeof(ushort) ||
            !TryGetTable(tablePosition, out var table))
        {
            return FieldLookup.Invalid;
        }
        if (offsetId + sizeof(ushort) > table.VtableBytes)
        {
            return FieldLookup.Missing;
        }
        var fieldOffset = _buffer.GetUshort((int)table.VtablePosition + offsetId);
        if (fieldOffset == 0)
        {
            return FieldLookup.Missing;
        }
        var absolute = (ulong)tablePosition + fieldOffset;
        if (fieldOffset >= table.TableBytes || absolute > uint.MaxValue ||
            !CheckElement(absolute, 1))
        {
            return FieldLookup.Invalid;
        }
        fieldPosition = (uint)absolute;
        return FieldLookup.Found;
    }

    private bool TryGetIndirectOffset(uint position, out uint target)
    {
        target = 0;
        if (!CheckScalar(position, sizeof(uint)))
        {
            return false;
        }
        var relative = _buffer.GetUint((int)position);
        var absolute = (ulong)position + relative;
        if (relative == 0 || absolute > uint.MaxValue || !CheckElement(absolute, 1))
        {
            return false;
        }
        target = (uint)absolute;
        return true;
    }

    private bool CheckVectorOrString(
        uint position,
        ulong elementSize,
        bool checkTerminator)
    {
        if (!TryGetVector(position, elementSize, out _, out var endPosition, out _))
        {
            return false;
        }
        return !checkTerminator || !_options.stringEndCheck ||
            (CheckElement(endPosition, 1) && _buffer.Get((int)endPosition) == 0);
    }

    private bool TryGetVector(
        uint position,
        ulong elementSize,
        out uint dataPosition,
        out uint endPosition,
        out uint count)
    {
        dataPosition = 0;
        endPosition = 0;
        count = 0;
        if (elementSize == 0 || !CheckScalar(position, sizeof(uint)))
        {
            return false;
        }
        count = _buffer.GetUint((int)position);
        var byteCount = (ulong)count * elementSize;
        var data = (ulong)position + sizeof(uint);
        var end = data + byteCount;
        if (data > uint.MaxValue || end > uint.MaxValue ||
            !CheckElement(data, byteCount))
        {
            return false;
        }
        dataPosition = (uint)data;
        endPosition = (uint)end;
        return true;
    }

    private bool CheckScalar(uint position, ulong size) =>
        CheckAlignment(position, size) && CheckElement(position, size);

    private bool CheckAlignment(ulong position, ulong alignment) =>
        !_options.alignmentCheck || alignment == 0 || (position & (alignment - 1)) == 0;

    private bool CheckElement(ulong position, ulong size) =>
        position <= (ulong)_buffer.Length && size <= (ulong)_buffer.Length - position;

    private readonly record struct TableEnvelope(
        uint VtablePosition,
        ushort VtableBytes,
        ushort TableBytes);

    private enum FieldLookup
    {
        Missing,
        Found,
        Invalid,
    }
}
