"""DP path-follower: unrolled outward-expanding 69-cell scan with interior fast path."""
from __future__ import annotations

from util.constants import INF

def dp_step_hop(w, cost, h, pos, path_idx, min_idx):
    """
    Hop-only DP: max `path_idx` among reachable cells, only considering
    cells with `path_idx > min_idx`. Returns `pos` if no such cell is
    found (caller treats that as "no forward progress, replan").
    """
    px = pos % w
    py = pos // w
    w2 = w + w
    w3 = w2 + w
    w4 = w3 + w
    reach1 = False
    gateway1: int = -1
    reach2 = False
    gateway2: int = -1
    reach3 = False
    gateway3: int = -1
    reach4 = False
    gateway4: int = -1
    reach5 = False
    gateway5: int = -1
    reach6 = False
    gateway6: int = -1
    reach7 = False
    gateway7: int = -1
    reach8 = False
    gateway8: int = -1
    reach9 = False
    gateway9: int = -1
    reach10 = False
    gateway10: int = -1
    reach11 = False
    gateway11: int = -1
    reach12 = False
    gateway12: int = -1
    reach13 = False
    gateway13: int = -1
    reach14 = False
    gateway14: int = -1
    reach15 = False
    gateway15: int = -1
    reach16 = False
    gateway16: int = -1
    reach17 = False
    gateway17: int = -1
    reach18 = False
    gateway18: int = -1
    reach19 = False
    gateway19: int = -1
    reach20 = False
    gateway20: int = -1
    reach21 = False
    gateway21: int = -1
    reach22 = False
    gateway22: int = -1
    reach23 = False
    gateway23: int = -1
    reach24 = False
    gateway24: int = -1
    reach25 = False
    gateway25: int = -1
    reach26 = False
    gateway26: int = -1
    reach27 = False
    gateway27: int = -1
    reach28 = False
    gateway28: int = -1
    reach29 = False
    gateway29: int = -1
    reach30 = False
    gateway30: int = -1
    reach31 = False
    gateway31: int = -1
    reach32 = False
    gateway32: int = -1
    reach33 = False
    gateway33: int = -1
    reach34 = False
    gateway34: int = -1
    reach35 = False
    gateway35: int = -1
    reach36 = False
    gateway36: int = -1
    reach37 = False
    gateway37: int = -1
    reach38 = False
    gateway38: int = -1
    reach39 = False
    gateway39: int = -1
    reach40 = False
    gateway40: int = -1
    reach41 = False
    gateway41: int = -1
    reach42 = False
    gateway42: int = -1
    reach43 = False
    gateway43: int = -1
    reach44 = False
    gateway44: int = -1
    reach45 = False
    gateway45: int = -1
    reach46 = False
    gateway46: int = -1
    reach47 = False
    gateway47: int = -1
    reach48 = False
    gateway48: int = -1
    reach49 = False
    gateway49: int = -1
    reach50 = False
    gateway50: int = -1
    reach51 = False
    gateway51: int = -1
    reach52 = False
    gateway52: int = -1
    reach53 = False
    gateway53: int = -1
    reach54 = False
    gateway54: int = -1
    reach55 = False
    gateway55: int = -1
    reach56 = False
    gateway56: int = -1
    reach57 = False
    gateway57: int = -1
    reach58 = False
    gateway58: int = -1
    reach59 = False
    gateway59: int = -1
    reach60 = False
    gateway60: int = -1
    reach61 = False
    gateway61: int = -1
    reach62 = False
    gateway62: int = -1
    reach63 = False
    gateway63: int = -1
    reach64 = False
    gateway64: int = -1
    reach65 = False
    gateway65: int = -1
    reach66 = False
    gateway66: int = -1
    reach67 = False
    gateway67: int = -1
    reach68 = False
    gateway68: int = -1
    best_idx = min_idx
    best_fs: int = -1
    if 4 <= px and px < w - 4 and 4 <= py and py < h - 4:
        cell = int(pos - w - 1)
        if cost[cell] != 1000000:
            reach1 = True
            gateway1 = 1
            pi = path_idx[cell]
            if pi > best_idx:
                best_idx = pi
                best_fs = gateway1
        cell = int(pos + w - 1)
        if cost[cell] != 1000000:
            reach2 = True
            gateway2 = 2
            pi = path_idx[cell]
            if pi > best_idx:
                best_idx = pi
                best_fs = gateway2
        cell = int(pos - w + 1)
        if cost[cell] != 1000000:
            reach3 = True
            gateway3 = 3
            pi = path_idx[cell]
            if pi > best_idx:
                best_idx = pi
                best_fs = gateway3
        cell = int(pos + w + 1)
        if cost[cell] != 1000000:
            reach4 = True
            gateway4 = 4
            pi = path_idx[cell]
            if pi > best_idx:
                best_idx = pi
                best_fs = gateway4
        cell = int(pos - 1)
        if cost[cell] != 1000000:
            reach5 = True
            gateway5 = 5
            pi = path_idx[cell]
            if pi > best_idx:
                best_idx = pi
                best_fs = gateway5
        cell = int(pos - w)
        if cost[cell] != 1000000:
            reach6 = True
            gateway6 = 6
            pi = path_idx[cell]
            if pi > best_idx:
                best_idx = pi
                best_fs = gateway6
        cell = int(pos + w)
        if cost[cell] != 1000000:
            reach7 = True
            gateway7 = 7
            pi = path_idx[cell]
            if pi > best_idx:
                best_idx = pi
                best_fs = gateway7
        cell = int(pos + 1)
        if cost[cell] != 1000000:
            reach8 = True
            gateway8 = 8
            pi = path_idx[cell]
            if pi > best_idx:
                best_idx = pi
                best_fs = gateway8
        cell = int(pos - 2)
        if cost[cell] != 1000000:
            if reach5:
                reach9 = True
                gateway9 = gateway5
            if reach9:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway9
        cell = int(pos - w2)
        if cost[cell] != 1000000:
            if reach6:
                reach10 = True
                gateway10 = gateway6
            if reach10:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway10
        cell = int(pos + w2)
        if cost[cell] != 1000000:
            if reach7:
                reach11 = True
                gateway11 = gateway7
            if reach11:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway11
        cell = int(pos + 2)
        if cost[cell] != 1000000:
            if reach8:
                reach12 = True
                gateway12 = gateway8
            if reach12:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway12
        cell = int(pos - w - 2)
        if cost[cell] != 1000000:
            if reach1:
                reach13 = True
                gateway13 = gateway1
            elif reach5:
                reach13 = True
                gateway13 = gateway5
            if reach13:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway13
        cell = int(pos + w - 2)
        if cost[cell] != 1000000:
            if reach2:
                reach14 = True
                gateway14 = gateway2
            elif reach5:
                reach14 = True
                gateway14 = gateway5
            if reach14:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway14
        cell = int(pos - w2 - 1)
        if cost[cell] != 1000000:
            if reach1:
                reach15 = True
                gateway15 = gateway1
            elif reach6:
                reach15 = True
                gateway15 = gateway6
            if reach15:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway15
        cell = int(pos + w2 - 1)
        if cost[cell] != 1000000:
            if reach2:
                reach16 = True
                gateway16 = gateway2
            elif reach7:
                reach16 = True
                gateway16 = gateway7
            if reach16:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway16
        cell = int(pos - w2 + 1)
        if cost[cell] != 1000000:
            if reach3:
                reach17 = True
                gateway17 = gateway3
            elif reach6:
                reach17 = True
                gateway17 = gateway6
            if reach17:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway17
        cell = int(pos + w2 + 1)
        if cost[cell] != 1000000:
            if reach4:
                reach18 = True
                gateway18 = gateway4
            elif reach7:
                reach18 = True
                gateway18 = gateway7
            if reach18:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway18
        cell = int(pos - w + 2)
        if cost[cell] != 1000000:
            if reach3:
                reach19 = True
                gateway19 = gateway3
            elif reach8:
                reach19 = True
                gateway19 = gateway8
            if reach19:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway19
        cell = int(pos + w + 2)
        if cost[cell] != 1000000:
            if reach4:
                reach20 = True
                gateway20 = gateway4
            elif reach8:
                reach20 = True
                gateway20 = gateway8
            if reach20:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway20
        cell = int(pos - w2 - 2)
        if cost[cell] != 1000000:
            if reach1:
                reach21 = True
                gateway21 = gateway1
            if reach21:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway21
        cell = int(pos + w2 - 2)
        if cost[cell] != 1000000:
            if reach2:
                reach22 = True
                gateway22 = gateway2
            if reach22:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway22
        cell = int(pos - w2 + 2)
        if cost[cell] != 1000000:
            if reach3:
                reach23 = True
                gateway23 = gateway3
            if reach23:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway23
        cell = int(pos + w2 + 2)
        if cost[cell] != 1000000:
            if reach4:
                reach24 = True
                gateway24 = gateway4
            if reach24:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway24
        cell = int(pos - 3)
        if cost[cell] != 1000000:
            if reach9:
                reach25 = True
                gateway25 = gateway9
            if reach25:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway25
        cell = int(pos - w3)
        if cost[cell] != 1000000:
            if reach10:
                reach26 = True
                gateway26 = gateway10
            if reach26:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway26
        cell = int(pos + w3)
        if cost[cell] != 1000000:
            if reach11:
                reach27 = True
                gateway27 = gateway11
            if reach27:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway27
        cell = int(pos + 3)
        if cost[cell] != 1000000:
            if reach12:
                reach28 = True
                gateway28 = gateway12
            if reach28:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway28
        cell = int(pos - w - 3)
        if cost[cell] != 1000000:
            if reach13:
                reach29 = True
                gateway29 = gateway13
            elif reach9:
                reach29 = True
                gateway29 = gateway9
            if reach29:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway29
        cell = int(pos + w - 3)
        if cost[cell] != 1000000:
            if reach14:
                reach30 = True
                gateway30 = gateway14
            elif reach9:
                reach30 = True
                gateway30 = gateway9
            if reach30:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway30
        cell = int(pos - w3 - 1)
        if cost[cell] != 1000000:
            if reach15:
                reach31 = True
                gateway31 = gateway15
            elif reach10:
                reach31 = True
                gateway31 = gateway10
            if reach31:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway31
        cell = int(pos + w3 - 1)
        if cost[cell] != 1000000:
            if reach16:
                reach32 = True
                gateway32 = gateway16
            elif reach11:
                reach32 = True
                gateway32 = gateway11
            if reach32:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway32
        cell = int(pos - w3 + 1)
        if cost[cell] != 1000000:
            if reach17:
                reach33 = True
                gateway33 = gateway17
            elif reach10:
                reach33 = True
                gateway33 = gateway10
            if reach33:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway33
        cell = int(pos + w3 + 1)
        if cost[cell] != 1000000:
            if reach18:
                reach34 = True
                gateway34 = gateway18
            elif reach11:
                reach34 = True
                gateway34 = gateway11
            if reach34:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway34
        cell = int(pos - w + 3)
        if cost[cell] != 1000000:
            if reach19:
                reach35 = True
                gateway35 = gateway19
            elif reach12:
                reach35 = True
                gateway35 = gateway12
            if reach35:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway35
        cell = int(pos + w + 3)
        if cost[cell] != 1000000:
            if reach20:
                reach36 = True
                gateway36 = gateway20
            elif reach12:
                reach36 = True
                gateway36 = gateway12
            if reach36:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway36
        cell = int(pos - w2 - 3)
        if cost[cell] != 1000000:
            if reach21:
                reach37 = True
                gateway37 = gateway21
            elif reach13:
                reach37 = True
                gateway37 = gateway13
            if reach37:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway37
        cell = int(pos + w2 - 3)
        if cost[cell] != 1000000:
            if reach22:
                reach38 = True
                gateway38 = gateway22
            elif reach14:
                reach38 = True
                gateway38 = gateway14
            if reach38:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway38
        cell = int(pos - w3 - 2)
        if cost[cell] != 1000000:
            if reach21:
                reach39 = True
                gateway39 = gateway21
            elif reach15:
                reach39 = True
                gateway39 = gateway15
            if reach39:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway39
        cell = int(pos + w3 - 2)
        if cost[cell] != 1000000:
            if reach22:
                reach40 = True
                gateway40 = gateway22
            elif reach16:
                reach40 = True
                gateway40 = gateway16
            if reach40:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway40
        cell = int(pos - w3 + 2)
        if cost[cell] != 1000000:
            if reach23:
                reach41 = True
                gateway41 = gateway23
            elif reach17:
                reach41 = True
                gateway41 = gateway17
            if reach41:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway41
        cell = int(pos + w3 + 2)
        if cost[cell] != 1000000:
            if reach24:
                reach42 = True
                gateway42 = gateway24
            elif reach18:
                reach42 = True
                gateway42 = gateway18
            if reach42:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway42
        cell = int(pos - w2 + 3)
        if cost[cell] != 1000000:
            if reach23:
                reach43 = True
                gateway43 = gateway23
            elif reach19:
                reach43 = True
                gateway43 = gateway19
            if reach43:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway43
        cell = int(pos + w2 + 3)
        if cost[cell] != 1000000:
            if reach24:
                reach44 = True
                gateway44 = gateway24
            elif reach20:
                reach44 = True
                gateway44 = gateway20
            if reach44:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway44
        cell = int(pos - 4)
        if cost[cell] != 1000000:
            if reach25:
                reach45 = True
                gateway45 = gateway25
            if reach45:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway45
        cell = int(pos - w4)
        if cost[cell] != 1000000:
            if reach26:
                reach46 = True
                gateway46 = gateway26
            if reach46:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway46
        cell = int(pos + w4)
        if cost[cell] != 1000000:
            if reach27:
                reach47 = True
                gateway47 = gateway27
            if reach47:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway47
        cell = int(pos + 4)
        if cost[cell] != 1000000:
            if reach28:
                reach48 = True
                gateway48 = gateway28
            if reach48:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway48
        cell = int(pos - w - 4)
        if cost[cell] != 1000000:
            if reach29:
                reach49 = True
                gateway49 = gateway29
            elif reach25:
                reach49 = True
                gateway49 = gateway25
            if reach49:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway49
        cell = int(pos + w - 4)
        if cost[cell] != 1000000:
            if reach30:
                reach50 = True
                gateway50 = gateway30
            elif reach25:
                reach50 = True
                gateway50 = gateway25
            if reach50:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway50
        cell = int(pos - w4 - 1)
        if cost[cell] != 1000000:
            if reach31:
                reach51 = True
                gateway51 = gateway31
            elif reach26:
                reach51 = True
                gateway51 = gateway26
            if reach51:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway51
        cell = int(pos + w4 - 1)
        if cost[cell] != 1000000:
            if reach32:
                reach52 = True
                gateway52 = gateway32
            elif reach27:
                reach52 = True
                gateway52 = gateway27
            if reach52:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway52
        cell = int(pos - w4 + 1)
        if cost[cell] != 1000000:
            if reach33:
                reach53 = True
                gateway53 = gateway33
            elif reach26:
                reach53 = True
                gateway53 = gateway26
            if reach53:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway53
        cell = int(pos + w4 + 1)
        if cost[cell] != 1000000:
            if reach34:
                reach54 = True
                gateway54 = gateway34
            elif reach27:
                reach54 = True
                gateway54 = gateway27
            if reach54:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway54
        cell = int(pos - w + 4)
        if cost[cell] != 1000000:
            if reach35:
                reach55 = True
                gateway55 = gateway35
            elif reach28:
                reach55 = True
                gateway55 = gateway28
            if reach55:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway55
        cell = int(pos + w + 4)
        if cost[cell] != 1000000:
            if reach36:
                reach56 = True
                gateway56 = gateway36
            elif reach28:
                reach56 = True
                gateway56 = gateway28
            if reach56:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway56
        cell = int(pos - w3 - 3)
        if cost[cell] != 1000000:
            if reach21:
                reach57 = True
                gateway57 = gateway21
            if reach57:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway57
        cell = int(pos + w3 - 3)
        if cost[cell] != 1000000:
            if reach22:
                reach58 = True
                gateway58 = gateway22
            if reach58:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway58
        cell = int(pos - w3 + 3)
        if cost[cell] != 1000000:
            if reach23:
                reach59 = True
                gateway59 = gateway23
            if reach59:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway59
        cell = int(pos + w3 + 3)
        if cost[cell] != 1000000:
            if reach24:
                reach60 = True
                gateway60 = gateway24
            if reach60:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway60
        cell = int(pos - w2 - 4)
        if cost[cell] != 1000000:
            if reach37:
                reach61 = True
                gateway61 = gateway37
            elif reach29:
                reach61 = True
                gateway61 = gateway29
            if reach61:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway61
        cell = int(pos + w2 - 4)
        if cost[cell] != 1000000:
            if reach38:
                reach62 = True
                gateway62 = gateway38
            elif reach30:
                reach62 = True
                gateway62 = gateway30
            if reach62:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway62
        cell = int(pos - w4 - 2)
        if cost[cell] != 1000000:
            if reach39:
                reach63 = True
                gateway63 = gateway39
            elif reach31:
                reach63 = True
                gateway63 = gateway31
            if reach63:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway63
        cell = int(pos + w4 - 2)
        if cost[cell] != 1000000:
            if reach40:
                reach64 = True
                gateway64 = gateway40
            elif reach32:
                reach64 = True
                gateway64 = gateway32
            if reach64:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway64
        cell = int(pos - w4 + 2)
        if cost[cell] != 1000000:
            if reach41:
                reach65 = True
                gateway65 = gateway41
            elif reach33:
                reach65 = True
                gateway65 = gateway33
            if reach65:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway65
        cell = int(pos + w4 + 2)
        if cost[cell] != 1000000:
            if reach42:
                reach66 = True
                gateway66 = gateway42
            elif reach34:
                reach66 = True
                gateway66 = gateway34
            if reach66:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway66
        cell = int(pos - w2 + 4)
        if cost[cell] != 1000000:
            if reach43:
                reach67 = True
                gateway67 = gateway43
            elif reach35:
                reach67 = True
                gateway67 = gateway35
            if reach67:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway67
        cell = int(pos + w2 + 4)
        if cost[cell] != 1000000:
            if reach44:
                reach68 = True
                gateway68 = gateway44
            elif reach36:
                reach68 = True
                gateway68 = gateway36
            if reach68:
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway68
    else:
        nx = px - 1
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                reach1 = True
                gateway1 = 1
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway1
        nx = px - 1
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                reach2 = True
                gateway2 = 2
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway2
        nx = px + 1
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                reach3 = True
                gateway3 = 3
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway3
        nx = px + 1
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                reach4 = True
                gateway4 = 4
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway4
        nx = px - 1
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                reach5 = True
                gateway5 = 5
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway5
        nx = px
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                reach6 = True
                gateway6 = 6
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway6
        nx = px
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                reach7 = True
                gateway7 = 7
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway7
        nx = px + 1
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                reach8 = True
                gateway8 = 8
                pi = path_idx[cell]
                if pi > best_idx:
                    best_idx = pi
                    best_fs = gateway8
        nx = px - 2
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach5:
                    reach9 = True
                    gateway9 = gateway5
                if reach9:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway9
        nx = px
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach6:
                    reach10 = True
                    gateway10 = gateway6
                if reach10:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway10
        nx = px
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach7:
                    reach11 = True
                    gateway11 = gateway7
                if reach11:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway11
        nx = px + 2
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach8:
                    reach12 = True
                    gateway12 = gateway8
                if reach12:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway12
        nx = px - 2
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach1:
                    reach13 = True
                    gateway13 = gateway1
                elif reach5:
                    reach13 = True
                    gateway13 = gateway5
                if reach13:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway13
        nx = px - 2
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach2:
                    reach14 = True
                    gateway14 = gateway2
                elif reach5:
                    reach14 = True
                    gateway14 = gateway5
                if reach14:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway14
        nx = px - 1
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach1:
                    reach15 = True
                    gateway15 = gateway1
                elif reach6:
                    reach15 = True
                    gateway15 = gateway6
                if reach15:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway15
        nx = px - 1
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach2:
                    reach16 = True
                    gateway16 = gateway2
                elif reach7:
                    reach16 = True
                    gateway16 = gateway7
                if reach16:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway16
        nx = px + 1
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach3:
                    reach17 = True
                    gateway17 = gateway3
                elif reach6:
                    reach17 = True
                    gateway17 = gateway6
                if reach17:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway17
        nx = px + 1
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach4:
                    reach18 = True
                    gateway18 = gateway4
                elif reach7:
                    reach18 = True
                    gateway18 = gateway7
                if reach18:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway18
        nx = px + 2
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach3:
                    reach19 = True
                    gateway19 = gateway3
                elif reach8:
                    reach19 = True
                    gateway19 = gateway8
                if reach19:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway19
        nx = px + 2
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach4:
                    reach20 = True
                    gateway20 = gateway4
                elif reach8:
                    reach20 = True
                    gateway20 = gateway8
                if reach20:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway20
        nx = px - 2
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach1:
                    reach21 = True
                    gateway21 = gateway1
                if reach21:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway21
        nx = px - 2
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach2:
                    reach22 = True
                    gateway22 = gateway2
                if reach22:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway22
        nx = px + 2
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach3:
                    reach23 = True
                    gateway23 = gateway3
                if reach23:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway23
        nx = px + 2
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach4:
                    reach24 = True
                    gateway24 = gateway4
                if reach24:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway24
        nx = px - 3
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach9:
                    reach25 = True
                    gateway25 = gateway9
                if reach25:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway25
        nx = px
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach10:
                    reach26 = True
                    gateway26 = gateway10
                if reach26:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway26
        nx = px
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach11:
                    reach27 = True
                    gateway27 = gateway11
                if reach27:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway27
        nx = px + 3
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach12:
                    reach28 = True
                    gateway28 = gateway12
                if reach28:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway28
        nx = px - 3
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach13:
                    reach29 = True
                    gateway29 = gateway13
                elif reach9:
                    reach29 = True
                    gateway29 = gateway9
                if reach29:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway29
        nx = px - 3
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach14:
                    reach30 = True
                    gateway30 = gateway14
                elif reach9:
                    reach30 = True
                    gateway30 = gateway9
                if reach30:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway30
        nx = px - 1
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach15:
                    reach31 = True
                    gateway31 = gateway15
                elif reach10:
                    reach31 = True
                    gateway31 = gateway10
                if reach31:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway31
        nx = px - 1
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach16:
                    reach32 = True
                    gateway32 = gateway16
                elif reach11:
                    reach32 = True
                    gateway32 = gateway11
                if reach32:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway32
        nx = px + 1
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach17:
                    reach33 = True
                    gateway33 = gateway17
                elif reach10:
                    reach33 = True
                    gateway33 = gateway10
                if reach33:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway33
        nx = px + 1
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach18:
                    reach34 = True
                    gateway34 = gateway18
                elif reach11:
                    reach34 = True
                    gateway34 = gateway11
                if reach34:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway34
        nx = px + 3
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach19:
                    reach35 = True
                    gateway35 = gateway19
                elif reach12:
                    reach35 = True
                    gateway35 = gateway12
                if reach35:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway35
        nx = px + 3
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach20:
                    reach36 = True
                    gateway36 = gateway20
                elif reach12:
                    reach36 = True
                    gateway36 = gateway12
                if reach36:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway36
        nx = px - 3
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach21:
                    reach37 = True
                    gateway37 = gateway21
                elif reach13:
                    reach37 = True
                    gateway37 = gateway13
                if reach37:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway37
        nx = px - 3
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach22:
                    reach38 = True
                    gateway38 = gateway22
                elif reach14:
                    reach38 = True
                    gateway38 = gateway14
                if reach38:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway38
        nx = px - 2
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach21:
                    reach39 = True
                    gateway39 = gateway21
                elif reach15:
                    reach39 = True
                    gateway39 = gateway15
                if reach39:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway39
        nx = px - 2
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach22:
                    reach40 = True
                    gateway40 = gateway22
                elif reach16:
                    reach40 = True
                    gateway40 = gateway16
                if reach40:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway40
        nx = px + 2
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach23:
                    reach41 = True
                    gateway41 = gateway23
                elif reach17:
                    reach41 = True
                    gateway41 = gateway17
                if reach41:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway41
        nx = px + 2
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach24:
                    reach42 = True
                    gateway42 = gateway24
                elif reach18:
                    reach42 = True
                    gateway42 = gateway18
                if reach42:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway42
        nx = px + 3
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach23:
                    reach43 = True
                    gateway43 = gateway23
                elif reach19:
                    reach43 = True
                    gateway43 = gateway19
                if reach43:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway43
        nx = px + 3
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach24:
                    reach44 = True
                    gateway44 = gateway24
                elif reach20:
                    reach44 = True
                    gateway44 = gateway20
                if reach44:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway44
        nx = px - 4
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach25:
                    reach45 = True
                    gateway45 = gateway25
                if reach45:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway45
        nx = px
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach26:
                    reach46 = True
                    gateway46 = gateway26
                if reach46:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway46
        nx = px
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach27:
                    reach47 = True
                    gateway47 = gateway27
                if reach47:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway47
        nx = px + 4
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach28:
                    reach48 = True
                    gateway48 = gateway28
                if reach48:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway48
        nx = px - 4
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach29:
                    reach49 = True
                    gateway49 = gateway29
                elif reach25:
                    reach49 = True
                    gateway49 = gateway25
                if reach49:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway49
        nx = px - 4
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach30:
                    reach50 = True
                    gateway50 = gateway30
                elif reach25:
                    reach50 = True
                    gateway50 = gateway25
                if reach50:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway50
        nx = px - 1
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach31:
                    reach51 = True
                    gateway51 = gateway31
                elif reach26:
                    reach51 = True
                    gateway51 = gateway26
                if reach51:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway51
        nx = px - 1
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach32:
                    reach52 = True
                    gateway52 = gateway32
                elif reach27:
                    reach52 = True
                    gateway52 = gateway27
                if reach52:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway52
        nx = px + 1
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach33:
                    reach53 = True
                    gateway53 = gateway33
                elif reach26:
                    reach53 = True
                    gateway53 = gateway26
                if reach53:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway53
        nx = px + 1
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach34:
                    reach54 = True
                    gateway54 = gateway34
                elif reach27:
                    reach54 = True
                    gateway54 = gateway27
                if reach54:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway54
        nx = px + 4
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach35:
                    reach55 = True
                    gateway55 = gateway35
                elif reach28:
                    reach55 = True
                    gateway55 = gateway28
                if reach55:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway55
        nx = px + 4
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach36:
                    reach56 = True
                    gateway56 = gateway36
                elif reach28:
                    reach56 = True
                    gateway56 = gateway28
                if reach56:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway56
        nx = px - 3
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach21:
                    reach57 = True
                    gateway57 = gateway21
                if reach57:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway57
        nx = px - 3
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach22:
                    reach58 = True
                    gateway58 = gateway22
                if reach58:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway58
        nx = px + 3
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach23:
                    reach59 = True
                    gateway59 = gateway23
                if reach59:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway59
        nx = px + 3
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach24:
                    reach60 = True
                    gateway60 = gateway24
                if reach60:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway60
        nx = px - 4
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach37:
                    reach61 = True
                    gateway61 = gateway37
                elif reach29:
                    reach61 = True
                    gateway61 = gateway29
                if reach61:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway61
        nx = px - 4
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach38:
                    reach62 = True
                    gateway62 = gateway38
                elif reach30:
                    reach62 = True
                    gateway62 = gateway30
                if reach62:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway62
        nx = px - 2
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach39:
                    reach63 = True
                    gateway63 = gateway39
                elif reach31:
                    reach63 = True
                    gateway63 = gateway31
                if reach63:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway63
        nx = px - 2
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach40:
                    reach64 = True
                    gateway64 = gateway40
                elif reach32:
                    reach64 = True
                    gateway64 = gateway32
                if reach64:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway64
        nx = px + 2
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach41:
                    reach65 = True
                    gateway65 = gateway41
                elif reach33:
                    reach65 = True
                    gateway65 = gateway33
                if reach65:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway65
        nx = px + 2
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach42:
                    reach66 = True
                    gateway66 = gateway42
                elif reach34:
                    reach66 = True
                    gateway66 = gateway34
                if reach66:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway66
        nx = px + 4
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach43:
                    reach67 = True
                    gateway67 = gateway43
                elif reach35:
                    reach67 = True
                    gateway67 = gateway35
                if reach67:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway67
        nx = px + 4
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            if cost[cell] != 1000000:
                if reach44:
                    reach68 = True
                    gateway68 = gateway44
                elif reach36:
                    reach68 = True
                    gateway68 = gateway36
                if reach68:
                    pi = path_idx[cell]
                    if pi > best_idx:
                        best_idx = pi
                        best_fs = gateway68
    if best_fs < 0:
        return pos
    if best_fs == 1:
        return pos - w - 1
    if best_fs == 2:
        return pos + w - 1
    if best_fs == 3:
        return pos - w + 1
    if best_fs == 4:
        return pos + w + 1
    if best_fs == 5:
        return pos - 1
    if best_fs == 6:
        return pos - w
    if best_fs == 7:
        return pos + w
    if best_fs == 8:
        return pos + 1
    return pos

