"""Double-precision triangle interpolation for thin native source facets."""
import math
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def closest(point,triangle):
    a,b,c=triangle;ab=sub(b,a);ac=sub(c,a);n=cross(ab,ac);nn=dot(n,n)
    if not math.isfinite(nn) or nn<=0:raise ValueError('Invalid reference triangle')
    ap=sub(point,a);height=dot(ap,n)/nn
    hit=tuple(p-height*q for p,q in zip(point,n));hp=sub(hit,a)
    wb=dot(cross(hp,ac),n)/nn;wc=dot(cross(ab,hp),n)/nn;weights=(1-wb-wc,wb,wc)
    if min(weights)>=0:return math.dist(point,hit),weights
    choices=[]
    for i,j in ((0,1),(1,2),(2,0)):
        p,q=triangle[i],triangle[j];edge=sub(q,p);length=dot(edge,edge)
        if length<=0:raise ValueError('Invalid reference edge')
        t=min(1.,max(0.,dot(sub(point,p),edge)/length))
        hit=tuple(x+t*y for x,y in zip(p,edge));w=[0.,0.,0.];w[i]=1-t;w[j]=t
        choices.append((math.dist(point,hit),tuple(w)))
    return min(choices,key=lambda x:x[0])
def interpolate(values,weights):
    return tuple(sum(w*value[i] for w,value in zip(weights,values)) for i in range(len(values[0])))
