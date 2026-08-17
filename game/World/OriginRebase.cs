using Godot;

namespace Cannonball.Game.World;

/// <summary>Moves a node with an origin rebase, as a teleport rather than motion.</summary>
/// <remarks>
/// Interpolation would otherwise smear the node across the shift, because it
/// blends from the pre-shift transform to the post-shift one over the next
/// rendered frame. Every node the rebase moves must reset its interpolation the
/// same way, so the rule lives here rather than in each shifted class.
/// </remarks>
public static class OriginRebase
{
    public static void ShiftForOriginRebase(this Node3D node, Vector3 shift)
    {
        node.Position -= shift;
        node.ResetPhysicsInterpolation();
    }
}
