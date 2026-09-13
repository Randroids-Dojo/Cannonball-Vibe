"""Bounded native short2 code selection for an explicit target corner field.

Blender5.1.2 mesh_normals.cc:660-662 treats first component0 as automatic.
No engine code is changed. Every result is measured using native decoding.
"""
import itertools,math
def angle(a,b):
    den=math.hypot(*a)*math.hypot(*b)
    if not math.isfinite(den) or den<=0:return math.inf
    return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(a,b))/den))))
def encode(mesh,targets):
    target=[tuple(n) for n in targets]
    if len(target)!=len(mesh.loops):raise ValueError('Corner target length')
    if any(not all(math.isfinite(v) for v in n) or abs(math.hypot(*n)-1)>1e-6 for n in target):raise ValueError('Invalid normal target')
    sharp=mesh.attributes.get('sharp_edge') or mesh.attributes.new(name='sharp_edge',type='BOOLEAN',domain='EDGE')
    for value in sharp.data:value.value=True
    mesh.update();mesh.normals_split_custom_set(target);mesh.update()
    actual=[tuple(n.vector) for n in mesh.corner_normals];errors=[angle(a,b) for a,b in zip(target,actual)]
    selected=[i for i,e in enumerate(errors) if e>.004]
    codes=[tuple(v.value) for v in mesh.attributes['custom_normal'].data]
    best={i:(errors[i],codes[i]) for i in selected}
    initial=max(errors,default=0);first_zero=[i for i in selected if codes[i][0]==0]
    offsets=(-128,-64,-32,-16,-8,-4,-2,-1,0,1,2,4,8,16,32,64,128)
    for dx,dy in itertools.product(offsets,repeat=2):
        for i in selected:
            x,y=codes[i];mesh.attributes['custom_normal'].data[i].value=(max(-32767,min(32767,x+dx)),max(-32767,min(32767,y+dy)))
        mesh.update()
        for i in selected:
            error=angle(target[i],tuple(mesh.corner_normals[i].vector))
            if error<best[i][0]:best[i]=(error,tuple(mesh.attributes['custom_normal'].data[i].value))
    centers={i:r[1] for i,r in best.items()}
    for dx,dy in itertools.product(range(-2,3),repeat=2):
        for i in selected:
            x,y=centers[i];mesh.attributes['custom_normal'].data[i].value=(max(-32767,min(32767,x+dx)),max(-32767,min(32767,y+dy)))
        mesh.update()
        for i in selected:
            error=angle(target[i],tuple(mesh.corner_normals[i].vector))
            if error<best[i][0]:best[i]=(error,tuple(mesh.attributes['custom_normal'].data[i].value))
    for i,r in best.items():mesh.attributes['custom_normal'].data[i].value=r[1]
    mesh.update();actual=[tuple(n.vector) for n in mesh.corner_normals];errors=[angle(a,b) for a,b in zip(target,actual)]
    recovery=[i for i,e in enumerate(errors) if e>.004]
    measured={}
    def unit(v):
        length=math.hypot(*v)
        if not math.isfinite(length) or length<=1e-12:raise ValueError('Invalid native normal basis')
        return tuple(x/length for x in v)
    def dot(a,b):return sum(x*y for x,y in zip(a,b))
    def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    probes={}
    for label,code in [('base',(0,0)),('alpha',(32767,0)),('beta',(32767,32767))]:
        for i in recovery:mesh.attributes['custom_normal'].data[i].value=code
        mesh.update();probes[label]={i:unit(tuple(mesh.corner_normals[i].vector)) for i in recovery}
    derived={}
    for i in recovery:
        n=probes['base'][i];a=probes['alpha'][i];b=probes['beta'][i]
        alpha=math.atan2(math.hypot(*cross(n,a)),dot(n,a))
        ref=unit(tuple(x-dot(n,a)*y for x,y in zip(a,n)));ortho=unit(cross(n,ref))
        beta=math.atan2(dot(b,ortho),dot(b,ref))%math.tau
        if beta<1e-6:beta=math.tau
        target_unit=unit(target[i]);ta=math.atan2(math.hypot(*cross(n,target_unit)),dot(n,target_unit));tb=math.atan2(dot(target_unit,ortho),dot(target_unit,ref))%math.tau
        if not 0<alpha<math.tau or not 0<beta<=math.tau:raise ValueError('Invalid recovered native angles')
        ca=ta/alpha if ta<=alpha else -(math.tau-ta)/(math.tau-alpha)
        cb=tb/beta if tb<=beta else -(math.tau-tb)/(math.tau-beta)
        code=(max(-32767,min(32767,math.floor(ca*32767+.5))),max(-32767,min(32767,math.floor(cb*32767+.5))))
        derived[i]=code
        measured[i]={'ref_alpha':alpha,'ref_beta':beta,'target_alpha':ta,'target_beta':tb,'derived_code':code,'before_angle_degrees':errors[i]}
        # Preserve the best earlier actual candidate as an explicit fallback.
        best[i]=(errors[i],tuple(mesh.attributes['custom_normal'].data[i].value)) if i not in best else best[i]
    for dx,dy in itertools.product(range(-2,3),repeat=2):
        for i in recovery:
            x,y=derived[i];mesh.attributes['custom_normal'].data[i].value=(max(-32767,min(32767,x+dx)),max(-32767,min(32767,y+dy)))
        mesh.update()
        for i in recovery:
            error=angle(target[i],tuple(mesh.corner_normals[i].vector))
            if error<best[i][0]:best[i]=(error,tuple(mesh.attributes['custom_normal'].data[i].value))
    for i,r in best.items():mesh.attributes['custom_normal'].data[i].value=r[1]
    mesh.update();actual=[tuple(n.vector) for n in mesh.corner_normals];errors=[angle(a,b) for a,b in zip(target,actual)]
    invalid=[i for i,n in enumerate(actual) if not all(math.isfinite(v) for v in n) or abs(math.hypot(*n)-1)>1e-6]
    maximum=max(errors,default=0)
    return {'maximum_input_float_encoding_degrees':initial,'maximum_native_decoded_degrees':maximum,'selected_corners':len(selected),
            'selected_initial_zero_codes':first_zero,'offset_grid':list(offsets),'refinement_grid':[-2,-1,0,1,2],
            'native_basis_recovery':measured,'invalid_native_normals':invalid,'passed':maximum<=.025 and not invalid,
            'worst_corners':[{'loop':i,'angle_degrees':errors[i],'target':target[i],'actual':actual[i]} for i in sorted(range(len(errors)),key=lambda i:errors[i],reverse=True)[:8]],
            'scope':'Independent sharp corner encoding spaces; shading still uses the measured authored custom normals. Native code search is finite and preserves geometry.'}
