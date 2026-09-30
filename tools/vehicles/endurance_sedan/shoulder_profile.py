"""Original finite shoulder fairing; preserve the pre-cut body and optical construction."""
import math

def cubic(values,t):
    slopes=[b-a for a,b in zip(values,values[1:])]
    tangent=[slopes[0]]+[0. if a*b<=0 else 2*a*b/(a+b) for a,b in zip(slopes,slopes[1:])]+[slopes[-1]]
    i=max(0,min(len(values)-2,int(math.floor(t))));s=max(0,min(1,t-i))
    p0,p1=values[i:i+2];m0,m1=tangent[i:i+2]
    c0=p0;c1=m0;c2=-3*p0-2*m0+3*p1-m1;c3=2*p0+m0-2*p1+m1
    return c0+c1*s+c2*s*s+c3*s*s*s,c1+2*c2*s+3*c3*s*s,2*c2+6*c3*s

def quintic(values,t,radius):
    a=6-radius;b=6+radius
    if t<a or t>b:return cubic(values,t)
    p0,v0,a0=cubic(values,a);p1,v1,a1=cubic(values,b);length=b-a;s=(t-a)/length
    c0=p0;c1=v0*length;c2=a0*length*length/2
    d0=p1-c0-c1-c2;d1=v1*length-c1-2*c2;d2=a1*length*length-2*c2
    c3=10*d0-4*d1+d2/2;c4=-15*d0+7*d1-d2;c5=6*d0-3*d1+d2/2
    p=c0+c1*s+c2*s*s+c3*s**3+c4*s**4+c5*s**5
    v=(c1+2*c2*s+3*c3*s*s+4*c4*s**3+5*c5*s**4)/length
    acc=(2*c2+6*c3*s+12*c4*s*s+20*c5*s**3)/(length*length)
    return p,v,acc

def profile(t,y,w,top,radius=.35):
    points=[(0,.135),(.72*w,.135),(.91*w,.20),(.982*w,.39),(w,.67),(.996*w,top-.075),(.94*w,top+.016),(.80*w,top+.017),(0,top)]
    s=max(0,min(1,(y-1.90)/.30));blend=s*s*s*(10-15*s+6*s*s)
    result=[]
    for axis in range(2):
        values=[p[axis] for p in points]
        old=cubic(values,t);new=quintic(values,t,radius)
        result.append(tuple(a+(b-a)*blend for a,b in zip(old,new)))
    if radius!=.35:raise ValueError('The finite original shoulder requires its locked .35 parameter span')
    result[1]=tuple(a+blend*b for a,b in zip(result[1],bump(t)))
    return result


COEFFICIENT_M=-0.034
PARAMETER_A=5.65
PARAMETER_B=6.35

def bump(t):
    if not PARAMETER_A<t<PARAMETER_B:return (0.,0.,0.)
    length=PARAMETER_B-PARAMETER_A;u=(t-PARAMETER_A)/length
    value=u**3*(1-u)**3
    first=3*u*u-12*u**3+15*u**4-6*u**5
    second=6*u-36*u*u+60*u**3-30*u**4
    return (COEFFICIENT_M*value,COEFFICIENT_M*first/length,COEFFICIENT_M*second/(length*length))
