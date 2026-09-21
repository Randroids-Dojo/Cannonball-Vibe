using Cannonball.Core.Simulation.Vehicle;

namespace Cannonball.Core.Tests;

public sealed class VehicleDynamicsStepTests
{
    private static float Limit(double force, double speed, double kii, double dt = 1.0 / 120) =>
        VehicleDynamicsForces.StepLimitedLateralTireForceNewtons(force, speed, kii, dt, 4);

    private static double OriginalForce(double lateral, double longitudinal = 0, double load = 6_000) =>
        VehicleDynamicsForces.LateralTireForceNewtons(lateral, longitudinal, 80_000, 1, load, 1.15, 2_400, 14, 4);

    [Fact]
    public void ExistingNearZeroForceCanIncreaseEnergyButFourSlotStepDoesNot()
    {
        const double speed = 0.01, mass = 2_400, dt = 1.0 / 120;
        var requested = OriginalForce(speed);
        var oldNext = speed + 4 * requested * dt / mass;
        var corrected = Limit(requested, speed, 1 / mass, dt);
        var newNext = speed + 4 * corrected * dt / mass;
        Assert.True(oldNext * oldNext > speed * speed);
        Assert.True(newNext * newNext < speed * speed);
        Assert.True(Math.Abs(corrected) < Math.Abs(requested));
    }

    [Fact]
    public void CoincidentContactsRejectAnUncoupledOneOverKCap()
    {
        const double speed = 0.125, kii = 0.25, dt = 0.125;
        var uncoupledImpulse = -speed / kii;
        var wrongNext = speed + 4 * kii * uncoupledImpulse;
        var safeImpulse = Limit(-10, speed, kii, dt) * dt;
        var safeNext = speed + 4 * kii * safeImpulse;
        Assert.Equal(-3 * speed, wrongNext);
        Assert.True(wrongNext * wrongNext > speed * speed);
        Assert.Equal(0, safeNext);
    }

    [Fact]
    public void CoupledObliqueContactsAndRotatedInertiaNeverInjectTireOnlyEnergy()
    {
        var rotation = Rotation(0.41, -0.63, 0.28);
        var inertia = Multiply(Multiply(rotation, Diagonal(1.0 / 740, 1.0 / 2_900, 1.0 / 3_200)), Transpose(rotation));
        V[] levers = [new(-0.82, -0.58, -1.58), new(0.82, -0.62, -1.58), new(-0.82, -0.60, 1.42), new(0.82, -0.57, 1.42)];
        V[] tangents = [new V(1, 0.11, -0.2).Unit(), new V(1, -0.06, -0.18).Unit(), new V(1, 0.04, 0.06).Unit(), new V(1, -0.02, 0.04).Unit()];
        var k = ContactMatrix(levers, tangents, 1.0 / 2_400, inertia);
        Assert.True(Math.Abs(k[0, 1]) > 0.1 * Math.Sqrt(k[0, 0] * k[1, 1]));
        var exercised = 0;
        foreach (var active in new[] { 1, 2, 3, 4 })
        foreach (var dt in new[] { 1.0 / 60, 1.0 / 120, 1.0 / 240 })
        foreach (var scale in new[] { 0.0001, 0.01, 0.1, 1.0, 30.0 })
        {
            var linear = new V(0.31 * scale, -0.17 * scale, 0.53 * scale);
            var angular = new V(-0.23 * scale, 0.47 * scale, 0.71 * scale);
            var slip = levers.Select((r, i) => (linear + angular.Cross(r)).Dot(tangents[i])).ToArray();
            var impulse = slip.Select((v, i) => i < active ? (double)Limit(OriginalForce(v), v, k[i, i], dt) * dt : 0).ToArray();
            var work = slip.Zip(impulse, (v, p) => v * p).Sum();
            double quadratic = 0;
            for (var i = 0; i < 4; i++)
            for (var j = 0; j < 4; j++) quadratic += impulse[i] * k[i, j] * impulse[j];
            Assert.True(work + 0.5 * quadratic <= 0, $"N={active}, dt={dt}, scale={scale}");
            Assert.Contains(impulse.Take(active), p => p != 0);
            exercised++;
        }
        Assert.Equal(60, exercised);
    }

