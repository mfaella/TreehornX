// left rotation at the root
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_shape_rotate_left(struct Node *root) {
    struct Node *r;
    struct Node *rl;

    if (!root) {
        return;
    }
    r = root->right;
    if (!r) {
        return;
    }
    rl = r->left;
    root->right = rl;
    r->left = root;
    root = r;
}
