// swaps the children of the root: still a tree
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_shape_swap(struct Node *root) {
    struct Node *l;
    struct Node *r;
    if (!root) {
        return;
    }
    l = root->left;
    r = root->right;
    root->left = r;
    root->right = l;
}
