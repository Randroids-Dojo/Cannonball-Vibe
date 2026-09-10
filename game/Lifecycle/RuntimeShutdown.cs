using System.Diagnostics;
using Cannonball.Game.Automation;
using Godot;

namespace Cannonball.Game.Lifecycle;

/// <summary>Drains managed finalizers while the native engine is still alive.</summary>
public sealed class RuntimeShutdown
{
    private Task? _completion;
    private int _exitCode;

    public bool Requested => _completion is not null;

    public Task Request(Node root, Func<Task> stopProducers, int exitCode, bool probe)
    {
        if (exitCode != 0)
        {
            _exitCode = exitCode;
        }
        return _completion ??= RunAsync(root, stopProducers, probe);
    }

    private async Task RunAsync(Node root, Func<Task> stopProducers, bool probe)
    {
        var elapsed = Stopwatch.StartNew();
        var tree = root.GetTree();
        try
        {
            // Some scenarios request quit from a physics callback. Move the
            // shutdown to idle before deactivating the native physics server.
            await root.ToSignal(tree, SceneTree.SignalName.ProcessFrame);
            // This is called only for an actual application quit. Pausing the
            // physics server and disabling every node also stops Always-mode
            // input/automation nodes while asynchronous file reads settle.
            tree.Paused = true;
            StopProcessing(tree.Root);
            await stopProducers().WaitAsync(TimeSpan.FromSeconds(10));
            if (probe)
            {
                ManagedShutdownScenario.Prepare();
            }
            // The engine's shutdown tracker stores short weak references, so it
            // cannot see wrappers whose finalizers were already queued by GC.
            // Two passes include objects released by the first finalizer pass.
            // Wait asynchronously so Godot can service any deferred disposals.
            for (var pass = 0; pass < 2; pass++)
            {
                GC.Collect();
                await Task.Run(GC.WaitForPendingFinalizers).WaitAsync(TimeSpan.FromSeconds(10));
            }
            if (probe)
            {
                ManagedShutdownScenario.VerifyDrained();
            }
            GD.Print($"CANNONBALL_SHUTDOWN_OK drains=2 producers_stopped=true elapsed_ms={elapsed.Elapsed.TotalMilliseconds:0.000}");
        }
        catch (Exception exception)
        {
            _exitCode = 1;
            GD.PushError($"Managed shutdown failed: {exception}");
        }
        tree.Quit(_exitCode);
    }

    private static void StopProcessing(Node node)
    {
        node.ProcessMode = Node.ProcessModeEnum.Disabled;
        node.SetProcessInput(false);
        node.SetProcessUnhandledInput(false);
        node.SetProcessUnhandledKeyInput(false);
        for (var index = 0; index < node.GetChildCount(); index++)
        {
            StopProcessing(node.GetChild(index));
        }
    }
}
