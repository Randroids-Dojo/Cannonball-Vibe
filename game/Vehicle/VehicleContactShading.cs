using System.Diagnostics;
using System.Security.Cryptography;
using Cannonball.Core.Performance;
using Cannonball.Game.World;
using Godot;

namespace Cannonball.Game.Vehicle;

/// <summary>Contact-driven cosmetic shading; never collision, physical AO, or a ride-height correction.</summary>
public partial class VehicleContactShading : Node3D
{
    public const uint ReceiverLayer = 1u << 16;
    private static readonly string[] Suffixes = ["FL", "FR", "RL", "RR"];
    private static readonly string[] RoadReceivers = ["RoadSurface", "PavedShoulders", "TerrainShoulders"];
    private readonly Decal[] _decals = new Decal[4];
    private readonly RayCast3D[] _rays = new RayCast3D[4];
    private readonly Node3D[] _wheels = new Node3D[4];
    private readonly Node3D[] _steeringPivots = new Node3D[4];
    private readonly bool[] _supported = new bool[4];
    private readonly bool[] _eligible = new bool[4];
    private readonly Vector3[] _points = new Vector3[4];
    private readonly Vector3[] _normals = new Vector3[4];
    private readonly Vector3[] _renderPoints = new Vector3[4];
    private readonly Dictionary<ulong, ReceiverGroup> _receivers = [];
    private readonly List<ulong> _expired = [];
    private CannonballVehicle _vehicle = null!;
    private ImageTexture? _mask;
    private int _maskBytes;
    private string? _maskSha256;
    private long _physicsUpdates;
    private long _renderUpdates;
    private double _physicsMicroseconds;
    private double _renderMicroseconds;
    private long _physicsAllocatedBytes;
    private long _renderAllocatedBytes;
    private int _maximumReceiverGroups;
    private int _totalReceiverGroups;
    private bool _exiting;
    public bool SupportedRenderer { get; private set; }
    public int VisibleDecals { get; private set; }

    public override void _Ready()
    {
        Name = "VehicleContactShading";
        ProcessPhysicsPriority = 1000;
        ProcessPriority = 1000;
        _vehicle = GetParent<CannonballVehicle>();
        SupportedRenderer = RenderingServer.GetCurrentRenderingMethod() == "forward_plus" && DisplayServer.GetName() != "headless";
        if (!SupportedRenderer)
        {
            SetPhysicsProcess(false);
            SetProcess(false);
            return;
        }
        using var image = Image.CreateEmpty(64, 64, false, Image.Format.Rgba8);
        for (var y = 0; y < 64; y++)
        for (var x = 0; x < 64; x++)
        {
            var u = ((x + 0.5f) / 64 - 0.5f) * 2;
            var v = ((y + 0.5f) / 64 - 0.5f) * 2;
            var t = Mathf.Clamp((1 - Mathf.Sqrt(u * u + v * v)) / 0.22f, 0, 1);
            image.SetPixel(x, y, new Color(1, 1, 1, t * t * (3 - 2 * t)));
        }
        image.GenerateMipmaps();
        var maskData = image.GetData();
        _maskBytes = maskData.Length;
        _maskSha256 = Convert.ToHexString(SHA256.HashData(maskData)).ToLowerInvariant();
        _mask = ImageTexture.CreateFromImage(image);
        for (var i = 0; i < 4; i++)
        {
            _rays[i] = _vehicle.SuspensionRay(i);
            _wheels[i] = _vehicle.VisualRig!.ResolveAnchor("Wheel_" + Suffixes[i]);
            _steeringPivots[i] = _vehicle.VisualRig.ResolveAnchor("Suspension_" + Suffixes[i]);
            _decals[i] = new Decal
            {
                Name = "ContactShading_" + Suffixes[i], Size = new Vector3(.34f, .024f, .24f),
                TextureAlbedo = _mask, AlbedoMix = 1, Modulate = new Color(0, 0, 0, .45f), CullMask = ReceiverLayer,
                UpperFade = 0, LowerFade = 0, NormalFade = .5f, DistanceFadeEnabled = true,
                DistanceFadeBegin = 30, DistanceFadeLength = 10, Visible = false,
                TopLevel = true, PhysicsInterpolationMode = PhysicsInterpolationModeEnum.Off,
            };
            AddChild(_decals[i]);
        }
    }

