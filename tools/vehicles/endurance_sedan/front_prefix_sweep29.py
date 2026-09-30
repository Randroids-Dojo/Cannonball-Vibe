"""Exact first derivatives of the frozen shoulder_roll27 surface.

Pure proposed construction target, no bpy/IO. This authors a normal from the
actual sweep; it does not restore the old averaged native corner field.
Call with the same source (t,y,side) used to create a side vertex, before the
front perimeter bevel. Cap/generated-bevel/Boolean-wall targets stay separate.
"""
import math

class D:
    __slots__=('v','d')
    def __init__(self,value,derivative=0.):self.v=float(value);self.d=float(derivative)
    @staticmethod
    def cast(x):return x if isinstance(x,D) else D(x)
    def __add__(a,b):
        b=D.cast(b);return D(a.v+b.v,a.d+b.d)
    __radd__=__add__
    def __neg__(a):return D(-a.v,-a.d)
    def __sub__(a,b):return a+-D.cast(b)
    def __rsub__(a,b):return D.cast(b)+-a
    def __mul__(a,b):
        b=D.cast(b);return D(a.v*b.v,a.d*b.v+a.v*b.d)
    __rmul__=__mul__
    def __truediv__(a,b):
        b=D.cast(b);return D(a.v/b.v,(a.d*b.v-a.v*b.d)/(b.v*b.v))
    def __rtruediv__(a,b):return D.cast(b)/a
    def __pow__(a,p):return D(a.v**p,p*a.v**(p-1)*a.d)
    def __lt__(a,b):return a.v<D.cast(b).v
    def __le__(a,b):return a.v<=D.cast(b).v
    def __gt__(a,b):return a.v>D.cast(b).v
    def __ge__(a,b):return a.v>=D.cast(b).v

def smooth(x):
    x=max(0.,min(1.,x));return x*x*x*(10.-15.*x+6.*x*x)

def differentiable_interpolate(value,points):
    slopes=[(b[1]-a[1])/(b[0]-a[0]) for a,b in zip(points,points[1:])]
    tangents=[slopes[0]]+[0. if left*right<=0. else 2.*left*right/(left+right) for left,right in zip(slopes,slopes[1:])]+[slopes[-1]]
    for i,((a,av),(b,bv)) in enumerate(zip(points,points[1:])):
        if value<=b:
            t=(value-a)/(b-a)
            # Strict clipping preserves the declared one-sided endpoint jet.
            if t<0.:t=0.
            elif t>1.:t=1.
            return (2*t**3-3*t*t+1)*av+(t**3-2*t*t+t)*(b-a)*tangents[i]+(-2*t**3+3*t*t)*bv+(t**3-t*t)*(b-a)*tangents[i+1]
    return points[-1][1]

def widths(y,interpolate):
    return interpolate(y,[(-2.54,.83),(-2.30,.91),(-1.46,.95),(-.60,.929),(.60,.929),(1.46,.95),(2.08,.919),(2.40,.825)])

def decks(y,interpolate):
    return interpolate(y,[(-2.54,.865),(-2.40,.92),(-1.94,.991),(-1.46,.997),(.74,.99),(1.46,.925),(2.17,.848),(2.40,.823)])

