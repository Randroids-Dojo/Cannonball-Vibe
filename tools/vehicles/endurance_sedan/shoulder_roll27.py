"""Proposed pre-cut shoulder math only. No bpy, IO, scene mutation or field setter.

Original design revision: blend the forward upper cross-section into a 75mm
rise, near-quarter-round roll ending at 0.90*width on the unchanged deck.
This removes the inherited 16/17mm raised shoulder shelf. It is not an
accepted source/fit/visual recipe. The caller supplies the exact original
section function returning ((x,dx,d2x),(z,dz,d2z)).
"""
import math

SOURCE_Y_START=1.90
SOURCE_Y_FULL=2.17
OUTER_T=5.
DECK_T=7.
DECK_X_FRACTION=.90
RISE_M=.075

def smooth(t):
    t=max(0.,min(1.,t));return t*t*t*(10.-15.*t+6.*t*t)

def controls(old_section,y,width,deck):
    # The left-hand source tangent/curvature at t=5 is the retained side
    # boundary. Geometric G2 is intended; parameter speed need not match.
    def left_boundary(values):
        slopes=[b-a for a,b in zip(values,values[1:])]
        tangents=[slopes[0]]+[0. if a*b<=0 else 2.*a*b/(a+b) for a,b in zip(slopes,slopes[1:])]+[slopes[-1]]
        p0,p1=values[4:6];m0,m1=tangents[4:6]
        c2=-3.*p0-2.*m0+3.*p1-m1;c3=2.*p0+m0-2.*p1+m1
        return p1,m1,2.*c2+6.*c3
    x=left_boundary([0.,.72*width,.91*width,.982*width,width,.996*width,.94*width,.80*width,0.])
    z=left_boundary([.135,.135,.20,.39,.67,deck-.075,deck+.016,deck+.017,deck])
    original=old_section(OUTER_T,y,width,deck)
    assert max(abs(original[k][j]-axis[j]) for k,axis in enumerate((x,z)) for j in (0,1))<1e-12
    # Exact endpoint comes from the locked nine-point source definition.
    p0=(.996*width,deck-RISE_M)
    speed=math.hypot(x[1],z[1]);tx=x[1]/speed;tz=z[1]/speed
    curvature=(x[1]*z[2]-z[1]*x[2])/(speed**3)
    p5=(DECK_X_FRACTION*width,deck)
    run=p0[0]-p5[0];rise=p5[1]-p0[1]
    assert run>0 and rise>0
    # Classical quarter-ellipse cubic endpoint speeds, with the quintic
    # second controls constrained to the actual start curvature and zero
    # terminal curvature. These are physical run/rise derived lengths.
    k=4.*(math.sqrt(2.)-1.)/3.
    d0=3.*k*rise;d1=3.*k*run
    p1=(p0[0]+d0*tx/5.,p0[1]+d0*tz/5.)
    p2=(2.*p1[0]-p0[0]-curvature*d0*d0*tz/20.,
        2.*p1[1]-p0[1]+curvature*d0*d0*tx/20.)
    p4=(p5[0]+d1/5.,p5[1]);p3=(2.*p4[0]-p5[0],p5[1])
    return (p0,p1,p2,p3,p4,p5)

def bezier(points,s):
    n=len(points)-1
    return tuple(sum(math.comb(n,i)*s**i*(1.-s)**(n-i)*p[axis] for i,p in enumerate(points)) for axis in (0,1))

def proposed_section(old_section,t,y,width,deck):
    old=old_section(t,y,width,deck)
    if t<=OUTER_T or y<=SOURCE_Y_START:return old
    blend=smooth((y-SOURCE_Y_START)/(SOURCE_Y_FULL-SOURCE_Y_START))
    if t<DECK_T:
        points=controls(old_section,y,width,deck);span=DECK_T-OUTER_T;s=(t-OUTER_T)/span
        d1=tuple(tuple(5.*(b[k]-a[k]) for k in (0,1)) for a,b in zip(points,points[1:]))
        d2=tuple(tuple(4.*(b[k]-a[k]) for k in (0,1)) for a,b in zip(d1,d1[1:]))
        p=bezier(points,s);v=bezier(d1,s);a=bezier(d2,s)
        new=((p[0],v[0]/span,a[0]/span**2),(p[1],v[1]/span,a[1]/span**2))
    else:
        # The inner top is at the existing deck; its sampling moves within
        # that surface. Centerline and deck extrema remain unchanged.
        factor=DECK_X_FRACTION/.80
        new=(tuple(factor*x for x in old[0]),(deck,0.,0.))
    return tuple(tuple(a+blend*(b-a) for a,b in zip(axis,target)) for axis,target in zip(old,new))


def section(t,y,width,deck,*,legacy_profile,legacy_cubic,interpolate):
    """Exact pure construction hook for model.lower_body.

    Preserve the former model.monotone_curve position evaluation outside the
    original tiny fairing, including exact centerline zeros. Derivatives are
    used only for new shape construction/targets.
    """
    def original(t,y,width,deck):
        if y>1.90 and 5.65<t<6.35:
            return legacy_profile(t,y,width,deck)
        coordinates=(
            [0.,.72*width,.91*width,.982*width,width,.996*width,.94*width,.80*width,0.],
            [.135,.135,.20,.39,.67,deck-.075,deck+.016,deck+.017,deck])
        result=[]
        for values in coordinates:
            derivatives=legacy_cubic(values,t)
            result.append((interpolate(t,list(enumerate(values))),derivatives[1],derivatives[2]))
        return tuple(result)
    return proposed_section(original,t,y,width,deck)