    public override void _PhysicsProcess(double delta)
    {
        if (_exiting || !SupportedRenderer) return;
        using var region = SubsystemProfiler.Measure(SubsystemProfiler.Subsystem.Vehicle);
        var allocated = GC.GetAllocatedBytesForCurrentThread();
        var started = Stopwatch.GetTimestamp();
        if (_physicsUpdates % 120 == 0) PruneReceivers();
        VisibleDecals = 0;
        for (var i = 0; i < 4; i++)
        {
            _supported[i] = _rays[i].IsColliding();
            _eligible[i] = false;
            if (_supported[i])
            {
                _points[i] = _rays[i].GetCollisionPoint();
                _normals[i] = _rays[i].GetCollisionNormal().Normalized();
                if (_rays[i].GetCollider() is Node collider)
                {
                    var id = collider.GetInstanceId();
                    if (!_receivers.TryGetValue(id, out var group)) group = InspectReceiver(collider);
                    _eligible[i] = group.Meshes.Count > 0;
                }
            }
            var decal = _decals[i];
            decal.Visible = _supported[i] && _eligible[i];
            if (!decal.Visible) continue;
            var normal = _normals[i];
            var tangent = Tangent(_steeringPivots[i].GlobalBasis.Z, normal);
            decal.GlobalTransform = new Transform3D(new Basis(normal.Cross(tangent).Normalized(), normal, tangent),
                _points[i] - normal * .002f);
            VisibleDecals++;
        }
        _physicsUpdates++;
        _physicsMicroseconds += Stopwatch.GetElapsedTime(started).TotalMicroseconds;
        _physicsAllocatedBytes += GC.GetAllocatedBytesForCurrentThread() - allocated;
    }

    public override void _Process(double delta)
    {
        if (_exiting || !SupportedRenderer) return;
        using var region = SubsystemProfiler.Measure(SubsystemProfiler.Subsystem.Vehicle);
        var allocated = GC.GetAllocatedBytesForCurrentThread();
        var started = Stopwatch.GetTimestamp();
        // The engine's final interpolation traversal follows _Process. Writing
        // in FramePreDraw would leave its cached displayed transform one frame old.
        for (var i = 0; i < 4; i++)
        {
            if (!_decals[i].Visible) continue;
            var normal = _normals[i];
            var wheel = _wheels[i].GetGlobalTransformInterpolated();
            var point = wheel.Origin - normal * (wheel.Origin - _points[i]).Dot(normal);
            _renderPoints[i] = point;
            var tangent = Tangent(_steeringPivots[i].GetGlobalTransformInterpolated().Basis.Z, normal);
            _decals[i].GlobalTransform = new Transform3D(new Basis(normal.Cross(tangent).Normalized(), normal, tangent), point - normal * .002f);
        }
        _renderUpdates++;
        _renderMicroseconds += Stopwatch.GetElapsedTime(started).TotalMicroseconds;
        _renderAllocatedBytes += GC.GetAllocatedBytesForCurrentThread() - allocated;
    }

    private ReceiverGroup InspectReceiver(Node collider)
    {
        // Collision can leave and re-enter independently of its persistent
        // visual chunk, before the periodic prune. Release the expired owner
        // before the replacement body claims those same receivers.
        PruneReceivers();
        var group = new ReceiverGroup(collider);
        if (collider.Name == "RoadCollision" && collider.GetParent() is RoadChunk chunk)
        {
            foreach (var name in RoadReceivers)
                if (chunk.GetNodeOrNull<MeshInstance3D>(name) is { } mesh) group.Meshes.Add(mesh);
        }
        else if ((collider.Name.ToString() is "EndurancePad" or "EnduranceBump") &&
            collider.GetParent()?.Name == "EnduranceSedanIntegrationCourse")
        {
            foreach (var child in collider.GetChildren())
                if (child is MeshInstance3D mesh) group.Meshes.Add(mesh);
        }
        if (group.Meshes.Any(mesh => (mesh.Layers & ReceiverLayer) != 0))
            throw new InvalidOperationException("The contact-shading receiver layer is already owned.");
        foreach (var mesh in group.Meshes) mesh.Layers |= ReceiverLayer;
        _receivers.Add(collider.GetInstanceId(), group);
        _totalReceiverGroups++;
        _maximumReceiverGroups = Math.Max(_maximumReceiverGroups, _receivers.Count);
        return group;
    }

    private void PruneReceivers()
    {
        _expired.Clear();
        foreach (var (id, group) in _receivers)
            if (!GodotObject.IsInstanceValid(group.Collider) || group.Collider.IsQueuedForDeletion())
            {
                RestoreLayers(group);
                _expired.Add(id);
            }
        foreach (var id in _expired) _receivers.Remove(id);
    }

    private static void RestoreLayers(ReceiverGroup group)
    {
        foreach (var mesh in group.Meshes)
            if (GodotObject.IsInstanceValid(mesh)) mesh.Layers &= ~ReceiverLayer;
    }

