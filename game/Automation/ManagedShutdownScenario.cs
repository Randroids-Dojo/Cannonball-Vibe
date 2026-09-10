using System.Runtime.CompilerServices;
using Godot;

namespace Cannonball.Game.Automation;

/// <summary>Exercises wrappers that are already queued for finalization at quit.</summary>
public static class ManagedShutdownScenario
{
    private static readonly ManualResetEventSlim FinalizerEntered = new(false);
    private static WeakReference<StandardMaterial3D>[]? _finalizationReferences;

    public static void Prepare()
    {
        QueueFinalizerBacklog();
        GC.Collect();
        if (!FinalizerEntered.Wait(TimeSpan.FromSeconds(2)))
        {
            throw new InvalidOperationException("Shutdown probe did not enter its finalizer backlog.");
        }
        var references = QueueResourceWrappers();
        GC.Collect();
        var inaccessible = references.Count(reference => !reference.TryGetTarget(out _));
        GD.Print($"CANNONBALL_SHUTDOWN_PROBE_QUEUED wrappers={references.Length} inaccessible={inaccessible} pending={GC.GetGCMemoryInfo().FinalizationPendingCount}");
        if (inaccessible != references.Length)
        {
            throw new InvalidOperationException("Shutdown probe did not queue every resource wrapper.");
        }
    }

    public static void VerifyDrained()
    {
        var references = _finalizationReferences
            ?? throw new InvalidOperationException("Shutdown probe was not prepared.");
        var finalized = references.Count(reference =>
            !reference.TryGetTarget(out var resource) || resource.NativeInstance == IntPtr.Zero);
        if (finalized != references.Length)
        {
            throw new InvalidOperationException($"Shutdown left {references.Length - finalized} resource finalizers pending.");
        }
        GD.Print($"CANNONBALL_SHUTDOWN_PROBE_OK wrappers={references.Length} finalized={finalized}");
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void QueueFinalizerBacklog() => _ = new FinalizerBacklog();

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference<StandardMaterial3D>[] QueueResourceWrappers()
    {
        var references = new WeakReference<StandardMaterial3D>[32];
        _finalizationReferences = new WeakReference<StandardMaterial3D>[references.Length];
        for (var index = 0; index < references.Length; index++)
        {
            var resource = new StandardMaterial3D();
            references[index] = new WeakReference<StandardMaterial3D>(resource);
            _finalizationReferences[index] = new WeakReference<StandardMaterial3D>(resource, trackResurrection: true);
        }
        return references;
    }

    private sealed class FinalizerBacklog
    {
        ~FinalizerBacklog()
        {
            FinalizerEntered.Set();
            Thread.Sleep(1500);
        }
    }
}
