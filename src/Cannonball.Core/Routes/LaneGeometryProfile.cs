namespace Cannonball.Core.Routes;

public sealed record LaneGeometryLane(
    string Id,
    int Index,
    double CenterMeters,
    double WidthMeters,
    LaneRole Role,
    LaneManeuver AllowedManeuvers);

public sealed record LaneGeometrySample(
    double DistanceMeters,
    double LaneLeftMeters,
    double LaneRightMeters,
    double PavedLeftMeters,
    double PavedRightMeters,
    IReadOnlyList<LaneGeometryLane> Lanes)
{
    public double LaneWidthMeters => LaneRightMeters - LaneLeftMeters;

    public double PavedWidthMeters => PavedRightMeters - PavedLeftMeters;
}

public static class LaneGeometryProfile
{
    public const double DefaultTransitionLengthMeters = 120;

    public static LaneGeometrySample Evaluate(
        RouteEdge edge,
        double distanceMeters,
        double transitionLengthMeters = DefaultTransitionLengthMeters)
    {
        ArgumentNullException.ThrowIfNull(edge);
        if (!double.IsFinite(distanceMeters) || distanceMeters < 0 ||
            distanceMeters > edge.LengthMeters)
        {
            throw new ArgumentOutOfRangeException(nameof(distanceMeters));
        }
        if (!double.IsFinite(transitionLengthMeters) || transitionLengthMeters < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(transitionLengthMeters));
        }

        var layouts = BuildAlignedLayouts(edge);
        for (var index = 1; index < layouts.Count; index++)
        {
            var boundary = layouts[index].Section.StartMeters;
            var availableBefore = boundary - layouts[index - 1].Section.StartMeters;
            var availableAfter = layouts[index].Section.EndMeters - boundary;
            var halfTransition = Math.Min(
                transitionLengthMeters / 2,
                Math.Min(availableBefore, availableAfter) / 2);
            if (halfTransition <= 0 ||
                distanceMeters < boundary - halfTransition ||
                distanceMeters > boundary + halfTransition)
            {
                continue;
            }
            var factor = SmoothStep(
                (distanceMeters - (boundary - halfTransition)) / (2 * halfTransition));
            return Interpolate(layouts[index - 1], layouts[index], distanceMeters, factor);
        }

