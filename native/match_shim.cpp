// C interface to LEMON's minimum-cost matching code, for use from Python through ctypes.
// LEMON maximises, so chinese_postman.fast passes weights C - d. Node and blossom duals are
// scaled by lm_scale(). lm_read copies the result into arrays sized by the caller.
#include <lemon/matching.h>
#include <lemon/smart_graph.h>

#include <cstdint>
#include <vector>

using lemon::SmartGraph;
typedef long long Value;
typedef SmartGraph::EdgeMap<Value> Weights;
typedef lemon::MaxWeightedPerfectMatching<SmartGraph, Weights> Matching;

struct Result {
    SmartGraph graph;
    std::vector<SmartGraph::Node> nodes;
    Weights weight;
    Matching matching;
    Result() : weight(graph), matching(graph, weight) {}
};

extern "C" {

void lm_free(void* p) { delete static_cast<Result*>(p); }

// Returns a handle, or null if the graph has no perfect matching.
void* lm_solve(int n, int64_t m, const int* ei, const int* ej, const int64_t* w) {
    Result* r = new Result();
    r->graph.reserveNode(n);
    r->graph.reserveEdge(m);
    r->nodes.resize(n);
    for (int i = 0; i < n; i++) r->nodes[i] = r->graph.addNode();
    for (int64_t k = 0; k < m; k++)
        r->weight[r->graph.addEdge(r->nodes[ei[k]], r->nodes[ej[k]])] = w[k];
    if (!r->matching.run()) {
        delete r;
        return nullptr;
    }
    return r;
}

int lm_scale() { return Matching::dualScale; }

int lm_blossoms(void* p) { return static_cast<Result*>(p)->matching.blossomNum(); }

int64_t lm_members(void* p) {
    Result* r = static_cast<Result*>(p);
    int64_t total = 0;
    for (int k = 0; k < r->matching.blossomNum(); k++) total += r->matching.blossomSize(k);
    return total;
}

void lm_read(void* p, int* mate, int64_t* node, int64_t* z, int* size, int* members) {
    Result* r = static_cast<Result*>(p);
    Matching& M = r->matching;
    for (size_t i = 0; i < r->nodes.size(); i++) {
        mate[i] = r->graph.id(M.mate(r->nodes[i]));
        node[i] = M.nodeValue(r->nodes[i]);
    }
    int64_t at = 0;
    for (int k = 0; k < M.blossomNum(); k++) {
        z[k] = M.blossomValue(k);
        size[k] = M.blossomSize(k);
        for (Matching::BlossomIt it(M, k); it != lemon::INVALID; ++it)
            members[at++] = r->graph.id(static_cast<SmartGraph::Node>(it));
    }
}

}
