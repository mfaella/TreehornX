// the left subtree is also grafted under the right child
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_shape_graft_no_cut(struct Node *root) {
    struct Node *l;
    struct Node *r;
    struct Node *rl;

    if (!root) {
        return;
    }
    l = root->left;
    r = root->right;
    if (!r) {
        return;
    }
    rl = r->left;
    if (rl) {
        return;
    }
    r->left = l;
}
