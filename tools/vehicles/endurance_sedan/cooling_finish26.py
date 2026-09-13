"""Current actual cooling construction, fields and finite receiver checks."""
import numpy as np
from . import geometry as geo, roof_feature26 as native, corner_encoding as codec
from . import surface_normals, boolean_surface
from . import charge_cooler26, cooler_economy26, radiator_fields26, complete_boundary26
from . import cooler_case_reference26, cooler_case_finish26
from . import main_fields_certificate26, main_fields_cell26, main_fields_validate26
from .qa.self_geometry import scan
from .qa.fitted_interfaces import partition, area


def plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    return value


def main_stack(obj, original, hose):
    if obj.name != 'LOD0_RadiatorStack':
        return None
    raw = native.row(obj)
    fields = radiator_fields26.apply(obj, original, surface_normals, codec.encode)

    def reverse(old, new, actual_hose):
        cell, _, cell_proof = main_fields_certificate26.terminal_cell(actual_hose, old, scan)
        outside, kept, removed, exact = main_fields_cell26.subtract(old, cell)
        result = complete_boundary26.complete(outside, new)
        return {'status': result['status'], 'complete_surface': result,
                'actual_cell': cell_proof, 'exact_subtraction': exact,
                'original_kept_fragments': len(kept), 'original_removed_fragments': len(removed)}

    proof = main_fields_validate26.validate(original, raw, native.row(obj), hose, fields,
        coverage=complete_boundary26.complete,
        field_check=lambda a, b, indices: main_fields_certificate26.field_certificate(a, b, indices, partition, area),
        reverse_check=reverse)
    return plain({'fields': fields, 'complete_proof': proof,
                  'original_receiver': original, 'actual_hose': hose,
                  'restored_cut_before_existing_retreat': native.row(obj)})


def charge_cooling():
    objects, construction, original = charge_cooler26.apply(
        geo, native.row, boolean_surface.repair, scan, cooler_economy26.simplify,
        lambda obj, old: radiator_fields26.apply(obj, old, surface_normals, codec.encode))
    finish = cooler_case_finish26.apply(construction, reference=cooler_case_reference26,
        row=native.row, encode=codec.encode, complete_boundary=complete_boundary26.complete,
        exact_scan=scan, evaluated_counts=geo.evaluated_counts)
    return plain({'construction': construction, 'original_receivers': original,
                  'case_finish': finish, 'actual_final_rows': {o.name: native.row(o) for o in objects}})
