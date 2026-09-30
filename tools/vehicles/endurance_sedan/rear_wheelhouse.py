"""Unsaved rear wheelhouse packaging candidate; not an adopted constructor.

Only rear tub/liner meshes change. Every seat, rail, belt and tire is preserved.
The existing native tub's Y/Z polygon, axle aperture and bevel outline remain.
Its X thickness is reduced from 4 to 2 mm; the inset leather cover is 1.2 mm.
Floor closure is deliberately outside this candidate, and remains unresolved.
"""
import bpy
from mathutils import Vector, geometry
from . import geometry as geo
from .floor_panels import freeze, offset
from .surface_normals import mark_fold_edges

WALL_INBOARD = .670
WALL_OUTBOARD = .672
COVER_THICKNESS = .0012

def hull(points):
    points = sorted(set(tuple(float(x) for x in p) for p in points))
    result = [points[i] for i in geometry.convex_hull_2d([Vector(p) for p in points])]
    area = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(result,result[1:]+result[:1]))
    return result if area > 0 else list(reversed(result))

def clip(poly, axis, value):
    result=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        ia,ib=a[axis]>=value,b[axis]>=value
        if ia: result.append(a)
        if ia != ib:
            t=(value-a[axis])/(b[axis]-a[axis])
            result.append(tuple(a[k]+t*(b[k]-a[k]) for k in range(2)))
    return result

def build(collection, parent, leather):
    changed={};proof={}
    if any(bpy.data.objects.get('LOD0_RearWheelhouseTrim_'+s) for s in ('L','R')):
        raise ValueError('Candidate08 must be installed once on unchanged tubs')
    for side,symbol in ((-1,'L'),(1,'R')):
        name='LOD0_InnerWheelTub_R'+symbol;obj=bpy.data.objects[name]
        freeze(obj);m=obj.data
        lo=min(side*v.co.x for v in m.vertices);hi=max(side*v.co.x for v in m.vertices)
        if abs(lo-.582)>1e-7 or abs(hi-.586)>1e-7:
            raise ValueError('Unexpected rear tub input bounds')
        scale=(WALL_OUTBOARD-WALL_INBOARD)/(hi-lo)
        normals=[Vector(n.vector) for n in m.corner_normals]
        for vertex in m.vertices:
            vertex.co.x=side*(WALL_INBOARD+(side*vertex.co.x-lo)*scale)
        m.update()
        m.normals_split_custom_set([tuple(Vector((n.x/scale,n.y,n.z)).normalized()) for n in normals])
        geo.project_uv(obj)
        obj['original_candidate08']='2mm rear wheelhouse wall; same YZ outline and axle passage'
        changed[name]=obj
        inside=min(side*v.co.x for v in m.vertices)
        flat=[(v.co.y,v.co.z) for v in m.vertices if abs(side*v.co.x-inside)<1e-8]
        support=offset(clip(clip(hull(flat),0,-1.400),1,.280),-.0002)
        rings=[support,support,offset(support,-.0002),offset(support,-.0005)]
        depths=[0,.0004,.0008,COVER_THICKNESS];n=len(support)
        vertices=[(side*(inside-d),y,z) for d,ring in zip(depths,rings) for y,z in ring]
        faces=[tuple(reversed(range(n))),tuple(range(3*n,4*n))]
        faces += [(r*n+i,r*n+(i+1)%n,(r+1)*n+(i+1)%n,(r+1)*n+i) for r in range(3) for i in range(n)]
        cover=geo.mesh('LOD0_RearWheelhouseTrim_'+symbol,vertices,faces,leather,collection,parent,smooth=True)
        mark_fold_edges(cover);changed[cover.name]=cover
        cover['original_candidate08']='1.2mm leather-faced molded wheelhouse trim; finite planar bonded backing'
        liner=bpy.data.objects['LOD0_WheelArchLiner_R'+symbol];freeze(liner)
        selected=[]
        for i,vertex in enumerate(liner.data.vertices):
            if abs(abs(vertex.co.x)-.586)<1e-7:
                selected.append(i);vertex.co.x=side*WALL_OUTBOARD
        if len(selected)!=98:raise ValueError('Unexpected rear liner input station inventory')
        liner.data.update()
        # A production rebuild would evaluate this narrower ruled liner natively.
        # Explicit actual face normals avoid carrying an invalid old custom field.
        liner.data.normals_split_custom_set([tuple(p.normal) for p in liner.data.polygons for _ in p.loop_indices])
        geo.project_uv(liner);changed[liner.name]=liner
        proof[symbol]={'old_tub_x_bounds_m':[lo,hi],'new_tub_x_bounds_m':[WALL_INBOARD,WALL_OUTBOARD],
                      'tub_x_scale':scale,'support_polygon_yz_m':support,'cover_x_depths_m':depths,
                      'cover_insets_m':[0,0,.0002,.0005],'liner_moved_vertex_indices':selected}
    return changed,proof
