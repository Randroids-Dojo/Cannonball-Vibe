using Godot;

namespace Cannonball.Game.World.RoadVisuals;

public enum GuideArrowDirection
{
    UpLeft,
    UpRight,
    Down,
}

public static class HighwaySignGeometry
{
    public const string StandardReference =
        "FHWA MUTCD 11th Edition Chapter 2E; 2024 Standard Highway Signs M1-1/M1-4";
    public const string StandardSource =
        "https://mutcd.fhwa.dot.gov/shsm_interim/index.htm";
    public const string TypographyStatus =
        "godot-default-font-pending-approved-highway-font-rights";

    public static IReadOnlyList<Vector2> RoundedRectangle(
        float width,
        float height,
        float radius,
        int cornerSegments = 4)
    {
        if (width <= 0 || height <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(width));
        }
        if (radius <= 0 || radius > Math.Min(width, height) / 2)
        {
            throw new ArgumentOutOfRangeException(nameof(radius));
        }
        if (cornerSegments < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(cornerSegments));
        }

        var halfWidth = width / 2;
        var halfHeight = height / 2;
        var centers = new[]
        {
            new Vector2(halfWidth - radius, halfHeight - radius),
            new Vector2(halfWidth - radius, -halfHeight + radius),
            new Vector2(-halfWidth + radius, -halfHeight + radius),
            new Vector2(-halfWidth + radius, halfHeight - radius),
        };
        var startDegrees = new[] { 90f, 0f, -90f, -180f };
        var points = new List<Vector2>(4 * (cornerSegments + 1));
        for (var corner = 0; corner < centers.Length; corner++)
        {
            for (var segment = 0; segment <= cornerSegments; segment++)
            {
                var angle = Mathf.DegToRad(
                    startDegrees[corner] - segment * 90f / cornerSegments);
                points.Add(centers[corner] + new Vector2(
                    Mathf.Cos(angle),
                    Mathf.Sin(angle)) * radius);
            }
        }
        return points;
    }

    public static IReadOnlyList<Vector2> InterstateShield()
    {
        var right = new List<Vector2> { new(0, 1.36f) };
        AddQuadratic(right, new(0, 1.36f), new(0.68f, 1.08f), new(1.30f, 1.30f), 6);
        AddQuadratic(right, right[^1], new(1.52f, 0.66f), new(1.39f, 0.06f), 5);
        AddQuadratic(right, right[^1], new(1.10f, -1.03f), new(0, -1.45f), 8);
        return CompleteSymmetricOutline(right);
    }

    public static IReadOnlyList<Vector2> InterstateHeader()
    {
        var right = new List<Vector2> { new(0, 1.25f) };
        AddQuadratic(right, new(0, 1.25f), new(0.62f, 1.02f), new(1.20f, 1.21f), 6);
        right.Add(new Vector2(1.29f, 0.44f));
        right.Add(new Vector2(0, 0.44f));
        var points = new List<Vector2>(right);
        for (var index = right.Count - 2; index > 0; index--)
        {
            points.Add(new Vector2(-right[index].X, right[index].Y));
        }
        return points;
    }

    public static IReadOnlyList<Vector2> UnitedStatesRouteShield()
    {
        var right = new List<Vector2>
        {
            new(0, 0.96f),
            new(0.34f, 1.15f),
            new(0.72f, 1.17f),
            new(1.31f, 0.61f),
            new(1.16f, 0.27f),
            new(1.10f, -0.12f),
            new(1.16f, -0.48f),
            new(1.05f, -0.80f),
            new(0.80f, -1.02f),
            new(0.42f, -1.08f),
            new(0, -1.36f),
        };
        return CompleteSymmetricOutline(right);
    }

    public static IReadOnlyList<Vector2> LaneArrow(GuideArrowDirection direction)
    {
        var points = new[]
        {
            new Vector2(-0.13f, -0.76f),
            new Vector2(0.13f, -0.76f),
            new Vector2(0.13f, 0.18f),
            new Vector2(0.43f, 0.18f),
            new Vector2(0, 0.78f),
            new Vector2(-0.43f, 0.18f),
            new Vector2(-0.13f, 0.18f),
        };
        var degrees = direction switch
        {
            GuideArrowDirection.UpLeft => 45f,
            GuideArrowDirection.UpRight => -45f,
            GuideArrowDirection.Down => 180f,
            _ => throw new ArgumentOutOfRangeException(nameof(direction)),
        };
        var angle = Mathf.DegToRad(degrees);
        var cosine = Mathf.Cos(angle);
        var sine = Mathf.Sin(angle);
        return points
            .Select(point => new Vector2(
                point.X * cosine - point.Y * sine,
                point.X * sine + point.Y * cosine))
            .ToArray();
    }

    private static IReadOnlyList<Vector2> CompleteSymmetricOutline(
        IReadOnlyList<Vector2> right)
    {
        var points = new List<Vector2>(right);
        for (var index = right.Count - 2; index > 0; index--)
        {
            points.Add(new Vector2(-right[index].X, right[index].Y));
        }
        return points;
    }

    private static void AddQuadratic(
        ICollection<Vector2> output,
        Vector2 start,
        Vector2 control,
        Vector2 end,
        int segments)
    {
        for (var segment = 1; segment <= segments; segment++)
        {
            var amount = segment / (float)segments;
            var inverse = 1 - amount;
            output.Add(
                inverse * inverse * start +
                2 * inverse * amount * control +
                amount * amount * end);
        }
    }
}
