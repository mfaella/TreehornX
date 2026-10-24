// the left grandchild points back to the root
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_grandchild_to_root(struct Node *root) {
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
    ll->right = root;
}