def dp_step(w, cost, h, pos, path_idx, min_idx):
    """
    Cost-aware DP. Max `path_idx`, tiebreak min cumulative cost. Only
    considers cells with `path_idx > min_idx` so the caller can require
    strict forward progress along the plan; returns `pos` when no such
    cell is reachable in the 69-cell window (caller replans).
    """
    px = pos % w
    py = pos // w
    w2 = w + w
    w3 = w2 + w
    w4 = w3 + w
    dist1 = 1000000
    dist2 = 1000000
    dist3 = 1000000
    dist4 = 1000000
    dist5 = 1000000
    dist6 = 1000000
    dist7 = 1000000
    dist8 = 1000000
    dist9 = 1000000
    dist10 = 1000000
    dist11 = 1000000
    dist12 = 1000000
    dist13 = 1000000
    dist14 = 1000000
    dist15 = 1000000
    dist16 = 1000000
    dist17 = 1000000
    dist18 = 1000000
    dist19 = 1000000
    dist20 = 1000000
    dist21 = 1000000
    dist22 = 1000000
    dist23 = 1000000
    dist24 = 1000000
    dist25 = 1000000
    dist26 = 1000000
    dist27 = 1000000
    dist28 = 1000000
    dist29 = 1000000
    dist30 = 1000000
    dist31 = 1000000
    dist32 = 1000000
    dist33 = 1000000
    dist34 = 1000000
    dist35 = 1000000
    dist36 = 1000000
    dist37 = 1000000
    dist38 = 1000000
    dist39 = 1000000
    dist40 = 1000000
    dist41 = 1000000
    dist42 = 1000000
    dist43 = 1000000
    dist44 = 1000000
    gateway9: int = -1
    gateway10: int = -1
    gateway11: int = -1
    gateway12: int = -1
    gateway13: int = -1
    gateway14: int = -1
    gateway15: int = -1
    gateway16: int = -1
    gateway17: int = -1
    gateway18: int = -1
    gateway19: int = -1
    gateway20: int = -1
    gateway21: int = -1
    gateway22: int = -1
    gateway23: int = -1
    gateway24: int = -1
    gateway25: int = -1
    gateway26: int = -1
    gateway27: int = -1
    gateway28: int = -1
    gateway29: int = -1
    gateway30: int = -1
    gateway31: int = -1
    gateway32: int = -1
    gateway33: int = -1
    gateway34: int = -1
    gateway35: int = -1
    gateway36: int = -1
    gateway37: int = -1
    gateway38: int = -1
    gateway39: int = -1
    gateway40: int = -1
    gateway41: int = -1
    gateway42: int = -1
    gateway43: int = -1
    gateway44: int = -1
    best_idx = min_idx
    best_dist = 1000000
    best_fs: int = -1
    if 4 <= px and px < w - 4 and 4 <= py and py < h - 4:
        cell = int(pos - w - 1)
        c = cost[cell]
        if c != 1000000:
            dist1 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 1
        cell = int(pos + w - 1)
        c = cost[cell]
        if c != 1000000:
            dist2 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 2
        cell = int(pos - w + 1)
        c = cost[cell]
        if c != 1000000:
            dist3 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 3
        cell = int(pos + w + 1)
        c = cost[cell]
        if c != 1000000:
            dist4 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 4
        cell = int(pos - 1)
        c = cost[cell]
        if c != 1000000:
            dist5 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 5
        cell = int(pos - w)
        c = cost[cell]
        if c != 1000000:
            dist6 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 6
        cell = int(pos + w)
        c = cost[cell]
        if c != 1000000:
            dist7 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 7
        cell = int(pos + 1)
        c = cost[cell]
        if c != 1000000:
            dist8 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 8
        cell = int(pos - 2)
        c = cost[cell]
        if c != 1000000:
            if dist5 != 1000000:
                nd = dist5 + c
                if nd < dist9:
                    dist9 = nd
                    gateway9 = 5
            if dist9 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist9 < best_dist:
                    best_idx = pi
                    best_dist = dist9
                    best_fs = gateway9
        cell = int(pos - w2)
        c = cost[cell]
        if c != 1000000:
            if dist6 != 1000000:
                nd = dist6 + c
                if nd < dist10:
                    dist10 = nd
                    gateway10 = 6
            if dist10 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist10 < best_dist:
                    best_idx = pi
                    best_dist = dist10
                    best_fs = gateway10
        cell = int(pos + w2)
        c = cost[cell]
        if c != 1000000:
            if dist7 != 1000000:
                nd = dist7 + c
                if nd < dist11:
                    dist11 = nd
                    gateway11 = 7
            if dist11 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist11 < best_dist:
                    best_idx = pi
                    best_dist = dist11
                    best_fs = gateway11
        cell = int(pos + 2)
        c = cost[cell]
        if c != 1000000:
            if dist8 != 1000000:
                nd = dist8 + c
                if nd < dist12:
                    dist12 = nd
                    gateway12 = 8
            if dist12 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist12 < best_dist:
                    best_idx = pi
                    best_dist = dist12
                    best_fs = gateway12
        cell = int(pos - w - 2)
        c = cost[cell]
        if c != 1000000:
            if dist1 != 1000000:
                nd = dist1 + c
                if nd < dist13:
                    dist13 = nd
                    gateway13 = 1
            if dist5 != 1000000:
                nd = dist5 + c
                if nd < dist13:
                    dist13 = nd
                    gateway13 = 5
            if dist13 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist13 < best_dist:
                    best_idx = pi
                    best_dist = dist13
                    best_fs = gateway13
        cell = int(pos + w - 2)
        c = cost[cell]
        if c != 1000000:
            if dist2 != 1000000:
                nd = dist2 + c
                if nd < dist14:
                    dist14 = nd
                    gateway14 = 2
            if dist5 != 1000000:
                nd = dist5 + c
                if nd < dist14:
                    dist14 = nd
                    gateway14 = 5
            if dist14 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist14 < best_dist:
                    best_idx = pi
                    best_dist = dist14
                    best_fs = gateway14
        cell = int(pos - w2 - 1)
        c = cost[cell]
        if c != 1000000:
            if dist1 != 1000000:
                nd = dist1 + c
                if nd < dist15:
                    dist15 = nd
                    gateway15 = 1
            if dist6 != 1000000:
                nd = dist6 + c
                if nd < dist15:
                    dist15 = nd
                    gateway15 = 6
            if dist15 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist15 < best_dist:
                    best_idx = pi
                    best_dist = dist15
                    best_fs = gateway15
        cell = int(pos + w2 - 1)
        c = cost[cell]
        if c != 1000000:
            if dist2 != 1000000:
                nd = dist2 + c
                if nd < dist16:
                    dist16 = nd
                    gateway16 = 2
            if dist7 != 1000000:
                nd = dist7 + c
                if nd < dist16:
                    dist16 = nd
                    gateway16 = 7
            if dist16 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist16 < best_dist:
                    best_idx = pi
                    best_dist = dist16
                    best_fs = gateway16
        cell = int(pos - w2 + 1)
        c = cost[cell]
        if c != 1000000:
            if dist3 != 1000000:
                nd = dist3 + c
                if nd < dist17:
                    dist17 = nd
                    gateway17 = 3
            if dist6 != 1000000:
                nd = dist6 + c
                if nd < dist17:
                    dist17 = nd
                    gateway17 = 6
            if dist17 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist17 < best_dist:
                    best_idx = pi
                    best_dist = dist17
                    best_fs = gateway17
        cell = int(pos + w2 + 1)
        c = cost[cell]
        if c != 1000000:
            if dist4 != 1000000:
                nd = dist4 + c
                if nd < dist18:
                    dist18 = nd
                    gateway18 = 4
            if dist7 != 1000000:
                nd = dist7 + c
                if nd < dist18:
                    dist18 = nd
                    gateway18 = 7
            if dist18 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist18 < best_dist:
                    best_idx = pi
                    best_dist = dist18
                    best_fs = gateway18
        cell = int(pos - w + 2)
        c = cost[cell]
        if c != 1000000:
            if dist3 != 1000000:
                nd = dist3 + c
                if nd < dist19:
                    dist19 = nd
                    gateway19 = 3
            if dist8 != 1000000:
                nd = dist8 + c
                if nd < dist19:
                    dist19 = nd
                    gateway19 = 8
            if dist19 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist19 < best_dist:
                    best_idx = pi
                    best_dist = dist19
                    best_fs = gateway19
        cell = int(pos + w + 2)
        c = cost[cell]
        if c != 1000000:
            if dist4 != 1000000:
                nd = dist4 + c
                if nd < dist20:
                    dist20 = nd
                    gateway20 = 4
            if dist8 != 1000000:
                nd = dist8 + c
                if nd < dist20:
                    dist20 = nd
                    gateway20 = 8
            if dist20 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist20 < best_dist:
                    best_idx = pi
                    best_dist = dist20
                    best_fs = gateway20
        cell = int(pos - w2 - 2)
        c = cost[cell]
        if c != 1000000:
            if dist1 != 1000000:
                nd = dist1 + c
                if nd < dist21:
                    dist21 = nd
                    gateway21 = 1
            if dist21 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist21 < best_dist:
                    best_idx = pi
                    best_dist = dist21
                    best_fs = gateway21
        cell = int(pos + w2 - 2)
        c = cost[cell]
        if c != 1000000:
            if dist2 != 1000000:
                nd = dist2 + c
                if nd < dist22:
                    dist22 = nd
                    gateway22 = 2
            if dist22 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist22 < best_dist:
                    best_idx = pi
                    best_dist = dist22
                    best_fs = gateway22
        cell = int(pos - w2 + 2)
        c = cost[cell]
        if c != 1000000:
            if dist3 != 1000000:
                nd = dist3 + c
                if nd < dist23:
                    dist23 = nd
                    gateway23 = 3
            if dist23 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist23 < best_dist:
                    best_idx = pi
                    best_dist = dist23
                    best_fs = gateway23
        cell = int(pos + w2 + 2)
        c = cost[cell]
        if c != 1000000:
            if dist4 != 1000000:
                nd = dist4 + c
                if nd < dist24:
                    dist24 = nd
                    gateway24 = 4
            if dist24 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist24 < best_dist:
                    best_idx = pi
                    best_dist = dist24
                    best_fs = gateway24
        cell = int(pos - 3)
        c = cost[cell]
        if c != 1000000:
            if dist9 != 1000000:
                nd = dist9 + c
                if nd < dist25:
                    dist25 = nd
                    gateway25 = gateway9
            if dist25 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist25 < best_dist:
                    best_idx = pi
                    best_dist = dist25
                    best_fs = gateway25
        cell = int(pos - w3)
        c = cost[cell]
        if c != 1000000:
            if dist10 != 1000000:
                nd = dist10 + c
                if nd < dist26:
                    dist26 = nd
                    gateway26 = gateway10
            if dist26 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist26 < best_dist:
                    best_idx = pi
                    best_dist = dist26
                    best_fs = gateway26
        cell = int(pos + w3)
        c = cost[cell]
        if c != 1000000:
            if dist11 != 1000000:
                nd = dist11 + c
                if nd < dist27:
                    dist27 = nd
                    gateway27 = gateway11
            if dist27 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist27 < best_dist:
                    best_idx = pi
                    best_dist = dist27
                    best_fs = gateway27
        cell = int(pos + 3)
        c = cost[cell]
        if c != 1000000:
            if dist12 != 1000000:
                nd = dist12 + c
                if nd < dist28:
                    dist28 = nd
                    gateway28 = gateway12
            if dist28 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist28 < best_dist:
                    best_idx = pi
                    best_dist = dist28
                    best_fs = gateway28
        cell = int(pos - w - 3)
        c = cost[cell]
        if c != 1000000:
            if dist13 != 1000000:
                nd = dist13 + c
                if nd < dist29:
                    dist29 = nd
                    gateway29 = gateway13
            if dist9 != 1000000:
                nd = dist9 + c
                if nd < dist29:
                    dist29 = nd
                    gateway29 = gateway9
            if dist29 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist29 < best_dist:
                    best_idx = pi
                    best_dist = dist29
                    best_fs = gateway29
        cell = int(pos + w - 3)
        c = cost[cell]
        if c != 1000000:
            if dist14 != 1000000:
                nd = dist14 + c
                if nd < dist30:
                    dist30 = nd
                    gateway30 = gateway14
            if dist9 != 1000000:
                nd = dist9 + c
                if nd < dist30:
                    dist30 = nd
                    gateway30 = gateway9
            if dist30 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist30 < best_dist:
                    best_idx = pi
                    best_dist = dist30
                    best_fs = gateway30
        cell = int(pos - w3 - 1)
        c = cost[cell]
        if c != 1000000:
            if dist15 != 1000000:
                nd = dist15 + c
                if nd < dist31:
                    dist31 = nd
                    gateway31 = gateway15
            if dist10 != 1000000:
                nd = dist10 + c
                if nd < dist31:
                    dist31 = nd
                    gateway31 = gateway10
            if dist31 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist31 < best_dist:
                    best_idx = pi
                    best_dist = dist31
                    best_fs = gateway31
        cell = int(pos + w3 - 1)
        c = cost[cell]
        if c != 1000000:
            if dist16 != 1000000:
                nd = dist16 + c
                if nd < dist32:
                    dist32 = nd
                    gateway32 = gateway16
            if dist11 != 1000000:
                nd = dist11 + c
                if nd < dist32:
                    dist32 = nd
                    gateway32 = gateway11
            if dist32 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist32 < best_dist:
                    best_idx = pi
                    best_dist = dist32
                    best_fs = gateway32
        cell = int(pos - w3 + 1)
        c = cost[cell]
        if c != 1000000:
            if dist17 != 1000000:
                nd = dist17 + c
                if nd < dist33:
                    dist33 = nd
                    gateway33 = gateway17
            if dist10 != 1000000:
                nd = dist10 + c
                if nd < dist33:
                    dist33 = nd
                    gateway33 = gateway10
            if dist33 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist33 < best_dist:
                    best_idx = pi
                    best_dist = dist33
                    best_fs = gateway33
        cell = int(pos + w3 + 1)
        c = cost[cell]
        if c != 1000000:
            if dist18 != 1000000:
                nd = dist18 + c
                if nd < dist34:
                    dist34 = nd
                    gateway34 = gateway18
            if dist11 != 1000000:
                nd = dist11 + c
                if nd < dist34:
                    dist34 = nd
                    gateway34 = gateway11
            if dist34 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist34 < best_dist:
                    best_idx = pi
                    best_dist = dist34
                    best_fs = gateway34
        cell = int(pos - w + 3)
        c = cost[cell]
        if c != 1000000:
            if dist19 != 1000000:
                nd = dist19 + c
                if nd < dist35:
                    dist35 = nd
                    gateway35 = gateway19
            if dist12 != 1000000:
                nd = dist12 + c
                if nd < dist35:
                    dist35 = nd
                    gateway35 = gateway12
            if dist35 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist35 < best_dist:
                    best_idx = pi
                    best_dist = dist35
                    best_fs = gateway35
        cell = int(pos + w + 3)
        c = cost[cell]
        if c != 1000000:
            if dist20 != 1000000:
                nd = dist20 + c
                if nd < dist36:
                    dist36 = nd
                    gateway36 = gateway20
            if dist12 != 1000000:
                nd = dist12 + c
                if nd < dist36:
                    dist36 = nd
                    gateway36 = gateway12
            if dist36 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist36 < best_dist:
                    best_idx = pi
                    best_dist = dist36
                    best_fs = gateway36
        cell = int(pos - w2 - 3)
        c = cost[cell]
        if c != 1000000:
            if dist21 != 1000000:
                nd = dist21 + c
                if nd < dist37:
                    dist37 = nd
                    gateway37 = gateway21
            if dist13 != 1000000:
                nd = dist13 + c
                if nd < dist37:
                    dist37 = nd
                    gateway37 = gateway13
            if dist37 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist37 < best_dist:
                    best_idx = pi
                    best_dist = dist37
                    best_fs = gateway37
        cell = int(pos + w2 - 3)
        c = cost[cell]
        if c != 1000000:
            if dist22 != 1000000:
                nd = dist22 + c
                if nd < dist38:
                    dist38 = nd
                    gateway38 = gateway22
            if dist14 != 1000000:
                nd = dist14 + c
                if nd < dist38:
                    dist38 = nd
                    gateway38 = gateway14
            if dist38 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist38 < best_dist:
                    best_idx = pi
                    best_dist = dist38
                    best_fs = gateway38
        cell = int(pos - w3 - 2)
        c = cost[cell]
        if c != 1000000:
            if dist21 != 1000000:
                nd = dist21 + c
                if nd < dist39:
                    dist39 = nd
                    gateway39 = gateway21
            if dist15 != 1000000:
                nd = dist15 + c
                if nd < dist39:
                    dist39 = nd
                    gateway39 = gateway15
            if dist39 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist39 < best_dist:
                    best_idx = pi
                    best_dist = dist39
                    best_fs = gateway39
        cell = int(pos + w3 - 2)
        c = cost[cell]
        if c != 1000000:
            if dist22 != 1000000:
                nd = dist22 + c
                if nd < dist40:
                    dist40 = nd
                    gateway40 = gateway22
            if dist16 != 1000000:
                nd = dist16 + c
                if nd < dist40:
                    dist40 = nd
                    gateway40 = gateway16
            if dist40 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist40 < best_dist:
                    best_idx = pi
                    best_dist = dist40
                    best_fs = gateway40
        cell = int(pos - w3 + 2)
        c = cost[cell]
        if c != 1000000:
            if dist23 != 1000000:
                nd = dist23 + c
                if nd < dist41:
                    dist41 = nd
                    gateway41 = gateway23
            if dist17 != 1000000:
                nd = dist17 + c
                if nd < dist41:
                    dist41 = nd
                    gateway41 = gateway17
            if dist41 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist41 < best_dist:
                    best_idx = pi
                    best_dist = dist41
                    best_fs = gateway41
        cell = int(pos + w3 + 2)
        c = cost[cell]
        if c != 1000000:
            if dist24 != 1000000:
                nd = dist24 + c
                if nd < dist42:
                    dist42 = nd
                    gateway42 = gateway24
            if dist18 != 1000000:
                nd = dist18 + c
                if nd < dist42:
                    dist42 = nd
                    gateway42 = gateway18
            if dist42 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist42 < best_dist:
                    best_idx = pi
                    best_dist = dist42
                    best_fs = gateway42
        cell = int(pos - w2 + 3)
        c = cost[cell]
        if c != 1000000:
            if dist23 != 1000000:
                nd = dist23 + c
                if nd < dist43:
                    dist43 = nd
                    gateway43 = gateway23
            if dist19 != 1000000:
                nd = dist19 + c
                if nd < dist43:
                    dist43 = nd
                    gateway43 = gateway19
            if dist43 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist43 < best_dist:
                    best_idx = pi
                    best_dist = dist43
                    best_fs = gateway43
        cell = int(pos + w2 + 3)
        c = cost[cell]
        if c != 1000000:
            if dist24 != 1000000:
                nd = dist24 + c
                if nd < dist44:
                    dist44 = nd
                    gateway44 = gateway24
            if dist20 != 1000000:
                nd = dist20 + c
                if nd < dist44:
                    dist44 = nd
                    gateway44 = gateway20
            if dist44 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist44 < best_dist:
                    best_idx = pi
                    best_dist = dist44
                    best_fs = gateway44
        cell = int(pos - 4)
        c = cost[cell]
        if c != 1000000 and dist25 != 1000000:
            nd = dist25 + c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and nd < best_dist:
                best_idx = pi
                best_dist = nd
                best_fs = gateway25
        cell = int(pos - w4)
        c = cost[cell]
        if c != 1000000 and dist26 != 1000000:
            nd = dist26 + c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and nd < best_dist:
                best_idx = pi
                best_dist = nd
                best_fs = gateway26
        cell = int(pos + w4)
        c = cost[cell]
        if c != 1000000 and dist27 != 1000000:
            nd = dist27 + c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and nd < best_dist:
                best_idx = pi
                best_dist = nd
                best_fs = gateway27
        cell = int(pos + 4)
        c = cost[cell]
        if c != 1000000 and dist28 != 1000000:
            nd = dist28 + c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and nd < best_dist:
                best_idx = pi
                best_dist = nd
                best_fs = gateway28
        cell = int(pos - w - 4)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist29 != 1000000:
                nd = dist29 + c
                gw_local = gateway29
            if dist25 != 1000000:
                nd1 = dist25 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway25
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos + w - 4)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist30 != 1000000:
                nd = dist30 + c
                gw_local = gateway30
            if dist25 != 1000000:
                nd1 = dist25 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway25
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos - w4 - 1)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist31 != 1000000:
                nd = dist31 + c
                gw_local = gateway31
            if dist26 != 1000000:
                nd1 = dist26 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway26
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos + w4 - 1)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist32 != 1000000:
                nd = dist32 + c
                gw_local = gateway32
            if dist27 != 1000000:
                nd1 = dist27 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway27
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos - w4 + 1)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist33 != 1000000:
                nd = dist33 + c
                gw_local = gateway33
            if dist26 != 1000000:
                nd1 = dist26 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway26
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos + w4 + 1)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist34 != 1000000:
                nd = dist34 + c
                gw_local = gateway34
            if dist27 != 1000000:
                nd1 = dist27 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway27
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos - w + 4)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist35 != 1000000:
                nd = dist35 + c
                gw_local = gateway35
            if dist28 != 1000000:
                nd1 = dist28 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway28
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos + w + 4)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist36 != 1000000:
                nd = dist36 + c
                gw_local = gateway36
            if dist28 != 1000000:
                nd1 = dist28 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway28
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos - w3 - 3)
        c = cost[cell]
        if c != 1000000 and dist21 != 1000000:
            nd = dist21 + c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and nd < best_dist:
                best_idx = pi
                best_dist = nd
                best_fs = gateway21
        cell = int(pos + w3 - 3)
        c = cost[cell]
        if c != 1000000 and dist22 != 1000000:
            nd = dist22 + c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and nd < best_dist:
                best_idx = pi
                best_dist = nd
                best_fs = gateway22
        cell = int(pos - w3 + 3)
        c = cost[cell]
        if c != 1000000 and dist23 != 1000000:
            nd = dist23 + c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and nd < best_dist:
                best_idx = pi
                best_dist = nd
                best_fs = gateway23
        cell = int(pos + w3 + 3)
        c = cost[cell]
        if c != 1000000 and dist24 != 1000000:
            nd = dist24 + c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and nd < best_dist:
                best_idx = pi
                best_dist = nd
                best_fs = gateway24
        cell = int(pos - w2 - 4)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist37 != 1000000:
                nd = dist37 + c
                gw_local = gateway37
            if dist29 != 1000000:
                nd1 = dist29 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway29
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos + w2 - 4)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist38 != 1000000:
                nd = dist38 + c
                gw_local = gateway38
            if dist30 != 1000000:
                nd1 = dist30 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway30
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos - w4 - 2)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist39 != 1000000:
                nd = dist39 + c
                gw_local = gateway39
            if dist31 != 1000000:
                nd1 = dist31 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway31
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos + w4 - 2)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist40 != 1000000:
                nd = dist40 + c
                gw_local = gateway40
            if dist32 != 1000000:
                nd1 = dist32 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway32
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos - w4 + 2)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist41 != 1000000:
                nd = dist41 + c
                gw_local = gateway41
            if dist33 != 1000000:
                nd1 = dist33 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway33
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos + w4 + 2)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist42 != 1000000:
                nd = dist42 + c
                gw_local = gateway42
            if dist34 != 1000000:
                nd1 = dist34 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway34
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos - w2 + 4)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist43 != 1000000:
                nd = dist43 + c
                gw_local = gateway43
            if dist35 != 1000000:
                nd1 = dist35 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway35
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
        cell = int(pos + w2 + 4)
        c = cost[cell]
        if c != 1000000:
            nd = 1000000
            gw_local: int = -1
            if dist44 != 1000000:
                nd = dist44 + c
                gw_local = gateway44
            if dist36 != 1000000:
                nd1 = dist36 + c
                if nd1 < nd:
                    nd = nd1
                    gw_local = gateway36
            if nd != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gw_local
    elif 3 <= px and px < w - 3 and 3 <= py and py < h - 3:
        cell = int(pos - w - 1)
        c = cost[cell]
        if c != 1000000:
            dist1 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 1
        cell = int(pos + w - 1)
        c = cost[cell]
        if c != 1000000:
            dist2 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 2
        cell = int(pos - w + 1)
        c = cost[cell]
        if c != 1000000:
            dist3 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 3
        cell = int(pos + w + 1)
        c = cost[cell]
        if c != 1000000:
            dist4 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 4
        cell = int(pos - 1)
        c = cost[cell]
        if c != 1000000:
            dist5 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 5
        cell = int(pos - w)
        c = cost[cell]
        if c != 1000000:
            dist6 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 6
        cell = int(pos + w)
        c = cost[cell]
        if c != 1000000:
            dist7 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 7
        cell = int(pos + 1)
        c = cost[cell]
        if c != 1000000:
            dist8 = c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and c < best_dist:
                best_idx = pi
                best_dist = c
                best_fs = 8
        cell = int(pos - 2)
        c = cost[cell]
        if c != 1000000:
            if dist5 != 1000000:
                nd = dist5 + c
                if nd < dist9:
                    dist9 = nd
                    gateway9 = 5
            if dist9 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist9 < best_dist:
                    best_idx = pi
                    best_dist = dist9
                    best_fs = gateway9
        cell = int(pos - w2)
        c = cost[cell]
        if c != 1000000:
            if dist6 != 1000000:
                nd = dist6 + c
                if nd < dist10:
                    dist10 = nd
                    gateway10 = 6
            if dist10 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist10 < best_dist:
                    best_idx = pi
                    best_dist = dist10
                    best_fs = gateway10
        cell = int(pos + w2)
        c = cost[cell]
        if c != 1000000:
            if dist7 != 1000000:
                nd = dist7 + c
                if nd < dist11:
                    dist11 = nd
                    gateway11 = 7
            if dist11 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist11 < best_dist:
                    best_idx = pi
                    best_dist = dist11
                    best_fs = gateway11
        cell = int(pos + 2)
        c = cost[cell]
        if c != 1000000:
            if dist8 != 1000000:
                nd = dist8 + c
                if nd < dist12:
                    dist12 = nd
                    gateway12 = 8
            if dist12 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist12 < best_dist:
                    best_idx = pi
                    best_dist = dist12
                    best_fs = gateway12
        cell = int(pos - w - 2)
        c = cost[cell]
        if c != 1000000:
            if dist1 != 1000000:
                nd = dist1 + c
                if nd < dist13:
                    dist13 = nd
                    gateway13 = 1
            if dist5 != 1000000:
                nd = dist5 + c
                if nd < dist13:
                    dist13 = nd
                    gateway13 = 5
            if dist13 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist13 < best_dist:
                    best_idx = pi
                    best_dist = dist13
                    best_fs = gateway13
        cell = int(pos + w - 2)
        c = cost[cell]
        if c != 1000000:
            if dist2 != 1000000:
                nd = dist2 + c
                if nd < dist14:
                    dist14 = nd
                    gateway14 = 2
            if dist5 != 1000000:
                nd = dist5 + c
                if nd < dist14:
                    dist14 = nd
                    gateway14 = 5
            if dist14 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist14 < best_dist:
                    best_idx = pi
                    best_dist = dist14
                    best_fs = gateway14
        cell = int(pos - w2 - 1)
        c = cost[cell]
        if c != 1000000:
            if dist1 != 1000000:
                nd = dist1 + c
                if nd < dist15:
                    dist15 = nd
                    gateway15 = 1
            if dist6 != 1000000:
                nd = dist6 + c
                if nd < dist15:
                    dist15 = nd
                    gateway15 = 6
            if dist15 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist15 < best_dist:
                    best_idx = pi
                    best_dist = dist15
                    best_fs = gateway15
        cell = int(pos + w2 - 1)
        c = cost[cell]
        if c != 1000000:
            if dist2 != 1000000:
                nd = dist2 + c
                if nd < dist16:
                    dist16 = nd
                    gateway16 = 2
            if dist7 != 1000000:
                nd = dist7 + c
                if nd < dist16:
                    dist16 = nd
                    gateway16 = 7
            if dist16 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist16 < best_dist:
                    best_idx = pi
                    best_dist = dist16
                    best_fs = gateway16
        cell = int(pos - w2 + 1)
        c = cost[cell]
        if c != 1000000:
            if dist3 != 1000000:
                nd = dist3 + c
                if nd < dist17:
                    dist17 = nd
                    gateway17 = 3
            if dist6 != 1000000:
                nd = dist6 + c
                if nd < dist17:
                    dist17 = nd
                    gateway17 = 6
            if dist17 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist17 < best_dist:
                    best_idx = pi
                    best_dist = dist17
                    best_fs = gateway17
        cell = int(pos + w2 + 1)
        c = cost[cell]
        if c != 1000000:
            if dist4 != 1000000:
                nd = dist4 + c
                if nd < dist18:
                    dist18 = nd
                    gateway18 = 4
            if dist7 != 1000000:
                nd = dist7 + c
                if nd < dist18:
                    dist18 = nd
                    gateway18 = 7
            if dist18 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist18 < best_dist:
                    best_idx = pi
                    best_dist = dist18
                    best_fs = gateway18
        cell = int(pos - w + 2)
        c = cost[cell]
        if c != 1000000:
            if dist3 != 1000000:
                nd = dist3 + c
                if nd < dist19:
                    dist19 = nd
                    gateway19 = 3
            if dist8 != 1000000:
                nd = dist8 + c
                if nd < dist19:
                    dist19 = nd
                    gateway19 = 8
            if dist19 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist19 < best_dist:
                    best_idx = pi
                    best_dist = dist19
                    best_fs = gateway19
        cell = int(pos + w + 2)
        c = cost[cell]
        if c != 1000000:
            if dist4 != 1000000:
                nd = dist4 + c
                if nd < dist20:
                    dist20 = nd
                    gateway20 = 4
            if dist8 != 1000000:
                nd = dist8 + c
                if nd < dist20:
                    dist20 = nd
                    gateway20 = 8
            if dist20 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist20 < best_dist:
                    best_idx = pi
                    best_dist = dist20
                    best_fs = gateway20
        cell = int(pos - w2 - 2)
        c = cost[cell]
        if c != 1000000:
            if dist1 != 1000000:
                nd = dist1 + c
                if nd < dist21:
                    dist21 = nd
                    gateway21 = 1
            if dist21 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist21 < best_dist:
                    best_idx = pi
                    best_dist = dist21
                    best_fs = gateway21
        cell = int(pos + w2 - 2)
        c = cost[cell]
        if c != 1000000:
            if dist2 != 1000000:
                nd = dist2 + c
                if nd < dist22:
                    dist22 = nd
                    gateway22 = 2
            if dist22 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist22 < best_dist:
                    best_idx = pi
                    best_dist = dist22
                    best_fs = gateway22
        cell = int(pos - w2 + 2)
        c = cost[cell]
        if c != 1000000:
            if dist3 != 1000000:
                nd = dist3 + c
                if nd < dist23:
                    dist23 = nd
                    gateway23 = 3
            if dist23 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist23 < best_dist:
                    best_idx = pi
                    best_dist = dist23
                    best_fs = gateway23
        cell = int(pos + w2 + 2)
        c = cost[cell]
        if c != 1000000:
            if dist4 != 1000000:
                nd = dist4 + c
                if nd < dist24:
                    dist24 = nd
                    gateway24 = 4
            if dist24 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist24 < best_dist:
                    best_idx = pi
                    best_dist = dist24
                    best_fs = gateway24
        cell = int(pos - 3)
        c = cost[cell]
        if c != 1000000:
            if dist9 != 1000000:
                nd = dist9 + c
                if nd < dist25:
                    dist25 = nd
                    gateway25 = gateway9
            if dist25 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist25 < best_dist:
                    best_idx = pi
                    best_dist = dist25
                    best_fs = gateway25
        cell = int(pos - w3)
        c = cost[cell]
        if c != 1000000:
            if dist10 != 1000000:
                nd = dist10 + c
                if nd < dist26:
                    dist26 = nd
                    gateway26 = gateway10
            if dist26 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist26 < best_dist:
                    best_idx = pi
                    best_dist = dist26
                    best_fs = gateway26
        cell = int(pos + w3)
        c = cost[cell]
        if c != 1000000:
            if dist11 != 1000000:
                nd = dist11 + c
                if nd < dist27:
                    dist27 = nd
                    gateway27 = gateway11
            if dist27 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist27 < best_dist:
                    best_idx = pi
                    best_dist = dist27
                    best_fs = gateway27
        cell = int(pos + 3)
        c = cost[cell]
        if c != 1000000:
            if dist12 != 1000000:
                nd = dist12 + c
                if nd < dist28:
                    dist28 = nd
                    gateway28 = gateway12
            if dist28 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist28 < best_dist:
                    best_idx = pi
                    best_dist = dist28
                    best_fs = gateway28
        cell = int(pos - w - 3)
        c = cost[cell]
        if c != 1000000:
            if dist13 != 1000000:
                nd = dist13 + c
                if nd < dist29:
                    dist29 = nd
                    gateway29 = gateway13
            if dist9 != 1000000:
                nd = dist9 + c
                if nd < dist29:
                    dist29 = nd
                    gateway29 = gateway9
            if dist29 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist29 < best_dist:
                    best_idx = pi
                    best_dist = dist29
                    best_fs = gateway29
        cell = int(pos + w - 3)
        c = cost[cell]
        if c != 1000000:
            if dist14 != 1000000:
                nd = dist14 + c
                if nd < dist30:
                    dist30 = nd
                    gateway30 = gateway14
            if dist9 != 1000000:
                nd = dist9 + c
                if nd < dist30:
                    dist30 = nd
                    gateway30 = gateway9
            if dist30 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist30 < best_dist:
                    best_idx = pi
                    best_dist = dist30
                    best_fs = gateway30
        cell = int(pos - w3 - 1)
        c = cost[cell]
        if c != 1000000:
            if dist15 != 1000000:
                nd = dist15 + c
                if nd < dist31:
                    dist31 = nd
                    gateway31 = gateway15
            if dist10 != 1000000:
                nd = dist10 + c
                if nd < dist31:
                    dist31 = nd
                    gateway31 = gateway10
            if dist31 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist31 < best_dist:
                    best_idx = pi
                    best_dist = dist31
                    best_fs = gateway31
        cell = int(pos + w3 - 1)
        c = cost[cell]
        if c != 1000000:
            if dist16 != 1000000:
                nd = dist16 + c
                if nd < dist32:
                    dist32 = nd
                    gateway32 = gateway16
            if dist11 != 1000000:
                nd = dist11 + c
                if nd < dist32:
                    dist32 = nd
                    gateway32 = gateway11
            if dist32 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist32 < best_dist:
                    best_idx = pi
                    best_dist = dist32
                    best_fs = gateway32
        cell = int(pos - w3 + 1)
        c = cost[cell]
        if c != 1000000:
            if dist17 != 1000000:
                nd = dist17 + c
                if nd < dist33:
                    dist33 = nd
                    gateway33 = gateway17
            if dist10 != 1000000:
                nd = dist10 + c
                if nd < dist33:
                    dist33 = nd
                    gateway33 = gateway10
            if dist33 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist33 < best_dist:
                    best_idx = pi
                    best_dist = dist33
                    best_fs = gateway33
        cell = int(pos + w3 + 1)
        c = cost[cell]
        if c != 1000000:
            if dist18 != 1000000:
                nd = dist18 + c
                if nd < dist34:
                    dist34 = nd
                    gateway34 = gateway18
            if dist11 != 1000000:
                nd = dist11 + c
                if nd < dist34:
                    dist34 = nd
                    gateway34 = gateway11
            if dist34 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist34 < best_dist:
                    best_idx = pi
                    best_dist = dist34
                    best_fs = gateway34
        cell = int(pos - w + 3)
        c = cost[cell]
        if c != 1000000:
            if dist19 != 1000000:
                nd = dist19 + c
                if nd < dist35:
                    dist35 = nd
                    gateway35 = gateway19
            if dist12 != 1000000:
                nd = dist12 + c
                if nd < dist35:
                    dist35 = nd
                    gateway35 = gateway12
            if dist35 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist35 < best_dist:
                    best_idx = pi
                    best_dist = dist35
                    best_fs = gateway35
        cell = int(pos + w + 3)
        c = cost[cell]
        if c != 1000000:
            if dist20 != 1000000:
                nd = dist20 + c
                if nd < dist36:
                    dist36 = nd
                    gateway36 = gateway20
            if dist12 != 1000000:
                nd = dist12 + c
                if nd < dist36:
                    dist36 = nd
                    gateway36 = gateway12
            if dist36 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist36 < best_dist:
                    best_idx = pi
                    best_dist = dist36
                    best_fs = gateway36
        cell = int(pos - w2 - 3)
        c = cost[cell]
        if c != 1000000:
            if dist21 != 1000000:
                nd = dist21 + c
                if nd < dist37:
                    dist37 = nd
                    gateway37 = gateway21
            if dist13 != 1000000:
                nd = dist13 + c
                if nd < dist37:
                    dist37 = nd
                    gateway37 = gateway13
            if dist37 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist37 < best_dist:
                    best_idx = pi
                    best_dist = dist37
                    best_fs = gateway37
        cell = int(pos + w2 - 3)
        c = cost[cell]
        if c != 1000000:
            if dist22 != 1000000:
                nd = dist22 + c
                if nd < dist38:
                    dist38 = nd
                    gateway38 = gateway22
            if dist14 != 1000000:
                nd = dist14 + c
                if nd < dist38:
                    dist38 = nd
                    gateway38 = gateway14
            if dist38 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist38 < best_dist:
                    best_idx = pi
                    best_dist = dist38
                    best_fs = gateway38
        cell = int(pos - w3 - 2)
        c = cost[cell]
        if c != 1000000:
            if dist21 != 1000000:
                nd = dist21 + c
                if nd < dist39:
                    dist39 = nd
                    gateway39 = gateway21
            if dist15 != 1000000:
                nd = dist15 + c
                if nd < dist39:
                    dist39 = nd
                    gateway39 = gateway15
            if dist39 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist39 < best_dist:
                    best_idx = pi
                    best_dist = dist39
                    best_fs = gateway39
        cell = int(pos + w3 - 2)
        c = cost[cell]
        if c != 1000000:
            if dist22 != 1000000:
                nd = dist22 + c
                if nd < dist40:
                    dist40 = nd
                    gateway40 = gateway22
            if dist16 != 1000000:
                nd = dist16 + c
                if nd < dist40:
                    dist40 = nd
                    gateway40 = gateway16
            if dist40 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist40 < best_dist:
                    best_idx = pi
                    best_dist = dist40
                    best_fs = gateway40
        cell = int(pos - w3 + 2)
        c = cost[cell]
        if c != 1000000:
            if dist23 != 1000000:
                nd = dist23 + c
                if nd < dist41:
                    dist41 = nd
                    gateway41 = gateway23
            if dist17 != 1000000:
                nd = dist17 + c
                if nd < dist41:
                    dist41 = nd
                    gateway41 = gateway17
            if dist41 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist41 < best_dist:
                    best_idx = pi
                    best_dist = dist41
                    best_fs = gateway41
        cell = int(pos + w3 + 2)
        c = cost[cell]
        if c != 1000000:
            if dist24 != 1000000:
                nd = dist24 + c
                if nd < dist42:
                    dist42 = nd
                    gateway42 = gateway24
            if dist18 != 1000000:
                nd = dist18 + c
                if nd < dist42:
                    dist42 = nd
                    gateway42 = gateway18
            if dist42 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist42 < best_dist:
                    best_idx = pi
                    best_dist = dist42
                    best_fs = gateway42
        cell = int(pos - w2 + 3)
        c = cost[cell]
        if c != 1000000:
            if dist23 != 1000000:
                nd = dist23 + c
                if nd < dist43:
                    dist43 = nd
                    gateway43 = gateway23
            if dist19 != 1000000:
                nd = dist19 + c
                if nd < dist43:
                    dist43 = nd
                    gateway43 = gateway19
            if dist43 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist43 < best_dist:
                    best_idx = pi
                    best_dist = dist43
                    best_fs = gateway43
        cell = int(pos + w2 + 3)
        c = cost[cell]
        if c != 1000000:
            if dist24 != 1000000:
                nd = dist24 + c
                if nd < dist44:
                    dist44 = nd
                    gateway44 = gateway24
            if dist20 != 1000000:
                nd = dist20 + c
                if nd < dist44:
                    dist44 = nd
                    gateway44 = gateway20
            if dist44 != 1000000:
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and dist44 < best_dist:
                    best_idx = pi
                    best_dist = dist44
                    best_fs = gateway44
        nx = px - 4
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000 and dist25 != 1000000:
                nd = dist25 + c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gateway25
        nx = px
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000 and dist26 != 1000000:
                nd = dist26 + c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gateway26
        nx = px
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000 and dist27 != 1000000:
                nd = dist27 + c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gateway27
        nx = px + 4
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000 and dist28 != 1000000:
                nd = dist28 + c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gateway28
        nx = px - 4
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist29 != 1000000:
                    nd = dist29 + c
                    gw_local = gateway29
                if dist25 != 1000000:
                    nd1 = dist25 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway25
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 4
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist30 != 1000000:
                    nd = dist30 + c
                    gw_local = gateway30
                if dist25 != 1000000:
                    nd1 = dist25 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway25
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 1
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist31 != 1000000:
                    nd = dist31 + c
                    gw_local = gateway31
                if dist26 != 1000000:
                    nd1 = dist26 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway26
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 1
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist32 != 1000000:
                    nd = dist32 + c
                    gw_local = gateway32
                if dist27 != 1000000:
                    nd1 = dist27 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway27
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 1
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist33 != 1000000:
                    nd = dist33 + c
                    gw_local = gateway33
                if dist26 != 1000000:
                    nd1 = dist26 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway26
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 1
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist34 != 1000000:
                    nd = dist34 + c
                    gw_local = gateway34
                if dist27 != 1000000:
                    nd1 = dist27 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway27
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 4
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist35 != 1000000:
                    nd = dist35 + c
                    gw_local = gateway35
                if dist28 != 1000000:
                    nd1 = dist28 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway28
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 4
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist36 != 1000000:
                    nd = dist36 + c
                    gw_local = gateway36
                if dist28 != 1000000:
                    nd1 = dist28 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway28
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        cell = int(pos - w3 - 3)
        c = cost[cell]
        if c != 1000000 and dist21 != 1000000:
            nd = dist21 + c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and nd < best_dist:
                best_idx = pi
                best_dist = nd
                best_fs = gateway21
        cell = int(pos + w3 - 3)
        c = cost[cell]
        if c != 1000000 and dist22 != 1000000:
            nd = dist22 + c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and nd < best_dist:
                best_idx = pi
                best_dist = nd
                best_fs = gateway22
        cell = int(pos - w3 + 3)
        c = cost[cell]
        if c != 1000000 and dist23 != 1000000:
            nd = dist23 + c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and nd < best_dist:
                best_idx = pi
                best_dist = nd
                best_fs = gateway23
        cell = int(pos + w3 + 3)
        c = cost[cell]
        if c != 1000000 and dist24 != 1000000:
            nd = dist24 + c
            pi = path_idx[cell]
            if pi > best_idx or pi == best_idx and nd < best_dist:
                best_idx = pi
                best_dist = nd
                best_fs = gateway24
        nx = px - 4
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist37 != 1000000:
                    nd = dist37 + c
                    gw_local = gateway37
                if dist29 != 1000000:
                    nd1 = dist29 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway29
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 4
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist38 != 1000000:
                    nd = dist38 + c
                    gw_local = gateway38
                if dist30 != 1000000:
                    nd1 = dist30 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway30
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 2
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist39 != 1000000:
                    nd = dist39 + c
                    gw_local = gateway39
                if dist31 != 1000000:
                    nd1 = dist31 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway31
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 2
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist40 != 1000000:
                    nd = dist40 + c
                    gw_local = gateway40
                if dist32 != 1000000:
                    nd1 = dist32 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway32
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 2
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist41 != 1000000:
                    nd = dist41 + c
                    gw_local = gateway41
                if dist33 != 1000000:
                    nd1 = dist33 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway33
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 2
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist42 != 1000000:
                    nd = dist42 + c
                    gw_local = gateway42
                if dist34 != 1000000:
                    nd1 = dist34 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway34
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 4
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist43 != 1000000:
                    nd = dist43 + c
                    gw_local = gateway43
                if dist35 != 1000000:
                    nd1 = dist35 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway35
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 4
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist44 != 1000000:
                    nd = dist44 + c
                    gw_local = gateway44
                if dist36 != 1000000:
                    nd1 = dist36 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway36
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
    else:
        nx = px - 1
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                dist1 = c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and c < best_dist:
                    best_idx = pi
                    best_dist = c
                    best_fs = 1
        nx = px - 1
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                dist2 = c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and c < best_dist:
                    best_idx = pi
                    best_dist = c
                    best_fs = 2
        nx = px + 1
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                dist3 = c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and c < best_dist:
                    best_idx = pi
                    best_dist = c
                    best_fs = 3
        nx = px + 1
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                dist4 = c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and c < best_dist:
                    best_idx = pi
                    best_dist = c
                    best_fs = 4
        nx = px - 1
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                dist5 = c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and c < best_dist:
                    best_idx = pi
                    best_dist = c
                    best_fs = 5
        nx = px
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                dist6 = c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and c < best_dist:
                    best_idx = pi
                    best_dist = c
                    best_fs = 6
        nx = px
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                dist7 = c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and c < best_dist:
                    best_idx = pi
                    best_dist = c
                    best_fs = 7
        nx = px + 1
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                dist8 = c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and c < best_dist:
                    best_idx = pi
                    best_dist = c
                    best_fs = 8
        nx = px - 2
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist5 != 1000000:
                    nd = dist5 + c
                    if nd < dist9:
                        dist9 = nd
                        gateway9 = 5
                if dist9 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist9 < best_dist:
                        best_idx = pi
                        best_dist = dist9
                        best_fs = gateway9
        nx = px
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist6 != 1000000:
                    nd = dist6 + c
                    if nd < dist10:
                        dist10 = nd
                        gateway10 = 6
                if dist10 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist10 < best_dist:
                        best_idx = pi
                        best_dist = dist10
                        best_fs = gateway10
        nx = px
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist7 != 1000000:
                    nd = dist7 + c
                    if nd < dist11:
                        dist11 = nd
                        gateway11 = 7
                if dist11 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist11 < best_dist:
                        best_idx = pi
                        best_dist = dist11
                        best_fs = gateway11
        nx = px + 2
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist8 != 1000000:
                    nd = dist8 + c
                    if nd < dist12:
                        dist12 = nd
                        gateway12 = 8
                if dist12 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist12 < best_dist:
                        best_idx = pi
                        best_dist = dist12
                        best_fs = gateway12
        nx = px - 2
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist1 != 1000000:
                    nd = dist1 + c
                    if nd < dist13:
                        dist13 = nd
                        gateway13 = 1
                if dist5 != 1000000:
                    nd = dist5 + c
                    if nd < dist13:
                        dist13 = nd
                        gateway13 = 5
                if dist13 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist13 < best_dist:
                        best_idx = pi
                        best_dist = dist13
                        best_fs = gateway13
        nx = px - 2
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist2 != 1000000:
                    nd = dist2 + c
                    if nd < dist14:
                        dist14 = nd
                        gateway14 = 2
                if dist5 != 1000000:
                    nd = dist5 + c
                    if nd < dist14:
                        dist14 = nd
                        gateway14 = 5
                if dist14 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist14 < best_dist:
                        best_idx = pi
                        best_dist = dist14
                        best_fs = gateway14
        nx = px - 1
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist1 != 1000000:
                    nd = dist1 + c
                    if nd < dist15:
                        dist15 = nd
                        gateway15 = 1
                if dist6 != 1000000:
                    nd = dist6 + c
                    if nd < dist15:
                        dist15 = nd
                        gateway15 = 6
                if dist15 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist15 < best_dist:
                        best_idx = pi
                        best_dist = dist15
                        best_fs = gateway15
        nx = px - 1
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist2 != 1000000:
                    nd = dist2 + c
                    if nd < dist16:
                        dist16 = nd
                        gateway16 = 2
                if dist7 != 1000000:
                    nd = dist7 + c
                    if nd < dist16:
                        dist16 = nd
                        gateway16 = 7
                if dist16 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist16 < best_dist:
                        best_idx = pi
                        best_dist = dist16
                        best_fs = gateway16
        nx = px + 1
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist3 != 1000000:
                    nd = dist3 + c
                    if nd < dist17:
                        dist17 = nd
                        gateway17 = 3
                if dist6 != 1000000:
                    nd = dist6 + c
                    if nd < dist17:
                        dist17 = nd
                        gateway17 = 6
                if dist17 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist17 < best_dist:
                        best_idx = pi
                        best_dist = dist17
                        best_fs = gateway17
        nx = px + 1
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist4 != 1000000:
                    nd = dist4 + c
                    if nd < dist18:
                        dist18 = nd
                        gateway18 = 4
                if dist7 != 1000000:
                    nd = dist7 + c
                    if nd < dist18:
                        dist18 = nd
                        gateway18 = 7
                if dist18 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist18 < best_dist:
                        best_idx = pi
                        best_dist = dist18
                        best_fs = gateway18
        nx = px + 2
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist3 != 1000000:
                    nd = dist3 + c
                    if nd < dist19:
                        dist19 = nd
                        gateway19 = 3
                if dist8 != 1000000:
                    nd = dist8 + c
                    if nd < dist19:
                        dist19 = nd
                        gateway19 = 8
                if dist19 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist19 < best_dist:
                        best_idx = pi
                        best_dist = dist19
                        best_fs = gateway19
        nx = px + 2
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist4 != 1000000:
                    nd = dist4 + c
                    if nd < dist20:
                        dist20 = nd
                        gateway20 = 4
                if dist8 != 1000000:
                    nd = dist8 + c
                    if nd < dist20:
                        dist20 = nd
                        gateway20 = 8
                if dist20 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist20 < best_dist:
                        best_idx = pi
                        best_dist = dist20
                        best_fs = gateway20
        nx = px - 2
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist1 != 1000000:
                    nd = dist1 + c
                    if nd < dist21:
                        dist21 = nd
                        gateway21 = 1
                if dist21 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist21 < best_dist:
                        best_idx = pi
                        best_dist = dist21
                        best_fs = gateway21
        nx = px - 2
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist2 != 1000000:
                    nd = dist2 + c
                    if nd < dist22:
                        dist22 = nd
                        gateway22 = 2
                if dist22 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist22 < best_dist:
                        best_idx = pi
                        best_dist = dist22
                        best_fs = gateway22
        nx = px + 2
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist3 != 1000000:
                    nd = dist3 + c
                    if nd < dist23:
                        dist23 = nd
                        gateway23 = 3
                if dist23 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist23 < best_dist:
                        best_idx = pi
                        best_dist = dist23
                        best_fs = gateway23
        nx = px + 2
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist4 != 1000000:
                    nd = dist4 + c
                    if nd < dist24:
                        dist24 = nd
                        gateway24 = 4
                if dist24 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist24 < best_dist:
                        best_idx = pi
                        best_dist = dist24
                        best_fs = gateway24
        nx = px - 3
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist9 != 1000000:
                    nd = dist9 + c
                    if nd < dist25:
                        dist25 = nd
                        gateway25 = gateway9
                if dist25 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist25 < best_dist:
                        best_idx = pi
                        best_dist = dist25
                        best_fs = gateway25
        nx = px
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist10 != 1000000:
                    nd = dist10 + c
                    if nd < dist26:
                        dist26 = nd
                        gateway26 = gateway10
                if dist26 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist26 < best_dist:
                        best_idx = pi
                        best_dist = dist26
                        best_fs = gateway26
        nx = px
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist11 != 1000000:
                    nd = dist11 + c
                    if nd < dist27:
                        dist27 = nd
                        gateway27 = gateway11
                if dist27 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist27 < best_dist:
                        best_idx = pi
                        best_dist = dist27
                        best_fs = gateway27
        nx = px + 3
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist12 != 1000000:
                    nd = dist12 + c
                    if nd < dist28:
                        dist28 = nd
                        gateway28 = gateway12
                if dist28 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist28 < best_dist:
                        best_idx = pi
                        best_dist = dist28
                        best_fs = gateway28
        nx = px - 3
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist13 != 1000000:
                    nd = dist13 + c
                    if nd < dist29:
                        dist29 = nd
                        gateway29 = gateway13
                if dist9 != 1000000:
                    nd = dist9 + c
                    if nd < dist29:
                        dist29 = nd
                        gateway29 = gateway9
                if dist29 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist29 < best_dist:
                        best_idx = pi
                        best_dist = dist29
                        best_fs = gateway29
        nx = px - 3
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist14 != 1000000:
                    nd = dist14 + c
                    if nd < dist30:
                        dist30 = nd
                        gateway30 = gateway14
                if dist9 != 1000000:
                    nd = dist9 + c
                    if nd < dist30:
                        dist30 = nd
                        gateway30 = gateway9
                if dist30 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist30 < best_dist:
                        best_idx = pi
                        best_dist = dist30
                        best_fs = gateway30
        nx = px - 1
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist15 != 1000000:
                    nd = dist15 + c
                    if nd < dist31:
                        dist31 = nd
                        gateway31 = gateway15
                if dist10 != 1000000:
                    nd = dist10 + c
                    if nd < dist31:
                        dist31 = nd
                        gateway31 = gateway10
                if dist31 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist31 < best_dist:
                        best_idx = pi
                        best_dist = dist31
                        best_fs = gateway31
        nx = px - 1
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist16 != 1000000:
                    nd = dist16 + c
                    if nd < dist32:
                        dist32 = nd
                        gateway32 = gateway16
                if dist11 != 1000000:
                    nd = dist11 + c
                    if nd < dist32:
                        dist32 = nd
                        gateway32 = gateway11
                if dist32 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist32 < best_dist:
                        best_idx = pi
                        best_dist = dist32
                        best_fs = gateway32
        nx = px + 1
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist17 != 1000000:
                    nd = dist17 + c
                    if nd < dist33:
                        dist33 = nd
                        gateway33 = gateway17
                if dist10 != 1000000:
                    nd = dist10 + c
                    if nd < dist33:
                        dist33 = nd
                        gateway33 = gateway10
                if dist33 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist33 < best_dist:
                        best_idx = pi
                        best_dist = dist33
                        best_fs = gateway33
        nx = px + 1
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist18 != 1000000:
                    nd = dist18 + c
                    if nd < dist34:
                        dist34 = nd
                        gateway34 = gateway18
                if dist11 != 1000000:
                    nd = dist11 + c
                    if nd < dist34:
                        dist34 = nd
                        gateway34 = gateway11
                if dist34 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist34 < best_dist:
                        best_idx = pi
                        best_dist = dist34
                        best_fs = gateway34
        nx = px + 3
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist19 != 1000000:
                    nd = dist19 + c
                    if nd < dist35:
                        dist35 = nd
                        gateway35 = gateway19
                if dist12 != 1000000:
                    nd = dist12 + c
                    if nd < dist35:
                        dist35 = nd
                        gateway35 = gateway12
                if dist35 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist35 < best_dist:
                        best_idx = pi
                        best_dist = dist35
                        best_fs = gateway35
        nx = px + 3
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist20 != 1000000:
                    nd = dist20 + c
                    if nd < dist36:
                        dist36 = nd
                        gateway36 = gateway20
                if dist12 != 1000000:
                    nd = dist12 + c
                    if nd < dist36:
                        dist36 = nd
                        gateway36 = gateway12
                if dist36 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist36 < best_dist:
                        best_idx = pi
                        best_dist = dist36
                        best_fs = gateway36
        nx = px - 3
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist21 != 1000000:
                    nd = dist21 + c
                    if nd < dist37:
                        dist37 = nd
                        gateway37 = gateway21
                if dist13 != 1000000:
                    nd = dist13 + c
                    if nd < dist37:
                        dist37 = nd
                        gateway37 = gateway13
                if dist37 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist37 < best_dist:
                        best_idx = pi
                        best_dist = dist37
                        best_fs = gateway37
        nx = px - 3
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist22 != 1000000:
                    nd = dist22 + c
                    if nd < dist38:
                        dist38 = nd
                        gateway38 = gateway22
                if dist14 != 1000000:
                    nd = dist14 + c
                    if nd < dist38:
                        dist38 = nd
                        gateway38 = gateway14
                if dist38 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist38 < best_dist:
                        best_idx = pi
                        best_dist = dist38
                        best_fs = gateway38
        nx = px - 2
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist21 != 1000000:
                    nd = dist21 + c
                    if nd < dist39:
                        dist39 = nd
                        gateway39 = gateway21
                if dist15 != 1000000:
                    nd = dist15 + c
                    if nd < dist39:
                        dist39 = nd
                        gateway39 = gateway15
                if dist39 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist39 < best_dist:
                        best_idx = pi
                        best_dist = dist39
                        best_fs = gateway39
        nx = px - 2
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist22 != 1000000:
                    nd = dist22 + c
                    if nd < dist40:
                        dist40 = nd
                        gateway40 = gateway22
                if dist16 != 1000000:
                    nd = dist16 + c
                    if nd < dist40:
                        dist40 = nd
                        gateway40 = gateway16
                if dist40 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist40 < best_dist:
                        best_idx = pi
                        best_dist = dist40
                        best_fs = gateway40
        nx = px + 2
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist23 != 1000000:
                    nd = dist23 + c
                    if nd < dist41:
                        dist41 = nd
                        gateway41 = gateway23
                if dist17 != 1000000:
                    nd = dist17 + c
                    if nd < dist41:
                        dist41 = nd
                        gateway41 = gateway17
                if dist41 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist41 < best_dist:
                        best_idx = pi
                        best_dist = dist41
                        best_fs = gateway41
        nx = px + 2
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist24 != 1000000:
                    nd = dist24 + c
                    if nd < dist42:
                        dist42 = nd
                        gateway42 = gateway24
                if dist18 != 1000000:
                    nd = dist18 + c
                    if nd < dist42:
                        dist42 = nd
                        gateway42 = gateway18
                if dist42 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist42 < best_dist:
                        best_idx = pi
                        best_dist = dist42
                        best_fs = gateway42
        nx = px + 3
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist23 != 1000000:
                    nd = dist23 + c
                    if nd < dist43:
                        dist43 = nd
                        gateway43 = gateway23
                if dist19 != 1000000:
                    nd = dist19 + c
                    if nd < dist43:
                        dist43 = nd
                        gateway43 = gateway19
                if dist43 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist43 < best_dist:
                        best_idx = pi
                        best_dist = dist43
                        best_fs = gateway43
        nx = px + 3
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                if dist24 != 1000000:
                    nd = dist24 + c
                    if nd < dist44:
                        dist44 = nd
                        gateway44 = gateway24
                if dist20 != 1000000:
                    nd = dist20 + c
                    if nd < dist44:
                        dist44 = nd
                        gateway44 = gateway20
                if dist44 != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and dist44 < best_dist:
                        best_idx = pi
                        best_dist = dist44
                        best_fs = gateway44
        nx = px - 4
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000 and dist25 != 1000000:
                nd = dist25 + c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gateway25
        nx = px
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000 and dist26 != 1000000:
                nd = dist26 + c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gateway26
        nx = px
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000 and dist27 != 1000000:
                nd = dist27 + c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gateway27
        nx = px + 4
        ny = py
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000 and dist28 != 1000000:
                nd = dist28 + c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gateway28
        nx = px - 4
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist29 != 1000000:
                    nd = dist29 + c
                    gw_local = gateway29
                if dist25 != 1000000:
                    nd1 = dist25 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway25
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 4
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist30 != 1000000:
                    nd = dist30 + c
                    gw_local = gateway30
                if dist25 != 1000000:
                    nd1 = dist25 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway25
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 1
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist31 != 1000000:
                    nd = dist31 + c
                    gw_local = gateway31
                if dist26 != 1000000:
                    nd1 = dist26 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway26
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 1
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist32 != 1000000:
                    nd = dist32 + c
                    gw_local = gateway32
                if dist27 != 1000000:
                    nd1 = dist27 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway27
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 1
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist33 != 1000000:
                    nd = dist33 + c
                    gw_local = gateway33
                if dist26 != 1000000:
                    nd1 = dist26 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway26
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 1
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist34 != 1000000:
                    nd = dist34 + c
                    gw_local = gateway34
                if dist27 != 1000000:
                    nd1 = dist27 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway27
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 4
        ny = py - 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist35 != 1000000:
                    nd = dist35 + c
                    gw_local = gateway35
                if dist28 != 1000000:
                    nd1 = dist28 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway28
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 4
        ny = py + 1
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist36 != 1000000:
                    nd = dist36 + c
                    gw_local = gateway36
                if dist28 != 1000000:
                    nd1 = dist28 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway28
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 3
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000 and dist21 != 1000000:
                nd = dist21 + c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gateway21
        nx = px - 3
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000 and dist22 != 1000000:
                nd = dist22 + c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gateway22
        nx = px + 3
        ny = py - 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000 and dist23 != 1000000:
                nd = dist23 + c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gateway23
        nx = px + 3
        ny = py + 3
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000 and dist24 != 1000000:
                nd = dist24 + c
                pi = path_idx[cell]
                if pi > best_idx or pi == best_idx and nd < best_dist:
                    best_idx = pi
                    best_dist = nd
                    best_fs = gateway24
        nx = px - 4
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist37 != 1000000:
                    nd = dist37 + c
                    gw_local = gateway37
                if dist29 != 1000000:
                    nd1 = dist29 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway29
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 4
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist38 != 1000000:
                    nd = dist38 + c
                    gw_local = gateway38
                if dist30 != 1000000:
                    nd1 = dist30 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway30
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 2
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist39 != 1000000:
                    nd = dist39 + c
                    gw_local = gateway39
                if dist31 != 1000000:
                    nd1 = dist31 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway31
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px - 2
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist40 != 1000000:
                    nd = dist40 + c
                    gw_local = gateway40
                if dist32 != 1000000:
                    nd1 = dist32 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway32
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 2
        ny = py - 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist41 != 1000000:
                    nd = dist41 + c
                    gw_local = gateway41
                if dist33 != 1000000:
                    nd1 = dist33 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway33
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 2
        ny = py + 4
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist42 != 1000000:
                    nd = dist42 + c
                    gw_local = gateway42
                if dist34 != 1000000:
                    nd1 = dist34 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway34
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 4
        ny = py - 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist43 != 1000000:
                    nd = dist43 + c
                    gw_local = gateway43
                if dist35 != 1000000:
                    nd1 = dist35 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway35
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
        nx = px + 4
        ny = py + 2
        if 0 <= nx and nx < w and 0 <= ny and ny < h:
            cell = int(ny * w + nx)
            c = cost[cell]
            if c != 1000000:
                nd = 1000000
                gw_local: int = -1
                if dist44 != 1000000:
                    nd = dist44 + c
                    gw_local = gateway44
                if dist36 != 1000000:
                    nd1 = dist36 + c
                    if nd1 < nd:
                        nd = nd1
                        gw_local = gateway36
                if nd != 1000000:
                    pi = path_idx[cell]
                    if pi > best_idx or pi == best_idx and nd < best_dist:
                        best_idx = pi
                        best_dist = nd
                        best_fs = gw_local
    if best_fs < 0:
        return pos
    if best_fs == 1:
        return pos - w - 1
    if best_fs == 2:
        return pos + w - 1
    if best_fs == 3:
        return pos - w + 1
    if best_fs == 4:
        return pos + w + 1
    if best_fs == 5:
        return pos - 1
    if best_fs == 6:
        return pos - w
    if best_fs == 7:
        return pos + w
    if best_fs == 8:
        return pos + 1
    return pos