        var layout = layouts.Last(candidate =>
            distanceMeters + 1e-9 >= candidate.Section.StartMeters);
        return ToSample(layout, distanceMeters);
    }

    private static IReadOnlyList<SectionLayout> BuildAlignedLayouts(RouteEdge edge)
    {
        var sections = edge.GetEffectiveLaneSections()
            .OrderBy(section => section.StartMeters)
            .ToArray();
        var result = new List<SectionLayout>(sections.Length);
        foreach (var section in sections)
        {
            var raw = BuildCenteredLayout(section);
            if (result.Count == 0)
            {
                result.Add(raw);
                continue;
            }
            var previous = result[^1];
            var common = raw.Lanes.Keys.Intersect(previous.Lanes.Keys, StringComparer.Ordinal)
                .ToArray();
            var offset = common.Length == 0
                ? 0
                : common.Average(id =>
                    previous.Lanes[id].CenterMeters - raw.Lanes[id].CenterMeters);
            result.Add(raw with
            {
                Lanes = raw.Lanes.ToDictionary(
                    entry => entry.Key,
                    entry => entry.Value with
                    {
                        CenterMeters = entry.Value.CenterMeters + offset,
                    },
                    StringComparer.Ordinal),
            });
        }
        return result;
    }

    private static SectionLayout BuildCenteredLayout(LaneSection section)
    {
        var ordered = section.Lanes.OrderBy(lane => lane.Index).ToArray();
        var cursor = -ordered.Sum(lane => lane.WidthMeters) / 2.0;
        var lanes = new Dictionary<string, LaneGeometryLane>(StringComparer.Ordinal);
        foreach (var lane in ordered)
        {
            lanes.Add(
                lane.Id,
                new LaneGeometryLane(
                    lane.Id,
                    lane.Index,
                    cursor + lane.WidthMeters / 2.0,
                    lane.WidthMeters,
                    lane.Role,
                    lane.AllowedManeuvers));
            cursor += lane.WidthMeters;
        }
        return new SectionLayout(section, lanes);
    }

    private static LaneGeometrySample Interpolate(
        SectionLayout before,
        SectionLayout after,
        double distanceMeters,
        double factor)
    {
        var beforeBounds = GetLaneBounds(before.Lanes.Values);
        var afterBounds = GetLaneBounds(after.Lanes.Values);
        var lanes = new List<LaneGeometryLane>();
        foreach (var id in before.Lanes.Keys.Union(after.Lanes.Keys, StringComparer.Ordinal))
        {
            var hasBefore = before.Lanes.TryGetValue(id, out var beforeLane);
            var hasAfter = after.Lanes.TryGetValue(id, out var afterLane);
            var source = hasBefore ? beforeLane! : afterLane!;
            var startCenter = hasBefore
                ? beforeLane!.CenterMeters
                : ClosestEdge(beforeBounds, afterLane!.CenterMeters);
            var endCenter = hasAfter
                ? afterLane!.CenterMeters
                : ClosestEdge(afterBounds, beforeLane!.CenterMeters);
            lanes.Add(source with
            {
                Index = hasAfter ? afterLane!.Index : beforeLane!.Index,
                CenterMeters = Lerp(startCenter, endCenter, factor),
                WidthMeters = Lerp(
                    hasBefore ? beforeLane!.WidthMeters : 0,
                    hasAfter ? afterLane!.WidthMeters : 0,
                    factor),
                Role = hasAfter ? afterLane!.Role : beforeLane!.Role,
                AllowedManeuvers = hasAfter
                    ? afterLane!.AllowedManeuvers
                    : beforeLane!.AllowedManeuvers,
            });
        }
        lanes.Sort((left, right) => left.CenterMeters.CompareTo(right.CenterMeters));
        var bounds = GetLaneBounds(lanes);
        var leftShoulder = Lerp(
            before.Section.LeftShoulder.WidthMeters,
            after.Section.LeftShoulder.WidthMeters,
            factor);
        var rightShoulder = Lerp(
            before.Section.RightShoulder.WidthMeters,
            after.Section.RightShoulder.WidthMeters,
            factor);
        return new LaneGeometrySample(
            distanceMeters,
            bounds.Left,
            bounds.Right,
            bounds.Left - leftShoulder,
            bounds.Right + rightShoulder,
            lanes);
    }

    private static LaneGeometrySample ToSample(SectionLayout layout, double distanceMeters)
    {
        var lanes = layout.Lanes.Values.OrderBy(lane => lane.CenterMeters).ToArray();
        var bounds = GetLaneBounds(lanes);
        return new LaneGeometrySample(
            distanceMeters,
            bounds.Left,
            bounds.Right,
            bounds.Left - layout.Section.LeftShoulder.WidthMeters,
            bounds.Right + layout.Section.RightShoulder.WidthMeters,
            lanes);
    }

    private static (double Left, double Right) GetLaneBounds(
        IEnumerable<LaneGeometryLane> lanes)
    {
        var active = lanes.Where(lane => lane.WidthMeters > 1e-9).ToArray();
        if (active.Length == 0)
        {
            return (0, 0);
        }
        return (
            active.Min(lane => lane.CenterMeters - lane.WidthMeters / 2),
            active.Max(lane => lane.CenterMeters + lane.WidthMeters / 2));
    }

    private static double ClosestEdge((double Left, double Right) bounds, double target) =>
        Math.Abs(target - bounds.Left) <= Math.Abs(target - bounds.Right)
            ? bounds.Left
            : bounds.Right;

    private static double SmoothStep(double value)
    {
        var clamped = Math.Clamp(value, 0, 1);
        return clamped * clamped * (3 - 2 * clamped);
    }

    private static double Lerp(double from, double to, double factor) =>
        from + (to - from) * factor;

    private sealed record SectionLayout(
        LaneSection Section,
        IReadOnlyDictionary<string, LaneGeometryLane> Lanes);
}
