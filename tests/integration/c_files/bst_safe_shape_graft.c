// moves the right subtree under the left child, when its right field is free
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_shape_graft(struct Node *root) {
    struct Node *l;
    struct Node *r;
    struct Node *lr;

    if (!root) {
        return;
    }
    l = root->left;
    r = root->right;
    if (!l) {
        return;
    }
    lr = l->right;
    if (lr) {
        return;
    }
    l->right = r;
    root->right = NULL;
}