def dual_section(t,y,width,deck,*,legacy_profile,legacy_cubic,interpolate):
    """The same finite construction algebra with an exact forward Y derivative."""
    def old(q):
        if y>1.90 and 5.65<q<6.35:return legacy_profile(q,y,width,deck)
        axes=([0.,.72*width,.91*width,.982*width,width,.996*width,.94*width,.80*width,0.],
              [.135,.135,.20,.39,.67,deck-.075,deck+.016,deck+.017,deck])
        return tuple((interpolate(q,list(enumerate(v))),*legacy_cubic(v,q)[1:]) for v in axes)
    original=old(t)
    if t<=5. or y<=1.90:return original
    weight=smooth((y-1.90)/.27)
    if t<7.:
        def left(values):
            slopes=[b-a for a,b in zip(values,values[1:])]
            tangents=[slopes[0]]+[0. if a*b<=0 else 2.*a*b/(a+b) for a,b in zip(slopes,slopes[1:])]+[slopes[-1]]
            p0,p1=values[4:6];m0,m1=tangents[4:6]
            c2=-3.*p0-2.*m0+3.*p1-m1;c3=2.*p0+m0-2.*p1+m1
            return p1,m1,2.*c2+6.*c3
        x=left([0.,.72*width,.91*width,.982*width,width,.996*width,.94*width,.80*width,0.])
        z=left([.135,.135,.20,.39,.67,deck-.075,deck+.016,deck+.017,deck])
        speed=(x[1]*x[1]+z[1]*z[1])**.5;tx=x[1]/speed;tz=z[1]/speed
        curvature=(x[1]*z[2]-z[1]*x[2])/(speed**3)
        p0=(.996*width,deck-.075);p5=(.90*width,deck)
        k=4.*(math.sqrt(2.)-1.)/3.;d0=3.*k*(p5[1]-p0[1]);d1=3.*k*(p0[0]-p5[0])
        p1=(p0[0]+d0*tx/5.,p0[1]+d0*tz/5.)
        p2=(2.*p1[0]-p0[0]-curvature*d0*d0*tz/20.,2.*p1[1]-p0[1]+curvature*d0*d0*tx/20.)
        p4=(p5[0]+d1/5.,p5[1]);p3=(2.*p4[0]-p5[0],p5[1]);points=(p0,p1,p2,p3,p4,p5)
        def bezier(points,s):
            n=len(points)-1
            return tuple(sum(math.comb(n,i)*s**i*(1.-s)**(n-i)*p[a] for i,p in enumerate(points)) for a in (0,1))
        v1=tuple(tuple(5.*(b[k]-a[k]) for k in (0,1)) for a,b in zip(points,points[1:]))
        v2=tuple(tuple(4.*(b[k]-a[k]) for k in (0,1)) for a,b in zip(v1,v1[1:]))
        p=bezier(points,(t-5.)/2.);v=bezier(v1,(t-5.)/2.);a=bezier(v2,(t-5.)/2.)
        new=((p[0],v[0]/2.,a[0]/4.),(p[1],v[1]/2.,a[1]/4.))
    else:new=(tuple(1.125*x for x in original[0]),(deck,0.,0.))
    return tuple(tuple(a+weight*(b-a) for a,b in zip(axis,target)) for axis,target in zip(original,new))

def point_and_normal(t,y,side,*,legacy_profile,legacy_cubic,interpolate):
    if side not in (-1,1) or not 0.<=t<=8. or not -2.54<=y<=2.4:raise ValueError('Invalid original side parameters')
    q=D(y,1.);w=D.cast(widths(q,differentiable_interpolate));deck=D.cast(decks(q,differentiable_interpolate))
    axes=dual_section(t,q,w,deck,legacy_profile=legacy_profile,legacy_cubic=legacy_cubic,interpolate=differentiable_interpolate)
    x=D.cast(axes[0][0]);z=D.cast(axes[1][0]);xt=D.cast(axes[0][1]).v;zt=D.cast(axes[1][1]).v
    adjusted=q;yt=0.
    if y>2.05:
        blend=((q-2.05)/.35)**2;adjusted-=.15*(x/w)**3*blend
        yt-=.45*(x.v/w.v)**2*xt/w.v*blend.v
    if y<-2.25:
        blend=((-2.25-q)/.29)**2;adjusted+=.105*(x/w)**3*blend
        yt+=.315*(x.v/w.v)**2*xt/w.v*blend.v
    if y>2.230:
        radius=3.457;root=(radius*radius-(z-.550)**2)**.5;blend=smooth((q-2.230)/.170)
        adjusted-=(radius-root)*blend;yt-=(z.v-.550)/root.v*zt*D.cast(blend).v
    st=(side*xt,yt,zt);sy=(side*x.d,adjusted.d,z.d)
    n=tuple(-side*v for v in (st[1]*sy[2]-st[2]*sy[1],st[2]*sy[0]-st[0]*sy[2],st[0]*sy[1]-st[1]*sy[0]))
    length=math.hypot(*n)
    if not math.isfinite(length) or length<=1e-12:raise ValueError('Degenerate swept-surface derivative')
    return (side*x.v,adjusted.v,z.v),tuple(v/length for v in n),{'source_t':t,'source_y_m':y,'side':side,'d_dt':st,'d_dy':sy}
