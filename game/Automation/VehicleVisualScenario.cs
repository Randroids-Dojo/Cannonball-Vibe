using Cannonball.Game.Vehicle;
using Godot;

namespace Cannonball.Game.Automation;

public sealed class VehicleVisualScenario
{
    private const int ReviewFramesPerStage = 60;
    private static readonly string[] StageNames =
    [
        "daylight-chase",
        "night-cockpit",
        "braking-pitch",
        "steering-lock",
        "full-suspension-travel",
        "lod-transitions",
        "damage-zones",
        "graybox-equivalence",
    ];

    private readonly CannonballVehicle _vehicle;
    private readonly CannonballVehicle _graybox;
    private readonly DirectionalLight3D _light;
    private readonly Godot.Environment _environment;
    private readonly SpringArm3D _chaseArm;
    private readonly Camera3D _chaseCamera;
    private readonly Camera3D _cockpitCamera;
    private readonly bool _review;
    private readonly HashSet<string> _completedStages = new(StringComparer.Ordinal);
    private int _stageIndex;
    private int _stageFrames;

    public VehicleVisualScenario(
        Node parent,
        CannonballVehicle vehicle,
        Vector3 roadPoint,
        Vector3 roadForward,
        DirectionalLight3D light,
        WorldEnvironment environment,
        bool review)
    {
        _vehicle = vehicle;
        _light = light;
        _environment = environment.Environment ??
            throw new InvalidOperationException("Vehicle visual scenario requires an environment.");
        _review = review;
        _vehicle.PlaceForReview(roadPoint, roadForward);
        _vehicle.AutopilotEnabled = false;
        _chaseArm = _vehicle.GetNode<SpringArm3D>("ChaseCameraArm");
        _chaseArm.SpringLength = 5.4f;
        _chaseArm.Position = new Vector3(0, 1.15f, 1.25f);
        _chaseCamera = _chaseArm.GetNode<Camera3D>("ChaseCamera");
        _cockpitCamera = _vehicle.VisualRig?.CockpitCameraAnchor.GetNode<Camera3D>("CockpitCamera") ??
            throw new InvalidOperationException("Vehicle visual scenario requires the cockpit camera.");
        _graybox = new CannonballVehicle
        {
            Name = "GrayboxEquivalenceVehicle",
            ForceGrayboxVisual = true,
            Freeze = true,
        };
        parent.AddChild(_graybox);
        var right = roadForward.Cross(Vector3.Up).Normalized();
        _graybox.PlaceForReview(roadPoint + right * 3.2f, roadForward);
        _graybox.Visible = false;
        _cockpitCamera.ClearCurrent(enableNext: false);
        _chaseCamera.MakeCurrent();
        _chaseArm.SpringLength = 5.4f;
        _chaseArm.Position = new Vector3(0, 1.15f, 1.25f);
        _chaseArm.RotationDegrees = new Vector3(-8, 0, 0);
    }

    public bool Complete { get; private set; }

    public void Advance()
    {
        if (Complete)
        {
            return;
        }
        var rig = _vehicle.VisualRig ??
            throw new InvalidOperationException("Vehicle visual profile requires the Hero GT rig.");
        ConfigureStage(rig, _stageIndex, _stageFrames);
        _stageFrames++;
        var framesNeeded = _review ? ReviewFramesPerStage : 3;
        if (_stageFrames < framesNeeded)
        {
            return;
        }
        ValidateStage(rig, _stageIndex);
        var stage = StageNames[_stageIndex];
        _completedStages.Add(stage);
        GD.Print(
            $"CANNONBALL_VEHICLE_VISUAL_STAGE_OK stage={stage} " +
            $"index={_stageIndex + 1} of={StageNames.Length}");
        _stageIndex++;
        _stageFrames = 0;
        if (_stageIndex < StageNames.Length)
        {
            return;
        }
        if (_completedStages.Count != StageNames.Length)
        {
            throw new InvalidOperationException("Vehicle visual profile missed a declared stage.");
        }
        Complete = true;
        var snapshot = rig.CaptureSnapshot();
        GD.Print(
            "CANNONBALL_VEHICLE_VISUAL_OK " +
            $"semantic_nodes={snapshot.SemanticNodeCount} lods=3 damage_zones={snapshot.DamageZoneCount} " +
            $"wheelbase_m=2.84 track_m=1.64 graybox_equivalent={_graybox.UsesGrayboxVisual}");
    }

