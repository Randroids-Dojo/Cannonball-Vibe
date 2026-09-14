"""Inspectable wheel tubs, closure seals and mechanically separate body panels."""

import math
import json

from mathutils import Vector

from . import geometry as geo
from . import model
from .exterior import attach


def wheel_tubs(collection, lod, mats, profile):
    for side, symbol in ((-1, 'L'), (1, 'R')):
        for axle, cy, inner_x in (('F', 1.46, .465), ('R', -1.46, .586)):
            # Closed molded liner: 5 mm shell outside a 444 mm clear envelope.
            # Its inboard wall closes the luggage/cabin view into the wheel.
            vertices=[];faces=[];steps=profile['angular_steps'];return_proof=[]
            for i in range(steps+1):
                lo_angle,hi_angle=profile['angular_span_degrees']
                angle=math.radians(lo_angle+(hi_angle-lo_angle)*i/steps)
                hits=[]
                for radius in profile['radii_m']:
                    y=cy+radius*math.cos(angle);z=.3433+radius*math.sin(angle)
                    point=model.BODY_UPPER_SURFACE.ray_cast(Vector((side*2.,y,z)),Vector((-side,0,0)),3.)[0]
                    if point is None:raise ValueError('Liner lacks original body envelope')
                    hits.append(abs(point.x))
                outer=min(profile['maximum_outer_abs_x_m'],min(hits)-profile['minimum_body_inset_m'])
                if outer<=inner_x:raise ValueError('Liner return inverts the molded shell')
                return_proof.append({'angle_radians':angle,'body_outer_x_m':hits,'new_outer_x_m':outer})
                for x,r in ((inner_x,.444),(outer,.444),(outer,.449),(inner_x,.449)):
                    vertices.append((side*x,cy+r*math.cos(angle),.3433+r*math.sin(angle)))
            for i in range(steps):
                for j in range(4):
                    faces.append((4*i+j,4*i+(j+1)%4,4*(i+1)+(j+1)%4,4*(i+1)+j))
            faces.extend([(3,2,1,0),tuple(4*steps+i for i in range(4))])
            liner=geo.mesh('LOD0_WheelArchLiner_'+axle+symbol,vertices,faces,mats['rubber'],collection,lod,smooth=True)
            liner['clear_inner_radius_m']=.444
            liner['molded_body_return']=json.dumps(return_proof,sort_keys=True)
            outline=[(cy+.449*math.cos(math.radians(-18+216*i/steps)),.3433+.449*math.sin(math.radians(-18+216*i/steps))) for i in range(steps+1)]
            lo,hi=sorted((side*(inner_x-.004),side*inner_x))
            wall=geo.prism_x('LOD0_InnerWheelTub_'+axle+symbol,outline,lo,hi,mats['trim'],collection,lod)
            cutter=geo.tube('AxleBootPassage',[(side*(inner_x-.016),cy,.35),(side*(inner_x+.016),cy,.35)],.047,None,collection,sides=24)
            geo.boolean(wall,cutter);model.remove(cutter)
            geo.bevel(wall,.001,1)
            for j,angle in enumerate((15,45,75,105,135,165)):
                a=math.radians(angle)
                center=(side*.917,cy+.450*math.cos(a),.3433+.450*math.sin(a))
                bolt=geo.tube('LOD0_LinerRetainer_'+axle+symbol+str(j),[(center[0]-side*.003,center[1],center[2]),center],.004,mats['trim'],collection,lod,sides=8)
                bolt['maximum_lod']=0


