// Thin C interface to Kolmogorov's Blossom V, for use from Python via ctypes.
// Blossom V itself is NOT included here: build_blossom5.sh downloads and compiles it.
// Blossom V licence: evaluation and non-commercial research only; see its LICENSE.TXT.
#include "PerfectMatching.h"

extern "C" {

void* pm_new(int n, int edge_cap) {
    PerfectMatching* pm = new PerfectMatching(n, edge_cap);
    pm->options.verbose = false;
    return pm;
}

void pm_free(void* p) { delete (PerfectMatching*)p; }

void pm_add_edges(void* p, int m, const int* ei, const int* ej, const int* w) {
    PerfectMatching* pm = (PerfectMatching*)p;
    for (int k = 0; k < m; k++) pm->AddEdge(ei[k], ej[k], w[k]);
}

void pm_solve(void* p) { ((PerfectMatching*)p)->Solve(); }

// Opens an update round and writes 2*y(i) (incl. blossom duals) for every node.
void pm_start_update(void* p, int n, int* twice_sum) {
    PerfectMatching* pm = (PerfectMatching*)p;
    pm->StartUpdate();
    for (int i = 0; i < n; i++) twice_sum[i] = pm->GetTwiceSum(i);
}

// Adds candidate edges; Blossom V keeps only those with negative slack. Returns how many were added.
int pm_add_new_edges(void* p, int m, const int* ei, const int* ej, const int* w) {
    PerfectMatching* pm = (PerfectMatching*)p;
    int added = 0;
    for (int k = 0; k < m; k++)
        if (pm->AddNewEdge(ei[k], ej[k], w[k], true) >= 0) added++;
    return added;
}

void pm_finish_update(void* p) { ((PerfectMatching*)p)->FinishUpdate(); }

void pm_get_match(void* p, int n, int* mate) {
    PerfectMatching* pm = (PerfectMatching*)p;
    for (int i = 0; i < n; i++) mate[i] = pm->GetMatch(i);
}

}