    private void ConfigureStage(VehicleVisualRig rig, int stage, int frame)
    {
        var phase = _review ? frame / (float)Math.Max(ReviewFramesPerStage - 1, 1) : 1.0f;
        _graybox.Visible = false;
        rig.SetDamageHighlight(false);
        rig.SetLod(0);
        _vehicle.Rotation = Vector3.Zero;
        _chaseArm.SpringLength = 5.4f;
        _chaseArm.Position = new Vector3(0, 1.15f, 1.25f);
        _chaseArm.RotationDegrees = new Vector3(-8, 0, 0);
        switch (stage)
        {
            case 0:
                SetLighting(daylight: true);
                rig.ApplyPhysicsState(0, 24, 1.0f / 60.0f, [0.18f, 0.18f, 0.18f, 0.18f]);
                break;
            case 1:
                SetLighting(daylight: false);
                _chaseArm.SpringLength = 0.05f;
                _chaseArm.Position = new Vector3(0, 0.8f, -0.27f);
                _chaseArm.RotationDegrees = Vector3.Zero;
                rig.ApplyPhysicsState(0, 42, 1.0f / 60.0f, [0.16f, 0.16f, 0.16f, 0.16f]);
                break;
            case 2:
                SetLighting(daylight: true);
                _vehicle.Rotation = new Vector3(-Mathf.DegToRad(2.2f) * phase, 0, 0);
                rig.ApplyPhysicsState(0, Mathf.Lerp(52, 8, phase), 1.0f / 60.0f, [0.34f, 0.34f, 0.12f, 0.12f]);
                break;
            case 3:
                rig.ApplyPhysicsState(Mathf.Lerp(-0.38f, 0.38f, phase), 18, 1.0f / 60.0f, [0.2f, 0.2f, 0.18f, 0.18f]);
                break;
            case 4:
                var travel = Mathf.Lerp(0, 0.62f, phase);
                rig.ApplyPhysicsState(0, 0, 1.0f / 60.0f, [travel, 0.62f - travel, travel, 0.62f - travel]);
                break;
            case 5:
                rig.SetLod(Math.Min((int)(phase * 3), 2));
                rig.ApplyPhysicsState(0, 30, 1.0f / 60.0f, [0.18f, 0.18f, 0.18f, 0.18f]);
                break;
            case 6:
                rig.SetDamageHighlight(true);
                rig.ApplyPhysicsState(0, 0, 1.0f / 60.0f, [0.22f, 0.22f, 0.22f, 0.22f]);
                break;
            case 7:
                _graybox.Visible = true;
                rig.ApplyPhysicsState(0, 0, 1.0f / 60.0f, [0.18f, 0.18f, 0.18f, 0.18f]);
                break;
        }
    }

    private void ValidateStage(VehicleVisualRig rig, int stage)
    {
        var snapshot = rig.CaptureSnapshot();
        if (!snapshot.ContractResolved || snapshot.SemanticNodeCount != VehicleVisualRig.RequiredSemanticNodes.Length)
        {
            throw new InvalidOperationException("Hero GT semantic rig did not resolve completely.");
        }
        switch (stage)
        {
            case 3 when Math.Abs(snapshot.SteeringRadians - 0.38f) > 0.001f:
                throw new InvalidOperationException("Steering-lock visual did not reach the declared angle.");
            case 4 when snapshot.MaximumSuspensionTravelMeters < 0.619f:
                throw new InvalidOperationException("Visual suspension did not exercise its full measured travel.");
            case 5 when snapshot.ActiveLod != 2:
                throw new InvalidOperationException("Visual LOD profile did not reach LOD2.");
            case 6 when snapshot.DamageZoneCount != 5:
                throw new InvalidOperationException("Damage-zone visual contract drifted.");
            case 7 when !_graybox.UsesGrayboxVisual || _graybox.VisualRig is not null ||
                _graybox.GetNodeOrNull<CollisionShape3D>("ChassisCollision") is null:
                throw new InvalidOperationException("Graybox fallback changed the authoritative collision contract.");
        }
    }

    private void SetLighting(bool daylight)
    {
        _light.LightColor = daylight ? new Color("fff2d6") : new Color("a9c4ff");
        _light.LightEnergy = daylight ? 1.8f : 1.3f;
        _environment.BackgroundColor = daylight ? new Color("78a7d8") : new Color("060912");
        _environment.AmbientLightColor = daylight ? new Color("dbe8f6") : new Color("425072");
        _environment.AmbientLightEnergy = daylight ? 0.8f : 0.45f;
    }
}
