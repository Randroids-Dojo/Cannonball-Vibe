# Meridian S8R packaging revision 5

2026-09-11. Independent source-control inspection D035 found the steering rim covering speed, gear, RPM and fuel at the locked driver eye. The actual 2560x1440 Cycles capture and source10 hashes remain in the QA defect record. This revision addresses physical placement. Separate D036/D037 findings cover source hazard telltales and truncated digit drivers; numeric display fidelity requires its own correction and verification.

This original cabin candidate moves the instrument anchor from (-0.430,0.550,0.958) m to (-0.430,0.400,1.050) m and lowers the steering-wheel center from Z=0.910 m to0.855 m. The column and stalk assembly follows the wheel center. The 388 mm outside wheel diameter, tilt, steering ratio, eye position, seat position and gameplay controls are unchanged. The cluster remains behind the wheel and below the sloping windshield; displayed information sits above the rim from the declared eye. Actual source and runtime captures, windshield separation and occupant knee clearance must confirm this candidate before acceptance.

These are fictional ergonomic choices, not measured Audi dimensions. The previous locked values are preserved in `specification-v4.json`. Source uncertainty remains separate from dimensional modeling error. No human visual, usability or driving-feel approval is inferred.
