// right rotation at the root
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_shape_rotate_right(struct Node *root) {
    struct Node *l;
    struct Node *lr;

    if (!root) {
        return;
    }
    l = root->left;
    if (!l) {
        return;
    }
    lr = l->right;
    root->left = lr;
    l->right = root;
    root = l;
}
