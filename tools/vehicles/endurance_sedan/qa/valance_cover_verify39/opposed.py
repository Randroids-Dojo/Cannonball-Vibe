"""Current-input finite verification; source bodies bound in extraction01."""

from fractions import Fraction as F
import numpy as np
from .triangle_distance import triangles

def check(row, outer, inner, intersection):
    av=np.array([[row['vertices'][v] for v in row['triangles'][i]] for i in outer]);bv=np.array([[row['vertices'][v] for v in row['triangles'][i]] for i in inner])
    alo,ahi=av.min(1),av.max(1);blo,bhi=bv.min(1),bv.max(1)
    gaps=np.maximum(0,np.maximum(alo[:,None,:]-bhi[None,:,:],blo[None,:,:]-ahi[:,None,:]));lower=np.sum(gaps*gaps,2)
    pairs=np.argwhere(lower<.00125**2);records=[]
    for ai,bi in pairs:
        a=av[ai].tolist();b=bv[bi].tolist();found=intersection(a,b);r=triangles(a,b)
        if found:r['distance_m']=0;r['exact_distance_squared_m2']='0';r['intersection']=[[str(x) for x in p] for p in found]
        r.update({'outer_face':outer[ai],'inner_face':inner[bi]});records.append(r)
    return {'pairs':len(outer)*len(inner),'aabb_at_least_1p25mm':len(outer)*len(inner)-len(pairs),'exact_pairs':len(pairs),'outer_faces':outer,'inner_faces':inner,
            'minimum':min(records,key=lambda x:x['distance_m']),'under_1p2mm':[r for r in records if r['distance_m']<.0012],'records':records}


def stock(actual,plan,roles,providers):
    from .contracts import require
    from . import finite_cells, end_caps
    paired={'formed_front':('authored_inner_front',None),'outer_side':('formed_side_inner',None),
            'inward_side_bend':('terminal_inner','inward_side_bend'),'deep_side':('terminal_inner','deep_side'),
            'closing_back':('terminal_inner','closing_back'),'inboard_closing_return':('terminal_inner','inboard_closing_return'),
            'bottom_return':('terminal_inner','bottom_return')}
    require(set(roles.values())==set(paired),'Incomplete complete-sheet role inventory')
    measurements={}
    for role,(domain,inner_role) in paired.items():
        outer=[i for i,(t,d) in enumerate(zip(plan['triangles'],plan['triangle_domains']))
               if d=='terminal_outer' and roles[tuple(sorted(t))]==role]
        inner=[i for i,(d,r) in enumerate(zip(plan['triangle_domains'],plan['triangle_authored_roles']))
               if d==domain and (inner_role is None or r==inner_role)]
        require(outer and inner,'Missing actual opposed sheet domain: '+role)
        measure=finite_cells.open_surface_distance(providers.fi.subset(actual,outer,'_outer_'+role),
                                                   providers.fi.subset(actual,inner,'_inner_'+role),providers.geometry)
        measurements[role]={'outer_triangles':outer,'inner_triangles':inner,'minimum':measure,
                            'status':'passed' if measure['distance_m']>=.001199 else 'failed'}
    outer=[i for i,d in enumerate(plan['triangle_domains']) if d in ('outer','terminal_outer')]
    inner=[i for i,d in enumerate(plan['triangle_domains']) if d in ('inner_preserved_fragment','terminal_inner','formed_side_inner','authored_inner_front')]
    result=check(actual,outer,inner,providers.intersection)
    short=[(r['outer_face'],r['inner_face']) for r in result['records'] if F(r['exact_distance_squared_m2'])<F('.001199')**2]
    try:
        caps=end_caps.classify({**actual,'triangle_domains':plan['triangle_domains'],
                               'triangle_authored_roles':plan['triangle_authored_roles']},short,providers.exact,triangles)
    except ValueError as error:
        caps={'status':'failed','reason':str(error),'short_pairs':short}
    passed=all(p['status']=='passed' for p in measurements.values()) and caps['status']=='passed_finite_stock_end_classification'
    return {'status':'passed' if passed else 'failed','seven_sheet_domains':measurements,'all_opposed':result,
            'finite_end_caps':caps,'sheet_stock_m':.0012,'native_guard_m':.000001,
            'separate_mandatory':'Exact global self and solid containment are not certified by sheet/end-cap distances.'}
