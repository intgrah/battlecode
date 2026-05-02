//! DP path-follower: unrolled outward-expanding 69-cell scan with interior fast path.

use crate::util::constants::INF;

/// Hop-only DP: max `path_idx` among reachable cells, only considering
/// cells with `path_idx > min_idx`. Returns `pos` if no such cell is
/// found (caller treats that as "no forward progress, replan").
#[allow(unused_assignments)]
#[must_use]
pub fn dp_step_hop(w: i32, cost: &[i32], h: i32, pos: i32, path_idx: &[i32], min_idx: i32) -> i32 {
    let px = pos % w;
    let py = pos / w;
    let w2 = w + w;
    let w3 = w2 + w;
    let w4 = w3 + w;

    let mut reach1 = false;
    let mut gateway1: i32 = -1;
    let mut reach2 = false;
    let mut gateway2: i32 = -1;
    let mut reach3 = false;
    let mut gateway3: i32 = -1;
    let mut reach4 = false;
    let mut gateway4: i32 = -1;
    let mut reach5 = false;
    let mut gateway5: i32 = -1;
    let mut reach6 = false;
    let mut gateway6: i32 = -1;
    let mut reach7 = false;
    let mut gateway7: i32 = -1;
    let mut reach8 = false;
    let mut gateway8: i32 = -1;
    let mut reach9 = false;
    let mut gateway9: i32 = -1;
    let mut reach10 = false;
    let mut gateway10: i32 = -1;
    let mut reach11 = false;
    let mut gateway11: i32 = -1;
    let mut reach12 = false;
    let mut gateway12: i32 = -1;
    let mut reach13 = false;
    let mut gateway13: i32 = -1;
    let mut reach14 = false;
    let mut gateway14: i32 = -1;
    let mut reach15 = false;
    let mut gateway15: i32 = -1;
    let mut reach16 = false;
    let mut gateway16: i32 = -1;
    let mut reach17 = false;
    let mut gateway17: i32 = -1;
    let mut reach18 = false;
    let mut gateway18: i32 = -1;
    let mut reach19 = false;
    let mut gateway19: i32 = -1;
    let mut reach20 = false;
    let mut gateway20: i32 = -1;
    let mut reach21 = false;
    let mut gateway21: i32 = -1;
    let mut reach22 = false;
    let mut gateway22: i32 = -1;
    let mut reach23 = false;
    let mut gateway23: i32 = -1;
    let mut reach24 = false;
    let mut gateway24: i32 = -1;
    let mut reach25 = false;
    let mut gateway25: i32 = -1;
    let mut reach26 = false;
    let mut gateway26: i32 = -1;
    let mut reach27 = false;
    let mut gateway27: i32 = -1;
    let mut reach28 = false;
    let mut gateway28: i32 = -1;
    let mut reach29 = false;
    let mut gateway29: i32 = -1;
    let mut reach30 = false;
    let mut gateway30: i32 = -1;
    let mut reach31 = false;
    let mut gateway31: i32 = -1;
    let mut reach32 = false;
    let mut gateway32: i32 = -1;
    let mut reach33 = false;
    let mut gateway33: i32 = -1;
    let mut reach34 = false;
    let mut gateway34: i32 = -1;
    let mut reach35 = false;
    let mut gateway35: i32 = -1;
    let mut reach36 = false;
    let mut gateway36: i32 = -1;
    let mut reach37 = false;
    let mut gateway37: i32 = -1;
    let mut reach38 = false;
    let mut gateway38: i32 = -1;
    let mut reach39 = false;
    let mut gateway39: i32 = -1;
    let mut reach40 = false;
    let mut gateway40: i32 = -1;
    let mut reach41 = false;
    let mut gateway41: i32 = -1;
    let mut reach42 = false;
    let mut gateway42: i32 = -1;
    let mut reach43 = false;
    let mut gateway43: i32 = -1;
    let mut reach44 = false;
    let mut gateway44: i32 = -1;
    let mut reach45 = false;
    let mut gateway45: i32 = -1;
    let mut reach46 = false;
    let mut gateway46: i32 = -1;
    let mut reach47 = false;
    let mut gateway47: i32 = -1;
    let mut reach48 = false;
    let mut gateway48: i32 = -1;
    let mut reach49 = false;
    let mut gateway49: i32 = -1;
    let mut reach50 = false;
    let mut gateway50: i32 = -1;
    let mut reach51 = false;
    let mut gateway51: i32 = -1;
    let mut reach52 = false;
    let mut gateway52: i32 = -1;
    let mut reach53 = false;
    let mut gateway53: i32 = -1;
    let mut reach54 = false;
    let mut gateway54: i32 = -1;
    let mut reach55 = false;
    let mut gateway55: i32 = -1;
    let mut reach56 = false;
    let mut gateway56: i32 = -1;
    let mut reach57 = false;
    let mut gateway57: i32 = -1;
    let mut reach58 = false;
    let mut gateway58: i32 = -1;
    let mut reach59 = false;
    let mut gateway59: i32 = -1;
    let mut reach60 = false;
    let mut gateway60: i32 = -1;
    let mut reach61 = false;
    let mut gateway61: i32 = -1;
    let mut reach62 = false;
    let mut gateway62: i32 = -1;
    let mut reach63 = false;
    let mut gateway63: i32 = -1;
    let mut reach64 = false;
    let mut gateway64: i32 = -1;
    let mut reach65 = false;
    let mut gateway65: i32 = -1;
    let mut reach66 = false;
    let mut gateway66: i32 = -1;
    let mut reach67 = false;
    let mut gateway67: i32 = -1;
    let mut reach68 = false;
    let mut gateway68: i32 = -1;
    let mut best_idx = min_idx;
    let mut best_fs: i32 = -1;
    if 4 <= px && px < w - 4 && 4 <= py && py < h - 4 {
        // cell 1: (-1, -1)
        let cell = (pos - w - 1) as usize;
        if cost[cell] != INF {
            reach1 = true;
            gateway1 = 1;
            let pi = path_idx[cell];
            if pi > best_idx {
                best_idx = pi;
                best_fs = gateway1;
            }
        }
        // cell 2: (-1, 1)
        let cell = (pos + w - 1) as usize;
        if cost[cell] != INF {
            reach2 = true;
            gateway2 = 2;
            let pi = path_idx[cell];
            if pi > best_idx {
                best_idx = pi;
                best_fs = gateway2;
            }
        }
        // cell 3: (1, -1)
        let cell = (pos - w + 1) as usize;
        if cost[cell] != INF {
            reach3 = true;
            gateway3 = 3;
            let pi = path_idx[cell];
            if pi > best_idx {
                best_idx = pi;
                best_fs = gateway3;
            }
        }
        // cell 4: (1, 1)
        let cell = (pos + w + 1) as usize;
        if cost[cell] != INF {
            reach4 = true;
            gateway4 = 4;
            let pi = path_idx[cell];
            if pi > best_idx {
                best_idx = pi;
                best_fs = gateway4;
            }
        }
        // cell 5: (-1, 0)
        let cell = (pos - 1) as usize;
        if cost[cell] != INF {
            reach5 = true;
            gateway5 = 5;
            let pi = path_idx[cell];
            if pi > best_idx {
                best_idx = pi;
                best_fs = gateway5;
            }
        }
        // cell 6: (0, -1)
        let cell = (pos - w) as usize;
        if cost[cell] != INF {
            reach6 = true;
            gateway6 = 6;
            let pi = path_idx[cell];
            if pi > best_idx {
                best_idx = pi;
                best_fs = gateway6;
            }
        }
        // cell 7: (0, 1)
        let cell = (pos + w) as usize;
        if cost[cell] != INF {
            reach7 = true;
            gateway7 = 7;
            let pi = path_idx[cell];
            if pi > best_idx {
                best_idx = pi;
                best_fs = gateway7;
            }
        }
        // cell 8: (1, 0)
        let cell = (pos + 1) as usize;
        if cost[cell] != INF {
            reach8 = true;
            gateway8 = 8;
            let pi = path_idx[cell];
            if pi > best_idx {
                best_idx = pi;
                best_fs = gateway8;
            }
        }
        // cell 9: (-2, 0)
        let cell = (pos - 2) as usize;
        if cost[cell] != INF {
            if reach5 {
                reach9 = true;
                gateway9 = gateway5;
            }
            if reach9 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway9;
                }
            }
        }
        // cell 10: (0, -2)
        let cell = (pos - w2) as usize;
        if cost[cell] != INF {
            if reach6 {
                reach10 = true;
                gateway10 = gateway6;
            }
            if reach10 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway10;
                }
            }
        }
        // cell 11: (0, 2)
        let cell = (pos + w2) as usize;
        if cost[cell] != INF {
            if reach7 {
                reach11 = true;
                gateway11 = gateway7;
            }
            if reach11 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway11;
                }
            }
        }
        // cell 12: (2, 0)
        let cell = (pos + 2) as usize;
        if cost[cell] != INF {
            if reach8 {
                reach12 = true;
                gateway12 = gateway8;
            }
            if reach12 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway12;
                }
            }
        }
        // cell 13: (-2, -1)
        let cell = (pos - w - 2) as usize;
        if cost[cell] != INF {
            if reach1 {
                reach13 = true;
                gateway13 = gateway1;
            } else if reach5 {
                reach13 = true;
                gateway13 = gateway5;
            }
            if reach13 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway13;
                }
            }
        }
        // cell 14: (-2, 1)
        let cell = (pos + w - 2) as usize;
        if cost[cell] != INF {
            if reach2 {
                reach14 = true;
                gateway14 = gateway2;
            } else if reach5 {
                reach14 = true;
                gateway14 = gateway5;
            }
            if reach14 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway14;
                }
            }
        }
        // cell 15: (-1, -2)
        let cell = (pos - w2 - 1) as usize;
        if cost[cell] != INF {
            if reach1 {
                reach15 = true;
                gateway15 = gateway1;
            } else if reach6 {
                reach15 = true;
                gateway15 = gateway6;
            }
            if reach15 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway15;
                }
            }
        }
        // cell 16: (-1, 2)
        let cell = (pos + w2 - 1) as usize;
        if cost[cell] != INF {
            if reach2 {
                reach16 = true;
                gateway16 = gateway2;
            } else if reach7 {
                reach16 = true;
                gateway16 = gateway7;
            }
            if reach16 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway16;
                }
            }
        }
        // cell 17: (1, -2)
        let cell = (pos - w2 + 1) as usize;
        if cost[cell] != INF {
            if reach3 {
                reach17 = true;
                gateway17 = gateway3;
            } else if reach6 {
                reach17 = true;
                gateway17 = gateway6;
            }
            if reach17 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway17;
                }
            }
        }
        // cell 18: (1, 2)
        let cell = (pos + w2 + 1) as usize;
        if cost[cell] != INF {
            if reach4 {
                reach18 = true;
                gateway18 = gateway4;
            } else if reach7 {
                reach18 = true;
                gateway18 = gateway7;
            }
            if reach18 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway18;
                }
            }
        }
        // cell 19: (2, -1)
        let cell = (pos - w + 2) as usize;
        if cost[cell] != INF {
            if reach3 {
                reach19 = true;
                gateway19 = gateway3;
            } else if reach8 {
                reach19 = true;
                gateway19 = gateway8;
            }
            if reach19 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway19;
                }
            }
        }
        // cell 20: (2, 1)
        let cell = (pos + w + 2) as usize;
        if cost[cell] != INF {
            if reach4 {
                reach20 = true;
                gateway20 = gateway4;
            } else if reach8 {
                reach20 = true;
                gateway20 = gateway8;
            }
            if reach20 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway20;
                }
            }
        }
        // cell 21: (-2, -2)
        let cell = (pos - w2 - 2) as usize;
        if cost[cell] != INF {
            if reach1 {
                reach21 = true;
                gateway21 = gateway1;
            }
            if reach21 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway21;
                }
            }
        }
        // cell 22: (-2, 2)
        let cell = (pos + w2 - 2) as usize;
        if cost[cell] != INF {
            if reach2 {
                reach22 = true;
                gateway22 = gateway2;
            }
            if reach22 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway22;
                }
            }
        }
        // cell 23: (2, -2)
        let cell = (pos - w2 + 2) as usize;
        if cost[cell] != INF {
            if reach3 {
                reach23 = true;
                gateway23 = gateway3;
            }
            if reach23 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway23;
                }
            }
        }
        // cell 24: (2, 2)
        let cell = (pos + w2 + 2) as usize;
        if cost[cell] != INF {
            if reach4 {
                reach24 = true;
                gateway24 = gateway4;
            }
            if reach24 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway24;
                }
            }
        }
        // cell 25: (-3, 0)
        let cell = (pos - 3) as usize;
        if cost[cell] != INF {
            if reach9 {
                reach25 = true;
                gateway25 = gateway9;
            }
            if reach25 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway25;
                }
            }
        }
        // cell 26: (0, -3)
        let cell = (pos - w3) as usize;
        if cost[cell] != INF {
            if reach10 {
                reach26 = true;
                gateway26 = gateway10;
            }
            if reach26 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway26;
                }
            }
        }
        // cell 27: (0, 3)
        let cell = (pos + w3) as usize;
        if cost[cell] != INF {
            if reach11 {
                reach27 = true;
                gateway27 = gateway11;
            }
            if reach27 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway27;
                }
            }
        }
        // cell 28: (3, 0)
        let cell = (pos + 3) as usize;
        if cost[cell] != INF {
            if reach12 {
                reach28 = true;
                gateway28 = gateway12;
            }
            if reach28 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway28;
                }
            }
        }
        // cell 29: (-3, -1)
        let cell = (pos - w - 3) as usize;
        if cost[cell] != INF {
            if reach13 {
                reach29 = true;
                gateway29 = gateway13;
            } else if reach9 {
                reach29 = true;
                gateway29 = gateway9;
            }
            if reach29 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway29;
                }
            }
        }
        // cell 30: (-3, 1)
        let cell = (pos + w - 3) as usize;
        if cost[cell] != INF {
            if reach14 {
                reach30 = true;
                gateway30 = gateway14;
            } else if reach9 {
                reach30 = true;
                gateway30 = gateway9;
            }
            if reach30 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway30;
                }
            }
        }
        // cell 31: (-1, -3)
        let cell = (pos - w3 - 1) as usize;
        if cost[cell] != INF {
            if reach15 {
                reach31 = true;
                gateway31 = gateway15;
            } else if reach10 {
                reach31 = true;
                gateway31 = gateway10;
            }
            if reach31 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway31;
                }
            }
        }
        // cell 32: (-1, 3)
        let cell = (pos + w3 - 1) as usize;
        if cost[cell] != INF {
            if reach16 {
                reach32 = true;
                gateway32 = gateway16;
            } else if reach11 {
                reach32 = true;
                gateway32 = gateway11;
            }
            if reach32 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway32;
                }
            }
        }
        // cell 33: (1, -3)
        let cell = (pos - w3 + 1) as usize;
        if cost[cell] != INF {
            if reach17 {
                reach33 = true;
                gateway33 = gateway17;
            } else if reach10 {
                reach33 = true;
                gateway33 = gateway10;
            }
            if reach33 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway33;
                }
            }
        }
        // cell 34: (1, 3)
        let cell = (pos + w3 + 1) as usize;
        if cost[cell] != INF {
            if reach18 {
                reach34 = true;
                gateway34 = gateway18;
            } else if reach11 {
                reach34 = true;
                gateway34 = gateway11;
            }
            if reach34 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway34;
                }
            }
        }
        // cell 35: (3, -1)
        let cell = (pos - w + 3) as usize;
        if cost[cell] != INF {
            if reach19 {
                reach35 = true;
                gateway35 = gateway19;
            } else if reach12 {
                reach35 = true;
                gateway35 = gateway12;
            }
            if reach35 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway35;
                }
            }
        }
        // cell 36: (3, 1)
        let cell = (pos + w + 3) as usize;
        if cost[cell] != INF {
            if reach20 {
                reach36 = true;
                gateway36 = gateway20;
            } else if reach12 {
                reach36 = true;
                gateway36 = gateway12;
            }
            if reach36 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway36;
                }
            }
        }
        // cell 37: (-3, -2)
        let cell = (pos - w2 - 3) as usize;
        if cost[cell] != INF {
            if reach21 {
                reach37 = true;
                gateway37 = gateway21;
            } else if reach13 {
                reach37 = true;
                gateway37 = gateway13;
            }
            if reach37 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway37;
                }
            }
        }
        // cell 38: (-3, 2)
        let cell = (pos + w2 - 3) as usize;
        if cost[cell] != INF {
            if reach22 {
                reach38 = true;
                gateway38 = gateway22;
            } else if reach14 {
                reach38 = true;
                gateway38 = gateway14;
            }
            if reach38 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway38;
                }
            }
        }
        // cell 39: (-2, -3)
        let cell = (pos - w3 - 2) as usize;
        if cost[cell] != INF {
            if reach21 {
                reach39 = true;
                gateway39 = gateway21;
            } else if reach15 {
                reach39 = true;
                gateway39 = gateway15;
            }
            if reach39 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway39;
                }
            }
        }
        // cell 40: (-2, 3)
        let cell = (pos + w3 - 2) as usize;
        if cost[cell] != INF {
            if reach22 {
                reach40 = true;
                gateway40 = gateway22;
            } else if reach16 {
                reach40 = true;
                gateway40 = gateway16;
            }
            if reach40 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway40;
                }
            }
        }
        // cell 41: (2, -3)
        let cell = (pos - w3 + 2) as usize;
        if cost[cell] != INF {
            if reach23 {
                reach41 = true;
                gateway41 = gateway23;
            } else if reach17 {
                reach41 = true;
                gateway41 = gateway17;
            }
            if reach41 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway41;
                }
            }
        }
        // cell 42: (2, 3)
        let cell = (pos + w3 + 2) as usize;
        if cost[cell] != INF {
            if reach24 {
                reach42 = true;
                gateway42 = gateway24;
            } else if reach18 {
                reach42 = true;
                gateway42 = gateway18;
            }
            if reach42 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway42;
                }
            }
        }
        // cell 43: (3, -2)
        let cell = (pos - w2 + 3) as usize;
        if cost[cell] != INF {
            if reach23 {
                reach43 = true;
                gateway43 = gateway23;
            } else if reach19 {
                reach43 = true;
                gateway43 = gateway19;
            }
            if reach43 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway43;
                }
            }
        }
        // cell 44: (3, 2)
        let cell = (pos + w2 + 3) as usize;
        if cost[cell] != INF {
            if reach24 {
                reach44 = true;
                gateway44 = gateway24;
            } else if reach20 {
                reach44 = true;
                gateway44 = gateway20;
            }
            if reach44 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway44;
                }
            }
        }
        // cell 45: (-4, 0)
        let cell = (pos - 4) as usize;
        if cost[cell] != INF {
            if reach25 {
                reach45 = true;
                gateway45 = gateway25;
            }
            if reach45 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway45;
                }
            }
        }
        // cell 46: (0, -4)
        let cell = (pos - w4) as usize;
        if cost[cell] != INF {
            if reach26 {
                reach46 = true;
                gateway46 = gateway26;
            }
            if reach46 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway46;
                }
            }
        }
        // cell 47: (0, 4)
        let cell = (pos + w4) as usize;
        if cost[cell] != INF {
            if reach27 {
                reach47 = true;
                gateway47 = gateway27;
            }
            if reach47 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway47;
                }
            }
        }
        // cell 48: (4, 0)
        let cell = (pos + 4) as usize;
        if cost[cell] != INF {
            if reach28 {
                reach48 = true;
                gateway48 = gateway28;
            }
            if reach48 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway48;
                }
            }
        }
        // cell 49: (-4, -1)
        let cell = (pos - w - 4) as usize;
        if cost[cell] != INF {
            if reach29 {
                reach49 = true;
                gateway49 = gateway29;
            } else if reach25 {
                reach49 = true;
                gateway49 = gateway25;
            }
            if reach49 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway49;
                }
            }
        }
        // cell 50: (-4, 1)
        let cell = (pos + w - 4) as usize;
        if cost[cell] != INF {
            if reach30 {
                reach50 = true;
                gateway50 = gateway30;
            } else if reach25 {
                reach50 = true;
                gateway50 = gateway25;
            }
            if reach50 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway50;
                }
            }
        }
        // cell 51: (-1, -4)
        let cell = (pos - w4 - 1) as usize;
        if cost[cell] != INF {
            if reach31 {
                reach51 = true;
                gateway51 = gateway31;
            } else if reach26 {
                reach51 = true;
                gateway51 = gateway26;
            }
            if reach51 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway51;
                }
            }
        }
        // cell 52: (-1, 4)
        let cell = (pos + w4 - 1) as usize;
        if cost[cell] != INF {
            if reach32 {
                reach52 = true;
                gateway52 = gateway32;
            } else if reach27 {
                reach52 = true;
                gateway52 = gateway27;
            }
            if reach52 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway52;
                }
            }
        }
        // cell 53: (1, -4)
        let cell = (pos - w4 + 1) as usize;
        if cost[cell] != INF {
            if reach33 {
                reach53 = true;
                gateway53 = gateway33;
            } else if reach26 {
                reach53 = true;
                gateway53 = gateway26;
            }
            if reach53 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway53;
                }
            }
        }
        // cell 54: (1, 4)
        let cell = (pos + w4 + 1) as usize;
        if cost[cell] != INF {
            if reach34 {
                reach54 = true;
                gateway54 = gateway34;
            } else if reach27 {
                reach54 = true;
                gateway54 = gateway27;
            }
            if reach54 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway54;
                }
            }
        }
        // cell 55: (4, -1)
        let cell = (pos - w + 4) as usize;
        if cost[cell] != INF {
            if reach35 {
                reach55 = true;
                gateway55 = gateway35;
            } else if reach28 {
                reach55 = true;
                gateway55 = gateway28;
            }
            if reach55 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway55;
                }
            }
        }
        // cell 56: (4, 1)
        let cell = (pos + w + 4) as usize;
        if cost[cell] != INF {
            if reach36 {
                reach56 = true;
                gateway56 = gateway36;
            } else if reach28 {
                reach56 = true;
                gateway56 = gateway28;
            }
            if reach56 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway56;
                }
            }
        }
        // cell 57: (-3, -3)
        let cell = (pos - w3 - 3) as usize;
        if cost[cell] != INF {
            if reach21 {
                reach57 = true;
                gateway57 = gateway21;
            }
            if reach57 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway57;
                }
            }
        }
        // cell 58: (-3, 3)
        let cell = (pos + w3 - 3) as usize;
        if cost[cell] != INF {
            if reach22 {
                reach58 = true;
                gateway58 = gateway22;
            }
            if reach58 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway58;
                }
            }
        }
        // cell 59: (3, -3)
        let cell = (pos - w3 + 3) as usize;
        if cost[cell] != INF {
            if reach23 {
                reach59 = true;
                gateway59 = gateway23;
            }
            if reach59 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway59;
                }
            }
        }
        // cell 60: (3, 3)
        let cell = (pos + w3 + 3) as usize;
        if cost[cell] != INF {
            if reach24 {
                reach60 = true;
                gateway60 = gateway24;
            }
            if reach60 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway60;
                }
            }
        }
        // cell 61: (-4, -2)
        let cell = (pos - w2 - 4) as usize;
        if cost[cell] != INF {
            if reach37 {
                reach61 = true;
                gateway61 = gateway37;
            } else if reach29 {
                reach61 = true;
                gateway61 = gateway29;
            }
            if reach61 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway61;
                }
            }
        }
        // cell 62: (-4, 2)
        let cell = (pos + w2 - 4) as usize;
        if cost[cell] != INF {
            if reach38 {
                reach62 = true;
                gateway62 = gateway38;
            } else if reach30 {
                reach62 = true;
                gateway62 = gateway30;
            }
            if reach62 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway62;
                }
            }
        }
        // cell 63: (-2, -4)
        let cell = (pos - w4 - 2) as usize;
        if cost[cell] != INF {
            if reach39 {
                reach63 = true;
                gateway63 = gateway39;
            } else if reach31 {
                reach63 = true;
                gateway63 = gateway31;
            }
            if reach63 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway63;
                }
            }
        }
        // cell 64: (-2, 4)
        let cell = (pos + w4 - 2) as usize;
        if cost[cell] != INF {
            if reach40 {
                reach64 = true;
                gateway64 = gateway40;
            } else if reach32 {
                reach64 = true;
                gateway64 = gateway32;
            }
            if reach64 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway64;
                }
            }
        }
        // cell 65: (2, -4)
        let cell = (pos - w4 + 2) as usize;
        if cost[cell] != INF {
            if reach41 {
                reach65 = true;
                gateway65 = gateway41;
            } else if reach33 {
                reach65 = true;
                gateway65 = gateway33;
            }
            if reach65 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway65;
                }
            }
        }
        // cell 66: (2, 4)
        let cell = (pos + w4 + 2) as usize;
        if cost[cell] != INF {
            if reach42 {
                reach66 = true;
                gateway66 = gateway42;
            } else if reach34 {
                reach66 = true;
                gateway66 = gateway34;
            }
            if reach66 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway66;
                }
            }
        }
        // cell 67: (4, -2)
        let cell = (pos - w2 + 4) as usize;
        if cost[cell] != INF {
            if reach43 {
                reach67 = true;
                gateway67 = gateway43;
            } else if reach35 {
                reach67 = true;
                gateway67 = gateway35;
            }
            if reach67 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway67;
                }
            }
        }
        // cell 68: (4, 2)
        let cell = (pos + w2 + 4) as usize;
        if cost[cell] != INF {
            if reach44 {
                reach68 = true;
                gateway68 = gateway44;
            } else if reach36 {
                reach68 = true;
                gateway68 = gateway36;
            }
            if reach68 {
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway68;
                }
            }
        }
    } else {
        // cell 1: (-1, -1)
        let nx = px - 1;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                reach1 = true;
                gateway1 = 1;
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway1;
                }
            }
        }
        // cell 2: (-1, 1)
        let nx = px - 1;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                reach2 = true;
                gateway2 = 2;
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway2;
                }
            }
        }
        // cell 3: (1, -1)
        let nx = px + 1;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                reach3 = true;
                gateway3 = 3;
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway3;
                }
            }
        }
        // cell 4: (1, 1)
        let nx = px + 1;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                reach4 = true;
                gateway4 = 4;
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway4;
                }
            }
        }
        // cell 5: (-1, 0)
        let nx = px - 1;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                reach5 = true;
                gateway5 = 5;
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway5;
                }
            }
        }
        // cell 6: (0, -1)
        let nx = px;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                reach6 = true;
                gateway6 = 6;
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway6;
                }
            }
        }
        // cell 7: (0, 1)
        let nx = px;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                reach7 = true;
                gateway7 = 7;
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway7;
                }
            }
        }
        // cell 8: (1, 0)
        let nx = px + 1;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                reach8 = true;
                gateway8 = 8;
                let pi = path_idx[cell];
                if pi > best_idx {
                    best_idx = pi;
                    best_fs = gateway8;
                }
            }
        }
        // cell 9: (-2, 0)
        let nx = px - 2;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach5 {
                    reach9 = true;
                    gateway9 = gateway5;
                }
                if reach9 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway9;
                    }
                }
            }
        }
        // cell 10: (0, -2)
        let nx = px;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach6 {
                    reach10 = true;
                    gateway10 = gateway6;
                }
                if reach10 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway10;
                    }
                }
            }
        }
        // cell 11: (0, 2)
        let nx = px;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach7 {
                    reach11 = true;
                    gateway11 = gateway7;
                }
                if reach11 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway11;
                    }
                }
            }
        }
        // cell 12: (2, 0)
        let nx = px + 2;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach8 {
                    reach12 = true;
                    gateway12 = gateway8;
                }
                if reach12 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway12;
                    }
                }
            }
        }
        // cell 13: (-2, -1)
        let nx = px - 2;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach1 {
                    reach13 = true;
                    gateway13 = gateway1;
                } else if reach5 {
                    reach13 = true;
                    gateway13 = gateway5;
                }
                if reach13 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway13;
                    }
                }
            }
        }
        // cell 14: (-2, 1)
        let nx = px - 2;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach2 {
                    reach14 = true;
                    gateway14 = gateway2;
                } else if reach5 {
                    reach14 = true;
                    gateway14 = gateway5;
                }
                if reach14 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway14;
                    }
                }
            }
        }
        // cell 15: (-1, -2)
        let nx = px - 1;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach1 {
                    reach15 = true;
                    gateway15 = gateway1;
                } else if reach6 {
                    reach15 = true;
                    gateway15 = gateway6;
                }
                if reach15 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway15;
                    }
                }
            }
        }
        // cell 16: (-1, 2)
        let nx = px - 1;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach2 {
                    reach16 = true;
                    gateway16 = gateway2;
                } else if reach7 {
                    reach16 = true;
                    gateway16 = gateway7;
                }
                if reach16 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway16;
                    }
                }
            }
        }
        // cell 17: (1, -2)
        let nx = px + 1;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach3 {
                    reach17 = true;
                    gateway17 = gateway3;
                } else if reach6 {
                    reach17 = true;
                    gateway17 = gateway6;
                }
                if reach17 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway17;
                    }
                }
            }
        }
        // cell 18: (1, 2)
        let nx = px + 1;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach4 {
                    reach18 = true;
                    gateway18 = gateway4;
                } else if reach7 {
                    reach18 = true;
                    gateway18 = gateway7;
                }
                if reach18 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway18;
                    }
                }
            }
        }
        // cell 19: (2, -1)
        let nx = px + 2;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach3 {
                    reach19 = true;
                    gateway19 = gateway3;
                } else if reach8 {
                    reach19 = true;
                    gateway19 = gateway8;
                }
                if reach19 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway19;
                    }
                }
            }
        }
        // cell 20: (2, 1)
        let nx = px + 2;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach4 {
                    reach20 = true;
                    gateway20 = gateway4;
                } else if reach8 {
                    reach20 = true;
                    gateway20 = gateway8;
                }
                if reach20 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway20;
                    }
                }
            }
        }
        // cell 21: (-2, -2)
        let nx = px - 2;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach1 {
                    reach21 = true;
                    gateway21 = gateway1;
                }
                if reach21 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway21;
                    }
                }
            }
        }
        // cell 22: (-2, 2)
        let nx = px - 2;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach2 {
                    reach22 = true;
                    gateway22 = gateway2;
                }
                if reach22 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway22;
                    }
                }
            }
        }
        // cell 23: (2, -2)
        let nx = px + 2;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach3 {
                    reach23 = true;
                    gateway23 = gateway3;
                }
                if reach23 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway23;
                    }
                }
            }
        }
        // cell 24: (2, 2)
        let nx = px + 2;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach4 {
                    reach24 = true;
                    gateway24 = gateway4;
                }
                if reach24 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway24;
                    }
                }
            }
        }
        // cell 25: (-3, 0)
        let nx = px - 3;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach9 {
                    reach25 = true;
                    gateway25 = gateway9;
                }
                if reach25 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway25;
                    }
                }
            }
        }
        // cell 26: (0, -3)
        let nx = px;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach10 {
                    reach26 = true;
                    gateway26 = gateway10;
                }
                if reach26 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway26;
                    }
                }
            }
        }
        // cell 27: (0, 3)
        let nx = px;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach11 {
                    reach27 = true;
                    gateway27 = gateway11;
                }
                if reach27 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway27;
                    }
                }
            }
        }
        // cell 28: (3, 0)
        let nx = px + 3;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach12 {
                    reach28 = true;
                    gateway28 = gateway12;
                }
                if reach28 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway28;
                    }
                }
            }
        }
        // cell 29: (-3, -1)
        let nx = px - 3;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach13 {
                    reach29 = true;
                    gateway29 = gateway13;
                } else if reach9 {
                    reach29 = true;
                    gateway29 = gateway9;
                }
                if reach29 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway29;
                    }
                }
            }
        }
        // cell 30: (-3, 1)
        let nx = px - 3;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach14 {
                    reach30 = true;
                    gateway30 = gateway14;
                } else if reach9 {
                    reach30 = true;
                    gateway30 = gateway9;
                }
                if reach30 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway30;
                    }
                }
            }
        }
        // cell 31: (-1, -3)
        let nx = px - 1;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach15 {
                    reach31 = true;
                    gateway31 = gateway15;
                } else if reach10 {
                    reach31 = true;
                    gateway31 = gateway10;
                }
                if reach31 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway31;
                    }
                }
            }
        }
        // cell 32: (-1, 3)
        let nx = px - 1;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach16 {
                    reach32 = true;
                    gateway32 = gateway16;
                } else if reach11 {
                    reach32 = true;
                    gateway32 = gateway11;
                }
                if reach32 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway32;
                    }
                }
            }
        }
        // cell 33: (1, -3)
        let nx = px + 1;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach17 {
                    reach33 = true;
                    gateway33 = gateway17;
                } else if reach10 {
                    reach33 = true;
                    gateway33 = gateway10;
                }
                if reach33 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway33;
                    }
                }
            }
        }
        // cell 34: (1, 3)
        let nx = px + 1;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach18 {
                    reach34 = true;
                    gateway34 = gateway18;
                } else if reach11 {
                    reach34 = true;
                    gateway34 = gateway11;
                }
                if reach34 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway34;
                    }
                }
            }
        }
        // cell 35: (3, -1)
        let nx = px + 3;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach19 {
                    reach35 = true;
                    gateway35 = gateway19;
                } else if reach12 {
                    reach35 = true;
                    gateway35 = gateway12;
                }
                if reach35 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway35;
                    }
                }
            }
        }
        // cell 36: (3, 1)
        let nx = px + 3;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach20 {
                    reach36 = true;
                    gateway36 = gateway20;
                } else if reach12 {
                    reach36 = true;
                    gateway36 = gateway12;
                }
                if reach36 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway36;
                    }
                }
            }
        }
        // cell 37: (-3, -2)
        let nx = px - 3;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach21 {
                    reach37 = true;
                    gateway37 = gateway21;
                } else if reach13 {
                    reach37 = true;
                    gateway37 = gateway13;
                }
                if reach37 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway37;
                    }
                }
            }
        }
        // cell 38: (-3, 2)
        let nx = px - 3;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach22 {
                    reach38 = true;
                    gateway38 = gateway22;
                } else if reach14 {
                    reach38 = true;
                    gateway38 = gateway14;
                }
                if reach38 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway38;
                    }
                }
            }
        }
        // cell 39: (-2, -3)
        let nx = px - 2;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach21 {
                    reach39 = true;
                    gateway39 = gateway21;
                } else if reach15 {
                    reach39 = true;
                    gateway39 = gateway15;
                }
                if reach39 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway39;
                    }
                }
            }
        }
        // cell 40: (-2, 3)
        let nx = px - 2;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach22 {
                    reach40 = true;
                    gateway40 = gateway22;
                } else if reach16 {
                    reach40 = true;
                    gateway40 = gateway16;
                }
                if reach40 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway40;
                    }
                }
            }
        }
        // cell 41: (2, -3)
        let nx = px + 2;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach23 {
                    reach41 = true;
                    gateway41 = gateway23;
                } else if reach17 {
                    reach41 = true;
                    gateway41 = gateway17;
                }
                if reach41 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway41;
                    }
                }
            }
        }
        // cell 42: (2, 3)
        let nx = px + 2;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach24 {
                    reach42 = true;
                    gateway42 = gateway24;
                } else if reach18 {
                    reach42 = true;
                    gateway42 = gateway18;
                }
                if reach42 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway42;
                    }
                }
            }
        }
        // cell 43: (3, -2)
        let nx = px + 3;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach23 {
                    reach43 = true;
                    gateway43 = gateway23;
                } else if reach19 {
                    reach43 = true;
                    gateway43 = gateway19;
                }
                if reach43 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway43;
                    }
                }
            }
        }
        // cell 44: (3, 2)
        let nx = px + 3;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach24 {
                    reach44 = true;
                    gateway44 = gateway24;
                } else if reach20 {
                    reach44 = true;
                    gateway44 = gateway20;
                }
                if reach44 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway44;
                    }
                }
            }
        }
        // cell 45: (-4, 0)
        let nx = px - 4;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach25 {
                    reach45 = true;
                    gateway45 = gateway25;
                }
                if reach45 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway45;
                    }
                }
            }
        }
        // cell 46: (0, -4)
        let nx = px;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach26 {
                    reach46 = true;
                    gateway46 = gateway26;
                }
                if reach46 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway46;
                    }
                }
            }
        }
        // cell 47: (0, 4)
        let nx = px;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach27 {
                    reach47 = true;
                    gateway47 = gateway27;
                }
                if reach47 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway47;
                    }
                }
            }
        }
        // cell 48: (4, 0)
        let nx = px + 4;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach28 {
                    reach48 = true;
                    gateway48 = gateway28;
                }
                if reach48 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway48;
                    }
                }
            }
        }
        // cell 49: (-4, -1)
        let nx = px - 4;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach29 {
                    reach49 = true;
                    gateway49 = gateway29;
                } else if reach25 {
                    reach49 = true;
                    gateway49 = gateway25;
                }
                if reach49 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway49;
                    }
                }
            }
        }
        // cell 50: (-4, 1)
        let nx = px - 4;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach30 {
                    reach50 = true;
                    gateway50 = gateway30;
                } else if reach25 {
                    reach50 = true;
                    gateway50 = gateway25;
                }
                if reach50 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway50;
                    }
                }
            }
        }
        // cell 51: (-1, -4)
        let nx = px - 1;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach31 {
                    reach51 = true;
                    gateway51 = gateway31;
                } else if reach26 {
                    reach51 = true;
                    gateway51 = gateway26;
                }
                if reach51 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway51;
                    }
                }
            }
        }
        // cell 52: (-1, 4)
        let nx = px - 1;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach32 {
                    reach52 = true;
                    gateway52 = gateway32;
                } else if reach27 {
                    reach52 = true;
                    gateway52 = gateway27;
                }
                if reach52 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway52;
                    }
                }
            }
        }
        // cell 53: (1, -4)
        let nx = px + 1;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach33 {
                    reach53 = true;
                    gateway53 = gateway33;
                } else if reach26 {
                    reach53 = true;
                    gateway53 = gateway26;
                }
                if reach53 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway53;
                    }
                }
            }
        }
        // cell 54: (1, 4)
        let nx = px + 1;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach34 {
                    reach54 = true;
                    gateway54 = gateway34;
                } else if reach27 {
                    reach54 = true;
                    gateway54 = gateway27;
                }
                if reach54 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway54;
                    }
                }
            }
        }
        // cell 55: (4, -1)
        let nx = px + 4;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach35 {
                    reach55 = true;
                    gateway55 = gateway35;
                } else if reach28 {
                    reach55 = true;
                    gateway55 = gateway28;
                }
                if reach55 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway55;
                    }
                }
            }
        }
        // cell 56: (4, 1)
        let nx = px + 4;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach36 {
                    reach56 = true;
                    gateway56 = gateway36;
                } else if reach28 {
                    reach56 = true;
                    gateway56 = gateway28;
                }
                if reach56 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway56;
                    }
                }
            }
        }
        // cell 57: (-3, -3)
        let nx = px - 3;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach21 {
                    reach57 = true;
                    gateway57 = gateway21;
                }
                if reach57 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway57;
                    }
                }
            }
        }
        // cell 58: (-3, 3)
        let nx = px - 3;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach22 {
                    reach58 = true;
                    gateway58 = gateway22;
                }
                if reach58 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway58;
                    }
                }
            }
        }
        // cell 59: (3, -3)
        let nx = px + 3;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach23 {
                    reach59 = true;
                    gateway59 = gateway23;
                }
                if reach59 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway59;
                    }
                }
            }
        }
        // cell 60: (3, 3)
        let nx = px + 3;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach24 {
                    reach60 = true;
                    gateway60 = gateway24;
                }
                if reach60 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway60;
                    }
                }
            }
        }
        // cell 61: (-4, -2)
        let nx = px - 4;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach37 {
                    reach61 = true;
                    gateway61 = gateway37;
                } else if reach29 {
                    reach61 = true;
                    gateway61 = gateway29;
                }
                if reach61 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway61;
                    }
                }
            }
        }
        // cell 62: (-4, 2)
        let nx = px - 4;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach38 {
                    reach62 = true;
                    gateway62 = gateway38;
                } else if reach30 {
                    reach62 = true;
                    gateway62 = gateway30;
                }
                if reach62 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway62;
                    }
                }
            }
        }
        // cell 63: (-2, -4)
        let nx = px - 2;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach39 {
                    reach63 = true;
                    gateway63 = gateway39;
                } else if reach31 {
                    reach63 = true;
                    gateway63 = gateway31;
                }
                if reach63 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway63;
                    }
                }
            }
        }
        // cell 64: (-2, 4)
        let nx = px - 2;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach40 {
                    reach64 = true;
                    gateway64 = gateway40;
                } else if reach32 {
                    reach64 = true;
                    gateway64 = gateway32;
                }
                if reach64 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway64;
                    }
                }
            }
        }
        // cell 65: (2, -4)
        let nx = px + 2;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach41 {
                    reach65 = true;
                    gateway65 = gateway41;
                } else if reach33 {
                    reach65 = true;
                    gateway65 = gateway33;
                }
                if reach65 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway65;
                    }
                }
            }
        }
        // cell 66: (2, 4)
        let nx = px + 2;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach42 {
                    reach66 = true;
                    gateway66 = gateway42;
                } else if reach34 {
                    reach66 = true;
                    gateway66 = gateway34;
                }
                if reach66 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway66;
                    }
                }
            }
        }
        // cell 67: (4, -2)
        let nx = px + 4;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach43 {
                    reach67 = true;
                    gateway67 = gateway43;
                } else if reach35 {
                    reach67 = true;
                    gateway67 = gateway35;
                }
                if reach67 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway67;
                    }
                }
            }
        }
        // cell 68: (4, 2)
        let nx = px + 4;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            if cost[cell] != INF {
                if reach44 {
                    reach68 = true;
                    gateway68 = gateway44;
                } else if reach36 {
                    reach68 = true;
                    gateway68 = gateway36;
                }
                if reach68 {
                    let pi = path_idx[cell];
                    if pi > best_idx {
                        best_idx = pi;
                        best_fs = gateway68;
                    }
                }
            }
        }
    }
    if best_fs < 0 {
        return pos;
    }
    if best_fs == 1 {
        return pos - w - 1;
    }
    if best_fs == 2 {
        return pos + w - 1;
    }
    if best_fs == 3 {
        return pos - w + 1;
    }
    if best_fs == 4 {
        return pos + w + 1;
    }
    if best_fs == 5 {
        return pos - 1;
    }
    if best_fs == 6 {
        return pos - w;
    }
    if best_fs == 7 {
        return pos + w;
    }
    if best_fs == 8 {
        return pos + 1;
    }
    pos
}

