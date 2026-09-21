"""Choose a common ruled quad's lower-curvature diagonal from actual sections."""
import math
from .vectors import normal,dot,area


def zipper(vertices,a,b):
    i=j=0;out=[]
    while i<len(a)-1 or j<len(b)-1:
        x=a[i+1][0]if i+1<len(a)else math.inf
        y=b[j+1][0]if j+1<len(b)else math.inf
        if abs(x-y)<1e-11:
            A,B,C,D=a[i][1],b[j][1],b[j+1][1],a[i+1][1]
            choices=[[[A,B,C],[A,C,D]],[[A,B,D],[B,C,D]]]
            def score(ts):
                if min(area(vertices,t)for t in ts)<=1e-12:return(-math.inf,-math.inf)
                return(dot(normal(vertices,ts[0]),normal(vertices,ts[1])),min(area(vertices,t)for t in ts))
            out.extend(max(choices,key=score));i+=1;j+=1
        elif x<y:out.append([a[i][1],b[j][1],a[i+1][1]]);i+=1
        else:out.append([a[i][1],b[j][1],b[j+1][1]]);j+=1
    return out