    [Fact]
    public void TrueComChangesBothSlipAndEffectiveMass()
    {
        var contact = new V(-0.82, -0.7, 1.42);
        var com = new V(0, -0.12, -0.16);
        var tangent = new V(1, 0, 0);
        var angular = new V(0, 0, 0.1);
        var inertia = Diagonal(1.0 / 700, 1.0 / 2_800, 1.0 / 3_100);
        var trueLever = contact - com;
        var oldSlip = angular.Cross(contact).Dot(tangent);
        var trueSlip = angular.Cross(trueLever).Dot(tangent);
        var oldK = EffectiveMass(contact, tangent, 1.0 / 2_400, inertia);
        var trueK = EffectiveMass(trueLever, tangent, 1.0 / 2_400, inertia);
        Assert.Equal(0.07, oldSlip, 12);
        Assert.Equal(0.058, trueSlip, 12);
        Assert.NotEqual(oldK, trueK);
        Assert.NotEqual(Limit(OriginalForce(oldSlip), oldSlip, oldK), Limit(OriginalForce(trueSlip), trueSlip, trueK));
    }

    [Fact]
    public void CommonRigidFrameAndTranslationPreserveTheContactProblem()
    {
        var bodyOrigin = new V(3, 7, -5);
        var comOffset = new V(0.04, -0.12, -0.16);
        var contact = new V(2.18, 6.3, -3.58);
        var linear = new V(0.07, -0.04, 0.11);
        var angular = new V(-0.06, 0.08, 0.10);
        var tangent = new V(1, 0.04, -0.11).Unit();
        var inertia = Diagonal(1.0 / 740, 1.0 / 2_900, 1.0 / 3_200);
        var r = contact - (bodyOrigin + comOffset);
        var k = EffectiveMass(r, tangent, 1.0 / 2_400, inertia);
        var v = (linear + angular.Cross(r)).Dot(tangent);
        var rotation = Rotation(-0.33, 0.57, 0.84);
        var translated = new V(-11, 17, 23);
        var newContact = Apply(rotation, contact) + translated;
        var newCom = Apply(rotation, bodyOrigin + comOffset) + translated;
        var newR = newContact - newCom;
        var newT = Apply(rotation, tangent);
        var newInertia = Multiply(Multiply(rotation, inertia), Transpose(rotation));
        var newK = EffectiveMass(newR, newT, 1.0 / 2_400, newInertia);
        var newV = (Apply(rotation, linear) + Apply(rotation, angular).Cross(newR)).Dot(newT);
        Assert.Equal(k, newK, 12);
        Assert.Equal(v, newV, 12);
        Assert.Equal(Limit(OriginalForce(v), v, k), Limit(OriginalForce(newV), newV, newK));
    }

    [Fact]
    public void ExistingNativeCastIsExactWhenBelowTheStepCap()
    {
        foreach (var lateral in new[] { -5.0, -0.25, 0.25, 5.0 })
        {
            var force = OriginalForce(lateral, 30);
            var actual = Limit(force, lateral, 1.0 / 2_400);
            Assert.Equal((float)force, actual);
        }
        Assert.Equal((float)-0.1, Limit(-0.1, 1, 0.25));
    }

    [Fact]
    public void Float32SubmissionNeverRoundsAcrossTheComputedCap()
    {
        var midpointAboveOne = 1.0 + 3.0 / (1 << 25);
        Assert.True((double)(float)midpointAboveOne > midpointAboveOne);
        var actual = Limit(-4, midpointAboveOne, 0.25, 1);
        Assert.Equal(-1f, actual);
        Assert.True(Math.Abs((double)actual) <= midpointAboveOne);
    }

    [Fact]
    public void SignsZeroLoadAndTimestepScalingArePreserved()
    {
        Assert.Equal(-4f, Limit(-100, 0.5, 0.25, 0.125));
        Assert.Equal(4f, Limit(100, -0.5, 0.25, 0.125));
        Assert.Equal(-2f, Limit(-100, 0.5, 0.25, 0.25));
        Assert.Equal(0, Limit(-100, 0, 0.25));
        Assert.Equal(0, Limit(0, 1, 0.25));
        Assert.Equal(0, Limit(OriginalForce(1, load: 0), 1, 0.25));
    }