/// Cost-aware DP. Max `path_idx`, tiebreak min cumulative cost. Only
/// considers cells with `path_idx > min_idx` so the caller can require
/// strict forward progress along the plan; returns `pos` when no such
/// cell is reachable in the 69-cell window (caller replans).
#[allow(unused_assignments)]
#[must_use]
pub fn dp_step(w: i32, cost: &[i32], h: i32, pos: i32, path_idx: &[i32], min_idx: i32) -> i32 {
    let px = pos % w;
    let py = pos / w;
    let w2 = w + w;
    let w3 = w2 + w;
    let w4 = w3 + w;

    let mut dist1 = INF;
    let mut dist2 = INF;
    let mut dist3 = INF;
    let mut dist4 = INF;
    let mut dist5 = INF;
    let mut dist6 = INF;
    let mut dist7 = INF;
    let mut dist8 = INF;
    let mut dist9 = INF;
    let mut dist10 = INF;
    let mut dist11 = INF;
    let mut dist12 = INF;
    let mut dist13 = INF;
    let mut dist14 = INF;
    let mut dist15 = INF;
    let mut dist16 = INF;
    let mut dist17 = INF;
    let mut dist18 = INF;
    let mut dist19 = INF;
    let mut dist20 = INF;
    let mut dist21 = INF;
    let mut dist22 = INF;
    let mut dist23 = INF;
    let mut dist24 = INF;
    let mut dist25 = INF;
    let mut dist26 = INF;
    let mut dist27 = INF;
    let mut dist28 = INF;
    let mut dist29 = INF;
    let mut dist30 = INF;
    let mut dist31 = INF;
    let mut dist32 = INF;
    let mut dist33 = INF;
    let mut dist34 = INF;
    let mut dist35 = INF;
    let mut dist36 = INF;
    let mut dist37 = INF;
    let mut dist38 = INF;
    let mut dist39 = INF;
    let mut dist40 = INF;
    let mut dist41 = INF;
    let mut dist42 = INF;
    let mut dist43 = INF;
    let mut dist44 = INF;
    let mut gateway9: i32 = -1;
    let mut gateway10: i32 = -1;
    let mut gateway11: i32 = -1;
    let mut gateway12: i32 = -1;
    let mut gateway13: i32 = -1;
    let mut gateway14: i32 = -1;
    let mut gateway15: i32 = -1;
    let mut gateway16: i32 = -1;
    let mut gateway17: i32 = -1;
    let mut gateway18: i32 = -1;
    let mut gateway19: i32 = -1;
    let mut gateway20: i32 = -1;
    let mut gateway21: i32 = -1;
    let mut gateway22: i32 = -1;
    let mut gateway23: i32 = -1;
    let mut gateway24: i32 = -1;
    let mut gateway25: i32 = -1;
    let mut gateway26: i32 = -1;
    let mut gateway27: i32 = -1;
    let mut gateway28: i32 = -1;
    let mut gateway29: i32 = -1;
    let mut gateway30: i32 = -1;
    let mut gateway31: i32 = -1;
    let mut gateway32: i32 = -1;
    let mut gateway33: i32 = -1;
    let mut gateway34: i32 = -1;
    let mut gateway35: i32 = -1;
    let mut gateway36: i32 = -1;
    let mut gateway37: i32 = -1;
    let mut gateway38: i32 = -1;
    let mut gateway39: i32 = -1;
    let mut gateway40: i32 = -1;
    let mut gateway41: i32 = -1;
    let mut gateway42: i32 = -1;
    let mut gateway43: i32 = -1;
    let mut gateway44: i32 = -1;
    let mut best_idx = min_idx;
    let mut best_dist = INF;
    let mut best_fs: i32 = -1;
    if 4 <= px && px < w - 4 && 4 <= py && py < h - 4 {
        // cell 1: (-1, -1)
        let cell = (pos - w - 1) as usize;
        let c = cost[cell];
        if c != INF {
            dist1 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 1;
            }
        }
        // cell 2: (-1, 1)
        let cell = (pos + w - 1) as usize;
        let c = cost[cell];
        if c != INF {
            dist2 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 2;
            }
        }
        // cell 3: (1, -1)
        let cell = (pos - w + 1) as usize;
        let c = cost[cell];
        if c != INF {
            dist3 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 3;
            }
        }
        // cell 4: (1, 1)
        let cell = (pos + w + 1) as usize;
        let c = cost[cell];
        if c != INF {
            dist4 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 4;
            }
        }
        // cell 5: (-1, 0)
        let cell = (pos - 1) as usize;
        let c = cost[cell];
        if c != INF {
            dist5 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 5;
            }
        }
        // cell 6: (0, -1)
        let cell = (pos - w) as usize;
        let c = cost[cell];
        if c != INF {
            dist6 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 6;
            }
        }
        // cell 7: (0, 1)
        let cell = (pos + w) as usize;
        let c = cost[cell];
        if c != INF {
            dist7 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 7;
            }
        }
        // cell 8: (1, 0)
        let cell = (pos + 1) as usize;
        let c = cost[cell];
        if c != INF {
            dist8 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 8;
            }
        }
        // cell 9: (-2, 0)
        let cell = (pos - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist5 != INF {
                let nd = dist5 + c;
                if nd < dist9 {
                    dist9 = nd;
                    gateway9 = 5;
                }
            }
            if dist9 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist9 < best_dist) {
                    best_idx = pi;
                    best_dist = dist9;
                    best_fs = gateway9;
                }
            }
        }
        // cell 10: (0, -2)
        let cell = (pos - w2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist6 != INF {
                let nd = dist6 + c;
                if nd < dist10 {
                    dist10 = nd;
                    gateway10 = 6;
                }
            }
            if dist10 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist10 < best_dist) {
                    best_idx = pi;
                    best_dist = dist10;
                    best_fs = gateway10;
                }
            }
        }
        // cell 11: (0, 2)
        let cell = (pos + w2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist7 != INF {
                let nd = dist7 + c;
                if nd < dist11 {
                    dist11 = nd;
                    gateway11 = 7;
                }
            }
            if dist11 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist11 < best_dist) {
                    best_idx = pi;
                    best_dist = dist11;
                    best_fs = gateway11;
                }
            }
        }
        // cell 12: (2, 0)
        let cell = (pos + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist8 != INF {
                let nd = dist8 + c;
                if nd < dist12 {
                    dist12 = nd;
                    gateway12 = 8;
                }
            }
            if dist12 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist12 < best_dist) {
                    best_idx = pi;
                    best_dist = dist12;
                    best_fs = gateway12;
                }
            }
        }
        // cell 13: (-2, -1)
        let cell = (pos - w - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist1 != INF {
                let nd = dist1 + c;
                if nd < dist13 {
                    dist13 = nd;
                    gateway13 = 1;
                }
            }
            if dist5 != INF {
                let nd = dist5 + c;
                if nd < dist13 {
                    dist13 = nd;
                    gateway13 = 5;
                }
            }
            if dist13 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist13 < best_dist) {
                    best_idx = pi;
                    best_dist = dist13;
                    best_fs = gateway13;
                }
            }
        }
        // cell 14: (-2, 1)
        let cell = (pos + w - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist2 != INF {
                let nd = dist2 + c;
                if nd < dist14 {
                    dist14 = nd;
                    gateway14 = 2;
                }
            }
            if dist5 != INF {
                let nd = dist5 + c;
                if nd < dist14 {
                    dist14 = nd;
                    gateway14 = 5;
                }
            }
            if dist14 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist14 < best_dist) {
                    best_idx = pi;
                    best_dist = dist14;
                    best_fs = gateway14;
                }
            }
        }
        // cell 15: (-1, -2)
        let cell = (pos - w2 - 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist1 != INF {
                let nd = dist1 + c;
                if nd < dist15 {
                    dist15 = nd;
                    gateway15 = 1;
                }
            }
            if dist6 != INF {
                let nd = dist6 + c;
                if nd < dist15 {
                    dist15 = nd;
                    gateway15 = 6;
                }
            }
            if dist15 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist15 < best_dist) {
                    best_idx = pi;
                    best_dist = dist15;
                    best_fs = gateway15;
                }
            }
        }
        // cell 16: (-1, 2)
        let cell = (pos + w2 - 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist2 != INF {
                let nd = dist2 + c;
                if nd < dist16 {
                    dist16 = nd;
                    gateway16 = 2;
                }
            }
            if dist7 != INF {
                let nd = dist7 + c;
                if nd < dist16 {
                    dist16 = nd;
                    gateway16 = 7;
                }
            }
            if dist16 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist16 < best_dist) {
                    best_idx = pi;
                    best_dist = dist16;
                    best_fs = gateway16;
                }
            }
        }
        // cell 17: (1, -2)
        let cell = (pos - w2 + 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist3 != INF {
                let nd = dist3 + c;
                if nd < dist17 {
                    dist17 = nd;
                    gateway17 = 3;
                }
            }
            if dist6 != INF {
                let nd = dist6 + c;
                if nd < dist17 {
                    dist17 = nd;
                    gateway17 = 6;
                }
            }
            if dist17 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist17 < best_dist) {
                    best_idx = pi;
                    best_dist = dist17;
                    best_fs = gateway17;
                }
            }
        }
        // cell 18: (1, 2)
        let cell = (pos + w2 + 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist4 != INF {
                let nd = dist4 + c;
                if nd < dist18 {
                    dist18 = nd;
                    gateway18 = 4;
                }
            }
            if dist7 != INF {
                let nd = dist7 + c;
                if nd < dist18 {
                    dist18 = nd;
                    gateway18 = 7;
                }
            }
            if dist18 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist18 < best_dist) {
                    best_idx = pi;
                    best_dist = dist18;
                    best_fs = gateway18;
                }
            }
        }
        // cell 19: (2, -1)
        let cell = (pos - w + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist3 != INF {
                let nd = dist3 + c;
                if nd < dist19 {
                    dist19 = nd;
                    gateway19 = 3;
                }
            }
            if dist8 != INF {
                let nd = dist8 + c;
                if nd < dist19 {
                    dist19 = nd;
                    gateway19 = 8;
                }
            }
            if dist19 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist19 < best_dist) {
                    best_idx = pi;
                    best_dist = dist19;
                    best_fs = gateway19;
                }
            }
        }
        // cell 20: (2, 1)
        let cell = (pos + w + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist4 != INF {
                let nd = dist4 + c;
                if nd < dist20 {
                    dist20 = nd;
                    gateway20 = 4;
                }
            }
            if dist8 != INF {
                let nd = dist8 + c;
                if nd < dist20 {
                    dist20 = nd;
                    gateway20 = 8;
                }
            }
            if dist20 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist20 < best_dist) {
                    best_idx = pi;
                    best_dist = dist20;
                    best_fs = gateway20;
                }
            }
        }
        // cell 21: (-2, -2)
        let cell = (pos - w2 - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist1 != INF {
                let nd = dist1 + c;
                if nd < dist21 {
                    dist21 = nd;
                    gateway21 = 1;
                }
            }
            if dist21 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist21 < best_dist) {
                    best_idx = pi;
                    best_dist = dist21;
                    best_fs = gateway21;
                }
            }
        }
        // cell 22: (-2, 2)
        let cell = (pos + w2 - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist2 != INF {
                let nd = dist2 + c;
                if nd < dist22 {
                    dist22 = nd;
                    gateway22 = 2;
                }
            }
            if dist22 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist22 < best_dist) {
                    best_idx = pi;
                    best_dist = dist22;
                    best_fs = gateway22;
                }
            }
        }
        // cell 23: (2, -2)
        let cell = (pos - w2 + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist3 != INF {
                let nd = dist3 + c;
                if nd < dist23 {
                    dist23 = nd;
                    gateway23 = 3;
                }
            }
            if dist23 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist23 < best_dist) {
                    best_idx = pi;
                    best_dist = dist23;
                    best_fs = gateway23;
                }
            }
        }
        // cell 24: (2, 2)
        let cell = (pos + w2 + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist4 != INF {
                let nd = dist4 + c;
                if nd < dist24 {
                    dist24 = nd;
                    gateway24 = 4;
                }
            }
            if dist24 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist24 < best_dist) {
                    best_idx = pi;
                    best_dist = dist24;
                    best_fs = gateway24;
                }
            }
        }
        // cell 25: (-3, 0)
        let cell = (pos - 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist9 != INF {
                let nd = dist9 + c;
                if nd < dist25 {
                    dist25 = nd;
                    gateway25 = gateway9;
                }
            }
            if dist25 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist25 < best_dist) {
                    best_idx = pi;
                    best_dist = dist25;
                    best_fs = gateway25;
                }
            }
        }
        // cell 26: (0, -3)
        let cell = (pos - w3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist10 != INF {
                let nd = dist10 + c;
                if nd < dist26 {
                    dist26 = nd;
                    gateway26 = gateway10;
                }
            }
            if dist26 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist26 < best_dist) {
                    best_idx = pi;
                    best_dist = dist26;
                    best_fs = gateway26;
                }
            }
        }
        // cell 27: (0, 3)
        let cell = (pos + w3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist11 != INF {
                let nd = dist11 + c;
                if nd < dist27 {
                    dist27 = nd;
                    gateway27 = gateway11;
                }
            }
            if dist27 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist27 < best_dist) {
                    best_idx = pi;
                    best_dist = dist27;
                    best_fs = gateway27;
                }
            }
        }
        // cell 28: (3, 0)
        let cell = (pos + 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist12 != INF {
                let nd = dist12 + c;
                if nd < dist28 {
                    dist28 = nd;
                    gateway28 = gateway12;
                }
            }
            if dist28 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist28 < best_dist) {
                    best_idx = pi;
                    best_dist = dist28;
                    best_fs = gateway28;
                }
            }
        }
        // cell 29: (-3, -1)
        let cell = (pos - w - 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist13 != INF {
                let nd = dist13 + c;
                if nd < dist29 {
                    dist29 = nd;
                    gateway29 = gateway13;
                }
            }
            if dist9 != INF {
                let nd = dist9 + c;
                if nd < dist29 {
                    dist29 = nd;
                    gateway29 = gateway9;
                }
            }
            if dist29 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist29 < best_dist) {
                    best_idx = pi;
                    best_dist = dist29;
                    best_fs = gateway29;
                }
            }
        }
        // cell 30: (-3, 1)
        let cell = (pos + w - 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist14 != INF {
                let nd = dist14 + c;
                if nd < dist30 {
                    dist30 = nd;
                    gateway30 = gateway14;
                }
            }
            if dist9 != INF {
                let nd = dist9 + c;
                if nd < dist30 {
                    dist30 = nd;
                    gateway30 = gateway9;
                }
            }
            if dist30 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist30 < best_dist) {
                    best_idx = pi;
                    best_dist = dist30;
                    best_fs = gateway30;
                }
            }
        }
        // cell 31: (-1, -3)
        let cell = (pos - w3 - 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist15 != INF {
                let nd = dist15 + c;
                if nd < dist31 {
                    dist31 = nd;
                    gateway31 = gateway15;
                }
            }
            if dist10 != INF {
                let nd = dist10 + c;
                if nd < dist31 {
                    dist31 = nd;
                    gateway31 = gateway10;
                }
            }
            if dist31 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist31 < best_dist) {
                    best_idx = pi;
                    best_dist = dist31;
                    best_fs = gateway31;
                }
            }
        }
        // cell 32: (-1, 3)
        let cell = (pos + w3 - 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist16 != INF {
                let nd = dist16 + c;
                if nd < dist32 {
                    dist32 = nd;
                    gateway32 = gateway16;
                }
            }
            if dist11 != INF {
                let nd = dist11 + c;
                if nd < dist32 {
                    dist32 = nd;
                    gateway32 = gateway11;
                }
            }
            if dist32 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist32 < best_dist) {
                    best_idx = pi;
                    best_dist = dist32;
                    best_fs = gateway32;
                }
            }
        }
        // cell 33: (1, -3)
        let cell = (pos - w3 + 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist17 != INF {
                let nd = dist17 + c;
                if nd < dist33 {
                    dist33 = nd;
                    gateway33 = gateway17;
                }
            }
            if dist10 != INF {
                let nd = dist10 + c;
                if nd < dist33 {
                    dist33 = nd;
                    gateway33 = gateway10;
                }
            }
            if dist33 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist33 < best_dist) {
                    best_idx = pi;
                    best_dist = dist33;
                    best_fs = gateway33;
                }
            }
        }
        // cell 34: (1, 3)
        let cell = (pos + w3 + 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist18 != INF {
                let nd = dist18 + c;
                if nd < dist34 {
                    dist34 = nd;
                    gateway34 = gateway18;
                }
            }
            if dist11 != INF {
                let nd = dist11 + c;
                if nd < dist34 {
                    dist34 = nd;
                    gateway34 = gateway11;
                }
            }
            if dist34 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist34 < best_dist) {
                    best_idx = pi;
                    best_dist = dist34;
                    best_fs = gateway34;
                }
            }
        }
        // cell 35: (3, -1)
        let cell = (pos - w + 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist19 != INF {
                let nd = dist19 + c;
                if nd < dist35 {
                    dist35 = nd;
                    gateway35 = gateway19;
                }
            }
            if dist12 != INF {
                let nd = dist12 + c;
                if nd < dist35 {
                    dist35 = nd;
                    gateway35 = gateway12;
                }
            }
            if dist35 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist35 < best_dist) {
                    best_idx = pi;
                    best_dist = dist35;
                    best_fs = gateway35;
                }
            }
        }
        // cell 36: (3, 1)
        let cell = (pos + w + 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist20 != INF {
                let nd = dist20 + c;
                if nd < dist36 {
                    dist36 = nd;
                    gateway36 = gateway20;
                }
            }
            if dist12 != INF {
                let nd = dist12 + c;
                if nd < dist36 {
                    dist36 = nd;
                    gateway36 = gateway12;
                }
            }
            if dist36 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist36 < best_dist) {
                    best_idx = pi;
                    best_dist = dist36;
                    best_fs = gateway36;
                }
            }
        }
        // cell 37: (-3, -2)
        let cell = (pos - w2 - 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist21 != INF {
                let nd = dist21 + c;
                if nd < dist37 {
                    dist37 = nd;
                    gateway37 = gateway21;
                }
            }
            if dist13 != INF {
                let nd = dist13 + c;
                if nd < dist37 {
                    dist37 = nd;
                    gateway37 = gateway13;
                }
            }
            if dist37 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist37 < best_dist) {
                    best_idx = pi;
                    best_dist = dist37;
                    best_fs = gateway37;
                }
            }
        }
        // cell 38: (-3, 2)
        let cell = (pos + w2 - 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist22 != INF {
                let nd = dist22 + c;
                if nd < dist38 {
                    dist38 = nd;
                    gateway38 = gateway22;
                }
            }
            if dist14 != INF {
                let nd = dist14 + c;
                if nd < dist38 {
                    dist38 = nd;
                    gateway38 = gateway14;
                }
            }
            if dist38 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist38 < best_dist) {
                    best_idx = pi;
                    best_dist = dist38;
                    best_fs = gateway38;
                }
            }
        }
        // cell 39: (-2, -3)
        let cell = (pos - w3 - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist21 != INF {
                let nd = dist21 + c;
                if nd < dist39 {
                    dist39 = nd;
                    gateway39 = gateway21;
                }
            }
            if dist15 != INF {
                let nd = dist15 + c;
                if nd < dist39 {
                    dist39 = nd;
                    gateway39 = gateway15;
                }
            }
            if dist39 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist39 < best_dist) {
                    best_idx = pi;
                    best_dist = dist39;
                    best_fs = gateway39;
                }
            }
        }
        // cell 40: (-2, 3)
        let cell = (pos + w3 - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist22 != INF {
                let nd = dist22 + c;
                if nd < dist40 {
                    dist40 = nd;
                    gateway40 = gateway22;
                }
            }
            if dist16 != INF {
                let nd = dist16 + c;
                if nd < dist40 {
                    dist40 = nd;
                    gateway40 = gateway16;
                }
            }
            if dist40 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist40 < best_dist) {
                    best_idx = pi;
                    best_dist = dist40;
                    best_fs = gateway40;
                }
            }
        }
        // cell 41: (2, -3)
        let cell = (pos - w3 + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist23 != INF {
                let nd = dist23 + c;
                if nd < dist41 {
                    dist41 = nd;
                    gateway41 = gateway23;
                }
            }
            if dist17 != INF {
                let nd = dist17 + c;
                if nd < dist41 {
                    dist41 = nd;
                    gateway41 = gateway17;
                }
            }
            if dist41 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist41 < best_dist) {
                    best_idx = pi;
                    best_dist = dist41;
                    best_fs = gateway41;
                }
            }
        }
        // cell 42: (2, 3)
        let cell = (pos + w3 + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist24 != INF {
                let nd = dist24 + c;
                if nd < dist42 {
                    dist42 = nd;
                    gateway42 = gateway24;
                }
            }
            if dist18 != INF {
                let nd = dist18 + c;
                if nd < dist42 {
                    dist42 = nd;
                    gateway42 = gateway18;
                }
            }
            if dist42 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist42 < best_dist) {
                    best_idx = pi;
                    best_dist = dist42;
                    best_fs = gateway42;
                }
            }
        }
        // cell 43: (3, -2)
        let cell = (pos - w2 + 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist23 != INF {
                let nd = dist23 + c;
                if nd < dist43 {
                    dist43 = nd;
                    gateway43 = gateway23;
                }
            }
            if dist19 != INF {
                let nd = dist19 + c;
                if nd < dist43 {
                    dist43 = nd;
                    gateway43 = gateway19;
                }
            }
            if dist43 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist43 < best_dist) {
                    best_idx = pi;
                    best_dist = dist43;
                    best_fs = gateway43;
                }
            }
        }
        // cell 44: (3, 2)
        let cell = (pos + w2 + 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist24 != INF {
                let nd = dist24 + c;
                if nd < dist44 {
                    dist44 = nd;
                    gateway44 = gateway24;
                }
            }
            if dist20 != INF {
                let nd = dist20 + c;
                if nd < dist44 {
                    dist44 = nd;
                    gateway44 = gateway20;
                }
            }
            if dist44 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist44 < best_dist) {
                    best_idx = pi;
                    best_dist = dist44;
                    best_fs = gateway44;
                }
            }
        }
        // cell 45: (-4, 0)
        let cell = (pos - 4) as usize;
        let c = cost[cell];
        if c != INF && dist25 != INF {
            let nd = dist25 + c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && nd < best_dist) {
                best_idx = pi;
                best_dist = nd;
                best_fs = gateway25;
            }
        }
        // cell 46: (0, -4)
        let cell = (pos - w4) as usize;
        let c = cost[cell];
        if c != INF && dist26 != INF {
            let nd = dist26 + c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && nd < best_dist) {
                best_idx = pi;
                best_dist = nd;
                best_fs = gateway26;
            }
        }
        // cell 47: (0, 4)
        let cell = (pos + w4) as usize;
        let c = cost[cell];
        if c != INF && dist27 != INF {
            let nd = dist27 + c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && nd < best_dist) {
                best_idx = pi;
                best_dist = nd;
                best_fs = gateway27;
            }
        }
        // cell 48: (4, 0)
        let cell = (pos + 4) as usize;
        let c = cost[cell];
        if c != INF && dist28 != INF {
            let nd = dist28 + c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && nd < best_dist) {
                best_idx = pi;
                best_dist = nd;
                best_fs = gateway28;
            }
        }
        // cell 49: (-4, -1)
        let cell = (pos - w - 4) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist29 != INF {
                nd = dist29 + c;
                gw_local = gateway29;
            }
            if dist25 != INF {
                let nd1 = dist25 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway25;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 50: (-4, 1)
        let cell = (pos + w - 4) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist30 != INF {
                nd = dist30 + c;
                gw_local = gateway30;
            }
            if dist25 != INF {
                let nd1 = dist25 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway25;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 51: (-1, -4)
        let cell = (pos - w4 - 1) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist31 != INF {
                nd = dist31 + c;
                gw_local = gateway31;
            }
            if dist26 != INF {
                let nd1 = dist26 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway26;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 52: (-1, 4)
        let cell = (pos + w4 - 1) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist32 != INF {
                nd = dist32 + c;
                gw_local = gateway32;
            }
            if dist27 != INF {
                let nd1 = dist27 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway27;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 53: (1, -4)
        let cell = (pos - w4 + 1) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist33 != INF {
                nd = dist33 + c;
                gw_local = gateway33;
            }
            if dist26 != INF {
                let nd1 = dist26 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway26;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 54: (1, 4)
        let cell = (pos + w4 + 1) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist34 != INF {
                nd = dist34 + c;
                gw_local = gateway34;
            }
            if dist27 != INF {
                let nd1 = dist27 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway27;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 55: (4, -1)
        let cell = (pos - w + 4) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist35 != INF {
                nd = dist35 + c;
                gw_local = gateway35;
            }
            if dist28 != INF {
                let nd1 = dist28 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway28;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 56: (4, 1)
        let cell = (pos + w + 4) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist36 != INF {
                nd = dist36 + c;
                gw_local = gateway36;
            }
            if dist28 != INF {
                let nd1 = dist28 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway28;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 57: (-3, -3)
        let cell = (pos - w3 - 3) as usize;
        let c = cost[cell];
        if c != INF && dist21 != INF {
            let nd = dist21 + c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && nd < best_dist) {
                best_idx = pi;
                best_dist = nd;
                best_fs = gateway21;
            }
        }
        // cell 58: (-3, 3)
        let cell = (pos + w3 - 3) as usize;
        let c = cost[cell];
        if c != INF && dist22 != INF {
            let nd = dist22 + c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && nd < best_dist) {
                best_idx = pi;
                best_dist = nd;
                best_fs = gateway22;
            }
        }
        // cell 59: (3, -3)
        let cell = (pos - w3 + 3) as usize;
        let c = cost[cell];
        if c != INF && dist23 != INF {
            let nd = dist23 + c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && nd < best_dist) {
                best_idx = pi;
                best_dist = nd;
                best_fs = gateway23;
            }
        }
        // cell 60: (3, 3)
        let cell = (pos + w3 + 3) as usize;
        let c = cost[cell];
        if c != INF && dist24 != INF {
            let nd = dist24 + c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && nd < best_dist) {
                best_idx = pi;
                best_dist = nd;
                best_fs = gateway24;
            }
        }
        // cell 61: (-4, -2)
        let cell = (pos - w2 - 4) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist37 != INF {
                nd = dist37 + c;
                gw_local = gateway37;
            }
            if dist29 != INF {
                let nd1 = dist29 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway29;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 62: (-4, 2)
        let cell = (pos + w2 - 4) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist38 != INF {
                nd = dist38 + c;
                gw_local = gateway38;
            }
            if dist30 != INF {
                let nd1 = dist30 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway30;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 63: (-2, -4)
        let cell = (pos - w4 - 2) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist39 != INF {
                nd = dist39 + c;
                gw_local = gateway39;
            }
            if dist31 != INF {
                let nd1 = dist31 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway31;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 64: (-2, 4)
        let cell = (pos + w4 - 2) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist40 != INF {
                nd = dist40 + c;
                gw_local = gateway40;
            }
            if dist32 != INF {
                let nd1 = dist32 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway32;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 65: (2, -4)
        let cell = (pos - w4 + 2) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist41 != INF {
                nd = dist41 + c;
                gw_local = gateway41;
            }
            if dist33 != INF {
                let nd1 = dist33 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway33;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 66: (2, 4)
        let cell = (pos + w4 + 2) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist42 != INF {
                nd = dist42 + c;
                gw_local = gateway42;
            }
            if dist34 != INF {
                let nd1 = dist34 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway34;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 67: (4, -2)
        let cell = (pos - w2 + 4) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist43 != INF {
                nd = dist43 + c;
                gw_local = gateway43;
            }
            if dist35 != INF {
                let nd1 = dist35 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway35;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
        // cell 68: (4, 2)
        let cell = (pos + w2 + 4) as usize;
        let c = cost[cell];
        if c != INF {
            let mut nd = INF;
            let mut gw_local: i32 = -1;
            if dist44 != INF {
                nd = dist44 + c;
                gw_local = gateway44;
            }
            if dist36 != INF {
                let nd1 = dist36 + c;
                if nd1 < nd {
                    nd = nd1;
                    gw_local = gateway36;
                }
            }
            if nd != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gw_local;
                }
            }
        }
    } else if 3 <= px && px < w - 3 && 3 <= py && py < h - 3 {
        // cell 1: (-1, -1) [inner-3]
        let cell = (pos - w - 1) as usize;
        let c = cost[cell];
        if c != INF {
            dist1 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 1;
            }
        }
        // cell 2: (-1, 1) [inner-3]
        let cell = (pos + w - 1) as usize;
        let c = cost[cell];
        if c != INF {
            dist2 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 2;
            }
        }
        // cell 3: (1, -1) [inner-3]
        let cell = (pos - w + 1) as usize;
        let c = cost[cell];
        if c != INF {
            dist3 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 3;
            }
        }
        // cell 4: (1, 1) [inner-3]
        let cell = (pos + w + 1) as usize;
        let c = cost[cell];
        if c != INF {
            dist4 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 4;
            }
        }
        // cell 5: (-1, 0) [inner-3]
        let cell = (pos - 1) as usize;
        let c = cost[cell];
        if c != INF {
            dist5 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 5;
            }
        }
        // cell 6: (0, -1) [inner-3]
        let cell = (pos - w) as usize;
        let c = cost[cell];
        if c != INF {
            dist6 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 6;
            }
        }
        // cell 7: (0, 1) [inner-3]
        let cell = (pos + w) as usize;
        let c = cost[cell];
        if c != INF {
            dist7 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 7;
            }
        }
        // cell 8: (1, 0) [inner-3]
        let cell = (pos + 1) as usize;
        let c = cost[cell];
        if c != INF {
            dist8 = c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && c < best_dist) {
                best_idx = pi;
                best_dist = c;
                best_fs = 8;
            }
        }
        // cell 9: (-2, 0) [inner-3]
        let cell = (pos - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist5 != INF {
                let nd = dist5 + c;
                if nd < dist9 {
                    dist9 = nd;
                    gateway9 = 5;
                }
            }
            if dist9 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist9 < best_dist) {
                    best_idx = pi;
                    best_dist = dist9;
                    best_fs = gateway9;
                }
            }
        }
        // cell 10: (0, -2) [inner-3]
        let cell = (pos - w2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist6 != INF {
                let nd = dist6 + c;
                if nd < dist10 {
                    dist10 = nd;
                    gateway10 = 6;
                }
            }
            if dist10 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist10 < best_dist) {
                    best_idx = pi;
                    best_dist = dist10;
                    best_fs = gateway10;
                }
            }
        }
        // cell 11: (0, 2) [inner-3]
        let cell = (pos + w2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist7 != INF {
                let nd = dist7 + c;
                if nd < dist11 {
                    dist11 = nd;
                    gateway11 = 7;
                }
            }
            if dist11 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist11 < best_dist) {
                    best_idx = pi;
                    best_dist = dist11;
                    best_fs = gateway11;
                }
            }
        }
        // cell 12: (2, 0) [inner-3]
        let cell = (pos + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist8 != INF {
                let nd = dist8 + c;
                if nd < dist12 {
                    dist12 = nd;
                    gateway12 = 8;
                }
            }
            if dist12 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist12 < best_dist) {
                    best_idx = pi;
                    best_dist = dist12;
                    best_fs = gateway12;
                }
            }
        }
        // cell 13: (-2, -1) [inner-3]
        let cell = (pos - w - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist1 != INF {
                let nd = dist1 + c;
                if nd < dist13 {
                    dist13 = nd;
                    gateway13 = 1;
                }
            }
            if dist5 != INF {
                let nd = dist5 + c;
                if nd < dist13 {
                    dist13 = nd;
                    gateway13 = 5;
                }
            }
            if dist13 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist13 < best_dist) {
                    best_idx = pi;
                    best_dist = dist13;
                    best_fs = gateway13;
                }
            }
        }
        // cell 14: (-2, 1) [inner-3]
        let cell = (pos + w - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist2 != INF {
                let nd = dist2 + c;
                if nd < dist14 {
                    dist14 = nd;
                    gateway14 = 2;
                }
            }
            if dist5 != INF {
                let nd = dist5 + c;
                if nd < dist14 {
                    dist14 = nd;
                    gateway14 = 5;
                }
            }
            if dist14 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist14 < best_dist) {
                    best_idx = pi;
                    best_dist = dist14;
                    best_fs = gateway14;
                }
            }
        }
        // cell 15: (-1, -2) [inner-3]
        let cell = (pos - w2 - 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist1 != INF {
                let nd = dist1 + c;
                if nd < dist15 {
                    dist15 = nd;
                    gateway15 = 1;
                }
            }
            if dist6 != INF {
                let nd = dist6 + c;
                if nd < dist15 {
                    dist15 = nd;
                    gateway15 = 6;
                }
            }
            if dist15 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist15 < best_dist) {
                    best_idx = pi;
                    best_dist = dist15;
                    best_fs = gateway15;
                }
            }
        }
        // cell 16: (-1, 2) [inner-3]
        let cell = (pos + w2 - 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist2 != INF {
                let nd = dist2 + c;
                if nd < dist16 {
                    dist16 = nd;
                    gateway16 = 2;
                }
            }
            if dist7 != INF {
                let nd = dist7 + c;
                if nd < dist16 {
                    dist16 = nd;
                    gateway16 = 7;
                }
            }
            if dist16 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist16 < best_dist) {
                    best_idx = pi;
                    best_dist = dist16;
                    best_fs = gateway16;
                }
            }
        }
        // cell 17: (1, -2) [inner-3]
        let cell = (pos - w2 + 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist3 != INF {
                let nd = dist3 + c;
                if nd < dist17 {
                    dist17 = nd;
                    gateway17 = 3;
                }
            }
            if dist6 != INF {
                let nd = dist6 + c;
                if nd < dist17 {
                    dist17 = nd;
                    gateway17 = 6;
                }
            }
            if dist17 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist17 < best_dist) {
                    best_idx = pi;
                    best_dist = dist17;
                    best_fs = gateway17;
                }
            }
        }
        // cell 18: (1, 2) [inner-3]
        let cell = (pos + w2 + 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist4 != INF {
                let nd = dist4 + c;
                if nd < dist18 {
                    dist18 = nd;
                    gateway18 = 4;
                }
            }
            if dist7 != INF {
                let nd = dist7 + c;
                if nd < dist18 {
                    dist18 = nd;
                    gateway18 = 7;
                }
            }
            if dist18 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist18 < best_dist) {
                    best_idx = pi;
                    best_dist = dist18;
                    best_fs = gateway18;
                }
            }
        }
        // cell 19: (2, -1) [inner-3]
        let cell = (pos - w + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist3 != INF {
                let nd = dist3 + c;
                if nd < dist19 {
                    dist19 = nd;
                    gateway19 = 3;
                }
            }
            if dist8 != INF {
                let nd = dist8 + c;
                if nd < dist19 {
                    dist19 = nd;
                    gateway19 = 8;
                }
            }
            if dist19 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist19 < best_dist) {
                    best_idx = pi;
                    best_dist = dist19;
                    best_fs = gateway19;
                }
            }
        }
        // cell 20: (2, 1) [inner-3]
        let cell = (pos + w + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist4 != INF {
                let nd = dist4 + c;
                if nd < dist20 {
                    dist20 = nd;
                    gateway20 = 4;
                }
            }
            if dist8 != INF {
                let nd = dist8 + c;
                if nd < dist20 {
                    dist20 = nd;
                    gateway20 = 8;
                }
            }
            if dist20 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist20 < best_dist) {
                    best_idx = pi;
                    best_dist = dist20;
                    best_fs = gateway20;
                }
            }
        }
        // cell 21: (-2, -2) [inner-3]
        let cell = (pos - w2 - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist1 != INF {
                let nd = dist1 + c;
                if nd < dist21 {
                    dist21 = nd;
                    gateway21 = 1;
                }
            }
            if dist21 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist21 < best_dist) {
                    best_idx = pi;
                    best_dist = dist21;
                    best_fs = gateway21;
                }
            }
        }
        // cell 22: (-2, 2) [inner-3]
        let cell = (pos + w2 - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist2 != INF {
                let nd = dist2 + c;
                if nd < dist22 {
                    dist22 = nd;
                    gateway22 = 2;
                }
            }
            if dist22 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist22 < best_dist) {
                    best_idx = pi;
                    best_dist = dist22;
                    best_fs = gateway22;
                }
            }
        }
        // cell 23: (2, -2) [inner-3]
        let cell = (pos - w2 + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist3 != INF {
                let nd = dist3 + c;
                if nd < dist23 {
                    dist23 = nd;
                    gateway23 = 3;
                }
            }
            if dist23 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist23 < best_dist) {
                    best_idx = pi;
                    best_dist = dist23;
                    best_fs = gateway23;
                }
            }
        }
        // cell 24: (2, 2) [inner-3]
        let cell = (pos + w2 + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist4 != INF {
                let nd = dist4 + c;
                if nd < dist24 {
                    dist24 = nd;
                    gateway24 = 4;
                }
            }
            if dist24 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist24 < best_dist) {
                    best_idx = pi;
                    best_dist = dist24;
                    best_fs = gateway24;
                }
            }
        }
        // cell 25: (-3, 0) [inner-3]
        let cell = (pos - 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist9 != INF {
                let nd = dist9 + c;
                if nd < dist25 {
                    dist25 = nd;
                    gateway25 = gateway9;
                }
            }
            if dist25 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist25 < best_dist) {
                    best_idx = pi;
                    best_dist = dist25;
                    best_fs = gateway25;
                }
            }
        }
        // cell 26: (0, -3) [inner-3]
        let cell = (pos - w3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist10 != INF {
                let nd = dist10 + c;
                if nd < dist26 {
                    dist26 = nd;
                    gateway26 = gateway10;
                }
            }
            if dist26 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist26 < best_dist) {
                    best_idx = pi;
                    best_dist = dist26;
                    best_fs = gateway26;
                }
            }
        }
        // cell 27: (0, 3) [inner-3]
        let cell = (pos + w3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist11 != INF {
                let nd = dist11 + c;
                if nd < dist27 {
                    dist27 = nd;
                    gateway27 = gateway11;
                }
            }
            if dist27 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist27 < best_dist) {
                    best_idx = pi;
                    best_dist = dist27;
                    best_fs = gateway27;
                }
            }
        }
        // cell 28: (3, 0) [inner-3]
        let cell = (pos + 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist12 != INF {
                let nd = dist12 + c;
                if nd < dist28 {
                    dist28 = nd;
                    gateway28 = gateway12;
                }
            }
            if dist28 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist28 < best_dist) {
                    best_idx = pi;
                    best_dist = dist28;
                    best_fs = gateway28;
                }
            }
        }
        // cell 29: (-3, -1) [inner-3]
        let cell = (pos - w - 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist13 != INF {
                let nd = dist13 + c;
                if nd < dist29 {
                    dist29 = nd;
                    gateway29 = gateway13;
                }
            }
            if dist9 != INF {
                let nd = dist9 + c;
                if nd < dist29 {
                    dist29 = nd;
                    gateway29 = gateway9;
                }
            }
            if dist29 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist29 < best_dist) {
                    best_idx = pi;
                    best_dist = dist29;
                    best_fs = gateway29;
                }
            }
        }
        // cell 30: (-3, 1) [inner-3]
        let cell = (pos + w - 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist14 != INF {
                let nd = dist14 + c;
                if nd < dist30 {
                    dist30 = nd;
                    gateway30 = gateway14;
                }
            }
            if dist9 != INF {
                let nd = dist9 + c;
                if nd < dist30 {
                    dist30 = nd;
                    gateway30 = gateway9;
                }
            }
            if dist30 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist30 < best_dist) {
                    best_idx = pi;
                    best_dist = dist30;
                    best_fs = gateway30;
                }
            }
        }
        // cell 31: (-1, -3) [inner-3]
        let cell = (pos - w3 - 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist15 != INF {
                let nd = dist15 + c;
                if nd < dist31 {
                    dist31 = nd;
                    gateway31 = gateway15;
                }
            }
            if dist10 != INF {
                let nd = dist10 + c;
                if nd < dist31 {
                    dist31 = nd;
                    gateway31 = gateway10;
                }
            }
            if dist31 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist31 < best_dist) {
                    best_idx = pi;
                    best_dist = dist31;
                    best_fs = gateway31;
                }
            }
        }
        // cell 32: (-1, 3) [inner-3]
        let cell = (pos + w3 - 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist16 != INF {
                let nd = dist16 + c;
                if nd < dist32 {
                    dist32 = nd;
                    gateway32 = gateway16;
                }
            }
            if dist11 != INF {
                let nd = dist11 + c;
                if nd < dist32 {
                    dist32 = nd;
                    gateway32 = gateway11;
                }
            }
            if dist32 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist32 < best_dist) {
                    best_idx = pi;
                    best_dist = dist32;
                    best_fs = gateway32;
                }
            }
        }
        // cell 33: (1, -3) [inner-3]
        let cell = (pos - w3 + 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist17 != INF {
                let nd = dist17 + c;
                if nd < dist33 {
                    dist33 = nd;
                    gateway33 = gateway17;
                }
            }
            if dist10 != INF {
                let nd = dist10 + c;
                if nd < dist33 {
                    dist33 = nd;
                    gateway33 = gateway10;
                }
            }
            if dist33 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist33 < best_dist) {
                    best_idx = pi;
                    best_dist = dist33;
                    best_fs = gateway33;
                }
            }
        }
        // cell 34: (1, 3) [inner-3]
        let cell = (pos + w3 + 1) as usize;
        let c = cost[cell];
        if c != INF {
            if dist18 != INF {
                let nd = dist18 + c;
                if nd < dist34 {
                    dist34 = nd;
                    gateway34 = gateway18;
                }
            }
            if dist11 != INF {
                let nd = dist11 + c;
                if nd < dist34 {
                    dist34 = nd;
                    gateway34 = gateway11;
                }
            }
            if dist34 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist34 < best_dist) {
                    best_idx = pi;
                    best_dist = dist34;
                    best_fs = gateway34;
                }
            }
        }
        // cell 35: (3, -1) [inner-3]
        let cell = (pos - w + 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist19 != INF {
                let nd = dist19 + c;
                if nd < dist35 {
                    dist35 = nd;
                    gateway35 = gateway19;
                }
            }
            if dist12 != INF {
                let nd = dist12 + c;
                if nd < dist35 {
                    dist35 = nd;
                    gateway35 = gateway12;
                }
            }
            if dist35 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist35 < best_dist) {
                    best_idx = pi;
                    best_dist = dist35;
                    best_fs = gateway35;
                }
            }
        }
        // cell 36: (3, 1) [inner-3]
        let cell = (pos + w + 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist20 != INF {
                let nd = dist20 + c;
                if nd < dist36 {
                    dist36 = nd;
                    gateway36 = gateway20;
                }
            }
            if dist12 != INF {
                let nd = dist12 + c;
                if nd < dist36 {
                    dist36 = nd;
                    gateway36 = gateway12;
                }
            }
            if dist36 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist36 < best_dist) {
                    best_idx = pi;
                    best_dist = dist36;
                    best_fs = gateway36;
                }
            }
        }
        // cell 37: (-3, -2) [inner-3]
        let cell = (pos - w2 - 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist21 != INF {
                let nd = dist21 + c;
                if nd < dist37 {
                    dist37 = nd;
                    gateway37 = gateway21;
                }
            }
            if dist13 != INF {
                let nd = dist13 + c;
                if nd < dist37 {
                    dist37 = nd;
                    gateway37 = gateway13;
                }
            }
            if dist37 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist37 < best_dist) {
                    best_idx = pi;
                    best_dist = dist37;
                    best_fs = gateway37;
                }
            }
        }
        // cell 38: (-3, 2) [inner-3]
        let cell = (pos + w2 - 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist22 != INF {
                let nd = dist22 + c;
                if nd < dist38 {
                    dist38 = nd;
                    gateway38 = gateway22;
                }
            }
            if dist14 != INF {
                let nd = dist14 + c;
                if nd < dist38 {
                    dist38 = nd;
                    gateway38 = gateway14;
                }
            }
            if dist38 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist38 < best_dist) {
                    best_idx = pi;
                    best_dist = dist38;
                    best_fs = gateway38;
                }
            }
        }
        // cell 39: (-2, -3) [inner-3]
        let cell = (pos - w3 - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist21 != INF {
                let nd = dist21 + c;
                if nd < dist39 {
                    dist39 = nd;
                    gateway39 = gateway21;
                }
            }
            if dist15 != INF {
                let nd = dist15 + c;
                if nd < dist39 {
                    dist39 = nd;
                    gateway39 = gateway15;
                }
            }
            if dist39 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist39 < best_dist) {
                    best_idx = pi;
                    best_dist = dist39;
                    best_fs = gateway39;
                }
            }
        }
        // cell 40: (-2, 3) [inner-3]
        let cell = (pos + w3 - 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist22 != INF {
                let nd = dist22 + c;
                if nd < dist40 {
                    dist40 = nd;
                    gateway40 = gateway22;
                }
            }
            if dist16 != INF {
                let nd = dist16 + c;
                if nd < dist40 {
                    dist40 = nd;
                    gateway40 = gateway16;
                }
            }
            if dist40 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist40 < best_dist) {
                    best_idx = pi;
                    best_dist = dist40;
                    best_fs = gateway40;
                }
            }
        }
        // cell 41: (2, -3) [inner-3]
        let cell = (pos - w3 + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist23 != INF {
                let nd = dist23 + c;
                if nd < dist41 {
                    dist41 = nd;
                    gateway41 = gateway23;
                }
            }
            if dist17 != INF {
                let nd = dist17 + c;
                if nd < dist41 {
                    dist41 = nd;
                    gateway41 = gateway17;
                }
            }
            if dist41 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist41 < best_dist) {
                    best_idx = pi;
                    best_dist = dist41;
                    best_fs = gateway41;
                }
            }
        }
        // cell 42: (2, 3) [inner-3]
        let cell = (pos + w3 + 2) as usize;
        let c = cost[cell];
        if c != INF {
            if dist24 != INF {
                let nd = dist24 + c;
                if nd < dist42 {
                    dist42 = nd;
                    gateway42 = gateway24;
                }
            }
            if dist18 != INF {
                let nd = dist18 + c;
                if nd < dist42 {
                    dist42 = nd;
                    gateway42 = gateway18;
                }
            }
            if dist42 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist42 < best_dist) {
                    best_idx = pi;
                    best_dist = dist42;
                    best_fs = gateway42;
                }
            }
        }
        // cell 43: (3, -2) [inner-3]
        let cell = (pos - w2 + 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist23 != INF {
                let nd = dist23 + c;
                if nd < dist43 {
                    dist43 = nd;
                    gateway43 = gateway23;
                }
            }
            if dist19 != INF {
                let nd = dist19 + c;
                if nd < dist43 {
                    dist43 = nd;
                    gateway43 = gateway19;
                }
            }
            if dist43 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist43 < best_dist) {
                    best_idx = pi;
                    best_dist = dist43;
                    best_fs = gateway43;
                }
            }
        }
        // cell 44: (3, 2) [inner-3]
        let cell = (pos + w2 + 3) as usize;
        let c = cost[cell];
        if c != INF {
            if dist24 != INF {
                let nd = dist24 + c;
                if nd < dist44 {
                    dist44 = nd;
                    gateway44 = gateway24;
                }
            }
            if dist20 != INF {
                let nd = dist20 + c;
                if nd < dist44 {
                    dist44 = nd;
                    gateway44 = gateway20;
                }
            }
            if dist44 != INF {
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && dist44 < best_dist) {
                    best_idx = pi;
                    best_dist = dist44;
                    best_fs = gateway44;
                }
            }
        }
        // cell 45: (-4, 0) [bounds-checked]
        let nx = px - 4;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF && dist25 != INF {
                let nd = dist25 + c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gateway25;
                }
            }
        }
        // cell 46: (0, -4) [bounds-checked]
        let nx = px;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF && dist26 != INF {
                let nd = dist26 + c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gateway26;
                }
            }
        }
        // cell 47: (0, 4) [bounds-checked]
        let nx = px;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF && dist27 != INF {
                let nd = dist27 + c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gateway27;
                }
            }
        }
        // cell 48: (4, 0) [bounds-checked]
        let nx = px + 4;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF && dist28 != INF {
                let nd = dist28 + c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gateway28;
                }
            }
        }
        // cell 49: (-4, -1) [bounds-checked]
        let nx = px - 4;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist29 != INF {
                    nd = dist29 + c;
                    gw_local = gateway29;
                }
                if dist25 != INF {
                    let nd1 = dist25 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway25;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 50: (-4, 1) [bounds-checked]
        let nx = px - 4;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist30 != INF {
                    nd = dist30 + c;
                    gw_local = gateway30;
                }
                if dist25 != INF {
                    let nd1 = dist25 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway25;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 51: (-1, -4) [bounds-checked]
        let nx = px - 1;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist31 != INF {
                    nd = dist31 + c;
                    gw_local = gateway31;
                }
                if dist26 != INF {
                    let nd1 = dist26 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway26;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 52: (-1, 4) [bounds-checked]
        let nx = px - 1;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist32 != INF {
                    nd = dist32 + c;
                    gw_local = gateway32;
                }
                if dist27 != INF {
                    let nd1 = dist27 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway27;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 53: (1, -4) [bounds-checked]
        let nx = px + 1;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist33 != INF {
                    nd = dist33 + c;
                    gw_local = gateway33;
                }
                if dist26 != INF {
                    let nd1 = dist26 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway26;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 54: (1, 4) [bounds-checked]
        let nx = px + 1;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist34 != INF {
                    nd = dist34 + c;
                    gw_local = gateway34;
                }
                if dist27 != INF {
                    let nd1 = dist27 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway27;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 55: (4, -1) [bounds-checked]
        let nx = px + 4;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist35 != INF {
                    nd = dist35 + c;
                    gw_local = gateway35;
                }
                if dist28 != INF {
                    let nd1 = dist28 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway28;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 56: (4, 1) [bounds-checked]
        let nx = px + 4;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist36 != INF {
                    nd = dist36 + c;
                    gw_local = gateway36;
                }
                if dist28 != INF {
                    let nd1 = dist28 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway28;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 57: (-3, -3) [inner-3]
        let cell = (pos - w3 - 3) as usize;
        let c = cost[cell];
        if c != INF && dist21 != INF {
            let nd = dist21 + c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && nd < best_dist) {
                best_idx = pi;
                best_dist = nd;
                best_fs = gateway21;
            }
        }
        // cell 58: (-3, 3) [inner-3]
        let cell = (pos + w3 - 3) as usize;
        let c = cost[cell];
        if c != INF && dist22 != INF {
            let nd = dist22 + c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && nd < best_dist) {
                best_idx = pi;
                best_dist = nd;
                best_fs = gateway22;
            }
        }
        // cell 59: (3, -3) [inner-3]
        let cell = (pos - w3 + 3) as usize;
        let c = cost[cell];
        if c != INF && dist23 != INF {
            let nd = dist23 + c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && nd < best_dist) {
                best_idx = pi;
                best_dist = nd;
                best_fs = gateway23;
            }
        }
        // cell 60: (3, 3) [inner-3]
        let cell = (pos + w3 + 3) as usize;
        let c = cost[cell];
        if c != INF && dist24 != INF {
            let nd = dist24 + c;
            let pi = path_idx[cell];
            if pi > best_idx || (pi == best_idx && nd < best_dist) {
                best_idx = pi;
                best_dist = nd;
                best_fs = gateway24;
            }
        }
        // cell 61: (-4, -2) [bounds-checked]
        let nx = px - 4;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist37 != INF {
                    nd = dist37 + c;
                    gw_local = gateway37;
                }
                if dist29 != INF {
                    let nd1 = dist29 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway29;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 62: (-4, 2) [bounds-checked]
        let nx = px - 4;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist38 != INF {
                    nd = dist38 + c;
                    gw_local = gateway38;
                }
                if dist30 != INF {
                    let nd1 = dist30 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway30;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 63: (-2, -4) [bounds-checked]
        let nx = px - 2;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist39 != INF {
                    nd = dist39 + c;
                    gw_local = gateway39;
                }
                if dist31 != INF {
                    let nd1 = dist31 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway31;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 64: (-2, 4) [bounds-checked]
        let nx = px - 2;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist40 != INF {
                    nd = dist40 + c;
                    gw_local = gateway40;
                }
                if dist32 != INF {
                    let nd1 = dist32 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway32;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 65: (2, -4) [bounds-checked]
        let nx = px + 2;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist41 != INF {
                    nd = dist41 + c;
                    gw_local = gateway41;
                }
                if dist33 != INF {
                    let nd1 = dist33 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway33;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 66: (2, 4) [bounds-checked]
        let nx = px + 2;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist42 != INF {
                    nd = dist42 + c;
                    gw_local = gateway42;
                }
                if dist34 != INF {
                    let nd1 = dist34 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway34;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 67: (4, -2) [bounds-checked]
        let nx = px + 4;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist43 != INF {
                    nd = dist43 + c;
                    gw_local = gateway43;
                }
                if dist35 != INF {
                    let nd1 = dist35 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway35;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 68: (4, 2) [bounds-checked]
        let nx = px + 4;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist44 != INF {
                    nd = dist44 + c;
                    gw_local = gateway44;
                }
                if dist36 != INF {
                    let nd1 = dist36 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway36;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
    } else {
        // cell 1: (-1, -1)
        let nx = px - 1;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                dist1 = c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && c < best_dist) {
                    best_idx = pi;
                    best_dist = c;
                    best_fs = 1;
                }
            }
        }
        // cell 2: (-1, 1)
        let nx = px - 1;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                dist2 = c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && c < best_dist) {
                    best_idx = pi;
                    best_dist = c;
                    best_fs = 2;
                }
            }
        }
        // cell 3: (1, -1)
        let nx = px + 1;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                dist3 = c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && c < best_dist) {
                    best_idx = pi;
                    best_dist = c;
                    best_fs = 3;
                }
            }
        }
        // cell 4: (1, 1)
        let nx = px + 1;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                dist4 = c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && c < best_dist) {
                    best_idx = pi;
                    best_dist = c;
                    best_fs = 4;
                }
            }
        }
        // cell 5: (-1, 0)
        let nx = px - 1;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                dist5 = c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && c < best_dist) {
                    best_idx = pi;
                    best_dist = c;
                    best_fs = 5;
                }
            }
        }
        // cell 6: (0, -1)
        let nx = px;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                dist6 = c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && c < best_dist) {
                    best_idx = pi;
                    best_dist = c;
                    best_fs = 6;
                }
            }
        }
        // cell 7: (0, 1)
        let nx = px;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                dist7 = c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && c < best_dist) {
                    best_idx = pi;
                    best_dist = c;
                    best_fs = 7;
                }
            }
        }
        // cell 8: (1, 0)
        let nx = px + 1;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                dist8 = c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && c < best_dist) {
                    best_idx = pi;
                    best_dist = c;
                    best_fs = 8;
                }
            }
        }
        // cell 9: (-2, 0)
        let nx = px - 2;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist5 != INF {
                    let nd = dist5 + c;
                    if nd < dist9 {
                        dist9 = nd;
                        gateway9 = 5;
                    }
                }
                if dist9 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist9 < best_dist) {
                        best_idx = pi;
                        best_dist = dist9;
                        best_fs = gateway9;
                    }
                }
            }
        }
        // cell 10: (0, -2)
        let nx = px;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist6 != INF {
                    let nd = dist6 + c;
                    if nd < dist10 {
                        dist10 = nd;
                        gateway10 = 6;
                    }
                }
                if dist10 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist10 < best_dist) {
                        best_idx = pi;
                        best_dist = dist10;
                        best_fs = gateway10;
                    }
                }
            }
        }
        // cell 11: (0, 2)
        let nx = px;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist7 != INF {
                    let nd = dist7 + c;
                    if nd < dist11 {
                        dist11 = nd;
                        gateway11 = 7;
                    }
                }
                if dist11 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist11 < best_dist) {
                        best_idx = pi;
                        best_dist = dist11;
                        best_fs = gateway11;
                    }
                }
            }
        }
        // cell 12: (2, 0)
        let nx = px + 2;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist8 != INF {
                    let nd = dist8 + c;
                    if nd < dist12 {
                        dist12 = nd;
                        gateway12 = 8;
                    }
                }
                if dist12 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist12 < best_dist) {
                        best_idx = pi;
                        best_dist = dist12;
                        best_fs = gateway12;
                    }
                }
            }
        }
        // cell 13: (-2, -1)
        let nx = px - 2;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist1 != INF {
                    let nd = dist1 + c;
                    if nd < dist13 {
                        dist13 = nd;
                        gateway13 = 1;
                    }
                }
                if dist5 != INF {
                    let nd = dist5 + c;
                    if nd < dist13 {
                        dist13 = nd;
                        gateway13 = 5;
                    }
                }
                if dist13 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist13 < best_dist) {
                        best_idx = pi;
                        best_dist = dist13;
                        best_fs = gateway13;
                    }
                }
            }
        }
        // cell 14: (-2, 1)
        let nx = px - 2;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist2 != INF {
                    let nd = dist2 + c;
                    if nd < dist14 {
                        dist14 = nd;
                        gateway14 = 2;
                    }
                }
                if dist5 != INF {
                    let nd = dist5 + c;
                    if nd < dist14 {
                        dist14 = nd;
                        gateway14 = 5;
                    }
                }
                if dist14 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist14 < best_dist) {
                        best_idx = pi;
                        best_dist = dist14;
                        best_fs = gateway14;
                    }
                }
            }
        }
        // cell 15: (-1, -2)
        let nx = px - 1;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist1 != INF {
                    let nd = dist1 + c;
                    if nd < dist15 {
                        dist15 = nd;
                        gateway15 = 1;
                    }
                }
                if dist6 != INF {
                    let nd = dist6 + c;
                    if nd < dist15 {
                        dist15 = nd;
                        gateway15 = 6;
                    }
                }
                if dist15 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist15 < best_dist) {
                        best_idx = pi;
                        best_dist = dist15;
                        best_fs = gateway15;
                    }
                }
            }
        }
        // cell 16: (-1, 2)
        let nx = px - 1;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist2 != INF {
                    let nd = dist2 + c;
                    if nd < dist16 {
                        dist16 = nd;
                        gateway16 = 2;
                    }
                }
                if dist7 != INF {
                    let nd = dist7 + c;
                    if nd < dist16 {
                        dist16 = nd;
                        gateway16 = 7;
                    }
                }
                if dist16 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist16 < best_dist) {
                        best_idx = pi;
                        best_dist = dist16;
                        best_fs = gateway16;
                    }
                }
            }
        }
        // cell 17: (1, -2)
        let nx = px + 1;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist3 != INF {
                    let nd = dist3 + c;
                    if nd < dist17 {
                        dist17 = nd;
                        gateway17 = 3;
                    }
                }
                if dist6 != INF {
                    let nd = dist6 + c;
                    if nd < dist17 {
                        dist17 = nd;
                        gateway17 = 6;
                    }
                }
                if dist17 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist17 < best_dist) {
                        best_idx = pi;
                        best_dist = dist17;
                        best_fs = gateway17;
                    }
                }
            }
        }
        // cell 18: (1, 2)
        let nx = px + 1;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist4 != INF {
                    let nd = dist4 + c;
                    if nd < dist18 {
                        dist18 = nd;
                        gateway18 = 4;
                    }
                }
                if dist7 != INF {
                    let nd = dist7 + c;
                    if nd < dist18 {
                        dist18 = nd;
                        gateway18 = 7;
                    }
                }
                if dist18 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist18 < best_dist) {
                        best_idx = pi;
                        best_dist = dist18;
                        best_fs = gateway18;
                    }
                }
            }
        }
        // cell 19: (2, -1)
        let nx = px + 2;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist3 != INF {
                    let nd = dist3 + c;
                    if nd < dist19 {
                        dist19 = nd;
                        gateway19 = 3;
                    }
                }
                if dist8 != INF {
                    let nd = dist8 + c;
                    if nd < dist19 {
                        dist19 = nd;
                        gateway19 = 8;
                    }
                }
                if dist19 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist19 < best_dist) {
                        best_idx = pi;
                        best_dist = dist19;
                        best_fs = gateway19;
                    }
                }
            }
        }
        // cell 20: (2, 1)
        let nx = px + 2;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist4 != INF {
                    let nd = dist4 + c;
                    if nd < dist20 {
                        dist20 = nd;
                        gateway20 = 4;
                    }
                }
                if dist8 != INF {
                    let nd = dist8 + c;
                    if nd < dist20 {
                        dist20 = nd;
                        gateway20 = 8;
                    }
                }
                if dist20 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist20 < best_dist) {
                        best_idx = pi;
                        best_dist = dist20;
                        best_fs = gateway20;
                    }
                }
            }
        }
        // cell 21: (-2, -2)
        let nx = px - 2;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist1 != INF {
                    let nd = dist1 + c;
                    if nd < dist21 {
                        dist21 = nd;
                        gateway21 = 1;
                    }
                }
                if dist21 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist21 < best_dist) {
                        best_idx = pi;
                        best_dist = dist21;
                        best_fs = gateway21;
                    }
                }
            }
        }
        // cell 22: (-2, 2)
        let nx = px - 2;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist2 != INF {
                    let nd = dist2 + c;
                    if nd < dist22 {
                        dist22 = nd;
                        gateway22 = 2;
                    }
                }
                if dist22 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist22 < best_dist) {
                        best_idx = pi;
                        best_dist = dist22;
                        best_fs = gateway22;
                    }
                }
            }
        }
        // cell 23: (2, -2)
        let nx = px + 2;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist3 != INF {
                    let nd = dist3 + c;
                    if nd < dist23 {
                        dist23 = nd;
                        gateway23 = 3;
                    }
                }
                if dist23 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist23 < best_dist) {
                        best_idx = pi;
                        best_dist = dist23;
                        best_fs = gateway23;
                    }
                }
            }
        }
        // cell 24: (2, 2)
        let nx = px + 2;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist4 != INF {
                    let nd = dist4 + c;
                    if nd < dist24 {
                        dist24 = nd;
                        gateway24 = 4;
                    }
                }
                if dist24 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist24 < best_dist) {
                        best_idx = pi;
                        best_dist = dist24;
                        best_fs = gateway24;
                    }
                }
            }
        }
        // cell 25: (-3, 0)
        let nx = px - 3;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist9 != INF {
                    let nd = dist9 + c;
                    if nd < dist25 {
                        dist25 = nd;
                        gateway25 = gateway9;
                    }
                }
                if dist25 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist25 < best_dist) {
                        best_idx = pi;
                        best_dist = dist25;
                        best_fs = gateway25;
                    }
                }
            }
        }
        // cell 26: (0, -3)
        let nx = px;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist10 != INF {
                    let nd = dist10 + c;
                    if nd < dist26 {
                        dist26 = nd;
                        gateway26 = gateway10;
                    }
                }
                if dist26 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist26 < best_dist) {
                        best_idx = pi;
                        best_dist = dist26;
                        best_fs = gateway26;
                    }
                }
            }
        }
        // cell 27: (0, 3)
        let nx = px;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist11 != INF {
                    let nd = dist11 + c;
                    if nd < dist27 {
                        dist27 = nd;
                        gateway27 = gateway11;
                    }
                }
                if dist27 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist27 < best_dist) {
                        best_idx = pi;
                        best_dist = dist27;
                        best_fs = gateway27;
                    }
                }
            }
        }
        // cell 28: (3, 0)
        let nx = px + 3;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist12 != INF {
                    let nd = dist12 + c;
                    if nd < dist28 {
                        dist28 = nd;
                        gateway28 = gateway12;
                    }
                }
                if dist28 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist28 < best_dist) {
                        best_idx = pi;
                        best_dist = dist28;
                        best_fs = gateway28;
                    }
                }
            }
        }
        // cell 29: (-3, -1)
        let nx = px - 3;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist13 != INF {
                    let nd = dist13 + c;
                    if nd < dist29 {
                        dist29 = nd;
                        gateway29 = gateway13;
                    }
                }
                if dist9 != INF {
                    let nd = dist9 + c;
                    if nd < dist29 {
                        dist29 = nd;
                        gateway29 = gateway9;
                    }
                }
                if dist29 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist29 < best_dist) {
                        best_idx = pi;
                        best_dist = dist29;
                        best_fs = gateway29;
                    }
                }
            }
        }
        // cell 30: (-3, 1)
        let nx = px - 3;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist14 != INF {
                    let nd = dist14 + c;
                    if nd < dist30 {
                        dist30 = nd;
                        gateway30 = gateway14;
                    }
                }
                if dist9 != INF {
                    let nd = dist9 + c;
                    if nd < dist30 {
                        dist30 = nd;
                        gateway30 = gateway9;
                    }
                }
                if dist30 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist30 < best_dist) {
                        best_idx = pi;
                        best_dist = dist30;
                        best_fs = gateway30;
                    }
                }
            }
        }
        // cell 31: (-1, -3)
        let nx = px - 1;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist15 != INF {
                    let nd = dist15 + c;
                    if nd < dist31 {
                        dist31 = nd;
                        gateway31 = gateway15;
                    }
                }
                if dist10 != INF {
                    let nd = dist10 + c;
                    if nd < dist31 {
                        dist31 = nd;
                        gateway31 = gateway10;
                    }
                }
                if dist31 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist31 < best_dist) {
                        best_idx = pi;
                        best_dist = dist31;
                        best_fs = gateway31;
                    }
                }
            }
        }
        // cell 32: (-1, 3)
        let nx = px - 1;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist16 != INF {
                    let nd = dist16 + c;
                    if nd < dist32 {
                        dist32 = nd;
                        gateway32 = gateway16;
                    }
                }
                if dist11 != INF {
                    let nd = dist11 + c;
                    if nd < dist32 {
                        dist32 = nd;
                        gateway32 = gateway11;
                    }
                }
                if dist32 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist32 < best_dist) {
                        best_idx = pi;
                        best_dist = dist32;
                        best_fs = gateway32;
                    }
                }
            }
        }
        // cell 33: (1, -3)
        let nx = px + 1;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist17 != INF {
                    let nd = dist17 + c;
                    if nd < dist33 {
                        dist33 = nd;
                        gateway33 = gateway17;
                    }
                }
                if dist10 != INF {
                    let nd = dist10 + c;
                    if nd < dist33 {
                        dist33 = nd;
                        gateway33 = gateway10;
                    }
                }
                if dist33 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist33 < best_dist) {
                        best_idx = pi;
                        best_dist = dist33;
                        best_fs = gateway33;
                    }
                }
            }
        }
        // cell 34: (1, 3)
        let nx = px + 1;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist18 != INF {
                    let nd = dist18 + c;
                    if nd < dist34 {
                        dist34 = nd;
                        gateway34 = gateway18;
                    }
                }
                if dist11 != INF {
                    let nd = dist11 + c;
                    if nd < dist34 {
                        dist34 = nd;
                        gateway34 = gateway11;
                    }
                }
                if dist34 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist34 < best_dist) {
                        best_idx = pi;
                        best_dist = dist34;
                        best_fs = gateway34;
                    }
                }
            }
        }
        // cell 35: (3, -1)
        let nx = px + 3;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist19 != INF {
                    let nd = dist19 + c;
                    if nd < dist35 {
                        dist35 = nd;
                        gateway35 = gateway19;
                    }
                }
                if dist12 != INF {
                    let nd = dist12 + c;
                    if nd < dist35 {
                        dist35 = nd;
                        gateway35 = gateway12;
                    }
                }
                if dist35 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist35 < best_dist) {
                        best_idx = pi;
                        best_dist = dist35;
                        best_fs = gateway35;
                    }
                }
            }
        }
        // cell 36: (3, 1)
        let nx = px + 3;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist20 != INF {
                    let nd = dist20 + c;
                    if nd < dist36 {
                        dist36 = nd;
                        gateway36 = gateway20;
                    }
                }
                if dist12 != INF {
                    let nd = dist12 + c;
                    if nd < dist36 {
                        dist36 = nd;
                        gateway36 = gateway12;
                    }
                }
                if dist36 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist36 < best_dist) {
                        best_idx = pi;
                        best_dist = dist36;
                        best_fs = gateway36;
                    }
                }
            }
        }
        // cell 37: (-3, -2)
        let nx = px - 3;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist21 != INF {
                    let nd = dist21 + c;
                    if nd < dist37 {
                        dist37 = nd;
                        gateway37 = gateway21;
                    }
                }
                if dist13 != INF {
                    let nd = dist13 + c;
                    if nd < dist37 {
                        dist37 = nd;
                        gateway37 = gateway13;
                    }
                }
                if dist37 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist37 < best_dist) {
                        best_idx = pi;
                        best_dist = dist37;
                        best_fs = gateway37;
                    }
                }
            }
        }
        // cell 38: (-3, 2)
        let nx = px - 3;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist22 != INF {
                    let nd = dist22 + c;
                    if nd < dist38 {
                        dist38 = nd;
                        gateway38 = gateway22;
                    }
                }
                if dist14 != INF {
                    let nd = dist14 + c;
                    if nd < dist38 {
                        dist38 = nd;
                        gateway38 = gateway14;
                    }
                }
                if dist38 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist38 < best_dist) {
                        best_idx = pi;
                        best_dist = dist38;
                        best_fs = gateway38;
                    }
                }
            }
        }
        // cell 39: (-2, -3)
        let nx = px - 2;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist21 != INF {
                    let nd = dist21 + c;
                    if nd < dist39 {
                        dist39 = nd;
                        gateway39 = gateway21;
                    }
                }
                if dist15 != INF {
                    let nd = dist15 + c;
                    if nd < dist39 {
                        dist39 = nd;
                        gateway39 = gateway15;
                    }
                }
                if dist39 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist39 < best_dist) {
                        best_idx = pi;
                        best_dist = dist39;
                        best_fs = gateway39;
                    }
                }
            }
        }
        // cell 40: (-2, 3)
        let nx = px - 2;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist22 != INF {
                    let nd = dist22 + c;
                    if nd < dist40 {
                        dist40 = nd;
                        gateway40 = gateway22;
                    }
                }
                if dist16 != INF {
                    let nd = dist16 + c;
                    if nd < dist40 {
                        dist40 = nd;
                        gateway40 = gateway16;
                    }
                }
                if dist40 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist40 < best_dist) {
                        best_idx = pi;
                        best_dist = dist40;
                        best_fs = gateway40;
                    }
                }
            }
        }
        // cell 41: (2, -3)
        let nx = px + 2;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist23 != INF {
                    let nd = dist23 + c;
                    if nd < dist41 {
                        dist41 = nd;
                        gateway41 = gateway23;
                    }
                }
                if dist17 != INF {
                    let nd = dist17 + c;
                    if nd < dist41 {
                        dist41 = nd;
                        gateway41 = gateway17;
                    }
                }
                if dist41 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist41 < best_dist) {
                        best_idx = pi;
                        best_dist = dist41;
                        best_fs = gateway41;
                    }
                }
            }
        }
        // cell 42: (2, 3)
        let nx = px + 2;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist24 != INF {
                    let nd = dist24 + c;
                    if nd < dist42 {
                        dist42 = nd;
                        gateway42 = gateway24;
                    }
                }
                if dist18 != INF {
                    let nd = dist18 + c;
                    if nd < dist42 {
                        dist42 = nd;
                        gateway42 = gateway18;
                    }
                }
                if dist42 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist42 < best_dist) {
                        best_idx = pi;
                        best_dist = dist42;
                        best_fs = gateway42;
                    }
                }
            }
        }
        // cell 43: (3, -2)
        let nx = px + 3;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist23 != INF {
                    let nd = dist23 + c;
                    if nd < dist43 {
                        dist43 = nd;
                        gateway43 = gateway23;
                    }
                }
                if dist19 != INF {
                    let nd = dist19 + c;
                    if nd < dist43 {
                        dist43 = nd;
                        gateway43 = gateway19;
                    }
                }
                if dist43 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist43 < best_dist) {
                        best_idx = pi;
                        best_dist = dist43;
                        best_fs = gateway43;
                    }
                }
            }
        }
        // cell 44: (3, 2)
        let nx = px + 3;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                if dist24 != INF {
                    let nd = dist24 + c;
                    if nd < dist44 {
                        dist44 = nd;
                        gateway44 = gateway24;
                    }
                }
                if dist20 != INF {
                    let nd = dist20 + c;
                    if nd < dist44 {
                        dist44 = nd;
                        gateway44 = gateway20;
                    }
                }
                if dist44 != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && dist44 < best_dist) {
                        best_idx = pi;
                        best_dist = dist44;
                        best_fs = gateway44;
                    }
                }
            }
        }
        // cell 45: (-4, 0)
        let nx = px - 4;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF && dist25 != INF {
                let nd = dist25 + c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gateway25;
                }
            }
        }
        // cell 46: (0, -4)
        let nx = px;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF && dist26 != INF {
                let nd = dist26 + c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gateway26;
                }
            }
        }
        // cell 47: (0, 4)
        let nx = px;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF && dist27 != INF {
                let nd = dist27 + c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gateway27;
                }
            }
        }
        // cell 48: (4, 0)
        let nx = px + 4;
        let ny = py;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF && dist28 != INF {
                let nd = dist28 + c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gateway28;
                }
            }
        }
        // cell 49: (-4, -1)
        let nx = px - 4;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist29 != INF {
                    nd = dist29 + c;
                    gw_local = gateway29;
                }
                if dist25 != INF {
                    let nd1 = dist25 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway25;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 50: (-4, 1)
        let nx = px - 4;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist30 != INF {
                    nd = dist30 + c;
                    gw_local = gateway30;
                }
                if dist25 != INF {
                    let nd1 = dist25 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway25;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 51: (-1, -4)
        let nx = px - 1;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist31 != INF {
                    nd = dist31 + c;
                    gw_local = gateway31;
                }
                if dist26 != INF {
                    let nd1 = dist26 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway26;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 52: (-1, 4)
        let nx = px - 1;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist32 != INF {
                    nd = dist32 + c;
                    gw_local = gateway32;
                }
                if dist27 != INF {
                    let nd1 = dist27 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway27;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 53: (1, -4)
        let nx = px + 1;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist33 != INF {
                    nd = dist33 + c;
                    gw_local = gateway33;
                }
                if dist26 != INF {
                    let nd1 = dist26 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway26;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 54: (1, 4)
        let nx = px + 1;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist34 != INF {
                    nd = dist34 + c;
                    gw_local = gateway34;
                }
                if dist27 != INF {
                    let nd1 = dist27 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway27;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 55: (4, -1)
        let nx = px + 4;
        let ny = py - 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist35 != INF {
                    nd = dist35 + c;
                    gw_local = gateway35;
                }
                if dist28 != INF {
                    let nd1 = dist28 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway28;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 56: (4, 1)
        let nx = px + 4;
        let ny = py + 1;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist36 != INF {
                    nd = dist36 + c;
                    gw_local = gateway36;
                }
                if dist28 != INF {
                    let nd1 = dist28 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway28;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 57: (-3, -3)
        let nx = px - 3;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF && dist21 != INF {
                let nd = dist21 + c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gateway21;
                }
            }
        }
        // cell 58: (-3, 3)
        let nx = px - 3;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF && dist22 != INF {
                let nd = dist22 + c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gateway22;
                }
            }
        }
        // cell 59: (3, -3)
        let nx = px + 3;
        let ny = py - 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF && dist23 != INF {
                let nd = dist23 + c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gateway23;
                }
            }
        }
        // cell 60: (3, 3)
        let nx = px + 3;
        let ny = py + 3;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF && dist24 != INF {
                let nd = dist24 + c;
                let pi = path_idx[cell];
                if pi > best_idx || (pi == best_idx && nd < best_dist) {
                    best_idx = pi;
                    best_dist = nd;
                    best_fs = gateway24;
                }
            }
        }
        // cell 61: (-4, -2)
        let nx = px - 4;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist37 != INF {
                    nd = dist37 + c;
                    gw_local = gateway37;
                }
                if dist29 != INF {
                    let nd1 = dist29 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway29;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 62: (-4, 2)
        let nx = px - 4;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist38 != INF {
                    nd = dist38 + c;
                    gw_local = gateway38;
                }
                if dist30 != INF {
                    let nd1 = dist30 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway30;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 63: (-2, -4)
        let nx = px - 2;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist39 != INF {
                    nd = dist39 + c;
                    gw_local = gateway39;
                }
                if dist31 != INF {
                    let nd1 = dist31 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway31;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 64: (-2, 4)
        let nx = px - 2;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist40 != INF {
                    nd = dist40 + c;
                    gw_local = gateway40;
                }
                if dist32 != INF {
                    let nd1 = dist32 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway32;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 65: (2, -4)
        let nx = px + 2;
        let ny = py - 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist41 != INF {
                    nd = dist41 + c;
                    gw_local = gateway41;
                }
                if dist33 != INF {
                    let nd1 = dist33 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway33;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 66: (2, 4)
        let nx = px + 2;
        let ny = py + 4;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist42 != INF {
                    nd = dist42 + c;
                    gw_local = gateway42;
                }
                if dist34 != INF {
                    let nd1 = dist34 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway34;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 67: (4, -2)
        let nx = px + 4;
        let ny = py - 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist43 != INF {
                    nd = dist43 + c;
                    gw_local = gateway43;
                }
                if dist35 != INF {
                    let nd1 = dist35 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway35;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
        // cell 68: (4, 2)
        let nx = px + 4;
        let ny = py + 2;
        if 0 <= nx && nx < w && 0 <= ny && ny < h {
            let cell = (ny * w + nx) as usize;
            let c = cost[cell];
            if c != INF {
                let mut nd = INF;
                let mut gw_local: i32 = -1;
                if dist44 != INF {
                    nd = dist44 + c;
                    gw_local = gateway44;
                }
                if dist36 != INF {
                    let nd1 = dist36 + c;
                    if nd1 < nd {
                        nd = nd1;
                        gw_local = gateway36;
                    }
                }
                if nd != INF {
                    let pi = path_idx[cell];
                    if pi > best_idx || (pi == best_idx && nd < best_dist) {
                        best_idx = pi;
                        best_dist = nd;
                        best_fs = gw_local;
                    }
                }
            }
        }
    }
    if best_fs < 0 {
        return pos;
    }
    if best_fs == 1 {
        return pos - w - 1;
    }
    if best_fs == 2 {
        return pos + w - 1;
    }
    if best_fs == 3 {
        return pos - w + 1;
    }
    if best_fs == 4 {
        return pos + w + 1;
    }
    if best_fs == 5 {
        return pos - 1;
    }
    if best_fs == 6 {
        return pos - w;
    }
    if best_fs == 7 {
        return pos + w;
    }
    if best_fs == 8 {
        return pos + 1;
    }
    pos
}
