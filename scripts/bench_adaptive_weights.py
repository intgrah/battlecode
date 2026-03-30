import heapq, sys, types, random, time, math, csv
from pathlib import Path
from collections import deque

cambc_mod = types.ModuleType("cambc")
class _E: EMPTY=0; WALL=1; ORE_TITANIUM=2; ORE_AXIONITE=3
class _P:
    __slots__=("x","y")
    def __init__(s,x,y): s.x=x; s.y=y
    def __eq__(s,o): return isinstance(o,_P) and s.x==o.x and s.y==o.y
    def __hash__(s): return hash((s.x,s.y))
cambc_mod.Environment=_E; cambc_mod.Position=_P
sys.modules["cambc"]=cambc_mod
_u=types.ModuleType("util")
_u.Symmetry=type('S',(),{'ROT':type('S',(),{'name':'ROT'})(),'HOR':type('S',(),{'name':'HOR'})(),'VER':type('S',(),{'name':'VER'})()})()
sys.modules["util"]=_u
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"bots"/"intgrah"/"v50"))
from hardcode.known import KnownMap
from hardcode.map import CORE_A, CORE_B, DIMENSIONS, TILES, decode

_INF=1_000_000; _CR=2; _CE=10; _CU=12; _MAX_EDGE=14
_DIR8=((0,-1),(1,-1),(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1))

def build_nb(w,h):
    n=w*h; nb=[[] for _ in range(n)]
    for i in range(n):
        cx,cy=i%w,i//w
        for dx,dy in _DIR8:
            nx,ny=cx+dx,cy+dy
            if 0<=nx<w and 0<=ny<h: nb[i].append((ny*w+nx,dx!=0 and dy!=0))
    return nb

