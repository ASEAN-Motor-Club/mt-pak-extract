# C1Full navigation — splines that fold back (the U-turn defect)

24 along-lane edges had their two ends pointing opposite ways, i.e. the AI had a legal
U-turn edge. The positions themselves double back, so the spline curve loops: control
points carry a tangent 3-9x longer than the chord to the next point.

**Do not delete these points.** Deleting one just moves the loop. Reset the tangent:
select the point in the editor, `Set Tangent -> Curve` (or set arrive/leave tangent to
about a third of the chord), then rebake and check `reversed along edges` is 0.

## Fix these first (each one produces a fold)

| road | point | world (cm) | chord to next | tangent | ratio |
|---|---|---|---|---|---|
| C1_Rd060 | 83 | -31479, 595250, 86435 | 18.5 m | 133.5 m | 7.2x |
| C1_Rd065 | 36 | -167993, 819912, 85968 | 62.2 m | 443.9 m | 7.1x |
| C1_Rd065 | 71 | -275037, 895447, 86083 | 18.8 m | 119.3 m | 6.4x |
| C1_Rd074 | 15 | 56971, -381502, 86113 | 38.7 m | 340.3 m | 8.8x |
| C1_Rd123 | 2 | 403945, 550430, 85098 | 16.3 m | 125.0 m | 7.7x |

## Confirmed duplicate control point

`C1_Rd065` points **194 and 195 are 1.07 m apart** — a straight duplicate. Delete one of
them; this is the only case where deleting is correct.

## Same pattern elsewhere (optional, no fold observed yet)

- `C1_Rd023` point 135 at (186514, -974235, 86193) cm — tangent 33 m over a 9.9 m chord (3.4x)
- `C1_Rd060` point 27 at (71293, 432207, 85691) cm — tangent 56 m over a 17.8 m chord (3.1x)
- `C1_Rd060` point 30 at (37207, 448235, 85690) cm — tangent 156 m over a 46.5 m chord (3.3x)
- `C1_Rd060` point 33 at (20666, 456629, 85719) cm — tangent 60 m over a 19.5 m chord (3.1x)
- `C1_Rd060` point 46 at (10739, 468815, 85755) cm — tangent 81 m over a 24.9 m chord (3.3x)
- `C1_Rd060` point 69 at (-13033, 532951, 86050) cm — tangent 77 m over a 21.7 m chord (3.6x)
- `C1_Rd060` point 71 at (-14826, 548342, 86109) cm — tangent 76 m over a 17.8 m chord (4.2x)
- `C1_Rd065` point 19 at (-39393, 682497, 86064) cm — tangent 255 m over a 64.2 m chord (4.0x)
- `C1_Rd065` point 34 at (-92241, 759561, 86046) cm — tangent 484 m over a 142.9 m chord (3.4x)
- `C1_Rd065` point 50 at (-204483, 862534, 86002) cm — tangent 109 m over a 20.7 m chord (5.3x)
- `C1_Rd065` point 98 at (-313692, 925624, 86251) cm — tangent 50 m over a 16.4 m chord (3.0x)
- `C1_Rd065` point 174 at (-522505, 1040913, 86017) cm — tangent 112 m over a 29.2 m chord (3.8x)
- `C1_Rd065` point 194 at (-667339, 1101055, 86080) cm — tangent 8 m over a 1.1 m chord (7.7x)
- `C1_Rd065` point 201 at (-677656, 1107651, 86035) cm — tangent 49 m over a 15.9 m chord (3.1x)
- `C1_Rd065` point 238 at (-780361, 1148617, 86331) cm — tangent 75 m over a 21.0 m chord (3.6x)
- `C1_Rd065` point 249 at (-794270, 1157116, 85714) cm — tangent 78 m over a 23.1 m chord (3.4x)
- `C1_Rd065` point 277 at (-889718, 1191256, 86137) cm — tangent 77 m over a 23.5 m chord (3.3x)
- `C1_Rd074` point 12 at (89249, -459128, 85878) cm — tangent 99 m over a 27.3 m chord (3.6x)
- `C1_Rd074` point 42 at (58183, -225169, 85897) cm — tangent 80 m over a 19.9 m chord (4.0x)
- `C1_Rd074` point 55 at (62666, -205091, 85925) cm — tangent 279 m over a 45.0 m chord (6.2x)
- `C1_Rd074` point 58 at (52174, -88254, 85232) cm — tangent 351 m over a 85.9 m chord (4.1x)
- `C1_Rd074` point 71 at (35452, -44126, 85347) cm — tangent 84 m over a 20.6 m chord (4.1x)
- `C1_Rd074` point 77 at (28888, -35670, 85495) cm — tangent 130 m over a 37.6 m chord (3.5x)
- `C1_Rd074` point 80 at (-1558, -9056, 85899) cm — tangent 83 m over a 22.5 m chord (3.7x)
- `C1_Rd074` point 116 at (-37413, 56675, 85993) cm — tangent 64 m over a 18.0 m chord (3.5x)
- `C1_Rd074` point 145 at (-53450, 104835, 86280) cm — tangent 132 m over a 31.0 m chord (4.3x)
- `C1_Rd074` point 161 at (-14744, 148169, 85530) cm — tangent 131 m over a 37.1 m chord (3.5x)
- `C1_Rd123` point 0 at (418106, 572554, 85031) cm — tangent 131 m over a 29.1 m chord (4.5x)
