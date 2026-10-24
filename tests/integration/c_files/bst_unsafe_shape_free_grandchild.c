// frees the left grandchild without unlinking it
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_free_grandchild(struct Node *root) {
    struct Node *l;
    struct Node *ll;

    if (!root) {
        return;
    }
    l = root->left;
    if (!l) {
        return;
    }
    ll = l->left;
    if (!ll) {
        return;
    }
    free(ll);
}