def door_seals(collection, lod, mats, pivots):
    outlines={
        'F':[(.627,1.011),(.657,.301),(-.508,.301),(-.542,1.019),(-.530,1.388),(.133,1.355)],
        'R':[(-.655,1.019),(-.645,.306),(-.993,.306)]+[(-1.46+.459*math.cos(math.radians(a)),.3433+.459*math.sin(math.radians(a))) for a in (-4,15,35,55,75,95)]+[(-1.681,1.022),(-1.264,1.320),(-.661,1.382)],
    }
    for side,symbol in ((-1,'L'),(1,'R')):
        for axle,outline in outlines.items():
            suffix=axle+symbol;pivot=pivots['Door_'+suffix]
            def x_at(z):return side*(.778 if z<1 else .823-(z-1)*.48)
            points=[(x_at(z),y,z) for y,z in outline]
            seal=geo.tube('LOD0_DoorApertureSeal_'+suffix,points,.006,mats['rubber'],collection,lod,sides=8,closed=True)
            seal['contact_policy']='Compressible closure seal at its parked stop only'
            # Visible rolled inner flange belongs to the moving door assembly.
            if axle=='R':
                outline_hem=[(-.668,.981),(-.655,.316)]+[(-1.46+.514*math.cos(math.radians(a)),.3433+.514*math.sin(math.radians(a))) for a in (-3,15,35,55,75)]+[(-1.606,.981)]
            else:
                outline_hem=[(y,min(z,.981)) for y,z in model.inset_polygon(model.split_door_outlines()[axle],.017)]
            lower=[(side*.812,y,z) for y,z in outline_hem]
            attach(geo.tube('LOD0_DoorInnerHem_'+suffix,lower,.006,mats['paint'],collection,lod,sides=6,closed=True),pivot)
            cy=-.515 if axle=='F' else -1.155
            attach(geo.box('LOD0_DoorLatch_'+suffix,(side*.836,cy,.795),(.032,.017,.055),mats['metal'],collection,lod,radius=.003),pivot)
            for z in (.775,.814):
                bolt=attach(geo.tube('LOD0_LatchFastener_'+suffix+str(z),[(side*.858,cy-.009,z),(side*.858,cy-.012,z)],.003,mats['metal'],collection,lod,sides=6),pivot)
                bolt['maximum_lod']=0
        geo.box('LOD0_SillTread_'+symbol,(side*.785,-.205,.278),(.120,1.77,.006),mats['wheel'],collection,lod,radius=.002)


def separate_front_fenders(body, collection, lod, mats):
    for side,symbol in ((-1,'L'),(1,'R')):
        outer=geo.box('FenderAssemblyBoundary',(side*.938,1.275,.715),(.36,1.19,.91),None,collection,radius=0)
        inset=geo.box('FenderAssemblyGap',(side*.93875,1.275,.71675),(.3585,1.183,.9065),None,collection,radius=0)
        panel=body.copy();panel.data=body.data.copy();panel.name='LOD0_FrontFender_'+symbol
        collection.objects.link(panel);panel.parent=lod;panel.modifiers.clear()
        geo.boolean(panel,inset,'INTERSECT');geo.boolean(body,outer)
        model.remove(outer);model.remove(inset)
        geo.bevel(panel,.0012,2,angle=1.0);panel['closure_gap_m']=.0035


def build(body, collection, lod, mats, pivots, spec):
    for label,x,dy in (('Hood',.43737,.010),('Trunk',.45506,-.010)):
        pivot=pivots[label+'_Hinge']
        for side in (-1,1):
            cutter=geo.box('ClosureHingePocket',(side*x,pivot.location.y+dy,pivot.location.z-.010),(.080,.102,.100),None,collection,radius=0)
            geo.boolean(body,cutter);model.remove(cutter)
    for suffix in ('FL','FR','RL','RR'):
        pivot=pivots['Door_'+suffix]
        for z in pivot['hardware_pin_heights_m']:
            side=-1 if suffix.endswith('L') else 1
            front=suffix.startswith('F')
            # This jamb pocket opens into the door aperture and cabin, leaving
            # the exterior body skin intact over the concealed pin and arm.
            cutter=geo.box('DoorHingeRecess',(side*.859,pivot.location.y-(.055 if front else .050),z),(.128,.186 if front else .170,.080),None,collection,radius=0)
            geo.boolean(body,cutter);model.remove(cutter)
    wheel_tubs(collection,lod,mats,spec['original_packaging']['finish_revision19']['wheel_liner_return'])
    door_seals(collection,lod,mats,pivots)
    separate_front_fenders(body,collection,lod,mats)
