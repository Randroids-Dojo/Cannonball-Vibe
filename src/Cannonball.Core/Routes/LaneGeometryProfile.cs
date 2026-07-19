namespace Cannonball.Core.Routes;

public sealed record LaneGeometryLane(
    string Id,
    int Index,
    double CenterMeters,
    double WidthMeters,
    LaneRole Role,
    LaneManeuver AllowedManeuvers,
    bool IsTransitioning = false);

public sealed record LaneGeometryTransition(
    double BoundaryMeters,
    double StartMeters,
    double EndMeters,
    double LateralOffsetMeters);

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
    public const double MinimumRuralTransitionLengthMeters = 60.96;

    private const double MetersPerFoot = 0.3048;
    private const double MilesPerHourPerMeterPerSecond = 2.2369362920544;
    private const double HighSpeedTransitionThresholdMilesPerHour = 45;

    public static LaneGeometrySample Evaluate(
        RouteEdge edge,
        double distanceMeters)
    {
        ArgumentNullException.ThrowIfNull(edge);
        if (!double.IsFinite(distanceMeters) || distanceMeters < 0 ||
            distanceMeters > edge.LengthMeters)
        {
            throw new ArgumentOutOfRangeException(nameof(distanceMeters));
        }
        var layouts = BuildAlignedLayouts(edge);
        var transitions = BuildTransitions(edge, layouts);
        for (var index = 1; index < layouts.Count; index++)
        {
            var transition = transitions[index - 1];
            if (transition.EndMeters <= transition.StartMeters ||
                distanceMeters < transition.StartMeters ||
                distanceMeters > transition.EndMeters)
            {
                continue;
            }
            var factor = TransitionProgress(
                (distanceMeters - transition.StartMeters) /
                (transition.EndMeters - transition.StartMeters));
            return Interpolate(layouts[index - 1], layouts[index], distanceMeters, factor);
        }

        var layout = layouts.Last(candidate =>
            distanceMeters + 1e-9 >= candidate.Section.StartMeters);
        return ToSample(layout, distanceMeters);
    }

    public static double GetRecommendedTransitionLengthMeters(RouteEdge edge)
    {
        ArgumentNullException.ThrowIfNull(edge);
        var layouts = BuildAlignedLayouts(edge);
        return Enumerable.Range(1, layouts.Count - 1)
            .Select(index => GetRecommendedTransitionLengthMeters(
                edge,
                layouts[index - 1],
                layouts[index]))
            .DefaultIfEmpty(0)
            .Max();
    }

    public static IReadOnlyList<LaneGeometryTransition> GetTransitions(RouteEdge edge)
    {
        ArgumentNullException.ThrowIfNull(edge);
        var layouts = BuildAlignedLayouts(edge);
        return BuildTransitions(edge, layouts);
    }

    private static IReadOnlyList<LaneGeometryTransition> BuildTransitions(
        RouteEdge edge,
        IReadOnlyList<SectionLayout> layouts)
    {
        var result = new List<LaneGeometryTransition>(Math.Max(0, layouts.Count - 1));
        for (var index = 1; index < layouts.Count; index++)
        {
            var before = layouts[index - 1];
            var after = layouts[index];
            var boundary = after.Section.StartMeters;
            var transitionLength = GetRecommendedTransitionLengthMeters(edge, before, after);
            var halfTransition = transitionLength / 2;
            var availableBefore = boundary - before.Section.StartMeters;
            var availableAfter = after.Section.EndMeters - boundary;
            if (availableBefore + 1e-9 < halfTransition ||
                availableAfter + 1e-9 < halfTransition)
            {
                throw new InvalidDataException(
                    $"Lane transition at {boundary:F3} meters on edge '{edge.Id}' needs " +
                    $"{transitionLength:F3} meters but its adjacent lane sections do not " +
                    "provide enough taper distance.");
            }
            result.Add(new LaneGeometryTransition(
                boundary,
                boundary - halfTransition,
                boundary + halfTransition,
                GetLateralOffsetMeters(before, after)));
        }
        return result;
    }

    private static double GetRecommendedTransitionLengthMeters(
        RouteEdge edge,
        SectionLayout before,
        SectionLayout after)
    {
        var lateralOffsetMeters = GetLateralOffsetMeters(before, after);
        if (lateralOffsetMeters <= 1e-9)
        {
            return 0;
        }

        var speedMilesPerHour = edge.SpeedLimitMetersPerSecond *
            MilesPerHourPerMeterPerSecond;
        var lateralOffsetFeet = lateralOffsetMeters / MetersPerFoot;
        var transitionLengthFeet = speedMilesPerHour >=
            HighSpeedTransitionThresholdMilesPerHour
            ? lateralOffsetFeet * speedMilesPerHour
            : lateralOffsetFeet * speedMilesPerHour * speedMilesPerHour / 60;
        return Math.Max(
            MinimumRuralTransitionLengthMeters,
            transitionLengthFeet * MetersPerFoot);
    }

    private static double GetLateralOffsetMeters(SectionLayout before, SectionLayout after)
    {
        var beforeBounds = GetLaneBounds(before.Lanes.Values);
        var afterBounds = GetLaneBounds(after.Lanes.Values);
        var maximum = Math.Max(
            Math.Abs(afterBounds.Left - beforeBounds.Left),
            Math.Abs(afterBounds.Right - beforeBounds.Right));
        var beforeSeparators = GetSeparatorOffsets(before.Lanes.Values);
        var afterSeparators = GetSeparatorOffsets(after.Lanes.Values);
        foreach (var key in beforeSeparators.Keys.Intersect(
                     afterSeparators.Keys,
                     StringComparer.Ordinal))
        {
            maximum = Math.Max(
                maximum,
                Math.Abs(afterSeparators[key] - beforeSeparators[key]));
        }
        return maximum;
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
            ValidateTransitionTopology(previous, raw);
            var common = raw.Lanes.Keys.Intersect(previous.Lanes.Keys, StringComparer.Ordinal)
                .ToArray();
            var throughAnchors = common.Where(id =>
                    raw.Lanes[id].Role == LaneRole.General &&
                    previous.Lanes[id].Role == LaneRole.General)
                .ToArray();
            var anchors = throughAnchors.Length > 0 ? throughAnchors : common;
            var offset = anchors.Length == 0
                ? 0
                : anchors.Average(id =>
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

    private static void ValidateTransitionTopology(SectionLayout before, SectionLayout after)
    {
        var beforeOrder = before.Lanes.Values.OrderBy(lane => lane.Index).ToArray();
        var afterOrder = after.Lanes.Values.OrderBy(lane => lane.Index).ToArray();
        var common = before.Lanes.Keys.Intersect(after.Lanes.Keys, StringComparer.Ordinal)
            .ToHashSet(StringComparer.Ordinal);
        var beforeCommon = beforeOrder.Where(lane => common.Contains(lane.Id))
            .Select(lane => lane.Id)
            .ToArray();
        var afterCommon = afterOrder.Where(lane => common.Contains(lane.Id))
            .Select(lane => lane.Id)
            .ToArray();
        if (!beforeCommon.SequenceEqual(afterCommon, StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                $"Lane sections '{before.Section.Id}' and '{after.Section.Id}' reorder " +
                "persistent lanes without an explicit lateral transition.");
        }
        if (common.Count == 0)
        {
            throw new InvalidDataException(
                $"Lane sections '{before.Section.Id}' and '{after.Section.Id}' have no " +
                "persistent lane identity for a deterministic transition.");
        }

        var beforeCommonIndexes = beforeOrder
            .Where(lane => common.Contains(lane.Id))
            .Select(lane => lane.Index)
            .ToArray();
        var afterCommonIndexes = afterOrder
            .Where(lane => common.Contains(lane.Id))
            .Select(lane => lane.Index)
            .ToArray();
        if (beforeOrder.Any(lane => !common.Contains(lane.Id) &&
                lane.Index > beforeCommonIndexes.Min() &&
                lane.Index < beforeCommonIndexes.Max()) ||
            afterOrder.Any(lane => !common.Contains(lane.Id) &&
                lane.Index > afterCommonIndexes.Min() &&
                lane.Index < afterCommonIndexes.Max()))
        {
            throw new InvalidDataException(
                $"Lane sections '{before.Section.Id}' and '{after.Section.Id}' add or " +
                "remove an interior lane while preserving a lane outside it.");
        }
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
                IsTransitioning = factor > 1e-9 && factor < 1 - 1e-9 &&
                    (Math.Abs(startCenter - endCenter) > 1e-9 ||
                        Math.Abs(
                            (hasBefore ? beforeLane!.WidthMeters : 0) -
                            (hasAfter ? afterLane!.WidthMeters : 0)) > 1e-9),
            });
        }
        lanes.Sort((left, right) => left.CenterMeters.CompareTo(right.CenterMeters));
        ValidateLaneTiling(before, after, lanes);
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

    private static Dictionary<string, double> GetSeparatorOffsets(
        IEnumerable<LaneGeometryLane> source)
    {
        var lanes = source.OrderBy(lane => lane.CenterMeters).ToArray();
        var result = new Dictionary<string, double>(StringComparer.Ordinal);
        for (var index = 0; index < lanes.Length - 1; index++)
        {
            var left = lanes[index];
            var right = lanes[index + 1];
            result[$"{left.Id}|{right.Id}"] =
                (left.CenterMeters + left.WidthMeters / 2 +
                    right.CenterMeters - right.WidthMeters / 2) / 2;
        }
        return result;
    }

    private static void ValidateLaneTiling(
        SectionLayout before,
        SectionLayout after,
        IReadOnlyList<LaneGeometryLane> lanes)
    {
        var active = lanes.Where(lane => lane.WidthMeters > 1e-9).ToArray();
        for (var index = 0; index < active.Length - 1; index++)
        {
            var gap = active[index + 1].CenterMeters - active[index + 1].WidthMeters / 2 -
                (active[index].CenterMeters + active[index].WidthMeters / 2);
            if (Math.Abs(gap) > 1e-6)
            {
                throw new InvalidDataException(
                    $"Lane transition between '{before.Section.Id}' and " +
                    $"'{after.Section.Id}' creates a {gap:F6}-meter gap or overlap.");
            }
        }
    }

    private static double TransitionProgress(double value) => Math.Clamp(value, 0, 1);

    private static double Lerp(double from, double to, double factor) =>
        from + (to - from) * factor;

    private sealed record SectionLayout(
        LaneSection Section,
        IReadOnlyDictionary<string, LaneGeometryLane> Lanes);
}
