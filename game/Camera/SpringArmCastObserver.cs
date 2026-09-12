using System.Globalization;
using Godot;

namespace Cannonball.Game.Camera;

/// <summary>
/// Debug automation observation of one completed native spring-arm cast.
/// </summary>
/// <remarks>
/// Godot 4.7.1 SceneTree dispatches INTERNAL_PHYSICS_PROCESS, then
/// PHYSICS_PROCESS consecutively for this same node. SpringArm3D performs its
/// native collision cast in the former. This callback only reads its result;
/// it never changes the request, transforms, collision query or camera.
/// </remarks>
public sealed partial class SpringArmCastObserver : SpringArm3D
{
    private ulong _epoch;
    private ulong _generation;
    private CompletedSpringCast _completed;
    private Godot.Collections.Dictionary? _publishedState;

    public CompletedSpringCast CompletedCast => _completed;
    public ulong ObservationEpoch => _epoch;

    public override void _EnterTree() => InvalidateCompletedCast();

    public override void _ExitTree() => InvalidateCompletedCast();

    public void BindAutomationState(Godot.Collections.Dictionary state)
    {
        _publishedState = state;
        WriteAutomationState(state);
    }

    public void InvalidateCompletedCast()
    {
        _epoch++;
        _completed = new CompletedSpringCast(false, _epoch, _generation, 0, GetInstanceId(), 0, 0);
        if (_publishedState is not null)
        {
            WriteAutomationState(_publishedState);
        }
    }

    public override void _PhysicsProcess(double delta)
    {
        // A direct call from render processing must not manufacture a cast.
        if (!Engine.IsInPhysicsFrame() || !IsInsideTree())
        {
            return;
        }
        if (!IsPhysicsProcessingInternal())
        {
            if (_completed.Ready)
            {
                InvalidateCompletedCast();
            }
            return;
        }
        _completed = new CompletedSpringCast(
            true, _epoch, ++_generation, Engine.GetPhysicsFrames(), GetInstanceId(),
            SpringLength, GetHitLength());
    }

    public void WriteAutomationState(Godot.Collections.Dictionary state)
    {
        var sample = _completed;
        state["spring_cast_ready"] = sample.Ready;
        state["spring_observation_epoch"] = (long)_epoch;
        state["spring_cast_epoch"] = (long)sample.Epoch;
        state["spring_cast_generation"] = (long)sample.Generation;
        state["spring_cast_physics_frame"] = (long)sample.PhysicsFrame;
        state["spring_observation_physics_frame"] = (long)Engine.GetPhysicsFrames();
        state["spring_arm_instance_id"] = GetInstanceId().ToString(CultureInfo.InvariantCulture);
        state["spring_cast_arm_instance_id"] = sample.ArmInstanceId.ToString(CultureInfo.InvariantCulture);
        state["spring_cast_request_m"] = sample.RequestLengthMeters;
        state["spring_cast_hit_m"] = sample.HitLengthMeters;
        state["spring_cast_compression_m"] = sample.CompressionMeters;
    }
}

public readonly record struct CompletedSpringCast(
    bool Ready,
    ulong Epoch,
    ulong Generation,
    ulong PhysicsFrame,
    ulong ArmInstanceId,
    double RequestLengthMeters,
    double HitLengthMeters)
{
    public double CompressionMeters => Math.Max(0, RequestLengthMeters - HitLengthMeters);
}