    public object CaptureMetrics() => new
    {
        supported_renderer = SupportedRenderer, visible_decals = VisibleDecals,
        physics_updates = _physicsUpdates, physics_total_microseconds = _physicsMicroseconds,
        render_updates = _renderUpdates, render_total_microseconds = _renderMicroseconds,
        physics_allocated_bytes = _physicsAllocatedBytes, render_allocated_bytes = _renderAllocatedBytes,
        active_receiver_groups = _receivers.Count, maximum_receiver_groups = _maximumReceiverGroups,
        total_receiver_groups = _totalReceiverGroups, receiver_layer = ReceiverLayer,
        added_resources = new
        {
            node_3d = 1, decals = SupportedRenderer ? _decals.Length : 0,
            authored_mesh_resources = 0, authored_mesh_triangles = 0, material_resources = 0,
            image_textures = _mask is null ? 0 : 1, mask_size = new[] { 64, 64 },
            mask_format = "RGBA8", mask_mipmaps = true, mask_actual_data_bytes = _maskBytes,
            mask_actual_data_sha256 = _maskSha256,
            renderer_cost_scope = "Decal cluster/atlas/shader work is measured separately; zero authored meshes is not a zero GPU cost claim.",
        },
        scope = "Cosmetic albedo contact shading; source geometry, collision and receiver materials are unchanged.",
    };

    public Counters ReadCounters() => new(_physicsUpdates, _physicsMicroseconds, _physicsAllocatedBytes,
        _renderUpdates, _renderMicroseconds, _renderAllocatedBytes);

    public readonly record struct Counters(long PhysicsUpdates, double PhysicsMicroseconds, long PhysicsAllocatedBytes,
        long RenderUpdates, double RenderMicroseconds, long RenderAllocatedBytes);

    public WheelReadback ReadWheel(int index)
    {
        var displayed = _decals[index].GetGlobalTransformInterpolated().Origin + _normals[index] * .002f;
        var wheel = _wheels[index].GetGlobalTransformInterpolated().Origin;
        return new(_supported[index], _eligible[index], _decals[index].Visible, _points[index], _normals[index],
            _renderPoints[index], displayed, wheel, displayed.DistanceTo(_renderPoints[index]),
            (displayed - wheel).Slide(_normals[index]).Length(), Math.Abs((displayed - _points[index]).Dot(_normals[index])));
    }

    public readonly record struct WheelReadback(bool Supported, bool EligibleReceiver, bool Visible,
        Vector3 RawContact, Vector3 Normal, Vector3 DerivedContact, Vector3 DisplayedContact, Vector3 DisplayedWheelCenter,
        float DerivedDisplayErrorMeters, float WheelTangentialErrorMeters, float ContactPlaneErrorMeters);

    /// <summary>Actual readback for explicit verification; call after native scene interpolation.</summary>
    public object CaptureSnapshot()
    {
        var wheels = new List<object>(4);
        if (SupportedRenderer)
            for (var i = 0; i < 4; i++)
            {
                var state = ReadWheel(i);
                wheels.Add(new
                {
                    name = Suffixes[i], supported = state.Supported, eligible_receiver = state.EligibleReceiver, visible = state.Visible,
                    raw_contact = V(state.RawContact), normal = V(state.Normal), derived_contact = V(state.DerivedContact),
                    displayed_contact = V(state.DisplayedContact), displayed_wheel_center = V(state.DisplayedWheelCenter),
                    derived_display_error_m = state.DerivedDisplayErrorMeters,
                    wheel_tangential_error_m = state.WheelTangentialErrorMeters,
                    contact_plane_error_m = state.ContactPlaneErrorMeters,
                });
            }
        return new { metrics = CaptureMetrics(), wheels, receivers = _receivers.Values.Select(group => new
        {
            collider = GodotObject.IsInstanceValid(group.Collider) ? group.Collider.GetPath().ToString() : "freed",
            meshes = group.Meshes.Where(GodotObject.IsInstanceValid).Select(mesh => new
                { path = mesh.GetPath().ToString(), layers = mesh.Layers }).ToArray(),
        }).ToArray() };
    }

    public override void _ExitTree()
    {
        _exiting = true;
        foreach (var group in _receivers.Values) RestoreLayers(group);
        _receivers.Clear();
        _mask?.Dispose();
        _mask = null;
    }

    private static Vector3 Tangent(Vector3 basisZ, Vector3 normal)
    {
        var tangent = basisZ.Slide(normal).Normalized();
        return tangent.LengthSquared() < .5f ? normal.Cross(Vector3.Right).Normalized() : tangent;
    }
    private static float[] V(Vector3 value) => [value.X, value.Y, value.Z];
    private sealed class ReceiverGroup(Node collider)
    {
        public Node Collider { get; } = collider;
        public List<MeshInstance3D> Meshes { get; } = [];
    }
}