def build_h(n,w,gi):
    gx,gy=gi%w,gi//w; h=[0]*n
    for i in range(n):
        dx=abs(i%w-gx); dy=abs(i//w-gy); h[i]=(dx if dx>dy else dy)*_CR
    return h

def dijk_gt(cost,nb,n,si):
    dist=[_INF]*n; dist[si]=0; heap=[(0,si)]
    while heap:
        d,node=heapq.heappop(heap)
        if d>dist[node]: continue
        for ni,diag in nb[node]:
            c=cost[ni];
            if c>=_INF: continue
            if diag: c+=1
            nd=d+c
            if nd<dist[ni]: dist[ni]=nd; heapq.heappush(heap,(nd,ni))
    return dist

def val_path(cost,w,path,si,gi):
    if not path or path[0]!=si or path[-1]!=gi: return -1
    total=0
    for i in range(len(path)-1):
        x0,y0=path[i]%w,path[i]//w; x1,y1=path[i+1]%w,path[i+1]//w
        dx,dy=abs(x1-x0),abs(y1-y0)
        if dx>1 or dy>1: return -1
        c=cost[path[i+1]]
        if c>=_INF: return -1
        if dx!=0 and dy!=0: c+=1
        total+=c
    return total

def place_roads(base_cost, nb, n, w, h, true_tiles, core_a, core_b):
    cost = list(base_cost)
    ca = core_a.y * w + core_a.x
    # Find ore-adjacent passable tiles
    ores = [i for i in range(n) if true_tiles[i] in (2, 3)]
    ore_adj = set()
    for oi in ores:
        for ni, _ in nb[oi]:
            if base_cost[ni] < _INF:
                ore_adj.add(ni)
    targets = list(ore_adj)[:5]
    # Midpoint toward enemy
    mx = (core_a.x + core_b.x) // 2
    my = (core_a.y + core_b.y) // 2
    mi = my * w + mx
    if base_cost[mi] < _INF:
        targets.append(mi)
    # Quarter-point
    qx = (core_a.x * 3 + core_b.x) // 4
    qy = (core_a.y * 3 + core_b.y) // 4
    qi = qy * w + qx
    if base_cost[qi] < _INF:
        targets.append(qi)

    road_tiles = set()
    for target in targets:
        dist = [_INF] * n; parent = [-1] * n; dist[ca] = 0
        heap = [(0, ca)]
        while heap:
            d, node = heapq.heappop(heap)
            if d > dist[node]: continue
            if node == target: break
            for ni, diag in nb[node]:
                c = base_cost[ni]
                if c >= _INF: continue
                if diag: c += 1
                nd = d + c
                if nd < dist[ni]:
                    dist[ni] = nd; parent[ni] = node
                    heapq.heappush(heap, (nd, ni))
        if dist[target] < _INF:
            cur = target
            while cur != -1 and cur != ca:
                road_tiles.add(cur)
                cur = parent[cur]
    for ri in road_tiles:
        cost[ri] = _CR
    return cost, len(road_tiles)

# Algorithms
def astar_w(cost, nb, n, w, si, gi, ht, g, p, weight):
    if si==gi: return [si], 0
    g[si]=0; touched=[si]; heap=[(ht[si]*weight,si)]; exp=0; result=None
    while heap:
        f,node=heapq.heappop(heap)
        if node==gi:
            path=[]; cur=gi
            while cur!=-1: path.append(cur); cur=p[cur]
            path.reverse(); result=path; break
        if f>g[node]+ht[node]*weight: continue
        exp+=1; gn=g[node]
        for ni,diag in nb[node]:
            c=cost[ni]
            if c>=_INF: continue
            if diag: c+=1
            nd=gn+c
            if nd<g[ni]:
                if g[ni]==_INF: touched.append(ni)
                g[ni]=nd; p[ni]=node; heapq.heappush(heap,(nd+ht[ni]*weight,ni))
    for ti in touched: g[ti]=_INF; p[ti]=-1
    return result, exp

def dial_ex(cost, nb, n, si, gi, dist, p):
    if si==gi: return [si], 0
    dist[si]=0; touched=[si]; bk=[deque() for _ in range(_MAX_EDGE)]
    bk[0].append(si); cur=0; exp=0; result=None; emp=0
    while emp<_MAX_EDGE:
        bi=cur%_MAX_EDGE
        if not bk[bi]: cur+=1; emp+=1; continue
        emp=0; node=bk[bi].popleft()
        if dist[node]!=cur: continue
        if node==gi:
            path=[]; c2=gi
            while c2!=-1: path.append(c2); c2=p[c2]
            path.reverse(); result=path; break
        exp+=1
        for ni,diag in nb[node]:
            c=cost[ni]
            if c>=_INF: continue
            if diag: c+=1
            nd=cur+c
            if nd<dist[ni]:
                if dist[ni]==_INF: touched.append(ni)
                dist[ni]=nd; p[ni]=node; bk[nd%_MAX_EDGE].append(ni)
    for ti in touched: dist[ti]=_INF; p[ti]=-1
    return result, exp

def greedy(cost, nb, n, si, gi, ht, p, v):
    if si==gi: return [si], 0
    touched=[si]; v[si]=1; heap=[(ht[si],si)]; exp=0; result=None
    while heap:
        _,node=heapq.heappop(heap)
        if node==gi:
            path=[]; cur=gi
            while cur!=-1: path.append(cur); cur=p[cur]
            path.reverse(); result=path; break
        exp+=1
        for ni,diag in nb[node]:
            if cost[ni]>=_INF: continue
            if not v[ni]:
                v[ni]=1; touched.append(ni); p[ni]=node
                heapq.heappush(heap,(ht[ni],ni))
    for ti in touched: v[ti]=0; p[ti]=-1
    return result, exp

def adaptive_w(cost, n):
    total=0; count=0
    for i in range(n):
        c=cost[i]
        if 0<c<_INF: total+=c; count+=1
    return max(1, int((total/count)/_CR)) if count else 1

def min_w(cost, n):
    mn=_INF
    for i in range(n):
        c=cost[i]
        if 0<c<mn: mn=c
    return max(1, mn//_CR) if mn<_INF else 1

TECHS = [
    ("dial_exact", "dial"),
    ("astar_w1", "w", 1),
    ("astar_w3", "w", 3),
    ("astar_w5", "w", 5),
    ("astar_w_avg", "w", "avg"),
    ("astar_w_min", "w", "min"),
    ("greedy", "greedy"),
]

out = Path(__file__).resolve().parent / "bench_adaptive_weights.csv"
f = open(out, "w", newline="")
wr = csv.writer(f)
wr.writerow(["map","width","height","n","passable","scenario","n_roads",
             "technique","weight","t_p50","t_p95","t_max","t_mean",
             "exp_mean","o_mean","o_p95","o_max","nopath"])

for km in KnownMap:
    w,h=DIMENSIONS[km]; n=w*h
    env=decode(TILES[km](),n); tt=[int(e) for e in env]
    base_cost=[_INF if tt[i] in (1,2,3) else _CE for i in range(n)]
    nb=build_nb(w,h)
    passable=[i for i in range(n) if base_cost[i]<_INF]
    ca,cb=CORE_A[km],CORE_B[km]
    rng=random.Random(42)
    pairs=[(rng.choice(passable),rng.choice(passable)) for _ in range(200)]

    for scenario in ["no_roads","with_roads"]:
        if scenario=="no_roads":
            cost=list(base_cost); nr=0
        else:
            cost, nr = place_roads(base_cost,nb,n,w,h,tt,ca,cb)

        gt_cache={}
        g_a=[_INF]*n; p_a=[-1]*n; d_a=[_INF]*n; v_a=[0]*n

        for tech_entry in TECHS:
            tname=tech_entry[0]; ttype=tech_entry[1]
            if ttype=="w":
                raw_w=tech_entry[2]
                if raw_w=="avg": actual_w=adaptive_w(cost,n)
                elif raw_w=="min": actual_w=min_w(cost,n)
                else: actual_w=raw_w
            else:
                actual_w=0

            times=[]; exps=[]; opts=[]; nop=0
            for si,gi in pairs:
                if si not in gt_cache: gt_cache[si]=dijk_gt(cost,nb,n,si)
                gd=gt_cache[si][gi]
                if gd>=_INF: continue
                ht=build_h(n,w,gi)
                t0=time.perf_counter()
                if ttype=="dial": path,exp=dial_ex(cost,nb,n,si,gi,d_a,p_a)
                elif ttype=="greedy": path,exp=greedy(cost,nb,n,si,gi,ht,p_a,v_a)
                else: path,exp=astar_w(cost,nb,n,w,si,gi,ht,g_a,p_a,actual_w)
                elapsed=(time.perf_counter()-t0)*1e6
                times.append(elapsed); exps.append(exp)
                if path and path[-1]==gi:
                    pc=val_path(cost,w,path,si,gi)
                    if pc>0: opts.append(pc/gd)
                else: nop+=1

            if not times: continue
            s=sorted(times); nt=len(s)
            os=sorted(opts) if opts else [0]; no=len(os)
            wr.writerow([
                km.value,w,h,n,len(passable),scenario,nr,tname,actual_w,
                round(s[nt//2],1), round(s[int(nt*.95)],1), round(s[-1],1),
                round(sum(s)/nt,1), round(sum(exps)/len(exps)),
                round(sum(opts)/len(opts),4) if opts else 0,
                round(os[int(no*.95)],4) if no>1 else 0,
                round(os[-1],4) if os[0]>0 else 0, nop
            ])

    print(f"  {km.value}",file=sys.stderr,flush=True)

f.close()
print(f"Wrote {out}",file=sys.stderr)

# Summary
rows=list(csv.DictReader(open(out)))
from collections import defaultdict
for scenario in ["no_roads","with_roads"]:
    print(f"\n{'='*110}")
    print(f"  {scenario.upper()}")
    print(f"{'='*110}")
    print(f"{'Tech':<16} {'w':>4} {'AvgExp':>7} {'MedMax':>7} {'MaxMax':>8} {'>=2ms':>6} {'>=1ms':>6} {'OptAvg':>7} {'Opt95':>6} {'OptMax':>7} {'NP':>5}")
    print("-"*100)
    for tname,*_ in TECHS:
        rs=[r for r in rows if r['scenario']==scenario and r['technique']==tname]
        if not rs: continue
        nm=len(rs)
        mx=sorted(float(r['t_max']) for r in rs)
        o2=sum(1 for m in mx if m>2000)
        o1=sum(1 for m in mx if m>1000)
        avg_e=sum(float(r['exp_mean']) for r in rs)/nm
        om=[float(r['o_max']) for r in rs if float(r['o_max'])>0]
        oa=[float(r['o_mean']) for r in rs if float(r['o_mean'])>0]
        op=[float(r['o_p95']) for r in rs if float(r['o_p95'])>0]
        ws=set(r['weight'] for r in rs)
        w_str=ws.pop() if len(ws)==1 else f"{min(int(x) for x in ws)}-{max(int(x) for x in ws)}"
        nop=sum(int(r['nopath']) for r in rs)
        print(f"{tname:<16} {w_str:>4} {avg_e:>7.0f} {mx[nm//2]:>6.0f}u {max(mx):>7.0f}u {o2:>4}/38 {o1:>4}/38 "
              f"{sum(oa)/len(oa) if oa else 0:>7.4f} {sorted(op)[len(op)//2] if op else 0:>6.4f} "
              f"{max(om) if om else 0:>7.4f} {nop:>5}")
