#include <Python.h>
#include <stdlib.h>

#define INF 1000000
#define COST_ROAD 2
#define DIAL_MOD 14
#define NODE_BUDGET 700
#define MAX_NB 8

typedef struct {
  int ni;
  int cost;
} Edge;

typedef struct {
  Edge edges[MAX_NB];
  int count;
} Neighbors;

typedef struct {
  int *data;
  int head;
  int tail;
  int cap;
} Deque;

static void deque_init(Deque *d, int cap) {
  d->data = (int *)malloc(cap * sizeof(int));
  d->head = 0;
  d->tail = 0;
  d->cap = cap;
}

static void deque_free(Deque *d) { free(d->data); }

static void deque_push(Deque *d, int val) {
  d->data[d->tail] = val;
  d->tail++;
  if (d->tail >= d->cap)
    d->tail = 0;
}

static int deque_pop(Deque *d) {
  int val = d->data[d->head];
  d->head++;
  if (d->head >= d->cap)
    d->head = 0;
  return val;
}

static int deque_empty(Deque *d) { return d->head == d->tail; }

static int iabs(int x) { return x < 0 ? -x : x; }
static int imax(int a, int b) { return a > b ? a : b; }

static const int DX[8] = {0, 1, 1, 1, 0, -1, -1, -1};
static const int DY[8] = {-1, -1, 0, 1, 1, 1, 0, -1};

static PyObject *find_path_raw(PyObject *self, PyObject *args) {
  int w, h, sx, sy, gx, gy;
  PyObject *cost_list;

  if (!PyArg_ParseTuple(args, "iiOiiii", &w, &h, &cost_list, &sx, &sy, &gx,
                        &gy))
    return NULL;

  int n = w * h;
  int si = sy * w + sx;
  int gi = gy * w + gx;

  if (si == gi) {
    PyObject *result = PyList_New(1);
    PyList_SET_ITEM(result, 0, PyLong_FromLong(si));
    return result;
  }

  int *cost = (int *)malloc(n * sizeof(int));
  for (int i = 0; i < n; i++) {
    cost[i] = (int)PyLong_AsLong(PyList_GET_ITEM(cost_list, i));
  }

  int *ht = (int *)malloc(n * sizeof(int));
  for (int i = 0; i < n; i++) {
    int ix = i % w, iy = i / w;
    ht[i] = imax(iabs(ix - gx), iabs(iy - gy)) * COST_ROAD;
  }

  Neighbors *nb = (Neighbors *)calloc(n, sizeof(Neighbors));
  for (int i = 0; i < n; i++) {
    if (cost[i] >= INF)
      continue;
    int cx = i % w, cy = i / w;
    for (int d = 0; d < 8; d++) {
      int nx = cx + DX[d], ny = cy + DY[d];
      if (nx < 0 || nx >= w || ny < 0 || ny >= h)
        continue;
      int ni = ny * w + nx;
      int c = cost[ni];
      if (c >= INF)
        continue;
      if (DX[d] != 0 && DY[d] != 0)
        c++;
      Edge *e = &nb[i].edges[nb[i].count++];
      e->ni = ni;
      e->cost = c;
    }
  }

  int *dist = (int *)malloc(n * sizeof(int));
  int *parent = (int *)malloc(n * sizeof(int));
  for (int i = 0; i < n; i++) {
    dist[i] = INF;
    parent[i] = -1;
  }

  int deque_cap = n + 16;
  Deque bk[DIAL_MOD];
  for (int i = 0; i < DIAL_MOD; i++)
    deque_init(&bk[i], deque_cap);

  dist[si] = 0;
  int f0 = ht[si];
  deque_push(&bk[f0 % DIAL_MOD], si);
  int cur_f = f0;
  int emp = 0;
  int exp = 0;
  int best_h = INF;
  int best_node = si;
  int found = -1;

  while (emp < DIAL_MOD) {
    int bi = cur_f % DIAL_MOD;
    if (deque_empty(&bk[bi])) {
      cur_f++;
      emp++;
      continue;
    }
    emp = 0;
    int node = deque_pop(&bk[bi]);
    int fn = dist[node] + ht[node];
    if (fn != cur_f)
      continue;
    if (node == gi) {
      found = gi;
      break;
    }
    exp++;
    int hv = ht[node];
    if (hv < best_h) {
      best_h = hv;
      best_node = node;
    }
    if (exp >= NODE_BUDGET) {
      found = best_node;
      break;
    }
    int gn = dist[node];
    Neighbors *nbs = &nb[node];
    for (int j = 0; j < nbs->count; j++) {
      int ni = nbs->edges[j].ni;
      int nd = gn + nbs->edges[j].cost;
      if (nd < dist[ni]) {
        dist[ni] = nd;
        parent[ni] = node;
        deque_push(&bk[(nd + ht[ni]) % DIAL_MOD], ni);
      }
    }
  }

  if (found == -1 && best_h < INF)
    found = best_node;

  PyObject *result = Py_None;
  if (found >= 0 && (parent[found] != -1 || found == si)) {
    int path_len = 0;
    int cur = found;
    while (cur != -1) {
      path_len++;
      cur = parent[cur];
    }

    result = PyList_New(path_len);
    cur = found;
    for (int i = path_len - 1; i >= 0; i--) {
      PyList_SET_ITEM(result, i, PyLong_FromLong(cur));
      cur = parent[cur];
    }
  } else {
    Py_INCREF(Py_None);
  }

  for (int i = 0; i < DIAL_MOD; i++)
    deque_free(&bk[i]);
  free(cost);
  free(ht);
  free(nb);
  free(dist);
  free(parent);

  return result;
}

static PyMethodDef methods[] = {
    {"find_path_raw", find_path_raw, METH_VARARGS, NULL},
    {NULL, NULL, 0, NULL}};

static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_astar_bucket_c",
                                    NULL, -1, methods};

PyMODINIT_FUNC PyInit__astar_bucket_c(void) { return PyModule_Create(&module); }
