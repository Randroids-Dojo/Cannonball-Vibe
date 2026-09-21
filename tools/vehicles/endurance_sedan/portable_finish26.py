"""Native six-pipe curve construction and original static Bfont atlas."""
from . import geometry as geo,roof_feature26 as native,boolean_surface,charge_cooler26,cooler_economy26
from . import pipe_bends26,static_labels26
from .cooling_finish26 import plain
from .qa.self_geometry import scan

def apply(texture_output):
    objects,proof,before=pipe_bends26.apply(geo,native.row,charge_cooler26,boolean_surface.repair,scan,cooler_economy26.simplify)
    pipes={'construction':proof,'original_rows':before,'actual_final_rows':{o.name:native.row(o) for o in objects}}
    atlas=static_labels26.apply(texture_output)
    from . import brake_edge27, corner_encoding
    objects, proof, before = brake_edge27.apply(geo=geo, row=native.row, encode=corner_encoding.encode, exact_scan=scan)
    brakes = {'construction':proof,'original_rows':before,'actual_final_rows':{o.name:native.row(o) for o in objects}}
    return plain({'pipe_bends':pipes,'static_labels':atlas,'brake_edge27':brakes})