    [Fact]
    public void InvalidArgumentsAndAssistingForcesFailClosed()
    {
        foreach (var invalid in new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity })
        {
            Assert.Throws<ArgumentOutOfRangeException>(() => Limit(invalid, 1, 0.25));
            Assert.Throws<ArgumentOutOfRangeException>(() => Limit(-1, invalid, 0.25));
            Assert.Throws<ArgumentOutOfRangeException>(() => Limit(-1, 1, invalid));
            Assert.Throws<ArgumentOutOfRangeException>(() => Limit(-1, 1, 0.25, invalid));
        }
        foreach (var nonpositive in new[] { 0.0, -1.0 })
        {
            Assert.Throws<ArgumentOutOfRangeException>(() => Limit(-1, 1, nonpositive));
            Assert.Throws<ArgumentOutOfRangeException>(() => Limit(-1, 1, 0.25, nonpositive));
        }
        Assert.Throws<ArgumentOutOfRangeException>(() => Limit(double.MaxValue, -1, 0.25));
        Assert.Throws<ArgumentOutOfRangeException>(() => VehicleDynamicsForces.StepLimitedLateralTireForceNewtons(-1, 1, 0.25, 0.1, 0));
        Assert.Throws<ArgumentException>(() => Limit(1, 1, 0.25));
        Assert.Throws<ArgumentException>(() => Limit(-1, -1, 0.25));
    }

    private static double EffectiveMass(V r, V t, double inverseMass, double[,] inverseInertia)
    {
        var moment = r.Cross(t);
        return inverseMass * t.Dot(t) + moment.Dot(Apply(inverseInertia, moment));
    }

    private static double[,] ContactMatrix(V[] r, V[] t, double inverseMass, double[,] inverseInertia)
    {
        var k = new double[4, 4];
        for (var i = 0; i < 4; i++)
        for (var j = 0; j < 4; j++)
            k[i, j] = inverseMass * t[i].Dot(t[j]) + r[i].Cross(t[i]).Dot(Apply(inverseInertia, r[j].Cross(t[j])));
        return k;
    }

    private static double[,] Diagonal(double x, double y, double z) => new[,] { { x, 0, 0 }, { 0, y, 0 }, { 0, 0, z } };
    private static V Apply(double[,] a, V v) => new(a[0, 0] * v.X + a[0, 1] * v.Y + a[0, 2] * v.Z,
        a[1, 0] * v.X + a[1, 1] * v.Y + a[1, 2] * v.Z, a[2, 0] * v.X + a[2, 1] * v.Y + a[2, 2] * v.Z);
    private static double[,] Transpose(double[,] a)
    {
        var result = new double[3, 3];
        for (var i = 0; i < 3; i++) for (var j = 0; j < 3; j++) result[i, j] = a[j, i];
        return result;
    }
    private static double[,] Multiply(double[,] a, double[,] b)
    {
        var result = new double[3, 3];
        for (var i = 0; i < 3; i++) for (var j = 0; j < 3; j++) for (var k = 0; k < 3; k++) result[i, j] += a[i, k] * b[k, j];
        return result;
    }
    private static double[,] Rotation(double x, double y, double z)
    {
        var rx = new[,] { { 1.0, 0, 0 }, { 0, Math.Cos(x), -Math.Sin(x) }, { 0, Math.Sin(x), Math.Cos(x) } };
        var ry = new[,] { { Math.Cos(y), 0, Math.Sin(y) }, { 0, 1.0, 0 }, { -Math.Sin(y), 0, Math.Cos(y) } };
        var rz = new[,] { { Math.Cos(z), -Math.Sin(z), 0 }, { Math.Sin(z), Math.Cos(z), 0 }, { 0, 0, 1.0 } };
        return Multiply(rz, Multiply(ry, rx));
    }
    private readonly record struct V(double X, double Y, double Z)
    {
        public static V operator +(V a, V b) => new(a.X + b.X, a.Y + b.Y, a.Z + b.Z);
        public static V operator -(V a, V b) => new(a.X - b.X, a.Y - b.Y, a.Z - b.Z);
        public double Dot(V b) => X * b.X + Y * b.Y + Z * b.Z;
        public V Cross(V b) => new(Y * b.Z - Z * b.Y, Z * b.X - X * b.Z, X * b.Y - Y * b.X);
        public V Unit() { var length = Math.Sqrt(Dot(this)); return new(X / length, Y / length, Z / length); }
    }
}
